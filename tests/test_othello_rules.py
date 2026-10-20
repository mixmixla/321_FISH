# -*- coding: utf-8 -*-
"""奥赛罗规则回归：初始局面、夹子翻转、让过（pass）与终局结算。

重点回归：对手无处可下被自动让过后，**当前玩家必须还能继续落子**。
"""
import random

import pytest

from games_pkg.base import GameRuleError
from games_pkg.othello import OthelloGame


def _game():
    return OthelloGame([1, 2], seed=1)


def test_initial_position_and_black_first():
    g = _game()
    assert g.board[3][3] == 1 and g.board[4][4] == 1
    assert g.board[3][4] == 2 and g.board[4][3] == 2
    assert g.snapshot()["turn_uid"] == 1


def test_illegal_moves_are_rejected():
    g = _game()
    with pytest.raises(GameRuleError):
        g.act(1, {"x": 0, "y": 0})       # 夹不到任何子
    with pytest.raises(GameRuleError):
        g.act(1, {"x": 3, "y": 3})       # 已有棋子
    with pytest.raises(GameRuleError):
        g.act(2, {"x": 4, "y": 2})       # 未轮到


def test_player_can_move_after_opponent_passes():
    """回归：pass_next 状态下当前玩家不能被拦（此前的死锁 bug）。"""
    g = _game()
    g.pass_next = True
    g.act(1, {"x": 2, "y": 4})
    assert g.board[4][2] == 1
    assert g.board[4][3] == 1            # 白子被翻转


def test_random_games_complete_without_pass_deadlock():
    for seed in range(8):
        g = OthelloGame([1, 2], seed=seed)
        rnd = random.Random(seed)
        for _ in range(200):
            if g.winner_uid is not None or g.scores is not None:
                break
            idx = g.turn
            cells = g._legal_cells(idx)
            assert cells, "让过处理正确时，当前玩家应始终有合法落点"
            x, y = rnd.choice(cells)
            g.act(g.players[idx], {"x": x, "y": y})
        assert g.scores is not None or g.winner_uid is not None


def test_finish_scores_and_winner():
    g = _game()
    # 直接铺满：黑子多则黑胜
    for y in range(8):
        for x in range(8):
            g.board[y][x] = 1 if (x + y) % 3 else 2
    g._finish()
    black = sum(row.count(1) for row in g.board)
    white = sum(row.count(2) for row in g.board)
    assert g.scores == {1: black, 2: white}
    assert g.winner_uid == (1 if black > white else 2 if white > black else None)
    assert g.ended() is not None
