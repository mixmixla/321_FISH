"""System-admin member removal retires only the target UID's group state."""
from copy import deepcopy
from dataclasses import replace
import sys
import threading

from config import CFG
from server import Hub, Session
from test_group_kick_scope import cleanup, running, shutdown, assert_stopped


def make_session(hub, nick, kind='tcp'):
    frames = []
    session = Session(0, nick, kind, '127.0.0.1',
                      lambda frame, *_, frames=frames: frames.append(frame))
    assert hub._attach(session)
    return session, frames


def test_admin_remove_notifies_every_target_session_and_preserves_other_group(tmp_path, monkeypatch):
    hub = Hub(cfg=replace(CFG, admin_pwd='', audit_dir=str(tmp_path/'audit'),
                          web_files_dir=str(tmp_path/'web')))
    try:
        owner, owner_frames = make_session(hub, 'admin-remove-owner')
        target, target_frames = make_session(hub, 'admin-remove-target')
        web, web_frames = make_session(hub, 'admin-remove-target', 'web')
        observer, observer_frames = make_session(hub, 'admin-remove-observer')
        admin, admin_frames = make_session(hub, 'admin-remove-admin')
        admin.is_admin = True
        hub.web_tokens['synthetic-remove-token'] = web
        for name in ('remove-one', 'keep-one'):
            hub._on_group_create(owner, {'name': name, 'public': True})
            hub._on_group_join(target, {'gid': max(hub.groups)})
        removed, kept = sorted(hub.groups)
        hub.groups[removed]['admins'].add(target.uid)
        hub.groups[removed]['mutes'][target.uid] = 12345
        hub.voice_rooms[f'group:{removed}'] = {target.uid: {'port': 30001},
                                               owner.uid: {'port': 30002}}
        hub.voice_rooms[f'group:{kept}'] = {target.uid: {'port': 30003}}
        audit = []
        monkeypatch.setattr(hub.audit, 'log', lambda **record: audit.append(record))
        for frames in (owner_frames, target_frames, web_frames, observer_frames, admin_frames):
            frames.clear()
        before = hub._group_state_revision
        hub._on_admin_group_set(admin, {'gid': removed, 'op': 'remove', 'uid': target.uid})
        assert target.uid not in hub.groups[removed]['members']
        assert target.uid not in hub.groups[removed]['admins']
        assert target.uid not in hub.groups[removed]['mutes']
        assert target.uid in hub.groups[kept]['members']
        assert owner.uid in hub.voice_rooms[f'group:{removed}']
        assert target.uid not in hub.voice_rooms[f'group:{removed}']
        assert target.uid in hub.voice_rooms[f'group:{kept}']
        assert hub.session_by_token('synthetic-remove-token') is web
        assert all(hub._session_is_active(s) for s in (owner, target, web, observer, admin))
        for frames in (target_frames, web_frames):
            removals = [f for f in frames if f.get('code') == 'group_removed']
            assert len(removals) == 1
            assert removals[0]['gid'] == removed
            assert type(removals[0]['group_revision']) is int
            assert before < removals[0]['group_revision'] <= hub._group_state_revision
        assert not any(f.get('code') == 'group_removed' for frames in
                       (owner_frames, observer_frames, admin_frames) for f in frames)
        assert len([r for r in audit if r.get('type') == 'admin_group_remove']) == 1
    finally:
        cleanup(sys.exception(), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))


def test_admin_remove_last_member_dissolves_and_notifies_sessions(tmp_path):
    hub = Hub(cfg=replace(CFG, admin_pwd='', audit_dir=str(tmp_path/'audit'),
                          web_files_dir=str(tmp_path/'web')))
    try:
        target, first_frames = make_session(hub, 'last-target')
        _, second_frames = make_session(hub, 'last-target', 'web')
        admin, _ = make_session(hub, 'last-admin')
        admin.is_admin = True
        hub._on_group_create(target, {'name': 'last', 'public': True})
        gid = next(iter(hub.groups))
        hub.voice_rooms[f'group:{gid}'] = {target.uid: {'port': 30001}}
        first_frames.clear()
        second_frames.clear()
        hub._on_admin_group_set(admin, {'gid': gid, 'op': 'remove', 'uid': target.uid})
        assert gid not in hub.groups
        assert f'group:{gid}' not in hub.voice_rooms
        for frames in (first_frames, second_frames):
            assert len([f for f in frames if f.get('code') == 'group_removed'
                        and f.get('gid') == gid]) == 1
    finally:
        cleanup(sys.exception(), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))


def test_admin_remove_owner_transfers_and_send_failure_does_not_block_other_session(tmp_path):
    hub = Hub(cfg=replace(CFG, admin_pwd='', audit_dir=str(tmp_path/'audit'),
                          web_files_dir=str(tmp_path/'web')))
    try:
        owner, owner_frames = make_session(hub, 'transfer-owner')
        same, same_frames = make_session(hub, 'transfer-owner', 'web')
        member, _ = make_session(hub, 'transfer-member')
        admin, _ = make_session(hub, 'transfer-admin')
        admin.is_admin = True
        hub._on_group_create(owner, {'name': 'transfer', 'public': True})
        gid = next(iter(hub.groups))
        hub._on_group_join(member, {'gid': gid})
        owner_frames.clear()
        same_frames.clear()
        original_send = owner.send

        def failing_send(frame, *args):
            if frame.get('code') == 'group_removed':
                raise OSError('synthetic target transport failure')
            return original_send(frame, *args)

        owner.send = failing_send
        hub._on_admin_group_set(admin, {'gid': gid, 'op': 'remove', 'uid': owner.uid})
        assert hub.groups[gid]['owner'] == member.uid
        assert set(hub.groups[gid]['members']) == {member.uid}
        assert len([f for f in same_frames if f.get('code') == 'group_removed']) == 1
        assert hub._session_is_active(same)
    finally:
        cleanup(sys.exception(), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))


def test_admin_remove_rejections_leave_group_and_revision_unchanged(tmp_path, monkeypatch):
    hub = Hub(cfg=replace(CFG, admin_pwd='', audit_dir=str(tmp_path/'audit'),
                          web_files_dir=str(tmp_path/'web')))
    probe_workers = []
    try:
        owner, _ = make_session(hub, 'reject-owner')
        absent, _ = make_session(hub, 'reject-absent')
        admin, admin_frames = make_session(hub, 'reject-admin')
        admin.is_admin = True
        hub._on_group_create(owner, {'name': 'reject', 'public': True})
        gid = next(iter(hub.groups))
        before_revision = hub._group_state_revision
        before_members = dict(hub.groups[gid]['members'])
        audit = []
        monkeypatch.setattr(hub.audit, 'log', lambda **record: audit.append(record))
        original_error = hub._error
        probes = []

        def error_unlocked(sess, code, message, *args, **kwargs):
            acquired = threading.Event()

            def probe():
                if hub.lock.acquire(timeout=2):
                    try:
                        acquired.set()
                    finally:
                        hub.lock.release()

            worker = threading.Thread(target=probe, name='admin-remove-error-lock-probe')
            probe_workers.append(worker)
            worker.start()
            probes.append(acquired.wait(.5))
            return original_error(sess, code, message, *args, **kwargs)

        monkeypatch.setattr(hub, '_error', error_unlocked)
        hub._on_admin_group_set(owner, {'gid': gid, 'op': 'remove', 'uid': owner.uid})
        hub._on_admin_group_set(admin, {'gid': gid, 'op': 'remove', 'uid': absent.uid})
        hub._on_admin_group_set(admin, {'gid': gid+100, 'op': 'remove', 'uid': owner.uid})
        assert [f['code'] for f in admin_frames if f.get('t') == 'error'] == ['member', 'group']
        assert probes == [True, True, True]
        assert hub._group_state_revision == before_revision
        assert hub.groups[gid]['members'] == before_members
        assert not audit
    finally:
        cleanup(sys.exception(), *(lambda worker=w: worker.join(3) for w in probe_workers),
                lambda: assert_stopped(*probe_workers), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))


def test_concurrent_admin_remove_same_uid_is_single_decision(tmp_path, monkeypatch):
    hub = Hub(cfg=replace(CFG, admin_pwd='', audit_dir=str(tmp_path/'audit'),
                          web_files_dir=str(tmp_path/'web')))
    workers, errors = [], []
    gate = threading.Barrier(2)
    original_lock = hub.lock
    try:
        owner, _ = make_session(hub, 'race-owner')
        target, target_frames = make_session(hub, 'race-target')
        admin, admin_frames = make_session(hub, 'race-admin')
        admin.is_admin = True
        hub._on_group_create(owner, {'name': 'race', 'public': True})
        gid = next(iter(hub.groups))
        hub._on_group_join(target, {'gid': gid})
        target_frames.clear()
        admin_frames.clear()
        before = hub._group_state_revision
        audit = []
        monkeypatch.setattr(hub.audit, 'log', lambda **record: audit.append(record))

        class MutationGate:
            def __init__(self, lock):
                self.lock = lock
                self.guard = threading.Lock()
                self.entries = {}
                self.reached = set()

            def __enter__(self):
                current = threading.current_thread()
                with self.guard:
                    count = self.entries.get(current, 0) + 1
                    self.entries[current] = count
                    at_write = current in workers and count == 2
                    if at_write:
                        self.reached.add(current)
                if at_write:
                    gate.wait(3)
                return self.lock.__enter__()

            def __exit__(self, *args):
                return self.lock.__exit__(*args)

            def acquire(self, *args, **kwargs):
                return self.lock.acquire(*args, **kwargs)

            def release(self):
                return self.lock.release()

        wrapper = MutationGate(original_lock)
        hub.lock = wrapper

        def remove():
            try:
                hub._on_admin_group_set(admin, {'gid': gid, 'op': 'remove', 'uid': target.uid})
            except BaseException as exc:
                errors.append(exc)

        workers = [threading.Thread(target=remove, name=f'admin-remove-{i}')
                   for i in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)
        assert_stopped(*workers)
        assert wrapper.reached == set(workers)
        assert all(wrapper.entries[w] >= 2 for w in workers)
        assert not errors, errors
        assert target.uid not in hub.groups[gid]['members']
        assert len([r for r in audit if r.get('type') == 'admin_group_remove']) == 1
        assert len([f for f in target_frames if f.get('code') == 'group_removed']) == 1
        assert len([f for f in admin_frames if f.get('code') == 'member']) == 1
        assert hub._group_state_revision == before + 2
    finally:
        hub.lock = original_lock
        cleanup(sys.exception(), gate.abort,
                *(lambda worker=worker: worker.join(5) for worker in workers),
                lambda: assert_stopped(*workers), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))


def test_admin_remove_clears_two_real_cores_without_rejoining(running, monkeypatch):
    hub, spawn = running
    owner, owner_events = spawn('admin-core-owner')
    first, first_events = spawn('admin-core-target')
    gids = []
    for name in ('adm-removed', 'adm-kept'):
        assert owner.create_group(name, public=True)
        gid = owner_events.wait('group_state', pred=lambda e: e.get('name') == name)['gid']
        gids.append(gid)
        assert first.join_group(gid)
        assert first_events.wait('group_state', pred=lambda e: e.get('gid') == gid
                                 and any(m['uid'] == first.uid for m in e['members']))
    removed, kept = gids
    second, second_events = spawn('admin-core-target')
    for gid in gids:
        assert second.join_group(gid)
        assert second_events.wait('error', pred=lambda e: e.get('code') == 'group')
    assert first.uid == second.uid
    material = []
    for core in (first, second):
        core.group_invites[removed] = 'synthetic-invite'
        for gid in gids:
            core.e2ee.new_group_epoch(gid)
            core.e2ee.set_peer_sender_key(gid, owner.uid, b'p' * 32, 1)
            core._e2ee_groups.add(gid)
            core._e2ee_group_members[gid] = frozenset((core.uid, owner.uid))
        material.append(deepcopy((core.e2ee._groups[kept], core.e2ee._my_sk[kept],
                                  core.e2ee._my_send[kept])))
    admin, _ = make_session(hub, 'admin-core-admin')
    admin.is_admin = True
    epochs = (first.connection_epoch, second.connection_epoch)
    hub._on_admin_group_set(admin, {'gid': removed, 'op': 'remove', 'uid': first.uid})
    for events in (first_events, second_events):
        assert events.wait('error', pred=lambda e: e.get('code') == 'group_removed'
                           and e.get('gid') == removed)
    for core, expected in zip((first, second), material):
        assert core.connected and not core._manual_login_required
        assert removed not in core._joined_groups
        assert removed not in core.group_members and removed not in core.group_invites
        assert kept in core._joined_groups
        assert not core.group_e2ee_on(removed) and removed not in core._e2ee_group_members
        assert all(removed not in mapping for mapping in
                   (core.e2ee._groups, core.e2ee._my_sk, core.e2ee._my_send))
        assert core.e2ee.peer_sender_entry(removed, owner.uid) is None
        assert core.group_e2ee_on(kept)
        assert expected == (core.e2ee._groups[kept], core.e2ee._my_sk[kept],
                            core.e2ee._my_send[kept])
    assert (first.connection_epoch, second.connection_epoch) == epochs
    welcome_done = threading.Event()
    original_welcome = second._on_welcome

    def on_welcome(frame):
        original_welcome(frame)
        welcome_done.set()

    monkeypatch.setattr(second, '_on_welcome', on_welcome)
    second.drop()
    assert second_events.wait('welcome', timeout=6,
                              pred=lambda e: e.get('_connection_epoch', 0) > epochs[1])
    assert welcome_done.wait(3)
    assert second.send_chat('admin-remove-order-barrier')
    assert owner_events.wait('chat', pred=lambda e: e.get('text') == 'admin-remove-order-barrier')
    assert first.uid not in hub.groups[removed]['members']
    assert first.uid in hub.groups[kept]['members']
    assert second.send_group('kept-after-admin-remove', kept)
    assert owner_events.wait('chat', pred=lambda e: e.get('to') == kept
                             and e.get('text') == 'kept-after-admin-remove')
    assert second.join_group(removed)
    assert second_events.wait('group_state', pred=lambda e: e.get('gid') == removed
                              and any(m['uid'] == second.uid for m in e['members']))
