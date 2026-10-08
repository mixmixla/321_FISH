# -*- coding: utf-8 -*-
"""CC-02B-STORE: strict bytes and typed receipt seam.

These tests deliberately resolve the new seam at call time.  The pre-GO
baseline therefore remains collectable and records a functional red instead
of failing collection because the new names do not exist yet.
"""
import hashlib
import importlib
import json
import math
import os
import builtins
import copy
import threading
from dataclasses import replace

import pytest
from server_recovery import StoreCoordinator


_test_hubs = []


@pytest.fixture(autouse=True)
def _close_owned_hubs():
    _test_hubs.clear()
    yield
    for h in _test_hubs:
        # Deliberate FAILED cases return False; cleanup proves lifetime ends,
        # rather than converting a failed Store into a successful shutdown.
        h.shutdown(normal=False)
        assert not h._recovery.owner.held
        assert not any(t.is_alive() for t in h._managed_threads)
    _test_hubs.clear()


def _store_module():
    return importlib.import_module("server_store")


def _api(name):
    fn = getattr(_store_module(), name, None)
    assert callable(fn), f"CC-02B seam missing: server_store.{name}"
    return fn


def _field(value, *names):
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    raise AssertionError(f"result field missing: {names!r}")


def _retire_fixture(tmp_path, *, with_admin=False):
    """Create a real known predecessor and an in-memory t0 pending candidate."""
    from config import CFG
    from server import Hub, Session

    cfg = replace(
        CFG,
        admin_nick="L57",
        admin_pwd="test-admin-password",
        audit_dir=str(tmp_path / "audit"),
        web_files_dir=str(tmp_path / "web"),
        persist_interval=0.0,
    )
    StoreCoordinator.initialize_new(tmp_path / 'store')
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"),
            store_dir=str(tmp_path / "store"))
    _test_hubs.append(h)
    h.nick_to_uid["victim"] = 7
    h.known[7] = {"nick": "victim", "last_online": 1.0}
    if with_admin:
        h._uid_seq = 8
    assert h._persist_flush()
    if with_admin:
        admin = Session(0, cfg.admin_nick, 'tcp', '127.0.0.1', lambda *_: None)
        # This fixture exercises a deliberately failed later retirement. Drain
        # setup's required fresh capture synchronously before creating its
        # intent, so an unrelated setup worker cannot publish the test's t0.
        queue, requested = h._persist_queue_trigger, []
        h._persist_queue_trigger = lambda *_: requested.append(True)
        try:
            assert h._on_hello(admin, {'nick': cfg.admin_nick, 'pwd': cfg.admin_pwd})
            assert requested and h._persist(force=True)
        finally:
            h._persist_queue_trigger = queue
        h._fixture_admin = admin
        assert h.store.load()['nick_to_uid'][cfg.admin_nick] == admin.uid
    predecessor = copy.deepcopy(h._snapshot_state())
    operation_id = "op-t1-victim"
    record = {"nick": "victim", "retired_at": 2.0, "operation_id": operation_id}
    with h._persist_writer_lock:
        assert h._recovery.accept_intent(7, record).effect == 'committed'
        with h.lock:
            h._apply_retirement_core_locked(7, record)
            h._retire_ops[7] = {
                "status": "pending", "operation_id": operation_id,
                "target_uid": 7, "target_nick": "victim",
                "persistence_phase": "snapshot", "identity_effect": "revoked",
            }
    candidate_state = h._snapshot_state()
    candidate = {
        "uid": 7,
        "operation_id": operation_id,
        "target_nick": "victim",
        "record": candidate_state["retired"]["7"],
    }
    return h, predecessor, candidate_state, candidate


def _read_result_for_payload(module, payload):
    read_cls = getattr(module, "ReadResult", None)
    assert read_cls is not None
    return read_cls("bytes", payload, len(payload),
                    hashlib.sha256(payload).hexdigest())


def test_strict_encode_state_returns_one_digestible_bytes_payload():
    encode_state = _api("encode_state")
    state = {
        "中文": "保留 UTF-8",
        "known": {1: {"nick": "alice", "remarks": {"x": [1, 2]}}},
        "burn": {"1": {"pend": [2, 3]}},
    }

    encoded = encode_state(state)
    payload = _field(encoded, "payload", "data")
    assert isinstance(payload, bytes)
    assert _field(encoded, "length") == len(payload)
    assert _field(encoded, "sha256", "digest") == hashlib.sha256(payload).hexdigest()
    assert json.loads(payload.decode("utf-8")) == {
        "中文": "保留 UTF-8",
        "known": {"1": {"nick": "alice", "remarks": {"x": [1, 2]} }},
        "burn": {"1": {"pend": [2, 3]}},
    }


@pytest.mark.parametrize(
    "state",
    [
        {"bad": object()},
        {"bad": {1, 2}},
        {"bad": float("nan")},
        {"bad": float("inf")},
        {1: "integer key", "1": "string key"},
    ],
)
def test_strict_encode_rejects_values_json_would_coerce_or_hide(state):
    encode_state = _api("encode_state")
    with pytest.raises((TypeError, ValueError, OverflowError)):
        encode_state(state)


def test_save_bytes_and_read_bytes_result_report_real_authority(tmp_path):
    module = _store_module()
    encode_state = _api("encode_state")
    store_cls = getattr(module, "ServerStore", None)
    assert store_cls is not None
    store = store_cls(str(tmp_path / "state.json"))
    payload = _field(encode_state({"n": 1}), "payload", "data")

    save_bytes = getattr(store, "save_bytes", None)
    assert callable(save_bytes), "CC-02B seam missing: ServerStore.save_bytes"
    saved = save_bytes(payload)
    assert _field(saved, "effect") == "committed"
    assert _field(saved, "length") == len(payload)
    assert _field(saved, "sha256", "digest") == hashlib.sha256(payload).hexdigest()
    assert (tmp_path / "state.json").read_bytes() == payload

    read_bytes_result = getattr(store, "read_bytes_result", None)
    assert callable(read_bytes_result), "CC-02B seam missing: ServerStore.read_bytes_result"
    read = read_bytes_result()
    assert _field(read, "status", "effect") == "bytes"
    assert _field(read, "payload", "data") == payload


def test_read_bytes_result_distinguishes_missing_without_falling_back_to_empty_object(tmp_path):
    module = _store_module()
    store_cls = getattr(module, "ServerStore", None)
    assert store_cls is not None
    store = store_cls(str(tmp_path / "missing.json"))
    read_bytes_result = getattr(store, "read_bytes_result", None)
    assert callable(read_bytes_result), "CC-02B seam missing: ServerStore.read_bytes_result"
    result = read_bytes_result()
    assert _field(result, "status", "effect") == "missing"
    assert _field(result, "payload", "data") is None


def test_strict_encode_rejects_non_finite_values_without_rewriting_state():
    encode_state = _api("encode_state")
    for number in (math.nan, math.inf, -math.inf):
        with pytest.raises((TypeError, ValueError, OverflowError)):
            encode_state({"number": number})


def test_save_bytes_completes_short_writes_and_rejects_zero_progress(tmp_path,
                                                                     monkeypatch):
    module = _store_module()
    store_cls = getattr(module, "ServerStore", None)
    assert store_cls is not None
    path = tmp_path / "state.json"
    store = store_cls(str(path))
    initial = _field(_api("encode_state")({"version": 1}), "payload", "data")
    assert store.save_bytes(initial).effect == "committed"
    real_open = builtins.open
    tmp_name = os.path.abspath(str(path) + ".tmp")

    class ShortFile:
        def __init__(self, inner, zero=False):
            self.inner = inner
            self.zero = zero

        def write(self, data):
            if self.zero:
                return 0
            piece = data[:2]
            self.inner.write(piece)
            return len(piece)

        def flush(self):
            return self.inner.flush()

        def fileno(self):
            return self.inner.fileno()

        def close(self):
            return self.inner.close()

    def short_open(name, mode="r", *args, **kwargs):
        inner = real_open(name, mode, *args, **kwargs)
        if os.path.abspath(str(name)) == tmp_name and "wb" in mode:
            return ShortFile(inner)
        return inner

    monkeypatch.setattr(builtins, "open", short_open)
    encoded = _field(_api("encode_state")({"version": 2}), "payload", "data")
    result = store.save_bytes(encoded)
    assert result.effect == "committed"
    assert path.read_bytes() == encoded

    def zero_open(name, mode="r", *args, **kwargs):
        inner = real_open(name, mode, *args, **kwargs)
        if os.path.abspath(str(name)) == tmp_name and "wb" in mode:
            return ShortFile(inner, zero=True)
        return inner

    monkeypatch.setattr(builtins, "open", zero_open)
    failed = store.save_bytes(initial)
    assert failed.effect == "not_committed"
    assert failed.stage == "write"
    assert path.read_bytes() == encoded


def test_replace_exception_after_real_replace_is_uncertain(tmp_path, monkeypatch):
    module = _store_module()
    store_cls = getattr(module, "ServerStore", None)
    assert store_cls is not None
    path = tmp_path / "state.json"
    store = store_cls(str(path))
    encode_state = _api("encode_state")
    old = _field(encode_state({"version": 1}), "payload", "data")
    new = _field(encode_state({"version": 2}), "payload", "data")
    assert store.save_bytes(old).effect == "committed"
    real_replace = os.replace

    def replace_then_raise(source, target):
        real_replace(source, target)
        raise OSError("replace acknowledgement lost")

    monkeypatch.setattr(os, "replace", replace_then_raise)
    result = store.save_bytes(new)
    assert result.effect == "uncertain"
    assert result.stage == "replace"
    assert path.read_bytes() == new


def test_strict_reconcile_reader_rejects_duplicate_keys_and_surrogates():
    from server import Hub

    with pytest.raises(ValueError):
        Hub._strict_state_from_bytes(b'{"a":1,"a":2}')
    with pytest.raises(UnicodeError):
        Hub._strict_state_from_bytes(b'{"text":"\\ud800"}')


@pytest.mark.parametrize(
    "residual",
    [
        "known", "draft", "sched", "blocks", "reads",
        "group_member", "group_admin", "group_mute", "group_owner",
        "bus_author", "burn_author",
    ],
)
def test_captured_t0_residual_is_rejected_before_any_save_or_replace(
        tmp_path, monkeypatch, residual):
    h, _predecessor, _candidate_state, _candidate = _retire_fixture(tmp_path)
    captured = threading.Event()
    release = threading.Event()
    holder = {}
    errors = []
    result = []

    def mutate(state):
        if residual == "known":
            state["known"][7] = {"nick": "victim"}
        elif residual == "draft":
            state["drafts"]["7|public"] = {"text": "late"}
        elif residual == "sched":
            state["scheds"]["7"] = {"rid": {"channel": "public"}}
        elif residual == "blocks":
            state["blocks"]["7"] = [2]
        elif residual == "reads":
            state["reads"].setdefault("public", {})["7"] = 1
        elif residual.startswith("group_"):
            group = {
                "gid": 1, "name": "g", "owner": 2,
                "admins": [], "members": {2: "other"}, "mutes": {},
                "announce": "", "announce_mode": 0, "invite": "",
                "kind": "", "public": 0, "slow": 0,
            }
            if residual == "group_member":
                group["members"][7] = "victim"
            elif residual == "group_admin":
                group["members"][7] = "victim"
                group["admins"] = [7]
            elif residual == "group_mute":
                group["members"][7] = "victim"
                group["mutes"] = {7: 99.0}
            else:
                group["owner"] = 7
                group["members"] = {7: "victim", 2: "other"}
            state["groups"]["1"] = group
        elif residual == "bus_author":
            state["bus"]["channels"].setdefault("all", []).append(
                {"seq": 99, "uid": 7, "channel": "public", "text": "late"})
        elif residual == "burn_author":
            state["burn"][99] = {"channel": "public", "uid": 7,
                                   "to": None, "ts": 1.0, "pend": []}
        else:  # pragma: no cover - parameter list is exhaustive
            raise AssertionError(residual)

    original_snapshot = h._snapshot_state

    def paused_snapshot():
        state = original_snapshot()
        holder["state"] = state
        captured.set()
        assert release.wait(5)
        return state

    monkeypatch.setattr(h, "_snapshot_state", paused_snapshot)
    save_calls = []
    replace_calls = []
    original_save = h.store._save_encoded
    monkeypatch.setattr(
        h.store, "_save_encoded",
        lambda encoded: save_calls.append(1) or original_save(encoded),
    )
    real_replace = os.replace
    monkeypatch.setattr(
        os, "replace",
        lambda source, target: replace_calls.append(1)
        or real_replace(source, target),
    )

    def run_writer():
        try:
            result.append(h._persist_sync())
        except BaseException as exc:  # report thread failures to pytest
            errors.append(exc)

    thread = threading.Thread(target=run_writer, name="cc02-st03-writer")
    thread.start()
    try:
        assert captured.wait(5)
        mutate(holder["state"])
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert not errors
    assert result == [False]
    assert save_calls == []
    assert replace_calls == []
    assert h._persist_dirty is True
    assert h.retired[7]["operation_id"] == "op-t1-victim"


@pytest.mark.parametrize("read_case", [
    "missing", "read_error", "bad_json", "same_uid_other_op",
    "nick_conflict", "cleanup_residual", "valid_unrecognized_predecessor",
])
@pytest.mark.parametrize("writer_path", [
    "worker", "force", "flush", "bound_save", "bound_save_bytes",
])
def test_unknown_blocks_every_writer_path_without_replacement(
        tmp_path, monkeypatch, read_case, writer_path):
    module = _store_module()
    encode_state = _api("encode_state")
    read_cls = getattr(module, "ReadResult", None)
    assert read_cls is not None
    h, predecessor, candidate_state, _candidate = _retire_fixture(tmp_path)
    real_replace = os.replace

    def replace_then_raise(source, target):
        real_replace(source, target)
        raise OSError("post-replace acknowledgement lost")

    monkeypatch.setattr(os, "replace", replace_then_raise)
    assert h._persist(force=True) is False
    monkeypatch.setattr(os, "replace", real_replace)
    assert h._persist_unresolved is not None
    assert h._retire_ops[7]["status"] == "unknown"

    def read_case_result():
        if read_case == "missing":
            return read_cls("missing")
        if read_case == "read_error":
            return read_cls("read_error", error_code="injected_read_error")
        if read_case == "bad_json":
            payload = b'{"retired":{},"retired":{}}'
            return _read_result_for_payload(module, payload)
        if read_case == "same_uid_other_op":
            state = copy.deepcopy(candidate_state)
            state["retired"]["7"]["operation_id"] = "other-op"
            encoded = encode_state(state)
            return _read_result_for_payload(module, encoded.payload)
        if read_case == "nick_conflict":
            state = copy.deepcopy(candidate_state)
            state["nick_to_uid"]["victim"] = 8
            encoded = encode_state(state)
            return _read_result_for_payload(module, encoded.payload)
        if read_case == "cleanup_residual":
            state = copy.deepcopy(candidate_state)
            state["known"]["7"] = {"nick": "victim"}
            encoded = encode_state(state)
            return _read_result_for_payload(module, encoded.payload)
        if read_case == "valid_unrecognized_predecessor":
            state = copy.deepcopy(predecessor)
            state["uid_seq"] = int(state.get("uid_seq", 0)) + 100
            encoded = encode_state(state)
            return _read_result_for_payload(module, encoded.payload)
        raise AssertionError(read_case)  # pragma: no cover

    read_called = threading.Event()

    def read_unknown():
        read_called.set()
        return read_case_result()

    monkeypatch.setattr(h.store, "read_bytes_result", read_unknown)
    save_calls = []
    replace_calls = []
    original_save = h.store._save_encoded

    def spy_save(encoded):
        save_calls.append(1)
        return original_save(encoded)

    monkeypatch.setattr(h.store, "_save_encoded", spy_save)
    monkeypatch.setattr(
        os, "replace",
        lambda source, target: replace_calls.append(1)
        or real_replace(source, target),
    )
    worker = None
    try:
        if writer_path == "worker":
            h._persist_last -= h._persist_interval + 1
            h._persist()
            worker = h._persist_worker_thread
        elif writer_path == "force":
            assert h._persist(force=True) is False
        elif writer_path == "flush":
            h._persist_flush()
        elif writer_path == "bound_save":
            assert h.store.save({"ignored": True}) is False
        else:
            result = h.store.save_bytes(b"ignored")
            assert _field(result, "effect") != "committed"
        assert read_called.wait(5)
    finally:
        if worker is not None:
            h._persist_closing = True
            h._persist_wake.set()
            worker.join(5)
    assert worker is None or not worker.is_alive()
    assert save_calls == []
    assert replace_calls == []
    assert h._persist_unresolved is not None
    assert h._retire_ops[7]["status"] == "unknown"
    assert h._persist_dirty is True
    assert 7 in h.retired


def test_known_predecessor_allows_same_operation_retry(tmp_path, monkeypatch):
    h, _predecessor, _candidate_state, _candidate = _retire_fixture(tmp_path, with_admin=True)
    from server import Session
    original_save = h.store._save_encoded
    module = _store_module()
    monkeypatch.setattr(h.store, '_save_encoded', lambda encoded: module.SaveResult(
        'not_committed', 'write', 'synthetic_predecessor', True, encoded.length, encoded.sha256))
    assert h._persist(force=True) is False
    assert h._retire_ops[7]['status'] == 'failed' and h._retire_ops[7]['retryable']
    prior_admin_uid = h._fixture_admin.uid
    h.unregister(h._fixture_admin, 'synthetic administrator disconnected after failure')
    save_seen = threading.Event()

    def spy_save(encoded):
        save_seen.set()
        return original_save(encoded)

    monkeypatch.setattr(h.store, "_save_encoded", spy_save)
    # Ordinary writers do not silently retry an accepted retirement. Only
    # an authenticated explicit retry may publish the same operation again.
    assert h._persist(force=True) is False
    assert not save_seen.is_set()
    admin = Session(0, h.cfg.admin_nick, 'tcp', '127.0.0.1', lambda *_: None)
    assert h._on_hello(admin, {'nick': h.cfg.admin_nick, 'pwd': h.cfg.admin_pwd})
    assert admin.uid == prior_admin_uid and not save_seen.is_set()
    h._on_admin_user_del(admin, {'uid': 7, 'operation_id': 'op-t1-victim', 'request_id': 'retry-proof'})
    assert save_seen.wait(5)
    assert h._retire_ops[7]["status"] == "confirmed"
    assert h._retirement_payload(7)["origin"] == "written"
    assert h.store.load()["retired"]["7"]["operation_id"] == "op-t1-victim"


def test_known_successor_same_operation_confirms_actual_sha_and_keeps_late_dirty(
        tmp_path, monkeypatch):
    h, _predecessor, _candidate_state, candidate = _retire_fixture(tmp_path)
    assert h._persist(force=True) is True
    committed = h.store.read_bytes_result()
    committed_sha = committed.sha256
    assert committed_sha in h._persist_success_evidence["op-t1-victim"]

    h._retire_ops[7]["status"] = "unknown"
    h._persist_unresolved = {
        "sha256": "uncommitted-candidate-sha",
        "length": 1,
        "capture_request_seq": h._persist_request_seq,
        "candidates": [dict(candidate)],
    }
    read_entered = threading.Event()
    release_read = threading.Event()
    original_read = h.store.read_bytes_result

    def blocked_read():
        read_entered.set()
        assert release_read.wait(5)
        return original_read()

    monkeypatch.setattr(h.store, "read_bytes_result", blocked_read)
    save_calls = []
    replace_calls = []
    original_save = h.store._save_encoded
    monkeypatch.setattr(
        h.store, "_save_encoded",
        lambda encoded: save_calls.append(1) or original_save(encoded),
    )
    real_replace = os.replace
    monkeypatch.setattr(
        os, "replace",
        lambda source, target: replace_calls.append(1)
        or real_replace(source, target),
    )
    result = []
    errors = []

    def run_force():
        try:
            result.append(h._persist(force=True))
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run_force, name="cc02-t1-successor")
    thread.start()
    try:
        assert read_entered.wait(5)
        h.nick_to_uid["late"] = 999
        h._persist_request()
    finally:
        release_read.set()
        thread.join(5)
    assert not thread.is_alive()
    assert not errors
    assert result == [True]
    assert h._retire_ops[7]["status"] == "confirmed"
    assert h._retirement_payload(7)["origin"] == "reconciled_current_json"
    assert h._retirement_payload(7)["content_sha256"] == committed_sha
    assert h._persist_receipt.origin == "reconciled_current_json"
    assert h._persist_receipt.sha256 == committed_sha
    assert h._persist_dirty is True
    assert save_calls == []
    assert replace_calls == []


@pytest.mark.parametrize("stage", ["open", "write", "flush", "fsync", "close"])
def test_real_io_failure_reports_stage_and_preserves_old_bytes(tmp_path,
                                                               monkeypatch,
                                                               stage):
    module = _store_module()
    store_cls = getattr(module, "ServerStore", None)
    assert store_cls is not None
    path = tmp_path / "state.json"
    store = store_cls(str(path))
    encode_state = _api("encode_state")
    old = _field(encode_state({"version": 1}), "payload", "data")
    new = _field(encode_state({"version": 2}), "payload", "data")
    assert store.save_bytes(old).effect == "committed"
    old_bytes = path.read_bytes()
    real_open = builtins.open
    tmp_name = os.path.abspath(str(path) + ".tmp")

    class FailingFile:
        def __init__(self, inner):
            self.inner = inner

        def write(self, data):
            if stage == "write":
                raise OSError("injected write failure")
            return self.inner.write(data)

        def flush(self):
            if stage == "flush":
                raise OSError("injected flush failure")
            return self.inner.flush()

        def fileno(self):
            return self.inner.fileno()

        def close(self):
            if stage == "close":
                raise OSError("injected close failure")
            return self.inner.close()

    if stage == "open":
        def fail_open(name, mode="r", *args, **kwargs):
            if os.path.abspath(str(name)) == tmp_name and "wb" in mode:
                raise OSError("injected open failure")
            return real_open(name, mode, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", fail_open)
    elif stage in {"write", "flush", "close"}:
        def wrapped_open(name, mode="r", *args, **kwargs):
            inner = real_open(name, mode, *args, **kwargs)
            if os.path.abspath(str(name)) == tmp_name and "wb" in mode:
                return FailingFile(inner)
            return inner

        monkeypatch.setattr(builtins, "open", wrapped_open)
    else:
        monkeypatch.setattr(
            os, "fsync",
            lambda _fd: (_ for _ in ()).throw(OSError("injected fsync failure")),
        )
    result = store.save_bytes(new)
    assert result.effect == "not_committed"
    assert result.stage == stage
    assert result.error_code
    assert result.retryable is True
    assert path.read_bytes() == old_bytes


@pytest.mark.parametrize("write_result", [None, -1, "invalid", True, False, 10**9])
def test_invalid_write_results_fail_once_without_looping(tmp_path, monkeypatch,
                                                         write_result):
    module = _store_module()
    store_cls = getattr(module, "ServerStore", None)
    assert store_cls is not None
    path = tmp_path / "state.json"
    store = store_cls(str(path))
    encode_state = _api("encode_state")
    old = _field(encode_state({"version": 1}), "payload", "data")
    new = _field(encode_state({"version": 2}), "payload", "data")
    assert store.save_bytes(old).effect == "committed"
    old_bytes = path.read_bytes()
    real_open = builtins.open
    tmp_name = os.path.abspath(str(path) + ".tmp")
    calls = []

    class InvalidWriter:
        def __init__(self, inner):
            self.inner = inner

        def write(self, _data):
            calls.append(1)
            return write_result

        def flush(self):
            return self.inner.flush()

        def fileno(self):
            return self.inner.fileno()

        def close(self):
            return self.inner.close()

    def wrapped_open(name, mode="r", *args, **kwargs):
        inner = real_open(name, mode, *args, **kwargs)
        if os.path.abspath(str(name)) == tmp_name and "wb" in mode:
            return InvalidWriter(inner)
        return inner

    monkeypatch.setattr(builtins, "open", wrapped_open)
    result = store.save_bytes(new)
    assert result.effect == "not_committed"
    assert result.stage == "write"
    assert calls == [1]
    assert path.read_bytes() == old_bytes


def test_cleanup_error_never_masks_first_write_error(tmp_path, monkeypatch):
    module = _store_module()
    store_cls = getattr(module, "ServerStore", None)
    assert store_cls is not None
    path = tmp_path / "state.json"
    store = store_cls(str(path))
    encode_state = _api("encode_state")
    old = _field(encode_state({"version": 1}), "payload", "data")
    new = _field(encode_state({"version": 2}), "payload", "data")
    assert store.save_bytes(old).effect == "committed"
    real_open = builtins.open
    tmp_name = os.path.abspath(str(path) + ".tmp")

    class FailingWriter:
        def __init__(self, inner):
            self.inner = inner

        def write(self, _data):
            raise OSError("first write failure")

        def close(self):
            return self.inner.close()

        def flush(self):
            return self.inner.flush()

        def fileno(self):
            return self.inner.fileno()

    def wrapped_open(name, mode="r", *args, **kwargs):
        inner = real_open(name, mode, *args, **kwargs)
        if os.path.abspath(str(name)) == tmp_name and "wb" in mode:
            return FailingWriter(inner)
        return inner

    monkeypatch.setattr(builtins, "open", wrapped_open)
    monkeypatch.setattr(
        os, "remove",
        lambda _path: (_ for _ in ()).throw(RuntimeError("cleanup failure")),
    )
    result = store.save_bytes(new)
    assert result.effect == "not_committed"
    assert result.stage == "write"
    assert result.error_code == "write_failed"


def test_query_supplements_confirmation_after_ack_exception(tmp_path, monkeypatch):
    h, _predecessor, _candidate_state, _candidate = _retire_fixture(tmp_path)
    original_ack = h._ack_commit

    def fail_first_ack(*_args, **_kwargs):
        raise RuntimeError("receipt construction failed")

    monkeypatch.setattr(h, "_ack_commit", fail_first_ack)
    assert h._persist(force=True) is False
    disk = h.store.read_bytes_result()
    assert disk.status == "bytes"
    assert json.loads(disk.payload.decode("utf-8"))["retired"]["7"][
        "operation_id"] == "op-t1-victim"
    monkeypatch.setattr(h, "_ack_commit", original_ack)
    payload = h._admin_user_payload(7)["retirement"]
    assert payload["status"] == "confirmed"
    assert payload["content_sha256"] == disk.sha256
    assert payload["origin"] in {"written", "reconciled_current_json"}


def test_legacy_save_wrapper_cannot_hide_post_replace_success(tmp_path, monkeypatch):
    h, _predecessor, _candidate_state, _candidate = _retire_fixture(tmp_path)
    native_save = h.store.save

    def legacy_wrapper(state):
        assert native_save(state) is True
        raise OSError("legacy wrapper acknowledgement failed")

    monkeypatch.setattr(h.store, "save", legacy_wrapper)
    assert h._persist(force=True) is False
    disk = h.store.read_bytes_result()
    assert disk.status == "bytes"
    assert json.loads(disk.payload.decode("utf-8"))["retired"]["7"][
        "operation_id"] == "op-t1-victim"
    payload = h._admin_user_payload(7)["retirement"]
    assert payload["status"] == "confirmed"
    assert payload["content_sha256"] == disk.sha256


def test_ordinary_persist_only_triggers_and_writer_encodes_once(tmp_path,
                                                                monkeypatch):
    module = _store_module()
    h, _predecessor, _candidate_state, _candidate = _retire_fixture(tmp_path)
    encode_state = module.encode_state
    calls = []
    encoded = threading.Event()

    def counted_encode(state):
        calls.append(1)
        result = encode_state(state)
        encoded.set()
        return result

    monkeypatch.setattr(module, "encode_state", counted_encode)
    worker = None
    try:
        h._persist_interval = 3600.0
        h._persist_last = 10**20
        h._persist()
        assert calls == []
        h._persist_interval = 0.0
        h._persist_last = 0.0
        h._persist()
        worker = h._persist_worker_thread
        assert encoded.wait(5)
        assert calls == [1]
    finally:
        if worker is not None:
            h._persist_closing = True
            h._persist_wake.set()
            worker.join(5)
    assert worker is None or not worker.is_alive()


def test_request_after_io_before_ack_remains_dirty(tmp_path, monkeypatch):
    h, _predecessor, _candidate_state, _candidate = _retire_fixture(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    errors = []
    result = []
    original_ack = h._ack_commit

    def paused_ack(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original_ack(*args, **kwargs)

    monkeypatch.setattr(h, "_ack_commit", paused_ack)
    h._persist_closing = True

    def run_force():
        try:
            result.append(h._persist(force=True))
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run_force, name="cc02-t2-ack-window")
    thread.start()
    try:
        assert entered.wait(5)
        h.nick_to_uid["late"] = 999
        h._persist_request()
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert not errors
    assert result == [True]
    assert h._retire_ops[7]["status"] == "confirmed"
    assert h._persist_dirty is True
    assert h.store.load()["nick_to_uid"].get("late") is None


def test_same_uid_late_failure_does_not_downgrade_confirmed(tmp_path):
    module = _store_module()
    h, _predecessor, candidate_state, candidate = _retire_fixture(tmp_path)
    success_done = threading.Event()
    errors = []
    success_result = []

    def run_success():
        try:
            success_result.append(h._persist(force=True))
        except BaseException as exc:
            errors.append(exc)
        finally:
            success_done.set()

    success_thread = threading.Thread(target=run_success,
                                      name="cc02-t2-success")
    success_thread.start()
    assert success_done.wait(5)
    assert success_thread.is_alive() is False
    assert success_result == [True]
    encoded = module.encode_state(candidate_state)
    late_errors = []

    def run_late_failure():
        try:
            h._ack_commit(
                candidate_state,
                encoded,
                module.SaveResult("not_committed", "write", "late_failure",
                                  True, encoded.length, encoded.sha256),
                h._persist_request_seq,
            )
        except BaseException as exc:
            late_errors.append(exc)

    late_thread = threading.Thread(target=run_late_failure,
                                   name="cc02-t2-late-failure")
    late_thread.start()
    late_thread.join(5)
    assert not late_thread.is_alive()
    assert not errors
    assert not late_errors
    assert h._retire_ops[candidate["uid"]]["status"] == "confirmed"
    assert h._retirement_payload(candidate["uid"])["status"] == "confirmed"


def test_unknown_reconcile_covers_all_captured_operations_atomically(tmp_path,
                                                                     monkeypatch):
    h, _predecessor, _candidate_state, _candidate = _retire_fixture(tmp_path)
    record = {"nick": "victim-2", "retired_at": 3.0,
              "operation_id": "op-t1-victim-2"}
    with h._persist_writer_lock:
        assert h._recovery.accept_intent(8, record).effect == 'committed'
        with h.lock:
            h._apply_retirement_core_locked(8, record)
    h._retire_ops[8] = {
        "status": "pending", "operation_id": "op-t1-victim-2",
        "target_uid": 8, "target_nick": "victim-2",
        "persistence_phase": "snapshot", "identity_effect": "revoked",
    }
    real_replace = os.replace

    def replace_then_raise(source, target):
        real_replace(source, target)
        raise OSError("acknowledgement lost")

    monkeypatch.setattr(os, "replace", replace_then_raise)
    assert h._persist(force=True) is False
    assert len(h._persist_unresolved["candidates"]) == 2
    monkeypatch.setattr(os, "replace", real_replace)
    payload = h._admin_user_payload(7)["retirement"]
    assert payload["status"] == "confirmed"
    assert h._retire_ops[8]["status"] == "confirmed"
    assert h._persist_unresolved is None
    assert set(h._persist_receipt.operation_ids) == {
        "op-t1-victim", "op-t1-victim-2"}


def test_bound_save_bytes_returns_current_reconciled_typed_result(tmp_path,
                                                                  monkeypatch):
    h, _predecessor, _candidate_state, _candidate = _retire_fixture(tmp_path)
    real_replace = os.replace

    def replace_then_raise(source, target):
        real_replace(source, target)
        raise OSError("acknowledgement lost")

    monkeypatch.setattr(os, "replace", replace_then_raise)
    assert h._persist(force=True) is False
    actual = h.store.read_bytes_result()
    monkeypatch.setattr(os, "replace", real_replace)
    result = h.store.save_bytes(b"ignored-by-active-hub")
    assert result.effect == "committed"
    assert result.sha256 == actual.sha256
    assert h._retire_ops[7]["status"] == "confirmed"


def test_capture_op_metadata_is_selected_under_hub_lock(tmp_path, monkeypatch):
    h, _predecessor, _candidate_state, _candidate = _retire_fixture(tmp_path)
    selected = threading.Event()
    release = threading.Event()
    ownership = []
    errors = []
    result = []
    original_candidates = h._retire_candidates_for_state

    def paused_candidates(state):
        if not selected.is_set():
            ownership.append(h.lock._is_owned())
            selected.set()
            assert release.wait(5)
        return original_candidates(state)

    monkeypatch.setattr(h, "_retire_candidates_for_state", paused_candidates)

    def run_force():
        try:
            result.append(h._persist(force=True))
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run_force, name="cc02-capture-opmeta")
    thread.start()
    try:
        assert selected.wait(5)
        acquired = h.lock.acquire(blocking=False)
        if acquired:
            h.lock.release()
        assert acquired is False
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert not errors
    assert ownership == [True]
    assert result == [True]
    assert h._retire_ops[7]["status"] == "confirmed"
