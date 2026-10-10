# -*- coding: utf-8 -*-
"""房间生命周期/权限/GC 单测"""
import pytest

from games_pkg import GAME_TYPES
from games_pkg.base import GameRuleError
from games_pkg.rooms import RoomManager, RoomStatus


@pytest.fixture()
def mgr():
    return RoomManager(GAME_TYPES)


def test_create_join_leave(mgr):
    room = mgr.create(1, "gomoku")
    assert room.game_name == "gomoku"
    mgr.join(2, room.room_id)
    assert room.players == [1, 2]
    assert mgr.leave(2, room.room_id) is False
    assert mgr.leave(1, room.room_id) is True   # 空房关闭


def test_join_full_auto_spectate(mgr):
    room = mgr.create(1, "gomoku")       # max 2
    mgr.join(2, room.room_id)
    mgr.join(3, room.room_id)            # 满员自动观战
    assert room.players == [1, 2]
    assert 3 in room.spectators


def test_spectate_cannot_act(mgr):
    room = mgr.create(1, "guess_number")
    mgr.join(2, room.room_id)
    mgr.spectate(3, room.room_id)
    mgr.start(1, room.room_id)
    with pytest.raises(GameRuleError):
        mgr.handle_action(3, room.room_id, {"guess": 50})


def test_min_players_enforced(mgr):
    room = mgr.create(1, "spy")          # min 4
    with pytest.raises(GameRuleError):
        mgr.start(1, room.room_id)


def test_owner_handover(mgr):
    room = mgr.create(1, "rps")
    mgr.join(2, room.room_id)
    mgr.join(3, room.room_id)
    mgr.leave(1, room.room_id)
    assert room.owner_uid == 2
    assert 1 not in room.players


def test_game_state_only_members(mgr):
    """快照投递集合 = 成员；观战可收 state 但不在 players"""
    room = mgr.create(1, "guess_number")
    mgr.join(2, room.room_id)
    mgr.spectate(9, room.room_id)
    assert set(room.members) == {1, 2, 9}
    mgr.start(1, room.room_id)
    snap = room.gs.snapshot()
    assert snap["game"] == "guess_number"


def test_unknown_game_rejected(mgr):
    with pytest.raises(GameRuleError):
        mgr.create(1, "不存在")


def test_disconnect_cleanup(mgr):
    room = mgr.create(1, "gomoku")
    mgr.join(2, room.room_id)
    mgr.on_disconnect(2)
    mgr.on_disconnect(1)
    assert room.room_id not in mgr.rooms


# ---- A6 通用动作层：认输 / 悔棋 / 求和 ----

def _start_gomoku(mgr):
    room = mgr.create(1, "gomoku")
    mgr.join(2, room.room_id)
    mgr.start(1, room.room_id)
    return room


def test_common_layer_only_wraps_listed_games(mgr):
    room = _start_gomoku(mgr)
    assert "common" in room.gs.snapshot()            # 棋类被代理
    g = mgr.create(1, "guess_number")
    mgr.join(2, g.room_id)
    mgr.start(1, g.room_id)
    assert "common" not in g.gs.snapshot()           # 未接入者不受影响


def test_common_resign_ends_game(mgr):
    room = _start_gomoku(mgr)
    msgs = mgr.handle_action(1, room.room_id, {"op": "resign"})
    assert msgs and "认输" in msgs[0]
    ended = room.gs.ended()
    assert ended["winner_uid"] == 2 and "认输" in ended["detail"]


def test_common_undo_without_history_rejected(mgr):
    room = _start_gomoku(mgr)
    with pytest.raises(GameRuleError):
        mgr.handle_action(1, room.room_id, {"op": "undo"})


def test_common_undo_rolls_back(mgr):
    room = _start_gomoku(mgr)
    mgr.handle_action(1, room.room_id, {"x": 0, "y": 0})
    mgr.handle_action(2, room.room_id, {"x": 1, "y": 1})
    mgr.handle_action(1, room.room_id, {"op": "undo"})   # 回退到玩家2落子前
    board = room.gs.snapshot()["board"]
    assert board[0][0] == 1 and board[1][1] == 0


def test_common_draw_flow(mgr):
    room = _start_gomoku(mgr)
    with pytest.raises(GameRuleError):                   # 不能回应自己的求和
        mgr.handle_action(1, room.room_id, {"op": "draw_accept"})
    mgr.handle_action(1, room.room_id, {"op": "draw"})
    assert room.gs.snapshot()["common"]["draw_offer"] == 1
    mgr.handle_action(2, room.room_id, {"op": "draw_reject"})
    assert room.gs.snapshot()["common"]["draw_offer"] is None
    mgr.handle_action(1, room.room_id, {"op": "draw"})
    mgr.handle_action(2, room.room_id, {"op": "draw_accept"})
    assert room.gs.ended() == {"winner_uid": None, "detail": "双方同意，和局"}
