# -*- coding: utf-8 -*-
"""Real loopback TCP evidence for the two flagship room lifecycles.

These tests intentionally exercise the encrypted TCP server path rather than
the client UI.  The GUI probe owns the desktop contract; this file owns the
wire proof that a finished room returns to CREATED and can start a new round.
"""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, serve as serve_tcp


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _TcpClient:
    __test__ = False

    def __init__(self, port: int, nick: str):
        from crypto import client_handshake
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.chan = client_handshake(self.sock)
        self.nick = nick
        self.uid = None
        self.events = []
        self.lock = threading.Lock()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while True:
                header, _body = self.chan.recv_frame()
                with self.lock:
                    self.events.append(header)
        except Exception:
            pass

    def send(self, header: dict) -> None:
        self.chan.send_frame(header)

    def wait(self, kind: str, predicate=None, timeout: float = 5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                for index, event in enumerate(self.events):
                    if event.get("t") == kind and (
                            predicate is None or predicate(event)):
                        return self.events.pop(index)
            time.sleep(0.01)
        return None

    def hello(self):
        self.send({"t": "hello", "nick": self.nick})
        event = self.wait("welcome")
        if event:
            self.uid = event["uid"]
        return event

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
        self.reader.join(timeout=2.0)


@pytest.fixture()
def tcp_hub(tmp_path):
    cfg = replace(CFG, bind_host="127.0.0.1", discovery_enabled=False,
                  audit_dir=str(tmp_path / "audit"), web_files_dir=str(tmp_path / "web"))
    hub = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    server_thread = threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                                     daemon=True)
    server_thread.start()
    time.sleep(0.1)
    yield port
    stop.set()
    server_thread.join(timeout=2.0)
    hub.audit.close()


def _state_for(client, rid, status=None, timeout=5.0, *, round_no=None, stones=None):
    def matches(event):
        room = event.get("room", {})
        if event.get("room_id") != rid or (status is not None and room.get("status") != status):
            return False
        if round_no is not None and room.get("round") != round_no:
            return False
        if stones is not None:
            board = (event.get("state") or {}).get("board", [])
            if not board or sum(bool(cell) for row in board for cell in row) != stones:
                return False
        return True

    return client.wait(
        "game_state",
        predicate=matches,
        timeout=timeout,
    )


def test_state_wait_ignores_queued_previous_move_and_round():
    """A matching status alone is not an acknowledgement of the last move."""
    client = object.__new__(_TcpClient)
    client.lock = threading.Lock()
    def snapshot(round_no, board):
        return {"t": "game_state", "room_id": 7,
                "room": {"status": "playing", "round": round_no},
                "state": {"board": board}}
    previous_move = snapshot(2, [[1, 0]])
    previous_round = snapshot(1, [[1, 2]])
    current = snapshot(2, [[1, 2]])
    client.events = [previous_move, previous_round, current]
    assert _state_for(client, 7, "playing", round_no=2, stones=2) is current
    assert client.events == [previous_move, previous_round]


@pytest.mark.parametrize(
    ("game", "moves"),
    [
        ("gomoku", [
            {"x": 0, "y": 0}, {"x": 0, "y": 1},
            {"x": 1, "y": 0}, {"x": 1, "y": 1},
            {"x": 2, "y": 0}, {"x": 2, "y": 1},
            {"x": 3, "y": 0}, {"x": 3, "y": 1},
            {"x": 4, "y": 0},
        ]),
        ("connect4", [
            {"col": 0}, {"col": 0}, {"col": 1}, {"col": 1},
            {"col": 2}, {"col": 2}, {"col": 3},
        ]),
    ],
)
def test_flagship_tcp_finish_reset_and_restart(tcp_hub, game, moves):
    a = _TcpClient(tcp_hub, f"flagship-a-{game}")
    b = _TcpClient(tcp_hub, f"flagship-b-{game}")
    try:
        assert a.hello() and b.hello()
        a.send({"t": "game_create", "game": game})
        created = a.wait("game_state", predicate=lambda event: event.get("state") is None)
        assert created
        rid = created["room_id"]
        b.send({"t": "game_join", "room_id": rid})
        assert _state_for(b, rid)
        a.send({"t": "game_start", "room_id": rid})
        started = _state_for(a, rid, status="playing", stones=0)
        assert started and started["room"]["status"] == "playing"
        round_no = started["room"]["round"]
        assert _state_for(b, rid, "playing", round_no=round_no, stones=0)

        for index, action in enumerate(moves):
            actor = a if index % 2 == 0 else b
            actor.send({"t": "game_action", "room_id": rid, "action": action})
            final = index == len(moves) - 1
            for peer in (a, b):
                confirmed = _state_for(peer, rid, "ended" if final else "playing",
                                       round_no=round_no, stones=index + 1)
                assert confirmed, (game, index, peer.nick)
                state = confirmed["state"]
                if final:
                    assert state["winner_uid"] == a.uid
                else:
                    assert state["winner_uid"] is None
                    assert state["turn_uid"] == (b.uid if actor is a else a.uid)

        reset = _state_for(a, rid, status="created", timeout=6.0, round_no=round_no)
        assert reset and reset["state"] is None
        round_before = reset["room"]["round"]
        a.send({"t": "game_start", "room_id": rid})
        restarted = _state_for(a, rid, status="playing", round_no=round_before + 1, stones=0)
        assert restarted and restarted["room"]["round"] == round_before + 1
        assert restarted["state"]["winner_uid"] is None
    finally:
        a.close()
        b.close()
