"""Matchpairs indexed draws, frame boundaries and private delivery."""
from copy import deepcopy
import json
import random

import pytest

from games_pkg.base import GameRuleError
from games_pkg.matchpairs import MatchPairsGame, SUITS, _card_str


def indexed(game, target, index):
    return {"op": "draw", "target": target, "index": index,
            "round_key": game.round_key, "seq": game.seq}


@pytest.mark.parametrize("players", [2, 3, 4, 5])
def test_opening_keeps_actual_rank_suit_and_counts_all_51_cards(players):
    seed = 108
    game = MatchPairsGame(range(1, players + 1), seed)
    deck = [(rank, suit) for rank in range(1, 14) for suit in SUITS
            if (rank, suit) != (12, "♠")]
    random.Random(seed).shuffle(deck)
    for seat, uid in enumerate(game.players):
        dealt = deck[seat::players]
        counts = {rank: sum(card[0] == rank for card in dealt) for rank, _ in dealt}
        expected = []
        for card in dealt:
            if counts[card[0]] % 2 and not any(prev[0] == card[0] for prev in expected):
                expected.append(card)
        assert game.private(uid)["hand"] == [_card_str(card) for card in expected]
        assert game.private(uid)["owner_uid"] == uid
    public = game.snapshot()
    assert sum(public["hand_size"].values()) + 2 * public["discarded_pairs"] == 51
    assert game.private(1000) is None
    assert public["last_draw"] is public["last_pair"] is None


def test_bad_index_and_wrong_turn_preserve_original_turn_hands_and_rng():
    game = MatchPairsGame([1, 2, 3], 108)
    game.hands = {1: [], 2: [(3, "♠")], 3: [(4, "♦"), (3, "♥")]}
    game.turn = 0
    before = deepcopy(game.hands), game.turn, game.seq, game.rng.getstate()
    good = indexed(game, 3, 1)
    for uid, fields in [(1, {}), (2, {"index": -1}), (2, {"index": 2}),
                        (2, {"index": True}), (2, {"index": "1"}),
                        (2, {"target": 1}), (2, {"target": "3"}),
                        (2, {"seq": -1}), (2, {"seq": False}), (2, {"round_key": "old"})]:
        with pytest.raises(GameRuleError):
            game.act(uid, good | fields)
        assert (game.hands, game.turn, game.seq, game.rng.getstate()) == before


def test_real_back_slot_pairs_and_duplicate_request_is_stale():
    game = MatchPairsGame([1, 2, 3], 108)
    game.hands = {1: [(3, "♠"), (8, "♥")], 2: [(4, "♣"), (3, "♥")],
                  3: [(9, "♦")]}
    request = indexed(game, 2, 1)
    game.act(1, request)
    assert game.hands == {1: [(8, "♥")], 2: [(4, "♣")], 3: [(9, "♦")]}
    assert game.snapshot()["last_pair"]["cards"] == ("3♥", "3♠")
    assert game.snapshot()["last_draw"] == {"uid": 1, "target": 2, "index": 1,
                                           "paired": True, "seq": 1}
    game.turn = 0  # A future turn with the same actor/target still must reject the old frame.
    before = deepcopy(game.hands)
    with pytest.raises(GameRuleError):
        game.act(1, request)
    assert game.hands == before and game.seq == 1


def test_unmatched_card_is_only_in_acting_players_private_frame():
    game = MatchPairsGame([1, 2, 3], 108)
    game.hands = {1: [(3, "♠")], 2: [(4, "♣"), (10, "♦")], 3: [(9, "♦")]}
    events = game.act(1, indexed(game, 2, 1))
    assert game.hands[2] == [(4, "♣")]
    assert game.private(1)["hand"] == ["3♠", "10♦"]
    assert game.private(1)["drawn_card"] == "10♦"
    assert game.private(1)["seq"] == game.snapshot()["seq"] == 1
    assert "drawn_card" not in game.private(2)
    assert game.private(999) is None
    assert "10♦" not in json.dumps([game.snapshot(), events], ensure_ascii=False)


def test_safe_exit_preserves_active_seat_and_advances_frame():
    game = MatchPairsGame([1, 2, 3], 108)
    game.hands = {1: [], 2: [(4, "♣")], 3: [(4, "♦"), (12, "♥")]}
    game.safe = {1}
    game.turn = 1
    request = indexed(game, 3, 0)
    game.player_left(1)
    assert game.snapshot()["turn_uid"] == 2
    assert game.snapshot()["draw_from_uid"] == 3
    assert game.private(1) is None
    with pytest.raises(GameRuleError):
        game.act(2, request)
    game.act(2, indexed(game, 3, 0))
    assert game.ended() and game.loser_uid == 3


def test_opening_that_leaves_one_card_ends_and_round_key_is_unique():
    a, b = MatchPairsGame([1, 2], 565), MatchPairsGame([1, 2], 565)
    assert a.ended() and a.snapshot()["turn_uid"] is None
    assert sum(a.snapshot()["hand_size"].values()) == 1
    assert a.round_key != b.round_key
