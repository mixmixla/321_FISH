"""Kaituo's new board objects agree with the existing game and send boundary."""
import copy
import random
from types import SimpleNamespace

import pytest

from boardgames.economy_kaituo import legal_targets, reject_action, submit_action
from games_pkg.base import GameRuleError
from games_pkg.kaituo import RES_COST, RES_ORDER
from kaituo_fixtures import fund, setup_game


@pytest.mark.parametrize("model", ["road", "settle", "city"])
def test_legal_board_targets_match_rules_and_pay_the_resource_chips(model):
    game = fund(setup_game())
    uid = game.players[0]
    vertices, edges = legal_targets(game.snapshot(), uid, model)
    points = [(row, col) for row in range(6) for col in range(6)]
    if model == "road":
        candidates = [(a,b) for a in points for b in points
                      if a < b and abs(a[0]-b[0])+abs(a[1]-b[1])==1]
    else:
        candidates = [(point,None) for point in points]
    for start,end in candidates:
        trial = copy.deepcopy(game)
        action = {"op":"build", "kind":model, "i":start[0], "j":start[1]}
        if end is not None:
            action.update(b_i=end[0], b_j=end[1])
        offered = (start,end) in edges if end is not None else start in vertices
        try:
            trial.act(uid, action)
        except GameRuleError:
            assert not offered, action
        else:
            assert offered, action
            for resource in RES_ORDER:
                assert game.res[uid][resource]-trial.res[uid][resource] == RES_COST[model].get(resource,0)


def test_dice_and_producing_tiles_match_authoritative_inventory():
    game = setup_game()
    uid = game.players[0]
    game.rng = random.Random(5)
    game.tiles[(0,0)]["num"] = 8
    game.tiles[(0,1)]["num"] = 8
    game.robber = (0,1)
    game.board[(0,0)]["city"] = True
    old_stock = copy.deepcopy(game.res)
    game.act(uid,{"op":"roll"})
    state = game.snapshot()
    assert state["last_dice"] == [5,3] and state["last_roll"] == 8
    production = state["production"]
    assert any(p["r"]==0 and p["c"]==0 and p["uid"]==uid and p["n"]==2 for p in production)
    assert all((p["r"],p["c"])!=game.robber for p in production)
    for owner in game.players:
        for resource in RES_ORDER:
            expected = sum(p["n"] for p in production if p["uid"]==owner and p["res"]==resource)
            assert game.res[owner][resource]-old_stock[owner][resource] == expected
    game.act(uid,{"op":"skip"})
    assert not game.snapshot()["rolled"]
    assert game.snapshot()["last_dice"] == [5,3]
    game._resolve_roll(game.players[1], 7)
    assert game.snapshot()["last_dice"] is None and game.snapshot()["production"] == []


def test_trade_receipt_and_display_revision_only_advance_after_success():
    game = fund(setup_game())
    uid = game.players[0]
    before = game.snapshot()["action_seq"]
    with pytest.raises(GameRuleError):
        game.act(uid,{"op":"trade","give":"wood","want":"ore","n":13})
    assert game.snapshot()["action_seq"] == before
    assert game.snapshot()["last_trade"] is None
    game.act(uid,{"op":"trade","give":"wood","want":"ore","n":4})
    assert game.snapshot()["action_seq"] == before+1
    assert (game.res[uid]["wood"],game.res[uid]["ore"]) == (8,13)
    assert game.snapshot()["last_trade"] == {"uid":uid,"give":"wood","want":"ore","n":4}


def test_two_desktop_views_share_pending_until_new_revision_or_exact_rejection():
    game = fund(setup_game())
    uid = game.players[0]
    state = copy.deepcopy(game.snapshot())
    room = {"game":"kaituo","room_id":"local-test","round":1,"status":"playing","players":list(game.players)}
    sent = []
    core = SimpleNamespace(uid=uid,connected=True,connection_epoch=1,
                           game_action=lambda rid,action: sent.append(action) or True)
    host = SimpleNamespace(core=core, _render_canvas=lambda: None)
    def view(s):
        return {"game":"kaituo","_room_context":("local-test",1),"me":uid,"state":s}
    trade = {"op":"trade","give":"wood","want":"ore","n":4}
    assert submit_action(host,room,state,view(state),trade)
    same_revision = copy.deepcopy(state)
    assert not submit_action(host,room,same_revision,view(same_revision),trade)
    reject_action(host,"unrelated")
    assert not submit_action(host,room,state,view(state),trade)
    reject_action(host,sent[0]["_kt_request"])
    assert submit_action(host,room,state,view(state),trade)
    game.act(uid,trade)
    next_state=game.snapshot()
    assert not submit_action(host,room,next_state,view(state),trade)
    assert submit_action(host,room,next_state,view(next_state),trade)
    assert len(sent)==3


def test_immediate_transport_failure_does_not_lock_the_desktop_table():
    game = fund(setup_game())
    uid = game.players[0]
    state = game.snapshot()
    room = {"game":"kaituo","room_id":"local-test","round":1,"status":"playing","players":list(game.players)}
    core = SimpleNamespace(uid=uid,connected=True,connection_epoch=1,game_action=lambda rid,action: False)
    host = SimpleNamespace(core=core)
    view={"game":"kaituo","_room_context":("local-test",1),"me":uid,"state":state}
    assert not submit_action(host,room,state,view,{"op":"skip"})
    assert host._kt_pending is None
    core.game_action=lambda rid,action: True
    assert submit_action(host,room,state,view,{"op":"skip"})
