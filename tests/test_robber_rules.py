# -*- coding: utf-8 -*-
"""开拓（卡坦）盗匪规则：7 点弃牌、盗匪挡产、移动盗匪与抢牌、动作门禁。"""
import copy

import pytest

from games_pkg.base import GameRuleError
from games_pkg.kaituo import KaituoGame


def _play(players=(1, 2), seed=1):
    g = KaituoGame(list(players), seed=seed)
    g.phase = "play"
    g.turn = 0
    return g


def _total(g, uid):
    return sum(g.res[uid].values())


def _snapshot_wo_pending(g):
    snap = g.snapshot()
    return copy.deepcopy({k: v for k, v in snap.items()})


# ================================================================ 初始状态
def test_initial_robber_sits_on_desert_tile():
    g = KaituoGame([1, 2], seed=3)
    assert g.tiles[g.robber]["res"] == "desert"
    assert g.robber == (2, 4)                 # ROWS 中唯一的 d
    assert g.robber_pending is False
    snap = g.snapshot()
    assert snap["robber"] == [2, 4]
    assert snap["robber_pending"] is False


def test_initial_robber_falls_back_to_origin_without_desert(monkeypatch):
    import games_pkg.kaituo as kt
    monkeypatch.setattr(kt, "ROWS", ["wrblt", "obtwb", "tlrtw", "rwbwo", "bttrw"])
    g = KaituoGame([1, 2], seed=3)
    assert all(t["res"] != "desert" for t in g.tiles.values())
    assert g.robber == (0, 0)


# ================================================================ 7 点弃牌
def test_roll_seven_discards_half_and_blocks_production():
    g = _play(players=(1, 2, 3))
    g.res[1] = {"wood": 1, "brick": 2, "lamb": 3, "wheat": 2, "ore": 1}   # 9 → 弃 4
    g.res[2] = {"wood": 0, "brick": 1, "lamb": 1, "wheat": 5, "ore": 1}   # 8 → 弃 4
    g.res[3] = {"wood": 0, "brick": 1, "lamb": 1, "wheat": 3, "ore": 2}   # 7 → 不弃
    g.board[(0, 0)] = {"owner": 1, "city": False}
    g.tiles[(0, 0)]["num"] = 7                # 若误产资源会在玩家 1 上体现

    msgs = g._resolve_roll(1, 7)

    assert _total(g, 1) == 5 and g.res[1]["lamb"] == 0
    assert g.res[1] == {"wood": 1, "brick": 1, "lamb": 0, "wheat": 2, "ore": 1}
    assert _total(g, 2) == 4
    assert _total(g, 3) == 7
    assert g.robber_pending is True and g.last_roll == 7
    assert sum("弃 4 张" in m for m in msgs) == 2
    assert not any("弃 3 张" in m for m in msgs)
    assert not any("⛰" in m for m in msgs)


def test_discard_order_is_deterministic_for_ties():
    g = _play(players=(1, 2))
    g.res[1] = {"wood": 2, "brick": 2, "lamb": 2, "wheat": 2, "ore": 1}   # 9 → 弃 4
    g._resolve_roll(1, 7)
    # 数量相同按 wood/brick/lamb/wheat/ore：弃 wood×2 + brick×2
    assert g.res[1] == {"wood": 0, "brick": 0, "lamb": 2, "wheat": 2, "ore": 1}


# ================================================================ 动作门禁
def test_pending_robber_blocks_build_trade_and_skip():
    g = _play(seed=5)
    g.roads[((0, 0), (0, 1))] = 1
    g.res[1].update(wood=4, brick=4, lamb=4, wheat=4, ore=4)
    g.rolled = True
    g._resolve_roll(1, 7)
    before = _snapshot_wo_pending(g)

    with pytest.raises(GameRuleError, match="请先移动盗匪"):
        g.act(1, {"op": "build", "kind": "road",
                  "i": 0, "j": 1, "b_i": 0, "b_j": 2})
    with pytest.raises(GameRuleError, match="请先移动盗匪"):
        g.act(1, {"op": "trade", "give": "wood", "want": "ore", "n": 4})
    with pytest.raises(GameRuleError, match="请先移动盗匪"):
        g.act(1, {"op": "skip"})
    with pytest.raises(GameRuleError, match="请先移动盗匪"):
        g.act(1, {"op": "roll"})

    assert _snapshot_wo_pending(g) == before


# ================================================================ 移动盗匪
def test_robber_cannot_stay_and_clears_pending():
    g = _play(seed=5)
    g.rolled = True
    g._resolve_roll(1, 7)
    with pytest.raises(GameRuleError, match="不能留在原地"):
        g.act(1, {"op": "robber", "r": g.robber[0], "c": g.robber[1]})
    with pytest.raises(GameRuleError, match="资源地内"):
        g.act(1, {"op": "robber", "r": 9, "c": 9})

    g.act(1, {"op": "robber", "r": 0, "c": 0})
    assert g.robber == (0, 0) and g.robber_pending is False
    assert g.snapshot()["robber_pending"] is False


def test_robber_steals_one_card_and_conserves_total():
    g = _play(seed=7)
    g.rolled = True
    g._resolve_roll(1, 7)
    # 目标地块 (0,0) 的 4 个顶点：(0,0)(0,1)(1,0)(1,1)
    g.board[(0, 1)] = {"owner": 2, "city": False}
    g.res[2] = {"wood": 3, "brick": 0, "lamb": 0, "wheat": 0, "ore": 0}
    g.res[1] = {"wood": 0, "brick": 0, "lamb": 0, "wheat": 0, "ore": 0}

    msgs = g.act(1, {"op": "robber", "r": 0, "c": 0})

    assert _total(g, 1) + _total(g, 2) == 3
    assert _total(g, 1) == 1 and _total(g, 2) == 2
    assert any("抢到 1木头" in m for m in msgs)


def test_robber_without_victim_says_nobody_to_rob():
    g = _play(seed=7)
    g.rolled = True
    g._resolve_roll(1, 7)

    msgs = g.act(1, {"op": "robber", "r": 4, "c": 4})
    assert g.robber == (4, 4) and g.robber_pending is False
    assert any("无人可抢" in m for m in msgs)


# ================================================================ 盗匪挡产
def test_robber_tile_produces_no_resource():
    g = _play(seed=9)
    g.robber = (0, 0)
    g.tiles[(0, 0)]["num"] = 8
    g.board[(0, 0)] = {"owner": 1, "city": False}   # 仅邻接 (0,0) 这一块地
    before = dict(g.res[1])

    msgs = g._resolve_roll(1, 8)
    assert g.res[1] == before
    assert not any("⛰" in m for m in msgs)

    g.robber = (4, 4)
    msgs = g._resolve_roll(1, 8)
    assert g.res[1]["wood"] == before["wood"] + 1
    assert any("⛰" in m for m in msgs)


# ================================================================ 移动后同回合可继续
def test_can_build_in_same_turn_after_moving_robber():
    g = _play(seed=11)
    g.roads[((0, 0), (0, 1))] = 1
    g.res[1].update(wood=3, brick=3)
    g.rolled = True
    g._resolve_roll(1, 7)
    assert g.robber_pending is True

    g.act(1, {"op": "robber", "r": 4, "c": 4})
    assert g.rolled is True
    g.act(1, {"op": "build", "kind": "road",
              "i": 0, "j": 1, "b_i": 0, "b_j": 2})
    assert ((0, 1), (0, 2)) in g.roads
    assert g.players[g.turn] == 1

    g.act(1, {"op": "skip"})
    assert g.players[g.turn] == 2
    assert g.rolled is False and g.robber_pending is False
