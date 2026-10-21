# -*- coding: utf-8 -*-
"""合法着法引擎 B：国际跳棋/跳棋/军棋/斗兽棋 legal_moves 与 act 交叉验证。"""
import pytest

from games_pkg.base import GameRuleError
from games_pkg.checkers import BLACK_KING, BLACK_MAN, RED_MAN, CheckersGame
from games_pkg.dou import CAT, DOG, ELEPHANT, LION, MOUSE, DouGame
from games_pkg.halma import HalmaGame
from games_pkg.junqi import (COLS, EMPTY, ENGINEER, FLAG, MINE, ROWS,
                             JunqiGame)


def _has(moves, fx, fy, tx, ty):
    return {"from": [fx, fy], "to": [tx, ty]} in moves


def _act(game, uid, mv):
    fx, fy = mv["from"]
    tx, ty = mv["to"]
    return game.act(uid, {"fx": fx, "fy": fy, "tx": tx, "ty": ty})


# ---------------------------------------------------------------- 国际跳棋
def test_checkers_initial_moves_are_accepted():
    g = CheckersGame([1, 2])
    moves = g.legal_moves(1)
    assert len(moves) == 7
    assert all(mv["to"][1] == 3 for mv in moves)      # 黑普通子只能向前
    assert g.legal_moves(2) == []                     # 非当前玩家
    for mv in moves:
        _act(CheckersGame([1, 2]), 1, mv)             # 全新实例上必须成功


def test_checkers_backward_and_occupied_targets_not_listed():
    g = CheckersGame([1, 2])
    g.board = [[0] * 8 for _ in range(8)]
    g.board[2][2] = BLACK_MAN
    g.board[3][3] = BLACK_MAN
    g.turn = 0
    moves = g.legal_moves(1)
    assert _has(moves, 2, 2, 1, 3)
    assert not _has(moves, 2, 2, 1, 1)                # 普通子不能后退
    assert not _has(moves, 2, 2, 3, 3)                # 目标格己方子
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 2, "fy": 2, "tx": 1, "ty": 1})
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 2, "fy": 2, "tx": 3, "ty": 3})


def test_checkers_capture_is_listed_and_executes():
    g = CheckersGame([1, 2])
    g.board = [[0] * 8 for _ in range(8)]
    g.board[2][2] = BLACK_MAN
    g.board[3][3] = RED_MAN
    g.turn = 0
    moves = g.legal_moves(1)
    assert _has(moves, 2, 2, 4, 4)
    assert not _has(moves, 2, 2, 3, 3)                # 不能落在敌子上
    fresh = CheckersGame([1, 2])
    fresh.board = [row[:] for row in g.board]
    fresh.turn = 0
    fresh.act(1, {"fx": 2, "fy": 2, "tx": 4, "ty": 4})
    assert fresh.board[3][3] == 0 and fresh.board[4][4] == BLACK_MAN


def test_checkers_promotion_and_king_flying_capture():
    g = CheckersGame([1, 2])
    g.board = [[0] * 8 for _ in range(8)]
    g.board[6][2] = BLACK_MAN
    g.turn = 0
    moves = g.legal_moves(1)
    assert _has(moves, 2, 6, 3, 7)
    fresh = CheckersGame([1, 2])
    fresh.board = [row[:] for row in g.board]
    fresh.turn = 0
    fresh.act(1, {"fx": 2, "fy": 6, "tx": 3, "ty": 7})
    assert fresh.board[7][3] == BLACK_KING            # 升王

    g2 = CheckersGame([1, 2])
    g2.board = [[0] * 8 for _ in range(8)]
    g2.board[0][0] = BLACK_KING
    g2.board[2][2] = RED_MAN
    g2.turn = 0
    moves = g2.legal_moves(1)
    assert _has(moves, 0, 0, 3, 3)                    # 飞王远距离吃
    assert not _has(moves, 0, 0, 2, 2)                # 不能落在敌子上
    fresh = CheckersGame([1, 2])
    fresh.board = [row[:] for row in g2.board]
    fresh.turn = 0
    fresh.act(1, {"fx": 0, "fy": 0, "tx": 3, "ty": 3})
    assert fresh.board[2][2] == 0 and fresh.board[3][3] == BLACK_KING


def test_checkers_terminal_returns_empty():
    g = CheckersGame([1, 2])
    g.winner = 1
    assert g.legal_moves(1) == [] and g.legal_moves(2) == []


# ---------------------------------------------------------------- 跳棋
def test_halma_initial_moves_are_accepted():
    g = HalmaGame([1, 2])
    moves = g.legal_moves(1)
    assert len(moves) == 26
    assert g.legal_moves(2) == []
    for mv in moves:
        _act(HalmaGame([1, 2]), 1, mv)


def test_halma_hop_over_piece_and_empty_middle():
    g = HalmaGame([1, 2])
    g.board = {(4, 4): (1, 0), (4, 3): (2, 1)}
    g.turn = 0
    moves = g.legal_moves(1)
    assert _has(moves, 4, 4, 4, 2)                    # 隔一子连跳
    assert not _has(moves, 4, 4, 4, 3)                # 目标格有子
    fresh = HalmaGame([1, 2])
    fresh.board = dict(g.board)
    fresh.turn = 0
    fresh.act(1, {"fx": 4, "fy": 4, "tx": 4, "ty": 2})
    assert (4, 2) in fresh.board and (4, 4) not in fresh.board

    g2 = HalmaGame([1, 2])
    g2.board = {(4, 4): (1, 0)}
    g2.turn = 0
    moves = g2.legal_moves(1)
    assert not _has(moves, 4, 4, 4, 2)                # 中间无子不能跳
    with pytest.raises(GameRuleError):
        g2.act(1, {"fx": 4, "fy": 4, "tx": 4, "ty": 2})


def test_halma_terminal_returns_empty():
    g = HalmaGame([1, 2])
    g.winner = 1
    assert g.legal_moves(1) == []
    g2 = HalmaGame([1, 2])
    g2.draw = True
    assert g2.legal_moves(1) == []


# ---------------------------------------------------------------- 军棋
def _junqi_engineer_game():
    g = JunqiGame([1, 2], seed=1)
    g.board = [[EMPTY] * COLS for _ in range(ROWS)]
    g.board[4][2] = 10 + ENGINEER
    g.board[4][1] = 10 + MINE          # 己方地雷
    g.board[3][2] = 10 + FLAG          # 己方军旗
    g.board[4][3] = 40 + MINE          # 敌方地雷（工兵可挖）
    g.board[5][2] = 40 + FLAG          # 敌方军旗（可扛）
    g.turn = 0
    return g


def test_junqi_initial_moves_are_accepted_and_immobile_pieces_excluded():
    g = JunqiGame([1, 2], seed=3)
    moves = g.legal_moves(1)
    assert len(moves) == 5                             # 只有最前排可越界吃子
    assert all(mv["from"][1] == 4 and mv["to"][1] == 5 for mv in moves)
    for y in range(ROWS):
        for x in range(COLS):
            if g.board[y][x] % 10 in (FLAG, MINE):
                assert not any(mv["from"] == [x, y] for mv in moves)
    assert g.legal_moves(2) == []
    for mv in moves:
        _act(JunqiGame([1, 2], seed=3), 1, mv)


def test_junqi_engineer_moves_onto_enemy_mine_and_flag():
    g = _junqi_engineer_game()
    moves = g.legal_moves(1)
    assert len(moves) == 2
    assert _has(moves, 2, 4, 3, 4)                    # 工兵挖雷
    assert _has(moves, 2, 4, 2, 5)                    # 扛旗
    assert not _has(moves, 2, 4, 1, 4)                # 己方地雷格
    assert not _has(moves, 2, 4, 2, 3)                # 己方军旗格
    assert all(mv["from"] == [2, 4] for mv in moves)

    fresh = _junqi_engineer_game()
    fresh.act(1, {"fx": 2, "fy": 4, "tx": 3, "ty": 4})
    assert fresh.board[4][3] == 10 + ENGINEER and fresh.turn == 1

    fresh = _junqi_engineer_game()
    fresh.act(1, {"fx": 2, "fy": 4, "tx": 2, "ty": 5})
    assert fresh.winner == 1


def test_junqi_flag_and_mine_cannot_move():
    g = _junqi_engineer_game()
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 2, "fy": 3, "tx": 3, "ty": 3})       # 军旗
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 1, "fy": 4, "tx": 0, "ty": 4})       # 地雷
    assert g.legal_moves(1)                               # 非法动作未破坏状态


def test_junqi_terminal_returns_empty():
    g = JunqiGame([1, 2], seed=1)
    g.winner = 1
    assert g.legal_moves(1) == [] and g.legal_moves(2) == []


# ---------------------------------------------------------------- 斗兽棋
def test_dou_initial_moves_are_accepted():
    g = DouGame([1, 2])
    moves = g.legal_moves(1)
    assert len(moves) == 11
    assert all(g.board[tuple(mv["from"])][0] == 0 for mv in moves)
    assert g.legal_moves(2) == []
    for mv in moves:
        _act(DouGame([1, 2]), 1, mv)


def test_dou_elephant_cannot_enter_water():
    g = DouGame([1, 2])
    g.board = {(1, 2): (0, ELEPHANT)}
    g.turn = 0
    moves = g.legal_moves(1)
    assert _has(moves, 1, 2, 1, 1)                     # 岸上可走
    assert not _has(moves, 1, 2, 1, 3)                 # 象不可入河
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 1, "fy": 2, "tx": 1, "ty": 3})


def test_dou_mouse_water_rules():
    g = DouGame([1, 2])
    g.board = {(1, 2): (0, MOUSE)}
    g.turn = 0
    moves = g.legal_moves(1)
    assert _has(moves, 1, 2, 1, 3)                     # 鼠可入河
    fresh = DouGame([1, 2])
    fresh.board = dict(g.board)
    fresh.turn = 0
    fresh.act(1, {"fx": 1, "fy": 2, "tx": 1, "ty": 3})
    assert fresh.board[(1, 3)] == (0, MOUSE)

    g2 = DouGame([1, 2])
    g2.board = {(1, 3): (0, MOUSE), (1, 2): (1, ELEPHANT)}
    g2.turn = 0
    moves = g2.legal_moves(1)
    assert not _has(moves, 1, 3, 1, 2)                 # 水中鼠不能吃岸上象
    with pytest.raises(GameRuleError):
        g2.act(1, {"fx": 1, "fy": 3, "tx": 1, "ty": 2})

    g3 = DouGame([1, 2])
    g3.board = {(1, 2): (0, MOUSE), (2, 2): (1, ELEPHANT)}
    g3.turn = 0
    moves = g3.legal_moves(1)
    assert _has(moves, 1, 2, 2, 2)                     # 岸上鼠吃象
    fresh = DouGame([1, 2])
    fresh.board = dict(g3.board)
    fresh.turn = 0
    fresh.act(1, {"fx": 1, "fy": 2, "tx": 2, "ty": 2})
    assert fresh.board[(2, 2)] == (0, MOUSE)


def test_dou_lion_jump_and_mouse_blocking():
    g = DouGame([1, 2])
    g.board = {(1, 2): (0, LION)}
    g.turn = 0
    moves = g.legal_moves(1)
    assert _has(moves, 1, 2, 1, 6)                     # 狮虎隔河竖跳
    fresh = DouGame([1, 2])
    fresh.board = dict(g.board)
    fresh.turn = 0
    fresh.act(1, {"fx": 1, "fy": 2, "tx": 1, "ty": 6})
    assert fresh.board[(1, 6)] == (0, LION)

    g2 = DouGame([1, 2])
    g2.board = {(1, 2): (0, LION), (1, 4): (0, MOUSE)}
    g2.turn = 0
    moves = g2.legal_moves(1)
    assert not _has(moves, 1, 2, 1, 6)                 # 河中有鼠不可跳
    with pytest.raises(GameRuleError):
        g2.act(1, {"fx": 1, "fy": 2, "tx": 1, "ty": 6})


def test_dou_rank_and_own_target_not_listed():
    g = DouGame([1, 2])
    g.board = {(1, 2): (0, CAT), (2, 2): (1, LION), (0, 2): (0, DOG)}
    g.turn = 0
    moves = g.legal_moves(1)
    assert _has(moves, 1, 2, 1, 1)                     # 空位可走
    assert not _has(moves, 1, 2, 2, 2)                 # 猫吃不了狮
    assert not _has(moves, 1, 2, 0, 2)                 # 不能吃己方子
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 1, "fy": 2, "tx": 2, "ty": 2})


def test_dou_terminal_returns_empty():
    g = DouGame([1, 2])
    g.winner = 1
    assert g.legal_moves(1) == [] and g.legal_moves(2) == []
