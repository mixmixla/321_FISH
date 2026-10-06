"""Explicit offline CLI and actual interrupted bootstrap processes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

import server
from server_recovery import StoreCoordinator, StoreError, strict_json


def cli(root, action, *, entry='run.py'):
    command = [sys.executable, str(Path(server.__file__).with_name(entry))]
    if entry == 'run.py':
        command.append('server')
    command.extend([action, '--store-dir', str(root)])
    return subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=12)


def test_offline_cli_has_no_hub_audit_crashlog_or_listeners(tmp_path, monkeypatch, capsys):
    root = tmp_path / 'new'
    monkeypatch.setattr(server, 'Hub', lambda **_: pytest.fail('offline Hub construction'))
    monkeypatch.setattr(server, 'enable_crashlog', lambda: pytest.fail('offline crash log'))
    assert server.main(['initialize-new', '--store-dir', str(root)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['ok'] and report['inspection']['pair'] == 'valid'
    assert set(p.name for p in root.iterdir()) == {'.owner.lock', 'state.json', 'control.json'}
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    assert server.main(['inspect', '--store-dir', str(root)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['inspection']['exclusive']
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}


@pytest.mark.parametrize('entry', ['run.py', 'server.py'])
def test_actual_cli_initializes_once_and_inspects_without_replacing(tmp_path, entry):
    root = tmp_path / 'new'
    result = cli(root, 'initialize-new', entry=entry)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['inspection']['pair'] == 'valid'
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    result = cli(root, 'initialize-new', entry=entry)
    assert result.returncode == 2 and json.loads(result.stdout)['error'] == 'target_exists'
    result = cli(root, 'inspect', entry=entry)
    assert result.returncode == 0 and json.loads(result.stdout)['inspection']['exclusive']
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}


def test_offline_requires_explicit_target_and_unknown_flags_never_initialize(tmp_path):
    entry = str(Path(server.__file__).with_name('run.py'))
    for arguments in (['initialize-new'], ['initialize-new', '--force', '--store-dir', str(tmp_path / 'new')]):
        result = subprocess.run([sys.executable, entry, 'server', *arguments],
                                capture_output=True, timeout=12)
        assert result.returncode == 2
        assert not (tmp_path / 'new').exists()


def test_cli_inspect_is_read_only_even_without_lock_or_on_bad_state(tmp_path):
    root = tmp_path / 'absent'
    result = cli(root, 'inspect')
    report = json.loads(result.stdout)['inspection']
    assert result.returncode == 0 and report['exclusive'] is False
    assert report['pair'] == 'unverified_without_ownership' and not root.exists()
    root.mkdir()
    private_value = b'{"private-synthetic-marker": "never-print-this"'
    (root / 'state.json').write_bytes(private_value)
    result = cli(root, 'inspect')
    assert result.returncode == 0 and 'never-print-this' not in result.stdout
    assert not (root / '.owner.lock').exists()
    assert (root / 'state.json').read_bytes() == private_value


def test_cli_adoption_preserves_original_and_open_of_bad_store_is_nonzero(tmp_path):
    root = tmp_path / 'legacy'
    root.mkdir()
    source = b'{ "uid_seq": 1 }\n'
    (root / 'state.json').write_bytes(source)
    result = cli(root, 'adopt-legacy')
    assert result.returncode == 0, result.stderr
    backup = root / ('state.legacy.' + hashlib.sha256(source).hexdigest() + '.json')
    assert backup.read_bytes() == source
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    assert cli(root, 'resume-bootstrap').returncode == 0
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}
    broken = tmp_path / 'broken'
    StoreCoordinator.initialize_new(broken)
    (broken / 'state.json').write_bytes(b'broken')
    result = cli(broken, 'open')
    assert result.returncode == 2
    assert (broken / 'state.json').read_bytes() == b'broken'


@pytest.mark.parametrize('mode', ['new', 'legacy'])
@pytest.mark.parametrize('write', [1, 2, 3])
@pytest.mark.parametrize('side', ['before', 'after'])
def test_real_process_exit_around_each_bootstrap_write(tmp_path, mode, write, side):
    root = tmp_path / 'store'
    source = b'{ "uid_seq": 1 }\n'
    if mode == 'legacy':
        root.mkdir()
        (root / 'state.json').write_bytes(source)
    script = '''
import os, sys
from server_recovery import StoreCoordinator
root, mode, write, side = sys.argv[1:]
original = StoreCoordinator._publish
calls = 0
def interrupted(store, value, previous):
    global calls
    calls += 1
    if calls == int(write) and side == 'before': os._exit(45)
    result = original(store, value, previous)
    if calls == int(write) and side == 'after': os._exit(45)
    return result
StoreCoordinator._publish = staticmethod(interrupted)
(StoreCoordinator.initialize_new if mode == 'new' else StoreCoordinator.adopt_legacy)(root)
'''
    result = subprocess.run([sys.executable, '-c', script, str(root), mode, str(write), side],
                            capture_output=True, timeout=12)
    assert result.returncode == 45, result.stderr
    if mode == 'legacy':
        backup = root / ('state.legacy.' + hashlib.sha256(source).hexdigest() + '.json')
        assert backup.read_bytes() == source
    if write == 1 and side == 'before':
        # No durable initialization intent exists; never infer an empty Store.
        with pytest.raises(StoreError):
            StoreCoordinator.resume_bootstrap(root)
        with pytest.raises(StoreError):
            StoreCoordinator(root).open()
        assert not (root / 'control.json').exists()
        if mode == 'legacy':
            assert (root / 'state.json').read_bytes() == source
            StoreCoordinator.adopt_legacy(root)
        else:
            assert not (root / 'state.json').exists()
            with pytest.raises(StoreError, match='target_exists'):
                StoreCoordinator.initialize_new(root)
            return
    else:
        StoreCoordinator.resume_bootstrap(root)
    owner = StoreCoordinator(root)
    try:
        pair = owner.open()
        assert pair.control['phase'] == 'ready'
        assert pair.state['_store']['store_id'] == pair.control['store_id']
        assert pair.state['uid_seq'] == 1
        assert not pair.state['known'] and not pair.state['retired']
    finally:
        owner.close()
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    StoreCoordinator.resume_bootstrap(root)
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}
