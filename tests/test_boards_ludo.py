"""Rule coordinates, live availability and stale/spectator input boundaries."""
from boardgames import boards_ludo as board
from games_pkg.ludo import LudoGame
from games_pkg.rooms import RoomManager
import client_gameui as cu


class Canvas:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def scene(game=None, me=1):
    game = game or LudoGame([1, 2, 3, 4], seed=19)
    state = game.snapshot()
    sent = []
    ui = dict(game="ludo", state=state, me=me, submit=sent.append,
              connected=True, room=dict(status="playing", players=game.players),
              _room_context=("synthetic", 1))
    cu.render(Canvas(), "ludo", state, me, str, sent.append, lambda: None, ui, None, 472, 360)
    return ui, sent


def test_curved_route_has_forty_unique_stops_and_four_real_entry_ports():
    points = [board.ring(i) for i in range(40)]
    assert len(set(points)) == 40
    assert [points[i] for i in (0, 10, 20, 30)] == [(310,189),(690,189),(690,511),(310,511)]
    assert all(5 < ((a[0]-b[0])**2+(a[1]-b[1])**2)**.5 < 100
               for a,b in zip(points,points[1:]+points[:1]))


def test_legal_planes_use_relative_progress_not_absolute_stall():
    game = LudoGame([1, 2, 3, 4], seed=1)
    game.turn, game.need_roll, game.dice = 1, False, 2
    game.miles[2] = [-1, 38, 39, 40]
    state = game.snapshot()
    assert state["positions"]["2"] == [-1, 8, 9, "FIN"]
    assert board.movable(state, 2) == [1]
    assert board.movable(state, 1) == []
    game.dice = 6
    assert board.movable(game.snapshot(), 2) == [0]


def test_real_painter_controls_roll_then_launch_then_move_with_room_rules():
    manager = RoomManager({"ludo": LudoGame})
    manager._seed_for = lambda room: 19  # first two rolls are 6 then 1
    room = manager.create(1, "ludo")
    manager.join(2, room.room_id)
    manager.start(1, room.room_id)
    game = room.gs
    for action, expected in [({"op": "roll"}, None), ({"op": "move", "idx": 0}, 0),
                             ({"op": "roll"}, None), ({"op": "move", "idx": 0}, 1)]:
        ui, sent = scene(game)
        target = next(r for r in ui["ludo_hits"] if r[-1] == action)
        cu.handle_click(ui, (target[0]+target[2])/2, (target[1]+target[3])/2)
        assert sent == [action]
        game.act(1, sent[0])
        if expected is not None:
            assert game.miles[1][0] == expected
            move = game.snapshot()["last_move"]
            assert move["takeoff"] == (expected == 0)
            assert move["steps"] == (0 if expected == 0 else 1)
            assert move["from_stall"] == (None if expected == 0 else 0)
    assert game.snapshot()["turn_uid"] == 2


def test_hits_stay_inside_small_board_and_stale_rounds_cannot_act():
    ui, sent = scene()
    for x0, y0, x1, y1, action in ui["ludo_hits"]:
        assert 0 <= x0 < x1 <= 472 and 0 <= y0 < y1 <= 360
    board.key(ui, "r")
    assert sent == [{"op": "roll"}]
    sent.clear()
    ui["state"] = dict(ui["state"])
    board.key(ui, "r")
    assert not sent
    ui["state"] = ui["ludo_state"]
    ui["_room_context"] = ("synthetic", 2)
    board.key(ui, "r")
    assert not sent


def test_opponent_spectator_disconnected_and_terminal_are_read_only():
    for me in (2, 99):
        ui, sent = scene(me=me)
        assert not ui["ludo_hits"]
        board.key(ui, "r")
        assert not sent
    ui, sent = scene()
    ui["connected"] = False
    board.key(ui, "r")
    assert not sent
    ui["connected"] = True
    ui["state"]["winner_uid"] = 1
    board.key(ui, "r")
    assert not sent


def test_exact_finish_capture_and_completed_aircraft_never_clickable():
    game = LudoGame([1, 2], seed=1)
    game.need_roll, game.dice = False, 2
    game.miles[1] = [38, 39, 40, -1]
    ui, sent = scene(game)
    assert {r[-1]["idx"] for r in ui["ludo_hits"] if r[-1]["op"] == "move"} == {0}
    board.key(ui, "2")
    assert not sent
    board.key(ui, "1")
    game.act(1, sent.pop())
    assert game.snapshot()["positions"]["1"][0] == "FIN"


def test_art_exact_allowlist_and_actual_renderer_registration():
    from boardgames.gallery import resource_path
    from boardgames.registry import web_parts
    from PIL import Image
    with Image.open(resource_path(board.ART)) as image:
        assert image.size[0] == image.size[1]
    js, css = web_parts()
    assert "Object.assign(GRENDER,{ludo:BoardsLudo.paint})" in js
    assert board.ART in js and board.MAP in js


def test_ludo_parameter_forms_are_removed_from_normal_actions():
    from client import _actions_for
    assert all(spec.get("kind") != "ludomove" and spec.get("fixed", {}).get("op") not in {"roll", "move", "skip"}
               for _, spec, _ in _actions_for("ludo", None))


def test_formal_web_entry_has_no_legacy_number_buttons():
    from web import PAGE
    start = PAGE.index("  ludo(box,s){")
    end = PAGE.index("  // ---- W4", start)
    assert PAGE[start:end].strip() == "ludo(box,s){BoardsLudo.paint(box,s);},"


def test_common_actions_keep_off_turn_semantics_but_old_dice_do_not():
    from types import SimpleNamespace
    from boardgames.boards_ludo import submit_allowed
    state=LudoGame([7,8],seed=19).snapshot()
    room=dict(room_id="fresh",round=1,game="ludo",status="playing",players=[7,8],spectators=[])
    core=SimpleNamespace(uid=8,connected=True,game_room=room,game_state=state)
    ui=dict(game="ludo",room=room,state=state,me=8,_room_context=("fresh",1))
    assert submit_allowed(core,ui,{"op":"resign"})
    assert submit_allowed(core,ui,{"op":"draw_accept"})
    assert not submit_allowed(core,ui,{"op":"roll"})
