# -*- coding: utf-8 -*-
"""SESSION-01：网页明确退出、Origin 校验、Cookie 与 SSE 生命周期。"""
import copy
import http.client
import json
import socket
import ssl
import time
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, Session
from web import COOKIE_NAME, PAGE, serve as serve_web


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _Http:
    __test__ = False

    def __init__(self, port, https=False):
        self.port = port
        self.https = https
        self.cookie = ""

    def request(self, method, path, body=None, headers=None):
        if self.https:
            conn = http.client.HTTPSConnection(
                "127.0.0.1", self.port, timeout=8,
                context=ssl._create_unverified_context())
        else:
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=8)
        req_headers = dict(headers or {})
        if self.cookie and "Cookie" not in req_headers:
            req_headers["Cookie"] = self.cookie
        raw = None
        if body is not None:
            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
        conn.request(method, path, raw, req_headers)
        response = conn.getresponse()
        payload = response.read()
        status = response.status
        set_cookie = response.getheader("Set-Cookie") or ""
        conn.close()
        if set_cookie.startswith(f"{COOKIE_NAME}="):
            self.cookie = set_cookie.split(";", 1)[0]
        try:
            data = json.loads(payload.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = payload
        return status, data, set_cookie

    def login(self, nick):
        return self.request("POST", "/api/login", {"nick": nick})

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body=None, headers=None):
        return self.request("POST", path, body, headers=headers)


class _Capture:
    __test__ = False

    def __init__(self):
        self.frames = []

    def send(self, payload, body=b""):
        self.frames.append((copy.deepcopy(payload), bytes(body or b"")))


@pytest.fixture()
def env(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"), web_password="")
    hub = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    httpd = serve_web(hub, port=port, https=False)
    time.sleep(0.08)
    try:
        yield hub, port, httpd
    finally:
        httpd.shutdown()
        hub.audit.close()


@pytest.fixture()
def https_env(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"), web_password="")
    hub = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    httpd = serve_web(hub, port=port, https=True)
    time.sleep(0.08)
    try:
        yield hub, port, httpd
    finally:
        httpd.shutdown()
        hub.audit.close()


def _attach(hub, nick, stype="tcp"):
    capture = _Capture()
    sess = Session(0, nick, stype, "127.0.0.1", capture.send)
    assert hub._attach(sess)
    return sess, capture


def _clear(*captures):
    for capture in captures:
        capture.frames.clear()


def _login(client, nick):
    status, body, set_cookie = client.login(nick)
    assert status == 200 and body["ok"]
    assert set_cookie.startswith(f"{COOKIE_NAME}=")
    return body["token"]


def test_http_logout_revokes_only_current_web_session(env):
    hub, port, _httpd = env
    first = _Http(port)
    second = _Http(port)
    token_a = _login(first, "logout-user")
    token_b = _login(second, "logout-user")
    web_a = hub.session_by_token(token_a)
    web_b = hub.session_by_token(token_b)
    tcp, tcp_out = _attach(hub, "logout-user")
    other, other_out = _attach(hub, "other-user")
    assert web_a is not None and web_b is not None
    assert web_a is not web_b and web_a.uid == web_b.uid == tcp.uid
    _clear(tcp_out, other_out)

    status, body, set_cookie = first.post(
        "/api/logout", {"token": token_a, "uid": other.uid},
        headers={"Origin": f"http://127.0.0.1:{port}"})

    assert status == 200 and body["ok"] is True
    assert set_cookie.startswith(f"{COOKIE_NAME}=")
    assert "Max-Age=0" in set_cookie
    assert "Path=/" in set_cookie and "HttpOnly" in set_cookie
    assert "SameSite=Strict" in set_cookie
    assert "Secure" not in set_cookie
    assert hub.session_by_token(token_a) is None
    assert hub.session_by_token(token_b) is web_b
    assert web_a.closed and not web_b.closed
    assert tcp.uid in hub.sessions and not tcp.closed
    assert other.uid in hub.sessions and not other.closed
    assert not any(f[0].get("text") == "logout-user 已下线"
                   for f in tcp_out.frames + other_out.frames)

    status, body, _ = first.get("/api/whoami")
    assert status == 401 and body["ok"] is False
    status, body, _ = second.get("/api/whoami")
    assert status == 200 and body["ok"] is True


@pytest.mark.parametrize(
    "origin",
    ["null", "https://evil.example", "not-an-origin"],
)
def test_logout_rejects_invalid_or_cross_origin_request_without_mutation(
        env, origin):
    hub, port, _httpd = env
    client = _Http(port)
    token = _login(client, "origin-user")
    before_cookie = client.cookie

    status, body, set_cookie = client.post(
        "/api/logout", {"token": token}, headers={"Origin": origin})

    assert status == 403 and body["ok"] is False
    assert set_cookie == ""
    assert client.cookie == before_cookie
    assert hub.session_by_token(token) is not None
    status, body, _ = client.get("/api/whoami")
    assert status == 200 and body["ok"] is True


def test_logout_without_origin_accepts_body_token_and_stale_token_clears_cookie(
        env):
    hub, port, _httpd = env
    client = _Http(port)
    token = _login(client, "body-token-user")
    bare = _Http(port)

    status, body, set_cookie = bare.post("/api/logout", {"token": token})
    assert status == 200 and body["ok"] is True
    assert "Max-Age=0" in set_cookie
    assert hub.session_by_token(token) is None

    status, body, set_cookie = bare.post("/api/logout", {"token": token})
    assert status == 401 and body["ok"] is False
    assert set_cookie.startswith(f"{COOKIE_NAME}=")


def test_logout_cookie_precedes_body_token_and_invalid_cookie_cannot_fallback(env):
    hub, port, _httpd = env
    client_a = _Http(port)
    client_b = _Http(port)
    token_a = _login(client_a, "cookie-a")
    token_b = _login(client_b, "cookie-b")

    status, body, _ = client_a.post(
        "/api/logout", {"token": token_b},
        headers={"Origin": f"http://127.0.0.1:{port}"})
    assert status == 200 and body["ok"] is True
    assert hub.session_by_token(token_a) is None
    assert hub.session_by_token(token_b) is not None

    invalid_cookie = _Http(port)
    invalid_cookie.cookie = f"{COOKIE_NAME}=expired-token"
    status, body, set_cookie = invalid_cookie.post(
        "/api/logout", {"token": token_b})
    assert status == 401 and body["ok"] is False
    assert set_cookie.startswith(f"{COOKIE_NAME}=")
    assert hub.session_by_token(token_b) is not None


def test_https_logout_deletes_cookie_with_secure_attribute(https_env):
    hub, port, _httpd = https_env
    client = _Http(port, https=True)
    token = _login(client, "https-logout")

    status, body, set_cookie = client.post(
        "/api/logout", {"token": token},
        headers={"Origin": f"https://127.0.0.1:{port}"})

    assert status == 200 and body["ok"] is True
    assert hub.session_by_token(token) is None
    assert "Secure" in set_cookie
    assert "HttpOnly" in set_cookie and "SameSite=Strict" in set_cookie


@pytest.mark.parametrize("origin_kind", ["scheme", "port", "path"])
def test_logout_rejects_same_host_wrong_origin_details(env, origin_kind):
    hub, port, _httpd = env
    client = _Http(port)
    token = _login(client, "origin-detail")
    if origin_kind == "scheme":
        origin = f"https://127.0.0.1:{port}"
    elif origin_kind == "port":
        origin = f"http://127.0.0.1:{port + 1}"
    else:
        origin = f"http://127.0.0.1:{port}/wrong"

    status, body, set_cookie = client.post(
        "/api/logout", {"token": token}, headers={"Origin": origin})

    assert status == 403 and body["ok"] is False
    assert set_cookie == ""
    assert hub.session_by_token(token) is not None
    status, body, _ = client.get("/api/whoami")
    assert status == 200 and body["ok"] is True

    unauthenticated = _Http(port)
    status, body, set_cookie = unauthenticated.post("/api/logout", {})
    assert status == 401 and body["ok"] is False
    assert set_cookie.startswith(f"{COOKIE_NAME}=")


def test_get_logout_has_no_side_effect(env):
    hub, port, _httpd = env
    client = _Http(port)
    token = _login(client, "get-logout-user")

    status, _body, set_cookie = client.get("/api/logout")

    assert status == 404
    assert set_cookie == ""
    assert hub.session_by_token(token) is not None
    status, body, _ = client.get("/api/whoami")
    assert status == 200 and body["ok"] is True


def test_sse_disconnect_does_not_logout_session(env):
    hub, port, _httpd = env
    client = _Http(port)
    token = _login(client, "sse-user")
    sess = hub.session_by_token(token)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
    conn.request("GET", "/api/events",
                 headers={"Cookie": f"{COOKIE_NAME}={token}"})
    response = conn.getresponse()
    assert response.status == 200
    assert "text/event-stream" in response.getheader("Content-Type", "")
    conn.close()
    time.sleep(0.15)

    assert hub.session_by_token(token) is sess
    status, body, _ = client.get("/api/whoami")
    assert status == 200 and body["ok"] is True


def test_page_has_explicit_logout_and_stale_sse_guard():
    required = {
        'title="退出登录"': "toolbar logout entry",
        "function logout()": "logout function",
        'fetch("/api/logout"': "logout POST",
        "state.es.close()": "SSE close",
        "state.token=null": "local token clear",
        "state.esRetry": "SSE retry handle",
        "if(!state.token)return": "stale SSE guard",
        "status===401": "401 local cleanup",
        'catch(()=>showStatus("退出失败': "network failure retention",
        "state.groom=null": "game room clear",
        "state.gst=null": "game snapshot clear",
        "state.gpriv=null": "game private clear",
        "state.glog=[]": "game log clear",
        "state.grooms=[]": "game room list clear",
        'document.getElementById("gpanel")': "game panel cleanup",
        "renderGames()": "game sidebar refresh",
        "closeLobby()": "game lobby cleanup",
    }
    for fragment, label in required.items():
        if fragment not in PAGE:
            raise AssertionError(f"missing {label}")
    start = PAGE.index("function logout()")
    end = PAGE.index("function login()", start)
    logout_source = PAGE[start:end]
    if "game_leave" in logout_source or "/api/game" in logout_source:
        raise AssertionError("logout must not send game_leave")
    onmessage_start = PAGE.index("es.onmessage=e=>")
    onmessage_end = PAGE.index("es.onerror", onmessage_start)
    if "if(state.es!==es||!state.token)return;" not in PAGE[onmessage_start:onmessage_end]:
        raise AssertionError("old SSE message guard missing from onmessage")
