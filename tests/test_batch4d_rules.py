# -*- coding: utf-8 -*-
"""批次 4d 桌游 P0 规则回归：猜数字、石头剪刀布、谁是卧底、你画我猜、24点、
抽牌配对、忍者之夜、骗子酒馆、COC、中国象棋。

每条回归用例都在 docstring 标注「回归：此前……」，并尽量用固定 seed 跑通
「阶段推进 → 终局」的可复现流程。
"""
import time

import pytest

from games_pkg.base import GameRuleError
from games_pkg.calc24 import Calc24Game, _p2, _parse_answer, _solve_seq
from games_pkg.coc import CHARS, CocGame, check_level
from games_pkg.drawguess import DrawGuessGame
from games_pkg.guess_number import GuessNumberGame
from games_pkg.liar import MAX_DRINK, LiarGame
from games_pkg.matchpairs import MatchPairsGame
from games_pkg.ninja import HP, NinjaNightGame
from games_pkg.rps import RpsGame
from games_pkg.spy import SpyGame
from games_pkg.xiangqi import XiangQiGame


# ================================================================ 猜数字
def test_guess_number_secret_cannot_be_reset_after_round_starts():
    """回归：此前 playing 阶段仍允许出题者重设数字，答案和已收窄的区间会被中途改掉。"""
    g = GuessNumberGame([1, 2], seed=1)
    g.act(1, {"secret": 50})
    g.act(2, {"guess": 30})
    assert (g.secret, g.low, g.high, g.status) == (50, 31, 100, "playing")
    with pytest.raises(GameRuleError):
        g.act(1, {"secret": 80})
    assert (g.secret, g.low, g.high, g.status) == (50, 31, 100, "playing")
    g.act(2, {"guess": 50})
    assert g.correct_uid == 2 and g.scores[2] == 1


def test_guess_number_round_flow_and_owner_rotation():
    g = GuessNumberGame([1, 2], seed=1)
    g.gap = 0
    g.act(1, {"secret": 77})
    g.act(2, {"guess": 50})
    assert g.low == 51 and g.high == 100
    g.act(2, {"guess": 77})
    assert g.status == "round_end" and g.scores[2] == 1
    assert g.snapshot()["secret"] == 77          # 揭晓期公开答案
    g.tick(time.time() + 1)
    assert g.status == "await_secret" and g.round_no == 2
    assert g.players[g.owner_idx] == 2           # 出题者轮转到猜中者


# ================================================================ 石头剪刀布
def test_rps_first_choice_does_not_auto_timeout():
    """回归：此前本轮 deadline 初始为 0，第一手提交后下一次 tick 立刻把其余人判负。"""
    g = RpsGame([1, 2, 3], seed=1)
    g.act(1, {"choice": 0})
    assert g.tick(time.time()) == []
    assert g.round == 0 and g.matches == [] and g.submitted == {1: 0}


def test_rps_timeout_resolves_after_clock_expires():
    g = RpsGame([1, 2, 3], seed=1)
    g.act(1, {"choice": 0})
    g.tick(g.round_end_at + 1)
    assert g.round == 1 and len(g.matches) == 1 and g.byes == [3]
    assert g.scores[1] == 1                     # 未出拳的 2 判负


def test_rps_scoring_and_draw():
    g = RpsGame([1, 2, 3, 4], seed=1)
    for u, c in ((1, 0), (2, 2), (3, 1), (4, 1)):
        g.act(u, {"choice": c})
    assert g.round == 1 and len(g.matches) == 2
    assert g.scores[1] == 1                     # 石头胜剪刀
    assert g.scores[3] == 0 and g.scores[4] == 0  # 双方出布，平局不计分


# ================================================================ 谁是卧底
def test_spy_basic_flow_civilians_win():
    g = SpyGame([1, 2, 3, 4], seed=3)
    for u in g.players:
        g.act(u, {"describe": "描述"})
    assert g.phase == "voting"
    spy = g.spy_uid
    other = next(u for u in g.alive if u != spy)
    for u in g.players:
        g.act(u, {"vote": other if u == spy else spy})
    assert g.phase == "reveal"
    res = g.ended()
    assert res is not None and res["winner_uid"] is None


def test_spy_player_left_during_describing_skips_speaker():
    """回归：此前掉线者仍占着描述顺序，轮到该座位时整局永远等不到描述。"""
    g = SpyGame([1, 2, 3, 4, 5], seed=1)
    speaker = g.alive[g.speaker_idx]
    g.player_left(speaker)
    assert speaker not in g.players and speaker not in g.alive
    nxt = g.alive[g.speaker_idx]                # 座位前移后下一位即可描述
    g.act(nxt, {"describe": "继续"})
    assert g.describes[-1]["uid"] == nxt


def test_spy_player_left_clears_votes_targeting_leaver():
    """回归：此前投给离场者的票仍计入票数，剩余玩家又无法补投，投票阶段卡死。"""
    g = SpyGame([1, 2, 3, 4, 5], seed=1)
    for u in g.players:
        g.act(u, {"describe": "x"})
    leaver = next(u for u in g.players if u != g.spy_uid)
    voter = next(u for u in g.alive if u != leaver)
    g.act(voter, {"vote": leaver})
    g.player_left(leaver)
    assert voter not in g.votes                # 目标离场，票作废可重投
    assert g.phase == "voting"
    for u in g.alive:
        target = g.spy_uid if u != g.spy_uid else next(x for x in g.alive if x != g.spy_uid)
        g.act(u, {"vote": target})
    assert g.phase == "reveal"


def test_spy_player_left_spy_gives_civilians_win():
    g = SpyGame([1, 2, 3, 4], seed=3)
    g.player_left(g.spy_uid)
    assert g.phase == "reveal"
    assert g.ended()["winner_uid"] is None


# ================================================================ 你画我猜
def test_drawguess_basic_round_flow():
    g = DrawGuessGame([1, 2, 3], seed=9)
    g.gap = 0
    drawer = g.players[g.drawer_idx]
    word = g.private(drawer)["word"]
    guesser = next(u for u in g.players if u != drawer)
    g.act(drawer, {"stroke": {"type": "line", "x1": 0, "y1": 0,
                              "x2": 1, "y2": 1, "color": "black", "width": 2}})
    g.act(guesser, {"guess": word})
    assert g.guessed_by == guesser and g.scores[guesser] == 1
    assert g.phase == "round_end"
    g.tick(time.time() + 1)
    assert g.phase == "drawing" and g.round == 2
    assert g.players[g.drawer_idx] != drawer


def test_drawguess_non_player_guess_rejected():
    """回归：此前非本局 uid 也能猜词，命中后写 scores 直接 KeyError，且猜测被算作有效。"""
    g = DrawGuessGame([1, 2], seed=1)
    word = g.private(g.players[g.drawer_idx])["word"]
    with pytest.raises(GameRuleError):
        g.act(99, {"guess": word})
    assert g.guess_log == [] and g.phase == "drawing"


def test_drawguess_drawer_left_starts_next_drawer_round():
    """回归：此前画手掉线仍占着画手座位，之后每一轮都没有画手、只能反复超时。"""
    g = DrawGuessGame([1, 2, 3], seed=1)
    drawer = g.players[g.drawer_idx]
    nxt = g.players[(g.drawer_idx + 1) % len(g.players)]
    g.player_left(drawer)
    assert drawer not in g.players and drawer not in g.scores
    assert g.phase == "drawing" and g.players[g.drawer_idx] == nxt
    g.act(nxt, {"stroke": {"type": "line", "x1": 0, "y1": 0,
                           "x2": 1, "y2": 1, "color": "black", "width": 2}})
    assert len(g.strokes) == 1


# ================================================================ 24 点
def test_calc24_solver_handles_none_intermediate():
    """回归：此前中间结果因除零为 None 时，_p2 会 Fraction(None) 抛 TypeError，整局无法开局。"""
    assert _p2(None, 3, "+") is None
    assert _p2(1, None, "*") is None
    for seed in range(30):
        g = Calc24Game([1, 2], seed=seed)
        assert g.win_seq is not None


def test_calc24_reference_expression_actually_makes_24():
    """回归：此前模板 2 的 o1/o3 与实际求值顺序不一致，公布的参考解可能不等于 24。"""
    expr = _solve_seq([1, 2, 6, 9])["expr"]     # 旧实现会给出 (1+(2*9))*6 = 114
    assert _parse_answer(expr, [1, 2, 6, 9]) == 24
    for seed in range(30):
        g = Calc24Game([1, 2], seed=seed)
        assert _parse_answer(g.win_seq["expr"], g.cards) == 24


def test_calc24_round_flow_to_end():
    g = Calc24Game([1, 2], seed=1)
    g.act(1, {"expr": g.win_seq["expr"]})
    assert g.solved_uid == 1 and g.scores[1] == 1 and g.phase == "revealed"
    g.reveal_end_at = time.time() - 1
    g.tick(time.time())
    assert g.round_no == 2 and g.phase == "answering"
    while g.phase != "ended":
        if g.phase == "answering":
            g.round_end_at = time.time() - 1
            g.tick(time.time())
        else:
            g.reveal_end_at = time.time() - 1
            g.tick(time.time())
    res = g.ended()
    assert res is not None and res["winner_uid"] == 1


def test_calc24_player_left_excluded_from_final_ranking():
    """回归：此前离场玩家仍留在计分表，可能被结算成最终胜者。"""
    g = Calc24Game([1, 2], seed=1)
    g.scores[1] = 5
    g.player_left(1)
    assert 1 not in g.players and 1 not in g.scores
    g.phase = "ended"
    assert g.ended()["winner_uid"] == 2


# ================================================================ 抽牌配对
def test_matchpairs_empty_hand_marked_safe_after_draw():
    """回归：此前被摸空手的玩家没有进入 safe 名单，快照仍把他显示成在局玩家。"""
    g = MatchPairsGame([1, 2, 3], seed=1)
    g.hands = {1: [(5, "♠")], 2: [(7, "♥")], 3: []}
    g.safe = {3}
    g.turn = 0
    g.loser_uid = None
    g.act(1, {"draw": True})
    assert g.hands[2] == [] and 2 in g.safe
    assert g.hands[1] == [(5, "♠"), (7, "♥")]


def test_matchpairs_play_to_loser():
    g = MatchPairsGame([1, 2, 3, 4], seed=3)
    guard = 0
    while g.ended() is None and guard < 500:
        g.act(g._current(), {"draw": True})
        guard += 1
    assert g.ended() is not None
    assert g.loser_uid is not None
    assert g.snapshot()["turn_uid"] is None


# ================================================================ 忍者之夜
def test_ninja_all_dead_ends_instead_of_deadlock():
    """回归：此前全员同归于尽时 winner=None，ended() 仍返回 None 且所有动作被拒，整局卡死。"""
    g = NinjaNightGame([1, 2, 3], seed=1)
    g.hp = {1: 1, 2: 1, 3: 1}
    g.act(1, {"op": "move", "move": "attack", "target": 2})
    g.act(2, {"op": "move", "move": "attack", "target": 3})
    g.act(3, {"op": "move", "move": "attack", "target": 1})
    assert g.alive == set()
    res = g.ended()
    assert res is not None and res["winner_uid"] is None
    assert g.snapshot()["done"] is True
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "next"})


def test_ninja_elimination_and_winner():
    g = NinjaNightGame([1, 2, 3], seed=1)
    g.hp = {1: 1, 2: 1, 3: 3}
    g.act(1, {"op": "move", "move": "attack", "target": 2})
    g.act(2, {"op": "move", "move": "attack", "target": 3})
    g.act(3, {"op": "move", "move": "attack", "target": 2})
    assert g.alive == {1, 3} and g.hp[3] == 2
    g.act(1, {"op": "next"})
    g.act(1, {"op": "move", "move": "attack", "target": 3})
    g.act(3, {"op": "move", "move": "attack", "target": 1})
    assert g.alive == {3} and g.winner == 3
    assert g.ended()["winner_uid"] == 3


def test_ninja_player_left_resolves_when_remaining_all_picked():
    """回归：此前掉线者永远不会提交行动，本轮凑不齐，整局永远停在 pick 阶段。"""
    g = NinjaNightGame([1, 2, 3], seed=1)
    g.act(1, {"op": "move", "move": "attack", "target": 2})
    g.act(2, {"op": "move", "move": "guard"})
    g.player_left(3)
    assert 3 not in g.players and 3 not in g.alive and 3 not in g.hp
    assert g.phase == "resolve"
    assert g.hp[1] == HP - 1                    # 攻击防御者被反伤


# ================================================================ 骗子酒馆
def _liar_total(g):
    total = sum(len(h) for h in g.hand.values()) + len(g.deck_pool) + len(g.discard)
    return total + (1 if g.pending else 0)


def test_liar_covered_card_goes_to_discard():
    """回归：此前新出牌直接覆盖 pending，上一张未挑战的牌凭空消失（牌数不守恒）。"""
    g = LiarGame([1, 2], seed=1)
    total = _liar_total(g)
    v1 = g.hand[1][0]
    g.act(1, {"op": "play", "card": v1, "claim": v1})
    v2 = g.hand[2][0]
    g.act(2, {"op": "play", "card": v2, "claim": v2})
    assert v1 in g.discard and g.pending["val"] == v2
    assert _liar_total(g) == total


def test_liar_refills_from_discard_and_never_deadlocks():
    """回归：此前牌池耗尽后手牌被逐渐打空，轮到无牌玩家时既不能出牌也不能挑战，卡死。"""
    g = LiarGame([1, 2], seed=1)
    total = _liar_total(g)
    for _ in range(40):
        uid = g._turn_uid()
        assert g.hand[uid], "手牌不应被打空"
        val = g.hand[uid][0]
        g.act(uid, {"op": "play", "card": val, "claim": val})
        assert all(g.hand[u] for u in g.players)
        assert _liar_total(g) == total
    assert g.winner is None


def test_liar_challenge_elimination_reaches_winner():
    g = LiarGame([1, 2], seed=2)
    for _ in range(MAX_DRINK):
        val = g.hand[1][0]
        g.act(1, {"op": "play", "card": val, "claim": val})
        g.act(2, {"op": "challenge"})
    assert 2 in g.out and g.winner == 1
    assert g.ended()["winner_uid"] == 1


def test_liar_player_left_advances_turn():
    """回归：此前掉线者仍占着回合，轮到他时没人能出牌或挑战，整局卡死。"""
    g = LiarGame([1, 2, 3], seed=3)
    cur = g._turn_uid()
    nxt = g.players[(g.players.index(cur) + 1) % len(g.players)]
    g.player_left(cur)
    assert cur not in g.players and cur not in g.hand
    assert g._turn_uid() == nxt
    val = g.hand[nxt][0]
    g.act(nxt, {"op": "play", "card": val, "claim": val})


# ================================================================ COC
def test_coc_roll_above_low_skill_is_failure():
    """回归：此前技能 30 时投出 40 仍按固定阈值判成困难成功（高于技能值也算成功）。"""
    assert check_level(40, 30) == "失败"
    assert check_level(31, 30) == "失败"
    assert check_level(96, 30) == "大失败"
    assert check_level(1, 30) == "大成功"
    assert check_level(30, 30) == "困难成功"


def test_coc_player_cap_matches_card_pool():
    """回归：此前 max_players 不限，7 人房永远选不满 6 张调查员卡，setup 阶段卡死。"""
    assert CocGame.max_players == len(CHARS) == 6


def test_coc_six_players_choose_and_begin():
    g = CocGame([1, 2, 3, 4, 5, 6], seed=2)
    for i, u in enumerate(g.players):
        g.act(u, {"op": "choose_card", "card_id": g.chars[i]["id"]})
    g.act(1, {"op": "begin"})
    assert g.phase == "play"
    skill = next(iter(g.assigned[1]["sig"]))
    g.act(1, {"op": "check", "skill": skill})
    assert g.last_check["uid"] == 1


# ================================================================ 中国象棋
def _empty_board(g):
    g.board = [[0] * 9 for _ in range(10)]


def test_xiangqi_horse_leg_blocks_jump():
    g = XiangQiGame([1, 2], seed=1)
    _empty_board(g)
    g.board[4][4] = 4                            # 红马 (4,4)
    g.turn = 0
    assert (6, 3) in g._move_gen(4, 4, 4)
    g.board[4][5] = 7                            # 马腿 (5,4) 被己方兵蹩住
    moves = g._move_gen(4, 4, 4)
    assert (6, 3) not in moves and (6, 5) not in moves
    assert (2, 3) in moves                       # 另一侧马腿通畅


def test_xiangqi_elephant_eye_blocks_move():
    g = XiangQiGame([1, 2], seed=1)
    _empty_board(g)
    g.board[7][4] = 3                            # 红相 (4,7)
    g.turn = 0
    assert (2, 5) in g._move_gen(4, 7, 3)
    g.board[6][3] = 7                            # 象眼 (3,6) 被塞
    assert (2, 5) not in g._move_gen(4, 7, 3)


def test_xiangqi_cannon_needs_screen_to_capture():
    g = XiangQiGame([1, 2], seed=1)
    _empty_board(g)
    g.board[7][4] = 6                            # 红炮 (4,7)
    g.board[4][4] = 16                           # 黑子 (4,4)
    g.turn = 0
    assert (4, 4) not in g._move_gen(4, 7, 6)    # 无炮架不能吃
    g.board[6][4] = 7                            # 架上己方兵
    assert (4, 4) in g._move_gen(4, 7, 6)


def test_xiangqi_facing_generals_move_rejected_and_rolled_back():
    """回归：此前移开挡子让将帅照面仍被当作合法着法，局面会被走坏。"""
    g = XiangQiGame([1, 2], seed=1)
    _empty_board(g)
    g.board[9][4] = 1                            # 红帅
    g.board[0][4] = 11                           # 黑将
    g.board[5][4] = 5                            # 红车挡在中间
    g.turn = 0
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 4, "fy": 5, "tx": 3, "ty": 5})
    assert g.board[5][4] == 5 and g.board[5][3] == 0
    assert g.turn == 0


def test_xiangqi_self_check_move_rejected_and_rolled_back():
    g = XiangQiGame([1, 2], seed=1)
    _empty_board(g)
    g.board[9][4] = 1                            # 红帅
    g.board[0][4] = 11                           # 黑将
    g.board[0][3] = 15                           # 黑车控制第 3 列
    g.board[5][4] = 7                            # 挡子，避免将帅照面
    g.turn = 0
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 4, "fy": 9, "tx": 3, "ty": 9})
    assert g.board[9][4] == 1 and g.board[9][3] == 0 and g.turn == 0


def test_xiangqi_checkmate_wins():
    g = XiangQiGame([1, 2], seed=1)
    _empty_board(g)
    g.board[0][4] = 11                           # 黑将 (4,0)
    g.board[9][3] = 1                            # 红帅 (3,9)
    g.board[2][0] = 5                            # 红车 (0,2)
    g.board[1][8] = 5                            # 红车 (8,1) 控制第 1 横线
    g.turn = 0
    msgs = g.act(1, {"fx": 0, "fy": 2, "tx": 0, "ty": 0})
    assert g.board[0][0] == 5
    assert g.winner == 1
    assert g.ended()["winner_uid"] == 1
    assert any("获胜" in m for m in msgs)


def test_xiangqi_basic_legal_move_switches_turn():
    g = XiangQiGame([1, 2], seed=1)
    g.act(1, {"fx": 0, "fy": 9, "tx": 0, "ty": 7})
    assert g.board[7][0] == 5 and g.board[9][0] == 0
    assert g.turn == 1
