# -*- coding: utf-8 -*-
"""第 4a 批桌游 P0 回归：四子棋、拉密、播棋、情书、井字棋、跳棋。"""
import pytest

from games_pkg.base import GameRuleError
from games_pkg.connect4 import Connect4Game
from games_pkg.halma import ARM_CELLS, VALID, HalmaGame
from games_pkg.kalah import KalahGame
from games_pkg.lovelove import COUNT, LoveLoveGame
from games_pkg.rummikub import N_TILE, RummikubGame, color_of, num_of
from games_pkg.tictactoe import TicTacToeGame


# ---------------------------------------------------------------- 四子棋
def test_connect4_gravity_and_diagonal_win():
    g = Connect4Game([1, 2], seed=1)
    for x, y in ((0, 5), (1, 4), (2, 3)):
        g.board[y][x] = 1
    for y in (3, 4, 5):
        g.board[y][3] = 2
    g.turn = 0
    g.act(1, {"col": 3})                       # 落在 (3,2)，斜向四连
    assert g.board[2][3] == 1
    assert g.ended() == {"winner_uid": 1, "detail": "玩家1 四连取胜"}


def test_connect4_full_column_rejected_without_state_change():
    g = Connect4Game([1, 2], seed=1)
    for r in range(6):
        g.board[r][0] = 1
    before = [row[:] for row in g.board]
    with pytest.raises(GameRuleError):
        g.act(1, {"col": 0})
    assert g.board == before and g.turn == 0 and g.last_move is None


# ---------------------------------------------------------------- 井字棋
def test_tictactoe_diagonal_win():
    g = TicTacToeGame([1, 2], seed=1)
    g.act(1, {"x": 0, "y": 0})
    g.act(2, {"x": 1, "y": 0})
    g.act(1, {"x": 1, "y": 1})
    g.act(2, {"x": 2, "y": 1})
    g.act(1, {"x": 2, "y": 2})
    assert g.winner_uid == 1
    assert g.ended()["winner_uid"] == 1


def test_tictactoe_occupied_cell_rejected_without_state_change():
    g = TicTacToeGame([1, 2], seed=1)
    g.act(1, {"x": 1, "y": 1})
    before = [row[:] for row in g.board]
    with pytest.raises(GameRuleError):
        g.act(2, {"x": 1, "y": 1})
    assert g.board == before and g.turn == 1


# ---------------------------------------------------------------- 播棋
def test_kalah_both_sides_can_sow_using_wire_holes():
    g = KalahGame([11, 22], seed=1)
    g.act(11, {"hole": 1})                     # A 用 1~6
    assert g.cells[0] == 0 and g.cells[1] == 5 and g.turn == 22
    g.act(22, {"hole": 9})                     # B 用 8~14 的全局洞号
    assert g.cells[8] == 0 and g.cells[9] == 5 and g.turn == 11


def test_kalah_capture_takes_the_opposite_pit():
    g = KalahGame([1, 2], seed=3)
    g.cells = [1, 0, 4, 0, 0, 0, 20, 15, 5, 0, 0, 0, 3, 0]
    g.act(1, {"hole": 1})                      # 落在己方空穴 1，对侧 12 有 3 子
    assert g.cells[1] == 0 and g.cells[12] == 0
    assert g.cells[6] == 24                    # 20 + 1 + 3（对侧）全入 A 库
    assert sum(g.cells) == 48
    assert g.turn == 2 and not g.finished


def test_kalah_empty_side_finishes_and_awards_remaining_seeds():
    g = KalahGame([1, 2], seed=4)
    g.cells = [0, 0, 0, 0, 0, 1, 30, 11] + [1] * 6
    msgs = g.act(1, {"hole": 6})               # 最后一子落在自己库
    assert g.finished and g.ended()["winner_uid"] == 1
    assert g.cells[6] == 31 and g.cells[6] + g.cells[7] == 48
    assert not any("再走一次" in m for m in msgs)


# ---------------------------------------------------------------- 拉密
def _tile(color, num):
    for i in range(N_TILE):
        if color_of[i] == color and num_of[i] == num:
            return i
    raise AssertionError("牌不存在")


def _red_run(nums):
    return [_tile(0, n) for n in nums]


def test_rummikub_cannot_extend_before_initial_meld():
    """回归：此前未完成首任 30 点的玩家也能直接接续桌面牌组。"""
    g = RummikubGame([1, 2], seed=1)
    row = _red_run([9, 10, 11, 12])
    g.table = [list(row)]
    g.rack[1] = [_tile(0, 13)]
    g.initial_ok[1] = False
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "extend", "row": 0, "tiles": [_tile(0, 13)]})
    assert g.table == [row] and g.rack[1] == [_tile(0, 13)]


def test_rummikub_extend_rolls_back_when_tile_not_in_hand():
    """回归：此前先改桌面再验手牌，缺牌时报错却留下了接续后的牌组。"""
    g = RummikubGame([1, 2], seed=1)
    row = _red_run([9, 10, 11, 12])
    g.table = [list(row)]
    g.initial_ok[1] = True
    g.rack[1] = []
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "extend", "row": 0, "tiles": [_tile(0, 13)]})
    assert g.table == [row] and g.rack[1] == []
    # 拿到牌后同一动作应当成功
    g.rack[1] = [_tile(0, 13)]
    g.act(1, {"op": "extend", "row": 0, "tiles": [_tile(0, 13)]})
    assert g.table == [_red_run([9, 10, 11, 12, 13])]


def test_rummikub_meld_clears_rack_and_wins():
    g = RummikubGame([1, 2], seed=7)
    big = _red_run([9, 10, 11, 12])
    g.rack[1] = list(big)
    g.act(1, {"op": "meld", "tiles": big})
    assert g.rack[1] == [] and g.winner == 1
    assert g.ended()["winner_uid"] == 1


def test_rummikub_player_left_returns_tiles_and_rotates_turn():
    """回归：此前掉线者仍留在座位表里，回合转一圈后会落到无人可操作的他身上。"""
    g = RummikubGame([1, 2, 3], seed=1)
    bag_before = len(g.bag)
    g.turn = 2
    g.player_left(1)
    assert 1 not in g.players and 1 not in g.rack and 1 not in g.initial_ok
    assert len(g.bag) == bag_before + 14
    assert g.players[g.turn] == 3


# ---------------------------------------------------------------- 情书
def test_lovelove_baron_self_loss_does_not_skip_next_seat():
    """回归：此前男爵令自己出局后会跳过下一位玩家，座位顺序被打乱。"""
    g = LoveLoveGame([1, 2, 3], seed=1)
    g.alive = [1, 2, 3]
    g.turn_idx = 0
    g.hand = {1: 3, 2: 7, 3: 2}
    g.deck = [1, 1, 2]
    g.act(1, {"play": 3, "target": 2})          # 留下摸到的 2，比 7 小 → 自己出局
    assert g.alive == [2, 3]
    assert g.cur == 2                          # 必须交给座位上的下一位，而不是 3


def test_lovelove_handmaid_blocks_guard():
    """回归：此前侍女(4)不产生任何保护，护卫仍能猜中淘汰被保护者。"""
    g = LoveLoveGame([1, 2], seed=1)
    g.alive = [1, 2]
    g.turn_idx = 0
    g.hand = {1: 4, 2: 1}
    g.deck = [7, 6, 5]
    g.act(1, {"play": 4})
    assert 1 in g.miss and g.cur == 2
    assert g.hand[1] == 5
    g.act(2, {"play": 1, "target": 1, "val": 5})   # 1 的贴身牌正是 5
    assert 1 in g.alive and 2 in g.alive
    assert g.cur == 1 and 1 not in g.miss          # 保护到自己下次回合开始为止


def test_lovelove_deck_empty_keeps_hand_for_comparison():
    """回归：此前牌堆空时先把当前玩家手牌清成 0，再比大小，胜负会被算错。"""
    g = LoveLoveGame([1, 2], seed=1)
    g.alive = [1, 2]
    g.turn_idx = 0
    g.hand = {1: 7, 2: 3}
    g.deck = []
    g.act(1, {"play": 7})
    assert g.hand[1] == 7
    assert g.winner == 1 and g.ended()["winner_uid"] == 1


def test_lovelove_last_draw_ends_round_instead_of_passing_turn():
    """回归：此前摸走最后一张后仍把回合交给下一位，对方无牌可抽只能卡死。"""
    g = LoveLoveGame([1, 2], seed=1)
    g.alive = [1, 2]
    g.turn_idx = 0
    g.hand = {1: 2, 2: 5}
    g.deck = [3]
    g.act(1, {"play": 3})                      # 摸走最后一张并弃掉
    assert g.hand[1] == 2
    assert g.game_over and g.winner == 2        # 立即比手牌：5 > 2
    assert g.ended()["winner_uid"] == 2


def test_lovelove_can_play_the_drawn_card():
    """回归：此前只允许弃回合开始时那张牌，摸到的牌永远不能打出。"""
    g = LoveLoveGame([1, 2], seed=1)
    g.alive = [1, 2]
    g.turn_idx = 0
    g.hand = {1: 2, 2: 3}
    g.deck = [1, 1, 6]
    g.act(1, {"play": 6})                      # 弃摸到的国王
    assert g.discard[-1] == (1, 6)
    assert g.hand[1] == 2                      # 原来的 2 留下
    with pytest.raises(GameRuleError):
        g.act(2, {"play": 2})                  # 2 不在手牌/牌堆顶，要被拒绝


def test_lovelove_countess_must_be_discarded_with_princess():
    """回归：此前摸到公主时仍可弃公主以外的牌，伯爵夫人强制弃牌规则失效。"""
    g = LoveLoveGame([1, 2], seed=1)
    g.alive = [1, 2]
    g.turn_idx = 0
    g.hand = {1: COUNT, 2: 2}
    g.deck = [1, 8]
    with pytest.raises(GameRuleError):
        g.act(1, {"play": 8})
    g.act(1, {"play": COUNT})
    assert g.discard[-1] == (1, COUNT) and 1 in g.alive


def test_lovelove_player_left_does_not_move_turn_backwards():
    """回归：此前当前玩家离场时回合索引 -1，3 人局会倒回上一位玩家。"""
    g = LoveLoveGame([1, 2, 3], seed=1)
    g.alive = [1, 2, 3]
    g.turn_idx = 1                             # 轮到 2
    g.player_left(2)
    assert g.alive == [1, 3]
    assert g.cur == 3                          # 应交给下一位 3，而不是倒退到 1


# ---------------------------------------------------------------- 跳棋
def test_halma_left_arm_exists():
    """回归：此前左营区条件写反导致集合为空，四角星盘少了整个左翼。"""
    assert len(ARM_CELLS[3]) == 16
    assert (0, 4) in ARM_CELLS[3] and (3, 4) in ARM_CELLS[3]
    assert len(VALID) == 69
    assert (4, 4) in VALID                   # 中央连接区


def test_halma_four_players_can_leave_the_full_camp():
    """回归：此前左营区为空且中央不通，4 人满座时棋盘 64 格全被占死，谁都动不了。"""
    g = HalmaGame([1, 2, 3, 4], seed=1)
    counts = {u: sum(1 for v in g.board.values() if v[0] == u) for u in g.players}
    assert counts == {1: 16, 2: 16, 3: 16, 4: 16}
    assert g.arm_of == {1: 0, 2: 1, 3: 2, 4: 3}
    for u in g.players:
        assert any(g._targets(x, y) for (x, y), v in g.board.items() if v[0] == u), u


def test_halma_step_into_adjacent_camp_and_switch_turn():
    g = HalmaGame([1, 2], seed=1)
    assert (4, 3) in g.board and (5, 4) not in g.board
    g.act(1, {"fx": 4, "fy": 3, "tx": 5, "ty": 4})
    assert (4, 3) not in g.board and g.board[(5, 4)] == (1, 0)
    assert g.turn == 1


def test_halma_all_pieces_in_goal_arm_wins():
    g = HalmaGame([1, 2], seed=1)
    goal = set(ARM_CELLS[2])                   # 玩家1(座次0)的对角目标营
    goal.discard((4, 5))
    g.board = {cell: (1, 0) for cell in goal}
    g.board[(5, 4)] = (1, 0)                   # 最后一枚在右翼，斜走一步进营
    g.turn = 0
    msgs = g.act(1, {"fx": 5, "fy": 4, "tx": 4, "ty": 5})
    assert g.winner == 1
    assert g.ended()["winner_uid"] == 1
    assert any("获胜" in m for m in msgs)


def test_halma_player_left_clears_pieces_and_seat():
    """回归：此前掉线者的棋子永远占着格子，3 人局还会把回合轮到他身上。"""
    g = HalmaGame([1, 2, 3], seed=1)
    g.turn = 1                                 # 轮到玩家2
    g.player_left(2)
    assert g.n == 2 and 2 not in g.players and 2 not in g.arm_of
    assert all(v[0] != 2 for v in g.board.values())
    assert g.players[g.turn] == 3
