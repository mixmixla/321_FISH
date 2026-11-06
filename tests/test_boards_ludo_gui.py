"""Actual Tk clicks on a private desktop, with two seats sharing real rules."""
import ctypes
import json
import os
from pathlib import Path
import tkinter as tk

import client_gameui as cu
from games_pkg.ludo import LudoGame


def test_private_two_seat_launch_move_keyboard_and_compact_screens(tmp_path):
    assert os.environ.get("MOYU_GATE_DESKTOP_NAME"), "Use run.py test-all for the private desktop"
    root = tk.Tk()
    root.title("合成飞行棋 · 私有测试桌面")
    root.geometry("720x650+10+10")
    game = LudoGame([1, 2, 3, 4], seed=19)
    evidence = Path(os.environ["MOYU_GATE_PROFILE"]) / "boards-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    actions, panels = [], []
    errors = []
    root.report_callback_exception = lambda *args: errors.append(str(args))
    try:
        for uid in (1, 2, 99):
            window = root if uid == 1 else tk.Toplevel(root)
            if uid != 1:
                window.geometry("480x400+750+10")
            cv = tk.Canvas(window, highlightthickness=0)
            cv.pack(fill="both", expand=True)
            ui = dict(game="ludo", me=uid, connected=True, _room_context=("synthetic", 1),
                      room=dict(status="playing", players=game.players))
            panels.append((uid, window, cv, ui))
        def paint():
            for uid, window, cv, ui in panels:
                ui["state"] = game.snapshot()
                ui["submit"] = lambda action, player=uid: act(player, action)
                cu.render(cv, "ludo", ui["state"], uid, lambda u: f"合成{u}", ui["submit"],
                          paint, ui, None, cv.winfo_width(), cv.winfo_height())
        def act(uid, action):
            actions.append(dict(uid=uid, action=action))
            game.act(uid, action)
            paint()
        for uid, window, cv, ui in panels:
            cv.bind("<Button-1>", lambda e, target=ui: cu.handle_click(target, e.x, e.y))
        root.update()
        paint()
        root.update()
        def shot(which, filename):
            from PIL import ImageGrab
            uid, window, cv, ui = panels[which]
            root.update_idletasks()
            hwnd = ctypes.windll.user32.GetAncestor(window.winfo_id(), 2)
            image = ImageGrab.grab(window=hwnd)
            image.save(evidence / filename)
            assert len(image.getcolors(image.width*image.height) or []) > 100
        def click(action):
            cv, ui = panels[0][2:]
            rect = next(r for r in ui["ludo_hits"] if r[-1] == action)
            cv.event_generate("<Button-1>", x=int((rect[0]+rect[2])/2), y=int((rect[1]+rect[3])/2))
            root.update()
        shot(0, "ludo-tk-before.png")
        click({"op": "roll"})
        assert game.dice == 6
        shot(0, "ludo-tk-six.png")
        click({"op": "move", "idx": 0})
        assert game.miles[1][0] == 0
        cv = panels[0][2]
        cv.focus_force()  # Local to this process's private desktop.
        root.update()
        cv.event_generate("<KeyPress-r>")
        root.update()
        assert game.dice == 1
        cv.event_generate("<KeyPress-1>")
        root.update()
        assert game.miles[1][0] == 1 and game.snapshot()["turn_uid"] == 2
        first_hand = game.snapshot()
        shot(0, "ludo-tk-moved.png")
        shot(1, "ludo-tk-opponent.png")
        shot(2, "ludo-tk-spectator.png")
        assert panels[2][3]["ludo_hits"] == []
        root.geometry("480x360+10+10")
        root.update()
        paint()
        root.update()
        shot(0, "ludo-tk-compact.png")
        assert len(panels[0][2].find_withtag("card-illustration")) == 5
        # Explicit near-finish synthetic fixture, completed by an actual click.
        game = LudoGame([1, 2, 3, 4], seed=19)
        game.miles[1] = [39, 40, 40, 40]
        game.dice, game.need_roll = 1, False
        paint()
        root.update()
        shot(0, "ludo-tk-finish-decision.png")
        click({"op": "move", "idx": 0})
        assert game.winner == 1 and game.miles[1] == [40, 40, 40, 40]
        shot(0, "ludo-tk-finished.png")
        assert all(not ui["ludo_hits"] for _, _, _, ui in panels)
        assert not errors
        (evidence / "ludo-tk-actions.json").write_text(json.dumps(dict(
            actions=actions, first_hand=first_hand, final=game.snapshot(), keyboard=True,
            terminal_fixture="separate synthetic near-finish state; final click uses real rules",
            private_desktop=os.environ["MOYU_GATE_DESKTOP_NAME"], errors=errors), ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        root.destroy()


def test_actual_gamewindow_and_focus_window_remove_parameter_buttons():
    assert os.environ.get("MOYU_GATE_DESKTOP_NAME")
    from types import SimpleNamespace
    import client
    from test_flagship_gui import _fake_game_core
    from PIL import ImageGrab
    root = tk.Tk()
    root.withdraw()
    core = _fake_game_core("ludo")
    game = LudoGame([7, 8, 9, 10], seed=19)
    core.game_room["players"] = game.players
    core.game_state = game.snapshot()
    core.game_meta["ludo"]["label"] = "飞行棋"
    app = SimpleNamespace(root=root, core=core, _dp=client._DEFAULT_PAL,
                          _frameless=False, _skin={}, _camo_title=lambda: "合成飞行棋")
    evidence = Path(os.environ["MOYU_GATE_PROFILE"]) / "boards-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    window = None
    try:
        window = client.GameWindow(app, pal=client._DEFAULT_PAL)
        def action(room_id, move):
            game.act(7, move)
            core.game_state = game.snapshot()
            window._sync()
            return True
        core.game_action = action
        window._sync()
        root.update()
        assert not any("走机" in child.cget("text") or child.cget("text") == "掷骰"
                       for child in window.act_btns.winfo_children())
        window._spawn_board_win()
        focus = window._board_win
        focus.win.geometry("480x400+10+10")
        root.update()
        focus.redraw(force=True)
        root.update()
        def click(move):
            rect = next(r for r in focus._cv_ui["ludo_hits"] if r[-1] == move)
            focus.game_cv.event_generate("<Button-1>", x=int((rect[0]+rect[2])/2), y=int((rect[1]+rect[3])/2))
            root.update()
        hwnd = ctypes.windll.user32.GetAncestor(focus.win.winfo_id(), 2)
        ImageGrab.grab(window=hwnd).save(evidence / "ludo-real-focus-before.png")
        click({"op": "roll"})
        assert game.dice == 6
        hwnd = ctypes.windll.user32.GetAncestor(focus.win.winfo_id(), 2)
        ImageGrab.grab(window=hwnd).save(evidence / "ludo-real-focus-six.png")
        click({"op": "move", "idx": 0})
        assert game.miles[7][0] == 0
        ImageGrab.grab(window=hwnd).save(evidence / "ludo-real-focus-launch.png")
        click({"op": "roll"})
        assert game.dice == 1
        ImageGrab.grab(window=hwnd).save(evidence / "ludo-real-focus-decision.png")
        click({"op": "move", "idx": 0})
        assert game.miles[7][0] == 1
        ImageGrab.grab(window=hwnd).save(evidence / "ludo-real-focus-landed.png")
        window.win.geometry("640x480+10+10")
        root.update()
        hwnd = ctypes.windll.user32.GetAncestor(window.win.winfo_id(), 2)
        ImageGrab.grab(window=hwnd).save(evidence / "ludo-real-gamewindow.png")
    finally:
        if window:
            window.close()
        root.destroy()
