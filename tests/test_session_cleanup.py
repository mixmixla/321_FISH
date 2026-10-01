# -*- coding: utf-8 -*-
"""SESSION-02：同 UID 多端离线清理边界与重登交错回归。"""
import copy
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from filexfer import TransferMeta, XferStatus
from server import Hub, Session


class _Capture:
    __test__ = False

    def __init__(self):
        self.frames = []

    def send(self, payload, body=b""):
        self.frames.append((copy.deepcopy(payload), bytes(body or b"")))


@pytest.fixture()
def hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"), admin_pwd="")
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    yield h
    h.audit.close()


def _attach(hub, nick, stype="tcp"):
    out = _Capture()
    sess = Session(0, nick, stype, "127.0.0.1", out.send)
    assert hub._attach(sess)
    return sess, out


def _seed_xfer(hub, fid, sender, receiver):
    rec = TransferMeta(
        file_id=fid, filename="session.bin", size=1, chunk_size=1,
        md5="0" * 32, sender_uid=sender.uid, receiver_uid=receiver.uid,
        status=XferStatus.ACCEPTED.value, sender_nick=sender.nick,
        sender_ip=sender.peer_ip,
    )
    hub.xfers[fid] = rec
    return rec


def _seed_uid_resources(hub, uid, receiver, prefix):
    fid = f"{prefix}-file"
    rec = _seed_xfer(hub, fid, hub.sessions[uid], receiver)
    room = hub.rooms.create(uid, "guess_number")
    hub.voice_rooms[hub._ROOM_PUBLIC] = {uid: {"port": 4567}}
    return fid, rec, room.room_id


def test_non_last_unregister_preserves_uid_resources_and_online_state(hub):
    first, first_out = _attach(hub, "multi")
    second, second_out = _attach(hub, "multi", "web")
    other, other_out = _attach(hub, "other")
    fid, _rec, room_id = _seed_uid_resources(hub, first.uid, other, "keep")
    first_out.frames.clear(); second_out.frames.clear(); other_out.frames.clear()

    hub.unregister(first, "test")

    assert first.closed
    assert not second.closed
    assert hub.sessions[first.uid] is second
    assert fid in hub.xfers
    assert room_id in hub.rooms.rooms
    assert first.uid in hub.rooms.rooms[room_id].members
    assert first.uid in hub.voice_rooms[hub._ROOM_PUBLIC]
    assert not any(f[0].get("text") == "multi 已下线"
                   for f in other_out.frames)


def test_last_unregister_cleans_uid_resources_once(hub):
    first, first_out = _attach(hub, "last")
    second, second_out = _attach(hub, "last", "web")
    other, other_out = _attach(hub, "other")
    fid, _rec, room_id = _seed_uid_resources(hub, first.uid, other, "last")
    first_out.frames.clear(); second_out.frames.clear(); other_out.frames.clear()

    hub.unregister(first, "test")
    assert fid in hub.xfers and room_id in hub.rooms.rooms

    hub.unregister(second, "test")

    assert first.uid not in hub.sessions
    assert first.uid not in hub._uid_clients
    assert fid not in hub.xfers
    assert room_id not in hub.rooms.rooms
    assert hub._ROOM_PUBLIC not in hub.voice_rooms
    offline = [f for f in other_out.frames
               if f[0].get("text") == "last 已下线"]
    assert len(offline) == 1

    hub.unregister(second, "repeat")
    offline = [f for f in other_out.frames
               if f[0].get("text") == "last 已下线"]
    assert len(offline) == 1


def test_old_unregister_cannot_clear_resources_created_after_relogin(
        hub, monkeypatch):
    old, _old_out = _attach(hub, "race")
    receiver, _receiver_out = _attach(hub, "receiver")
    entered = threading.Event()
    resume = threading.Event()
    original_drop = hub._drop_xfers_of

    def delayed_drop(uid):
        entered.set()
        assert resume.wait(5)
        return original_drop(uid)

    monkeypatch.setattr(hub, "_drop_xfers_of", delayed_drop)
    thread = threading.Thread(target=hub.unregister,
                              args=(old, "disconnect"), daemon=True)
    thread.start()
    assert entered.wait(5)

    new, _new_out = _attach(hub, "race", "web")
    new_fid, _new_rec, new_room = _seed_uid_resources(
        hub, new.uid, receiver, "new")
    resume.set()
    thread.join(5)
    assert not thread.is_alive()

    assert hub.sessions[new.uid] is new
    assert not new.closed
    assert new_fid in hub.xfers
    assert new_room in hub.rooms.rooms
    assert new.uid in hub.rooms.rooms[new_room].members


def test_relogin_before_offline_publish_suppresses_stale_notice(hub):
    old, _old_out = _attach(hub, "notice-user")
    observer, observer_out = _attach(hub, "observer")
    observer_out.frames.clear()
    entered = threading.Event()
    resume = threading.Event()
    actual = hub._offline_notice_before_snapshot

    def pause_notice(uid, text):
        if uid == old.uid and text == "notice-user 已下线":
            entered.set()
            assert resume.wait(5)
        actual(uid, text)

    hub._offline_notice_before_snapshot = pause_notice
    thread = threading.Thread(target=hub.unregister,
                              args=(old, "synthetic_notice"), daemon=True)
    thread.start()
    assert entered.wait(5)
    fresh, _fresh_out = _attach(hub, "notice-user", "web")
    assert hub._session_is_active(fresh)
    resume.set()
    thread.join(5)
    assert not thread.is_alive()
    assert not any(f[0].get("text") == "notice-user 已下线"
                   for f in observer_out.frames)


def test_rapid_relogin_then_fresh_last_disconnect_cleans_and_notifies_once(hub):
    old, _ = _attach(hub, "rapid-user")
    observer, out = _attach(hub, "rapid-observer")
    entered, resume = threading.Event(), threading.Event()
    first = True

    def pause_first_notice(uid, text):
        nonlocal first
        if uid == old.uid and first:
            first = False
            entered.set()
            assert resume.wait(5)

    hub._offline_notice_before_snapshot = pause_first_notice
    thread = threading.Thread(target=hub.unregister, args=(old, "old"), daemon=True)
    thread.start()
    assert entered.wait(5)
    fresh, _ = _attach(hub, "rapid-user", "web")
    fid, _, rid = _seed_uid_resources(hub, fresh.uid, observer, "rapid-fresh")
    out.frames.clear()
    hub.unregister(fresh, "fresh")
    resume.set()
    thread.join(5)
    assert not thread.is_alive()
    assert fresh.uid not in hub._uid_clients and fresh.uid not in hub.sessions
    assert fid not in hub.xfers and rid not in hub.rooms.rooms
    assert hub._ROOM_PUBLIC not in hub.voice_rooms
    assert fresh.uid not in hub._offline_notice_records
    assert sum(f[0].get("text") == "rapid-user 已下线" for f in out.frames) == 1


def test_repopulated_group_survives_old_dissolved_gc(hub):
    old, _old_out = _attach(hub, "group-user")
    _observer, _observer_out = _attach(hub, "observer")
    hub.groups[7] = {
        "gid": 7, "name": "synthetic", "owner": old.uid,
        "members": {old.uid: old.nick}, "admins": set(), "mutes": {},
        "announce": "", "announce_mode": 0, "invite": "", "kind": "",
        "public": 1, "slow": 0,
    }
    original_lock = hub.lock
    fresh_holder = []
    premise = []

    class _InterleaveLock:
        armed = True

        def __enter__(self):
            return original_lock.__enter__()

        def __exit__(self, *args):
            result = original_lock.__exit__(*args)
            if self.armed:
                self.armed = False
                fresh, _fresh_out = _attach(hub, "group-user")
                fresh_holder.append(fresh)
                hub.dispatch(fresh, {"t": "group_join", "gid": 7})
                premise.append(7 in hub.groups
                               and fresh.uid in hub.groups[7]["members"])
                hub.voice_rooms["group:7"] = {fresh.uid: {"port": 4567}}
            return result

        def acquire(self, *args, **kwargs):
            return original_lock.acquire(*args, **kwargs)

        def release(self):
            return original_lock.release()

    hub.lock = _InterleaveLock()
    hub.unregister(old, "synthetic_group_gc")
    fresh = fresh_holder[0]
    assert premise == [True]
    assert hub._session_is_active(fresh)
    assert 7 in hub.groups
    assert fresh.uid in hub.groups[7]["members"]
    assert "group:7" in hub.voice_rooms


def test_min_idle_recheck_and_repeated_unregister_are_idempotent(hub):
    sess, _out = _attach(hub, "idle")
    sess.last_seen = time.time()
    hub.unregister(sess, "zombie", min_idle=60)
    assert not sess.closed
    assert hub.sessions[sess.uid] is sess

    hub.unregister(sess, "disconnect")
    assert sess.closed
    assert sess.uid not in hub.sessions
    hub.unregister(sess, "repeat")
    assert sess.closed
