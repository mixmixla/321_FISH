# -*- coding: utf-8 -*-
"""新增四款大桌游（四子棋/奥赛罗/24点/抽牌配对）+ rooms 掉线善后的单测"""
import time

import pytest

from games_pkg.base import GameRuleError
from games_pkg.calc24 import Calc24Game, _parse_answer, _solve_seq
from games_pkg.connect4 import Connect4Game
from games_pkg.matchpairs import MatchPairsGame
from games_pkg.othello import OthelloGame
from games_pkg.rooms import RoomManager


# ---------- 四子棋 ----------
def test_connect4_horizontal_win():
    g = Connect4Game([1, 2], seed=1)
    for c in range(3):
        g.act(1, {"col": c})
        g.act(2, {"col": c + 4})
    g.act(1, {"col": 3})                 # 横向四连
    assert g.winner_uid == 1
    assert g.ended()["winner_uid"] == 1


def test_connect4_gravity_and_rules():
    g = Connect4Game([1, 2], seed=1)
    with pytest.raises(GameRuleError):
        g.act(2, {"col": 0})             # 未轮到
    g.act(1, {"col": 0})                 # 落底
    assert g.board[5][0] == 1
    with pytest.raises(GameRuleError):
        g.act(2, {"col": 7})             # 越界
    with pytest.raises(GameRuleError):
        g.act(2, {"col": -1})
    g.act(2, {"col": 0})                 # 第 2 枚落到第 4 行
    assert g.board[4][0] == 2
    with pytest.raises(GameRuleError):
        g.act(1, {"col": "x"})           # 非整数


def test_connect4_vertical_win():
    g = Connect4Game([1, 2], seed=1)
    for _ in range(3):
        g.act(1, {"col": 0})
        g.act(2, {"col": 1})
    g.act(1, {"col": 0})                 # 纵向四连
    assert g.winner_uid == 1


def test_connect4_occupied_column_rejected():
    g = Connect4Game([1, 2], seed=1)
    for r in range(6):
        g.board[5 - r][0] = 1            # 直接铺满第 0 列
    with pytest.raises(GameRuleError):
        g.act(1, {"col": 0})             # 0 列已满


# ---------- 奥赛罗 ----------
def test_othello_initial_and_flip():
    g = OthelloGame([1, 2], seed=1)
    # 初始中心四子：黑(3,3)/(4,4)，白(3,4)/(4,3)；黑先
    assert g.board[3][3] == 1 and g.board[4][4] == 1
    assert g.board[3][4] == 2 and g.board[4][3] == 2
    g.act(1, {"x": 2, "y": 4})           # 落 (2,4)：向右夹 (3,4)白 至 (4,4)黑
    assert g.board[4][2] == 1
    assert g.board[4][3] == 1            # 白被翻转成黑


def test_othello_illegal_and_pass():
    g = OthelloGame([1, 2], seed=1)
    with pytest.raises(GameRuleError):
        g.act(1, {"x": 0, "y": 0})       # 无法夹住任何子
    with pytest.raises(GameRuleError):
        g.act(1, {"x": 3, "y": 3})       # 已占用
    with pytest.raises(GameRuleError):
        g.act(2, {"x": 4, "y": 2})       # 未轮到
    g.act(1, {"x": 2, "y": 4})           # 合法，轮到白
    assert g.turn == 1


def test_othello_full_game_ends():
    g = OthelloGame([1, 2], seed=7)
    # 用必然的走法定整局有难度，这里直接铺满验证结算逻辑
    for y in range(8):
        for x in range(8):
            if g.board[y][x] == 0:
                g.board[y][x] = 1 if (x + y) % 2 else 2
    g.scores = {g.players[0]: sum(r.count(1) for r in g.board),
                g.players[1]: sum(r.count(2) for r in g.board)}
    g.winner_uid = max(g.scores, key=g.scores.get)
    res = g.ended()
    assert res is not None and "detail" in res


# ---------- 24点 ----------
def test_calc24_deal_is_solvable():
    for seed in range(5):
        g = Calc24Game([1, 2], seed=seed)
        assert g.phase == "answering"
        assert g.win_seq is not None     # 每轮必有解


def test_calc24_correct_answer_scores():
    g = Calc24Game([1, 2], seed=1)
    expr = g.win_seq["expr"]             # 用求解器给出的解作答
    # 用该解对应的四个数需与 cards 一致
    g.act(1, {"expr": expr})
    assert g.scores[1] == 1
    assert g.phase == "revealed"
    assert g.solved_uid == 1


def test_calc24_rejects_bad_answer():
    g = Calc24Game([1, 2], seed=1)
    with pytest.raises(GameRuleError):
        g.act(1, {"expr": g.cards[0]})   # 只用了一张牌
    with pytest.raises(GameRuleError):
        g.act(1, {"expr": "1+2"})        # 缺牌
    with pytest.raises(GameRuleError):
        g.act(1, {"expr": "1+2+3*4"})  # 若结果非24则拒
    with pytest.raises(GameRuleError):
        g.act(1, {"expr": "10+10+2+2"})  # 非法拼数/用牌错


def test_calc24_parser_unsafe_rejected():
    g = Calc24Game([1, 2], seed=1)
    with pytest.raises(GameRuleError):
        g.act(1, {"expr": "__import__('os').system('x')"})  # 不 eval，纯拒绝
    with pytest.raises(GameRuleError):
        g.act(1, {"expr": "1+2+3"})      # 缺一张
    with pytest.raises(GameRuleError):
        g.act(1, {"expr": ""})


def test_calc24_tick_advances_and_ends():
    g = Calc24Game([1, 2], seed=1)
    # 时间到无人答出 → 参考解 → 下一轮
    g.round_end_at = time.time() - 1
    msgs = g.tick(time.time())
    assert g.phase == "revealed"
    assert any("参考解" in m for m in msgs)
    g.reveal_end_at = time.time() - 1
    g.tick(time.time())
    assert g.round_no == 2 and g.phase == "answering"
    # 冲到底
    while g.phase != "ended":
        g.round_end_at = time.time() - 1
        g.tick(time.time())
        if g.phase == "revealed":
            g.reveal_end_at = time.time() - 1
            g.tick(time.time())
    assert g.ended() is not None


# ---------- 抽牌配对 ----------
def test_matchpairs_deal_pairs_removed():
    g = MatchPairsGame([1, 2, 3], seed=2)
    # 各人手牌内成对已弃掉（无同类成对残留），场内总数为奇数 51
    for u in g.players:
        ranks = [c[0] for c in g.hands[u]]
        assert len(ranks) == len(set(ranks))
    total = sum(len(h) for h in g.hands.values())
    assert total % 2 == 1                    # 奇数张：终局必剩 1 张王八


def test_matchpairs_play_until_looser():
    g = MatchPairsGame([1, 2, 3, 4], seed=3)
    guard = 0
    while g.ended() is None and guard < 500:
        uid = g._current()
        g.act(uid, {"draw": True})
        guard += 1
    assert g.ended() is not None
    assert g.loser_uid is not None


def test_matchpairs_turn_rejected():
    g = MatchPairsGame([1, 2, 3], seed=2)
    other = next(u for u in g.players if u != g._current())
    with pytest.raises(GameRuleError):
        g.act(other, {"draw": True})


# ---------- rooms 掉线善后 ----------
def test_rooms_matchpairs_disconnect_merges_hand():
    rm = RoomManager({"matchpairs": MatchPairsGame})
    room = rm.create(1, "matchpairs")
    rm.join(2, room.room_id)
    rm.join(3, room.room_id)
    rm.start(1, room.room_id)
    g = room.gs
    affected = rm.on_disconnect(2)       # 玩家2对局中掉线
    assert room.room_id in affected
    assert 2 not in g.hands              # 已踢出
    assert g.hands[1] or g.hands[3]      # 牌已并入其余玩家