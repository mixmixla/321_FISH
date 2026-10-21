"""Real Tk timer ownership, synthetic core; no OS input or screen capture."""
import gc
import time
import tkinter as tk
import types
import weakref
from types import SimpleNamespace

import pytest

from client import GameWindow, _DEFAULT_PAL


def _pending(root):
    return {str(job): str(root.tk.call('after', 'info', job)[0])
            for job in root.tk.splitlist(root.tk.call('after', 'info'))}


def _owned(root, window):
    commands = set(window._tclCommands or ())
    return {job: script for job, script in _pending(root).items()
            if root.tk.splitlist(script)[0] in commands}


def _until(root, predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        root.update()
        time.sleep(0.005)
    assert predicate(), 'real Tk event condition did not complete'


@pytest.fixture
def scene():
    # Tk failure is an environment failure here, never a successful skip.
    root = tk.Tk()
    root.withdraw()
    errors, python_errors, windows = [], [], []
    root.tk.createcommand('bgerror', errors.append)
    root.report_callback_exception = lambda *exc: python_errors.append(str(exc))

    def create():
        calls = []
        core = SimpleNamespace(
            uid=7, connected=True, game_meta={}, game_rooms=[],
            game_room=None, game_state=None, game_private=None,
            game_events=[], roster={}, game_list=lambda: calls.append('list'))
        app = SimpleNamespace(root=root, core=core, _dp=_DEFAULT_PAL,
                              _frameless=False, _skin={},
                              _camo_title=lambda: 'synthetic timer lifetime')
        window = GameWindow(app, pal=_DEFAULT_PAL)
        windows.append(weakref.ref(window))
        return window, calls

    try:
        yield root, create, errors, python_errors
    finally:
        if not getattr(root, "_timer_test_destroyed", False):
            for ref in windows:
                window = ref()
                if window is not None:
                    window.close()
            # RED cleanup only, after assertions: do not leak this test's
            # timers into tkguard's retained interpreter or the next test.
            for job in tuple(_pending(root)):
                root.tk.call('after', 'cancel', job)
            root.destroy()


@pytest.mark.parametrize('after_poll', [False, True])
def test_close_cancels_only_own_pending_jobs(scene, after_poll):
    root, create, errors, python_errors = scene
    window, _ = create()
    other, _ = create()
    root.update_idletasks()
    before = _owned(root, window.win)
    assert len(before) == 4, before
    if after_poll:
        _until(root, lambda: set(_owned(root, window.win)) != set(before))
    own = _owned(root, window.win)
    other_jobs = _owned(root, other.win)
    assert own and other_jobs
    sentinel = root.after(5000, lambda: None)
    window.close()
    window.close()
    remaining = _pending(root)
    stale = {job: script for job, script in own.items() if job in remaining}
    print('closed owned jobs remaining:', stale)
    assert not stale, stale
    assert set(other_jobs) <= set(remaining)
    assert sentinel in remaining
    assert not errors and not python_errors


def test_close_has_no_real_tcl_background_errors(scene):
    root, create, errors, python_errors = scene
    window, calls = create()
    root.update_idletasks()
    assert len(_owned(root, window.win)) == 4
    window.close()
    fired = []
    root.after(750, lambda: fired.append(True))
    _until(root, lambda: bool(fired))
    print('real bgerror after close:', errors)
    assert not errors, errors
    assert not python_errors, python_errors
    assert calls == ['list'], calls


def test_repeated_close_rebuild_releases_window_and_queue(scene):
    root, create, errors, python_errors = scene
    baseline = set(_pending(root))
    refs, callbacks = [], []
    for _ in range(6):
        window, _ = create()
        root.update_idletasks()
        refs.append(weakref.ref(window))
        # Inspect only this repair's callbacks, without retaining a callback
        # or its bound owner in the probe. Old code has none of these wrappers.
        for candidate in gc.get_objects():
            if (isinstance(candidate, types.FunctionType)
                    and candidate.__qualname__ ==
                    'GameWindow._schedule_after.<locals>.run'
                    and any(cell.cell_contents is window
                            for cell in candidate.__closure__ or ())):
                callbacks.append(weakref.ref(candidate))
        del candidate
        window.close()
        del window
        gc.collect()
        assert set(_pending(root)) == baseline
        assert all(ref() is None for ref in callbacks)
    assert len(callbacks) == 24
    # Existing root-owned bind_all(MouseWheel) retains GameWindow until root
    # destruction. Independently diagnosed, not fixed or counted as new leak.
    root.destroy()
    root._timer_test_destroyed = True
    gc.collect()
    assert all(ref() is None for ref in refs)
    assert not errors and not python_errors


def test_hide_show_keeps_polling_and_retry_and_drains_one_shots(scene):
    root, create, errors, python_errors = scene
    window, calls = create()
    root.update_idletasks()
    initial = set(_owned(root, window.win))
    window.hide()
    _until(root, lambda: len(calls) >= 2)  # actual 600 ms retry, hidden
    assert window.win.state() == 'withdrawn'
    assert set(_owned(root, window.win)) != initial  # actual poll fired
    window.show()
    assert len(calls) >= 3
    # All three real retry deadlines pass; only the recurring poll survives.
    _until(root, lambda: len(calls) >= 5, timeout=4)
    assert len(_owned(root, window.win)) == 1
    if hasattr(window, '_after_jobs'):
        assert set(window._after_jobs) == set(_owned(root, window.win))
    assert not errors and not python_errors


def test_close_during_real_poll_does_not_schedule_again(scene):
    root, create, errors, python_errors = scene
    window, _ = create()
    root.update_idletasks()
    closed = []
    real_sync = window._sync

    def sync_then_close():
        real_sync()
        window.close()
        closed.append(True)

    window._sync = sync_then_close
    original = set(_pending(root))
    _until(root, lambda: bool(closed))
    assert not _pending(root), _pending(root)
    assert original
    assert not errors and not python_errors
