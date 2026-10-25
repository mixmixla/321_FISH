"""Deterministic first-WELCOME directory races using only disposable data."""
import hashlib
from pathlib import Path
import stat
import threading
from types import SimpleNamespace

import pytest

import local_identity
from client_core import ClientCore


SCOPE = 'a' * 32


def welcome(core, uid):
    core._dispatch({'t': 'welcome', 'uid': uid,
                    'auth': {'store_mode': 'durable', 'store_scope_id': SCOPE}})


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('level', ['root', 'v2', 'scope'])
def test_two_uids_accept_welcome_when_other_core_creates_shared_parent(tmp_path, monkeypatch, level):
    root = tmp_path / 'history'
    contested = {'root': root, 'v2': root / 'v2',
                 'scope': root / 'v2' / SCOPE}[level]
    contested.parent.mkdir(parents=True, exist_ok=True)
    first = ClientCore(nick='synthetic-first', history_dir=str(root))
    second = ClientCore(nick='synthetic-second', history_dir=str(root))
    arrived = threading.Event()
    release = threading.Event()
    errors = []
    real_mkdir = Path.mkdir

    def gated_mkdir(path, *args, **kwargs):
        if path == contested and threading.current_thread() is worker:
            # Product already decided that this precise path was missing.
            arrived.set()
            if not release.wait(5):
                raise AssertionError('directory race gate was not released')
        return real_mkdir(path, *args, **kwargs)

    def run_first():
        try:
            welcome(first, 11)
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=run_first, name='synthetic-first-welcome')
    monkeypatch.setattr(Path, 'mkdir', gated_mkdir)
    try:
        worker.start()
        assert arrived.wait(5), 'first WELCOME did not reach the exact mkdir gate'
        welcome(second, 12)
        assert second.local_identity == (SCOPE, 12)
        second._store_chat({'t': 'chat', 'channel': 'private', 'uid': 12,
                            'to': 11, 'seq': 1, 'text': 'second-only'})
        second._history._flush()
        second_dir = Path(second._history._dir)
        history_path = Path(second._history._path('private:11:12'))
        key_path = second_dir / 'e2ee_identity.json'
        before = (digest(history_path), digest(key_path))

        release.set()
        worker.join(5)
        assert not worker.is_alive(), 'first WELCOME did not finish'
        assert errors == []
        outcome = {
            'identity': first.local_identity,
            'manual_login_required': first._manual_login_required,
            'errors': [event for event in list(first.events.queue)
                       if event.get('t') == 'error'],
        }
        assert outcome == {'identity': (SCOPE, 11),
                           'manual_login_required': False, 'errors': []}
        assert not second._manual_login_required
        first_dir = Path(first._history._dir)
        assert first_dir == root / 'v2' / SCOPE / 'uid-11'
        assert second_dir == root / 'v2' / SCOPE / 'uid-12'
        assert first.history_tail('private', 12) == []
        first._store_chat({'t': 'chat', 'channel': 'private', 'uid': 11,
                           'to': 12, 'seq': 2, 'text': 'first-only'})
        first._history._flush()
        assert [m['text'] for m in first.history_tail('private', 12)] == ['first-only']
        assert [m['text'] for m in second.history_tail('private', 11)] == ['second-only']
        assert (digest(history_path), digest(key_path)) == before
        assert (first_dir / 'e2ee_identity.json').is_file()
    finally:
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        first.stop()
        second.stop()


@pytest.mark.parametrize('phase', ['existing', 'collision', 'created'])
@pytest.mark.parametrize('kind', ['file', 'symlink', 'reparse'])
def test_every_directory_outcome_rejects_non_plain_paths(tmp_path, monkeypatch, phase, kind):
    root = tmp_path / 'history'
    target = root / 'v2' / SCOPE / 'uid-11'
    target.parent.mkdir(parents=True)
    marker = b'preserve-synthetic-original'
    real_mkdir = Path.mkdir
    real_lstat = local_identity.os.lstat
    installed = False

    def install_obstacle():
        nonlocal installed
        if kind == 'file':
            target.write_bytes(marker)
        else:
            real_mkdir(target)
            (target / 'marker').write_bytes(marker)
        installed = True

    def competing_mkdir(path, *args, **kwargs):
        if path == target:
            if phase == 'collision':
                install_obstacle()
                return real_mkdir(path, *args, **kwargs)
            if phase == 'created':
                # Model replacement/attribute change immediately after our
                # successful mkdir, before the required post-create lstat.
                real_mkdir(path, *args, **kwargs)
                path.rmdir()
                install_obstacle()
                return None
        return real_mkdir(path, *args, **kwargs)

    def synthetic_lstat(path, *args, **kwargs):
        info = real_lstat(path, *args, **kwargs)
        if Path(path) == target and installed and kind != 'file':
            return SimpleNamespace(
                st_mode=stat.S_IFLNK if kind == 'symlink' else info.st_mode,
                st_file_attributes=0x400 if kind == 'reparse' else 0)
        return info

    if phase == 'existing':
        install_obstacle()
    monkeypatch.setattr(Path, 'mkdir', competing_mkdir)
    monkeypatch.setattr(local_identity.os, 'lstat', synthetic_lstat)
    with pytest.raises(OSError):
        local_identity.scoped_directory(root, (SCOPE, 11))
    assert installed
    original = target if kind == 'file' else target / 'marker'
    assert original.read_bytes() == marker
    if kind != 'file':
        assert {path.name for path in target.iterdir()} == {'marker'}


def test_non_collision_mkdir_error_is_not_swallowed(tmp_path, monkeypatch):
    root = tmp_path / 'history'
    target = root / 'v2'
    root.mkdir()
    marker = root / 'keep'
    marker.write_bytes(b'keep')
    real_mkdir = Path.mkdir

    def denied(path, *args, **kwargs):
        if path == target:
            raise PermissionError('synthetic permission denial')
        return real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'mkdir', denied)
    with pytest.raises(PermissionError, match='synthetic permission denial'):
        local_identity.scoped_directory(root, (SCOPE, 11))
    assert marker.read_bytes() == b'keep'
    assert not target.exists()


def test_existing_plain_directories_remain_usable(tmp_path):
    root = tmp_path / 'history'
    target = root / 'v2' / SCOPE / 'uid-11'
    target.mkdir(parents=True)
    marker = target / 'keep'
    marker.write_bytes(b'keep')
    assert Path(local_identity.scoped_directory(root, (SCOPE, 11))) == target
    assert marker.read_bytes() == b'keep'
