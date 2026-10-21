# -*- coding: utf-8 -*-
"""规则收尾 A 回归：拉密首任 30 点回合内累计、跳棋无子可动自动跳过。"""
import pytest

from games_pkg.base import GameRuleError
from games_pkg.halma import VALID, HalmaGame
from games_pkg.rummikub import N_TILE, RummikubGame, color_of, num_of


def _tile(color, num):
    for i in range(N_TILE):
        if color_of[i] == color and num_of[i] == num:
            return i
    raise AssertionError("牌不存在")


def _run(color, nums):
    return [_tile(color, n) for n in nums]


# ---------------------------------------------------------------- 拉密
def test_rummikub_initial_15_plus_15_commits():
    """回归：此前首任按单次出牌判定，先出 15 点再出 15 点会被拒绝。"""
    g = RummikubGame([1, 2], seed=1)
    first = _run(0, [4, 5, 6])          # 15 点
    second = _run(1, [4, 5, 6])         # 15 点
    g.rack[1] = list(first + second)

    g.act(1, {"op": "meld", "tiles": first})
    assert not g.initial_ok[1]
    assert g.table == [] and g.staged[1] == [first]

    msgs = g.act(1, {"op": "meld", "tiles": second})
    assert g.initial_ok[1] and g.staged[1] == []
    assert g.table == [first, second]
    assert g.rack[1] == [] and g.winner == 1
    assert any("首任" in m for m in msgs)


def test_rummikub_turn_end_below_30_rolls_back():
    """回归：此前不足 30 点的出牌会扣掉手牌并留在桌面，回合结束不回滚。"""
    g = RummikubGame([1, 2], seed=2)
    first = _run(0, [4, 5, 6])          # 15 点
    rest = [_tile(2, 1), _tile(2, 2)]
    rack = list(first + rest)
    g.rack[1] = list(rack)

    g.act(1, {"op": "meld", "tiles": first})
    assert g.table == [] and g.rack[1] == rest

    drawn = g.bag[-1]
    msgs = g.act(1, {"op": "done"})
    assert g.table == [] and g.staged[1] == []
    assert sorted(g.rack[1]) == sorted(rack + [drawn])   # 收回 3 张 + 未出牌摸 1 张
    assert not g.initial_ok[1]
    assert g.turn == 1
    assert any("收回" in m for m in msgs)
    assert any("摸一张" in m for m in msgs)


def test_rummikub_draw_ends_turn_and_rolls_back_staging():
    """回归：此前出牌后摸牌一律被拒，首任不足时只能卡在本回合无法结束。"""
    g = RummikubGame([1, 2], seed=6)
    first = _run(0, [4, 5, 6])          # 15 点
    rest = [_tile(2, 1)]
    rack = list(first + rest)
    g.rack[1] = list(rack)
    g.act(1, {"op": "meld", "tiles": first})
    drawn = g.bag[-1]

    msgs = g.act(1, {"op": "draw"})
    assert g.table == [] and g.staged[1] == []
    assert sorted(g.rack[1]) == sorted(rack + [drawn])
    assert not g.initial_ok[1] and g.turn == 1
    assert any("收回" in m for m in msgs)


def test_rummikub_cannot_extend_before_initial_with_staging():
    """回归：此前未完成首任的玩家能接续桌面；现在接续被拒且暂存原样保留。"""
    g = RummikubGame([1, 2], seed=3)
    row = _run(0, [9, 10, 11, 12])
    g.table = [list(row)]
    first = _run(1, [4, 5, 6])          # 15 点暂存
    tail = [_tile(0, 13)]
    g.rack[1] = list(first + tail)

    g.act(1, {"op": "meld", "tiles": first})
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "extend", "row": 0, "tiles": tail})

    assert g.table == [row]
    assert g.staged[1] == [first]
    assert g.rack[1] == tail
    assert not g.initial_ok[1]


def test_rummikub_invalid_meld_is_atomic():
    """回归：此前非法出牌可能留下半改的暂存/手牌/桌面，回滚不完整。"""
    g = RummikubGame([1, 2], seed=4)
    first = _run(0, [4, 5, 6])
    bad = [_tile(2, 1), _tile(3, 2)]    # 不同色不同数，不构成群或顺
    g.rack[1] = list(first + bad)

    g.act(1, {"op": "meld", "tiles": first})
    staged_before = [list(x) for x in g.staged[1]]
    rack_before = list(g.rack[1])

    # 牌不在手
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "meld", "tiles": [_tile(3, 13)]})
    assert g.staged[1] == staged_before
    assert g.rack[1] == rack_before and g.table == []

    # 组合非法
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "meld", "tiles": bad})
    assert g.staged[1] == staged_before
    assert g.rack[1] == rack_before and g.table == []


def test_rummikub_player_left_clears_staging():
    """回归：此前掉线玩家的暂存牌没有清理，牌既不在手也不在牌袋。"""
    g = RummikubGame([1, 2], seed=5)
    first = _run(0, [4, 5, 6])
    g.rack[1] = list(first)
    g.act(1, {"op": "meld", "tiles": first})
    assert g.rack[1] == [] and g.staged[1] == [first]

    bag_before = len(g.bag)
    g.player_left(1)
    assert 1 not in g.staged
    assert len(g.bag) == bag_before + len(first)


# ---------------------------------------------------------------- 跳棋
def _first_move(g, uid):
    for (x, y), (p, _) in list(g.board.items()):
        if p != uid:
            continue
        targets = g._targets(x, y)
        if targets:
            return (x, y), targets[0]
    raise AssertionError("该玩家无子可动")


def test_halma_auto_skips_player_without_moves():
    """回归：此前轮到无子可动的玩家会永久卡住，引擎没有任何跳过机制。"""
    g = HalmaGame([1, 2], seed=1)
    g.board = {k: v for k, v in g.board.items() if v[0] != 2}
    (fx, fy), (tx, ty) = _first_move(g, 1)

    msgs = g.act(1, {"fx": fx, "fy": fy, "tx": tx, "ty": ty})
    assert g.players[g.turn] == 1
    assert any("无子可动，跳过" in m for m in msgs)
    assert g.ended() is None


def test_halma_all_stuck_ends_with_progress_winner():
    """回归：此前全员无子可动时既不跳过也不终局，整局永久卡死。"""
    g = HalmaGame([1, 2], seed=1)
    # 满盘无空格：玩家1 无步可走，玩家2 无子，回合推进必须直接终局
    g.board = {cell: (1, 0) for cell in VALID}
    g.turn = 0

    msgs = g._skip_to_movable()
    assert any("无子可动" in m for m in msgs)
    assert any("全员无子可动" in m for m in msgs)
    result = g.ended()
    assert result is not None and result["winner_uid"] == 1
    assert g.snapshot()["turn_uid"] is None


def test_halma_all_stuck_equal_progress_is_draw():
    """回归：此前无合法步时 ended() 永远返回 None，连平局都无法结束。"""
    g = HalmaGame([1, 2], seed=1)
    g.board = {}

    msgs = g._skip_to_movable()
    result = g.ended()
    assert result is not None and result["winner_uid"] is None
    assert any("平局" in m for m in msgs)
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 0, "fy": 0, "tx": 0, "ty": 1})
