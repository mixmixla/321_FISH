"""Game-card filters: real Tk widgets and the embedded production JavaScript."""
import json
from pathlib import Path
import shutil
import subprocess
import tkinter as tk
from types import SimpleNamespace

import pytest

from games_pkg import GAME_META


@pytest.fixture
def lobby():
    import client
    from test_flagship_gui import _fake_game_core

    root = tk.Tk()
    root.withdraw()
    core = _fake_game_core()
    core.game_room = core.game_state = None
    core.game_meta = dict(GAME_META)
    created = []
    core.game_create = lambda name, options=None: created.append((name, options))
    app = SimpleNamespace(root=root, core=core, _frameless=False,
                          _camo_title=lambda: "Synthetic lobby filter")
    gw = client.GameWindow(app, pal=client._DEFAULT_PAL)
    try:
        gw.win.geometry("1000x720")
        gw._sync()
        root.update()
        yield root, gw, created
    finally:
        gw.close()
        root.destroy()


def test_tk_name_id_and_actual_player_count_compose(lobby):
    root, gw, _ = lobby
    gw.game_query_entry.insert(0, "铁路")
    assert set(gw.game_cards) == {"tielu"}
    gw.game_query_var.set(" TIELU ")
    assert set(gw.game_cards) == {"tielu"}
    gw.game_players_entry.insert(0, "4")
    assert set(gw.game_cards) == {"tielu"}
    gw.game_players_var.set("1")
    assert not gw.game_cards
    assert any("没有符合" in w.cget("text") for w in gw.game_inner.winfo_children())
    gw.game_query_var.set("")
    assert set(gw.game_cards) == {"go_solo", "balatro_solo", "gomoku_solo", "tile2048"}
    gw.game_players_var.set("2")
    assert {"gomoku", "tielu"} <= set(gw.game_cards)
    assert not {"go_solo", "rps"} & set(gw.game_cards)
    gw.game_players_var.set("4")
    assert {"tielu", "rps", "spy"} <= set(gw.game_cards)
    assert "gomoku" not in gw.game_cards
    # An unbounded GAME_META maximum also supports counts beyond the finite games.
    gw.game_players_var.set("17")
    assert "spy" in gw.game_cards and "tielu" not in gw.game_cards
    for invalid in ("0", "-1", "2.5", "abc"):
        gw.game_players_var.set(invalid)
        assert not gw.game_cards
    gw._clear_game_filter()
    root.update()
    assert set(gw.game_cards) == set(GAME_META)


def test_tk_creation_never_uses_a_hidden_selection(lobby):
    _, gw, created = lobby
    gw._on_pick_game("gomoku")
    gw.game_query_var.set("铁路")
    assert gw._sel_game is None
    gw._on_create_game("gomoku")
    assert not created
    gw._on_create()
    assert created == [("tielu", None)]
    gw.game_query_var.set("does-not-exist")
    gw._on_create()
    assert len(created) == 1 and gw._sel_game is None
    for name, count in (("go_solo", "1"), ("gomoku_solo", "1"), ("tile2048", "1"),
                        ("gomoku", "2"), ("rps", "3")):
        gw.game_query_var.set(name)
        gw.game_players_var.set(count)
        gw.game_cards[name].create_btn.invoke()
        assert created[-1] == (name, None)


def test_tk_live_refresh_and_resize_keep_filters_and_rooms(lobby):
    root, gw, _ = lobby
    gw.game_query_var.set("铁路")
    gw.game_players_var.set("4")
    gw._on_pick_game("tielu")
    gw.core.game_rooms = [{"room_id": "synthetic-room", "game": "gomoku", "owner_uid": 8,
                           "players": [8], "spectators": [], "status": "created"}]
    gw._sync()
    assert set(gw.room_cards) == {"synthetic-room"}
    assert set(gw.game_cards) == {"tielu"} and gw._sel_game == "tielu"
    for width, height in ((860, 600), (1000, 720), (1280, 760)):
        gw.win.geometry(f"{width}x{height}")
        root.update()
        assert gw.game_query_var.get() == "铁路" and gw.game_players_var.get() == "4"
        assert gw.game_cards["tielu"].winfo_manager() == "grid"
        assert gw.game_query_entry.winfo_width() >= 50
        assert gw._scroll_regions[1][0].winfo_height() >= 35
    gw.core.game_meta = {}
    gw._sync()
    assert not gw.game_cards and gw._sel_game is None
    gw.core.game_meta = dict(GAME_META)
    gw.core.game_rooms = []
    gw._sync()
    assert set(gw.game_cards) == {"tielu"} and not gw.room_cards
    assert gw.game_query_var.get() == "铁路" and gw.game_players_var.get() == "4"


def test_web_game_card_filters_and_creation(tmp_path):
    node = shutil.which("node")
    assert node, "production JavaScript validation requires Node"
    data = tmp_path / "games.json"
    data.write_text(json.dumps(GAME_META), encoding="utf-8")
    probe = Path(__file__).with_name("lobby_filter_probe.cjs")
    result = subprocess.run([node, str(probe), str(data)], capture_output=True,
                            text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["passed"] is True
