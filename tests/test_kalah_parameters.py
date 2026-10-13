"""Desktop local numbering, modal identity and real Kalah rules."""
import copy
from types import MethodType, SimpleNamespace

import pytest

import client
from client import GameWindow
from games_pkg.kalah import KalahGame

SPEC = {"key": "hole", "kind": "int"}


def make_host(uid):
    game = KalahGame([11, 22], seed=1)
    if uid == 22:
        game.act(11, {"hole": 1})  # natural A -> B
        assert game.turn == 22
    sent, hints = [], []

    def send(rid, action):
        sent.append((rid, copy.deepcopy(action)))
        game.act(core.uid, action)

    core = SimpleNamespace(uid=uid, connected=True, game_state=game.snapshot(),
                           game_room=dict(room_id="synthetic", round=1, game="kalah",
                                          status="playing", players=[11, 22]),
                           game_meta={"kalah": {"label": "播棋"}}, game_action=send)
    host = SimpleNamespace(core=core, win=None, _sel_game="kalah", _cv_ui={}, _board_win=None,
                           act_hint=SimpleNamespace(config=lambda **kw: hints.append(kw)))
    for name in ("_cur_game", "_room_ctx", "_parse_action", "_do_action", "_kalah_parameter_action", "_kalah_can_submit"):
        if hasattr(GameWindow, name):
            setattr(host, name, MethodType(getattr(GameWindow, name), host))
    host._nick = lambda who: {11: "阿甲", 22: "阿乙"}.get(who, "旁观者")
    return host, game, sent, hints


def input_value(monkeypatch, value, during=None):
    import widgets.dialogbox as dialogbox

    def ask(*a):
        if during:
            during()
        return value

    monkeypatch.setitem(client._KIND_INPUTS, "int", ask)
    monkeypatch.setattr(dialogbox, "show_message", lambda *a, **kw: None)


@pytest.mark.parametrize("uid", [11, 22])
@pytest.mark.parametrize("local", range(1, 7))
def test_each_local_hole_is_accepted_by_real_rules(monkeypatch, uid, local):
    host, game, sent, _ = make_host(uid)
    expected = copy.deepcopy(game)
    wire = local if uid == 11 else local + 8
    expected.act(uid, {"hole": wire})
    input_value(monkeypatch, str(local))
    GameWindow._ask_params(host, SPEC, "输入本方洞号1~6")
    assert sent == [("synthetic", {"hole": wire})]
    assert game.snapshot() == expected.snapshot()
    assert sum(game.cells) == 48


@pytest.mark.parametrize("change", ["room_id", "round", "game", "uid", "seats"])
def test_modal_context_change_discards_parameter(monkeypatch, change):
    host, game, sent, hints = make_host(22)

    def mutate():
        if change in ("room_id", "round", "game"):
            host.core.game_room[change] = {"room_id": "new-room", "round": 2, "game": "gemcity"}[change]
        elif change == "uid":
            host.core.uid = 11
        else:
            host.core.game_state = dict(host.core.game_state, p0=22, p1=11)

    before = copy.deepcopy(game.cells)
    input_value(monkeypatch, "1", mutate)
    GameWindow._ask_params(host, SPEC, "输入本方洞号1~6")
    assert sent == [] and game.cells == before
    assert hints[-1]["text"] == "对局已变化，请重新操作"


@pytest.mark.parametrize("case", ["observer", "turn", "room-ended", "draw", "winner",
                                  "empty", "disconnected", "not-seated", "wrong-state"])
@pytest.mark.parametrize("phase", ["before", "during"])
def test_latest_state_blocks_unavailable_action(monkeypatch, case, phase):
    host, game, sent, _ = make_host(22)

    def mutate():
        core = host.core
        if case == "observer":
            core.uid = 99
        elif case == "turn":
            core.game_state["turn"] = 11
        elif case == "room-ended":
            core.game_room["status"] = "ended"
        elif case in ("draw", "winner"):
            core.game_state["status"] = "ended"
            core.game_state["winner_uid"] = 22 if case == "winner" else None
        elif case == "empty":
            core.game_state["cells"] = list(core.game_state["cells"])
            core.game_state["cells"][8] = 0
        elif case == "disconnected":
            core.connected = False
        elif case == "not-seated":
            core.game_room["players"] = [11]
        else:
            core.game_state["game"] = "gemcity"

    if phase == "before":
        mutate()
    before = copy.deepcopy(game.__dict__)
    input_value(monkeypatch, "1", mutate if phase == "during" else None)
    GameWindow._ask_params(host, SPEC, "输入本方洞号1~6")
    assert not sent
    after = copy.deepcopy(game.__dict__)
    assert after.pop("rng").getstate() == before.pop("rng").getstate()
    assert after == before


@pytest.mark.parametrize("value", ["0", "7", "9", "-1", "abc", None])
def test_local_input_rejects_out_of_range_wire_numbers_and_cancel(monkeypatch, value):
    host, _, sent, _ = make_host(22)
    input_value(monkeypatch, value)
    GameWindow._ask_params(host, SPEC, "输入本方洞号1~6")
    assert not sent


@pytest.mark.parametrize("uid", [11, 22, 99])
def test_summary_identifies_actual_sides_and_observer(uid):
    host, _, _, _ = make_host(uid)
    state = dict(game="kalah", p0=11, p1=22, turn=22,
                 cells=list(range(14)), status="playing")
    lines = GameWindow._fmt_state(host, state).splitlines()
    assert "阿乙" in lines[0] and "13 12 11 10 9 8" in lines[0] and "库 7" in lines[0]
    assert "阿甲" in lines[1] and "0 1 2 3 4 5" in lines[1] and "库 6" in lines[1]
    assert ("（你）" in lines[0]) == (uid == 22)
    assert ("（你）" in lines[1]) == (uid == 11)
    assert lines[2] == "轮到 阿乙 播子"


def test_other_integer_parameter_contract_is_unchanged():
    host, _, _, _ = make_host(22)
    assert GameWindow._parse_action(host, "guess", "int", "99") == {"guess": 99}
    host.core.game_room["game"] = "guess_number"
    assert GameWindow._parse_action(host, "hole", "int", "9") == {"hole": 9}


@pytest.mark.parametrize("change", [None, "room", "round", "game", "snapshot", "uid", "turn", "draw", "empty"])
def test_direct_global_wire_rechecks_current_core_not_only_old_ui(change):
    host, game, sent, _ = make_host(22)
    ui = dict(_room_context=("synthetic", 1), state=host.core.game_state, me=22, game="kalah")
    if change == "room":
        host.core.game_room["room_id"] = "new-room"
    elif change == "round":
        host.core.game_room["round"] = 2
    elif change == "game":
        host.core.game_room["game"] = "gemcity"
    elif change == "snapshot":
        host.core.game_state = copy.deepcopy(host.core.game_state)
    elif change == "uid":
        host.core.uid = 11
    elif change == "turn":
        host.core.game_state["turn"] = 11
    elif change == "draw":
        host.core.game_state["status"] = "ended"
    elif change == "empty":
        host.core.game_state["cells"] = list(host.core.game_state["cells"])
        host.core.game_state["cells"][8] = 0
    before = copy.deepcopy(game.cells)
    GameWindow._do_action(host, {"hole": 9}, ui)  # global wire; no second local mapping
    if change is None:
        assert sent == [("synthetic", {"hole": 9})]
        assert game.last_move[1] == 8 and sum(game.cells) == 48
    else:
        assert not sent and game.cells == before


@pytest.mark.parametrize("uid", [11, 22])
@pytest.mark.parametrize("surface", ["lobby", "focus"])
def test_live_integrated_renderer_routes_wire_and_rejects_old_round(uid, surface):
    import tkinter as tk
    from client import BoardFocusWindow
    host, game, sent, _ = make_host(uid)
    root = tk.Tk()
    root.geometry("480x400")
    cv = tk.Canvas(root, highlightthickness=0)
    cv.pack(fill="both", expand=True)
    try:
        root.update()
        host.win = root
        host.game_cv = cv
        host._closed = False
        host.core.game_private = None
        for name in ("_cancel_repaint", "_schedule_repaint", "_render_to"):
            setattr(host, name, MethodType(getattr(GameWindow, name), host))
        if surface == "lobby":
            ui = host._cv_ui
            callback = MethodType(GameWindow._on_cv_click, host)
        else:
            ui = {}
            board = SimpleNamespace(host=host, game_cv=cv, _cv_ui=ui)
            callback = MethodType(BoardFocusWindow._on_click, board)
        host._render_to(cv, ui)
        root.update()
        index = 0 if uid == 11 else 8
        x, y, _, _ = next(hole for hole in ui["holes"] if hole[3] == index)
        cv.bind("<Button-1>", callback)
        before = list(game.cells)
        host.core.game_room["round"] = 2  # core changed before next redraw
        cv.event_generate("<Button-1>", x=int(x), y=int(y))
        root.update()
        assert not sent and game.cells == before
        host.core.game_room["round"] = 1
        cv.event_generate("<Button-1>", x=int(x), y=int(y))
        root.update()
        assert sent == [("synthetic", {"hole": index + 1})]
        assert game.last_move[1] == index and sum(game.cells) == 48
        assert host._last_board_ui is ui
    finally:
        root.destroy()
