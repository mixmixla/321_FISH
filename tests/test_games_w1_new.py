# -*- coding: utf-8 -*-
"""W1 新增四款：花砖物语/拉密/快艇骰子/牛头王 逻辑+房间单测"""
import pytest

from games_pkg.azul import _wall_col, AzulGame
from games_pkg.base import GameRuleError
from games_pkg.nimmt import heads as nimmt_heads, NimmtGame
from games_pkg.rooms import RoomManager
from games_pkg.rummikub import color_of, num_of, RummikubGame
from games_pkg.yahtzee import _cat_score, YahtzeeGame


# ---------- 花砖物语 Azul ----------
def _azul_one_full_turn(g, uid, src=0, col=None):
    """取砖并落一行，完成一次完整行动（回合移交）。"""
    if col is None:
        col = g.offers[src][0]
    g.act(uid, {"op": "take", "src": src, "col": col})
    for row in range(5):
        cc = _wall_col(["r", "w", "b", "y", "k"].index(col), row)
        if g.wall[uid][(row, cc)] is None:
            g.act(uid, {"op": "place", "row": row})
            return
    g.act(uid, {"op": "floor"})


def test_azul_take_place_and_advance():
    g = AzulGame([1, 2], seed=1)
    assert g.round == 1 and len(g.offers) == 2
    _azul_one_full_turn(g, 1, 0)
    assert g.turn == 1


def test_azul_wrong_turn_and_color():
    g = AzulGame([1, 2], seed=3)
    with pytest.raises(GameRuleError):
        g.act(2, {"op": "take", "src": 0, "col": "r"})
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "take", "src": 0, "col": "x"})


def test_azul_snapshot_shape():
    g = AzulGame([1, 2], seed=8)
    s = g.snapshot()
    assert s["game"] == "azul" and "offers" in s and "wall" in s
    assert len(s["wall"]["1"]) == 25


def _red_run_ids(nums):
    """取一个颜色(红/#0)的指定连号各一张的牌 id"""
    out = []
    for n in nums:
        for i in range(len(num_of)):
            if color_of[i] == 0 and num_of[i] == n:
                out.append(i)
                break
    return out


# ---------- 拉密 Rummikub ----------
def test_rummikub_classify():
    run = _red_run_ids([3, 4, 5])
    assert RummikubGame.classify(run)[0] == "run"
    ids7, seen = [], set()
    for i in range(len(num_of)):
        if num_of[i] == 7 and color_of[i] not in seen:
            seen.add(color_of[i]); ids7.append(i)
        if len(ids7) == 3:
            break
    assert RummikubGame.classify(ids7)[0] == "group"
    assert RummikubGame.classify([0, 0, 0]) is None      # 重复同牌不成组


def test_rummikub_initial_meld_needs_30():
    g = RummikubGame([1, 2], seed=5)
    u = 1
    # 小连号 <30 应被拒
    small = _red_run_ids([3, 4, 5])
    g.rack[u] = list(small)
    with pytest.raises(GameRuleError):
        g.act(u, {"op": "meld", "tiles": small})
    # 大连号 ≥30 应成功
    big = _red_run_ids([9, 10, 11, 12])      # 42 点
    g.rack[u] = list(big)
    g.act(u, {"op": "meld", "tiles": big})
    assert g.initial_ok[u] and len(g.table) == 1


def test_rummikub_win_by_clearing():
    g = RummikubGame([1, 2], seed=7)
    u = 1
    big = _red_run_ids([9, 10, 11, 12])
    g.rack[u] = list(big)
    g.act(u, {"op": "meld", "tiles": big})
    assert g.rack[u] == [] and g.winner == u

def test_rummikub_no_draw_after_place():
    g = RummikubGame([1, 2], seed=7)
    u = 1
    big = _red_run_ids([9, 10, 11, 12])
    g.rack[u] = list(big)
    g.act(u, {"op": "meld", "tiles": big})
    with pytest.raises(GameRuleError):
        g.act(u, {"op": "draw"})          # 已出牌不能摸


# ---------- 快艇骰子 Yahtzee ----------
def test_yahtzee_score_categories():
    assert _cat_score("1", [1, 1, 1, 2, 3]) == 3
    assert _cat_score("three", [3, 3, 3, 4, 5]) == 18
    assert _cat_score("three", [1, 2, 3, 4, 5]) == 0
    assert _cat_score("house", [2, 2, 3, 3, 3]) == 25
    assert _cat_score("house", [2, 2, 3, 3, 4]) == 0
    assert _cat_score("small", [1, 2, 3, 4, 6]) == 30
    assert _cat_score("large", [2, 3, 4, 5, 6]) == 40
    assert _cat_score("yahtzee", [4, 4, 4, 4, 4]) == 50
    assert _cat_score("chance", [1, 2, 3, 4, 5]) == 15


def test_yahtzee_turn_and_reroll():
    g = YahtzeeGame([1, 2], seed=2)
    g.act(1, {"op": "roll"})
    before = list(g.dice)
    g.act(1, {"op": "reroll", "keep": [0, 1, 2]})
    assert g.dice[0] in (before[0], None) or g.dice[:3] == before[:3]
    g.act(1, {"op": "score", "cat": "chance"})
    assert g.turn == 1 and g.scores[1]["chance"] is not None
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "roll"})                 # 已轮到 2


# ---------- 牛头王 Nimmt ----------
def test_nimmt_heads():
    assert nimmt_heads(1) == 1
    assert nimmt_heads(55) == 7
    assert nimmt_heads(10) == 3
    assert nimmt_heads(11) == 5


def test_nimmt_round_flow():
    g = NimmtGame([1, 2], seed=1)
    assert len(g.hands[1]) == 10 and len(g.table) == 4
    c1, c2 = g.hands[1][0], g.hands[2][0]
    g.act(1, {"card": c1})
    g.act(2, {"card": c2})
    assert len(g.choices) == 0 and len(g.hands[1]) == 9
    assert g.round == 2


def test_nimmt_duplicate_choice():
    g = NimmtGame([1, 2], seed=2)
    c1 = g.hands[1][0]
    g.act(1, {"card": c1})
    with pytest.raises(GameRuleError):
        g.act(1, {"card": c1})


# ---------- 房间 / 注册 ----------
def test_registered_in_meta():
    from games_pkg import GAME_META
    for k in ("azul", "rummikub", "yahtzee", "nimmt"):
        assert k in GAME_META
        assert GAME_META[k]["label"] and GAME_META[k]["rules"]


def test_room_create_each():
    from games_pkg import GAME_TYPES
    rm = RoomManager(GAME_TYPES)
    for k in ("azul", "rummikub", "yahtzee", "nimmt"):
        rm.create(1, k)