from boardgames.manor_catalog import ATLASES
from games_pkg.betrayal import (
    BetrayalGame, EVENT_DECK, ITEM_DECK, ITEM_TEXT, OMEN_DECK, ROOM_SHORT,
)
from games_pkg.rooms import RoomManager


def test_atlases_cover_the_actual_room_and_card_catalogues():
    names = {"room": set(ROOM_SHORT), "item": set(ITEM_DECK), "event": set(EVENT_DECK),
             "omen": {name for name, _ in OMEN_DECK}}
    for kind, atlas in ATLASES.items():
        assert names[kind] == set(atlas["names"])
        assert len(atlas["names"]) == atlas["cols"] * atlas["rows"] == len(names[kind])
    assert set(ITEM_TEXT) == names["item"]


def test_one_foyer_and_nineteen_distinct_unseen_rooms():
    for seed in range(32):
        game = BetrayalGame([1, 2, 3], seed=seed)
        assert {name for name, _ in game.tiles} == set(ROOM_SHORT) - {"门厅", "出口之门"}
        state = game.snapshot()
        assert state["room_names"] == {"0,0": "门厅"}
        assert state["rooms"] == {"0,0": "门"} and state["discoveries"] == []
        assert state["tiles_left"] == 19


def test_real_room_move_reveals_a_card_once_and_revisit_is_just_a_move():
    manager = RoomManager({"betrayal": BetrayalGame})
    room = manager.create(11, "betrayal")
    for uid in (22, 33):
        manager.join(uid, room.room_id)
    manager.start(11, room.room_id)
    game = room.gs
    manager.handle_action(11, room.room_id, {"move": "left"})
    state = game.snapshot()
    found, = state["discoveries"]
    assert found["uid"] == 11 and found["pos"] == "-1,0"
    assert found["room"] == state["room_names"]["-1,0"]
    assert found["cards"] and all(c["text"] for c in found["cards"])
    manager.handle_action(11, room.room_id, {"move": "right"})
    assert game.snapshot()["discoveries"] == [found]
    assert game.snapshot()["tiles_left"] == state["tiles_left"]


def test_gift_discloses_the_drawn_item_and_secret_door_only_reveals_a_room():
    for event in ("意外的馈赠", "暗门"):
        game = BetrayalGame([1, 2, 3], seed=12)
        i = next(i for i, (_, kind) in enumerate(game.tiles) if kind == "event")
        game.tiles[i], game.tiles[-1] = game.tiles[-1], game.tiles[i]
        game.event_deck.remove(event)
        game.event_deck.append(event)
        item = game.item_deck[-1]
        messages = game.act(1, {"move": "up"})
        state = game.snapshot()
        discovery, = state["discoveries"]
        event_card = discovery["cards"][0]
        assert (event_card["kind"], event_card["name"]) == ("event", event)
        assert event_card["text"] == "\n".join(messages[1:])
        if event == "意外的馈赠":
            assert discovery["cards"][1] == {"kind": "item", "name": item, "text": ITEM_TEXT[item]}
            assert game.items[1] == [item]
        else:
            assert len(state["room_names"]) == 3 and len(discovery["cards"]) == 1


def test_omen_card_records_the_actual_check_and_haunt_exit():
    game = BetrayalGame([1, 2, 3], seed=2)
    i = next(i for i, (_, kind) in enumerate(game.tiles) if kind == "omen")
    game.tiles[i], game.tiles[-1] = game.tiles[-1], game.tiles[i]
    game.omens = 5
    name, stat = game.omen_deck[-1]
    before = game.stats[1][stat]
    lines = game.act(1, {"move": "down"})
    state = game.snapshot()
    assert state["omens"] == 6 and game.stats[1][stat] >= before + 1
    assert state["room_names"][state["haunt"]["exit"]] == "出口之门"
    card, = state["discoveries"][0]["cards"]
    assert (card["kind"], card["name"]) == ("omen", name)
    assert next(line for line in lines if "惊魂检定掷出" in line) in card["text"]
