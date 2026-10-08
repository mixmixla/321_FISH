"""Real Hub integration over explicit, disposable versioned Stores."""
from dataclasses import replace
import ctypes
import hashlib
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time

import pytest

from config import CFG
from server import Hub, Session
from server_recovery import StoreCoordinator, StoreError, StoreOwner, strict_json
from server_store import SaveResult, encode_state


def config_for(path):
    return replace(CFG, admin_pwd=secrets.token_urlsafe(24),
                   web_files_dir=str(path / 'web'), audit_dir=str(path / 'audit'),
                   persist_interval=3600.0, bind_host='127.0.0.1',
                   discovery_enabled=False, tray_enabled=False)


def fresh_hub(path):
    root = path / 'store'
    StoreCoordinator.initialize_new(root)
    hub = Hub(cfg=config_for(path), store_dir=str(root))
    hub._persist_last = time.time()
    return hub


def stop_fixture(hub):
    """Fixture cleanup only; product shutdown is tested in the lifecycle slice."""
    hub._service_ready = False
    hub._persist_closing = True
    with hub._persist_lock:
        hub._persist_pending = False
    hub._persist_wake.set()
    worker = hub._persist_worker_thread
    if worker is not None:
        worker.join(5)
        assert not worker.is_alive()
    hub.audit.close()
    hub._recovery.close()


def login(hub, name=None, *, admin=False):
    frames = []
    name = hub.cfg.admin_nick if admin else name
    sess = Session(0, name, 'tcp', '127.0.0.1', lambda header, *_: frames.append(header))
    payload = {'nick': name}
    if admin:
        payload['pwd'] = hub.cfg.admin_pwd
    assert hub._on_hello(sess, payload)
    return sess, frames


def people(hub):
    admin, frames = login(hub, admin=True)
    user, _ = login(hub, '合成目标')
    survivor, _ = login(hub, '合成旁观')
    assert hub._persist(force=True)
    return admin, frames, user, survivor


def retire(hub, admin, uid, *, op=None, request_id='delete_1'):
    payload = {'uid': uid, 'request_id': request_id}
    if op is not None:
        payload['operation_id'] = op
    hub._on_admin_user_del(admin, payload)


@pytest.mark.parametrize('kind', ['missing', 'corrupt', 'wrong_id', 'unknown_key'])
def test_bad_startup_never_reaches_resources_audit_or_writes(tmp_path, monkeypatch, kind):
    root = tmp_path / 'store'
    StoreCoordinator.initialize_new(root)
    state_path = root / 'state.json'
    if kind == 'missing':
        state_path.unlink()
    elif kind == 'corrupt':
        state_path.write_bytes(b'{')
    else:
        state = strict_json(state_path.read_bytes())
        if kind == 'wrong_id':
            state['_store']['store_id'] = 'f' * 32
        else:
            state['unknown_private_value'] = 'do not emit this content'
        state_path.write_bytes(encode_state(state).payload)
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    monkeypatch.setattr(Hub, '_initialize_resources', lambda *_: pytest.fail('resources before load proof'))
    monkeypatch.setattr('server.audit_mod.AuditLog', lambda *_: pytest.fail('audit before load proof'))
    with pytest.raises(StoreError) as caught:
        Hub(cfg=config_for(tmp_path), store_dir=str(root))
    assert 'do not emit this content' not in str(caught.value)
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}
    assert not (tmp_path / 'web').exists()
    assert not (tmp_path / 'audit').exists()


def test_completed_retirement_reopens_with_same_identity_and_truthful_origin(tmp_path):
    hub = fresh_hub(tmp_path)
    admin, frames, user, survivor = people(hub)
    uid = user.uid
    try:
        retire(hub, admin, uid)
        receipt = hub._retirement_payload(uid)
        assert receipt['status'] == 'confirmed', receipt
        assert receipt['persistence_phase'] == 'snapshot' and receipt['identity_effect'] == 'revoked'
        assert user.closed and hub._session_is_active(survivor)
        assert hub._recovery.intents[str(uid)] == hub.retired[uid]
        info = [f for f in frames if f.get('request_id') == 'delete_1']
        assert [f['retirement']['status'] for f in info] == ['pending', 'confirmed']
        assert receipt['content_sha256'] == hashlib.sha256((tmp_path / 'store/state.json').read_bytes()).hexdigest()
    finally:
        stop_fixture(hub)
    reopened = Hub(cfg=config_for(tmp_path), store_dir=str(tmp_path / 'store'))
    try:
        restored = reopened._retirement_payload(uid)
        assert restored['status'] == 'confirmed' and restored['operation_id'] == receipt['operation_id']
        assert restored['origin'] == 'restored_valid_json' and restored['content_sha256'] is None
        rejected = Session(0, user.nick, 'tcp', '127.0.0.1', lambda *_: None)
        assert reopened._on_hello(rejected, {'nick': user.nick}) is False
    finally:
        stop_fixture(reopened)


def test_intent_failure_leaves_identity_active_and_explicit_retry_reuses_op(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    admin, frames, user, survivor = people(hub)
    before = (tmp_path / 'store/state.json').read_bytes()
    original = hub._recovery.control_store.save_bytes
    monkeypatch.setattr(hub._recovery.control_store, 'save_bytes',
                        lambda _: SaveResult('not_committed', 'write', 'synthetic', True))
    try:
        retire(hub, admin, user.uid)
        failed = hub._retirement_payload(user.uid)
        assert failed['status'] == 'failed' and failed['identity_effect'] == 'not_started'
        assert failed['retryable'] is True
        assert hub._session_is_active(user) and user.uid in hub.known
        assert user.uid not in hub.retired and hub._recovery.intents == {}
        assert (tmp_path / 'store/state.json').read_bytes() == before
        monkeypatch.setattr(hub._recovery.control_store, 'save_bytes', original)
        retire(hub, admin, user.uid, op=failed['operation_id'], request_id='retry_1')
        final = hub._retirement_payload(user.uid)
        assert final['status'] == 'confirmed' and final['operation_id'] == failed['operation_id']
        assert user.closed and hub._session_is_active(survivor)
    finally:
        stop_fixture(hub)


def test_first_snapshot_failure_replays_before_cloud_scan_and_keeps_old_bytes(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    admin, frames, user, survivor = people(hub)
    uid = user.uid
    hub._drafts[(uid, 'public')] = {'text': '待清理', 'ts': 1.0}
    hub.bus.publish({'t': 'chat', 'uid': uid, 'nick': user.nick, 'channel': 'public',
                     'text': '目标历史', 'ts': 1.0})
    assert hub._persist(force=True)
    old_state = (tmp_path / 'store/state.json').read_bytes()
    (Path(hub.cloud_dir) / f'{uid}.bin').write_bytes(b'synthetic-private')
    (Path(hub.cloud_dir) / f'{survivor.uid}.bin').write_bytes(b'synthetic-survivor')
    monkeypatch.setattr(hub.store, '_save_encoded',
                        lambda encoded: SaveResult('not_committed', 'write', 'synthetic', True,
                                                   encoded.length, encoded.sha256))
    try:
        retire(hub, admin, uid)
        failed = hub._retirement_payload(uid)
        assert failed['status'] == 'failed' and failed['identity_effect'] == 'revoked', failed
        assert user.closed and uid in hub.retired
        assert (tmp_path / 'store/state.json').read_bytes() == old_state
        assert hub._recovery.intents[str(uid)]['operation_id'] == failed['operation_id']
        # Ordinary/flush writers cannot silently retry a failed retirement.
        assert hub._persist(force=True) is False
        assert (tmp_path / 'store/state.json').read_bytes() == old_state
    finally:
        stop_fixture(hub)
    monkeypatch.undo()
    original_scan = Hub._cloud_load_disk
    def guarded_scan(current):
        assert uid in current.retired
        assert uid not in current.known
        assert current._recovery.phase == 'READY'
        assert current._all_intents_clean(strict_json((tmp_path / 'store/state.json').read_bytes()),
                                          current._recovery.intents)
        original_scan(current)
    monkeypatch.setattr(Hub, '_cloud_load_disk', guarded_scan)
    reopened = Hub(cfg=config_for(tmp_path), store_dir=str(tmp_path / 'store'))
    try:
        final = reopened._retirement_payload(uid)
        assert final['status'] == 'confirmed' and final['operation_id'] == failed['operation_id']
        assert final['origin'] == 'written'
        assert (uid, 'public') not in reopened._drafts
        assert not reopened.bus.history('all')
        assert uid not in reopened.cloud and survivor.uid in reopened.cloud
        assert (Path(reopened.cloud_dir) / f'{uid}.bin').read_bytes() == b'synthetic-private'
    finally:
        stop_fixture(reopened)


def test_explicit_snapshot_retry_keeps_operation_and_does_not_repeat_t0(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    admin, frames, user, _ = people(hub)
    original = hub.store._save_encoded
    monkeypatch.setattr(hub.store, '_save_encoded',
                        lambda encoded: SaveResult('not_committed', 'write', 'synthetic', True,
                                                   encoded.length, encoded.sha256))
    try:
        retire(hub, admin, user.uid)
        failed = hub._retirement_payload(user.uid)
        assert failed['status'] == 'failed' and failed['retryable'] is True
        monkeypatch.setattr(hub.store, '_save_encoded', original)
        monkeypatch.setattr(hub, '_apply_retirement_core_locked',
                            lambda *_: pytest.fail('t0 must not run again'))
        retire(hub, admin, user.uid, op=failed['operation_id'], request_id='snapshot_retry')
        final = hub._retirement_payload(user.uid)
        assert final['status'] == 'confirmed' and final['operation_id'] == failed['operation_id']
        replies = [f['retirement']['status'] for f in frames if f.get('request_id') == 'snapshot_retry']
        assert replies == ['pending', 'confirmed']
    finally:
        stop_fixture(hub)


def test_actual_state_replace_then_real_read_refusal_stays_unknown_until_query(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    admin, frames, user, _ = people(hub)
    original = hub.store._save_encoded
    api, handles = hub._recovery.owner._api, []
    def save_and_lock(encoded):
        result = original(encoded)
        assert result.effect == 'committed'
        handle = api.CreateFileW(str(tmp_path / 'store/state.json'), 0x80000000, 0, None, 3, 0x80, None)
        assert handle != ctypes.c_void_p(-1).value
        handles.append(handle)
        return result
    monkeypatch.setattr(hub.store, '_save_encoded', save_and_lock)
    try:
        retire(hub, admin, user.uid)
        unknown = hub._retirement_payload(user.uid)
        assert unknown['status'] == 'unknown' and unknown['identity_effect'] == 'revoked'
        assert unknown['content_sha256'] is None
        assert hub._persist_unresolved is not None and len(handles) == 1
        for handle in handles:
            api.CloseHandle(handle)
        handles.clear()
        monkeypatch.setattr(hub.store, '_save_encoded',
                            lambda *_: pytest.fail('query cannot write'))
        hub._on_admin_user_get(admin, {'uid': user.uid, 'operation_id': unknown['operation_id'],
                                       'request_id': 'query_after_refusal'})
        final = hub._retirement_payload(user.uid)
        assert final['status'] == 'confirmed' and final['origin'] == 'reconciled_current_json'
        assert final['content_sha256'] == hashlib.sha256((tmp_path / 'store/state.json').read_bytes()).hexdigest()
    finally:
        for handle in handles:
            api.CloseHandle(handle)
        stop_fixture(hub)


def test_t0_exception_and_capture_exception_stop_without_final_flush(tmp_path, monkeypatch):
    for stage in ('t0', 'capture'):
        base = tmp_path / stage
        hub = fresh_hub(base)
        admin, frames, user, _ = people(hub)
        before = (base / 'store/state.json').read_bytes()
        method = '_apply_retirement_core_locked' if stage == 't0' else '_capture_persist_state'
        original = getattr(hub, method)
        injected = []
        def broken(*args, **kwargs):
            lease = getattr(hub._writer_local, 'lease', None)
            if getattr(lease, 'kind', None) == 'retirement':
                injected.append((lease.uid, str(user.uid) in hub._recovery.intents))
                raise RuntimeError('synthetic retirement failure')
            # Credential setup may still have an ordinary fresh capture queued.
            # This case injects after retirement admission, not into that worker.
            return original(*args, **kwargs)
        monkeypatch.setattr(hub, method, broken)
        try:
            retire(hub, admin, user.uid)
            assert injected == [(user.uid, True)]
            assert hub._recovery.phase == 'FAILED'
            assert hub._service_stop.is_set()
            receipt = hub._retirement_payload(user.uid)
            assert receipt['status'] == 'unknown' and receipt['identity_effect'] == 'revoked'
            assert str(user.uid) in hub._recovery.intents
            assert hub._persist_flush() is False
            assert (base / 'store/state.json').read_bytes() == before
        finally:
            monkeypatch.setattr(hub, method, original)
            stop_fixture(hub)


def test_recovery_write_failure_stops_before_resource_construction(tmp_path, monkeypatch):
    root = tmp_path / 'store'
    StoreCoordinator.initialize_new(root)
    coordinator = StoreCoordinator(root)
    pair = coordinator.open()
    coordinator.mark_ready(pair.state)
    assert coordinator.accept_intent(8, {'nick': '合成旧目标', 'retired_at': 1,
                                         'operation_id': 'replay-8'}).effect == 'committed'
    coordinator.close()
    before = (root / 'state.json').read_bytes()
    monkeypatch.setattr(Hub, '_store_commit', lambda *_: SaveResult('not_committed', 'write', 'synthetic', True))
    monkeypatch.setattr(Hub, '_initialize_resources', lambda *_: pytest.fail('resource before recovery proof'))
    with pytest.raises(StoreError, match='recovery_write_failed'):
        Hub(cfg=config_for(tmp_path), store_dir=str(root))
    assert (root / 'state.json').read_bytes() == before
    assert not (tmp_path / 'web').exists()
    assert StoreCoordinator.inspect(root)['exclusive'] is True


def test_intent_ambiguity_fails_all_writer_entrances_without_t0(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    admin, frames, user, _ = people(hub)
    before = (tmp_path / 'store/state.json').read_bytes()
    def ambiguous(_):
        (tmp_path / 'store/control.json').write_bytes(b'broken synthetic authority')
        return SaveResult('uncertain', 'replace', 'synthetic', False)
    monkeypatch.setattr(hub._recovery.control_store, 'save_bytes', ambiguous)
    try:
        retire(hub, admin, user.uid)
        receipt = hub._retirement_payload(user.uid)
        assert receipt['status'] == 'unknown' and receipt['identity_effect'] == 'unverified'
        assert hub._recovery.phase == 'FAILED' and hub._service_stop.is_set()
        assert user.uid not in hub.retired
        assert hub._persist(force=True) is False
        assert hub._persist_flush() is False
        assert hub.store.save({}) is False
        assert hub.store.save_bytes(b'{}').effect == 'not_committed'
        assert (tmp_path / 'store/state.json').read_bytes() == before
        assert hub.dispatch(user, {'t': 'heartbeat'}) is False
    finally:
        stop_fixture(hub)


def test_same_uid_pending_attempt_has_one_intent_and_one_t0(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    admin, frames, user, _ = people(hub)
    entered, release = threading.Event(), threading.Event()
    original, calls = hub._recovery.accept_intent, []
    def delayed(uid, record):
        calls.append(record['operation_id'])
        entered.set()
        assert release.wait(5)
        return original(uid, record)
    monkeypatch.setattr(hub._recovery, 'accept_intent', delayed)
    first = threading.Thread(target=retire, args=(hub, admin, user.uid))
    try:
        first.start()
        assert entered.wait(5)
        retire(hub, admin, user.uid, request_id='duplicate_1')
        assert len(calls) == 1 and user.uid not in hub.retired
        release.set()
        first.join(5)
        assert not first.is_alive()
        assert hub._retirement_payload(user.uid)['status'] == 'confirmed'
        assert len(calls) == 1
    finally:
        release.set()
        first.join(5)
        stop_fixture(hub)


def test_authorization_change_before_intent_remains_retryable_for_fresh_admin(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    admin, frames, user, _ = people(hub)
    reserved = threading.Event()
    original = hub._send_retirement_info
    def observe(sess, uid, request_id):
        original(sess, uid, request_id)
        if request_id == 'stale_admin':
            reserved.set()
    monkeypatch.setattr(hub, '_send_retirement_info', observe)
    worker = threading.Thread(target=lambda: retire(hub, admin, user.uid, request_id='stale_admin'))
    try:
        with hub._persist_writer_lock:
            worker.start()
            assert reserved.wait(5)
            with hub.lock:
                admin.is_admin = False
        worker.join(5)
        assert not worker.is_alive()
        failed = hub._retirement_payload(user.uid)
        assert failed['status'] == 'failed' and failed['identity_effect'] == 'not_started'
        assert failed['error_code'] == 'authorization_changed' and failed['retryable'] is True
        assert user.uid not in hub.retired and hub._recovery.intents == {}
        replacement, _ = login(hub, admin=True)
        retire(hub, replacement, user.uid, op=failed['operation_id'], request_id='fresh_admin')
        final = hub._retirement_payload(user.uid)
        assert final['status'] == 'confirmed' and final['operation_id'] == failed['operation_id']
    finally:
        worker.join(5)
        stop_fixture(hub)


@pytest.mark.parametrize('point', ['after_intent', 'after_t0'])
def test_real_hub_process_exit_between_intent_and_state_recovers_before_login(tmp_path, point):
    hub = fresh_hub(tmp_path)
    admin, _, user, survivor = people(hub)
    uid, nick = user.uid, user.nick
    before = (tmp_path / 'store/state.json').read_bytes()
    stop_fixture(hub)
    script = r'''
import os, secrets, sys, time
from pathlib import Path
from dataclasses import replace
from config import CFG
from server import Hub, Session
root, uid, point = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
cfg = replace(CFG, admin_pwd=secrets.token_urlsafe(24),
              web_files_dir=str(root/'web'), audit_dir=str(root/'audit'),
              persist_interval=3600.0, discovery_enabled=False, tray_enabled=False)
hub = Hub(cfg=cfg, store_dir=str(root/'store'))
hub._persist_last = time.time()
admin = Session(0, cfg.admin_nick, 'tcp', '127.0.0.1', lambda *_: None)
assert hub._on_hello(admin, {'nick':cfg.admin_nick,'pwd':cfg.admin_pwd})
def abrupt(*_): os._exit(41)
if point == 'after_intent': hub._apply_retirement_core_locked = abrupt
else: hub._store_commit = abrupt
hub._on_admin_user_del(admin, {'uid':uid, 'request_id':'process_exit'})
os._exit(99)
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path), str(uid), point],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 41, result.stderr
    assert (tmp_path / 'store/state.json').read_bytes() == before
    accepted = strict_json((tmp_path / 'store/control.json').read_bytes())['intents'][str(uid)]
    reopened = Hub(cfg=config_for(tmp_path), store_dir=str(tmp_path / 'store'))
    try:
        receipt = reopened._retirement_payload(uid)
        assert receipt['status'] == 'confirmed' and receipt['operation_id'] == accepted['operation_id']
        assert uid not in reopened.known and reopened.nick_to_uid[nick] == uid
        rejected = Session(0, nick, 'tcp', '127.0.0.1', lambda *_: None)
        assert reopened._on_hello(rejected, {'nick': nick}) is False
        assert survivor.uid in reopened.known
    finally:
        stop_fixture(reopened)


@pytest.mark.parametrize('stage', ['resources', 'audit'])
def test_resource_or_audit_initialization_failure_releases_owner_without_flush(tmp_path, monkeypatch, stage):
    root = tmp_path / 'store'
    StoreCoordinator.initialize_new(root)
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    captured = []
    original = Hub._initialize_resources
    def resource_init(hub):
        captured.append(hub)
        if stage == 'resources':
            raise OSError('synthetic resource init')
        original(hub)
    def audit_init(*_):
        raise OSError('synthetic audit init')
    monkeypatch.setattr(Hub, '_initialize_resources', resource_init)
    if stage == 'audit':
        monkeypatch.setattr('server.audit_mod.AuditLog', audit_init)
    with pytest.raises(OSError, match='synthetic'):
        Hub(cfg=config_for(tmp_path), store_dir=str(root))
    failed, = captured
    assert failed._recovery.phase == 'FAILED' and not failed._recovery.owner.held
    assert failed._service_ready is False and failed._persist_worker_thread is None
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}
    assert StoreCoordinator.inspect(root)['pair'] == 'valid'


def test_concurrent_different_targets_preserve_both_intents_and_fresh_snapshot(tmp_path):
    hub = fresh_hub(tmp_path)
    admin, _, first, second = people(hub)
    barrier = threading.Barrier(3)
    def action(uid):
        barrier.wait(timeout=5)
        retire(hub, admin, uid, request_id=f'parallel_{uid}')
    workers = [threading.Thread(target=action, args=(user.uid,)) for user in (first, second)]
    try:
        for worker in workers:
            worker.start()
        barrier.wait(timeout=5)
        for worker in workers:
            worker.join(5)
            assert not worker.is_alive()
        final = strict_json((tmp_path / 'store/state.json').read_bytes())
        control = strict_json((tmp_path / 'store/control.json').read_bytes())
        assert set(final['retired']) == set(control['intents']) == {str(first.uid), str(second.uid)}
        assert len({rec['operation_id'] for rec in control['intents'].values()}) == 2
        for user in (first, second):
            assert hub._retirement_payload(user.uid)['status'] == 'confirmed'
            assert str(user.uid) not in final['known']
    finally:
        for worker in workers:
            worker.join(5)
        stop_fixture(hub)


def test_real_legacy_counter_adopt_allocate_save_reopen_keeps_existing_identity(tmp_path):
    root = tmp_path / 'store'
    root.mkdir()
    legacy = {'uid_seq': 2, 'nick_to_uid': {'旧用户': 1, '旧目标': 999},
              'known': {'1': {'nick': '旧用户'}},
              'retired': {'999': {'nick': '旧目标', 'retired_at': 1.0,
                                   'operation_id': 'legacy-high-uid'}}}
    original = encode_state(legacy).payload
    (root / 'state.json').write_bytes(original)
    StoreCoordinator.adopt_legacy(root)
    adopted = (root / 'state.json').read_bytes()
    parsed = strict_json(adopted)
    parsed.pop('_store')
    assert parsed == legacy
    hub = Hub(cfg=config_for(tmp_path), store_dir=str(root))
    try:
        assert hub._uid_seq == 1000
        assert (root / 'state.json').read_bytes() == adopted
        assert hub._retirement_payload(999)['operation_id'] == 'legacy-high-uid'
        denied = Session(0, '旧目标', 'tcp', '127.0.0.1', lambda *_: None)
        assert hub._on_hello(denied, {'nick': '旧目标'}) is False
        hub._persist_last = time.time()
        fresh, _ = login(hub, '新的合成账户')
        assert fresh.uid == 1000
        assert hub.nick_to_uid['旧用户'] == 1 and hub.nick_to_uid['旧目标'] == 999
        assert hub._persist(force=True)
    finally:
        stop_fixture(hub)
    reopened = Hub(cfg=config_for(tmp_path), store_dir=str(root))
    try:
        assert reopened._uid_seq == 1001
        assert reopened.nick_to_uid['新的合成账户'] == 1000
        assert reopened.retired[999]['operation_id'] == 'legacy-high-uid'
        backup, = root.glob('state.legacy.*.json')
        assert backup.read_bytes() == original
    finally:
        stop_fixture(reopened)
