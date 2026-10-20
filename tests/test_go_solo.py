# -*- coding: utf-8 -*-
"""围棋·单人练习：玩家执黑、电脑执白；玩家每手后电脑立即应手。"""
from games_pkg.go import AI_UID, GoSoloGame


def _game():
    return GoSoloGame([1], seed=1)


def test_solo_snapshot_has_one_human_and_human_turn():
    g = _game()
    s = g.snapshot()
    assert s["players"] == [1] and s["solo"] is True
    assert s["turn_uid"] == 1 and s["ai_uid"] == AI_UID


def test_human_move_is_followed_by_an_immediate_ai_reply():
    g = _game()
    g.act(1, {"x": 4, "y": 4})
    black = sum(cell == 1 for row in g.board for cell in row)
    white = sum(cell == 2 for row in g.board for cell in row)
    assert black == 1 and white == 1          # 电脑已经应手
    assert g.snapshot()["turn_uid"] == 1      # 又轮到玩家


def test_ai_captures_a_group_in_atari():
    g = _game()
    g.board = [[0] * 9 for _ in range(9)]
    g.board[0][0] = 1                          # 黑子 (0,0)，仅剩 (0,1) 一气
    g.board[0][1] = 2                          # 白子 (1,0)
    g.board[1][1] = 2                          # 白子 (1,1)
    g.turn = 1
    assert g._ai_choose() == {"x": 0, "y": 1}
    g._apply(g._ai_choose(), 2)
    assert g.board[0][0] == 0                  # 黑子被提
    assert g.captured[1] == 1


def test_pass_pass_ends_the_solo_game():
    g = _game()
    g.act(1, {"pass": True})                   # 玩家过，电脑跟着过
    assert g.over is True
    assert g.snapshot()["turn_uid"] is None
    assert g.ended() is not None


def test_ai_winner_maps_to_computer_uid():
    g = _game()
    g.over = True
    g.scores = {1: 5, 2: 10}
    g.winner = g._decide_winner()
    assert g.winner == AI_UID
    res = g.ended()
    assert res["winner_uid"] == AI_UID and "电脑" in res["detail"]


def test_mcts_ai_never_returns_an_illegal_move():
    """短时限随机对练：电脑每手都必须能被引擎接受，且落子后回到玩家回合。"""
    import random

    from games_pkg.base import GameRuleError

    g = _game()
    g.mcts_time = 0.05
    rnd = random.Random(3)
    played = 0
    for _ in range(20):
        if g.over or g.winner:
            break
        empties = [(x, y) for y in range(g.size) for x in range(g.size)
                   if not g.board[y][x]]
        if not empties:
            break
        x, y = rnd.choice(empties)
        before_black = sum(cell == 1 for row in g.board for cell in row)
        try:
            g.act(1, {"x": x, "y": y})
        except GameRuleError:
            after_black = sum(cell == 1 for row in g.board for cell in row)
            assert after_black == before_black, "人类落子已生效但电脑着法非法"
            continue                      # 随机人类着法可能自杀/打劫，换一手
        played += 1
        assert g.over or g.snapshot()["turn_uid"] == 1
    assert played > 0
