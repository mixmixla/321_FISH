"""Authentication nickname maps are injective and never allocate a BOT UID."""
import copy
import json

import pytest

import bots
from server_recovery import StoreCoordinator, StoreError, StoreOwner, validate_state
from server_store import encode_state
from server import Hub, Session
from test_retire_recovery_hub import fresh_hub, people, retire, stop_fixture, config_for


def bad_mapping(kind):
    state = {'uid_seq': 3, 'nick_to_uid': {'alice': 1},
             'known': {'1': {'nick': 'alice'}}}
    if kind == 'known_alias':
        state['nick_to_uid']['other-alice'] = 1
    elif kind == 'unclaimed_alias':
        state['nick_to_uid'].update({'reserved-a': 2, 'reserved-b': 2})
    else:
        bot = bots.BOTS[0]
        state['nick_to_uid']['ordinary-bot-alias'] = bot.uid
        if kind == 'bot_with_record':
            state['known'][str(bot.uid)] = {'nick': bot.nick, 'type': 'bot'}
    return state


KINDS = ['known_alias', 'unclaimed_alias', 'bot_without_record', 'bot_with_record']


@pytest.mark.parametrize('kind', KINDS)
def test_ambiguous_authentication_maps_are_invalid_not_silently_normalized(kind):
    state = bad_mapping(kind)
    before = copy.deepcopy(state)
    with pytest.raises(StoreError, match='invalid_schema'):
        validate_state(state, legacy=True)
    assert state == before


@pytest.mark.parametrize('retired', [False, True])
def test_ordinary_uid_keeps_same_bot_display_name_without_becoming_a_bot(retired):
    bot = bots.BOTS[0]
    state = {'uid_seq': 2, 'nick_to_uid': {bot.nick: 1},
             'known': {str(bot.uid): {'nick': bot.nick, 'type': 'bot'}}}
    if retired:
        state['retired'] = {'1': {'nick': bot.nick, 'retired_at': 1.0, 'operation_id': 'display-only'}}
    else:
        state['known']['1'] = {'nick': bot.nick}
    normalized = validate_state(state, legacy=True)
    assert normalized['nick_to_uid'][bot.nick] == 1
    assert normalized['known'][str(bot.uid)]['type'] == 'bot'
    assert ('1' in normalized['retired']) is retired


@pytest.mark.parametrize('kind', KINDS)
def test_bad_mapping_cannot_be_adopted_or_start_business_services(tmp_path, kind):
    root = tmp_path / 'legacy'
    root.mkdir()
    raw = encode_state(bad_mapping(kind)).payload
    (root / 'state.json').write_bytes(raw)
    with pytest.raises(StoreError, match='invalid_schema'):
        StoreCoordinator.adopt_legacy(root)
    assert (root / 'state.json').read_bytes() == raw
    assert not (root / 'control.json').exists()
    assert not list(root.glob('state.legacy.*'))
    versioned = tmp_path / 'versioned'
    StoreCoordinator.initialize_new(versioned)
    meta = json.loads((versioned / 'state.json').read_bytes())['_store']
    value = bad_mapping(kind)
    value['_store'] = meta
    (versioned / 'state.json').write_bytes(encode_state(value).payload)
    before = {p.name: p.read_bytes() for p in versioned.iterdir()}
    with pytest.raises(StoreError, match='invalid_schema'):
        Hub(cfg=config_for(tmp_path), store_dir=str(versioned))
    assert before == {p.name: p.read_bytes() for p in versioned.iterdir()}
    assert not (tmp_path / 'web').exists() and not (tmp_path / 'audit').exists()
    with StoreOwner(versioned / '.owner.lock'):
        pass


def inject_bad(value, kind):
    if kind == 'known_alias':
        uid = next(uid for uid in value['nick_to_uid'].values() if uid not in bots.BOT_BY_UID)
        value['nick_to_uid']['synthetic-other-alias'] = uid
    elif kind == 'unclaimed_alias':
        value['nick_to_uid'].update({'synthetic-reserved-a': 777, 'synthetic-reserved-b': 777})
    else:
        bot = bots.BOTS[0]
        value['nick_to_uid']['synthetic-bot-alias'] = bot.uid
        if kind == 'bot_without_record':
            value['known'].pop(str(bot.uid), None)
    return value


@pytest.mark.parametrize('kind', KINDS)
def test_bad_mapping_cannot_be_captured_to_disk(tmp_path, monkeypatch, kind):
    hub = fresh_hub(tmp_path)
    people(hub)
    original = hub._snapshot_state
    before = (tmp_path / 'store/state.json').read_bytes()
    monkeypatch.setattr(hub, '_snapshot_state', lambda: inject_bad(original(), kind))
    monkeypatch.setattr(hub.store, '_save_encoded', lambda *_: pytest.fail('bad identity capture cannot write'))
    try:
        assert hub._persist(force=True) is False
        assert hub._recovery.phase == 'FAILED' and hub._persist_dirty
        assert (tmp_path / 'store/state.json').read_bytes() == before
    finally:
        stop_fixture(hub)


@pytest.mark.parametrize('kind', KINDS)
def test_bad_mapping_actual_readback_never_confirms_or_repairs_by_writing(tmp_path, monkeypatch, kind):
    hub = fresh_hub(tmp_path)
    admin, _, user, _ = people(hub)
    original_save = hub.store._save_encoded
    path = tmp_path / 'store/state.json'
    def corrupt_after_write(encoded):
        result = original_save(encoded)
        assert result.effect == 'committed'
        path.write_bytes(encode_state(inject_bad(json.loads(encoded.payload), kind)).payload)
        return result
    monkeypatch.setattr(hub.store, '_save_encoded', corrupt_after_write)
    try:
        retire(hub, admin, user.uid)
        assert hub._retirement_payload(user.uid)['status'] == 'unknown'
        raw = path.read_bytes()
        monkeypatch.setattr(hub.store, '_save_encoded', lambda *_: pytest.fail('unknown alias authority cannot write'))
        hub._on_admin_user_get(admin, {'uid': user.uid, 'request_id': 'alias-readonly'})
        assert hub._persist(force=True) is False
        assert hub._retirement_payload(user.uid)['status'] == 'unknown'
        assert path.read_bytes() == raw
    finally:
        stop_fixture(hub)


def test_real_ordinary_login_with_bot_display_name_roundtrips_its_distinct_uid(tmp_path):
    bot = bots.BOTS[0]
    hub = fresh_hub(tmp_path)
    user = Session(0, bot.nick, 'tcp', '127.0.0.1', lambda *_: None)
    try:
        assert hub._on_hello(user, {'nick': bot.nick})
        assert user.uid not in bots.BOT_BY_UID and not user.is_admin
        assert hub._persist(force=True)
    finally:
        stop_fixture(hub)
    reopened = Hub(cfg=config_for(tmp_path), store_dir=str(tmp_path / 'store'))
    try:
        again = Session(0, bot.nick, 'tcp', '127.0.0.1', lambda *_: None)
        assert reopened._on_hello(again, {'nick': bot.nick}) and again.uid == user.uid
        assert reopened.known[bot.uid]['type'] == 'bot'
        assert reopened.known[again.uid].get('type', '') != 'bot'
    finally:
        stop_fixture(reopened)
