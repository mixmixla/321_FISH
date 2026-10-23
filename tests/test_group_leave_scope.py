"""A UID-wide group leave must retire every existing session's group state."""
from dataclasses import replace
from copy import deepcopy
import sys
import threading

from config import CFG
from server import Hub, Session
from test_group_kick_scope import cleanup, running, shutdown, assert_stopped, assert_no_errors


def test_two_clients_leave_without_rejoining_on_reconnect(running, monkeypatch):
    hub, spawn = running
    owner, owner_events = spawn('leave-owner')
    first, first_events = spawn('leave-member')
    gids = []
    for name in ('left-group', 'kept-group'):
        assert owner.create_group(name, public=True)
        gid = owner_events.wait('group_state', pred=lambda e: e.get('name') == name)['gid']
        gids.append(gid)
        assert first.join_group(gid)
        assert first_events.wait('group_state', pred=lambda e: e.get('gid') == gid
                                 and any(m['uid'] == first.uid for m in e['members']))
    left, kept = gids
    second, second_events = spawn('leave-member')
    for gid in gids:
        assert second.join_group(gid)
        assert second_events.wait('error', pred=lambda e: e.get('code') == 'group')
    assert first.uid == second.uid
    assert set(gids) <= second._joined_groups
    first.group_invites[left] = 'synthetic-invite'
    second.group_invites[left] = 'synthetic-invite'
    kept_material = []
    for core in (first, second):
        for gid in gids:
            core.e2ee.new_group_epoch(gid)
            core.e2ee.set_peer_sender_key(gid, owner.uid, b'p' * 32, 1)
            core._e2ee_groups.add(gid)
            core._e2ee_group_members[gid] = frozenset((core.uid, owner.uid))
        kept_material.append(deepcopy((core.e2ee._groups[kept],
                                       core.e2ee._my_sk[kept], core.e2ee._my_send[kept])))
    epochs = (first.connection_epoch, second.connection_epoch)

    assert first.leave_group(left)
    for events in (first_events, second_events):
        event = events.wait('error', pred=lambda e: e.get('code') == 'group_removed'
                            and e.get('gid') == left)
        assert event and type(event.get('group_revision')) is int
    for core, expected in zip((first, second), kept_material):
        assert core.connected and not core._manual_login_required
        assert left not in core._joined_groups
        assert left not in core.group_members and left not in core.group_invites
        assert kept in core._joined_groups
        assert not core.group_e2ee_on(left) and left not in core._e2ee_group_members
        assert all(left not in mapping for mapping in
                   (core.e2ee._groups, core.e2ee._my_sk, core.e2ee._my_send))
        assert core.e2ee.peer_sender_entry(left, owner.uid) is None
        assert core.group_e2ee_on(kept)
        assert expected == (core.e2ee._groups[kept],
                            core.e2ee._my_sk[kept], core.e2ee._my_send[kept])
    assert (first.connection_epoch, second.connection_epoch) == epochs
    assert first.uid not in hub.groups[left]['members']
    assert first.uid in hub.groups[kept]['members']

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
    assert second.send_chat('leave-order-barrier')
    assert owner_events.wait('chat', pred=lambda e: e.get('text') == 'leave-order-barrier')
    assert first.uid not in hub.groups[left]['members']
    assert second.send_group('kept-group-alive', kept)
    assert owner_events.wait('chat', pred=lambda e: e.get('to') == kept
                             and e.get('text') == 'kept-group-alive')
    assert second.join_group(left)
    assert second_events.wait('group_state', pred=lambda e: e.get('gid') == left
                              and any(m['uid'] == second.uid for m in e['members']))


def test_last_member_dissolve_notifies_every_existing_session(tmp_path):
    hub = Hub(cfg=replace(CFG, admin_pwd='', audit_dir=str(tmp_path/'audit'),
                          web_files_dir=str(tmp_path/'web')))
    sessions, outputs = [], []
    try:
        for kind in ('tcp', 'web'):
            frames = []
            sess = Session(0, 'sole-member', kind, '127.0.0.1',
                           lambda h, *_, frames=frames: frames.append(h))
            assert hub._attach(sess)
            sessions.append(sess)
            outputs.append(frames)
        first, web = sessions
        hub.web_tokens['synthetic-leave-token'] = web
        hub._on_group_create(first, {'name': 'last-member', 'public': True})
        gid = next(iter(hub.groups))
        for frames in outputs:
            frames.clear()
        hub._on_group_leave(first, {'gid': gid})
        assert gid not in hub.groups
        for frames in outputs:
            removed = [f for f in frames if f.get('code') == 'group_removed']
            assert len(removed) == 1 and removed[0]['gid'] == gid
            assert type(removed[0]['group_revision']) is int
        assert hub.session_by_token('synthetic-leave-token') is web
        assert all(hub._session_is_active(sess) for sess in sessions)
    finally:
        cleanup(sys.exception(), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))


def test_older_group_snapshot_cannot_restore_member_after_leave(tmp_path):
    hub = Hub(cfg=replace(CFG, admin_pwd='', audit_dir=str(tmp_path/'audit'),
                          web_files_dir=str(tmp_path/'web')))
    entered, release = threading.Event(), threading.Event()
    frames, errors = [], []
    worker = None
    def capture(frame, *_):
        if frame.get('text') == 'paused-before-leave':
            entered.set()
            assert release.wait(4)
        frames.append(frame)
    try:
        owner = Session(0, 'owner', 'tcp', '127.0.0.1', lambda *_: None)
        target = Session(0, 'member', 'tcp', '127.0.0.1', capture)
        assert hub._attach(owner) and hub._attach(target)
        hub._on_group_create(owner, {'name': 'ordered-leave', 'public': True})
        gid = next(iter(hub.groups))
        hub._on_group_join(target, {'gid': gid})
        frames.clear()
        def delayed():
            try:
                hub._send_group_state(gid, text='paused-before-leave')
            except BaseException as exc:
                errors.append(exc)
        worker = threading.Thread(target=delayed)
        worker.start()
        assert entered.wait(3)
        hub._on_group_leave(target, {'gid': gid})
        release.set()
        worker.join(4)
        assert_stopped(worker)
        assert_no_errors(errors)
        removed = next(f for f in frames if f.get('code') == 'group_removed')
        old = next(f for f in frames if f.get('text') == 'paused-before-leave')
        assert frames.index(removed) < frames.index(old)
        assert old['group_revision'] < removed['group_revision']
        assert target.uid in [m['uid'] for m in old['members']]
    finally:
        cleanup(sys.exception(), release.set,
                lambda: worker.join(5) if worker else None,
                lambda: assert_stopped(worker), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads),
                lambda: assert_no_errors(errors))


def test_concurrent_same_uid_leaves_remove_once_and_reject_other(tmp_path):
    hub = Hub(cfg=replace(CFG, admin_pwd='', audit_dir=str(tmp_path/'audit'),
                          web_files_dir=str(tmp_path/'web')))
    sessions, outputs, errors = [], [], []
    workers = []
    barrier = threading.Barrier(2)
    original_lock = hub.lock
    try:
        owner = Session(0, 'owner', 'tcp', '127.0.0.1', lambda *_: None)
        assert hub._attach(owner)
        for _ in range(2):
            frames = []
            sess = Session(0, 'same-member', 'tcp', '127.0.0.1',
                           lambda h, *_, frames=frames: frames.append(h))
            assert hub._attach(sess)
            sessions.append(sess)
            outputs.append(frames)
        hub._on_group_create(owner, {'name': 'concurrent-leave', 'public': True})
        gid = next(iter(hub.groups))
        hub._on_group_join(sessions[0], {'gid': gid})
        for frames in outputs:
            frames.clear()
        before = hub._group_state_revision
        # Both workers reach their first Hub-lock acquisition together. In the
        # old handler they have already passed the lock-free membership check;
        # in the fixed handler that check happens after this gate, under lock.
        class FirstEntryGate:
            def __init__(self, lock):
                self.lock = lock
                self.seen = set()
                self.guard = threading.Lock()

            def __enter__(self):
                current = threading.current_thread()
                with self.guard:
                    first = current in workers and current not in self.seen
                    if first:
                        self.seen.add(current)
                if first:
                    barrier.wait(3)
                return self.lock.__enter__()

            def __exit__(self, *args):
                return self.lock.__exit__(*args)

            def acquire(self, *args, **kwargs):
                return self.lock.acquire(*args, **kwargs)

            def release(self):
                return self.lock.release()

        hub.lock = FirstEntryGate(original_lock)
        def leave(sess):
            try:
                hub._on_group_leave(sess, {'gid': gid})
            except BaseException as exc:
                errors.append(exc)
        workers = [threading.Thread(target=leave, args=(sess,)) for sess in sessions]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(4)
        assert_stopped(*workers)
        assert_no_errors(errors)
        assert sessions[0].uid not in hub.groups[gid]['members']
        assert hub._group_state_revision == before + 2  # one removal, one remaining-member snapshot
        for frames in outputs:
            assert len([f for f in frames if f.get('code') == 'group_removed']) == 1
        assert sum(bool(any(f.get('code') == 'group' for f in frames)) for frames in outputs) == 1
    finally:
        hub.lock = original_lock
        cleanup(sys.exception(), barrier.abort,
                *(lambda worker=worker: worker.join(5) for worker in workers),
                lambda: assert_stopped(*workers), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))
