"""Reject ambiguous input; never turn a replay into another credential write."""
import base64
import json
import struct
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from credential_ops import (ClaimLedger, CredentialError, CredentialResult, LoginIntent,
                            OperationLedger, QueryRequest, UpdateRequest,
                            WebContext, strict_json)


EPOCH = 'a' * 32
SCOPE = 'b' * 32


def update(rid='set_1', old='synthetic-old', new='synthetic-new'):
    return UpdateRequest.parse({'credential_v': 1, 'request_id': rid,
                                'old': old, 'new': new}, password_max=64)


def query(original='set_1', op=None, epoch=EPOCH):
    return QueryRequest.parse({'credential_v': 1, 'request_id': 'query_1',
                               'original_request_id': original,
                               'operation_id': op, 'operation_epoch': epoch})


@pytest.mark.parametrize('change', [
    {'credential_v': True}, {'credential_v': 2}, {'credential_v': '1'},
    {'request_id': ''}, {'request_id': 'x' * 65}, {'request_id': '换密'},
    {'request_id': 'a\n'}, {'old': None}, {'new': None}, {'new': False},
    {'old': ['secret']}, {'new': {'secret': 'value'}}, {'new': 'x' * 65},
])
def test_update_rejects_ambiguous_input_without_echoing_secrets(change):
    raw = {'credential_v': 1, 'request_id': 'set_1',
           'old': 'synthetic-old', 'new': 'synthetic-new', **change}
    with pytest.raises(CredentialError) as caught:
        UpdateRequest.parse(raw, password_max=64)
    assert 'synthetic' not in str(caught.value)
    assert 'secret' not in str(caught.value)


def test_missing_new_is_not_a_clear_intent_and_empty_new_is_explicit_clear():
    with pytest.raises(CredentialError, match='invalid_password_fields'):
        UpdateRequest.parse({'credential_v': 1, 'request_id': 'clear'}, password_max=64)
    assert update(new='').new == ''
    assert 'synthetic-old' not in repr(update())
    assert 'synthetic-new' not in repr(update())


@pytest.mark.parametrize('raw', [
    '{"new":"first","new":"second"}', '{"nested":{"uid":1,"uid":2}}',
    '{"value":NaN}', '{"value":Infinity}', '{"value":1e999}',
    b'\xff', '{',
])
def test_strict_json_rejects_duplicate_or_nonfinite_input(raw):
    with pytest.raises(CredentialError, match='invalid_json'):
        strict_json(raw)


@pytest.mark.parametrize('raw', [
    b'{"t":"set_pwd","credential_v":1,"new":"first","new":"second"}',
    b'{"t":"set_pwd","credential_v":NaN,"new":"synthetic"}',
])
def test_actual_frame_reader_rejects_ambiguous_credential_headers(raw):
    from protocol import FrameReader, ProtocolError
    with pytest.raises(ProtocolError):
        FrameReader().feed(struct.pack('>I', len(raw)) + raw)


def test_login_claim_requires_explicit_version_and_typed_context():
    assert LoginIntent.parse({}).claim_password is False
    with pytest.raises(CredentialError, match='credential_upgrade_required'):
        LoginIntent.parse({'claim_password': True})
    valid = {'auth_v': 1, 'request_id': 'hello', 'expected_server_epoch': EPOCH,
             'expected_store_scope_id': SCOPE, 'claim_password': True}
    assert LoginIntent.parse(valid).claim_password is True
    assert LoginIntent.parse({**valid, 'expected_store_scope_id': None}).store_scope_id is None
    for changes in ({'claim_password': 1}, {'auth_v': True},
                    {'expected_server_epoch': 'a' * 8 + '-' + 'a' * 23},
                    {'expected_store_scope_id': ''}):
        with pytest.raises(CredentialError):
            LoginIntent.parse({**valid, **changes})
    del valid['expected_store_scope_id']
    with pytest.raises(CredentialError):
        LoginIntent.parse(valid)


def test_same_operation_is_not_reexecuted_and_conflicting_parameters_reject():
    ledger = OperationLedger(EPOCH)
    first, fresh = ledger.begin(5, update())
    assert fresh and first.status == 'pending'
    again, fresh = ledger.begin(5, update())
    assert not fresh and again == first
    with pytest.raises(CredentialError, match='request_parameter_conflict'):
        ledger.begin(5, update(new='different'))
    result = ledger.finish(first, status='confirmed')
    again, fresh = ledger.begin(5, update())
    assert not fresh and again == result
    assert ledger.finish(first, status='failed', reason='late_failure') == result


def test_simultaneous_replays_admit_exactly_one_operation():
    ledger = OperationLedger(EPOCH)
    barrier = threading.Barrier(8)

    def begin():
        barrier.wait(timeout=5)
        return ledger.begin(5, update())

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: begin(), range(8)))
    assert sum(fresh for _, fresh in results) == 1
    assert len({result.operation_id for result, _ in results}) == 1


def test_failed_and_unknown_request_ids_remain_terminal():
    ledger = OperationLedger(EPOCH)
    for index, status in enumerate(('failed', 'unknown')):
        request = update(rid=f'set_{index}')
        operation, _ = ledger.begin(5, request)
        terminal = ledger.finish(operation, status=status, reason='injected', retryable=True)
        assert terminal.retryable is (status == 'failed')
        assert ledger.begin(5, request) == (terminal, False)
    assert ledger.begin(5, update(rid='explicit_new'))[1]


def test_query_is_owner_epoch_and_operation_specific_and_does_not_allocate():
    ledger = OperationLedger(EPOCH)
    operation, _ = ledger.begin(5, update())
    terminal = ledger.finish(operation, status='confirmed')
    assert ledger.query(5, query(op=operation.operation_id)) == terminal
    assert ledger.query(5, query()) == terminal
    for uid, req in ((6, query()), (5, query(epoch='c' * 32)),
                     (5, query(op='d' * 32)), (5, query(original='missing'))):
        result = ledger.query(uid, req)
        assert result.status == 'unknown' and result.reason == 'operation_unavailable'
        assert 'persisted' not in result.payload(server_epoch=EPOCH, query_request_id='query_1')
    assert len(ledger._entries) == 1


def test_capacity_preserves_active_and_terminal_idempotency_and_queries():
    ledger = OperationLedger(EPOCH, capacity=2, max_active=1)
    first, _ = ledger.begin(5, update())
    with pytest.raises(CredentialError, match='credential_capacity'):
        ledger.begin(6, update())
    first = ledger.finish(first, status='confirmed')
    second, _ = ledger.begin(6, update())
    ledger.finish(second, status='failed', reason='injected')
    with pytest.raises(CredentialError, match='credential_capacity'):
        ledger.begin(5, update(rid='new_id'))
    assert ledger.begin(5, update()) == (first, False)
    assert ledger.query(5, query()) == first


def test_receipt_contains_only_result_fields_never_passwords_mac_or_revision():
    ledger = OperationLedger(EPOCH)
    operation, _ = ledger.begin(5, update())
    confirmed = ledger.finish(operation, status='confirmed')
    payload = confirmed.payload(server_epoch=EPOCH, query_request_id='query_1')
    assert payload['persisted'] is True
    assert payload['request_id'] == 'query_1' and payload['original_request_id'] == 'set_1'
    assert payload['status'] == payload['credential_status'] == 'confirmed'
    assert not {'old', 'new', 'password', 'pwd', 'input_mac', 'revision'} & payload.keys()
    assert 'synthetic' not in json.dumps(payload)
    not_attached = CredentialResult('claim', 'd' * 32, EPOCH, 5,
                                    status='confirmed', login_status='not_attached')
    assert not_attached.payload(server_epoch=EPOCH)['login_status'] == 'not_attached'


def test_web_context_is_strict_and_volatile_null_is_not_missing():
    context = WebContext(EPOCH, SCOPE, 5, 'd' * 32)
    assert WebContext.decode(context.encode()) == context
    volatile = WebContext(EPOCH, None, 5, 'd' * 32)
    assert WebContext.decode(volatile.encode()).store_scope_id is None
    for value in ('', context.encode() + '=', '@invalid', 'a' * 513):
        with pytest.raises(CredentialError, match='context_invalid'):
            WebContext.decode(value)
    for changes in ({'v': True}, {'uid': True}, {'uid': 0},
                    {'store_scope_id': ''}, {'session_binding_id': 'D' * 32},
                    {'token': 'not-a-context-field'}):
        encoded = base64.urlsafe_b64encode(json.dumps({**context.payload(), **changes}).encode()).rstrip(b'=').decode()
        with pytest.raises(CredentialError, match='context_invalid'):
            WebContext.decode(encoded)


def test_claim_table_covers_effectful_input_retains_terminal_and_has_no_query():
    from dataclasses import replace
    ledger = ClaimLedger(EPOCH, capacity=1, max_active=1)
    intent = LoginIntent(1, 'claim', EPOCH, SCOPE, True)
    first, fresh = ledger.begin('合成昵称', 'synthetic-password', intent)
    assert fresh and first.status == 'pending'
    assert ledger.begin('合成昵称', 'synthetic-password', intent) == (first, False)
    for password, changed in (('different', intent),
                              ('synthetic-password', replace(intent, store_scope_id='c' * 32))):
        with pytest.raises(CredentialError, match='request_parameter_conflict'):
            ledger.begin('合成昵称', password, changed)
    with pytest.raises(CredentialError, match='credential_capacity'):
        ledger.begin('另一个昵称', 'synthetic-password', intent)
    failed = replace(first, status='failed', reason='injected', login_status='attached')
    assert ledger.finish('合成昵称', failed) == failed
    repeated, fresh = ledger.begin('合成昵称', 'synthetic-password', intent)
    assert not fresh and repeated.status == 'failed' and repeated.login_status == 'not_attached'
    with pytest.raises(CredentialError, match='credential_capacity'):
        ledger.begin('合成昵称', 'synthetic-password', replace(intent, request_id='new'))
    assert not hasattr(ledger, 'query')
