"""Group removal is not account revocation; late work cannot restore membership."""
from dataclasses import replace
from copy import deepcopy
import sys
import threading
import time

import pytest

from client_core import ClientCore
from config import CFG
from server import Hub, Session, serve
from test_client_core import Collector, _free_port, _make_core


def cleanup(original, *actions):
    failures = []
    for action in actions:
        try:
            action()
        except BaseException as exc:
            failures.append(exc)
    if failures:
        if original is not None:
            original.add_note('owned cleanup failed: '+','.join(type(e).__name__ for e in failures))
        else:
            raise AssertionError('owned cleanup failed') from failures[0]


def assert_stopped(*threads):
    assert not any(t and t.is_alive() for t in threads)


def shutdown(hub):
    assert hub.shutdown(normal=True)


def assert_no_errors(errors):
    assert not errors, errors


@pytest.fixture
def running(tmp_path):
    hub = Hub(cfg=replace(CFG, admin_pwd='', audit_dir=str(tmp_path/'audit'),
                          web_files_dir=str(tmp_path/'web'), bind_host='127.0.0.1',
                          discovery_enabled=False, tray_enabled=False))
    stop, errors, cores = threading.Event(), [], []
    port = _free_port()
    def run():
        try:
            serve(hub, port, stop, False)
        except BaseException as exc:
            errors.append(exc)
    thread = threading.Thread(target=run, name='group-scope-server')
    def spawn(nick):
        core = _make_core(port, nick, tmp_path, history_dir=str(tmp_path/f'client-{len(cores)}'))
        cores.append(core)
        events = Collector(core)
        core.start()
        assert events.wait('welcome', timeout=6)
        return core, events
    thread.start()
    try:
        deadline = time.monotonic()+5
        while not hub._service_started and not errors:
            assert time.monotonic()<deadline
            stop.wait(.01)
        assert not errors
        yield hub, spawn
    finally:
        actions = []
        for core in cores:
            actions.extend((core.stop, lambda core=core: assert_stopped(
                core._reader, core._heartbeat, core._reconnector)))
        cleanup(sys.exception(), *actions, stop.set, lambda: thread.join(12),
                lambda: assert_stopped(thread), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads),
                lambda: assert_no_errors(errors))


def test_group_removal_keeps_both_real_clients_online_and_does_not_rejoin(running, monkeypatch):
    hub, spawn = running
    owner, oc = spawn('scope-owner')
    first, fc = spawn('scope-target')
    gids = []
    for name in ('removed-group', 'kept-group'):
        assert owner.create_group(name, public=True)
        gid = oc.wait('group_state', pred=lambda e:e.get('name')==name)['gid']
        gids.append(gid)
        assert first.join_group(gid)
        assert fc.wait('group_state', pred=lambda e:e.get('gid')==gid
                       and any(m['uid']==first.uid for m in e['members']))
    removed, kept = gids
    second, sc = spawn('scope-target')
    for gid in gids:
        # Existing membership is UID-wide; this second core still records its
        # explicit join intent, even though the server correctly says already in.
        assert second.join_group(gid)
        assert sc.wait('error', pred=lambda e:e.get('code')=='group')
    assert first.uid==second.uid
    assert set(gids)<=first._joined_groups and set(gids)<=second._joined_groups
    epochs = (first.connection_epoch, second.connection_epoch)
    assert owner.kick_member(removed, first.uid)
    notification = sc.wait('error', pred=lambda e:e.get('code') in ('group_removed','kicked'))
    assert notification
    assert second.connected and not second._manual_login_required, notification
    assert notification['code']=='group_removed' and notification['gid']==removed
    assert fc.wait('error', pred=lambda e:e.get('code')=='group_removed' and e.get('gid')==removed)
    for core in (first,second):
        assert core.connected and not core._stop.is_set()
        assert removed not in core._joined_groups and kept in core._joined_groups
    assert (first.connection_epoch,second.connection_epoch)==epochs
    assert first.uid not in hub.groups[removed]['members']
    assert first.uid in hub.groups[kept]['members']
    assert first.send_chat('still authenticated after group removal')
    assert sc.wait('chat',pred=lambda e:e.get('text')=='still authenticated after group removal')
    # Wait on a later response from the new connection, after any automatic join
    # frames have been processed; an arbitrary sleep cannot prove no rejoin.
    welcome_done = threading.Event()
    original_welcome = first._on_welcome
    def on_welcome(frame):
        original_welcome(frame)
        welcome_done.set()
    monkeypatch.setattr(first, '_on_welcome', on_welcome)
    first.drop()
    assert fc.wait('welcome',timeout=6,pred=lambda e:e.get('_connection_epoch',0)>epochs[0])
    assert welcome_done.wait(3)
    assert first.send_chat('after ordinary reconnect')
    assert oc.wait('chat',pred=lambda e:e.get('text')=='after ordinary reconnect')
    assert first.uid not in hub.groups[removed]['members']
    assert first.uid in hub.groups[kept]['members']
    assert first.send_group('kept group still works', kept)
    assert oc.wait('chat', pred=lambda e:e.get('to')==kept and e.get('text')=='kept group still works')
    assert first.join_group(removed)
    assert fc.wait('group_state', pred=lambda e:e.get('gid')==removed
                   and any(m['uid']==first.uid for m in e['members']))
    assert removed in first._joined_groups and removed not in first._removed_groups
    assert first.connected and not first._manual_login_required


@pytest.fixture
def core(tmp_path):
    value=ClientCore(nick='synthetic-group-core',history_dir=str(tmp_path/'core'))
    value.uid=7
    try:
        yield value
    finally:
        cleanup(sys.exception(), value.stop, lambda: assert_stopped(
            value._reader, value._heartbeat, value._reconnector))


def state(gid=10, revision=1):
    return {'t':'group_state','gid':gid,'group_revision':revision,
            'members':[{'uid':7,'nick':'target'},{'uid':8,'nick':'owner'}]}


def test_late_group_state_and_old_removal_cannot_restore_or_remove_new_membership(core, monkeypatch):
    core._dispatch(state())
    core._dispatch(state(gid=11))
    core.group_invites[10]='synthetic-old-invite'
    session_key = b's'*32
    monkeypatch.setattr(core.e2ee, 'session_key', lambda _uid: session_key)
    for gid in (10, 11):
        core.e2ee.new_group_epoch(gid)
        core.e2ee.set_peer_sender_key(gid, 8, b'p'*32, 1)
        core._e2ee_groups.add(gid)
        core._e2ee_group_members[gid] = frozenset((7, 8))
    kept = deepcopy((core.e2ee._groups[11], core.e2ee._my_sk[11], core.e2ee._my_send[11]))
    envelope = {'t':'e2ee_sk_dist_one','gid':10,'epoch':2,'from':8,
                'ct':core.e2ee.seal(session_key, {'sk':(b'n'*32).hex()}).hex()}
    assert core.e2ee.unseal(session_key, bytes.fromhex(envelope['ct']))['sk']==(b'n'*32).hex()
    core._dispatch({'t':'error','code':'group_removed','gid':10,'group_revision':2})
    core._on_e2ee_sk_dist_one(envelope)
    assert not core.group_e2ee_on(10) and 10 not in core._e2ee_group_members
    assert all(10 not in mapping for mapping in (core.e2ee._groups, core.e2ee._my_sk, core.e2ee._my_send))
    assert core.e2ee.peer_sender_entry(10, 8) is None
    assert core.group_e2ee_on(11) and core._e2ee_group_members[11]==frozenset((7, 8))
    assert kept==(core.e2ee._groups[11], core.e2ee._my_sk[11], core.e2ee._my_send[11])
    core._dispatch(state(revision=1))
    assert 10 not in core._joined_groups and 10 not in core.group_members
    assert 10 not in core.group_invites and 11 in core._joined_groups
    core._dispatch(state(revision=3))  # a later legitimate explicit rejoin
    core._dispatch({'t':'error','code':'group_removed','gid':10,'group_revision':2})
    assert 10 in core._joined_groups and core.group_members[10]
    assert not core._manual_login_required and not core._stop.is_set()


@pytest.mark.parametrize('reconnect', [False, True])
def test_group_key_worker_cannot_publish_after_removal(core,monkeypatch,reconnect):
    core._dispatch(state())
    entered=threading.Event()
    result=[]
    errors=[]
    pending=[]
    calls=[0]
    created=[]
    original_epoch=core.e2ee.new_group_epoch
    def new_epoch(*args,**kwargs):
        created.append(args[0])
        return original_epoch(*args,**kwargs)
    def key(_peer):
        calls[0]+=1
        return None if calls[0]==1 else b'x'*32
    def send(frame,body=b''):
        if frame['t']=='e2ee_pub':
            pending.append(core._e2ee_pending[frame['nonce']]['ev'])
            entered.set()
        return True
    monkeypatch.setattr(core.e2ee,'session_key',key)
    monkeypatch.setattr(core.e2ee,'new_group_epoch',new_epoch)
    monkeypatch.setattr(core,'_send_frame',send)
    def run():
        try:
            result.append(core.open_group_e2ee(10,timeout=4))
        except BaseException as exc:
            errors.append(exc)
    worker=threading.Thread(target=run)
    worker.start()
    try:
        assert entered.wait(3)
        core._dispatch({'t':'error','code':'group_removed','gid':10,'group_revision':2})
        if reconnect:
            core._dispatch({'t':'welcome','uid':7,'roster':[],'groups':[],'history':[]})
            core._dispatch(state(revision=1))
            assert 10 in core._joined_groups  # a restarted Hub's counter begins again
        pending[0].set()
        worker.join(3)
        assert not worker.is_alive() and not errors
        assert result and result[0][0] is False
        assert created == []
        assert not core.group_e2ee_on(10)
        assert 10 not in core.e2ee._my_sk and 10 not in core.e2ee._groups
    finally:
        cleanup(sys.exception(), *(event.set for event in pending),
                lambda: worker.join(5), lambda: assert_stopped(worker),
                lambda: assert_no_errors(errors))


def test_server_old_group_snapshot_is_ordered_before_later_removal(tmp_path):
    hub=Hub(cfg=replace(CFG,admin_pwd='',audit_dir=str(tmp_path/'audit'),
                        web_files_dir=str(tmp_path/'web')))
    entered,release=threading.Event(),threading.Event()
    frames=[]
    errors=[]
    worker=None
    def capture(frame,*_):
        if frame.get('text')=='paused old snapshot':
            entered.set()
            assert release.wait(4)
        frames.append(frame)
    try:
        owner=Session(0,'owner','tcp','127.0.0.1',lambda *_:None)
        target=Session(0,'target','tcp','127.0.0.1',capture)
        assert hub._attach(owner) and hub._attach(target)
        hub._on_group_create(owner,{'name':'ordered','public':True})
        gid=next(iter(hub.groups))
        hub._on_group_join(target,{'gid':gid})
        def delayed():
            try:
                hub._send_group_state(gid,text='paused old snapshot')
            except BaseException as exc:
                errors.append(exc)
        worker=threading.Thread(target=delayed)
        worker.start()
        assert entered.wait(3)
        hub._on_group_kick(owner,{'gid':gid,'target':target.uid})
        release.set()
        worker.join(3)
        assert not worker.is_alive() and not errors
        removed=next(f for f in frames if f.get('code')=='group_removed')
        old=next(f for f in frames if f.get('text')=='paused old snapshot')
        assert frames.index(removed)<frames.index(old)
        assert old['group_revision']<removed['group_revision']
        assert target.uid in [m['uid'] for m in old['members']]
    finally:
        cleanup(sys.exception(), release.set,
                lambda: worker.join(5) if worker else None,
                lambda: assert_stopped(worker), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads),
                lambda: assert_no_errors(errors))


def test_group_removal_notifies_all_sessions_without_revoking_web_token(tmp_path):
    hub=Hub(cfg=replace(CFG,admin_pwd='',audit_dir=str(tmp_path/'audit'),
                        web_files_dir=str(tmp_path/'web')))
    sessions=[]
    outputs=[]
    try:
        for nick,kind in [('owner','tcp'),('target','tcp'),('target','web'),('observer','tcp')]:
            frames=[]
            session=Session(0,nick,kind,'127.0.0.1',lambda h,*_,frames=frames:frames.append(h))
            assert hub._attach(session)
            sessions.append(session)
            outputs.append(frames)
        owner,target,web,observer=sessions
        hub.web_tokens['synthetic-group-token']=web
        hub._on_group_create(owner,{'name':'scoped','public':True})
        gid=next(iter(hub.groups))
        hub._on_group_join(target,{'gid':gid})
        for frames in outputs:
            frames.clear()
        hub._on_group_kick(owner,{'gid':gid,'target':target.uid})
        for frames in outputs[1:3]:
            removed=[f for f in frames if f.get('code')=='group_removed']
            assert len(removed)==1 and removed[0]['gid']==gid
            assert type(removed[0]['group_revision']) is int
            assert not any(f.get('code')=='kicked' for f in frames)
        assert hub.session_by_token('synthetic-group-token') is web
        assert all(hub._session_is_active(s) for s in sessions)
        assert not any(f.get('code')=='group_removed' for f in outputs[0]+outputs[3])
    finally:
        cleanup(sys.exception(), lambda: shutdown(hub),
                lambda: assert_stopped(*hub._managed_threads))
