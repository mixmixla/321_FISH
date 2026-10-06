"""Candidate readback proof and ordinary-state handoff on real synthetic JSON."""
import auth
import pytest

from server_recovery import strict_json
from server_store import SaveResult
from test_retire_recovery_hub import fresh_hub, login, stop_fixture


def setup_candidate(path):
    hub = fresh_hub(path)
    user, _ = login(hub, '合成凭据提交')
    assert hub._persist(force=True)
    candidate = hub._snapshot_state()
    digest = auth.make('synthetic-candidate')
    candidate['known'][user.uid]['pwd'] = digest
    return hub, user, candidate, digest


def test_candidate_seam_requires_the_exact_credential_lease(tmp_path):
    hub, _, candidate, _ = setup_candidate(tmp_path)
    before = (tmp_path / 'store/state.json').read_bytes()
    try:
        assert hub._commit_credential_candidate(candidate, None).effect == 'not_committed'
        with hub._writer_scope() as ordinary:
            assert hub._commit_credential_candidate(candidate, ordinary).effect == 'not_committed'
        assert (tmp_path / 'store/state.json').read_bytes() == before
    finally:
        stop_fixture(hub)


def test_confirmed_candidate_does_not_recapture_or_publish_live_password(tmp_path):
    hub, user, candidate, digest = setup_candidate(tmp_path)
    old_fp = hub._persist_fp
    try:
        with hub._writer_scope(kind='credential') as lease:
            proof = hub._commit_credential_candidate(candidate, lease)
            assert proof.effect == 'committed'
            assert not hub.known[user.uid].get('pwd')
            assert hub._persist_fp == old_fp
            actual = strict_json((tmp_path / 'store/state.json').read_bytes())
            assert actual['known'][str(user.uid)]['pwd'] == digest
        assert hub._recovery.phase == 'READY'
    finally:
        stop_fixture(hub)


def test_failed_publish_is_failed_only_when_predecessor_is_read_back(tmp_path, monkeypatch):
    hub, user, candidate, _ = setup_candidate(tmp_path)
    before = (tmp_path / 'store/state.json').read_bytes()
    old_fp = hub._persist_fp
    monkeypatch.setattr(hub, '_store_commit', lambda _: SaveResult('not_committed', 'injected', 'write_failed', True))
    try:
        with hub._writer_scope(kind='credential') as lease:
            proof = hub._commit_credential_candidate(candidate, lease)
        assert proof.effect == 'not_committed' and proof.retryable
        assert proof.error_code == 'credential_write_failed'
        assert (tmp_path / 'store/state.json').read_bytes() == before
        assert hub._persist_fp == old_fp and not hub.known[user.uid].get('pwd')
        assert hub._recovery.phase == 'READY'
    finally:
        stop_fixture(hub)


def test_exception_after_real_replace_can_be_confirmed_without_second_publish(tmp_path, monkeypatch):
    hub, user, candidate, digest = setup_candidate(tmp_path)
    original = hub._store_commit
    writes = []

    def replace_then_raise(encoded):
        writes.append(encoded.sha256)
        assert original(encoded).effect == 'committed'
        raise OSError('synthetic post-replace exception')

    monkeypatch.setattr(hub, '_store_commit', replace_then_raise)
    try:
        with hub._writer_scope(kind='credential') as lease:
            proof = hub._commit_credential_candidate(candidate, lease)
        assert proof.effect == 'committed' and len(writes) == 1
        assert strict_json((tmp_path / 'store/state.json').read_bytes())['known'][str(user.uid)]['pwd'] == digest
        assert not hub.known[user.uid].get('pwd')
    finally:
        stop_fixture(hub)


def test_unreadable_post_replace_is_unknown_and_blocks_ordinary_and_final(tmp_path, monkeypatch):
    hub, user, candidate, digest = setup_candidate(tmp_path)
    original_commit, original_read = hub._store_commit, hub.store.read_bytes_result
    changed = []

    def commit(encoded):
        result = original_commit(encoded)
        changed.append(True)
        return result

    def read():
        if changed:
            raise OSError('synthetic readback failure')
        return original_read()

    monkeypatch.setattr(hub, '_store_commit', commit)
    monkeypatch.setattr(hub.store, 'read_bytes_result', read)
    try:
        with hub._writer_scope(kind='credential') as lease:
            proof = hub._commit_credential_candidate(candidate, lease)
        assert proof.effect == 'uncertain' and proof.error_code == 'credential_unknown'
        assert not proof.retryable
        assert hub._recovery.phase == 'FAILED' and not hub._service_available()
        assert not hub.known[user.uid].get('pwd')
        assert hub._persist(force=True) is False
        assert hub._persist_flush() is False
        # Disk really holds the candidate: unknown does not mean rolled back.
        assert strict_json((tmp_path / 'store/state.json').read_bytes())['known'][str(user.uid)]['pwd'] == digest
    finally:
        stop_fixture(hub)


def test_control_change_after_replace_prevents_credential_confirmation(tmp_path, monkeypatch):
    hub, _, candidate, _ = setup_candidate(tmp_path)
    original = hub._store_commit

    def change_control(encoded):
        result = original(encoded)
        control = tmp_path / 'store/control.json'
        control.write_bytes(b'{"synthetic":"conflicting control"}')
        return result

    monkeypatch.setattr(hub, '_store_commit', change_control)
    try:
        with hub._writer_scope(kind='credential') as lease:
            proof = hub._commit_credential_candidate(candidate, lease)
        assert proof.effect == 'uncertain' and hub._recovery.phase == 'FAILED'
    finally:
        stop_fixture(hub)


@pytest.mark.parametrize('status', ['pending', 'failed', 'unknown'])
def test_credential_cannot_implicitly_publish_waiting_retirement(tmp_path, monkeypatch, status):
    hub, _, candidate, _ = setup_candidate(tmp_path)
    hub._retire_ops[77] = {'status': status, 'persistence_phase': 'snapshot'}
    monkeypatch.setattr(hub, '_store_commit', lambda _: pytest.fail('blocked retirement cannot write'))
    before = (tmp_path / 'store/state.json').read_bytes()
    try:
        with hub._writer_scope(kind='credential') as lease:
            proof = hub._commit_credential_candidate(candidate, lease)
        assert proof.effect == 'not_committed' and proof.error_code == 'credential_store_busy'
        assert (tmp_path / 'store/state.json').read_bytes() == before
    finally:
        stop_fixture(hub)


def test_confirmed_delta_handoff_retains_unregister_change_and_queues_fresh_capture(tmp_path, monkeypatch):
    hub, user, candidate, digest = setup_candidate(tmp_path)
    requests_before = hub._persist_request_seq
    queued = []
    monkeypatch.setattr(hub, '_persist_queue_trigger', lambda *_: queued.append(True))
    try:
        with hub._writer_scope(kind='credential') as lease:
            proof = hub._commit_credential_candidate(candidate, lease)
            hub.unregister(user, 'synthetic IO interleave')
            assert hub._persist_request_seq == requests_before
            with hub.lock:
                last_online = hub.known[user.uid]['last_online']
                assert last_online > 0
                hub.known[user.uid]['pwd'] = digest  # Only the confirmed delta is published.
            hub._credential_capture_confirmed(proof)
            assert hub._persist_request_seq == requests_before + 1
            assert hub._persist_dirty and queued == [True]
        assert hub._persist(force=True)
        actual = strict_json((tmp_path / 'store/state.json').read_bytes())['known'][str(user.uid)]
        assert actual['pwd'] == digest and actual['last_online'] == last_online
    finally:
        stop_fixture(hub)
