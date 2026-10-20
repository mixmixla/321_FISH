# -*- coding: utf-8 -*-
"""国际跳棋规则回归：飞王远走/远吃、吃子提示、无路可走判定、升王。

休闲版约定：不强制吃子、不强制连跳。
"""
import pytest

from games_pkg.base import GameRuleError
from games_pkg.checkers import (BLACK_KING, BLACK_MAN, N, RED_KING, RED_MAN,
                                CheckersGame)


def _game():
    g = CheckersGame([1, 2], seed=1)
    g.board = [[0] * N for _ in range(N)]
    g.turn = 0
    return g


def test_initial_piece_counts():
    g = CheckersGame([1, 2], seed=1)
    assert sum(row.count(BLACK_MAN) for row in g.board) == 12
    assert sum(row.count(RED_MAN) for row in g.board) == 12


def test_man_moves_forward_only():
    g = _game()
    g.board[2][1] = BLACK_MAN                      # (x=1, y=2)
    g.act(1, {"fx": 1, "fy": 2, "tx": 2, "ty": 3})
    assert g.board[3][2] == BLACK_MAN

    g2 = _game()
    g2.board[2][1] = BLACK_MAN
    with pytest.raises(GameRuleError):
        g2.act(1, {"fx": 1, "fy": 2, "tx": 0, "ty": 1})   # 后退


def test_man_capture_removes_enemy():
    g = _game()
    g.board[2][1] = BLACK_MAN
    g.board[3][2] = RED_MAN
    g.act(1, {"fx": 1, "fy": 2, "tx": 3, "ty": 4})
    assert g.board[3][2] == 0
    assert g.board[4][3] == BLACK_MAN


def test_flying_king_can_move_two_or_more_empty_squares():
    g = _game()
    g.board[1][1] = BLACK_KING
    g.act(1, {"fx": 1, "fy": 1, "tx": 3, "ty": 3})       # 恰好 2 格（旧版误判为吃子）
    assert g.board[3][3] == BLACK_KING

    g2 = _game()
    g2.board[1][1] = BLACK_KING
    g2.act(1, {"fx": 1, "fy": 1, "tx": 5, "ty": 5})      # 4 格
    assert g2.board[5][5] == BLACK_KING


def test_flying_king_captures_at_distance():
    g = _game()
    g.board[0][0] = BLACK_KING
    g.board[3][3] = RED_MAN
    g.act(1, {"fx": 0, "fy": 0, "tx": 5, "ty": 5})
    assert g.board[3][3] == 0
    assert g.board[5][5] == BLACK_KING


def test_flying_king_cannot_pass_through_pieces():
    g = _game()
    g.board[0][0] = BLACK_KING
    g.board[2][2] = BLACK_MAN
    with pytest.raises(GameRuleError):
        g.act(1, {"fx": 0, "fy": 0, "tx": 4, "ty": 4})


def test_has_move_sees_captures_not_only_quiet_moves():
    """回归：前向两格都被敌子堵住、但可跳吃时，不能误判无路可走。"""
    g = _game()
    g.board[2][1] = BLACK_MAN        # (x=1, y=2)
    g.board[3][0] = RED_MAN          # (x=0, y=3) 堵住前左
    g.board[3][2] = RED_MAN          # (x=2, y=3) 堵住前右，但可跳过它
    g.turn = 0
    assert g._has_move() is True


def test_non_capture_move_is_allowed_even_if_capture_exists():
    """休闲版：不强制吃子。"""
    g = _game()
    g.board[2][1] = BLACK_MAN        # (x=1, y=2)
    g.board[3][2] = RED_MAN          # (x=2, y=3) 有吃子机会
    g.act(1, {"fx": 1, "fy": 2, "tx": 0, "ty": 3})       # 选择普通移动
    assert g.board[3][0] == BLACK_MAN


def test_capturing_last_enemy_wins():
    g = _game()
    g.board[5][0] = BLACK_MAN
    g.board[6][1] = RED_MAN
    g.act(1, {"fx": 0, "fy": 5, "tx": 2, "ty": 7})
    assert g.winner == 1


def test_man_promotes_on_last_row():
    g = _game()
    g.board[6][1] = BLACK_MAN
    g.board[0][6] = RED_MAN          # 留一枚红子，避免吃光判胜
    g.act(1, {"fx": 1, "fy": 6, "tx": 2, "ty": 7})
    assert g.board[7][2] == BLACK_KING
