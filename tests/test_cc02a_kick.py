# -*- coding: utf-8 -*-
"""CC-02A KICK：全端 Session/token 撤权与重登竞态。"""

import copy
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from filexfer import TransferMeta, XferStatus
from protocol import MsgType
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


def _attach(hub, nick, stype="tcp", is_admin=False):
    out = _Capture()
    sess = Session(0, nick, stype, "127.0.0.1", out.send)
    sess.is_admin = is_admin
    assert hub._attach(sess)
    return sess, out


def _tokenize(hub, sess, token):
    with hub.lock:
        hub.web_tokens[token] = sess


def _seed_uid_resources(hub, uid, receiver, prefix):
    fid = f"{prefix}-file"
    hub.xfers[fid] = TransferMeta(
        file_id=fid, filename="kick.bin", size=1, chunk_size=1,
        md5="0" * 32, sender_uid=uid, receiver_uid=receiver.uid,
        status=XferStatus.ACCEPTED.value, sender_nick=hub.known[uid]["nick"],
        sender_ip="127.0.0.1",
    )
    room = hub.rooms.create(uid, "guess_number")
    hub.voice_rooms[hub._ROOM_PUBLIC] = {uid: {"port": 4567}}
    return fid, room.room_id


def _kicked(out):
    return [frame for frame, _body in out.frames
            if frame.get("t") == MsgType.ERROR.value
            and frame.get("code") == "kicked"]


def test_admin_kick_revokes_all_sessions_tokens_and_old_dispatch(hub):
    admin, _admin_out = _attach(hub, "kick-admin", is_admin=True)
    target_tcp, tcp_out = _attach(hub, "kick-target", "tcp")
    target_web1, web1_out = _attach(hub, "kick-target", "web")
    target_web2, web2_out = _attach(hub, "kick-target", "web")
    observer, observer_out = _attach(hub, "kick-observer")
    _tokenize(hub, target_web1, "kick-token-1")
    _tokenize(hub, target_web2, "kick-token-2")
    closed = []
    for target in (target_tcp, target_web1, target_web2):
        target.close_conn = lambda target=target: closed.append(target)
    tcp_out.frames.clear()
    web1_out.frames.clear()
    web2_out.frames.clear()
    observer_out.frames.clear()

    # 非管理员不能改变目标状态。
    hub.dispatch(observer, {"t": MsgType.ADMIN_KICK.value,
                            "uid": target_tcp.uid})
    assert any(frame.get("code") == "forbid"
               for frame, _body in observer_out.frames)
    assert hub._session_is_active(target_tcp)

    assert hub.dispatch(admin, {"t": MsgType.ADMIN_KICK.value,
                                "uid": target_tcp.uid}) is True

    for target in (target_tcp, target_web1, target_web2):
        assert target.closed
        assert not hub._session_is_active(target)
    assert _kicked(tcp_out) and _kicked(web1_out) and _kicked(web2_out)
    assert set(closed) == {target_tcp, target_web1, target_web2}
    assert hub.session_by_token("kick-token-1") is None
    assert hub.session_by_token("kick-token-2") is None
    assert target_tcp.uid not in hub.sessions
    assert target_tcp.uid not in hub._uid_clients

    # t0 后的旧 Session 不能再提交消息；他人/管理员仍可正常发送。
    before = len(hub.bus.history("all"))
    assert hub.dispatch(target_tcp, {"t": MsgType.CHAT.value,
                                     "channel": "public",
                                     "text": "stale-kick"}) is False
    assert len(hub.bus.history("all")) == before
    assert hub.dispatch(observer, {"t": MsgType.CHAT.value,
                                   "channel": "public",
                                   "text": "observer-alive"}) is True
    assert any(msg.get("text") == "observer-alive"
               for msg in hub.bus.history("all"))
    assert hub._session_is_active(admin)

    # KICK 不是封禁：后续正常认证可重新建立同 UID、独立 token。
    fresh, fresh_token = hub.login_web("kick-target", "127.0.0.1")
    assert fresh is not None and fresh.uid == target_tcp.uid
    assert hub.session_by_token(fresh_token) is fresh
    assert hub._session_is_active(fresh)


def test_kick_t0_preserves_new_session_token_and_resources(hub, monkeypatch):
    admin, _admin_out = _attach(hub, "race-admin", is_admin=True)
    old, _old_out = _attach(hub, "race-kick-old")
    receiver, _receiver_out = _attach(hub, "race-kick-receiver")
    entered = threading.Event()
    resume = threading.Event()
    fresh_holder = []
    original_unregister = hub.unregister

    def gated_unregister(sess, reason, min_idle=None):
        if sess is old and not entered.is_set():
            entered.set()
            assert resume.wait(5)
        return original_unregister(sess, reason, min_idle=min_idle)

    monkeypatch.setattr(hub, "unregister", gated_unregister)
    thread = threading.Thread(
        target=hub.dispatch,
        args=(admin, {"t": MsgType.ADMIN_KICK.value, "uid": old.uid}),
        daemon=True,
    )
    thread.start()
    assert entered.wait(5)
    assert old.closed

    # 这里发生在 KICK 的 t0 之后、旧 unregister 之前：新 token/资源不能被
    # 旧注销流程误删。使用 attach 而非直接改 Hub，模拟正常重登路径。
    fresh, _fresh_out = _attach(hub, "race-kick-old", "web")
    fresh_holder.append(fresh)
    _tokenize(hub, fresh, "race-kick-new-token")
    new_fid, new_room = _seed_uid_resources(
        hub, fresh.uid, receiver, "race-kick-new")
    resume.set()
    thread.join(5)
    assert not thread.is_alive()

    assert fresh_holder[0] is fresh
    assert hub._session_is_active(fresh)
    assert hub.sessions[fresh.uid] is fresh
    assert hub.session_by_token("race-kick-new-token") is fresh
    assert new_fid in hub.xfers
    assert new_room in hub.rooms.rooms
    assert fresh.uid in hub.rooms.rooms[new_room].members
    assert fresh.uid in hub.voice_rooms[hub._ROOM_PUBLIC]


def test_kick_without_relogin_cleans_uid_resources_and_notifies_once(hub):
    admin, _admin_out = _attach(hub, "last-kick-admin", is_admin=True)
    first, first_out = _attach(hub, "last-kick-target")
    second, second_out = _attach(hub, "last-kick-target", "web")
    receiver, observer_out = _attach(hub, "last-kick-observer")
    _tokenize(hub, second, "last-kick-token")
    fid, room_id = _seed_uid_resources(hub, first.uid, receiver,
                                       "last-kick")
    first_out.frames.clear()
    second_out.frames.clear()
    observer_out.frames.clear()

    hub.dispatch(admin, {"t": MsgType.ADMIN_KICK.value, "uid": first.uid})

    assert _kicked(first_out) and _kicked(second_out)
    assert hub.session_by_token("last-kick-token") is None
    assert first.uid not in hub.sessions
    assert first.uid not in hub._uid_clients
    assert fid not in hub.xfers
    assert room_id not in hub.rooms.rooms
    assert hub._ROOM_PUBLIC not in hub.voice_rooms
    offline = [frame for frame, _body in observer_out.frames
               if frame.get("text") == "last-kick-target 已下线"]
    assert len(offline) == 1


def test_kick_notification_failure_does_not_abort_other_targets(hub):
    admin, _admin_out = _attach(hub, "notify-admin", is_admin=True)
    failed, failed_out = _attach(hub, "notify-target", "web")
    healthy, healthy_out = _attach(hub, "notify-target", "tcp")
    observer, _observer_out = _attach(hub, "notify-observer")
    _tokenize(hub, failed, "notify-failed-token")
    failed.send = lambda payload, body=b"": (_ for _ in ()).throw(
        OSError("synthetic notify failure"))
    failed.close_conn = lambda: (_ for _ in ()).throw(
        OSError("synthetic close failure"))
    healthy_out.frames.clear()

    hub.dispatch(admin, {"t": MsgType.ADMIN_KICK.value, "uid": failed.uid})

    assert failed.closed and healthy.closed
    assert hub.session_by_token("notify-failed-token") is None
    assert _kicked(healthy_out)
    assert not hub._session_is_active(failed)
    assert not hub._session_is_active(healthy)
    assert hub._session_is_active(admin)
    assert hub._session_is_active(observer)
