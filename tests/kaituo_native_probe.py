"""Real Tk lobby/focus windows on a Windows private desktop with a synthetic core."""
import copy
import ctypes
import json
import random
import sys
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

from PIL import ImageGrab
import client
from kaituo_fixtures import setup_game, fund
from test_flagship_gui import _fake_game_core


def main():
    out = Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    game = setup_game((7,8))
    game.rng=random.Random(5)
    game.tiles[(0,0)]["num"] = 8
    game.act(7,{"op":"roll"})
    assert game.last_dice == [5,3]
    fund(game)
    root = tk.Tk();root.withdraw()
    core = _fake_game_core('kaituo')
    core.roster={7:{'nick':'港湾甲'},8:{'nick':'港湾乙'}}
    core.game_state=copy.deepcopy(game.snapshot())
    core.game_meta['kaituo']['label']='开拓'
    app=SimpleNamespace(root=root,core=core,_dp=client._DEFAULT_PAL,_frameless=False,_skin={},_camo_title=lambda:'合成棋桌')
    win=None; actions=[]
    try:
        win=client.GameWindow(app,pal=client._DEFAULT_PAL)
        def action(room_id, frame):
            payload={key:value for key,value in frame.items() if key!='_kt_request'}
            game.act(core.uid,payload)
            actions.append(payload)
            core.game_state=copy.deepcopy(game.snapshot())
            win._sync()
            return True
        core.game_action=action
        win.win.geometry('1240x750+0+0');win.show();win._sync();root.update()
        def press(window,target):
            hit=next(rect for rect,value in window._cv_ui['kt_hits'] if value==target)
            window.game_cv.event_generate('<Button-1>',x=round((hit[0]+hit[2])/2),y=round((hit[1]+hit[3])/2));root.update()
        def shot(window,name):
            root.update()
            handle=ctypes.windll.user32.GetAncestor(window.win.winfo_id(),2)
            ImageGrab.grab(window=handle).save(out/name)
        shot(win,'native-lobby.png')
        win._spawn_board_win();focus=win._board_win;focus.win.geometry('1024x740+0+0');root.update();focus.redraw()
        press(focus,('model','settle'))
        shot(focus,'native-wide-before-building.png')
        press(focus,('vertex',(0,4)))
        assert game.board[(0,4)]['owner']==7
        shot(focus,'native-wide-after-building.png')
        press(focus,('model','road'))
        press(focus,('edge',((0,0),(1,0))))
        assert game.roads[((0,0),(1,0))]==7
        assert game.res[7]['wood']==10 and game.res[7]['ore']==12
        press(focus,('give','wood'));press(focus,('want','ore'))
        shot(focus,'native-wide-trade-ready.png')
        win._render_to(win.game_cv,win._cv_ui)
        if any(target==('tab','harbour') for _,target in win._cv_ui['kt_hits']):
            press(win,('tab','harbour'))
        press(win,('give','wood'));press(win,('want','ore'))
        shot(win,'native-lobby-trade-ready.png')
        focus.win.geometry('480x400+0+0');root.update();focus.redraw()
        press(focus,('model','settle'))
        shot(focus,'native-480-map.png')
        assert len(focus._cv_ui['kt_hits'])>2
        press(focus,('tab','harbour'))
        shot(focus,'native-480-harbour.png')
        (out/'trade-ready-state.json').write_text(json.dumps(game.snapshot(),ensure_ascii=False,indent=2),encoding='utf-8')
        press(focus,('trade',None))
        assert game.res[7]['wood']==6 and game.res[7]['ore']==13
        focus.win.geometry('1024x740+0+0');root.update();focus.redraw()
        shot(focus,'native-wide-trade-complete.png')
        assert not win.act_btns.winfo_children()
        (out/'native-actions.json').write_text(json.dumps({'actions':actions,'sizes':[1240,1024,480],'final':game.snapshot()},ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        if win: win.close()
        root.destroy()

if __name__=='__main__':main()
