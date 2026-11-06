"""Exact 400x300 strokes, tool state, prompt privacy and native guessing."""
import os
from pathlib import Path
import tkinter as tk
from types import SimpleNamespace

import client_gameui as cu
from boardgames import arcade_drawguess as table
from games_pkg.drawguess import DrawGuessGame
from test_arcade_halloween import Canvas


def setup(g,me=7):
    return {'game':'drawguess','me':me,'connected':True,'room':{'room_id':'art','round':1,'status':'playing','players':[7,8],'spectators':[9]},'_room_context':('art',1),'state':g.snapshot(),'submit':lambda a:None,'repaint':lambda:None}


def paint(cv,ui,priv=None,w=480,h=360):
    cu.render(cv,'drawguess',ui['state'],ui['me'],lambda u:f'合成{u}',ui['submit'],ui['repaint'],ui,priv,w,h)


def select(ui,kind,value=None):
    r=next(r for r in ui['atelier_hits'] if r[-2]==kind and (value is None or r[-1]==value))
    cu.handle_click(ui,(r[0]+r[2])/2,(r[1]+r[3])/2)


def test_tools_map_to_true_stroke_and_ignore_toolbar_drag():
    g=DrawGuessGame([7,8],seed=2);ui=setup(g);sent=[];ui['submit']=sent.append;paint(Canvas(),ui,g.private(7))
    select(ui,'color',table.COLORS[1]);select(ui,'width',10)
    ox,oy,scale=ui['dg_map'];cu.handle_drag(None,ui,ox,oy,'down');cu.handle_drag(None,ui,ox+200*scale,oy+100*scale,'move');cu.handle_drag(None,ui,0,0,'up')
    assert sent==[{'stroke':{'type':'line','x1':0,'y1':0,'x2':200,'y2':100,'color':table.COLORS[1],'width':10}}]
    cu.handle_drag(None,ui,0,359,'down');cu.handle_drag(None,ui,ox,oy,'move');assert len(sent)==1
    select(ui,'clear');assert sent[-1]=={'clear':True}


def test_prompt_hidden_from_guesser_spectator_and_stale_callback():
    g=DrawGuessGame([7,8],seed=1)
    for uid in [8,9]:
        ui=setup(g,uid);cv=Canvas();paint(cv,ui,{'word':'PRIVATE_SENTINEL'})
        assert not any('PRIVATE_SENTINEL' in str(k.get('text','')) for _,_,k in cv.calls)
        assert not table.can_draw(ui['state'],ui)
    ui=setup(g,8);sent=[];ui['submit']=sent.append;old=ui['state'];ui['_room_context']=('other',2)
    table.send_guess(ui,old,('art',1),SimpleNamespace(get=lambda:'秘密',delete=lambda *a:None))
    assert not sent


def test_old_coordinate_and_guess_dialogs_removed():
    import client,web
    assert client._actions_for('drawguess',None)==[]
    assert client.GameWindow._fmt_state(SimpleNamespace(),DrawGuessGame([7,8]).snapshot())==''
    page=web._SERVED_PAGE().decode('utf-8')
    assert '@@ARCADE_ATELIER' not in page and 'drawguess(box,s){AtelierTable.render(box,s);}' in page


def test_real_canvas_brush_clear_and_native_guess_return():
    from arcade_capture import capture
    g=DrawGuessGame([7,8],seed=3);ui=setup(g);sent=[];out=Path(os.environ.get('ARCADE_EVIDENCE_DIR','_tmp_gui/arcade-evidence'))
    root=tk.Tk();root.geometry('820x590+0+0');cv=tk.Canvas(root,highlightthickness=0);cv.pack(fill='both',expand=True)
    def redraw():ui['state']=g.snapshot();paint(cv,ui,g.private(ui['me']),cv.winfo_width(),cv.winfo_height());root.update()
    def submit(a):sent.append(a);g.act(ui['me'],a);redraw()
    ui['submit']=submit;ui['repaint']=redraw
    cv.bind('<Button-1>',lambda e:(cu.handle_click(ui,e.x,e.y),cu.handle_drag(cv,ui,e.x,e.y,'down')))
    cv.bind('<B1-Motion>',lambda e:cu.handle_drag(cv,ui,e.x,e.y,'move'))
    cv.bind('<ButtonRelease-1>',lambda e:cu.handle_drag(cv,ui,e.x,e.y,'up'))
    def click(kind,value=None):
        r=next(r for r in ui['atelier_hits'] if r[-2]==kind and (value is None or r[-1]==value));cv.event_generate('<Button-1>',x=int((r[0]+r[2])/2),y=int((r[1]+r[3])/2));root.update()
    try:
        root.update();redraw();capture(root,out/'drawguess-tk-start.png')
        click('color',table.COLORS[4]);click('width',10)
        ox,oy,scale=ui['dg_map']
        cv.event_generate('<Button-1>',x=int(ox+30*scale),y=int(oy+30*scale))
        cv.event_generate('<B1-Motion>',x=int(ox+250*scale),y=int(oy+150*scale));cv.event_generate('<ButtonRelease-1>',x=int(ox+250*scale),y=int(oy+150*scale));root.update()
        assert g.strokes and g.strokes[-1]['color']==table.COLORS[4] and g.strokes[-1]['width']==10
        redraw();capture(root,out/'drawguess-tk-decision.png')
        root.geometry('480x360');root.update();redraw();capture(root,out/'drawguess-tk-small.png')
        click('clear');assert not g.strokes
        ui['me']=8;redraw();entry=cv._atelier_entry;entry.insert(0,g.word);entry.focus_force();root.update();entry.event_generate('<Return>');root.update()
        assert g.guessed_by==8 and g.phase=='round_end';capture(root,out/'drawguess-tk-ended.png')
    finally:root.destroy()
