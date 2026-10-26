# -*- coding: utf-8 -*-
"""规则收尾 B 回归：璀璨宝石 10 枚宝石上限/掉线善后，铁路有限车票牌库/掉线善后。

每条回归用例的 docstring 用「回归：此前……」说明被修掉的错误行为。
"""
import copy

import pytest

from games_pkg.base import GameRuleError
from games_pkg.gemcity import COLORS, GemCityGame
from games_pkg.tielu import (COLORS as TICKET_COLORS, END_TARGET,
                             TICKET_PER_COLOR, TieluGame)


def _state(game):
    state = copy.deepcopy({k: v for k, v in vars(game).items() if k != "rng"})
    state["rng"] = game.rng.getstate()
    return state


def _gems(game, uid):
    return sum(game.tokens[uid][c] for c in COLORS)


def _free_card(pts=0, cost=None):
    return {"tier": 1, "disc": "s", "pts": pts,
            "cost": {c: (cost or {}).get(c, 0) for c in COLORS}}


# ================================================================ 璀璨宝石
def test_gemcity_tenth_gem_is_allowed():
    """回归：此前没有 10 枚宝石上限，玩家可以无限囤积宝石。"""
    g = GemCityGame([1, 2], seed=1)
    g.tokens[1].update(o=3, d=2, r=2)               # 7 枚
    g.tokens[1]["g"] = 2                            # 金币不计入
    g.turn = 0
    g.act(1, {"op": "take", "colors": ["o", "d", "r"]})
    assert _gems(g, 1) == 10
    assert g.players[g.turn] == 2

    g2 = GemCityGame([1, 2], seed=1)
    g2.tokens[1].update(o=4, d=4)                   # 8 枚
    g2.turn = 0
    g2.act(1, {"op": "take2", "color": "o"})
    assert _gems(g2, 1) == 10


def test_gemcity_overflow_is_returned_instead_of_rejected():
    """回归：此前 8 枚再取 3 会被直接拒绝；现在按官方允许取 1~3 颗，
    超过 10 枚的部分自动退回金库，避免玩家被上限锁死。"""
    g = GemCityGame([1, 2], seed=1)
    g.tokens[1].update(o=3, d=3, r=2)               # 8 枚，再取 3 → 11
    g.tokens[1]["g"] = 4
    g.turn = 0
    msgs = g.act(1, {"op": "take", "colors": ["o", "d", "r"]})
    assert _gems(g, 1) == 10
    assert "退回" in msgs[0]

    g2 = GemCityGame([1, 2], seed=1)
    g2.tokens[1].update(o=5, d=4)                   # 9 枚，再取 2 → 11
    g2.turn = 0
    msgs = g2.act(1, {"op": "take2", "color": "o"})
    assert _gems(g2, 1) == 10
    assert "退回" in msgs[0]


def test_gemcity_can_take_a_single_gem():
    """回归：此前只允许取 3 异色，9 枚时取 3 会超限，玩家没有任何取宝石动作可做。"""
    g = GemCityGame([1, 2], seed=1)
    g.tokens[1].update(o=4, d=4)                    # 8 枚
    g.turn = 0
    g.act(1, {"op": "take", "colors": ["o"]})
    assert _gems(g, 1) == 9


def test_gemcity_purchase_reduces_gems_below_limit():
    """回归：此前宝石不设上限，购卡后也无从回落；现在购卡扣款应自然低于 10。"""
    g = GemCityGame([1, 2], seed=1)
    g.tokens[1].update(o=6, d=4)                    # 恰好 10 枚
    g.turn = 0
    g.market[1][0] = _free_card(cost={"o": 3, "d": 2})
    g.act(1, {"op": "buy", "tier": 1, "idx": 0})
    assert _gems(g, 1) == 5
    assert g.cards[1][0]["cost"] == {c: (2 if c == "d" else 3 if c == "o" else 0)
                                    for c in COLORS}

    g.act(2, {"op": "take", "colors": ["o", "d", "r"]})
    g.act(1, {"op": "take", "colors": ["o", "d", "r"]})   # 5 + 3 = 8，可继续取
    assert _gems(g, 1) == 8


def test_gemcity_player_left_clears_seat_and_assets_without_touching_others():
    """回归：此前 player_left 为空实现，3~4 人局离场者的回合会永久卡住。"""
    g = GemCityGame([1, 2, 3], seed=1)
    g.tokens[2].update(o=2, d=1)
    g.tokens[2]["g"] = 2
    g.discount[2].update(o=1, s=2)
    g.cards[2] = [_free_card(pts=2)]
    g.reserved[2] = [_free_card()]
    g.score[2] = 5
    g.nobles_cards[2] = [3]
    g.turn = 1                                      # 轮到离场者
    bank_before = dict(g.bank)
    tokens_1 = dict(g.tokens[1])
    score_3 = g.score[3]

    msgs = g.player_left(2)
    assert msgs and "离开" in msgs[0]
    assert g.players == [1, 3]
    for book in (g.tokens, g.discount, g.cards, g.reserved,
                 g.score, g.nobles_cards):
        assert 2 not in book
    assert g.bank["o"] == bank_before["o"] + 2      # 宝石退回金库
    assert g.bank["d"] == bank_before["d"] + 1
    assert g.bank["g"] == bank_before["g"] + 2
    assert g.tokens[1] == tokens_1 and g.score[3] == score_3
    assert g.players[g.turn] == 3                   # 跳过离场者，轮到下家

    g.act(3, {"op": "take", "colors": ["o", "d", "r"]})
    assert g.players[g.turn] == 1
    assert "2" not in {str(u) for u in g.snapshot()["players"]}


def test_gemcity_player_left_during_final_round_keeps_one_turn_each():
    """回归：此前终局补回合列表含离场者，离场后剩余玩家无法正常补完并结算。"""
    g = GemCityGame([1, 2, 3, 4], seed=1)
    g.score[2] = 14
    g.reserved[2] = [_free_card(pts=1)]
    g.turn = 1                                      # 玩家 2 行动并触发终局
    g.act(2, {"op": "buy_res", "idx": 0})
    assert g.trigger_uid == 2
    assert g.players[g.turn] == 3 and g.extra == [4, 1]

    g.player_left(4)                                # 玩家 4 尚未补回合就离场
    assert g.players == [1, 2, 3]
    assert g.players[g.turn] == 3 and g.extra == [1]

    g.act(3, {"op": "take", "colors": ["o", "d", "r"]})
    assert g.players[g.turn] == 1                   # 玩家 1 仍各有一次补回合
    g.act(1, {"op": "take", "colors": ["o", "d", "r"]})
    assert g.winner == 2
    assert g.ended()["winner_uid"] == 2


def test_gemcity_two_player_leave_awards_remaining_player():
    g = GemCityGame([1, 2], seed=1)
    g.player_left(2)
    assert g.players == [1]
    assert g.winner == 1
    assert g.ended()["winner_uid"] == 1


# ================================================================ 铁路
def test_tielu_ticket_deck_is_finite_and_snapshot_reports_remaining():
    """回归：此前摸票从无限随机牌堆生成，同一玩家可以无限抽票。"""
    g = TieluGame([1, 2], seed=3)
    total = len(TICKET_COLORS) * TICKET_PER_COLOR - sum(
        sum(g.hand[u].values()) for u in g.players)
    assert len(g.ticket_deck) == total
    for c in TICKET_COLORS:
        in_hand = sum(g.hand[u][c] for u in g.players)
        assert g.ticket_deck.count(c) + in_hand == TICKET_PER_COLOR
    assert g.snapshot()["ticket_left"] == total

    g.turn = 0
    g.act(1, {"op": "draw"})
    assert len(g.ticket_deck) == total - 2
    assert g.snapshot()["ticket_left"] == total - 2
    assert sum(g.hand[1].values()) == 7             # 起手 5 + 摸 2
    assert g.snapshot()["route_left"] == len(g.route_deck)


def test_tielu_exhausted_ticket_deck_rejects_draw_atomically():
    """回归：此前车票卡无限生成，牌库概念不存在，抽空也不会被拒绝；
    牌库只剩 1 张时也应能摸走最后 1 张，只有真正为空才拒绝。"""
    g = TieluGame([1, 2], seed=3)
    g.ticket_deck = ["red"]
    g.turn = 0
    hand_before = dict(g.hand[1])
    msgs = g.act(1, {"op": "draw"})
    assert g.ticket_deck == []
    assert g.hand[1]["red"] == hand_before["red"] + 1
    assert "摸到 1 张" in msgs[0]
    assert g.players[g.turn] == 2

    g.turn = 0
    g.ticket_deck = []
    before = _state(g)
    with pytest.raises(GameRuleError, match="车票卡已抽空"):
        g.act(1, {"op": "draw"})
    assert _state(g) == before
    assert g.turn == 0


def test_tielu_player_left_skips_seat_and_drops_unsettled_tickets():
    """回归：此前 player_left 为空实现，离场者回合卡死且未结算票证仍参与终局计分。"""
    g = TieluGame([1, 2, 3], seed=4)
    g.tickets[2] = [[0, 7, 5]]
    g.turn = 1                                      # 轮到离场者
    deck_before = len(g.ticket_deck)
    hand_3 = dict(g.hand[3])
    score_1 = g._score(1)

    msgs = g.player_left(2)
    assert msgs and "离开" in msgs[0]
    assert g.players == [1, 3]
    assert 2 not in g.hand and 2 not in g.mine and 2 not in g.tickets
    assert len(g.ticket_deck) == deck_before        # 离场不额外发牌
    assert g._score(1) == score_1                   # 他人分数与线路不受影响
    assert g.players[g.turn] == 3                   # 跳过离场者

    g.act(3, {"op": "draw"})
    assert len(g.ticket_deck) == deck_before - 2
    assert sum(g.hand[3].values()) == sum(hand_3.values()) + 2
    assert "2" not in g.snapshot()["hand_count"]


def test_tielu_player_left_during_final_round_finishes_normally():
    """回归：此前终局补回合列表含离场者，剩余玩家补不完、终局无法结算。"""
    g = TieluGame([1, 2, 3, 4], seed=2)
    g.tickets = {u: [] for u in g.players}
    route = g.route_deck[0]
    length = route["length"]
    g.mine[2] = [(0, 1, END_TARGET - length)]       # 再认领一条即恰好 10 分
    g.hand[2][route["color"]] = length
    g.turn = 1
    g.act(2, {"op": "claim", "a": route["a"], "b": route["b"]})
    assert g.trigger_uid == 2
    assert g.players[g.turn] == 3 and g.extra == [4, 1]

    g.player_left(4)
    assert g.players == [1, 2, 3]
    assert g.players[g.turn] == 3 and g.extra == [1]

    g.act(3, {"op": "skip"})
    assert g.players[g.turn] == 1
    g.act(1, {"op": "skip"})
    assert g.winner == 2
    assert g.ended()["winner_uid"] == 2


def test_tielu_two_player_leave_awards_remaining_player():
    g = TieluGame([1, 2], seed=2)
    g.player_left(1)
    assert g.players == [2]
    assert g.winner == 2
    assert g.ended()["winner_uid"] == 2
