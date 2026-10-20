# -*- coding: utf-8 -*-
"""角斗士棋规则回归：角接触只需一次、禁止同边相邻、空袋跳过与终局时机。"""
import pytest

from games_pkg.base import GameRuleError
from games_pkg.blokus import BOARD, BlokusGame


def _game(n=2):
    return BlokusGame(list(range(1, n + 1)), seed=1)


def _orient_with(ots, a, b):
    for i, cells in enumerate(ots):
        if a in cells and b in cells:
            return i
    raise AssertionError("orientation not found")


def test_first_piece_must_touch_a_corner():
    g = _game()
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "place", "piece": "M", "oi": 0, "x": 5, "y": 5})
    g.act(1, {"op": "place", "piece": "M", "oi": 0, "x": 0, "y": 0})
    assert g.board[(0, 0)] == 1


def test_one_diagonal_contact_is_enough_for_the_whole_piece():
    """回归：不能要求拼块每一格都角接触；整块有一次即可。"""
    g = _game()
    g.act(1, {"op": "place", "piece": "M", "oi": 0, "x": 0, "y": 0})
    g.act(2, {"op": "place", "piece": "M", "oi": 0,
              "x": BOARD - 1, "y": BOARD - 1})
    oi = _orient_with(g.bag[1]["D"][1], (0, 0), (1, 0))
    g.act(1, {"op": "place", "piece": "D", "oi": oi, "x": 1, "y": 1})
    assert g.board[(1, 1)] == 1 and g.board[(2, 1)] == 1


def test_same_edge_contact_with_own_piece_is_rejected():
    g = _game()
    g.act(1, {"op": "place", "piece": "M", "oi": 0, "x": 0, "y": 0})
    g.act(2, {"op": "place", "piece": "M", "oi": 0,
              "x": BOARD - 1, "y": BOARD - 1})
    oi = _orient_with(g.bag[1]["D"][1], (0, 0), (0, 1))
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "place", "piece": "D", "oi": oi, "x": 0, "y": 1})


def test_empty_bag_is_skipped_instead_of_ending_immediately():
    """回归：某人拼块用完不应立刻终局，其余玩家继续。"""
    g = _game()
    g.bag[1] = {}
    assert g._advance_turn() is None
    assert g.turn == 1 and g.winner is None
    g.bag[2] = {}
    assert g._advance_turn() is not None
    assert g.winner is not None


def test_two_consecutive_passes_finish_two_player_game():
    g = _game()
    g.act(1, {"op": "pass"})
    assert g.winner is None
    g.act(2, {"op": "pass"})
    assert g.winner is not None
