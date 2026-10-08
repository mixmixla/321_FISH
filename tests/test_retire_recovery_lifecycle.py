"""Admission, worker ownership and shutdown over synthetic local resources."""
from dataclasses import replace
import http.client
import faulthandler
import json
import sys
import socket
import ssl
import threading
import time

import pytest

from server import Session, serve
from server_recovery import StoreError, StoreOwner, strict_json
from server_store import SaveResult
from test_retire_recovery_hub import fresh_hub, people, retire, stop_fixture


def test_retirement_between_password_check_and_attach_does_not_register_uid_zero(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    admin, _, user, _ = people(hub)
    original = hub._pwd_check_for_login
    uid, nick = user.uid, user.nick
    def racing_check(name, password):
        answer = original(name, password)
        if name == nick and answer is None:
            retire(hub, admin, uid)
        return answer
    monkeypatch.setattr(hub, '_pwd_check_for_login', racing_check)
    try:
        attempted = Session(0, nick, 'tcp', '127.0.0.1', lambda *_: None)
        assert hub._on_hello(attempted, {'nick': nick}) is False
        assert hub.nick_to_uid[nick] == uid
        assert 0 not in hub.known and 0 not in hub.sessions and 0 not in hub._uid_clients
        assert hub.retired[uid]['nick'] == nick
        assert hub._persist(force=True) is True
    finally:
        stop_fixture(hub)


def wait_for(predicate, seconds=4):
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, 'bounded condition wait expired'
        time.sleep(0.01)


def test_shutdown_joins_mutator_before_one_final_fresh_capture(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    _, _, user, _ = people(hub)
    hub._service_started = True  # This unit probes the shutdown contract; wire coverage is below.
    entered, release, done, quiescing = (threading.Event() for _ in range(4))
    def mutation():
        entered.set()
        assert release.wait(5)
        with hub.lock:
            hub.known[user.uid]['sign'] = '完成后才保存'
        done.set()
    worker = hub._start_worker(mutation, name='synthetic-mutator')
    assert entered.wait(5)
    original_set, original_flush = hub._persist_wake.set, hub._persist_flush
    def wake():
        original_set()
        if hub._persist_closing:
            quiescing.set()
    monkeypatch.setattr(hub._persist_wake, 'set', wake)
    calls = []
    def final_flush():
        assert done.is_set() and not worker.is_alive()
        calls.append('final')
        return original_flush()
    monkeypatch.setattr(hub, '_persist_flush', final_flush)
    results = []
    closer = threading.Thread(target=lambda: results.append(hub.shutdown(normal=True, timeout=5)))
    try:
        closer.start()
        assert quiescing.wait(5)
        assert not calls and hub._recovery.owner.held
        with pytest.raises(StoreError, match='store_in_use'):
            StoreOwner(tmp_path / 'store/.owner.lock').acquire()
        release.set()
        closer.join(5)
        assert not closer.is_alive() and results == [True]
        assert calls == ['final']
        saved = strict_json((tmp_path / 'store/state.json').read_bytes())
        assert saved['known'][str(user.uid)]['sign'] == '完成后才保存'
        assert not hub._recovery.owner.held
        assert hub.shutdown(normal=True) is True and calls == ['final']
    finally:
        release.set()
        worker.join(5)
        closer.join(5)
        hub.shutdown(normal=False)


def test_shutdown_timeout_holds_owner_and_late_cleanup_never_flushes(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    hub._service_started = True
    entered, release = threading.Event(), threading.Event()
    def blocked():
        entered.set()
        release.wait(5)
    worker = hub._start_worker(blocked, name='synthetic-blocked')
    assert entered.wait(5)
    original = (tmp_path / 'store/state.json').read_bytes()
    monkeypatch.setattr(hub, '_persist_flush', lambda: pytest.fail('timeout/FAILED cannot flush'))
    try:
        assert hub.shutdown(normal=True, timeout=0.05) is False
        assert hub._recovery.phase == 'FAILED' and hub._recovery.owner.held
        assert worker.is_alive()
        with pytest.raises(StoreError, match='store_in_use'):
            StoreOwner(tmp_path / 'store/.owner.lock').acquire()
        assert hub._start_worker(lambda: pytest.fail('new work after close')) is None
        release.set()
        worker.join(5)
        assert hub.shutdown(normal=False, timeout=1) is False
        assert not hub._recovery.owner.held
        assert (tmp_path / 'store/state.json').read_bytes() == original
    finally:
        release.set()
        worker.join(5)
        hub.shutdown(normal=False)


@pytest.mark.parametrize('failed', [False, True])
def test_failed_or_never_served_hub_has_no_shutdown_flush(tmp_path, monkeypatch, failed):
    hub = fresh_hub(tmp_path)
    before = (tmp_path / 'store/state.json').read_bytes()
    if failed:
        hub._service_started = True
        hub._fail_store()
    monkeypatch.setattr(hub, '_persist_flush', lambda: pytest.fail('no final permission'))
    assert hub.shutdown(normal=True) is (not failed)
    assert (tmp_path / 'store/state.json').read_bytes() == before
    assert not hub._recovery.owner.held


def test_tcp_http_sse_and_half_handshake_are_all_closed_before_store_release(tmp_path, monkeypatch):
    import web
    hub = fresh_hub(tmp_path)
    hub.cfg = replace(hub.cfg, tcp_port=0, web_port=0)
    monkeypatch.setenv('MOYU_WEB_HTTPS', '0')
    stop, errors = threading.Event(), []
    def run():
        try:
            serve(hub, port=0, stop=stop)
        except BaseException as exc:
            errors.append(exc)
    supervisor = threading.Thread(target=run)
    idle_tcp, http_conn, events = None, None, None
    supervisor.start()
    try:
        wait_for(lambda: hub._service_started)
        listener, = hub._listener_sockets
        tcp_port = listener.getsockname()[1]
        httpd, = hub._http_servers
        http_port = httpd.server_address[1]
        http_conn = http.client.HTTPConnection('127.0.0.1', http_port, timeout=3)
        http_conn.request('GET', '/')
        page = http_conn.getresponse()
        assert page.status == 200 and page.read()
        session, token = hub.login_web('合成Web用户', '127.0.0.1')
        assert session is not None
        events = http.client.HTTPConnection('127.0.0.1', http_port, timeout=3)
        events.request('GET', '/api/events', headers={'Cookie': f'{web.COOKIE_NAME}={token}'})
        event_response = events.getresponse()
        assert event_response.status == 200
        assert event_response.getheader('Content-Type').startswith('text/event-stream')
        idle_tcp = socket.create_connection(('127.0.0.1', tcp_port), timeout=3)
        wait_for(lambda: any(t.name == 'tcp-client' and t.is_alive() for t in hub._managed_threads))
        stop.set()
        supervisor.join(8)
        if supervisor.is_alive():
            with (tmp_path / 'shutdown-stacks.txt').open('w') as report:
                faulthandler.dump_traceback(file=report, all_threads=True)
            readers = []
            for frame in sys._current_frames().values():
                current = frame
                while current is not None:
                    obj = current.f_locals.get('self')
                    if current.f_code.co_name == 'handle_one_request' and hasattr(obj, 'connection'):
                        readers.append({'path': obj.path.split('?', 1)[0],
                                        'object': id(obj.connection), 'fd': obj.connection.fileno()})
                    current = current.f_back
            (tmp_path / 'socket-close-diagnostic.json').write_text(json.dumps({
                'readers': readers,
                'registry': [{'object': id(c), 'fd': c.fileno()} for c in hub._managed_sockets]}))
        assert not supervisor.is_alive() and not errors, errors
        assert hub._shutdown_result is True and not hub._recovery.owner.held
        assert not any(t.is_alive() for t in hub._managed_threads)
        assert not hub._managed_sockets and web._sse_active == 0
        assert not hub.web_tokens
        saved = strict_json((tmp_path / 'store/state.json').read_bytes())
        assert saved['known'][str(session.uid)]['nick'] == '合成Web用户'
        for port in (tcp_port, http_port):
            with pytest.raises(OSError):
                socket.create_connection(('127.0.0.1', port), timeout=0.2)
    finally:
        stop.set()
        for connection in (idle_tcp, http_conn, events):
            if connection is not None:
                connection.close()
        supervisor.join(12)
        hub.shutdown(normal=False)


def test_bind_failure_never_flushes_and_releases_the_owner(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    before = (tmp_path / 'store/state.json').read_bytes()
    monkeypatch.setattr(hub, '_persist_flush', lambda: pytest.fail('bind failure cannot flush'))
    with socket.socket() as occupied:
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        occupied.bind(('127.0.0.1', 0))
        occupied.listen(1)
        with pytest.raises(OSError):
            serve(hub, port=occupied.getsockname()[1], start_web=False)
    assert hub._service_started is False and hub._recovery.phase == 'FAILED'
    assert not hub._recovery.owner.held
    assert (tmp_path / 'store/state.json').read_bytes() == before


@pytest.mark.parametrize('https', [False, True])
def test_keepalive_and_buffered_http_pipeline_survive_cancellable_wait(tmp_path, https):
    import web
    import tls_cert
    hub = fresh_hub(tmp_path)
    httpd = web.serve(hub, port=0, https=https)
    connection, stream = None, None
    try:
        connection = socket.create_connection(('127.0.0.1', httpd.server_address[1]), timeout=3)
        if https:
            cert, _ = tls_cert.ensure_cert(str(tmp_path / 'web_tls'))
            context = ssl.create_default_context(cafile=cert)
            connection = context.wrap_socket(connection, server_hostname='127.0.0.1')
        stream = connection.makefile('rb')
        connection.sendall(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n'
                           b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        for _ in range(2):
            assert stream.readline().startswith(b'HTTP/1.1 200')
            headers = {}
            while True:
                line = stream.readline()
                if line == b'\r\n':
                    break
                assert line
                key, value = line.decode('latin1').split(':', 1)
                headers[key.lower()] = value.strip()
            body = stream.read(int(headers['content-length']))
            assert len(body) == int(headers['content-length']) and b'<!' in body
        stream.close()
        stream = None
        connection.close()
        connection = None
        assert hub.shutdown(normal=False, timeout=3)
        assert not any(t.is_alive() for t in hub._managed_threads)
    finally:
        if stream:
            stream.close()
        if connection:
            connection.close()
        hub.shutdown(normal=False)


@pytest.mark.parametrize('kind', ['agent', 'preview'])
def test_owned_late_callback_finishes_before_release_without_publishing_after_stop(tmp_path, monkeypatch, kind):
    import agent_bot
    import server as server_mod
    hub = fresh_hub(tmp_path)
    _, _, user, _ = people(hub)
    hub._service_started = True
    entered, release = threading.Event(), threading.Event()
    called = []
    def adapter(*_):
        called.append(kind)
        entered.set()
        assert release.wait(5)
        return '合成迟到答案'
    def preview(*_):
        adapter()
        return {'title': '合成迟到预览', 'url': 'https://example.invalid/'}
    if kind == 'agent':
        monkeypatch.setattr(agent_bot, '_324_ROOT', tmp_path)
        monkeypatch.setattr(agent_bot, '_has_adapter', lambda: True)
        monkeypatch.setattr(agent_bot, '_adapter_answer', adapter)
        agent_bot._dispatch(hub, {'text': '研究 合成', 'uid': user.uid, 'seq': 1})
    else:
        monkeypatch.setattr(server_mod, 'fetch_preview', preview)
        message = hub.bus.publish({'t': 'chat', 'channel': 'public', 'uid': user.uid,
                                  'nick': user.nick, 'text': 'https://example.invalid/', 'ts': 1.0})
        hub._maybe_fetch_preview('https://example.invalid/', message)
    assert entered.wait(5)
    results = []
    closer = threading.Thread(target=lambda: results.append(hub.shutdown(normal=True, timeout=5)))
    try:
        closer.start()
        wait_for(lambda: hub._admission_closed)
        assert hub._recovery.owner.held
        release.set()
        closer.join(5)
        assert not closer.is_alive() and results == [True]
        assert not any(t.is_alive() for t in hub._managed_threads)
        if kind == 'agent':
            assert not hub.bus.history(hub.bus.key('private', agent_bot.get_agent_bot().uid, user.uid))
            monkeypatch.setattr(agent_bot, '_has_adapter', lambda: pytest.fail('no adapter import after close'))
            agent_bot._dispatch(hub, {'text': '研究 新任务', 'uid': user.uid, 'seq': 2})
            assert called == ['agent']
        else:
            _, stored = hub.bus.find(message['seq'])
            assert 'preview' not in stored
            assert not hub._preview_inflight
    finally:
        release.set()
        closer.join(5)
        hub.shutdown(normal=False)


def test_worker_cannot_join_itself_or_release_its_own_store(tmp_path):
    hub = fresh_hub(tmp_path)
    outcomes = []
    worker = hub._start_worker(lambda: outcomes.append(hub.shutdown(normal=True, timeout=0.1)),
                               name='synthetic-self-stop')
    worker.join(3)
    assert not worker.is_alive() and outcomes == [False]
    assert hub._recovery.owner.held and hub._recovery.phase == 'FAILED'
    assert hub.shutdown(normal=False) is False
    assert not hub._recovery.owner.held


def test_zero_budget_does_not_start_a_final_writer(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    hub._service_started = True
    before = (tmp_path / 'store/state.json').read_bytes()
    monkeypatch.setattr(hub, '_persist_flush', lambda: pytest.fail('no final after deadline'))
    assert hub.shutdown(normal=True, timeout=0) is False
    assert not hub._final_started and not hub._final_io_started
    assert (tmp_path / 'store/state.json').read_bytes() == before
    hub.shutdown(normal=False)


def test_final_io_timeout_keeps_owner_until_existing_writer_finishes_once(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    hub._service_started = True
    entered, release = threading.Event(), threading.Event()
    original, writes = hub.store._save_encoded, []
    def blocked_write(encoded):
        writes.append(encoded.sha256)
        entered.set()
        assert release.wait(5)
        return original(encoded)
    monkeypatch.setattr(hub.store, '_save_encoded', blocked_write)
    try:
        assert hub.shutdown(normal=True, timeout=0.2) is False
        assert entered.is_set() and hub._final_timed_out
        assert hub._final_thread.is_alive() and hub._recovery.owner.held
        assert hub._recovery.phase == 'QUIESCING'
        with pytest.raises(StoreError, match='store_in_use'):
            StoreOwner(tmp_path / 'store/.owner.lock').acquire()
        assert hub.store.save({}) is False
        assert hub.shutdown(normal=True, timeout=0.01) is False
        assert hub._final_thread.is_alive() and hub._recovery.owner.held
        assert hub._recovery.phase == 'QUIESCING'
        release.set()
        hub._final_thread.join(5)
        assert not hub._final_thread.is_alive() and len(writes) == 1
        assert hub._recovery.phase == 'FAILED'
        assert hub.shutdown(normal=True) is False
        assert len(writes) == 1 and not hub._recovery.owner.held
    finally:
        release.set()
        if hub._final_thread is not None:
            hub._final_thread.join(5)
        hub.shutdown(normal=False)


def test_stop_rejects_new_writes_but_finishes_only_the_existing_retirement_lease(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    admin, _, user, _ = people(hub)
    original = hub._recovery.accept_intent
    accepted, release = threading.Event(), threading.Event()
    ordinary_results = []
    def pause_after_accept(uid, record):
        result = original(uid, record)
        accepted.set()
        assert release.wait(5)
        ordinary_results.extend([hub._persist(force=True), hub.store.save({})])
        return result
    monkeypatch.setattr(hub._recovery, 'accept_intent', pause_after_accept)
    worker = threading.Thread(target=lambda: retire(hub, admin, user.uid))
    try:
        worker.start()
        assert accepted.wait(5)
        hub._service_stop.set()
        assert not hub._service_available()
        assert hub._start_worker(lambda: pytest.fail('new work after stop')) is None
        assert hub._persist(force=True) is False
        assert hub.store.save_bytes(b'{}').effect == 'not_committed'
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        assert ordinary_results == [False, False]
        assert hub._retirement_payload(user.uid)['status'] == 'confirmed'
        assert str(user.uid) in strict_json((tmp_path / 'store/state.json').read_bytes())['retired']
    finally:
        release.set()
        worker.join(5)
        hub.shutdown(normal=False)


def test_pre_set_stop_still_releases_an_unstarted_store(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    stop = threading.Event()
    stop.set()
    monkeypatch.setattr(hub, '_persist_flush', lambda: pytest.fail('unstarted flush'))
    assert serve(hub, stop=stop, start_web=False) is stop
    assert not hub._service_started and not hub._recovery.owner.held


def test_tls_client_without_clienthello_is_owned_and_cancellable(tmp_path):
    import web
    hub = fresh_hub(tmp_path)
    httpd = web.serve(hub, port=0, https=True)
    raw = socket.create_connection(('127.0.0.1', httpd.server_address[1]), timeout=3)
    try:
        wait_for(lambda: any(t.name == 'http-request' and t.is_alive() for t in tuple(hub._managed_threads)))
        assert hub.shutdown(normal=False, timeout=2)
        assert not hub._recovery.owner.held and not hub._managed_sockets
        assert not any(t.is_alive() for t in hub._managed_threads)
    finally:
        raw.close()
        hub.shutdown(normal=False)


def test_logout_closes_sse_and_does_not_touch_the_revoked_session(tmp_path):
    import web
    hub = fresh_hub(tmp_path)
    httpd = web.serve(hub, port=0, https=False)
    port = httpd.server_address[1]
    session, token = hub.login_web('合成退出用户', '127.0.0.1')
    assert session is not None
    events = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
    logout = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
    try:
        cookie = f'{web.COOKIE_NAME}={token}'
        events.request('GET', '/api/events', headers={'Cookie': cookie})
        response = events.getresponse()
        assert response.status == 200
        wait_for(lambda: web._sse_active == 1)
        logout.request('POST', '/api/logout', body='{}', headers={
            'Cookie': cookie, 'Content-Type': 'application/json',
            'Origin': f'http://127.0.0.1:{port}'})
        result = logout.getresponse()
        assert result.status == 200 and json.loads(result.read())['ok']
        last_seen = session.last_seen
        session.send({'t': 'chat', 'text': '合成迟到内容'})
        wait_for(lambda: web._sse_active == 0)
        assert session.last_seen == last_seen
        assert not hub._session_is_active(session) and token not in hub.web_tokens
    finally:
        events.close()
        logout.close()
        hub.shutdown(normal=False)


@pytest.mark.parametrize('kind', ['web', 'tcp'])
def test_claim_failure_removes_only_the_attempted_session(tmp_path, monkeypatch, kind):
    hub = fresh_hub(tmp_path)
    _, _, survivor, _ = people(hub)
    monkeypatch.setattr(hub, '_store_commit', lambda encoded: SaveResult(
        'not_committed', 'write', 'synthetic_failure', True, encoded.length, encoded.sha256))
    cap = hub.auth_capabilities()
    header = {'auth_v': 1, 'request_id': 'failed_claim', 'claim_password': True,
              'expected_server_epoch': cap['server_epoch'],
              'expected_store_scope_id': cap['store_scope_id']}
    try:
        if kind == 'web':
            failed, failure = hub.login_web('合成失败登录', '127.0.0.1', password='synthetic',
                                            auth_header=header)
            assert failed is None
            assert failure.credential.status == 'failed'
        else:
            failed = Session(0, '合成失败登录', 'tcp', '127.0.0.1', lambda *_: None)
            assert hub._on_hello(failed, {**header, 'nick': failed.nick, 'pwd': 'synthetic'}) is False
            assert failed.uid == 0
        # Failed candidate never published UID/mapping or a Session at all.
        assert '合成失败登录' not in hub.nick_to_uid
        assert not any(s.nick == '合成失败登录' for s in hub.sessions.values())
        assert not any(s.nick == '合成失败登录' for s in hub.web_tokens.values())
        assert hub._session_is_active(survivor)
    finally:
        hub.shutdown(normal=False)


def test_admitted_ordinary_write_drains_once_while_queued_writer_is_rejected(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    _, _, user, _ = people(hub)
    with hub.lock:
        hub.known[user.uid]['sign'] = '停机前已接纳的单次写入'
    entered, release, queued = threading.Event(), threading.Event(), threading.Event()
    original, commits, results = hub._store_commit, [], []
    first = threading.Thread(target=lambda: results.append(('first', hub._persist(force=True))))
    def pause_before_commit(encoded):
        if threading.current_thread() is not first:
            # Initial credential confirmations can leave a background fresh
            # capture. It must not masquerade as the explicitly admitted writer.
            assert not entered.is_set(), 'unexpected writer after admission boundary'
            return original(encoded)
        entered.set()
        assert release.wait(5)
        commits.append(encoded.sha256)
        return original(encoded)
    monkeypatch.setattr(hub, '_store_commit', pause_before_commit)
    def attempt_queued():
        queued.set()
        results.append(('queued', hub._persist(force=True)))
    second = threading.Thread(target=attempt_queued)
    try:
        first.start()
        assert entered.wait(5)
        second.start()
        assert queued.wait(5)
        hub._service_stop.set()
        release.set()
        first.join(5)
        second.join(5)
        assert not first.is_alive() and not second.is_alive()
        assert sorted(results) == [('first', True), ('queued', False)]
        assert len(commits) == 1
        saved = strict_json((tmp_path / 'store/state.json').read_bytes())
        assert saved['known'][str(user.uid)]['sign'] == '停机前已接纳的单次写入'
        assert hub._persist(force=True) is False and len(commits) == 1
    finally:
        release.set()
        first.join(5)
        if second.ident:
            second.join(5)
        hub.shutdown(normal=False)
