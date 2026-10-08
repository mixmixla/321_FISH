"""A room retained by spectators must become usable by its next players."""
import pytest

from games_pkg.base import GameRuleError
from games_pkg.gomoku import GomokuGame
from games_pkg.connect4 import Connect4Game
from games_pkg.rooms import RoomManager


@pytest.mark.parametrize('game_cls', [GomokuGame, Connect4Game])
def test_first_new_player_takes_abandoned_owner_without_promoting_spectators(game_cls):
    manager = RoomManager({game_cls.name: game_cls})
    room = manager.create(11, game_cls.name)
    manager.spectate(12, room.room_id)
    manager.leave(11, room.room_id)
    assert room.players == [] and room.spectators == {12}
    manager.join(13, room.room_id)
    manager.join(14, room.room_id)
    assert room.owner_uid == 13
    assert room.players == [13, 14] and room.spectators == {12}
    with pytest.raises(GameRuleError, match='只有房主'):
        manager.start(11, room.room_id)
    assert manager.start(13, room.room_id).status.value == 'playing'


@pytest.mark.parametrize('game_cls', [GomokuGame, Connect4Game])
def test_remaining_player_keeps_owner_and_full_room_join_cannot_steal_it(game_cls):
    manager = RoomManager({game_cls.name: game_cls})
    room = manager.create(21, game_cls.name)
    manager.join(22, room.room_id)
    manager.leave(21, room.room_id)
    assert room.owner_uid == 22
    manager.join(23, room.room_id)
    manager.join(24, room.room_id)
    assert room.owner_uid == 22 and room.spectators == {24}
    assert manager.start(22, room.room_id).status.value == 'playing'
