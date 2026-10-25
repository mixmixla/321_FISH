"""Untrusted schedule times must not poison the durable whole-state snapshot."""
import copy
from dataclasses import replace
import json
import math
import time

import pytest

from config import CFG
from server import Hub, Session
from server_recovery import StoreCoordinator


@pytest.fixture
def hubs(tmp_path):
    owned = []

    def create(*, durable=False, reopen=None):
        root = reopen or tmp_path / str(len(owned))
        cfg = replace(CFG, audit_dir=str(root / 'audit'),
                      web_files_dir=str(root / 'web'), persist_interval=3600.0,
                      bind_host='127.0.0.1', discovery_enabled=False,
                      tray_enabled=False)
        store = root / 'store'
        if durable and reopen is None:
            StoreCoordinator.initialize_new(store)
        hub = Hub(cfg=cfg, store_dir=str(store) if durable else None)
        hub._persist_last = time.time()
        owned.append(hub)
        return hub, root

    yield create
    for hub in reversed(owned):
        hub.shutdown(normal=False)
        if hub._recovery is not None:
            assert not hub._recovery.owner.held
        assert not any(worker.is_alive() for worker in hub._managed_threads)


def login(hub):
    frames = []
    sess = Session(0, 'synthetic-scheduler', 'tcp', '127.0.0.1',
                   lambda header, *_: frames.append(header))
    assert hub.dispatch(sess, {'t': 'hello', 'nick': sess.nick})
    frames.clear()
    return sess, frames


def schedule(hub, sess, fire_at, text='synthetic schedule'):
    return hub.dispatch(sess, {'t': 'sched_set', 'channel': 'public',
                               'text': text, 'fire_at': fire_at})


@pytest.mark.parametrize('bad_time', [
    pytest.param(float('nan'), id='float-nan'),
    pytest.param('NaN', id='json-string-NaN'),
    pytest.param('nan', id='json-string-nan'),
    pytest.param(float('inf'), id='float-positive-infinity'),
    pytest.param(float('-inf'), id='float-negative-infinity'),
    pytest.param('Infinity', id='string-positive-infinity'),
    pytest.param('-Infinity', id='string-negative-infinity'),
    pytest.param(10 ** 1000, id='integer-conversion-overflow'),
])
def test_invalid_time_rejected_without_queue_or_success_side_effects(hubs, monkeypatch, bad_time):
    hub, _ = hubs()
    sess, frames = login(hub)
    schedule(hub, sess, time.time() + 3600, 'keep existing')
    before = copy.deepcopy(hub.scheds)
    frames.clear()
    audit = []
    persistence = []
    monkeypatch.setattr(hub.audit, 'log', lambda **entry: audit.append(entry))
    monkeypatch.setattr(hub, '_persist', lambda *a, **kw: persistence.append((a, kw)))

    schedule(hub, sess, bad_time)

    assert frames and frames[-1].get('code') == 'fire_at'
    assert hub.scheds == before
    assert not any(frame.get('t') == 'sched_list' for frame in frames)
    assert audit == []
    assert persistence == []


@pytest.mark.parametrize('kind', ['float', 'integer', 'numeric-string'])
def test_finite_future_time_preserves_existing_input_forms(hubs, kind):
    hub, _ = hubs()
    sess, frames = login(hub)
    future = time.time() + 3600
    value = {'float': future, 'integer': int(future),
             'numeric-string': str(future)}[kind]
    schedule(hub, sess, value)
    records = list(hub.scheds[sess.uid].values())
    assert len(records) == 1
    assert records[0]['fire_at'] == float(value)
    assert math.isfinite(records[0]['fire_at'])
    assert any(frame.get('t') == 'sched_list' for frame in frames)
    assert not any(frame.get('t') == 'error' for frame in frames)


@pytest.mark.parametrize(('offset', 'code'), [(-60, 'past'), (86400 * 8, 'far')])
def test_finite_time_window_errors_remain_distinct(hubs, offset, code):
    hub, _ = hubs()
    sess, frames = login(hub)
    schedule(hub, sess, time.time() + offset)
    assert frames[-1].get('code') == code
    assert hub.scheds == {}


def test_json_nan_request_keeps_real_durable_store_writable_and_recoverable(hubs):
    hub, root = hubs(durable=True)
    sess, frames = login(hub)
    future = time.time() + 3600
    schedule(hub, sess, future, 'existing durable schedule')
    assert hub._persist(force=True)
    frames.clear()
    request = json.loads('{"t":"sched_set","channel":"public",'
                         '"text":"invalid schedule","fire_at":"NaN"}')
    hub.dispatch(sess, request)

    # Do not assert the rejection first: on the original product this must
    # reach the real snapshot validator and expose the Store FAILED outcome.
    persisted = hub._persist(force=True)
    outcome = {'persisted': persisted, 'ready': hub._service_ready,
               'stopped': hub._service_stop.is_set(), 'phase': hub._recovery.phase}
    assert outcome == {'persisted': True, 'ready': True, 'stopped': False, 'phase': 'READY'}
    assert frames[-1].get('code') == 'fire_at'
    assert len(hub.scheds[sess.uid]) == 1

    schedule(hub, sess, future + 1, 'later durable schedule')
    assert hub._persist(force=True)
    assert hub.shutdown(normal=False)
    reopened, _ = hubs(durable=True, reopen=root)
    assert {r['text'] for r in reopened.scheds[sess.uid].values()} == {
        'existing durable schedule', 'later durable schedule'}
    reopened._sweep_scheds(future + 2)
    assert not reopened.scheds
    assert {m['text'] for m in reopened.bus.history('all')} >= {
        'existing durable schedule', 'later durable schedule'}
    assert reopened._persist(force=True)
