"""Explicit admin dissolution retires every former member's group state."""
from copy import deepcopy
from dataclasses import replace
import sys
import threading

from config import CFG
from server import Hub
from test_admin_group_remove_scope import make_session
from test_group_kick_scope import cleanup, running, shutdown, assert_stopped


def hub_for_test(tmp_path):
    return Hub(cfg=replace(CFG, admin_pwd='', audit_dir=str(tmp_path/'audit'),
                           web_files_dir=str(tmp_path/'web')))


def test_dissolve_notifies_all_former_member_sessions_and_clears_only_own_voice(tmp_path, monkeypatch):
    hub = hub_for_test(tmp_path)
    try:
        owner, owner_frames = make_session(hub, 'diss-owner')
        owner_web, owner_web_frames = make_session(hub, 'diss-owner', 'web')
        member, member_frames = make_session(hub, 'diss-member')
        member_web, member_web_frames = make_session(hub, 'diss-member', 'web')
        outsider, outsider_frames = make_session(hub, 'diss-outsider')
        admin, admin_frames = make_session(hub, 'diss-admin')
        admin.is_admin = True
        hub.web_tokens['synthetic-dissolve-owner'] = owner_web
        hub.web_tokens['synthetic-dissolve-member'] = member_web
        hub._on_group_create(owner, {'name': 'diss-one', 'public': True})
        gid = next(iter(hub.groups))
        hub._on_group_join(member, {'gid': gid})
        hub._on_group_create(owner, {'name': 'diss-kept', 'public': True})
        kept = max(hub.groups)
        hub._on_group_join(member, {'gid': kept})
        hub.voice_rooms[f'group:{gid}'] = {owner.uid: {'port': 30001},
                                           member.uid: {'port': 30002}}
        hub.voice_rooms[f'group:{kept}'] = {member.uid: {'port': 30003}}
        audit = []
        monkeypatch.setattr(hub.audit, 'log', lambda **record: audit.append(record))
        for frames in (owner_frames, owner_web_frames, member_frames,
                       member_web_frames, outsider_frames, admin_frames):
            frames.clear()
        before = hub._group_state_revision
        hub._on_admin_group_set(admin, {'gid': gid, 'op': 'dissolve'})
        assert gid not in hub.groups and kept in hub.groups
        assert f'group:{gid}' not in hub.voice_rooms
        assert member.uid in hub.voice_rooms[f'group:{kept}']
        for frames in (owner_frames, owner_web_frames, member_frames, member_web_frames):
            removals = [f for f in frames if f.get('code') == 'group_removed']
            assert len(removals) == 1
            assert removals[0]['gid'] == gid
            assert type(removals[0]['group_revision']) is int
            assert before < removals[0]['group_revision'] <= hub._group_state_revision
        assert not any(f.get('code') == 'group_removed' for frames in
                       (outsider_frames, admin_frames) for f in frames)
        assert hub.session_by_token('synthetic-dissolve-owner') is owner_web
        assert hub.session_by_token('synthetic-dissolve-member') is member_web
        assert all(hub._session_is_active(s) for s in
                   (owner, owner_web, member, member_web, outsider, admin))
        assert len([r for r in audit if r.get('type') == 'admin_group_dissolve']) == 1
    finally:
        cleanup(sys.exception(), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))


def test_dissolve_one_send_failure_does_not_block_other_members(tmp_path):
    hub = hub_for_test(tmp_path)
    try:
        owner, _ = make_session(hub, 'fail-owner')
        member, member_frames = make_session(hub, 'fail-member')
        admin, _ = make_session(hub, 'fail-admin')
        admin.is_admin = True
        hub._on_group_create(owner, {'name': 'fail-diss', 'public': True})
        gid = next(iter(hub.groups))
        hub._on_group_join(member, {'gid': gid})
        original_send = owner.send

        def failing_send(frame, *args):
            if frame.get('code') == 'group_removed':
                raise OSError('synthetic dissolved transport failure')
            return original_send(frame, *args)

        owner.send = failing_send
        member_frames.clear()
        hub._on_admin_group_set(admin, {'gid': gid, 'op': 'dissolve'})
        assert gid not in hub.groups
        assert len([f for f in member_frames if f.get('code') == 'group_removed']) == 1
    finally:
        cleanup(sys.exception(), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))


def test_dissolve_nonadmin_and_missing_group_are_noops(tmp_path, monkeypatch):
    hub = hub_for_test(tmp_path)
    try:
        owner, owner_frames = make_session(hub, 'reject-owner')
        admin, admin_frames = make_session(hub, 'reject-admin')
        admin.is_admin = True
        hub._on_group_create(owner, {'name': 'reject-diss', 'public': True})
        gid = next(iter(hub.groups))
        before = hub._group_state_revision
        audit = []
        monkeypatch.setattr(hub.audit, 'log', lambda **record: audit.append(record))
        owner_frames.clear()
        admin_frames.clear()
        hub._on_admin_group_set(owner, {'gid': gid, 'op': 'dissolve'})
        hub._on_admin_group_set(admin, {'gid': gid + 100, 'op': 'dissolve'})
        assert gid in hub.groups
        assert hub._group_state_revision == before
        assert not audit
        assert [f.get('code') for f in owner_frames if f.get('t') == 'error'] == ['forbid']
        assert [f.get('code') for f in admin_frames if f.get('t') == 'error'] == ['group']
    finally:
        cleanup(sys.exception(), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))


def test_concurrent_dissolve_of_same_group_has_one_success(tmp_path, monkeypatch):
    hub = hub_for_test(tmp_path)
    gate = threading.Barrier(2)
    workers, errors = [], []
    original_lock = hub.lock
    try:
        owner, owner_frames = make_session(hub, 'race-owner')
        admin, _ = make_session(hub, 'race-admin')
        admin.is_admin = True
        hub._on_group_create(owner, {'name': 'race-diss', 'public': True})
        gid = next(iter(hub.groups))
        owner_frames.clear()
        before = hub._group_state_revision
        audit = []
        monkeypatch.setattr(hub.audit, 'log', lambda **record: audit.append(record))

        class FirstEntryGate:
            def __init__(self, lock):
                self.lock = lock
                self.guard = threading.Lock()
                self.reached = set()

            def __enter__(self):
                current = threading.current_thread()
                with self.guard:
                    first = current in workers and current not in self.reached
                    if first:
                        self.reached.add(current)
                if first:
                    gate.wait(3)
                return self.lock.__enter__()

            def __exit__(self, *args):
                return self.lock.__exit__(*args)

            def acquire(self, *args, **kwargs):
                return self.lock.acquire(*args, **kwargs)

            def release(self):
                return self.lock.release()

        wrapper = FirstEntryGate(original_lock)
        hub.lock = wrapper

        def dissolve():
            try:
                hub._on_admin_group_set(admin, {'gid': gid, 'op': 'dissolve'})
            except BaseException as exc:
                errors.append(exc)

        workers = [threading.Thread(target=dissolve, name=f'admin-dissolve-{i}')
                   for i in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)
        assert_stopped(*workers)
        assert wrapper.reached == set(workers)
        assert not errors, errors
        assert gid not in hub.groups
        assert hub._group_state_revision == before + 1
        assert len([f for f in owner_frames if f.get('code') == 'group_removed']) == 1
        assert len([r for r in audit if r.get('type') == 'admin_group_dissolve']) == 1
    finally:
        hub.lock = original_lock
        cleanup(sys.exception(), gate.abort,
                *(lambda worker=w: worker.join(5) for w in workers),
                lambda: assert_stopped(*workers), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))


def test_real_cores_retire_dissolved_group_and_do_not_attempt_rejoin(running, monkeypatch):
    hub, spawn = running
    owner, owner_events = spawn('diss-core-owner')
    first, first_events = spawn('diss-core-member')
    gids = []
    for name in ('diss-gone', 'diss-kept'):
        assert owner.create_group(name, public=True)
        gid = owner_events.wait('group_state', pred=lambda e: e.get('name') == name)['gid']
        gids.append(gid)
        assert first.join_group(gid)
        assert first_events.wait('group_state', pred=lambda e: e.get('gid') == gid
                                 and any(m['uid'] == first.uid for m in e['members']))
    removed, kept = gids
    second, second_events = spawn('diss-core-member')
    for gid in gids:
        assert second.join_group(gid)
        assert second_events.wait('error', pred=lambda e: e.get('code') == 'group')
    assert first.uid == second.uid != owner.uid
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
    admin, _ = make_session(hub, 'diss-core-admin')
    admin.is_admin = True
    epochs = (owner.connection_epoch, first.connection_epoch, second.connection_epoch)
    hub._on_admin_group_set(admin, {'gid': removed, 'op': 'dissolve'})
    for events in (owner_events, first_events, second_events):
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
    assert removed not in owner._joined_groups and removed not in owner.group_members
    assert (owner.connection_epoch, first.connection_epoch, second.connection_epoch) == epochs
    inbound_joins = []
    original_join = hub._on_group_join

    def record_join(sess, frame):
        inbound_joins.append((sess.uid, frame.get('gid')))
        return original_join(sess, frame)

    monkeypatch.setattr(hub, '_on_group_join', record_join)
    welcome_done = threading.Event()
    original_welcome = second._on_welcome

    def on_welcome(frame):
        original_welcome(frame)
        welcome_done.set()

    monkeypatch.setattr(second, '_on_welcome', on_welcome)
    second.drop()
    assert second_events.wait('welcome', timeout=6,
                              pred=lambda e: e.get('_connection_epoch', 0) > epochs[2])
    assert welcome_done.wait(3)
    assert second.send_chat('dissolve-order-barrier')
    assert owner_events.wait('chat', pred=lambda e: e.get('text') == 'dissolve-order-barrier')
    assert (second.uid, removed) not in inbound_joins
    assert second.uid not in {m['uid'] for m in hub.groups.get(removed, {}).get('members', {})}
    assert second.send_group('kept-after-dissolve', kept)
    assert owner_events.wait('chat', pred=lambda e: e.get('to') == kept
                             and e.get('text') == 'kept-after-dissolve')
