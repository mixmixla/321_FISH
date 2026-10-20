# -*- coding: utf-8 -*-
"""第 3 批牌/骰类 P0 回归：快艇骰子、牛头王、21 点、达芬奇、德国心脏病、UNO。"""
import pytest

from games_pkg.base import GameRuleError
from games_pkg.blackjack import BlackjackGame
from games_pkg.davinci import DaVinCiGame
from games_pkg.halloween import HalloweenGame
from games_pkg.nimmt import NimmtGame
from games_pkg.uno import UnoGame
from games_pkg.yahtzee import CATS, YahtzeeGame


# ---------------------------------------------------------------- 快艇骰子
def test_yahtzee_must_roll_before_scoring():
    g = YahtzeeGame([1, 2], seed=1)
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "score", "cat": "1"})


def test_yahtzee_filling_one_category_does_not_skip_the_player():
    """回归：此前只看「1点」是否已填，填了 1 点就会把整回合跳掉。"""
    g = YahtzeeGame([1, 2], seed=1)
    g.act(1, {"op": "roll"})
    g.act(1, {"op": "score", "cat": "1"})
    g.act(2, {"op": "roll"})
    g.act(2, {"op": "score", "cat": "1"})
    assert g._cur() == 1
    msgs = g.act(1, {"op": "roll"})
    assert any("掷骰" in m for m in msgs)


def test_yahtzee_upper_bonus_is_awarded_only_once():
    g = YahtzeeGame([1, 2], seed=1)
    for c in "12345":
        g.scores[1][c] = 12
    g.totals[1] = 60
    g.rolled = True
    g.dice = [6, 6, 6, 6, 6]
    g.act(1, {"op": "score", "cat": "6"})        # 上区 90 → +35
    assert g.totals[1] == 60 + 30 + 35
    # 再记一个下区分类，不应重复发奖
    g.turn = 0
    g.rolled = True
    g.category = None
    g.dice = [1, 1, 1, 1, 1]
    g.act(1, {"op": "score", "cat": "chance"})
    assert g.totals[1] == 60 + 30 + 35 + 5


# ---------------------------------------------------------------- 牛头王
def test_nimmt_row_overflows_at_six_cards_and_resets_to_one():
    g = NimmtGame([1, 2], seed=1)
    g.table = [[1, 2, 3, 4, 5], [10, 11, 12, 13, 14],
               [20, 21, 22, 23, 24], [30, 31, 32, 33, 34]]
    g.hands = {1: [6], 2: [40]}
    g.choices = {1: 6, 2: 40}
    g.bulls = {1: 0, 2: 0}
    g._resolve()
    assert g.table[0] == [6]                     # 前 5 张被吞，新牌独占一行
    assert g.table[3] == [40]
    assert g.bulls[1] == 6                       # 1+1+1+1+2
    assert all(len(row) <= 5 for row in g.table)


# ---------------------------------------------------------------- 21 点
def test_blackjack_ace_value_is_order_independent():
    g = BlackjackGame([1, 2], seed=1)
    assert g._hand_value([("♠", "A"), ("♥", "9"), ("♦", "9")]) == 19
    assert g._hand_value([("♠", "A"), ("♥", "A"), ("♦", "9")]) == 21
    assert g._hand_value([("♠", "A"), ("♥", "A"), ("♦", "A")]) == 13
    assert g._hand_value([("♠", "K"), ("♥", "Q"), ("♦", "J")]) == 30


# ---------------------------------------------------------------- 达芬奇密码
def test_davinci_turn_skips_eliminated_players():
    g = DaVinCiGame([1, 2, 3], seed=1)
    g.hands.pop(2)
    g.dead.append(2)
    g.turn = 1
    g.order_uid = 0
    g._advance_turn()
    assert g.turn == 3                           # 跳过已出局的 2 号


def test_davinci_must_draw_before_guessing():
    g = DaVinCiGame([1, 2], seed=1)
    g.turn = 1
    g.order_uid = 0
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "guess", "target": 2, "pos": 0, "val": 0})


# ---------------------------------------------------------------- 德国心脏病
def test_halloween_last_card_ends_the_game_instead_of_sticking():
    g = HalloweenGame([1, 2], seed=1)
    g.turn = 1
    g.stack[1] = [0]
    g.have_flipped = False
    g.act(1, {"op": "flip"})
    g.act(1, {"op": "pass"})
    assert g.finished is True
    assert g.ended() is not None


# ---------------------------------------------------------------- UNO
def _uno_with_first(card):
    g = UnoGame([1, 2], seed=1)
    g.hands = {1: [], 2: []}
    g.discard = [card]
    g.current_color = card["color"]
    g.current_idx = 0
    g.direction = 1
    g.deck = [{"id": 1000 + i, "color": "red", "kind": "num", "value": 1}
              for i in range(20)]
    return g


def test_uno_first_draw2_hits_the_first_player_and_skips_them():
    card = {"id": 999, "color": "red", "kind": "action", "value": "draw2"}
    g = _uno_with_first(card)
    g._apply_first_card_effect()
    assert len(g.hands[1]) == 2                  # 首家抽 2
    assert len(g.hands[2]) == 0
    assert g.current_idx == 1                    # 首家被跳过


def test_uno_first_skip_and_reverse_skip_the_first_player():
    for value in ("skip", "reverse"):
        card = {"id": 999, "color": "red", "kind": "action", "value": value}
        g = _uno_with_first(card)
        g._apply_first_card_effect()
        assert g.current_idx == 1, value
        assert g.hands[1] == [] and g.hands[2] == []


def test_uno_draw2_and_wild4_hit_the_opponent_not_the_mover():
    """回归：功能牌抽牌必须给下家 uid，不能把下标当 uid（此前会给错人或 KeyError）。"""
    for card, n in (({"id": 9, "color": "red", "kind": "action", "value": "draw2"}, 2),
                    ({"id": 10, "color": None, "kind": "wild", "value": "wild4"}, 4)):
        g = UnoGame([1, 2], seed=1)
        g.hands = {1: [], 2: []}
        g.discard = [{"id": 1, "color": "red", "kind": "num", "value": 5}]
        g.current_idx = 0
        g.direction = 1
        g.deck = [{"id": 1000 + i, "color": "red", "kind": "num", "value": 1}
                  for i in range(20)]
        g._apply_action(card, [])
        assert len(g.hands[1]) == 0, card["value"]
        assert len(g.hands[2]) == n, card["value"]
