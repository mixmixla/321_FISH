"""公共游戏生命周期：拒绝覆盖进行中或尚未复位的已结束对局。"""
import copy

import pytest

from games_pkg import GAME_TYPES
from games_pkg.base import GameRuleError
from games_pkg.rooms import RoomManager, RoomStatus


def _started_room():
    manager = RoomManager(GAME_TYPES)
    room = manager.create(1, "tictactoe")
    manager.join(2, room.room_id)
    manager.start(1, room.room_id)
    manager.handle_action(1, room.room_id, {"x": 0, "y": 0})
    return manager, room


@pytest.mark.parametrize("status", [RoomStatus.PLAYING, RoomStatus.ENDED])
def test_start_cannot_replace_live_or_unreset_game(status):
    manager, room = _started_room()
    room.status = status
    game = room.gs
    summary = copy.deepcopy(room.summary())
    snapshot = copy.deepcopy(game.snapshot())

    with pytest.raises(GameRuleError):
        manager.start(1, room.room_id)

    assert room.gs is game
    assert room.summary() == summary
    assert game.snapshot() == snapshot


def test_owner_can_start_fresh_round_after_room_reset():
    manager, room = _started_room()
    previous = room.gs
    room.status = RoomStatus.ENDED
    room.status = RoomStatus.CREATED  # 此用例只测start条件，实际Timer复位在Hub集成用例覆盖。
    room.gs = None
    manager.start(1, room.room_id)

    assert room.status == RoomStatus.PLAYING
    assert room.gs is not previous
    assert room.round_no == 2
    assert room.players == [1, 2]
    assert room.gs.snapshot()["board"] == [[0, 0, 0] for _ in range(3)]


def test_owner_and_player_minimum_rejections_preserve_room():
    manager = RoomManager(GAME_TYPES)
    room = manager.create(1, "spy")
    before = copy.deepcopy(room.summary())
    with pytest.raises(GameRuleError):
        manager.start(2, room.room_id)
    with pytest.raises(GameRuleError):
        manager.start(1, room.room_id)
    assert room.gs is None
    assert room.summary() == before


def test_unknown_room_start_does_not_change_other_room():
    manager, room = _started_room()
    before = copy.deepcopy(room.summary())
    game = room.gs
    with pytest.raises(GameRuleError):
        manager.start(1, "missing-room")
    assert room.summary() == before
    assert room.gs is game
