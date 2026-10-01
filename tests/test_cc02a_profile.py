# -*- coding: utf-8 -*-
"""CC-02A PROFILE：正常注销保留 known 资料且不伪造在线状态。"""

import copy
from dataclasses import replace

import pytest

from config import CFG
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


def _seed_profile(hub, sess, other_uid):
    """合成已有持久资料，包含空值/False，覆盖原资料复制边界。"""
    with hub.lock:
        hub.known[sess.uid].update({
            "pwd": "synthetic-pwd-hash",
            "sign": "",
            "avatar": "",
            "invisible": False,
            "status": "",
            "remarks": {str(other_uid): "备注保留"},
        })


def test_attach_and_last_unregister_preserve_profile_and_offline_roster(hub):
    first, _first_out = _attach(hub, "profile-user")
    other, _other_out = _attach(hub, "profile-other")
    _seed_profile(hub, first, other.uid)
    expected = copy.deepcopy(hub.known[first.uid])

    # 同 UID 第二端上线时也不得因空字符串/False 把原资料删掉。
    second, _second_out = _attach(hub, "profile-user", "web")
    assert hub.known[first.uid] == expected
    assert hub.sessions[first.uid] is second
    assert len(hub._uid_clients[first.uid]) == 2

    hub.unregister(first, "profile_middle")
    assert hub.sessions[first.uid] is second
    assert hub.known[first.uid] == expected
    assert any(item["uid"] == first.uid for item in hub._roster(other.uid))

    before_last_online = hub.known[first.uid]["last_online"]
    hub.unregister(second, "profile_last")

    info = hub.known[first.uid]
    assert info["nick"] == expected["nick"]
    assert info["last_online"] >= before_last_online
    for key in ("pwd", "sign", "avatar", "invisible", "status", "remarks"):
        assert info[key] == expected[key]
    assert first.uid not in hub.sessions
    assert not any(item["uid"] == first.uid for item in hub._roster(other.uid))
    admin_row = next(item for item in hub._admin_users()
                     if item["uid"] == first.uid)
    assert admin_row["online"] is False
    assert hub.known[other.uid] == {
        "nick": "profile-other", "last_online": 0,
    }


def test_profile_survives_json_restart_and_relogin(tmp_path):
    store_dir = tmp_path / "store"
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit1"),
                  web_files_dir=str(tmp_path / "web1"), admin_pwd="")
    h1 = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit1"),
             store_dir=str(store_dir))
    try:
        first, _out = _attach(h1, "restart-profile")
        other, _other_out = _attach(h1, "restart-other")
        with h1.lock:
            h1.known[first.uid].update({
                "pwd": "synthetic-pwd-hash",
                "sign": "重启签名",
                "avatar": "png",
                "invisible": True,
                "status": "busy",
                "remarks": {str(other.uid): "重启备注"},
            })
        h1._persist_flush()
        uid = first.uid
        h1.unregister(first, "restart_profile")
        h1.unregister(other, "restart_other")
        h1._persist_flush()
    finally:
        h1.audit.close()

    cfg2 = replace(CFG, audit_dir=str(tmp_path / "audit2"),
                   web_files_dir=str(tmp_path / "web2"), admin_pwd="")
    h2 = Hub(cfg=cfg2, audit_dir=str(tmp_path / "audit2"),
             store_dir=str(store_dir))
    try:
        info = h2.known[uid]
        assert uid not in h2.sessions
        assert info["nick"] == "restart-profile"
        assert info["sign"] == "重启签名"
        assert info["avatar"] == "png"
        assert info["invisible"] is True
        assert info["status"] == "busy"
        assert info["remarks"] == {"2": "重启备注"}

        relogin, out = _attach(h2, "restart-profile", "web")
        assert relogin.uid == uid
        assert h2.known[uid] == info
        welcome = next(frame for frame, _body in out.frames
                       if frame.get("t") == "welcome")
        assert welcome["sign"] == "重启签名"
        assert welcome["avatar"] == "png"
        assert welcome["invisible"] is True
        assert welcome["status"] == "busy"
    finally:
        h2.audit.close()
