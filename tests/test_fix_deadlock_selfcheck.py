# -*- coding: utf-8 -*-
"""死锁与自将修复回归：璀璨宝石无动作自动跳过；将棋禁止走成被将军。"""
import copy

import pytest

from games_pkg.base import GameRuleError
from games_pkg.gemcity import COLORS, GemCityGame
from games_pkg.shogi import ShogiGame


def _no_action_gemcity():
    """构造：银行无彩色宝石、保留位已满 3 张、所有卡都买不起。"""
    g = GemCityGame([1, 2], seed=3)
    g.turn = 0
    for c in COLORS:
        g.bank[c] = 0
    g.bank["g"] = 0
    g.tokens[1] = {c: 2 for c in COLORS}
    g.tokens[1]["g"] = 0
    g.tokens[2] = {c: 2 for c in COLORS}
    g.tokens[2]["g"] = 0
    g.reserved[1] = [g.market[1][0], g.market[1][1], g.market[1][2]]
    for tier in g.market:
        for card in g.market[tier]:
            card["cost"] = {c: 9 for c in COLORS}
    for card in g.reserved[1]:
        card["cost"] = {c: 9 for c in COLORS}
    return g


def test_gemcity_auto_skips_a_player_with_no_legal_action():
    """回归：此前该局面下 take/take2/reserve/buy/buy_res 全部被拒，回合永久卡死。"""
    g = _no_action_gemcity()
    assert g._can_act(1) is False
    msgs = g.tick(0)
    assert msgs and "自动跳过" in msgs[0]
    assert g.players[g.turn] == 2


def test_gemcity_tick_does_not_skip_when_actions_exist():
    """有取宝石动作时不得自动跳过，避免正常思考回合被吞。"""
    g = GemCityGame([1, 2], seed=3)
    g.turn = 0
    assert g._can_act(1) is True
    assert g.tick(0) == []
    assert g.players[g.turn] == 1


def _check_position():
    s = ShogiGame([1, 2], seed=1)
    s.board = [[0] * 9 for _ in range(9)]
    s.board[0][4] = 1        # 黑玉
    s.board[3][3] = 11       # 白玉
    s.board[4][4] = 2        # 黑飞车：横向照住 (3,4)
    s.turn = 1               # 白方
    return s


def test_shogi_cannot_move_into_check():
    """回归：此前白王可以走进黑飞车的攻击线，引擎不做自将校验。"""
    s = _check_position()
    before = copy.deepcopy(s.board)
    with pytest.raises(GameRuleError, match="被将军"):
        s.act(2, {"fx": 3, "fy": 3, "tx": 3, "ty": 4})
    assert s.board == before


def test_shogi_legal_moves_exclude_self_check_but_keep_safe_moves():
    """回归：此前 legal_moves 会把自将着法也标成合法落点。"""
    s = _check_position()
    before = copy.deepcopy(s.board)
    legal = s.legal_moves(2)
    assert before == s.board                       # 试走不得留下状态
    assert {"from": [3, 3], "to": [3, 4]} not in legal
    assert {"from": [3, 3], "to": [2, 3]} in legal
    s.act(2, {"fx": 3, "fy": 3, "tx": 2, "ty": 3})
    assert s.board[3][2] == 11
