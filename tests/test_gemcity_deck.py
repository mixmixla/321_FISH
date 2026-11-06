"""Jewel-v2 fixed 60-card identity through real take/reserve/purchase actions."""
from collections import Counter, defaultdict
from copy import deepcopy

import pytest

from games_pkg.gemcity import CARD_TITLES, COLORS, GemCityGame


def _all_cards(game):
    return {(tier, card["art"]): deepcopy(card)
            for tier in (1, 2, 3) for card in game.market[tier] + game.deck[tier]}


def _market_examples():
    """Find two naturally dealt, different seeds for every picture, without injecting cards."""
    examples = defaultdict(list)
    for seed in range(128):
        game = GemCityGame([11, 22], seed=seed)
        for tier, cards in game.market.items():
            for index, card in enumerate(cards):
                if len(examples[tier, card["art"]]) < 2:
                    examples[tier, card["art"]].append((seed, index))
    assert len(examples) == 60 and all(len(seeds) == 2 for seeds in examples.values())
    return examples


def _supply(game):
    return {c: game.bank[c] + sum(tokens[c] for tokens in game.tokens.values())
            for c in COLORS + ["g"]}


def _other_turn(game, card):
    # The other player takes a non-payment colour, leaving the intended purchase available.
    color = next(c for c in COLORS if not card["cost"][c] and game.bank[c])
    game.act(22, {"op": "take", "colors": [color]})


def _earn_and_buy(game, card, action):
    initial_supply = _supply(game)
    for _ in range(5):
        if game._affordable(11, card):
            break
        needed = [c for c in COLORS
                  if card["cost"][c] - game.discount[11][c] > game.tokens[11][c]]
        game.act(11, {"op": "take", "colors": needed[:3]})
        _other_turn(game, card)
    assert game._affordable(11, card), card
    tokens, discounts, bank = deepcopy(game.tokens[11]), dict(game.discount[11]), dict(game.bank)
    need = {c: max(0, card["cost"][c] - discounts[c]) for c in COLORS}
    colored = {c: min(tokens[c], need[c]) for c in COLORS}
    gold = sum(need[c] - colored[c] for c in COLORS)
    game.act(11, action)
    assert game.private(11)["collection"][-1] == card
    assert game.discount[11] == {c: discounts[c] + (c == card["disc"]) for c in COLORS}
    assert "g" not in game.discount[11]
    assert game.tokens[11] == {**{c: tokens[c] - colored[c] for c in COLORS}, "g": tokens["g"] - gold}
    assert game.bank == {**{c: bank[c] + colored[c] for c in COLORS}, "g": bank["g"] + gold}
    assert _supply(game) == initial_supply


def test_all_sixty_cards_have_fixed_balanced_five_gem_identity_across_seeds():
    catalog = _all_cards(GemCityGame([11, 22], seed=0))
    assert len(catalog) == 60
    assert len({card["title"] for card in catalog.values()}) == 60
    orders = []
    for seed in (0, 1, 3, 17, 20261106, None):
        game = GemCityGame([11, 22], seed=seed)
        assert _all_cards(game) == catalog
        orders.append(tuple(card["art"] for card in game.market[1]))
        rng_before = game.rng.getstate()
        for (tier, art), card in catalog.items():
            assert card == game._make_card(tier, art, CARD_TITLES[tier][art])
        assert game.rng.getstate() == rng_before
    assert len(set(orders)) > 1
    for tier in (1, 2, 3):
        cards = [card for (t, _), card in catalog.items() if t == tier]
        assert len({card["title"] for card in cards}) == 20
        assert Counter(card["disc"] for card in cards) == {c: 4 for c in COLORS}
        for card in cards:
            assert card["art_set"] == "jewel-v2"
            assert card["disc"] == COLORS[card["art"] // 4]
            assert card["pts"] == tier and sum(card["cost"].values()) == tier + 1
            assert set(card["cost"]) == set(COLORS)
            assert card["cost"][card["disc"]] == 0
            assert all(type(n) is int and n >= 0 for n in card["cost"].values())
            assert "黄" not in card["title"] and "紫" not in card["title"]
        assert len({sum(card["cost"][c] for card in cards) for c in COLORS}) == 1
        for color in COLORS:
            assert len({tuple(card["cost"].values()) for card in cards if card["disc"] == color}) == 4


@pytest.mark.parametrize("reserved", [False, True], ids=["market", "reserved"])
def test_every_picture_in_two_real_deals_keeps_its_identity_and_actual_payments(reserved):
    for (tier, art), deals in _market_examples().items():
        for seed, index in deals:
            game = GemCityGame([11, 22], seed=seed)
            card = deepcopy(game.snapshot()["market"][str(tier)][index])
            assert card["art"] == art
            if reserved:
                game.act(11, {"op": "reserve", "tier": tier, "idx": index})
                assert game.private(11)["reserved"] == [card]
                assert game.private(22)["reserved"] == []
                assert game.tokens[11]["g"] == 1
                assert card not in game.market[tier]
                _other_turn(game, card)
                action = {"op": "buy_res", "idx": 0}
            else:
                action = {"op": "buy", "tier": tier, "idx": index}
            _earn_and_buy(game, card, action)
            assert not game.private(11)["reserved"]
            assert game.private(11)["cards"] == 1 and game.score[11] == tier
            assert game.private(22)["collection"] == [] and "collection" not in game.snapshot()
            assert len(game.market[tier]) == 4 and len(game.deck[tier]) == 15


@pytest.mark.parametrize("art,color,title", [(16, "s", "钴蓝矿井"), (12, "e", "翠玉矿脉")],
                         ids=["blue-earns-blue", "green-not-yellow"])
def test_reported_gem_colors_grant_and_spend_their_real_permanent_discount(art, color, title):
    seed, index = _market_examples()[1, art][0]
    game = GemCityGame([11, 22], seed=seed)
    card = deepcopy(game.market[1][index])
    assert card["title"] == title and card["disc"] == color and card["art_set"] == "jewel-v2"
    _earn_and_buy(game, card, {"op": "buy", "tier": 1, "idx": index})
    assert game.discount[11][color] == 1
    assert all(game.discount[11][c] == 0 for c in COLORS if c != color)
    # Apply the new bonus to a different, actually dealt card charging that colour.
    tier, index, next_card = next((tier, i, deepcopy(c))
                                 for tier, cards in game.market.items() for i, c in enumerate(cards)
                                 if c["cost"][color] > 0)
    _other_turn(game, next_card)
    _earn_and_buy(game, next_card, {"op": "buy", "tier": tier, "idx": index})
    assert len(game.cards[11]) == 2
