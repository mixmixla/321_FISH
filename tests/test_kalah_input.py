"""Kalah UI/wire mapping over natural turns and actual rule snapshots."""
import copy

import pytest

import client_gameui as cu
from games_pkg.kalah import KalahGame


class Canvas:
    def __getattr__(self, name):
        return lambda *a, **k: None


def scene(me, *, b_turn=False):
    game = KalahGame([11, 22], seed=1)
    if b_turn:
        game.act(11, {"hole": 1})
        assert game.turn == 22
    state = game.snapshot()
    sent = []
    ui = {"state": state, "submit": sent.append, "repaint": lambda: None}
    cu._p_kalah(Canvas(), state, me, lambda u: f"P{u}", sent.append,
                lambda: None, ui, None, 640, 400)
    return game, state, ui, sent


@pytest.mark.parametrize("me,b_turn,expected", [(11, False, set(range(1, 7))),
                                              (22, True, set(range(9, 15)))])
def test_natural_turn_six_desktop_holes_match_real_rule(me, b_turn, expected):
    game, _, ui, sent = scene(me, b_turn=b_turn)
    assert len(ui["holes"]) == 6
    for x, y, radius, index in ui["holes"]:
        cu.handle_click(ui, x, y)
        assert sent[-1] == {"hole": index + 1}
        copy.deepcopy(game).act(me, sent[-1])
    assert {a["hole"] for a in sent} == expected
    xs = [x for x, _, _, _ in sorted(ui["holes"], key=lambda pit: pit[3])]
    assert xs == sorted(xs, reverse=b_turn)       # B logical 1..6 is right-to-left


@pytest.mark.parametrize("me,b_turn", [(22, False), (11, True), (33, False)])
def test_desktop_nonactor_and_spectator_have_no_hotspots(me, b_turn):
    _, _, ui, sent = scene(me, b_turn=b_turn)
    assert ui["holes"] == []
    cu.handle_click(ui, 320, 280)
    assert not sent


def test_desktop_empty_and_finished_holes_do_not_submit():
    game, state, ui, sent = scene(22, b_turn=True)
    game.cells[8] = 0
    cu._p_kalah(Canvas(), state, 22, str, sent.append, lambda: None, ui, None, 640, 400)
    assert {h[3] for h in ui["holes"]} == set(range(9, 14))
    old_holes = list(ui["holes"])
    state["status"] = "ended"                  # includes drawn games, winner=None
    for x, y, _, _ in old_holes:
        cu.handle_click(ui, x, y)
    assert not sent
    cu._p_kalah(Canvas(), state, 22, str, sent.append, lambda: None, ui, None, 640, 400)
    assert ui["holes"] == []


def test_desktop_stale_hotspot_rechecks_turn_and_cell():
    _, state, ui, sent = scene(22, b_turn=True)
    x, y, _, index = ui["holes"][0]
    state["cells"][index] = 0
    cu.handle_click(ui, x, y)
    state["cells"][index] = 4
    state["turn"] = 11
    cu.handle_click(ui, x, y)
    assert not sent


def test_b_recent_move_uses_global_index_and_board_direction(monkeypatch):
    game, _, _, _ = scene(22, b_turn=True)
    game.act(22, {"hole": 9})
    assert game.last_move[1] == 8
    observed = []
    monkeypatch.setattr(cu, "_g_kalah_board_fx",
                        lambda cv, ui, now, cells, a, b, radius, breath, center:
                        observed.append((a, b, center)))
    ui = {}
    cu._p_kalah(Canvas(), game.snapshot(), 22, str, lambda a: None,
                lambda: None, ui, None, 640, 400)
    a, b, center = observed[0]
    assert center == b[0]
    assert a[0][0] < a[5][0] and b[0][0] > b[5][0]
