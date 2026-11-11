"""Eleven actual value images, readable numeric layer and three input paths."""
from pathlib import Path
from types import SimpleNamespace
import os
import tkinter as tk

import client_gameui as cu
from boardgames.tile2048 import desktop as table
from games_pkg.tile2048 import Tile2048Game


def setup(g,me=7):
    return {'game':'tile2048','me':me,'connected':True,'_room_context':('star',1),'state':g.snapshot(),'room':{'game':'tile2048','room_id':'star','round':1,'status':'playing','players':[7],'spectators':[8]},'submit':lambda a:None,'repaint':lambda:None}


def paint(cv,ui,w=480,h=400):
    cu.render(cv,'tile2048',ui['state'],ui['me'],str,ui['submit'],ui['repaint'],ui,None,w,h)


def test_sprite_indices_match_exact_powers_and_numeric_fallback():
    assert table._ATLAS_VALUES==tuple(2**n for n in range(1,12))
    from PIL import Image
    with Image.open(table._ATLAS_PATH) as im:
        assert im.width*3==im.height*4
        assert len({im.crop((i%4*im.width//4,i//4*im.height//3,(i%4+1)*im.width//4,(i//4+1)*im.height//3)).tobytes() for i in range(11)})==11
    assert table._tile_color(4096) and table._font_size(2048,60)>=10


def test_spectator_disconnect_and_terminal_block_swipe():
    g=Tile2048Game([7],seed=1)
    for change in ({'me':8},{'connected':False},{'state':dict(g.snapshot(),status='won')}):
        ui=dict(setup(g),**change);sent=[];ui['submit']=sent.append;ui['tile2048_board']=(0,0,200,200)
        table.drag(None,ui,10,10,'down');table.drag(None,ui,150,10,'up');assert not sent


def test_legacy_direction_row_and_raw_matrix_removed():
    import client
    assert client._actions_for('tile2048',None)==[]
    assert client.GameWindow._fmt_state(SimpleNamespace(),Tile2048Game([7]).snapshot())==''


def test_real_tile_images_compass_swipe_keyboard_and_winning_number_layer():
    from arcade_capture import capture
    import client
    from test_flagship_gui import _fake_game_core
    g=Tile2048Game([7],seed=2);ui=setup(g);sent=[];out=Path(os.environ.get('ARCADE_EVIDENCE_DIR','_tmp_gui/arcade-evidence'))
    root=tk.Tk();root.geometry('480x400+0+0');cv=tk.Canvas(root,highlightthickness=0);cv.pack(fill='both',expand=True)
    def redraw():ui['state']=g.snapshot();paint(cv,ui,cv.winfo_width(),cv.winfo_height());root.update()
    def submit(a):sent.append(a);g.act(7,a);redraw()
    ui['submit']=submit;ui['repaint']=redraw
    cv.bind('<Button-1>',lambda e:(cu.handle_click(ui,e.x,e.y),cu.handle_drag(cv,ui,e.x,e.y,'down')))
    cv.bind('<ButtonRelease-1>',lambda e:cu.handle_drag(cv,ui,e.x,e.y,'up'))
    def compass(direction):
        r=next(r for r in ui['tile2048_hits'] if r[-1]==direction);cv.event_generate('<Button-1>',x=int((r[0]+r[2])/2),y=int((r[1]+r[3])/2));root.update()
    gw=None
    try:
        root.update();redraw();capture(root,out/'tile2048-tk-start.png')
        g.board=[[2,2,4,8],[16,32,64,128],[256,512,1024,0],[0,0,0,0]];redraw();compass('left');assert g.score==4 and g.board[0][:3]==[4,4,8]
        assert set(ui['tile2048_image_cache']['tiles'])==set(table._ATLAS_VALUES)
        capture(root,out/'tile2048-tk-decision.png')
        x0,y0,x1,y1=ui['tile2048_board'];cv.event_generate('<Button-1>',x=int((x0+x1)/2),y=int(y0+30));cv.event_generate('<ButtonRelease-1>',x=int((x0+x1)/2),y=int(y1-30));root.update();assert sent[-1]=={'op':'move','dir':'down'}
        root.geometry('480x360');root.update();redraw();capture(root,out/'tile2048-tk-small.png')
        g.board=[[1024,1024,0,0]]+[[0]*4 for _ in range(3)];g.score=0;redraw();compass('left');assert g.status=='won' and g.score==2048
        labels=[cv.itemcget(i,'text') for i in cv.find_all() if cv.type(i)=='text'];assert '2048' in labels
        assert not ui['tile2048_hits'];capture(root,out/'tile2048-tk-ended.png')
        # Existing ordinary host bindings are still the keyboard path.
        g=Tile2048Game([7],seed=2);g.board=[[2,2,0,0]]+[[0]*4 for _ in range(3)]
        core=_fake_game_core('tile2048');core.game_room['players']=[7];core.game_state=g.snapshot();core.game_private=None
        def core_action(rid,a):g.act(7,a);core.game_state=g.snapshot();return True
        core.game_action=core_action
        gw=client.GameWindow(SimpleNamespace(root=root,core=core,_frameless=False,_camo_title=lambda:'合成2048星阶'),pal=client._DEFAULT_PAL)
        gw.win.geometry('950x720');gw.win.deiconify();root.update();gw._sync();gw._render_canvas();root.update()
        assert not gw.act_btns.winfo_children();gw.game_cv.focus_force();root.update();gw.game_cv.event_generate('<Left>');root.update();assert g.score==4
    finally:
        if gw:gw.close()
        root.destroy()
