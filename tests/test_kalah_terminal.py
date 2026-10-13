"""KALAH-TERMINAL-01: public actions, 48-seed fixtures, and natural legal plays."""
import copy
import random

import pytest

from games_pkg.base import GameRuleError
from games_pkg.kalah import KalahGame
from games_pkg.rooms import RoomManager

A, B = 11, 22


def _store_finish(actor, outcome):
    game = KalahGame([A, B], seed=1)
    game.turn = actor
    if actor == A:
        a_store, b_store, b_pits, expected = {
            "win": (30, 11, [1] * 6, (31, 17, A)),
            "loss": (10, 31, [1] * 6, (11, 37, B)),
            "draw": (23, 20, [4, 0, 0, 0, 0, 0], (24, 24, None)),
        }[outcome]
        game.cells = [0, 0, 0, 0, 0, 1, a_store, b_store] + b_pits
        action, last = {"hole": 6}, 6
    else:
        a_store, b_store, expected = {
            "win": (5, 30, (17, 31, B)),
            "loss": (25, 10, (37, 11, A)),
            "draw": (12, 23, (24, 24, None)),
        }[outcome]
        # B global13 sends seven seeds over A0..5, skips A store6, then B store7.
        game.cells = [1] * 6 + [a_store, b_store] + [0, 0, 0, 0, 0, 7]
        action, last = {"hole": 14}, 7
    assert sum(game.cells) == 48
    return game, action, last, expected


def _assert_terminal(game, actor, action, last, stores, winner, messages, captured=0):
    assert game.finished is True, game.snapshot()
    assert game.turn == actor                  # no further turn after terminal move
    assert game.cells[:6] == [0] * 6 and game.cells[8:] == [0] * 6
    assert (game.cells[6], game.cells[7]) == stores
    assert sum(game.cells) == 48
    state = game.snapshot()
    assert state["status"] == "ended" and state["winner_uid"] == winner
    assert state["stores"] == {str(A): stores[0], str(B): stores[1]}
    assert state["last"] == (actor, action["hole"] - 1, last, False, captured)
    result = game.ended()
    assert result is not None and result["winner_uid"] == winner
    assert messages and not any("再走一次" in m or "轮到" in m for m in messages)
    if winner is None:
        assert "平局" in result["detail"] and any("平局" in m for m in messages)
    else:
        assert any(f"玩家{winner}" in m and "取胜" in m for m in messages)
    before = copy.deepcopy(state)
    for uid, hole in ((A, 6), (B, 14)):
        with pytest.raises(GameRuleError, match="本局已结束"):
            game.act(uid, {"hole": hole})
        assert game.snapshot() == before


@pytest.mark.parametrize("actor", [A, B])
@pytest.mark.parametrize("outcome", ["win", "loss", "draw"])
def test_final_own_store_move_finishes_before_extra_turn(actor, outcome):
    game, action, last, expected = _store_finish(actor, outcome)
    messages = game.act(actor, action)
    _assert_terminal(game, actor, action, last, expected[:2], expected[2], messages)


@pytest.mark.parametrize("actor", [A, B])
def test_capture_draw_finishes_without_changing_turn(actor):
    game = KalahGame([A, B], seed=1)
    game.turn = actor
    if actor == A:
        game.cells = [1, 0, 0, 0, 0, 0, 20, 20, 4, 0, 0, 0, 3, 0]
        action, last = {"hole": 1}, 1
    else:
        game.cells = [4, 0, 0, 0, 3, 0, 20, 20, 1, 0, 0, 0, 0, 0]
        action, last = {"hole": 9}, 9
    assert sum(game.cells) == 48
    messages = game.act(actor, action)
    _assert_terminal(game, actor, action, last, (24, 24), None, messages, captured=4)


@pytest.mark.parametrize("actor", [A, B])
def test_nonterminal_extra_turn_still_keeps_actor(actor):
    game = KalahGame([A, B], seed=1)
    game.turn = actor
    if actor == A:
        game.cells = [4, 4, 4, 4, 4, 1, 1, 2] + [4] * 6
        action, last = {"hole": 6}, 6
    else:
        game.cells = [1] * 6 + [10, 21] + [4, 0, 0, 0, 0, 7]
        action, last = {"hole": 14}, 7
    assert sum(game.cells) == 48
    messages = game.act(actor, action)
    assert game.ended() is None and game.snapshot()["status"] == "playing"
    assert game.turn == actor and sum(game.cells) == 48
    assert game.last_move == (actor, action["hole"] - 1, last, True, 0)
    assert any("再走一次" in m for m in messages) and not any("轮到" in m for m in messages)


@pytest.mark.parametrize("actor", [A, B])
def test_nonterminal_normal_turn_still_changes_actor(actor):
    game = KalahGame([A, B], seed=1)
    game.turn = actor
    if actor == A:
        game.cells = [1, 4, 4, 4, 4, 4, 1, 2] + [4] * 6
        action = {"hole": 1}
    else:
        game.cells = [4] * 6 + [1, 2, 1, 4, 4, 4, 4, 4]
        action = {"hole": 9}
    assert sum(game.cells) == 48
    messages = game.act(actor, action)
    other = B if actor == A else A
    assert game.ended() is None and game.turn == other and sum(game.cells) == 48
    assert game.last_move[3] is False
    assert any(f"轮到 玩家{other}" in m for m in messages)


@pytest.mark.parametrize("actor", [A, B])
def test_real_room_manager_action_returns_terminal_rule_result(actor):
    manager = RoomManager({"kalah": KalahGame})
    room = manager.create(A, "kalah")
    manager.join(B, room.room_id)
    manager.start(A, room.room_id)
    game, action, last, expected = _store_finish(actor, "draw")
    # Synthetic near-terminal position, injected only in test; real room/game paths.
    room.gs.cells = list(game.cells)
    room.gs.turn = actor
    messages = manager.handle_action(actor, room.room_id, action)
    _assert_terminal(room.gs, actor, action, last, expected[:2], None, messages)
    assert room.gs.ended()["winner_uid"] is None


@pytest.mark.parametrize("choice_seed", [0, 1, 2, 3])
def test_natural_public_action_sequence_never_stalls_on_empty_actor(choice_seed):
    game = KalahGame([A, B], seed=1)
    chooser = random.Random(choice_seed)
    for step in range(400):
        assert sum(game.cells) == 48
        if game.finished:
            assert game.snapshot()["status"] == "ended" and game.ended() is not None
            return
        actor = game.turn
        holes = range(6) if actor == A else range(8, 14)
        legal = [i for i in holes if game.cells[i] > 0]
        assert legal, (choice_seed, step, game.snapshot())
        messages = game.act(actor, {"hole": chooser.choice(legal) + 1})
        if game.finished:
            assert game.last_move[3] is False
            assert not any("再走一次" in m or "轮到" in m for m in messages)
    pytest.fail(f"bounded natural sequence seed {choice_seed} did not finish in 400 moves")
