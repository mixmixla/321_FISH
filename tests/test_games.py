# -*- coding: utf-8 -*-
"""7 个游戏的状态推进与胜负判定单测"""
import time

import pytest

from games_pkg.base import GameRuleError
from games_pkg.blackjack import BlackjackGame
from games_pkg.drawguess import DrawGuessGame
from games_pkg.gomoku import GomokuGame
from games_pkg.guess_number import GuessNumberGame
from games_pkg.rps import RpsGame
from games_pkg.spy import SpyGame
from games_pkg.uno import UnoGame


# ---------- 猜数字 ----------
def test_guess_number_interval_and_score():
    g = GuessNumberGame([1, 2, 3], seed=1)
    g.gap = 0
    g.act(1, {"secret": 50})
    assert g.status == "playing"
    g.act(2, {"guess": 30})
    assert g.low == 31
    g.act(3, {"guess": 70})
    assert g.high == 69
    g.act(1, {"guess": 50})
    assert g.status == "round_end" and g.correct_uid == 1
    assert g.scores[1] == 1
    g.tick(time.time() + 1)
    assert g.status == "await_secret" and g.round_no == 2


def test_guess_number_rules():
    g = GuessNumberGame([1, 2], seed=1)
    with pytest.raises(GameRuleError):
        g.act(2, {"secret": 5})          # 非出题者
    with pytest.raises(GameRuleError):
        g.act(1, {"guess": 5})           # 未出题不能猜
    with pytest.raises(GameRuleError):
        g.act(1, {"secret": 101})        # 出题越界拒绝
    g.act(1, {"secret": 88})
    with pytest.raises(GameRuleError):
        g.act(1, {"guess": 999})         # 超出区间
    g.act(2, {"guess": 50})              # 低了 → 区间收窄
    assert g.low == 51
    with pytest.raises(GameRuleError):
        g.act(2, {"guess": 50})          # 已收窄，区间外
    g.act(1, {"guess": 88})              # 猜中
    assert g.scores[1] == 1


def test_guess_number_auto_secret_fallback():
    g = GuessNumberGame([1, 2], seed=1)
    g.auto_secret_wait = 0
    msgs = g.tick(time.time() + 1)
    assert g.status == "playing" and g.secret is not None


# ---------- 五子棋 ----------
def test_gomoku_five_in_row():
    g = GomokuGame([1, 2], seed=1)
    for x in range(4):
        g.act(1, {"x": x, "y": 0})
        g.act(2, {"x": x, "y": 5})
    g.act(1, {"x": 4, "y": 0})           # 横向五连
    assert g.winner_uid == 1
    res = g.ended()
    assert res["winner_uid"] == 1


def test_gomoku_rules():
    g = GomokuGame([1, 2], seed=1)
    with pytest.raises(GameRuleError):
        g.act(2, {"x": 0, "y": 0})       # 未轮到
    g.act(1, {"x": 0, "y": 0})
    with pytest.raises(GameRuleError):
        g.act(1, {"x": 1, "y": 0})       # 重复落子
    with pytest.raises(GameRuleError):
        g.act(2, {"x": -1, "y": 0})      # 越界
    with pytest.raises(GameRuleError):
        g.act(2, {"x": 0, "y": 0})       # 占位


def test_gomoku_draw():
    g = GomokuGame([1, 2], seed=1)
    # 填满棋盘且不出现五连：棋盘按 (x//2 + y) % 2 染色（任意方向连子 ≤2），
    # 再把颜色 0/1 的格子分别排进严格交替的落子序列，保证 225 手填满即平局。
    cells0 = [(x, y) for y in range(15) for x in range(15) if (x // 2 + y) % 2 == 0]
    cells1 = [(x, y) for y in range(15) for x in range(15) if (x // 2 + y) % 2 == 1]
    assert len(cells0) == 113 and len(cells1) == 112
    moves = []
    i = j = 0
    for k in range(225):
        if k % 2 == 0:
            moves.append(cells0[i]); i += 1
        else:
            moves.append(cells1[j]); j += 1
    for x, y in moves:
        g.act(g.players[g.turn], {"x": x, "y": y})
    assert g.draw


# ---------- 石头剪刀布 ----------
def test_rps_pairing_and_score():
    g = RpsGame([1, 2, 3, 4], seed=5)
    for u, c in [(1, 0), (2, 2), (3, 1), (4, 0)]:
        g.act(u, {"choice": c})
    assert g.phase == "collecting"       # 自动进入下一轮收集
    assert g.round == 1
    assert len(g.matches) == 2
    # 每对必有胜者或平局
    for m in g.matches:
        assert m["winner"] in (m["a"], m["b"], -1)
    # 石头(0) 胜 剪刀(2)
    m = g.matches[0]
    assert _pair_winner(m) is not None


def _pair_winner(m):
    if m["ca"] == 0 and m["cb"] == 2:
        return m["a"]
    if m["cb"] == 0 and m["ca"] == 2:
        return m["b"]
    return None


def test_rps_odd_bye_and_timeout():
    g = RpsGame([1, 2, 3], seed=1)
    g.timeout = 0
    for u, c in [(1, 0), (2, 1)]:
        g.act(u, {"choice": c})
    msgs = g.tick(time.time() + 1)       # 超时未提交者判负
    assert g.round == 1
    assert len(g.matches) == 1
    assert g.byes == [3]


def test_rps_no_double_submit():
    g = RpsGame([1, 2, 3], seed=1)
    g.act(1, {"choice": 0})
    with pytest.raises(GameRuleError):
        g.act(1, {"choice": 1})


# ---------- 谁是卧底 ----------
def test_spy_deal_one_spy():
    g = SpyGame([1, 2, 3, 4, 5], seed=7)
    assert g.phase == "describing"
    assert g.spy_uid in [1, 2, 3, 4, 5]
    civ = [u for u in g.players if u != g.spy_uid][0]
    assert g.private(g.spy_uid)["role"] == "spy"
    assert g.private(civ)["role"] == "civilian"
    assert g.private(g.spy_uid)["word"] != g.private(civ)["word"]


def test_spy_civilians_win():
    g = SpyGame([1, 2, 3, 4], seed=3)
    # 全部描述
    for u in g.players:
        g.act(u, {"describe": f"我的词和{ u }有关"})
    assert g.phase == "voting"
    spy = g.spy_uid
    others = [u for u in g.players if u != spy]
    for u in others:
        g.act(u, {"vote": spy})
    g.act(spy, {"vote": others[0]})
    assert g.ended() is not None
    res = g.ended()
    assert res["winner_uid"] is None      # 平民胜


def test_spy_spy_wins_last_two():
    g = SpyGame([1, 2, 3, 4], seed=3)
    spy = g.spy_uid
    others = [u for u in g.players if u != spy]
    # 描述轮
    for u in g.players:
        g.act(u, {"describe": "xx"})
    # 自投被拒
    with pytest.raises(GameRuleError):
        g.act(others[0], {"vote": others[0]})
    # 投票淘汰平民甲：卧底+2 平民投甲，甲投乙
    g.act(spy, {"vote": others[0]})
    g.act(others[1], {"vote": others[0]})
    g.act(others[2], {"vote": others[0]})
    g.act(others[0], {"vote": others[1]})
    assert others[0] not in g.alive      # 平民甲出局
    assert g.phase == "describing"       # 卧底仍在场，进入下一轮描述
    for u in g.alive:
        g.act(u, {"describe": "yy"})
    # 投票淘汰平民乙 → alive = 卧底 + 1 → 卧底胜
    g.act(spy, {"vote": others[1]})
    g.act(others[2], {"vote": others[1]})
    g.act(others[1], {"vote": others[2]})
    assert g.phase == "reveal"
    assert g.ended()["winner_uid"] == spy


def test_spy_tie_no_elimination():
    g = SpyGame([1, 2, 3, 4], seed=3)
    for u in g.players:
        g.act(u, {"describe": "z"})
    # 2:2 平票
    g.act(1, {"vote": 2})
    g.act(2, {"vote": 1})
    g.act(3, {"vote": 4})
    g.act(4, {"vote": 3})
    assert g.eliminated_uid is None
    assert g.phase == "describing"        # 无人出局继续


# ---------- 21 点 ----------
def test_blackjack_round_flow():
    g = BlackjackGame([1, 2], seed=4)
    g.gap = 0
    msgs = g.tick(time.time() + 1)        # 自动开局
    assert g.phase == "playing"
    assert len(g.hands[1]) == 2 and len(g.dealer) == 2
    # 打到结算
    guard = 0
    while g.phase == "playing" and guard < 50:
        u = g.players[g.current_idx]
        if g._hand_value(g.hands[u]) > 17:
            g.act(u, {"action": "stand"})
        else:
            g.act(u, {"action": "hit"})
        guard += 1
    assert g.phase == "round_end"
    assert set(g.results.keys()) == {1, 2}


def test_blackjack_bust():
    g = BlackjackGame([1, 2], seed=4)
    g.tick(time.time() + 1)
    # 强制小牌堆？直接调用爆牌判定
    g.hands[g.players[0]].append(("♠", "10"))
    g.hands[g.players[0]].append(("♠", "9"))
    g.hands[g.players[0]].append(("♠", "5"))
    assert g._hand_value(g.hands[g.players[0]]) > 21


def test_blackjack_turn_order():
    g = BlackjackGame([1, 2, 3], seed=4)
    g.tick(time.time() + 1)
    assert g.current_idx == 0
    with pytest.raises(GameRuleError):
        g.act(2, {"action": "hit"})       # 未轮到


# ---------- 你画我猜 ----------
def test_drawguess_flow():
    g = DrawGuessGame([1, 2, 3], seed=9)
    g.gap = 0
    assert g.phase == "drawing"
    drawer = g.players[g.drawer_idx]
    assert g.private(drawer)["word"]
    g.act(drawer, {"stroke": {"type": "line", "x1": 0, "y1": 0, "x2": 5, "y2": 5, "color": "black", "width": 2}})
    assert len(g.strokes) == 1
    g.act(drawer, {"clear": True})
    assert g.strokes == []
    word = g.private(drawer)["word"]
    with pytest.raises(GameRuleError):
        g.act(drawer, {"guess": word})    # 画手不能猜
    guesser = [u for u in g.players if u != drawer][0]
    g.act(guesser, {"guess": word})
    assert g.guessed_by == guesser and g.phase == "round_end"
    g.tick(time.time() + 1)
    assert g.phase == "drawing" and g.round == 2


# ---------- UNO ----------
def test_uno_deal_seven():
    g = UnoGame([1, 2, 3], seed=11)
    assert all(len(h) == 7 for h in g.hands.values())
    assert g.phase == "playing"
    assert g.discard[-1]["kind"] == "num"


def test_uno_same_color_play():
    g = UnoGame([1, 2], seed=11)
    top = g.discard[-1]
    uid = g.players[g.current_idx]
    # 找一张同色的牌
    playable = [c for c in g.hands[uid] if c["color"] == top["color"]]
    if playable:
        c = playable[0]
        before = len(g.hands[uid])
        g.act(uid, {"card": c["id"]})
        assert len(g.hands[uid]) == before - 1
    else:
        g.act(uid, {"draw": True})


def test_uno_wild4_restriction():
    g = UnoGame([1, 2], seed=11)
    uid = g.players[g.current_idx]
    wild4 = next((c for c in g.hands[uid] if c["value"] == "wild4"), None)
    if wild4 is None:
        g.hands[uid].append({"id": 9999, "color": None, "kind": "wild", "value": "wild4"})
        wild4 = g.hands[uid][-1]
    # 若手中有当前颜色牌 -> 拒绝
    top = g.discard[-1]
    if any(c["kind"] != "wild" and c["color"] == g.current_color for c in g.hands[uid]):
        with pytest.raises(GameRuleError):
            g.act(uid, {"card": wild4["id"], "color": "red"})


def test_uno_win_and_score():
    g = UnoGame([1, 2], seed=2)
    # 清空玩家1手牌，只剩一张可出的牌
    uid = g.players[g.current_idx]
    other = g.players[1 - g.current_idx]
    top = g.discard[-1]
    keep = next(c for c in g.hands[uid] if c["color"] == top["color"] or c["kind"] == "wild")
    g.hands[uid] = [keep]
    before = len(g.hands[other])
    g.act(uid, {"card": keep["id"]})
    assert g.winner_uid == uid
    assert g.phase == "round_end"
    assert g.scores[uid] >= 1
