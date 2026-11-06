"""Normal two-column hall must repaint to its own viewport while focus is open."""
import ctypes
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from PIL import ImageGrab
import client
import client_gameui as cu
from games_pkg.ludo import LudoGame
from test_flagship_gui import _fake_game_core


def test_normal_ludo_hall_resize_keeps_all_airports_and_real_clicks(monkeypatch):
    assert os.environ.get("MOYU_GATE_DESKTOP_NAME")
    folder=Path(os.environ["MOYU_GATE_PROFILE"])/"boards-evidence";folder.mkdir(parents=True,exist_ok=True)
    root=tk.Tk();root.withdraw();core=_fake_game_core("ludo");game=LudoGame([7,8,9,10],seed=19)
    core.game_room["players"]=game.players;core.game_state=game.snapshot()
    core.game_meta["ludo"].update(label="飞行棋",max=4)
    app=SimpleNamespace(root=root,core=core,_dp=client._DEFAULT_PAL,_frameless=False,_skin={},_camo_title=lambda:"合成普通大厅")
    rendered=[];real=cu.render;window=None;actions=[]
    def record(cv,*args):
        rendered.append(dict(canvas=cv,width=args[-2],height=args[-1],state=args[1]));return real(cv,*args)
    monkeypatch.setattr(cu,"render",record)
    try:
        window=client.GameWindow(app,pal=client._DEFAULT_PAL)
        def send(rid,action):
            actions.append(dict(room=rid,action=action));game.act(7,action)
            core.game_state=game.snapshot();window._sync();return True
        core.game_action=send
        window.win.geometry("1200x760+10+10");window._sync();root.update();root.update()
        window._spawn_board_win();root.update()
        window.win.geometry("860x600+10+10");root.update();root.update()
        latest=next(r for r in reversed(rendered) if r["canvas"] is window.game_cv)
        metrics=dict(window=[window.win.winfo_width(),window.win.winfo_height()],
                     canvas=[window.game_cv.winfo_width(),window.game_cv.winfo_height()],
                     last_paint=[latest["width"],latest["height"]],focus_open=window._board_win.active())
        hwnd=ctypes.windll.user32.GetAncestor(window.win.winfo_id(),2)
        ImageGrab.grab(window=hwnd).save(folder/"ludo-normal-hall-resized-focus-open.png")
        (folder/"ludo-normal-hall-metrics.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8")
        assert metrics["last_paint"]==metrics["canvas"],metrics
        assert window.game_cv.winfo_rootx()+window.game_cv.winfo_width() <= window.win.winfo_rootx()+window.win.winfo_width()
        window._board_win.hide();root.update();window._render_canvas(force=True);root.update()
        ImageGrab.grab(window=hwnd).save(folder/"ludo-normal-hall-before.png")
        def click(action):
            rect=next(r for r in window._cv_ui["ludo_hits"] if r[-1]==action)
            assert rect[2] <= window.game_cv.winfo_width() and rect[3] <= window.game_cv.winfo_height()
            window.game_cv.event_generate("<Button-1>",x=int((rect[0]+rect[2])/2),y=int((rect[1]+rect[3])/2));root.update()
        click({"op":"roll"});assert game.dice==6
        ImageGrab.grab(window=hwnd).save(folder/"ludo-normal-hall-six.png")
        click({"op":"move","idx":0});assert game.miles[7][0]==0
        ImageGrab.grab(window=hwnd).save(folder/"ludo-normal-hall-launch.png")
        metrics["actions"]=actions;metrics["all_aircraft_visible"]=True
        (folder/"ludo-normal-hall-metrics.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8")
    finally:
        if window: window.close()
        root.destroy()
