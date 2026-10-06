import json
from pathlib import Path
import pytest
import friend_trial_start as starter

@pytest.fixture
def bundle(tmp_path):
    root=tmp_path/'包含空格的试用包'
    (root/'dist').mkdir(parents=True)
    for name in ('client.exe','server.exe'):(root/'dist'/name).write_bytes(b'MZ synthetic fixture; not executable')
    return root

@pytest.mark.parametrize('value',['8.8.8.8','0.0.0.0','169.254.1.2','100.64.1.2','::1','fd00::1','example.com'])
def test_public_wildcard_link_local_and_non_ipv4_refused(value):
    with pytest.raises(ValueError):starter.permitted_address(value,lan=False)

@pytest.mark.parametrize('value',['10.1.2.3','172.16.0.1','172.31.255.254','192.168.0.2'])
def test_only_explicit_private_ipv4_allowed_for_lan(value):
    assert starter.permitted_address(value,lan=True)==value
    with pytest.raises(ValueError):starter.permitted_address('127.0.0.1',lan=True)

@pytest.mark.parametrize('port',[True,0,1023,65536])
def test_invalid_port_refused(port):
    with pytest.raises(ValueError):starter.valid_port(port)

def test_dry_run_generates_plan_without_profiles_or_processes(bundle,monkeypatch,capsys):
    monkeypatch.setattr(starter,'run_plan',lambda _:pytest.fail('dry run launched'))
    assert starter.main(['--mode','demo','--bundle-dir',str(bundle),'--dry-run'])==0
    plan=json.loads(capsys.readouterr().out)
    assert plan['fresh_only'] and plan['address']=='127.0.0.1'
    assert not (bundle/'trial_runs').exists()
    assert not plan['real_data_import'] and not plan['firewall_changes']

def test_each_plan_is_fresh_and_profiles_are_distinct(bundle):
    a=starter.make_plan(bundle,'demo','',9527,9529)
    b=starter.make_plan(bundle,'demo','',9527,9529)
    assert a['run_dir']!=b['run_dir']
    assert len(set(a['profiles'].values()))==3
    assert all(Path(p).is_relative_to(bundle) for p in a['profiles'].values())
    assert a['nicks']['alpha']!=a['nicks']['beta']

def test_environment_has_no_inherited_credentials_hooks_or_real_profile(tmp_path,monkeypatch):
    for name in ('MOYU_ADMIN_PASSWORD','GITHUB_TOKEN','PYTHONPATH','MOYU_GATE_SANDBOX'):
        monkeypatch.setenv(name,'synthetic-do-not-copy')
    monkeypatch.setenv('USERPROFILE','C:/synthetic-old-user')
    alpha=starter.child_environment(tmp_path/'alpha',bind_host='127.0.0.1',tcp=9527,web=9529)
    beta=starter.child_environment(tmp_path/'beta',bind_host='127.0.0.1',tcp=9527,web=9529)
    assert not any(k in alpha for k in ('MOYU_ADMIN_PASSWORD','GITHUB_TOKEN','PYTHONPATH','MOYU_GATE_SANDBOX'))
    assert alpha['USERPROFILE']==str((tmp_path/'alpha').absolute())
    assert alpha['USERNAME']!=beta['USERNAME']
    assert all(alpha[k]=='0' for k in ('MOYU_DISCOVERY','MOYU_TRAY','MOYU_GLOBAL_HOTKEYS','MOYU_HARDWARE'))

def test_fresh_profile_creation_refuses_reuse(tmp_path):
    profile=tmp_path/'fresh'
    starter.create_profile(profile,'trial_friend')
    original=(profile/'moeyu_helper/prefs.json').read_bytes()
    with pytest.raises(FileExistsError):starter.create_profile(profile,'other')
    assert (profile/'moeyu_helper/prefs.json').read_bytes()==original

def test_join_requires_only_client_and_never_starts_server(bundle):
    (bundle/'dist/server.exe').unlink()
    plan=starter.make_plan(bundle,'join','192.168.1.8',9527,9529)
    assert plan['server_exe'] is None and set(plan['profiles'])=={'alpha'}
    with pytest.raises(ValueError):starter.make_plan(bundle,'host','192.168.1.8',9527,9529)

def test_missing_empty_executable_and_equal_ports_refused(bundle):
    with pytest.raises(ValueError):starter.make_plan(bundle,'demo','',9527,9527)
    (bundle/'dist/client.exe').write_bytes(b'')
    with pytest.raises(ValueError):starter.make_plan(bundle,'demo','',9527,9529)

class Owned:
    def __init__(self,role,exit_code=0,cleanup=True,close_error=False):
        self.role=role;self.exit_code=exit_code;self.cleanup=cleanup;self.terminated=False;self.closed=False;self.close_error=close_error
    def wait(self,timeout=None):return self.exit_code
    def poll(self):return None if self.role=='server' else self.exit_code
    def terminate_tree(self):self.terminated=True;return self.cleanup
    def close(self):
        self.closed=True
        if self.close_error:raise OSError('synthetic close error')

@pytest.mark.parametrize('failure',['none','beta_spawn','client_crash','cleanup','close'])
def test_partial_start_failure_and_owned_cleanup_reported(bundle,monkeypatch,failure):
    owned=[]
    def launch(command,*,cwd,env,log_path):
        role=log_path.stem
        assert Path(cwd)==bundle and env['USERPROFILE'].startswith(str(bundle/'trial_runs'))
        if role=='beta' and failure=='beta_spawn':raise OSError('synthetic partial start')
        p=Owned(role,exit_code=9 if role=='beta' and failure=='client_crash' else 0,
                cleanup=not(role=='server' and failure=='cleanup'),
                close_error=role=='server' and failure=='close')
        owned.append(p)
        return p
    monkeypatch.setattr(starter,'launch_process',launch)
    monkeypatch.setattr(starter,'wait_server',lambda *args:None)
    monkeypatch.setattr(starter,'check_free_ports',lambda *args:None)
    ports=iter([52123,52124])
    monkeypatch.setattr(starter,'free_port',lambda:next(ports))
    plan=starter.make_plan(bundle,'demo','',9527,9529)
    result=starter.run_plan(plan)
    assert result==({'none':0,'beta_spawn':1,'client_crash':1,'cleanup':2,'close':2}[failure])
    summary=json.loads((Path(plan['run_dir'])/'session-summary.json').read_text('utf-8'))
    assert summary['exit_code']==result and not summary['native_gui_acceptance']
    assert summary['cleanup_ok']==(failure not in ('cleanup','close'))
    assert all(p.closed for p in owned)
    assert next(p for p in owned if p.role=='server').terminated

def test_existing_run_directory_is_not_reused(bundle,monkeypatch):
    plan=starter.make_plan(bundle,'demo','',9527,9529)
    run=Path(plan['run_dir']);run.mkdir(parents=True)
    keep=run/'keep';keep.write_bytes(b'synthetic-existing')
    monkeypatch.setattr(starter,'launch_process',lambda *a,**k:pytest.fail('must refuse before launch'))
    with pytest.raises(FileExistsError):starter.run_plan(plan)
    assert keep.read_bytes()==b'synthetic-existing'

@pytest.mark.parametrize('failure',['server_crash','server_stopped','client_crash'])
def test_host_never_reports_success_after_runtime_failure(bundle,monkeypatch,failure):
    def launch(command,*,cwd,env,log_path):
        role=log_path.stem
        p=Owned(role,exit_code=9 if role=='alpha' and failure=='client_crash' else 0)
        if role=='server':
            p.poll=lambda: 9 if failure=='server_crash' else (0 if failure=='server_stopped' else None)
        return p
    monkeypatch.setattr(starter,'launch_process',launch)
    monkeypatch.setattr(starter,'wait_server',lambda *a:None)
    monkeypatch.setattr(starter,'check_free_ports',lambda *a:None)
    monkeypatch.setattr('builtins.input',lambda *a:'')
    monkeypatch.setattr(starter,'console_key',lambda:'\r',raising=False)
    plan=starter.make_plan(bundle,'host','192.168.1.8',9527,9529)
    assert starter.run_plan(plan)==1
    summary=json.loads((Path(plan['run_dir'])/'session-summary.json').read_text('utf-8'))
    assert summary['exit_code']==1 and summary['cleanup_ok']

def test_host_detects_server_failure_while_waiting_without_enter(monkeypatch):
    states=iter([None,7])
    server=Owned('server');server.poll=lambda:next(states)
    monkeypatch.setattr(starter,'console_key',lambda:None)
    monkeypatch.setattr(starter.time,'sleep',lambda _:None)
    with pytest.raises(RuntimeError):starter.wait_host(server,[Owned('alpha')])

def test_host_normal_enter_and_control_c(monkeypatch):
    monkeypatch.setattr(starter,'console_key',lambda:'\r')
    starter.wait_host(Owned('server'),[Owned('alpha')])
    monkeypatch.setattr(starter,'console_key',lambda:'\x03')
    with pytest.raises(KeyboardInterrupt):starter.wait_host(Owned('server'),[Owned('alpha')])

def test_demo_reports_server_stop_even_if_clients_have_not_exited():
    server=Owned('server');server.poll=lambda:3
    client=Owned('alpha');client.poll=lambda:None
    with pytest.raises(RuntimeError):starter.wait_clients([client],server)

def test_windows_job_natural_completion(tmp_path):
    import sys
    from friend_trial_process import launch_owned
    env=starter.child_environment(tmp_path/'profile',bind_host='127.0.0.1',tcp=9527,web=9529)
    proc=launch_owned([sys.executable,'-X','utf8','-B','-c',"print('owned synthetic child')"],cwd=str(tmp_path),env=env,log_path=tmp_path/'child.log')
    try:
        assert proc.wait(15)==0
        assert proc.terminate_tree() and proc.active_count()==0
    finally:proc.close()
    assert 'owned synthetic child' in (tmp_path/'child.log').read_text('utf-8')

def test_owned_job_child_is_on_requested_private_desktop(tmp_path):
    import sys,uuid
    from friend_trial_process import launch_owned
    desktop='FriendTrialJob-'+uuid.uuid4().hex
    script="import ctypes;from ctypes import wintypes;k=ctypes.WinDLL('kernel32');u=ctypes.WinDLL('user32');u.GetThreadDesktop.restype=wintypes.HANDLE;u.GetUserObjectInformationW.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p];h=u.GetThreadDesktop(k.GetCurrentThreadId());b=ctypes.create_unicode_buffer(1024);assert u.GetUserObjectInformationW(h,2,b,ctypes.sizeof(b),None);print(b.value)"
    env=starter.child_environment(tmp_path/'profile',bind_host='127.0.0.1',tcp=9527,web=9529)
    proc=launch_owned([sys.executable,'-X','utf8','-B','-c',script],cwd=str(tmp_path),env=env,log_path=tmp_path/'desktop.log',desktop_name=desktop)
    try:
        assert proc.wait(15)==0
        assert proc.terminate_tree()
    finally:proc.close()
    assert (tmp_path/'desktop.log').read_text('utf-8').strip()==desktop

def test_windows_owner_death_kills_its_children_but_preserves_other_job(tmp_path):
    import subprocess
    import sys
    import time
    from friend_trial_process import launch_owned
    from test_sandbox import process_state
    marker=tmp_path/'owned-pids.json'
    environment=starter.child_environment(tmp_path/'profile',bind_host='127.0.0.1',tcp=9527,web=9529)
    grandchild="import time;time.sleep(120)"
    child="import json,os,subprocess,sys,time;from pathlib import Path;p=subprocess.Popen([sys.executable,'-B','-c',"+repr(grandchild)+"],creationflags=0x08000000);Path("+repr(str(marker))+ ").write_text(json.dumps([os.getpid(),p.pid]));time.sleep(120)"
    source=str(Path(starter.__file__).parent)
    parent="import sys,time;from pathlib import Path;sys.path.insert(0,"+repr(source)+");from friend_trial_process import launch_owned;p=launch_owned([sys.executable,'-B','-c',"+repr(child)+"],cwd="+repr(str(tmp_path))+",env=dict(__import__('os').environ),log_path=Path("+repr(str(tmp_path/'tree.log'))+"));time.sleep(120)"
    sentinel=launch_owned([sys.executable,'-B','-c',grandchild],cwd=str(tmp_path),env=environment,log_path=tmp_path/'sentinel.log')
    owner=subprocess.Popen([sys.executable,'-X','utf8','-B','-c',parent],cwd=str(tmp_path),env=environment,creationflags=0x08000200,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    pids=[]
    try:
        deadline=time.monotonic()+15
        while not marker.exists() and time.monotonic()<deadline:
            assert owner.poll() is None
            time.sleep(0.05)
        assert marker.exists()
        pids=json.loads(marker.read_text())
        assert all(process_state(p)=='running' for p in pids)
        owner.terminate() # Terminate this exact synthetic parent only, no /T.
        owner.wait(10)
        deadline=time.monotonic()+10
        while any(process_state(p)!='exited' for p in pids) and time.monotonic()<deadline:time.sleep(0.05)
        assert all(process_state(p)=='exited' for p in pids)
        assert sentinel.poll() is None
    finally:
        if owner.poll() is None:owner.terminate();owner.wait(10)
        assert sentinel.terminate_tree()
        sentinel.close()
