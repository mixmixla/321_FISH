"""Retirement correlation over real encrypted loopback TCP and synthetic stores."""
from dataclasses import replace
import builtins
import os
from pathlib import Path
import socket
import threading
import time
from types import SimpleNamespace

import pytest

from config import CFG
from server_recovery import StoreCoordinator
from crypto import client_handshake
from server import Hub, _handle_tcp


class Peer:
    def __init__(self, port, nick, password=''):
        self.sock = socket.create_connection(('127.0.0.1', port), timeout=3)
        self.channel = client_handshake(self.sock)
        self.send(t='hello', nick=nick, pwd=password)
        self.welcome = self.take(lambda e: e.get('t') in ('welcome', 'error'))
        assert self.welcome['t'] == 'welcome'
        self.uid = self.welcome['uid']

    def send(self, **frame):
        self.channel.send_frame(frame)

    def take(self, predicate):
        deadline = time.monotonic() + 3
        for _ in range(128):
            self.sock.settimeout(max(.01, deadline - time.monotonic()))
            event, _ = self.channel.recv_frame()
            if predicate(event):
                return event
        pytest.fail('Expected TCP event was not received within 128 frames')

    def reply(self):
        return self.take(lambda e: e.get('t') in ('admin_user_info', 'error'))

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


@pytest.fixture
def wire(tmp_path):
    cfg = replace(CFG, admin_nick='RCS_admin', admin_pwd='synthetic-RCS-password',
                  audit_dir=str(tmp_path/'audit'), web_files_dir=str(tmp_path/'files'),
                  persist_interval=0.0)
    StoreCoordinator.initialize_new(tmp_path / 'store')
    hub = Hub(cfg=cfg, audit_dir=cfg.audit_dir, store_dir=str(tmp_path/'store'))
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    listener.listen(16)
    listener.settimeout(.1)
    stop = threading.Event()
    workers, peers, connections = [], [], []
    hub_slot, hubs = [hub], [hub]
    accept_lock = threading.Lock()

    def accept():
        while not stop.is_set():
            try:
                conn, addr = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with accept_lock:
                thread = threading.Thread(target=_handle_tcp, args=(hub_slot[0], conn, addr), daemon=True)
                connections.append(conn)
                workers.append(thread)
                thread.start()

    acceptor = threading.Thread(target=accept, daemon=True)
    acceptor.start()

    def connect(nick, password=''):
        peer = Peer(listener.getsockname()[1], nick, password)
        peers.append(peer)
        return peer

    def stop_writer(value):
        # Test-server crash/teardown: producers have already exited. Retire any
        # queued, unsaved ordinary triggers under the writer barrier. Setting
        # closing+wake alone can lose its wake when a worker is finishing a
        # pending write; do not leave that daemon alive or invent a final save.
        with value._persist_writer_lock:
            with value._persist_lock:
                value._persist_pending = False
                value._persist_closing = True
                value._persist_slot = value._persist_slot_fp = None
            value._persist_wake.set()
        if value._persist_worker_thread is not None:
            value._persist_worker_thread.join(4)
            assert not value._persist_worker_thread.is_alive()
        value.shutdown(normal=False)
        assert not value._recovery.owner.held
        assert not any(t.is_alive() for t in value._managed_threads)

    def restart(before_restore=lambda: None):
        # Explicitly stop old transports and writer before constructing a fresh
        # Hub over the actual same JSON. No synthetic receipt is substituted.
        with accept_lock:
            for conn in connections:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                conn.close()
            for worker in workers:
                worker.join(4)
                assert not worker.is_alive()
            stop_writer(hub_slot[0])
            before_restore()
            restored = Hub(cfg=cfg, audit_dir=cfg.audit_dir, store_dir=str(tmp_path/'store'))
            hubs.append(restored)
            hub_slot[0] = restored
            return restored

    connect.restart = restart

    try:
        admin = connect(cfg.admin_nick, cfg.admin_pwd)
        victim = connect('RCS_target#2')
        yield hub, admin, victim, connect
    finally:
        for peer in peers:
            peer.close()
        stop.set()
        listener.close()
        acceptor.join(3)
        for worker in workers:
            worker.join(3)
        assert not acceptor.is_alive()
        assert not any(worker.is_alive() for worker in workers)
        for value in hubs:
            stop_writer(value)


def test_get_echo_and_legacy_shape_without_creating_retirement(wire):
    hub, admin, victim, _ = wire
    admin.send(t='admin_user_get', uid=victim.uid, request_id='get-A_7')
    info = admin.reply()
    assert info.get('request_id') == 'get-A_7'
    assert info['uid'] == victim.uid and 'retirement' not in info
    assert not hub.retired
    admin.send(t='admin_user_get', uid=victim.uid)
    assert 'request_id' not in admin.reply()
    assert 'request_id' not in hub._admin_user_payload(victim.uid)  # HTTP shape unchanged


def test_del_echoes_pending_and_final_without_breaking_third_party(wire):
    hub, admin, victim, connect = wire
    second_target = connect('RCS_target#2')
    other = connect('RCS_other')
    admin.send(t='admin_user_del', uid=victim.uid, request_id='delete-1')
    pending = admin.reply()
    final = admin.reply()
    assert pending.get('request_id') == final.get('request_id') == 'delete-1'
    assert pending['retirement']['status'] == 'pending'
    assert final['retirement']['status'] == 'confirmed'
    operation_id = final['retirement']['operation_id']
    assert operation_id == pending['retirement']['operation_id']
    for peer in (victim, second_target):
        assert peer.take(lambda e: e.get('code') == 'deleted')['t'] == 'error'
    other.send(t='chat', channel='public', text='RCS unaffected third party')
    assert admin.take(lambda e: e.get('text') == 'RCS unaffected third party')['uid'] == other.uid
    admin.send(t='admin_user_del', uid=victim.uid, operation_id=operation_id, request_id='repeat-1')
    repeated = admin.reply()
    assert repeated.get('request_id') == 'repeat-1'
    assert repeated['retirement']['operation_id'] == operation_id
    assert repeated['retirement']['status'] == 'confirmed'
    assert 'request_id' not in hub.store.load()['retired'][str(victim.uid)]


@pytest.mark.parametrize('message', ['admin_user_get', 'admin_user_del'])
@pytest.mark.parametrize('request_id', [None, '', True, 12, [], {}, '含中文', 'a'*65, 'bad id'])
def test_invalid_id_rejected_before_payload_or_retirement(wire, monkeypatch, message, request_id):
    hub, admin, victim, _ = wire
    called = []
    original = hub._admin_user_payload

    def observe(target):
        called.append(target)
        return original(target)

    monkeypatch.setattr(hub, '_admin_user_payload', observe)
    admin.send(t=message, uid=victim.uid, request_id=request_id)
    error = admin.reply()
    assert error.get('code') == 'request_id'
    assert 'request_id' not in error  # Never echo arbitrary invalid input
    assert called == [] and victim.uid not in hub.retired
    assert victim.uid in hub.known


@pytest.mark.parametrize('message', ['admin_user_get', 'admin_user_del'])
def test_forbidden_and_wrong_operation_echo_without_changing_target(wire, message):
    hub, admin, victim, _ = wire
    victim.send(t=message, uid=admin.uid, request_id='forbidden-1')
    error = victim.reply()
    assert error.get('code') == 'forbid' and error.get('request_id') == 'forbidden-1'
    admin.send(t=message, uid=victim.uid, operation_id='wrong-operation', request_id='wrong-op-1')
    error = admin.reply()
    assert error.get('code') == 'operation_id' and error.get('request_id') == 'wrong-op-1'
    assert not hub.retired


@pytest.mark.parametrize('request_id', ['x', 'A_0-'*16])
def test_valid_id_boundaries(wire, request_id):
    _, admin, victim, _ = wire
    admin.send(t='admin_user_get', uid=victim.uid, request_id=request_id)
    assert admin.reply().get('request_id') == request_id


def test_legacy_delete_receives_original_shape(wire):
    _, admin, victim, _ = wire
    admin.send(t='admin_user_del', uid=victim.uid)
    pending, final = admin.reply(), admin.reply()
    assert pending['retirement']['status'] == 'pending'
    assert final['retirement']['status'] == 'confirmed'
    assert 'request_id' not in pending and 'request_id' not in final


def test_real_open_failure_and_same_operation_retry_keep_request_identity(wire, monkeypatch):
    hub, admin, victim, connect = wire
    hub._persist_flush()
    path = Path(hub.store._path)
    before = path.read_bytes()
    real_open = builtins.open

    def fail_temporary_open(name, mode='r', *args, **kwargs):
        if os.path.abspath(str(name)).startswith(os.path.abspath(str(path)+'.tmp-')) and mode == 'xb':
            raise PermissionError('synthetic Store open failure')
        return real_open(name, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, 'open', fail_temporary_open)
    admin.send(t='admin_user_del', uid=victim.uid, request_id='fail-1')
    pending, failed = admin.reply(), admin.reply()
    assert pending.get('request_id') == failed.get('request_id') == 'fail-1'
    result = failed['retirement']
    assert result['status'] == 'failed' and result['retryable'] is True
    assert result['failed_stage'] == 'open'
    assert path.read_bytes() == before
    assert victim.uid in hub.retired and victim.uid not in hub.known
    operation = result['operation_id']
    monkeypatch.setattr(builtins, 'open', real_open)
    cleanup_calls = []
    original = hub._admin_del_remove_groups

    def count_cleanup(uid):
        cleanup_calls.append(uid)
        return original(uid)

    monkeypatch.setattr(hub, '_admin_del_remove_groups', count_cleanup)
    admin.send(t='admin_user_del', uid=victim.uid, operation_id=operation, request_id='retry-2')
    retry_pending, confirmed = admin.reply(), admin.reply()
    assert retry_pending.get('request_id') == confirmed.get('request_id') == 'retry-2'
    assert retry_pending['retirement']['status'] == 'pending'
    assert confirmed['retirement']['status'] == 'confirmed'
    assert confirmed['retirement']['operation_id'] == operation
    assert cleanup_calls == []  # Persistence retry cannot repeat t0
    restored = connect.restart()
    restored_result = restored._retirement_payload(victim.uid)
    assert restored_result['operation_id'] == operation
    assert restored_result['origin'] == 'restored_valid_json'
    assert restored_result['content_sha256'] is None


def test_post_replace_unknown_queries_echo_and_reconcile_without_second_write(wire, monkeypatch):
    hub, admin, victim, _ = wire
    hub._persist_flush()
    path = os.path.abspath(hub.store._path)
    real_replace, real_open = os.replace, builtins.open
    replacements = []

    def replace_then_fail(src, dst):
        real_replace(src, dst)
        if os.path.abspath(str(dst)) == path:
            replacements.append(str(dst))
            raise OSError('synthetic post-replace acknowledgement failure')

    def fail_authority_read(name, mode='r', *args, **kwargs):
        if os.path.abspath(str(name)) == path and mode == 'rb':
            raise PermissionError('synthetic authority read failure')
        return real_open(name, mode, *args, **kwargs)

    monkeypatch.setattr(os, 'replace', replace_then_fail)
    monkeypatch.setattr(builtins, 'open', fail_authority_read)
    admin.send(t='admin_user_del', uid=victim.uid, request_id='unknown-del')
    pending, unknown = admin.reply(), admin.reply()
    assert pending.get('request_id') == unknown.get('request_id') == 'unknown-del'
    operation = unknown['retirement']['operation_id']
    assert unknown['retirement']['status'] == 'unknown'
    assert unknown['retirement']['retryable'] is False
    for message in ('admin_user_get', 'admin_user_del'):
        admin.send(t=message, uid=victim.uid, operation_id=operation, request_id=message)
        result = admin.reply()
        assert result.get('request_id') == message
        assert result['retirement']['status'] == 'unknown'
        assert len(replacements) == 1
    monkeypatch.setattr(builtins, 'open', real_open)
    admin.send(t='admin_user_get', uid=victim.uid, operation_id=operation, request_id='reconcile')
    confirmed = admin.reply()
    assert confirmed.get('request_id') == 'reconcile'
    assert confirmed['retirement']['status'] == 'confirmed'
    assert confirmed['retirement']['origin'] == 'reconciled_current_json'
    assert confirmed['retirement']['operation_id'] == operation
    assert len(replacements) == 1


class CoreEvents:
    """Real Core callback synchronization, without sleeps or a Tk substitute."""
    def __init__(self):
        self.condition = threading.Condition()
        self.events = []

    def __call__(self, event):
        with self.condition:
            self.events.append(event)
            self.condition.notify_all()

    def wait(self, predicate, after=0):
        with self.condition:
            ready = self.condition.wait_for(lambda: any(predicate(e) for e in self.events[after:]), 5)
            diagnostics = [(e.get('t'), e.get('code'),
                            [(r.phase, r.receipt) for r in e.get('records', ())])
                           for e in self.events[after:] if e.get('t') in ('error', 'retirement_status')]
            assert ready, diagnostics[-8:]
            return next(e for e in self.events[after:] if predicate(e))


@pytest.fixture
def real_cores(wire, tmp_path):
    from client_core import ClientCore
    _hub, admin, _victim, _connect = wire
    port = admin.sock.getpeername()[1]
    cores = []

    def open_core(nick, password=''):
        events = CoreEvents()
        core = ClientCore('127.0.0.1', port, nick, pwd=password,
                          history_dir=str(tmp_path/f'core-{len(cores)}'), on_event=events,
                          heartbeat_interval=.2, heartbeat_timeout=3,
                          reconnect_base=.01, reconnect_max=.01)
        cores.append(core)
        core.start()
        events.wait(lambda e: e.get('t') == 'welcome')
        return core, events

    yield open_core
    for core in cores:
        core.stop()
        assert all(t is None or not t.is_alive() for t in (core._reader, core._heartbeat, core._reconnector))


def test_real_core_preflight_receipt_revoke_and_online_retired_target_error(wire, real_cores):
    hub, _admin, victim, connect = wire
    admin, events = real_cores(hub.cfg.admin_nick, hub.cfg.admin_pwd)
    target, target_events = real_cores('RCS_target#2')
    other = connect('Core_third_party')
    assert admin.send_admin_user_del(victim.uid, expected_nick='RCS_target#2')
    result = events.wait(lambda e: e.get('t') == 'retirement_status'
                         and any(r.confirmed for r in e['records']))
    record = result['records'][0]
    assert record.receipt.target_uid == victim.uid and record.ever_del
    assert victim.uid not in admin.known and victim.uid not in admin.roster
    assert not any(e.get('t') == 'admin_user_info' for e in events.events)
    revoked = target_events.wait(lambda e: e.get('code') == 'deleted')
    assert revoked['manual_login_required'] is True
    target._reconnector.join(3)
    assert not target._reconnector.is_alive() and target._epoch == 1
    other.send(t='chat', channel='public', text='Core unrelated member still works')
    events.wait(lambda e: e.get('text') == 'Core unrelated member still works')
    before = len(events.events)
    assert admin._send_frame({'t': 'chat', 'channel': 'private', 'to': victim.uid, 'text': 'retired target'})
    error = events.wait(lambda e: e.get('code') == 'retired', after=before)
    assert not error.get('manual_login_required')
    assert admin.connected and not admin._stop.is_set()


def test_real_core_reconnect_joins_old_workers_and_queries_historical_operation(wire, real_cores):
    hub, _admin, victim, _connect = wire
    core, events = real_cores(hub.cfg.admin_nick, hub.cfg.admin_pwd)
    assert core.send_admin_user_del(victim.uid, expected_nick='RCS_target#2')
    events.wait(lambda e: e.get('t') == 'retirement_status' and any(r.confirmed for r in e['records']))
    historical = core.retirement_snapshot()[0]
    old = core._connection
    before = len(events.events)
    core.drop()
    welcome = events.wait(lambda e: e.get('t') == 'welcome', after=before)
    assert welcome['_connection_epoch'] > old.epoch
    assert old.stop.is_set() and not old.reader.is_alive() and not old.heartbeat.is_alive()
    assert core.retirement_snapshot()[0].confirmed == historical.confirmed
    assert not core.retirement_snapshot()[0].current_verified
    assert not core.retirement.confirmed_uids(core.connection_epoch)
    before = len(events.events)
    assert core.query_admin_retirement(intent_id=historical.intent_id)
    refreshed = events.wait(lambda e: e.get('t') == 'retirement_status'
                            and any(r.current_verified for r in e['records']), after=before)
    assert refreshed['records'][0].receipt.operation_id == historical.receipt.operation_id


@pytest.mark.parametrize('first_write_fails', [False, True])
def test_real_core_and_new_hub_restart_preserve_truth_and_never_blindly_delete(wire, real_cores, monkeypatch, first_write_fails):
    hub, _admin, victim, connect = wire
    core, events = real_cores(hub.cfg.admin_nick, hub.cfg.admin_pwd)
    hub._persist_flush()
    path = Path(hub.store._path)
    old_bytes = path.read_bytes()
    real_open = builtins.open

    def failed_open(name, mode='r', *args, **kwargs):
        if os.path.abspath(str(name)).startswith(os.path.abspath(str(path)+'.tmp-')) and mode == 'xb':
            raise PermissionError('synthetic first retirement save failure')
        return real_open(name, mode, *args, **kwargs)

    if first_write_fails:
        monkeypatch.setattr(builtins, 'open', failed_open)
    assert core.send_admin_user_del(victim.uid, expected_nick='RCS_target#2')
    expected = 'failed' if first_write_fails else 'confirmed'
    terminal = events.wait(lambda e: e.get('t') == 'retirement_status'
                           and any(r.receipt and r.receipt.status in ('failed', 'unknown', 'confirmed')
                                   for r in e['records']))['records'][0]
    assert terminal.receipt.status == expected, terminal.receipt
    before = core.retirement_snapshot()[0]
    if first_write_fails:
        assert path.read_bytes() == old_bytes
    start = len(events.events)
    restored = connect.restart(lambda: monkeypatch.setattr(builtins, 'open', real_open))
    events.wait(lambda e: e.get('t') == 'welcome', after=start)
    assert not core.retirement_snapshot()[0].current_verified
    start = len(events.events)
    assert core.query_admin_retirement(intent_id=before.intent_id)
    result = events.wait(lambda e: e.get('t') == 'retirement_status'
                         and any(r.current_verified for r in e['records']), after=start)['records'][0]
    assert result.receipt.operation_id == before.receipt.operation_id
    assert result.receipt.status == 'confirmed'
    assert victim.uid in restored.retired
    if first_write_fails:
        assert result.receipt.origin == 'written'  # Startup materialized the accepted intent.
        assert result.receipt.content_sha256 is not None
        assert not core.retirement_snapshot()[0].can_retry
        # A new UI request re-queries the same recovered operation, without
        # reissuing DEL or clearing its durable intent after the restart.
        deletes = []
        original_delete = restored._on_admin_user_del
        def counted_delete(*args):
            deletes.append(args)
            return original_delete(*args)
        monkeypatch.setattr(restored, '_on_admin_user_del', counted_delete)
        control_before = Path(restored.store._path).with_name('control.json').read_bytes()
        start = len(events.events)
        assert core.send_admin_user_del(victim.uid, expected_nick='RCS_target#2')
        events.wait(lambda e: e.get('t') == 'retirement_status'
                    and any(r.current_verified and r.receipt.status == 'confirmed'
                            for r in e['records']), after=start)
        assert not deletes and victim.uid in restored.retired
        assert Path(restored.store._path).with_name('control.json').read_bytes() == control_before
    else:
        assert result.receipt.origin == 'restored_valid_json'
        assert result.receipt.content_sha256 is None


def test_core_preflight_send_failure_and_desired_host_change_never_pop_or_send_delete(tmp_path):
    from client_core import ClientCore, _Connection
    from retirement_status import Scope
    core = ClientCore(nick='synthetic-admin', history_dir=str(tmp_path/'core'))
    frames = []

    def send(frame, body=b''):
        frames.append(frame)
        if len(frames) == 1:
            raise OSError('synthetic partial or failed send')

    connection = _Connection(1, core.host, core.port, chan=SimpleNamespace(send_frame=send), authenticating=False)
    core._connection, core._epoch = connection, 1
    core.uid, core.is_admin, core.state = 1, True, 'online'
    core.known[7] = {'nick': 'target'}
    core.roster[7] = {'uid': 7, 'nick': 'target'}
    core._conn_alive.set()
    core.retirement.connect(Scope(core.host, core.port, 1), 1)
    try:
        assert core.send_admin_user_del(7) is False
        assert 7 in core.known and 7 in core.roster
        assert not core.retirement_snapshot()[0].ever_del
        assert core.send_admin_user_del(7)
        request = frames[-1]
        core.set_host('127.0.0.2')
        core._dispatch({'t': 'admin_user_info', 'uid': 7, 'nick': 'target',
                        'request_id': request['request_id']}, connection=connection)
        assert [frame['t'] for frame in frames] == ['admin_user_get', 'admin_user_get']
        assert 7 in core.known and 7 in core.roster
        assert not core.retirement_snapshot()[0].ever_del
    finally:
        core.stop()


def test_real_core_lost_delete_receipts_cannot_use_cleared_as_confirmation(wire, real_cores, monkeypatch):
    hub, _admin, victim, _connect = wire
    core, events = real_cores(hub.cfg.admin_nick, hub.cfg.admin_pwd)
    handled = threading.Event()
    dropped, deletes = [], []
    handler = hub._on_admin_user_del

    def drop_receipts(session, header):
        deletes.append(header['request_id'])
        send = session.send

        def filtered(payload, body=b''):
            if payload.get('t') == 'admin_user_info':
                dropped.append(payload)
                return
            return send(payload, body)

        session.send = filtered
        try:
            return handler(session, header)
        finally:
            session.send = send
            handled.set()

    monkeypatch.setattr(hub, '_on_admin_user_del', drop_receipts)
    assert core.send_admin_user_del(victim.uid, expected_nick='RCS_target#2')
    assert handled.wait(4)
    events.wait(lambda e: e.get('t') == 'cleared' and e.get('uid') == victim.uid)
    assert len(dropped) == 2 and dropped[-1]['retirement']['status'] == 'confirmed'
    record = core.retirement_snapshot()[0]
    assert record.ever_del and record.confirmed is None and record.receipt is None
    before = len(events.events)
    assert core.query_admin_retirement(intent_id=record.intent_id)
    events.wait(lambda e: e.get('t') == 'retirement_status'
                and any(r.confirmed for r in e['records']), after=before)
    assert len(deletes) == 1


def test_new_core_with_no_echo_server_keeps_readonly_detail_but_never_deletes(wire, real_cores, monkeypatch):
    hub, _admin, victim, _connect = wire
    core, events = real_cores(hub.cfg.admin_nick, hub.cfg.admin_pwd)
    monkeypatch.setattr(hub, '_admin_correlated', lambda payload, request_id: payload)
    now = [0.0]
    core.retirement._clock = lambda: now[0]
    received = threading.Event()
    receive = core.retirement.receive

    def observe(frame, epoch):
        result = receive(frame, epoch)
        if frame.get('t') == 'admin_user_info':
            received.set()
        return result

    monkeypatch.setattr(core.retirement, 'receive', observe)
    assert core.send_admin_user_del(victim.uid, expected_nick='RCS_target#2')
    assert received.wait(3)
    assert not core.retirement_snapshot()[0].ever_del
    assert victim.uid not in hub.retired
    now[0] = 11
    assert core.retirement_snapshot()[0].phase == 'query_failed'
    before = len(events.events)
    assert core.send_admin_user_groups(victim.uid)
    detail = events.wait(lambda e: e.get('t') == 'admin_user_info', after=before)
    assert detail['uid'] == victim.uid and detail['correlated'] is False
    assert victim.uid not in hub.retired


@pytest.mark.parametrize('unavailable', [False, True])
def test_real_hello_retirement_refusal_stops_core_before_welcome(wire, tmp_path, unavailable):
    from client_core import ClientCore
    hub, admin, victim, _connect = wire
    if unavailable:
        hub._retired_schema_invalid = True
    else:
        admin.send(t='admin_user_del', uid=victim.uid, request_id='retire-before-login')
        assert admin.reply()['retirement']['status'] == 'pending'
        assert admin.reply()['retirement']['status'] == 'confirmed'
    events = CoreEvents()
    core = ClientCore('127.0.0.1', admin.sock.getpeername()[1], 'RCS_target#2',
                      history_dir=str(tmp_path/'refused-core'), on_event=events,
                      reconnect_base=.01, reconnect_max=.01)
    try:
        core.start()
        error = events.wait(lambda e:e.get('t') == 'error')
        assert error['code'] == 'retired', error
        assert error['manual_login_required'] is True
        core._reconnector.join(3)
        assert not core._reconnector.is_alive() and core.connection_epoch == 1
        assert not any(e.get('t') == 'welcome' for e in events.events)
    finally:
        core.stop()


def test_real_hello_bad_password_racing_retirement_is_terminal(wire, tmp_path, monkeypatch):
    import auth
    from client_core import ClientCore
    hub, admin, victim, _connect = wire
    hub.known[victim.uid]['pwd'] = auth.make('synthetic-correct-password')
    entered, release = threading.Event(), threading.Event()
    real_verify = auth.verify

    def verify(password, stored):
        if password == 'synthetic-wrong-paused':
            entered.set()
            assert release.wait(4)
            return False
        return real_verify(password, stored)

    monkeypatch.setattr(auth, 'verify', verify)
    events = CoreEvents()
    core = ClientCore('127.0.0.1', admin.sock.getpeername()[1], 'RCS_target#2', pwd='synthetic-wrong-paused',
                      history_dir=str(tmp_path/'refused-core'), on_event=events,
                      reconnect_base=.01, reconnect_max=.01)
    try:
        core.start()
        assert entered.wait(3)
        admin.send(t='admin_user_del', uid=victim.uid, request_id='retire-during-check')
        assert admin.reply()['retirement']['status'] == 'pending'
        assert admin.reply()['retirement']['status'] == 'confirmed'
        release.set()
        error = events.wait(lambda e:e.get('t') == 'error')
        assert error['code'] == 'retired', error
        assert error['manual_login_required'] is True
        core._reconnector.join(3)
        assert not core._reconnector.is_alive() and core.connection_epoch == 1
    finally:
        release.set()
        core.stop()
