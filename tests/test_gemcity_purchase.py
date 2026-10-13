"""GemCity purchases either reject intact or pay once and acquire one card."""
import copy

import pytest

from games_pkg.base import GameRuleError
from games_pkg.gemcity import COLORS, GemCityGame
from games_pkg.rooms import RoomManager


def _state(game):
    state = copy.deepcopy({k: v for k, v in vars(game).items() if k != "rng"})
    state["rng"] = game.rng.getstate()
    return state


def _card(cost=None, *, disc="s", pts=1):
    return {"tier": 1, "disc": disc, "pts": pts,
            "cost": {c: (cost or {}).get(c, 0) for c in COLORS}}


def _offer(game, card, reserved):
    if reserved:
        # Buy the middle card: adjacent reserved cards must survive intact.
        game.reserved[1] = [_card({"o": 3}), card, _card({"d": 3})]
        return {"op": "buy_res", "idx": 1}
    game.market[1][1] = card
    return {"op": "buy", "tier": 1, "idx": 1}


def _fund(game, tokens):
    for color, amount in tokens.items():
        game.tokens[1][color] = amount
        game.bank[color] -= amount


def _supply(game):
    return {c: game.bank[c] + sum(t[c] for t in game.tokens.values())
            for c in COLORS + ["g"]}


@pytest.mark.parametrize("reserved", [False, True], ids=["market", "reserved"])
@pytest.mark.parametrize("cost,tokens,discount", [
    ({"o": 1}, {}, {}),
    ({"o": 1, "d": 1}, {"g": 1}, {}),
    ({"o": 2, "d": 2, "r": 1}, {"o": 1, "d": 1, "g": 2}, {}),
    ({"o": 2, "d": 2}, {"g": 1}, {"o": 1, "d": 1}),
])
def test_unaffordable_purchase_rejects_without_any_state_change(reserved, cost, tokens, discount):
    game = GemCityGame([1, 2], seed=17)
    action = _offer(game, _card(cost), reserved)
    _fund(game, tokens)
    game.discount[1].update(discount)
    before = _state(game)
    with pytest.raises(GameRuleError):
        game.act(1, action)
    assert _state(game) == before


@pytest.mark.parametrize("reserved", [False, True], ids=["market", "reserved"])
@pytest.mark.parametrize("cost,tokens,discount,paid,gold", [
    ({"o": 1, "d": 1}, {"g": 2}, {}, {}, 2),
    ({"o": 2, "d": 2}, {"o": 2, "d": 1, "g": 2}, {}, {"o": 2, "d": 1}, 1),
    ({"o": 2, "d": 2}, {"o": 1, "g": 1}, {"o": 1, "d": 1}, {"o": 1}, 1),
    ({"o": 1}, {"g": 1}, {"o": 2}, {}, 0),
])
def test_successful_purchase_pays_once_preserves_supply_and_advances(reserved, cost, tokens, discount, paid, gold):
    game = GemCityGame([1, 2], seed=17)
    card = _card(cost)
    action = _offer(game, card, reserved)
    _fund(game, tokens)
    game.discount[1].update(discount)
    before = _state(game)
    supply = _supply(game)
    messages = game.act(1, action)
    assert len(messages) == 1 and "购得" in messages[0]
    assert game.cards[1] == [card]
    assert game.score[1] == 1 and game.score[2] == 0
    assert game.discount[1]["s"] == 1
    assert game.turn == 1 and game.trigger_uid is None and game.winner is None
    for color in COLORS + ["g"]:
        amount = gold if color == "g" else paid.get(color, 0)
        assert game.tokens[1][color] == before["tokens"][1][color] - amount
        assert game.bank[color] == before["bank"][color] + amount
        assert game.tokens[1][color] >= 0
    assert _supply(game) == supply
    assert game.rng.getstate() == before["rng"]
    if reserved:
        assert game.reserved[1] == [before["reserved"][1][0], before["reserved"][1][2]]
        assert game.market == before["market"] and game.deck == before["deck"]
    else:
        assert game.reserved == before["reserved"]
        assert game.market[1] == before["market"][1][:1] + before["market"][1][2:] + [before["deck"][1][-1]]
        assert game.deck[1] == before["deck"][1][:-1]


def test_reserved_purchase_retains_noble_and_end_round_behavior():
    game = GemCityGame([1, 2], seed=17)
    action = _offer(game, _card(disc="o", pts=3), True)
    game.discount[1].update(o=3, d=4)
    game.score[1] = 9
    game.act(1, action)
    assert game.score[1] == 15
    assert game.nobles_cards[1] == [3]
    assert {"o": 4, "d": 4} not in game.nobles_left
    assert game.trigger_uid == 1 and game.turn == 1 and game.winner is None
    game.act(2, {"op": "take", "colors": ["o", "d", "r"]})
    assert game.ended()["winner_uid"] == 1


@pytest.mark.parametrize("uid", [2, 99])
def test_other_player_or_spectator_cannot_change_purchase_state(uid):
    game = GemCityGame([1, 2], seed=17)
    action = _offer(game, _card(), True)
    before = _state(game)
    with pytest.raises(GameRuleError):
        game.act(uid, action)
    assert _state(game) == before


@pytest.mark.parametrize("reserved", [False, True], ids=["market", "reserved"])
def test_room_action_keeps_rejected_purchase_intact_then_accepts_funded_card(reserved):
    manager = RoomManager({"gemcity": GemCityGame})
    room = manager.create(1, "gemcity")
    manager.join(2, room.room_id)
    manager.start(1, room.room_id)
    game = room.gs
    action = _offer(game, _card({"o": 1, "d": 1}), reserved)
    _fund(game, {"g": 1})
    before = _state(game)
    with pytest.raises(GameRuleError):
        manager.handle_action(1, room.room_id, action)
    assert _state(game) == before
    game.tokens[1]["g"] += 1
    game.bank["g"] -= 1
    manager.handle_action(1, room.room_id, action)
    assert game.tokens[1]["g"] == 0 and len(game.cards[1]) == 1 and game.turn == 1
