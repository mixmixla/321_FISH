# -*- coding: utf-8 -*-
"""R47 回归：昵称占用与账号系统。

A1 僵尸会话活性释放——浏览器刷新/崩溃后 web 会话 5 分钟才被清扫，
  期间同名重登被拒（锁名窗口）；_release_zombie 登录时活性复查，
  死亡即释放；min_idle 锁内复查防「检查后复活」误踢。
A2 web 会话恢复——/api/whoami 页面加载探活，Cookie 命中返回登录同款
  数据包，刷新免重登。
B 昵称可选密码——PBKDF2 存储；web/tcp 登录校验；首次带密码即绑定
  （claim 先到先得）；SET_PWD 帧与 /api/passwd 设置/修改/清除；
  站点口令与昵称密码字段语义隔离（防误绑）。
"""
import http.client
import json
import socket
import threading
import time
from dataclasses import replace

import pytest

import server as server_mod
from config import CFG
from server import Hub, serve as serve_tcp
from web import COOKIE_NAME, serve as serve_web


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_hub(tmp_path, **kw):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"))
    return Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"), **kw)


@pytest.fixture()
def env(tmp_path):
    """A1 用：zombie_web_idle 缩到 0.05s，老化会话只须回拨 1s 即判僵尸。"""
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"),
                  zombie_web_idle=0.05)
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


@pytest.fixture()
def web_env(tmp_path):
    """A2/B 用：默认阈值 + 真实 HTTP 服务。"""
    h = _make_hub(tmp_path)
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


def _age(h, uid, seconds=1.0):
    """把会话 last_seen 回拨，模拟断线僵尸。"""
    with h.lock:
        sess = h.sessions.get(uid)
    if sess:
        sess.last_seen = server_mod._now() - seconds


def _drop(h, nick):
    """注销当前同名会话（模拟该用户离开，释放昵称）。"""
    with h.lock:
        uid = h.nick_to_uid.get(nick)
        sess = h.sessions.get(uid) if uid is not None else None
    if sess:
        h.unregister(sess, "test")


def _wait_pwd(h, uid, timeout=3.0):
    """welcome 先于 claim 发出，轮询等待昵称密码落定。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with h.lock:
            if (h.known.get(uid) or {}).get("pwd"):
                return True
        time.sleep(0.02)
    return False


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

    def hello(self, pwd: str = ""):
        hdr = {"t": "hello", "nick": self.nick}
        if pwd:
            hdr["pwd"] = pwd
        self.send(hdr)
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
        data = json.loads(r.read().decode() or "{}")
        conn.close()
        return r.status, data

    def login(self, nick, password=None, nick_pwd=None):
        body = {"nick": nick}
        if password is not None:
            body["password"] = password
        if nick_pwd is not None:
            body["nick_pwd"] = nick_pwd
        status, data = self._post("/api/login", body)
        assert status == 200 and data.get("ok"), (status, data)
        return data


# ============ A1：僵尸会话活性释放 ============

def test_web_zombie_released_on_same_nick_login(env):
    """web 僵尸（老化超阈值）同名重登：先释放再放行，uid 复用。"""
    h, _tcp, _web = env
    s1, _tok = h.login_web("甲", "127.0.0.1")
    old_uid = s1.uid
    _age(h, old_uid)                       # 回拨 1s > 0.05s 阈值 → 僵尸
    s2, _tok2 = h.login_web("甲", "127.0.0.1")
    assert s2 is not None and s2.uid == old_uid   # uid 复用（R12fix）


def test_web_fresh_session_not_released(env):
    """web 活会话（刚 touch）：同名重登不再被拒（多端并存），且活会话不被误释放。

    陈旧契约修正：`_attach` 在「同 uid 多端并存」改造后恒返回 True，
    `login_web` 的「昵称已被占用」分支已不可达 → 断言改为验「uid 复用且旧端仍在」。"""
    h, _tcp, _web = env
    s1, _tok = h.login_web("乙", "127.0.0.1")
    s1.touch()                             # 显式刷新，绝不越 0.05s 阈值
    s2, _tok2 = h.login_web("乙", "127.0.0.1")
    assert s2 is not None and s2.uid == s1.uid          # uid 复用（跨重连稳定）
    assert s1 in h._uid_clients[s1.uid]                # 活会话仍在线（未被踢）


def test_web_revived_session_not_released(env):
    """min_idle 复活保护：老化后又被新流量 touch → 不被当僵尸释放，uid 复用。"""
    h, _tcp, _web = env
    s1, _tok = h.login_web("丙", "127.0.0.1")
    _age(h, s1.uid)
    s1.touch()                             # 检查后复活
    s2, _tok2 = h.login_web("丙", "127.0.0.1")
    assert s2 is not None and s2.uid == s1.uid
    assert s1 in h._uid_clients[s1.uid]                # 复活会话未被 release_zombie 释放


def test_tcp_zombie_released_on_same_nick_hello(web_env):
    """tcp 僵尸（心跳超时）同名重连：_attach 兜底释放后放行。"""
    h, tcp_port, _web = web_env
    a = _Cli(tcp_port, "丁")
    try:
        assert a.hello()
        tcp_uid = a.uid
        a.close()
        _age(h, tcp_uid, seconds=h._hb_timeout + 1.0)
        b = _Cli(tcp_port, "丁")
        try:
            assert b.hello() and b.uid == tcp_uid
        finally:
            b.close()
    finally:
        a.close()


# ============ A2：web 会话恢复 ============

def test_whoami_with_cookie_returns_session(web_env):
    """/api/whoami Cookie 命中：返回登录同款数据包（刷新免重登）。"""
    _h, _tcp, web_port = web_env
    w = _Web(web_port)
    d = w.login("甲")
    status, d2 = w._get("/api/whoami")
    assert status == 200 and d2["ok"], d2
    assert d2["uid"] == d["uid"] and d2["nick"] == "甲"
    assert d2["token"] == d["token"]
    for key in ("roster", "groups", "history", "stickers"):
        assert key in d2, key


def test_whoami_without_cookie_401(web_env):
    """无 Cookie / 无效 token → 401 未登录。"""
    _h, _tcp, web_port = web_env
    w = _Web(web_port)
    status, d = w._get("/api/whoami")
    assert status == 401 and not d["ok"]
    w.login("乙")
    w.cookie = f"{COOKIE_NAME}=deadbeef"   # 伪造失效 token
    status, d = w._get("/api/whoami")
    assert status == 401 and not d["ok"]


# ============ B：昵称可选密码 ============

def test_web_login_binds_password_claim(web_env):
    """未设密码昵称首次带密码登录 → 绑定（claim 先到先得）。"""
    h, _tcp, web_port = web_env
    w = _Web(web_port)
    d = w.login("甲", password="abc123")
    with h.lock:
        stored = h.known[d["uid"]].get("pwd")
    assert stored, "首次带密码登录应绑定昵称密码"


def test_web_login_protected_nick_requires_pwd(web_env):
    """已设密码昵称：不带密码登录 → 拒绝并提示。"""
    h, _tcp, web_port = web_env
    s, _tok = h.login_web("甲", "127.0.0.1")
    h._pwd_claim(s.uid, "abc123")
    w = _Web(web_port)
    status, d = w._post("/api/login", {"nick": "甲"})
    assert status == 403 and "密码" in d.get("error", "")


def test_web_login_wrong_pwd_rejected(web_env):
    """已设密码昵称：错误密码 → 拒绝「密码错误」。"""
    h, _tcp, web_port = web_env
    s, _tok = h.login_web("甲", "127.0.0.1")
    h._pwd_claim(s.uid, "abc123")
    w = _Web(web_port)
    status, d = w._post("/api/login", {"nick": "甲", "password": "wrong"})
    assert status == 403 and d.get("error") == "密码错误"


def test_web_login_correct_pwd_ok(web_env):
    """已设密码昵称：正确密码 → 登录成功。"""
    h, _tcp, web_port = web_env
    s, _tok = h.login_web("甲", "127.0.0.1")
    h._pwd_claim(s.uid, "abc123")
    _drop(h, "甲")                         # 原会话离开，释放昵称
    w = _Web(web_port)
    d = w.login("甲", password="abc123")
    assert d["nick"] == "甲"


def test_api_passwd_set_change_clear(web_env):
    """/api/passwd：设置 → 旧密码错误拒改 → 正确改密 → 清除。"""
    h, _tcp, web_port = web_env
    w = _Web(web_port)
    d = w.login("甲")
    status, d = w._post("/api/passwd", {"old": "", "new": "p1"})
    assert status == 200 and d["ok"], d
    # 旧密码错误 → 403
    status, d = w._post("/api/passwd", {"old": "bad", "new": "p2"})
    assert status == 403 and "旧密码" in d.get("error", "")
    # 正确改密
    status, d = w._post("/api/passwd", {"old": "p1", "new": "p2"})
    assert status == 200 and d["ok"]
    # 原会话离开 → 新密码登录生效
    _drop(h, "甲")
    w2 = _Web(web_port)
    w2.login("甲", password="p2")
    # 清除（new 空）
    status, d = w2._post("/api/passwd", {"old": "p2", "new": ""})
    assert status == 200 and d["ok"]
    _drop(h, "甲")
    w3 = _Web(web_port)
    w3.login("甲")                         # 清除后免密登录
    assert w3.cookie


def test_api_passwd_clear_without_pwd_403(web_env):
    """未设密码时清除 → 403「尚未设置密码」。"""
    _h, _tcp, web_port = web_env
    w = _Web(web_port)
    w.login("甲")
    status, d = w._post("/api/passwd", {"old": "", "new": ""})
    assert status == 403 and "尚未设置密码" in d.get("error", "")


def test_tcp_hello_requires_pwd_for_protected_nick(web_env):
    """已设密码昵称：TCP hello 不带密码 → error(pwd)；带密码 → welcome。
    hello 校验失败即断连，密码重试用新连接。"""
    h, tcp_port, _web = web_env
    s, _tok = h.login_web("甲", "127.0.0.1")
    h._pwd_claim(s.uid, "abc123")
    _drop(h, "甲")                         # 释放占名 web 会话
    a = _Cli(tcp_port, "甲")
    try:
        a.send({"t": "hello", "nick": "甲"})
        err = a.wait("error", timeout=3.0)
        assert err and err.get("code") == "pwd", err
    finally:
        a.close()
    b = _Cli(tcp_port, "甲")
    try:
        assert b.hello(pwd="abc123") is not None
    finally:
        b.close()


def test_tcp_hello_claims_pwd_first_time(web_env):
    """TCP 首登带密码 → 绑定；此后不带密码的同名 hello 被拒。"""
    h, tcp_port, _web = web_env
    a = _Cli(tcp_port, "甲")
    try:
        assert a.hello(pwd="abc123")
        assert _wait_pwd(h, a.uid), "hello 带密码应绑定昵称密码"
    finally:
        a.close()
    b = _Cli(tcp_port, "甲")
    try:
        b.send({"t": "hello", "nick": "甲"})
        err = b.wait("error", timeout=3.0)
        assert err and err.get("code") == "pwd"
    finally:
        b.close()


def test_tcp_set_pwd_flow(web_env):
    """SET_PWD 帧：设置 → 旧密码错拒（pwd_set）→ 改密 → 清除。"""
    _h, tcp_port, _web = web_env
    a = _Cli(tcp_port, "甲")
    try:
        assert a.hello()
        a.send({"t": "set_pwd", "old": "", "new": "p1"})
        sys = a.wait("system", timeout=3.0,
                     pred=lambda x: "已设置" in x.get("text", ""))
        assert sys is not None
        # 旧密码错误 → pwd_set（区别于登录 pwd，避免误弹登录框）
        a.send({"t": "set_pwd", "old": "bad", "new": "p2"})
        err = a.wait("error", timeout=3.0)
        assert err and err.get("code") == "pwd_set", err
        # 正确改密
        a.send({"t": "set_pwd", "old": "p1", "new": "p2"})
        sys = a.wait("system", timeout=3.0,
                     pred=lambda x: "已修改" in x.get("text", ""))
        assert sys is not None
        # 清除
        a.send({"t": "set_pwd", "old": "p2", "new": ""})
        sys = a.wait("system", timeout=3.0,
                     pred=lambda x: "已清除" in x.get("text", ""))
        assert sys is not None
    finally:
        a.close()


def test_web_password_mode_no_nick_claim(web_env):
    """站点口令模式：password 只作站点口令，不误绑成昵称密码；
    昵称密码经独立 nick_pwd 字段绑定。"""
    h, _tcp, web_port = web_env
    h._web_password = "site"               # 模拟 MOYU_WEB_PASSWORD
    w = _Web(web_port)
    d = w.login("甲", password="site")     # 仅站点口令
    with h.lock:
        assert not h.known[d["uid"]].get("pwd"), "站点口令不得误绑为昵称密码"
    # 站点口令错误 → 403
    w2 = _Web(web_port)
    status, d2 = w2._post("/api/login", {"nick": "乙", "password": "bad"})
    assert status == 403
    # 站点口令 + nick_pwd → 昵称密码绑定
    w3 = _Web(web_port)
    d3 = w3.login("丙", password="site", nick_pwd="np1")
    with h.lock:
        assert h.known[d3["uid"]].get("pwd"), "nick_pwd 应绑定昵称密码"
