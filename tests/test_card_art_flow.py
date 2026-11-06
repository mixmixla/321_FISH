"""Card artwork and private choices through the existing game actions."""
from games_pkg.gemcity import COLORS, NOBLES, GemCityGame
from games_pkg.lovelove import LoveLoveGame


def test_development_art_covers_the_deck_and_survives_reservation_and_purchase():
    game = GemCityGame([11, 22], seed=3)
    for tier in (1, 2, 3):
        cards = game.market[tier] + game.deck[tier]
        assert sorted(card["art"] for card in cards) == list(range(20))
        assert len({card["title"] for card in cards}) == 20
    card = dict(game.snapshot()["market"]["1"][0])
    colour = next(c for c in COLORS if card["cost"][c])
    other_colour = next(c for c in COLORS if c != colour)
    game.act(11, {"op": "reserve", "tier": 1, "idx": 0})
    assert game.private(11)["reserved"] == [card]
    assert game.private(22)["reserved"] == []
    assert game.market[1][0]["art"] != card["art"]
    game.act(22, {"op": "take", "colors": [other_colour]})
    game.act(11, {"op": "take", "colors": [colour]})
    game.act(22, {"op": "take", "colors": [other_colour]})
    game.act(11, {"op": "buy_res", "idx": 0})
    assert game.private(11)["collection"] == [card]
    assert game.private(11)["cards"] == 1 and not game.private(11)["reserved"]
    assert game.private(22)["collection"] == [] and "collection" not in game.snapshot()


def test_patron_portraits_follow_the_requirements_after_a_patron_leaves():
    game = GemCityGame([11, 22], seed=3)
    game.nobles_left.remove(NOBLES[1])
    state = game.snapshot()
    assert state["noble_art"] == [0, 2, 3, 4]
    assert state["noble_titles"] == ["翡翠侯爵", "蓝晶航长", "黄玉银行家", "紫晶工匠王"]


def test_only_the_actor_sees_the_draw_and_can_play_it_to_keep_their_hand():
    game = LoveLoveGame([11, 22], seed=10)
    hand = game.hand[11]
    assert hand != 4
    assert game.private(11) == {"hand": hand, "drawn": 4}
    assert "drawn" not in game.private(22) and game.private(33) is None
    assert "drawn" not in game.snapshot()
    game.act(11, {"op": "discard", "play": 4})
    assert game.snapshot()["discard"][-1] == (11, 4)
    assert game.private(11) == {"hand": hand}
    assert game.private(22)["drawn"] == game.deck[-1]
