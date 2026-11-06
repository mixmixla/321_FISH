"""Card art stays attached to real rule cards and private canvas interactions."""
import copy
from types import SimpleNamespace
import tkinter as tk

import pytest

import client
import client_gameui as cu
from boardgames import card_table_tk as table
from games_pkg.gemcity import GemCityGame
from games_pkg.lovelove import LoveLoveGame
from games_pkg.rooms import RoomManager
from test_flagship_gui import _fake_game_core


class Canvas:
    def __init__(self): self.calls = []
    def __getattr__(self, name):
        def call(*args, **kwargs): self.calls.append((name, args, kwargs))
        return call


def _room(game, seed=3):
    manager = RoomManager({"gemcity": GemCityGame, "lovelove": LoveLoveGame})
    manager._seed_for = lambda room: seed
    room = manager.create(7, game)
    manager.join(8, room.room_id)
    manager.start(7, room.room_id)
    return manager, room


def _ui(room, uid=7):
    sent = []
    ui = {"game": room.game_name, "me": uid, "room": room.summary(),
          "state": room.gs.snapshot(), "submit": sent.append, "repaint": lambda: None,
          "_room_context": (room.room_id, room.round_no)}
    return ui, sent


def _paint(room, ui, private=None, width=480, height=400):
    cv = Canvas()
    cu.render(cv, room.game_name, ui["state"], ui["me"], lambda uid: f"合成{uid}",
              ui["submit"], ui["repaint"], ui, private, width, height)
    return cv


def _click(ui, rect):
    cu.handle_click(ui, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2)


def _nav(ui, name):
    return next(r for r in ui["gc_navigation"] if r[-1] == name)


def _love(ui, kind, value=None):
    return next(r for r in ui["ll_hits"] if r[-2] == kind and (value is None or r[-1] == value))


def _labels(cv):
    return [str(kw.get("text", "")) for name, _, kw in cv.calls if name == "create_text"]


def test_market_all_twelve_actions_fit_small_canvas_and_costs_survive_without_art():
    _, room = _room("gemcity")
    ui, sent = _ui(room)
    cv = _paint(room, ui, room.gs.private(7))
    assert len(ui["gc_cards"]) == 12 and len(ui["gc_reserve"]) == 12
    assert len(ui["gc_bank"]) == 5
    for rect in ui["gc_cards"]+ui["gc_reserve"]+ui["gc_bank"]:
        assert 0 <= rect[0] < rect[2] <= 480 and 0 <= rect[1] < rect[3] <= 400
    assert any("发展卡" in t for t in _labels(cv))
    _click(ui, ui["gc_reserve"][0])
    assert sent == [{"op": "reserve", "tier": 3, "idx": 0}]


def test_private_album_has_every_card_pages_off_turn_and_no_spectator_leak():
    _, room = _room("gemcity")
    ui, sent = _ui(room)
    ui["state"] = {**ui["state"], "turn_uid": 8}
    cards = [dict(room.gs.market[1][0], title=f"私人收藏{i}", art=i) for i in range(13)]
    private = {"cards": 13, "collection": cards, "reserved": [dict(cards[0], title="私人保留") ]}
    _paint(room, ui, private)
    _click(ui, _nav(ui, "collection"))
    labels = []
    for page in range(3):
        labels += _labels(_paint(room, ui, private))
        _click(ui, _nav(ui, "next"))
    assert all(f"私人收藏{i}" in labels for i in range(13))
    assert not sent
    ui["me"] = 99
    cv = _paint(room, ui, private)
    assert not any("私人" in label for label in _labels(cv))
    assert not any(r[-1] in ("collection", "reserved") for r in ui["gc_navigation"])
    _click(ui, _nav(ui, "nobles"))
    cv = _paint(room, ui, private)
    assert sum("需折扣" in s for s in _labels(cv)) == len(room.gs.nobles_left)


def test_lovelove_new_draw_guard_selection_waits_for_target_guess_and_confirm():
    _, room = _room("lovelove", seed=3)
    private = room.gs.private(7)
    assert private["drawn"] == 1 and private["hand"] == 3
    ui, sent = _ui(room)
    _paint(room, ui, private)
    _click(ui, _love(ui, "play", 1))
    _paint(room, ui, private)
    assert not sent and not any(r[-2] == "confirm" for r in ui["ll_hits"])
    _click(ui, _love(ui, "target", 8))
    _paint(room, ui, private)
    assert not sent
    _click(ui, _love(ui, "guess", 2))
    _paint(room, ui, private)
    assert not sent
    _click(ui, _love(ui, "confirm"))
    assert sent == [{"op": "discard", "play": 1, "target": 8, "val": 2}]
    room.gs.act(7, sent[0])
    assert room.gs.discard[-1] == (7, 1)


def test_owned_album_expands_exact_art_read_only_and_returns_to_same_page(monkeypatch):
    _, room = _room("gemcity")
    ui, sent = _ui(room)
    ui["state"] = {**ui["state"], "turn_uid": 8}
    private = {"collection": [dict(room.gs.market[1][0], title=f"藏品{i}", art=i)
                              for i in range(13)], "cards": 13}
    _paint(room, ui, private)
    _click(ui, _nav(ui, "collection"))
    ui["gc_page"] = 1
    _paint(room, ui, private)
    _click(ui, _nav(ui, ("open", 7)))
    asked = []
    def record(cv, filename, index, columns, rows, rect, contain=False):
        asked.append((filename, index, contain)); return False
    monkeypatch.setattr(table, "art", record)
    cv = _paint(room, ui, private)
    assert asked == [("gemcity-tier1.webp", 7, True)]
    assert "藏品7" in _labels(cv) and "已购买的卡面 · 只读欣赏" in _labels(cv)
    assert not ui["gc_cards"] and not ui["gc_reserved"] and not ui["gc_bank"]
    cu.handle_click(ui, 240, 200)
    assert not sent
    _click(ui, _nav(ui, "album_back"))
    _paint(room, ui, private)
    assert ui["gc_page"] == 1 and ui["gc_detail"] is None
    assert any(r[-1] == ("open", 7) for r in ui["gc_navigation"])
    assert not sent


def test_lovelove_late_private_frame_keeps_legal_selection_and_force_seven():
    _, room = _room("lovelove", seed=3)
    ui, sent = _ui(room)
    _paint(room, ui, {"hand": 3})
    _click(ui, _love(ui, "play", 3))
    _paint(room, ui, {"hand": 3, "drawn": 1})
    assert ui["ll_play"] == 3 and not sent
    _paint(room, ui, {"hand": 7, "drawn": 8})
    assert [r[-1] for r in ui["ll_hits"] if r[-2] == "play"] == [7]
    assert ui["ll_play"] is None
    ui["me"] = 99
    cv = _paint(room, ui, {"hand": 7, "drawn": 8})
    assert not ui["ll_hits"]
    assert not any("伯爵夫人" in t or "公主" in t for t in _labels(cv))


@pytest.fixture
def window():
    root = tk.Tk(); root.withdraw()
    core = _fake_game_core()
    core.game_meta = {}
    core.game_room = core.game_state = None
    app = SimpleNamespace(root=root, core=core, _frameless=False,
                          _camo_title=lambda: "合成卡牌桌面")
    gw = client.GameWindow(app, pal=client._DEFAULT_PAL)
    gw.win.geometry("1000x760")
    try:
        root.update(); yield root, core, gw
    finally:
        gw.close(); root.destroy()


def _sync(core, gw, room, private=True):
    core.game_room = copy.deepcopy(room.summary())
    core.game_state = copy.deepcopy(room.gs.snapshot())
    if private:
        core.game_private = copy.deepcopy(room.gs.private(core.uid))
    gw._sync()
    gw.win.update_idletasks()


def test_private_frames_redraw_both_real_canvases_without_resizing(window):
    root, core, gw = window
    _, room = _room("lovelove", seed=3)
    _sync(core, gw, room, private=False)
    assert not gw._cv_ui["ll_hits"]
    core.game_private = {"hand": 3}
    gw._sync()
    assert any(r[-2:] == ("play", 3) for r in gw._cv_ui["ll_hits"])
    _click(gw._cv_ui, _love(gw._cv_ui, "play", 3))
    core.game_private = {"hand": 3, "drawn": 1}
    gw._sync()
    assert gw._cv_ui["ll_play"] == 3
    assert {r[-1] for r in gw._cv_ui["ll_hits"] if r[-2] == "play"} == {1, 3}
    gw._spawn_board_win(); root.update()
    board = gw._board_win
    board.win.minsize(480, 400); board.win.geometry("480x400")
    root.update(); board.redraw()
    assert len(board.game_cv.find_withtag("card-illustration")) >= 2
    core.game_private = {"hand": 4, "drawn": 5}
    gw._sync()
    assert {r[-1] for r in board._cv_ui["ll_hits"] if r[-2] == "play"} == {4, 5}


def test_normal_room_reserve_buy_and_album_keep_card_identity(window):
    root, core, gw = window
    manager, room = _room("gemcity", seed=3)
    _sync(core, gw, room)
    original = copy.deepcopy(room.gs.market[1][0])
    actions = []
    def submit(rid, action):
        actions.append(action)
        manager.handle_action(7, rid, action)
        _sync(core, gw, room)
    core.game_action = submit
    def other_turn():
        color = next(k for k in table.COLORS if room.gs.bank[k] > 0)
        manager.handle_action(8, room.room_id, {"op": "take", "colors": [color]})
        _sync(core, gw, room)
    cost = original["cost"]
    wanted = [key for key in table.COLORS if cost.get(key)]
    for key in wanted:
        _click(gw._cv_ui, next(r for r in gw._cv_ui["gc_bank"] if r[-1] == key))
        if cost[key] == 2 and len(wanted) == 1:
            _click(gw._cv_ui, next(r for r in gw._cv_ui["gc_bank"] if r[-1] == key))
    if room.gs.turn == 0:
        _click(gw._cv_ui, gw._cv_ui["gc_take"])
    other_turn()
    _click(gw._cv_ui, next(r for r in gw._cv_ui["gc_reserve"] if r[-2:] == (1, 0)))
    assert room.gs.reserved[7][0] == original
    other_turn()
    _click(gw._cv_ui, _nav(gw._cv_ui, "reserved"))
    _click(gw._cv_ui, gw._cv_ui["gc_reserved"][0])
    assert actions[-1] == {"op": "buy_res", "idx": 0}
    assert room.gs.private(7)["collection"][0] == original
    _click(gw._cv_ui, _nav(gw._cv_ui, "collection"))
    assert gw._cv_ui["gc_view"] == "collection"
    assert not gw._cv_ui["gc_reserved"]
    assert core.game_private["collection"][0]["art"] == original["art"]


def test_gemcity_late_collection_frame_preserves_open_album_and_bounded_photos(window):
    root, core, gw = window
    _, room = _room("gemcity")
    core.game_private = None
    _sync(core, gw, room, private=False)
    _click(gw._cv_ui, _nav(gw._cv_ui, "collection"))
    card = dict(room.gs.market[1][0], title="迟到的收藏")
    core.game_private = {"cards": 1, "collection": [card], "reserved": []}
    gw._sync()
    assert gw._cv_ui["gc_view"] == "collection"
    assert any("迟到的收藏" == gw.game_cv.itemcget(item, "text")
               for item in gw.game_cv.find_all() if gw.game_cv.type(item) == "text")
    # Real Tk photos are capped per canvas, even across many resize variants.
    for width in range(80, 680, 8):
        assert table.art(gw.game_cv, "lovelove-court.webp", 0, 4, 2, (0, 0, width, 96))
    assert len(gw.game_cv._card_art_cache) == 64
