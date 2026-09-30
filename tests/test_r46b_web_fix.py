# -*- coding: utf-8 -*-
"""R46b 网页端联调修复回归：纯表情消息渲染 / 📎 图片附件自动内联。

背景（真机联调发现）：
- 服务器纯表情消息只带 sticker 字段、无 text 键（server._on_chat 仅非空才入 msg），
  网页端 addMsg 旧分支要求 e.text!==undefined → 气泡渲染成空行，点表情「像没发出去」；
- 网页端 📎 以 kind="file" 发图片 → 对端网页只出下载链接，不出内联 <img>。
覆盖：
- 服务器契约：纯表情 chat 事件带 sticker、无 text 键（JS 分支修复依据）；
- /api/upload：kind="file" + 图片扩展名 → 自动改写为 image；普通扩展名保持 file；
- /api/file：Content-Type 按扩展名（png/jpg），非图片仍 octet-stream。
"""
import base64
import http.client
import json
import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, serve as serve_tcp
from stickers import STICKER_PACK
from web import COOKIE_NAME, serve as serve_web


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def env(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    tcp_port = _free_port()
    web_port = _free_port()
    stop_tcp = threading.Event()
    stop_web = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, tcp_port, stop_tcp, False),
                     daemon=True).start()
    threading.Thread(target=serve_web, args=(h, web_port, stop_web, False),
                     daemon=True).start()
    time.sleep(0.2)
    yield h, tcp_port, web_port
    stop_web.set()
    stop_tcp.set()
    time.sleep(0.2)


class _Cli:
    """TCP 加密客户端（服务器契约验证用）。"""

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
                hdr, body = self.chan.recv_frame()
                with self._lock:
                    self.events.append((hdr, body))
        except Exception:
            pass

    def send(self, header, body=b""):
        self.chan.send_frame(header, body)

    def wait(self, t, timeout=3.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, (h, _b) in enumerate(self.events):
                    if h.get("t") == t and (pred is None or pred(h)):
                        del self.events[i]
                        return h
            time.sleep(0.01)
        return None

    def hello(self):
        self.send({"t": "hello", "nick": self.nick})
        hdr = self.wait("welcome")
        if hdr:
            self.uid = hdr["uid"]
        return hdr

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class _Web:
    """轻量 HTTP 客户端（Cookie 登录态）。"""

    def __init__(self, port):
        self.port = port
        self.cookie = ""

    def _post(self, path, body):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=8)
        headers = {"Content-Type": "application/json"}
        if self.cookie:
            headers["Cookie"] = self.cookie
        conn.request("POST", path, json.dumps(body).encode(), headers)
        r = conn.getresponse()
        data = json.loads(r.read().decode() or "{}")
        sc = r.getheader("Set-Cookie") or ""
        conn.close()
        if sc.startswith(f"{COOKIE_NAME}="):
            self.cookie = sc.split(";")[0]
        return r.status, data

    def _get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=8)
        headers = {"Cookie": self.cookie} if self.cookie else {}
        conn.request("GET", path, headers=headers)
        r = conn.getresponse()
        raw = r.read()
        ctype = r.getheader("Content-Type") or ""
        conn.close()
        return r.status, raw, ctype

    def login(self, nick):
        status, data = self._post("/api/login", {"nick": nick})
        assert status == 200 and data.get("ok"), data
        return data


# ============ 服务器契约：纯表情消息无 text 键 ============

def test_sticker_only_event_has_sticker_no_text(env):
    """纯表情 chat：服务器事件只带 sticker 字段、无 text 键（网页端分支修复依据）。"""
    _h, tcp_port, _web_port = env
    code = STICKER_PACK[0]["code"]
    a = _Cli(tcp_port, "甲")
    try:
        assert a.hello()
        a.send({"t": "chat", "channel": "public", "text": "", "sticker": code})
        ev = a.wait("chat", timeout=3.0,
                    pred=lambda x: x.get("sticker") == code)
        assert ev is not None, "未收到纯表情回显"
        assert "text" not in ev                     # 旧 JS 分支因此漏渲染
        assert ev["sticker"] == code
    finally:
        a.close()


def test_text_sticker_mixed_keeps_both(env):
    """文本+表情混合：text 与 sticker 同时在事件里。"""
    _h, tcp_port, _web_port = env
    code = STICKER_PACK[0]["code"]
    a = _Cli(tcp_port, "乙")
    try:
        assert a.hello()
        a.send({"t": "chat", "channel": "public",
                "text": f"你好 :{code}:", "sticker": code})
        ev = a.wait("chat", timeout=3.0,
                    pred=lambda x: x.get("sticker") == code)
        assert ev is not None and ev.get("text") == f"你好 :{code}:"
    finally:
        a.close()


# ============ /api/upload：图片扩展名自动改写 kind ============

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
_JPG = b"\xff\xd8\xff\xe0" + b"0" * 64


def test_upload_file_with_image_ext_becomes_image(env):
    """📎 以 kind=file 上传 .PNG → 服务器自动改写为 image（网页端内联 <img>）。"""
    _h, _tcp_port, web_port = env
    w = _Web(web_port)
    w.login("丙")
    status, data = w._post("/api/upload", {
        "token": "", "name": "截图.PNG", "kind": "file",
        "data": base64.b64encode(_PNG).decode()})
    assert status == 200 and data["ok"], data
    assert data["file"]["kind"] == "image"
    assert data["file"]["name"] == "截图.PNG"


def test_upload_plain_file_stays_file(env):
    """非图片扩展名保持 file（下载链接语义不变）。"""
    _h, _tcp_port, web_port = env
    w = _Web(web_port)
    w.login("丁")
    status, data = w._post("/api/upload", {
        "token": "", "name": "说明.txt", "kind": "file",
        "data": base64.b64encode("hello".encode()).decode()})
    assert status == 200 and data["ok"], data
    assert data["file"]["kind"] == "file"


def test_upload_jpe_gif_bmp_webp_rewrite(env):
    """jpg/jpeg/gif/bmp/webp 同样改写为 image。"""
    _h, _tcp_port, web_port = env
    w = _Web(web_port)
    w.login("戊")
    for name in ("a.jpg", "b.jpeg", "c.gif", "d.bmp", "e.webp"):
        status, data = w._post("/api/upload", {
            "token": "", "name": name, "kind": "file",
            "data": base64.b64encode(_JPG).decode()})
        assert status == 200 and data["file"]["kind"] == "image", (name, data)


# ============ /api/file：Content-Type 按扩展名 ============

def test_file_content_type_by_ext(env):
    """png→image/png、jpg→image/jpeg、txt→application/octet-stream。"""
    _h, _tcp_port, web_port = env
    w = _Web(web_port)
    w.login("己")
    for name, raw, want in (("p.png", _PNG, "image/png"),
                            ("p.jpg", _JPG, "image/jpeg"),
                            ("p.txt", b"x", "application/octet-stream")):
        status, data = w._post("/api/upload", {
            "token": "", "name": name, "kind": "file",
            "data": base64.b64encode(raw).decode()})
        assert status == 200 and data["ok"], data
        fid = data["file"]["fid"]
        _s, _raw, ctype = w._get(f"/api/file?fid={fid}")
        assert ctype == want, (name, ctype)
