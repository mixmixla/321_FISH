"""A group slot and an admin add decision must be claimed under the Hub lock."""
from dataclasses import replace
import sys
import threading

import pytest

from config import CFG
from server import Hub, Session


def _session(hub, nick, output):
    frames = []
    sess = Session(0, nick, 'tcp', '127.0.0.1',
                   lambda frame, *_, frames=frames: frames.append(frame))
    assert hub._attach(sess)
    output[nick] = frames
    return sess


class PreMutationGate:
    """Rendezvous before the real mutation lock, never while holding it."""

    def __init__(self, lock, target_entries):
        self.lock = lock
        self.target_entries = target_entries
        self.barrier = threading.Barrier(len(target_entries))
        self.guard = threading.Lock()
        self.entries = {}
        self.reached = set()

    def __enter__(self):
        current = threading.current_thread()
        with self.guard:
            count = self.entries.get(current, 0) + 1
            self.entries[current] = count
            at_mutation = count == self.target_entries.get(current)
            if at_mutation:
                self.reached.add(current)
        if at_mutation:
            self.barrier.wait(3)
        return self.lock.__enter__()

    def __exit__(self, *args):
        return self.lock.__exit__(*args)

    def acquire(self, *args, **kwargs):
        return self.lock.acquire(*args, **kwargs)

    def release(self):
        return self.lock.release()


def _run_pair(hub, actions, mutation_entries):
    errors = []
    workers = [threading.Thread(target=lambda action=action: _capture(action, errors),
                                name=f'capacity-{i}')
               for i, action in enumerate(actions)]
    gate = PreMutationGate(hub.lock, dict(zip(workers, mutation_entries)))
    original_lock = hub.lock
    hub.lock = gate
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)
        assert not any(worker.is_alive() for worker in workers)
        assert not errors, errors
        assert gate.reached == set(workers), 'both handlers must reach the post-precheck gate'
        assert all(gate.entries[worker] >= gate.target_entries[worker]
                   for worker in workers)
    finally:
        original = sys.exception()
        gate.barrier.abort()
        for worker in workers:
            worker.join(5)
        hub.lock = original_lock
        if any(worker.is_alive() for worker in workers):
            if original is not None:
                original.add_note('owned capacity worker did not stop')
            else:
                raise AssertionError('owned capacity worker did not stop')


def _capture(action, errors):
    try:
        action()
    except BaseException as exc:
        errors.append(exc)


@pytest.fixture
def group(tmp_path, monkeypatch):
    hub = Hub(cfg=replace(CFG, group_max_members=3, admin_pwd='',
                          audit_dir=str(tmp_path/'audit'),
                          web_files_dir=str(tmp_path/'web')))
    output = {}
    lock_probes = []
    probe_workers = []
    original_lock = hub.lock

    def observe_rejection(sess):
        frames = output[sess.nick]
        def send(frame, *_):
            frames.append(frame)
            if frame.get('t') != 'error' or frame.get('code') not in ('full', 'member', 'group'):
                return
            acquired = threading.Event()
            def probe():
                if original_lock.acquire(timeout=2):
                    try:
                        acquired.set()
                    finally:
                        original_lock.release()
            worker = threading.Thread(target=probe, name='capacity-error-lock-probe')
            probe_workers.append(worker)
            worker.start()
            lock_probes.append((frame['code'], acquired.wait(.5)))
        sess.send = send

    try:
        owner = _session(hub, 'capacity-owner', output)
        filler = _session(hub, 'capacity-filler', output)
        first = _session(hub, 'capacity-first', output)
        second = _session(hub, 'capacity-second', output)
        admin = _session(hub, 'capacity-admin', output)
        admin.is_admin = True
        hub._on_group_create(owner, {'name': 'capacity-public', 'public': True})
        gid = next(iter(hub.groups))
        hub._on_group_join(filler, {'gid': gid})
        assert len(hub.groups[gid]['members']) == 2
        for sess in (first, second, admin):
            observe_rejection(sess)
        for frames in output.values():
            frames.clear()
        audit = []
        monkeypatch.setattr(hub.audit, 'log', lambda **record: audit.append(record))
        yield hub, gid, owner, first, second, admin, output, lock_probes, audit
    finally:
        original = sys.exception()
        failures = []
        for worker in probe_workers:
            worker.join(3)
            if worker.is_alive():
                failures.append(AssertionError('owned rejection probe did not stop'))
        try:
            assert hub.shutdown(normal=True)
            assert not any(t.is_alive() for t in hub._managed_threads)
        except BaseException as exc:
            failures.append(exc)
        if failures:
            if original is not None:
                original.add_note('owned group cleanup failed: ' +
                                  ', '.join(type(e).__name__ for e in failures))
            else:
                raise AssertionError('owned group cleanup failed') from failures[0]


@pytest.mark.parametrize('routes,entries', [
    (('public', 'public'), (1, 1)),
    (('admin', 'admin'), (2, 2)),
    (('public', 'admin'), (1, 2)),
])
def test_two_distinct_claimants_cannot_take_one_slot(group, routes, entries):
    hub, gid, _, first, second, admin, output, lock_probes, audit = group
    targets = (first, second)
    actions = [
        (lambda target=target, route=route:
         hub._on_group_join(target, {'gid': gid}) if route == 'public'
         else hub._on_admin_group_set(admin, {'gid': gid, 'op': 'add', 'uid': target.uid}))
        for target, route in zip(targets, routes)
    ]
    _run_pair(hub, actions, entries)
    members = hub.groups[gid]['members']
    assert len(members) == 3
    assert sum(target.uid in members for target in targets) == 1
    assert len([r for r in audit if r.get('type') in ('group_join', 'admin_group_add')]) == 1
    error_frames = [frame for frames in output.values() for frame in frames
                    if frame.get('t') == 'error' and frame.get('code') == 'full']
    assert len(error_frames) == 1
    assert lock_probes == [('full', True)]  # another thread acquired the same Hub lock


def test_two_admin_adds_of_same_uid_have_one_success(group):
    hub, gid, _, first, _, admin, output, lock_probes, audit = group
    actions = [lambda: hub._on_admin_group_set(admin,
               {'gid': gid, 'op': 'add', 'uid': first.uid}) for _ in range(2)]
    _run_pair(hub, actions, (2, 2))
    assert first.uid in hub.groups[gid]['members']
    assert len([r for r in audit if r.get('type') == 'admin_group_add']) == 1
    assert len([frame for frame in output[admin.nick]
                if frame.get('t') == 'error' and frame.get('code') == 'member']) == 1
    assert lock_probes == [('member', True)]


def test_existing_full_private_and_invite_controls(group):
    hub, gid, owner, first, second, admin, output, _, _ = group
    hub._on_group_join(first, {'gid': gid})
    hub._on_group_join(first, {'gid': gid})
    hub._on_group_join(second, {'gid': gid})
    assert len(hub.groups[gid]['members']) == 3
    assert any(f.get('code') == 'group' for f in output[first.nick])
    assert any(f.get('code') == 'full' for f in output[second.nick])
    hub._on_group_invite_get(owner, {'gid': gid})
    code = next(f['code'] for f in output[owner.nick] if f.get('t') == 'group_invite')
    hub._on_group_join_invite(second, {'code': code})
    assert len([f for f in output[second.nick] if f.get('code') == 'full']) == 2
    hub._on_group_create(owner, {'name': 'capacity-private', 'public': False})
    private_gid = max(hub.groups)
    hub._on_group_join(second, {'gid': private_gid})
    assert any(f.get('code') == 'private' for f in output[second.nick])
    hub._on_group_join(admin, {'gid': private_gid})  # system admin override remains available
    assert admin.uid in hub.groups[private_gid]['members']
