"""Real Win32 sharing errors on synthetic Store files; no ACL changes."""
import ctypes
import os
from pathlib import Path

import auth

from server import Hub
from server_recovery import strict_json
from test_account_credential_transactions import attempt, update
from test_retire_recovery_gate_io import hold_metadata
from test_retire_recovery_hub import config_for, fresh_hub, stop_fixture


def test_real_replace_refusal_preserves_old_password_and_replay_does_not_retry(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    handle = None
    try:
        ok, user, _ = attempt(hub, '合成真实拒写', 'synthetic-old', claim=True)
        assert ok and hub._persist(force=True)
        path = tmp_path / 'store/state.json'
        before = path.read_bytes()
        old_hash = hub.known[user.uid]['pwd']
        api, handle = hold_metadata(path)  # Shares reads/writes, refuses replacement/delete.
        original = os.replace
        attempts, codes = [], []

        def observed(source, target):
            try:
                return original(source, target)
            except OSError as exc:
                if Path(target) == path:
                    attempts.append(Path(source))
                    codes.append(exc.winerror)
                raise

        monkeypatch.setattr(os, 'replace', observed)
        result = update(hub, user, 'synthetic-old', 'synthetic-new', 'denied')
        assert result['status'] == 'failed' and result['reason'] == 'credential_write_failed'
        assert result['retryable'] and 'persisted' not in result
        assert codes and set(codes) <= {5, 32, 33}
        assert len(attempts) >= 2 and len(set(attempts)) == 1
        assert path.read_bytes() == before and hub.known[user.uid]['pwd'] == old_hash
        assert hub._recovery.phase == 'READY'
        api.CloseHandle(handle)
        handle = None
        calls_before = len(attempts)
        assert update(hub, user, 'synthetic-old', 'synthetic-new', 'denied') == result
        assert len(attempts) == calls_before and path.read_bytes() == before
        confirmed = update(hub, user, 'synthetic-old', 'synthetic-new', 'explicit_new')
        assert confirmed['status'] == 'confirmed'
        assert auth.verify('synthetic-new', strict_json(path.read_bytes())['known'][str(user.uid)]['pwd'])
        assert not list(path.parent.glob('state.json.tmp-*'))
    finally:
        if handle is not None:
            api.CloseHandle(handle)
        stop_fixture(hub)


def test_real_read_refusal_reports_unknown_then_restart_uses_actual_old_state(tmp_path):
    hub = fresh_hub(tmp_path)
    handle = None
    try:
        ok, user, _ = attempt(hub, '合成真实拒读', 'synthetic-old', claim=True)
        assert ok and hub._persist(force=True)
        path = tmp_path / 'store/state.json'
        before, old_hash = path.read_bytes(), hub.known[user.uid]['pwd']
        api, setup_handle = hold_metadata(path)
        api.CloseHandle(setup_handle)
        handle = api.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
        assert handle != ctypes.c_void_p(-1).value
        result = update(hub, user, 'synthetic-old', 'synthetic-new', 'read_denied')
        assert result['status'] == 'unknown' and 'persisted' not in result
        assert not result['retryable'] and hub._recovery.phase == 'FAILED'
        assert hub.known[user.uid]['pwd'] == old_hash
        assert hub._persist(force=True) is False and hub._persist_flush() is False
        api.CloseHandle(handle)
        handle = None
        assert path.read_bytes() == before
        uid, epoch = user.uid, hub._server_epoch
    finally:
        if handle is not None:
            api.CloseHandle(handle)
        stop_fixture(hub)
    reopened = Hub(cfg=config_for(tmp_path), store_dir=str(tmp_path / 'store'))
    try:
        ok, current, _ = attempt(reopened, '合成真实拒读', 'synthetic-old')
        assert ok and current.uid == uid
        response = reopened.credential_query(current, {
            'credential_v': 1, 'request_id': 'lookup', 'original_request_id': 'read_denied',
            'operation_id': result['operation_id'], 'operation_epoch': epoch})
        assert response['status'] == 'unknown' and response['reason'] == 'operation_unavailable'
    finally:
        stop_fixture(reopened)
