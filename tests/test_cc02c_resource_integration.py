# -*- coding: utf-8 -*-
"""CC-02C RESOURCE：隔离 TCP/HTTP/文件/JSON 重启边界。

固定合成输入：``b"integration-resource-123"``、``WEB_OP_1``、
``integration.txt``。所有服务绑定随机 localhost 端口，所有目录来自
pytest ``tmp_path``；不接触真实 web_files/cloud/audit/prefs 数据。
"""
import base64
import copy
import http.client
import json
import os
import socket
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from config import CFG
from server import Hub, Session


DATA = b"integration-resource-123"
OP = "WEB_OP_1"  # invalid/unknown-input sentinel only; first writes omit op


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _cfg(tmp_path, *, store=False, admin_pwd=""):
    return replace(CFG, audit_dir=str(tmp_path / "audit"),
                   web_files_dir=str(tmp_path / "web"),
                   admin_pwd=admin_pwd, persist_interval=0.0)


def _start_loopback_tcp(hub):
    import server

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    listener.settimeout(0.2)
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            try:
                conn, addr = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=server._handle_tcp,
                             args=(hub, conn, addr), daemon=True).start()

    threading.Thread(target=loop, daemon=True).start()
    return listener, stop


@pytest.fixture()
def env(tmp_path):
    import web

    cfg = _cfg(tmp_path)
    hub = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    listener, tcp_stop = _start_loopback_tcp(hub)
    tcp_port = listener.getsockname()[1]
    web_port = _free_port()
    httpd = web.serve(hub, web_port, threading.Event(), False)
    time.sleep(0.15)
    yield hub, tcp_port, web_port, httpd, tcp_stop, tmp_path
    tcp_stop.set()
    try:
        listener.close()
    except OSError:
        pass
    try:
        httpd.shutdown()
    except Exception:
        pass
    time.sleep(0.15)


class _Web:
    __test__ = False

    def __init__(self, port):
        self.port = port
        self.cookie = ""

    def _request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=8)
        headers = {}
        raw = None
        if body is not None:
            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.cookie:
            headers["Cookie"] = self.cookie
        conn.request(method, path, raw, headers)
        response = conn.getresponse()
        payload = response.read()
        status = response.status
        ctype = response.getheader("Content-Type") or ""
        cookie = response.getheader("Set-Cookie") or ""
        conn.close()
        if cookie.startswith("mt_token="):
            self.cookie = cookie.split(";", 1)[0]
        return status, payload, ctype

    def post(self, path, body):
        status, raw, _ctype = self._request("POST", path, body)
        try:
            return status, json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, ValueError):
            return status, raw

    def get(self, path):
        status, raw, ctype = self._request("GET", path)
        return status, raw, ctype

    def login(self, nick):
        status, payload = self.post("/api/login", {"nick": nick})
        assert status == 200 and payload.get("ok"), payload
        return payload


def _attach(hub, nick, stype="tcp"):
    frames = []

    def send(payload, body=b""):
        frames.append((copy.deepcopy(payload), bytes(body or b"")))

    sess = Session(0, nick, stype, "127.0.0.1", send)
    assert hub._attach(sess)
    frames.clear()
    return sess, frames


def _recv_until(chan, target, *, limit=32):
    """Consume bounded bootstrap/event frames until the requested frame type."""
    for _ in range(limit):
        header, body = chan.recv_frame()
        if header.get("t") == "error" and target != "error":
            raise AssertionError(f"TCP resource request error: {header!r}")
        if header.get("t") == target:
            return header, body
    raise AssertionError(f"TCP frame {target!r} not received in {limit} frames")


def test_web_upload_query_download_and_chat_use_same_verified_bytes(env):
    hub, _tcp_port, web_port, _httpd, _stop, _tmp = env
    web = _Web(web_port)
    login = web.login("integration-web")
    upload_status, upload = web.post("/api/upload", {
        "name": "integration.txt", "kind": "file",
        "data": base64.b64encode(DATA).decode("ascii"),
    })
    assert upload_status == 200 and upload.get("ok"), upload
    file_meta = upload["file"]
    assert file_meta["size"] == len(DATA)
    assert file_meta.get("fid")
    op = (upload.get("resource") or {}).get("resource_operation_id")
    assert op
    status, raw, ctype = web.get("/api/file?fid=" + file_meta["fid"])
    assert status == 200 and raw == DATA
    assert "octet-stream" in ctype
    qs, result, _ = web.get("/api/resource_result?resource_operation_id=" + op)
    assert qs == 200
    result = json.loads(result.decode("utf-8"))
    assert result["resource"]["status"] == "confirmed"
    assert result["resource"]["visibility"] == "available"
    # CHAT canonicalization must use the same in-memory verified qualification.
    owner = hub.sessions[login["uid"]]
    hub._on_chat(owner, {"t": "chat", "channel": "public", "text": "attach",
                         "file": file_meta})
    assert any(m.get("text") == "attach" and
               m.get("file", {}).get("fid") == file_meta["fid"]
               for m in hub.bus.history("all"))


def test_encrypted_tcp_cloud_put_query_and_get_use_resource_result(env):
    _hub, tcp_port, _web_port, _httpd, _stop, _tmp = env
    from crypto import client_handshake

    sock = socket.create_connection(("127.0.0.1", tcp_port), timeout=5)
    try:
        chan = client_handshake(sock)
        chan.send_frame({"t": "hello", "nick": "integration-tcp"})
        welcome, _ = _recv_until(chan, "welcome")
        assert welcome.get("t") == "welcome"
        chan.send_frame({"t": "cloud_put", "size": len(DATA)}, DATA)
        done, body = _recv_until(chan, "cloud_done")
        assert not body and done.get("t") == "cloud_done"
        resource = done.get("resource") or {}
        assert resource.get("status") == "confirmed"
        op = resource.get("resource_operation_id")
        assert op
        chan.send_frame({"t": "cloud_get",
                         "resource_operation_id": op})
        summary, summary_body = _recv_until(chan, "cloud_done")
        assert not summary_body and summary.get("t") == "cloud_done"
        assert (summary.get("resource") or {}).get("visibility") == "available"
        chan.send_frame({"t": "cloud_get"})
        data_header, data_body = _recv_until(chan, "cloud_data")
        assert data_header.get("t") == "cloud_data"
        assert data_body == DATA
    finally:
        sock.close()


def test_wellformed_unknown_operation_is_handler_error_with_zero_resource_io(env):
    hub, tcp_port, web_port, _httpd, _stop, _tmp = env
    web = _Web(web_port)
    web.login("unknown-op-web")
    before_ops = set(hub._resource_ops)
    before_meta = set(Path(hub.web_files).glob("*.json"))
    status, payload = web.post("/api/upload", {
        "name": "unknown.txt", "kind": "file",
        "resource_operation_id": "unknown-op-r4",
        "data": base64.b64encode(DATA).decode("ascii"),
    })
    assert status == 400 and not payload.get("ok")
    assert set(hub._resource_ops) == before_ops
    assert set(Path(hub.web_files).glob("*.json")) == before_meta

    from crypto import client_handshake

    sock = socket.create_connection(("127.0.0.1", tcp_port), timeout=5)
    try:
        chan = client_handshake(sock)
        chan.send_frame({"t": "hello", "nick": "unknown-op-tcp"})
        welcome, _ = _recv_until(chan, "welcome")
        chan.send_frame({"t": "cloud_put", "size": len(DATA),
                         "resource_operation_id": "unknown-op-r4"}, DATA)
        error, body = _recv_until(chan, "error")
        assert not body and error.get("code") == "unknown_operation"
        assert welcome.get("uid") not in hub.cloud
    finally:
        sock.close()


def test_web_upload_invalid_operation_identity_has_no_valid_fid(env):
    hub, _tcp_port, web_port, _httpd, _stop, _tmp = env
    web = _Web(web_port)
    web.login("integration-invalid")
    status, payload = web.post("/api/upload", {
        "name": "integration.txt", "kind": "file",
        "resource_operation_id": "bad op with spaces",
        "data": base64.b64encode(DATA).decode("ascii"),
    })
    assert status == 400
    assert not payload.get("ok")
    assert not any(p.name.endswith(".json") for p in Path(hub.web_files).iterdir())


def test_web_auth_and_fid_validation_fail_closed(env):
    _hub, _tcp_port, web_port, _httpd, _stop, _tmp = env
    anonymous = _Web(web_port)
    status, _raw, _ctype = anonymous.get("/api/file?fid=" + "a" * 32)
    assert status == 401
    anonymous.login("integration-invalid-fid")
    status, _raw, _ctype = anonymous.get("/api/file?fid=../state.json")
    assert status == 404
    status, _raw, _ctype = anonymous.get(
        "/api/resource_result?resource_operation_id=wellformed-missing")
    assert status == 404


def test_web_unknown_manifest_is_not_legacy_downloadable(env):
    hub, _tcp_port, web_port, _httpd, _stop, _tmp = env
    web = _Web(web_port)
    web.login("integration-manifest")
    status, payload = web.post("/api/upload", {
        "name": "integration.txt", "kind": "file",
        "data": base64.b64encode(DATA).decode("ascii"),
    })
    assert status == 200 and payload.get("ok"), payload
    fid = payload["file"]["fid"]
    meta_path = Path(hub.web_files) / (fid + ".json")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["resource_manifest_version"] = 99
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    status, _raw, _ctype = web.get("/api/file?fid=" + fid)
    assert status == 404


def test_resource_result_is_owner_scoped_and_does_not_leak_paths(env):
    hub, _tcp_port, web_port, _httpd, _stop, _tmp = env
    owner_web = _Web(web_port)
    owner = owner_web.login("integration-owner")
    status, payload = owner_web.post("/api/upload", {
        "name": "integration.txt", "kind": "file",
        "data": base64.b64encode(DATA).decode("ascii"),
    })
    assert status == 200 and payload.get("ok")
    op = (payload.get("resource") or {}).get("resource_operation_id")
    assert op
    other_web = _Web(web_port)
    other_web.login("integration-other")
    shared_status, shared_raw, _ = other_web.get(
        "/api/file?fid=" + payload["file"]["fid"])
    assert shared_status == 200 and shared_raw == DATA
    status, raw, _ctype = other_web.get(
        "/api/resource_result?resource_operation_id=" + op)
    assert status in (401, 403, 404)
    if raw:
        text = raw.decode("utf-8", errors="ignore")
        assert str(Path(hub.web_files)) not in text
        assert "resource_owner_uid" not in text or str(owner["uid"]) not in text


def test_runtime_result_eviction_does_not_delete_shared_file(env):
    hub, _tcp_port, web_port, _httpd, _stop, _tmp = env
    web = _Web(web_port)
    web.login("integration-evict")
    first = None
    for index in range(66):
        status, payload = web.post("/api/upload", {
            "name": f"evict-{index}.txt", "kind": "file",
            "data": base64.b64encode(DATA + str(index).encode()).decode("ascii"),
        })
        assert status == 200 and payload.get("ok"), payload
        if first is None:
            first = payload
    first_op = first["resource"]["resource_operation_id"]
    # Natural terminal cap eviction removes old runtime receipts while complete
    # manifests remain independently readable through the shared fid path.
    query_status, _raw, _ctype = web.get(
        "/api/resource_result?resource_operation_id=" + first_op)
    assert query_status == 404
    file_status, file_raw, _ctype = web.get(
        "/api/file?fid=" + first["file"]["fid"])
    assert file_status == 200 and file_raw == DATA + b"0"


def test_restart_restores_manifest_access_but_not_runtime_operation_receipt(env,
                                                                            tmp_path):
    hub, _tcp_port, web_port, _httpd, _stop, _tmp = env
    web = _Web(web_port)
    web.login("integration-restart")
    status, payload = web.post("/api/upload", {
        "name": "integration.txt", "kind": "file",
        "data": base64.b64encode(DATA).decode("ascii"),
    })
    assert status == 200 and payload.get("ok")
    fid = payload["file"]["fid"]
    cfg = _cfg(tmp_path)
    restored = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    assert restored._resource_query is not None
    op = (payload.get("resource") or {}).get("resource_operation_id")
    assert op
    # Runtime op ledger is intentionally not reconstructed; complete manifest
    # remains a shared file fact and is still readable through a new session.
    new_sess, _frames = _attach(restored, "integration-restart")
    assert restored._web_file_path(fid)
    with open(restored._web_file_path(fid), "rb") as stream:
        assert stream.read() == DATA
    with pytest.raises((LookupError, KeyError, PermissionError, ValueError)):
        restored._resource_query(new_sess, op)


def test_restart_unknown_cloud_and_incomplete_manifest_keep_limited_facts(
        tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    h1 = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    owner, out = _attach(h1, "restart-unknown-cloud")
    real_replace = os.replace

    def replace_then_raise(src, dst):
        real_replace(src, dst)
        raise OSError("replace ack lost")

    monkeypatch.setattr(os, "replace", replace_then_raise)
    h1._on_cloud_put(owner, {"t": "cloud_put"}, DATA)
    op = next(reversed(h1._resource_ops))
    assert op
    body_fid = "c" * 32
    Path(h1.web_files, body_fid).write_bytes(DATA)
    Path(h1.web_files, body_fid + ".json").write_text(
        json.dumps({"fid": body_fid, "name": "incomplete.txt",
                    "size": len(DATA), "kind": "file", "ts": 1,
                    "resource_manifest_version": 1}), encoding="utf-8")
    monkeypatch.undo()
    h2 = Hub(cfg=_cfg(tmp_path), audit_dir=str(tmp_path / "audit"))
    assert h2.cloud[owner.uid]["blob"] == DATA
    restored, _restored_out = _attach(h2, "restart-unknown-cloud")
    with pytest.raises(LookupError):
        h2._resource_query(restored, op)
    assert h2._web_file_meta(body_fid) is None


def test_retired_cloud_is_filtered_after_valid_state_restore(tmp_path):
    from server_store import ServerStore

    store_dir = tmp_path / "store"
    cfg = _cfg(tmp_path, store=True)
    h1 = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"),
             store_dir=str(store_dir))
    owner, _frames = _attach(h1, "integration-retired")
    h1._on_cloud_put(owner, {"t": "cloud_put"}, DATA)
    with h1.lock:
        h1.nick_to_uid[owner.nick] = owner.uid
        h1.known.pop(owner.uid, None)
        h1.retired[owner.uid] = {"nick": owner.nick, "retired_at": time.time(),
                                 "operation_id": "retire-integration"}
    h1._persist_flush()
    assert ServerStore(str(store_dir / "state.json")).load()["retired"]
    cfg2 = replace(_cfg(tmp_path, store=True),
                   audit_dir=str(tmp_path / "restart" / "audit"))
    h2 = Hub(cfg=cfg2,
             audit_dir=str(tmp_path / "restart" / "audit"),
             store_dir=str(store_dir))
    assert owner.uid not in h2.cloud
    assert (Path(h2.cloud_dir) / f"{owner.uid}.bin").is_file()


def test_admin_resource_summary_is_bounded_and_has_no_file_body_or_path(tmp_path):
    h = Hub(cfg=_cfg(tmp_path), audit_dir=str(tmp_path / "audit"))
    owner, _frames = _attach(h, "integration-admin-target")
    h._on_cloud_put(owner, {"t": "cloud_put"}, DATA)
    payload = h._admin_user_payload(owner.uid)
    assert payload is not None
    resources = payload.get("resources") or {}
    encoded = json.dumps(resources, ensure_ascii=False)
    assert "blob" not in encoded and "path" not in encoded
    assert str(Path(h.web_files)) not in encoded
    assert resources.get("operations")
