"""Credential admission contracts over fresh synthetic stores and sessions."""
import copy

import auth
from server import Hub, Session
from server_recovery import strict_json
from test_retire_recovery_hub import config_for, fresh_hub, login, stop_fixture


def session(nick, frames):
    return Session(0, nick, 'tcp', '127.0.0.1', lambda h, *_: frames.append(h))


def test_legacy_password_does_not_implicitly_claim_or_authorize(tmp_path):
    hub = fresh_hub(tmp_path)
    before = (tmp_path / 'store/state.json').read_bytes()
    frames = []
    attempt = session('合成隐式认领', frames)
    uid_seq = hub._uid_seq
    try:
        accepted = hub.dispatch(attempt, {'t': 'hello', 'nick': attempt.nick,
                                          'pwd': 'synthetic-claim'})
        assert accepted is False
        assert not any(h.get('t') == 'welcome' for h in frames)
        assert any(h.get('reason') == 'claim_required' for h in frames)
        assert attempt.uid == 0 and attempt.nick not in hub.nick_to_uid
        assert hub._uid_seq == uid_seq
        assert (tmp_path / 'store/state.json').read_bytes() == before
    finally:
        stop_fixture(hub)


def test_legacy_set_password_requires_upgrade_without_changing_live_or_disk(tmp_path):
    hub = fresh_hub(tmp_path)
    user, frames = login(hub, '合成旧端改密')
    assert hub._persist(force=True)
    before = (tmp_path / 'store/state.json').read_bytes()
    frames.clear()
    try:
        assert hub.dispatch(user, {'t': 'set_pwd', 'old': '', 'new': 'synthetic-set'})
        assert not hub.known[user.uid].get('pwd')
        assert any(h.get('reason') == 'credential_upgrade_required' for h in frames)
        assert not any(h.get('t') == 'system' for h in frames)
        assert (tmp_path / 'store/state.json').read_bytes() == before
    finally:
        stop_fixture(hub)


def test_volatile_set_password_rejects_before_derivation(tmp_path, monkeypatch):
    hub = Hub(cfg=config_for(tmp_path))
    frames = []
    user = session('合成临时账号', frames)
    assert hub._on_hello(user, {'nick': user.nick})
    frames.clear()
    calls = []
    original_make = auth.make

    def derive(value):
        calls.append(value)
        return original_make(value)

    monkeypatch.setattr(auth, 'make', derive)
    try:
        assert hub.dispatch(user, {'t': 'set_pwd', 'credential_v': 1,
                                  'request_id': 'volatile_set', 'old': '',
                                  'new': 'synthetic-set'})
        assert not calls
        assert not hub.known[user.uid].get('pwd')
        assert any(h.get('reason') == 'credential_store_unavailable' for h in frames)
    finally:
        hub.shutdown(normal=False)


def test_login_rechecks_credential_proof_before_session_registration(tmp_path, monkeypatch):
    hub = fresh_hub(tmp_path)
    user, _ = login(hub, '合成凭据竞争')
    before_hash, after_hash = auth.make('synthetic-before'), auth.make('synthetic-after')
    with hub.lock:
        hub.known[user.uid]['pwd'] = before_hash
    assert hub._persist(force=True)
    original_verify = auth.verify
    changed = []

    def verify_then_change(password, stored):
        valid = original_verify(password, stored)
        if valid and password == 'synthetic-before' and not changed:
            # A deterministic concurrent-authority seam. The expected value must
            # be rechecked even if a legacy writer failed to increment revision.
            with hub.lock:
                hub.known[user.uid]['pwd'] = after_hash
            changed.append(True)
        return valid

    monkeypatch.setattr(auth, 'verify', verify_then_change)
    frames = []
    attempt = session(user.nick, frames)
    try:
        assert hub._on_hello(attempt, {'nick': user.nick, 'pwd': 'synthetic-before'}) is False
        assert changed == [True]
        assert not any(h.get('t') == 'welcome' for h in frames)
        assert attempt not in hub._uid_clients[user.uid]
        assert hub.known[user.uid]['pwd'] == after_hash
        assert hub._session_is_active(user)  # D6 keeps the previously logged-in session.
    finally:
        stop_fixture(hub)


def test_capability_probe_has_no_identity_or_store_side_effect(tmp_path):
    hub = fresh_hub(tmp_path)
    before_bytes = (tmp_path / 'store/state.json').read_bytes()
    before = copy.deepcopy((hub.known, hub.nick_to_uid, hub._uid_seq))
    frames = []
    attempt = session('', frames)
    try:
        assert hub.dispatch(attempt, {'t': 'auth_capabilities', 'auth_v': 1,
                                      'request_id': 'cap_1'}) is True
        reply = next(h for h in frames if h.get('t') == 'auth_capabilities')
        assert reply['request_id'] == 'cap_1'
        assert reply['auth']['store_scope_id'] == hub._recovery.store_id
        assert reply['auth']['store_mode'] == 'durable'
        assert reply['auth']['credential_commit_v'] == 1
        assert len(reply['auth']['server_epoch']) == 32
        assert (hub.known, hub.nick_to_uid, hub._uid_seq) == before
        assert not hub.sessions and not hub.web_tokens
        assert (tmp_path / 'store/state.json').read_bytes() == before_bytes
        assert hub.dispatch(attempt, {'t': 'auth_capabilities', 'auth_v': 1,
                                      'request_id': 'cap_2'}) is False
    finally:
        stop_fixture(hub)


def test_new_identity_is_durable_before_welcome(tmp_path):
    hub = fresh_hub(tmp_path)
    observed = []

    def on_frame(h, *_):
        if h.get('t') == 'welcome':
            state = strict_json((tmp_path / 'store/state.json').read_bytes())
            observed.append((state.get('nick_to_uid', {}).get(h['nick']),
                             state.get('known', {}).get(str(h['uid']))))

    user = Session(0, '合成持久免密', 'tcp', '127.0.0.1', on_frame)
    try:
        assert hub._on_hello(user, {'nick': user.nick})
        assert len(observed) == 1
        assert observed[0][0] == user.uid
        assert observed[0][1]['nick'] == user.nick
        assert not observed[0][1].get('pwd')
    finally:
        stop_fixture(hub)
