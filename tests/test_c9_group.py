# -*- coding: utf-8 -*-
"""C9 群协作批：
② 群@已读 by N 逐人统计（MSG_READERS：已读/未读成员集、count/total、权限）；
① 群公告置顶 + 仅公告说话模式（GROUP_ANN_MODE：普通成员被拒 / owner 通过 /
   公告引用互动放行 / 权限校验）。
独立跑：python -m pytest tests/test_c9_group.py -q
"""
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
from test_server import TestClient


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)
    yield h, port, stop
    stop.set()
    time.sleep(0.2)


def _make(hub):
    _h, port, _stop = hub
    return port


def _setup_group(hub, owner_name="alice", members=("bob",)):
    port = _make(hub)
    o = TestClient(port, owner_name)
    o.hello()
    o.send({"t": "group_create", "name": "群A", "public": 1})
    gs = o.wait("group_state", pred=lambda e: e.get("name") == "群A")
    gid = gs["gid"]
    clients = [o]
    for name in members:
        m = TestClient(port, name)
        m.hello()
        m.send({"t": "group_join", "gid": gid})
        assert m.wait("group_state", pred=lambda e: e.get("gid") == gid)
        clients.append(m)
    return o, gid, clients, port


# ---------- ② 群@已读 by N 逐人统计 ----------
def test_msg_readers_group_summary(hub):
    owner, gid, (o, b), port = _setup_group(hub, members=("bob",))
    key = f"group:{gid}"
    # owner 发一条 @ 群消息
    o.send({"t": "chat", "channel": "group", "to": gid,
            "text": "@bob 今晚节奏快点", "mentions": [b.uid]})
    msg = b.wait("chat", pred=lambda e: e.get("text", "").startswith("@bob"))
    seq = msg["seq"]
    # 初始无人已读（都还没发读回执）→ count=0, total=2, unread=2
    o.send({"t": "msg_readers", "key": key, "seq": seq})
    r = o.wait("msg_readers", pred=lambda e: e.get("seq") == seq)
    assert r is not None, "缺少 msg_readers 回帧"
    assert r["total"] == 2 and r["count"] == 0
    assert len(r["unread"]) == 2
    # bob 读到本条之后 → count=1，unread 剩 owner
    b.send({"t": "read", "channel": "group", "to": gid, "seq": seq})
    time.sleep(0.1)
    o.send({"t": "msg_readers", "key": key, "seq": seq})
    r2 = o.wait("msg_readers", pred=lambda e: e.get("seq") == seq)
    assert r2["count"] == 1 and r2["total"] == 2
    assert {m["uid"] for m in r2["members"]} == {b.uid}
    assert {m["uid"] for m in r2["unread"]} == {owner.uid}

    # 读到更远的 seq 也计入本条已读
    b.send({"t": "read", "channel": "group", "to": gid, "seq": seq + 5})
    time.sleep(0.1)
    o.send({"t": "msg_readers", "key": key, "seq": seq})
    r3 = o.wait("msg_readers", pred=lambda e: e.get("seq") == seq)
    assert r3["count"] == 1

    # 非群成员无权查
    outsider = TestClient(port, "eve")
    outsider.hello()
    outsider.send({"t": "msg_readers", "key": key, "seq": seq})
    assert outsider.wait("error", timeout=1) is not None

    # 仅支持群 key
    o.send({"t": "msg_readers", "key": "public", "seq": 1})
    assert o.wait("error", pred=lambda e: e.get("code") == "key", timeout=1) is not None

    for c in (o, b):
        c.close()
    outsider.close()


# ---------- ① 仅公告说话模式 ----------
def test_announce_mode_blocks_normal_member(hub):
    owner, gid, (o, b), port = _setup_group(hub, members=("bob",))
    # 群主设公告为一条消息：先 pin 群内某条作为"公告"（复用 pin 置顶=公告）
    o.send({"t": "chat", "channel": "group", "to": gid, "text": "这是群公告"})
    ann = b.wait("chat", pred=lambda e: e.get("text") == "这是群公告")
    ann_seq = ann["seq"]
    o.send({"t": "pin", "channel": "group", "to": gid, "seq": ann_seq, "on": True})
    # 开启仅公告说话模式
    o.send({"t": "group_ann_mode", "gid": gid, "on": True})
    gs = o.wait("group_state", pred=lambda e: e.get("gid") == gid and e.get("announce_mode") == 1)
    assert gs is not None

    # 普通成员 bob 发普通正文 → 被拒 announce_only
    b.send({"t": "chat", "channel": "group", "to": gid, "text": "我来说两句"})
    err = b.wait("error", pred=lambda e: e.get("code") == "announce_only", timeout=2)
    assert err is not None

    # bob 回复引用公告 → 放行
    b.send({"t": "chat", "channel": "group", "to": gid,
            "text": "收到", "reply": {"nick": "alice", "text": "这是群公告", "seq": ann_seq}})
    got = o.wait("chat", pred=lambda e: e.get("reply") and e["reply"].get("seq") == ann_seq, timeout=2)
    assert got is not None

    # bob 回复引用别的消息 → 也被拒
    b.send({"t": "chat", "channel": "group", "to": gid, "text": "别的",
            "reply": {"nick": "alice", "text": "x", "seq": ann_seq + 1}})
    assert b.wait("error", pred=lambda e: e.get("code") == "announce_only", timeout=2) is not None

    # 群主不受限
    o.send({"t": "chat", "channel": "group", "to": gid, "text": "群主可以发"})
    assert b.wait("chat", pred=lambda e: e.get("text") == "群主可以发", timeout=2) is not None

    for c in (o, b):
        c.close()


def test_announce_mode_permission_and_persist(hub):
    owner, gid, (o, b), _port = _setup_group(hub, members=("bob",))
    # 普通成员不能开模式
    b.send({"t": "group_ann_mode", "gid": gid, "on": True})
    assert b.wait("error", pred=lambda e: e.get("code") == "perm", timeout=2) is not None
    # 群主能开/关
    o.send({"t": "group_ann_mode", "gid": gid, "on": True})
    assert o.wait("group_state", pred=lambda e: e.get("announce_mode") == 1, timeout=2)
    o.send({"t": "group_ann_mode", "gid": gid, "on": False})
    assert o.wait("group_state", pred=lambda e: e.get("announce_mode") == 0, timeout=2)
    for c in (o, b):
        c.close()


# ---------- ②/① web HTTP 对等端点 ----------
class _Web:
    """轻量 web HTTP 客户端（仿 test_web_group_read._Web）。"""
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
        self.token, self.uid = d["token"], d["uid"]

    def group(self, action, **kw):
        st, d = self._post("/api/group", {"token": self.token,
                                          "action": action, **kw})
        assert st == 200 and d["ok"], d
        return d

    def detail(self, gid):
        st, d = self._get(f"/api/group_detail?token={self.token}&gid={gid}")
        assert st == 200 and d["ok"], d
        return d

    def readers(self, key, seq):
        return self._post("/api/readers", {"token": self.token,
                                           "key": key, "seq": seq})

    def send(self, channel, seq, to=None):
        body = {"token": self.token, "channel": channel, "seq": seq}
        if to is not None:
            body["to"] = to
        st, d = self._post("/api/read", body)
        assert st == 200 and d["ok"], d
        return d


def test_web_c9_readers_and_annmode(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    wport = _free_port()
    serve_web(h, port=wport)
    time.sleep(0.2)
    try:
        u1 = _Web(wport, "群主")
        u2 = _Web(wport, "队员")
        d = u1.group("create", name="协作群", public=1)
        gid = next(g["gid"] for g in d["groups"] if g["name"] == "协作群")
        u2.group("join", gid=gid)
        key = f"group:{gid}"

        # 普通成员开模式被服务端拒（web 转发层不翻转状态，权限在 socket 层强制）→ detail 仍 0
        u2.group("ann_mode", gid=gid, on=True)
        assert u1.detail(gid)["announce_mode"] == 0
        # 群主开模式 → detail 反映 announce_mode==1
        u1.group("ann_mode", gid=gid, on=True)
        assert u1.detail(gid)["announce_mode"] == 1

        # /api/readers：无人已读 → count 0 total 2；成员回读 → count 1
        st, r0 = u2.readers(key, 1)
        assert st == 200 and r0["ok"] and r0["total"] == 2 and r0["count"] == 0
        u2.send("group", 1, to=gid)
        time.sleep(0.1)
        st, r1 = u2.readers(key, 1)
        assert r1["ok"] and r1["count"] == 1
        assert {m["nick"] for m in r1["members"]} == {"队员"}
        # 非群 key → 400
        st, bad = u2.readers("public", 1)
        assert st == 400 and not bad["ok"]
    finally:
        stop.set()
        time.sleep(0.2)