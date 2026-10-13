"""Live Tk canvases on the gate's private desktop; synthetic game state only."""
import tkinter as tk

import pytest

import client_gameui as cu
from games_pkg.blokus import BlokusGame
from games_pkg.drawguess import DrawGuessGame


@pytest.fixture
def canvas():
    root = tk.Tk()
    root.geometry("480x400")
    tk.Label(root, text="棋盘 · 专注对局", font=("Microsoft YaHei UI", 11)).pack(
        fill="x", pady=4)
    cv = tk.Canvas(root, highlightthickness=0)
    cv.pack(fill="both", expand=True, padx=4, pady=(0, 4))
    root.update()
    assert cv.winfo_width() == 472
    assert 300 <= cv.winfo_height() < 400
    yield root, cv
    root.destroy()


def test_live_blokus_all_tiles_rotation_and_pass_at_minimum_window(canvas):
    root, cv = canvas
    game = BlokusGame([1, 2, 3, 4], seed=1)
    state = game.snapshot()
    sent = []
    ui = {"game": "blokus", "state": state, "me": 1, "submit": sent.append}

    def paint():
        cu.render(cv, "blokus", state, 1, lambda u: f"玩家{u}", sent.append,
                  paint, ui, None, cv.winfo_width(), cv.winfo_height())

    ui["repaint"] = paint
    cv.bind("<Button-1>", lambda event: cu.handle_click(ui, event.x, event.y))
    paint()

    def click(rect):
        assert 0 <= rect[0] < rect[2] <= cv.winfo_width()
        assert 0 <= rect[1] < rect[3] <= cv.winfo_height()
        cv.event_generate("<Button-1>", x=int((rect[0] + rect[2]) / 2),
                          y=int((rect[1] + rect[3]) / 2))
        root.update()

    visited = set()
    for _ in range(21):
        for rect in list(ui["blok_chips"]):
            click(rect)
            assert ui["blok_pick"] == rect[4]
            visited.add(rect[4])
        if not ui.get("blok_page_next"):
            break
        click(ui["blok_page_next"])
    assert visited == set(state["has_piece"]["1"])
    assert not sent
    orientations = len(state["pieces"][ui["blok_pick"]])
    click(ui["blok_rot"])
    assert ui["blok_oi"] == 1 % orientations
    click(ui["blok_pass"])
    assert sent == [{"op": "pass"}]


def test_live_hud_own_text_is_visible_without_phase_overlap(canvas):
    root, cv = canvas
    game = DrawGuessGame(list(range(1, 9)), seed=1)
    game.scores = {u: u * 12345 for u in game.players}
    cu._status_hud(cv, cv.winfo_width(), 68, game.snapshot(), 8,
                   lambda u: "长昵称测试玩家" + str(u), "#16796C")
    root.update()
    text_items = {cv.itemcget(item, "text"): item for item in cv.find_all()
                  if cv.type(item) == "text"}
    mine = cv.bbox(text_items["我 98760"])
    phase = cv.bbox(text_items["作画中 · 第 1 轮"])
    assert 0 <= mine[0] < mine[2] <= cv.winfo_width()
    assert 0 <= mine[1] < mine[3] <= cv.winfo_height()
    assert mine[0] > phase[2]               # actual font metrics, not width estimates
    assert any(text.startswith("+") for text in text_items)


def test_live_blokus_long_title_stays_visible(canvas):
    root, cv = canvas
    state = BlokusGame([1, 2, 3, 4], seed=1).snapshot()
    cu.render(cv, "blokus", state, 1, lambda u: "这是特别特别特别特别长的合成玩家昵称",
              lambda action: None, lambda: None, {}, None,
              cv.winfo_width(), cv.winfo_height())
    root.update()
    titles = [item for item in cv.find_all() if cv.type(item) == "text"
              and "角斗士棋" in cv.itemcget(item, "text")]
    assert len(titles) == 1
    bbox = cv.bbox(titles[0])
    assert 0 <= bbox[0] < bbox[2] <= cv.winfo_width()
