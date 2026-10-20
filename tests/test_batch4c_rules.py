# -*- coding: utf-8 -*-
"""批次 4c 桌游 P0 规则回归：四季物语、波兰大选、山屋惊魂、狼人杀、阿瓦隆、一夜狼人。

每条回归用例都在 docstring 标注「回归：此前……」，并尽量用固定 seed 跑通
「阶段推进 → 终局」的可复现流程。
"""
import pytest

from games_pkg.avalon import (ASSASSIN, LOYAL, MERLIN, MORDRED,
                              AvalonGame)
from games_pkg.base import GameRuleError
from games_pkg.betrayal import BetrayalGame
from games_pkg.bolan import BolanGame
from games_pkg.onewolf import (ROBBER, SEER, VILLAGER, WEREWOLF,
                               OneNightWolfGame)
from games_pkg.siji import MAX_ENGINE, SijiGame
from games_pkg.werewolf import (HUNTER, SEER as WW_SEER,
                                VILLAGER as WW_VILLAGER, WEREWOLF as WW_WOLF,
                                WITCH, WerewolfGame)


# ================================================================ 四季物语
def _siji_take_action(g):
    """给当前玩家选一个合法动作：优先打牌，满 6 张后激活未用卡。"""
    uid = g.players[g.turn]
    if len(g.engine[uid]) < MAX_ENGINE:
        return uid, {"op": "play", "idx": 0}
    idx = next((i for i, c in enumerate(g.engine[uid]) if not c["played"]), None)
    if idx is not None:
        return uid, {"op": "activate", "idx": idx}
    return uid, {"op": "convert"}


def test_siji_play_without_crystal_does_not_eat_the_card():
    """回归：此前先把手牌 pop 掉再校验水晶，失败会永久丢掉一张牌并留下半状态。"""
    g = SijiGame([1, 2], seed=1)
    idx = next(i for i, c in enumerate(g.hand[1]) if c["cost"] > 0)
    g.crystal[1] = 0
    before_hand = [dict(c) for c in g.hand[1]]
    before_turn = g.turn
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "play", "idx": idx})
    assert g.hand[1] == before_hand
    assert g.engine[1] == [] and g.turn == before_turn


def test_siji_engine_cards_reset_at_new_season():
    """回归：此前季节切换不重置 played，引擎卡从第二季起永久不可再激活。"""
    g = SijiGame([1, 2], seed=1)
    g.engine[1] = [{"id": 0, "name": "晶田", "kind": "crystal",
                    "cost": 0, "out": 2, "played": True}]
    g.engine[2] = [{"id": 1, "name": "金窖", "kind": "apple",
                    "cost": 1, "out": 2, "played": True}]
    g._next_season()
    assert g.season == 2
    assert all(not c["played"] for u in g.players for c in g.engine[u])
    before = g.crystal[1]
    g.act(1, {"op": "activate", "idx": 0})       # 新一季可再次生产
    assert g.crystal[1] == before + 2


def test_siji_player_left_removes_seat_and_advances_turn():
    """回归：此前玩家掉线仍占着回合，剩余玩家会永久等待该座位。"""
    g = SijiGame([1, 2, 3], seed=1)
    g.turn = 1                                   # 2 号当前行动
    g.player_left(2)
    assert 2 not in g.players and 2 not in g.hand
    assert g.players[g.turn] == 3
    idx = next(i for i, c in enumerate(g.hand[3]) if c["cost"] <= g.crystal[3])
    g.act(3, {"op": "play", "idx": idx})
    assert g.players[g.turn] == 1


def test_siji_three_seasons_reach_end():
    """三季行动推进到终局，并在换季时验证引擎卡全部恢复。"""
    g = SijiGame([1, 2], seed=1)
    g.crystal = {u: 99 for u in g.players}       # 排除资源不足对流程的干扰
    saw_season2 = False
    for _ in range(40):
        if g.ended():
            break
        uid, action = _siji_take_action(g)
        g.act(uid, action)
        if g.season == 2 and not saw_season2:
            saw_season2 = True
            assert all(not c["played"]
                       for p in g.players for c in g.engine[p])
    assert saw_season2
    assert g.season == 3 and g.ended() is not None
    assert g.ended()["winner_uid"] in g.players


# ================================================================ 波兰大选
def test_bolan_devote_advances_turn():
    """回归：此前弃子翻倍不调用 _advance，同一玩家可无限行动、其他人永远轮不到。"""
    g = BolanGame([1, 2], seed=1)
    g.act(1, {"op": "devote", "r": 0})
    assert g.board[0][1] == 2
    assert g.players[g.turn] == 2
    g.act(2, {"op": "place", "r": 0})
    assert g.election_round == 2                 # 两人各行动一次 → 完成一轮选举


def test_bolan_devote_bad_region_rolls_back():
    """回归：此前弃子不校验选区范围，越界会直接 KeyError 并可能留下半状态。"""
    g = BolanGame([1, 2], seed=1)
    before = (g.influence[1], dict(g.board[0]), g.turn)
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "devote", "r": 99})
    assert (g.influence[1], g.board[0], g.turn) == before


def test_bolan_influence_exhaustion_reaches_end():
    """反复投放直到某位玩家影响力耗尽，触发终局并产生赢家。"""
    g = BolanGame([1, 2], seed=1)
    for _ in range(30):
        if g.ended():
            break
        g.act(g.players[g.turn], {"op": "place", "r": 0})
    assert g.ended() is not None
    assert g.winner in g.players
    assert any(v == 0 for v in g.influence.values())


def test_bolan_player_left_moves_turn_and_clears_pieces():
    """回归：此前玩家掉线后仍保留影响力/棋子，且轮到该座位时无人能行动。"""
    g = BolanGame([1, 2, 3], seed=1)
    g.board[0][2] = 3
    g.turn = 1
    g.player_left(2)
    assert 2 not in g.players and 2 not in g.board[0] and 2 not in g.influence
    assert g.players[g.turn] == 3


# ================================================================ 山屋惊魂
class _Rng:
    """确定性随机：randint 恒 1、choice 取首个。"""
    def randint(self, a, b):
        return 1

    def choice(self, seq):
        return seq[0]

    def shuffle(self, x):
        pass

    def sample(self, seq, n):
        return list(seq)[:n]


def _bring_tile(g, kind):
    idx = next(i for i, (_, k) in enumerate(g.tiles) if k == kind)
    g.tiles.append(g.tiles.pop(idx))


def _force_haunt(g):
    g.rng = _Rng()
    for i in range(8):
        _bring_tile(g, "omen")
        cur = g.players[g.turn_idx]
        g.pos[cur] = (900, i)
        g.act(cur, {"move": "right"})
        if g.phase == "haunt":
            return
    assert False, "8 枚预兆必触发惊魂"


def test_betrayal_dead_player_cannot_take_a_turn():
    """回归：此前只要轮到阵亡玩家的座位，act 仍会放行，死人可以继续行动。"""
    g = BetrayalGame([1, 2, 3], seed=1)
    g.dead.add(1)
    g.turn_idx = 0
    with pytest.raises(GameRuleError):
        g.act(1, {"end": True})
    assert g.players[g.turn_idx] == 1 and g.dead == {1}


def test_betrayal_player_left_skips_dead_successor():
    """回归：此前当前玩家掉线后固定把回合交给下一位，哪怕下一位已阵亡。"""
    g = BetrayalGame([1, 2, 3, 4], seed=1)
    g.dead.add(2)
    g.turn_idx = 0
    g.player_left(1)
    assert g.players == [2, 3, 4]
    assert g.players[g.turn_idx] == 3
    g.act(3, {"end": True})                     # 活着的继任者可以正常行动


def test_betrayal_haunt_to_kill_traitor_reaches_end():
    """惊魂阶段击杀叛徒 → 幸存者胜利，覆盖探索→惊魂→终局流程。"""
    g = BetrayalGame([1, 2, 3], seed=7)
    _force_haunt(g)
    t = g.haunt["traitor"]
    v = next(u for u in g.players if u != t)
    g.rng = _Rng()
    g.pos[t] = g.pos[v] = (0, 0)
    g.turn_idx = g.players.index(v)
    g.steps_left = 3
    g.attack_used = False
    g.stats[v]["might"] = 5
    g.stats[t]["might"] = 1
    g.act(v, {"attack": t})
    assert t in g.dead
    e = g.ended()
    assert e and "叛徒" in e["detail"]


# ================================================================ 狼人杀
def _ww_force(g, roles):
    for u, r in roles.items():
        g.role[u] = r
    if HUNTER in roles.values():
        g.hunter_uid = next(u for u in g.players if g.role[u] == HUNTER)
    g.alive = set(g.players)


def test_werewolf_day_skips_dead_seer_into_wolf_phase():
    """回归：此前预言家出局后仍进入 night_seer 且 need 为空，夜晚永远无法推进。"""
    g = WerewolfGame([1, 2, 3, 4, 5, 6], seed=3)
    _ww_force(g, {1: WW_WOLF, 2: WW_VILLAGER, 3: WW_VILLAGER,
                  4: WITCH, 5: HUNTER, 6: WW_VILLAGER})
    g.phase, g.need, g.acted = "day", list(g.alive), []
    for u in g.players:
        g.act(u, {"op": "vote", "target": 2})
    assert g.night == 2
    assert g.phase == "night_wolf" and g.need == [1]


def test_werewolf_night_without_witch_resolves_to_day():
    """回归：此前女巫出局后 night_witch 无人可行动，夜晚结算永远等不到。"""
    g = WerewolfGame([1, 2, 3, 4, 5, 6], seed=3)
    _ww_force(g, {1: WW_SEER, 2: WW_WOLF, 3: WW_VILLAGER,
                  4: WW_VILLAGER, 5: HUNTER, 6: WW_VILLAGER})
    g.phase, g.need, g.acted = "night_seer", [1], []
    g.act(1, {"op": "check", "target": 2})
    assert g.phase == "night_wolf" and g.need == [2]
    g.act(2, {"op": "kill", "target": 3})
    assert g.phase == "day"
    assert 3 not in g.alive


def test_werewolf_witch_without_potions_is_skipped():
    """回归：此前女巫两瓶药都用完后仍会停在 night_witch，整晚卡死。"""
    g = WerewolfGame([1, 2, 3, 4, 5, 6], seed=3)
    _ww_force(g, {1: WW_SEER, 2: WW_WOLF, 3: WITCH,
                  4: WW_VILLAGER, 5: HUNTER, 6: WW_VILLAGER})
    g.witch_save_left = g.witch_poison_left = False
    g.phase, g.need, g.acted = "night_seer", [1], []
    g.act(1, {"op": "check", "target": 2})
    g.act(2, {"op": "kill", "target": 4})
    assert g.phase == "day"
    assert 4 not in g.alive


def test_werewolf_two_nights_and_days_reach_good_win():
    """完整流程：救人 → 白天放逐 → 毒杀猎人（不能开枪）→ 放逐狼人 → 好人胜。"""
    g = WerewolfGame([1, 2, 3, 4, 5, 6], seed=3)
    _ww_force(g, {1: WW_WOLF, 2: WW_SEER, 3: WITCH,
                  4: HUNTER, 5: WW_VILLAGER, 6: WW_VILLAGER})
    g.phase, g.need, g.acted = "night_seer", [2], []
    g.act(2, {"op": "check", "target": 1})
    g.act(1, {"op": "kill", "target": 5})
    g.act(3, {"op": "save"})
    assert g.phase == "day" and 5 in g.alive
    for u in list(g.alive):
        g.act(u, {"op": "vote", "target": 5})
    assert 5 not in g.alive and g.night == 2
    g.act(2, {"op": "check", "target": 1})
    g.act(1, {"op": "kill", "target": 6})
    g.act(3, {"op": "poison", "target": 4})
    assert g.phase == "day" and 4 not in g.alive and 6 not in g.alive
    for u in list(g.alive):
        g.act(u, {"op": "vote", "target": 1})
    e = g.ended()
    assert e and "好人" in e["detail"]


def test_werewolf_snapshot_hides_roles_private_is_per_player():
    """身份/查验结果只走私密通道，公开快照不出现 role/seer_view。"""
    g = WerewolfGame([1, 2, 3, 4, 5, 6], seed=3)
    seer = next(u for u in g.players if g.role[u] == WW_SEER)
    target = next(u for u in g.players if u != seer)
    g.seer_view = {"target": target, "role": g.role[target],
                   "name": "x"}
    snap = g.snapshot()
    assert "role" not in snap and "roles" not in snap and "seer_view" not in snap
    assert g.private(seer)["seer_view"]["target"] == target
    other = next(u for u in g.players if u != seer)
    assert "seer_view" not in g.private(other)
    for u in g.players:
        assert g.private(u)["role"] == g.role[u]
    assert g.private(99) is None


# ================================================================ 阿瓦隆
def _av_force(g, roles):
    for u, r in roles.items():
        g.role[u] = r
    g.evil_uids = {u for u in g.players if g.role[u] in (ASSASSIN, MORDRED)}
    g.merlin_uid = next(u for u in g.players if g.role[u] == MERLIN)
    g.assassin_uid = next(u for u in g.players if g.role[u] == ASSASSIN)


def test_avalon_final_guess_without_target_is_rule_error():
    """回归：此前刺客不带 target 指认会抛 TypeError，且不满足 GameRuleError 契约。"""
    g = AvalonGame([1, 2, 3, 4, 5], seed=3)
    _av_force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    g.phase, g.need, g.acted = "final", [2], []
    with pytest.raises(GameRuleError):
        g.act(2, {"op": "guess"})
    assert g.winner is None and g.phase == "final"


def test_avalon_bad_nominate_payload_is_rule_error():
    """回归：此前提名里出现非数字 uid 会抛 ValueError，而不是约定的 GameRuleError。"""
    g = AvalonGame([1, 2, 3, 4, 5], seed=3)
    _av_force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    g.leader_idx = 0
    g._need_leader()
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "nominate", "team": ["x", "y"]})
    assert g.phase == "nominate" and g.team == []


def test_avalon_leader_can_vote_on_own_team():
    """回归：此前提名后 acted 未清空，领袖被当成已行动，团队票少一人且无法补票。"""
    g = AvalonGame([1, 2, 3, 4, 5], seed=3)
    _av_force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    g.leader_idx = 0
    g._need_leader()
    g.act(1, {"op": "nominate", "team": [1, 2]})
    assert g.phase == "teamvote" and g.acted == []
    for u in g.players:                          # 含领袖 1 在内全员都能投
        g.act(u, {"op": "vote", "approve": True})
    assert g.phase == "quest" and set(g.need) == {1, 2}


def test_avalon_player_left_unblocks_team_vote():
    """回归：此前投票者掉线后团队票永远凑不齐，状态停在 teamvote。"""
    g = AvalonGame([1, 2, 3, 4, 5], seed=3)
    _av_force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    g.phase, g.team, g.need, g.acted, g.votes = \
        "teamvote", [1, 2], list(g.players), [], {}
    for u, ok in ((1, True), (2, True), (3, True), (4, False)):
        g.act(u, {"op": "vote", "approve": ok})
    g.player_left(5)
    assert g.phase == "quest"                    # 3/4 赞成过半，团队通过
    assert set(g.need) == {1, 2}


def test_avalon_leader_left_reassigns_nomination():
    """回归：此前领袖掉线后 need 仍指向已离场玩家，提名阶段无人能行动。"""
    g = AvalonGame([1, 2, 3, 4, 5], seed=3)
    _av_force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    g.leader_idx = 0
    g._need_leader()
    assert g.need == [1]
    g.player_left(1)
    assert g.phase == "nominate" and g.need == [2] and g._leader_uid() == 2
    g.act(2, {"op": "nominate", "team": [2, 3]})


def test_avalon_assassin_left_in_final_good_wins():
    """回归：此前刺客在最终指认前掉线，final 阶段无人可行动，对局无法结束。"""
    g = AvalonGame([1, 2, 3, 4, 5], seed=3)
    _av_force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    g.phase, g.need, g.acted = "final", [2], []
    g.player_left(2)
    assert g.winner is True
    assert g.ended() and "好人" in g.ended()["detail"]


def test_avalon_missing_assassin_still_finishes_third_quest():
    """回归：此前刺客提前离场后达成 3 次成功会把 need 设成 [None]，终局卡死。"""
    g = AvalonGame([1, 2, 3, 4, 5], seed=3)
    _av_force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    g.results = [True, True]
    g.phase, g.team, g.need, g.acted = "quest", [3], [3], []
    g.player_left(2)
    g.act(3, {"op": "finish", "success": True})
    assert g.winner is True and g.phase == "done"


def test_avalon_three_quests_then_assassin_misses():
    """完整流程：组队→投票→任务 ×3，进入最终指认，指错则好人胜。"""
    g = AvalonGame([1, 2, 3, 4, 5], seed=3)
    _av_force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    for _ in range(3):
        leader = g._leader_uid()
        size = g._quest_size()
        team = [u for u in g.players if u != leader][:size - 1] + [leader]
        g.act(leader, {"op": "nominate", "team": team})
        for u in g.players:
            g.act(u, {"op": "vote", "approve": True})
        for u in list(g.need):
            g.act(u, {"op": "finish", "success": True})
    assert g.phase == "final" and g.need == [2]
    g.act(2, {"op": "guess", "target": 4})
    e = g.ended()
    assert e and "好人" in e["detail"]


def test_avalon_snapshot_hides_roles_private_is_per_player():
    """梅林/叛军信息只走私密通道，公开快照不含身份或叛军名单。"""
    g = AvalonGame([1, 2, 3, 4, 5], seed=3)
    _av_force(g, {1: MERLIN, 2: ASSASSIN, 3: MORDRED, 4: LOYAL, 5: LOYAL})
    snap = g.snapshot()
    assert "role" not in snap and "roles" not in snap and "evil" not in snap
    assert set(g.private(1)["evil"]) == {2, 3}
    assert "evil" not in g.private(4)
    for u in g.players:
        assert g.private(u)["role"] == g.role[u]
    assert g.private(99) is None


# ================================================================ 一夜狼人
def _ow_force(g, roles):
    for u, r in roles.items():
        g.original[u] = r
        g.role[u] = r
    g.need_act = {u for u in g.players if g.original[u] in (SEER, ROBBER)}
    g.acted, g.votes, g.dead = set(), {}, []


def test_onewolf_robber_must_wait_for_seer():
    """回归：此前强盗可先换牌，预言家随后看到的是换牌后的身份（行动顺序错误）。"""
    g = OneNightWolfGame([1, 2, 3, 4, 5], seed=2)
    _ow_force(g, {1: SEER, 2: ROBBER, 3: WEREWOLF, 4: VILLAGER, 5: VILLAGER})
    before = dict(g.role)
    with pytest.raises(GameRuleError):
        g.act(2, {"op": "swap", "rob": 3})
    assert g.role == before and g.phase == "night" and 2 not in g.acted
    g.act(1, {"op": "peek", "look_one": 3})
    g.act(2, {"op": "swap", "rob": 3})
    assert g.role[2] == WEREWOLF and g.role[3] == ROBBER
    assert g._seer_view[1] == (3, WEREWOLF)      # 预言家看到的是换牌前身份
    assert g.phase == "vote"


def test_onewolf_bad_center_payload_is_rule_error():
    """回归：此前 look_center 缺失/形状不对会抛 TypeError/ValueError，且可能留下半个行动。"""
    g = OneNightWolfGame([1, 2, 3, 4, 5], seed=2)
    _ow_force(g, {1: SEER, 2: ROBBER, 3: WEREWOLF, 4: VILLAGER, 5: VILLAGER})
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "peek", "look_center": [0]})
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "peek", "look_center": [0, 0]})
    assert 1 not in g.acted and 1 not in g._seer_cen


def test_onewolf_outsider_vote_rejected_and_game_resolves():
    """回归：此前非玩家 uid 也能投票，票数永远凑不齐导致投票阶段卡死。"""
    g = OneNightWolfGame([1, 2, 3, 4], seed=2)
    _ow_force(g, {1: SEER, 2: ROBBER, 3: WEREWOLF, 4: VILLAGER})
    g.phase = "vote"
    with pytest.raises(GameRuleError):
        g.act(99, {"op": "vote", "target": 3})
    assert g.votes == {}
    for u in g.players:
        g.act(u, {"op": "vote", "target": 3})
    assert g.phase == "result" and g.winner is True


def test_onewolf_night_to_vote_reaches_result():
    """夜晚行动 → 投票处决狼人 → 结果揭晓，覆盖完整一局流程。"""
    g = OneNightWolfGame([1, 2, 3, 4], seed=2)
    _ow_force(g, {1: SEER, 2: ROBBER, 3: WEREWOLF, 4: VILLAGER})
    g.act(1, {"op": "peek", "look_one": 3})
    g.act(2, {"op": "swap", "rob": 4})
    assert g.phase == "vote"
    for u in g.players:
        g.act(u, {"op": "vote", "target": 3})
    e = g.ended()
    assert e and "好人" in e["detail"]


def test_onewolf_snapshot_hides_roles_until_result():
    """公开快照在终局前不暴露任何身份；私密身份只发给本人。"""
    g = OneNightWolfGame([1, 2, 3, 4], seed=2)
    snap = g.snapshot()
    assert snap["reveal"] is None
    assert "role" not in snap and "roles" not in snap
    for u in g.players:
        assert g.private(u)["role"] == g.role[u]
    assert g.private(99) is None
