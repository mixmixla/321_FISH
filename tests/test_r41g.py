# -*- coding: utf-8 -*-
"""R41G 网页端引用补全回归：/api/send 引用快照透传与净化。

- 带 reply={nick,text,seq} 发送 → 公共历史含 reply（桌面端 msg_list 读同一
  字段，web↔桌面互通）；
- 非法输入净化（浏览器输入属边界）：非 dict 忽略、seq 非整型剥除、
  缺 nick/text 丢弃、超长 nick/text 截断。
"""
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


class _Web:
    """轻量 web HTTP 客户端：登录拿 token + 通用 POST/GET。"""
    __test__ = False

    def __init__(self, port, nick):
        self.port = port
        self.token = None
        self.uid = None
        self.login(nick)

    def _post(self, path, body):
        import http.client
        import json
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", path, json.dumps(body).encode(),
                     {"Content-Type": "application/json"})
        r = conn.getresponse()
        data = json.loads(r.read().decode() or "{}")
        conn.close()
        return r.status, data

    def _get(self, path):
        import http.client
        import json
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

    def send(self, text, reply=None):
        body = {"token": self.token, "channel": "public", "text": text}
        if reply is not None:
            body["reply"] = reply
        return self._post("/api/send", body)

    def history(self):
        st, d = self._get(f"/api/history?token={self.token}&channel=public")
        assert st == 200 and d["ok"], d
        return d["msgs"]


def _by_text(msgs, text):
    return next(m for m in msgs if m.get("text") == text)


def test_web_reply_roundtrip(hub):
    """带引用快照发送 → 双方历史里都有 reply，seq 指向被引用消息。"""
    h, port, wport, _ = hub
    u1 = _Web(wport, "引用源")
    u2 = _Web(wport, "引用者")

    u1.send("被引用的消息")
    seq = _by_text(u1.history(), "被引用的消息")["seq"]

    st, d = u2.send("回复内容",
                    reply={"nick": "引用源", "text": "被引用的消息", "seq": seq})
    assert st == 200 and d["ok"], d

    for u in (u1, u2):                       # 发送者与接收者视角一致（互通）
        m = _by_text(u.history(), "回复内容")
        assert m["reply"]["nick"] == "引用源"
        assert m["reply"]["text"] == "被引用的消息"
        assert m["reply"]["seq"] == seq


def test_web_reply_sanitized(hub):
    """浏览器侧乱造的 reply 逐项净化，不污染协议。"""
    h, port, wport, _ = hub
    u = _Web(wport, "净化员")
    u.send("基线消息")

    # 非 dict → 整体忽略
    st, d = u.send("r1", reply="不是字典")
    assert st == 200 and d["ok"]
    assert "reply" not in _by_text(u.history(), "r1")

    # seq 非整型 → 剥除 seq，nick/text 保留
    u.send("r2", reply={"nick": "甲", "text": "t", "seq": "abc"})
    m = _by_text(u.history(), "r2")
    assert m["reply"]["nick"] == "甲" and m["reply"]["text"] == "t"
    assert "seq" not in m["reply"]

    # 缺 nick/text → 快照无意义，整体丢弃
    u.send("r3", reply={"seq": 5})
    assert "reply" not in _by_text(u.history(), "r3")

    # 超长 nick/text 截断；合法 seq 保留
    u.send("r4", reply={"nick": "甲" * 100, "text": "长" * 300, "seq": 7})
    m = _by_text(u.history(), "r4")
    assert m["reply"]["nick"] == "甲" * 64
    assert m["reply"]["text"] == "长" * 200
    assert m["reply"]["seq"] == 7
