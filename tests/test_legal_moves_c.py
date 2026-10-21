# -*- coding: utf-8 -*-
"""合法着法引擎 C：othello / tictactoe / connect4 的 legal_moves"""
import copy

import pytest

from games_pkg.base import GameRuleError
from games_pkg.othello import OthelloGame
from games_pkg.tictactoe import TicTacToeGame
from games_pkg.connect4 import Connect4Game


def _cells(moves):
    return {(m["x"], m["y"]) for m in moves}


# ---------------- othello ----------------

def test_othello_initial_four_and_act_consistency():
    g = OthelloGame([1, 2])
    moves = g.legal_moves(1)
    assert len(moves) == 4
    assert _cells(moves) == {(2, 4), (3, 5), (4, 2), (5, 3)}
    # 每个提示点都被 act 接受
    for mv in moves:
        probe = copy.deepcopy(g)
        probe.act(1, mv)
    # 非夹点 / 已占点都不在列表，且 act 拒绝
    for x, y in [(0, 0), (3, 3), (4, 4), (3, 4), (4, 3)]:
        assert {"x": x, "y": y} not in moves
        probe = copy.deepcopy(g)
        with pytest.raises(GameRuleError):
            probe.act(1, {"x": x, "y": y})


def test_othello_non_current_and_ended_empty():
    g = OthelloGame([1, 2])
    assert g.legal_moves(2) == []
    assert g.legal_moves(99) == []

    g.winner_uid = 1
    g.scores = {1: 40, 2: 24}
    assert g.legal_moves(1) == []
    assert g.legal_moves(2) == []

    draw = OthelloGame([1, 2])
    draw.scores = {1: 32, 2: 32}
    assert draw.legal_moves(1) == []


def test_othello_auto_pass_keeps_turn_and_legal():
    g = OthelloGame([1, 2])
    g.board = [[1] * 8 for _ in range(8)]
    g.board[0][2] = 2          # 白子
    g.board[1][6] = 2          # 白子
    g.board[0][0] = g.board[0][1] = 0
    g.board[1][0] = g.board[1][1] = 0
    g.board[1][5] = 0
    # 黑：可下 (1,0)、(5,1)；白：无子可下
    assert _cells(g.legal_moves(1)) == {(1, 0), (5, 1)}

    msgs = g.act(1, {"x": 1, "y": 0})
    assert "让过" in msgs[0]
    assert g.snapshot()["turn_uid"] == 1
    assert g.legal_moves(1) == [{"x": 5, "y": 1}]
    assert g.legal_moves(2) == []


# ---------------- tictactoe ----------------

def test_tictactoe_empty_nine_and_occupied_excluded():
    g = TicTacToeGame([1, 2])
    moves = g.legal_moves(1)
    assert len(moves) == 9
    assert _cells(moves) == {(x, y) for x in range(3) for y in range(3)}

    g.act(1, {"x": 1, "y": 1})
    after = g.legal_moves(2)
    assert len(after) == 8
    assert {"x": 1, "y": 1} not in after
    assert g.legal_moves(1) == []


def test_tictactoe_ended_empty():
    g = TicTacToeGame([1, 2])
    for x, y in [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)]:
        g.act(g.players[g.turn], {"x": x, "y": y})
    assert g.winner_uid is not None
    assert g.legal_moves(1) == []
    assert g.legal_moves(2) == []


# ---------------- connect4 ----------------

def test_connect4_empty_seven_and_full_column_excluded():
    g = Connect4Game([1, 2])
    moves = g.legal_moves(1)
    assert len(moves) == 7
    assert {m["col"] for m in moves} == set(range(7))
    assert g.legal_moves(2) == []

    for _ in range(6):
        g.act(g.players[g.turn], {"col": 3})
    after = g.legal_moves(g.players[g.turn])
    assert {m["col"] for m in after} == {0, 1, 2, 4, 5, 6}
    assert {"col": 3} not in after
    assert {"col": -1} not in after and {"col": 7} not in after


def test_connect4_moves_match_act():
    g = Connect4Game([1, 2])
    for mv in g.legal_moves(1):
        probe = copy.deepcopy(g)
        probe.act(1, mv)


def test_connect4_ended_empty():
    g = Connect4Game([1, 2])
    for col in (0, 1, 0, 1, 0, 1, 0):
        g.act(g.players[g.turn], {"col": col})
    assert g.winner_uid is not None
    assert g.legal_moves(1) == []
    assert g.legal_moves(2) == []
