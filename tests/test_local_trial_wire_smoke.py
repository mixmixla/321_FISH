"""Real loopback wire checks and explicit fault injection; no GUI acceptance.

The harness seam tests use real owned Jobs with synthetic Python children,
not EXEs. Actual compiled EXE acceptance is recorded separately.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import socket
import struct
import sys
import threading
import time
from types import SimpleNamespace
import uuid

import pytest

import local_trial
from crypto import server_handshake


@pytest.fixture()
def hub_port(tmp_path):
    from config import CFG
    from server import Hub, serve
    cfg = replace(CFG, bind_host='127.0.0.1', discovery_enabled=False,
                  audit_dir=str(tmp_path/'audit'), web_files_dir=str(tmp_path/'web'))
    hub = Hub(cfg=cfg, audit_dir=cfg.audit_dir)
    port = local_trial._free_port()
    stop = threading.Event()
    worker = threading.Thread(target=serve, args=(hub, port, stop, False), daemon=True)
    worker.start()
    try:
        assert local_trial._wait_tcp(port)
        yield port
    finally:
        stop.set()
        worker.join(12)
        assert not worker.is_alive()
        assert hub._shutdown_result is True


@contextmanager
def fault_peer(handler):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    listener.settimeout(.1)
    stop = threading.Event()
    connections, workers, errors = [], [], []
    ended = [threading.Event(), threading.Event()]

    def handle(conn, index):
        try:
            conn.settimeout(3)
            handler(conn, index)
        except (OSError, EOFError):
            pass
        except Exception as exc:
            # Closing the test-owned listener/connection is expected cleanup;
            # unexpected assertion failures in the fault server remain visible.
            from crypto import HandshakeError
            if not isinstance(exc, HandshakeError):
                errors.append(exc)
        finally:
            conn.close()
            ended[index].set()

    def accept():
        while not stop.is_set() and len(connections) < 2:
            try:
                conn, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            index = len(connections)
            connections.append(conn)
            worker = threading.Thread(target=handle, args=(conn, index), daemon=True)
            workers.append(worker)
            worker.start()

    owner = threading.Thread(target=accept, daemon=True)
    owner.start()
    try:
        yield listener.getsockname()[1], ended
    finally:
        stop.set()
        listener.close()
        owner.join(2)
        for conn in connections:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()
        for worker in workers:
            worker.join(2)
            assert not worker.is_alive()
        assert not owner.is_alive()
        assert not errors, errors


def welcome(conn, index, *, duplicate=False):
    channel = server_handshake(conn)
    hello, _ = channel.recv_frame()
    assert hello['t'] == 'hello'
    channel.send_frame({'t': 'welcome', 'uid': 1 if duplicate else index+1})
    return channel


def wait_for_eof(conn):
    while conn.recv(4096):
        pass


def test_real_hub_chat_and_two_complete_game_lifecycles(hub_port):
    result = local_trial._wire_probe(hub_port)
    assert result['ok'] and result['cleanup_ok'] and not result['timed_out']
    assert [x['name'] for x in result['steps']] == [
        'welcome', 'chat', 'chat', 'gomoku', 'gomoku_leave', 'connect4', 'connect4_leave']
    games = [x for x in result['steps'] if x['name'] in ('gomoku', 'connect4')]
    assert [(x['moves'], x['round'], x['next_round']) for x in games] == [(9, 1, 2), (7, 1, 2)]
    assert len(result['cleanup']) == 2 and all(x['ok'] for x in result['cleanup'])
    assert not result['gui_accepted'] and not result['natural_exit_verified']
    assert not result['physical_lan_verified']


def test_silent_handshake_times_out_and_releases_socket():
    with fault_peer(lambda conn, _index: wait_for_eof(conn)) as (port, ended):
        start = time.monotonic()
        result = local_trial._wire_probe(port, timeout=.2)
        assert not result['ok'] and result['timed_out'] and result['cleanup_ok']
        assert time.monotonic()-start < 1.5
        assert ended[0].wait(1), 'probe left the real handshake socket open'


def test_trickle_handshake_obeys_absolute_deadline():
    def trickle(conn, _index):
        data = b''
        while len(data) < 96:
            part = conn.recv(96-len(data))
            if not part:
                raise EOFError('fault peer closed before handshake prefix')
            data += part
        for _ in range(32):
            conn.sendall(b'\x01')
            time.sleep(.06)
    with fault_peer(trickle) as (port, ended):
        start = time.monotonic()
        result = local_trial._wire_probe(port, timeout=.2)
        assert not result['ok'] and result['timed_out'] and result['cleanup_ok']
        assert time.monotonic()-start < 1.5
        assert ended[0].wait(1)


def test_duplicate_welcome_is_rejected_and_both_peers_close():
    def duplicate(conn, index):
        welcome(conn, index, duplicate=True)
        wait_for_eof(conn)
    with fault_peer(duplicate) as (port, ended):
        result = local_trial._wire_probe(port, timeout=2)
        assert not result['ok'] and not result['timed_out']
        assert result['cleanup_ok'] and len(result['cleanup']) == 2
        assert all(e.wait(1) for e in ended)


def test_chat_timeout_closes_both_connected_peers():
    def silent_chat(conn, index):
        welcome(conn, index)
        wait_for_eof(conn)
    with fault_peer(silent_chat) as (port, ended):
        result = local_trial._wire_probe(port, timeout=.25)
        assert not result['ok'] and result['timed_out'] and result['cleanup_ok']
        assert result['stage'] == 'chat_a' and len(result['cleanup']) == 2
        assert all(e.wait(1) for e in ended)


def test_oversized_frame_is_rejected_before_waiting_for_payload():
    def oversized(conn, _index):
        channel = server_handshake(conn)
        header, _ = channel.recv_frame()
        assert header['t'] == 'hello'
        conn.sendall(struct.pack('>I', 1_000_000))
        wait_for_eof(conn)
    with fault_peer(oversized) as (port, ended):
        result = local_trial._wire_probe(port, timeout=2)
        assert not result['ok'] and not result['timed_out'] and result['cleanup_ok']
        assert result['error_type'] == 'ProtocolError'
        assert ended[0].wait(1)


def test_chat_eof_fails_and_closes_other_peer():
    def disconnect(conn, index):
        channel = welcome(conn, index)
        if index == 0:
            header, _ = channel.recv_frame()
            assert header['t'] == 'chat'
        else:
            wait_for_eof(conn)
    with fault_peer(disconnect) as (port, ended):
        result = local_trial._wire_probe(port, timeout=2)
        assert not result['ok'] and not result['timed_out'] and result['cleanup_ok']
        assert result['stage'] == 'chat_a'
        assert all(e.wait(1) for e in ended)


def test_second_handshake_failure_closes_first_connected_peer():
    def second_fails(conn, index):
        if index == 0:
            welcome(conn, index)
            wait_for_eof(conn)
    with fault_peer(second_fails) as (port, ended):
        result = local_trial._wire_probe(port, timeout=2)
        assert not result['ok'] and result['cleanup_ok'] and len(result['cleanup']) == 2
        assert all(e.wait(1) for e in ended)


def test_state_wait_rejects_old_room_round_status_and_move():
    def snapshots(conn, index):
        channel = welcome(conn, index)
        for rid, status, round_no, board, marker in [
            ('old', 'playing', 2, [[1, 2]], 'old-room'),
            ('g1', 'ended', 2, [[1, 2]], 'old-status'),
            ('g1', 'playing', 1, [[1, 2]], 'old-round'),
            ('g1', 'playing', 2, [[1, 0]], 'old-move'),
            ('g1', 'playing', 2, [[1, 2]], 'current')]:
            channel.send_frame({'t': 'game_state', 'room_id': rid,
                                'room': {'status': status, 'round': round_no},
                                'state': {'board': board, 'marker': marker}})
        wait_for_eof(conn)
    with fault_peer(snapshots) as (port, ended):
        peer = local_trial._WirePeer('test-state', time.monotonic()+3)
        try:
            peer.connect(port)
            event = local_trial._wire_state(peer, 'g1', 'playing', round_no=2, stones=2)
            assert event['state']['marker'] == 'current'
        finally:
            peer.close()
        assert ended[0].wait(1)


def test_expired_budget_cannot_accept_buffered_state():
    def buffered(conn, index):
        channel = welcome(conn, index)
        channel.send_frame({'t': 'ready'})
        wait_for_eof(conn)
    with fault_peer(buffered) as (port, ended):
        peer = local_trial._WirePeer('test-expired', time.monotonic()+.2)
        try:
            peer.connect(port)
            time.sleep(.25)
            with pytest.raises(TimeoutError):
                peer.wait('ready')
        finally:
            peer.close()
        assert ended[0].wait(1)


def test_unmatched_frame_flood_is_bounded():
    def flood(conn, index):
        channel = welcome(conn, index)
        for i in range(300):
            channel.send_frame({'t': 'irrelevant', 'index': i})
        wait_for_eof(conn)
    with fault_peer(flood) as (port, ended):
        peer = local_trial._WirePeer('test-flood', time.monotonic()+3)
        try:
            peer.connect(port)
            with pytest.raises(RuntimeError, match='frame limit'):
                peer.wait('never')
        finally:
            peer.close()
        assert ended[0].wait(1)


def test_close_failure_continues_other_cleanup_and_preserves_unrelated_peer(hub_port, monkeypatch):
    sentinel = local_trial._WirePeer('wire-sentinel', time.monotonic()+30)
    sentinel.connect(hub_port)
    original = local_trial._WirePeer.close
    calls = []
    def close(peer):
        calls.append(peer.nick)
        original(peer)
        if peer.nick == 'REL_wire_a':
            raise OSError('synthetic close failure after releasing real socket')
    try:
        monkeypatch.setattr(local_trial._WirePeer, 'close', close)
        result = local_trial._wire_probe(hub_port)
        assert not result['ok'] and not result['cleanup_ok']
        assert calls == ['REL_wire_a', 'REL_wire_b']
        assert result['cleanup'][1]['ok'] is True
        sentinel.send({'t': 'game_list'})
        assert 'games' in sentinel.wait('game_list')
    finally:
        original(sentinel)


@pytest.mark.parametrize('timeout', [0, -1, float('nan'), float('inf')])
def test_invalid_budget_rejected_before_opening_socket(monkeypatch, timeout):
    def unexpected(*_args, **_kwargs):
        raise AssertionError('invalid budget opened a network socket')
    monkeypatch.setattr(local_trial.socket, 'socket', unexpected)
    with pytest.raises(ValueError):
        local_trial._wire_probe(1, timeout=timeout)


def harness_scene(tmp_path, monkeypatch):
    """Explicit seam doubles around real Jobs, never called EXE acceptance."""
    source = tmp_path/'candidate'
    (source/'dist').mkdir(parents=True)
    for name in ('server.exe', 'client.exe'):
        (source/'dist'/name).write_bytes(b'synthetic-not-executable')
    (source/'config.py').write_text('SYNTHETIC = True\n', encoding='utf-8')
    jobs = []
    original_launcher = local_trial.launch_process
    def launch(command, **kwargs):
        code = 'raise SystemExit(0)' if 'initialize-new' in command else 'import time;time.sleep(60)'
        proc = original_launcher([sys._base_executable, '-B', '-c', code], **kwargs)
        jobs.append(proc)
        return proc
    monkeypatch.setattr(local_trial, 'launch_process', launch)
    monkeypatch.setattr(local_trial, '_wait_tcp', lambda _port: True)
    monkeypatch.setattr(local_trial, '_web_probe', lambda _port: {'ok': True, 'status': 200})
    monkeypatch.setattr(local_trial, '_wait_login_audit', lambda *_a: {'ok': True})
    monkeypatch.setattr(local_trial, '_process_record', lambda proc, **_kw: {
        'state': 'running' if proc.poll() is None else 'exited', 'image_matches_expected': True})
    monkeypatch.setattr(local_trial, 'time', SimpleNamespace(sleep=lambda _s: None, monotonic=time.monotonic, time=time.time))
    return source, jobs


@pytest.mark.parametrize('failure', ['result', 'exception'])
def test_harness_wire_failure_is_nonzero_and_closes_real_owned_jobs(tmp_path, monkeypatch, failure):
    source, jobs = harness_scene(tmp_path, monkeypatch)
    calls = []
    def fail(port):
        calls.append(port)
        if failure == 'exception':
            raise TimeoutError('synthetic wire timeout')
        return {'ok': False, 'timed_out': True, 'cleanup_ok': True}
    monkeypatch.setattr(local_trial, '_wire_probe', fail, raising=False)
    try:
        code, summary = local_trial.run_candidate(source, tmp_path/'runs')
        assert calls, 'standard run never invoked the wire probe'
        assert code != 0 and summary['exit_code'] == code
        if failure == 'result':
            assert summary['probes']['wire']['timed_out'] is True
        else:
            assert summary['error']['type'] == 'TimeoutError'
        assert len(summary['cleanup']) == 4
        assert all(x['ok'] and x['close_ok'] and x['active_after'] == 0 for x in summary['cleanup'].values())
        assert all(proc._closed for proc in jobs)
    finally:
        for proc in jobs:
            if not proc._closed:
                local_trial._cleanup_trial_process(proc)


def test_failed_startup_does_not_run_wire_but_closes_jobs(tmp_path, monkeypatch):
    source, jobs = harness_scene(tmp_path, monkeypatch)
    monkeypatch.setattr(local_trial, '_wait_tcp', lambda _port: False)
    def unexpected(_port):
        raise AssertionError('wire probe ran after failed startup')
    monkeypatch.setattr(local_trial, '_wire_probe', unexpected, raising=False)
    try:
        code, summary = local_trial.run_candidate(source, tmp_path/'runs')
        assert code != 0
        assert summary['probes']['wire']['not_run_reason'] == 'startup_failed'
        assert all(x['ok'] and x['close_ok'] for x in summary['cleanup'].values())
    finally:
        for proc in jobs:
            if not proc._closed:
                local_trial._cleanup_trial_process(proc)
