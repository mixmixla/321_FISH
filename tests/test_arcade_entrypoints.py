"""New solo games through real rooms, Hub broadcasts and the normal Tk lobby."""
import copy
from dataclasses import replace
import socket
import threading
import time
import tkinter as tk
from types import SimpleNamespace

import pytest

import client
import client_gameui
from client_core import ClientCore
from config import CFG
from protocol import MsgType
from server import Hub, serve as serve_tcp
from test_server_game_lifecycle import (
    hub, _attach, _create, _frames, _defer_game_reset,
)


def _position(room, result):
    """Synthetic near-end boards; the final move and room lifecycle stay real."""
    game = room.gs
    if room.game_name == "gomoku_solo":
        game.board = [[0] * 15 for _ in range(15)]
        game.board[3][:4] = [1 if result == "win" else 2] * 4
        return {"x": 4, "y": 3} if result == "win" else {"x": 7, "y": 7}
    if result == "win":
        game.board = [[1024, 1024, 0, 0]] + [[0] * 4 for _ in range(3)]
    else:
        game.board = [[0, 2, 4, 8], [8, 16, 32, 64],
                      [32, 64, 128, 256], [128, 256, 512, 1024]]
    return {"op": "move", "dir": "left"}


@pytest.mark.parametrize("game", ["gomoku_solo", "tile2048"])
@pytest.mark.parametrize("result", ["win", "loss"])
def test_room_hub_final_result_both_session_types_and_restart(hub, monkeypatch, game, result):
    owner, owner_out = _attach(hub, "arcade-owner")
    watcher, watcher_out = _attach(hub, "arcade-watcher", "web")
    rid = _create(hub, owner, game)
    hub.dispatch(watcher, {"t": "game_spectate", "room_id": rid})
    hub.dispatch(owner, {"t": "game_start", "room_id": rid})
    room = hub.rooms.room_for(rid)
    assert room.players == [owner.uid]
    assert room.gs.snapshot()["players"] == [owner.uid]
    before = copy.deepcopy(room.gs.snapshot())
    hub.dispatch(watcher, {"t": "game_action", "room_id": rid,
                           "action": {"x": 0, "y": 0, "op": "move", "dir": "left"}})
    assert room.gs.snapshot() == before
    assert _frames(watcher_out, MsgType.ERROR.value)

    callbacks = _defer_game_reset(hub, monkeypatch)
    action = _position(room, result)
    hub.dispatch(owner, {"t": "game_action", "room_id": rid, "action": action})
    winner = owner.uid if result == "win" else (-1 if game == "gomoku_solo" else None)
    assert room.status.value == "ended" and room.gs.ended()["winner_uid"] == winner
    for out in (owner_out, watcher_out):
        terminal = [f for f in _frames(out, "game_state")
                    if (f.get("room") or {}).get("status") == "ended"][-1]
        state = terminal["state"]
        assert state["winner_uid"] == winner and state["players"] == [owner.uid]
        if game == "gomoku_solo":
            assert state["ai_uid"] == -1
            if result == "loss":
                assert "电脑" in " ".join(terminal["events"])
                assert len(client_gameui.flagship_win_line(state, 5)) == 5
        else:
            assert state["status"] == ("won" if result == "win" else "lost")
            assert isinstance(state["score"], int)
    previous = room.gs
    assert len(callbacks) == 1
    callbacks[0]()
    assert room.status.value == "created" and room.gs is None
    hub.dispatch(owner, {"t": "game_start", "room_id": rid})
    assert room.status.value == "playing" and room.round_no == 2
    assert room.gs is not previous and room.gs.ended() is None


def _wait(predicate, root=None, timeout=6):
    deadline = time.monotonic() + timeout
    if root is not None:
        # The production client runs mainloop. update() alone cannot service
        # a Tcl call queued by Pillow image finalization on a network thread.
        def check():
            if predicate() or time.monotonic() >= deadline:
                root.quit()
            else:
                root.after(15, check)
        root.after(0, check)
        root.mainloop()
        assert predicate(), "timed out waiting for real arcade state"
        return
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.015)
    assert predicate(), "timed out waiting for real arcade state"


@pytest.fixture
def live_core(tmp_path):
    import gc
    gc.collect()  # Dispose of prior Tk test objects on their owning thread.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    h = Hub(cfg=replace(CFG, bind_host="127.0.0.1", admin_pwd="",
                         audit_dir=str(tmp_path / "audit"),
                         web_files_dir=str(tmp_path / "web")),
            audit_dir=str(tmp_path / "audit"))
    stop = threading.Event()
    worker = threading.Thread(target=serve_tcp, args=(h, port, stop, False), daemon=True)
    worker.start()
    observed = []
    core = ClientCore(host="127.0.0.1", port=port, nick="arcade-tk-synthetic",
                      history_dir=str(tmp_path / "history"), reconnect_base=0.05,
                      on_event=observed.append)
    core._arcade_observed = observed
    core.start()
    try:
        _wait(lambda: core.connected and core.uid is not None)
        assert core.game_list()
        _wait(lambda: "tile2048" in core.game_meta)
        yield h, core
    finally:
        core.stop()
        stop.set()
        worker.join(6)
        assert not worker.is_alive()


def _button(widget, label):
    for child in widget.winfo_children():
        if isinstance(child, tk.Button) and child.cget("text") == label:
            return child
        found = _button(child, label)
        if found is not None:
            return found
    return None


@pytest.mark.parametrize("game", ["gomoku_solo", "tile2048"])
def test_real_tk_lobby_socket_play_loss_return_and_restart(live_core, game):
    h, core = live_core
    root = tk.Tk()
    root.withdraw()
    app = SimpleNamespace(root=root, core=core, _frameless=False,
                          _camo_title=lambda: "Synthetic arcade trial")
    gw = client.GameWindow(app, pal=client._DEFAULT_PAL)
    try:
        gw.win.geometry("1000x760")
        _wait(lambda: game in core.game_meta, root)
        gw._sync()
        gw.game_players_var.set("1")
        assert {"tile2048", "gomoku_solo"} <= set(gw.game_cards)
        gw.game_cards[game].create_btn.invoke()
        _wait(lambda: core.game_room is not None, root)
        assert core.game_room["players"] == [core.uid]
        _button(gw.win, "开始").invoke()
        _wait(lambda: core.game_state is not None, root)
        gw._sync()
        root.update()
        rid = core.game_room["room_id"]
        room = h.rooms.room_for(rid)
        if game == "gomoku_solo":
            ui = gw._cv_ui
            gw.game_cv.event_generate("<Button-1>", x=int(ui["ox"]), y=int(ui["oy"]), when="tail")
            _wait(lambda: sum(bool(v) for row in (core.game_state or {}).get("board", [])
                              for v in row) == 2, root)
            assert core.game_state["board"][0][0] == 1
            assert core.game_state["last_move_uid"] == -1
        else:
            # Each real control dispatches through GameWindow -> Core -> TCP -> RoomManager.
            direction = room.gs.legal_moves(core.uid)[0]["dir"]
            labels = {"up": "↑ 上", "down": "↓ 下", "left": "← 左", "right": "→ 右"}
            initial = copy.deepcopy(core.game_state["board"])
            _button(gw.act_btns, labels[direction]).invoke()
            _wait(lambda: core.game_state["board"] != initial, root)
            # The second actual move is a focused Canvas key event.
            gw._sync(); root.update()
            direction = room.gs.legal_moves(core.uid)[0]["dir"]
            initial = copy.deepcopy(core.game_state["board"])
            gw.game_cv.focus_force(); root.update()
            assert gw.game_cv.focus_get() is gw.game_cv
            gw.game_cv.event_generate(f"<{direction.title()}>", when="tail")
            _wait(lambda: core.game_state["board"] != initial, root)
            gw._spawn_board_win(); root.update()
            board = gw._board_win
            board.redraw(force=True)
            direction = room.gs.legal_moves(core.uid)[0]["dir"]
            initial = copy.deepcopy(core.game_state["board"])
            board.game_cv.focus_force(); root.update()
            board.game_cv.event_generate(f"<{direction.title()}>", when="tail")
            _wait(lambda: core.game_state["board"] != initial, root)
            board.hide()
            # Text input keeps arrows for caret movement.
            calls = []
            original = core.game_action
            core.game_action = lambda *args: calls.append(args)
            gw._toggle_chat(); root.update()
            gw.chat_entry.focus_force(); root.update()
            assert gw.chat_entry.focus_get() is gw.chat_entry
            gw.chat_entry.event_generate("<Left>", when="tail"); root.update()
            assert not calls
            core.game_action = original

        with h.rooms.lock:
            action = _position(room, "loss")
        h._send_room_state(room)
        _wait(lambda: core.game_state["board"] == room.gs.snapshot()["board"], root)
        gw._sync()
        if game == "gomoku_solo":
            ui = gw._cv_ui
            gw.game_cv.event_generate("<Button-1>", x=int(ui["ox"] + action["x"] * ui["cell"]),
                                      y=int(ui["oy"] + action["y"] * ui["cell"]), when="tail")
        else:
            _button(gw.act_btns, "← 左").invoke()
        _wait(lambda: (core.game_room or {}).get("status") == "ended", root)
        gw._sync()
        text = gw.state_text.get("1.0", "end")
        assert ("电脑 获胜" if game == "gomoku_solo" else "无路可走") in text
        assert core.game_state["winner_uid"] == (-1 if game == "gomoku_solo" else None)
        _wait(lambda: (core.game_room or {}).get("status") == "created", root)
        _button(gw.win, "开始").invoke()
        _wait(lambda: core.game_state is not None and core.game_room["round"] == 2, root)
        assert core.game_state["winner_uid"] is None
        assert core.game_leave(rid)
        try:
            _wait(lambda: core.game_room is None, root)
        except AssertionError:
            pytest.fail(repr({"room": core.game_room, "rooms": h.rooms.list_rooms(),
                              "events": [{key: event.get(key) for key in
                                          ("t", "code", "text", "room_id")}
                                         for event in core._arcade_observed[-12:]]}))
    finally:
        gw.close()
        root.destroy()
        import gc
        gc.collect()
