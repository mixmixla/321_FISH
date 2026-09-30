# -*- coding: utf-8 -*-
"""W2 纯逻辑类：达芬奇密码/非洲播棋/情书/德国心脏病 单测"""
import pytest

from games_pkg.base import GameRuleError
from games_pkg.davinci import DaVinCiGame, _hands_count
from games_pkg.halloween import HalloweenGame, SLAP_N
from games_pkg.kalah import KalahGame
from games_pkg.lovelove import LoveLoveGame
from games_pkg.rooms import RoomManager
from games_pkg import GAME_TYPES


# ---------- 达芬奇密码 DaVinCi ----------
def test_davinci_deal_opens_one_per_player():
    g = DaVinCiGame([1, 2], seed=1)
    assert _hands_count(2) == 4
    for u in (1, 2):
        row = g.hands[u]
        assert len([r for r in row if not r["removed"]]) == 4
        assert len([r for r in row if r["open"]]) == 1


def test_davinci_guess_hit_flips_and_turn_changes():
    g = DaVinCiGame([1, 2], seed=3)
    g.turn = 1
    g.hands[2] = [{"v": 5, "open": False, "pos": 0, "removed": False},
                  {"v": 3, "open": False, "pos": 1, "removed": False}]
    g.hands[1] = [{"v": 3, "open": True, "pos": 0, "removed": False}]
    g.draw = [9]
    g.act(1, {"op": "draw", "open": False})          # 摸一张暗牌
    g.act(1, {"op": "guess", "target": 2, "pos": 0, "val": 5})   # 猜中 v5
    assert g.hands[2][0]["open"] is True
    assert g.turn == 2                              # 已换手


def test_davinci_guess_miss_opens_own_drawn():
    g = DaVinCiGame([1, 2], seed=3)
    g.turn = 1
    g.hands[2] = [{"v": 5, "open": False, "pos": 0, "removed": False}]
    g.hands[1] = [{"v": 3, "open": True, "pos": 0, "removed": False},
                  {"v": 11, "open": False, "pos": 1, "removed": False}]
    g.draw = [9]
    g.act(1, {"op": "draw", "open": False})
    g.act(1, {"op": "guess", "target": 2, "pos": 0, "val": 8})   # 猜错
    # 自己暗藏的 9 被翻开
    mine = [r for r in g.hands[1] if not r["removed"] and r["v"] == 9]
    assert mine and mine[0]["open"] is True


def test_davinci_wrong_turn_rejected():
    g = DaVinCiGame([1, 2], seed=2)
    with pytest.raises(GameRuleError):
        g.act(2, {"op": "draw", "open": True})       # 未轮到玩家2
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "guess", "target": 1, "pos": 0, "val": 1})  # 不能猜自己


# ---------- 非洲播棋 Kalah ----------
def test_kalah_one_move():
    g = KalahGame([1, 2], seed=1)
    g.act(1, {"hole": 1})                    # 洞0 取4子 → 1,2,3,4
    assert g.cells[0] == 0
    assert g.cells[1] == 5 and g.cells[4] == 5 and g.cells[5] == 4
    assert g.turn == 2                       # 未落在库里 → 换人


def test_kalah_store_go_again():
    g = KalahGame([1, 2], seed=2)
    g.cells[5] = 1                           # 末洞1子 → 正好落自己库(6)
    g.act(1, {"hole": 6})
    assert g.cells[6] >= 1
    assert g.turn == 1                       # 再走一次


def test_kalah_capture():
    g = KalahGame([1, 2], seed=3)
    g.cells[0] = 1                           # 洞0 1子播到洞1
    g.cells[12] = 3                          # 洞1 对侧洞 3 子
    for i in (1, 2, 3, 4, 5, 8, 9, 10, 11, 13):
        g.cells[i] = 0
    g.act(1, {"hole": 1})
    assert g.cells[1] == 0 and g.cells[6] == 4   # 收 1+3 子入库


def test_kalah_win_triggers_finish():
    g = KalahGame([1, 2], seed=4)
    g.cells[0:6] = [0, 0, 0, 0, 0, 8]
    g.act(1, {"hole": 6})
    assert g.finished


def test_kalah_empty_hole_rejected():
    g = KalahGame([1, 2], seed=5)
    g.cells[0] = 0
    with pytest.raises(GameRuleError):
        g.act(1, {"hole": 1})
    with pytest.raises(GameRuleError):
        g.act(1, {"hole": 8})                # 只能己方洞


# ---------- 情书 LoveLove ----------
def test_lovelove_princess_discard_eliminates():
    g = LoveLoveGame([1, 2], seed=1)
    g.alive = [1, 2]; g.hand = {1: 8, 2: 3}
    g.act(1, {"play": 8})
    assert 1 not in g.alive and len(g.alive) == 1


def test_lovelove_guard_guessing_kills():
    g = LoveLoveGame([1, 2], seed=2)
    g.alive = [1, 2]; g.hand = {1: 1, 2: 6}
    g.act(1, {"play": 1, "target": 2, "val": 6})
    assert 2 not in g.alive


def test_lovelove_biggest_hand_wins_at_deck_end():
    g = LoveLoveGame([1, 2], seed=3)
    g.alive = [1, 2]; g.hand = {1: 3, 2: 7}
    g.game_over = True
    g._after(g.alive[0], [], 0)
    assert g.winner == 2


def test_lovelove_guard_unique_num_two_cards_ok():
    g = LoveLoveGame([1, 2], seed=4)
    g.alive = [1, 2]; g.hand = {1: 2, 2: 4}
    g.act(1, {"play": 2, "target": 2})       # 牧师可正常看牌


# ---------- 德国心脏病 Halloween ----------
def test_halloween_flip_then_slap_keep_turn():
    g = HalloweenGame([1, 2], seed=1)
    g.stack[1] = [0] * 5
    g.act(1, {"op": "flip"})
    assert g.counts[0] == 1
    g.counts[0] = SLAP_N                      # 凑到 5
    g.act(1, {"op": "slap"})
    assert g.turn == 1                        # 收牌后再走


def test_halloween_slap_empty_penalizes():
    g = HalloweenGame([1, 2], seed=2)
    g.have_flipped = True
    g.score[1] = 3
    g.counts = [2, 0, 0, 0, 0]                # 无 5
    g.act(1, {"op": "slap"})
    assert g.score[1] == 2
    assert g.turn == 2


def test_halloween_needs_flip_before_slap():
    g = HalloweenGame([1, 2], seed=3)
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "slap"})


def test_halloween_snapshot_score():
    g = HalloweenGame([1, 2], seed=4)
    s = g.snapshot()
    assert s["game"] == "halloween" and "score" in s and len(s["fruits"]) == 5


# ---------- 注册与房间 ----------
def test_w2_registered():
    for name in ("davinci", "kalah", "lovelove", "halloween"):
        assert name in GAME_TYPES


def test_room_manager_w2_lifecycle():
    rm = RoomManager(GAME_TYPES)
    r = rm.create(1, "davinci")
    rid = r.room_id
    rm.join(2, rid)
    rm.start(1, rid)
    msgs = rm.handle_action(1, rid, {"op": "draw", "open": False})
    assert isinstance(msgs, list)
    assert rm.room_for(rid) is not None