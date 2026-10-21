# -*- coding: utf-8 -*-
"""合法着法私密投递的 TCP 证据：只有当前行动者收到 legal，且随回合转移。"""
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


class _Client:
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
    thread = threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                              daemon=True)
    thread.start()
    time.sleep(0.1)
    yield port
    stop.set()
    thread.join(timeout=2.0)
    hub.audit.close()


def test_only_current_player_receives_legal_moves(tcp_hub):
    a = _Client(tcp_hub, "legal-a")
    b = _Client(tcp_hub, "legal-b")
    try:
        assert a.hello() and b.hello()
        a.send({"t": "game_create", "game": "tictactoe"})
        created = a.wait("game_state", predicate=lambda e: e.get("state") is None)
        assert created
        rid = created["room_id"]
        b.send({"t": "game_join", "room_id": rid})
        assert b.wait("game_state", predicate=lambda e: e.get("room_id") == rid)
        a.send({"t": "game_start", "room_id": rid})
        started = a.wait("game_state", predicate=lambda e: (
            e.get("room_id") == rid and (e.get("room") or {}).get("status") == "playing"))
        assert started

        mine = a.wait("game_private", predicate=lambda e: e.get("room_id") == rid)
        assert mine and len(mine["state"].get("legal") or []) == 9
        assert b.wait("game_private", timeout=0.4) is None

        a.send({"t": "game_action", "room_id": rid, "action": {"x": 0, "y": 0}})
        theirs = b.wait("game_private", predicate=lambda e: (
            e.get("room_id") == rid and len(e["state"].get("legal") or []) == 8))
        assert theirs
        assert {"x": 0, "y": 0} not in (theirs["state"].get("legal") or [])
    finally:
        a.close()
        b.close()
