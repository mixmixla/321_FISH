# -*- coding: utf-8 -*-
"""W5 骗子酒馆逻辑单测"""
import pytest
from games_pkg import GAME_TYPES
from games_pkg.base import GameRuleError
from games_pkg.liar import MAX_DRINK, HAND


def _g(uids, seed=3):
    return GAME_TYPES["liar"](uids, seed)


def _card(g, uid, claim=None):
    """出 teléo一张手牌报数 claim（默认真报）"""
    hand = g.hand[uid]
    val = hand[0]
    return g.act(uid, {"op": "play", "card": val, "claim": val if claim is None else claim})


def test_setup():
    g = _g([1, 2, 3])
    assert g.phase == "play"
    assert all(len(g.hand[u]) == HAND for u in g.players)
    assert g.pending is None
    assert g._turn_uid() == 1


def test_play_sets_pending():
    g = _g([1, 2, 3])
    g.act(1, {"op": "play", "card": g.hand[1][0], "claim": 3})
    assert g.pending["uid"] == 1
    assert g.pending["claim"] == 3
    assert g._turn_uid() == 2


def test_play_illegal_card():
    g = _g([1, 2, 3])
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "play", "card": 9, "claim": 3})   # 手牌里没有 9


def test_challenge_no_pending_rejected():
    g = _g([1, 2, 3])
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "challenge"})                     # 还没人出牌


def test_not_your_turn():
    g = _g([1, 2, 3])
    with pytest.raises(GameRuleError):
        g.act(2, {"op": "play", "card": g.hand[2][0], "claim": 1})


def test_challenge_truth_claimer_drinks():
    g = _g([1, 2, 3], seed=1)
    val = g.hand[1][0]
    g.act(1, {"op": "play", "card": val, "claim": val})   # 说真话
    d0 = g.drink[2]
    g.act(2, {"op": "challenge"})                         # 挑战者猜错 → 2 喝
    assert g.drink[2] == d0 + 1
    assert g.pending is None


def test_challenge_liar_claimer_drinks():
    g = _g([1, 2, 3], seed=1)
    val = g.hand[1][0]
    lie = (val + 1) % 10
    if lie == val:
        lie = (val + 2) % 10
    g.act(1, {"op": "play", "card": val, "claim": lie})   # 说谎
    d1 = g.drink[1]
    g.act(2, {"op": "challenge"})                         # 1 被戳穿 → 1 喝
    assert g.drink[1] == d1 + 1
    assert g.pending is None


def test_drunk_eliminated_and_winner():
    g = _g([1, 2], seed=2)
    # 让玩家 2 连续被罚到出局
    for _ in range(MAX_DRINK):
        # 玩家1出真牌，玩家2挑战失败
        val = g.hand[1][0]
        g.act(1, {"op": "play", "card": val, "claim": val})
        g.act(2, {"op": "challenge"})
    assert 2 in g.out
    assert g.winner == 1
    assert g.ended()["winner_uid"] == 1


def test_private_hand():
    g = _g([1, 2, 3], seed=1)
    p = g.private(1)
    assert p["hand"] == sorted(g.hand[1])
    assert g.private(999) is None


def test_snapshot_health():
    g = _g([1, 2, 3], seed=4)
    s = g.snapshot()
    assert s["turn"] == 1
    assert str(3) in s["drink"]
    assert s["done"] is False


def test_ended_none_during_game():
    g = _g([1, 2, 3])
    assert g.ended() is None