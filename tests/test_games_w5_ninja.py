# -*- coding: utf-8 -*-
"""W5 忍者之夜逻辑单测"""
import pytest
from games_pkg import GAME_TYPES
from games_pkg.base import GameRuleError
from games_pkg.ninja import HP


def _g(uids, seed=3):
    return GAME_TYPES["ninja"](uids, seed)


def _pick(g, uid, move, target=None):
    a = {"op": "move", "move": move}
    if target is not None:
        a["target"] = target
    return g.act(uid, a)


def test_setup():
    g = _g([1, 2, 3, 4])
    assert g.phase == "pick"
    assert all(g.hp[u] == HP for u in g.players)
    assert g.alive == {1, 2, 3, 4}


def test_resolve_after_all_pick():
    g = _g([1, 2, 3], seed=1)
    _pick(g, 1, "attack", 2)
    assert g.phase == "pick"          # 未齐
    _pick(g, 2, "guard")
    _pick(g, 3, "attack", 1)
    assert g.phase == "resolve"
    # 1 攻击 2，但 2 防御 → 1 反伤；3 攻击 1（非防御）→ 1 再伤
    assert g.hp[1] == HP - 2
    assert g.hp[2] == HP              # 防御者无损


def test_attack_hits_unguarded():
    g = _g([1, 2, 3], seed=2)
    _pick(g, 1, "attack", 2)          # 2 未防御
    _pick(g, 2, "attack", 3)
    _pick(g, 3, "guard")
    assert g.phase == "resolve"
    assert g.hp[2] == HP - 2          # 1 攻击 2(未防) + 2 攻击防住的 3 反伤
    assert g.hp[3] == HP              # 3 防御无损
    assert g.hp[1] == HP              # 1 攻击未防御目标，自身无损


def test_guard_counterattacks_attacker():
    g = _g([1, 2, 3], seed=2)
    _pick(g, 1, "attack", 2)
    _pick(g, 2, "guard")              # 2 防御 → 1 反伤
    _pick(g, 3, "guard")
    assert g.phase == "resolve"
    assert g.hp[1] == HP - 1          # 攻击者反被反伤
    assert g.hp[2] == HP              # 防御者无损


def test_mutual_attack_both_hurt():
    g = _g([1, 2, 3], seed=3)
    _pick(g, 1, "attack", 2)
    _pick(g, 2, "attack", 1)
    _pick(g, 3, "guard")
    assert g.hp[1] == HP - 1
    assert g.hp[2] == HP - 1
    assert g.hp[3] == HP


def test_elimination_and_win():
    g = _g([1, 2, 3, 4], seed=4)
    # 集体低血：一轮 1/2/3/4 循环互伤，仅 4 多血存活
    g.hp = {1: 1, 2: 1, 3: 1, 4: 5}
    _pick(g, 1, "attack", 2)
    _pick(g, 2, "attack", 3)
    _pick(g, 3, "attack", 4)
    _pick(g, 4, "attack", 1)
    assert g.phase == "resolve"
    assert g.alive == {4}
    assert g.winner == 4
    assert g.ended()["winner_uid"] == 4
    assert "存活" in g.ended()["detail"]


def test_dead_cannot_act():
    g = _g([1, 2, 3, 4], seed=5)
    g.alive = {1, 2, 3}              # 4 已出局
    g.hp[4] = 0
    with pytest.raises(GameRuleError):
        g.act(4, {"op": "move", "move": "attack", "target": 1})


def test_next_round():
    g = _g([1, 2, 3], seed=6)
    _pick(g, 1, "guard")
    _pick(g, 2, "guard")
    _pick(g, 3, "guard")
    assert g.phase == "resolve"
    g.act(1, {"op": "next"})
    assert g.phase == "pick"
    assert g.round == 2
    assert g.moves == {}


def test_next_wrong_phase():
    g = _g([1, 2, 3])
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "next"})      # pick 阶段不能 next


def test_illegal_move():
    g = _g([1, 2, 3])
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "move", "move": "sleep"})


def test_attack_dead_target():
    g = _g([1, 2, 3, 4], seed=7)
    g.alive = {1, 2, 3}              # 4 已出局
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "move", "move": "attack", "target": 4})


def test_private_hp():
    g = _g([1, 2, 3])
    p = g.private(1)
    assert p["hp"] == HP
    assert g.private(999) is None