# -*- coding: utf-8 -*-
"""W5 阿瓦隆逻辑单测"""
import pytest
from games_pkg import GAME_TYPES
from games_pkg.base import GameRuleError
from games_pkg.avalon import LOYAL, MERLIN, ASSASSIN, MORDRED, QUESTS


def _g(uids, seed=3):
    return GAME_TYPES["avalon"](uids, seed)


def _force(g, roles):
    for u, r in roles.items():
        g.role[u] = r
    g.evil_uids = {u for u in g.players if g.role[u] in (ASSASSIN, MORDRED)}
    g.merlin_uid = next(u for u in g.players if g.role[u] == MERLIN)
    g.assassin_uid = next(u for u in g.players if g.role[u] == ASSASSIN)


def test_roles_dealt():
    g = _g([1, 2, 3, 4, 5])
    assert any(g.role[u] == MERLIN for u in g.players)
    assert any(g.role[u] == ASSASSIN for u in g.players)
    assert len(g.evil_uids) == 2      # n>=5 → 2 bad
    assert len(g.results) == 0
    # 梅林知道坏人有几人
    m = next(u for u in g.players if g.role[u] == MERLIN)
    assert len(g.private(m)["evil"]) == 2


def test_merlin_sees_evil():
    g = _g([1, 2, 3, 4, 5])
    _force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    p = g.private(1)
    assert set(p["evil"]) == {2, 3}
    a = g.private(2)
    assert set(a["evil"]) == {2, 3}
    assert a["teammates"] == [3]


def test_nominate_and_vote_approve():
    g = _g([1, 2, 3, 4, 5])
    _force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    g.phase = "teamvote"; g.need = [1, 2, 3, 4, 5]; g.acted = []
    for u in [1, 2, 3, 4]:
        g.act(u, {"op": "vote", "approve": True})
    assert g.phase == "teamvote"      # 4/5 > 半 → 通过
    g.act(5, {"op": "vote", "approve": True})
    assert g.phase == "quest"
    assert g.need == sorted(g.team) or set(g.need) == set(g.team)


def test_quest_success():
    g = _g([1, 2, 3, 4, 5])
    _force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    g.team = [1, 2]; g.phase = "quest"; g.need = [1, 2]; g.acted = []
    g.act(1, {"op": "finish", "success": True})
    g.act(2, {"op": "finish", "success": True})
    assert g.results == [True]
    assert g.phase == "nominate"      # 下一任务


def test_quest_fail_counts():
    g = _g([1, 2, 3, 4, 5])
    _force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    g.team = [1, 2]; g.phase = "quest"; g.need = [1, 2]; g.acted = []
    g.act(1, {"op": "finish", "success": True})
    g.act(2, {"op": "finish", "success": False})
    assert g.results == [False]


def test_three_fails_bad_wins():
    g = _g([1, 2, 3, 4, 5])
    _force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    g.results = [False, False]
    g.team = [1]; g.phase = "quest"; g.need = [1]; g.acted = []
    g.act(1, {"op": "finish", "success": True})   # 只剩 1 人团队但结果为...仅 1 人成功 → 仍成功
    # 需要 1 人投失败才失败：直接造另一个场景
    g2 = _g([1, 2, 3, 4, 5]); _force(g2, {1: MERLIN, 2: ASSASSIN})
    g2.results = [False, False]
    g2.team = [2]; g2.phase = "quest"; g2.need = [2]; g2.acted = []
    g2.act(2, {"op": "finish", "success": False})
    assert g2.winner is False
    assert g2.phase == "done"


def test_three_success_triggers_assassin():
    g = _g([1, 2, 3, 4, 5])
    _force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    g.results = [True, True]
    g.team = [3]; g.phase = "quest"; g.need = [3]; g.acted = []
    g.act(3, {"op": "finish", "success": True})
    assert g.phase == "final"
    assert g.need == [2]


def test_assassin_guess_correct_bad_wins():
    g = _g([1, 2, 3, 4, 5])
    _force(g, {1: MERLIN, 2: ASSASSIN})
    g.phase = "final"; g.need = [2]; g.acted = []
    g.act(2, {"op": "guess", "target": 1})          # 指对梅林
    assert g.winner is False
    assert g.phase == "done"


def test_assassin_guess_wrong_good_wins():
    g = _g([1, 2, 3, 4, 5])
    _force(g, {1: MERLIN, 2: ASSASSIN})
    g.phase = "final"; g.need = [2]; g.acted = []
    g.act(2, {"op": "guess", "target": 4})          # 指错
    assert g.winner is True
    assert g.phase == "done"


def test_vote_reject_changes_leader():
    g = _g([1, 2, 3, 4, 5])
    _force(g, {1: MERLIN, 2: ASSASSIN})
    g.leader_idx = 0
    g.phase = "teamvote"; g.need = [1, 2, 3, 4, 5]; g.acted = []; g.votes = {}
    leader = g._leader_uid()
    g.act(1, {"op": "vote", "approve": False})
    g.act(2, {"op": "vote", "approve": False})
    g.act(3, {"op": "vote", "approve": False})          # 3 反对 → 否决（还差 2 人投完）
    g.act(4, {"op": "vote", "approve": True})
    g.act(5, {"op": "vote", "approve": True})
    assert g.phase == "nominate"
    assert g.attempt == 1
    assert g._leader_uid() != leader or len(g.players) == 1


def test_illegal_nominate_size():
    g = _g([1, 2, 3, 4, 5])
    _force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    need_size = g._quest_size()
    g.leader_idx = 0                                   # 确保领袖是 1
    g.acted = []; g.need = [1]
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "navo", "team": [1]})          # 人数不符被拒
    assert need_size >= 2


def test_quest_sizes_valid():
    for n in range(4, 11):
        assert len(QUESTS[n]) == 5
        for sz in QUESTS[n]:
            assert 1 < sz <= n