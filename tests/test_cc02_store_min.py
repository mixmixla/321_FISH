# -*- coding: utf-8 -*-
"""CC-02A-RETIRE-CORE: minimal truthful ServerStore/Hub commit semantics."""
import json
import os
import secrets
import threading
import time
import builtins
from dataclasses import replace

import pytest

import bots
from config import CFG
from server import Hub
from server_store import ServerStore


def _cfg(tmp_path, password=None):
    return replace(CFG, admin_nick="L57", admin_pwd=password or secrets.token_urlsafe(24),
                   audit_dir=str(tmp_path / "audit"),
                   web_files_dir=str(tmp_path / "web"), persist_interval=0.0)


def _hub(tmp_path, store=None):
    return Hub(cfg=_cfg(tmp_path), audit_dir=str(tmp_path / "audit"),
               store_dir=str(store or (tmp_path / "store")))


def test_server_store_save_reports_success_and_failures(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    store = ServerStore(str(path))
    assert store.save({"a": 1}) is True
    assert store.load() == {"a": 1}

    def bad_replace(_src, _dst):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", bad_replace)
    assert store.save({"a": 2}) is False
    assert store.load() == {"a": 1}


@pytest.mark.parametrize("stage", ["encode", "open", "write", "flush",
                                    "fsync", "replace"])
def test_server_store_real_json_failure_keeps_old_authority(tmp_path, monkeypatch, stage):
    path = tmp_path / "state.json"
    store = ServerStore(str(path))
    assert store.save({"version": 1}) is True
    old_bytes = path.read_bytes()
    real_open = builtins.open
    tmp_name = os.path.abspath(str(path) + ".tmp")

    class FailingFile:
        def __init__(self, inner):
            self.inner = inner

        def __enter__(self):
            self.inner.__enter__()
            return self

        def __exit__(self, *args):
            return self.inner.__exit__(*args)

        def write(self, data):
            if stage == "write":
                raise OSError("write failed")
            return self.inner.write(data)

        def flush(self):
            if stage == "flush":
                raise OSError("flush failed")
            return self.inner.flush()

        def fileno(self):
            return self.inner.fileno()

    if stage == "open":
        def fail_open(name, mode="r", *args, **kwargs):
            if os.path.abspath(str(name)) == tmp_name and "w" in mode:
                raise OSError("open failed")
            return real_open(name, mode, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", fail_open)
    elif stage in {"write", "flush"}:
        def wrapped_open(name, mode="r", *args, **kwargs):
            fh = real_open(name, mode, *args, **kwargs)
            return FailingFile(fh) if os.path.abspath(str(name)) == tmp_name else fh

        monkeypatch.setattr(builtins, "open", wrapped_open)
    elif stage == "fsync":
        monkeypatch.setattr(os, "fsync", lambda _fd: (_ for _ in ()).throw(
            OSError("fsync failed")))
    elif stage == "replace":
        monkeypatch.setattr(os, "replace", lambda _src, _dst: (_ for _ in ()).throw(
            OSError("replace failed")))

    payload = {"bad": object()} if stage == "encode" else {"version": 2}
    assert store.save(payload) is False
    monkeypatch.undo()
    assert path.read_bytes() == old_bytes
    assert store.load() == {"version": 1}


def test_failed_force_save_does_not_advance_fingerprint_or_claim_confirmation(tmp_path):
    h = _hub(tmp_path)
    h._persist_flush()
    old_fp = h._persist_fp
    h.nick_to_uid["changed"] = 999

    h.store.save = lambda _state: False
    assert h._persist(force=True) is False
    assert h._persist_fp == old_fp
    assert h._persist_dirty is True


def test_actual_writer_recaptures_after_waiting_and_never_writes_stale_snapshot(tmp_path):
    h = _hub(tmp_path)
    h._persist_flush()
    stale = h._snapshot_state()
    stale_fp = h._state_fingerprint(stale)
    h.nick_to_uid["newer"] = 321

    # The writer receives an old trigger, but must capture current live state
    # only after obtaining the writer ordering lock.
    assert h._persist_sync(stale, stale_fp) is True
    saved = h.store.load()
    assert saved["nick_to_uid"]["newer"] == 321


def test_real_json_success_restarts_with_retirement_fence(tmp_path):
    store = tmp_path / "store"
    h1 = _hub(tmp_path, store)
    h1.nick_to_uid["old"] = 7
    h1.retired[7] = {"nick": "old", "retired_at": 1.0, "operation_id": "op-7"}
    h1._persist_flush()
    h2 = _hub(tmp_path / "restart", store)
    assert h2.retired[7]["operation_id"] == "op-7"
    assert h2.nick_to_uid["old"] == 7


def test_retirement_state_is_only_minimal_top_level_json(tmp_path):
    h = _hub(tmp_path)
    h.nick_to_uid["old"] = 7
    h.retired[7] = {"nick": "old", "retired_at": 1.0, "operation_id": "op-7"}
    state = h._snapshot_state()
    assert set(state["retired"]["7"]) == {"nick", "retired_at", "operation_id"}
    assert "pwd" not in state["retired"]["7"]


def _hub_from_state(tmp_path, state):
    cfg = _cfg(tmp_path)
    store_dir = tmp_path / "store"
    store = ServerStore(str(store_dir / "state.json"))
    assert store.save(state)
    return Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"),
               store_dir=str(store_dir))


def test_legacy_json_without_retired_does_not_infer_tombstone(tmp_path):
    h = _hub_from_state(tmp_path, {
        "uid_seq": 2,
        "nick_to_uid": {"legacy": 1},
        "known": {"1": {"nick": "legacy"}},
    })
    assert h.retired == {}
    assert not h._retired_schema_invalid
    from server import Session
    sess = Session(0, "legacy", "tcp", "127.0.0.1", lambda *_: None)
    assert h._on_hello(sess, {"t": "hello", "nick": "legacy"}) is True
    assert sess.uid == 1


def test_valid_retired_uid_is_skipped_by_new_allocation(tmp_path):
    h = _hub_from_state(tmp_path, {
        "uid_seq": 2,
        "nick_to_uid": {"old": 2},
        "known": {},
        "retired": {"2": {"nick": "old", "retired_at": 1.0,
                            "operation_id": "op-2"}},
    })
    from server import Session
    sess = Session(0, "fresh", "tcp", "127.0.0.1", lambda *_: None)
    assert h._on_hello(sess, {"t": "hello", "nick": "fresh"}) is True
    assert sess.uid == 3
    assert h.nick_to_uid["old"] == 2


def test_retired_nick_may_match_bot_name_but_bot_uid_stays_active(tmp_path):
    bot_nick = bots.BOTS[0].nick
    h = _hub_from_state(tmp_path, {
        "uid_seq": 2,
        "nick_to_uid": {bot_nick: 2},
        "known": {},
        "retired": {"2": {"nick": bot_nick, "retired_at": 1.0,
                            "operation_id": "op-bot-name"}},
    })
    assert h.retired[2]["nick"] == bot_nick
    assert bots.BOTS[0].uid in h.known
    assert bots.BOTS[0].uid not in h.retired


@pytest.mark.parametrize("state", [
    {"uid_seq": 3, "nick_to_uid": {"old": 2},
     "known": {"2": {"nick": "old"}},
     "retired": {"2": {"nick": "old", "retired_at": 1.0,
                         "operation_id": "op-2"}}},
    {"uid_seq": 3, "nick_to_uid": {"old": 3}, "known": {},
     "retired": {"2": {"nick": "old", "retired_at": 1.0,
                         "operation_id": "op-2"}}},
])
def test_invalid_retired_json_fails_closed_without_authorizing_new_uid(tmp_path, state):
    h = _hub_from_state(tmp_path, state)
    assert h._retired_schema_invalid
    from server import Session
    sess = Session(0, "fresh", "tcp", "127.0.0.1", lambda *_: None)
    assert h._on_hello(sess, {"t": "hello", "nick": "fresh"}) is False


def test_new_request_during_blocked_actual_writer_is_not_cleared(tmp_path):
    h = _hub(tmp_path)
    h._persist_flush()
    h._persist_interval = 3600.0
    original_save = h.store.save
    started = threading.Event()
    release = threading.Event()
    followup_started = threading.Event()
    followup_release = threading.Event()
    calls = [0]

    def blocked_save(state):
        calls[0] += 1
        if calls[0] == 1:
            started.set()
            assert release.wait(5)
        else:
            followup_started.set()
            assert followup_release.wait(5)
        return original_save(state)

    h.store.save = blocked_save
    done = []
    worker = threading.Thread(target=lambda: done.append(h._persist(force=True)))
    worker.start()
    assert started.wait(5)
    h.nick_to_uid["during-io"] = 4321
    h._persist_last = time.time()
    h._persist()
    assert h._persist_dirty or h._persist_pending
    assert "during-io" not in h.store.load().get("nick_to_uid", {})
    release.set()
    worker.join(5)
    assert not worker.is_alive() and done == [True]
    assert followup_started.wait(5)
    assert h._persist_dirty or h._persist_pending
    assert "during-io" not in h.store.load().get("nick_to_uid", {})
    followup_release.set()
    if h._persist_worker_thread is not None:
        h._persist_worker_thread.join(5)

    h._persist_flush()
    assert h.store.load()["nick_to_uid"]["during-io"] == 4321


def test_request_between_snapshot_and_fingerprint_stays_dirty(tmp_path, monkeypatch):
    h = _hub(tmp_path)
    h._persist_flush()
    original_fp = h._state_fingerprint
    started = threading.Event()
    release = threading.Event()
    writer_started = threading.Event()
    writer_release = threading.Event()
    calls = [0]

    def paused_fp(state):
        calls[0] += 1
        if calls[0] == 1:
            started.set()
            assert release.wait(5)
        return original_fp(state)

    monkeypatch.setattr(h, "_state_fingerprint", paused_fp)
    original_save = h.store.save

    def blocked_followup_save(state):
        writer_started.set()
        assert writer_release.wait(5)
        return original_save(state)

    h.store.save = blocked_followup_save
    h._persist_last -= h._persist_interval + 1
    thread = threading.Thread(target=h._persist)
    thread.start()
    assert started.wait(5)
    h.nick_to_uid["between-capture-and-fp"] = 5432
    h._persist_last = time.time()
    h._persist()
    assert h._persist_dirty or h._persist_pending
    assert "between-capture-and-fp" not in h.store.load().get("nick_to_uid", {})
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    assert writer_started.wait(5)
    assert h._persist_dirty or h._persist_pending
    assert "between-capture-and-fp" not in h.store.load().get("nick_to_uid", {})
    writer_release.set()
    if h._persist_worker_thread is not None:
        h._persist_worker_thread.join(5)
    h._persist_flush()
    assert h.store.load()["nick_to_uid"]["between-capture-and-fp"] == 5432


@pytest.mark.parametrize("force_method", ["force", "flush"])
def test_old_worker_candidate_cannot_overwrite_force_retire_json(tmp_path, force_method):
    h = _hub(tmp_path)
    h._persist_flush()
    original_save = h.store.save
    old_started = threading.Event()
    release_old = threading.Event()
    force_called = threading.Event()
    writes = []

    def ordered_save(state):
        writes.append(json.loads(json.dumps(state, ensure_ascii=False)))
        if len(writes) == 1:
            old_started.set()
            assert release_old.wait(5)
        return original_save(state)

    h.store.save = ordered_save
    h.nick_to_uid["worker-old"] = 123
    h._persist()
    assert old_started.wait(5)
    h.nick_to_uid["retired-owner"] = 456
    h.retired[456] = {"nick": "retired-owner", "retired_at": 1.0,
                      "operation_id": "op-456"}

    result = []

    def force_writer():
        force_called.set()
        result.append(h._persist(force=True) if force_method == "force"
                       else h._persist_flush())

    thread = threading.Thread(target=force_writer)
    thread.start()
    assert force_called.wait(5)
    release_old.set()
    thread.join(5)
    assert not thread.is_alive() and result == [True]
    assert len(writes) >= 2
    assert writes[0]["retired"].get("456") is None
    assert writes[0]["nick_to_uid"].get("retired-owner") is None
    assert writes[-1]["retired"]["456"]["operation_id"] == "op-456"
    assert h.store.load()["retired"]["456"]["operation_id"] == "op-456"


def test_old_normal_snapshot_queues_after_force_retire_without_overwrite(tmp_path,
                                                                          monkeypatch):
    h = _hub(tmp_path)
    h._persist_flush()
    h._persist_interval = 0.0
    original_fp = h._state_fingerprint
    old_captured = threading.Event()
    release_old = threading.Event()
    fp_calls = [0]

    def pause_old_fp(state):
        fp_calls[0] += 1
        if fp_calls[0] == 1:
            old_captured.set()
            assert release_old.wait(5)
        return original_fp(state)

    monkeypatch.setattr(h, "_state_fingerprint", pause_old_fp)
    h.nick_to_uid["old-normal"] = 123
    old_thread = threading.Thread(target=h._persist)
    old_thread.start()
    assert old_captured.wait(5)

    h.nick_to_uid["confirmed-retired"] = 456
    h.retired[456] = {"nick": "confirmed-retired", "retired_at": 1.0,
                      "operation_id": "op-confirmed"}
    force_result = []
    force_thread = threading.Thread(target=lambda: force_result.append(
        h._persist(force=True)))
    force_thread.start()
    force_thread.join(5)
    assert not force_thread.is_alive() and force_result == [True]
    confirmed = h.store.load()
    assert confirmed["retired"]["456"]["operation_id"] == "op-confirmed"
    assert confirmed["nick_to_uid"]["confirmed-retired"] == 456

    # The old normal thread is released only after the force save has completed;
    # its late queue trigger must cause a fresh capture, never an old overwrite.
    release_old.set()
    old_thread.join(5)
    assert not old_thread.is_alive()
    if h._persist_worker_thread is not None:
        h._persist_worker_thread.join(5)
    final_state = h.store.load()
    assert final_state["retired"]["456"]["operation_id"] == "op-confirmed"
    assert final_state["nick_to_uid"]["confirmed-retired"] == 456
    assert h._persist_fp == Hub._state_fingerprint(final_state)
