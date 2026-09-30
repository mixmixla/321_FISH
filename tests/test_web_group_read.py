# -*- coding: utf-8 -*-
"""R20 网页端增强：群管理（create/join/detail/kick/mute/admin/announce）
与已读回执接口的 HTTP 级验证（复用 Hub 群内部逻辑 + web.py API）。"""
import http.client
import json
import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, serve as serve_tcp
from web import serve as serve_web


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Web:
    """轻量 web HTTP 客户端：登录拿 token + 通用 POST/GET。"""
    def __init__(self, port, nick):
        self.port = port
        self.token = None
        self.uid = None
        self.login(nick)

    def _post(self, path, body):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", path, json.dumps(body).encode(),
                     {"Content-Type": "application/json"})
        r = conn.getresponse()
        data = json.loads(r.read().decode() or "{}")
        conn.close()
        return r.status, data

    def _get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        r = conn.getresponse()
        data = json.loads(r.read().decode() or "{}")
        conn.close()
        return r.status, data

    def login(self, nick):
        st, d = self._post("/api/login", {"nick": nick})
        assert st == 200 and d["ok"], d
        self.token = d["token"]
        self.uid = d["uid"]

    def group(self, action, **kw):
        st, d = self._post("/api/group", {"token": self.token,
                                          "action": action, **kw})
        assert st == 200 and d["ok"], d
        return d

    def detail(self, gid):
        st, d = self._get(f"/api/group_detail?token={self.token}&gid={gid}")
        assert st == 200 and d["ok"], d
        return d

    def read(self, channel, seq, to=None):
        body = {"token": self.token, "channel": channel, "seq": seq}
        if to is not None:
            body["to"] = to
        st, d = self._post("/api/read", body)
        assert st == 200 and d["ok"], d
        return d


@pytest.fixture()
def hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    wport = _free_port()
    httpd = serve_web(h, port=wport)
    time.sleep(0.2)
    yield h, port, wport, stop
    stop.set()
    time.sleep(0.2)


def test_web_group_manage_and_read(hub):
    h, port, wport, _ = hub
    u1 = _Web(wport, "绿灯主")
    u2 = _Web(wport, "黄灯客")

    # 1) 群主建群，成员加入
    d = u1.group("create", name="研发群", public=1)   # R54：公开群才可被直接加入
    gid = next(g["gid"] for g in d["groups"] if g["name"] == "研发群")
    u2.group("join", gid=gid)

    dt = u1.detail(gid)
    assert dt["member"] and dt["my_role"] == "owner"
    nicks = {m["nick"] for m in dt["members"]}
    assert nicks == {"绿灯主", "黄灯客"}

    # 2) 公告 / 设管理员 / 禁言 → detail 反映
    u1.group("announce", gid=gid, text="今晚发版")
    assert u1.detail(gid)["announce"] == "今晚发版"
    u1.group("admin", gid=gid, target=u2.uid, enable=True)
    u2role = next(m for m in u1.detail(gid)["members"] if m["uid"] == u2.uid)
    assert u2role["role"] == "admin"
    u1.group("mute", gid=gid, target=u2.uid, duration=600)
    u2m = next(m for m in u1.detail(gid)["members"] if m["uid"] == u2.uid)
    assert u2m["muted"] is True
    # 解禁
    u1.group("mute", gid=gid, target=u2.uid, duration=0)
    u2m = next(m for m in u1.detail(gid)["members"] if m["uid"] == u2.uid)
    assert u2m["muted"] is False

    # 3) 已读回执接口（公聊任意 seq，校验幂等不报错）
    u1.read("public", 1)
    # 未登录取群详情 → 401
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn.request("GET", f"/api/group_detail?token=bad&gid={gid}")
    r = conn.getresponse()
    assert r.status == 401
    conn.close()

    # 4) 成员被踢 → detail 不再含该成员
    u2.group("join", gid=gid)      # u2 先重新加入（模拟仍在群里被踢）
    u1.group("kick", gid=gid, target=u2.uid)
    u2role = None
    if u1.detail(gid).get("members"):
        u2role = next((m for m in u1.detail(gid)["members"] if m["uid"] == u2.uid), None)
    assert u2role is None