# -*- coding: utf-8 -*-
"""服务器游戏房间 e2e：真 socket 全链路——游戏列表/建房/加入/观战/开始/
动作广播/非法动作拒绝/离开清理"""
import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, serve as serve_tcp


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)
    yield h, port, stop
    stop.set()
    time.sleep(0.2)


class TestClient:
    __test__ = False

    def __init__(self, port: int, nick: str) -> None:
        from crypto import client_handshake
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.chan = client_handshake(self.sock)
        self.nick = nick
        self.uid = None
        self.events = []
        self._lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            while True:
                h, _b = self.chan.recv_frame()
                with self._lock:
                    self.events.append(h)
        except Exception:
            pass

    def send(self, header: dict) -> None:
        self.chan.send_frame(header)

    def wait(self, t: str, timeout: float = 3.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, e in enumerate(self.events):
                    if e.get("t") == t and (pred is None or pred(e)):
                        del self.events[i]
                        return e
            time.sleep(0.01)
        return None

    def hello(self):
        self.send({"t": "hello", "nick": self.nick})
        w = self.wait("welcome")
        if w:
            self.uid = w["uid"]
        return w

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def test_game_list_metadata(hub):
    _, port, _ = hub
    a = TestClient(port, "alice")
    a.hello()
    a.send({"t": "game_list"})
    gl = a.wait("game_list")
    assert gl and gl["games"]
    names = {g["name"] for g in gl["games"]}
    assert {"guess_number", "gomoku", "uno", "spy"} <= names
    assert gl["rooms"] == []
    a.close()


def test_create_join_start_guess(hub):
    _, port, _ = hub
    a = TestClient(port, "alice")
    a.hello()
    b = TestClient(port, "bob")
    b.hello()
    a.send({"t": "game_create", "game": "guess_number"})
    st = a.wait("game_state", pred=lambda e: e.get("room_id", "").startswith("g"))
    assert st and st["state"] is None
    rid = st["room_id"]
    # 房间列表广播给所有人
    gl = b.wait("game_list", pred=lambda e: e["rooms"])
    assert any(r["room_id"] == rid and r["game"] == "guess_number"
               for r in gl["rooms"])
    # bob 加入
    b.send({"t": "game_join", "room_id": rid})
    st2 = b.wait("game_state", pred=lambda e: e.get("room_id") == rid)
    assert st2["room"]["players"] == [a.uid, b.uid]
    # alice 开始
    a.send({"t": "game_start", "room_id": rid})
    st3 = a.wait("game_state", pred=lambda e: e.get("state") is not None)
    assert st3["state"]["game"] == "guess_number"
    assert st3["state"]["status"] == "await_secret"
    # bob 抢出题（非房主应被拒）
    b.send({"t": "game_action", "room_id": rid,
            "action": {"secret": 42}})
    err = b.wait("error", pred=lambda e: e.get("code") == "game")
    assert err
    # alice 出题
    a.send({"t": "game_action", "room_id": rid, "action": {"secret": 42}})
    st4 = a.wait("game_state",
                 pred=lambda e: any("出题完成" in x for x in e.get("events", [])))
    assert st4["state"]["status"] == "playing"
    # bob 猜中
    b.send({"t": "game_action", "room_id": rid, "action": {"guess": 42}})
    st5 = a.wait("game_state", pred=lambda e: any("猜中" in e for e in e.get("events", [])))
    assert st5["state"]["correct_uid"] == b.uid
    assert st5["state"]["scores"][str(b.uid)] == 1
    a.close(); b.close()


def test_spectate_cannot_act(hub):
    _, port, _ = hub
    a = TestClient(port, "alice")
    a.hello()
    a.send({"t": "game_create", "game": "gomoku"})
    st = a.wait("game_state")
    rid = st["room_id"]
    c = TestClient(port, "carol")
    c.hello()
    c.send({"t": "game_spectate", "room_id": rid})
    st2 = c.wait("game_state", pred=lambda e: e.get("room_id") == rid)
    assert st2["room"]["spectators"] == [c.uid]
    c.send({"t": "game_action", "room_id": rid, "action": {}})
    assert c.wait("error", pred=lambda e: e.get("code") == "game")
    a.close(); c.close()


def test_leave_closes_empty_room(hub):
    _, port, _ = hub
    a = TestClient(port, "alice")
    a.hello()
    a.send({"t": "game_create", "game": "rps"})
    st = a.wait("game_state")
    rid = st["room_id"]
    a.send({"t": "game_leave", "room_id": rid})
    gl = a.wait("game_list", pred=lambda e: e["rooms"] == [])
    assert gl
    a.close()
