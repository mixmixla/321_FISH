# -*- coding: utf-8 -*-
"""Default real-Tk probe for the flagship canvas contract.

This test creates only its own synthetic canvases and pixels; it performs no
screen capture.  The formal per-file gate therefore runs it by default on its
private Windows desktop.  A machine without Tk still reports an environment
skip, which is distinct from a successful GUI verification.
"""

import tkinter as tk
import threading
from types import SimpleNamespace

import pytest

import client_gameui


def _state(game):
    if game == "gomoku":
        board = [[0] * 15 for _ in range(15)]
    else:
        board = [[0] * 7 for _ in range(6)]
    return {
        "game": game, "board": board, "players": [7, 8], "turn_uid": 7,
        "winner_uid": None, "draw": False, "last_move": None,
        **({"size": 15} if game == "gomoku" else {"rows": 6, "cols": 7}),
    }


def _descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def test_flagship_canvas_real_tk_click_and_private_feedback():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.geometry("820x680+40+40")
    root.deiconify()
    canvas_a = tk.Canvas(root, width=400, height=300, highlightthickness=0)
    canvas_b = tk.Canvas(root, width=400, height=300, highlightthickness=0)
    canvas_a.pack(side="left", fill="both", expand=True)
    canvas_b.pack(side="right", fill="both", expand=True)
    sent_a, sent_b, scheduled_a, scheduled_b = [], [], [], []
    try:
        root.update_idletasks()
        root.update()
        for cv, game, sent, scheduled, context in (
                (canvas_a, "gomoku", sent_a, scheduled_a, ("g", 1)),
                (canvas_b, "connect4", sent_b, scheduled_b, ("c", 1))):
            ui = {
                "game": game, "state": _state(game), "room": {
                    "room_id": context[0], "round": context[1],
                    "status": "playing", "players": [7, 8], "spectators": [],
                }, "me": 7, "can_move": True, "connected": True,
                "_room_context": context,
                "submit": sent.append,
                "_schedule_repaint": lambda delay, out=scheduled: out.append(delay),
            }
            client_gameui.render(
                cv, game, ui["state"], 7, lambda uid: f"P{uid}",
                sent.append, lambda: None, ui, None,
                cv.winfo_width(), cv.winfo_height())
            if game == "gomoku":
                client_gameui.handle_click(ui, ui["ox"], ui["oy"])
            else:
                client_gameui.handle_click(ui, ui["ox"] + 4, ui["oy"] - 4)
            assert sent

            # A final-state snapshot keeps the board and only schedules the
            # finite feedback callback; the two canvases own separate queues.
            ui["state"]["last_move"] = [0, 0]
            ui["state"]["winner_uid"] = 7
            client_gameui.render(
                cv, game, ui["state"], 7, lambda uid: f"P{uid}",
                sent.append, lambda: None, ui, None,
                cv.winfo_width(), cv.winfo_height())
            assert scheduled
        root.update()
        assert scheduled_a == [40] and scheduled_b == [40]
    finally:
        root.destroy()


def test_rps_match_results_render_real_tk():
    """F4：rps 有战报（matches/byes）时渲染对战结果可视化——胜负/平局/轮空
    三类行均绘制且不抛异常；空战报时不再出现「请见日志」占位。"""
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.geometry("760x600+40+40")
    root.deiconify()
    cv = tk.Canvas(root, width=560, height=460, highlightthickness=0)
    cv.pack(fill="both", expand=True)
    try:
        root.update_idletasks()
        root.update()
        st = {
            "game": "rps", "status": "collecting", "round": 3,
            "submitted": [7], "players": [7, 8, 9, 10, 11],
            "scores": {7: 1, 8: 1, 9: 0, 10: 0, 11: 0},
            "matches": [
                {"a": 7, "b": 8, "ca": 0, "cb": 1, "winner": 8},     # 胜负
                {"a": 9, "b": 10, "ca": 2, "cb": 2, "winner": -1},   # 平局
            ],
            "byes": [11],                                            # 轮空
        }
        ui = {"me": 7}
        client_gameui.render(
            cv, "rps", st, 7, lambda uid: f"P{uid}",
            lambda *a: None, lambda: None, ui, None,
            cv.winfo_width(), cv.winfo_height())
        root.update()
        texts = [str(cv.itemcget(it, "text")) for it in cv.find_all()
                 if cv.type(it) == "text"]
        blob = "\n".join(texts)
        assert "上轮战报" in blob                 # 结果面板出现
        assert "🏆" in blob and "（平）" in blob and "轮空" in blob
        assert "请见日志" not in blob             # 旧的占位文案已移除
    finally:
        root.destroy()


def _fake_game_core(game="gomoku"):
    size = 15 if game == "gomoku" else None
    board = ([[0] * 15 for _ in range(15)] if game == "gomoku"
             else [[0] * 7 for _ in range(6)])
    calls = []

    class Core:
        uid = 7
        connected = True
        game_meta = {
            game: {"label": game, "min": 2, "max": 2,
                   "desc": "synthetic", "rules": "synthetic rules"}
        }
        game_rooms = []
        game_private = None
        game_events = []
        roster = {}

        def __init__(self):
            self.game_room = {
                "room_id": "room-1", "round": 1, "game": game,
                "status": "playing", "players": [7, 8], "spectators": [],
            }
            self.game_state = {
                "game": game, "board": board, "players": [7, 8],
                "turn_uid": 7, "winner_uid": None, "draw": False,
                "last_move": None,
                **({"size": size} if game == "gomoku" else {"rows": 6, "cols": 7}),
            }

        def game_list(self):
            return True

        def game_action(self, rid, action):
            calls.append((rid, action))
            return True

    core = Core()
    core.calls = calls
    return core


def test_real_game_window_bindings_focus_gate_and_collapse_restore(monkeypatch):
    """Synthetic app/core, real GameWindow/BoardFocusWindow and Tk events."""
    import client as client_module

    clock = [100.0]
    monkeypatch.setattr(
        client_gameui, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.geometry("1100x760+40+40")
    root.deiconify()
    core = _fake_game_core("gomoku")
    app = SimpleNamespace(
        root=root, core=core, _dp=client_module._DEFAULT_PAL,
        _frameless=False, _skin={}, _camo_title=lambda: "synthetic",
    )
    gw = None
    try:
        gw = client_module.GameWindow(app, pal=client_module._DEFAULT_PAL)
        gw._sync()
        root.update_idletasks()
        assert gw.win.winfo_width() >= 640 and gw.win.winfo_height() >= 480

        # Real bound mouse event on the embedded board.
        root.update()
        ui = gw._cv_ui
        gw.game_cv.event_generate(
            "<Button-1>", x=int(ui["ox"]), y=int(ui["oy"]), when="tail")
        root.update()
        assert core.calls and core.calls[-1][1] == {"x": 0, "y": 0}

        # The action button uses the same latest-state gate.  Replace the
        # dialog provider only for this synthetic input, then trigger the
        # actual Tk Button invoke path.
        old_input = client_module._KIND_INPUTS["pos"]
        client_module._KIND_INPUTS["pos"] = lambda *_args: "1,1"
        try:
            button = next(w for w in gw.act_btns.winfo_children()
                          if w.cget("text") == "落子")
            button.invoke()
            after_invoke = len(core.calls)
            button.focus_force()
            root.update()
            button.event_generate("<KeyPress-Return>", when="tail")
            root.update()
        finally:
            client_module._KIND_INPUTS["pos"] = old_input
        assert len(core.calls) >= after_invoke + 1
        assert core.calls[-1][1] == {"x": 1, "y": 1}

        # The normal minimum layout remains usable after an explicit resize.
        gw.win.geometry("640x480+50+50")
        root.update_idletasks()
        assert gw.win.winfo_width() >= 640 and gw.win.winfo_height() >= 480

        # A separate focus window has its own canvas/UI and receives a real
        # event; both windows remain tied to the same synthetic core state.
        gw._spawn_board_win()
        board = gw._board_win
        root.update_idletasks()
        board.redraw(force=True)
        board.game_cv.event_generate(
            "<Button-1>", x=int(board._cv_ui["ox"]),
            y=int(board._cv_ui["oy"]), when="tail")
        root.update()
        assert board.active() and core.calls[-1][1] == {"x": 0, "y": 0}

        # Off-turn and spectator frames block both canvases without changing
        # the wire call list.
        before = len(core.calls)
        core.game_room = {**core.game_room, "round": 2, "spectators": [7]}
        core.game_state = {**core.game_state, "turn_uid": 7}
        gw._sync(); board.redraw(force=True); root.update()
        gw.game_cv.event_generate("<Button-1>", x=int(ui["ox"]),
                                  y=int(ui["oy"]), when="tail")
        board.game_cv.event_generate("<Button-1>", x=int(board._cv_ui["ox"]),
                                     y=int(board._cv_ui["oy"]), when="tail")
        root.update()
        assert len(core.calls) == before

        # A final frame remains read-only and keeps the board visible; the
        # next round changes context and cancels any queued feedback callback.
        core.game_room = {**core.game_room, "round": 3, "spectators": []}
        core.game_state = {**core.game_state, "winner_uid": 7,
                           "last_move": [0, 0]}
        clock[0] = 200.0
        gw._sync(); root.update_idletasks()
        assert board._cv_ui.get("_after_id") is not None
        board.hide(reason="collapse")
        assert board._cv_ui.get("_after_id") is None
        board.show(reason="collapse")
        board.redraw(force=True)
        clock[0] = 201.0
        expiry_job = board._cv_ui.get("_after_id")
        assert expiry_job is not None
        expiry_script = root.tk.call("after", "info", expiry_job)[0]
        root.tk.call("after", "cancel", expiry_job)
        root.tk.call(expiry_script)
        root.update_idletasks()
        assert board._cv_ui.get("_after_id") is None
        gw.game_cv.event_generate("<Button-1>", x=int(ui["ox"]),
                                  y=int(ui["oy"]), when="tail")
        root.update()
        assert len(core.calls) == before

        # A draw is also read-only, then a CREATED snapshot can restart with a
        # new round without creating a new window or preserving the old board.
        core.game_room = {**core.game_room, "round": 3, "status": "ended"}
        core.game_state = {**core.game_state, "winner_uid": None,
                           "draw": True}
        gw._sync(); board.redraw(force=True); root.update()
        board.game_cv.event_generate("<Button-1>", x=int(board._cv_ui["ox"]),
                                     y=int(board._cv_ui["oy"]), when="tail")
        root.update()
        assert len(core.calls) == before
        core.game_room = {**core.game_room, "round": 3, "status": "created"}
        core.game_state = None
        gw._sync(); root.update()
        core.game_room = {**core.game_room, "round": 4, "status": "playing"}
        core.game_state = {**_state("gomoku"), "turn_uid": 7}
        gw._sync(); board.redraw(force=True); root.update()
        assert board.active() and board._cv_ui["_room_context"] == ("room-1", 4)

        # Use the real MiniBar/BossWindow objects for nested mini→boss capture
        # and restore; this is intentionally a window-level test, not a direct
        # handler-only assertion.
        core.files = SimpleNamespace(_lock=threading.Lock(), xfers={})
        core.me = {}
        core.send_status = lambda _status: None
        mini_app = SimpleNamespace(
            root=root, core=core, _prefs=SimpleNamespace(get=lambda *_a, **_k: True),
            _unread={}, _boss_active=False,
        )
        mini = client_module.MiniBar(mini_app, pal=client_module._DEFAULT_PAL)
        boss = client_module.BossWindow(root, skin="excel")
        snapshot_host = SimpleNamespace(
            root=root, core=core, _game_win=gw, _mini=mini,
            _collapse_snapshot=None,
            _visible_window=client_module.ChatWindow._visible_window,
            _boss=boss,
            _boss_active=False,
            _append_sys=lambda *_a, **_k: None,
        )
        snapshot_host._capture_collapse_snapshot = (
            lambda: client_module.ChatWindow._capture_collapse_snapshot(snapshot_host))
        snapshot_host._restore_collapse_snapshot = (
            lambda: client_module.ChatWindow._restore_collapse_snapshot(snapshot_host))
        snapshot_host._boss_enter_silent = (
            lambda: client_module.ChatWindow._boss_enter_silent(snapshot_host))
        snapshot_host._boss_exit_silent = (
            lambda: client_module.ChatWindow._boss_exit_silent(snapshot_host))
        client_module.ChatWindow._capture_collapse_snapshot(snapshot_host)
        first_snapshot = snapshot_host._collapse_snapshot
        client_module.ChatWindow._capture_collapse_snapshot(snapshot_host)
        assert snapshot_host._collapse_snapshot is first_snapshot
        client_module.ChatWindow._toggle_boss(snapshot_host)
        root.update()
        assert root.state() == "withdrawn" and not client_module.ChatWindow._visible_window(gw.win)
        assert boss.visible() and mini.win.state() == "withdrawn"
        client_module.ChatWindow._toggle_boss(snapshot_host)
        root.update()
        assert client_module.ChatWindow._visible_window(gw.win)
        assert board.active()
        board.hide(reason="manual")
        snapshot_host._collapse_snapshot = None
        client_module.ChatWindow._capture_collapse_snapshot(snapshot_host)
        client_module.ChatWindow._toggle_boss(snapshot_host)
        client_module.ChatWindow._toggle_boss(snapshot_host)
        root.update()
        assert not board.active()
        boss.close()
        mini.win.destroy()
    finally:
        if gw is not None:
            gw.close()
        root.destroy()


def test_collapse_visibility_manual_hide_unsupported_guard_and_after_cleanup(monkeypatch):
    """Real Tk regressions for nested mini/boss and stale desktop game state."""
    import client as client_module

    clock = [100.0]
    monkeypatch.setattr(
        client_gameui, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.geometry("1100x760+60+60")
    root.deiconify()
    core = _fake_game_core("gomoku")
    core.files = SimpleNamespace(_lock=threading.Lock(), xfers={})
    core.me = {}
    core.send_status = lambda _status: None
    app = SimpleNamespace(
        root=root, core=core, _dp=client_module._DEFAULT_PAL,
        _frameless=False, _skin={}, _camo_title=lambda: "synthetic",
        _prefs=SimpleNamespace(get=lambda *_a, **_k: True),
        _unread={}, _boss_active=False,
    )
    gw = mini = boss = None
    try:
        gw = client_module.GameWindow(app, pal=client_module._DEFAULT_PAL)
        app._game_win = gw
        mini = client_module.MiniBar(app, pal=client_module._DEFAULT_PAL)
        boss = client_module.BossWindow(root, skin="excel")
        app._mini = mini
        app._boss = boss
        app._collapse_snapshot = None
        app._visible_window = client_module.ChatWindow._visible_window
        app._capture_collapse_snapshot = (
            lambda: client_module.ChatWindow._capture_collapse_snapshot(app))
        app._restore_collapse_snapshot = (
            lambda: client_module.ChatWindow._restore_collapse_snapshot(app))
        app._boss_enter_silent = (
            lambda: client_module.ChatWindow._boss_enter_silent(app))
        app._boss_exit_silent = (
            lambda: client_module.ChatWindow._boss_exit_silent(app))
        app._append_sys = lambda *_a, **_k: None

        # A real mini state has the root withdrawn and the game window already
        # hidden before the boss overlay is entered.
        gw.hide(reason="manual")
        root.withdraw()
        mini.show()
        root.update()
        client_module.ChatWindow._capture_collapse_snapshot(app)
        client_module.ChatWindow._toggle_boss(app)
        root.update()
        assert boss.visible() and mini.win.state() == "withdrawn"
        client_module.ChatWindow._toggle_boss(app)
        root.update()
        assert root.state() == "withdrawn"
        assert mini.win.state() not in ("withdrawn", "iconic")
        client_module.ChatWindow.show_main(app)
        root.update()
        assert root.state() == "normal" and mini.win.state() == "withdrawn"

        # Exercise the production hide_to_mini path (snapshot is taken before
        # MiniBar visibility changes), then enter/exit boss mode from there.
        app._toast = SimpleNamespace(show=lambda *_a, **_k: None)
        app._mini_hint_shown = False
        app._collapse_snapshot = None
        client_module.ChatWindow.hide_to_mini(app)
        root.update()
        assert root.state() == "withdrawn" and mini.win.state() != "withdrawn"
        client_module.ChatWindow._toggle_boss(app)
        client_module.ChatWindow._toggle_boss(app)
        root.update()
        assert root.state() == "normal" and mini.win.state() == "withdrawn"

        # Manual hide after a snapshot must invalidate that window's restore
        # eligibility, even though it still exists when boss mode exits.
        root.deiconify()
        mini.hide()
        gw.show()
        gw.win.geometry("640x480+80+80")
        root.update()
        top = gw.win.winfo_rooty()
        bottom = top + gw.win.winfo_height()
        for widget in (gw.game_cv, gw.state_text, gw.act_btns, gw.act_hint):
            assert widget.winfo_ismapped()
            assert widget.winfo_rooty() >= top - 2
            assert widget.winfo_rooty() + widget.winfo_height() <= bottom + 2
        toolbar = [w for w in _descendants(gw.win)
                   if isinstance(w, tk.Button)
                   and w.cget("text") in ("规则", "棋盘", "专注窗")]
        assert {str(w.cget("text")) for w in toolbar} == {
            "规则", "棋盘", "专注窗",
        }
        for button in toolbar:
            assert button.winfo_width() >= button.winfo_reqwidth()

        # Waiting-state text with a long opponent nickname must remain inside
        # both the status text widget and the Canvas banner at minimum size.
        long_nick = "对方超长昵称_等待对手_视觉QA"
        core.roster[8] = {"nick": long_nick}
        core.game_state = {**core.game_state, "turn_uid": 8}
        gw._sync()
        root.update_idletasks()
        assert long_nick in gw.state_text.get("1.0", "end")
        text_items = [item for item in gw.game_cv.find_all()
                      if gw.game_cv.type(item) == "text"
                      and long_nick[:7] in str(gw.game_cv.itemcget(item, "text"))]
        assert text_items
        for item in text_items:
            box = gw.game_cv.bbox(item)
            assert box[0] >= -2 and box[2] <= gw.game_cv.winfo_width() + 2

        # Core state keeps changing while the boss window owns the desktop;
        # recovery must render that latest terminal frame in the same window.
        app._collapse_snapshot = None
        client_module.ChatWindow._capture_collapse_snapshot(app)
        client_module.ChatWindow._toggle_boss(app)
        core.game_state = {
            **core.game_state, "winner_uid": 7, "last_move": [7, 4],
        }
        gw._sync()
        client_module.ChatWindow._toggle_boss(app)
        root.update()
        assert client_module.ChatWindow._visible_window(gw.win)
        assert gw._cv_ui.get("state", {}).get("winner_uid") == 7

        app._collapse_snapshot = None
        client_module.ChatWindow._capture_collapse_snapshot(app)
        gw.hide(reason="manual")
        client_module.ChatWindow._toggle_boss(app)
        client_module.ChatWindow._toggle_boss(app)
        root.update()
        assert not client_module.ChatWindow._visible_window(gw.win)

        # Unsupported desktop games remain visible in the room state but have
        # no action widgets and cannot send a stale action through _do_action.
        core.game_room = {**core.game_room, "game": "go", "round": 2}
        core.game_state = {"game": "go", "turn_uid": 7,
                           "board": [[0] * 19 for _ in range(19)],
                           "size": 19}
        gw.show(); gw._sync(); root.update()
        assert gw.act_btns.winfo_children() == []
        calls_before = len(core.calls)
        gw._do_action({"pass": True})
        assert len(core.calls) == calls_before

        # Both real canvases own separate finite after jobs; hiding the game
        # window cancels both queues while preserving the latest core frame.
        gw._spawn_board_win()
        board = gw._board_win
        core.game_room = {**core.game_room, "game": "gomoku", "round": 9,
                          "status": "ended"}
        board = gw._board_win
        winning = [[0] * 15 for _ in range(15)]
        for col in range(5):
            winning[7][col] = 1
        core.game_room = {**core.game_room, "game": "gomoku", "round": 9,
                          "status": "ended"}
        core.game_state = {
            "game": "gomoku", "board": winning, "players": [7, 8],
            "turn_uid": 8, "winner_uid": 7, "draw": False,
            "last_move": [7, 4], "size": 15,
        }
        gw._render_to(gw.game_cv, gw._cv_ui)
        board.redraw(force=True)
        root.update_idletasks()
        assert gw._cv_ui.get("_after_id") is not None
        assert board._cv_ui.get("_after_id") is not None
        gw.hide(reason="collapse")
        root.update()
        assert gw._cv_ui.get("_after_id") is None
        assert board._cv_ui.get("_after_id") is None
    finally:
        if gw is not None:
            gw.close()
        if boss is not None:
            boss.close()
        if mini is not None:
            try:
                mini.win.destroy()
            except tk.TclError:
                pass
        root.destroy()


def test_disabled_tray_hotkey_boss_protocol_recovers_real_windows(monkeypatch):
    """The real Boss WM_DELETE Tcl protocol must recover the captured UI."""
    import client as client_module

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.geometry("1100x760+60+60")
    root.deiconify()
    core = _fake_game_core("gomoku")
    core.files = SimpleNamespace(_lock=threading.Lock(), xfers={})
    core.me = {}
    statuses = []
    core.send_status = lambda status: statuses.append(status)
    app = SimpleNamespace(
        root=root, core=core, _dp=client_module._DEFAULT_PAL,
        _frameless=False, _skin={}, _camo_title=lambda: "synthetic",
        _prefs=SimpleNamespace(get=lambda *_a, **_k: True),
        _unread={}, _boss_active=False,
    )
    gw = mini = boss = None
    try:
        monkeypatch.setattr(client_module.CFG, "tray_enabled", False)
        monkeypatch.setattr(client_module.CFG, "global_hotkeys_enabled", False)
        gw = client_module.GameWindow(app, pal=client_module._DEFAULT_PAL)
        app._game_win = gw
        mini = client_module.MiniBar(app, pal=client_module._DEFAULT_PAL)
        app._mini = mini
        boss = client_module.BossWindow(root, skin="excel")
        app._boss = boss
        app._collapse_snapshot = None
        app._visible_window = client_module.ChatWindow._visible_window
        app._capture_collapse_snapshot = (
            lambda: client_module.ChatWindow._capture_collapse_snapshot(app))
        app._restore_collapse_snapshot = (
            lambda: client_module.ChatWindow._restore_collapse_snapshot(app))
        app._boss_enter_silent = (
            lambda: client_module.ChatWindow._boss_enter_silent(app))
        app._boss_exit_silent = (
            lambda: client_module.ChatWindow._boss_exit_silent(app))
        app._toggle_boss = (
            lambda: client_module.ChatWindow._toggle_boss(app))
        messages = []
        app._append_sys = lambda text, *_a, **_k: messages.append(text)
        gw._spawn_board_win()
        board = gw._board_win
        board.redraw(force=True)
        root.update()

        client_module.ChatWindow._toggle_boss(app)
        root.update()
        assert boss.visible() and root.state() == "withdrawn"
        assert statuses == ["busy"]
        assert any("关闭伪装工作窗即可恢复原界面" in text for text in messages)
        protocol_command = boss.win.protocol("WM_DELETE_WINDOW")
        assert protocol_command
        # Invoke the actual Tcl command registered for WM_DELETE_WINDOW.
        root.tk.call(protocol_command)
        root.update()
        assert root.state() == "normal"
        assert client_module.ChatWindow._visible_window(gw.win)
        assert board.active()
        assert app._boss_active is False
    finally:
        if gw is not None:
            gw.close()
        if boss is not None:
            boss.close()
        if mini is not None:
            try:
                mini.win.destroy()
            except tk.TclError:
                pass
        root.destroy()


def test_default_boss_protocol_keeps_hide_only_and_external_toggle_recovers(monkeypatch):
    """Default flags preserve Boss WM_DELETE hide-only semantics."""
    import client as client_module

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.geometry("900x600+60+60")
    root.deiconify()
    core = _fake_game_core("gomoku")
    core.files = SimpleNamespace(_lock=threading.Lock(), xfers={})
    core.me = {}
    statuses = []
    core.send_status = lambda status: statuses.append(status)
    app = SimpleNamespace(
        root=root, core=core, _dp=client_module._DEFAULT_PAL,
        _frameless=False, _skin={}, _camo_title=lambda: "synthetic",
        _prefs=SimpleNamespace(get=lambda *_a, **_k: True),
        _unread={}, _boss_active=False, _mini=None, _game_win=None,
        _collapse_snapshot=None,
    )
    boss = None
    try:
        monkeypatch.setattr(client_module.CFG, "tray_enabled", True)
        monkeypatch.setattr(client_module.CFG, "global_hotkeys_enabled", False)
        boss = client_module.BossWindow(root, skin="excel")
        app._boss = boss
        app._visible_window = client_module.ChatWindow._visible_window
        app._capture_collapse_snapshot = (
            lambda: client_module.ChatWindow._capture_collapse_snapshot(app))
        app._restore_collapse_snapshot = (
            lambda: client_module.ChatWindow._restore_collapse_snapshot(app))
        app._boss_enter_silent = (
            lambda: client_module.ChatWindow._boss_enter_silent(app))
        app._boss_exit_silent = (
            lambda: client_module.ChatWindow._boss_exit_silent(app))
        app._toggle_boss = (
            lambda: client_module.ChatWindow._toggle_boss(app))
        app._append_sys = lambda *_a, **_k: None

        client_module.ChatWindow._toggle_boss(app)
        root.update()
        assert statuses == ["busy"]
        protocol_command = boss.win.protocol("WM_DELETE_WINDOW")
        root.tk.call(protocol_command)
        root.update()
        assert not boss.visible()
        assert root.state() == "withdrawn"
        assert app._boss_active is True

        # Existing external toggle path remains the recovery route when the
        # default hide-only protocol has been used.
        boss.show()
        client_module.ChatWindow._toggle_boss(app)
        root.update()
        assert root.state() == "normal"
        assert app._boss_active is False
        assert statuses[-1] == "online"
    finally:
        if boss is not None:
            boss.close()
        root.destroy()
