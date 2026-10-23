"""Flagship draw text on a real Tk state widget, including an old snapshot."""

from copy import deepcopy
from types import SimpleNamespace
import sys
import tkinter as tk

import pytest

from client import GameWindow
from games_pkg.connect4 import Connect4Game
from games_pkg.gomoku import GomokuGame


def _draw_game(kind):
    if kind == "connect4":
        game = Connect4Game([1, 2], seed=1)
        row = [1, 1, 2, 2, 1, 1, 2]
        inverse = [2, 2, 1, 1, 2, 2, 1]
        game.board = [row[:], inverse[:], row[:], inverse[:], row[:], inverse[:]]
        game.board[0][6] = 0
        game.turn = 1
        game.act(2, {"col": 6})
    else:
        game = GomokuGame([1, 2], seed=1)
        for y in range(15):
            for x in range(15):
                game.board[y][x] = 1 if (x // 2 + y) % 2 == 0 else 2
        game.board[14][14] = 0
        game.turn = 0
        game.act(1, {"x": 14, "y": 14})
    assert game.draw and game.ended() is not None
    return game


@pytest.mark.parametrize("kind", ["gomoku", "connect4"])
def test_real_tk_state_text_draw_and_new_round(kind):
    game = _draw_game(kind)
    root = tk.Tk()
    root.withdraw()
    try:
        # Only the state widget is needed; its real Tk insert/delete path is
        # GameWindow._render_state -> _fmt_state -> _append_state.
        window = object.__new__(GameWindow)
        window.state_text = tk.Text(root)
        window._render_canvas = lambda: None
        window._rebuild_actions = lambda _game: None
        window._sel_room = None
        window.core = SimpleNamespace(
            uid=1, game_meta={}, roster={1: {"nick": "甲"}, 2: {"nick": "乙"}},
            game_room={"game": kind, "room_id": "draw-room", "round": 1,
                       "status": "ended", "players": [1, 2], "spectators": []},
            game_state=game.snapshot())

        def shown():
            window._render_state()
            return window.state_text.get("1.0", "end")

        text = shown()
        assert "平局" in text and "轮到" not in text

        legacy = deepcopy(window.core.game_state)
        legacy["turn_uid"] = 1
        window.core.game_state = legacy
        text = shown()
        assert "平局" in text and "轮到" not in text

        restarted = type(game)([1, 2], seed=1)
        window.core.game_room = {**window.core.game_room,
                                 "round": 2, "status": "playing"}
        window.core.game_state = restarted.snapshot()
        text = shown()
        assert "轮到 甲" in text and "平局" not in text
    finally:
        original = sys.exception()
        try:
            root.destroy()
        except BaseException as exc:
            if original is None:
                raise
            original.add_note(f"owned Tk cleanup failed: {type(exc).__name__}: {exc}")
