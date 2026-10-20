# -*- coding: utf-8 -*-
"""第 2 批棋类 P0 回归：围棋打劫回滚、军棋空位、斗兽棋水域、将棋桂马打、
国际象棋自将回滚/易位权/终局锁定。"""
import pytest

from games_pkg.base import GameRuleError
from games_pkg.chess import ChessGame
from games_pkg.dou import DOG, ELEPHANT, LION, MOUSE, DouGame
from games_pkg.go import GoGame
from games_pkg.junqi import JunqiGame
from games_pkg.shogi import N_, ShogiGame


# ---------------------------------------------------------------- 围棋
def _ko_go():
    g = GoGame([1, 2])
    for x, y in ((1, 0), (0, 1), (1, 2)):
        g.board[y][x] = 1
    for x, y in ((2, 0), (1, 1), (3, 1), (2, 2)):
        g.board[y][x] = 2
    g.turn = 0
    return g


def test_go_ko_is_rejected_and_board_rolled_back():
    g = _ko_go()
    g.act(1, {"x": 2, "y": 1})                 # 黑提 (1,1)
    assert g.board[1][1] == 0 and g.board[1][2] == 1
    after_black = [row[:] for row in g.board]
    with pytest.raises(GameRuleError):
        g.act(2, {"x": 1, "y": 1})             # 白立即回提 → 打劫
    assert g.board == after_black              # 回滚：不能留下半状态


def test_go_suicide_is_rejected_without_mutation():
    g = GoGame([1, 2])
    for x, y in ((1, 0), (0, 1), (2, 1), (1, 2)):
        g.board[y][x] = 2
    g.turn = 0
    with pytest.raises(GameRuleError):
        g.act(1, {"x": 1, "y": 1})
    assert g.board[1][1] == 0


# ---------------------------------------------------------------- 军棋
def test_junqi_cannot_move_from_an_empty_square():
    g = JunqiGame([1, 2], seed=1)
    g.board[5][2] = 0                          # (x=2, y=5) 空
    g.turn = 0
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 2, "fy": 5, "tx": 2, "ty": 6})


# ---------------------------------------------------------------- 斗兽棋
def test_dou_only_mouse_may_enter_water():
    g = DouGame([1, 2])
    g.board = {(1, 2): (0, LION)}
    g.turn = 0
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 1, "fy": 2, "tx": 1, "ty": 3})   # 狮入水

    g2 = DouGame([1, 2])
    g2.board = {(1, 2): (0, MOUSE)}
    g2.turn = 0
    g2.act(1, {"fx": 1, "fy": 2, "tx": 1, "ty": 3})
    assert g2.board[(1, 3)] == (0, MOUSE)


def test_dou_no_capture_across_water():
    g = DouGame([1, 2])
    g.board = {(1, 3): (0, MOUSE), (1, 2): (1, DOG)}   # 水中鼠 vs 岸上狗
    g.turn = 0
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 1, "fy": 3, "tx": 1, "ty": 2})


def test_dou_mouse_eats_elephant_on_land():
    g = DouGame([1, 2])
    g.board = {(1, 2): (0, MOUSE), (2, 2): (1, ELEPHANT)}
    g.turn = 0
    g.act(1, {"fx": 1, "fy": 2, "tx": 2, "ty": 2})
    assert g.board[(2, 2)] == (0, MOUSE)


# ---------------------------------------------------------------- 将棋
def test_shogi_knight_cannot_be_dropped_on_last_two_ranks():
    g = ShogiGame([1, 2], seed=1)
    g.hand[0] = [N_]
    g.turn = 0
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "drop", "t": N_, "x": 4, "y": 7})   # 倒数第二行（空位）
    g.act(1, {"op": "drop", "t": N_, "x": 1, "y": 6})       # 再往前一行可打
    assert g.board[6][1] != 0 and N_ not in g.hand[0]


# ---------------------------------------------------------------- 国际象棋
def test_chess_self_check_move_rolls_back():
    g = ChessGame([1, 2], seed=1)
    g.board = [[0] * 8 for _ in range(8)]
    g.board[7][4] = 1                          # 白王 e1
    g.board[6][4] = 3                          # 白车 e2（被黑车牵制）
    g.board[0][4] = 13                         # 黑车 e8
    g.board[0][0] = 11                         # 黑王 a8
    g.kpos = {0: (4, 7), 1: (0, 0)}
    g.cast = {0: [False, False], 1: [False, False]}
    g.ep = None
    g.turn = 0
    before = [row[:] for row in g.board]
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 4, "fy": 6, "tx": 3, "ty": 6})
    assert g.board == before                   # 棋子/王位整体回滚
    assert g.kpos[0] == (4, 7)


def test_chess_captured_rook_removes_opponent_castling_right():
    g = ChessGame([1, 2], seed=1)
    g.board = [[0] * 8 for _ in range(8)]
    g.board[7][4] = 1                          # 白王 e1
    g.board[7][7] = 3                          # 白车 h1
    g.board[0][7] = 13                         # 黑车 h8
    g.board[0][0] = 11                         # 黑王 a8
    g.kpos = {0: (4, 7), 1: (0, 0)}
    g.cast = {0: [True, True], 1: [False, False]}
    g.ep = None
    g.turn = 1
    g.act(2, {"fx": 7, "fy": 0, "tx": 7, "ty": 7})
    assert g.cast[0][0] is False               # 白方短易位权因 h1 车被吃而失效


def test_chess_no_moves_after_draw():
    g = ChessGame([1, 2], seed=1)
    g.result = "draw"
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 4, "fy": 6, "tx": 4, "ty": 4})
