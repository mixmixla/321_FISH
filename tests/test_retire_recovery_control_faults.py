"""Control-file IO fault boundaries with actual authority-byte readback."""
import builtins
import ctypes
import os
from pathlib import Path

import pytest

from server_recovery import StoreCoordinator, StoreError, strict_json


RECORD = {'nick': '合成意图目标', 'retired_at': 1.0, 'operation_id': 'synthetic-control-op'}


@pytest.mark.parametrize('stage', ['open', 'write', 'short_then_zero', 'flush', 'fsync', 'close', 'replace', 'short_complete'])
def test_control_io_stages_use_real_predecessor_bytes_without_state_write(tmp_path, monkeypatch, stage):
    root = tmp_path / 'store'
    StoreCoordinator.initialize_new(root)
    owner = StoreCoordinator(root)
    pair = owner.open()
    owner.mark_ready(pair.state)
    before_control, before_state = pair.control_bytes, pair.state_bytes
    original_open, original_fsync, original_replace = builtins.open, os.fsync, os.replace
    descriptors, stages_seen = set(), []

    class FaultFile:
        def __init__(self, inner):
            self.inner, self.writes, self.closed_once = inner, 0, False
            descriptors.add(inner.fileno())

        def write(self, value):
            self.writes += 1
            stages_seen.append('write')
            if stage == 'write':
                raise OSError('synthetic control write')
            if stage == 'short_then_zero':
                return self.inner.write(value[:3]) if self.writes == 1 else 0
            if stage == 'short_complete':
                return self.inner.write(value[:max(1, len(value) // 2)])
            return self.inner.write(value)

        def flush(self):
            stages_seen.append('flush')
            if stage == 'flush':
                raise OSError('synthetic control flush')
            return self.inner.flush()

        def fileno(self):
            return self.inner.fileno()

        def close(self):
            self.inner.close()
            if stage == 'close' and not self.closed_once:
                self.closed_once = True
                stages_seen.append('close')
                raise OSError('synthetic control close')

    def controlled_open(name, mode='r', *args, **kwargs):
        is_control_temp = (Path(name).parent == root and Path(name).name.startswith('control.json.tmp-') and mode == 'xb')
        if is_control_temp:
            stages_seen.append('open')
            if stage == 'open':
                raise PermissionError('synthetic control open')
        stream = original_open(name, mode, *args, **kwargs)
        return FaultFile(stream) if is_control_temp else stream

    def controlled_fsync(fd):
        if fd in descriptors:
            stages_seen.append('fsync')
            if stage == 'fsync':
                raise OSError('synthetic control fsync')
        return original_fsync(fd)

    def controlled_replace(source, target):
        if Path(target) == root / 'control.json':
            stages_seen.append('replace')
            if stage == 'replace':
                raise PermissionError('synthetic control replace')
        return original_replace(source, target)

    monkeypatch.setattr(builtins, 'open', controlled_open)
    monkeypatch.setattr(os, 'fsync', controlled_fsync)
    monkeypatch.setattr(os, 'replace', controlled_replace)
    try:
        result = owner.accept_intent(17, RECORD)
        assert (root / 'state.json').read_bytes() == before_state
        assert owner.phase == 'READY'
        if stage == 'short_complete':
            assert result.effect == 'committed' and owner.intents == {'17': RECORD}
            assert stages_seen.count('write') > 1
            assert strict_json((root / 'control.json').read_bytes())['intents'] == {'17': RECORD}
        else:
            assert result.effect == 'not_committed' and result.retryable
            assert not owner.intents and (root / 'control.json').read_bytes() == before_control
            assert ('write' if stage == 'short_then_zero' else stage) in stages_seen
    finally:
        owner.close()


@pytest.mark.parametrize('fault', ['denied_readback', 'corrupt_readback'])
def test_control_replace_then_unverifiable_readback_stops_all_writers(tmp_path, monkeypatch, fault):
    root = tmp_path / 'store'
    StoreCoordinator.initialize_new(root)
    owner = StoreCoordinator(root)
    pair = owner.open()
    owner.mark_ready(pair.state)
    original_replace, locked = os.replace, []
    api = owner.owner._api

    def replace_then_fault(source, target):
        original_replace(source, target)
        if Path(target) != root / 'control.json':
            return
        if fault == 'denied_readback':
            handle = api.CreateFileW(str(target), 0x80000000, 0, None, 3, 0x80, None)
            assert handle != ctypes.c_void_p(-1).value
            locked.append(handle)
        else:
            (root / 'control.json').write_bytes(b'broken synthetic control')

    monkeypatch.setattr(os, 'replace', replace_then_fault)
    try:
        result = owner.accept_intent(17, RECORD)
        assert result.effect == 'uncertain' and not result.retryable
        assert owner.phase == 'FAILED'
        assert (root / 'state.json').read_bytes() == pair.state_bytes
        with pytest.raises(StoreError, match='store_not_writable'):
            owner.validate_snapshot(pair.state)
    finally:
        for handle in locked:
            api.CloseHandle(handle)
        owner.close()
    raw = (root / 'control.json').read_bytes()
    if fault == 'denied_readback':
        assert strict_json(raw)['intents'] == {'17': RECORD}
        reopened = StoreCoordinator(root)
        try:
            loaded = reopened.open()
            assert loaded.control['intents'] == {'17': RECORD}
            with pytest.raises(StoreError, match='recovery_required'):
                reopened.mark_ready(loaded.state)
        finally:
            reopened.close()
    else:
        with pytest.raises(StoreError):
            StoreCoordinator(root).open()
        assert (root / 'control.json').read_bytes() == raw
