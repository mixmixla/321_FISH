"""Owned Store publication under real Windows sharing refusal."""
import copy
import ctypes
import json
import os
from pathlib import Path
import threading
import time

import pytest

from server_recovery import StoreCoordinator, StoreError, StoreOwner
from server_store import ServerStore
from test_retire_recovery_gate_io import hold_metadata
from test_retire_recovery_hub import fresh_hub, people, retire


def coordinator(root):
    StoreCoordinator.initialize_new(root)
    owner = StoreCoordinator(root)
    pair = owner.open()
    owner.mark_ready(pair.state)
    return owner, pair


def publication(owner, pair, kind):
    if kind == 'state':
        value = copy.deepcopy(pair.state)
        value['nick_to_uid']['synthetic'] = 1
        value['uid_seq'] = 2
        return owner.state_store, value, pair.state_bytes
    value = copy.deepcopy(pair.control)
    value['intents']['1'] = {'nick': 'synthetic', 'retired_at': 1.0,
                             'operation_id': 'synthetic-publication'}
    return owner.control_store, value, pair.control_bytes


@pytest.mark.parametrize('kind', ['state', 'control'])
def test_real_reader_release_completes_same_owned_publication(tmp_path, monkeypatch, kind):
    owner, pair = coordinator(tmp_path / 'store')
    store, value, previous = publication(owner, pair, kind)
    path = Path(store._path)
    api, handle = hold_metadata(path)
    denied, paths, results, errors = threading.Event(), [], [], []
    original = os.replace
    def replace(source, target):
        if Path(target) == path:
            paths.append(Path(source))
        try:
            return original(source, target)
        except OSError as exc:
            assert exc.winerror in (5, 32, 33)
            denied.set()
            raise
    monkeypatch.setattr(os, 'replace', replace)
    def publish():
        try:
            with owner.writer:
                results.append(owner._publish(store, value, previous))
        except BaseException as exc:
            errors.append(exc)
    writer = threading.Thread(target=publish)
    try:
        writer.start()
        assert denied.wait(2)
        assert path.read_bytes() == previous
        api.CloseHandle(handle)
        handle = None
        writer.join(2)
        assert not writer.is_alive() and not errors, errors
        assert len(results) == 1 and results[0].effect == 'committed', results
        assert len(paths) >= 2 and len(set(paths)) == 1
        assert path.read_bytes() != previous
        assert not list(path.parent.glob(path.name + '.tmp-*'))
    finally:
        if handle is not None:
            api.CloseHandle(handle)
        writer.join(2)
        owner.close()


@pytest.mark.parametrize('kind', ['state', 'control'])
def test_permanent_reader_refusal_is_bounded_and_reports_actual_predecessor(tmp_path, monkeypatch, kind):
    owner, pair = coordinator(tmp_path / 'store')
    store, value, previous = publication(owner, pair, kind)
    path = Path(store._path)
    api, handle = hold_metadata(path)
    original, attempts = os.replace, []
    def replace(source, target):
        attempts.append(Path(source))
        return original(source, target)
    monkeypatch.setattr(os, 'replace', replace)
    started = time.monotonic()
    try:
        with owner.writer:
            result = owner._publish(store, value, previous)
        assert time.monotonic() - started < 2
        assert result.effect == 'not_committed' and result.retryable
        assert result.stage == 'replace' and result.error_code == 'replace_failed'
        assert path.read_bytes() == previous
        assert len(attempts) >= 2 and len(set(attempts)) == 1
        assert not list(path.parent.glob(path.name + '.tmp-*'))
    finally:
        api.CloseHandle(handle)
        owner.close()


@pytest.mark.parametrize('kind', ['state', 'control'])
def test_after_replace_then_raise_never_reissues_and_actual_readback_confirms(tmp_path, monkeypatch, kind):
    owner, pair = coordinator(tmp_path / 'store')
    store, value, previous = publication(owner, pair, kind)
    original, completed = os.replace, []
    def ambiguous(source, target):
        assert not completed, 'never issue another replace after temp disappears'
        original(source, target)
        completed.append(Path(source))
        raise ctypes.WinError(5)
    monkeypatch.setattr(os, 'replace', ambiguous)
    try:
        with owner.writer:
            result = owner._publish(store, value, previous)
        assert len(completed) == 1 and not completed[0].exists()
        assert result.effect == 'committed' and result.stage == 'readback'
        assert Path(store._path).read_bytes() != previous
    finally:
        owner.close()


@pytest.mark.parametrize('fault', ['missing', 'different_file', 'changed_content', 'other_error'])
def test_unproven_temp_or_nonsharing_error_never_retries_or_deletes_foreign_file(tmp_path, monkeypatch, fault):
    owner, pair = coordinator(tmp_path / 'store')
    store, value, previous = publication(owner, pair, 'state')
    attempts, foreign = [], []
    def rejected(source, target):
        source = Path(source)
        attempts.append(source)
        if fault == 'missing':
            source.unlink()
        elif fault == 'different_file':
            original_bytes = source.read_bytes()
            source.rename(source.with_suffix('.preserved'))
            source.write_bytes(original_bytes)
            foreign.append(source)
        elif fault == 'changed_content':
            source.write_bytes(b'unrelated bytes')
        raise ctypes.WinError(112 if fault == 'other_error' else 5)
    monkeypatch.setattr(os, 'replace', rejected)
    try:
        with owner.writer:
            result = owner._publish(store, value, previous)
        assert len(attempts) == 1
        assert result.effect == 'not_committed' and result.retryable
        assert Path(store._path).read_bytes() == previous
        assert all(path.exists() for path in foreign)
    finally:
        owner.close()


def test_standalone_store_does_not_gain_implicit_retry(tmp_path, monkeypatch):
    store = ServerStore(str(tmp_path / 'legacy.json'))
    assert store.save_bytes(b'old').effect == 'committed'
    calls = []
    def denied(*_):
        calls.append(1)
        raise ctypes.WinError(5)
    monkeypatch.setattr(os, 'replace', denied)
    result = store.save_bytes(b'new')
    assert result.effect == 'uncertain' and calls == [1]
    assert Path(store._path).read_bytes() == b'old'


def test_final_replace_does_not_start_after_deadline_even_if_temp_io_started(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    hub._service_started = True
    before = Path(hub.store._path).read_bytes()
    real_fsync, real_replace = os.fsync, os.replace
    entered, release = threading.Event(), threading.Event()
    replacements = []
    def delayed_fsync(fd):
        real_fsync(fd)
        entered.set()
        assert release.wait(3)
    def observed_replace(source, target):
        replacements.append(Path(target))
        return real_replace(source, target)
    monkeypatch.setattr(os, 'fsync', delayed_fsync)
    monkeypatch.setattr(os, 'replace', observed_replace)
    try:
        assert hub.shutdown(normal=True, timeout=0.1) is False
        assert entered.is_set() and hub._final_thread.is_alive()
        assert hub._recovery.owner.held
        with pytest.raises(StoreError, match='store_in_use'):
            StoreOwner(Path(hub.store._path).parent / '.owner.lock').acquire()
        release.set()
        hub._final_thread.join(3)
        assert not hub._final_thread.is_alive() and not replacements
        result = hub._persist_last_result
        assert result.effect == 'not_committed' and result.error_code == 'replace_deadline'
        assert Path(hub.store._path).read_bytes() == before
        assert hub.shutdown(normal=False) is False
        assert not hub._recovery.owner.held
    finally:
        release.set()
        if hub._final_thread:
            hub._final_thread.join(3)
        hub.shutdown(normal=False)


def test_final_refusal_cannot_retry_after_deadline_and_keeps_owner_while_inflight(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    hub._service_started = True
    path = Path(hub.store._path)
    before = path.read_bytes()
    api, handle = hold_metadata(path)
    original, attempts = os.replace, []
    denied, release = threading.Event(), threading.Event()
    def blocked_native(source, target):
        attempts.append(time.monotonic())
        try:
            return original(source, target)
        except OSError:
            denied.set()
            assert release.wait(3)
            raise
    monkeypatch.setattr(os, 'replace', blocked_native)
    try:
        assert hub.shutdown(normal=True, timeout=0.1) is False
        assert denied.is_set() and hub._recovery.owner.held
        assert hub._final_thread.is_alive() and len(attempts) == 1
        release.set()
        hub._final_thread.join(3)
        assert not hub._final_thread.is_alive() and len(attempts) == 1
        assert hub._persist_last_result.effect == 'uncertain'
        assert path.read_bytes() == before
        assert hub.shutdown(normal=False) is False
        assert not hub._recovery.owner.held
    finally:
        release.set()
        api.CloseHandle(handle)
        if hub._final_thread:
            hub._final_thread.join(3)
        hub.shutdown(normal=False)


@pytest.mark.parametrize('mode', ['new', 'adopt', 'resume'])
def test_bootstrap_final_control_survives_real_short_reader_refusal(tmp_path, monkeypatch, mode):
    root = tmp_path / 'store'
    original = os.replace
    if mode == 'adopt':
        root.mkdir()
        (root / 'state.json').write_text(json.dumps({'uid_seq': 2, 'nick_to_uid': {'legacy': 1}}), encoding='utf-8')
    elif mode == 'resume':
        def interrupt_state(source, target):
            if Path(target) == root / 'state.json':
                raise OSError('synthetic pre-state bootstrap interruption')
            return original(source, target)
        with monkeypatch.context() as patch:
            patch.setattr(os, 'replace', interrupt_state)
            with pytest.raises(StoreError, match='bootstrap_write_failed'):
                StoreCoordinator.initialize_new(root)
        assert json.loads((root / 'control.json').read_bytes())['phase'] == 'bootstrap'
    held, denied, control_paths, errors = [], threading.Event(), [], []
    def release_reader():
        try:
            assert denied.wait(3)
        except BaseException as exc:
            errors.append(exc)
        finally:
            if held:
                held[0][0].CloseHandle(held[0][1])
    reader = threading.Thread(target=release_reader)
    def replace(source, target):
        target = Path(target)
        if target == root / 'control.json' and target.exists():
            control_paths.append(Path(source))
            if not held:
                held.append(hold_metadata(target))
        try:
            return original(source, target)
        except OSError as exc:
            if target == root / 'control.json':
                assert exc.winerror in (5, 32, 33)
                denied.set()
            raise
    monkeypatch.setattr(os, 'replace', replace)
    reader.start()
    try:
        action = {'new': StoreCoordinator.initialize_new, 'adopt': StoreCoordinator.adopt_legacy,
                  'resume': StoreCoordinator.resume_bootstrap}[mode]
        action(root)
        reader.join(3)
        assert not reader.is_alive() and not errors, errors
        assert denied.is_set() and len(control_paths) >= 2 and len(set(control_paths)) == 1
        owner = StoreCoordinator(root)
        try:
            pair = owner.open()
            assert pair.control['phase'] == 'ready'
            if mode == 'adopt':
                assert pair.state['nick_to_uid']['legacy'] == 1
        finally:
            owner.close()
    finally:
        denied.set()
        reader.join(3)


def test_live_retirement_transient_snapshot_refusal_keeps_one_intent_t0_and_operation(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    admin, _, user, _ = people(hub)
    path = Path(hub.store._path)
    previous = path.read_bytes()
    api, handle = hold_metadata(path)
    original, intent, apply = os.replace, hub._recovery.accept_intent, hub._apply_retirement_core_locked
    denied, paths, intents, t0s, errors = threading.Event(), [], [], [], []
    def replace(source, target):
        if Path(target) == path:
            paths.append(Path(source))
        try:
            return original(source, target)
        except OSError as exc:
            assert exc.winerror in (5, 32, 33)
            denied.set()
            raise
    def accepted(uid, record):
        intents.append(record['operation_id'])
        return intent(uid, record)
    def t0(uid, record):
        t0s.append(record['operation_id'])
        return apply(uid, record)
    monkeypatch.setattr(os, 'replace', replace)
    monkeypatch.setattr(hub._recovery, 'accept_intent', accepted)
    monkeypatch.setattr(hub, '_apply_retirement_core_locked', t0)
    def delete():
        try:
            retire(hub, admin, user.uid)
        except BaseException as exc:
            errors.append(exc)
    worker = threading.Thread(target=delete)
    try:
        worker.start()
        assert denied.wait(2)
        assert path.read_bytes() == previous
        with hub.lock:
            assert user.uid in hub.retired
        assert hub._recovery.owner.held
        api.CloseHandle(handle)
        handle = None
        worker.join(3)
        assert not worker.is_alive() and not errors, errors
        receipt = hub._retirement_payload(user.uid)
        assert receipt['status'] == 'confirmed' and receipt['origin'] == 'written'
        assert intents == t0s == [receipt['operation_id']]
        assert len(paths) >= 2 and len(set(paths)) == 1
        retire(hub, admin, user.uid, op=receipt['operation_id'])
        assert intents == t0s == [receipt['operation_id']]
        assert hub._retirement_payload(user.uid)['status'] == 'confirmed'
    finally:
        if handle is not None:
            api.CloseHandle(handle)
        worker.join(3)
        hub.shutdown(normal=False)
