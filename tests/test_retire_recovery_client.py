"""Receipt phase truthfulness and actual Tk result-widget text (not native QA)."""
import itertools

import pytest

from retirement_status import Receipt, RetirementBook, RetirementError, Scope
from test_retirement_status_gui import app


VALID = {
    ('pending', 'intent', 'not_started'), ('pending', 'snapshot', 'revoked'),
    ('failed', 'intent', 'not_started'), ('failed', 'snapshot', 'revoked'),
    ('unknown', 'intent', 'unverified'), ('unknown', 'snapshot', 'revoked'),
    ('confirmed', 'snapshot', 'revoked'),
}


def receipt(status='failed', **extra):
    return dict(status=status, operation_id='synthetic-operation', target_uid=7,
                target_nick='样例#2', retryable=status == 'failed', **extra)


@pytest.mark.parametrize('status,phase,effect', list(itertools.product(
    ('pending', 'failed', 'unknown', 'confirmed'), ('intent', 'snapshot'),
    ('not_started', 'revoked', 'unverified'))))
def test_exact_phase_effect_matrix(status, phase, effect):
    value = receipt(status, persistence_phase=phase, identity_effect=effect)
    if (status, phase, effect) in VALID:
        result = Receipt.parse(value, 7, '样例#2')
        assert result.persistence_phase == phase and result.identity_effect == effect
    else:
        with pytest.raises(RetirementError, match='阶段组合'):
            Receipt.parse(value, 7, '样例#2')


@pytest.mark.parametrize('extra', [
    {'persistence_phase': 'intent'}, {'identity_effect': 'not_started'},
    {'persistence_phase': None, 'identity_effect': None},
    {'persistence_phase': None, 'identity_effect': 'not_started'},
    {'persistence_phase': 'intent', 'identity_effect': None},
    {'persistence_phase': 'other', 'identity_effect': 'not_started'},
    {'persistence_phase': [], 'identity_effect': {}},
])
def test_partial_null_unknown_and_bad_types_are_invalid_evidence(extra):
    with pytest.raises(RetirementError):
        Receipt.parse(receipt(**extra), 7, '样例#2')


def test_legacy_receipt_never_infers_an_identity_effect():
    for status in ('pending', 'failed', 'unknown', 'confirmed'):
        result = Receipt.parse(receipt(status), 7, '样例#2')
        assert result.persistence_phase is None and result.identity_effect is None


@pytest.mark.parametrize('status', ['pending', 'failed', 'unknown'])
@pytest.mark.parametrize('proof', [
    {'origin': 'written'}, {'origin': 'restored_valid_json'},
    {'origin': 'reconciled_current_json'}, {'content_sha256': 'a' * 64}, {'content_length': 0},
])
def test_unconfirmed_result_cannot_supply_confirmation_proof(status, proof):
    with pytest.raises(RetirementError, match='未确认'):
        Receipt.parse(receipt(status, **proof), 7, '样例#2')


def deliver(book, value):
    request = book.begin(7, nick='样例#2', purpose='query')
    book.receive({'t': 'admin_user_info', 'request_id': request.request_id,
                  'uid': 7, 'nick': '样例#2', 'retirement': value}, 1)


def test_invalid_new_phase_preserves_confirmation_and_allows_only_query():
    book = RetirementBook()
    book.connect(Scope('127.0.0.1', 9527, 1), 1)
    deliver(book, receipt('confirmed', persistence_phase='snapshot', identity_effect='revoked'))
    original = book.snapshot()[0].confirmed
    deliver(book, receipt('failed', persistence_phase='intent', identity_effect='revoked'))
    view = book.snapshot()[0]
    assert view.confirmed is original and view.phase == 'unverified'
    assert view.can_query and not view.can_retry and not view.can_cancel
    assert not view.current_verified


def test_result_widget_transitions_display_each_phase_without_inference(app):
    window, _, _ = app
    window._retirement_results()
    for status, phase, effect, expected in [
        ('failed', 'intent', 'not_started', '尚未开始撤权'),
        ('failed', 'snapshot', 'revoked', '已撤销身份权限'),
        ('unknown', 'intent', 'unverified', '撤权效果未核实'),
        ('confirmed', 'snapshot', 'revoked', '已撤销身份权限'),
        ('failed', None, None, '未提供撤权阶段'),
    ]:
        # Independent server observations in one existing results window;
        # also checks that refresh does not leave text from its previous row.
        book = RetirementBook()
        book.connect(Scope('127.0.0.1', 9527, 1), 1)
        window.core.retirement_snapshot = book.snapshot
        extra = {} if phase is None else {'persistence_phase': phase, 'identity_effect': effect}
        deliver(book, receipt(status, **extra))
        window._refresh_retirement_results()
        window.root.update()
        text = window._retirement_ui['detail'].get('1.0', 'end')
        assert expected in text
        if effect != 'revoked':
            assert '已撤销身份权限' not in text
        assert window._RETIRE_STATES[status] in text
        if phase is not None:
            assert ('退役意图' if phase == 'intent' else '状态快照') in text
