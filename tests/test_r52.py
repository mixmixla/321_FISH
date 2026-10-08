# -*- coding: utf-8 -*-
"""R52 微信三栏 UI 配套：头像 + 个性签名 + 网页端资料 API。

- AVATAR_SET：校验（格式白名单 / 大小 ≤1MB / 非空）→ 落盘 avatars/{uid}.{ext}、
  known["avatar"] 记录、AVATAR_DATA 回帧、roster 广播（含 avatar/sign）；
- AVATAR_DEL：删文件 + 清 known 记录 + AVATAR_DATA ext="" 回帧 + roster 广播；
- AVATAR_GET：有头像单播字节 / 无头像 ext=""；
- SIGN_SET：服务器权威截断（≤60 字符）→ known["sign"] + roster 广播；
- 快照持久化：avatar ext / sign 随重启恢复；
- 网页端：/api/avatar（POST set/del + GET 直出字节）、/api/profile（签名）。
"""
import json
import os
import socket
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from config import CFG
from server_recovery import StoreCoordinator
from protocol import MsgType
from server import Hub, serve as serve_tcp
from web import serve as serve_web

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 256   # 服务器只验格式/大小，不解析图片内容


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

    def send(self, payload: dict, body: bytes = b""):
        f = dict(payload)
        if body:
            f["_body"] = body
        self.frames.append(f)

    def touch(self):
        self.last_seen = time.time()

    def last_frame(self, t: str) -> dict | None:
        for f in reversed(self.frames):
            if f.get("t") == t:
                return f
        return None

    def roster(self) -> dict | None:
        return self.last_frame("roster")

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

    def _req(self, method, path, body=None, raw=False):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        if body is not None:
            conn.request(method, path, json.dumps(body).encode(),
                         {"Content-Type": "application/json"})
        else:
            conn.request(method, path)
        r = conn.getresponse()
        data = r.read()
        conn.close()
        if not raw:
            try:
                return r.status, json.loads(data.decode() or "{}")
            except (ValueError, UnicodeDecodeError):
                return r.status, {}
        return r.status, data

    def login(self, nick):
        st, d = self._req("POST", "/api/login", {"nick": nick})
        assert st == 200 and d["ok"], d
        self.token = d["token"]
        self.uid = d["uid"]
        self.last_login = d

    def avatar_set(self, ext, data):
        import base64
        return self._req("POST", "/api/avatar",
                         {"token": self.token, "op": "set", "ext": ext,
                          "data": base64.b64encode(data).decode()})

    def avatar_del(self):
        return self._req("POST", "/api/avatar", {"token": self.token, "op": "del"})

    def avatar_get(self, uid, token=None):
        tok = token if token is not None else self.token
        return self._req("GET", f"/api/avatar?uid={uid}&token={tok}", raw=True)

    def profile(self, sign):
        return self._req("POST", "/api/profile", {"token": self.token, "sign": sign})


def _avatar_dir(h: Hub) -> str:
    return h.avatar_dir


# ================= 头像：TCP 协议帧 =================

def test_avatar_set_validation(hub):
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    # 非法格式
    h.dispatch(a, {"t": MsgType.AVATAR_SET.value, "ext": "exe"}, PNG_BYTES)
    assert any(f.get("code") == "avatar" for f in a.errors())
    # 超限（1MB）
    h.dispatch(a, {"t": MsgType.AVATAR_SET.value, "ext": "png"},
               b"\x00" * (CFG.avatar_max_bytes + 1))
    assert any(f.get("code") == "avatar" for f in a.errors())
    # 空 body
    h.dispatch(a, {"t": MsgType.AVATAR_SET.value, "ext": "png"}, b"")
    assert any(f.get("code") == "avatar" for f in a.errors())
    # 文件未落盘
    assert not os.listdir(_avatar_dir(h))


def test_avatar_set_success_and_roster(hub):
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    b = _Sess(h, "乙")
    h.dispatch(a, {"t": MsgType.AVATAR_SET.value, "ext": "png"}, PNG_BYTES)
    # 落盘 + known 记录
    assert Path(h.avatar_dir, f"{a.uid}.png").read_bytes() == PNG_BYTES
    assert h._avatar_known(a.uid) == "png"
    # 回帧 AVATAR_DATA 带 body
    f = a.last_frame("avatar_data")
    assert f and f["uid"] == a.uid and f["ext"] == "png"
    assert f["_body"] == PNG_BYTES
    # roster 广播（含 avatar / sign 字段）→ 全员同步
    for sess in (a, b):
        r = sess.roster()
        assert r and "online" in r
        me = next(x for x in r["online"] if x["uid"] == a.uid)
        assert me["avatar"] == "png"
        assert "sign" in me


def test_avatar_del(hub):
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    h.dispatch(a, {"t": MsgType.AVATAR_SET.value, "ext": "jpg"}, PNG_BYTES)
    assert Path(h.avatar_dir, f"{a.uid}.jpg").exists()
    h.dispatch(a, {"t": MsgType.AVATAR_DEL.value})
    assert not Path(h.avatar_dir, f"{a.uid}.jpg").exists()
    assert h._avatar_known(a.uid) == ""
    f = a.last_frame("avatar_data")
    assert f and f["uid"] == a.uid and f["ext"] == ""
    # roster 广播 avatar 清空
    me = next(x for x in a.roster()["online"] if x["uid"] == a.uid)
    assert me["avatar"] == ""


def test_avatar_set_replaces_old_ext(hub):
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    h.dispatch(a, {"t": MsgType.AVATAR_SET.value, "ext": "png"}, PNG_BYTES)
    h.dispatch(a, {"t": MsgType.AVATAR_SET.value, "ext": "webp"}, PNG_BYTES)
    assert Path(h.avatar_dir, f"{a.uid}.webp").exists()
    assert not Path(h.avatar_dir, f"{a.uid}.png").exists()   # 旧 ext 文件被清理
    assert h._avatar_known(a.uid) == "webp"


def test_avatar_get(hub):
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    b = _Sess(h, "乙")
    # 无头像 → ext=""
    h.dispatch(b, {"t": MsgType.AVATAR_GET.value, "uid": a.uid})
    f = b.last_frame("avatar_data")
    assert f and f["uid"] == a.uid and f["ext"] == ""
    # 有头像 → 单播字节
    h.dispatch(a, {"t": MsgType.AVATAR_SET.value, "ext": "png"}, PNG_BYTES)
    h.dispatch(b, {"t": MsgType.AVATAR_GET.value, "uid": a.uid})
    f = b.last_frame("avatar_data")
    assert f and f["ext"] == "png" and f["_body"] == PNG_BYTES


def test_avatar_get_bad_uid(hub):
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    h.dispatch(a, {"t": MsgType.AVATAR_GET.value, "uid": "abc"})
    assert any(f.get("code") == "avatar" for f in a.errors())


# ================= 个性签名 =================

def test_sign_set_broadcast_and_truncate(hub):
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    b = _Sess(h, "乙")
    long_sign = "很长的签名" * 20                       # 远超 60 字符
    h.dispatch(a, {"t": MsgType.SIGN_SET.value, "sign": long_sign})
    sign = h.known[a.uid]["sign"]
    assert len(sign) <= CFG.sign_max_len
    for sess in (a, b):
        me = next(x for x in sess.roster()["online"] if x["uid"] == a.uid)
        assert me["sign"] == sign


def test_sign_set_trim_and_empty(hub):
    h, _wport, _ = hub
    a = _Sess(h, "甲")
    h.dispatch(a, {"t": MsgType.SIGN_SET.value, "sign": "  你好  "})
    assert h.known[a.uid]["sign"] == "你好"             # 去首尾空白
    h.dispatch(a, {"t": MsgType.SIGN_SET.value, "sign": ""})
    assert h.known[a.uid]["sign"] == ""                 # 清空


# ================= 持久化 =================

def test_avatar_sign_persist_restore(tmp_path):
    store_dir = str(tmp_path / "store")
    StoreCoordinator.initialize_new(store_dir)
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"))
    h1 = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"), store_dir=store_dir)
    a = _Sess(h1, "甲")
    h1.dispatch(a, {"t": MsgType.AVATAR_SET.value, "ext": "png"}, PNG_BYTES)
    h1.dispatch(a, {"t": MsgType.SIGN_SET.value, "sign": "重启仍在"})
    h1._persist(force=True)

    assert h1.shutdown(normal=False)
    h2 = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"), store_dir=store_dir)
    assert h2._avatar_known(a.uid) == "png"
    assert Path(h2.avatar_dir, f"{a.uid}.png").read_bytes() == PNG_BYTES
    assert h2.known[a.uid]["sign"] == "重启仍在"
    assert h2.shutdown(normal=False)


# ================= 网页端 =================

def test_web_avatar_and_profile(hub):
    h, wport, _ = hub
    u1 = _Web(wport, "红宝")
    u2 = _Web(wport, "蓝宝")
    # 未登录 GET → 401（鉴权拦截）
    st, _ = u2.avatar_get(u1.uid, token="bad-token")
    assert st == 401
    # 无头像 GET → 404
    st, data = u2.avatar_get(u1.uid)
    assert st == 404
    # 上传 → 200；GET 直出字节 + Content-Type
    st, d = u1.avatar_set("png", PNG_BYTES)
    assert st == 200 and d["ok"], d
    st, body = u2.avatar_get(u1.uid)
    assert st == 200 and body == PNG_BYTES
    # 上传非法格式 → 400
    st, d = u1.avatar_set("exe", PNG_BYTES)
    assert st == 400
    # 删除 → 200；再 GET → 404
    st, d = u1.avatar_del()
    assert st == 200 and d["ok"]
    st, _ = u2.avatar_get(u1.uid)
    assert st == 404
    # 签名：保存 → 200；登录响应 roster 带 sign
    st, d = u1.profile("网页端签名")
    assert st == 200 and d["ok"], d
    u3 = _Web(wport, "绿宝")
    me = next(x for x in u3.last_login["roster"] if x["uid"] == u1.uid)
    assert me["sign"] == "网页端签名"
    assert me["avatar"] == ""                          # 删除后无头像
