"""Synthetic regression for stars preservation; handler tests do not prove GUI acceptance."""
import ast
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from prefs import Prefs, trim_stars

FAVORITES = {'public': {'7': {'text': 'synthetic favorite', 'ts': 1}}}
OPAQUE = [FAVORITES, {}, None, False, 0, 'future-format']


def seed(tmp_path, payload):
    path = tmp_path / 'synthetic-prefs.json'
    path.write_text(json.dumps(payload), 'utf-8')
    original = path.read_bytes()
    prefs = Prefs(str(path))
    assert path.read_bytes() == original
    return prefs, path


def saved(path):
    return json.loads(path.read_text('utf-8'))


@pytest.mark.parametrize('raw', OPAQUE)
def test_unrelated_repeated_saves_and_reopen_preserve_opaque_top_stars(tmp_path, raw):
    prefs, path = seed(tmp_path, {'stars': raw, 'future': {'opaque': [False, 3]}})
    assert prefs.get('stars') == []  # preserve the existing reader view
    for value in [True, False, True]:
        prefs.set('dnd', value)
        assert saved(path)['stars'] == raw
        assert saved(path)['future'] == {'opaque': [False, 3]}
    reopened = Prefs(str(path))
    reopened.toggle_pin('group:1')
    assert saved(path)['stars'] == raw


@pytest.mark.parametrize('operation', ['set-list', 'set-dict', 'toggle', 'remember', 'switch'])
def test_destructive_top_operations_reject_before_mutation_or_save(tmp_path, operation):
    prefs, path = seed(tmp_path, {'stars': FAVORITES})
    before = path.read_bytes()
    state = deepcopy(prefs._data)
    with pytest.raises(ValueError):
        if operation == 'set-list':
            prefs.set('stars', [])
        elif operation == 'set-dict':
            prefs.set('stars', {})
        elif operation == 'toggle':
            prefs.toggle_star('public')
        elif operation == 'remember':
            prefs.remember_account('alpha')
        else:
            prefs.switch_profile('alpha')
    assert path.read_bytes() == before
    assert prefs._data == state


@pytest.mark.parametrize('raw', OPAQUE)
def test_opaque_profile_switch_in_rejects_without_changing_any_field(tmp_path, raw):
    prefs, path = seed(tmp_path, {'active_profile': 'beta', 'stars': ['group:1'],
                                'profiles': {'alpha': {'stars': raw}, 'beta': {}}})
    state = deepcopy(prefs._data)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        prefs.switch_profile('alpha')
    assert prefs._data == state
    assert path.read_bytes() == before
    prefs.set('dnd', True)
    assert saved(path)['profiles']['alpha']['stars'] == raw


def test_switch_out_does_not_overwrite_opaque_saved_profile_snapshot(tmp_path):
    prefs, path = seed(tmp_path, {'active_profile': 'alpha', 'stars': [],
                                'profiles': {'alpha': {'stars': FAVORITES}, 'beta': {}}})
    before = path.read_bytes()
    state = deepcopy(prefs._data)
    with pytest.raises(ValueError):
        prefs.switch_profile('beta')
    assert prefs._data == state
    assert path.read_bytes() == before


@pytest.mark.parametrize('replacement', [{}, {'alpha': {}}, {'alpha': {'stars': []}}])
def test_generic_profiles_set_cannot_erase_protected_stars(tmp_path, replacement):
    prefs, path = seed(tmp_path, {'profiles': {'alpha': {'stars': FAVORITES}}})
    state = deepcopy(prefs._data)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        prefs.set('profiles', replacement)
    assert prefs._data == state
    assert path.read_bytes() == before


@pytest.mark.parametrize('operation', ['replace', 'getter-alias', 'setter-input-alias'])
def test_newly_stored_opaque_profile_stars_become_protected_immediately(tmp_path, operation):
    prefs = Prefs(str(tmp_path / 'synthetic-prefs.json'))
    incoming = {'alpha': {'stars': deepcopy(FAVORITES)}}
    prefs.set('profiles', incoming)
    path = Path(prefs._path)
    before = path.read_bytes()
    if operation == 'replace':
        with pytest.raises(ValueError):
            prefs.set('profiles', {})
        assert path.read_bytes() == before
    else:
        alias = prefs.get('profiles') if operation == 'getter-alias' else incoming
        alias['alpha']['stars'].clear()
        prefs.set('dnd', True)
    assert saved(path)['profiles']['alpha']['stars'] == FAVORITES


def test_protected_reader_aliases_cannot_modify_persisted_raw_values(tmp_path):
    prefs, path = seed(tmp_path, {'stars': FAVORITES, 'profiles': {'alpha': {'stars': FAVORITES}}})
    prefs.get('stars').append('group:changed')
    prefs.get('profiles')['alpha']['stars']['public']['7']['text'] = 'changed'
    incoming = prefs.get('profiles')
    prefs.set('profiles', incoming)
    incoming['alpha']['stars']['public']['7']['text'] = 'changed after set'
    prefs.set('dnd', True)
    assert saved(path)['stars'] == FAVORITES
    assert saved(path)['profiles']['alpha']['stars'] == FAVORITES


def test_unrelated_legal_profile_can_switch_while_preserving_opaque_other_profile(tmp_path):
    prefs, path = seed(tmp_path, {'active_profile': 'beta', 'stars': ['group:1'],
                                'profiles': {'alpha': {'stars': FAVORITES}, 'beta': {},
                                             'gamma': {'stars': ['public']}}})
    prefs.switch_profile('gamma')
    assert prefs.starred() == ['public']
    assert saved(path)['profiles']['alpha']['stars'] == FAVORITES
    assert saved(path)['profiles']['beta']['stars'] == ['group:1']


def test_legal_list_loader_toggle_and_profile_roundtrip_remain_compatible(tmp_path):
    prefs, path = seed(tmp_path, {'stars': [1, False, None]})
    assert prefs.starred() == ['1', 'False', 'None']
    assert prefs.toggle_star('public') is True
    assert prefs.toggle_star('public') is False
    prefs.remember_account('alpha')
    prefs.switch_profile('beta')
    assert prefs.starred() == []
    prefs.toggle_star('group:2')
    prefs.switch_profile('alpha')
    assert prefs.starred() == ['1', 'False', 'None']
    assert saved(path)['profiles']['beta']['stars'] == ['group:2']


@pytest.mark.parametrize('initial,replacement', [(['public'], FAVORITES), (FAVORITES, ['public'])])
def test_nonempty_known_format_cannot_be_overwritten_by_other_format(tmp_path, initial, replacement):
    prefs = Prefs(str(tmp_path / 'synthetic-prefs.json'))
    prefs.set('stars', deepcopy(initial))
    before = Path(prefs._path).read_bytes()
    with pytest.raises(ValueError):
        prefs.set('stars', deepcopy(replacement))
    assert prefs.get('stars') == initial
    assert Path(prefs._path).read_bytes() == before


def test_runtime_message_dict_same_format_edit_remains_compatible(tmp_path):
    prefs = Prefs(str(tmp_path / 'synthetic-prefs.json'))
    prefs.set('stars', deepcopy(FAVORITES))
    changed = deepcopy(FAVORITES)
    changed['public']['8'] = {'text': 'new synthetic favorite'}
    prefs.set('stars', changed)
    assert saved(Path(prefs._path))['stars'] == changed
    before = Path(prefs._path).read_bytes()
    with pytest.raises(ValueError):
        prefs.toggle_star('public')
    assert prefs.get('stars') == changed
    assert Path(prefs._path).read_bytes() == before


def function_from_source(filename, name, globals_, owner=None):
    """Execute the actual handler function only, avoiding client import/real Tk/startup IO."""
    tree = ast.parse((Path(__file__).resolve().parents[1] / filename).read_text('utf-8-sig'))
    nodes = tree.body
    if owner:
        nodes = next(n.body for n in nodes if isinstance(n, ast.ClassDef) and n.name == owner)
    node = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == name)
    code = compile(ast.Module(body=[node], type_ignores=[]), filename, 'exec')
    exec(code, globals_)
    return globals_[name]


@pytest.mark.parametrize('method', ['_toggle_star', '_toggle_star_conv'])
def test_actual_client_handler_refusal_preserves_local_state_and_never_reports_success(tmp_path, method):
    prefs, path = seed(tmp_path, {'stars': FAVORITES})
    messages, touches = [], []
    app = SimpleNamespace(_prefs=prefs, _stars={}, view=('public', None),
                          _pin_key=lambda *args: 'public', _append_sys=messages.append,
                          _touch_conv_state=touches.append,
                          msg_list=SimpleNamespace(get_row=lambda idx: {'seq': 8, 'nick': 'synthetic'},
                                                   body_text=lambda idx: 'synthetic text'))
    before = path.read_bytes()
    fn = function_from_source('client.py', method, {'StarsPreservationError': ValueError,
                                                   'trim_stars': trim_stars}, 'ChatWindow')
    fn(app, 0 if method == '_toggle_star' else 'public')
    assert app._stars == {} and touches == []
    assert path.read_bytes() == before
    assert len(messages) == 1 and '已保留' in messages[0]
    assert '已收藏' not in messages[0] and '已取消收藏' not in messages[0]


def test_actual_message_handler_can_add_and_remove_runtime_dict_favorites(tmp_path):
    prefs = Prefs(str(tmp_path / 'synthetic-prefs.json'))
    prefs.set('stars', deepcopy(FAVORITES))
    messages = []
    app = SimpleNamespace(_prefs=prefs, _stars=deepcopy(FAVORITES), view=('public', None),
                          _pin_key=lambda *args: 'public', _append_sys=messages.append,
                          msg_list=SimpleNamespace(get_row=lambda idx: {'seq': 8, 'nick': 'synthetic'},
                                                   body_text=lambda idx: 'synthetic text'))
    fn = function_from_source('client.py', '_toggle_star', {'StarsPreservationError': ValueError,
                                                          'trim_stars': trim_stars, 'deepcopy': deepcopy},
                              'ChatWindow')
    fn(app, 0)
    assert 8 in app._stars['public'] and messages == ['已收藏']
    assert '8' in saved(Path(prefs._path))['stars']['public']
    fn(app, 0)
    assert 8 not in app._stars['public'] and messages == ['已收藏', '已取消收藏']
    assert saved(Path(prefs._path))['stars'] == FAVORITES


def test_actual_message_handler_does_not_publish_local_mutation_after_late_refusal(tmp_path, monkeypatch):
    prefs = Prefs(str(tmp_path / 'synthetic-prefs.json'))
    prefs.set('stars', deepcopy(FAVORITES))
    before = Path(prefs._path).read_bytes()
    messages = []
    app = SimpleNamespace(_prefs=prefs, _stars=deepcopy(FAVORITES), view=('public', None),
                          _pin_key=lambda *args: 'public', _append_sys=messages.append,
                          msg_list=SimpleNamespace(get_row=lambda idx: {'seq': 8, 'nick': 'synthetic'},
                                                   body_text=lambda idx: 'synthetic text'))
    def refuse(*args):
        raise ValueError('原值已保留；本次操作未保存。')
    monkeypatch.setattr(prefs, 'set', refuse)
    fn = function_from_source('client.py', '_toggle_star', {'StarsPreservationError': ValueError,
                                                          'trim_stars': trim_stars, 'deepcopy': deepcopy},
                              'ChatWindow')
    fn(app, 0)
    assert app._stars == FAVORITES and Path(prefs._path).read_bytes() == before
    assert messages == ['原值已保留；本次操作未保存。']


@pytest.mark.parametrize('trusted', [False, True])
def test_actual_launcher_refuses_ambiguous_profile_before_opening_chat(tmp_path, trusted):
    prefs, path = seed(tmp_path, {'stars': FAVORITES, 'default_account': 'alpha',
                                'trusted_nicks': ['alpha'] if trusted else []})
    calls, errors, choices = [], [], []
    form = {'nick':'alpha', 'host':'127.0.0.1', 'port':9527,
            'name':'synthetic', 'remember':False, 'pwd':''}
    forms = iter([None] if trusted else [form, None])
    def choose(**kwargs):
        choices.append(kwargs)
        return next(forms)
    globals_ = {'Prefs': Prefs, 'StarsPreservationError': ValueError,
                'CFG': SimpleNamespace(tcp_port=9527), 'bootlog': lambda text: None,
                'messagebox': SimpleNamespace(showerror=lambda *args, **kwargs: errors.append(args)),
                'run_chat': lambda *args: calls.append(args) or 'quit',
                'show_login': choose}
    function_from_source('launcher.py', '_last_server', globals_)
    try:
        function_from_source('launcher.py', '_prepare_profile', globals_)
    except StopIteration:
        pass  # the old launcher did not have a protected profile preparation path
    launch = function_from_source('launcher.py', 'launch', globals_)
    assert launch('127.0.0.1', 9527, prefs) == 0  # explicit user cancellation
    assert len(choices) == (1 if trusted else 2)
    assert calls == [] and len(errors) == 1
    assert saved(path)['stars'] == FAVORITES
    assert not saved(path).get('profiles')  # no owner assignment from the ambiguous value


def test_actual_launcher_refusal_returns_to_choose_a_safe_profile(tmp_path):
    prefs, path = seed(tmp_path, {'active_profile': 'beta', 'stars': ['group:beta'],
                                'profiles': {'alpha': {'stars': FAVORITES},
                                             'beta': {'stars': ['group:beta']},
                                             'gamma': {'stars': ['public']}}})
    calls, errors, choices = [], [], []
    forms = iter([{'nick':nick, 'host':'127.0.0.1', 'port':9527,
                   'name':'synthetic', 'remember':False, 'pwd':''}
                  for nick in ['alpha', 'gamma']])
    def choose(**kwargs):
        choices.append(kwargs)
        return next(forms)
    globals_ = {'Prefs': Prefs, 'StarsPreservationError': ValueError,
                'CFG': SimpleNamespace(tcp_port=9527), 'bootlog': lambda text: None,
                'messagebox': SimpleNamespace(showerror=lambda *args, **kwargs: errors.append(args)),
                'run_chat': lambda *args: calls.append(args) or 'quit', 'show_login': choose}
    function_from_source('launcher.py', '_last_server', globals_)
    function_from_source('launcher.py', '_prepare_profile', globals_)
    launch = function_from_source('launcher.py', 'launch', globals_)
    assert launch('127.0.0.1', 9527, prefs) == 0
    assert len(choices) == 2 and len(errors) == 1
    assert len(calls) == 1 and calls[0][3] == 'gamma'
    selected = calls[0][2]  # launcher intentionally reopens Prefs on each loop
    assert selected.active_account() == 'gamma' and selected.starred() == ['public']
    assert saved(path)['active_profile'] == 'gamma' and saved(path)['stars'] == ['public']
    assert saved(path)['profiles']['alpha']['stars'] == FAVORITES
    assert saved(path)['profiles']['beta']['stars'] == ['group:beta']
