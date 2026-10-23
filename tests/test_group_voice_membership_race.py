"""A late voice join cannot revive group membership after revocation."""
from dataclasses import replace
import sys
import threading

import pytest

from config import CFG
from server import Hub
from test_admin_group_remove_scope import make_session
from test_group_kick_scope import cleanup, shutdown, assert_stopped


@pytest.mark.parametrize('revoke', ('leave', 'kick', 'admin_remove', 'admin_dissolve'))
def test_late_group_voice_join_cannot_restore_removed_member(tmp_path, monkeypatch, revoke):
    hub = Hub(cfg=replace(CFG, admin_pwd='', audit_dir=str(tmp_path/'audit'),
                          web_files_dir=str(tmp_path/'web')))
    worker = None
    probes = []
    errors = []
    reached, release = threading.Event(), threading.Event()
    original_lock = hub.lock
    try:
        owner, owner_frames = make_session(hub, 'voice-owner')
        target, target_frames = make_session(hub, 'voice-target')
        admin, _ = make_session(hub, 'voice-admin')
        admin.is_admin = True
        hub._on_group_create(owner, {'name': 'voice-left', 'public': True})
        gid = next(iter(hub.groups))
        hub._on_group_join(target, {'gid': gid})
        hub._on_group_create(owner, {'name': 'voice-kept', 'public': True})
        kept = max(hub.groups)
        hub._on_group_join(target, {'gid': kept})
        room = f'group:{gid}'
        kept_room = f'group:{kept}'
        hub._on_room_join(owner, {'room': room})
        hub._on_room_join(target, {'room': kept_room})
        hub._on_room_join(target, {'room': 'public'})
        assert owner.uid in hub.voice_rooms[room]
        assert target.uid in hub.voice_rooms[kept_room]
        assert target.uid in hub.voice_rooms['public']
        audit = []
        monkeypatch.setattr(hub.audit, 'log', lambda **record: audit.append(record))
        owner_frames.clear()
        target_frames.clear()
        original_send = target.send
        unlocked = []

        def send(frame, *args):
            if frame.get('t') == 'error' and frame.get('code') == 'room':
                acquired = threading.Event()

                def probe():
                    if original_lock.acquire(timeout=2):
                        try:
                            acquired.set()
                        finally:
                            original_lock.release()

                thread = threading.Thread(target=probe, name='voice-error-lock-probe')
                probes.append(thread)
                thread.start()
                unlocked.append(acquired.wait(.5))
            return original_send(frame, *args)

        target.send = send

        class FirstJoinLockGate:
            def __init__(self, lock):
                self.lock = lock
                self.count = 0

            def __enter__(self):
                if threading.current_thread() is worker and self.count == 0:
                    self.count += 1
                    reached.set()
                    assert release.wait(4), 'owned join was not released'
                return self.lock.__enter__()

            def __exit__(self, *args):
                return self.lock.__exit__(*args)

            def acquire(self, *args, **kwargs):
                return self.lock.acquire(*args, **kwargs)

            def release(self):
                return self.lock.release()

        gate = FirstJoinLockGate(original_lock)
        hub.lock = gate

        def late_join():
            try:
                hub._on_room_join(target, {'room': room})
            except BaseException as exc:
                errors.append(exc)

        worker = threading.Thread(target=late_join, name='late-group-voice-join')
        worker.start()
        assert reached.wait(3)
        assert gate.count == 1
        if revoke == 'leave':
            hub._on_group_leave(target, {'gid': gid})
        elif revoke == 'kick':
            hub._on_group_kick(owner, {'gid': gid, 'target': target.uid})
        elif revoke == 'admin_remove':
            hub._on_admin_group_set(admin, {'gid': gid, 'op': 'remove', 'uid': target.uid})
        else:
            hub._on_admin_group_set(admin, {'gid': gid, 'op': 'dissolve'})
        assert gid not in hub.groups or target.uid not in hub.groups[gid]['members']
        release.set()
        worker.join(5)
        assert_stopped(worker)
        assert not errors, errors
        assert gate.count == 1
        assert unlocked == [True]
        assert len([f for f in target_frames if f.get('t') == 'error'
                    and f.get('code') == 'room']) == 1
        assert not any(f.get('t') == 'room_peers' and f.get('room') == room
                       for f in target_frames)
        assert not any(r.get('type') == 'room_join' and r.get('room') == room
                       and r.get('uid') == target.uid for r in audit)
        if revoke == 'admin_dissolve':
            assert room not in hub.voice_rooms
        else:
            assert owner.uid in hub.voice_rooms[room]
            assert target.uid not in hub.voice_rooms[room]
        assert target.uid in hub.voice_rooms[kept_room]
        assert target.uid in hub.voice_rooms['public']
    finally:
        hub.lock = original_lock
        cleanup(sys.exception(), release.set,
                lambda: worker.join(5) if worker else None,
                lambda: assert_stopped(worker),
                *(lambda probe=probe: probe.join(3) for probe in probes),
                lambda: assert_stopped(*probes), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))


def test_public_and_valid_group_voice_reentry_preserve_port_and_capacity(tmp_path):
    hub = Hub(cfg=replace(CFG, admin_pwd='', audit_dir=str(tmp_path/'audit'),
                          web_files_dir=str(tmp_path/'web'), voice_room_max=1))
    probes = []
    try:
        owner, owner_frames = make_session(hub, 'control-owner')
        other, other_frames = make_session(hub, 'control-other')
        web, web_frames = make_session(hub, 'control-owner', 'web')
        hub._on_group_create(owner, {'name': 'control-voice', 'public': True})
        gid = next(iter(hub.groups))
        room = f'group:{gid}'
        hub._on_room_join(owner, {'room': room})
        hub.voice_rooms[room][owner.uid]['port'] = 34567
        owner_frames.clear()
        hub._on_room_join(owner, {'room': room})
        assert hub.voice_rooms[room][owner.uid]['port'] == 34567
        assert any(f.get('t') == 'room_peers' and f.get('room') == room for f in owner_frames)
        hub._on_group_join(other, {'gid': gid})
        other_frames.clear()
        original_send = other.send
        unlocked = []

        def send(frame, *args):
            if frame.get('code') == 'room_full':
                acquired = threading.Event()

                def probe():
                    if hub.lock.acquire(timeout=2):
                        try:
                            acquired.set()
                        finally:
                            hub.lock.release()

                thread = threading.Thread(target=probe, name='voice-full-lock-probe')
                probes.append(thread)
                thread.start()
                unlocked.append(acquired.wait(.5))
            return original_send(frame, *args)

        other.send = send
        hub._on_room_join(other, {'room': room})
        assert [f.get('code') for f in other_frames if f.get('t') == 'error'] == ['room_full']
        assert unlocked == [True]
        assert other.uid not in hub.voice_rooms[room]
        hub._on_room_join(other, {'room': 'public'})
        assert other.uid in hub.voice_rooms['public']
        hub._on_room_join(web, {'room': room})
        assert any(f.get('code') == 'room' for f in web_frames)
        assert owner.uid in hub.voice_rooms[room]
    finally:
        cleanup(sys.exception(), *(lambda probe=probe: probe.join(3) for probe in probes),
                lambda: assert_stopped(*probes), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))
