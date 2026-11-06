# -*- coding: utf-8 -*-
"""2048 规则与展示包的专项回归。"""
from __future__ import annotations

import copy

import pytest

from boardgames.tile2048 import PKG
from boardgames.tile2048 import desktop as tile_desktop
from boardgames.tile2048.desktop import paint
from boardgames.tile2048.web import WEB_CSS, WEB_JS
from games_pkg.base import GameRuleError
from games_pkg.rooms import RoomManager
from games_pkg.tile2048 import Tile2048Game


def _game(board=None, score=0):
    game = Tile2048Game([17], seed=7)
    if board is not None:
        game.board = [list(row) for row in board]
        game.score = score
        game.status = "playing"
        game.over = False
        game.winner_uid = None
    return game


def test_start_has_standard_board_and_two_tiles():
    game = Tile2048Game([17], seed=7)
    assert len(game.board) == 4
    assert all(len(row) == 4 for row in game.board)
    nonzero = [v for row in game.board for v in row if v]
    assert len(nonzero) == 2
    assert set(nonzero) <= {2, 4}
    assert game.snapshot()["players"] == [17]


def test_merge_is_once_per_source_and_score_is_sum_of_merged_tiles():
    game = _game([
        [2, 2, 2, 2],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ])
    lines = game.act(17, {"op": "move", "dir": "left"})
    assert game.board[0][:2] == [4, 4]
    assert game.score == 8
    assert "向 左 移动" in lines[0]
    # two merged tiles plus exactly one newly spawned tile
    assert sum(value != 0 for row in game.board for value in row) == 3


@pytest.mark.parametrize(
    ("direction", "board", "expected"),
    [
        ("left", [[0, 2, 4, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
         [[2, 4, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]),
        ("right", [[0, 2, 4, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
         [[0, 0, 2, 4], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]),
        ("up", [[0, 0, 0, 0], [2, 0, 0, 0], [4, 0, 0, 0], [0, 0, 0, 0]],
         [[2, 0, 0, 0], [4, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]),
        ("down", [[2, 0, 0, 0], [4, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
         [[0, 0, 0, 0], [0, 0, 0, 0], [2, 0, 0, 0], [4, 0, 0, 0]]),
    ],
)
def test_all_directions_pack_without_merge(direction, board, expected):
    moved, changed, gained = Tile2048Game._move_board(board, direction)
    assert moved == expected
    assert changed is True
    assert gained == 0


def test_invalid_step_does_not_spawn_or_change_state():
    game = _game([
        [2, 4, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ])
    before = copy.deepcopy(game.snapshot())
    with pytest.raises(GameRuleError, match="无法移动"):
        game.act(17, {"op": "move", "dir": "left"})
    assert game.snapshot() == before


def test_reaching_2048_ends_with_player_winner():
    game = _game([
        [1024, 1024, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ])
    game.act(17, {"op": "move", "dir": "left"})
    assert game.status == "won"
    assert game.over is True
    assert game.winner_uid == 17
    assert game.ended() == {"winner_uid": 17, "detail": "玩家17 达成 2048，得分 2048"}
    with pytest.raises(GameRuleError, match="已结束"):
        game.act(17, {"op": "move", "dir": "right"})


def test_room_manager_can_observe_terminal_result():
    manager = RoomManager({"tile2048": Tile2048Game})
    room = manager.create(17, "tile2048")
    manager.start(17, room.room_id)
    room.gs.board = [
        [1024, 1024, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    manager.handle_action(17, room.room_id, {"op": "move", "dir": "left"})
    assert room.gs.ended()["winner_uid"] == 17


def test_last_valid_slide_can_end_in_loss_without_inventing_a_winner():
    game = _game([
        [0, 2, 4, 8],
        [16, 32, 64, 128],
        [256, 512, 1024, 2],
        [4, 8, 16, 32],
    ])

    # The legal slide fills the only gap.  Make the random spawn deterministic
    # while still exercising the normal post-move terminal check.
    def spawn_at_last_gap():
        game.board[0][3] = 4
        return {"row": 0, "col": 3, "value": 4}

    game._spawn_tile = spawn_at_last_gap
    game.act(17, {"op": "move", "dir": "left"})
    assert game.status == "lost"
    assert game.over is True
    assert game.winner_uid is None
    assert game.ended()["winner_uid"] is None


def test_package_and_render_contracts_are_self_contained():
    assert PKG.name == "tile2048"
    assert PKG.rules == "games_pkg.tile2048:Tile2048Game"
    assert PKG.desktop.endswith(":paint")
    assert PKG.web_js.endswith(":WEB_JS")
    assert PKG.web_css.endswith(":WEB_CSS")
    snap = _game().snapshot()
    assert isinstance(snap["score"], int)
    assert "grid" not in snap
    for direction in ("left", "right", "up", "down"):
        assert direction in WEB_JS
    assert "touchstart" in WEB_JS and "touchend" in WEB_JS
    assert "tile2048-atlas.webp" in WEB_CSS
    assert "dataset.stage" in WEB_JS
    assert "box-sizing:border-box" in WEB_CSS
    assert "min-width:0" in WEB_CSS
    assert "touch-action:none" in WEB_CSS


class _Canvas:
    def __init__(self):
        self.calls = []

    def create_rectangle(self, *args, **kwargs):
        self.calls.append(("rectangle", args, kwargs))

    def create_text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))


def test_desktop_painter_draws_board_and_exposes_hit_geometry():
    cv = _Canvas()
    ui = {}
    paint(cv, {"board": [[2, 4, 0, 0]] + [[0] * 4 for _ in range(3)], "score": 12},
          17, str, lambda action: None, lambda: None, ui, None, 420, 520)
    assert ui["game"] == "tile2048"
    x0, y0, x1, y1 = ui["tile2048_board"]
    assert 0 <= x0 < x1 <= 420
    assert 0 <= y0 < y1 <= 520
    assert sum(kind == "rectangle" for kind, _args, _kwargs in cv.calls) >= 18


def test_desktop_atlas_is_cropped_once_and_cached(monkeypatch):
    from PIL import ImageTk

    calls = []

    class _Photo:
        pass

    def fake_photo(*args, **kwargs):
        calls.append((args, kwargs))
        return _Photo()

    monkeypatch.setattr(ImageTk, "PhotoImage", fake_photo)
    ui = {}
    assert tile_desktop._is_tk_canvas(object()) is False
    assert tile_desktop._tile_images(object(), ui, 28.0) == {}
    assert calls == []
    monkeypatch.setattr(tile_desktop, "_is_tk_canvas", lambda _cv: True)
    first = tile_desktop._tile_images(object(), ui, 28.0)
    second = tile_desktop._tile_images(object(), ui, 28.0)
    assert set(first) == {2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048}
    assert second is first
    assert len(calls) == 11
    old_tiles = first
    resized = tile_desktop._tile_images(object(), ui, 32.0)
    assert resized is not first
    assert old_tiles == {}
    assert ui["tile2048_image_cache"]["size"] == 32
    assert len(calls) == 22
