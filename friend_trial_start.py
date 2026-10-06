"""Portable friend-trial entry: fresh profiles, exact children, no shell/config edits."""
from __future__ import annotations
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys
import time
import uuid

from friend_trial_process import launch_owned as launch_process

PRIVATE_NETS=tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
FLAGS={'MOYU_DISCOVERY':'0','MOYU_TRAY':'0','MOYU_GLOBAL_HOTKEYS':'0','MOYU_HARDWARE':'0','MOYU_WEB_HTTPS':'0'}

def permitted_address(value: str, *, lan: bool) -> str:
    address=ipaddress.ip_address(value)
    if address.version!=4 or (not address.is_loopback and not any(address in n for n in PRIVATE_NETS)):
        raise ValueError('只接受本机或可信局域网的 IPv4 地址；不支持公网、域名或通配监听。')
    if lan and address.is_loopback:
        raise ValueError('局域网模式需要明确的局域网 IPv4 地址。')
    return str(address)

def valid_port(value: int) -> int:
    if not isinstance(value,int) or isinstance(value,bool) or not 1024<=value<=65535:
        raise ValueError('端口需在1024至65535之间。')
    return value

def reject_reparse(path: Path, root: Path) -> None:
    assert path.absolute().is_relative_to(root.absolute())
    current=path
    while True:
        if current.exists() or current.is_symlink():
            if current.is_symlink() or current.is_junction() or getattr(current.stat(),'st_file_attributes',0)&0x400:
                raise ValueError('试用目录包含链接或重解析点，已拒绝启动。')
        if current.absolute()==root.absolute():return
        current=current.parent

def executable(bundle: Path, name: str) -> Path:
    path=bundle/'dist'/name
    reject_reparse(path,bundle)
    if not path.is_file() or path.stat().st_size==0:
        raise ValueError(f'缺少 {name}，请先解压完整试用包。')
    return path

def child_environment(profile: Path, *, bind_host: str, tcp: int, web: int) -> dict[str,str]:
    profile=profile.absolute()
    system=os.environ.get('SystemRoot','C:\\Windows')
    env={'SystemRoot':system,'WINDIR':system,'SystemDrive':Path(system).drive or 'C:',
         'ComSpec':str(Path(system)/'System32/cmd.exe'),'PATH':str(Path(system)/'System32')+';'+system,
         'PATHEXT':'.COM;.EXE;.BAT;.CMD','OS':'Windows_NT',
         'PROCESSOR_ARCHITECTURE':os.environ.get('PROCESSOR_ARCHITECTURE','AMD64'),
         'NUMBER_OF_PROCESSORS':os.environ.get('NUMBER_OF_PROCESSORS','1'),
         'USERNAME':'trial_'+hashlib.sha256(str(profile).encode()).hexdigest()[:20],
         'USERPROFILE':str(profile),'HOMEDRIVE':profile.drive,'HOMEPATH':str(profile)[len(profile.drive):],
         'APPDATA':str(profile/'AppData/Roaming'),'LOCALAPPDATA':str(profile/'AppData/Local'),
         'TEMP':str(profile/'Temp'),'TMP':str(profile/'Temp'),
         'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','PYTHONUNBUFFERED':'1',
         'MOYU_BIND_HOST':bind_host,'MOYU_TCP_PORT':str(valid_port(tcp)),
         'MOYU_WEB_PORT':str(valid_port(web)),**FLAGS}
    return env

def make_plan(bundle: Path, mode: str, address: str, port: int, web_port: int, nick: str='') -> dict:
    bundle=bundle.absolute()
    if mode not in ('demo','host','join'):raise ValueError('未知试用模式。')
    if mode=='demo':address='127.0.0.1'
    address=permitted_address(address,lan=mode!='demo')
    valid_port(port);valid_port(web_port)
    if mode!='join' and port==web_port:raise ValueError('聊天与网页端口必须不同。')
    client=executable(bundle,'client.exe')
    server=executable(bundle,'server.exe') if mode!='join' else None
    run=bundle/'trial_runs'/('trial-'+uuid.uuid4().hex)
    reject_reparse(run,bundle)
    if run.exists():raise ValueError('新试用目录已存在，已拒绝复用。')
    nick=nick.strip()
    if nick and (len(nick)>24 or any(ord(c)<32 for c in nick) or nick in ('管理员','admin')):
        raise ValueError('请使用24字以内的普通试用昵称。')
    roles=['alpha','beta'] if mode=='demo' else ['alpha']
    tag=run.name[-6:]
    profiles={role:str(run/role) for role in roles}
    nicks={role:(nick or 'trial_friend_'+tag) if role=='alpha' else 'trial_beta_'+tag for role in roles}
    if server:profiles['server']=str(run/'server')
    return {'mode':mode,'address':address,'tcp_port':port,'web_port':web_port,
            'bundle':str(bundle),'run_dir':str(run),'profiles':profiles,'nicks':nicks,
            'client_exe':str(client),'server_exe':str(server) if server else None,
            'fresh_only':True,'automatic_demo_ports':mode=='demo','network_settings_changed':False,
            'firewall_changes':False,'real_data_import':False,'features':['chat','gomoku','connect4'],
            'external_windows_and_real_lan_verified':False}

def create_profile(profile: Path,nick: str|None=None) -> None:
    profile.mkdir()
    for sub in ('AppData/Roaming','AppData/Local','Temp'):(profile/sub).mkdir(parents=True)
    if nick:
        prefdir=profile/'moeyu_helper'
        prefdir.mkdir()
        # This is generated fresh trial input, not a copy of user preferences.
        data={'trusted_nicks':[nick],'muted':['public'],'dnd':True,'ui_sound':False,'notify_sound':'off'}
        (prefdir/'prefs.json').write_text(json.dumps(data,ensure_ascii=False),'utf-8')

def free_port() -> int:
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]

def wait_server(proc,address:str,port:int,timeout:float=45.0) -> None:
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if proc.poll() is not None:raise RuntimeError('服务器退出，请查看本次试用日志。')
        try:
            with socket.create_connection((address,port),timeout=0.4):return
        except OSError:time.sleep(0.2)
    raise RuntimeError('服务器未在等待时间内就绪；未修改网络设置。')

def check_free_ports(address:str,ports:tuple[int,int]) -> None:
    for port in ports:
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            probe.bind((address,port))

def run_plan(plan:dict) -> int:
    bundle=Path(plan['bundle']);run=Path(plan['run_dir'])
    reject_reparse(run,bundle)
    run.parent.mkdir(exist_ok=True)
    run.mkdir()
    if plan['mode']=='demo':
        plan['tcp_port']=free_port();plan['web_port']=free_port()
        while plan['web_port']==plan['tcp_port']:plan['web_port']=free_port()
    owned=[];clients=[];cleanup=[]
    code=1
    def spawn(role,command,env):
        proc=launch_process(command,cwd=str(bundle),env=env,log_path=run/(role+'.log'))
        owned.append((role,proc))
        return proc
    try:
        for role,name in plan['profiles'].items():create_profile(Path(name),plan['nicks'].get(role))
        if plan['server_exe']:
            profile=Path(plan['profiles']['server'])
            env=child_environment(profile,bind_host=plan['address'],tcp=plan['tcp_port'],web=plan['web_port'])
            # Bind locally once before opening our fresh server to catch an
            # already occupied address/port; never attach to an old server.
            check_free_ports(plan['address'],(plan['tcp_port'],plan['web_port']))
            store=str(profile/'store')
            initializer=spawn('initialize',[plan['server_exe'],'initialize-new','--store-dir',store],env)
            if initializer.wait(timeout=90)!=0:raise RuntimeError('新试用服务器初始化失败。')
            server=spawn('server',[plan['server_exe'],'open','--store-dir',store],env)
            wait_server(server,plan['address'],plan['tcp_port'])
        for role,nick in plan['nicks'].items():
            env=child_environment(Path(plan['profiles'][role]),bind_host='127.0.0.1',tcp=plan['tcp_port'],web=plan['web_port'])
            proc=spawn(role,[plan['client_exe'],'--host',plan['address'],'--port',str(plan['tcp_port']),'--nick',nick],env)
            clients.append(proc)
        print('试用窗口已启动，请在窗口确认登录。资料只写入本次新目录：'+str(run),flush=True)
        if plan['mode']=='host':
            print(f"朋友可选择加入，输入 {plan['address']}，端口 {plan['tcp_port']}。仅用于可信局域网。",flush=True)
            print('结束服务器将断开本次连接；按回车结束，或保持本窗口打开。',flush=True)
            wait_host(server,clients)
        else:
            print('请通过客户端红色退出按钮结束；本窗口需保持打开。Ctrl+C可停止本次试用子进程。',flush=True)
            wait_clients(clients,server if plan['server_exe'] else None)
        code=0
    except KeyboardInterrupt:code=130
    except Exception as exc:
        print(str(exc)+'\n本次日志目录：'+str(run),flush=True)
    finally:
        for role,proc in reversed(owned):
            try:
                ok=bool(proc.terminate_tree())
            except Exception:ok=False
            try:proc.close()
            except Exception:ok=False
            cleanup.append({'role':role,'ok':ok})
        if not all(row['ok'] for row in cleanup):code=2
        (run/'session-summary.json').write_text(json.dumps({'plan':plan,'exit_code':code,'cleanup':cleanup,'cleanup_ok':all(r['ok'] for r in cleanup),'native_gui_acceptance':False},ensure_ascii=False,indent=2),'utf-8')
    return code

def console_key():
    import msvcrt
    return msvcrt.getwch() if msvcrt.kbhit() else None

def wait_host(server,clients):
    while True:
        if server.poll() is not None:
            raise RuntimeError('服务器意外停止，请查看本次 server.log。')
        if any(p.poll() not in (None,0) for p in clients):
            raise RuntimeError('客户端异常退出，请查看本次客户端日志。')
        key=console_key()
        if key=='\x03':raise KeyboardInterrupt
        if key in ('\r','\n'):return
        time.sleep(0.2)

def wait_clients(clients,server=None):
    while True:
        if server is not None and server.poll() is not None:
            raise RuntimeError('服务器意外停止，请查看本次 server.log。')
        codes=[p.poll() for p in clients]
        if any(c not in (None,0) for c in codes):
            raise RuntimeError('客户端异常退出，请查看本次客户端日志。')
        if all(c==0 for c in codes):return
        time.sleep(0.3)

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description='少量朋友受控试用入口；不修改防火墙或导入旧资料。')
    parser.add_argument('--mode',choices=('demo','host','join'))
    parser.add_argument('--host',default='')
    parser.add_argument('--port',type=int,default=9527)
    parser.add_argument('--web-port',type=int,default=9529)
    parser.add_argument('--nick',default='')
    parser.add_argument('--bundle-dir',type=Path)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv)
    bundle=args.bundle_dir or Path(sys.executable if getattr(sys,'frozen',False) else __file__).absolute().parent
    try:
        mode=args.mode
        if not mode:
            print('受控试用预览：非开发机Windows和物理LAN尚未验证。每次生成新资料，不读取旧记录。')
            print('1 本机双窗口体验  2 在可信局域网开房  3 加入朋友  0 退出')
            mode={'1':'demo','2':'host','3':'join'}.get(input('请选择 [1]：').strip() or '1')
            if mode is None:return 0
        address=args.host
        if mode!='demo' and not address:address=input('请输入明确的局域网 IPv4 地址：').strip()
        plan=make_plan(bundle,mode,address,args.port,args.web_port,args.nick)
        if args.dry_run:
            print(json.dumps(plan,ensure_ascii=True,sort_keys=True))
            return 0
        return run_plan(plan)
    except (ValueError,OSError) as exc:
        print(str(exc),flush=True)
        return 1

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    result=main()
    if not '--dry-run' in sys.argv and not '--mode' in sys.argv:
        try:input('按回车关闭本窗口。')
        except (EOFError,KeyboardInterrupt):pass
    raise SystemExit(result)
