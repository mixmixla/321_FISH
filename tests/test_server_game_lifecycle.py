# -*- coding: utf-8 -*-
"""GameB：服务器游戏房间公共生命周期回归。"""
import copy
import threading
from dataclasses import replace

import pytest

import server as server_mod
from config import CFG
from protocol import MsgType
from server import Hub, Session


class _Capture:
    __test__ = False

    def __init__(self):
        self.frames = []

    def send(self, payload, body=b""):
        self.frames.append((copy.deepcopy(payload), bytes(body or b"")))


@pytest.fixture()
def hub(tmp_path):
    h = Hub(cfg=replace(CFG, audit_dir=str(tmp_path / "audit"),
                         web_files_dir=str(tmp_path / "web"), admin_pwd=""),
            audit_dir=str(tmp_path / "audit"))
    yield h
    h.audit.close()


def _attach(hub, nick, stype="tcp"):
    out = _Capture()
    sess = Session(0, nick, stype, "127.0.0.1", out.send)
    assert hub._attach(sess)
    return sess, out


def _frames(out, frame_type):
    return [f for f, _body in out.frames if f.get("t") == frame_type]


def _clear(*outs):
    for out in outs:
        out.frames.clear()


def _create(hub, sess, game):
    hub.dispatch(sess, {"t": MsgType.GAME_CREATE.value, "game": game})
    return next(iter(hub.rooms.rooms))


def _join_start(hub, owner, other, room_id):
    hub.dispatch(other, {"t": MsgType.GAME_JOIN.value, "room_id": room_id})
    hub.dispatch(owner, {"t": MsgType.GAME_START.value, "room_id": room_id})


def test_tictactoe_finish_keeps_public_snapshot_and_resets_once(hub, monkeypatch):
    a, a_out = _attach(hub, "ttt-a")
    b, b_out = _attach(hub, "ttt-b")
    rid = _create(hub, a, "tictactoe")
    _join_start(hub, a, b, rid)
    _clear(a_out, b_out)
    timers = []

    class _Timer:
        def __init__(self, delay, callback, *args, **kwargs):
            self.delay = delay
            self.callback = callback
            self.args = args
            self.kwargs = kwargs
            self.daemon = False
            timers.append(self)

        def start(self):
            self.started = True

        def fire(self):
            return self.callback(*self.args, **self.kwargs)

    monkeypatch.setattr(server_mod.threading, "Timer", _Timer)
    moves = [
        (a, {"x": 0, "y": 0}), (b, {"x": 0, "y": 1}),
        (a, {"x": 1, "y": 0}), (b, {"x": 1, "y": 1}),
        (a, {"x": 2, "y": 0}),
    ]
    for sess, action in moves:
        hub.dispatch(sess, {"t": MsgType.GAME_ACTION.value,
                             "room_id": rid, "action": action})

    room = hub.rooms.room_for(rid)
    assert room.status.value == "ended"
    ended = [f for f in _frames(a_out, MsgType.GAME_STATE.value)
             if f.get("room", {}).get("status") == "ended"]
    assert ended and ended[-1]["state"] is not None
    assert ended[-1]["state"]["winner_uid"] == a.uid
    assert len(timers) == 1 and timers[0].daemon is True

    # Duplicate finish callback/notification must not schedule a second reset.
    hub._finish_game(room, room.gs.ended())
    assert len(timers) == 1
    timers[0].fire()
    assert room.status.value == "created" and room.gs is None
    lobby = [f for f in _frames(a_out, MsgType.GAME_LIST.value)
             if any(r["room_id"] == rid and r["status"] == "created"
                    for r in f.get("rooms", []))]
    assert lobby
    # 旧 Timer 在新一轮已进入 ENDED 后也不能复位新 gs。
    with hub.rooms.lock:
        new_round = room.round_no + 1
        new_gs = room.game_cls(room.players, seed=hub.rooms._seed_for(room))
        room.round_no = new_round
        room.gs = new_gs
        room.status = type(room.status).ENDED
    timers[0].fire()
    assert room.status.value == "ended" and room.gs is new_gs


def test_game_permissions_spectator_and_start_guard(hub):
    owner, owner_out = _attach(hub, "owner")
    player, player_out = _attach(hub, "player")
    watcher, watcher_out = _attach(hub, "watcher")
    rid = _create(hub, owner, "tictactoe")
    hub.dispatch(watcher, {"t": MsgType.GAME_SPECTATE.value, "room_id": rid})
    hub.dispatch(player, {"t": MsgType.GAME_START.value, "room_id": rid})
    assert any(f.get("t") == MsgType.ERROR.value
               and f.get("code") == "game" for f, _ in player_out.frames)
    hub.dispatch(owner, {"t": MsgType.GAME_START.value, "room_id": rid})
    assert any(f.get("t") == MsgType.ERROR.value
               and f.get("code") == "game" for f, _ in owner_out.frames)
    hub.dispatch(player, {"t": MsgType.GAME_JOIN.value, "room_id": rid})
    hub.dispatch(owner, {"t": MsgType.GAME_START.value, "room_id": rid})
    room = hub.rooms.room_for(rid)
    assert room.status.value == "playing"
    hub.dispatch(watcher, {"t": MsgType.GAME_LEAVE.value, "room_id": rid})
    assert watcher.uid not in room.spectators
    hub.dispatch(owner, {"t": MsgType.GAME_START.value, "room_id": rid})
    assert room.status.value == "playing"


def test_kalah_disconnect_uses_native_player_left_and_ends_public_game(hub):
    leaver, leaver_out = _attach(hub, "kalah-a")
    winner, winner_out = _attach(hub, "kalah-b")
    rid = _create(hub, leaver, "kalah")
    _join_start(hub, leaver, winner, rid)
    _clear(leaver_out, winner_out)

    hub.unregister(leaver, "game_disconnect")

    room = hub.rooms.room_for(rid)
    assert room is not None and room.status.value == "ended"
    assert room.gs is not None and room.gs.ended()["winner_uid"] == winner.uid
    states = [f for f in _frames(winner_out, MsgType.GAME_STATE.value)
              if f.get("room", {}).get("room_id") == rid]
    assert states and states[-1]["state"] is not None
    assert states[-1]["state"]["winner_uid"] == winner.uid
    assert any("离开" in line for line in states[-1].get("events", []))


def test_non_native_leave_aborts_without_winner(hub):
    owner, owner_out = _attach(hub, "abort-owner")
    player, player_out = _attach(hub, "abort-player")
    rid = _create(hub, owner, "tictactoe")
    _join_start(hub, owner, player, rid)
    hub.dispatch(owner, {"t": MsgType.GAME_ACTION.value, "room_id": rid,
                         "action": {"x": 0, "y": 0}})
    _clear(owner_out, player_out)

    hub.dispatch(player, {"t": MsgType.GAME_LEAVE.value, "room_id": rid})

    room = hub.rooms.room_for(rid)
    assert room is not None and room.status.value == "ended"
    states = [f for f in _frames(owner_out, MsgType.GAME_STATE.value)
              if f.get("room", {}).get("room_id") == rid]
    assert states and states[-1]["state"]["winner_uid"] is None
    assert any("中止" in line for line in states[-1].get("events", []))


def test_game_leave_ack_clears_member_and_empty_room(hub):
    owner, owner_out = _attach(hub, "leave-owner")
    player, player_out = _attach(hub, "leave-player")
    rid = _create(hub, owner, "tictactoe")
    hub.dispatch(player, {"t": MsgType.GAME_JOIN.value, "room_id": rid})
    _clear(owner_out, player_out)

    hub.dispatch(player, {"t": MsgType.GAME_LEAVE.value, "room_id": rid})
    ack = [f for f in _frames(player_out, MsgType.GAME_STATE.value)
           if f.get("room_id") == rid]
    assert ack and player.uid not in ack[-1]["room"]["players"]
    assert player.uid not in hub.rooms.room_for(rid).members

    hub.dispatch(owner, {"t": MsgType.GAME_LEAVE.value, "room_id": rid})
    empty_ack = [f for f in _frames(owner_out, MsgType.GAME_STATE.value)
                 if f.get("room_id") == rid]
    assert empty_ack and empty_ack[-1].get("room") is None
    assert hub.rooms.room_for(rid) is None


def test_game_leave_ack_fanout_reaches_same_uid_sessions(hub):
    first, first_out = _attach(hub, "leave-multi")
    other, _other_out = _attach(hub, "leave-other")
    second, second_out = _attach(hub, "leave-multi", "web")
    assert first.uid == second.uid
    rid = _create(hub, first, "tictactoe")
    hub.dispatch(other, {"t": MsgType.GAME_JOIN.value, "room_id": rid})
    _clear(first_out, second_out)

    hub.dispatch(first, {"t": MsgType.GAME_LEAVE.value, "room_id": rid})

    for out in (first_out, second_out):
        acks = [f for f in _frames(out, MsgType.GAME_STATE.value)
                if f.get("room_id") == rid]
        assert acks and first.uid not in acks[-1]["room"]["players"]


def test_stale_finish_capture_cannot_end_replaced_round(hub, monkeypatch):
    owner, owner_out = _attach(hub, "stale-owner")
    player, player_out = _attach(hub, "stale-player")
    rid = _create(hub, owner, "tictactoe")
    _join_start(hub, owner, player, rid)
    room = hub.rooms.room_for(rid)
    with hub.rooms.lock:
        old_gs, old_round = room.gs, room.round_no
        room.round_no += 1
        room.gs = room.game_cls(room.players, seed=hub.rooms._seed_for(room))
        room.status = type(room.status).PLAYING
        new_gs = room.gs
    timers = []

    class _Timer:
        def __init__(self, delay, callback, *args, **kwargs):
            timers.append(self)
            self.callback = callback
            self.daemon = False

        def start(self):
            self.daemon = True

    monkeypatch.setattr(server_mod.threading, "Timer", _Timer)
    hub._finish_game(room, {"winner_uid": old_gs.players[0],
                            "detail": "旧轮"},
                     expected_gs=old_gs, expected_round=old_round)
    assert room.status.value == "playing" and room.gs is new_gs
    assert timers == []


def test_stale_tick_capture_cannot_finish_replaced_round(hub, monkeypatch):
    owner, _owner_out = _attach(hub, "tick-owner")
    player, _player_out = _attach(hub, "tick-player")
    rid = _create(hub, owner, "tictactoe")
    _join_start(hub, owner, player, rid)
    room = hub.rooms.room_for(rid)
    old_gs = room.gs
    old_round = room.round_no
    new_holder = []

    def old_tick(_now):
        with hub.rooms.lock:
            room.round_no += 1
            room.gs = room.game_cls(room.players, seed=hub.rooms._seed_for(room))
            room.status = type(room.status).PLAYING
            new_holder.append(room.gs)
        return []

    old_gs.tick = old_tick
    old_gs.ended = lambda: {"winner_uid": owner.uid, "detail": "旧 tick"}

    class _Stop:
        calls = 0

        def wait(self, _interval):
            self.calls += 1
            return self.calls > 1

    server_mod._game_tick_loop(hub, _Stop())
    assert new_holder and room.gs is new_holder[0]
    assert room.round_no != old_round
    assert room.status.value == "playing"
    assert old_gs is not room.gs


def test_game_state_fanout_reaches_all_same_uid_sessions(hub):
    first, first_out = _attach(hub, "same-game")
    other, other_out = _attach(hub, "other")
    second, second_out = _attach(hub, "same-game", "web")
    assert first.uid == second.uid
    _clear(first_out, other_out, second_out)

    rid = _create(hub, first, "tictactoe")
    assert any(f.get("t") == MsgType.GAME_STATE.value
               and f.get("room_id") == rid for f, _ in first_out.frames)
    assert any(f.get("t") == MsgType.GAME_STATE.value
               and f.get("room_id") == rid for f, _ in second_out.frames)


def test_action_snapshot_identity_guard_blocks_mixed_new_round_frame(hub):
    owner, owner_out = _attach(hub, "action-stale-owner")
    player, _player_out = _attach(hub, "action-stale-player")
    rid = _create(hub, owner, "tictactoe")
    _join_start(hub, owner, player, rid)
    _clear(owner_out)
    entered = threading.Event()
    resume = threading.Event()
    original = hub._game_state_payload

    def paused(room, events=None, **kwargs):
        entered.set()
        assert resume.wait(5)
        return original(room, events, **kwargs)

    hub._game_state_payload = paused
    thread = threading.Thread(
        target=hub.dispatch,
        args=(owner, {"t": MsgType.GAME_ACTION.value, "room_id": rid,
                       "action": {"x": 0, "y": 0}}),
        daemon=True)
    thread.start()
    assert entered.wait(5)
    with hub.rooms.lock:
        room = hub.rooms.room_for(rid)
        room.round_no += 1
        room.gs = room.game_cls(room.players, seed=hub.rooms._seed_for(room))
        room.status = type(room.status).PLAYING
    resume.set()
    thread.join(5)
    assert not thread.is_alive()
    assert not any(f.get("t") == MsgType.GAME_STATE.value
                   and f.get("events") == ["✅ 玩家1 落子（0,0）"]
                   for f, _ in owner_out.frames)


def test_tick_snapshot_identity_guard_blocks_mixed_new_round_frame(hub):
    owner, owner_out = _attach(hub, "tick-stale-owner")
    player, _player_out = _attach(hub, "tick-stale-player")
    rid = _create(hub, owner, "tictactoe")
    _join_start(hub, owner, player, rid)
    _clear(owner_out)
    room = hub.rooms.room_for(rid)
    old_gs = room.gs
    old_gs.tick = lambda _now: ["旧 tick 事件"]
    old_gs.ended = lambda: None
    entered = threading.Event()
    resume = threading.Event()
    original = hub._game_state_payload

    def paused(room, events=None, **kwargs):
        entered.set()
        assert resume.wait(5)
        return original(room, events, **kwargs)

    hub._game_state_payload = paused

    class _Stop:
        calls = 0

        def wait(self, _interval):
            self.calls += 1
            return self.calls > 1

    thread = threading.Thread(target=server_mod._game_tick_loop,
                              args=(hub, _Stop()), daemon=True)
    thread.start()
    assert entered.wait(5)
    with hub.rooms.lock:
        room.round_no += 1
        room.gs = room.game_cls(room.players, seed=hub.rooms._seed_for(room))
        room.status = type(room.status).PLAYING
    resume.set()
    thread.join(5)
    assert not thread.is_alive()
    assert not any(f.get("t") == MsgType.GAME_STATE.value
                   and "旧 tick 事件" in (f.get("events") or [])
                   for f, _ in owner_out.frames)


def test_game_leave_ack_send_error_does_not_block_other_same_uid_session(hub):
    first, first_out = _attach(hub, "ack-safe")
    other, _other_out = _attach(hub, "ack-other")
    bad, _bad_out = _attach(hub, "ack-safe", "web")
    good, good_out = _attach(hub, "ack-safe", "web")
    rid = _create(hub, first, "tictactoe")
    hub.dispatch(other, {"t": MsgType.GAME_JOIN.value, "room_id": rid})
    _clear(first_out, good_out)

    def broken_send(_payload, _body=b""):
        raise OSError("closed session")

    bad.send = broken_send
    hub.dispatch(first, {"t": MsgType.GAME_LEAVE.value, "room_id": rid})
    assert any(f.get("t") == MsgType.GAME_STATE.value
               and f.get("room_id") == rid for f, _ in good_out.frames)
