"""The native click-then-drag event order submits one real Azul move."""
from types import SimpleNamespace

import client
import client_gameui as cu
from boardgames.azul import desktop as az
from test_azul_drag import Probe, _state, _ui


def _paint(monkeypatch):
    monkeypatch.setattr(cu, "_banner_icon", lambda *args, **kwargs: None)
    sent=[];state=_state();canvas=Probe();ui=_ui(state,sent,canvas)
    ui['_room_context']=('az-1',1)
    ui['room'].update(room_id='az-1',round=1,game='azul',players=[7,8])
    ui['repaint']();return state,canvas,ui,sent


def _point(rect):
    return (rect[0]+rect[2])/2,(rect[1]+rect[3])/2


def _press(canvas,ui,point):
    # This is the exact GameWindow._on_cv_click order.
    cu.handle_click(ui,*point);cu.handle_drag(canvas,ui,*point,'down')


def test_click_source_release_then_click_row_is_exactly_one_pair(monkeypatch):
    state,canvas,ui,sent=_paint(monkeypatch)
    source=next(h for h in ui['azul_src'] if h[-2:]==(0,'r'))
    _press(canvas,ui,_point(source));cu.handle_drag(canvas,ui,*_point(source),'up')
    assert not sent and ui['azul_pick']['col']=='r'
    dest=next(h for h in ui['azul_dst'] if h[-1]==3)
    _press(canvas,ui,_point(dest));cu.handle_drag(canvas,ui,*_point(dest),'up')
    assert sent==[{'op':'take','src':0,'col':'r'},{'op':'place','row':3}]
    _press(canvas,ui,_point(dest));cu.handle_drag(canvas,ui,*_point(dest),'up')
    assert len(sent)==2


def test_real_click_down_motion_up_drag_is_exactly_one_pair(monkeypatch):
    state,canvas,ui,sent=_paint(monkeypatch)
    source=next(h for h in ui['azul_src'] if h[-2:]==('center','k'))
    dest=next(h for h in ui['azul_dst'] if h[-1]==-1)
    _press(canvas,ui,_point(source));cu.handle_drag(canvas,ui,*_point(dest),'move')
    assert not sent
    cu.handle_drag(canvas,ui,*_point(dest),'up');cu.handle_drag(canvas,ui,*_point(dest),'up')
    assert sent==[{'op':'take','src':'center','col':'k'},{'op':'floor'}]


def test_selected_tile_and_drag_are_rejected_after_room_or_snapshot_changes(monkeypatch):
    for changed in ('room','snapshot'):
        state,canvas,ui,sent=_paint(monkeypatch)
        source=next(h for h in ui['azul_src'] if h[-2:]==(0,'r'))
        dest=next(h for h in ui['azul_dst'] if h[-1]==3)
        _press(canvas,ui,_point(source))
        if changed=='room':ui['_room_context']=('az-2',1)
        else:ui['state']=dict(state)
        cu.handle_drag(canvas,ui,*_point(dest),'up')
        cu.handle_click(ui,*_point(dest))
        assert not sent and 'azul_pick' not in ui


def test_click_full_or_wrong_color_row_never_sends_take(monkeypatch):
    state,canvas,ui,sent=_paint(monkeypatch)
    source=next(h for h in ui['azul_src'] if h[-2:]==(0,'b'))
    _press(canvas,ui,_point(source));cu.handle_drag(canvas,ui,*_point(source),'up')
    # Row 1 is already full of blue. The selection stays local.
    dest=next(h for h in ui['azul_dst'] if h[-1]==1)
    _press(canvas,ui,_point(dest));cu.handle_drag(canvas,ui,*_point(dest),'up')
    assert not sent


def test_first_marker_draws_once_in_center_or_on_owner(monkeypatch):
    state,canvas,ui,sent=_paint(monkeypatch)
    for owner in (None,7,8):
        canvas.calls.clear();state['marker_uid']=owner;ui['repaint']()
        markers=[kw for name,args,kw in canvas.calls if name=='create_oval' and kw.get('tags')=='azul-first-marker']
        assert len(markers)==1
        if owner==7:
            assert any('含先手筹' in str(kw.get('text','')) for name,args,kw in canvas.calls)


def test_final_native_guard_rejects_old_room_state_game_or_account():
    for mismatch in ('room','state','game','source_game','account'):
        st=_state();room={'room_id':'az-1','round':1,'game':'azul','status':'playing','players':[7,8]}
        sent=[];core=SimpleNamespace(uid=7,connected=True,game_room=room,game_state=st,
                                     game_action=lambda *args:sent.append(args))
        ui={'game':'azul','_room_context':('az-1',1),'state':st,'me':7}
        if mismatch=='room':ui['_room_context']=('old-room',1)
        elif mismatch=='state':ui['state']=dict(st)
        elif mismatch=='game':room['game']='lovelove'
        elif mismatch=='source_game':ui['game']='gomoku'
        else:ui['me']=8
        client.GameWindow._do_action(SimpleNamespace(core=core),{'op':'take','src':0,'col':'r'},ui)
        assert not sent


def test_take_ack_between_pair_calls_can_finish_only_its_matching_place():
    st=_state();room={'room_id':'az-1','round':1,'game':'azul','status':'playing','players':[7,8]}
    sent=[];core=SimpleNamespace(uid=7,connected=True,game_room=room,game_state=st)
    ui={'game':'azul','_room_context':('az-1',1),'state':st,'me':7}
    follow={'op':'place','row':3};pair=az._pair(ui,{'src':0,'col':'r'},follow);ui['_azul_pair']=pair
    def action(rid,payload):
        sent.append(payload)
        if payload['op']=='take':core.game_state={**st,'pending':['r','r']}
        return True
    core.game_action=action;host=SimpleNamespace(core=core)
    client.GameWindow._do_action(host,pair['take'],ui)
    assert pair['accepted'] and core.game_state is not st
    client.GameWindow._do_action(host,{'op':'floor'},ui)
    assert len(sent)==1
    client.GameWindow._do_action(host,follow,ui)
    assert sent==[pair['take'],follow]
    ui.pop('_azul_pair')
    client.GameWindow._do_action(host,follow,ui)
    assert len(sent)==2


def test_graphic_keyboard_uses_same_objects_and_no_legacy_action_row(monkeypatch):
    state,canvas,ui,sent=_paint(monkeypatch)
    assert client._actions_for('azul',None)==[]
    assert az.key(ui,'Right')=='break'
    pick=dict(ui['azul_pick']);assert not sent
    az.key(ui,'Down');row=ui['azul_key_row'];assert not sent
    az.key(ui,'Return')
    assert sent==[{'op':'take','src':pick['src'],'col':pick['col']},
                  {'op':'floor'} if row<0 else {'op':'place','row':row}]
    state,canvas,ui,sent=_paint(monkeypatch)
    az.key(ui,'Right');az.key(ui,'Down');az.key(ui,'Escape');az.key(ui,'Return')
    assert not sent and 'azul_pick' not in ui


def test_mouse_selecting_another_tile_clears_the_previous_keyboard_target(monkeypatch):
    state,canvas,ui,sent=_paint(monkeypatch)
    az.key(ui,'Right');az.key(ui,'Down');assert 'azul_key_row' in ui
    source=next(h for h in ui['azul_src'] if h[-2:]==('center','k'))
    _press(canvas,ui,_point(source));cu.handle_drag(canvas,ui,*_point(source),'up')
    az.key(ui,'Return')
    assert not sent and 'azul_key_row' not in ui


def test_full_floor_keeps_marker_ownership_without_inventing_an_eighth_slot(monkeypatch):
    state,canvas,ui,sent=_paint(monkeypatch)
    state.update(marker_uid=7,floor={'7':7,'8':0},floor_tiles={'7':['r']*7,'8':[]})
    canvas.calls.clear();ui['repaint']()
    labels=[str(kw.get('text','')) for name,args,kw in canvas.calls if name=='create_text']
    assert any('地板 7 · 先手筹'==label for label in labels)
    assert not any('含先手筹' in label for label in labels)
