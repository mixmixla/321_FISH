"""Strict load and explicit Store lifecycle, using disposable real files."""
import copy
import ctypes
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import signal
import sys

import pytest

import bots
import server_recovery as recovery
from server_recovery import StoreCoordinator, StoreError, StoreOwner
from server_store import SaveResult, ServerStore, encode_state


def legacy_state():
    """Representative persisted writer shapes, including easily lost values."""
    return {
        'uid_seq': 3, 'gid_seq': 2, 'gf_seq': 1, 'task_seq': 1, 'pid_seq': 1,
        'nick_to_uid': {'甲': 1, '乙': 2},
        'known': {'1': {'nick': '甲', 'last_online': 1.0, 'pwd': '', 'status': '',
                        'invisible': False, 'remarks': {'2': '同事'}},
                  '2': {'nick': '乙'},
                  str(bots.BOTS[0].uid): {'nick': bots.BOTS[0].nick,
                                         'last_online': 1.0, 'type': 'bot'}},
        'groups': {'1': {'gid': 1, 'name': '协作', 'owner': 1,
                         'members': {'1': '甲', '2': '乙'}}},
        'reads': {'public': {'1': 3}, 'private:1:2': {'2': 2}},
        'blocks': {'1': [2]},
        'drafts': {'1|public': {'text': '  草稿\n', 'ts': 1.0}},
        'scheds': {'1': {'s1': {'channel': 'private', 'to': 2, 'text': '提醒',
                               'fire_at': 9999999999.0, 'created': 1.0}}},
        'bus': {'seq': 3, 'channels': {
            'all': [{'t': 'chat', 'seq': 1, 'uid': 1, 'nick': '甲', 'channel': 'public',
                     'to': None, 'text': '你好', 'ts': 1.0,
                     'preview': {'title': '合成标题', 'url': 'https://example.invalid/'}}],
            'private:1:2': [{'t': 'chat', 'seq': 2, 'uid': 2, 'nick': '乙',
                             'channel': 'private', 'to': 1, 'text': '好', 'ts': 1.1}]}},
        'pins': {'public': {'seq': 1, 'nick': None, 'text': '你好', 'sticker': '', 'ts': 1.0}},
        'burn': {'2': {'channel': 'private', 'uid': 2, 'to': 1, 'ts': 1.1, 'pend': [1]}},
        'polls': {'3': {'channel': 'public', 'to': None, 'uid': 1, 'question': '午休？',
                        'options': ['下棋', '散步'], 'end': 9999999999.0,
                        'votes': {'2': 0}}},
        'group_files': {'1': [{'fid': '1', 'name': '合成.txt', 'size': 4,
                               'ts': 1.0, 'uid': 1, 'nick': '甲'}]},
        'tasks': {'1': [{'tid': 1, 'text': '合成事项'}]},
        'fish_board': {'五子棋': {'1': 5}},
        'moments': {'1': {'pid': 1, 'uid': 1, 'nick': '甲', 'text': '动态', 'ts': 1.0,
                          'images': ['synthetic.jpg'], 'likes': [2], 'comments': [
                              {'uid': 2, 'nick': '乙', 'text': '赞', 'ts': 1.1,
                               'rep': {'uid': None, 'nick': '旧引用'}}]}},
        'moment_covers': {'1': {'mode': 'img', 'preset': None, 'ext': 'png'},
                          '2': {'mode': 'preset', 'preset': 0, 'ext': None}},
        'custom_stickers': {'test_1': {'code': 'test_1', 'label': '合成', 'pack': '',
                                      'ext': 'png', 'order': 0}},
        'sticker_pack_meta': {'测试包': {'cover': 'png'}},
    }


def test_strict_normalization_preserves_legal_values_without_resource_io(tmp_path, monkeypatch):
    value = legacy_state()
    original = copy.deepcopy(value)
    monkeypatch.setattr(Path, 'exists', lambda *_: pytest.fail('schema must not read resources'))
    normalized = recovery.validate_state(value, legacy=True)
    assert value == original
    assert normalized['known']['1']['status'] == ''
    assert normalized['known']['1']['invisible'] is False
    assert normalized['known']['1']['pwd'] == ''
    assert normalized['known']['1']['remarks'] == {'2': '同事'}
    assert normalized['moment_covers']['1']['preset'] is None
    assert normalized['moments']['1']['comments'][0]['rep']['uid'] is None
    assert normalized['polls']['3']['votes'] == {'2': [0]}
    assert normalized['custom_stickers'] == original['custom_stickers']
    assert normalized['bus'] == original['bus']
    raw = encode_state(normalized).payload
    assert recovery.validate_state(recovery.strict_json(raw), legacy=True) == normalized


def test_actual_hub_produced_snapshot_passes_the_same_validator(tmp_path):
    from config import CFG
    from server import Hub, Session
    cfg = replace(CFG, admin_pwd='', web_files_dir=str(tmp_path / 'web'),
                  audit_dir=str(tmp_path / 'audit'))
    hub = Hub(cfg=cfg, audit_dir=str(tmp_path / 'audit'))
    try:
        first = Session(0, '合成甲', 'tcp', '127.0.0.1', lambda *_: None)
        second = Session(0, '合成乙', 'tcp', '127.0.0.1', lambda *_: None)
        assert hub._on_hello(first, {'nick': first.nick})
        assert hub._on_hello(second, {'nick': second.nick})
        hub.bus.publish({'t': 'chat', 'uid': first.uid, 'nick': first.nick,
                         'channel': 'public', 'text': '合成消息', 'ts': 1.0})
        hub.bus.publish({'t': 'chat', 'uid': second.uid, 'nick': second.nick,
                         'channel': 'private', 'to': first.uid, 'text': '合成私聊', 'ts': 2.0})
        raw = encode_state(hub._snapshot_state()).payload
        decoded = recovery.strict_json(raw)
        normalized = recovery.validate_state(decoded, legacy=True)
        assert normalized['bus'] == decoded['bus']
        assert normalized['known'] == decoded['known']
    finally:
        hub.audit.close()


@pytest.mark.parametrize('counter,expected', [(2, 1000), (1000, 1000), (1200, 1200), ('missing', 1000)])
def test_real_legacy_high_retirement_uid_raises_only_the_future_allocation_floor(counter, expected):
    value = {'nick_to_uid': {'旧用户': 1, '旧目标': 999}, 'known': {'1': {'nick': '旧用户'}},
             'retired': {'999': {'nick': '旧目标', 'retired_at': 1.0, 'operation_id': 'legacy-999'}}}
    if counter != 'missing':
        value['uid_seq'] = counter
    before = copy.deepcopy(value)
    normalized = recovery.validate_state(value, legacy=True)
    assert value == before
    assert normalized['uid_seq'] == expected
    assert normalized['known'] == before['known']
    assert normalized['retired'] == before['retired']
    assert normalized['nick_to_uid'] == before['nick_to_uid']
    assert recovery.validate_state(normalized, legacy=True) == normalized


@pytest.mark.parametrize('counter', [True, False, None, 0, -1, 2.0, '2'])
def test_legacy_counter_compatibility_does_not_coerce_wrong_types(counter):
    with pytest.raises(StoreError, match='invalid_schema'):
        recovery.validate_state({'uid_seq': counter}, legacy=True)


def test_fixed_bot_uids_do_not_raise_the_human_allocation_floor():
    bot = bots.BOTS[0]
    normalized = recovery.validate_state({'uid_seq': 2, 'nick_to_uid': {'旧用户': 1},
        'known': {'1': {'nick': '旧用户'}, str(bot.uid): {'nick': bot.nick, 'type': 'bot'}}}, legacy=True)
    assert normalized['uid_seq'] == 2


@pytest.mark.parametrize('raw', [b'{"a":1,"a":2}', b'{"x":{"a":1,"a":2}}',
    b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}', b'[]', b'null',
    b'{"x":"\\ud800"}', b'{"x":"\xff"}', b'{'])
def test_invalid_json_is_not_an_empty_database(raw):
    with pytest.raises(StoreError, match='invalid_json'):
        recovery.strict_json(raw)


@pytest.mark.parametrize('path,bad', [
    (('known', '1', 'status'), 'not-a-status'),
    (('known', '1', 'invisible'), 'false'),
    (('known', '1', 'remarks'), {'02': 'collision'}),
    (('known', '1', 'type'), 'bot'),
    (('groups', '1', 'owner'), 3),
    (('groups', '1', 'members'), {'1': True}),
    (('reads', 'public', '1'), True),
    (('blocks', '1'), [2, 2]),
    (('drafts', '1|public', 'text'), 123),
    (('scheds', '1', 's1', 'fire_at'), 'invalid'),
    (('polls', '3', 'votes'), {'2': [3]}),
    (('polls', '3', 'correct'), 0),
    (('fish_board', '五子棋', '1'), 1.5),
    (('moment_covers', '1', 'ext'), '../secret'),
    (('custom_stickers', 'test_1', 'code'), '../bad'),
    (('sticker_pack_meta', '测试包', 'cover'), 'exe'),
    (('bus', 'seq'), 0), (('uid_seq',), True),
    (('unknown_top_level',), {}), (('known',), None),
])
def test_schema_rejects_ambiguous_values_instead_of_filtering_records(path, bad):
    value = legacy_state()
    parent = value
    for part in path[:-1]:
        parent = parent[part]
    parent[path[-1]] = bad
    before = copy.deepcopy(value)
    with pytest.raises(StoreError, match='invalid_schema'):
        recovery.validate_state(value, legacy=True)
    assert value == before


def test_open_does_not_initialize_or_write_on_missing_legacy_or_corrupt_files(tmp_path):
    root = tmp_path / 'absent'
    with pytest.raises(StoreError, match='uninitialized'):
        StoreCoordinator(root).open()
    assert not root.exists()
    root.mkdir()
    with pytest.raises(StoreError, match='uninitialized'):
        StoreCoordinator(root).open()
    assert list(root.iterdir()) == []
    raw = encode_state(legacy_state()).payload
    (root / 'state.json').write_bytes(raw)
    with pytest.raises(StoreError, match='legacy_requires_adoption'):
        StoreCoordinator(root).open()
    assert {p.name for p in root.iterdir()} == {'state.json'}
    assert (root / 'state.json').read_bytes() == raw
    (root / 'state.json').write_bytes(b'{')
    with pytest.raises(StoreError, match='invalid_json'):
        StoreCoordinator(root).open()
    assert (root / 'state.json').read_bytes() == b'{'


def test_initialize_is_explicit_and_never_resets_an_existing_directory(tmp_path):
    root = tmp_path / 'new'
    StoreCoordinator.initialize_new(root)
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    with pytest.raises(StoreError, match='target_exists'):
        StoreCoordinator.initialize_new(root)
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}
    owner = StoreCoordinator(root)
    pair = owner.open()
    try:
        assert owner.phase == 'RECOVERING'
        assert pair.state['known'] == pair.control['intents'] == {}
        owner.mark_ready(pair.state)
        assert owner.phase == 'READY'
        assert StoreCoordinator.inspect(root)['exclusive'] is False
    finally:
        owner.close()
    assert StoreCoordinator.inspect(root)['pair'] == 'valid'


def test_adopt_keeps_exact_backup_and_only_adds_store_metadata(tmp_path):
    root = tmp_path / 'legacy'
    root.mkdir()
    value = legacy_state()
    raw = json.dumps(value, ensure_ascii=False, indent=3).encode()
    (root / 'state.json').write_bytes(raw)
    StoreCoordinator.adopt_legacy(root)
    backups = list(root.glob('state.legacy.*.json'))
    assert len(backups) == 1 and backups[0].read_bytes() == raw
    current = recovery.strict_json((root / 'state.json').read_bytes())
    meta = current.pop('_store')
    assert current == value
    assert meta['store_id'] == recovery.strict_json((root / 'control.json').read_bytes())['store_id']
    owner = StoreCoordinator(root)
    pair = owner.open()
    try:
        assert pair.state['known']['1']['status'] == ''
        assert pair.state['custom_stickers'] == value['custom_stickers']
    finally:
        owner.close()


@pytest.mark.parametrize('stage', ['short_writes', 'write', 'flush', 'fsync', 'close',
                                  'rename_before', 'rename_after'])
def test_legacy_backup_partial_failure_never_poisoned_the_final_backup_name(tmp_path, monkeypatch, stage):
    root = tmp_path / 'legacy'
    root.mkdir()
    (root / '.owner.lock').touch()
    raw = encode_state(legacy_state()).payload
    (root / 'state.json').write_bytes(raw)
    real_open, real_rename = Path.open, os.rename
    class StageFile:
        def __init__(self, inner):
            self.inner = inner
            self.writes = 0
        def write(self, data):
            self.writes += 1
            if stage == 'write' and self.writes > 1:
                raise OSError('synthetic short write failure')
            return self.inner.write(data[:max(1, len(data) // 2)])
        def flush(self):
            if stage == 'flush':
                raise OSError('synthetic flush failure')
            return self.inner.flush()
        def fileno(self):
            return self.inner.fileno()
        def close(self):
            self.inner.close()
            if stage == 'close':
                raise OSError('synthetic close failure')
    def patched_open(path, *args, **kwargs):
        stream = real_open(path, *args, **kwargs)
        return StageFile(stream) if path.name.startswith('.backup-stage-') else stream
    def patched_rename(src, dst):
        if stage == 'rename_before':
            raise OSError('synthetic before rename')
        result = real_rename(src, dst)
        if stage == 'rename_after':
            raise OSError('synthetic after rename')
        return result
    monkeypatch.setattr(Path, 'open', patched_open)
    monkeypatch.setattr(os, 'rename', patched_rename)
    if stage == 'fsync':
        monkeypatch.setattr(os, 'fsync', lambda _: (_ for _ in ()).throw(OSError('synthetic fsync failure')))
    if stage in ('short_writes', 'rename_after'):
        StoreCoordinator.adopt_legacy(root)
    else:
        with pytest.raises(StoreError, match='backup_write_failed'):
            StoreCoordinator.adopt_legacy(root)
        assert (root / 'state.json').read_bytes() == raw
        assert not list(root.glob('state.legacy.*.json'))
        assert not (root / 'control.json').exists()
    monkeypatch.undo()
    if not (root / 'control.json').exists():
        StoreCoordinator.adopt_legacy(root)
    backup = list(root.glob('state.legacy.*.json'))
    assert len(backup) == 1 and backup[0].read_bytes() == raw
    assert not list(root.glob('.backup-stage-*'))


def test_real_process_exit_mid_backup_preserves_source_and_allows_explicit_adoption(tmp_path):
    root = tmp_path / 'legacy-crash'
    root.mkdir()
    raw = encode_state(legacy_state()).payload
    (root / 'state.json').write_bytes(raw)
    script = r'''
import os, sys
from pathlib import Path
from server_recovery import StoreCoordinator
original_open = Path.open
class CrashDuringWrite:
    def __init__(self, inner): self.inner = inner
    def write(self, data):
        self.inner.write(data[:max(1, len(data)//2)])
        self.inner.flush()
        os.fsync(self.inner.fileno())
        os._exit(37)
def intercepted(path, *args, **kwargs):
    stream = original_open(path, *args, **kwargs)
    return CrashDuringWrite(stream) if path.name.startswith('.backup-stage-') else stream
Path.open = intercepted
StoreCoordinator.adopt_legacy(sys.argv[1])
'''
    result = subprocess.run([sys.executable, '-c', script, str(root)],
                            cwd=Path(recovery.__file__).parent,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 37, result.stderr
    assert (root / 'state.json').read_bytes() == raw
    assert not (root / 'control.json').exists()
    assert not list(root.glob('state.legacy.*.json'))
    orphan, = root.glob('.backup-stage-*')
    orphan_bytes = orphan.read_bytes()
    assert 0 < len(orphan_bytes) < len(raw)
    StoreCoordinator.adopt_legacy(root)
    backup, = root.glob('state.legacy.*.json')
    assert backup.read_bytes() == raw
    assert orphan.read_bytes() == orphan_bytes
    assert StoreCoordinator.inspect(root)['pair'] == 'valid'


@pytest.mark.parametrize('stage', ['control_bootstrap', 'state', 'control_ready'])
@pytest.mark.parametrize('mode', ['new', 'legacy'])
def test_bootstrap_failure_has_an_explicit_recoverable_stop(tmp_path, monkeypatch, stage, mode):
    root = tmp_path / 'store'
    if mode == 'legacy':
        root.mkdir()
        (root / 'state.json').write_bytes(encode_state(legacy_state()).payload)
    original = recovery.ServerStore.save_bytes
    def fail_selected(store, payload):
        data = recovery.strict_json(payload)
        selected = ('state' if store._path.endswith('state.json') else
                    'control_' + data['phase'])
        if selected == stage:
            return SaveResult('not_committed', 'write', 'injected_failure', True)
        return original(store, payload)
    monkeypatch.setattr(recovery.ServerStore, 'save_bytes', fail_selected)
    with pytest.raises(StoreError, match='bootstrap_write_failed'):
        (StoreCoordinator.initialize_new if mode == 'new' else StoreCoordinator.adopt_legacy)(root)
    monkeypatch.undo()
    with pytest.raises(StoreError):
        StoreCoordinator(root).open()
    if stage == 'control_bootstrap':
        # No durable bootstrap authority exists. No implicit recovery/new.
        with pytest.raises(StoreError):
            StoreCoordinator.resume_bootstrap(root)
    else:
        StoreCoordinator.resume_bootstrap(root)
        StoreCoordinator.resume_bootstrap(root)
        owner = StoreCoordinator(root)
        owner.open()
        owner.close()


def test_bootstrap_resume_rejects_conflicting_state_and_preserves_it(tmp_path, monkeypatch):
    root = tmp_path / 'store'
    original = recovery.ServerStore.save_bytes
    def stop_state(store, payload):
        if store._path.endswith('state.json'):
            return SaveResult('not_committed', 'open', 'injected', True)
        return original(store, payload)
    monkeypatch.setattr(recovery.ServerStore, 'save_bytes', stop_state)
    with pytest.raises(StoreError):
        StoreCoordinator.initialize_new(root)
    monkeypatch.undo()
    (root / 'state.json').write_bytes(b'{"unexpected":"private synthetic value"}')
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    with pytest.raises(StoreError) as exc:
        StoreCoordinator.resume_bootstrap(root)
    assert 'private synthetic value' not in str(exc.value)
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}


def test_intent_is_durable_before_any_snapshot_change_and_never_a_complete_receipt(tmp_path):
    root = tmp_path / 'store'
    StoreCoordinator.initialize_new(root)
    owner = StoreCoordinator(root)
    pair = owner.open()
    owner.mark_ready(pair.state)
    old_state = (root / 'state.json').read_bytes()
    record = {'nick': '将退役', 'retired_at': 1.0, 'operation_id': 'op-17'}
    try:
        result = owner.accept_intent(17, record)
        assert result.effect == 'committed'
        assert (root / 'state.json').read_bytes() == old_state
        assert owner.intents == {'17': record}
        with pytest.raises(StoreError, match='recovery_required'):
            owner.validate_snapshot(pair.state)
    finally:
        owner.close()
    reopened = StoreCoordinator(root)
    restored = reopened.open()
    try:
        assert reopened.phase == 'RECOVERING'
        assert restored.control['intents'] == {'17': record}
        assert restored.state['retired'] == {}
        with pytest.raises(StoreError, match='recovery_required'):
            reopened.mark_ready(restored.state)
        pretend = copy.deepcopy(restored.state)
        pretend['retired']['17'] = record
        pretend['nick_to_uid']['将退役'] = 17
        pretend['uid_seq'] = 18
        with pytest.raises(StoreError, match='recovery_required'):
            reopened.mark_ready(pretend, verify_cleanup=lambda *_: True)
        assert reopened.phase == 'RECOVERING'
    finally:
        reopened.close()


def test_loaded_pair_cannot_mutate_the_coordinators_accepted_identity_floor(tmp_path):
    root = tmp_path / 'store'
    StoreCoordinator.initialize_new(root)
    owner = StoreCoordinator(root)
    pair = owner.open()
    try:
        actual_id = owner.store_id
        pair.control['store_id'] = 'a' * 32
        pair.control['intents']['17'] = {'nick': '伪造', 'retired_at': 1, 'operation_id': 'fake'}
        assert owner.store_id == actual_id
        assert owner.intents == {}
        owner.mark_ready(pair.state)
        assert owner.phase == 'READY'
    finally:
        owner.close()


def test_real_windows_sharing_refusal_is_read_error_without_overwriting(tmp_path):
    root = tmp_path / 'store'
    StoreCoordinator.initialize_new(root)
    before = (root / 'state.json').read_bytes(), (root / 'control.json').read_bytes()
    lock = StoreOwner(root / '.owner.lock').acquire()
    api = lock._api
    lock.close()
    handle = api.CreateFileW(str(root / 'state.json'), 0x80000000, 0, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    try:
        broken = StoreCoordinator(root)
        with pytest.raises(StoreError, match='read_error'):
            broken.open()
        assert broken.phase == 'FAILED' and not broken.owner.held
    finally:
        api.CloseHandle(handle)
    assert before == ((root / 'state.json').read_bytes(), (root / 'control.json').read_bytes())


def test_unique_temp_collision_never_removes_someone_elses_file(tmp_path, monkeypatch):
    import server_store
    monkeypatch.setattr(server_store.secrets, 'token_hex', lambda _: 'collision')
    path = tmp_path / 'state.json'
    path.write_bytes(b'old')
    occupied = tmp_path / 'state.json.tmp-collision'
    occupied.write_bytes(b'other writer evidence')
    store = ServerStore(str(path), create_parent=False, unique_temp=True)
    result = store.save_bytes(b'candidate')
    assert result.effect == 'not_committed' and result.stage == 'open'
    assert path.read_bytes() == b'old'
    assert occupied.read_bytes() == b'other writer evidence'


def test_duplicate_message_sequences_cannot_replace_the_recovered_index():
    value = legacy_state()
    value['bus']['channels']['private:1:2'][0]['seq'] = 1
    with pytest.raises(StoreError, match='duplicate_seq'):
        recovery.validate_state(value, legacy=True)


@pytest.mark.parametrize('outcome', ['predecessor', 'accepted_then_error', 'conflict', 'missing'])
def test_intent_result_uses_actual_authority_and_unknown_stops_the_coordinator(tmp_path, monkeypatch, outcome):
    root = tmp_path / 'store'
    StoreCoordinator.initialize_new(root)
    owner = StoreCoordinator(root)
    pair = owner.open()
    owner.mark_ready(pair.state)
    old_state = (root / 'state.json').read_bytes()
    old_control = (root / 'control.json').read_bytes()
    real_save = owner.control_store.save_bytes
    def fault(payload):
        if outcome == 'predecessor':
            return SaveResult('not_committed', 'write', 'injected', True)
        if outcome == 'accepted_then_error':
            assert real_save(payload).effect == 'committed'
        elif outcome == 'conflict':
            (root / 'control.json').write_bytes(b'broken control')
        return SaveResult('uncertain', 'replace', 'injected', False)
    monkeypatch.setattr(owner.control_store, 'save_bytes', fault)
    if outcome == 'missing':
        (root / 'control.json').unlink()
    try:
        result = owner.accept_intent(17, {'nick': '目标', 'retired_at': 1.0, 'operation_id': 'op'})
        assert (root / 'state.json').read_bytes() == old_state
        if outcome == 'predecessor':
            assert result.effect == 'not_committed' and owner.phase == 'READY'
            assert owner.intents == {}
            assert (root / 'control.json').read_bytes() == old_control
        elif outcome == 'accepted_then_error':
            assert result.effect == 'committed' and owner.phase == 'READY'
            assert owner.intents['17']['operation_id'] == 'op'
        else:
            assert result.effect == 'uncertain' and owner.phase == 'FAILED'
            with pytest.raises(StoreError, match='store_not_writable'):
                owner.validate_snapshot(pair.state)
    finally:
        owner.close()


def test_real_second_process_ownership_and_crash_release(tmp_path):
    root = tmp_path / 'store'
    StoreCoordinator.initialize_new(root)
    script = ('import sys,os,json; from server_recovery import StoreOwner; '
              'owner=StoreOwner(sys.argv[1]).acquire(); '
              'print(json.dumps({"held":True,"pid":os.getpid()}), flush=True); sys.stdin.read()')
    process = subprocess.Popen([sys.executable, '-c', script, str(root / '.owner.lock')],
                               cwd=Path(recovery.__file__).parent,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    try:
        marker = json.loads(process.stdout.readline())
        assert marker['held'] is True and type(marker['pid']) is int
        (tmp_path / 'owner-process.json').write_text(json.dumps({
            'launcher_pid': process.pid, 'lock_owner_pid': marker['pid']}))
        before = (root / 'state.json').read_bytes(), (root / 'control.json').read_bytes()
        with pytest.raises(StoreError, match='store_in_use'):
            StoreCoordinator(root).open()
        # A Windows venv redirector can have a different PID from Python.
        # Terminate the exact synthetic process that proved ownership.
        os.kill(marker['pid'], signal.SIGTERM)
        process.wait(timeout=5)
        with StoreOwner(root / '.owner.lock'):
            assert before == ((root / 'state.json').read_bytes(), (root / 'control.json').read_bytes())
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
