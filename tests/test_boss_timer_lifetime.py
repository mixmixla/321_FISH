"""Real Tk Boss ownership with unchanged 1500/3000ms product delays."""
import gc
import json
import time
import tkinter as tk
import weakref

import pytest

from boss import BossWindow, BOSS_ALIVE_INTERVAL


def _pending(root):
    return {str(job): str(root.tk.call('after', 'info', job)[0])
            for job in root.tk.splitlist(root.tk.call('after', 'info'))}


def _owned(root, window):
    commands = set(window._tclCommands or ())
    return {job: script for job, script in _pending(root).items()
            if root.tk.splitlist(script)[0] in commands}


def _run_for(root, ms):
    root.after(ms, root.quit)
    root.mainloop()


def _until(root, predicate, timeout=5):
    if predicate():
        return
    deadline = time.monotonic() + timeout

    def check():
        if predicate() or time.monotonic() >= deadline:
            root.quit()
        else:
            root.after(20, check)

    root.after(0, check)
    root.mainloop()
    assert predicate(), 'real Tk event condition did not complete'


@pytest.fixture
def scene():
    assert BOSS_ALIVE_INTERVAL == 3.0
    root = tk.Tk()  # Missing real Tk fails, never becomes passing acceptance.
    root.withdraw()
    errors, python_errors, refs = [], [], []

    def bgerror(message):
        errors.append(message)
        return ''

    root.tk.createcommand('bgerror', bgerror)
    root.report_callback_exception = lambda *exc: python_errors.append(str(exc))

    def create(show=False):
        boss = BossWindow(root, skin='excel')
        refs.append(weakref.ref(boss))
        if show:
            boss.show()
        return boss

    try:
        yield root, create, errors, python_errors
    finally:
        if not getattr(root, '_boss_test_destroyed', False):
            for ref in refs:
                boss = ref()
                if boss is not None:
                    boss.close()
        # Test-owned RED cleanup only, after all acceptance assertions.
        for job in tuple(_pending(root)):
            root.tk.call('after', 'cancel', job)
        if not getattr(root, '_boss_test_destroyed', False):
            root.destroy()


def test_close_inside_mainloop_clears_jobs_without_real_bgerror(scene):
    root, create, errors, python_errors = scene
    boss = create(show=True)
    root.update_idletasks()
    start = time.monotonic()
    heartbeat, deadlines, closed = [], [], {}

    def beat():
        heartbeat.append(time.monotonic() - start)
        root.after(100, beat)

    def close():
        own = _owned(root, boss.win)
        assert len(own) == 2, own
        assert boss.win.winfo_exists()
        assert all(root.tk.call('info', 'commands', root.tk.splitlist(s)[0])
                   for s in own.values())
        boss.close()
        closed.update(exists=bool(boss.win.winfo_exists()),
                      stale={j:s for j,s in own.items() if j in _pending(root)})

    root.after(0, beat)
    root.after(100, close)
    root.after(1600, lambda: deadlines.append('past1500'))
    root.after(3100, lambda: deadlines.append('past3000'))
    _run_for(root, 3500)
    print(json.dumps({'closed': closed, 'heartbeat_count': len(heartbeat),
                      'elapsed': time.monotonic()-start,
                      'deadlines': deadlines, 'bgerror': errors,
                      'python_errors': python_errors}))
    assert time.monotonic() - start >= 3.4
    assert len(heartbeat) >= 25
    assert set(deadlines) == {'past1500', 'past3000'}
    assert closed and not closed['exists']
    assert not closed['stale'], closed['stale']
    assert not errors and not python_errors


@pytest.mark.parametrize('after_tick', [False, True])
def test_close_cancels_only_own_tasks(scene, after_tick):
    root, create, errors, python_errors = scene
    boss, other = create(show=True), create()
    root.update_idletasks()
    ticks = []
    real_tick = boss._tick_fn

    def tick():
        real_tick()
        ticks.append(True)

    boss._tick_fn = tick
    if after_tick:
        _until(root, lambda: bool(ticks))
    own, others = _owned(root, boss.win), _owned(root, other.win)
    assert own and others
    sentinel = root.after(5000, lambda: None)
    boss.close()
    boss.close()
    remaining = _pending(root)
    assert not set(own).intersection(remaining)
    assert set(others) <= set(remaining) and sentinel in remaining
    assert not errors and not python_errors


def test_hide_show_keeps_real_tick_and_releases_finished_one_shot(scene):
    root, create, errors, python_errors = scene
    boss = create(show=True)
    root.update_idletasks()
    ticks = []
    real_tick = boss._tick_fn

    def tick():
        real_tick()
        ticks.append(True)

    boss._tick_fn = tick
    _run_for(root, 1700)
    assert not bool(boss.win.attributes('-topmost'))
    assert len(_owned(root, boss.win)) == 1
    boss.hide()
    _until(root, lambda: bool(ticks))
    assert boss.win.state() == 'withdrawn'
    assert len(_owned(root, boss.win)) == 1
    if hasattr(boss, '_after_jobs'):
        assert set(boss._after_jobs) == set(_owned(root, boss.win))
    boss.show()
    assert boss.visible()
    assert not errors and not python_errors


def test_child_skin_rebuild_does_not_destroy_owner_updates(scene):
    root, create, errors, python_errors = scene
    boss = create()
    boss.set_skin('terminal')
    ticks = []
    real_tick = boss._tick_fn

    def tick():
        real_tick()
        ticks.append(True)

    boss._tick_fn = tick
    _until(root, lambda: bool(ticks))
    assert boss.win.winfo_exists() and boss._alive
    own = _owned(root, boss.win)
    assert own
    boss.close()
    assert not set(own).intersection(_pending(root))
    assert not errors and not python_errors


def test_repeated_close_rebuild_releases_objects_and_queue(scene):
    root, create, errors, python_errors = scene
    baseline = set(_pending(root))
    refs = []
    for _ in range(6):
        boss = create(show=True)
        root.update_idletasks()
        refs.append(weakref.ref(boss))
        boss.close()
        del boss
        gc.collect()
        assert set(_pending(root)) == baseline
        assert all(ref() is None for ref in refs)
    assert not errors and not python_errors


def test_parent_root_destroy_cancels_owner_tasks(scene):
    root, create, errors, python_errors = scene
    boss = create(show=True)
    root.update_idletasks()
    own = _owned(root, boss.win)
    assert len(own) == 2
    root.destroy()
    root._boss_test_destroyed = True
    assert not set(own).intersection(_pending(root))
    assert not errors and not python_errors


def test_direct_owner_destroy_cancels_tasks(scene):
    root, create, errors, python_errors = scene
    boss = create(show=True)
    root.update_idletasks()
    own = _owned(root, boss.win)
    assert len(own) == 2
    boss.win.destroy()
    assert not set(own).intersection(_pending(root))
    assert not errors and not python_errors


def test_close_during_real_tick_does_not_reschedule(scene):
    root, create, errors, python_errors = scene
    boss = create(show=True)
    closed = []
    real_tick = boss._tick_fn

    def tick_then_close():
        real_tick()
        boss.close()
        closed.append(True)

    boss._tick_fn = tick_then_close
    _until(root, lambda: bool(closed))
    assert not _pending(root), _pending(root)
    assert not errors and not python_errors
