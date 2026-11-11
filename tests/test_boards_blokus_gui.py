"""Real GameWindow and compact focus window, isolated private desktop only."""
import ctypes
import os
import json
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from PIL import ImageGrab
import client
import client_gameui as cu
from games_pkg.blokus import BlokusGame
from games_pkg.rooms import RoomManager
from test_flagship_gui import _fake_game_core


def test_real_two_seat_polyomino_rotation_placement_and_pass_finish():
    assert os.environ.get("MOYU_GATE_DESKTOP_NAME")
    root=tk.Tk();root.withdraw();core=_fake_game_core("blokus")
    manager=RoomManager({"blokus":BlokusGame});room=manager.create(7,"blokus");manager.join(8,room.room_id);manager.start(7,room.room_id)
    game=room.gs;core.game_room=room.summary();core.game_state=game.snapshot();core.game_meta["blokus"]["label"]="角斗士棋"
    app=SimpleNamespace(root=root,core=core,_dp=client._DEFAULT_PAL,_frameless=False,_skin={},_camo_title=lambda:"合成拼筑工坊")
    folder=Path(os.environ["MOYU_GATE_PROFILE"])/"boards-evidence";folder.mkdir(parents=True,exist_ok=True)
    actions=[];window=None;errors=[]
    root.report_callback_exception=lambda *details:errors.append(str(details))
    try:
        window=client.GameWindow(app,pal=client._DEFAULT_PAL)
        def send(room_id,action):
            actions.append(dict(uid=core.uid,action=action));manager.handle_action(core.uid,room_id,action)
            core.game_state=game.snapshot();window._sync();return True
        core.game_action=send;window._sync();root.update();window._spawn_board_win();focus=window._board_win
        focus.win.geometry("480x400+10+10");root.update();focus.redraw(force=True);root.update()
        hwnd=ctypes.windll.user32.GetAncestor(focus.win.winfo_id(),2)
        def shot(name):
            root.update();ImageGrab.grab(window=hwnd).save(folder/name)
        def click(rect):
            focus.game_cv.event_generate("<Button-1>",x=int((rect[0]+rect[2])/2),y=int((rect[1]+rect[3])/2));root.update()
        def pick(name):
            for _ in range(21):
                ui=focus._cv_ui
                found=next((r for r in ui["blok_chips"] if r[4]==name),None)
                if found: click(found);return
                click(ui["blok_page_next"])
            raise AssertionError(name)
        def place(row,col):
            ui=focus._cv_ui;x=ui["ox"]+(col+.5)*ui["cell"];y=ui["oy"]+(row+.5)*ui["cell"]
            focus.game_cv.event_generate("<Motion>",x=int(x),y=int(y));root.update()
            focus.game_cv.event_generate("<Button-1>",x=int(x),y=int(y));root.update()
        assert window.act_btns.winfo_children()==[]
        shot("blokus-tk-before.png");pick("M");place(19,0);assert game.board[(19,0)]==7
        core.uid=8;window._sync();focus.redraw(force=True);root.update();pick("M");place(0,19);assert game.board[(0,19)]==8
        core.uid=7;window._sync();focus.redraw(force=True);root.update();pick("D")
        focus.game_cv.focus_force();root.update();focus.game_cv.event_generate("<KeyPress-r>");root.update()
        assert focus._cv_ui["blok_oi"]==1
        focus.game_cv.event_generate("<KeyPress-r>");root.update();assert focus._cv_ui["blok_oi"]==0
        ui=focus._cv_ui;focus.game_cv.event_generate("<Motion>",x=int(ui["ox"]+1.5*ui["cell"]),y=int(ui["oy"]+17.5*ui["cell"]));root.update()
        shot("blokus-tk-decision.png");place(17,1);assert game.board[(17,1)]==game.board[(18,1)]==7
        shot("blokus-tk-landed.png")
        core.uid=8;window._sync();focus.redraw(force=True);root.update();click(focus._cv_ui["blok_pass"])
        core.uid=7;window._sync();focus.redraw(force=True);root.update();click(focus._cv_ui["blok_pass"]);assert game.winner==7
        shot("blokus-tk-finished.png");assert focus._cv_ui["blok_chips"]==[]
        assert len(focus.game_cv.find_withtag("card-illustration"))==2
        assert not errors
        (folder/"blokus-tk-actions.json").write_text(json.dumps(dict(actions=actions,state=game.snapshot(),private_desktop=os.environ["MOYU_GATE_DESKTOP_NAME"]),ensure_ascii=False,indent=2),encoding="utf-8")
    finally:
        if window: window.close()
        root.destroy()
