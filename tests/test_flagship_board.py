"""Pure board input/feedback contracts; no Tk window or real input devices."""
import pytest
from types import SimpleNamespace

import client_gameui as ui_module


def board_ui(game="gomoku", can_move=True):
    rows, cols = (15, 15) if game == "gomoku" else (6, 7)
    sent = []
    state = {"board": [[0] * cols for _ in range(rows)], "players": [7, 8],
             "turn_uid": 7, "winner_uid": None, "draw": False, "last_move": None}
    ui = {"game": game, "ox": 20, "oy": 60, "cell": 20, "n": cols,
          "rows": rows, "cols": cols, "state": state, "can_move": can_move,
          "me": 7, "submit": sent.append}
    return ui, sent


@pytest.mark.parametrize(("x", "y", "expected"), [
    (20, 60, (0, 0)), (32, 60, (1, 0)), (10, 60, (0, 0)),
    (9.9, 60, None), (310, 60, None), (309.9, 60, (14, 0)),
    (20, 49.9, None), (20, 50, (0, 0)), (20, 350, None),
])
def test_gomoku_click_and_hover_share_intersection_geometry(x, y, expected):
    ui, sent = board_ui()
    ui_module.handle_click(ui, x, y)
    assert ui_module._cell_of(ui, x, y) == expected
    assert sent == ([] if expected is None else [{"x": expected[0], "y": expected[1]}])


def test_occupied_intersection_is_not_submitted():
    ui, sent = board_ui()
    ui["state"]["board"][0][0] = 1
    ui_module.handle_click(ui, 20, 60)
    assert not sent


@pytest.mark.parametrize("game", ["gomoku", "connect4"])
def test_read_only_player_or_spectator_never_submits(game):
    ui, sent = board_ui(game, can_move=False)
    ui_module.handle_click(ui, 40, 80)
    assert not sent


@pytest.mark.parametrize(("x", "y", "valid"), [
    (20, 40, True), (159.9, 179.9, True), (20, 39.9, False),
    (20, 180, False), (19.9, 60, False), (160, 60, False),
])
def test_connect4_click_is_limited_to_board_and_column_hint(x, y, valid):
    ui, sent = board_ui("connect4")
    ui_module.handle_click(ui, x, y)
    assert bool(sent) is valid


def test_connect4_full_column_cannot_submit():
    ui, sent = board_ui("connect4")
    for row in ui["state"]["board"]:
        row[0] = 1
    ui_module.handle_click(ui, 25, 70)
    assert not sent


def test_connect4_prompt_strip_shares_column_geometry_with_click():
    ui, sent = board_ui("connect4")
    # One row immediately above the board is the same clickable column hint.
    assert ui_module._cell_of(ui, 25, 45) == (0, -1)
    ui_module.handle_click(ui, 25, 45)
    assert sent == [{"col": 0}]
    sent.clear()
    assert ui_module._cell_of(ui, 25, 39.9) is None
    ui_module.handle_click(ui, 25, 39.9)
    assert not sent


@pytest.mark.parametrize("direction", [(1, 0), (0, 1), (1, 1), (1, -1)])
@pytest.mark.parametrize("needed", [4, 5])
def test_win_line_uses_maximal_run_through_last_move(direction, needed):
    dx, dy = direction
    state = {"board": [[0] * 15 for _ in range(15)], "players": [7, 8],
             "winner_uid": 8, "last_move": [5 + dx, 7 + dy], "draw": False}
    expected = [(5 + i * dx, 7 + i * dy) for i in range(needed + 1)]
    for x, y in expected:
        state["board"][y][x] = 2
    assert ui_module.flagship_win_line(state, needed) == expected


@pytest.mark.parametrize("change", [{"draw": True}, {"winner_uid": None},
                                    {"last_move": [-1, 0]}, {"last_move": None}])
def test_draw_or_invalid_result_never_invents_a_win_line(change):
    state = {"board": [[1] * 5], "players": [7, 8], "winner_uid": 7,
             "last_move": [2, 0], "draw": False}
    state.update(change)
    assert ui_module.flagship_win_line(state, 5) == []


def test_color_is_independent_of_whose_turn_it_is():
    state = {"players": [7, 8], "turn_uid": 8, "winner_uid": None, "draw": False}
    nick = lambda uid: f"玩家{uid}"
    assert "执白" in ui_module.flagship_status("gomoku", state, 8, nick)
    assert "轮到你" in ui_module.flagship_status("gomoku", state, 8, nick)
    state["turn_uid"] = 7
    assert "执白" in ui_module.flagship_status("gomoku", state, 8, nick)
    assert "等待" in ui_module.flagship_status("gomoku", state, 8, nick)
    assert "观战" in ui_module.flagship_status("gomoku", state, 99, nick)
    assert "执黄" in ui_module.flagship_status("connect4", state, 8, nick)


def test_flagship_can_move_requires_current_player_context():
    room = {"status": "playing", "players": [7, 8], "spectators": []}
    state = {"turn_uid": 7, "winner_uid": None, "draw": False}
    assert ui_module.flagship_can_move(room, state, 7, True)
    assert not ui_module.flagship_can_move(room, state, 8, True)
    assert not ui_module.flagship_can_move(
        {**room, "spectators": [7]}, state, 7, True)
    assert not ui_module.flagship_can_move(room, state, 7, False)
    assert not ui_module.flagship_can_move(
        room, {**state, "winner_uid": 7}, 7, True)


def test_client_action_gate_rechecks_round_turn_and_connection():
    from client import GameWindow

    sent = []
    core = SimpleNamespace(
        game_room={"room_id": "r1", "round": 2, "status": "playing",
                   "game": "gomoku", "players": [7, 8], "spectators": []},
        game_state={"turn_uid": 7, "winner_uid": None, "draw": False},
        uid=7, connected=True,
        game_action=lambda rid, action: sent.append((rid, action)),
    )
    host = SimpleNamespace(core=core)
    ui = {"_room_context": ("r1", 2)}
    GameWindow._do_action(host, {"x": 3, "y": 4}, ui)
    assert sent == [("r1", {"x": 3, "y": 4})]

    sent.clear()
    ui["_room_context"] = ("r1", 1)       # late callback from old round
    GameWindow._do_action(host, {"x": 3, "y": 4}, ui)
    assert not sent

    ui["_room_context"] = ("r1", 2)
    core.game_state["turn_uid"] = 8         # off-turn player
    GameWindow._do_action(host, {"x": 3, "y": 4}, ui)
    assert not sent


def test_desktop_game_entry_map_keeps_unverified_games_available():
    from client import _desktop_game_status

    assert _desktop_game_status("go")[0] == "unsupported"
    assert _desktop_game_status("rummikub")[0] == "unsupported"
    assert _desktop_game_status("coc")[0] == "unsupported"
    assert _desktop_game_status("balatro")[0] == "unverified"
    assert _desktop_game_status("gomoku")[0] == "flagship"
