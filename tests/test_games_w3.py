# -*- coding: utf-8 -*-
"""W3 锈象级棋类：井字棋 / 跳棋 / 国际跳棋 / 角斗士棋 / 飞行棋 单元测试"""
import pytest
from games_pkg import GAME_TYPES
from games_pkg.base import GameRuleError
from games_pkg.halma import VALID


def _g(name, p, seed=7):
    return GAME_TYPES[name](p, seed)


# ---------- 井字棋 ----------
def test_tictactoe_two_line():
    g = _g("tictactoe", [1, 2])
    g.act(1, {"x": 0, "y": 0})
    g.act(2, {"x": 0, "y": 1})
    g.act(1, {"x": 1, "y": 0})
    g.act(2, {"x": 1, "y": 1})
    g.act(1, {"x": 2, "y": 0})
    assert g.winner_uid == 1
    assert g.ended()["winner_uid"] == 1


def test_tictactoe_draw():
    g = _g("tictactoe", [1, 2])
    o = [(0, 0), (0, 2), (2, 1), (2, 0), (1, 2)]   # 玩家1(O) 走偶数步
    x = [(0, 1), (1, 0), (1, 1), (2, 2)]           # 玩家2(X) 走奇数步
    seq = []
    for i in range(4):
        seq.append(o[i]); seq.append(x[i])
    seq.append(o[4])
    for i, (cx, cy) in enumerate(seq):
        g.act(1 if i % 2 == 0 else 2, {"x": cx, "y": cy})
    assert g.draw
    assert g.ended() == {"winner_uid": None, "detail": "平局"}


def test_tictactoe_invalid():
    g = _g("tictactoe", [1, 2])
    g.act(1, {"x": 0, "y": 0})
    with pytest.raises(GameRuleError):
        g.act(2, {"x": 0, "y": 0})   # 占用
    with pytest.raises(GameRuleError):
        g.act(1, {"x": 5, "y": 0})   # 越界


# ---------- 跳棋 ----------
def test_halma_step():
    g = _g("halma", [1, 2])
    uid = g.players[g.turn]
    moved = False
    for (fx, fy), (o, arm) in list(g.board.items()):
        if o != uid:
            continue
        for dx, dy in [(0, 1), (1, 1), (1, 0), (-1, 1)]:
            tx, ty = fx + dx, fy + dy
            if (tx, ty) in g.board or (tx, ty) not in VALID:
                continue
            g.act(uid, {"fx": fx, "fy": fy, "tx": tx, "ty": ty})
            moved = True
            break
        if moved:
            break
    assert moved and g.last_move is not None


def test_halma_non_straight_jump_rejected():
    g = _g("halma", [1, 2])
    (fx, fy), (o, arm) = next(iter(g.board.items()))
    if o != 1:  # 需轮到玩家1，取它的子
        pass
    for (fx, fy), (o, arm) in list(g.board.items()):
        if o == 1:
            break
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": fx, "fy": fy, "tx": fx + 2, "ty": fy + 1, "mid_none": True})
    with pytest.raises(GameRuleError):
        g.act(2, {"fx": fx, "fy": fy, "tx": fx + 1, "ty": fy + 1})  # 移别人的子


def test_halma_snapshot_fields():
    g = _g("halma", [1, 2])
    s = g.snapshot()
    assert s["size"] == 9 and s["game"] == "halma"
    assert sum(row.count(0) for row in s["valid"]) <= 81


# ---------- 国际跳棋 ----------
def test_checkers_initial_move():
    g = _g("checkers", [1, 2])
    uid = g.players[g.turn]
    moved = False
    for r in range(5):
        for c in range(8):
            if g.board[r][c] != 1 or (r + c) % 2 != 1:
                continue
            for dc in (-1, 1):
                nc = c + dc
                if 0 <= nc < 8 and g.board[r + 1][nc] == 0:
                    g.act(uid, {"fx": c, "fy": r, "tx": nc, "ty": r + 1})
                    moved = True
                    break
            if moved:
                break
        if moved:
            break
    assert moved


def test_checkers_capture():
    g = _g("checkers", [1, 2])
    g.board[3][3] = 1              # 黑子置于中部
    g.board[4][4] = 2              # 白子成为其可吃目标
    g.act(1, {"fx": 3, "fy": 3, "tx": 5, "ty": 5})
    assert g.board[5][5] == 1 and g.board[4][4] == 0 and g.board[3][3] == 0


def test_checkers_can_only_own():
    g = _g("checkers", [1, 2])
    spot = None
    for r in range(5, 8):
        for c in range(8):
            if g.board[r][c] == 2:
                spot = (c, r)
                break
        if spot:
            break
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": spot[0], "fy": spot[1], "tx": spot[0], "ty": spot[1]})


# ---------- 角斗士棋 ----------
def test_blokus_first_must_corner():
    g = _g("blokus", [1, 2, 3, 4])
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "place", "piece": "M", "oi": 0, "x": 5, "y": 5})
    g.act(1, {"op": "place", "piece": "M", "oi": 0, "x": 0, "y": 0})
    assert g.placed[1] == 1


def test_blokus_corner_contact_rule():
    g = _g("blokus", [1, 2])
    # 玩家1 首块放 O4 方块覆盖角落 (0,0)
    g.act(1, {"op": "place", "piece": "O4", "oi": 0, "x": 0, "y": 0})
    g.act(2, {"op": "place", "piece": "M", "oi": 0, "x": 19, "y": 19})
    # 与己方块同边相邻(占用) -> 拒绝
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "place", "piece": "M", "oi": 0, "x": 1, "y": 0})
    # 单块角对角 (2,2) 连接 (1,1) -> 合法
    g.act(1, {"op": "place", "piece": "M", "oi": 0, "x": 2, "y": 2})
    assert g.placed[1] == 5


def test_blokus_pass_end():
    g = _g("blokus", [1, 2])
    for u in (1, 2):
        g.act(u, {"op": "pass"})
    assert g.winner is not None


# ---------- 飞行棋 ----------
def test_ludo_need_roll():
    g = _g("ludo", [1, 2])
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "move", "idx": 0})


def test_ludo_launch_and_advance():
    g = _g("ludo", [1, 2, 3, 4])
    uid = g.players[g.turn]
    g.dice, g.need_roll = 6, False
    g.act(uid, {"op": "move", "idx": 0})
    assert g.miles[uid][0] == 0
    s0 = g.snapshot()
    assert s0["positions"][str(uid)][0] != -1


def test_ludo_cant_move_over_finish():
    g = _g("ludo", [1, 2])
    uid = g.players[g.turn]
    g.miles[uid][0] = 39
    g.dice, g.need_roll = 2, False
    with pytest.raises(GameRuleError):
        g.act(uid, {"op": "move", "idx": 0})