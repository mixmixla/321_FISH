# -*- coding: utf-8 -*-
"""回合流程与牌库收尾：开拓同回合多动作 / 工坊轮换先手 / 铁路摸走最后一张卡。"""
import copy

import pytest

from games_pkg.base import GameRuleError
from games_pkg.gongfang import GongfangGame
from games_pkg.kaituo import KaituoGame
from games_pkg.lovelove import LoveLoveGame
from games_pkg.tielu import TieluGame


def _kaituo_play(seed=1):
    g = KaituoGame([1, 2], seed=seed)
    g.phase = "play"
    g.turn = 0
    return g


def _total_res(g, uid):
    return sum(g.res[uid].values())


# ================================================================ 开拓
def test_kaituo_roll_keeps_turn_and_allows_build_and_trade():
    g = _kaituo_play(seed=5)
    g.roads[((0, 0), (0, 1))] = 1
    g.res[1].update(wood=5, brick=5, ore=0)

    g.act(1, {"op": "roll"})
    assert g.rolled is True
    assert g.players[g.turn] == 1               # 掷骰不结束回合

    g.act(1, {"op": "build", "kind": "road", "i": 0, "j": 1, "b_i": 0, "b_j": 2})
    assert ((0, 1), (0, 2)) in g.roads
    assert g.players[g.turn] == 1               # 建造后仍是自己的回合

    msgs = g.act(1, {"op": "trade", "give": "wood", "want": "ore", "n": 4})
    assert "🔄" in msgs[0]
    assert g.res[1]["ore"] == 1
    assert g.players[g.turn] == 1


def test_kaituo_roll_only_once_per_turn():
    g = _kaituo_play(seed=2)
    g.act(1, {"op": "roll"})
    if g.robber_pending:                     # 7 点须先移动盗匪才能继续操作
        g.act(1, {"op": "robber", "r": 0, "c": 0})
    before = copy.deepcopy(g.res)

    with pytest.raises(GameRuleError, match="本回合已掷过骰"):
        g.act(1, {"op": "roll"})
    assert g.res == before and g.players[g.turn] == 1


def test_kaituo_build_and_trade_require_roll():
    g = _kaituo_play(seed=3)
    g.roads[((0, 0), (0, 1))] = 1
    g.res[1].update(wood=4, brick=4)
    res_before = dict(g.res[1])
    roads_before = dict(g.roads)

    with pytest.raises(GameRuleError, match="请先掷骰"):
        g.act(1, {"op": "build", "kind": "road", "i": 0, "j": 1, "b_i": 0, "b_j": 2})
    with pytest.raises(GameRuleError, match="请先掷骰"):
        g.act(1, {"op": "trade", "give": "wood", "want": "ore", "n": 4})

    assert g.res[1] == res_before and g.roads == roads_before
    assert g.rolled is False and g.players[g.turn] == 1


def test_kaituo_skip_is_what_ends_the_turn():
    g = _kaituo_play(seed=4)
    g.act(1, {"op": "roll"})
    assert g.players[g.turn] == 1

    g.act(1, {"op": "skip"})
    assert g.players[g.turn] == 2 and g.rolled is False

    g.act(2, {"op": "roll"})
    assert g.players[g.turn] == 2
    g.act(2, {"op": "skip"})
    assert g.players[g.turn] == 1 and g.rolled is False


def test_kaituo_resources_are_conserved_across_same_turn_actions():
    g = _kaituo_play(seed=6)
    g.roads[((0, 0), (0, 1))] = 1
    g.res[1] = {"wood": 5, "brick": 5, "lamb": 5, "wheat": 5, "ore": 5}
    total = _total_res(g, 1)

    g.rolled = True
    g._resolve_roll(1, 8)                             # 固定非 7 点：场上无定居点，不产资源
    assert _total_res(g, 1) == total

    g.act(1, {"op": "build", "kind": "road", "i": 0, "j": 1, "b_i": 0, "b_j": 2})
    assert _total_res(g, 1) == total - 2              # 路：1 木 + 1 砖

    g.act(1, {"op": "trade", "give": "wood", "want": "ore", "n": 4})
    assert _total_res(g, 1) == total - 2 - 4 + 1      # 4:1 港口交换
    assert g.res[1]["wood"] == 0 and g.res[1]["ore"] == 6
    assert all(v >= 0 for v in g.res[1].values())
    assert g.players[g.turn] == 1


def test_kaituo_current_player_leaving_resets_roll_state():
    """回归：已掷骰的当前玩家掉线后，接手的人不能继承 rolled 而无法掷骰。"""
    g = KaituoGame([1, 2, 3], seed=8)
    g.phase = "play"
    g.turn = 0
    g.rolled = True

    g.player_left(1)
    assert g.rolled is False
    assert g.players[g.turn] == 2


# ================================================================ 工坊
def _pass_whole_round(g):
    first = g.players[g.turn]
    round_no = g.round_no
    for _ in range(len(g.players)):
        g.act(g.players[g.turn], {"op": "pass"})
    assert g.round_no > round_no or g.winner is not None
    return first


def test_gongfang_round_start_rotates_each_round():
    g = GongfangGame([1, 2, 3], seed=7)
    assert g.round_no == 1 and g.players[g.turn] == 1

    assert _pass_whole_round(g) == 1
    assert g.round_no == 2 and g.players[g.turn] == 2   # 第 2 轮由 1 号位（uid 2）先手

    assert _pass_whole_round(g) == 2
    assert g.round_no == 3 and g.players[g.turn] == 3   # 第 3 轮由 2 号位（uid 3）先手

    assert _pass_whole_round(g) == 3
    assert g.winner is not None


# ================================================================ 情书
def test_lovelove_burns_one_card_before_play():
    """回归：此前开局不烧暗牌，牌堆比官方多 1 张。"""
    for players, left in (([1, 2], 13), ([1, 2, 3, 4], 11)):
        g = LoveLoveGame(players, seed=1)
        assert len(g.burned) == 1
        assert len(g.deck) == left
        dealt = sum(1 for u in g.alive if g.hand[u] is not None)
        assert len(g.deck) + len(g.burned) + dealt == 16


# ================================================================ 铁路
def test_tielu_draw_takes_the_last_single_card():
    g = TieluGame([1, 2], seed=2)
    g.ticket_deck = ["blue"]
    g.turn = 0
    hand_before = dict(g.hand[1])

    msgs = g.act(1, {"op": "draw"})
    assert g.ticket_deck == []
    assert g.hand[1]["blue"] == hand_before["blue"] + 1
    assert "摸到 1 张" in msgs[0] and "蓝" in msgs[0]
    assert g.players[g.turn] == 2


def test_tielu_empty_ticket_deck_rejects_without_mutation():
    g = TieluGame([1, 2], seed=2)
    g.ticket_deck = []
    g.turn = 0
    routes_before = copy.deepcopy(g.route_deck)
    hands_before = copy.deepcopy(g.hand)

    with pytest.raises(GameRuleError, match="车票卡已抽空"):
        g.act(1, {"op": "draw"})

    assert g.ticket_deck == [] and g.route_deck == routes_before
    assert g.hand == hands_before and g.turn == 0
