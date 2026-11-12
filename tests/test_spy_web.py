import pytest

from games_pkg.base import GameRuleError
from games_pkg.spy import SpyGame, WORD_PAIRS


def describe_round(game):
    for uid in game.alive:
        game.act(uid, {"describe": "合成线索"})


def context(game):
    return {"round_key": game.round_key, "clue_round": game.clue_round}


def test_ballot_persists_across_tie_and_nonterminal_elimination():
    game = SpyGame(range(1, 5), seed=3)
    describe_round(game)
    first_round = context(game)
    for uid in game.alive:
        game.act(uid, {"vote": uid % 4 + 1, "spy_context": first_round})
    state = game.snapshot()
    assert state["clue_round"] == 2 and state["status"] == "describing"
    assert state["describes"] == state["voted"] == []
    assert state["last_ballot"] == {"clue_round": 1, "counts": dict.fromkeys(range(1, 5), 1),
                                     "eliminated_uid": None, "tie": True}
    with pytest.raises(GameRuleError, match="这一轮已变化"):
        game.act(game.alive[0], {"describe": "旧描述", "spy_context": first_round})
    assert game.snapshot() == state

    describe_round(game)
    target = next(uid for uid in game.alive if uid != game.spy_uid)
    for uid in game.alive[:]:
        game.act(uid, {"vote": target if uid != target else game.spy_uid})
    next_state = game.snapshot()
    assert next_state["status"] == "describing" and next_state["clue_round"] == 3
    assert next_state["last_ballot"]["eliminated_uid"] == target
    assert next_state["last_ballot"]["counts"][target] == 3
    assert target not in next_state["alive"] and game.private(target) is None
    assert next_state["spy_uid"] is None and next_state["reveal_words"] is None


def test_vote_privacy_and_invalidation_on_target_departure():
    game = SpyGame(range(1, 6), seed=1)
    describe_round(game)
    target = next(uid for uid in game.players if uid != game.spy_uid)
    voter = next(uid for uid in game.players if uid != target)
    game.act(voter, {"vote": target, "spy_context": context(game)})
    assert game.snapshot()["vote_counts"] == {}
    assert game.snapshot()["last_ballot"] is None
    assert game.private(voter)["own_vote"] == target
    assert game.private(target)["own_vote"] is None and game.private(99) is None
    before = game.snapshot()["revision"]
    game.player_left(target)
    state = game.snapshot()
    assert state["revision"] == before + 1
    assert target in state["seat_order"] and target not in state["players"]
    assert voter not in state["voted"] and game.private(voter)["own_vote"] is None
    replacement = next(uid for uid in game.alive if uid != voter)
    game.act(voter, {"vote": replacement, "spy_context": context(game)})
    assert game.private(voter)["own_vote"] == replacement


def test_words_are_public_only_on_reveal_and_action_is_bound_to_its_game():
    game = SpyGame([1, 2, 3, 4], seed=3)
    other = SpyGame([1, 2, 3, 4], seed=3)
    assert other.round_key != game.round_key
    private = game.private(1)
    assert private["owner_uid"] == 1 and private["round_key"] == game.round_key
    assert game.snapshot()["reveal_words"] is None
    with pytest.raises(GameRuleError, match="这一轮已变化"):
        game.act(1, {"describe": "旧房回调", "spy_context": context(other)})
    describe_round(game)
    for uid in game.alive[:]:
        target = game.spy_uid if uid != game.spy_uid else next(p for p in game.alive if p != uid)
        game.act(uid, {"vote": target})
    state = game.snapshot()
    assert state["status"] == "reveal" and state["winner_uid"] is None
    assert state["reveal_words"] == dict(zip(("civilian", "spy"), WORD_PAIRS[game.pair_idx]))
