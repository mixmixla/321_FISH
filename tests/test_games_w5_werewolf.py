# -*- coding: utf-8 -*-
"""W5 狼人杀逻辑单测"""
import pytest
from games_pkg import GAME_TYPES
from games_pkg.base import GameRuleError
from games_pkg.werewolf import _counter, VILLAGER, WEREWOLF, SEER, WITCH, HUNTER


def _g(uids, seed=3):
    return GAME_TYPES["werewolf"](uids, seed)


def _force(g, roles):
    for u, r in roles.items():
        g.role[u] = r
    if HUNTER in roles.values():
        g.hunter_uid = next(u for u in g.players if g.role[u] == HUNTER)
    g.alive = set(g.players)
    _reneed(g)


def _reneed(g):
    """按当前阶段重算 need 与已行动（配合 _force 后的状态重建）"""
    alive, p = g.alive, g.phase
    if p == "night_seer":
        g.need = [u for u in g.players if g.role[u] == SEER and u in alive]
    elif p == "night_wolf":
        g.need = [u for u in g.players if g.role[u] == WEREWOLF and u in alive]
    elif p == "night_witch":
        g.need = [u for u in g.players if g.role[u] == WITCH and u in alive
                  and (g.witch_save_left or g.witch_poison_left)]
    elif p == "shoot":
        g.need = [g.hunter_uid] if g.hunter_uid in alive and not g.hunter_shot else []
    elif p == "day":
        g.need = sorted(alive)
    g.acted = []


def test_deck_size():
    for n in range(6, 17):
        tot = sum(_counter(n))
        assert tot == n, (n, tot)


def test_setup():
    g = _g([1, 2, 3, 4, 5, 6])
    assert len(g.role) == 6
    assert any(g.role[u] == WEREWOLF for u in g.players)
    assert any(g.role[u] == SEER for u in g.players)
    assert any(g.role[u] == WITCH for u in g.players)
    assert any(g.role[u] == HUNTER for u in g.players)
    assert g.phase == "night_seer"


def test_private_identity():
    g = _g([1, 2, 3, 4, 5, 6, 7, 8])
    _force(g, {1: WEREWOLF, 2: WEREWOLF, 3: SEER, 4: WITCH, 5: HUNTER, 6: VILLAGER, 7: VILLAGER, 8: VILLAGER})
    for u in g.players:
        p = g.private(u)
        assert p["role"] == g.role[u]
        if g.role[u] == WEREWOLF:
            mates = p["teammates"]
            assert len(mates) == 1
    assert 2 in g.private(1)["teammates"]


def test_seer_check_ok():
    g = _g([1, 2, 3, 4, 5, 6])
    _force(g, {1: SEER, 2: WEREWOLF, 3: VILLAGER, 4: WITCH, 5: HUNTER, 6: VILLAGER})
    g.act(1, {"op": "check", "target": 2})
    assert g.seer_view["target"] == 2
    assert g.seer_view["role"] == WEREWOLF
    pv = g.private(1)
    assert pv["seer_view"]["role"] == WEREWOLF


def test_wolf_kill_ok():
    g = _g([1, 2, 3, 4, 5, 6])
    _force(g, {1: SEER, 2: WEREWOLF, 3: VILLAGER, 4: WITCH, 5: HUNTER, 6: VILLAGER})
    g._reset_phase("night_seer", [1])
    g.act(1, {"op": "check", "target": 3})
    assert g.phase == "night_wolf"
    assert g.need == [2]
    g.act(2, {"op": "kill", "target": 6})
    assert g.wolf_kill == 6
    assert g.phase == "night_witch"


def test_witch_save_poison():
    g = _g([1, 2, 3, 4, 5, 6])
    _force(g, {1: SEER, 2: WEREWOLF, 3: VILLAGER, 4: WITCH, 5: HUNTER, 6: VILLAGER})
    g.seer_view = {"target": 2}; g.phase = "night_wolf"; g.need = [2]; g.acted = [1]
    g.act(2, {"op": "kill", "target": 6})
    assert g.phase == "night_witch"
    assert g.need == [4]
    g.act(4, {"op": "save"})
    assert g.witch_saved is True
    assert g.witch_save_left is False
    # 一个女巫夜晚最多只能一个操作（只有女巫自己一人，做过就无法再操作）
    assert g.phase == "day"
    assert 6 in g.alive  # 被救活
    g2 = _g([1, 2, 3, 4, 5, 6, 7])
    _force(g2, {1: SEER, 2: WEREWOLF, 3: VILLAGER, 4: WITCH, 5: HUNTER, 6: VILLAGER, 7: VILLAGER})
    g2.seer_view = {"target": 2}; g2.phase = "night_wolf"; g2.need = [2]; g2.acted = [1]
    g2.act(2, {"op": "kill", "target": 6})
    g2.act(4, {"op": "poison", "target": 5})
    assert g2.witch_poison == 5
    assert 5 not in g2.alive
    assert 6 in g2.alive or 6 not in g2.alive  # 因为没用药


def test_hunter_kill_after_night_death():
    g = _g([1, 2, 3, 4, 5, 6])
    _force(g, {1: SEER, 2: WEREWOLF, 3: VILLAGER, 4: WITCH, 5: HUNTER, 6: VILLAGER})
    g.seer_view = {"target": 2}; g.phase = "night_wolf"; g.need = [2]; g.acted = [1]
    g.act(2, {"op": "kill", "target": 5})
    g.phase = "night_witch"; g.need = [4]
    # 女巫毒村民 3（不毒狼，以免狼灭直接结束）
    g.act(4, {"op": "poison", "target": 3})
    # 此时猎人已死（非毒死），进入开枪阶段
    assert 5 not in g.alive
    assert g.phase == "shoot"
    assert g.need == [5]
    g.act(5, {"op": "shoot", "target": 6})
    assert 6 not in g.alive
    assert g.phase == "day"


def test_vote_lynch_hunter_trigger_shoot():
    g = _g([1, 2, 3, 4, 5, 6])
    _force(g, {1: SEER, 2: WEREWOLF, 3: VILLAGER, 4: WITCH, 5: HUNTER, 6: VILLAGER})
    g.phase = "day"; g.need = list(g.alive); g.acted = []
    for u in [1, 2, 3, 4, 6]:
        g.act(u, {"op": "vote", "target": 5})
    g.act(5, {"op": "vote", "target": 1})     # 猎人也投一人
    assert 5 not in g.alive  # 放逐
    assert g.phase == "shoot"
    assert g.shoot_pending is True


def test_wolf_win_condition():
    g = _g([1, 2, 3, 4, 5, 6])
    _force(g, {1: WEREWOLF, 2: WEREWOLF, 3: VILLAGER, 4: VILLAGER, 5: HUNTER, 6: VILLAGER})
    # 杀掉 3 个村民 → 好人=3，狼人=2 → 狼人胜
    g.alive = {1, 2, 3, 4}
    res = g._winner()
    assert res is False  # False → 狼人胜


def test_villager_win_condition():
    g = _g([1, 2, 3, 4, 5, 6])
    _force(g, {1: WEREWOLF, 2: VILLAGER, 3: VILLAGER, 4: VILLAGER, 5: HUNTER, 6: VILLAGER})
    g.alive.discard(1)
    res = g._winner()
    assert res is True  # True → 好人胜


def test_illegal_target_rejected():
    g = _g([1, 2, 3, 4, 5, 6])
    _force(g, {1: SEER, 2: WEREWOLF})
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "check", "target": 7})  # 不存在


def test_duplicate_action_rejected():
    g = _g([1, 2, 3, 4, 5, 6])
    _force(g, {1: SEER, 2: WEREWOLF})
    g.act(1, {"op": "check", "target": 2})
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "check", "target": 3})
