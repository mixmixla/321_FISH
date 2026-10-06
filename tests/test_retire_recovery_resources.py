"""Durable retirement versus resource C/G and retained shared bodies."""
import os
from pathlib import Path
import threading
import uuid

import pytest

from server import Hub
from test_cc02c_resource_files import _begin, _context, RESOURCE_A, RESOURCE_B
from test_retire_recovery_hub import fresh_hub, people, retire, stop_fixture, config_for


def seed_resources(hub, user, survivor):
    hub._on_cloud_put(user, {'t': 'cloud_put'}, RESOURCE_A)
    hub._on_cloud_put(survivor, {'t': 'cloud_put'}, RESOURCE_B)
    fid = uuid.uuid4().hex
    ctx = _context(_begin(hub, user, kind='web_file', key=fid, op=None,
                          payload=RESOURCE_A, name='synthetic.txt', kind_name='file'))
    assert hub._resource_file_commit(ctx, RESOURCE_A, {'name': 'synthetic.txt', 'kind': 'file'})['status'] == 'confirmed'
    assert hub._persist(force=True)
    return fid


@pytest.mark.parametrize('point', ['before_c', 'after_c'])
def test_actual_retirement_crosses_resource_io_without_waiting_or_reviving_private_index(tmp_path, monkeypatch, point):
    hub = fresh_hub(tmp_path)
    admin, _, user, survivor = people(hub)
    fid = seed_resources(hub, user, survivor)
    entered, release, retired = threading.Event(), threading.Event(), threading.Event()
    original_stage, original_replace = hub._resource_stage_bytes, os.replace
    private_path = Path(hub.cloud_dir) / f'{user.uid}.bin'
    errors = []
    if point == 'before_c':
        def pause_stage(data, suffix):
            entered.set()
            assert release.wait(5)
            return original_stage(data, suffix)
        monkeypatch.setattr(hub, '_resource_stage_bytes', pause_stage)
    else:
        def pause_replace(source, target):
            original_replace(source, target)
            if Path(target) == private_path:
                entered.set()
                assert release.wait(5)
        monkeypatch.setattr(os, 'replace', pause_replace)
    def upload():
        try:
            hub._on_cloud_put(user, {'t': 'cloud_put'}, RESOURCE_B)
        except BaseException as exc:
            errors.append(exc)
    def delete():
        try:
            retire(hub, admin, user.uid)
        except BaseException as exc:
            errors.append(exc)
        finally:
            retired.set()
    upload_thread, retire_thread = threading.Thread(target=upload), threading.Thread(target=delete)
    try:
        upload_thread.start()
        assert entered.wait(5)
        retire_thread.start()
        assert retired.wait(4), 'Resource IO must not retain Hub/G or block t0/state commit'
        assert not errors and hub._retirement_payload(user.uid)['status'] == 'confirmed'
        assert user.closed and user.uid not in hub.cloud
        assert not hub._session_is_active(user) and hub._session_is_active(survivor)
        hub._on_chat(user, {'t': 'chat', 'channel': 'public', 'text': 'late-denied'})
        assert not any(m.get('text') == 'late-denied' for m in hub.bus.history('all'))
        release.set()
        upload_thread.join(5)
        retire_thread.join(5)
        assert not upload_thread.is_alive() and not retire_thread.is_alive() and not errors
        ctx = next(c for c in reversed(list(hub._resource_ops.values()))
                   if c['owner_uid'] == user.uid and c['kind'] == 'cloud')
        result = hub._resource_query(admin, ctx['resource_operation_id'], explicit_owner=user.uid)
        assert result['status'] == ('failed' if point == 'before_c' else 'confirmed')
        assert result['visibility'] == 'withdrawn'
        with pytest.raises(PermissionError):
            hub._resource_query(user, ctx['resource_operation_id'])
        assert user.uid not in hub.cloud and survivor.uid in hub.cloud
        assert private_path.read_bytes() == (RESOURCE_A if point == 'before_c' else RESOURCE_B)
        assert hub._read_web_resource(fid)[1] == RESOURCE_A
    finally:
        release.set()
        if upload_thread.ident:
            upload_thread.join(5)
        if retire_thread.ident:
            retire_thread.join(5)
        monkeypatch.undo()
        stop_fixture(hub)


def test_g_only_summary_finishes_while_retirement_holds_hub_waiting_for_g(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    admin, _, user, survivor = people(hub)
    seed_resources(hub, user, survivor)
    accepted, allow_t0, summary_entered, release_g, core_done = (threading.Event() for _ in range(5))
    original_accept = hub._recovery.accept_intent
    original_result, original_core = hub._resource_public_result, hub._apply_retirement_core_locked
    outputs, errors = [], []
    def accept(*args):
        result = original_accept(*args)
        accepted.set()
        assert allow_t0.wait(5)
        return result
    def public_result(ctx):
        if threading.current_thread().name == 'synthetic-g-summary':
            summary_entered.set()
            assert release_g.wait(5)
        return original_result(ctx)
    def core(*args):
        effects = original_core(*args)
        core_done.set()
        return effects
    monkeypatch.setattr(hub._recovery, 'accept_intent', accept)
    monkeypatch.setattr(hub, '_resource_public_result', public_result)
    monkeypatch.setattr(hub, '_apply_retirement_core_locked', core)
    def delete():
        try:
            retire(hub, admin, user.uid)
        except BaseException as exc:
            errors.append(exc)
    retire_thread = threading.Thread(target=delete)
    summary_thread = threading.Thread(target=lambda: outputs.append(hub._resource_summary(user.uid)),
                                      name='synthetic-g-summary')
    try:
        retire_thread.start()
        assert accepted.wait(5)
        summary_thread.start()
        assert summary_entered.wait(5)
        allow_t0.set()
        assert core_done.wait(5)
        assert retire_thread.is_alive()  # t0 owns Hub and awaits summary's G.
        release_g.set()
        summary_thread.join(4)
        retire_thread.join(4)
        assert not summary_thread.is_alive() and not retire_thread.is_alive()
        assert outputs and not errors
        assert hub._retirement_payload(user.uid)['status'] == 'confirmed'
        assert user.uid not in hub.cloud and survivor.uid in hub.cloud
    finally:
        allow_t0.set()
        release_g.set()
        retire_thread.join(5)
        if summary_thread.ident:
            summary_thread.join(5)
        monkeypatch.undo()
        stop_fixture(hub)


def test_withdrawal_exception_stops_without_state_flush_then_recovers_before_resource_scan(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    admin, _, user, survivor = people(hub)
    fid = seed_resources(hub, user, survivor)
    state_path = Path(hub.store._path)
    before = state_path.read_bytes()
    monkeypatch.setattr(hub, '_resource_withdraw_owner_locked', lambda *_: (_ for _ in ()).throw(RuntimeError('synthetic G withdrawal')))
    monkeypatch.setattr(hub.store, '_save_encoded', lambda *_: pytest.fail('FAILED withdrawal cannot state-flush'))
    try:
        retire(hub, admin, user.uid)
        receipt = hub._retirement_payload(user.uid)
        assert receipt['status'] == 'unknown' and receipt['identity_effect'] == 'revoked'
        assert hub._recovery.phase == 'FAILED' and not hub._service_available()
        assert hub._persist(force=True) is False and state_path.read_bytes() == before
        assert hub.shutdown(normal=True) is False
        assert not hub._recovery.owner.held and state_path.read_bytes() == before
    finally:
        monkeypatch.undo()
        stop_fixture(hub)
    reopened = Hub(cfg=config_for(tmp_path), store_dir=str(state_path.parent))
    try:
        restored = reopened._retirement_payload(user.uid)
        assert restored['status'] == 'confirmed' and restored['operation_id'] == receipt['operation_id']
        assert user.uid not in reopened.cloud and survivor.uid in reopened.cloud
        assert (Path(reopened.cloud_dir) / f'{user.uid}.bin').read_bytes() == RESOURCE_A
        assert reopened._read_web_resource(fid)[1] == RESOURCE_A
    finally:
        stop_fixture(reopened)
