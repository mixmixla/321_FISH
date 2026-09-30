# -*- coding: utf-8 -*-
"""P0 web 安全加固回归：自签 HTTPS / Cookie 登录态（token 移出 URL）/ 登录限速。

- tls_cert.ensure_cert：首次生成、二次复用、ssl.load_cert_chain 配对加载；
- web.serve(https=True)：TLS 握手可用，/api/login 下发 Set-Cookie（HttpOnly+Secure）；
- Cookie 鉴权：GET/SSE/POST 不带 URL token 可用；?token= 兼容回退保留；HTTP 下无 Secure；
- _LoginGuard：连续失败 ≥ 阈值指数退避 429，成功重置，封顶 900s。
"""
import http.client
import json
import socket
import ssl
import threading
import time
from dataclasses import replace

import pytest

import tls_cert
from config import CFG
from server import Hub, serve as serve_tcp
from web import PAGE, COOKIE_NAME, _LoginGuard, serve as serve_web


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_hub(tmp_path, password: str = ""):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_password=password)
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    return h, port, stop


class _Web:
    """轻量 HTTP(S) 客户端：可选 TLS 上下文 / Cookie 头。"""

    def __init__(self, port, https: bool = False):
        self.port = port
        self.https = https
        self.cookie = ""

    def _conn(self):
        if self.https:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return http.client.HTTPSConnection("127.0.0.1", self.port,
                                               context=ctx, timeout=8)
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=8)

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.cookie:
            h["Cookie"] = self.cookie
        return h

    def _post(self, path, body):
        conn = self._conn()
        conn.request("POST", path, json.dumps(body).encode(), self._headers())
        r = conn.getresponse()
        data = json.loads(r.read().decode() or "{}")
        sc = r.getheader("Set-Cookie") or ""
        conn.close()
        if sc.startswith(f"{COOKIE_NAME}="):        # 模拟浏览器存 Cookie
            self.cookie = sc.split(";")[0]
        return r.status, data, sc

    def _get(self, path):
        conn = self._conn()
        headers = {"Cookie": self.cookie} if self.cookie else {}
        conn.request("GET", path, headers=headers)
        r = conn.getresponse()
        status = r.status
        body = r.read()
        conn.close()
        return status, body


# ---------------------------------------------------------------- tls_cert

def test_cert_generate_reuse_and_pair(tmp_path):
    d = str(tmp_path / "web_tls")
    cert, key = tls_cert.ensure_cert(d)
    with open(cert, "rb") as f:
        assert f.read().startswith(b"-----BEGIN CERTIFICATE-----")
    with open(key, "rb") as f:
        assert f.read().startswith(b"-----BEGIN RSA PRIVATE KEY-----")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)                      # 配对加载成功
    cert2, key2 = tls_cert.ensure_cert(d)               # 二次调用复用
    assert (cert, key) == (cert2, key2)
    try:                                                # CPython 证书解析自检
        info = ssl._test_decode_cert(cert)
        assert info.get("subject")
        sans = info.get("subjectAltName") or []
        dns_names = {v for k, v in sans if k == "DNS"}
        assert "localhost" in dns_names
    except AttributeError:                              # 私有 API 缺失时跳过
        pass


# ---------------------------------------------------------------- HTTPS

@pytest.fixture()
def https_hub(tmp_path):
    h, port, stop = _make_hub(tmp_path)
    wport = _free_port()
    httpd = serve_web(h, port=wport, https=True)
    time.sleep(0.3)
    yield h, wport, stop
    stop.set()
    httpd.shutdown()


def test_https_login_sets_secure_cookie(https_hub):
    _, wport, _ = https_hub
    web = _Web(wport, https=True)
    st, d, sc = web._post("/api/login", {"nick": "alice"})
    assert st == 200 and d["ok"], d
    assert sc.startswith(f"{COOKIE_NAME}=")
    assert "HttpOnly" in sc and "Secure" in sc and "SameSite=Strict" in sc
    # 登录态走 Cookie 后，GET 无 URL token 可用
    st, body = web._get("/api/history?channel=public")
    assert st == 200 and json.loads(body)["ok"]
    st, body = web._get("/api/convos")
    assert st == 200 and json.loads(body)["ok"]


def test_https_rejects_plain_http(https_hub):
    _, wport, _ = https_hub
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    with pytest.raises((ssl.SSLError, OSError, http.client.HTTPException)):
        conn.request("GET", "/")
        conn.getresponse()
    conn.close()


# ---------------------------------------------------------------- Cookie 鉴权

@pytest.fixture()
def http_hub(tmp_path):
    h, port, stop = _make_hub(tmp_path)
    wport = _free_port()
    httpd = serve_web(h, port=wport)                    # https=None→cfg 缺省 False
    time.sleep(0.2)
    yield h, wport, stop
    stop.set()
    httpd.shutdown()


def test_cookie_auth_and_query_fallback(http_hub):
    _, wport, _ = http_hub
    web = _Web(wport)
    st, d, sc = web._post("/api/login", {"nick": "bob"})
    assert st == 200 and d["ok"]
    assert sc.startswith(f"{COOKIE_NAME}=")
    assert "HttpOnly" in sc and "Secure" not in sc      # 明文 HTTP 下不带 Secure
    token = d["token"]

    # 1) 纯 Cookie（URL/POST 均无 token）
    web.cookie = f"{COOKIE_NAME}={token}"
    st, body = web._get("/api/history?channel=public")
    assert st == 200 and json.loads(body)["ok"]
    st, body = web._get("/api/convos")
    assert st == 200 and json.loads(body)["ok"]
    st, d2, _ = web._post("/api/send", {"channel": "public", "text": "hi"})
    assert st == 200 and d2["ok"]

    # 2) 完全不带凭证 → 401
    bare = _Web(wport)
    st, body = bare._get("/api/history?channel=public")
    assert st == 401

    # 3) 旧客户端兼容：?token= 回退仍可用
    legacy = _Web(wport)
    st, body = legacy._get(f"/api/history?channel=public&token={token}")
    assert st == 200 and json.loads(body)["ok"]
    st, body = legacy._get(f"/api/group_detail?gid=99999&token={token}")
    assert st in (200, 400, 404)                        # 鉴权已过（业务码不限）


def test_sse_cookie_auth(http_hub):
    _, wport, _ = http_hub
    web = _Web(wport)
    st, d, _ = web._post("/api/login", {"nick": "carol"})
    token = d["token"]
    # Cookie 鉴权的 SSE：响应头 event-stream 立即返回
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=8)
    conn.request("GET", "/api/events", headers={"Cookie": f"{COOKIE_NAME}={token}"})
    r = conn.getresponse()
    assert r.status == 200
    assert "text/event-stream" in r.getheader("Content-Type", "")
    conn.close()
    # 无凭证 SSE → 401
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=8)
    conn.request("GET", "/api/events")
    r = conn.getresponse()
    assert r.status == 401
    conn.close()


def test_page_has_no_token_in_url():
    # P0 验收：页面 JS 不再把 token 拼进 URL（POST body 兼容回退保留）
    assert "token=state.token" not in PAGE
    assert "/api/events?token=" not in PAGE
    assert "/api/file?token=" not in PAGE
    assert "/api/group_detail?token=" not in PAGE
    assert "{token:state.token,channel:c.type}" not in PAGE
    assert 'EventSource("/api/events")' in PAGE


def test_security_headers_on_all_responses(http_hub):
    """Web 安全头：页面 / JSON / SSE 每路响应统一附加 CSP 等头。"""
    _, wport, _ = http_hub
    web = _Web(wport)
    st, d, _ = web._post("/api/login", {"nick": "dave"})
    assert st == 200 and d["ok"]

    # 页面（HTML）
    conn = web._conn()
    conn.request("GET", "/", headers={"Cookie": web.cookie})
    r = conn.getresponse()
    assert r.status == 200
    csp = r.getheader("Content-Security-Policy") or ""
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "form-action 'self'" in csp
    assert r.getheader("X-Content-Type-Options") == "nosniff"
    assert r.getheader("X-Frame-Options") == "DENY"
    assert r.getheader("Referrer-Policy") == "no-referrer"
    assert r.read().startswith(b"<!DOCTYPE html>")
    conn.close()

    # JSON API
    conn = web._conn()
    conn.request("GET", "/api/convos", headers={"Cookie": web.cookie})
    r = conn.getresponse()
    assert r.status == 200
    assert (r.getheader("Content-Security-Policy") or "").startswith("default-src 'self'")
    assert r.getheader("X-Content-Type-Options") == "nosniff"
    conn.close()

    # SSE 长连接（头在流式开始前发出）
    conn = web._conn()
    conn.request("GET", "/api/events", headers={"Cookie": web.cookie})
    r = conn.getresponse()
    assert r.status == 200
    assert (r.getheader("Content-Security-Policy") or "").startswith("default-src 'self'")
    conn.close()

    # 未登录 JSON 401 同样带安全头
    conn = web._conn()
    conn.request("GET", "/api/history?channel=public")
    r = conn.getresponse()
    assert r.status == 401
    assert r.getheader("X-Content-Type-Options") == "nosniff"
    conn.close()


# ---------------------------------------------------------------- 登录限速

def test_login_guard_unit():
    g = _LoginGuard(max_fails=3, base=2.0, cap=900.0)
    assert g.check("1.2.3.4") == 0.0
    assert g.fail("1.2.3.4") == 0.0
    assert g.fail("1.2.3.4") == 0.0
    assert g.check("1.2.3.4") == 0.0
    assert g.fail("1.2.3.4") == pytest.approx(2.0)      # 第 3 次触发
    assert g.check("1.2.3.4") > 0
    g.success("1.2.3.4")                                # 成功重置
    assert g.check("1.2.3.4") == 0.0
    # 指数退避 + 封顶
    g2 = _LoginGuard(max_fails=1, base=2.0, cap=900.0)
    assert g2.fail("ip") == pytest.approx(2.0)
    g2.fail("ip")
    assert g2.fail("ip") == pytest.approx(8.0)
    for _ in range(30):
        g2.fail("ip")
    assert g2.fail("ip") == pytest.approx(900.0)        # 封顶
    # 多 IP 互不影响
    g3 = _LoginGuard(max_fails=1)
    g3.fail("a")
    assert g3.check("b") == 0.0


def test_login_rate_limit_integration(tmp_path):
    h, port, stop = _make_hub(tmp_path, password="pw123")
    wport = _free_port()
    httpd = serve_web(h, port=wport)
    web = _Web(wport)
    try:
        for _ in range(5):                              # 前 5 次失败仍返回 403
            st, d, _ = web._post("/api/login", {"nick": "eve", "password": "bad"})
            assert st == 403 and "口令错误" in d["error"]
        st, d, _ = web._post("/api/login",              # 第 6 次进入锁定期
                             {"nick": "eve", "password": "pw123"})
        assert st == 429 and "频繁" in d["error"]
        # 限速器按 hub 挂载：锁定期内有记录
        guard = getattr(h, "_web_login_guard", None)
        assert guard is not None and guard.check("127.0.0.1") > 0
    finally:
        stop.set()
        httpd.shutdown()
