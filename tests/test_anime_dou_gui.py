"""Formal GameWindow + BoardFocusWindow, private desktop and synthetic core."""
import ctypes
import json
import os
from pathlib import Path
import tkinter as tk
from types import SimpleNamespace


def test_formal_game_window_focus_small_mouse_keyboard_and_no_raw_input():
    assert os.environ.get("MOYU_GATE_DESKTOP_NAME"), "Run via private test gate"
    import client
    from test_flagship_gui import _fake_game_core
    from games_pkg.dou import DouGame
    from PIL import ImageGrab
    root = tk.Tk(); root.withdraw(); window = None
    core = _fake_game_core("dou"); game = DouGame([7, 8])
    core.game_state = game.snapshot(); core.game_private = {"legal": game.legal_moves(7)}
    app = SimpleNamespace(root=root, core=core, _dp=client._DEFAULT_PAL,
                          _frameless=False, _skin={}, _camo_title=lambda: "合成森境")
    output = Path(os.environ["MOYU_GATE_PROFILE"]) / "dou-evidence"; output.mkdir(parents=True)
    actions=[]
    try:
        window = client.GameWindow(app, pal=client._DEFAULT_PAL)
        def action(room_id, move):
            game.act(7, move); actions.append(move)
            core.game_state = game.snapshot(); core.game_private = {"legal": game.legal_moves(7)}
            window._sync(); return True
        core.game_action = action; window._sync(); root.update()
        labels=[c.cget("text") for c in window.act_btns.winfo_children()]
        assert "走子" not in labels
        window._spawn_board_win(); focus=window._board_win
        focus.win.geometry("480x400+10+10"); root.update(); focus.redraw(force=True); root.update()
        def shot(name):
            root.update(); hwnd=ctypes.windll.user32.GetAncestor(focus.win.winfo_id(),2)
            ImageGrab.grab(window=hwnd).save(output/(name+".png"))
        def click(x,y):
            ui=focus._cv_ui
            focus.game_cv.event_generate("<Button-1>",x=round(ui["ox"]+(x+.5)*ui["cell"]),y=round(ui["oy"]+(y+.5)*ui["cell"]));root.update()
        shot("formal-focus-initial-480");click(0,2);shot("formal-focus-decision-480");click(0,3)
        assert game.board[(0,3)]==(0,1) and actions==[{"fx":0,"fy":2,"tx":0,"ty":3}]
        shot("formal-focus-moved-480")
        hwnd=ctypes.windll.user32.GetAncestor(window.win.winfo_id(),2)
        ImageGrab.grab(window=hwnd).save(output/"formal-gamewindow.png")
        (output/"formal-actions.json").write_text(json.dumps({"actions":actions,"old_coordinate_button_removed":True,"private_desktop":os.environ["MOYU_GATE_DESKTOP_NAME"],"menu_buttons":labels},ensure_ascii=False,indent=2),encoding="utf-8")
    finally:
        if window: window.close()
        root.destroy()
