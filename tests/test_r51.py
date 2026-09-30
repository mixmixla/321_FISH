# -*- coding: utf-8 -*-
"""R51 P1 优化回归：服务器权威定时消息 + 私聊双向删除。

P1-1 服务器权威定时消息（客户端离线也到点发出）：
- SCHED_SET 校验（频道/文本/时间/私聊目标）→ 入服务器队列并持久化；
- sweeper 到点以创建者身份入频道历史并广播（创建者已离线仍发出）；
- SCHED_CANCEL 取消、SCHED_LIST 拉取；
- 队列随 R16 快照持久化，重启恢复（已到点项不再补发）。

P1-2 双向删除：
- MSG_DEL 带 scope：默认 self 仅本人；私聊 scope=both 双方均可删；
- 公开/群聊非本人删除仍被拒；私聊对端 scope=self 仍被拒。

网页端：/api/sched（set/cancel/list）+ /api/del（scope）。
"""
import json
import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from protocol import MsgType
from server import Hub, serve as serve_tcp
from web import serve as serve_web


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    wport = _free_port()
    httpd = serve_web(h, port=wport)
    time.sleep(0.2)
    yield h, wport, stop
    stop.set()
    time.sleep(0.2)


class _Sess:
    """伪造 TCP 会话：注册进 hub，send 收集所有帧（含 error）。"""
    __test__ = False

    def __init__(self, hub: Hub, nick: str):
        self.hub = hub
        self.frames = []
        self.uid = 0
        self.nick = nick
        self.type = "tcp"
        self.peer_ip = "127.0.0.1"
        self.closed = False
        self.last_seen = time.time()
        self.is_admin = False        # R53：welcome 帧读取，假会话需显式声明
        self.close_conn = lambda: None
        hub._attach(self)

    def send(self, payload: dict):
        self.frames.append(payload)

    def touch(self):
        self.last_seen = time.time()

    def last_frame(self, t: str) -> dict | None:
        for f in reversed(self.frames):
            if f.get("t") == t:
                return f
        return None

    def errors(self) -> list:
        return [f for f in self.frames if f.get("t") == "error"]


class _Web:
    """轻量 web 客户端：登录拿 token；POST/GET 封装。"""
    __test__ = False

    def __init__(self, port, nick):
        self.port = port
        self.token = None
        self.uid = None
        self.login(nick)

    def _req(self, method, path, body=None):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        if body is not None:
            conn.request(method, path, json.dumps(body).encode(),
                         {"Content-Type": "application/json"})
        else:
            conn.request(method, path)
        r = conn.getresponse()
        data = json.loads(r.read().decode() or "{}")
        conn.close()
        return r.status, data

    def login(self, nick):
        st, d = self._req("POST", "/api/login", {"nick": nick})
        assert st == 200 and d["ok"], d
        self.token = d["token"]
        self.uid = d["uid"]
        self.last_login = d

    def sched(self, body):
        body = dict(body)
        body["token"] = self.token
        return self._req("POST", "/api/sched", body)

    def delete(self, seq, scope="self"):
        return self._req("POST", "/api/del",
                         {"token": self.token, "seq": seq, "scope": scope})

    def send(self, channel="public", to=None, text="hi"):
        body = {"token": self.token, "channel": channel, "text": text}
        if to is not None:
            body["to"] = to
        return self._req("POST", "/api/send", body)


# ================= P1-1 服务器权威定时消息 =================

def test_sched_set_validates_and_stores(hub):
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    now = time.time()
    # 过去时间被拒
    h.dispatch(a, {"t": MsgType.SCHED_SET.value, "channel": "public",
                   "text": "x", "fire_at": now - 1})
    assert any(f.get("code") == "past" for f in a.errors())
    # 空文本被拒
    h.dispatch(a, {"t": MsgType.SCHED_SET.value, "channel": "public",
                   "text": "  ", "fire_at": now + 60})
    assert any(f.get("code") == "empty" for f in a.errors())
    # 未知频道被拒
    h.dispatch(a, {"t": MsgType.SCHED_SET.value, "channel": "void",
                   "text": "x", "fire_at": now + 60})
    assert any(f.get("code") == "channel" for f in a.errors())
    # 合法创建 → 队列有 1 条，回帧 SCHED_LIST
    h.dispatch(a, {"t": MsgType.SCHED_SET.value, "channel": "public",
                   "text": "早上好", "fire_at": now + 120})
    assert len(h.scheds.get(a.uid, {})) == 1
    stored = next(iter(h.scheds[a.uid].values()))
    assert stored["text"] == "早上好" and stored["channel"] == "public"
    lst = a.last_frame("sched_list")
    assert lst and len(lst.get("items", [])) == 1
    assert lst["items"][0]["text"] == "早上好"


def test_sched_fires_via_sweeper_even_offline(hub):
    """创建者离线后，到点定时消息仍以创建者身份发出（服务器权威）。"""
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    b = _Sess(h, "乙")
    now = time.time()
    h.dispatch(a, {"t": MsgType.SCHED_SET.value, "channel": "private",
                   "to": b.uid, "text": "到点见", "fire_at": now + 5})
    rid = next(iter(h.scheds[a.uid]))
    h.unregister(a, "offline")                       # 创建者下线
    h._sweep_scheds(now + 6)                          # sweeper 手动拨到点
    assert h.scheds.get(a.uid) in (None, {})         # 到期项已出队
    key = f"private:{min(a.uid, b.uid)}:{max(a.uid, b.uid)}"
    msgs = [m for m in h.bus.history(key) if m.get("text") == "到点见"]
    assert msgs and msgs[0]["uid"] == a.uid and msgs[0]["to"] == b.uid
    # 目标端（乙）收到广播帧
    got = [f for f in b.frames if f.get("t") == "chat" and f.get("text") == "到点见"]
    assert got


def test_sched_cancel_and_list(hub):
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    now = time.time()
    h.dispatch(a, {"t": MsgType.SCHED_SET.value, "channel": "public",
                   "text": "t1", "fire_at": now + 60})
    rid = next(iter(h.scheds[a.uid]))
    # SCHED_LIST 显式拉取
    h.dispatch(a, {"t": MsgType.SCHED_LIST.value})
    assert a.last_frame("sched_list")["items"][0]["rid"] == rid
    # 取消后队列清空
    h.dispatch(a, {"t": MsgType.SCHED_CANCEL.value, "rid": rid})
    assert not h.scheds.get(a.uid)
    assert a.last_frame("sched_list")["items"] == []


def test_sched_private_unknown_target_rejected(hub):
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    now = time.time()
    h.dispatch(a, {"t": MsgType.SCHED_SET.value, "channel": "private",
                   "to": 999999, "text": "x", "fire_at": now + 60})
    assert any(f.get("code") == "offline" for f in a.errors())


def test_sched_persist_restore(tmp_path):
    """R51 队列随快照持久化；重启恢复后未到点项保留、已到点项丢弃。"""
    store_dir = str(tmp_path / "store")
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"))
    h1 = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"), store_dir=store_dir)
    a = _Sess(h1, "甲")
    now = time.time()
    h1.dispatch(a, {"t": MsgType.SCHED_SET.value, "channel": "public",
                    "text": "保留我", "fire_at": now + 3600})
    h1.dispatch(a, {"t": MsgType.SCHED_SET.value, "channel": "public",
                    "text": "已到点", "fire_at": now + 2})
    h1._persist(force=True)                          # 快照含两条
    h1._sweep_scheds(now + 3)                        # 到点项被消费
    h1._persist(force=True)                          # 快照只剩未到点项
    state = h1.store.load()
    assert "scheds" in state                          # 队列确实持久化

    # 重启恢复：快照中未到点项保留（h1 sweep 已消费到点项，快照只含未到点项）
    h1._persist(force=True)
    h2 = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"), store_dir=store_dir)
    assert len(h2.scheds.get(a.uid, {})) == 1
    r = next(iter(h2.scheds[a.uid].values()))
    assert r["text"] == "保留我"


# ================= P1-2 私聊双向删除 =================

def _send_private(h, a, b, text="私聊内容"):
    h.dispatch(a, {"t": MsgType.CHAT.value, "channel": "private",
                   "to": b.uid, "text": text})
    key = f"private:{min(a.uid, b.uid)}:{max(a.uid, b.uid)}"
    msgs = h.bus.history(key)
    return msgs[-1]["seq"]


def test_del_own_any_channel(hub):
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    seq = _send_private(h, a, a, "收藏夹草稿")          # 发给自己的收藏夹
    h.dispatch(a, {"t": MsgType.MSG_DEL.value, "seq": seq, "scope": "self"})
    _key, msg = h.bus.find(seq)
    assert msg["deleted"] and msg["text"] == ""


def test_del_private_peer_scope_both(hub):
    """私聊中，对端可用 scope=both 删除对方消息。"""
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    b = _Sess(h, "乙")
    seq = _send_private(h, a, b, "被乙撤回")
    h.dispatch(b, {"t": MsgType.MSG_DEL.value, "seq": seq, "scope": "both"})
    _key, msg = h.bus.find(seq)
    assert msg["deleted"]
    assert not any(f.get("code") == "forbid" for f in b.errors())


def test_del_private_peer_scope_self_rejected(hub):
    """私聊对端用 scope=self 删对方消息 → 拒绝。"""
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    b = _Sess(h, "乙")
    seq = _send_private(h, a, b)
    h.dispatch(b, {"t": MsgType.MSG_DEL.value, "seq": seq, "scope": "self"})
    assert any(f.get("code") == "forbid" for f in b.errors())
    _key, msg = h.bus.find(seq)
    assert not msg.get("deleted")


def test_del_public_non_owner_rejected(hub):
    """公开频道非本人删除（即使 scope=both）→ 拒绝。"""
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    b = _Sess(h, "乙")
    h.dispatch(a, {"t": MsgType.CHAT.value, "channel": "public", "text": "公聊"})
    seq = h.bus.history("all")[-1]["seq"]
    h.dispatch(b, {"t": MsgType.MSG_DEL.value, "seq": seq, "scope": "both"})
    assert any(f.get("code") == "forbid" for f in b.errors())
    _key, msg = h.bus.find(seq)
    assert not msg.get("deleted")


# ================= 网页端接口 =================

def test_web_sched_and_del(hub):
    h, wport, _ = hub
    u1 = _Web(wport, "红宝")
    u2 = _Web(wport, "蓝宝")
    now = time.time()
    # 定时：set → list 可见；登录响应也带 scheds
    st, d = u1.sched({"action": "set", "channel": "public", "text": "定时公聊",
                      "minutes": 5})
    assert st == 200 and d["ok"], d
    st, d = u1.sched({"action": "list"})
    assert st == 200 and d["ok"]
    assert any(r["text"] == "定时公聊" for r in d["scheds"])
    # 取消
    rid = next(r["rid"] for r in d["scheds"] if r["text"] == "定时公聊")
    u1.sched({"action": "cancel", "rid": rid})
    st, d = u1.sched({"action": "list"})
    assert not d["scheds"]
    # 私聊 + 双向删除
    u1.send(channel="private", to=u2.uid, text="网页私聊")
    key = f"private:{min(u1.uid, u2.uid)}:{max(u1.uid, u2.uid)}"
    seq = h.bus.history(key)[-1]["seq"]
    st, d = u2.delete(seq, scope="both")
    assert st == 200 and d["ok"]
    _key, msg = h.bus.find(seq)
    assert msg["deleted"]
