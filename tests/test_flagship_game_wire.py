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
            self.sock.close()
        except OSError:
            pass


@pytest.fixture()
def tcp_hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"), web_files_dir=str(tmp_path / "web"))
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


def _state_for(client, rid, status=None, timeout=5.0):
    return client.wait(
        "game_state",
        predicate=lambda event: event.get("room_id") == rid and (
            status is None or event.get("room", {}).get("status") == status),
        timeout=timeout,
    )


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
        started = _state_for(a, rid, status="playing")
        assert started and started["room"]["status"] == "playing"

        for index, action in enumerate(moves):
            actor = a if index % 2 == 0 else b
            actor.send({"t": "game_action", "room_id": rid, "action": action})
            if index < len(moves) - 1:
                assert _state_for(actor, rid, status="playing")

        ended = _state_for(a, rid, status="ended")
        assert ended and ended["state"]["winner_uid"] == a.uid
        assert ended["room"]["round"] == started["room"]["round"]

        reset = _state_for(a, rid, status="created", timeout=6.0)
        assert reset and reset["state"] is None
        round_before = reset["room"]["round"]
        a.send({"t": "game_start", "room_id": rid})
        restarted = _state_for(a, rid, status="playing")
        assert restarted and restarted["room"]["round"] == round_before + 1
        assert restarted["state"]["winner_uid"] is None
    finally:
        a.close()
        b.close()
