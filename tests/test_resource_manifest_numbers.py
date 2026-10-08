"""RESOURCE-FIX-01: malformed JSON numbers must fail closed on every reader.

Synthetic files only; HTTP binds an ephemeral loopback port directly (no
discovery, external tools, subprocesses, devices or GUI).
"""
import hashlib
import http.client
import json
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from config import CFG
from server import Hub, Session
from web import serve as serve_web


FID = "c" * 32
BODY = b"synthetic-number-boundary"


@pytest.fixture
def resource(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"), admin_pwd="", bind_host='127.0.0.1')
    hub = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    frames = []
    session = Session(0, "manifest-number-owner", "web", "127.0.0.1",
                      lambda header, body=b"": frames.append(header.copy()))
    assert hub._attach(session)
    # The HTTP authentication check still executes; token creation is synthetic.
    hub.session_by_token = lambda token: session if token == "synthetic-token" else None
    yield hub, session, frames
    assert hub.shutdown(normal=False)
    assert not any(worker.is_alive() for worker in hub._managed_threads)


def _manifest(hub, session, new, **changes):
    meta = {"fid": FID, "name": "synthetic.txt", "size": len(BODY),
            "kind": "file", "ts": 1}
    if new:
        meta.update(resource_manifest_version=1, resource_owner_uid=session.uid,
                    resource_operation_id="manifest-number-op",
                    content_length=len(BODY), content_sha256=hashlib.sha256(BODY).hexdigest())
    meta.update(changes)
    path = Path(hub.web_files)
    path.mkdir(parents=True, exist_ok=True)
    (path / FID).write_bytes(BODY)
    (path / (FID + ".json")).write_text(json.dumps(meta), encoding="utf-8")


@pytest.mark.parametrize("new", [False, True], ids=["legacy", "new"])
@pytest.mark.parametrize("timestamp", [10**1000, -(10**1000), True, None,
                                        "1", float("nan"), float("inf"), -float("inf")],
                         ids=["huge", "negative-huge", "bool", "null", "string", "nan", "inf", "negative-inf"])
def test_invalid_timestamp_is_not_a_readable_resource(resource, new, timestamp):
    hub, session, _ = resource
    _manifest(hub, session, new, ts=timestamp)
    assert hub._web_file_meta(FID) is None
    assert hub._read_web_resource(FID) == (None, None)


@pytest.mark.parametrize("new", [False, True], ids=["legacy", "new"])
@pytest.mark.parametrize("timestamp", [0, -1, 1, 1.25, 1e300])
def test_finite_legacy_and_new_timestamps_keep_existing_read_behavior(resource, new, timestamp):
    hub, session, _ = resource
    _manifest(hub, session, new, ts=timestamp)
    meta, body = hub._read_web_resource(FID)
    assert meta["ts"] == timestamp
    assert body == BODY


@pytest.mark.parametrize("version", [1.0, True, "1", None, 2])
def test_new_manifest_version_requires_the_supported_json_integer(resource, version):
    hub, session, _ = resource
    _manifest(hub, session, True, resource_manifest_version=version)
    assert hub._web_file_meta(FID) is None


@pytest.mark.parametrize("new", [False, True], ids=["legacy", "new"])
def test_huge_timestamp_chat_is_rejected_without_bus_side_effect(resource, new):
    hub, session, frames = resource
    _manifest(hub, session, new, ts=10**1000)
    before = list(hub.bus.history("all"))
    frames.clear()
    hub._on_chat(session, {"t": "chat", "channel": "public", "text": "bad-manifest",
                           "file": {"fid": FID}})
    assert list(hub.bus.history("all")) == before
    assert not any(frame.get("t") == "chat" for frame in frames)


@pytest.mark.parametrize("new", [False, True], ids=["legacy", "new"])
def test_huge_timestamp_http_get_returns_404(resource, new):
    hub, session, _ = resource
    _manifest(hub, session, new, ts=10**1000)
    httpd = serve_web(hub, port=0, https=False)
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
    try:
        conn.request("GET", "/api/file?fid=" + FID,
                     headers={"Cookie": "mt_token=synthetic-token"})
        response = conn.getresponse()
        assert response.status == 404
        assert json.loads(response.read())["ok"] is False
    finally:
        conn.close()
        assert hub.shutdown(normal=False)
        assert not any(worker.is_alive() for worker in hub._managed_threads)
