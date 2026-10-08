"""Actual on-disk malformed evidence cannot become a reconciliation receipt."""
import json
from pathlib import Path

import pytest

from server_store import SaveResult
from server_recovery import StoreCoordinator
from test_retire_recovery_hub import fresh_hub, people, retire, stop_fixture


def corrupted(state, fault):
    value = json.loads(json.dumps(state))
    if fault == 'unknown_key':
        value['unexpected_authority'] = True
    elif fault == 'wrong_type':
        value['bus']['seq'] = 'not-an-integer'
    elif fault == 'store_id':
        value['_store']['store_id'] = '0' * 32
    else:
        value['_store']['format_version'] = 999
    return json.dumps(value, ensure_ascii=False).encode('utf-8')


@pytest.mark.parametrize('fault', ['unknown_key', 'wrong_type', 'store_id', 'format_version'])
@pytest.mark.parametrize('entry', ['unknown_query', 'failed_retry', 'commit_readback'])
def test_each_reconcile_entry_rejects_real_bad_schema_and_keeps_actual_bytes(tmp_path, monkeypatch, fault, entry):
    # Preserve typed IO diagnostics if an actual bootstrap failure recurs;
    # no retry/resume or alteration of the failed initialization is hidden.
    publications = []
    original_publish = StoreCoordinator._publish
    def recorded_publish(store, value, previous):
        result = original_publish(store, value, previous)
        publications.append({'file': Path(store._path).name, 'effect': result.effect,
                             'stage': result.stage, 'error_code': result.error_code,
                             'retryable': result.retryable})
        return result
    with monkeypatch.context() as bootstrap_patch:
        bootstrap_patch.setattr(StoreCoordinator, '_publish', staticmethod(recorded_publish))
        try:
            hub = fresh_hub(tmp_path)
        finally:
            (tmp_path / 'bootstrap-io.json').write_text(json.dumps(publications), encoding='utf-8')
    admin, frames, user, _ = people(hub)
    path = Path(hub.store._path)
    original_save = hub.store._save_encoded

    def first_save(encoded):
        if entry == 'commit_readback':
            result = original_save(encoded)
            assert result.effect == 'committed'
            path.write_bytes(corrupted(json.loads(encoded.payload), fault))
            return result
        if entry == 'unknown_query':
            # Leave actual unverified bytes before the handler's immediate
            # read-only reply reconciliation; a known predecessor would
            # correctly resolve an uncertain result back to failed.
            path.write_bytes(corrupted(json.loads(encoded.payload), fault))
        return SaveResult('not_committed' if entry == 'failed_retry' else 'uncertain',
                          'write', 'synthetic-initial-failure', entry == 'failed_retry',
                          encoded.length, encoded.sha256)

    monkeypatch.setattr(hub.store, '_save_encoded', first_save)
    try:
        retire(hub, admin, user.uid)
        receipt = hub._retirement_payload(user.uid)
        assert receipt['status'] == ('failed' if entry == 'failed_retry' else 'unknown')
        operation = receipt['operation_id']
        if entry != 'commit_readback':
            path.write_bytes(corrupted(hub._snapshot_state(), fault))
        bad_bytes = path.read_bytes()
        control_bytes = path.with_name('control.json').read_bytes()
        monkeypatch.setattr(hub.store, '_save_encoded', lambda *_: pytest.fail('unverified authority cannot write'))
        if entry == 'failed_retry':
            retire(hub, admin, user.uid, op=operation, request_id='explicit-retry')
        hub._on_admin_user_get(admin, {'uid': user.uid, 'operation_id': operation,
                                        'request_id': 'readonly-query'})
        assert hub._persist(force=True) is False
        assert hub._persist_flush() is False
        assert hub.store.save({}) is False
        assert hub.store.save_bytes(b'{}').effect != 'committed'
        result = hub._retirement_payload(user.uid)
        assert result['status'] == 'unknown' and result['operation_id'] == operation
        assert result['origin'] is None and result['content_sha256'] is None
        assert not result['retryable']
        assert path.read_bytes() == bad_bytes
        assert path.with_name('control.json').read_bytes() == control_bytes
        assert user.uid in hub.retired and user.uid not in hub.known
    finally:
        stop_fixture(hub)
