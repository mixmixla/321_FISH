"""Supported compact game canvases: controls stay reachable and own score wins space."""
import copy

import pytest

import client_gameui as cu
from games_pkg.blokus import BlokusGame
from games_pkg.drawguess import DrawGuessGame


class Canvas:
    def __init__(self):
        self.texts = []
        self.polygons = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            if name == "create_text":
                self.texts.append(kwargs.get("text"))
            elif name == "create_polygon":
                self.polygons.append(args[0] if len(args) == 1 else args)
        return record


def blokus_scene(players, width, height):
    game = BlokusGame(list(range(1, players + 1)), seed=1)
    state = game.snapshot()
    sent = []
    ui = {"game": "blokus", "state": state, "me": 1, "submit": sent.append}

    def paint():
        cu._p_blokus(Canvas(), state, 1, lambda u: f"P{u}", sent.append,
                     paint, ui, None, width, height)

    ui["repaint"] = paint
    paint()
    return state, ui, sent


def click(ui, rect):
    cu.handle_click(ui, (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)


@pytest.mark.parametrize("players", [2, 3, 4])
@pytest.mark.parametrize("width,height", [(920, 680), (640, 400), (480, 400),
                                         (472, 360), (480, 300)])
def test_blokus_initial_actions_and_visible_tiles_fit(players, width, height):
    _, ui, _ = blokus_scene(players, width, height)
    for rect in [ui["blok_rot"], ui["blok_pass"], *ui["blok_chips"],
                 ui.get("blok_page_prev"), ui.get("blok_page_next")]:
        if rect is None:
            continue
        assert 0 <= rect[0] < rect[2] <= width
        assert 0 <= rect[1] < rect[3] <= height
        assert rect[3] - rect[1] >= 20


@pytest.mark.parametrize("players", [2, 3, 4])
def test_every_initial_blokus_piece_is_reachable_at_minimum_canvas(players):
    state, ui, sent = blokus_scene(players, 472, 360)
    expected = set(state["has_piece"]["1"])
    visited = set()
    for _ in range(21):
        chips = list(ui["blok_chips"])
        for rect in chips:
            click(ui, rect)
            assert ui["blok_pick"] == rect[4]
            visited.add(rect[4])
        if not ui.get("blok_page_next"):
            break
        click(ui, ui["blok_page_next"])
    assert visited == expected
    assert not sent                     # browsing/selecting never places or passes
    if ui.get("blok_page_prev"):
        selected = ui["blok_pick"]
        click(ui, ui["blok_page_prev"])
        assert ui["blok_pick"] == selected


def test_blokus_compact_rotation_and_pass_keep_action_contract():
    state, ui, sent = blokus_scene(4, 472, 360)
    while not any(c[4] == "I5" for c in ui["blok_chips"]):
        click(ui, ui["blok_page_next"])
    click(ui, next(c for c in ui["blok_chips"] if c[4] == "I5"))
    orientations = len(state["pieces"]["I5"])
    click(ui, ui["blok_rot"])
    assert ui["blok_oi"] == 1 % orientations
    click(ui, ui["blok_pass"])
    assert sent == [{"op": "pass"}]
    old_ui = copy.deepcopy({k: ui[k] for k in ("blok_pick", "blok_oi", "blok_page")})
    state["turn_uid"] = 2
    click(ui, ui["blok_rot"])
    assert {k: ui[k] for k in old_ui} == old_ui
    assert sent == [{"op": "pass"}]


@pytest.mark.parametrize("width", [480, 472, 400])
@pytest.mark.parametrize("me", [1, 8])
def test_hud_own_score_survives_compact_canvas_and_counts_hidden(width, me):
    game = DrawGuessGame(list(range(1, 9)), seed=1)
    game.scores = {u: u * 12345 for u in game.players}
    cv = Canvas()
    cu._status_hud(cv, width, 68, game.snapshot(), me,
                   lambda u: "长昵称测试玩家" + str(u), "#16796C")
    assert f"我 {game.scores[me]}" in cv.texts
    hidden = [int(t[1:]) for t in cv.texts if t.startswith("+")]
    shown = [t for t in cv.texts if t.startswith("我 ") or "… " in t]
    assert len(hidden) == 1 and hidden[0] + len(shown) == 8
    for points in cv.polygons:
        assert min(points[::2]) >= 0 and max(points[::2]) <= width


def test_hud_width_cropping_reports_hidden_even_under_six_player_cap():
    cv = Canvas()
    cu._status_hud(cv, 400, 68,
                   {"status": "round_end", "round": 12,
                    "scores": {u: 1000 for u in range(1, 7)}},
                   6, lambda u: f"Player{u}", "#16796C")
    assert "我 1000" in cv.texts
    hidden = [int(t[1:]) for t in cv.texts if t.startswith("+")]
    shown = [t for t in cv.texts if " 1000" in t]
    assert len(hidden) == 1 and hidden[0] + len(shown) == 6
