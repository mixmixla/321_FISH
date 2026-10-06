# -*- coding: utf-8 -*-
"""CC-01A 管理员部署凭据、登录会话和权限回归。

这里的管理员口令全部由测试 fixture 注入；测试本身不依赖源码中的默认 secret。
覆盖配置缺省 fail closed、TCP/Web 共用校验、真实加密 TCP、Cookie 会话以及
同 uid 多端的 token 生命周期。
"""
import http.client
import json
import secrets
import socket
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

import auth
from config import CFG, Cfg
from server_recovery import StoreCoordinator
from protocol import MsgType
from server import Hub, Session, serve as serve_tcp
from web import COOKIE_NAME, serve as serve_web


ADMIN_NICK = "L57"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _new_hub(base: Path, admin_password, site_password: str = "",
             *, admin_nick: str = ADMIN_NICK, store_dir: Path | None = None):
    cfg = replace(
        CFG,
        admin_nick=admin_nick,
        admin_pwd=admin_password,
        web_password=site_password,
        audit_dir=str(base / "audit"),
        web_files_dir=str(base / "web"),
    )
    return Hub(cfg=cfg, audit_dir=str(base / "audit"),
               store_dir=str(store_dir) if store_dir is not None else None)


def _start_env(base: Path, admin_password: str, site_password: str = "", *, durable=False):
    root = base / 'credential-store' if durable else None
    if root is not None:
        StoreCoordinator.initialize_new(root)
    hub = _new_hub(base, admin_password, site_password, store_dir=root)
    tcp_port = _free_port()
    stop = threading.Event()
    hub._test_serve_thread = threading.Thread(target=serve_tcp, args=(hub, tcp_port, stop, False), daemon=True)
    hub._test_serve_thread.start()
    web_port = _free_port()
    httpd = serve_web(hub, port=web_port)
    time.sleep(0.15)
    return hub, tcp_port, web_port, stop, httpd


def _stop_env(stop, httpd):
    stop.set()
    httpd.shutdown()
    httpd.hub._test_serve_thread.join(10)
    assert not httpd.hub._test_serve_thread.is_alive()
    assert httpd.hub._recovery is None or not httpd.hub._recovery.owner.held


class _Rec:
    def __init__(self):
        self.frames = []

    def send(self, payload, body=b""):
        frame = dict(payload)
        if body:
            frame["_body"] = body
        self.frames.append(frame)


def _hello(hub: Hub, nick: str, password: str = "", **extra):
    rec = _Rec()
    sess = Session(0, "", "tcp", "127.0.0.1", rec.send)
    header = {"t": MsgType.HELLO.value, "nick": nick, "pwd": password}
    header.update(extra)
    ok = hub.dispatch(sess, header)
    return sess, rec, ok


def _claim(hub, nick, password):
    cap = hub.auth_capabilities()
    return _hello(hub, nick, password, auth_v=1, claim_password=True,
                  request_id=secrets.token_hex(16), expected_server_epoch=cap['server_epoch'],
                  expected_store_scope_id=cap['store_scope_id'])


class _Http:
    """HTTP 客户端，刻意只用 Cookie 鉴权验证网页会话。"""

    def __init__(self, port: int):
        self.port = port
        self.cookie = ""

    def request(self, method: str, path: str, body: dict | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {}
        if self.cookie:
            headers["Cookie"] = self.cookie
        if body is not None:
            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
            conn.request(method, path, raw, headers)
        else:
            conn.request(method, path, headers=headers)
        response = conn.getresponse()
        raw_response = response.read()
        set_cookie = response.getheader("Set-Cookie") or ""
        conn.close()
        if set_cookie.startswith(f"{COOKIE_NAME}="):
            self.cookie = set_cookie.split(";", 1)[0]
        try:
            payload = json.loads(raw_response.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = raw_response
        return response.status, payload, set_cookie

    def login(self, nick: str, password: str = "", nick_password=None):
        body = {"nick": nick, "password": password}
        if nick_password is not None:
            body["nick_pwd"] = nick_password
        return self.request("POST", "/api/login", body)

    def get(self, path: str):
        return self.request("GET", path)

    def post(self, path: str, body: dict):
        return self.request("POST", path, body)


class _Tcp:
    """单连接真实加密 TCP 客户端，避免 ClientCore 失败登录自动重连。"""

    def __init__(self, port: int):
        from crypto import client_handshake

        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.chan = client_handshake(self.sock)

    def hello(self, nick: str, password: str = ""):
        header = {"t": MsgType.HELLO.value, "nick": nick}
        if password:
            header["pwd"] = password
        self.chan.send_frame(header)
        return self.chan.recv_frame()

    def send(self, header: dict, body: bytes = b""):
        self.chan.send_frame(header, body)

    def recv_until(self, frame_type: str, limit: int = 20):
        for _ in range(limit):
            header, body = self.chan.recv_frame()
            if header.get("t") == frame_type:
                return header, body
        raise AssertionError(f"未收到帧: {frame_type}")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


@pytest.fixture()
def admin_password() -> str:
    return secrets.token_urlsafe(24)


@pytest.fixture()
def running(tmp_path, admin_password):
    env = _start_env(tmp_path, admin_password)
    yield (*env, admin_password)
    _stop_env(env[3], env[4])


@pytest.fixture()
def running_durable(tmp_path, admin_password):
    env = _start_env(tmp_path, admin_password, durable=True)
    yield (*env, admin_password)
    _stop_env(env[3], env[4])


def test_cfg_reads_deployment_env_and_redacts_password(monkeypatch):
    secret = secrets.token_urlsafe(24)
    monkeypatch.setenv("MOYU_ADMIN_PASSWORD", secret)
    monkeypatch.setenv("MOYU_ADMIN_NICK", "OpsAdmin")
    configured = Cfg()
    assert configured.admin_pwd == secret
    assert configured.admin_nick == "OpsAdmin"
    assert secret not in repr(configured)

    monkeypatch.delenv("MOYU_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("MOYU_ADMIN_NICK", raising=False)
    assert Cfg().admin_pwd == ""
    assert Cfg().admin_nick == ADMIN_NICK


def test_invalid_admin_nick_fails_without_secret_in_exception(tmp_path,
                                                               admin_password):
    for bad_nick in ("", " \t", "x" * 25, None, object()):
        cfg = replace(CFG, admin_nick=bad_nick, admin_pwd=admin_password,
                      audit_dir=str(tmp_path / "audit"),
                      web_files_dir=str(tmp_path / "web"))
        with pytest.raises(ValueError) as excinfo:
            Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
        assert admin_password not in str(excinfo.value)


def test_configured_tcp_dispatch_rejects_wrong_empty_and_spoofed_admin(
        tmp_path, admin_password):
    hub = _new_hub(tmp_path, admin_password)

    wrong, wrong_rec, ok = _hello(hub, ADMIN_NICK, "wrong")
    assert not ok and wrong.uid == 0 and not wrong.is_admin
    assert any(f.get("code") == "pwd" for f in wrong_rec.frames)

    empty, empty_rec, ok = _hello(hub, ADMIN_NICK)
    assert not ok and empty.uid == 0 and not empty.is_admin
    assert any(f.get("code") == "pwd" for f in empty_rec.frames)

    admin, admin_rec, ok = _hello(hub, ADMIN_NICK, admin_password)
    assert ok and admin.uid > 0 and admin.is_admin
    welcome = next(f for f in admin_rec.frames if f.get("t") == "welcome")
    assert welcome["is_admin"] is True

    # is_admin/uid/token 只存在于客户端输入时不能改变服务器授予身份。
    spoof, spoof_rec, ok = _hello(
        hub, "ordinary-spoof", "", is_admin=True, uid=admin.uid,
        token=secrets.token_hex(16))
    assert ok and spoof.uid != admin.uid and not spoof.is_admin
    spoof_welcome = next(f for f in spoof_rec.frames if f.get("t") == "welcome")
    assert spoof_welcome["is_admin"] is False


@pytest.mark.parametrize("configured", ["", " ", "\t\n", None])
def test_missing_or_blank_admin_password_fails_closed(tmp_path, configured):
    hub = _new_hub(tmp_path, configured)
    assert hub._admin_pwd_hash is None
    for candidate in ("", "L57", secrets.token_urlsafe(18)):
        sess, rec, ok = _hello(hub, ADMIN_NICK, candidate)
        assert not ok and sess.uid == 0 and not sess.is_admin
        assert any(f.get("code") == "pwd" for f in rec.frames)
    web_sess, err = hub.login_web(ADMIN_NICK, "127.0.0.1", "L57")
    assert web_sess is None and err


def test_custom_admin_nick_is_normalized_and_legacy_nick_stays_reserved(
        tmp_path, admin_password):
    hub = _new_hub(tmp_path, admin_password, admin_nick="  OpsRoot  ")
    assert hub._admin_nick == "OpsRoot"
    admin, _rec, ok = _hello(hub, " OpsRoot ", admin_password)
    assert ok and admin.is_admin

    # 部署者更换标识后，公开仓库里原来的 L57 仍不能被普通账号认领。
    old, old_rec, old_ok = _hello(hub, ADMIN_NICK, "")
    assert not old_ok and old.uid == 0 and not old.is_admin
    assert any(f.get("code") == "pwd" for f in old_rec.frames)
    old_web, old_err = hub.login_web(ADMIN_NICK, "127.0.0.1", "")
    assert old_web is None and old_err


@pytest.mark.parametrize("admin_value", ["missing", "blank", "configured"])
@pytest.mark.parametrize("transport", ["tcp", "web"])
def test_real_tcp_and_http_admin_login_fail_closed_matrix(
        tmp_path, admin_password, admin_value, transport):
    configured = {
        "missing": "",
        "blank": " \t\n",
        "configured": admin_password,
    }[admin_value]
    base = tmp_path / f"{admin_value}-{transport}"
    env = _start_env(base, configured)
    _hub, tcp_port, web_port, stop, httpd = env
    # 在已配置实例上，correct 只有部署口令；未配置/空白实例连旧公开口令也拒绝。
    candidates = (admin_password, "wrong", "") if admin_value == "configured" \
        else ("L57", "wrong", "")
    try:
        for candidate in candidates:
            if transport == "tcp":
                client = _Tcp(tcp_port)
                try:
                    frame, _body = client.hello(ADMIN_NICK, candidate)
                finally:
                    client.close()
                if admin_value == "configured" and candidate == admin_password:
                    assert frame["t"] == MsgType.WELCOME.value
                    assert frame["is_admin"] is True
                else:
                    assert frame["t"] == MsgType.ERROR.value
                    assert frame["code"] == "pwd"
            else:
                client = _Http(web_port)
                status, payload, _ = client.login(ADMIN_NICK, candidate)
                if admin_value == "configured" and candidate == admin_password:
                    assert status == 200 and payload["ok"]
                    assert payload["is_admin"] is True
                else:
                    assert status == 403 and payload["ok"] is False
    finally:
        _stop_env(stop, httpd)


def test_config_without_admin_pwd_and_legacy_snapshot_hash_do_not_enable_admin(
        tmp_path, admin_password):
    legacy_cfg = replace(CFG, admin_nick=ADMIN_NICK,
                         audit_dir=str(tmp_path / "legacy-audit"),
                         web_files_dir=str(tmp_path / "legacy-web"))
    delattr(legacy_cfg, "admin_pwd")
    missing_cfg_hub = Hub(cfg=legacy_cfg,
                          audit_dir=str(tmp_path / "missing-audit"))
    sess, _rec, ok = _hello(missing_cfg_hub, ADMIN_NICK, admin_password)
    assert not ok and sess.uid == 0

    store_dir = tmp_path / "store"
    store_dir.mkdir()
    old_password = "legacy-admin-password"
    state = {
        "uid_seq": 2,
        "nick_to_uid": {ADMIN_NICK: 1},
        "known": {"1": {"nick": ADMIN_NICK,
                         "pwd": auth.make(old_password),
                         "last_online": 0}},
    }
    (store_dir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8")
    StoreCoordinator.adopt_legacy(store_dir)
    unconfigured = _new_hub(tmp_path / "restored-unconfigured", "",
                            store_dir=store_dir)
    legacy_sess, _legacy_rec, legacy_ok = _hello(
        unconfigured, ADMIN_NICK, old_password)
    assert not legacy_ok and legacy_sess.uid == 0

    assert unconfigured.shutdown(normal=False)

    restored = _new_hub(tmp_path / "restored", admin_password,
                        store_dir=store_dir)
    old_sess, _old_rec, old_ok = _hello(restored, ADMIN_NICK, old_password)
    assert not old_ok and old_sess.uid == 0
    new_sess, _new_rec, new_ok = _hello(restored, ADMIN_NICK, admin_password)
    assert new_ok and new_sess.is_admin
    assert restored.shutdown(normal=False)


def test_admin_set_pwd_is_rejected_and_permission_path_stays_live(
        tmp_path, admin_password):
    hub = _new_hub(tmp_path, admin_password)
    admin, rec, ok = _hello(hub, ADMIN_NICK, admin_password)
    assert ok and admin.is_admin
    before = len(rec.frames)
    assert hub.dispatch(admin, {"t": MsgType.SET_PWD.value,
                                "old": admin_password, "new": "other"})
    assert any(f.get("t") == MsgType.ERROR.value and
               f.get("code") == "pwd_set" for f in rec.frames[before:])
    assert hub._pwd_check_for_login(ADMIN_NICK, admin_password) is None
    assert hub._pwd_check_for_login(ADMIN_NICK, "other")

    before = len(rec.frames)
    assert hub.dispatch(admin, {"t": MsgType.ADMIN_GROUPS.value})
    assert any(f.get("t") == MsgType.ADMIN_GROUPS_ROSTER.value
               for f in rec.frames[before:])


def test_ordinary_registration_chat_and_admin_payload_spoof_do_not_escalate(
        tmp_path, admin_password, request):
    root = tmp_path / 'credential-store'
    StoreCoordinator.initialize_new(root)
    hub = _new_hub(tmp_path, admin_password, store_dir=root)
    request.addfinalizer(lambda: hub.shutdown(normal=False))
    user, user_rec, ok = _hello(hub, "ordinary-user")
    assert ok and user.uid > 0 and not user.is_admin
    assert hub.dispatch(user, {"t": MsgType.CHAT.value,
                               "channel": "public", "text": "ordinary"})
    assert any(f.get("t") == MsgType.CHAT.value and
               f.get("text") == "ordinary" for f in user_rec.frames)

    before = len(user_rec.frames)
    assert hub.dispatch(user, {"t": MsgType.ADMIN_GROUPS.value,
                               "is_admin": True, "uid": 1,
                               "token": secrets.token_hex(16)})
    assert any(f.get("t") == MsgType.ERROR.value and
               f.get("code") == "forbid" for f in user_rec.frames[before:])
    assert not user.is_admin

    claim, _claim_rec, claim_ok = _claim(hub, "claimable", "ordinary-pwd")
    assert claim_ok and not claim.is_admin
    assert hub.known[claim.uid].get("pwd")
    # 管理员昵称不能被普通密码首次认领。
    assert ADMIN_NICK not in hub.nick_to_uid or hub.nick_to_uid[ADMIN_NICK] != user.uid


def test_web_cookie_whoami_admin_api_and_ordinary_denial(running):
    hub, _tcp_port, web_port, _stop, _httpd, admin_password = running
    admin = _Http(web_port)
    status, login, _set_cookie = admin.login(ADMIN_NICK, admin_password)
    assert status == 200 and login["ok"] and login["is_admin"] is True
    status, whoami, _ = admin.get("/api/whoami")
    assert status == 200 and whoami["ok"] and whoami["is_admin"] is True
    status, payload, _ = admin.post("/api/admin", {"op": "users"})
    assert status == 200 and payload["ok"]

    ordinary = _Http(web_port)
    status, ordinary_login, _ = ordinary.login("ordinary-web")
    assert status == 200 and ordinary_login["ok"]
    assert ordinary_login["is_admin"] is False
    status, ordinary_whoami, _ = ordinary.get("/api/whoami")
    assert status == 200 and ordinary_whoami["is_admin"] is False
    status, denied, _ = ordinary.post(
        "/api/admin", {"op": "users", "is_admin": True,
                        "uid": admin_login_uid(login)})
    assert status == 403 and denied["ok"] is False
    status, sent, _ = ordinary.post(
        "/api/send", {"channel": "public", "text": "web ordinary"})
    assert status == 200 and sent["ok"]
    assert any(m.get("text") == "web ordinary"
               for m in hub.bus.history("all"))


def admin_login_uid(login: dict) -> int:
    """让伪造 uid 字段使用一个真实值，验证服务端仍以 Cookie 为准。"""
    return int(login["uid"])


def test_web_site_password_on_uses_separate_nick_credential(tmp_path,
                                                             admin_password):
    site_password = secrets.token_urlsafe(24)
    env = _start_env(tmp_path, admin_password, site_password)
    hub, _tcp_port, web_port, stop, httpd = env
    try:
        client = _Http(web_port)
        status, failed, _ = client.login(ADMIN_NICK, site_password)
        assert status == 403 and not failed["ok"]
        status, succeeded, _ = client.login(
            ADMIN_NICK, site_password, nick_password=admin_password)
        assert status == 200 and succeeded["ok"]
        assert succeeded["is_admin"] is True
        status, meta, _ = client.get("/api/meta")
        assert status == 200 and meta["site_pwd"] is True

        ordinary = _Http(web_port)
        status, logged, _ = ordinary.login("site-user", site_password)
        assert status == 200 and logged["ok"]
        assert logged["is_admin"] is False
    finally:
        _stop_env(stop, httpd)


def test_real_encrypted_tcp_auth_and_chat(running):
    _hub, tcp_port, _web_port, _stop, _httpd, admin_password = running
    admin = _Tcp(tcp_port)
    ordinary = _Tcp(tcp_port)
    wrong = _Tcp(tcp_port)
    try:
        welcome, _ = admin.hello(ADMIN_NICK, admin_password)
        assert welcome["t"] == MsgType.WELCOME.value
        assert welcome["is_admin"] is True
        admin.send({"t": MsgType.ADMIN_GROUPS.value})
        groups, _ = admin.recv_until(MsgType.ADMIN_GROUPS_ROSTER.value)
        assert groups["t"] == MsgType.ADMIN_GROUPS_ROSTER.value

        normal_welcome, _ = ordinary.hello("encrypted-user")
        assert normal_welcome["t"] == MsgType.WELCOME.value
        assert normal_welcome["is_admin"] is False
        ordinary.send({"t": MsgType.CHAT.value, "channel": "public",
                       "text": "encrypted chat"})
        chat, _ = ordinary.recv_until(MsgType.CHAT.value)
        assert chat["text"] == "encrypted chat"

        error, _ = wrong.hello(ADMIN_NICK, "wrong")
        assert error["t"] == MsgType.ERROR.value
        assert error["code"] == "pwd"
    finally:
        admin.close()
        ordinary.close()
        wrong.close()


def test_web_tcp_same_uid_keeps_original_web_token_session(tmp_path,
                                                            admin_password):
    hub = _new_hub(tmp_path, admin_password)
    admin_web, admin_token = hub.login_web(ADMIN_NICK, "127.0.0.1",
                                           admin_password)
    assert admin_web is not None and admin_web.is_admin
    admin_tcp, _admin_rec, admin_ok = _hello(
        hub, ADMIN_NICK, admin_password)
    assert admin_ok and admin_tcp.uid == admin_web.uid and admin_tcp.is_admin
    assert hub.session_by_token(admin_token) is admin_web
    assert hub.session_by_token(admin_token) is not admin_tcp

    web_session, web_token = hub.login_web("cross-device", "127.0.0.1")
    assert web_session is not None and web_token
    tcp_session, _rec, ok = _hello(hub, "cross-device")
    assert ok and tcp_session.uid == web_session.uid
    assert hub.session_by_token(web_token) is web_session
    assert hub.session_by_token(web_token) is not tcp_session

    second_web, second_token = hub.login_web("cross-device", "127.0.0.1")
    assert second_web is not None and second_token
    assert hub.session_by_token(second_token) is second_web
    hub.unregister(web_session, "logout")
    assert hub.session_by_token(web_token) is None
    assert hub.session_by_token(second_token) is second_web
    assert tcp_session.uid in hub.sessions
    assert not tcp_session.closed
    relogged, relogged_token = hub.login_web("cross-device", "127.0.0.1")
    assert relogged is not None and relogged_token != web_token
    assert hub.session_by_token(web_token) is None
    assert hub.session_by_token(relogged_token) is relogged
    assert tcp_session.uid in hub.sessions and not tcp_session.closed


def test_http_cookie_old_token_rejected_after_logout_and_relogin(
        tmp_path, admin_password):
    env = _start_env(tmp_path, admin_password)
    hub, _tcp_port, web_port, stop, httpd = env
    old_client = _Http(web_port)
    try:
        status, first_login, _ = old_client.login("cookie-user")
        assert status == 200 and first_login["ok"]
        old_token = first_login["token"]
        web_session = hub.session_by_token(old_token)
        assert web_session is not None
        tcp_session, _tcp_rec, tcp_ok = _hello(hub, "cookie-user")
        assert tcp_ok and tcp_session.uid == web_session.uid

        hub.unregister(web_session, "logout")
        status, body, _ = old_client.get("/api/whoami")
        assert status == 401 and body["ok"] is False
        assert tcp_session.uid in hub.sessions and not tcp_session.closed

        new_client = _Http(web_port)
        status, second_login, _ = new_client.login("cookie-user")
        assert status == 200 and second_login["ok"]
        assert second_login["token"] != old_token
        status, body, _ = old_client.get("/api/whoami")
        assert status == 401 and body["ok"] is False
        status, body, _ = new_client.get("/api/whoami")
        assert status == 200 and body["ok"]
    finally:
        _stop_env(stop, httpd)


def test_admin_delete_invalidates_all_web_tokens_and_reboot_tokens(
        tmp_path, admin_password):
    store_dir = tmp_path / "store"
    StoreCoordinator.initialize_new(store_dir)
    hub = _new_hub(tmp_path / "before", admin_password,
                   store_dir=store_dir)
    admin, _admin_rec, admin_ok = _hello(hub, ADMIN_NICK, admin_password)
    assert admin_ok and admin.is_admin
    victim_web, token_a = hub.login_web("delete-me", "127.0.0.1")
    victim_web_2, token_b = hub.login_web("delete-me", "127.0.0.1")
    victim_tcp, _victim_rec, victim_ok = _hello(hub, "delete-me")
    assert victim_ok and victim_web.uid == victim_tcp.uid

    hub.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value,
                         "uid": victim_web.uid})
    assert token_a not in hub.web_tokens and token_b not in hub.web_tokens
    assert hub.session_by_token(token_a) is None
    assert hub.session_by_token(token_b) is None
    assert victim_web.closed and victim_web_2.closed and victim_tcp.closed
    assert victim_web.uid not in hub.known
    assert victim_web.uid in hub.retired
    assert hub.retired[victim_web.uid]["nick"] == "delete-me"
    assert set(hub.retired[victim_web.uid]) == {"nick", "retired_at", "operation_id"}
    hub._persist(force=True)

    assert hub.shutdown(normal=False)
    restored = _new_hub(tmp_path / "after", admin_password,
                         store_dir=store_dir)
    assert restored.session_by_token(token_a) is None
    assert restored.session_by_token(token_b) is None
    assert token_a not in restored.web_tokens
    assert token_b not in restored.web_tokens
    assert restored.retired[victim_web.uid]["nick"] == "delete-me"
    assert restored.nick_to_uid["delete-me"] == victim_web.uid
    assert restored.shutdown(normal=False)


def test_secret_absent_from_errors_audit_snapshot_and_repr(running_durable, capsys):
    hub, _tcp_port, web_port, _stop, _httpd, admin_password = running_durable
    good, good_rec, good_ok = _hello(hub, ADMIN_NICK, admin_password)
    assert good_ok and good.is_admin
    bound = secrets.token_urlsafe(24)
    ordinary, ordinary_rec, ordinary_ok = _claim(hub, "secret-user", bound)
    assert ordinary_ok and not ordinary.is_admin
    failed_secret = secrets.token_urlsafe(24)
    bad, bad_rec, ok = _hello(hub, "secret-user", failed_secret)
    assert not ok and bad.uid == 0
    before = len(ordinary_rec.frames)
    assert hub.dispatch(ordinary, {"t": MsgType.SET_PWD.value,
                                   "credential_v": 1, "request_id": "redaction_failure",
                                   "old": failed_secret,
                                   "new": failed_secret})
    assert any(f.get("t") == MsgType.CREDENTIAL_RESULT.value and f.get('status') == 'failed'
               for f in ordinary_rec.frames[before:])

    web = _Http(web_port)
    status, web_error, _ = web.login(ADMIN_NICK, failed_secret)
    assert status == 403 and web_error["ok"] is False

    error_text = json.dumps(
        [good_rec.frames, bad_rec.frames, ordinary_rec.frames, web_error],
        ensure_ascii=False)
    audit_text = json.dumps(hub.audit.recent(100), ensure_ascii=False)
    snapshot_text = json.dumps(hub._snapshot_state(), ensure_ascii=False,
                               default=str)
    captured = capsys.readouterr()
    output = captured.out + captured.err
    for secret in (admin_password, bound, failed_secret):
        assert secret not in error_text
        assert secret not in audit_text
        assert secret not in snapshot_text
        assert secret not in repr(hub.cfg)
        assert secret not in output
