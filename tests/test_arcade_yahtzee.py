"""Dice position, three-roll limit, score ownership and real tabletop clicks."""
import os
from pathlib import Path
import tkinter as tk
from types import SimpleNamespace

import pytest
import client_gameui as gameui
from boardgames import arcade_yahtzee as table
from games_pkg.yahtzee import YahtzeeGame, CATS, _cat_score
from games_pkg.base import GameRuleError
from test_arcade_halloween import Canvas


def ui_for(g,me=7):
    return {"game":"yahtzee","state":g.snapshot(),"room":{"status":"playing","players":[7,8],"spectators":[9]},"connected":True,"me":me,"submit":lambda a:None,"repaint":lambda:None}


def paint(cv,ui,w=480,h=360):
    gameui.render(cv,'yahtzee',ui['state'],ui['me'],lambda u:f'合成{u}',ui['submit'],ui['repaint'],ui,None,w,h)


def pick(ui,kind,value=None):
    r=next(r for r in ui['yacht_hits'] if r[-2]==kind and (value is None or r[-1]==value))
    gameui.handle_click(ui,(r[0]+r[2])/2,(r[1]+r[3])/2)


def test_roll_limit_and_kept_dice_remain_in_exact_positions():
    g=YahtzeeGame([7,8],seed=17);g.act(7,{'op':'roll'})
    with pytest.raises(GameRuleError):g.act(7,{'op':'roll'})
    before=g.dice[:]
    g.act(7,{'op':'reroll','keep':[1,4]})
    assert g.dice[1]==before[1] and g.dice[4]==before[4]
    g.act(7,{'op':'reroll','keep':[1,4]})
    assert g.dice[1]==before[1] and g.dice[4]==before[4]
    with pytest.raises(GameRuleError):g.act(7,{'op':'reroll','keep':[]})
    assert g.snapshot()['preview']=={c:_cat_score(c,g.dice) for c in CATS}


@pytest.mark.parametrize('me,connected,room_status',[(8,True,'playing'),(9,True,'playing'),(7,False,'playing'),(7,True,'ended')])
def test_only_active_owner_can_write_or_roll(me,connected,room_status):
    g=YahtzeeGame([7,8],seed=1);g.act(7,{'op':'roll'});ui=ui_for(g,me);ui['connected']=connected;ui['room']['status']=room_status
    sent=[];ui['submit']=sent.append;paint(Canvas(),ui)
    assert all(r[-2]=='owner' for r in ui['yacht_hits'])
    for x,y in [(450,150),(100,280)]:gameui.handle_click(ui,x,y)
    assert not sent


def test_scorebook_previews_owned_cells_and_small_hit_bounds():
    g=YahtzeeGame([7,8],seed=3);g.act(7,{'op':'roll'});g.dice=[2,2,2,3,3]
    ui=ui_for(g);sent=[];ui['submit']=sent.append
    paint(Canvas(),ui,320,300)
    assert len([r for r in ui['yacht_hits'] if r[-2]=='score'])==13
    assert all(0<=a<c<=320 and 0<=b<d<=300 for a,b,c,d,*_ in ui['yacht_hits'])
    pick(ui,'owner',8);paint(Canvas(),ui,320,300)
    assert not [r for r in ui['yacht_hits'] if r[-2]=='score']
    pick(ui,'owner',7);paint(Canvas(),ui,320,300);pick(ui,'score','house')
    g.act(7,sent.pop());assert g.scores[7]['house']==25


def test_legacy_numeric_controls_are_removed():
    import client,web
    assert client._actions_for('yahtzee',None)==[]
    assert client.GameWindow._fmt_state(SimpleNamespace(),YahtzeeGame([7,8]).snapshot())==''
    page=web._SERVED_PAGE().decode('utf-8')
    assert '@@ARCADE_YACHT' not in page and 'yahtzee(box,s){YachtTable.render(box,s);}' in page
    assert 'placeholder:"保留位如 0 1 2"' not in page


def test_real_dice_tray_mouse_and_normal_game_window():
    from arcade_capture import capture
    import client
    from test_flagship_gui import _fake_game_core
    out=Path(os.environ.get('ARCADE_EVIDENCE_DIR','_tmp_gui/arcade-evidence'))
    root=tk.Tk();root.geometry('820x590+0+0');cv=tk.Canvas(root,highlightthickness=0);cv.pack(fill='both',expand=True)
    g=YahtzeeGame([7,8],seed=23);ui=ui_for(g);sent=[]
    def redraw():ui['state']=g.snapshot();paint(cv,ui,cv.winfo_width(),cv.winfo_height());root.update()
    def submit(a):sent.append(a);g.act(7,a);redraw()
    ui['submit']=submit;ui['repaint']=redraw
    cv.bind('<Button-1>',lambda e:gameui.handle_click(ui,e.x,e.y))
    def event(kind,value=None):
        r=next(r for r in ui['yacht_hits'] if r[-2]==kind and (value is None or r[-1]==value))
        cv.event_generate('<Button-1>',x=int((r[0]+r[2])/2),y=int((r[1]+r[3])/2));root.update()
    gw=None
    try:
        root.update();redraw();capture(root,out/'yahtzee-tk-start.png')
        event('roll');before=g.dice[:];event('keep',1);event('keep',4);event('roll')
        assert g.dice[1]==before[1] and g.dice[4]==before[4]
        assert sent[-1]=={'op':'reroll','keep':[1,4]}
        capture(root,out/'yahtzee-tk-decision.png')
        root.geometry('480x400');root.update();redraw();capture(root,out/'yahtzee-tk-480-decision.png')
        root.geometry('480x360');root.update();redraw();capture(root,out/'yahtzee-tk-small.png')
        event('score','chance');assert g.scores[7]['chance'] is not None
        # Last blank field of the last player's scorebook: actual completion.
        g.turn=0;g.rolled=True;g.dice=[6]*5;g.scores={u:{c:0 for c in CATS} for u in [7,8]};g.scores[7]['yahtzee']=None;redraw();event('score','yahtzee')
        assert g.snapshot()['status']=='ended' and g.done==7
        capture(root,out/'yahtzee-tk-ended.png')
        # Exercise the ordinary entry and its submit path using a synthetic core.
        g=YahtzeeGame([7,8],seed=2);core=_fake_game_core('yahtzee');core.game_state=g.snapshot();core.game_private=None
        def core_action(rid,a):g.act(7,a);core.game_state=g.snapshot();return True
        core.game_action=core_action
        app=SimpleNamespace(root=root,core=core,_frameless=False,_camo_title=lambda:'合成快艇社团')
        gw=client.GameWindow(app,pal=client._DEFAULT_PAL);gw.win.geometry('950x720');gw.win.deiconify();root.update();gw._sync();gw._render_canvas();root.update()
        assert not gw.act_btns.winfo_children()
        r=next(r for r in gw._cv_ui['yacht_hits'] if r[-2]=='roll')
        gw.game_cv.event_generate('<Button-1>',x=int((r[0]+r[2])/2),y=int((r[1]+r[3])/2));root.update()
        assert g.rolled
        gw._sync();gw._render_canvas();root.update();capture(gw.win,out/'yahtzee-tk-normal-window.png')
    finally:
        if gw:gw.close()
        root.destroy()
