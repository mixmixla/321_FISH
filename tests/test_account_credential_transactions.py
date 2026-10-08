"""Identity, CAS, multi-session and lifecycle proofs on disposable real Stores."""
import copy
import threading
from dataclasses import replace

import pytest

import auth
from server import Hub, Session
from server_recovery import strict_json
from server_store import SaveResult
from test_retire_recovery_hub import config_for, fresh_hub, login, retire, stop_fixture


def hello_header(hub, nick, password='', *, claim=False, rid='hello_1'):
    cap = hub.auth_capabilities()
    return {'t': 'hello', 'auth_v': 1, 'request_id': rid,
            'expected_server_epoch': cap['server_epoch'],
            'expected_store_scope_id': cap['store_scope_id'],
            'claim_password': claim, 'nick': nick, 'pwd': password}


def attempt(hub, nick, password='', *, claim=False, rid='hello_1'):
    frames = []
    sess = Session(0, nick, 'tcp', '127.0.0.1', lambda h, *_: frames.append(h))
    accepted = hub.dispatch(sess, hello_header(hub, nick, password, claim=claim, rid=rid))
    return accepted, sess, frames


def update(hub, sess, old, new, rid):
    return hub.credential_update(sess, {'credential_v': 1, 'request_id': rid,
                                        'old': old, 'new': new})


def persisted(path):
    return strict_json((path / 'store/state.json').read_bytes())


def join(thread):
    thread.join(8)
    assert not thread.is_alive(), 'synthetic credential worker did not terminate'


def test_explicit_claim_change_clear_and_own_query_keep_other_sessions(tmp_path):
    hub = fresh_hub(tmp_path)
    try:
        ok, one, frames = attempt(hub, '合成完整凭据', 'synthetic-first', claim=True)
        assert ok
        claimed = next(h['credential'] for h in frames if h.get('t') == 'welcome')
        assert claimed['status'] == 'confirmed' and claimed['persisted']
        assert claimed['login_status'] == 'attached'
        assert auth.verify('synthetic-first', persisted(tmp_path)['known'][str(one.uid)]['pwd'])
        ok, two, frames = attempt(hub, one.nick, 'synthetic-first', rid='hello_2')
        assert ok and two.uid == one.uid
        assert not any('credential' in h for h in frames)
        result = update(hub, one, 'synthetic-first', 'synthetic-second', 'change_1')
        assert result['status'] == 'confirmed'
        assert hub._session_is_active(one) and hub._session_is_active(two)
        assert auth.verify('synthetic-second', persisted(tmp_path)['known'][str(one.uid)]['pwd'])
        query = hub.credential_query(two, {'credential_v': 1, 'request_id': 'get_1',
                                          'original_request_id': 'change_1',
                                          'operation_id': result['operation_id'],
                                          'operation_epoch': result['operation_epoch']})
        assert query['status'] == 'confirmed' and query['request_id'] == 'get_1'
        assert update(hub, two, 'synthetic-first', 'synthetic-second', 'change_1') == result
        assert update(hub, one, 'synthetic-second', '', 'clear_1')['status'] == 'confirmed'
        assert 'pwd' not in persisted(tmp_path)['known'][str(one.uid)]
        stale_ok, stale, stale_frames = attempt(hub, one.nick, 'synthetic-second')
        assert not stale_ok and stale.uid == 0
        assert any(h.get('reason') == 'claim_required' for h in stale_frames)
        assert hub._session_is_active(two)
    finally:
        stop_fixture(hub)


@pytest.mark.parametrize('same_password', [False, True])
def test_two_initial_claims_authorize_only_verified_winner(tmp_path, monkeypatch, same_password):
    hub = fresh_hub(tmp_path)
    barrier = threading.Barrier(2)
    original_make = auth.make
    values = ['synthetic-left', 'synthetic-left' if same_password else 'synthetic-right']
    results, errors = [], []

    def make(value):
        if value in values:
            barrier.wait(timeout=5)
        return original_make(value)

    monkeypatch.setattr(auth, 'make', make)

    def run(index):
        try:
            results.append((index, attempt(hub, '合成抢先认领', values[index], claim=True,
                                           rid=f'claim_{index}')))
        except BaseException as exc:
            errors.append(type(exc).__name__)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            join(thread)
        assert not errors and len(results) == 2
        accepted = [(i, sess, frames) for i, (ok, sess, frames) in results if ok]
        assert len(accepted) == (2 if same_password else 1)
        uid = accepted[0][1].uid
        disk_hash = persisted(tmp_path)['known'][str(uid)]['pwd']
        assert all(auth.verify(values[i], disk_hash) for i, _, _ in accepted)
        receipts = [h['credential'] for _, _, frames in accepted for h in frames
                    if h.get('t') == 'welcome' and 'credential' in h]
        assert sum(r['status'] == 'confirmed' for r in receipts) == 1
        if same_password:
            loser = next(r for r in receipts if r['status'] == 'failed')
            assert loser['reason'] == 'credential_already_bound' and 'persisted' not in loser
        for _, (ok, sess, frames) in results:
            if not ok:
                assert sess.uid == 0 and not any(h.get('t') == 'welcome' for h in frames)
                assert all(sess not in members for members in hub._uid_clients.values())
        assert hub._uid_seq == uid + 1
    finally:
        barrier.abort()
        for thread in threads:
            if thread.ident is not None:
                join(thread)
        stop_fixture(hub)


def test_concurrent_changes_from_same_old_password_cannot_overwrite(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    ok, user, _ = attempt(hub, '合成并发改密', 'synthetic-old', claim=True)
    assert ok
    original_verify = auth.verify
    barrier = threading.Barrier(2)
    results = []

    def verify(value, stored):
        valid = original_verify(value, stored)
        if valid and value == 'synthetic-old':
            barrier.wait(timeout=5)
        return valid

    monkeypatch.setattr(auth, 'verify', verify)
    threads = [threading.Thread(target=lambda i=i: results.append(
        (i, update(hub, user, 'synthetic-old', f'synthetic-new-{i}', f'change_{i}')))) for i in range(2)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            join(thread)
        assert len(results) == 2
        assert sorted(r['status'] for _, r in results) == ['confirmed', 'failed']
        assert next(r for _, r in results if r['status'] == 'failed')['reason'] == 'credential_conflict'
        winner = next(i for i, r in results if r['status'] == 'confirmed')
        assert auth.verify(f'synthetic-new-{winner}', persisted(tmp_path)['known'][str(user.uid)]['pwd'])
    finally:
        barrier.abort()
        for thread in threads:
            join(thread)
        stop_fixture(hub)


def test_revision_blocks_set_clear_set_aba_even_when_hash_returns_to_same_value(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    ok, user, _ = attempt(hub, '合成ABA', 'synthetic-original', claim=True)
    assert ok
    initial_hash = hub.known[user.uid]['pwd']
    original_make = auth.make
    entered, release = threading.Event(), threading.Event()
    results = []

    def make(value):
        if value == 'synthetic-delayed':
            entered.set()
            assert release.wait(5)
        if value == 'synthetic-restore-fixture':
            return initial_hash  # Deliberately make value-only comparison insufficient.
        return original_make(value)

    monkeypatch.setattr(auth, 'make', make)
    thread = threading.Thread(target=lambda: results.append(
        update(hub, user, 'synthetic-original', 'synthetic-delayed', 'delayed')))
    try:
        thread.start()
        assert entered.wait(5)
        assert update(hub, user, 'synthetic-original', '', 'clear')['status'] == 'confirmed'
        assert update(hub, user, '', 'synthetic-restore-fixture', 'restore')['status'] == 'confirmed'
        assert hub.known[user.uid]['pwd'] == initial_hash
        release.set()
        join(thread)
        assert results[0]['status'] == 'failed' and results[0]['reason'] == 'credential_conflict'
        assert persisted(tmp_path)['known'][str(user.uid)]['pwd'] == initial_hash
    finally:
        release.set()
        join(thread)
        stop_fixture(hub)


@pytest.mark.parametrize('after_admission', [False, True])
def test_logout_before_admission_refuses_but_after_admission_drains_once(tmp_path, monkeypatch, after_admission):
    hub = fresh_hub(tmp_path)
    ok, user, _ = attempt(hub, '合成注销交错', 'synthetic-old', claim=True)
    assert ok
    entered, release = threading.Event(), threading.Event()
    results = []
    if after_admission:
        original = hub._store_commit

        def gate(encoded):
            entered.set()
            assert release.wait(5)
            return original(encoded)

        monkeypatch.setattr(hub, '_store_commit', gate)
    else:
        original = auth.make

        def gate(value):
            if value == 'synthetic-new':
                entered.set()
                assert release.wait(5)
            return original(value)

        monkeypatch.setattr(auth, 'make', gate)
    thread = threading.Thread(target=lambda: results.append(
        update(hub, user, 'synthetic-old', 'synthetic-new', 'logout_race')))
    try:
        thread.start()
        assert entered.wait(5)
        hub.unregister(user, 'synthetic logout')
        last_online = hub.known[user.uid]['last_online']
        release.set()
        join(thread)
        assert results[0]['status'] == ('confirmed' if after_admission else 'failed')
        if not after_admission:
            assert results[0]['reason'] == 'session_inactive'
        assert hub._persist(force=True)
        info = persisted(tmp_path)['known'][str(user.uid)]
        assert auth.verify('synthetic-new' if after_admission else 'synthetic-old', info['pwd'])
        assert info['last_online'] == last_online
        assert not hub._session_is_active(user)
    finally:
        release.set()
        join(thread)
        stop_fixture(hub)


def test_retirement_can_finish_while_derivation_waits_and_blocks_old_work(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    admin, _ = login(hub, admin=True)
    ok, user, _ = attempt(hub, '合成退役竞争', 'synthetic-old', claim=True)
    assert ok
    entered, release = threading.Event(), threading.Event()
    original_make = auth.make
    results = []

    def make(value):
        if value == 'synthetic-new':
            entered.set()
            assert release.wait(5)
        return original_make(value)

    monkeypatch.setattr(auth, 'make', make)
    thread = threading.Thread(target=lambda: results.append(
        update(hub, user, 'synthetic-old', 'synthetic-new', 'retire_race')))
    try:
        thread.start()
        assert entered.wait(5)
        retire(hub, admin, user.uid)
        assert user.uid in hub.retired and user.uid not in hub.known
        release.set()
        join(thread)
        assert results[0]['status'] == 'failed' and results[0]['reason'] == 'retired'
        state = persisted(tmp_path)
        assert str(user.uid) in state['retired'] and str(user.uid) not in state['known']
    finally:
        release.set()
        join(thread)
        stop_fixture(hub)


def test_confirmed_claim_with_lost_connection_never_claims_login_completed(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    frames = []
    user = Session(0, '合成提交后断线', 'tcp', '127.0.0.1', lambda h, *_: frames.append(h))
    original = hub._store_commit

    def lose_connection(encoded):
        result = original(encoded)
        user.closed = True
        return result

    monkeypatch.setattr(hub, '_store_commit', lose_connection)
    try:
        assert hub._on_hello(user, hello_header(hub, user.nick, 'synthetic-claim', claim=True)) is False
        reply = next(h['credential'] for h in frames if 'credential' in h)
        assert reply['status'] == 'confirmed' and reply['login_status'] == 'not_attached'
        assert reply['persisted'] is True and user.uid == 0
        assert not any(h.get('t') == 'welcome' for h in frames)
        uid = reply['uid']
        assert uid not in hub.sessions
        assert auth.verify('synthetic-claim', persisted(tmp_path)['known'][str(uid)]['pwd'])
    finally:
        stop_fixture(hub)


@pytest.mark.parametrize('claim', [False, True])
def test_first_identity_write_failure_consumes_no_live_identity_or_session(tmp_path, monkeypatch, claim):
    hub = fresh_hub(tmp_path)
    before = (tmp_path / 'store/state.json').read_bytes()
    original_seq = hub._uid_seq
    original_known = copy.deepcopy(hub.known)
    monkeypatch.setattr(hub, '_store_commit', lambda _: SaveResult('not_committed', 'synthetic', 'write_failed', True))
    try:
        ok, user, frames = attempt(hub, '合成创建失败', 'synthetic-claim' if claim else '', claim=claim)
        assert not ok and user.uid == 0
        assert not any(h.get('t') == 'welcome' for h in frames)
        assert hub._uid_seq == original_seq and hub.known == original_known
        assert user.nick not in hub.nick_to_uid and not hub.sessions
        assert (tmp_path / 'store/state.json').read_bytes() == before
        if claim:
            reply = next(h['credential'] for h in frames if 'credential' in h)
            assert reply['status'] == 'failed' and 'persisted' not in reply
    finally:
        stop_fixture(hub)


def test_restart_authenticates_actual_state_but_cannot_recreate_prior_receipt(tmp_path):
    hub = fresh_hub(tmp_path)
    try:
        ok, user, _ = attempt(hub, '合成重启', 'synthetic-old', claim=True)
        assert ok
        result = update(hub, user, 'synthetic-old', 'synthetic-new', 'before_restart')
        assert result['status'] == 'confirmed'
        uid, prior_epoch = user.uid, hub._server_epoch
    finally:
        stop_fixture(hub)
    reopened = Hub(cfg=config_for(tmp_path), store_dir=str(tmp_path / 'store'))
    try:
        ok, again, frames = attempt(reopened, '合成重启', 'synthetic-new')
        assert ok and again.uid == uid and reopened._server_epoch != prior_epoch
        assert not any('credential' in h for h in frames)
        query = reopened.credential_query(again, {
            'credential_v': 1, 'request_id': 'after_restart',
            'original_request_id': 'before_restart', 'operation_id': result['operation_id'],
            'operation_epoch': prior_epoch})
        assert query['status'] == 'unknown' and query['reason'] == 'operation_unavailable'
        assert 'persisted' not in query
    finally:
        stop_fixture(reopened)


@pytest.mark.parametrize('retirement', [False, True])
def test_revoke_between_admission_and_delivery_never_emits_welcome(tmp_path, monkeypatch, retirement):
    hub = fresh_hub(tmp_path)
    admin, _ = login(hub, admin=True)
    original = hub._announce_login

    def revoked_before_delivery(sess, was_online, credential=None):
        if sess.nick == '合成发送前撤销':
            if retirement:
                retire(hub, admin, sess.uid)
            else:
                hub.unregister(sess, 'synthetic pre-delivery logout')
        return original(sess, was_online, credential)

    monkeypatch.setattr(hub, '_announce_login', revoked_before_delivery)
    try:
        ok, sess, frames = attempt(hub, '合成发送前撤销', 'synthetic-claim', claim=True)
        assert not ok
        assert not any(h.get('t') == 'welcome' for h in frames)
        receipt = next(h['credential'] for h in frames if 'credential' in h)
        assert receipt['status'] == 'confirmed' and receipt['login_status'] == 'not_attached'
        assert not hub._session_is_active(sess)
    finally:
        stop_fixture(hub)


def test_volatile_claim_returns_structured_failed_without_operation_or_derivation(tmp_path, monkeypatch):
    hub = Hub(cfg=config_for(tmp_path))
    calls = []
    original = auth.make
    monkeypatch.setattr(auth, 'make', lambda value: (calls.append(True), original(value))[1])
    try:
        ok, sess, frames = attempt(hub, '合成无Store认领', 'synthetic-claim', claim=True)
        assert not ok and sess.uid == 0 and not calls
        receipt = next(h['credential'] for h in frames if 'credential' in h)
        assert receipt['status'] == 'failed' and receipt['operation_id'] is None
        assert receipt['reason'] == 'credential_store_unavailable' and 'persisted' not in receipt
        assert not hub.nick_to_uid
    finally:
        hub.shutdown(normal=False)


def test_failed_claim_replay_never_reexecutes_even_after_storage_recovers(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    original = hub._store_commit
    monkeypatch.setattr(hub, '_store_commit', lambda _: SaveResult('not_committed', 'injected', 'write_failed', True))
    before = (tmp_path / 'store/state.json').read_bytes()
    try:
        ok, _, frames = attempt(hub, '合成失败重复', 'synthetic-claim', claim=True, rid='same')
        assert not ok
        first = next(h['credential'] for h in frames if 'credential' in h)
        monkeypatch.setattr(hub, '_store_commit', original)
        ok, sess, frames = attempt(hub, '合成失败重复', 'synthetic-claim', claim=True, rid='same')
        assert not ok and sess.uid == 0
        second = next(h['credential'] for h in frames if 'credential' in h)
        assert second['status'] == 'failed' and second['operation_id'] == first['operation_id']
        assert (tmp_path / 'store/state.json').read_bytes() == before
        assert attempt(hub, '合成失败重复', 'synthetic-claim', claim=True, rid='explicit_new')[0]
    finally:
        stop_fixture(hub)


def test_confirmed_claim_replay_reauthenticates_and_returns_original_operation(tmp_path):
    hub = fresh_hub(tmp_path)
    try:
        ok, first_sess, frames = attempt(hub, '合成确认重复', 'synthetic-claim', claim=True, rid='same')
        assert ok
        first = next(h['credential'] for h in frames if h.get('t') == 'welcome')
        ok, second_sess, frames = attempt(hub, first_sess.nick, 'synthetic-claim', claim=True, rid='same')
        assert ok and second_sess.uid == first_sess.uid
        welcome = next(h for h in frames if h.get('t') == 'welcome')
        assert 'credential' in welcome
        assert welcome['credential']['operation_id'] == first['operation_id']
        assert welcome['credential']['status'] == 'confirmed'
        bad, _, frames = attempt(hub, first_sess.nick, 'different', claim=True, rid='same')
        assert not bad and any(h.get('reason') == 'request_parameter_conflict' for h in frames)
        assert not any('credential' in h for h in frames)
    finally:
        stop_fixture(hub)


def test_confirmed_claim_cannot_be_replayed_to_restore_a_cleared_password(tmp_path):
    hub = fresh_hub(tmp_path)
    try:
        ok, user, _ = attempt(hub, '合成确认后清除', 'synthetic-old', claim=True, rid='old_claim')
        assert ok
        assert update(hub, user, 'synthetic-old', '', 'clear')['status'] == 'confirmed'
        ok, rejected, frames = attempt(hub, user.nick, 'synthetic-old', claim=True, rid='old_claim')
        assert not ok and rejected.uid == 0
        assert not hub.known[user.uid].get('pwd')
        assert 'pwd' not in persisted(tmp_path)['known'][str(user.uid)]
        assert not any('credential' in h for h in frames)
    finally:
        stop_fixture(hub)


def test_pending_claim_duplicate_is_inline_only_without_second_derivation(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    original = auth.make
    entered, release = threading.Event(), threading.Event()
    results, calls = [], []

    def make(password):
        if password == 'synthetic-pending':
            calls.append(True)
            entered.set()
            assert release.wait(5)
        return original(password)

    monkeypatch.setattr(auth, 'make', make)
    thread = threading.Thread(target=lambda: results.append(
        attempt(hub, '合成处理中重复', 'synthetic-pending', claim=True, rid='same')))
    try:
        thread.start()
        assert entered.wait(5)
        ok, sess, frames = attempt(hub, '合成处理中重复', 'synthetic-pending', claim=True, rid='same')
        assert not ok and sess.uid == 0 and calls == [True]
        pending = next(h['credential'] for h in frames if 'credential' in h)
        assert pending['status'] == 'pending' and pending['login_status'] == 'not_attached'
        release.set()
        join(thread)
        assert results[0][0]
        confirmed = next(h['credential'] for h in results[0][2] if h.get('t') == 'welcome')
        assert confirmed['operation_id'] == pending['operation_id']
    finally:
        release.set()
        join(thread)
        stop_fixture(hub)


def test_already_bound_claim_is_recorded_without_fake_commit_and_cannot_later_bind(tmp_path):
    hub = fresh_hub(tmp_path)
    try:
        ok, user, _ = attempt(hub, '合成已绑定声明', 'synthetic-old', claim=True, rid='first')
        assert ok
        ok, _, frames = attempt(hub, user.nick, 'synthetic-old', claim=True, rid='already_bound')
        assert ok
        receipt = next(h['credential'] for h in frames if h.get('t') == 'welcome')
        assert receipt['status'] == 'failed' and receipt['reason'] == 'credential_already_bound'
        assert receipt['login_status'] == 'attached' and 'persisted' not in receipt
        assert update(hub, user, 'synthetic-old', '', 'clear')['status'] == 'confirmed'
        ok, sess, frames = attempt(hub, user.nick, 'synthetic-old', claim=True, rid='already_bound')
        assert not ok and sess.uid == 0 and not hub.known[user.uid].get('pwd')
        again = next(h['credential'] for h in frames if 'credential' in h)
        assert again['operation_id'] == receipt['operation_id'] and again['status'] == 'failed'
    finally:
        stop_fixture(hub)


def test_deployment_admin_password_is_not_subject_to_nickname_new_password_limit(tmp_path):
    secret = 'synthetic-deployment-secret-' * 5
    hub = Hub(cfg=replace(config_for(tmp_path), admin_pwd=secret))
    try:
        ok, admin, frames = attempt(hub, hub._admin_nick, secret)
        assert ok and admin.is_admin
        assert next(h for h in frames if h.get('t') == 'welcome')['is_admin'] is True
        assert 'pwd' not in hub.known[admin.uid]
    finally:
        hub.shutdown(normal=False)


def test_existing_legacy_long_password_can_authenticate_and_change(tmp_path):
    hub = fresh_hub(tmp_path)
    long_password = 'synthetic-existing-secret-' * 5
    try:
        user, _ = login(hub, '合成既有长密码')
        # A synthetic historical digest, created by the old unrestricted claim
        # path. No plaintext or actual user Store is imported.
        with hub.lock:
            hub.known[user.uid]['pwd'] = auth.make(long_password)
        assert hub._persist(force=True)
        ok, current, _ = attempt(hub, user.nick, long_password)
        assert ok and current.uid == user.uid
        result = update(hub, current, long_password, 'synthetic-short-new', 'long_to_new')
        assert result['status'] == 'confirmed'
        assert auth.verify('synthetic-short-new', persisted(tmp_path)['known'][str(user.uid)]['pwd'])
    finally:
        stop_fixture(hub)
