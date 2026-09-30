# -*- coding: utf-8 -*-
"""R26D 链接预览的离线 SSRF/大小/超时回归测试。"""
from types import SimpleNamespace
import socket

import pytest

import server


def _cfg(**overrides):
    values = {
        "preview_timeout": 1.25,
        "preview_max_bytes": 64,
        "preview_title_max": 80,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _public_info(host, port, **_kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
             ("93.184.216.34", port))]


class _FakeResponse:
    def __init__(self, body=b"<title>ok</title>", *, status=200,
                 headers=None):
        self.status = status
        self._body = body
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.read_calls = 0

    def getheader(self, name, default=None):
        return self._headers.get(name.lower(), default)

    def read(self, size=-1):
        self.read_calls += 1
        if size < 0:
            size = len(self._body)
        out, self._body = self._body[:size], self._body[size:]
        return out


class _FakeConnection:
    response = _FakeResponse()
    instances = []

    def __init__(self, host, port, address_info, *, timeout):
        self.host = host
        self.port = port
        self.address_info = address_info
        self.timeout = timeout
        self.requests = []
        self.closed = False
        type(self).instances.append(self)

    def request(self, method, target, headers):
        self.requests.append((method, target, headers))

    def getresponse(self):
        return type(self).response

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_fake():
    _FakeConnection.instances = []
    _FakeConnection.response = _FakeResponse()


def test_redirect_to_loopback_is_rejected_without_second_resolution(monkeypatch):
    """3xx 不自动跟随，因此 Location 的 loopback 永远不会建立连接。"""
    calls = []

    def resolve(host, port, **kwargs):
        calls.append((host, port))
        return _public_info(host, port, **kwargs)

    monkeypatch.setattr(server.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(server, "_PinnedHTTPConnection", _FakeConnection)
    _FakeConnection.response = _FakeResponse(
        b"", status=302, headers={"Location": "http://127.0.0.1/private"})

    assert server.fetch_preview("http://public.example/redirect", _cfg()) is None
    assert calls == [("public.example", 80)]
    assert len(_FakeConnection.instances) == 1
    assert _FakeConnection.instances[0].closed


def test_mixed_public_and_private_dns_answers_are_rejected(monkeypatch):
    """DNS 返回公网+私网混合结果时整体拒绝，避免选择性解析留下 SSRF 面。"""
    calls = []

    def mixed(host, port, **_kwargs):
        calls.append((host, port))
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
             ("93.184.216.34", port)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
             ("192.168.1.10", port)),
        ]

    monkeypatch.setattr(server.socket, "getaddrinfo", mixed)
    monkeypatch.setattr(server, "_PinnedHTTPConnection", _FakeConnection)
    assert server.fetch_preview("http://mixed.example/", _cfg()) is None
    assert calls == [("mixed.example", 80)]
    assert _FakeConnection.instances == []


def test_public_dns_is_resolved_once_and_connection_uses_fixed_address(monkeypatch):
    """连接使用已检查的地址信息，不触发第二次 DNS 解析。"""
    calls = []

    def resolve(host, port, **kwargs):
        calls.append((host, port))
        return _public_info(host, port, **kwargs)

    monkeypatch.setattr(server.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(server, "_PinnedHTTPConnection", _FakeConnection)
    _FakeConnection.response = _FakeResponse(
        "<html><head><title>公网页面</title></head></html>".encode(),
        headers={"Content-Type": "text/html; charset=utf-8"})

    meta = server.fetch_preview("http://public.example/path?q=1", _cfg())
    assert meta["title"] == "公网页面"
    assert calls == [("public.example", 80)]
    conn = _FakeConnection.instances[0]
    assert conn.address_info[-1] == "93.184.216.34"
    assert conn.timeout == 1.25
    assert conn.requests[0][1] == "/path?q=1"
    assert conn.requests[0][2]["Host"] == "public.example"


def test_preview_size_limit_is_preserved(monkeypatch):
    monkeypatch.setattr(server.socket, "getaddrinfo", _public_info)
    monkeypatch.setattr(server, "_PinnedHTTPConnection", _FakeConnection)
    _FakeConnection.response = _FakeResponse(
        b"<title>too large</title>",
        headers={"Content-Type": "text/html", "Content-Length": "65"})
    assert server.fetch_preview("http://public.example/large", _cfg()) is None
    assert _FakeConnection.response.read_calls == 0


def test_preview_timeout_is_passed_and_failure_degrades_to_none(monkeypatch):
    monkeypatch.setattr(server.socket, "getaddrinfo", _public_info)

    class TimeoutConnection(_FakeConnection):
        def getresponse(self):
            raise TimeoutError("mock timeout")

    monkeypatch.setattr(server, "_PinnedHTTPConnection", TimeoutConnection)
    assert server.fetch_preview("http://public.example/slow", _cfg(
        preview_timeout=0.2)) is None
    assert TimeoutConnection.instances[0].timeout == 0.2
    assert TimeoutConnection.instances[0].closed
