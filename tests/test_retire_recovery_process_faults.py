"""Actual Windows sharing failures followed by abrupt process exit/recovery."""
from pathlib import Path
import hashlib
import subprocess
import sys

import pytest

from server import Hub, Session
from server_recovery import strict_json
from test_retire_recovery_hub import fresh_hub, people, stop_fixture, config_for


@pytest.mark.parametrize('fault', ['intent_replace', 'intent_read', 'snapshot_replace'])
def test_actual_sharing_fault_then_exit_never_invents_or_loses_retirement(tmp_path, fault):
    hub = fresh_hub(tmp_path)
    _, _, user, survivor = people(hub)
    uid, nick = user.uid, user.nick
    cloud_file = Path(hub.cloud_dir) / f'{uid}.bin'
    cloud_file.write_bytes(b'synthetic-private-body')
    before_state = (tmp_path / 'store/state.json').read_bytes()
    before_control = (tmp_path / 'store/control.json').read_bytes()
    stop_fixture(hub)
    script = r'''
import ctypes, hashlib, json, os, secrets, sys, time
from pathlib import Path
from dataclasses import replace
from config import CFG
from server import Hub, Session
root, uid, fault = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
cfg = replace(CFG, admin_pwd=secrets.token_urlsafe(24),
              web_files_dir=str(root/'web'), audit_dir=str(root/'audit'),
              persist_interval=3600.0, discovery_enabled=False, tray_enabled=False)
hub = Hub(cfg=cfg, store_dir=str(root/'store'))
hub._persist_last = time.time()
admin = Session(0, cfg.admin_nick, 'tcp', '127.0.0.1', lambda *_: None)
assert hub._on_hello(admin, {'nick': cfg.admin_nick, 'pwd': cfg.admin_pwd})
api = hub._recovery.owner._api
target = root/'store'/('state.json' if fault == 'snapshot_replace' else 'control.json')
handle = api.CreateFileW(str(target), 0x80000000, 0 if fault == 'intent_read' else 1,
                         None, 3, 0x80, None)
assert handle != ctypes.c_void_p(-1).value
hub._on_admin_user_del(admin, {'uid': uid, 'request_id': 'real_sharing_fault'})
result = {'receipt': hub._retirement_payload(uid), 'retired': uid in hub.retired,
          'service_available': hub._service_available(), 'phase': hub._recovery.phase,
          'before_flush_sha256': hashlib.sha256((root/'store/state.json').read_bytes()).hexdigest(),
          'ordinary_flush': hub._persist(force=True)}
(root/'fault-result.json').write_text(json.dumps(result), encoding='utf-8')
os._exit(46)  # No Hub/finally flush. The OS releases the actual file and owner handles.
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path), str(uid), fault],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 46, result.stderr
    report = strict_json((tmp_path / 'fault-result.json').read_bytes())
    receipt = report['receipt']
    assert report['before_flush_sha256'] == hashlib.sha256(before_state).hexdigest()
    if fault == 'intent_replace':
        # A known pre-intent failure leaves ordinary service healthy. This
        # explicitly requested later ordinary flush may save login metadata,
        # but must not invent a tombstone or turn the DEL into a confirmation.
        assert report['ordinary_flush'] is True and report['service_available']
        assert not strict_json((tmp_path / 'store/state.json').read_bytes())['retired']
    else:
        assert report['ordinary_flush'] is False
        assert (tmp_path / 'store/state.json').read_bytes() == before_state
    if fault == 'snapshot_replace':
        assert receipt['status'] == 'failed' and report['retired']
        assert receipt['persistence_phase'] == 'snapshot' and receipt['identity_effect'] == 'revoked'
        accepted = strict_json((tmp_path / 'store/control.json').read_bytes())['intents'][str(uid)]
        assert accepted['operation_id'] == receipt['operation_id']
        # Abort one recovery itself before its state IO; the next recovery
        # must still use the same accepted operation and old authority.
        recovery_script = r'''
import os, sys
from pathlib import Path
from dataclasses import replace
from config import CFG
from server import Hub
root = Path(sys.argv[1])
Hub._store_commit = lambda *_: os._exit(47)
Hub(cfg=replace(CFG, web_files_dir=str(root/'web'), audit_dir=str(root/'audit')),
    store_dir=str(root/'store'))
'''
        again = subprocess.run([sys.executable, '-c', recovery_script, str(tmp_path)],
                               capture_output=True, timeout=12)
        assert again.returncode == 47, again.stderr
        assert (tmp_path / 'store/state.json').read_bytes() == before_state
    else:
        assert not report['retired'] and receipt['persistence_phase'] == 'intent'
        assert (tmp_path / 'store/control.json').read_bytes() == before_control
        if fault == 'intent_read':
            assert receipt['status'] == 'unknown' and receipt['identity_effect'] == 'unverified'
            assert report['phase'] == 'FAILED' and not report['service_available']
        else:
            assert receipt['status'] == 'failed' and receipt['identity_effect'] == 'not_started'
    reopened = Hub(cfg=config_for(tmp_path), store_dir=str(tmp_path / 'store'))
    try:
        assert survivor.uid in reopened.known and reopened.nick_to_uid[nick] == uid
        assert cloud_file.read_bytes() == b'synthetic-private-body'
        attempted = Session(0, nick, 'tcp', '127.0.0.1', lambda *_: None)
        if fault == 'snapshot_replace':
            current = reopened._retirement_payload(uid)
            assert current['status'] == 'confirmed' and current['operation_id'] == receipt['operation_id']
            assert uid not in reopened.known and uid not in reopened.cloud
            assert reopened._on_hello(attempted, {'nick': nick}) is False
        else:
            assert uid not in reopened.retired and uid in reopened.known
            assert reopened._on_hello(attempted, {'nick': nick}) is True
    finally:
        stop_fixture(reopened)
