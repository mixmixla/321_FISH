"""Location metadata must remain finite before entering durable chat history."""

from dataclasses import replace
import json
import math
import time

import pytest

from config import CFG
import server
from server import Hub, Session
from server_recovery import StoreCoordinator


NOW = 1_800_000_000.0


@pytest.fixture
def hubs(tmp_path):
    owned = []

    def create(*, durable=False, reopen=None):
        root = reopen or tmp_path / str(len(owned))
        cfg = replace(CFG, audit_dir=str(root / 'audit'), web_files_dir=str(root / 'web'),
                      persist_interval=3600.0, bind_host='127.0.0.1',
                      discovery_enabled=False, tray_enabled=False)
        if durable and reopen is None:
            StoreCoordinator.initialize_new(root / 'store')
        hub = Hub(cfg=cfg, store_dir=str(root / 'store') if durable else None)
        hub._persist_last = time.time()
        owned.append(hub)
        return hub, root

    yield create
    for hub in reversed(owned):
        hub.shutdown(normal=False)
        if hub._recovery is not None:
            assert not hub._recovery.owner.held
        assert not any(worker.is_alive() for worker in hub._managed_threads)


def login(hub, nick='synthetic-geo'):
    frames = []
    sess = Session(0, nick, 'tcp', '127.0.0.1',
                   lambda header, *_: frames.append(header))
    assert hub.dispatch(sess, {'t': 'hello', 'nick': sess.nick})
    frames.clear()
    return sess, frames


@pytest.mark.parametrize('expiry', [
    pytest.param(float('nan'), id='float-nan'),
    pytest.param('NaN', id='string-NaN'),
    pytest.param('nan', id='string-nan'),
    pytest.param(float('inf'), id='positive-infinity'),
    pytest.param(float('-inf'), id='negative-infinity'),
    pytest.param('Infinity', id='string-positive-infinity'),
    pytest.param('-Infinity', id='string-negative-infinity'),
    pytest.param(10 ** 1000, id='conversion-overflow'),
    pytest.param('invalid', id='invalid-text'),
    pytest.param({}, id='invalid-object'),
    pytest.param(None, id='missing-value'),
])
def test_invalid_expiry_uses_finite_default_ttl(hubs, monkeypatch, expiry):
    hub, _ = hubs()
    monkeypatch.setattr(server, '_now', lambda: NOW)
    geo = hub._san_geo({'lat': 12.3456789, 'lon': 45.1234567, 'live': 1,
                        'expire': expiry, 'name': 'synthetic place', 'session': 'synthetic'})
    assert math.isfinite(geo['expire'])
    assert geo['expire'] == NOW + hub.cfg.geo_live_ttl
    assert geo['lat'] == 12.345679 and geo['lon'] == 45.123457
    assert geo['name'] == 'synthetic place' and geo['session'] == 'synthetic'


@pytest.mark.parametrize('offset', [-30, 0, 150, 500, 3600, 7200, '500'])
def test_finite_expiry_preserves_clamp_and_numeric_strings(hubs, monkeypatch, offset):
    hub, _ = hubs()
    monkeypatch.setattr(server, '_now', lambda: NOW)
    value = NOW + float(offset)
    if isinstance(offset, str):
        value = str(value)
    geo = hub._san_geo({'lat': 12, 'lon': 45, 'live': 1, 'expire': value})
    assert geo['expire'] == min(max(float(value), NOW + hub.cfg.geo_live_ttl), NOW + 3600)


@pytest.mark.parametrize(('field', 'value'), [
    ('lat', float('nan')), ('lon', float('inf')), ('lat', 91), ('lon', 181),
    pytest.param('lat', 10 ** 1000, id='latitude-overflow'),
    pytest.param('lon', 10 ** 1000, id='longitude-overflow'),
])
def test_invalid_coordinate_drops_metadata_but_keeps_chat_text(hubs, field, value):
    hub, _ = hubs()
    sess, _ = login(hub)
    geo = {'lat': 12, 'lon': 45, field: value}
    hub.dispatch(sess, {'t': 'chat', 'channel': 'public', 'text': 'keep synthetic text', 'geo': geo})
    message = hub.bus.history('all')[-1]
    assert message['text'] == 'keep synthetic text'
    assert 'geo' not in message


def test_static_location_does_not_use_expiry(hubs):
    hub, _ = hubs()
    assert hub._san_geo({'lat': 12, 'lon': 45, 'expire': 'NaN'}) == {'lat': 12.0, 'lon': 45.0}


@pytest.mark.parametrize('expiry', ['NaN', pytest.param(10 ** 1000, id='conversion-overflow')])
def test_live_update_broadcast_is_finite_without_history(hubs, monkeypatch, expiry):
    hub, _ = hubs()
    sess, _ = login(hub)
    _receiver, frames = login(hub, 'synthetic-receiver')
    before = hub.bus.history('all')
    monkeypatch.setattr(server, '_now', lambda: NOW)
    hub.dispatch(sess, {'t': 'geo_live', 'channel': 'public',
                        'geo': {'lat': 12, 'lon': 45, 'live': 1, 'expire': expiry}})
    updates = [frame for frame in frames if frame.get('t') == 'geo_live']
    assert len(updates) == 1
    assert math.isfinite(updates[0]['geo']['expire'])
    assert updates[0]['geo']['expire'] == NOW + hub.cfg.geo_live_ttl
    assert hub.bus.history('all') == before


def test_json_nan_chat_keeps_real_durable_store_healthy(hubs):
    hub, root = hubs(durable=True)
    sess, frames = login(hub)
    assert hub._persist(force=True)
    request = json.loads('{"t":"chat","channel":"public","text":"synthetic location",'
                         '"geo":{"lat":12,"lon":45,"live":1,"expire":"NaN"}}')
    hub.dispatch(sess, request)
    persisted = hub._persist(force=True)
    outcome = {'persisted': persisted, 'ready': hub._service_ready,
               'stopped': hub._service_stop.is_set(), 'phase': hub._recovery.phase}
    # Reach the original real FAILED path before any field/rejection assertion.
    assert outcome == {'persisted': True, 'ready': True, 'stopped': False, 'phase': 'READY'}
    message = hub.bus.history('all')[-1]
    assert message['text'] == 'synthetic location' and math.isfinite(message['geo']['expire'])
    assert any(frame.get('t') == 'chat' and frame.get('text') == 'synthetic location' for frame in frames)
    hub.dispatch(sess, {'t': 'chat', 'channel': 'public', 'text': 'after location'})
    assert hub._persist(force=True)
    assert hub.shutdown(normal=False)
    reopened, _ = hubs(durable=True, reopen=root)
    messages = {message['text']: message for message in reopened.bus.history('all') if 'text' in message}
    assert 'after location' in messages
    assert math.isfinite(messages['synthetic location']['geo']['expire'])
    assert reopened._persist(force=True)
