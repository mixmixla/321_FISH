# -*- coding: utf-8 -*-
"""W4 补录单测：军棋 + 斗兽棋"""
import pytest
from games_pkg import GAME_TYPES
from games_pkg.base import GameRuleError
from games_pkg.junqi import _side, _rank, ENGINEER, MINE, BOMB, FLAG
from games_pkg.dou import MOUSE, ELEPHANT, LION, TIGER


def _g(name, uids, seed=1):
    return GAME_TYPES[name](uids, seed)


# ================= 军棋 =================
def test_junqi_setup():
    g = _g("junqi", [1, 2])
    assert g.board[0][0] >= 10 and g.board[0][0] <= 21      # 玩家0 占上行
    assert g.board[9][0] >= 40 and g.board[9][0] <= 51      # 玩家1 占下行


def test_junqi_codec():
    assert _side(15) == 0 and _rank(15) == 5
    assert _side(48) == 1 and _rank(48) == 8


def test_junqi_engineer_digs_mine():
    g = _g("junqi", [1, 2])
    g.board = [[0] * 5 for _ in range(10)]
    g.board[0][0] = 10 + ENGINEER      # 玩家0 工兵
    g.board[0][1] = 40 + MINE          # 玩家1 地雷
    g.act(1, {"fx": 0, "fy": 0, "tx": 1, "ty": 0})
    assert g.board[0][1] == 10 + ENGINEER and g.turn == 1


def test_junqi_non_engineer_dies_on_mine():
    g = _g("junqi", [1, 2])
    g.board = [[0] * 5 for _ in range(10)]
    g.board[0][0] = 10 + 6             # 玩家0 连长
    g.board[0][1] = 40 + MINE
    g.act(1, {"fx": 0, "fy": 0, "tx": 1, "ty": 0})
    assert g.board[0][0] == 0 and g.board[0][1] == 40 + MINE
    assert g.turn == 1


def test_junqi_bomb_blast():
    g = _g("junqi", [1, 2])
    g.board = [[0] * 5 for _ in range(10)]
    g.board[0][0] = 10 + BOMB          # 玩家0 炸弹
    g.board[0][1] = 40 + 11            # 玩家1 司令
    g.act(1, {"fx": 0, "fy": 0, "tx": 1, "ty": 0})
    assert g.board[0][1] == 0 and g.board[0][0] == 0      # 同归于尽


def test_junqi_rank_capture():
    g = _g("junqi", [1, 2])
    g.board = [[0] * 5 for _ in range(10)]
    g.board[0][0] = 10 + 11            # 玩家0 司令
    g.board[0][1] = 40 + 6             # 玩家1 营长
    g.act(1, {"fx": 0, "fy": 0, "tx": 1, "ty": 0})
    assert g.board[0][1] == 10 + 11 and g.board[0][0] == 0


def test_junqi_lose_when_outranked():
    g = _g("junqi", [1, 2])
    g.board = [[0] * 5 for _ in range(10)]
    g.board[0][0] = 10 + 4             # 玩家0 排长
    g.board[0][1] = 40 + 8             # 玩家1 旅长
    g.act(1, {"fx": 0, "fy": 0, "tx": 1, "ty": 0})
    assert g.board[0][0] == 0 and g.board[0][1] == 40 + 8   # 自己被吃


def test_junqi_flag_capture_wins():
    g = _g("junqi", [1, 2])
    g.board = [[0] * 5 for _ in range(10)]
    g.board[0][0] = 10 + 3             # 玩家0 工兵
    g.board[0][1] = 40 + FLAG          # 玩家1 军旗
    g.act(1, {"fx": 0, "fy": 0, "tx": 1, "ty": 0})
    assert g.winner == 1
    assert g.ended()["winner_uid"] == 1


def test_junqi_flag_miner_immobile():
    g = _g("junqi", [1, 2])
    g.board = [[0] * 5 for _ in range(10)]
    g.board[1][0] = 10 + FLAG
    g.board[1][1] = 10 + MINE
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 0, "fy": 1, "tx": 1, "ty": 1})    # 军旗不可动


def test_junqi_needs_adjacent():
    g = _g("junqi", [1, 2])
    g.board = [[0] * 5 for _ in range(10)]
    g.board[0][0] = 10 + 5
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 0, "fy": 0, "tx": 2, "ty": 0})    # 非相邻


# ================= 斗兽棋 =================
def test_dou_setup():
    g = _g("dou", [1, 2])
    assert g.board[(0, 0)] == (1, LION)      # 玩家1 狮
    assert g.board[(6, 8)] == (0, TIGER)     # 玩家0 虎


def test_dou_lion_jump_water():
    g = _g("dou", [1, 2])
    g.board = {}
    # 河：x=1..5, y=3,4,5；player0 狮 (x3,y2) 竖跳过河吃 player1 狼 (x3,y6)
    g.board[(3, 2)] = (0, LION)
    g.board[(3, 6)] = (1, 4)
    g.act(1, {"fx": 3, "fy": 2, "tx": 3, "ty": 6})
    assert (3, 6) in g.board and g.board[(3, 6)][0] == 0


def test_dou_mouse_eats_elephant():
    g = _g("dou", [1, 2])
    g.board = {}
    g.board[(0, 2)] = (0, MOUSE)
    g.board[(0, 1)] = (1, ELEPHANT)          # 鼠在陆上(x=0)吃象
    g.act(1, {"fx": 0, "fy": 2, "tx": 0, "ty": 1})
    assert g.board[(0, 1)][1] == MOUSE


def test_dou_den_capture_wins():
    g = _g("dou", [1, 2])
    g.board = {}
    # player0(先手) 的敌营是白大本营 DENS[1]=(3,8)
    g.board[(3, 7)] = (0, MOUSE)
    g.act(1, {"fx": 3, "fy": 7, "tx": 3, "ty": 8})
    assert g.winner == 1
    assert g.ended()["winner_uid"] == 1



def test_dou_turn_enforced():
    g = _g("dou", [1, 2])
    with pytest.raises(GameRuleError):
        g.act(2, {"fx": 0, "fy": 7, "tx": 0, "ty": 8})   # 轮到玩家1(红下)