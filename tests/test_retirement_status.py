"""Behavioral retirement-state matrix, with explicit clock/receipt ordering."""
from dataclasses import FrozenInstanceError

import pytest

from retirement_status import RetirementBook, RetirementError, Scope


SCOPE = Scope('127.0.0.1', 9527, 1)


@pytest.fixture
def model():
    now = [0.0]
    book = RetirementBook(clock=lambda: now[0])
    book.connect(SCOPE, 1)
    return book, now


def info(request, status=None, **changes):
    result = {'t': 'admin_user_info', 'request_id': request.request_id,
              'uid': 7, 'nick': 'target', 'online': False, 'groups': []}
    if status:
        result['retirement'] = {'status': status, 'operation_id': 'operation-7',
                                'target_uid': 7, 'target_nick': 'target',
                                'origin': None, 'content_sha256': None, 'content_length': None,
                                'failed_stage': None, 'error_code': None,
                                'retryable': status == 'failed'}
        result['retirement'].update(changes)
    else:
        result.update(changes)
    return result


def start_delete(book):
    preflight = book.begin(7, nick='target', purpose='preflight')
    assert preflight.frame()['t'] == 'admin_user_get'
    outcome = book.receive(info(preflight), 1)
    assert len(outcome.outbound) == 1
    return outcome.outbound[0]


def test_fresh_confirmation_preflights_once_before_delete(model):
    book, _ = model
    preflight = book.begin(7, nick='target', purpose='preflight')
    view = book.snapshot()[0]
    assert view.phase == 'preflight' and not view.ever_del and view.can_cancel
    with pytest.raises(RetirementError):
        book.begin('target', purpose='preflight')
    reply = info(preflight)
    delete, = book.receive(reply, 1).outbound
    assert delete.frame()['t'] == 'admin_user_del'
    assert delete.request_id != preflight.request_id and len(delete.request_id) == 32
    assert 'operation_id' not in delete.frame()
    assert book.receive(reply, 1).outbound == ()
    assert book.snapshot()[0].ever_del


@pytest.mark.parametrize('status', ['pending', 'failed', 'unknown', 'confirmed'])
def test_existing_server_operation_never_auto_deletes(model, status):
    book, _ = model
    request = book.begin(7, nick='target', purpose='preflight')
    assert not book.receive(info(request, status), 1).outbound
    view = book.snapshot()[0]
    assert view.receipt.status == status and not view.ever_del
    assert view.can_retry == (status == 'failed')
    query = book.query(view.intent_id)
    assert query.frame()['operation_id'] == 'operation-7'
    assert query.frame()['t'] == 'admin_user_get'


def test_fast_receipt_wins_over_later_send_failure(model):
    book, _ = model
    delete = start_delete(book)
    book.receive(info(delete, 'pending'), 1)
    book.sent(delete.request_id, 1, False)
    assert book.snapshot()[0].phase == 'pending'
    book.receive(info(delete, 'confirmed', origin='written'), 1)
    assert book.snapshot()[0].confirmed.origin == 'written'


def test_partial_send_failure_is_unknown_and_only_queries(model):
    book, _ = model
    delete = start_delete(book)
    book.sent(delete.request_id, 1, False)
    view = book.snapshot()[0]
    assert view.phase == 'unknown' and view.can_query and not view.can_retry
    request = book.begin(7, nick='target', purpose='preflight')
    assert request.purpose == 'query'
    assert not book.receive(info(request), 1).outbound
    assert book.snapshot()[0].phase == 'unverified'


@pytest.mark.parametrize('ending', ['cancel', 'timeout', 'disconnect', 'no_echo'])
def test_invalidated_preflight_cannot_send_delete(model, ending):
    book, now = model
    request = book.begin(7, nick='target', purpose='preflight')
    reply = info(request)
    if ending == 'cancel':
        assert book.cancel(request.intent_id)
    elif ending == 'timeout':
        now[0] = 11
    elif ending == 'disconnect':
        book.disconnect(1)
        book.connect(SCOPE, 2)
    else:
        reply.pop('request_id')
    assert not book.receive(reply, 1).outbound
    assert not book.snapshot()[0].ever_del


@pytest.mark.parametrize('bad', [None, {}, [], 'confirmed',
                               {'status': 'confirmed', 'operation_id': 'op'},
                               {'status': 'failed', 'target_uid': 7, 'target_nick': 'target',
                                'operation_id': 'op', 'retryable': 'true'}])
def test_present_but_invalid_retirement_is_not_absence_or_retry(model, bad):
    book, _ = model
    request = book.begin(7, nick='target', purpose='preflight')
    assert not book.receive(info(request, retirement=bad), 1).outbound
    assert not book.snapshot()[0].can_retry
    fresh = book.begin(7, nick='target', purpose='preflight')
    assert fresh.purpose == 'query'
    assert not book.receive(info(fresh), 1).outbound


@pytest.mark.parametrize('changes', [{'target_uid': True}, {'target_uid': 8}, {'target_nick': 'other'},
                                   {'status': 'success'}, {'operation_id': ''}, {'origin': 'invented'},
                                   {'content_sha256': 'x'*64}, {'content_length': True},
                                   {'content_length': -1}, {'failed_stage': {}}, {'retryable': None}])
def test_invalid_receipt_fields_cannot_confirm(model, changes):
    book, _ = model
    request = book.begin(7, purpose='query')
    frame = info(request, 'confirmed')
    frame['retirement'].update(changes)
    book.receive(frame, 1)
    assert book.snapshot()[0].confirmed is None
    assert not book.snapshot()[0].can_retry


def test_wrong_outer_target_id_epoch_and_unlinked_error_do_not_correlate(model):
    book, _ = model
    delete = start_delete(book)
    baseline = book.snapshot()
    frame = info(delete, 'confirmed')
    frame['request_id'] = 'different'
    book.receive(frame, 1)
    book.receive(info(delete, 'confirmed'), 0)
    book.receive({'t': 'error', 'code': 'forbid'}, 1)
    assert book.snapshot() == baseline
    frame = info(delete, 'confirmed')
    frame['uid'] = 8
    book.receive(frame, 1)
    assert book.snapshot()[0].confirmed is None


def test_old_attempt_failure_cannot_override_retry_but_confirmation_can(model):
    book, _ = model
    first = start_delete(book)
    book.receive(info(first, 'failed'), 1)
    retry = book.retry(first.intent_id)
    assert retry.frame()['operation_id'] == 'operation-7'
    assert retry.request_id != first.request_id
    book.receive(info(retry, 'pending'), 1)
    book.receive(info(first, 'failed'), 1)
    assert book.snapshot()[0].receipt.status == 'pending'
    book.receive(info(first, 'confirmed'), 1)
    book.receive(info(retry, 'failed'), 1)
    view = book.snapshot()[0]
    assert view.receipt.status == 'confirmed' and view.confirmed
    assert not view.can_retry


def test_failed_must_be_retryable_and_verified_in_current_connection(model):
    book, _ = model
    delete = start_delete(book)
    book.receive(info(delete, 'failed', retryable=False), 1)
    with pytest.raises(RetirementError):
        book.retry(delete.intent_id)
    query = book.query(delete.intent_id)
    book.receive(info(query, 'failed'), 1)
    assert book.snapshot()[0].can_retry
    book.disconnect(1)
    book.connect(SCOPE, 2)
    with pytest.raises(RetirementError):
        book.retry(delete.intent_id)
    query = book.query(delete.intent_id)
    assert query.frame()['operation_id'] == 'operation-7'
    book.receive(info(query, 'failed'), 2)
    assert book.retry(delete.intent_id).epoch == 2


@pytest.mark.parametrize('next_scope', [Scope('127.0.0.2', 9527, 1), Scope('127.0.0.1', 9530, 1),
                                      Scope('127.0.0.1', 9527, 2)])
def test_same_core_history_survives_missing_restart_record_and_scope_changes(model, next_scope):
    book, _ = model
    delete = start_delete(book)
    book.receive(info(delete, 'failed'), 1)
    book.disconnect(1)
    book.connect(SCOPE, 2)
    query = book.query(delete.intent_id)
    book.receive(info(query), 2)
    view = book.snapshot()[0]
    assert view.phase == 'unverified' and not view.can_retry
    preflight = book.begin(7, nick='target', purpose='preflight')
    assert preflight.purpose == 'query'
    book.connect(next_scope, 3)
    with pytest.raises(RetirementError):
        book.query(delete.intent_id)
    other = book.begin(7, purpose='query')
    assert 'operation_id' not in other.frame()
    book.connect(None, 4)
    with pytest.raises(RetirementError):
        book.begin(7)


def test_confirmation_fence_is_epoch_bound_but_not_removed_by_query_error(model):
    book, _ = model
    delete = start_delete(book)
    book.receive(info(delete, 'confirmed'), 1)
    query = book.query(delete.intent_id)
    book.receive({'t': 'error', 'request_id': query.request_id, 'code': 'operation_id'}, 1)
    assert book.confirmed_uids(1) == frozenset({7})
    assert book.snapshot()[0].confirmed and not book.snapshot()[0].current_verified
    book.connect(SCOPE, 2)
    assert not book.confirmed_uids(2)
    assert book.snapshot()[0].confirmed and not book.snapshot()[0].current_verified
    book.receive(info(delete, 'confirmed'), 1)
    assert not book.confirmed_uids(2)


def test_new_query_contradiction_separates_current_verification_from_confirmed_history(model):
    book, _ = model
    delete = start_delete(book)
    book.receive(info(delete, 'confirmed'), 1)
    query = book.query(delete.intent_id)
    book.receive(info(query, 'failed'), 1)
    view = book.snapshot()[0]
    assert view.confirmed and view.phase == 'unverified'
    assert not view.current_verified and not view.can_retry
    assert book.confirmed_uids(1) == frozenset({7})


def test_detail_and_legacy_details_never_authorize_retirement(model):
    book, _ = model
    request = book.begin(7, purpose='detail')
    reply = info(request)
    reply.pop('request_id')
    out = book.receive(reply, 1)
    assert out.detail['correlated'] is False and not out.outbound
    assert not book.snapshot()[0].ever_del
    request = book.begin(7, purpose='detail')
    out = book.receive(info(request, 'failed'), 1)
    assert out.detail['correlated'] is True and not out.outbound
    request = book.begin(7, nick='target', purpose='preflight')
    assert request.purpose == 'query'


def test_concurrent_alias_resolution_merges_and_cancels_duplicate_authority(model):
    book, _ = model
    book.begin(7, purpose='query')  # UID not yet associated with its server nickname
    alias = book.begin('target', purpose='preflight')
    assert len(book.snapshot()) == 2
    assert not book.receive(info(alias), 1).outbound
    assert len(book.snapshot()) == 1
    assert not book.snapshot()[0].ever_del


def test_capacity_never_evicts_confirmed_or_uncertain_history():
    book = RetirementBook(limit=1)
    book.connect(SCOPE, 1)
    delete = start_delete(book)
    book.receive(info(delete, 'confirmed'), 1)
    with pytest.raises(RetirementError):
        book.begin(8, purpose='query')
    assert book.query(delete.intent_id).frame()['operation_id'] == 'operation-7'


def test_terminal_unsubmitted_preflight_can_be_evicted_without_dropping_history():
    now = [0.0]
    book = RetirementBook(limit=1, clock=lambda: now[0])
    book.connect(SCOPE, 1)
    request = book.begin(7, nick='target', purpose='preflight')
    now[0] = 11
    book.snapshot()
    newer = book.begin(8, purpose='query')
    assert newer.intent_id != request.intent_id
    assert not book.receive(info(request), 1).outbound


def test_request_ledger_is_bounded_and_latest_operation_never_changes(model):
    book, _ = model
    delete = start_delete(book)
    for _ in range(8):
        book.receive(info(delete, 'failed'), 1)
        delete = book.retry(delete.intent_id)
    assert len(book._requests) <= 3  # one active mutation + two retired attempt IDs
    frame = info(delete, 'confirmed', operation_id='different-op')
    book.receive(frame, 1)
    view = book.snapshot()[0]
    assert view.confirmed is None and view.receipt.operation_id == 'operation-7'
    with pytest.raises(FrozenInstanceError):
        view.phase = 'confirmed'
    with pytest.raises(FrozenInstanceError):
        view.receipt.status = 'confirmed'


@pytest.mark.parametrize('status', ['failed', 'unknown'])
@pytest.mark.parametrize('late', ['pending', 'failed', 'unknown', 'error', 'send_true', 'send_false'])
def test_newer_query_observation_blocks_older_nonconfirmation_and_send_result(model, status, late):
    book, _ = model
    delete = start_delete(book)
    query = book.query(delete.intent_id)
    book.receive(info(query, status), 1)
    expected = book.snapshot()
    if late.startswith('send_'):
        book.sent(delete.request_id, 1, late == 'send_true')
    elif late == 'error':
        book.receive({'t': 'error', 'request_id': delete.request_id, 'code': 'store_required'}, 1)
    else:
        book.receive(info(delete, late), 1)
    assert book.snapshot() == expected
    # Historical attempt still can supply the same operation's durable proof.
    book.receive(info(delete, 'confirmed'), 1)
    assert book.snapshot()[0].confirmed


@pytest.mark.parametrize('success', [True, False])
def test_older_send_return_cannot_override_new_retry_without_old_receipt(model, success):
    book, _ = model
    delete = start_delete(book)
    query = book.query(delete.intent_id)
    book.receive(info(query, 'failed'), 1)
    retry = book.retry(delete.intent_id)
    assert retry.purpose == 'retry'
    expected = book.snapshot()
    book.sent(delete.request_id, 1, success)
    assert book.snapshot() == expected


def test_reusing_disconnected_epoch_cannot_accept_unlinked_old_detail(model):
    book, _ = model
    old = book.begin(7, purpose='detail')
    book.disconnect(1)
    assert book.connect(SCOPE, 1) is False
    with pytest.raises(RetirementError):
        book.begin(7, purpose='detail')
    assert book.connect(SCOPE, 2)
    book.begin(7, purpose='detail')
    reply = info(old)
    reply.pop('request_id')
    assert book.receive(reply, 1).detail is None


def test_pending_epoch_can_authenticate_once_but_disconnect_revokes_authority():
    book = RetirementBook()
    assert book.begin_connection(1)
    assert book.authenticate(SCOPE, 1)
    assert not book.authenticate(Scope('other', 9, 2), 1)
    assert book.begin_connection(2)
    book.disconnect(2)
    assert not book.authenticate(SCOPE, 2)
    assert not book.begin_connection(2)


@pytest.mark.parametrize('uid', [0, -1, True, '1'])
def test_invalid_admin_identity_never_produces_outbound(uid):
    book = RetirementBook()
    with pytest.raises(RetirementError):
        book.connect(Scope('127.0.0.1', 9527, uid), 1)
    assert not book.authenticate(SCOPE, 1)
    with pytest.raises(RetirementError):
        book.begin(7)
