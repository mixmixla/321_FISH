"""Real Windows metadata sharing refusal; no ACL or security-setting changes."""
import ctypes
from ctypes import wintypes
import json
import os
import threading
import time
from types import SimpleNamespace

import pytest

import test_gate


def hold_metadata(path):
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = (wintypes.HANDLE,)
    api.CloseHandle.restype = wintypes.BOOL
    handle = api.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    return api, handle


def test_metadata_real_sharing_refusal_recovers_only_after_reader_releases(tmp_path, monkeypatch):
    path = tmp_path / 'progress.json'
    old = b'{"generation": 1}\n'
    path.write_bytes(old)
    api, handle = hold_metadata(path)
    denied, errors, attempts = threading.Event(), [], []
    original = os.replace
    def observed(source, target):
        try:
            return original(source, target)
        except OSError as exc:
            attempts.append(getattr(exc, 'winerror', None))
            denied.set()
            raise
    monkeypatch.setattr(test_gate.os, 'replace', observed)
    def write():
        try:
            test_gate._atomic_json(path, {'generation': 2, 'text': '完整的新元数据'})
        except BaseException as exc:
            errors.append(exc)
    writer = threading.Thread(target=write)
    try:
        writer.start()
        assert denied.wait(2)
        assert path.read_bytes() == old
        assert attempts and attempts[0] in (5, 32, 33)
        api.CloseHandle(handle)
        handle = None
        writer.join(2)
        assert not writer.is_alive() and not errors, errors
        assert json.loads(path.read_bytes()) == {'generation': 2, 'text': '完整的新元数据'}
        assert not list(tmp_path.glob('.*.tmp'))
    finally:
        if handle is not None:
            api.CloseHandle(handle)
        writer.join(2)


def test_metadata_permanent_sharing_refusal_is_bounded_and_keeps_old_target(tmp_path):
    path = tmp_path / 'summary.json'
    old = b'{"generation": 1}\n'
    path.write_bytes(old)
    api, handle = hold_metadata(path)
    started = time.monotonic()
    try:
        with pytest.raises(OSError) as caught:
            test_gate._atomic_json(path, {'generation': 2})
        assert caught.value.winerror in (5, 32, 33)
        assert time.monotonic() - started < 2.0
        assert path.read_bytes() == old
        assert not list(tmp_path.glob('.*.tmp'))
    finally:
        api.CloseHandle(handle)


def test_metadata_other_error_is_not_retried_or_hidden_by_cleanup(tmp_path, monkeypatch):
    path = tmp_path / 'manifest.json'
    old = b'{"generation": 1}\n'
    path.write_bytes(old)
    error = OSError('synthetic non-sharing IO error')
    error.winerror = 112
    calls = []
    def fail(*_):
        calls.append(1)
        raise error
    monkeypatch.setattr(test_gate.os, 'replace', fail)
    monkeypatch.setattr(test_gate.time, 'sleep', lambda *_: pytest.fail('non-sharing error must not wait'))
    with pytest.raises(OSError) as caught:
        test_gate._atomic_json(path, {'generation': 2})
    assert caught.value is error and calls == [1]
    assert path.read_bytes() == old
    assert not list(tmp_path.glob('.*.tmp'))


def test_metadata_cleanup_failure_never_replaces_original_error(tmp_path, monkeypatch):
    path = tmp_path / 'progress.json'
    path.write_bytes(b'{"generation": 1}')
    error = OSError('synthetic publication error')
    error.winerror = 112
    def fail(*_):
        raise error
    def failed_cleanup(*_, **__):
        raise PermissionError('synthetic cleanup failure')
    monkeypatch.setattr(test_gate.os, 'replace', fail)
    monkeypatch.setattr(test_gate.Path, 'unlink', failed_cleanup)
    with pytest.raises(OSError) as caught:
        test_gate._atomic_json(path, {'generation': 2})
    assert caught.value is error
    assert json.loads(path.read_bytes()) == {'generation': 1}


def test_metadata_temp_collision_never_overwrites_or_removes_another_file(tmp_path, monkeypatch):
    path = tmp_path / 'progress.json'
    path.write_bytes(b'{"generation": 1}')
    monkeypatch.setattr(test_gate.uuid, 'uuid4', lambda: SimpleNamespace(hex='c' * 32))
    collision = tmp_path / f'.progress.json.{os.getpid()}.{"c" * 32}.tmp'
    collision.write_bytes(b'other owned marker')
    with pytest.raises(FileExistsError):
        test_gate._atomic_json(path, {'generation': 2})
    assert collision.read_bytes() == b'other owned marker'
    assert json.loads(path.read_bytes()) == {'generation': 1}
