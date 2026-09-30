# -*- coding: utf-8 -*-
"""W5 一夜狼人逻辑单测"""
import pytest
from games_pkg import GAME_TYPES
from games_pkg.base import GameRuleError
from games_pkg.onewolf import _counter, VILLAGER, WEREWOLF, SEER, ROBBER, INSOMNIAC, NAME


def _g(uids, seed=3):
    return GAME_TYPES["onewolf"](uids, seed)


def _force(g, roles):
    """按 uid 依次指定 original+role，重建 need_act。roles: {uid: role}"""
    for u, r in roles.items():
        g.original[u] = r
        g.role[u] = r
    g.need_act = {u for u in g.players if g.original[u] in (SEER, ROBBER)}


def test_deck_size():
    for n in range(3, 11):
        tot = sum(_counter(n))
        assert tot == n + 3, (n, tot)


def test_setup():
    g = _g([1, 2, 3])
    assert len(g.role) == 3
    assert len(g.center) == 3
    assert g.phase == "night"


def test_find_special():
    g = _g([1, 2, 3, 4, 5], seed=1)
    assert any(g.original[u] == SEER for u in g.players)  # 必有预言家


def test_private_identity():
    g = _g([1, 2, 3, 4, 5], seed=1)
    for u in g.players:
        p = g.private(u)
        assert p["role"] == g.role[u]
        assert p["name"] == NAME[g.role[u]]


def test_private_wolf_knows_team():
    g = _g([1, 2, 3, 4, 5, 6], seed=7)
    g.original[1] = WEREWOLF
    g.original[4] = WEREWOLF
    g.role[1] = WEREWOLF
    g.role[4] = WEREWOLF
    p = g.private(1)
    assert p["name"] == "狼人"
    assert p["teammates"] == [4]


def test_seer_look_one():
    g = _g([1, 2, 3, 4, 5], seed=1)
    _force(g, {1: SEER, 2: WEREWOLF, 3: VILLAGER, 4: VILLAGER, 5: VILLAGER})
    g.act(1, {"op": "peek", "look_one": 2})
    assert 1 in g.acted
    assert g._seer_view[1] == (2, WEREWOLF)
    assert g.private(1)["seer_view"]["role"] == WEREWOLF


def test_robber_swap():
    g = _g([1, 2, 3, 4, 5], seed=2)
    _force(g, {1: ROBBER, 2: WEREWOLF, 3: VILLAGER, 4: VILLAGER, 5: VILLAGER})
    g.role[2] = VILLAGER  # WEREWOLF 只在 original
    g.act(1, {"op": "swap", "rob": 2})
    assert g.role[1] == VILLAGER       # 强盗抢到村民身份
    assert g.role[2] == ROBBER         # 被换者变成强盗
    assert g._rob_seen[1] == VILLAGER


def test_villager_cannot_act():
    g = _g([1, 2, 3])
    _force(g, {1: VILLAGER})
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "peek"})


def test_all_act_progresses_to_vote():
    g = _g([1, 2, 3, 4, 5], seed=1)
    _force(g, {1: SEER, 2: ROBBER, 3: VILLAGER, 4: VILLAGER, 5: VILLAGER})
    g.act(1, {"op": "peek", "look_one": 3})
    assert g.phase == "night"          # 强盗还没行动
    g.act(2, {"op": "swap", "rob": 5})
    assert g.phase == "vote"           # 全员行动完毕 → 进入投票


def test_vote_outs_wolf_village_win():
    g = _g([1, 2, 3, 4, 5], seed=1)
    _force(g, {1: VILLAGER, 2: WEREWOLF, 3: VILLAGER, 4: VILLAGER, 5: VILLAGER})
    g.phase = "vote"
    # 每人投 2（狼人），但投自己的人换目标
    for u in g.players:
        t = 2 if u != 2 else 2
        if u == 2:
            t = 1
        g.act(u, {"op": "vote", "target": t})
    assert g.phase == "result"
    assert g.winner is True            # 狼人出局 → 好人胜
    assert g.ended()["detail"]


def test_vote_outs_villager_wolf_win():
    g = _g([1, 2, 3, 4, 5], seed=1)
    _force(g, {1: VILLAGER, 2: WEREWOLF, 3: VILLAGER, 4: VILLAGER, 5: VILLAGER})
    g.phase = "vote"
    # 2 带动投 1（村民）
    for u in g.players:
        t = 2 if u == 2 else 1
        g.act(u, {"op": "vote", "target": t})
    assert g.winner is False           # 狼人存活 → 狼人胜


def test_vote_duplicate_rejected():
    g = _g([1, 2, 3, 4, 5], seed=1)
    g.phase = "vote"
    g.act(1, {"op": "vote", "target": 2})
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "vote", "target": 3})