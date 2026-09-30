# -*- coding: utf-8 -*-
"""R34 群内话题 Threads 测试。

覆盖：
- 服务器：thread_root 校验（无效/跨频道/嵌套均拒绝）、正常回复透传广播、
  THREAD_FETCH → THREAD_HISTORY 环形过滤、群权限校验
- 网页端：/api/send 带 thread_root 落话题、/api/thread 拉取、权限 403
- 客户端：send_chat(thread_root=…) 入 header、send_thread_fetch、
  THREAD_HISTORY 进事件流、LocalHistory.thread_msgs 本地过滤
- UI：msg_list 徽标计数（set_thread_count → 估算增高 + raw 标记 + 渲染不崩）
"""
import http.client
import json
import socket
import threading
import time
import tkinter as tk
from dataclasses import replace

import pytest

from client_core import ClientCore, LocalHistory
from config import CFG
from protocol import MsgType
from server import Hub, serve as serve_tcp
from web import serve as serve_web
from widgets.msg_list import MsgList

FONT = ("Microsoft YaHei UI", 9)


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
    yield h, port, wport, stop
    stop.set()
    time.sleep(0.2)


class _Cli:
    __test__ = False

    def __init__(self, port, nick):
        from crypto import client_handshake
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.chan = client_handshake(self.sock)
        self.nick = nick
        self.uid = None
        self.events = []
        self._lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            while True:
                h, b = self.chan.recv_frame()
                with self._lock:
                    self.events.append((h, b))
        except Exception:
            pass

    def send(self, header, body=b""):
        self.chan.send_frame(header, body)

    def wait(self, t, timeout=3.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, (h, b) in enumerate(self.events):
                    if h.get("t") == t and (pred is None or pred(h)):
                        del self.events[i]
                        return h, b
            time.sleep(0.01)
        return None, None

    def hello(self):
        self.send({"t": "hello", "nick": self.nick})
        h, _ = self.wait("welcome")
        if h:
            self.uid = h["uid"]
        return h

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ================= 服务器：thread_root 校验与透传 =================

def test_thread_reply_ok_and_broadcast(hub):
    h, port, _w, _ = hub
    a, b = _Cli(port, "甲"), _Cli(port, "乙")
    a.hello(), b.hello()
    a.send({"t": "chat", "channel": "public", "text": "根消息"})
    h1, _ = a.wait("chat", pred=lambda x: x.get("uid") == a.uid)
    assert h1 and h1.get("seq")
    root = h1["seq"]

    a.send({"t": "chat", "channel": "public", "text": "话题回复",
            "thread_root": root})
    ha, _ = a.wait("chat", pred=lambda x: x.get("thread_root") == root)
    hb, _ = b.wait("chat", pred=lambda x: x.get("thread_root") == root)
    assert ha and hb                        # 发者与收者都拿到带 thread_root 的广播
    assert hb.get("seq") and hb["seq"] != root
    a.close(), b.close()


def test_thread_reject_bad_root(hub):
    h, port, _w, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    a.send({"t": "chat", "channel": "public", "text": "x", "thread_root": 99999})
    he, _ = a.wait("error", pred=lambda x: x.get("code") == "thread")
    assert he and "不存在" in (he.get("text") or "")
    a.close()


def test_thread_reject_cross_channel(hub):
    h, port, _w, _ = hub
    a, b = _Cli(port, "甲"), _Cli(port, "乙")
    a.hello(), b.hello()
    a.send({"t": "chat", "channel": "public", "text": "根"})
    h1, _ = a.wait("chat", pred=lambda x: x.get("uid") == a.uid)
    root = h1["seq"]
    a.send({"t": "chat", "channel": "private", "to": b.uid, "text": "私聊回复",
            "thread_root": root})
    he, _ = a.wait("error", pred=lambda x: x.get("code") == "thread")
    assert he and "频道" in (he.get("text") or "")
    a.close(), b.close()


def test_thread_reject_nested(hub):
    h, port, _w, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    a.send({"t": "chat", "channel": "public", "text": "根"})
    h1, _ = a.wait("chat", pred=lambda x: x.get("uid") == a.uid)
    root = h1["seq"]
    a.send({"t": "chat", "channel": "public", "text": "回复1", "thread_root": root})
    h2, _ = a.wait("chat", pred=lambda x: x.get("thread_root") == root)
    a.send({"t": "chat", "channel": "public", "text": "套娃",
            "thread_root": h2["seq"]})
    he, _ = a.wait("error", pred=lambda x: x.get("code") == "thread")
    assert he and "话题" in (he.get("text") or "")
    a.close()


def test_thread_fetch_history_and_permission(hub):
    h, port, _w, _ = hub
    a, b, c = _Cli(port, "甲"), _Cli(port, "乙"), _Cli(port, "丙")
    a.hello(), b.hello(), c.hello()
    a.send({"t": "chat", "channel": "public", "text": "根"})
    h1, _ = a.wait("chat", pred=lambda x: x.get("uid") == a.uid)
    root = h1["seq"]
    for i in range(3):
        a.send({"t": "chat", "channel": "public", "text": f"回复{i}",
                "thread_root": root})
    a.send({"t": "chat", "channel": "public", "text": "普通消息"})
    time.sleep(0.3)

    # 乙拉取话题：只含 thread_root 命中的 3 条
    b.send({"t": MsgType.THREAD_FETCH.value, "channel": "public",
            "root_seq": root})
    hth, _ = b.wait(MsgType.THREAD_HISTORY.value, timeout=3)
    assert hth and hth.get("root_seq") == root
    msgs = hth.get("msgs") or []
    assert len(msgs) == 3 and all(m.get("thread_root") == root for m in msgs)

    # 丙对群话题无权限 → deny
    c.send({"t": MsgType.THREAD_FETCH.value, "channel": "group",
            "to": 1, "root_seq": root})
    he, _ = c.wait("error", pred=lambda x: x.get("code") == "deny")
    assert he
    a.close(), b.close(), c.close()


# ================= 网页端 =================

def test_web_send_thread_and_fetch(hub):
    h, _port, wport, _ = hub
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)

    def post(path, obj):
        conn.request("POST", path, json.dumps(obj).encode(),
                     {"Content-Type": "application/json"})
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read().decode())

    st, d = post("/api/login", {"nick": "网页甲"})
    assert st == 200 and d["ok"]
    token = d["token"]
    # 根消息（普通 send）
    st, d = post("/api/send", {"token": token, "channel": "public", "text": "根"})
    assert d["ok"]
    time.sleep(0.2)
    # 话题回复
    st, d = post("/api/send", {"token": token, "channel": "public",
                               "text": "网页回复", "thread_root": 1})
    assert d["ok"]
    time.sleep(0.2)
    st, d = post("/api/thread", {"token": token, "channel": "public",
                                 "root_seq": 1})
    assert st == 200 and d["ok"]
    msgs = d.get("msgs") or []
    assert len(msgs) == 1 and msgs[0]["text"] == "网页回复"
    assert msgs[0]["thread_root"] == 1
    # 非群成员查群话题（不存在群）→ 403（私聊键天然含请求者本人，无 403 分支）
    st, d = post("/api/thread", {"token": token, "channel": "group",
                                 "to": 999, "root_seq": 1})
    assert st == 403
    conn.close()


# ================= 客户端核心 =================

def test_core_send_thread_and_dispatch(tmp_path):
    core = ClientCore(nick="测试", history_dir=str(tmp_path / "d"))
    calls = []

    def fake_send(header, body=b""):
        calls.append(header)
        return True

    core._send_frame = fake_send
    assert core.send_chat("hi", thread_root=42)
    assert calls[-1]["thread_root"] == 42
    assert core.send_thread_fetch("public", None, 42)
    assert calls[-1]["t"] == MsgType.THREAD_FETCH.value
    assert calls[-1]["root_seq"] == 42


def test_core_thread_history_event_and_local_filter(tmp_path):
    core = ClientCore(nick="测试", history_dir=str(tmp_path / "d1"))
    core._push({"t": MsgType.THREAD_HISTORY.value, "root_seq": 7, "msgs": [1, 2]})
    ev = core.events.get_nowait()          # events 为 Queue：THREAD_HISTORY 进事件流
    assert ev["t"] == MsgType.THREAD_HISTORY.value and ev["root_seq"] == 7
    # LocalHistory.thread_msgs：混存频道里按 thread_root 过滤
    lh = LocalHistory(base_dir=str(tmp_path / "d2"))
    lh.add("public", {"seq": 1, "text": "根"})
    lh.add("public", {"seq": 2, "text": "回1", "thread_root": 1})
    lh.add("public", {"seq": 3, "text": "回2", "thread_root": 1})
    lh.add("public", {"seq": 4, "text": "回3", "thread_root": 2})
    assert [m["seq"] for m in lh.thread_msgs("public", 1)] == [2, 3]
    assert [m["seq"] for m in lh.thread_msgs("public", 2)] == [4]
    assert lh.thread_msgs("public", 99) == []


# ================= UI：徽标 =================

@pytest.fixture(scope="module")
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def test_thread_badge_estimate_and_render(root):
    opened = []
    ml = MsgList(root, FONT, me_uid=1,
                 on_open_thread=lambda row: opened.append(row))
    ml.configure(width=400, height=400)
    try:
        ml.append({"uid": 2, "nick": "乙", "channel": "public",
                   "ts": time.time(), "text": "根消息", "seq": 50})
        i = ml.count - 1
        est0 = ml._estimate(i, ml._rows[i])
        ml.set_thread_count(50, 3)
        est1 = ml._estimate(i, ml._rows[i])
        assert est1 == est0 + ml._thread_badge_h(ml._rows[i])   # 估算含徽标占位
        assert ml._rows[i].raw.get("thread_count") == 3
        ml._render()                                             # 渲染不崩
        ml.set_thread_count(50, 0)                               # 归零摘徽标
        assert "thread_count" not in ml._rows[i].raw
        assert ml._estimate(i, ml._rows[i]) == est0
        # 点击徽标 → 回调携带 row（模拟）
        ml._on_open_thread(ml._rows[i])
        assert opened and opened[0].raw.get("seq") == 50
    finally:
        ml.destroy()
