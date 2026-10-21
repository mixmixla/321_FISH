# -*- coding: utf-8 -*-
"""规则收尾 D 回归：阿瓦隆连续否决/忠臣失败票、山屋探索独存、抽牌配对动作校验、
COC 技能值服务端权威。

每条回归用例的 docstring 均以「回归：此前……」说明修复前的行为。
"""
import pytest

from games_pkg.avalon import ASSASSIN, LOYAL, MERLIN, MORDRED, AvalonGame
from games_pkg.base import GameRuleError
from games_pkg.betrayal import BetrayalGame
from games_pkg.coc import CocGame
from games_pkg.matchpairs import MatchPairsGame


# ================================================================ 阿瓦隆
def _av_force(g, roles):
    for u, r in roles.items():
        g.role[u] = r
    g.evil_uids = {u for u in g.players if g.role[u] in (ASSASSIN, MORDRED)}
    g.merlin_uid = next(u for u in g.players if g.role[u] == MERLIN)
    g.assassin_uid = next(u for u in g.players if g.role[u] == ASSASSIN)


def _reject_team(g):
    """让当前领袖提名合法团队，然后全体否决一次。"""
    leader = g._leader_uid()
    size = g._quest_size()
    team = [u for u in g.players if u != leader][:size - 1] + [leader]
    g.act(leader, {"op": "nominate", "team": team})
    for u in list(g.players):
        g.act(u, {"op": "vote", "approve": False})


def test_avalon_fifth_consecutive_rejection_ends_with_evil_win():
    """回归：此前连续 5 次组队被否决不会终局，领袖可以无限重提，对局卡死。"""
    g = AvalonGame([1, 2, 3, 4, 5], seed=3)
    _av_force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    for i in range(4):
        _reject_team(g)
        assert g.rejections == i + 1
        assert g.ended() is None
    _reject_team(g)
    e = g.ended()
    assert e is not None and e["winner_uid"] is None
    assert e["detail"] == "连续 5 次组队被否决，邪恶方获胜"
    assert g.phase == "done" and g.snapshot()["rejections"] == 5
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "nominate", "team": [1, 2]})


def test_avalon_approved_team_resets_rejection_streak():
    """回归：此前否决计数只增不清零，任意 5 次历史上的否决都会误判邪恶方获胜。"""
    g = AvalonGame([1, 2, 3, 4, 5], seed=3)
    _av_force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    for _ in range(4):
        _reject_team(g)
    assert g.rejections == 4 and g.ended() is None
    leader = g._leader_uid()
    size = g._quest_size()
    team = [u for u in g.players if u != leader][:size - 1] + [leader]
    g.act(leader, {"op": "nominate", "team": team})
    for u in list(g.players):
        g.act(u, {"op": "vote", "approve": True})
    assert g.phase == "quest" and g.rejections == 0
    assert g.ended() is None


def test_avalon_loyal_fail_vote_rejected_atomically():
    """回归：此前忠臣也能投失败票，任务结果可被好人方自己破坏。"""
    g = AvalonGame([1, 2, 3, 4, 5], seed=3)
    _av_force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    g.phase, g.team, g.need, g.acted = "quest", [1, 2], [1, 2], []
    with pytest.raises(GameRuleError, match="忠臣不能投失败票"):
        g.act(1, {"op": "finish", "success": False})     # 梅林属好人阵营
    assert g.quest_votes == {} and g.acted == []
    assert g.phase == "quest" and g.results == []
    g.act(1, {"op": "finish", "success": True})
    g.act(2, {"op": "finish", "success": False})         # 刺客投失败仍允许
    assert g.results == [False]


# ================================================================ 山屋惊魂
def test_betrayal_explore_solo_winner_after_player_left():
    """回归：此前探索阶段玩家掉线至只剩 1 人时没有终局，剩余玩家无事可做。"""
    g = BetrayalGame([1, 2, 3], seed=1)
    g.player_left(1)
    assert g.ended() is None
    g.player_left(2)
    e = g.ended()
    assert e is not None and e["winner_uid"] == 3
    assert "独自逃出山屋" in e["detail"]
    assert g._solo_winner == 3
    assert g.ended() == e                               # 重复查询不重复结算
    with pytest.raises(GameRuleError):
        g.act(3, {"end": True})


def test_betrayal_explore_solo_winner_after_stat_zero():
    """回归：此前探索阶段属性归零致死只剩 1 人时没有终局，山屋直接卡在探索。"""
    g = BetrayalGame([1, 2, 3], seed=1)
    g.player_left(3)
    assert g.ended() is None
    g.event_deck = ["地板坍塌"]                         # 速度 -1
    idx = next(i for i, (_, k) in enumerate(g.tiles) if k == "event")
    g.tiles.append(g.tiles.pop(idx))
    g.turn_idx = 0
    g.pos[1] = (900, 0)
    g.stats[1]["speed"] = 1
    g.act(1, {"move": "right"})
    assert 1 in g.dead
    e = g.ended()
    assert e is not None and e["winner_uid"] == 2
    assert "独自逃出山屋" in e["detail"]
    assert g.ended() == e
    with pytest.raises(GameRuleError):
        g.act(2, {"end": True})


# ================================================================ 抽牌配对
def test_matchpairs_illegal_action_rejected_without_state_change():
    """回归：此前 act 完全不校验动作内容，任意 op 都会被当成摸牌处理。"""
    g = MatchPairsGame([1, 2, 3], seed=1)
    g.hands = {1: [(5, "♠")], 2: [(7, "♥")], 3: [(9, "♦")]}
    g.safe, g.turn, g.loser_uid = set(), 0, None
    before = (dict(g.hands), set(g.safe), g.turn)
    for bad in ({"op": "steal"}, {}, {"draw": False},
                {"draw": True, "target": 99}):
        with pytest.raises(GameRuleError):
            g.act(1, bad)
        assert (g.hands, g.safe, g.turn) == before
    with pytest.raises(GameRuleError):
        g.act(2, {"draw": True})                        # 非本人回合
    assert (g.hands, g.safe, g.turn) == before
    g.act(1, {"draw": True})
    assert 2 in g.safe and g.hands[2] == []
    assert g.hands[1] == [(5, "♠"), (7, "♥")]


def test_matchpairs_empty_hand_turn_skipped_automatically():
    """回归：此前轮次停在已空手的玩家身上时，他仍可摸牌，或整局无人能行动。"""
    g = MatchPairsGame([1, 2, 3], seed=1)
    g.hands = {1: [(5, "♠")], 2: [], 3: [(7, "♥")]}
    g.safe, g.turn, g.loser_uid = {2}, 1, None
    assert g.snapshot()["turn_uid"] == 3                # 自动跳到下一位有牌者
    with pytest.raises(GameRuleError):
        g.act(2, {"draw": True})
    assert g.turn == 2
    g.act(3, {"draw": True})
    assert g.hands[2] == [] and 2 in g.safe
    assert g.hands[1] == [] and 1 in g.safe


# ================================================================ COC
class _FixedRng:
    def __init__(self, roll):
        self.roll = roll

    def randint(self, a, b):
        return self.roll


def _coc_started():
    g = CocGame([1, 2], seed=2)
    for u, c in zip(g.players, g.chars):
        g.act(u, {"op": "choose_card", "card_id": c["id"]})
    g.act(1, {"op": "begin"})
    return g


def test_coc_client_base_ignored_for_unlisted_skill():
    """回归：此前客户端传 base 即可把任意未列出技能抬到高值，检定可作弊。"""
    g = _coc_started()
    g.rng = _FixedRng(60)
    g.act(1, {"op": "check", "skill": "伪造技能", "base": 95})
    assert g.last_check["level"] == "失败"              # 60 > 未列出技能的 50 基准
    g.rng = _FixedRng(60)
    g.act(1, {"op": "check", "skill": "另一个技能", "base": 99})
    assert g.last_check["level"] == "失败"


def test_coc_card_skill_value_cannot_be_overridden_by_base():
    """回归：此前客户端可用 base 覆盖角色卡上的技能值，绕过卡面设定。"""
    g = _coc_started()
    skill, val = max(g.assigned[1]["sig"].items(), key=lambda kv: kv[1])
    assert val > 60
    g.rng = _FixedRng(60)
    g.act(1, {"op": "check", "skill": skill, "base": 1})
    assert g.last_check["level"] == "普通成功"          # 仍按卡面值判定（base=1 会判失败）
