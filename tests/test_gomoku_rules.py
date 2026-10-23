# -*- coding: utf-8 -*-
"""五子棋规则对齐 BGA 默认（15×15 / Standard / Opening None）。

关键点：**恰好 5 子**才赢，连成 6 子及以上不算（Freestyle 才允许长连）。
"""
import random

import pytest

from games_pkg.base import GameRuleError
from games_pkg.gomoku import SIZE, GomokuGame


def _game():
    return GomokuGame([1, 2], seed=1)


def _prefill(g, cells, stone=1):
    for x, y in cells:
        g.board[y][x] = stone


# ---------- 基本对局流程 ----------
def test_black_plays_first_and_turn_alternates():
    g = _game()
    assert g.snapshot()["turn_uid"] == 1
    g.act(1, {"x": 7, "y": 7})
    assert g.board[7][7] == 1 and g.snapshot()["turn_uid"] == 2
    g.act(2, {"x": 8, "y": 8})
    assert g.board[8][8] == 2 and g.snapshot()["turn_uid"] == 1
    assert g.snapshot()["last_move"] == (8, 8)


def test_wrong_turn_occupied_and_out_of_bounds_are_rejected():
    g = _game()
    with pytest.raises(GameRuleError):
        g.act(2, {"x": 0, "y": 0})              # 还没轮到白方
    g.board[0][0] = 1
    with pytest.raises(GameRuleError):
        g.act(1, {"x": 0, "y": 0})              # 已有棋子
    with pytest.raises(GameRuleError):
        g.act(1, {"x": -1, "y": 0})             # 越界
    with pytest.raises(GameRuleError):
        g.act(1, {"x": "a", "y": 0})            # 非整数


# ---------- 恰好 5 子：四个方向都算 ----------
@pytest.mark.parametrize(("cells", "last"), [
    ([(0, 7), (1, 7), (2, 7), (3, 7)], (4, 7)),          # 横
    ([(7, 0), (7, 1), (7, 2), (7, 3)], (7, 4)),          # 竖
    ([(0, 0), (1, 1), (2, 2), (3, 3)], (4, 4)),          # 斜
    ([(0, 10), (1, 9), (2, 8), (3, 7)], (4, 6)),         # 反斜
])
def test_exactly_five_in_a_row_wins(cells, last):
    g = _game()
    _prefill(g, cells)
    g.act(1, {"x": last[0], "y": last[1]})
    assert g.winner_uid == 1
    assert g.snapshot()["turn_uid"] is None


# ---------- 长连（6 子及以上）不算赢 ----------
def test_six_in_a_row_does_not_win():
    g = _game()
    _prefill(g, [(x, 7) for x in range(5)])     # 已有 5 连
    g.act(1, {"x": 5, "y": 7})                  # 第 6 子
    assert g.winner_uid is None
    assert g.snapshot()["turn_uid"] == 2        # 继续轮到白方


def test_overline_does_not_block_a_separate_exact_five():
    """长连方向不算赢，但同一手在另一个方向恰好 5 连仍可取胜。"""
    g = _game()
    # 横向已 5 连（长连方向）
    _prefill(g, [(x, 7) for x in range(5)])
    # 在 (5,7) 落子后，纵向 (5,3..7) 恰好 5 连
    _prefill(g, [(5, y) for y in range(3, 7)])
    g.act(1, {"x": 5, "y": 7})
    assert g.winner_uid == 1


def test_actions_after_game_over_are_rejected():
    g = _game()
    _prefill(g, [(x, 7) for x in range(4)])
    g.act(1, {"x": 4, "y": 7})
    assert g.winner_uid == 1
    with pytest.raises(GameRuleError):
        g.act(2, {"x": 0, "y": 0})


# ---------- 平局 ----------
def test_full_board_without_five_is_a_draw(monkeypatch):
    g = _game()
    monkeypatch.setattr(g, "_check_win", lambda *a: False)   # 只测平局分支
    for y in range(SIZE):
        for x in range(SIZE):
            g.board[y][x] = 1 if (x + y) % 2 == 0 else 2
    g.board[SIZE - 1][SIZE - 1] = 0
    g.turn = 0
    g.act(1, {"x": SIZE - 1, "y": SIZE - 1})
    assert g.draw is True and g.winner_uid is None
    assert g.ended()["winner_uid"] is None
    assert g.snapshot()["turn_uid"] is None
    with pytest.raises(GameRuleError, match="本局已结束"):
        g.act(1, {"x": 0, "y": 0})


# ---------- 快照与随机全流程 ----------
def test_snapshot_shape():
    s = _game().snapshot()
    assert s["game"] == "gomoku" and s["size"] == SIZE
    assert len(s["board"]) == SIZE and len(s["board"][0]) == SIZE
    assert s["turn_uid"] == 1 and s["winner_uid"] is None
    assert s["last_move"] is None and s["draw"] is False


def test_random_game_terminates():
    rnd = random.Random(7)
    g = _game()
    for _ in range(SIZE * SIZE + 5):
        if g.winner_uid is not None or g.draw:
            break
        empties = [(x, y) for y in range(SIZE) for x in range(SIZE)
                   if not g.board[y][x]]
        assert empties
        x, y = rnd.choice(empties)
        g.act(g.players[g.turn], {"x": x, "y": y})
    assert g.winner_uid is not None or g.draw
