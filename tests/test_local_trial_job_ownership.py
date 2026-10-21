"""Real Windows Job ownership through the standard local-trial launch seam.

No desktop inputs, screenshots, network, devices or real profiles are used.
Fault injection is limited to cleanup error reporting around real owned Jobs.
"""
from __future__ import annotations

import _winapi
import sys
import time
import uuid

import pytest

import local_trial
from friend_trial_process import OwnedJobProcess, launch_owned


def _start(tmp_path, role, code, *, standard=False):
    launcher = local_trial.launch_process if standard else launch_owned
    # These children only use stdlib. Pin the same base interpreter directly:
    # baseline handle cleanup must not leave a venv redirector's child behind.
    return launcher([sys._base_executable, '-B', '-X', 'utf8', '-c', code],
        cwd=str(tmp_path), env=local_trial._clean_env(profile=tmp_path/('profile-'+role)),
        log_path=tmp_path/(role+'.log'), desktop_name='MoyuJobTest-'+uuid.uuid4().hex)


def _release(proc):
    """Safe RED cleanup: a retained process handle, never an old numeric PID."""
    if proc is None or getattr(proc, '_closed', False):
        return
    if isinstance(proc, OwnedJobProcess):
        try:
            assert proc.terminate_tree()
        finally:
            proc.close()
    else:
        try:
            if proc.poll() is None:
                _winapi.TerminateProcess(proc._process_handle, 124)
                assert _winapi.WaitForSingleObject(proc._process_handle, 5000) == 0
        finally:
            proc.close()


def _retain_handle(proc):
    owner = _winapi.GetCurrentProcess()
    return _winapi.DuplicateHandle(owner, proc._process_handle, owner, 0, False,
                                   _winapi.DUPLICATE_SAME_ACCESS)


def _assert_sentinel_alive(proc):
    assert proc.poll() is None
    assert proc.active_count() > 0


@pytest.mark.parametrize('exit_code', [0, 7])
def test_standard_initializer_job_can_be_cleaned_after_natural_exit(tmp_path, exit_code):
    sentinel = _start(tmp_path, 'sentinel', 'import time; time.sleep(60)')
    proc = None
    try:
        proc = _start(tmp_path, 'initializer', f'raise SystemExit({exit_code})', standard=True)
        assert proc.wait(timeout=10) == exit_code
        assert isinstance(proc, OwnedJobProcess), 'standard trial launcher lacks owned Job'
        # A signaled process handle can precede Job accounting by a few ms.
        # Require natural Job completion before exercising completed-Job cleanup.
        deadline = time.monotonic()+2
        while proc.active_count() and time.monotonic()<deadline:
            time.sleep(.01)
        assert proc.active_count() == 0, 'initializer Job did not finish naturally'
        result = local_trial._cleanup_trial_process(proc)
        assert result['active_before'] == result['active_after'] == 0
        assert result['close_ok'] is True and result['ok'] is True
        _assert_sentinel_alive(sentinel)
    finally:
        _release(proc)
        _release(sentinel)


def test_standard_job_removes_its_descendants_and_preserves_other_job(tmp_path):
    # The old launcher must fail the ownership assertion before it can spawn
    # descendants, so baseline RED cleanup never needs a numeric PID tree kill.
    go, ready = tmp_path/'go', tmp_path/'descendant-ready'
    child = "import time; time.sleep(60)"
    code = (
        "import subprocess,sys,time; from pathlib import Path; "
        f"go=Path({str(go)!r}); deadline=time.monotonic()+15; "
        "\nwhile not go.exists() and time.monotonic()<deadline: time.sleep(.02)"
        "\nif not go.exists(): raise SystemExit(9)"
        f"\np=subprocess.Popen([sys.executable,'-B','-c',{child!r}]); "
        f"Path({str(ready)!r}).write_text(str(p.pid)); time.sleep(60)"
    )
    sentinel = _start(tmp_path, 'sentinel', 'import time; time.sleep(60)')
    proc = None
    retained = None
    try:
        proc = _start(tmp_path, 'tree', code, standard=True)
        assert isinstance(proc, OwnedJobProcess), 'standard trial launcher lacks owned Job'
        retained = _retain_handle(proc)
        go.write_text('owned-job-confirmed', encoding='utf-8')
        deadline = time.monotonic()+8
        while not ready.exists() and time.monotonic()<deadline:
            time.sleep(.02)
        assert ready.exists(), 'owned child did not launch its real descendant'
        assert proc.active_count() >= 2
        result = local_trial._cleanup_trial_process(proc)
        assert result['active_before'] >= 2 and result['active_after'] == 0
        assert result['ok'] is True and result['close_ok'] is True
        assert _winapi.WaitForSingleObject(retained, 5000) == 0
        _assert_sentinel_alive(sentinel)
    finally:
        _release(proc)
        _release(sentinel)
        if retained is not None:
            _winapi.CloseHandle(retained)


@pytest.mark.parametrize('fault', ['query', 'terminate', 'close'])
def test_cleanup_errors_are_reported_and_job_is_closed(tmp_path, monkeypatch, fault):
    cleanup = local_trial._cleanup_trial_process
    sentinel = _start(tmp_path, 'sentinel', 'import time; time.sleep(60)')
    proc = None
    retained = None
    close_calls = []
    def close():
        close_calls.append(True)
        original_close()
        if fault == 'close':
            raise OSError('synthetic close failure after releasing real Job')
    def fail():
        raise OSError('synthetic cleanup failure')
    try:
        proc = _start(tmp_path, 'fault-target', 'import time; time.sleep(60)')
        retained = _retain_handle(proc)
        original_close = proc.close
        with monkeypatch.context() as patch:
            patch.setattr(proc, 'close', close)
            if fault == 'query':
                patch.setattr(proc, 'active_count', fail)
            elif fault == 'terminate':
                patch.setattr(proc, 'terminate_tree', fail)
            result = cleanup(proc)
        assert result['ok'] is False
        assert close_calls == [True]
        assert result['close_ok'] is (fault != 'close')
        assert result.get('error_type') == 'OSError' or result.get('close_error_type') == 'OSError'
        assert _winapi.WaitForSingleObject(retained, 5000) == 0
        _assert_sentinel_alive(sentinel)
    finally:
        _release(proc)
        _release(sentinel)
        if retained is not None:
            _winapi.CloseHandle(retained)
