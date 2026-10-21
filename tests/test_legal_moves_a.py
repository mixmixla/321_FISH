# -*- coding: utf-8 -*-
"""合法着法引擎 A：国际象棋 / 中国象棋 / 将棋的 legal_moves 契约。

legal_moves 是 UI 高亮的唯一权威，必须与 act 的接受条件一致：
- 仅当前行动者、未终局时返回，否则 [];
- 走子用 {"from": [fx, fy], "to": [tx, ty]}，将棋持子打入用 {"drop": t, "x": x, "y": y}；
- 不得包含会被 act 以 GameRuleError 拒绝的着法（被牵制、蹩马腿、塞象眼、无炮架等）。
"""
from games_pkg import shogi as shogi_mod
from games_pkg.chess import ChessGame
from games_pkg.shogi import ShogiGame
from games_pkg.xiangqi import XiangQiGame


def _targets(legal, frm):
    """取某一子的全部目标格。"""
    return {tuple(m["to"]) for m in legal if m.get("from") == list(frm)}


# ================================================================ 国际象棋
def test_chess_initial_legal_moves_known_targets():
    g = ChessGame([1, 2], seed=1)
    legal = g.legal_moves(1)
    assert len(legal) == 20                                  # 16 兵步 + 4 马步
    assert {"from": [4, 6], "to": [4, 4]} in legal           # e2-e4
    assert {"from": [4, 6], "to": [4, 5]} in legal           # e2-e3
    assert {"from": [6, 7], "to": [5, 5]} in legal           # Ng1-f3
    assert {"from": [1, 7], "to": [2, 5]} in legal           # Nb1-c3
    assert {"from": [4, 6], "to": [4, 3]} not in legal       # 兵不能一步三格
    assert {"from": [4, 6], "to": [3, 5]} not in legal       # 兵不能斜走空格
    assert {"from": [6, 7], "to": [6, 5]} not in legal       # 马不能直走
    assert {"from": [1, 1], "to": [1, 2]} not in legal       # 不是自己的棋子
    assert all(0 < g.board[m["from"][1]][m["from"][0]] <= 6 for m in legal)


def test_chess_legal_moves_skip_pinned_piece():
    """被黑车牵制的白车只能沿牵制线走，横走会送将。"""
    g = ChessGame([1, 2], seed=1)
    g.board = [[0] * 8 for _ in range(8)]
    g.board[7][4] = 1                          # 白王 e1
    g.board[6][4] = 3                          # 白车 e2（被牵制）
    g.board[0][4] = 13                         # 黑车 e8
    g.board[0][0] = 11                         # 黑王 a8
    g.kpos = {0: (4, 7), 1: (0, 0)}
    g.cast = {0: [False, False], 1: [False, False]}
    g.ep = None
    g.turn = 0
    targets = _targets(g.legal_moves(1), (4, 6))
    assert (3, 6) not in targets               # 横走 = 送将
    assert (4, 5) in targets                   # 沿牵制线前进
    assert g.board[6][4] == 3 and g.board[6][3] == 0   # 模拟不残留状态


def test_chess_castling_listed_only_when_path_safe():
    """王车易位按 act 接受的目标格 (6,7) 返回；穿越被攻击格时不得返回。"""
    g = ChessGame([1, 2], seed=1)
    g.board = [[0] * 8 for _ in range(8)]
    g.board[7][4] = 1                          # 白王 e1
    g.board[7][7] = 3                          # 白车 h1
    g.board[0][4] = 11                         # 黑王 e8
    g.kpos = {0: (4, 7), 1: (4, 0)}
    g.cast = {0: [True, True], 1: [False, False]}
    g.ep = None
    g.turn = 0
    assert {"from": [4, 7], "to": [6, 7]} in g.legal_moves(1)
    g.board[0][5] = 13                         # 黑车控制 f1 (5,7)
    assert {"from": [4, 7], "to": [6, 7]} not in g.legal_moves(1)


def test_chess_legal_moves_apply_through_act():
    g = ChessGame([1, 2], seed=1)
    plan = [((4, 6), (4, 4), 1), ((4, 1), (4, 3), 2),
            ((6, 7), (5, 5), 1), ((1, 0), (2, 2), 2)]
    for frm, to, uid in plan:
        action = {"from": list(frm), "to": list(to)}
        assert action in g.legal_moves(uid)
        g.act(uid, {"fx": frm[0], "fy": frm[1], "tx": to[0], "ty": to[1]})
    assert g.board[4][4] == 6 and g.board[5][5] == 5 and g.board[2][2] == 15
    assert g.board[6][4] == 0 and g.board[1][4] == 0


def test_chess_legal_moves_empty_for_non_current_and_finished():
    g = ChessGame([1, 2], seed=1)
    assert g.legal_moves(2) == []
    assert g.legal_moves(99) == []
    g.winner = 1
    assert g.legal_moves(1) == []
    g2 = ChessGame([1, 2], seed=1)
    g2.result = "draw"
    assert g2.legal_moves(1) == []


# ================================================================ 中国象棋
def _xq_blank(g):
    g.board = [[0] * 9 for _ in range(10)]
    g.turn = 0
    g.winner = None


def test_xiangqi_initial_legal_moves_known_targets():
    g = XiangQiGame([1, 2], seed=1)
    legal = g.legal_moves(1)
    assert len(legal) == 44
    assert {"from": [0, 9], "to": [0, 7]} in legal      # 红车直上两格
    assert {"from": [1, 9], "to": [0, 7]} in legal      # 红马
    assert {"from": [1, 9], "to": [2, 7]} in legal
    assert {"from": [1, 7], "to": [1, 0]} in legal      # 炮隔黑炮打黑马
    assert {"from": [0, 9], "to": [0, 5]} not in legal  # 被己方兵挡住
    assert {"from": [1, 9], "to": [1, 6]} not in legal  # 马不能直走
    assert {"from": [0, 0], "to": [0, 2]} not in legal  # 不是自己的棋子
    assert _targets(legal, (4, 9)) == {(4, 8)}          # 帅不出九宫
    assert g.legal_moves(2) == []


def test_xiangqi_horse_leg_and_elephant_eye():
    g = XiangQiGame([1, 2], seed=1)
    _xq_blank(g)
    g.board[9][4] = 1                          # 红帅
    g.board[0][3] = 11                         # 黑将
    g.board[4][4] = 4                          # 红马 (4,4)
    g.board[4][5] = 7                          # 马腿 (5,4) 被己方兵蹩住
    targets = _targets(g.legal_moves(1), (4, 4))
    assert (6, 3) not in targets and (6, 5) not in targets
    assert (2, 3) in targets                   # 另一侧马腿通畅
    g.board[4][5] = 0
    g.board[6][3] = 7                          # 象眼 (3,6) 被塞
    g.board[7][4] = 3                          # 红相 (4,7)
    targets = _targets(g.legal_moves(1), (4, 7))
    assert (2, 5) not in targets
    assert (6, 5) in targets


def test_xiangqi_cannon_capture_needs_screen():
    g = XiangQiGame([1, 2], seed=1)
    _xq_blank(g)
    g.board[9][4] = 1                          # 红帅
    g.board[0][3] = 11                         # 黑将
    g.board[6][4] = 6                          # 红炮 (4,6)
    g.board[3][4] = 15                         # 黑车 (4,3)
    targets = _targets(g.legal_moves(1), (4, 6))
    assert (4, 3) not in targets               # 无炮架不能吃
    assert (4, 4) in targets                   # 空位可平移
    g.board[4][4] = 7                          # 架上己方兵
    targets = _targets(g.legal_moves(1), (4, 6))
    assert (4, 3) in targets                   # 隔山打


def test_xiangqi_legal_moves_exclude_flying_general_exposure():
    """移开挡子让将帅照面的着法不返回，沿同列保持遮挡的着法保留。"""
    g = XiangQiGame([1, 2], seed=1)
    _xq_blank(g)
    g.board[9][4] = 1                          # 红帅 (4,9)
    g.board[0][4] = 11                         # 黑将 (4,0)
    g.board[5][4] = 5                          # 红车挡在中间
    legal = g.legal_moves(1)
    assert {"from": [4, 5], "to": [3, 5]} not in legal   # 让将帅照面
    assert {"from": [4, 5], "to": [4, 4]} in legal       # 仍挡在中间


def test_xiangqi_legal_moves_apply_through_act():
    g = XiangQiGame([1, 2], seed=1)
    plan = [((0, 9), (0, 7), 1), ((0, 0), (0, 2), 2), ((1, 7), (1, 3), 1)]
    for frm, to, uid in plan:
        action = {"from": list(frm), "to": list(to)}
        assert action in g.legal_moves(uid)
        g.act(uid, {"fx": frm[0], "fy": frm[1], "tx": to[0], "ty": to[1]})
    assert g.board[7][0] == 5 and g.board[2][0] == 15 and g.board[3][1] == 6


def test_xiangqi_legal_moves_empty_for_non_current_and_finished():
    g = XiangQiGame([1, 2], seed=1)
    assert g.legal_moves(2) == []
    g.winner = 1
    assert g.legal_moves(1) == []


# ================================================================ 将棋
def test_shogi_initial_legal_moves_known_targets():
    g = ShogiGame([1, 2], seed=1)
    legal = g.legal_moves(1)
    assert len(legal) == 32
    assert {"from": [0, 6], "to": [0, 5]} in legal       # 步兵
    assert {"from": [7, 7], "to": [7, 1]} in legal       # 飞车吃白飞车
    assert {"from": [7, 7], "to": [7, 8]} not in legal   # 被己方桂马挡住
    assert {"from": [0, 6], "to": [1, 5]} not in legal   # 步兵不能斜走
    assert {"from": [1, 8], "to": [1, 6]} not in legal   # 桂马不能直走
    assert {"from": [0, 2], "to": [0, 3]} not in legal   # 不是自己的棋子
    assert all("drop" not in m for m in legal)           # 初始无持子
    assert g.legal_moves(2) == []


def test_shogi_drop_moves_follow_engine_restrictions():
    g = ShogiGame([1, 2], seed=1)
    g.board = [[0] * 9 for _ in range(9)]
    g.hand = {0: [shogi_mod.N_, shogi_mod.P, shogi_mod.R], 1: []}
    g.turn = 0
    drops = {(m["drop"], m["x"], m["y"]) for m in g.legal_moves(1) if "drop" in m}
    assert (shogi_mod.N_, 0, 7) not in drops      # 桂马不能落最后两行
    assert (shogi_mod.N_, 0, 6) in drops
    assert (shogi_mod.P, 0, 8) not in drops       # 步兵不能落最后一行
    assert (shogi_mod.P, 0, 7) in drops
    assert (shogi_mod.R, 0, 8) in drops
    # 二步：同列已有己方步兵则整列不得再打步兵
    g.board[0][0] = shogi_mod.P
    drops = {(m["drop"], m["x"], m["y"]) for m in g.legal_moves(1) if "drop" in m}
    assert not any(d[0] == shogi_mod.P and d[1] == 0 for d in drops)
    assert (shogi_mod.P, 1, 7) in drops


def test_shogi_legal_drop_applies_through_act():
    g = ShogiGame([1, 2], seed=1)
    g.hand = {0: [shogi_mod.P], 1: []}
    g.turn = 0
    action = next(m for m in g.legal_moves(1) if m.get("drop") == shogi_mod.P)
    g.act(1, {"op": "drop", "t": action["drop"], "x": action["x"], "y": action["y"]})
    assert g.board[action["y"]][action["x"]] == shogi_mod.P
    assert shogi_mod.P not in g.hand[0]


def test_shogi_legal_moves_apply_through_act():
    g = ShogiGame([1, 2], seed=1)
    plan = [((0, 6), (0, 5), 1), ((0, 2), (0, 3), 2), ((7, 7), (7, 4), 1)]
    for frm, to, uid in plan:
        action = {"from": list(frm), "to": list(to)}
        assert action in g.legal_moves(uid)
        g.act(uid, {"fx": frm[0], "fy": frm[1], "tx": to[0], "ty": to[1]})
    assert g.board[5][0] == 8 and g.board[3][0] == 18 and g.board[4][7] == 2


def test_shogi_legal_moves_empty_for_non_current_and_finished():
    g = ShogiGame([1, 2], seed=1)
    g.hand = {0: [shogi_mod.P], 1: [shogi_mod.G]}
    assert g.legal_moves(2) == []
    g.winner = 1
    assert g.legal_moves(1) == []
