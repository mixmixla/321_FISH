# -*- coding: utf-8 -*-
"""CC-02C RESOURCE：文件资源/attempt/manifest/查询的稳定回归。

这些用例只使用隔离 tmp_path 和合成 bytes。固定输入声明：
``RESOURCE_A = b"resource-A-0123456789"``、
``RESOURCE_B = b"resource-B-9876543210"``、``OP_*`` 和 32 位十六进制 fid。
不读取项目运行目录，也不依赖新资源类型的顶层 import；实现缺失时应表现为
普通测试失败，而不是 collection error。
"""
import builtins
import copy
import hashlib
import json
import os
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from config import CFG
from server import Hub, Session


RESOURCE_A = b"resource-A-0123456789"
RESOURCE_B = b"resource-B-9876543210"
OP_A = "resource-op-a-0001"
OP_B = "resource-op-b-0001"
FID_A = "a" * 32
FID_B = "b" * 32


class _Capture:
    __test__ = False

    def __init__(self):
        self.frames = []

    def send(self, payload, body=b""):
        self.frames.append((copy.deepcopy(payload), bytes(body or b"")))


def _cfg(tmp_path, *, store=False):
    return replace(
        CFG,
        audit_dir=str(tmp_path / "audit"),
        web_files_dir=str(tmp_path / "web"),
        admin_pwd="",
        persist_interval=0.0,
    )


def _hub(tmp_path, *, store=False):
    h = Hub(
        cfg=_cfg(tmp_path, store=store),
        audit_dir=str(tmp_path / "audit"),
        store_dir=str(tmp_path / "store") if store else None,
    )
    return h


def _attach(hub, nick, stype="tcp"):
    out = _Capture()
    sess = Session(0, nick, stype, "127.0.0.1", out.send)
    assert hub._attach(sess)
    out.frames.clear()
    return sess, out


def _plain(value):
    """Normalize a ResourceResult dataclass/dict for assertions."""
    if isinstance(value, dict):
        return value
    return {
        key: getattr(value, key, None)
        for key in (
            "resource_operation_id", "resource_owner_uid", "kind",
            "resource_key", "status", "io_effect", "visibility", "stage",
            "error_code", "length", "sha256", "origin", "retryable",
        )
    }


def _begin(hub, sess, *, kind, key, op, payload, **metadata):
    identity = {
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "content_length": len(payload),
        **metadata,
    }
    return hub._resource_begin(
        sess,
        kind,
        key,
        identity,
        resource_operation_id=op,
    )


def _context(value):
    if isinstance(value, dict) and "context" in value:
        return value["context"]
    return value


def _ctx_field(value, key):
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _result(hub, sess, op, **kwargs):
    return _plain(hub._resource_query(sess, op, **kwargs))


def _cloud_done(out):
    return [p for p, _body in out.frames if p.get("t") == "cloud_done"]


def _resource_commit_catching(hub, ctx, payload):
    try:
        hub._resource_file_commit(ctx, payload)
    except Exception as exc:
        return getattr(exc, "code", type(exc).__name__)
    return "ok"


def _issued_op(out):
    for payload, _body in reversed(out.frames):
        if payload.get("t") == "cloud_done":
            resource = payload.get("resource") or {}
            if resource.get("resource_operation_id"):
                return resource["resource_operation_id"]
        resource = payload.get("resource")
        if isinstance(resource, dict) and resource.get("resource_operation_id"):
            return resource["resource_operation_id"]
    raise AssertionError("server did not issue resource_operation_id")


def test_resource_begin_binds_payload_metadata_before_stage(tmp_path):
    h = _hub(tmp_path)
    owner, _out = _attach(h, "resource-owner")
    begin = _begin(h, owner, kind="cloud", key=owner.uid, op=None,
                   payload=RESOURCE_A, name="cloud.bin", kind_name="opaque")
    ctx = _context(begin)
    assert ctx is not None
    issued = _ctx_field(ctx, "resource_operation_id")
    assert isinstance(issued, str) and issued
    identity = _ctx_field(ctx, "payload_identity")
    assert identity["payload_sha256"] == hashlib.sha256(RESOURCE_A).hexdigest()
    # A duplicate pending begin is the same executor/attempt and cannot allocate
    # a second permit or fid.
    again = _begin(h, owner, kind="cloud", key=owner.uid, op=issued,
                   payload=RESOURCE_A, name="cloud.bin", kind_name="opaque")
    assert _context(again) is ctx or _context(again) == ctx


def test_cloud_success_reports_committed_written_and_queryable(tmp_path):
    h = _hub(tmp_path)
    owner, out = _attach(h, "cloud-owner")
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    done = _cloud_done(out)
    assert done and done[-1].get("size") == len(RESOURCE_A)
    op = _issued_op(out)
    result = _result(h, owner, op)
    assert result["status"] == "confirmed"
    assert result["io_effect"] == "committed"
    assert result["origin"] == "written"
    assert result["visibility"] == "available"
    assert result["length"] == len(RESOURCE_A)
    assert result["sha256"] == hashlib.sha256(RESOURCE_A).hexdigest()
    assert h.cloud[owner.uid]["blob"] == RESOURCE_A


def test_cloud_response_failure_does_not_downgrade_confirmed_result(tmp_path):
    h = _hub(tmp_path)
    owner, out = _attach(h, "cloud-response-lost")
    original_send = owner.send

    def fail_after_write(payload, body=b""):
        if payload.get("t") == "cloud_done":
            raise OSError("response lost")
        return original_send(payload, body)

    owner.send = fail_after_write
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    op = next(reversed(h._resource_ops))
    result = _result(h, owner, op)
    assert result["status"] == "confirmed"
    assert result["origin"] == "written"
    assert h.cloud[owner.uid]["blob"] == RESOURCE_A


def test_noop_response_loss_has_no_latest_or_payload_auto_recovery(tmp_path):
    h = _hub(tmp_path)
    owner, out = _attach(h, "cloud-noop-loss")
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    generated = next(reversed(h._resource_ops))
    out.frames.clear()
    with pytest.raises(LookupError):
        h._resource_query(owner, "unknown-after-response-loss")
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_B)
    assert h.cloud[owner.uid]["blob"] == RESOURCE_B
    assert generated in h._resource_ops


def test_cloud_replace_failure_is_failed_without_cloud_done(tmp_path, monkeypatch):
    h = _hub(tmp_path)
    owner, out = _attach(h, "cloud-fail")

    def fail_replace(_src, _dst):
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    assert not _cloud_done(out)
    op = _issued_op(out)
    result = _result(h, owner, op)
    assert result["status"] == "failed"
    assert result["io_effect"] == "not_committed"
    assert result["visibility"] in ("pending", "unavailable")
    assert owner.uid not in h.cloud


def test_cloud_replace_then_ack_failure_is_unknown_and_query_reconciles(tmp_path,
                                                                         monkeypatch):
    h = _hub(tmp_path)
    owner, out = _attach(h, "cloud-unknown")
    real_replace = os.replace

    def replace_then_raise(src, dst):
        real_replace(src, dst)
        raise OSError("ack lost after replace")

    monkeypatch.setattr(os, "replace", replace_then_raise)
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    assert not _cloud_done(out)
    op = _issued_op(out)
    pending = next(p.get("resource") or {}
                   for p, _body in out.frames if p.get("t") == "error")
    assert pending["status"] == "unknown"
    assert pending["io_effect"] == "uncertain"
    # The first explicit query performs strict read-back reconciliation.
    reconciled = _result(h, owner, op)
    assert reconciled["status"] == "confirmed"
    assert reconciled["io_effect"] == "uncertain"
    assert reconciled["origin"] == "reconciled_current_resource"
    assert reconciled["visibility"] == "available"
    assert not _cloud_done(out)


def test_latest_permit_blocks_old_failed_retry_but_keeps_old_readable(tmp_path):
    h = _hub(tmp_path)
    owner, out = _attach(h, "cloud-order")
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    op_a = _issued_op(out)
    out.frames.clear()

    # The second operation is allowed to become the latest permit, but its
    # failed/unknown result must not make the confirmed A index disappear.
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_B)
    assert _cloud_done(out)
    op_b = _issued_op(out)
    assert op_b != op_a
    current = h.cloud[owner.uid]["blob"]
    assert current == RESOURCE_B
    out.frames.clear()
    h._on_cloud_put(owner, {"t": "cloud_put",
                             "resource_operation_id": op_a}, RESOURCE_A)
    assert not _cloud_done(out)
    stale = _result(h, owner, op_a)
    assert stale["status"] in ("confirmed", "failed", "unknown")
    assert stale["visibility"] == "superseded"
    assert h.cloud[owner.uid]["blob"] == RESOURCE_B


def test_confirmed_old_op_stays_available_while_new_op_fails(tmp_path, monkeypatch):
    h = _hub(tmp_path)
    owner, out = _attach(h, "cloud-current")
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    op_a = _issued_op(out)
    out.frames.clear()

    monkeypatch.setattr(os, "replace",
                        lambda _src, _dst: (_ for _ in ()).throw(
                            OSError("pre-replace failure")))
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_B)
    assert not _cloud_done(out)
    assert h.cloud[owner.uid]["blob"] == RESOURCE_A
    out.frames.clear()
    h._on_cloud_put(owner, {"t": "cloud_put",
                             "resource_operation_id": op_a}, RESOURCE_A)
    # Confirmed A is query-only and remains the current readable version while
    # B is failed; the retry must not be treated as superseded merely because
    # B became latest_permit.
    assert _cloud_done(out)
    result = _result(h, owner, op_a)
    assert result["status"] == "confirmed"
    assert result["visibility"] == "available"


def test_pre_replace_failure_with_identical_old_bytes_is_failed(tmp_path,
                                                                monkeypatch):
    h = _hub(tmp_path)
    owner, out = _attach(h, "cloud-same-bytes")
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    out.frames.clear()
    monkeypatch.setattr(os, "replace",
                        lambda _src, _dst: (_ for _ in ()).throw(
                            OSError("known pre-replace failure")))
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    op = _issued_op(out)
    result = _result(h, owner, op)
    assert result["status"] == "failed"
    assert result["io_effect"] == "not_committed"
    assert result["error_code"]
    assert h.cloud[owner.uid]["blob"] == RESOURCE_A


def test_cloud_same_bytes_after_actual_replace_ack_is_unknown_then_reconciled(
        tmp_path, monkeypatch):
    h = _hub(tmp_path)
    owner, out = _attach(h, "cloud-same-unknown")
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    out.frames.clear()
    real_replace = os.replace

    def replace_then_raise(src, dst):
        real_replace(src, dst)
        raise OSError("replace ack lost")

    monkeypatch.setattr(os, "replace", replace_then_raise)
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    op = _issued_op(out)
    unknown = next(p["resource"] for p, _body in out.frames
                   if p.get("t") == "error" and p.get("resource"))
    assert unknown["status"] == "unknown"
    reconciled = _result(h, owner, op)
    assert reconciled["status"] == "confirmed"
    assert reconciled["io_effect"] == "uncertain"
    assert reconciled["origin"] == "reconciled_current_resource"


def test_failed_retry_checks_quota_before_new_attempt(tmp_path, monkeypatch):
    h = _hub(tmp_path)
    owner, out = _attach(h, "cloud-retry-quota")
    monkeypatch.setattr(os, "replace",
                        lambda _src, _dst: (_ for _ in ()).throw(
                            OSError("first attempt failed")))
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    op = _issued_op(out)
    ctx = h._resource_ops[op]
    assert ctx["status"] == "failed"
    h._resource_max_active = 0
    out.frames.clear()
    h._on_cloud_put(owner, {"t": "cloud_put",
                             "resource_operation_id": op}, RESOURCE_A)
    assert ctx["status"] == "failed"
    assert not _cloud_done(out)


def test_failed_op_after_t0_cannot_retry_or_replace(tmp_path, monkeypatch):
    h = _hub(tmp_path)
    owner, out = _attach(h, "retry-after-t0")
    monkeypatch.setattr(os, "replace",
                        lambda _src, _dst: (_ for _ in ()).throw(
                            OSError("first failure")))
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    op = _issued_op(out)
    ctx = h._resource_ops[op]
    attempt = ctx["attempt"]
    with h.lock:
        h.retired[owner.uid] = {"nick": owner.nick, "retired_at": time.time(),
                                "operation_id": "retire-before-retry"}
    out.frames.clear()
    h._on_cloud_put(owner, {"t": "cloud_put",
                             "resource_operation_id": op}, RESOURCE_A)
    assert ctx["attempt"] == attempt
    assert ctx["status"] == "failed"
    assert not _cloud_done(out)


def test_quota_is_per_owner_and_different_uid_can_progress(tmp_path):
    h = _hub(tmp_path)
    first, _first_out = _attach(h, "quota-first")
    second, second_out = _attach(h, "quota-second")
    h._resource_max_active = 1
    pending = _context(_begin(h, first, kind="cloud", key=first.uid, op=None,
                              payload=RESOURCE_A))
    h._on_cloud_put(second, {"t": "cloud_put"}, RESOURCE_B)
    assert _cloud_done(second_out)
    assert h.cloud[second.uid]["blob"] == RESOURCE_B
    assert pending["status"] == "pending"


def test_resource_stage_pause_allows_store_force_progress(tmp_path, monkeypatch):
    h = _hub(tmp_path, store=True)
    owner, _out = _attach(h, "store-progress")
    entered = threading.Event()
    release = threading.Event()
    original_stage = h._resource_stage_bytes

    def blocked_stage(data, suffix):
        entered.set()
        assert release.wait(3.0)
        return original_stage(data, suffix)

    monkeypatch.setattr(h, "_resource_stage_bytes", blocked_stage)
    thread = threading.Thread(target=lambda: h._on_cloud_put(
        owner, {"t": "cloud_put"}, RESOURCE_A), daemon=True)
    thread.start()
    assert entered.wait(3.0)
    h.nick_to_uid["store-progress-live"] = 998
    h._persist_flush()
    assert Path(tmp_path, "store", "state.json").is_file()
    release.set()
    thread.join(3.0)
    assert not thread.is_alive()


def test_resource_bytes_do_not_replace_first_store_failure_old_json(tmp_path,
                                                                   monkeypatch):
    h = _hub(tmp_path, store=True)
    owner, _out = _attach(h, "store-old-json")
    h._persist_flush()
    state_path = Path(tmp_path, "store", "state.json")
    old_state = state_path.read_bytes()
    monkeypatch.setattr(h.store, "_save_encoded",
                        lambda _encoded: (_ for _ in ()).throw(
                            OSError("synthetic first store failure")))
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    h._persist(force=True)
    assert state_path.read_bytes() == old_state
    restored = _hub(tmp_path, store=True)
    assert restored.cloud[owner.uid]["blob"] == RESOURCE_A
    restored_owner, _restored_out = _attach(restored, "store-old-json")
    op = next(reversed(h._resource_ops))
    with pytest.raises(LookupError):
        restored._resource_query(restored_owner, op)


def test_failed_retry_uses_immutable_attempt_context(tmp_path):
    h = _hub(tmp_path)
    owner, _out = _attach(h, "immutable-attempt")
    begin = _begin(h, owner, kind="cloud", key=owner.uid, op=None,
                   payload=RESOURCE_A)
    op = _ctx_field(begin, "resource_operation_id")
    with h.lock:
        with h._resource_lock:
            h._resource_finalize_locked(
                begin, status="failed", io_effect="not_committed",
                stage="replace", error_code="synthetic", retryable=True)
    retry = _begin(h, owner, kind="cloud", key=owner.uid, op=op,
                   payload=RESOURCE_A)
    assert retry is not begin
    assert begin["attempt"] == 1 and begin["status"] == "failed"
    assert retry["attempt"] == 2 and retry["status"] == "pending"
    # latest_permit is reserved at final C, not at begin/stage; the registry
    # still points the logical op at the fresh immutable attempt context.
    assert h._resource_ops[op] is retry


def test_same_key_staged_ops_are_ordered_at_final_c(tmp_path):
    h = _hub(tmp_path)
    owner, _out = _attach(h, "same-key-c-order")
    a = _context(_begin(h, owner, kind="cloud", key=owner.uid, op=None,
                        payload=RESOURCE_A))
    b = _context(_begin(h, owner, kind="cloud", key=owner.uid, op=None,
                        payload=RESOURCE_B))
    result_b = h._resource_file_commit(b, RESOURCE_B)
    assert result_b["status"] == "confirmed"
    with pytest.raises(RuntimeError):
        h._resource_file_commit(a, RESOURCE_A)
    assert h.cloud[owner.uid]["blob"] == RESOURCE_B


def test_late_old_io_cannot_finalize_new_retry_attempt(tmp_path, monkeypatch):
    h = _hub(tmp_path)
    owner, _out = _attach(h, "late-old-io")
    ctx = _context(_begin(h, owner, kind="cloud", key=owner.uid, op=None,
                          payload=RESOURCE_A))
    entered = threading.Event()
    release = threading.Event()
    original_stage = h._resource_stage_bytes
    result = []

    def blocked_stage(data, suffix):
        entered.set()
        assert release.wait(3.0)
        return original_stage(data, suffix)

    monkeypatch.setattr(h, "_resource_stage_bytes", blocked_stage)
    thread = threading.Thread(
        target=lambda: result.append(_resource_commit_catching(
            h, ctx, RESOURCE_A)), daemon=True)
    thread.start()
    assert entered.wait(3.0)
    with h.lock:
        with h._resource_lock:
            h._resource_finalize_locked(
                ctx, status="failed", io_effect="not_committed",
                stage="synthetic", error_code="late-failure", retryable=True)
    retry = _begin(h, owner, kind="cloud", key=owner.uid,
                   op=ctx["resource_operation_id"], payload=RESOURCE_A)
    assert retry is not ctx and retry["attempt"] == 2
    release.set()
    thread.join(3.0)
    assert not thread.is_alive()
    assert result and result[0] == "stale_attempt"
    assert retry["status"] == "pending"
    assert owner.uid not in h.cloud


def test_resource_io_pause_does_not_block_t0_or_other_chat(tmp_path, monkeypatch):
    h = _hub(tmp_path)
    owner, out = _attach(h, "io-pause")
    other, _other_out = _attach(h, "io-pause-other")
    entered = threading.Event()
    release = threading.Event()
    original = h._resource_stage_bytes

    def blocked_stage(data, suffix):
        entered.set()
        assert release.wait(3.0)
        return original(data, suffix)

    monkeypatch.setattr(h, "_resource_stage_bytes", blocked_stage)
    thread = threading.Thread(target=lambda: h._on_cloud_put(
        owner, {"t": "cloud_put"}, RESOURCE_A), daemon=True)
    thread.start()
    assert entered.wait(3.0)
    with h.lock:
        h.retired[owner.uid] = {"nick": owner.nick, "retired_at": time.time(),
                                "operation_id": "retire-io-pause"}
    h._on_chat(owner, {"t": "chat", "channel": "public", "text": "late"})
    assert not any(m.get("text") == "late" for m in h.bus.history("all"))
    h._on_chat(other, {"t": "chat", "channel": "public", "text": "other-live"})
    assert any(m.get("text") == "other-live" for m in h.bus.history("all"))
    release.set()
    thread.join(3.0)
    assert not thread.is_alive()
    assert not h.cloud.get(owner.uid)


def test_c_before_t0_allows_cloud_io_but_withdraws_readable_index(tmp_path,
                                                                  monkeypatch):
    h = _hub(tmp_path)
    owner, _out = _attach(h, "c-before-t0")
    real_replace = os.replace
    entered = threading.Event()
    release = threading.Event()

    def replace_pause(src, dst):
        real_replace(src, dst)
        entered.set()
        assert release.wait(3.0)

    monkeypatch.setattr(os, "replace", replace_pause)
    thread = threading.Thread(target=lambda: h._on_cloud_put(
        owner, {"t": "cloud_put"}, RESOURCE_A), daemon=True)
    thread.start()
    assert entered.wait(3.0)
    with h.lock:
        h.retired[owner.uid] = {"nick": owner.nick, "retired_at": time.time(),
                                "operation_id": "retire-after-c"}
    release.set()
    thread.join(3.0)
    assert not thread.is_alive()
    op = next(reversed(h._resource_ops))
    owner.is_admin = True
    result = _result(h, owner, op, explicit_owner=owner.uid)
    assert result["status"] == "confirmed"
    assert result["visibility"] == "withdrawn"
    assert not h.cloud.get(owner.uid)
    assert Path(h.cloud_dir, f"{owner.uid}.bin").read_bytes() == RESOURCE_A


def test_unknown_cloud_missing_read_stays_unknown_without_write(tmp_path):
    h = _hub(tmp_path)
    owner, out = _attach(h, "cloud-missing-read")
    real_replace = os.replace

    def replace_then_raise(src, dst):
        real_replace(src, dst)
        raise OSError("ack lost")

    original = os.replace
    os.replace = replace_then_raise
    try:
        h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    finally:
        os.replace = original
    op = _issued_op(out)
    path = Path(h.cloud_dir, f"{owner.uid}.bin")
    path.unlink()
    result = _result(h, owner, op)
    assert result["status"] == "unknown"
    assert not h.cloud.get(owner.uid)


def test_unknown_target_equal_known_predecessor_becomes_failed(tmp_path,
                                                              monkeypatch):
    h = _hub(tmp_path)
    owner, out = _attach(h, "cloud-known-predecessor")
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    out.frames.clear()
    real_replace = os.replace

    def replace_then_raise(src, dst):
        real_replace(src, dst)
        raise OSError("replace ack lost")

    monkeypatch.setattr(os, "replace", replace_then_raise)
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_B)
    op = _issued_op(out)
    Path(h.cloud_dir, f"{owner.uid}.bin").write_bytes(RESOURCE_A)
    result = _result(h, owner, op)
    assert result["status"] == "failed"
    assert result["error_code"] == "known_predecessor"
    assert result["io_effect"] == "not_committed"


@pytest.mark.parametrize("failure", ["open", "fsync"])
def test_cloud_stage_real_io_failures_are_failed_before_c(tmp_path, monkeypatch,
                                                          failure):
    h = _hub(tmp_path)
    owner, out = _attach(h, f"cloud-stage-{failure}")
    if failure == "open":
        original_fdopen = os.fdopen

        def fail_fdopen(*args, **kwargs):
            raise OSError("synthetic stage open failure")

        monkeypatch.setattr(os, "fdopen", fail_fdopen)
    else:
        monkeypatch.setattr(os, "fsync", lambda _fd: (_ for _ in ()).throw(
            OSError("synthetic fsync failure")))
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    op = _issued_op(out)
    result = _result(h, owner, op)
    assert result["status"] == "failed"
    assert result["io_effect"] == "not_committed"
    assert not _cloud_done(out)


def test_stage_fdopen_failure_closes_raw_fd_and_temp(tmp_path, monkeypatch):
    h = _hub(tmp_path)
    owner, out = _attach(h, "stage-fd-cleanup")
    captured = []

    def fail_fdopen(fd, *args, **kwargs):
        captured.append(fd)
        raise OSError("fdopen failed")

    monkeypatch.setattr(os, "fdopen", fail_fdopen)
    before = set(Path(h._resource_stage_dir).iterdir())
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    after = set(Path(h._resource_stage_dir).iterdir())
    assert captured
    with pytest.raises(OSError):
        os.fstat(captured[0])
    assert after == before
    op = _issued_op(out)
    assert _result(h, owner, op)["status"] == "failed"


@pytest.mark.parametrize("failure", ["shortwrite", "flush", "close"])
def test_cloud_stage_shortwrite_flush_close_fail_before_c(tmp_path, monkeypatch,
                                                           failure):
    h = _hub(tmp_path)
    owner, out = _attach(h, f"cloud-stage-{failure}")
    real_fdopen = os.fdopen

    class WrappedFile:
        def __init__(self, inner):
            self.inner = inner

        def __enter__(self):
            self.inner.__enter__()
            return self

        def __exit__(self, *args):
            result = self.inner.__exit__(*args)
            if failure == "close":
                raise OSError("synthetic close failure")
            return result

        def write(self, data):
            if failure == "shortwrite":
                return 0
            return self.inner.write(data)

        def flush(self):
            if failure == "flush":
                raise OSError("synthetic flush failure")
            return self.inner.flush()

        def fileno(self):
            return self.inner.fileno()

    monkeypatch.setattr(os, "fdopen",
                        lambda *args, **kwargs: WrappedFile(
                            real_fdopen(*args, **kwargs)))
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    op = _issued_op(out)
    result = _result(h, owner, op)
    assert result["status"] == "failed"
    assert result["io_effect"] == "not_committed"


def test_cloud_get_sends_only_current_confirmed_bytes(tmp_path):
    h = _hub(tmp_path)
    owner, out = _attach(h, "cloud-get")
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    op = _issued_op(out)
    out.frames.clear()
    # Ordinary CLOUD_GET returns the current bytes; resource_operation_id is
    # the result/query surface and returns a finite CLOUD_DONE summary only.
    h._on_cloud_get(owner, {})
    data = [body for payload, body in out.frames if payload.get("t") == "cloud_data"]
    assert data == [RESOURCE_A]


def test_resource_quota_rejection_performs_no_stage_io(tmp_path, monkeypatch):
    h = _hub(tmp_path)
    owner, _out = _attach(h, "quota-owner")
    calls = []
    real_open = builtins.open

    def record_open(*args, **kwargs):
        calls.append(args[0] if args else "")
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", record_open)
    h._resource_max_active = 0
    with pytest.raises((PermissionError, RuntimeError, ValueError)):
        _begin(h, owner, kind="cloud", key=owner.uid, op=None,
               payload=RESOURCE_A)
    assert calls == []


def test_web_new_manifest_requires_body_and_exact_hash(tmp_path):
    h = _hub(tmp_path)
    owner, out = _attach(h, "web-owner")
    fid = FID_A
    root = Path(h.web_files)
    root.mkdir(parents=True, exist_ok=True)
    (root / fid).write_bytes(RESOURCE_A)
    manifest = {
        "fid": fid,
        "name": "a.txt",
        "size": len(RESOURCE_A),
        "kind": "file",
        "ts": 1.0,
        "resource_manifest_version": 1,
        "resource_owner_uid": owner.uid,
        "resource_operation_id": OP_A,
        "content_length": len(RESOURCE_A),
        "content_sha256": hashlib.sha256(RESOURCE_A).hexdigest(),
    }
    (root / (fid + ".json")).write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    h._on_chat(owner, {"t": "chat", "channel": "public", "text": "file",
                        "file": {"fid": fid}})
    assert any(m.get("file", {}).get("fid") == fid
               for m in h.bus.history("all"))
    out.frames.clear()
    (root / fid).write_bytes(RESOURCE_B)
    h._on_chat(owner, {"t": "chat", "channel": "public", "text": "bad",
                        "file": {"fid": fid}})
    assert not any(p.get("t") == "chat" and p.get("text") == "bad"
                   for p, _body in out.frames)


def test_web_body_replace_after_wrapper_error_is_failed_orphan(tmp_path,
                                                               monkeypatch):
    h = _hub(tmp_path)
    owner, _out = _attach(h, "web-body-orphan")
    real_replace = os.replace
    calls = []

    def replace_then_raise_once(src, dst):
        calls.append((src, dst))
        real_replace(src, dst)
        raise OSError("body acknowledgement lost")

    monkeypatch.setattr(os, "replace", replace_then_raise_once)
    with pytest.raises(RuntimeError):
        h._save_web_file("orphan.txt", RESOURCE_A, "file", sess=owner)
    assert calls
    op = next(reversed(h._resource_ops))
    ctx = h._resource_ops[op]
    fid = ctx["resource_key"]
    assert ctx["status"] == "failed"
    assert ctx["io_effect"] == "not_committed"
    assert Path(h.web_files, fid).is_file()
    assert not Path(h.web_files, fid + ".json").is_file()
    assert h._web_file_meta(fid) is None


def test_web_existing_body_then_manifest_replace_ack_is_unknown_reconciled(
        tmp_path, monkeypatch):
    h = _hub(tmp_path)
    owner, _out = _attach(h, "web-reconcile-manifest")
    real_replace = os.replace
    phase = ["first-body"]

    def staged_replace(src, dst):
        real_replace(src, dst)
        if phase[0] == "first-body":
            phase[0] = "retry-body"
            raise OSError("first body ack lost")
        if phase[0] == "retry-body":
            phase[0] = "retry-manifest"
            return
        if phase[0] == "retry-manifest":
            real_replace(src, dst)
            raise OSError("manifest ack lost after replace")

    monkeypatch.setattr(os, "replace", staged_replace)
    with pytest.raises(RuntimeError) as first_error:
        h._save_web_file("recover.txt", RESOURCE_A, "file", sess=owner)
    first_op = next(reversed(h._resource_ops))
    assert first_error.value.result["status"] == "failed"
    with pytest.raises(RuntimeError) as second_error:
        h._save_web_file("recover.txt", RESOURCE_A, "file", sess=owner,
                         resource_operation_id=first_op)
    assert second_error.value.result["status"] == "unknown"
    reconciled = _result(h, owner, first_op)
    assert reconciled["status"] == "confirmed"
    assert reconciled["origin"] == "reconciled_current_resource"


def test_web_known_op_metadata_mismatch_rejects_without_file_io(tmp_path,
                                                               monkeypatch):
    h = _hub(tmp_path)
    owner, _out = _attach(h, "web-metadata-mismatch")
    saved = h._save_web_file("same.txt", RESOURCE_A, "file", sess=owner)
    op = saved["resource"]["resource_operation_id"]
    calls = []
    real_open = builtins.open

    def record_open(*args, **kwargs):
        calls.append(args[0] if args else "")
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", record_open)
    with pytest.raises(PermissionError):
        h._save_web_file("different.txt", RESOURCE_A, "file", sess=owner,
                         resource_operation_id=op)
    assert calls == []


def test_web_cread_captures_verified_bytes_then_rechecks_next_request(tmp_path):
    h = _hub(tmp_path)
    owner, _owner_out = _attach(h, "cread-owner")
    other, _other_out = _attach(h, "cread-other")
    saved = h._save_web_file("cread.txt", RESOURCE_A, "file", sess=owner)
    fid = saved["fid"]
    meta = h._web_file_meta(fid)
    captured = h._web_file_read(other, fid, meta)
    with h.lock:
        h.retired[owner.uid] = {"nick": owner.nick, "retired_at": time.time(),
                                "operation_id": "retire-cread-owner"}
    Path(h.web_files, fid).write_bytes(RESOURCE_B)
    assert captured == RESOURCE_A
    with pytest.raises(OSError):
        h._web_file_read(other, fid, meta)


@pytest.mark.parametrize("bad_manifest", [
    '{"fid":"' + FID_B + '","name":"x","size":1,"kind":"file",'
    '"ts":1,"resource_manifest_version":2}',
    '{"fid":"' + FID_B + '","name":"x","size":1,"kind":"file",'
    '"ts":1,"resource_manifest_version":1,"resource_owner_uid":1}',
    '{"fid":"' + FID_B + '","name":"x","size":1,"kind":"file",'
    '"ts":1,"resource_manifest_version":1,"resource_owner_uid":1,'
    '"resource_operation_id":"x","content_length":1,'
    '"content_sha256":"bad","content_sha256":"bad2"}',
])
def test_web_bad_new_manifest_never_falls_back_to_legacy(tmp_path, bad_manifest):
    h = _hub(tmp_path)
    owner, out = _attach(h, "manifest-owner")
    root = Path(h.web_files)
    root.mkdir(parents=True, exist_ok=True)
    (root / FID_B).write_bytes(RESOURCE_A)
    (root / (FID_B + ".json")).write_text(bad_manifest, encoding="utf-8")
    h._on_chat(owner, {"t": "chat", "channel": "public", "text": "bad",
                        "file": {"fid": FID_B}})
    assert not any(p.get("t") == "chat" for p, _body in out.frames)


def test_legacy_manifest_remains_shared_only_when_body_is_present(tmp_path):
    h = _hub(tmp_path)
    owner, out = _attach(h, "legacy-owner")
    root = Path(h.web_files)
    root.mkdir(parents=True, exist_ok=True)
    legacy = {"fid": FID_A, "name": "legacy.txt", "size": len(RESOURCE_A),
              "kind": "file", "ts": 1.0}
    (root / (FID_A + ".json")).write_text(json.dumps(legacy), encoding="utf-8")
    h._on_chat(owner, {"t": "chat", "channel": "public", "text": "missing",
                        "file": {"fid": FID_A}})
    assert not any(p.get("t") == "chat" for p, _body in out.frames)
    (root / FID_A).write_bytes(RESOURCE_A)
    h._on_chat(owner, {"t": "chat", "channel": "public", "text": "legacy",
                        "file": {"fid": FID_A}})
    assert any(p.get("t") == "chat" and p.get("text") == "legacy"
               for p, _body in out.frames)


def test_resource_query_wrong_owner_performs_no_file_read(tmp_path, monkeypatch):
    h = _hub(tmp_path)
    owner, _out = _attach(h, "query-owner")
    other, _other_out = _attach(h, "query-other")
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    op = _issued_op(_out)
    calls = []
    real_open = builtins.open

    def record_open(*args, **kwargs):
        calls.append(args[0] if args else "")
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", record_open)
    with pytest.raises((PermissionError, ValueError, LookupError)):
        h._resource_query(other, op)
    assert calls == []


def test_t0_withdraws_private_cloud_index_without_deleting_body(tmp_path):
    h = _hub(tmp_path)
    owner, _owner_out = _attach(h, "withdraw-owner")
    h._on_cloud_put(owner, {"t": "cloud_put"}, RESOURCE_A)
    op = _issued_op(_owner_out)
    path = Path(h.cloud_dir) / f"{owner.uid}.bin"
    assert path.read_bytes() == RESOURCE_A
    with h.lock:
        h.retired[owner.uid] = {"nick": owner.nick, "retired_at": time.time(),
                                "operation_id": "retire-resource"}
    h._resource_withdraw_owner(owner.uid)
    owner.is_admin = True
    result = _result(h, owner, op, explicit_owner=owner.uid)
    assert result["visibility"] == "withdrawn"
    assert path.read_bytes() == RESOURCE_A
