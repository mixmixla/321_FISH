# -*- coding: utf-8 -*-
"""五子棋单人陪练：真实规则与 RoomManager 的有限专项回归。"""

import pytest

from games_pkg.base import GameRuleError
from games_pkg.gomoku_solo import AI_UID, GomokuSoloGame
from games_pkg.rooms import RoomManager


def _game(uid=1, seed=7):
    return GomokuSoloGame([uid], seed=seed)


def test_snapshot_marks_human_and_computer_without_fake_room_player():
    game = _game()
    state = game.snapshot()
    assert state["game"] == "gomoku_solo"
    assert state["size"] == 15
    assert state["players"] == [1]
    assert state["solo"] is True and state["ai_uid"] == AI_UID
    assert state["turn_uid"] == 1
    assert state["last_move"] is None and state["last_move_uid"] is None


def test_human_move_gets_immediate_local_computer_reply_and_is_repeatable():
    first = _game(seed=13)
    second = _game(seed=13)
    first_lines = first.act(1, {"x": 7, "y": 7})
    second_lines = second.act(1, {"x": 7, "y": 7})
    assert sum(v == 1 for row in first.board for v in row) == 1
    assert sum(v == 2 for row in first.board for v in row) == 1
    assert first.snapshot()["turn_uid"] == 1
    assert first.snapshot()["last_move_uid"] == AI_UID
    assert first.snapshot()["last_move"] == second.snapshot()["last_move"]
    assert first.board == second.board
    assert any("电脑" in line for line in first_lines)


def test_computer_takes_its_own_exact_five_before_heuristic_move():
    game = _game()
    for x in range(4):
        game.board[7][x] = 2
    game.board[0][0] = 1
    lines = game.act(1, {"x": 7, "y": 7})
    assert game.board[7][4] == 2
    assert game.winner_uid == AI_UID
    assert game.snapshot()["turn_uid"] is None
    assert game.ended() == {"winner_uid": AI_UID, "detail": "电脑 五连取胜"}
    assert any("电脑落子(4,7)" in line for line in lines)


def test_computer_blocks_human_immediate_five():
    game = _game()
    for x in range(2, 6):
        game.board[5][x] = 1
    game.board[0][0] = 2
    game.act(1, {"x": 7, "y": 7})
    # Both ends are legal blocks; center-first ordering chooses the right end
    # on this board, but either endpoint proves the must-block contract.
    assert game.board[5][1] == 2 or game.board[5][6] == 2
    assert game.winner_uid is None
    assert game.snapshot()["turn_uid"] == 1


def test_human_exact_five_ends_before_computer_reply():
    game = _game()
    for x in range(4):
        game.board[3][x] = 1
    lines = game.act(1, {"x": 4, "y": 3})
    assert game.winner_uid == 1
    assert game.last_move == (4, 3)
    assert game.snapshot()["last_move_uid"] == 1
    assert sum(v == 2 for row in game.board for v in row) == 0
    assert any("玩家1" in line for line in lines)


def test_human_overline_is_not_a_win_and_still_gets_ai_reply():
    game = _game()
    for x in range(6):
        game.board[7][x] = 1
    lines = game.act(1, {"x": 6, "y": 7})
    assert game.board[7][6] == 1
    assert game.winner_uid is None and game.draw is False
    assert game.snapshot()["turn_uid"] == 1
    assert game.snapshot()["last_move_uid"] == AI_UID
    assert any("电脑落子" in line for line in lines)


def test_duplicate_or_wrong_player_does_not_trigger_computer():
    game = _game()
    game.act(1, {"x": 7, "y": 7})
    before = [row[:] for row in game.board]
    with pytest.raises(GameRuleError):
        game.act(1, {"x": 7, "y": 7})
    assert game.board == before
    with pytest.raises(GameRuleError):
        game.act(2, {"x": 6, "y": 6})
    assert game.board == before


def test_full_board_becomes_draw_without_an_ai_extra_move(monkeypatch):
    game = _game()
    monkeypatch.setattr(game, "_check_win", lambda *args: False)
    for y in range(15):
        for x in range(15):
            game.board[y][x] = 1 if (x + y) % 2 == 0 else 2
    game.board[14][14] = 0
    game.act(1, {"x": 14, "y": 14})
    assert game.draw is True and game.winner_uid is None
    assert game.snapshot()["turn_uid"] is None
    assert game.ended() == {"winner_uid": None, "detail": "平局"}
    with pytest.raises(GameRuleError, match="本局已结束"):
        game.act(1, {"x": 0, "y": 0})


def test_room_manager_can_start_one_human_and_expose_settlement():
    manager = RoomManager({"gomoku_solo": GomokuSoloGame})
    room = manager.create(31, "gomoku_solo")
    assert room.players == [31]
    manager.start(31, room.room_id)
    manager.handle_action(31, room.room_id, {"x": 7, "y": 7})
    assert room.gs.snapshot()["solo"] is True
    assert sum(v == 1 for row in room.gs.board for v in row) == 1
    assert sum(v == 2 for row in room.gs.board for v in row) == 1
    with pytest.raises(GameRuleError):
        manager.handle_action(32, room.room_id, {"x": 0, "y": 0})


def test_room_rejects_second_player_for_solo_game():
    manager = RoomManager({"gomoku_solo": GomokuSoloGame})
    room = manager.create(31, "gomoku_solo")
    manager.join(32, room.room_id)
    assert room.players == [31]
    assert 32 in room.spectators
