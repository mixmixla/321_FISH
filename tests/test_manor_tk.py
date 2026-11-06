"""Revealed room geometry and real Betrayal rules through Tk's normal routes."""
import copy
from types import SimpleNamespace
import tkinter as tk

import pytest

import client
import client_gameui as cu
from boardgames import manor_tk as manor
from games_pkg.betrayal import BetrayalGame
from games_pkg.rooms import RoomManager
from test_flagship_gui import _fake_game_core


class Canvas:
    def __init__(self): self.calls = []
    def __getattr__(self, name):
        def call(*args, **kwargs): self.calls.append((name, args, kwargs))
        return call


def room(seed=10):
    manager = RoomManager({"betrayal": BetrayalGame})
    manager._seed_for = lambda _: seed
    game_room = manager.create(7, "betrayal")
    manager.join(8, game_room.room_id);manager.join(9, game_room.room_id)
    manager.start(7, game_room.room_id)
    return manager, game_room


def ui_for(game_room, me=7):
    sent = []
    return {"game": "betrayal", "state": copy.deepcopy(game_room.gs.snapshot()),
            "room": game_room.summary(), "me": me, "connected": True,
            "_room_context": (game_room.room_id, game_room.round_no),
            "submit": sent.append, "repaint": lambda: None}, sent


def paint(ui, width=472, height=364):
    cv = Canvas()
    cu.render(cv, "betrayal", ui["state"], ui["me"], lambda u: f"玩家{u}",
              ui["submit"], ui["repaint"], ui, None, width, height)
    return cv


def click(ui, rect):
    cu.handle_click(ui, (rect[0]+rect[2])/2, (rect[1]+rect[3])/2)


def hit(ui, key):
    return next(r for r in ui["manor_hits"] if r[-1] == key)


def test_initial_hall_three_separate_seats_and_only_door_centres_move():
    _, game_room = room()
    ui, sent = ui_for(game_room)
    paint(ui)
    assert set(ui["manor_cells"]) == {"0,0"}
    assert len(ui["manor_people"]) == 3
    assert len({tuple(p[:4]) for p in ui["manor_people"]}) == 3
    assert len(ui["manor_doors"]) == 4
    for person in ui["manor_people"]:
        click(ui, person)
    assert not sent
    north = next(d for d in ui["manor_doors"] if d[-2] == "up")
    x0, y0, x1, y1 = ui["manor_cells"]["0,0"]
    assert (x1-x0) % 8 == 0  # Bitmap and tile edges align, including the door centre.
    assert (north[0]+north[2])/2 == (x0+x1)/2
    assert (north[1]+north[3])/2 == y0
    cu.handle_click(ui, north[2]+2, y0)  # Just outside the real doorway.
    assert not sent
    paint(ui)
    assert ui["manor_tab"] == "journal"  # Room inspection is read-only.
    click(ui, hit(ui, ("tab", "map")));paint(ui)
    click(ui, next(d for d in ui["manor_doors"] if d[-2] == "up"))
    assert sent == [{"move": "up"}]


@pytest.mark.parametrize("change", ["off_turn", "dead", "spectator", "disconnected", "ended", "no_steps", "empty_deck"])
def test_door_gates_block_without_hiding_revealed_rooms(change):
    _, game_room = room()
    ui, sent = ui_for(game_room)
    if change == "off_turn": ui["state"]["turn_uid"] = 8
    if change == "dead": ui["state"]["alive"].remove(7)
    if change == "spectator": ui["room"]["players"].remove(7)
    if change == "disconnected": ui["connected"] = False
    if change == "ended": ui["room"]["status"] = "ended"
    if change == "no_steps": ui["state"]["steps_left"] = 0
    if change == "empty_deck": ui["state"]["tiles_left"] = 0
    paint(ui)
    assert set(ui["manor_cells"]) == {"0,0"}
    assert not ui["manor_doors"] and not sent


def test_natural_open_return_and_gift_keep_actual_discovery_cards():
    manager, game_room = room(3)
    ui, sent = ui_for(game_room)
    def submit(action):
        sent.append(action)
        manager.handle_action(7, game_room.room_id, action)
        ui["state"] = copy.deepcopy(game_room.gs.snapshot())
    ui["submit"] = submit
    paint(ui)
    click(ui, next(d for d in ui["manor_doors"] if d[-2] == "up"))
    record = ui["state"]["discoveries"][-1]
    assert [c["name"] for c in record["cards"]] == ["意外的馈赠", "光之水晶"]
    paint(ui)
    click(ui, hit(ui, ("tab", "journal")))
    cv = paint(ui)
    labels = [k.get("text") for n, _, k in cv.calls if n == "create_text"]
    assert all(c["text"] in labels for c in record["cards"])
    click(ui, hit(ui, ("tab", "map")));paint(ui)
    discovered = copy.deepcopy(ui["state"]["discoveries"])
    click(ui, next(d for d in ui["manor_doors"] if d[-2] == "down"))
    assert ui["state"]["discoveries"] == discovered
    assert ui["state"]["pos"]["7"] == "0,0"
    click(ui, hit(ui, ("tab", "inventory")));paint(ui)
    before = ui["state"]["stats"]["7"]["speed"]
    click(ui, hit(ui, ("action", {"use": "光之水晶"})))
    assert ui["state"]["stats"]["7"]["speed"] == before+1
    assert not ui["state"]["items"]["7"]


def test_distant_exit_overview_navigates_without_teleport_or_tiny_local_tiles():
    _, game_room = room(92)
    game_room.gs.act(7, {"move": "up"})
    ui, sent = ui_for(game_room)
    paint(ui)
    local = ui["manor_cells"]["0,-1"]
    assert local[2]-local[0] >= 60
    click(ui, hit(ui, "overview"));paint(ui)
    exit_pos = ui["state"]["haunt"]["exit"]
    assert exit_pos in ui["manor_cells"] and not ui["manor_doors"]
    click(ui, ui["manor_cells"][exit_pos]);paint(ui)
    assert ui["manor_center"] == manor.point(exit_pos) and not ui["manor_overview"]
    assert not ui["manor_doors"] and not sent
    assert ui["state"]["pos"]["7"] == "0,-1"
    click(ui, hit(ui, "follow"));paint(ui)
    assert "0,-1" in ui["manor_cells"]


def test_close_room_view_enlarges_only_the_view_and_keeps_doors_usable():
    _, game_room = room()
    ui, sent = ui_for(game_room)
    paint(ui)
    before = copy.deepcopy(ui["state"])
    click(ui, hit(ui, "close"));paint(ui)
    rect = ui["manor_cells"]["0,0"]
    assert rect[2]-rect[0] >= 180
    assert len(ui["manor_people"]) == 3 and len(ui["manor_doors"]) == 4
    assert not sent and ui["state"] == before
    click(ui, hit(ui, "close"));paint(ui)
    assert not ui["manor_close"] and not sent


@pytest.mark.parametrize("change", ["room", "round", "game", "snapshot", "uid", "turn", "dead", "disconnected"])
def test_gamewindow_rejects_stale_door_source_against_current_core(change):
    _, game_room = room()
    ui, sent = ui_for(game_room)
    state = ui["state"]
    core = SimpleNamespace(uid=7, connected=True, game_room=game_room.summary(),
                           game_state=state, game_action=lambda *args: sent.append(args))
    if change == "room":core.game_room["room_id"] = "different"
    if change == "round":core.game_room["round"] = 2
    if change == "game":core.game_room["game"] = "guess_number"
    if change == "snapshot":core.game_state = copy.deepcopy(state)
    if change == "uid":core.uid = 8
    if change == "turn":state["turn_uid"] = 8
    if change == "dead":state["alive"].remove(7)
    if change == "disconnected":core.connected = False
    client.GameWindow._do_action(SimpleNamespace(core=core), {"move": "up"}, ui)
    assert not sent


def test_real_gamewindow_and_small_focus_route_door_and_item_to_formal_room():
    manager, game_room = room(3)
    root = tk.Tk();root.withdraw()
    core = _fake_game_core();core.game_meta = {};core.game_room = core.game_state = None
    app = SimpleNamespace(root=root, core=core, _frameless=False, _camo_title=lambda:"合成山屋试玩")
    gw = client.GameWindow(app, pal=client._DEFAULT_PAL)
    def sync():
        core.game_room = copy.deepcopy(game_room.summary())
        core.game_state = copy.deepcopy(game_room.gs.snapshot())
        core.game_private = copy.deepcopy(game_room.gs.private(7))
        gw._sync();root.update()
    def action(rid, payload):
        manager.handle_action(7, rid, payload);sync()
    core.game_action = action
    try:
        gw.win.geometry("1000x760");sync()
        click(gw._cv_ui, next(d for d in gw._cv_ui["manor_doors"] if d[-2] == "up"))
        assert core.game_state["room_names"]["0,-1"] == "阁楼"
        gw._spawn_board_win();board = gw._board_win
        board.win.minsize(480, 400);board.win.geometry("480x400");root.update();board.redraw()
        click(board._cv_ui, hit(board._cv_ui, ("tab", "journal")))
        assert len(board.game_cv.find_withtag("manor-event")) == 1
        assert len(board.game_cv.find_withtag("manor-item")) == 1
        click(board._cv_ui, hit(board._cv_ui, ("tab", "inventory")))
        assert len(board.game_cv.find_withtag("manor-item")) == 1
        click(board._cv_ui, hit(board._cv_ui, ("action", {"use": "光之水晶"})))
        assert not game_room.gs.items[7] and game_room.gs.stats[7]["speed"] == 4
    finally:
        gw.close();root.destroy()
