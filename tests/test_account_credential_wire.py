"""Actual HTTP and encrypted TCP; only synthetic profiles and loopback sockets."""
import http.client
import json
import socket
import threading
import time
import urllib.parse

import pytest

import auth
from credential_ops import CredentialError, WebContext
from crypto import client_handshake
from server import Hub, serve
from server_recovery import strict_json
from test_retire_recovery_hub import config_for, fresh_hub
from web import COOKIE_NAME, serve as serve_web


class HttpPeer:
    def __init__(self, port):
        self.port, self.cookie, self.context, self.token = port, '', None, ''

    def request(self, method, path, body=None, *, bind=False, headers=None, raw=None):
        fields = {'Content-Type': 'application/json'}
        if self.cookie:
            fields['Cookie'] = self.cookie
        if bind and self.context is not None:
            fields['X-Moyu-Context'] = self.context.encode()
        fields.update(headers or {})
        payload = raw if raw is not None else json.dumps(body).encode() if body is not None else None
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=8)
        try:
            conn.request(method, path, body=payload, headers=fields)
            response = conn.getresponse()
            result = json.loads(response.read())
            cookie = response.getheader('Set-Cookie')
            if cookie:
                self.cookie = cookie.split(';', 1)[0]
            return response.status, result, cookie
        finally:
            conn.close()

    def login(self, nick, password='', *, claim=False, rid='login', site_password=''):
        status, meta, _ = self.request('GET', '/api/meta')
        assert status == 200
        cap = meta['auth']
        body = {'nick': nick, 'nick_pwd': password, 'password': site_password,
                'claim_password': claim, 'auth_v': 1, 'request_id': rid,
                'expected_server_epoch': cap['server_epoch'],
                'expected_store_scope_id': cap['store_scope_id']}
        result = self.request('POST', '/api/login', body)
        if result[0] == 200:
            data = result[1]
            self.context = WebContext(data['auth']['server_epoch'], data['auth']['store_scope_id'],
                                      data['uid'], data['session_binding_id'])
            self.token = data['token']
        return result

    def update(self, old, new, rid, **kwargs):
        return self.request('POST', '/api/passwd', {'credential_v': 1, 'request_id': rid,
                                                    'old': old, 'new': new}, bind=True, **kwargs)

    def query(self, result, *, rid='query'):
        data = {'credential_v': '1', 'request_id': rid,
                'original_request_id': result['original_request_id'],
                'operation_epoch': result['operation_epoch']}
        if result.get('operation_id'):
            data['operation_id'] = result['operation_id']
        return self.request('GET', '/api/credential_result?' + urllib.parse.urlencode(data), bind=True)


@pytest.fixture
def http_env(tmp_path):
    hub = fresh_hub(tmp_path)
    listener = serve_web(hub, port=0, https=False)
    try:
        yield hub, listener.server_address[1]
    finally:
        hub.shutdown(normal=False, timeout=8)
        assert not hub._recovery.owner.held
        assert not any(t.is_alive() for t in hub._managed_threads)


def test_http_meta_login_and_whoami_keep_bootstrap_and_confirm_disk(http_env, tmp_path):
    hub, port = http_env
    peer = HttpPeer(port)
    before = (tmp_path / 'store/state.json').read_bytes()
    status, meta, _ = peer.request('GET', '/api/meta')
    assert status == 200 and set(meta) == {'ok', 'site_pwd', 'auth'}
    assert set(meta['auth']) == {'v', 'server_epoch', 'store_scope_id', 'store_mode',
                                 'credential_commit_v', 'web_binding_v'}
    assert (tmp_path / 'store/state.json').read_bytes() == before
    status, data, cookie = peer.login('合成HTTP认领', 'synthetic-http', claim=True)
    assert status == 200 and data['ok']
    assert cookie and 'HttpOnly' in cookie and 'SameSite=Strict' in cookie
    assert data['credential']['status'] == 'confirmed'
    assert data['credential']['login_status'] == 'attached'
    state = strict_json((tmp_path / 'store/state.json').read_bytes())
    assert auth.verify('synthetic-http', state['known'][str(data['uid'])]['pwd'])
    status, restored, _ = peer.request('GET', '/api/whoami')
    assert status == 200 and restored['uid'] == data['uid']
    assert restored['session_binding_id'] == data['session_binding_id']
    assert restored['auth'] == data['auth']
    assert {'token', 'roster', 'known', 'groups', 'bots', 'convos', 'stickers',
            'custom_stickers', 'sticker_pack_meta', 'sticker_subs', 'history',
            'drafts', 'blocked'} <= restored.keys()
    assert 'credential' not in restored  # No anonymous query of the past claim.


def test_http_legacy_login_and_set_are_explicitly_limited(http_env):
    hub, port = http_env
    peer = HttpPeer(port)
    status, data, cookie = peer.request('POST', '/api/login',
                                      {'nick': '合成旧HTTP', 'password': 'synthetic-old'})
    assert status == 409 and data['reason'] == 'claim_required' and cookie is None
    assert '合成旧HTTP' not in hub.nick_to_uid
    status, data, _ = peer.request('POST', '/api/login', {'nick': '合成旧HTTP'})
    assert status == 200 and data['ok']
    status, result, _ = peer.request('POST', '/api/passwd', {'old': '', 'new': 'synthetic-old'})
    assert status == 426 and result['reason'] == 'credential_upgrade_required'
    assert not hub.known[data['uid']].get('pwd')


def test_http_change_query_clear_and_other_uid_query_is_unknown(http_env):
    hub, port = http_env
    one, other = HttpPeer(port), HttpPeer(port)
    assert one.login('合成HTTP修改', 'synthetic-old', claim=True)[0] == 200
    status, result, _ = one.update('synthetic-old', 'synthetic-new', 'change')
    assert status == 200 and result['status'] == 'confirmed' and result['persisted']
    status, query, _ = one.query(result)
    assert status == 200 and query['status'] == 'confirmed'
    assert query['request_id'] == 'query' and query['original_request_id'] == 'change'
    assert other.login('合成HTTP旁观')[0] == 200
    status, unknown, _ = other.query(result)
    assert status == 200 and unknown['status'] == 'unknown'
    assert unknown['reason'] == 'operation_unavailable' and 'persisted' not in unknown
    assert one.update('synthetic-new', '', 'clear')[0] == 200
    assert not hub.known[one.context.uid].get('pwd')
    stale = HttpPeer(port)
    assert stale.login('合成HTTP修改', 'synthetic-new')[1]['reason'] == 'claim_required'


def test_http_claim_replay_returns_same_proof_then_cannot_rebind_after_clear(http_env):
    hub, port = http_env
    first, duplicate = HttpPeer(port), HttpPeer(port)
    status, data, _ = first.login('合成HTTP认领重复', 'synthetic-old', claim=True, rid='same')
    assert status == 200
    status, again, _ = duplicate.login('合成HTTP认领重复', 'synthetic-old', claim=True, rid='same')
    assert status == 200 and again['credential']['operation_id'] == data['credential']['operation_id']
    assert first.update('synthetic-old', '', 'clear')[0] == 200
    status, refused, _ = HttpPeer(port).login('合成HTTP认领重复', 'synthetic-old', claim=True, rid='same')
    assert status == 409 and refused['reason'] == 'claim_required' and 'credential' not in refused
    assert not hub.known[data['uid']].get('pwd')


def test_cookie_priority_and_context_prevent_old_tab_changing_new_identity(http_env):
    hub, port = http_env
    a, b = HttpPeer(port), HttpPeer(port)
    assert a.login('合成TabA')[0] == 200 and b.login('合成TabB')[0] == 200
    body = {'credential_v': 1, 'request_id': 'cross_tab', 'old': '', 'new': 'synthetic-cross',
            'token': a.token, 'uid': a.context.uid}
    status, result, cookie = a.request('POST', '/api/passwd', body, bind=True,
                                      headers={'Cookie': b.cookie})
    assert status == 409 and result['reason'] == 'context_changed' and cookie is None
    assert not hub.known[a.context.uid].get('pwd') and not hub.known[b.context.uid].get('pwd')
    status, result, _ = a.request('POST', '/api/passwd', body, bind=True,
                                 headers={'Cookie': COOKIE_NAME + '='})
    assert status == 401 and not hub.known[a.context.uid].get('pwd')
    a.cookie = ''  # Explicit-token programmatic client still needs its binding.
    status, result, _ = a.request('POST', '/api/passwd', body, bind=True)
    assert status == 200 and result['status'] == 'confirmed'
    assert auth.verify('synthetic-cross', hub.known[a.context.uid]['pwd'])
    assert not hub.known[b.context.uid].get('pwd')


def test_http_context_header_query_and_origin_are_enforced(http_env):
    hub, port = http_env
    peer = HttpPeer(port)
    assert peer.login('合成HTTP上下文')[0] == 200
    body = {'credential_v': 1, 'request_id': 'context', 'old': '', 'new': 'synthetic-new'}
    assert peer.request('POST', '/api/passwd', {**body, 'context': peer.context.payload()})[0] == 428
    assert peer.request('POST', '/api/passwd', body,
                        headers={'X-Moyu-Context': 'not_base64!'})[0] == 400
    wrong = WebContext(peer.context.server_epoch, peer.context.store_scope_id,
                        peer.context.uid, 'f' * 32).encode()
    status, result, _ = peer.request('POST', '/api/passwd?moyu_ctx=' + wrong, body, bind=True)
    assert status == 400 and result['reason'] == 'context_invalid'
    status, result, _ = peer.request('POST', '/api/passwd', body, bind=True,
                                     headers={'Origin': 'https://synthetic.invalid'})
    assert status == 403 and not hub.known[peer.context.uid].get('pwd')


@pytest.mark.parametrize('raw', [
    b'[]', b'{', b'{"credential_v":1,"request_id":"bad","old":"","new":"x","new":"y"}',
    b'{"credential_v":1,"request_id":"bad","old":""}',
    b'{"credential_v":1,"request_id":"bad","old":"","new":null}',
    b'{"credential_v":1,"request_id":"bad","old":"","new":NaN}',
])
def test_bad_credential_json_never_clears_or_sets(http_env, raw):
    hub, port = http_env
    peer = HttpPeer(port)
    assert peer.login('合成错误请求', 'synthetic-original', claim=True)[0] == 200
    stored = hub.known[peer.context.uid]['pwd']
    status, _, _ = peer.request('POST', '/api/passwd', raw=raw, bind=True)
    assert status == 400 and hub.known[peer.context.uid]['pwd'] == stored


def test_site_password_and_v1_nickname_password_have_independent_meaning(http_env):
    hub, port = http_env
    peer = HttpPeer(port)
    assert peer.login('合成错误站点字段', site_password='synthetic-wrong')[1]['reason'] == 'unexpected_site_password'
    hub._web_password = 'synthetic-site'
    assert peer.login('合成独立密码', 'synthetic-nick', claim=True,
                      site_password='synthetic-site')[0] == 200
    stored = hub.known[peer.context.uid]['pwd']
    assert auth.verify('synthetic-nick', stored) and not auth.verify('synthetic-site', stored)


def test_http_session_replaced_during_derivation_cannot_change_new_session(http_env, monkeypatch):
    hub, port = http_env
    a, b = HttpPeer(port), HttpPeer(port)
    assert a.login('合成HTTP代次', 'synthetic-old', claim=True)[0] == 200
    entered, release = threading.Event(), threading.Event()
    original_make = auth.make
    responses = []

    def make(value):
        if value == 'synthetic-new':
            entered.set()
            assert release.wait(5)
        return original_make(value)

    monkeypatch.setattr(auth, 'make', make)
    thread = threading.Thread(target=lambda: responses.append(a.update('synthetic-old', 'synthetic-new', 'late')))
    try:
        thread.start()
        assert entered.wait(5)
        hub.unregister(hub.session_by_token(a.token), 'synthetic old tab logout')
        assert b.login('合成HTTP代次', 'synthetic-old', rid='new_session')[0] == 200
        release.set()
        thread.join(8)
        assert not thread.is_alive() and len(responses) == 1
        status, result, cookie = responses[0]
        assert status == 401 and result['reason'] == 'session_inactive' and cookie is None
        assert hub.session_by_token(b.token) is not None
        assert auth.verify('synthetic-old', hub.known[b.context.uid]['pwd'])
    finally:
        release.set()
        thread.join(8)


def test_http_metadata_failure_after_registration_removes_undelivered_session(http_env, monkeypatch):
    hub, port = http_env
    peer = HttpPeer(port)
    status, meta, _ = peer.request('GET', '/api/meta')
    assert status == 200
    original_capabilities = hub.auth_capabilities

    def metadata():
        if hub.web_tokens:
            raise CredentialError('service_unavailable')
        return original_capabilities()

    # Allow Hub's complete login to return, then fail only the HTTP metadata read.
    original_login = hub.login_web

    def login_then_break_metadata(*args, **kwargs):
        result = original_login(*args, **kwargs)
        monkeypatch.setattr(hub, 'auth_capabilities', metadata)
        return result

    monkeypatch.setattr(hub, 'login_web', login_then_break_metadata)
    cap = meta['auth']
    status, result, cookie = peer.request('POST', '/api/login', {
        'nick': '合成HTTP响应失败', 'nick_pwd': 'synthetic-claim', 'claim_password': True,
        'auth_v': 1, 'request_id': 'metadata_failure', 'expected_server_epoch': cap['server_epoch'],
        'expected_store_scope_id': cap['store_scope_id']})
    assert status == 503 and cookie is None
    assert not hub.sessions and not hub.web_tokens
    assert result['credential']['status'] == 'confirmed'
    assert result['credential']['login_status'] == 'not_attached'


class TcpPeer:
    def __init__(self, port):
        self.sock = socket.create_connection(('127.0.0.1', port), timeout=8)
        self.channel = client_handshake(self.sock)

    def send(self, header):
        self.channel.send_frame(header)

    def receive(self, kind, *, request_id=None):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            self.sock.settimeout(max(0.01, deadline - time.monotonic()))
            header, _ = self.channel.recv_frame()
            if header.get('t') == kind and (request_id is None or header.get('request_id') == request_id):
                return header
        pytest.fail('synthetic wire response missing')

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


def test_encrypted_tcp_probe_claim_change_query_clear_and_legacy_refusal(tmp_path):
    hub = fresh_hub(tmp_path)
    stop = threading.Event()
    failures = []

    def run():
        try:
            serve(hub, 0, stop, False)
        except BaseException as exc:
            failures.append(type(exc).__name__)

    thread = threading.Thread(target=run)
    peers = []
    try:
        thread.start()
        deadline = time.monotonic() + 5
        while not hub._service_started:
            assert not failures and time.monotonic() < deadline
            time.sleep(0.01)
        port = next(iter(hub._listener_sockets)).getsockname()[1]
        a = TcpPeer(port)
        peers.append(a)
        a.send({'t': 'auth_capabilities', 'auth_v': 1, 'request_id': 'cap'})
        cap = a.receive('auth_capabilities', request_id='cap')['auth']
        assert not hub.nick_to_uid
        a.send({'t': 'hello', 'nick': '合成加密TCP', 'pwd': 'synthetic-old',
                'auth_v': 1, 'request_id': 'claim', 'claim_password': True,
                'expected_server_epoch': cap['server_epoch'],
                'expected_store_scope_id': cap['store_scope_id']})
        welcome = a.receive('welcome')
        assert welcome['credential']['status'] == 'confirmed'
        a.send({'t': 'set_pwd', 'credential_v': 1, 'request_id': 'set',
                'old': 'synthetic-old', 'new': 'synthetic-new'})
        changed = a.receive('credential_result', request_id='set')
        assert changed['status'] == 'confirmed'
        a.send({'t': 'credential_get', 'credential_v': 1, 'request_id': 'get',
                'original_request_id': 'set', 'operation_id': changed['operation_id'],
                'operation_epoch': changed['operation_epoch']})
        assert a.receive('credential_result', request_id='get')['status'] == 'confirmed'
        b = TcpPeer(port)
        peers.append(b)
        b.send({'t': 'hello', 'nick': '合成加密TCP', 'pwd': 'synthetic-new'})
        assert b.receive('welcome')['uid'] == welcome['uid']
        a.send({'t': 'set_pwd', 'credential_v': 1, 'request_id': 'clear',
                'old': 'synthetic-new', 'new': ''})
        assert a.receive('credential_result', request_id='clear')['status'] == 'confirmed'
        b.send({'t': 'chat', 'channel': 'public', 'text': 'synthetic D6 session remains'})
        assert b.receive('chat')['text'] == 'synthetic D6 session remains'
        b.send({'t': 'set_pwd', 'old': '', 'new': 'synthetic-legacy'})
        assert b.receive('error')['reason'] == 'credential_upgrade_required'
        stale = TcpPeer(port)
        peers.append(stale)
        stale.send({'t': 'hello', 'nick': '合成加密TCP', 'pwd': 'synthetic-new'})
        assert stale.receive('error')['reason'] == 'claim_required'
        assert not hub.known[welcome['uid']].get('pwd')
    finally:
        for peer in peers:
            peer.close()
        stop.set()
        thread.join(10)
        assert not thread.is_alive() and not failures
        assert not hub._recovery.owner.held


def test_actual_tcp_shutdown_progresses_while_password_derivation_waits(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    stop, entered, release = threading.Event(), threading.Event(), threading.Event()
    failures = []

    def run():
        try:
            serve(hub, 0, stop, False)
        except BaseException as exc:
            failures.append(type(exc).__name__)

    server_thread = threading.Thread(target=run)
    peer = None
    try:
        server_thread.start()
        deadline = time.monotonic() + 5
        while not hub._service_started:
            assert not failures and time.monotonic() < deadline
            time.sleep(0.01)
        port = next(iter(hub._listener_sockets)).getsockname()[1]
        peer = TcpPeer(port)
        cap = hub.auth_capabilities()
        peer.send({'t': 'hello', 'nick': '合成停止派生', 'pwd': 'synthetic-old',
                   'auth_v': 1, 'request_id': 'claim', 'claim_password': True,
                   'expected_server_epoch': cap['server_epoch'],
                   'expected_store_scope_id': cap['store_scope_id']})
        user = peer.receive('welcome')['uid']
        original_make = auth.make

        def make(value):
            if value == 'synthetic-delayed':
                entered.set()
                assert release.wait(6)
            return original_make(value)

        monkeypatch.setattr(auth, 'make', make)
        peer.send({'t': 'set_pwd', 'credential_v': 1, 'request_id': 'shutdown',
                   'old': 'synthetic-old', 'new': 'synthetic-delayed'})
        assert entered.wait(5)
        assert hub._persist_writer_lock.acquire(timeout=1)
        hub._persist_writer_lock.release()
        stop.set()
        deadline = time.monotonic() + 5
        while not hub._admission_closed:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert hub._recovery.owner.held and server_thread.is_alive()
        release.set()
        server_thread.join(10)
        assert not server_thread.is_alive() and not failures
        state = strict_json((tmp_path / 'store/state.json').read_bytes())
        assert auth.verify('synthetic-old', state['known'][str(user)]['pwd'])
        assert not hub._recovery.owner.held
    finally:
        release.set()
        if peer is not None:
            peer.close()
        stop.set()
        server_thread.join(10)
        hub.shutdown(normal=False, timeout=2)
