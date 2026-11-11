"""Number-card actions, interval exclusion and keyboard access."""
from pathlib import Path
from types import SimpleNamespace
import os
import tkinter as tk

import client_gameui as cu
from boardgames import arcade_numbers as table
from games_pkg.guess_number import GuessNumberGame
from test_arcade_halloween import Canvas


def setup(g,me=7):
    return {'game':'guess_number','me':me,'connected':True,'_room_context':('numbers',1),'state':g.snapshot(),'room':{'status':'playing','players':[7,8],'spectators':[9]},'submit':lambda a:None,'repaint':lambda:None}


def paint(cv,ui,w=480,h=400):
    cu.render(cv,'guess_number',ui['state'],ui['me'],lambda u:f'合成{u}',ui['submit'],ui['repaint'],ui,None,w,h)


def select(ui,kind,value):
    r=next(r for r in ui['number_hits'] if r[-2:]==(kind,value));cu.handle_click(ui,(r[0]+r[2])/2,(r[1]+r[3])/2)


def test_secret_card_then_interval_guesses_only_legal_numbers_are_clickable():
    g=GuessNumberGame([7,8],seed=1);ui=setup(g);sent=[];ui['submit']=sent.append;ui['repaint']=lambda:paint(Canvas(),ui)
    paint(Canvas(),ui);select(ui,'page',2);select(ui,'number',73);assert sent.pop()=={'secret':73}
    g.act(7,{'secret':73});assert g.snapshot()['secret'] is None
    for n,bounds in [(50,(51,100)),(90,(51,89))]:g.act(8,{'guess':n});assert (g.low,g.high)==bounds
    ui['me']=8;ui['state']=g.snapshot();paint(Canvas(),ui)
    assert all(g.low<=r[-1]<=g.high for r in ui['number_hits'] if r[-2]=='number')
    table.choose(ui,50);assert not sent
    table.choose(ui,73);g.act(8,sent.pop());assert g.scores[8]==1 and g.status=='round_end'


def test_spectator_and_non_owner_cannot_set_secret_or_bypass_board_gate():
    g=GuessNumberGame([7,8],seed=1)
    for me in [8,9]:
        ui=setup(g,me);sent=[];ui['submit']=sent.append;paint(Canvas(),ui);table.choose(ui,73)
        assert not sent and all(r[-2]=='page' for r in ui['number_hits'])
    ui=setup(g);ui['connected']=False;assert not table.allowed(g.snapshot(),ui,73)


def test_legacy_integer_dialogs_removed():
    import client,web
    assert client._actions_for('guess_number',None)==[]
    assert client.GameWindow._fmt_state(SimpleNamespace(),GuessNumberGame([7,8]).snapshot())==''
    page=web._SERVED_PAGE().decode('utf-8');assert '@@ARCADE_NUMBER' not in page and 'guess_number(box,s){NumberTable.render(box,s);}' in page


def test_real_number_board_clicks_and_arrow_enter():
    from arcade_capture import capture
    g=GuessNumberGame([7,8],seed=1);ui=setup(g);sent=[];out=Path(os.environ.get('ARCADE_EVIDENCE_DIR','_tmp_gui/arcade-evidence'))
    root=tk.Tk();root.geometry('480x400+0+0');cv=tk.Canvas(root,highlightthickness=0);cv.pack(fill='both',expand=True)
    def redraw():ui['state']=g.snapshot();paint(cv,ui,cv.winfo_width(),cv.winfo_height());root.update()
    def submit(a):sent.append(a);g.act(ui['me'],a);redraw()
    ui['submit']=submit;ui['repaint']=redraw;cv.bind('<Button-1>',lambda e:cu.handle_click(ui,e.x,e.y))
    def event(kind,value):
        r=next(r for r in ui['number_hits'] if r[-2:]==(kind,value));cv.event_generate('<Button-1>',x=int((r[0]+r[2])/2),y=int((r[1]+r[3])/2));root.update()
    try:
        root.update();redraw();capture(root,out/'guess-number-tk-start.png')
        event('page',2);event('number',73);assert g.secret==73 and g.snapshot()['secret'] is None
        ui['me']=8;redraw();event('page',1);event('number',50);event('page',3);event('number',90)
        assert (g.low,g.high)==(51,89);capture(root,out/'guess-number-tk-decision.png')
        root.geometry('480x360');root.update();redraw();capture(root,out/'guess-number-tk-small.png')
        ui['number_focus']=72;cv.focus_force();root.update();cv.event_generate('<Right>');root.update();cv.event_generate('<Return>');root.update()
        assert sent[-1]=={'guess':73} and g.scores[8]==1;capture(root,out/'guess-number-tk-ended.png')
    finally:root.destroy()
