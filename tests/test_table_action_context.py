"""A click is a decision about the board drawn in a specific player's room."""
from types import SimpleNamespace

import pytest

from client import GameWindow


@pytest.mark.parametrize("change", [
    "room", "round", "game", "uid", "public", "private", "disconnected",
    "ended", "nonmember", "spectator", "current",
])
@pytest.mark.parametrize("game, action", [
    ("dou", {"fx": 0, "fy": 2, "tx": 0, "ty": 3}),
    ("gongfang", {"op": "work", "id": 0}),
    ("lingdi", {"op": "place", "r": 4, "c": 4}),
    ("ludo", {"op": "roll"}),
])
def test_old_table_cannot_send_a_decision_into_the_current_room(game, action, change):
    sent = []
    core = SimpleNamespace(uid=7, connected=True,
                           game_room={"room_id": "A", "round": 1, "game": game,
                                      "status": "playing", "players": [7, 8], "spectators": []},
                           game_state={"game": game, "turn_uid": 7}, game_private={},
                           game_action=lambda rid, value: sent.append((rid, value)))
    frame = {"_room_context": ("A", 1), "state": core.game_state, "game": game,
             "me": 7, "_drawn_private": core.game_private}
    if change == "room":
        core.game_room["room_id"] = "B"
    elif change == "round":
        core.game_room["round"] = 2
    elif change == "game":
        core.game_room["game"] = "spy"
    elif change == "uid":
        core.uid = 8
    elif change == "public":
        core.game_state = dict(core.game_state)
    elif change == "private":
        core.game_private = dict(core.game_private)
    elif change == "disconnected":
        core.connected = False
    elif change == "ended":
        core.game_room["status"] = "ended"
    elif change == "nonmember":
        core.game_room["players"] = [8]
    elif change == "spectator":
        core.game_room["spectators"] = [7]
    GameWindow._do_action(SimpleNamespace(core=core), action, frame)
    assert sent == ([("A", action)] if change == "current" else [])
