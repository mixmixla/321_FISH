"""Recent board selection is authoritative, including a deliberate empty selection."""
import copy
import tkinter as tk
from types import MethodType, SimpleNamespace

import pytest

from client import BoardFocusWindow, GameWindow
from games_pkg.rummikub import RummikubGame


def host_for_game():
    game = RummikubGame([1, 2], seed=1)
    game.rack[1] = [18, 20, 22, 42]  # legal opening red 10/11/12, plus a spare
    for tile in game.rack[1]:
        for pile in (game.bag, game.rack[2]):
            if tile in pile:
                pile.remove(tile)
    sent, hints = [], []

    def send(rid, action):
        sent.append((rid, copy.deepcopy(action)))
        game.act(1, action)

    core = SimpleNamespace(uid=1, game_state=game.snapshot(), game_action=send,
                           game_room=dict(room_id="synthetic", round=1,
                                          game="rummikub", status="playing"),
                           game_meta={"rummikub": {"label": "拉密"}})
    lobby, focus = ({"game": "rummikub", "sel": {},
                     "cards": [(0, 0, 30, 30, 42)], "repaint": lambda: None}
                    for _ in range(2))
    host = SimpleNamespace(core=core, _cv_ui=lobby, _last_board_ui=focus,
                           _sel_game="rummikub", win=None,
                           act_hint=SimpleNamespace(config=lambda **kw: hints.append(kw)))
    host._board_win = SimpleNamespace(_cv_ui=focus, active=lambda: True, host=host)
    for name in ("_board_uis", "_room_ctx", "_cur_game", "_do_action"):
        setattr(host, name, MethodType(getattr(GameWindow, name), host))
    return host, game, sent, hints, lobby, focus


@pytest.mark.parametrize("recent", ["lobby", "focus"])
def test_live_select_then_deselect_does_not_submit_other_board_tiles(recent):
    host, game, sent, hints, lobby, focus = host_for_game()
    root = tk.Tk()
    root.geometry("100x100")
    cv = tk.Canvas(root)
    cv.pack(fill="both", expand=True)
    try:
        root.update()
        chosen, other = (lobby, focus) if recent == "lobby" else (focus, lobby)
        other["sel"]["rmk"] = [18, 20, 22]
        if recent == "lobby":
            host.game_cv = cv
            callback = MethodType(GameWindow._on_cv_click, host)
        else:
            host._board_win.game_cv = cv
            callback = MethodType(BoardFocusWindow._on_click, host._board_win)
        cv.bind("<Button-1>", callback)
        for expected in ([42], []):
            cv.event_generate("<Button-1>", x=10, y=10)
            root.update()
            assert chosen["sel"]["rmk"] == expected
            assert host._last_board_ui is chosen
        before = copy.deepcopy(game.__dict__)
        GameWindow._submit_sel(host, {"op": "meld", "sel_key": "rmk"})
        assert sent == []
        after = copy.deepcopy(game.__dict__)
        assert after.pop("rng").getstate() == before.pop("rng").getstate()
        assert after == before
        assert hints[-1]["text"] == "先在棋盘上点选要出的牌"
        assert other["sel"]["rmk"] == [18, 20, 22]
    finally:
        root.destroy()


@pytest.mark.parametrize("last,active,expected", [
    ("lobby", True, "lobby"), ("focus", True, "focus"),
    (None, True, "focus"), (None, False, "lobby"),
])
def test_recent_and_default_sources_still_submit_legal_meld(last, active, expected):
    host, game, sent, _, lobby, focus = host_for_game()
    host._last_board_ui = {"lobby": lobby, "focus": focus}.get(last)
    host._board_win.active = lambda: active
    chosen = {"lobby": lobby, "focus": focus}[expected]
    chosen["sel"]["rmk"] = [18, 20, 22]
    other = focus if chosen is lobby else lobby
    other["sel"]["rmk"] = [42]
    GameWindow._submit_sel(host, {"op": "meld", "sel_key": "rmk"})
    assert sent == [("synthetic", {"op": "meld", "tiles": [18, 20, 22]})]
    assert game.table == [[18, 20, 22]] and game.rack[1] == [42]
    assert "rmk" not in lobby["sel"]
    if active:
        assert "rmk" not in focus["sel"]
    else:
        assert focus["sel"]["rmk"] == [42]  # inactive board is not a candidate


def test_no_selection_does_not_open_extension_dialog(monkeypatch):
    import widgets.dialogbox as dialogbox
    host, _, sent, hints, _, _ = host_for_game()
    monkeypatch.setattr(dialogbox, "ask_string", lambda *a, **kw: pytest.fail("empty selection opened modal"))
    GameWindow._submit_sel(host, {"op": "extend", "sel_key": "rmk", "need_row": True})
    assert not sent and hints[-1]["text"] == "先在棋盘上点选要出的牌"
