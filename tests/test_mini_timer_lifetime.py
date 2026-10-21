"""Real Tk MiniBar destruction, synthetic core; no OS input/screenshots."""
import gc
import threading
import time
import tkinter as tk
import weakref
from types import SimpleNamespace

import pytest

from client import MiniBar, _DEFAULT_PAL


def _pending(root):
    return {str(job): str(root.tk.call('after', 'info', job)[0])
            for job in root.tk.splitlist(root.tk.call('after', 'info'))}


def _owned(root, win):
    commands = set(win._tclCommands or ())
    return {job: script for job, script in _pending(root).items()
            if root.tk.splitlist(script)[0] in commands}


def _until(root, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        root.update()
        time.sleep(0.005)
    assert predicate(), 'real Tk event condition did not complete'


def _create(root):
    core = SimpleNamespace(connected=True, files=SimpleNamespace(
        _lock=threading.Lock(), xfers={}))
    app = SimpleNamespace(root=root, core=core,
                          _prefs={'mini_transparent': False}, _unread={})
    return MiniBar(app, pal=_DEFAULT_PAL)


@pytest.fixture
def scene():
    root = tk.Tk()  # An unavailable real Tk is a failure, not a passing skip.
    root.withdraw()
    errors, python_errors, refs = [], [], []
    root.tk.createcommand('bgerror', errors.append)
    root.report_callback_exception = lambda *exc: python_errors.append(str(exc))

    def create():
        mini = _create(root)
        refs.append(weakref.ref(mini))
        return mini

    try:
        yield root, create, errors, python_errors
    finally:
        if not getattr(root, '_mini_test_destroyed', False):
            for ref in refs:
                mini = ref()
                if mini is not None and mini.win.winfo_exists():
                    mini.win.destroy()
        # After assertions only: release this test's own retained interpreter
        # jobs, including deliberately stale jobs from the original RED.
        for job in tuple(_pending(root)):
            root.tk.call('after', 'cancel', job)
        if not getattr(root, '_mini_test_destroyed', False):
            root.destroy()


@pytest.mark.parametrize('after_tick', [False, True])
def test_destroy_cancels_only_own_update(scene, after_tick):
    root, create, errors, python_errors = scene
    mini, other = create(), create()
    root.update_idletasks()
    before = _owned(root, mini.win)
    assert len(before) == 1, before
    if after_tick:
        _until(root, lambda: set(_owned(root, mini.win)) != set(before))
    own, others = _owned(root, mini.win), _owned(root, other.win)
    sentinel = root.after(5000, lambda: None)
    mini.win.destroy()
    remaining = _pending(root)
    stale = {job: script for job, script in own.items() if job in remaining}
    print('MiniBar destroyed owner pending:', stale)
    assert not stale, stale
    assert set(others) <= set(remaining) and sentinel in remaining
    assert not errors and not python_errors


def test_destroy_produces_no_natural_bgerror(scene):
    root, create, errors, python_errors = scene
    mini = create()
    root.update_idletasks()
    mini.win.destroy()
    fired = []
    root.after(1150, lambda: fired.append(True))
    _until(root, lambda: bool(fired))
    print('MiniBar natural bgerror:', errors)
    assert not errors, errors
    assert not python_errors, python_errors


def test_hide_show_keeps_one_live_loop(scene):
    root, create, errors, python_errors = scene
    mini = create()
    mini.hide()
    mini.app.core.connected = False
    _until(root, lambda: mini.label.cget('text').startswith('○'))
    assert mini.win.state() == 'withdrawn'
    assert len(_owned(root, mini.win)) == 1
    mini.show()
    mini.app.core.connected = True
    _until(root, lambda: mini.label.cget('text').startswith('●'))
    assert len(_owned(root, mini.win)) == 1
    assert not errors and not python_errors


def test_tooltip_child_destroy_keeps_owner_update(scene):
    root, create, errors, python_errors = scene
    mini = create()
    root.update_idletasks()
    before = set(_owned(root, mini.win))
    mini._tip_enter()
    assert mini._tip.winfo_exists()
    mini._tip.destroy()
    assert set(_owned(root, mini.win)) == before
    mini.app.core.connected = False
    _until(root, lambda: mini.label.cget('text').startswith('○'))
    assert len(_owned(root, mini.win)) == 1
    assert not errors and not python_errors


def test_repeated_destroy_rebuild_releases_queue_and_object(scene):
    root, create, errors, python_errors = scene
    baseline = set(_pending(root))
    refs = []
    for _ in range(6):
        mini = create()
        root.update_idletasks()
        refs.append(weakref.ref(mini))
        mini.win.destroy()
        del mini
        gc.collect()
        assert set(_pending(root)) == baseline
        assert all(ref() is None for ref in refs)
    assert not errors and not python_errors


def test_parent_root_destroy_cancels_mini_job(scene):
    root, create, errors, python_errors = scene
    mini = create()
    root.update_idletasks()
    own = _owned(root, mini.win)
    assert len(own) == 1
    root.destroy()
    root._mini_test_destroyed = True
    assert not set(own).intersection(_pending(root))
    assert not errors and not python_errors


def test_destroy_during_actual_update_does_not_reschedule(scene):
    root, create, errors, python_errors = scene
    mini = create()
    root.update_idletasks()
    real_config = mini.label.config
    destroyed = []

    def config_then_destroy(*args, **kwargs):
        result = real_config(*args, **kwargs)
        mini.win.destroy()
        destroyed.append(True)
        return result

    mini.label.config = config_then_destroy
    _until(root, lambda: bool(destroyed))
    assert not _pending(root), _pending(root)
    assert not errors and not python_errors
