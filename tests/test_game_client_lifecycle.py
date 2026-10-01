"""客户端只接受本端房间的离开确认，不能保留或复活旧私密状态。"""
import copy
from collections import deque

import pytest

from client_core import ClientCore


def _core():
    core = ClientCore.__new__(ClientCore)
    core.uid = 1
    core.game_room = {"room_id": "g1", "game": "tictactoe", "status": "playing",
                      "players": [1, 2], "spectators": [], "round": 1}
    core.game_state = {"board": [[1, 0, 0]], "turn_uid": 2}
    core.game_private = {"hand": ["synthetic-old"]}
    core.game_events = deque(["old-event"], maxlen=200)
    core._game_left_rooms = set()
    core.sent = []
    core.pushed = []
    core._send_frame = lambda h, body=b"": core.sent.append(copy.deepcopy(h)) or True
    core._push = lambda h: core.pushed.append(copy.deepcopy(h))
    return core


def _frame(rid="g1", uid=1, status="playing", round_no=1):
    return {"t": "game_state", "room_id": rid,
            "room": {"room_id": rid, "game": "tictactoe", "status": status,
                     "players": [uid, 2], "spectators": [], "round": round_no},
            "state": {"board": [[1, 0, 0]], "winner_uid": 1}, "events": ["fresh"]}


@pytest.mark.parametrize("room", [None, {"room_id": "g1", "players": [2], "spectators": []}])
def test_matching_leave_ack_clears_public_private_and_events(room):
    core = _core()
    core._dispatch({"t": "game_state", "room_id": "g1", "room": room,
                    "state": None, "events": ["left"]})
    assert core.game_room is None
    assert core.game_state is None
    assert core.game_private is None
    assert not core.game_events
    assert core.pushed[-1]["room_id"] == "g1"


def test_unrelated_room_leave_ack_cannot_clear_current_room():
    core = _core()
    room, state, private = core.game_room, core.game_state, core.game_private
    core._dispatch({"t": "game_state", "room_id": "g-other", "room": None,
                    "state": None, "events": ["unrelated"]})
    assert core.game_room is room and core.game_state is state
    assert core.game_private is private
    assert list(core.game_events) == ["old-event"]
    assert core.pushed == []


def test_late_frames_cannot_restore_left_room_but_explicit_rejoin_can():
    core = _core()
    core._dispatch({"t": "game_state", "room_id": "g1", "room": None, "state": None})
    core._dispatch(_frame())
    core._dispatch({"t": "game_private", "room_id": "g1", "state": {"hand": ["stale"]}})
    assert core.game_room is None and core.game_private is None

    assert core.game_join("g1")
    core._dispatch(_frame())
    assert core.game_room["room_id"] == "g1"
    assert core.game_state["winner_uid"] == 1


def test_private_frame_is_bound_to_current_playing_room():
    core = _core()
    private = core.game_private
    core._dispatch({"t": "game_private", "room_id": "g-other", "state": {"hand": ["wrong"]}})
    assert core.game_private is private
    core._dispatch({"t": "game_private", "room_id": "g1", "state": {"hand": ["fresh"]}})
    assert core.game_private == {"hand": ["fresh"]}


def test_ended_snapshot_survives_but_private_state_does_not():
    core = _core()
    frame = _frame(status="ended")
    core._dispatch(frame)
    assert core.game_state == frame["state"]
    assert core.game_room["status"] == "ended"
    assert core.game_private is None
    core._dispatch({"t": "game_private", "room_id": "g1", "state": {"hand": ["late"]}})
    assert core.game_private is None


def test_new_round_resets_private_and_old_event_history():
    core = _core()
    core._dispatch(_frame(round_no=2))
    assert core.game_private is None
    assert list(core.game_events) == ["fresh"]


def test_spectator_state_is_a_valid_current_membership():
    core = _core()
    frame = _frame(uid=3)
    frame["room"]["spectators"] = [1]
    core._dispatch(frame)
    assert core.game_room == frame["room"]
    assert core.game_state == frame["state"]


@pytest.mark.parametrize("method", ["game_join", "game_spectate"])
def test_reentry_state_arriving_before_send_returns_is_not_lost(method):
    core = _core()
    core._dispatch({"t": "game_state", "room_id": "g1", "room": None})
    frame = _frame()
    if method == "game_spectate":
        frame["room"]["players"] = [2, 3]
        frame["room"]["spectators"] = [1]

    def send_and_receive_before_return(header, body=b""):
        core._dispatch(frame)
        return True

    core._send_frame = send_and_receive_before_return
    assert getattr(core, method)("g1")
    assert core.game_room == frame["room"]
    assert core.game_state == frame["state"]


@pytest.mark.parametrize("method", ["game_join", "game_spectate"])
def test_failed_reentry_send_preserves_stale_frame_fence(method):
    core = _core()
    core._dispatch({"t": "game_state", "room_id": "g1", "room": None})
    core._send_frame = lambda *_: False
    assert not getattr(core, method)("g1")
    core._dispatch(_frame())
    assert core.game_room is None
    assert "g1" in core._game_left_rooms
