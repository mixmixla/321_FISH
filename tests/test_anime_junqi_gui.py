"""Formal desktop window and tactical move/mine/capture/flag on private desktop."""
import ctypes
import json
import os
from pathlib import Path
import tkinter as tk
from types import SimpleNamespace


def test_formal_junqi_counter_mouse_keyboard_and_read_only():
    assert os.environ.get('MOYU_GATE_DESKTOP_NAME')
    import client
    from test_flagship_gui import _fake_game_core
    from games_pkg.junqi import JunqiGame
    from PIL import ImageGrab
    root=tk.Tk();root.withdraw();window=None
    core=_fake_game_core('junqi');game=JunqiGame([7,8],seed=3)
    core.game_state=game.snapshot();core.game_private={'legal':game.legal_moves(7)}
    core.game_meta['junqi']['label']='军棋'
    app=SimpleNamespace(root=root,core=core,_dp=client._DEFAULT_PAL,_frameless=False,_skin={},_camo_title=lambda:'合成军棋')
    output=Path(os.environ['MOYU_GATE_PROFILE'])/'junqi-evidence';output.mkdir(parents=True)
    actions=[];errors=[];root.report_callback_exception=lambda *args:errors.append(str(args))
    try:
        window=client.GameWindow(app,pal=client._DEFAULT_PAL)
        def sync():
            core.game_state=game.snapshot();core.game_private={'legal':game.legal_moves(core.uid)};window._sync();root.update()
            if getattr(window,'_board_win',None):window._board_win.redraw(force=True);root.update()
        def action(rid,move):
            game.act(core.uid,move);actions.append({'uid':core.uid,'action':move,'after':game.snapshot()});sync();return True
        core.game_action=action;sync()
        assert not any(c.cget('text')=='走子' for c in window.act_btns.winfo_children())
        window._spawn_board_win();focus=window._board_win;focus.win.geometry('480x400+10+10');sync()
        def shot(name):
            root.update();hwnd=ctypes.windll.user32.GetAncestor(focus.win.winfo_id(),2);ImageGrab.grab(window=hwnd).save(output/(name+'.png'))
        def click(x,y):
            u=focus._cv_ui;focus.game_cv.event_generate('<Button-1>',x=round(u['ox']+(x+.5)*u['junqi_cw']),y=round(u['oy']+(y+.5)*u['cell']));root.update()
        assert len(focus.game_cv.find_withtag('junqi-character'))==50
        shot('formal-initial-480')
        m=game.legal_moves(7)[0];click(*m['from']);assert focus.game_cv.find_withtag('junqi-legal');shot('formal-decision-480');click(*m['to']);assert actions
        shot('formal-moved-480')
        # Separate synthetic tactics: engineer clears a mine; opponent eats a platoon.
        game=JunqiGame([7,8],seed=3);game.board=[[0]*5 for _ in range(10)]
        game.board[4][0]=13;game.board[5][0]=41;game.board[6][4]=51;game.board[5][4]=14
        core.uid=7;sync();click(0,4);click(0,5);assert game.last_event['kind']=='mine_clear'
        core.uid=8;sync();click(4,6);click(4,5);assert game.last_event['kind']=='eat';shot('formal-captures-480')
        core.uid=99;sync();n=len(actions);click(4,5);click(4,4);assert len(actions)==n;shot('formal-spectator-480')
        game=JunqiGame([7,8],seed=3);game.board=[[0]*5 for _ in range(10)];game.board[4][0]=13;game.board[5][0]=40
        core.uid=7;sync();click(0,4)
        focus._cv_ui['junqi_cursor']=[0,4];focus.game_cv.focus_force();root.update()
        focus.game_cv.event_generate('<Down>');focus.game_cv.event_generate('<Return>');root.update()
        assert game.winner==7;shot('formal-finished-480')
        assert not errors,errors
        (output/'formal-actions.json').write_text(json.dumps({'actions':actions,'keyboard':True,'private_desktop':os.environ['MOYU_GATE_DESKTOP_NAME'],'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        if window:window.close()
        root.destroy()
