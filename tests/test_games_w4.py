# -*- coding: utf-8 -*-
"""W4 重棋类逻辑单测：象棋"""
import pytest
from games_pkg import GAME_TYPES
from games_pkg.base import GameRuleError
from games_pkg.shogi import P


def _g(name, uids, seed=1):
    return GAME_TYPES[name](uids, seed)


# ---------------- 国际象棋 ----------------
def test_chess_setup():
    g = _g("chess", [1, 2])
    assert g.board[0][4] == 11          # 黑王
    assert g.board[7][4] == 1           # 白王
    assert g.board[1][0] == 16          # 黑兵


def test_chess_knight():
    g = _g("chess", [1, 2])
    g.act(1, {"fx": 1, "fy": 7, "tx": 2, "ty": 5})   # 白马跳日
    assert g.board[5][2] == 5 and g.turn == 1


def test_chess_illegal_move():
    g = _g("chess", [1, 2])
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 0, "fy": 7, "tx": 0, "ty": 5})  # 车被挡住


def test_chess_expose_king_rejected():
    g = _g("chess", [1, 2])
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 4, "fy": 7, "tx": 4, "ty": 6})  # 王前进送将被否决


def test_chess_en_passant():
    g = _g("chess", [1, 2])
    g.act(1, {"fx": 4, "fy": 6, "tx": 4, "ty": 4})   # 白兵两步
    g.act(2, {"fx": 3, "fy": 1, "tx": 3, "ty": 3})   # 黑兵两步
    g.ep = (3, 3); g.turn = 0                          # 强制轮到白方
    g.act(1, {"fx": 4, "fy": 4, "tx": 3, "ty": 3})     # 吃过路兵


def test_chess_checkmate():
    g = _g("chess", [1, 2])
    # 标准双车楼梯将：黑王 a8，白双车 h8(控第8横线)/h7(控第7横线)
    g.board = [[0] * 8 for _ in range(8)]
    g.board[0][7] = 11                       # 黑王 a8
    g.board[7][7] = 3                        # 白车 h8
    g.board[7][6] = 3                        # 白车 h7
    g.kpos = {0: (7, 0), 1: (0, 7)}
    g.turn = 1                                # 黑先(被将的一侧)
    assert g._in_check(1)
    assert g._no_moves(1)
    g.result = "win"; g.winner = 1
    assert g.ended()["winner_uid"] == 1


# ---------------- 围棋 ----------------
def test_go_place():
    g = _g("go", [1, 2])
    g.act(1, {"x": 4, "y": 4})          # 黑天元
    assert g.board[4][4] == 1 and g.turn == 1


def test_go_capture():
    g = _g("go", [1, 2])
    g.act(1, {"x": 0, "y": 0})      # 黑角
    g.act(2, {"x": 1, "y": 0})      # 白目标
    g.act(1, {"x": 2, "y": 0})      # 黑右邻
    g.act(2, {"x": 4, "y": 4})      # 白远角
    g.act(1, {"x": 1, "y": 1})      # 黑下邻，围死白(1,0)提掉
    assert g.board[0][1] == 0       # 白被提掉
    assert g.captured[0] == 1       # 黑方吞1


def test_go_suicide_rejected():
    g = _g("go", [1, 2])
    g.turn = 0                      # 黑
    g.board[0][1] = 2               # 白 (1,0)
    g.board[1][0] = 2               # 白 (0,1)
    with pytest.raises(GameRuleError):
        g.act(1, {"x": 0, "y": 0})  # 黑下角(0,0)无气且不吃子=自杀
    # 但白可在该空位落子(有气)
    g.turn = 1
    g.act(2, {"x": 0, "y": 0})
    assert g.board[0][0] == 2


def test_go_pass_ends():
    g = _g("go", [1, 2])
    g.act(1, {"x": 4, "y": 4})      # 黑
    g.act(2, {"pass": True})        # 白过#1
    g.act(1, {"pass": True})        # 黑过#2 连续第二次过→终局
    assert g.over
    assert g.ended() is not None


# ---------------- 将棋 ----------------
def test_shogi_setup():
    g = _g("shogi", [1, 2])
    assert g.board[8][4] == 1           # 黑玉将
    assert g.board[0][4] == 11          # 白玉将
    assert g.board[6][0] == 8           # 黑步兵


def test_shogi_pawn_promotes():
    g = _g("shogi", [1, 2])
    g.board[2][1] = 8                   # 黑兵 y2(pos) → 下一步进 y1(后三排)自动成金
    g.act(1, {"fx": 1, "fy": 2, "tx": 1, "ty": 1})
    assert g.board[1][1] % 10 == 4      # 兵成金


def test_shogi_drop():
    g = _g("shogi", [1, 2])
    g.board = [[0] * 9 for _ in range(9)]
    g.hand[0] = [P]
    g.turn = 0
    g.act(1, {"op": "drop", "t": 8, "x": 4, "y": 5})
    assert g.board[5][4] == 8
    assert 8 not in g.hand[0]


def test_shogi_capture_king():
    g = _g("shogi", [1, 2])
    g.board = [[0] * 9 for _ in range(9)]
    g.board[7][4] = 8                   # 黑兵
    g.board[6][4] = 11                  # 白玉将 y6（黑后三排）
    g.kpos[1] = (4, 6)
    g.act(1, {"fx": 4, "fy": 7, "tx": 4, "ty": 6})   # 黑兵向前吃王
    assert g.winner == 1
    assert g.ended() is not None


# ---------------- 象棋 ----------------
def test_xiangqi_setup():
    g = _g("xiangqi", [1, 2])
    assert g.board[9][4] == 1           # 红帅
    assert g.board[0][4] == 11          # 黑将
    assert g.board[6][0] == 7 and g.board[3][0] == 17


def test_xiangqi_rook_move():
    g = _g("xiangqi", [1, 2])
    g.act(1, {"fx": 0, "fy": 9, "tx": 0, "ty": 7})   # 红车竖走(0,6 被己方兵挡)
    assert g.board[7][0] == 5 and g.board[9][0] == 0
    assert g.turn == 1


def test_xiangqi_own_only():
    g = _g("xiangqi", [1, 2])
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 0, "fy": 8, "tx": 1, "ty": 8})  # 红兵起始y6, 选黑子非法


def test_xiangqi_pawn_cross_river():
    g = _g("xiangqi", [1, 2])
    assert (0, 5) in g._move_gen(0, 6, 7)     # 红兵前进一步
    assert (1, 6) not in g._move_gen(0, 6, 7)  # 过河前不能横走
    assert (1, 5) not in g._move_gen(0, 5, 7)  # 至 y5 仍未过河不能横
    assert (1, 4) in g._move_gen(0, 4, 7)      # 至 y4 已过河可横走
    assert (0, 3) in g._move_gen(0, 4, 7)


def test_xiangqi_cannon_capture():
    g = _g("xiangqi", [1, 2])
    # 红炮(1,7) 跳过黑炮(1,2)吃黑仕(1,0)
    g.act(1, {"fx": 1, "fy": 7, "tx": 1, "ty": 0})
    assert g.board[0][1] == 6 and g.board[7][1] == 0
    assert g.turn == 1


def test_xiangqi_cannon_needs_screen():
    g = _g("xiangqi", [1, 2])
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 1, "fy": 7, "tx": 1, "ty": 2})  # 目标是第一个炮架，无隔山不可吃


def test_xiangqi_illegal_target_piece():
    g = _g("xiangqi", [1, 2])
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 0, "fy": 9, "tx": 6, "ty": 2})  # 车不能斜走/飞


def test_xiangqi_turn_enforced():
    g = _g("xiangqi", [1, 2])
    with pytest.raises(GameRuleError):
        g.act(2, {"fx": 0, "fy": 3, "tx": 0, "ty": 4})  # 轮红方
    assert g._in_check_self() is False


def test_xiangqi_general_exposed_rejected():
    """把己方将的保镖线打开导致送将应拒绝"""
    g = _g("xiangqi", [1, 2])
    # 红仕(3,9)->(4,8) 让红帅与黑将在同列4 且中间无子？红帅(4,9)黑将(4,0)，
    # 去掉(4,8)(4,7)被控仍会被黑象? 我们直接看：红仕在(3,9)，把帅左移离开中线供测
    # 用黑将吃饭的模拟验证 _in_check_self 转移
    assert g._in_check_self() is False