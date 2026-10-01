# -*- coding: utf-8 -*-
"""R53 回归：服务器管理员账号（昵称 L57，最高清理权限）。

- 管理员部署凭据：错误密码拒绝，不可被占用或经账号接口修改；
- 撤回任何人消息（任何频道）；清空全部聊天记录；清空指定用户全部消息；踢人下线；
- 权限校验：非管理员一律拒绝（forbid）；
- 广播 CLEARED 使桌面/网页客户端同步清空本地历史（core._apply_cleared）；
- 网页端 /api/admin（kick/clear_all/clear_uid）+ 登录响应 is_admin 字段。
"""
import json
import secrets
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
def admin_password() -> str:
    """为每个管理员回归实例注入一次不可预测的部署口令。"""
    return secrets.token_urlsafe(24)


@pytest.fixture()
def hub(tmp_path, admin_password):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"),
                  admin_nick="L57", admin_pwd=admin_password)
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    # 测试实例显式保存部署口令，避免全局 conftest 隐式开启管理员。
    h._test_admin_password = admin_password
    h._test_admin_nick = cfg.admin_nick
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
    """伪造 TCP 会话：走真实 hello 登录（校验管理员密码并置 is_admin）。"""
    __test__ = False

    def __init__(self, hub: Hub, nick: str, pwd: str = ""):
        self.hub = hub
        self.frames = []
        self.uid = 0
        self.nick = nick
        self.type = "tcp"
        self.peer_ip = "127.0.0.1"
        self.closed = False
        self.last_seen = time.time()
        self.is_admin = False
        self.close_conn = lambda: None
        self.send = lambda payload: self.frames.append(payload)
        hub._on_hello(self, {"t": MsgType.HELLO.value, "nick": nick,
                             "pwd": pwd})

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
    """轻量 web 客户端：登录拿 token（管理员显式注入部署口令）。"""
    __test__ = False

    def __init__(self, port, nick, pwd=""):
        self.port = port
        self.token = None
        self.uid = None
        self.last_login = None
        self.login(nick, pwd)

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

    def login(self, nick, pwd=""):
        st, d = self._req("POST", "/api/login",
                          {"nick": nick, "password": pwd})
        if st != 200 or not d.get("ok"):
            self.last_login = d
            return
        self.token = d["token"]
        self.uid = d["uid"]
        self.last_login = d

    def admin(self, body):
        body = dict(body)
        body["token"] = self.token
        return self._req("POST", "/api/admin", body)

    def send(self, channel="public", to=None, text="hi"):
        body = {"token": self.token, "channel": channel, "text": text}
        if to is not None:
            body["to"] = to
        return self._req("POST", "/api/send", body)


def _admin_session(h: Hub):
    return _Sess(h, h._test_admin_nick, pwd=h._test_admin_password)


def _admin_web(h: Hub, port: int):
    return _Web(port, h._test_admin_nick, pwd=h._test_admin_password)


# ================= 管理员账号登录/占用/改密 =================

def test_admin_login_wrong_pwd_rejected(hub):
    """管理员昵称的空/错密码一律拒绝，无法冒用。"""
    h, _w, _ = hub
    a = _Sess(h, h._test_admin_nick, pwd="")            # 空密码 → 拒
    assert any(f.get("code") == "pwd" for f in a.errors())
    assert a.uid == 0 and not a.is_admin

    b = _Sess(h, h._test_admin_nick, pwd="wrong")       # 错密码 → 拒
    assert any(f.get("code") == "pwd" for f in b.errors())

    c = _admin_session(h)                   # 正确密码 → 登录成功
    assert c.is_admin and c.uid > 0
    welcome = c.last_frame("welcome")
    assert welcome and welcome.get("is_admin") is True


def test_admin_deploy_password_not_modifiable_by_account_api(hub):
    """管理员部署凭据不能经普通账号 set_password 修改/清除。"""
    h, _w, _ = hub
    a = _admin_session(h)
    err = h.set_password(a.uid, h._test_admin_nick, "newpwd")
    assert err
    err2 = h.set_password(a.uid, h._test_admin_nick, "")
    assert err2
    # 密码仍可正常校验（未被改坏）
    assert h._pwd_check_for_login(h._test_admin_nick,
                                 h._test_admin_password) is None


def test_normal_user_not_admin(hub):
    h, _w, _ = hub
    a = _Sess(h, "普通用户")
    assert not a.is_admin
    welcome = a.last_frame("welcome")
    assert welcome and welcome.get("is_admin") is False


# ================= 管理员撤回任何人消息 =================

def test_admin_del_any_message_any_channel(hub):
    """管理员可撤回公共频道/私聊中任何人的消息（普通用户不行）。"""
    h, _w, _ = hub
    a = _Sess(h, "甲")
    b = _Sess(h, "乙")
    adm = _admin_session(h)
    # 公共频道：甲发消息，管理员撤回
    h.dispatch(a, {"t": MsgType.CHAT.value, "channel": "public", "text": "公聊内容"})
    seq_pub = h.bus.history("all")[-1]["seq"]
    h.dispatch(adm, {"t": MsgType.MSG_DEL.value, "seq": seq_pub, "scope": "self"})
    _k, msg = h.bus.find(seq_pub)
    assert msg["deleted"]
    # 私聊：乙发消息给甲，管理员撤回
    h.dispatch(b, {"t": MsgType.CHAT.value, "channel": "private",
                   "to": a.uid, "text": "私聊内容"})
    key = f"private:{min(a.uid, b.uid)}:{max(a.uid, b.uid)}"
    seq_priv = h.bus.history(key)[-1]["seq"]
    h.dispatch(adm, {"t": MsgType.MSG_DEL.value, "seq": seq_priv, "scope": "self"})
    _k2, msg2 = h.bus.find(seq_priv)
    assert msg2["deleted"]
    # 普通用户乙撤回甲的公聊消息 → 仍被拒
    h.dispatch(a, {"t": MsgType.CHAT.value, "channel": "public", "text": "再一条"})
    seq3 = h.bus.history("all")[-1]["seq"]
    h.dispatch(b, {"t": MsgType.MSG_DEL.value, "seq": seq3, "scope": "both"})
    assert any(f.get("code") == "forbid" for f in b.errors())
    _k3, msg3 = h.bus.find(seq3)
    assert not msg3.get("deleted")


# ================= 管理员清空全部/指定用户 =================

def _public_seq(h) -> int:
    return h.bus.history("all")[-1]["seq"]


def test_admin_clear_all_only_admin(hub):
    """非管理员 CLEAR_ALL 被拒；管理员执行后总线清空并广播 CLEARED all。"""
    h, _w, _ = hub
    a = _Sess(h, "甲")
    b = _Sess(h, "乙")
    adm = _admin_session(h)
    h.dispatch(a, {"t": MsgType.CHAT.value, "channel": "public", "text": "t1"})
    h.dispatch(b, {"t": MsgType.CHAT.value, "channel": "public", "text": "t2"})
    assert len(h.bus.history("all")) >= 2
    # 非管理员 → 拒绝
    h.dispatch(a, {"t": MsgType.CLEAR_ALL.value})
    assert any(f.get("code") == "forbid" for f in a.errors())
    assert len(h.bus.history("all")) >= 2
    # 管理员 → 清空 + 全员收到 CLEARED all + 系统广播
    n = h.dispatch(adm, {"t": MsgType.CLEAR_ALL.value})
    assert n is True
    assert h.bus.history("all") == []
    assert a.last_frame("cleared") == {"t": "cleared", "all": True}
    assert b.last_frame("cleared") == {"t": "cleared", "all": True}
    assert adm.last_frame("cleared") == {"t": "cleared", "all": True}
    assert any(f.get("t") == "system" and "清空全部" in f.get("text", "")
               for f in a.frames)


def test_admin_clear_uid_only_target(hub):
    """管理员清空指定用户：跨频道只删该用户消息，他人消息保留。"""
    h, _w, _ = hub
    a = _Sess(h, "甲")
    b = _Sess(h, "乙")
    adm = _admin_session(h)
    h.dispatch(a, {"t": MsgType.CHAT.value, "channel": "public", "text": "甲-公"})
    h.dispatch(b, {"t": MsgType.CHAT.value, "channel": "public", "text": "乙-公"})
    h.dispatch(a, {"t": MsgType.CHAT.value, "channel": "private",
                   "to": b.uid, "text": "甲-私"})
    before_a = [m for m in h.bus.history("all") if m.get("uid") == a.uid]
    assert before_a
    n = h.dispatch(adm, {"t": MsgType.CLEAR_UID.value, "uid": a.uid})
    assert n is True
    rest = h.bus.history("all")
    assert not [m for m in rest if m.get("uid") == a.uid]     # 甲的消息全清
    assert [m for m in rest if m.get("uid") == b.uid]          # 乙的消息保留
    # 全员收到 CLEARED uid
    assert b.last_frame("cleared") == {"t": "cleared", "uid": a.uid}
    # 非管理员 → 拒绝
    h.dispatch(b, {"t": MsgType.CLEAR_UID.value, "uid": adm.uid})
    assert any(f.get("code") == "forbid" for f in b.errors())


# ================= 管理员踢人下线 =================

def test_admin_kick_user(hub):
    h, _w, _ = hub
    a = _Sess(h, "甲")
    b = _Sess(h, "乙")
    adm = _admin_session(h)
    assert b.uid in h.sessions
    h.dispatch(adm, {"t": MsgType.ADMIN_KICK.value, "uid": b.uid})
    assert b.uid not in h.sessions              # 已注销
    assert b.closed
    # 目标端收到 error/kicked 提示帧
    kicked = [f for f in b.frames
              if f.get("t") == "error" and f.get("code") == "kicked"]
    assert kicked


def test_admin_kick_offline_and_non_admin(hub):
    h, _w, _ = hub
    a = _Sess(h, "甲")
    adm = _admin_session(h)
    # 踢离线用户 → offline
    h.dispatch(adm, {"t": MsgType.ADMIN_KICK.value, "uid": 999999})
    assert any(f.get("code") == "offline" for f in adm.errors())
    # 踢自己 → 拒绝
    h.dispatch(adm, {"t": MsgType.ADMIN_KICK.value, "uid": adm.uid})
    assert any(f.get("code") == "uid" for f in adm.errors())
    # 非管理员 → 拒绝
    h.dispatch(a, {"t": MsgType.ADMIN_KICK.value, "uid": adm.uid})
    assert any(f.get("code") == "forbid" for f in a.errors())


# ================= 客户端本地历史同步清空（core） =================

def _mk_core(tmp_path, nick="测试员"):
    from client_core import ClientCore
    c = ClientCore(host="127.0.0.1", port=1, nick=nick,
                   history_dir=str(tmp_path / f"hist_{nick}"))
    return c


def test_core_cleared_all_clears_local_history(tmp_path):
    c = _mk_core(tmp_path, "甲")
    for i in range(3):
        c._history.add("public", {"t": "chat", "seq": i + 1, "uid": 1,
                                  "nick": "甲", "text": f"m{i}", "ts": 1.0})
    assert len(c._history.load("public")) == 3
    c._apply_cleared({"t": "cleared", "all": True})
    assert c._history.load("public") == []
    assert c._history.load_disk("public") == []   # 磁盘同步清空
    c.stop() if c.state != "idle" else None


def test_core_cleared_uid_removes_only_target(tmp_path):
    c = _mk_core(tmp_path, "乙")
    c._history.add("public", {"t": "chat", "seq": 1, "uid": 10,
                              "nick": "A", "text": "a1", "ts": 1.0})
    c._history.add("public", {"t": "chat", "seq": 2, "uid": 20,
                              "nick": "B", "text": "b1", "ts": 2.0})
    c._history.add(f"private:{10}:{20}", {"t": "chat", "seq": 3, "uid": 10,
                                          "nick": "A", "text": "a2", "ts": 3.0})
    c._apply_cleared({"t": "cleared", "uid": 10})
    pub = c._history.load("public")
    assert [m["uid"] for m in pub] == [20]        # A 的消息被清，B 保留
    assert c._history.load(f"private:{10}:{20}") == []  # 私聊频道 A 消息也清
    c.stop() if c.state != "idle" else None


# ================= 网页端 =================

def test_web_admin_login_flag(hub):
    h, wport, _ = hub
    adm = _admin_web(h, wport)
    assert adm.last_login.get("is_admin") is True
    u = _Web(wport, "普通")
    assert u.last_login.get("is_admin") is False


def test_web_admin_api(hub):
    h, wport, _ = hub
    adm = _admin_web(h, wport)
    u = _Web(wport, "普通")
    # 非管理员 → 403
    st, d = u.admin({"op": "clear_all"})
    assert st == 403 and not d.get("ok")
    # 管理员先造消息再清空
    adm.send("public", None, "被清空的公聊")
    assert h.bus.history("all")
    st, d = adm.admin({"op": "clear_all"})
    assert st == 200 and d.get("ok")
    assert h.bus.history("all") == []
    # 清空指定用户 + 踢人
    st, d = adm.admin({"op": "clear_uid", "uid": u.uid})
    assert st == 200 and d.get("ok")
    assert u.uid in h.sessions
    st, d = adm.admin({"op": "kick", "uid": u.uid})
    assert st == 200 and d.get("ok")
    assert u.uid not in h.sessions
