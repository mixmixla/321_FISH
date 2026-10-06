"""Audit-only characterization of legacy Prefs with synthetic temporary data.

PASS means the observed baseline behavior is reproduced, including known
loss/coercion conflicts. It does not approve those conflicts for a new schema.
No application UI, real preferences, owner registry or migration is exercised.
"""
import json
import math

import pytest

from auth import verify
from prefs import Prefs


def seeded(tmp_path, value):
    path = tmp_path / 'synthetic-prefs.json'
    path.write_text(json.dumps(value), 'utf-8')
    return Prefs(str(path)), path


def test_audit_stars_dict_uses_legacy_view_but_survives_later_unrelated_save(tmp_path):
    favorites = {'public': {'7': {'text': 'synthetic favorite', 'ts': 1}}}
    prefs, path = seeded(tmp_path, {'stars': favorites})
    original = path.read_bytes()
    assert prefs.get('stars') == []
    assert path.read_bytes() == original  # _load itself did not delete the source
    prefs.set('dnd', True)
    assert json.loads(path.read_text('utf-8'))['stars'] == favorites


def test_audit_profile_stars_dict_cannot_be_assigned_or_overwritten_by_switch(tmp_path):
    favorites = {'public': {'7': {'text': 'synthetic favorite', 'ts': 1}}}
    prefs, _ = seeded(tmp_path, {'profiles': {'alpha': {'stars': favorites}, 'beta': {}}})
    with pytest.raises(ValueError):
        prefs.switch_profile('alpha')
    assert prefs.get('stars') == []
    assert prefs.get('profiles')['alpha']['stars'] == favorites
    prefs.switch_profile('beta')
    assert prefs.get('profiles')['alpha']['stars'] == favorites


@pytest.mark.parametrize('conversation', ['public', 'group:1'])
def test_audit_conversation_star_api_cannot_use_message_favorite_dict(tmp_path, conversation):
    prefs = Prefs(str(tmp_path / 'synthetic-prefs.json'))
    favorites = {'public': {'7': {'text': 'synthetic favorite'}}}
    prefs.set('stars', favorites)
    with pytest.raises(ValueError):
        prefs.toggle_star(conversation)
    assert prefs.get('stars') == favorites


def test_audit_current_profile_switch_does_not_partition_other_designed_owner_fields(tmp_path):
    prefs = Prefs(str(tmp_path / 'synthetic-prefs.json'))
    prefs.remember_account('alpha')
    prefs.set('drafts', {'public': 'alpha draft'})
    prefs.set('auto_reply_text', 'alpha reply')
    prefs.set('excel_cells', {'E1': 'alpha cell'})
    prefs.switch_profile('beta')
    assert prefs.get('drafts') == {}
    assert prefs.get('auto_reply_text') == 'alpha reply'
    assert prefs.get('excel_cells') == {'E1': 'alpha cell'}


@pytest.mark.parametrize('key', ['pinned', 'muted', 'archived', 'stars', 'unread_marks'])
def test_audit_known_list_loader_coerces_items_to_strings(tmp_path, key):
    prefs, _ = seeded(tmp_path, {key: [1, False, None, {'x': 2}]})
    assert prefs.get(key) == ['1', 'False', 'None', "{'x': 2}"]


def test_audit_unknown_legacy_extension_survives_load_and_an_unrelated_save(tmp_path):
    extension = {'opaque': [1, False, {'future': 'synthetic'}]}
    prefs, path = seeded(tmp_path, {'future_extension': extension})
    assert prefs.get('future_extension') == extension
    prefs.set('dnd', True)
    assert json.loads(path.read_text('utf-8'))['future_extension'] == extension


@pytest.mark.parametrize('stored', ['synthetic-invalid-hash', True, ['synthetic'], {'opaque': 'synthetic'}])
def test_audit_malformed_truthy_security_value_is_retained_and_not_validated_as_unlocked(tmp_path, stored):
    prefs, path = seeded(tmp_path, {'passcode': stored})
    original = path.read_bytes()
    assert prefs.passcode() == stored
    assert prefs.has_passcode() is True
    assert verify('synthetic-attempt', prefs.passcode()) is False
    assert path.read_bytes() == original


def test_audit_corrupt_document_and_missing_document_cannot_prove_lock_is_disabled(tmp_path):
    corrupt = tmp_path / 'synthetic-corrupt.json'
    corrupt.write_text('{ invalid synthetic JSON', 'utf-8')
    original = corrupt.read_bytes()
    damaged = Prefs(str(corrupt))
    missing = Prefs(str(tmp_path / 'synthetic-missing.json'))
    # Both currently expose the same default. This is an ambiguity, not an
    # accepted upgrade/security policy or authorization to clear an old lock.
    assert damaged.has_passcode() is missing.has_passcode() is False
    assert corrupt.read_bytes() == original


def test_audit_generic_numeric_storage_has_no_finite_number_validation(tmp_path):
    path = tmp_path / 'synthetic-prefs.json'
    prefs = Prefs(str(path))
    prefs.set('chat_alpha', math.nan)
    assert math.isnan(prefs.get('chat_alpha'))
    assert math.isnan(Prefs(str(path)).get('chat_alpha'))


def test_audit_get_returns_a_live_container_without_implicit_save(tmp_path):
    prefs, path = seeded(tmp_path, {'drafts': {}})
    prefs.get('drafts')['public'] = 'synthetic unsaved draft'
    assert prefs.get('drafts') == {'public': 'synthetic unsaved draft'}
    assert json.loads(path.read_text('utf-8'))['drafts'] == {}


def test_audit_boolean_fields_do_not_share_one_strict_legacy_rule(tmp_path):
    prefs, _ = seeded(tmp_path, {'dnd': 'false', 'frameless': 'false'})
    assert prefs.get('dnd') is False  # _load accepts only bool for dnd
    assert prefs.get('frameless') == 'false'
    assert prefs.frameless() is True  # existing accessor uses truthiness
