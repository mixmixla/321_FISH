"""动态图片 HTTP 入口必须登录，且只能读取现存动态引用的图片。"""
from email.message import Message
import io
from types import SimpleNamespace

import pytest

from web import COOKIE_NAME, _Handler


def _handler(tmp_path, logged_in, active):
    image = tmp_path / "1_0.jpg"
    image.write_bytes(b"private image bytes")
    session = SimpleNamespace(touch=lambda: None)
    hub = SimpleNamespace(
        moment_dir=str(tmp_path),
        session_by_token=lambda token: session if token == "valid" else None,
        _moment_image_active=lambda fn: active and fn == image.name,
    )
    handler = _Handler.__new__(_Handler)
    handler.hub = hub
    handler.path = "/api/moment_img/1_0.jpg"
    handler.headers = Message()
    if logged_in:
        handler.headers["Cookie"] = f"{COOKIE_NAME}=valid"
    handler.wfile = io.BytesIO()
    handler.sent_headers = {}
    handler.send_response = lambda status: setattr(handler, "status", status)
    handler.send_header = lambda name, value: handler.sent_headers.update({name: value})
    handler.end_headers = lambda: None
    handler._json = lambda status, data: setattr(handler, "status", status)
    return handler


@pytest.mark.parametrize(("logged_in", "active", "expected"), [
    (False, True, 401),
    (True, False, 404),
    (True, True, 200),
])
def test_moment_image_auth_and_live_reference(tmp_path, logged_in, active, expected):
    handler = _handler(tmp_path, logged_in, active)
    handler._moment_img("1_0.jpg")
    assert handler.status == expected
    if expected == 200:
        assert handler.wfile.getvalue() == b"private image bytes"
        assert handler.sent_headers["Cache-Control"] == "private, no-store"
    else:
        assert handler.wfile.getvalue() == b""


def test_authenticated_path_traversal_still_rejected(tmp_path):
    handler = _handler(tmp_path, True, True)
    handler._moment_img("../1_0.jpg")
    assert handler.status == 400
    assert handler.wfile.getvalue() == b""
