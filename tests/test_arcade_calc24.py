"""Value-card identity, expression editing and exact Fraction rule submission."""
from pathlib import Path
from types import SimpleNamespace
import os
import tkinter as tk

import client_gameui as cu
from boardgames import arcade_calc24 as table
from games_pkg.calc24 import Calc24Game
from test_arcade_halloween import Canvas


def setup(g,me=7):
    return {'game':'calc24','me':me,'connected':True,'state':g.snapshot(),'_room_context':('math',1),'room':{'status':'playing','players':[7,8],'spectators':[9]},'submit':lambda a:None,'repaint':lambda:None}


def paint(cv,ui,w=480,h=400):
    cu.render(cv,'calc24',ui['state'],ui['me'],lambda u:f'合成{u}',ui['submit'],ui['repaint'],ui,None,w,h)


def pick(ui,kind,value=None):
    r=next(r for r in ui['calc_hits'] if r[-2]==kind and (value is None or r[-1]==value));cu.handle_click(ui,(r[0]+r[2])/2,(r[1]+r[3])/2)


def test_equal_values_keep_clicked_card_identity_and_undo_releases_it():
    g=Calc24Game([7,8],seed=1);g.cards=[3,3,8,8];ui=setup(g)
    ui['repaint']=lambda:paint(Canvas(),ui)
    paint(Canvas(),ui);pick(ui,'card',1)
    assert table.used(g.cards,ui['calc_expr'],ui['calc_picked'])=={1}
    assert 0 in [r[-1] for r in ui['calc_hits'] if r[-2]=='card']
    pick(ui,'token','⌫');assert not table.used(g.cards,ui['calc_expr'],ui['calc_picked'])


def test_cards_and_operator_chips_build_actual_solution_without_number_input():
    g=Calc24Game([7,8],seed=1);g.cards=[1,2,3,4];ui=setup(g);sent=[]
    ui['submit']=sent.append;ui['repaint']=lambda:paint(Canvas(),ui);paint(Canvas(),ui)
    for kind,value in [('token','('),('card',0),('token','+'),('card',1),('token','+'),('card',2),('token',')'),('token','*'),('card',3)]:pick(ui,kind,value)
    pick(ui,'send');assert sent==[{'expr':'(1+2+3)*4'}];g.act(7,sent[0]);assert g.scores[7]==1


def test_spectator_disconnect_and_old_submission_callbacks_do_not_send():
    g=Calc24Game([7,8],seed=1);ui=setup(g);sent=[];ui['submit']=sent.append;paint(Canvas(),ui)
    old=ui['state'];ui['calc_expr']='(1+2+3)*4';ui['_room_context']=('different',2);table.send(ui,old,('math',1));assert not sent
    for change in ({'me':9},{'connected':False},{'state':dict(old,status='revealed')}):
        other=dict(ui,**change);paint(Canvas(),other);assert not other['calc_hits']


def test_legacy_answer_dialog_removed_and_production_page_uses_math_cards():
    import client,web
    assert client._actions_for('calc24',None)==[]
    assert client.GameWindow._fmt_state(SimpleNamespace(),Calc24Game([7,8]).snapshot())==''
    page=web._SERVED_PAGE().decode('utf-8');assert '@@ARCADE_MATH' not in page and 'calc24(box,s){MathTable.render(box,s);}' in page


def test_real_cards_chips_seal_and_keyboard_fraction_expression():
    from arcade_capture import capture
    g=Calc24Game([7,8],seed=3);g.cards=[1,2,3,4];ui=setup(g);sent=[]
    out=Path(os.environ.get('ARCADE_EVIDENCE_DIR','_tmp_gui/arcade-evidence'))
    root=tk.Tk();root.geometry('480x400+0+0');cv=tk.Canvas(root,highlightthickness=0);cv.pack(fill='both',expand=True)
    def redraw():ui['state']=g.snapshot();paint(cv,ui,cv.winfo_width(),cv.winfo_height());root.update()
    def submit(a):sent.append(a);g.act(7,a);redraw()
    ui['submit']=submit;ui['repaint']=redraw
    cv.bind('<Button-1>',lambda e:cu.handle_click(ui,e.x,e.y))
    def event(kind,value=None):
        r=next(r for r in ui['calc_hits'] if r[-2]==kind and (value is None or r[-1]==value));cv.event_generate('<Button-1>',x=int((r[0]+r[2])/2),y=int((r[1]+r[3])/2));root.update()
    try:
        root.update();redraw();capture(root,out/'calc24-tk-start.png')
        for kind,value in [('token','('),('card',0),('token','+'),('card',1),('token','+'),('card',2),('token',')'),('token','*'),('card',3)]:event(kind,value)
        capture(root,out/'calc24-tk-decision.png');event('send');assert g.phase=='revealed';capture(root,out/'calc24-tk-revealed.png')
        g._next_round();g.cards=[3,3,8,8];redraw();entry=cv._calc24_entry;entry.insert(0,'8/(3-8/3)');entry.focus_force();root.update();entry.event_generate('<Return>');root.update()
        assert g.scores[7]==2 and g.phase=='revealed'
        g.round_no=5;g.tick(g.reveal_end_at+1);redraw();assert g.phase=='ended';capture(root,out/'calc24-tk-ended.png')
    finally:root.destroy()
