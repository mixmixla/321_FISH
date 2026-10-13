"""Independent exact-client-method probes; no Tk root, network, prefs or gate."""
import ast,copy,hashlib,json,sys,types
from pathlib import Path
from types import MethodType,SimpleNamespace
src=Path('D:/Project/321_FISH/_tmp_gui/gate-collection-20261013')
sys.path.insert(0,str(src))
from games_pkg.kalah import KalahGame
from games_pkg.rummikub import RummikubGame
import client_gameui as ui_module
text=(src/'client.py').read_text(encoding='utf-8');before=hashlib.sha256((src/'client.py').read_bytes()).hexdigest()
tree=ast.parse(text);cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='GameWindow')
names={'_board_uis','_room_ctx','_submit_sel','_ask_params','_kalah_parameter_action','_kalah_can_submit',
       '_cur_game','_parse_action','_do_action','_fmt_state'}
methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names]
status=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_desktop_game_status')
ns={'_DESKTOP_UNSUPPORTED_GAMES':set(),'client_gameui':ui_module,'_KIND_INPUTS':{}}
exec(compile(ast.Module(body=[status]+methods,type_ignores=[]),str(src/'client.py'),'exec'),ns)
widgets=types.ModuleType('widgets');dialog=types.ModuleType('widgets.dialogbox')
dialog.show_message=lambda *a,**k:None;dialog.ask_string=lambda *a,**k:'1';widgets.dialogbox=dialog
sys.modules['widgets']=widgets;sys.modules['widgets.dialogbox']=dialog
results=[]
def make(uid=22):
    game=KalahGame([11,22],seed=1)
    if uid==22:game.act(11,{'hole':1})
    sent=[];hints=[]
    def send(rid,action):sent.append((rid,copy.deepcopy(action)));game.act(core.uid,action)
    core=SimpleNamespace(uid=uid,connected=True,game_state=game.snapshot(),
        game_room={'room_id':'r1','round':1,'game':'kalah','status':'playing','players':[11,22]},
        game_meta={'kalah':{'label':'播棋'}},game_action=send)
    host=SimpleNamespace(core=core,win=None,_sel_game='kalah',_cv_ui={},_board_win=None,
        act_hint=SimpleNamespace(config=lambda **k:hints.append(k)),
        _nick=lambda u:{11:'阿甲',22:'阿乙'}.get(u,'旁观者'))
    for name in names:setattr(host,name,MethodType(ns[name],host))
    return host,game,sent,hints
spec={'key':'hole','kind':'int'}
for uid in (11,22):
    for local in range(1,7):
        h,g,sent,_=make(uid);expected=copy.deepcopy(g);wire=local+(8 if uid==22 else 0)
        expected.act(uid,{'hole':wire});ns['_KIND_INPUTS']['int']=lambda *a,n=local:str(n)
        h._ask_params(spec,'本方1..6');assert sent==[('r1',{'hole':wire})]
        assert g.snapshot()==expected.snapshot();results.append(f'local-{uid}-{local}')
changes=('observer','turn','room-ended','draw','winner','empty','disconnected','not-seated','wrong-state')
def mutate(h,case):
    c=h.core
    if case=='observer':c.uid=99
    elif case=='turn':c.game_state['turn']=11
    elif case=='room-ended':c.game_room['status']='ended'
    elif case in ('draw','winner'):c.game_state.update(status='ended',winner_uid=22 if case=='winner' else None)
    elif case=='empty':c.game_state['cells']=list(c.game_state['cells']);c.game_state['cells'][8]=0
    elif case=='disconnected':c.connected=False
    elif case=='not-seated':c.game_room['players']=[11]
    else:c.game_state['game']='gemcity'
for phase in ('before','during'):
    for case in changes:
        h,g,sent,_=make()
        if phase=='before':mutate(h,case)
        def ask(*a,h=h,case=case,phase=phase):
            if phase=='during':mutate(h,case)
            return '1'
        ns['_KIND_INPUTS']['int']=ask;old=copy.deepcopy(g.cells);h._ask_params(spec,'本方1..6')
        assert not sent and g.cells==old;results.append(f'{phase}-{case}')
for key in ('room_id','round','game','uid','seats'):
    h,g,sent,hints=make()
    def ask(*a,key=key,h=h):
        if key in ('room_id','round','game'):h.core.game_room[key]={'room_id':'r2','round':2,'game':'gemcity'}[key]
        elif key=='uid':h.core.uid=11
        else:h.core.game_state=dict(h.core.game_state,p0=22,p1=11)
        return '1'
    ns['_KIND_INPUTS']['int']=ask;h._ask_params(spec,'本方1..6')
    assert not sent and hints[-1]['text']=='对局已变化，请重新操作';results.append(f'context-{key}')
for value in ('0','7','9','-1','abc',None):
    h,g,sent,_=make();ns['_KIND_INPUTS']['int']=lambda *a,v=value:v
    h._ask_params(spec,'本方1..6');assert not sent;results.append(f'invalid-local-{value}')
for change in (None,'room','round','game','snapshot','uid','turn','draw','empty'):
    h,g,sent,_=make();u={'game':'kalah','me':22,'state':h.core.game_state,'_room_context':('r1',1)}
    if change=='room':h.core.game_room['room_id']='r2'
    elif change=='round':h.core.game_room['round']=2
    elif change=='game':h.core.game_room['game']='gemcity'
    elif change=='snapshot':h.core.game_state=copy.deepcopy(h.core.game_state)
    elif change=='uid':h.core.uid=11
    elif change in ('turn','draw','empty'):mutate(h,change)
    h._do_action({'hole':9},u)
    assert bool(sent)==(change is None);results.append(f'wire-context-{change}')
for value in (-1,0,7,8,15,'9',None):
    h,g,sent,_=make();h._do_action({'hole':value});assert not sent;results.append(f'invalid-wire-{value}')
for uid in (11,22,99):
    h,g,sent,_=make(uid);st={'game':'kalah','p0':11,'p1':22,'turn':22,'cells':list(range(14)),'status':'playing'}
    lines=h._fmt_state(st).splitlines()
    assert '阿乙' in lines[0] and '13 12 11 10 9 8' in lines[0] and '库 7' in lines[0]
    assert '阿甲' in lines[1] and '0 1 2 3 4 5' in lines[1] and '库 6' in lines[1]
    assert ('（你）' in lines[0])==(uid==22) and ('（你）' in lines[1])==(uid==11)
    results.append(f'summary-{uid}')
for recent in ('lobby','focus'):
    lobby={'game':'rummikub','sel':{},'cards':[(0,0,30,30,42)],'repaint':lambda:None}
    focus=copy.copy(lobby);focus['sel']={}
    chosen,other=(lobby,focus) if recent=='lobby' else (focus,lobby)
    other['sel']['rmk']=[18,20,22];ui_module.handle_click(chosen,10,10);ui_module.handle_click(chosen,10,10)
    sent=[];h=SimpleNamespace(_cv_ui=lobby,_last_board_ui=chosen,
       _board_win=SimpleNamespace(_cv_ui=focus,active=lambda:True),
       act_hint=SimpleNamespace(config=lambda **k:None),_do_action=lambda *a:sent.append(a[0]))
    h._board_uis=MethodType(ns['_board_uis'],h);ns['_submit_sel'](h,{'op':'meld','sel_key':'rmk'})
    assert not sent and other['sel']['rmk']==[18,20,22];results.append(f'rummikub-cancel-{recent}')
for last,active,expected in (('lobby',True,'lobby'),('focus',True,'focus'),(None,True,'focus'),(None,False,'lobby')):
    lobby={'sel':{}};focus={'sel':{}};chosen={'lobby':lobby,'focus':focus}[expected];chosen['sel']['rmk']=[18,20,22]
    sent=[];h=SimpleNamespace(_cv_ui=lobby,_last_board_ui={'lobby':lobby,'focus':focus}.get(last),
       _board_win=SimpleNamespace(_cv_ui=focus,active=lambda:active),
       act_hint=SimpleNamespace(config=lambda **k:None),_do_action=lambda *a:sent.append(a[0]))
    h._board_uis=MethodType(ns['_board_uis'],h);ns['_submit_sel'](h,{'op':'meld','sel_key':'rmk'})
    assert sent==[{'op':'meld','tiles':[18,20,22]}];results.append(f'rummikub-default-{last}-{active}')
h,g,sent,_=make();assert h._parse_action('guess','int','99')=={'guess':99};results.append('other-int')
after=hashlib.sha256((src/'client.py').read_bytes()).hexdigest();assert before==after
proof={'client_sha256':before,'source_unchanged_during_probe':True,'cases_passed':len(results),'cases':results,
       'scope':'exact client.py methods only; no Tk root, network, gate or review of own UI/PAGE implementation'}
Path('D:/Project/321_FISH/_tmp_gui/controller-review-20261013/probe.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in proof.items() if k!='cases'},ensure_ascii=False))