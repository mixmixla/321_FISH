"""Controlled directory faults; no ACL changes. Harness seams are not EXE acceptance."""
from contextlib import contextmanager
import errno
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import local_trial


def deny_scandir(monkeypatch, blocked, *, midway=False, armed=lambda: True):
    original = local_trial.os.scandir
    failure = PermissionError(errno.EACCES, 'synthetic enumeration denied', str(blocked))

    @contextmanager
    def interrupted(path):
        with original(path) as entries:
            def rows():
                yield next(entries)
                raise failure
            yield rows()

    def scan(path):
        if isinstance(path, (str, Path)) and Path(path) == blocked and armed():
            if midway:
                return interrupted(path)
            raise failure
        return original(path)
    monkeypatch.setattr(local_trial.os, 'scandir', scan)
    return failure


@pytest.mark.parametrize('where', ['root', 'nested', 'iteration'])
def test_enumeration_denial_never_returns_a_partial_inventory(tmp_path, monkeypatch, where):
    root = tmp_path/'owned'
    (root/'nested').mkdir(parents=True)
    (root/'visible.txt').write_bytes(b'visible')
    (root/'nested'/'hidden.txt').write_bytes(b'not deleted')
    blocked = root/'nested' if where == 'nested' else root
    failure = deny_scandir(monkeypatch, blocked, midway=where == 'iteration')
    with pytest.raises(PermissionError) as caught:
        local_trial._owned_inventory(root)
    assert caught.value is failure
    assert caught.value.errno == errno.EACCES and caught.value.filename == str(blocked)
    assert (root/'nested'/'hidden.txt').read_bytes() == b'not deleted'


def test_incomplete_tree_cannot_receive_a_fingerprint(tmp_path, monkeypatch):
    root = tmp_path/'owned'
    (root/'nested').mkdir(parents=True)
    (root/'nested'/'payload').write_bytes(b'owned')
    failure = deny_scandir(monkeypatch, root/'nested')
    with pytest.raises(PermissionError) as caught:
        local_trial._tree_fingerprint(root)
    assert caught.value is failure


def test_normal_unicode_spaces_empty_directories_and_global_order_are_compatible(tmp_path):
    root = tmp_path/'中文 空格'
    (root/'a'/'empty').mkdir(parents=True)
    (root/'空 目录').mkdir()
    payloads = {'a/z.txt': b'owned', 'a.txt': b'flat', '中文.bin': b'\x00\xff'}
    for name, data in payloads.items():
        (root/name).write_bytes(data)
    expected = [{'path': p, 'type': 'dir', 'size': 0, 'sha256': None}
                for p in ['.', 'a', 'a/empty', '空 目录']]
    expected += [{'path': p, 'type': 'file', 'size': len(data),
                  'sha256': hashlib.sha256(data).hexdigest()} for p, data in payloads.items()]
    expected.sort(key=lambda row: row['path'])
    assert local_trial._owned_inventory(root) == expected
    encoded = json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    assert local_trial._tree_fingerprint(root) == (hashlib.sha256(encoded).hexdigest(), len(expected))


def test_empty_root_is_a_complete_single_directory(tmp_path):
    assert local_trial._owned_inventory(tmp_path) == [
        {'path': '.', 'type': 'dir', 'size': 0, 'sha256': None}]


def test_reparse_rejection_happens_before_descending(tmp_path, monkeypatch):
    root = tmp_path/'owned'
    blocked = root/'nested'
    blocked.mkdir(parents=True)
    (blocked/'payload').write_bytes(b'must not descend')
    original_scan = local_trial.os.scandir
    visited = []
    class ReparseEntry:
        def __init__(self, entry):
            self.entry = entry
        def __getattr__(self, name):
            return getattr(self.entry, name)
        def stat(self, *, follow_symlinks=True):
            info = self.entry.stat(follow_symlinks=follow_symlinks)
            return SimpleNamespace(st_mode=info.st_mode, st_size=info.st_size,
                                   st_file_attributes=info.st_file_attributes | 0x400)
    @contextmanager
    def wrapped(path):
        with original_scan(path) as entries:
            yield (ReparseEntry(entry) if Path(entry.path) == blocked else entry
                   for entry in entries)
    def scan(path):
        visited.append(Path(path))
        assert Path(path) != blocked, 'reparse entry was traversed'
        return wrapped(path)
    monkeypatch.setattr(local_trial.os, 'scandir', scan)
    with pytest.raises(ValueError, match='symlink/junction'):
        local_trial._owned_inventory(root)
    assert blocked not in visited


def test_directory_classification_error_is_propagated_without_omitting_subtree(tmp_path, monkeypatch):
    root = tmp_path/'owned'
    blocked = root/'nested'
    blocked.mkdir(parents=True)
    (blocked/'payload').write_bytes(b'not deleted')
    failure = PermissionError(errno.EACCES, 'synthetic classification denied', str(blocked))
    original = local_trial.os.scandir
    calls = []
    class UnclassifiableEntry:
        def __init__(self, entry):
            self.entry = entry
        def __getattr__(self, name):
            return getattr(self.entry, name)
        def is_dir(self, **_kwargs):
            calls.append('is_dir')
            raise failure
        def stat(self, **_kwargs):
            calls.append('stat')
            raise failure
    @contextmanager
    def scan(path):
        with original(path) as entries:
            yield (UnclassifiableEntry(entry) if Path(entry.path) == blocked else entry
                   for entry in entries)
    monkeypatch.setattr(local_trial.os, 'scandir', scan)
    with pytest.raises(PermissionError) as caught:
        local_trial._owned_inventory(root)
    assert caught.value is failure and calls
    assert failure.filename == str(blocked)


def test_file_read_failure_is_not_a_complete_inventory(tmp_path, monkeypatch):
    payload = tmp_path/'payload'
    payload.write_bytes(b'owned')
    failure = PermissionError(errno.EACCES, 'synthetic read denied', str(payload))
    def denied(_path):
        raise failure
    monkeypatch.setattr(local_trial, '_sha256', denied)
    with pytest.raises(PermissionError) as caught:
        local_trial._owned_inventory(tmp_path)
    assert caught.value is failure


@pytest.mark.parametrize('phase', ['before', 'after'])
def test_formal_run_preserves_inventory_failure_and_cleans_owned_jobs(tmp_path, monkeypatch, phase):
    # Existing seams around actual owned Python Jobs, not actual server/client EXEs.
    from test_local_trial_wire_smoke import harness_scene
    source, jobs = harness_scene(tmp_path, monkeypatch)
    armed = [phase == 'before']
    original_scan = local_trial.os.scandir
    denied_paths = []
    def scan(path):
        if isinstance(path, (str, Path)) and Path(path).name == 'profile-server' and armed[0]:
            denied_paths.append(str(path))
            raise PermissionError(errno.EACCES, 'synthetic profile enumeration denied', str(path))
        return original_scan(path)
    monkeypatch.setattr(local_trial.os, 'scandir', scan)
    def wire(_port):
        armed[0] = True
        return {'ok': True}
    monkeypatch.setattr(local_trial, '_wire_probe', wire)
    try:
        code, result = local_trial.run_candidate(source, tmp_path/'runs')
        assert code == result['exit_code'] == 5
        error = result['profile_inventory_error']
        assert error['type'] == 'PermissionError' and error['errno'] == errno.EACCES
        assert error['filename'] in denied_paths and error['phase'] == phase
        assert 'synthetic profile enumeration denied' in error['message']
        assert result['profile_paths_scoped'] is False
        assert 'inventory_after' not in result['profiles']['server']
        stored = json.loads(next((tmp_path/'runs').glob('run-*/summary.json')).read_text(encoding='utf-8'))
        assert stored == result
        if phase == 'before':
            assert not jobs and not result['processes']
        else:
            assert result['probes']['wire']['ok'] is True and len(jobs) == 4
            assert result['cleanup_ok'] is True
            assert all(row['ok'] and row['close_ok'] and row['active_after'] == 0
                       for row in result['cleanup'].values())
            assert all(proc._closed for proc in jobs)
    finally:
        for proc in jobs:
            if not proc._closed:
                local_trial._cleanup_trial_process(proc)
