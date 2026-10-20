# -*- coding: utf-8 -*-
"""飞行棋规则回归：普通点数移交回合、掷 6 再掷、起飞、吃子、终点精确与胜利。"""
import pytest

from games_pkg.base import GameRuleError
from games_pkg.ludo import FIN, TRACK, LudoGame


def _game(n=2):
    g = LudoGame(list(range(1, n + 1)), seed=1)
    g.need_roll = False
    return g


def test_non_six_move_hands_over_the_turn():
    g = _game()
    g.miles[1][0] = 0
    g.dice = 3
    g.act(1, {"op": "move", "idx": 0})
    assert g.miles[1][0] == 3
    assert g.turn == 1


def test_six_grants_another_roll():
    g = _game()
    g.miles[1][0] = 0
    g.dice = 6
    g.act(1, {"op": "move", "idx": 0})
    assert g.miles[1][0] == 6
    assert g.turn == 0


def test_six_takes_off_from_hangar():
    g = _game()
    g.dice = 6
    g.act(1, {"op": "move", "idx": 0})
    assert g.miles[1][0] == 0
    assert g.turn == 0


def test_capture_sends_opponent_back_to_hangar():
    g = _game()
    g.miles[1][0] = 0
    g.miles[2][0] = (3 - g._start(1)) % TRACK      # 对手正好停在 1 号机的目标格
    g.dice = 3
    g.act(1, {"op": "move", "idx": 0})
    assert g.miles[2][0] == -1


def test_must_finish_exactly():
    g = _game()
    g.miles[1][0] = FIN - 1
    g.dice = 2
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "move", "idx": 0})


def test_all_four_home_wins():
    g = _game()
    g.miles[1] = [FIN - 1, FIN, FIN, FIN]
    g.dice = 1
    g.act(1, {"op": "move", "idx": 0})
    assert g.winner == 1
