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
