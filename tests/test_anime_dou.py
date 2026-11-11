"""Art identity, terrain and rule validation for the beast-girl board."""
import copy
import pytest
from games_pkg.dou import DouGame, WATER, TRAPS, DENS, MOUSE, CAT, DOG, LION, TIGER, ELEPHANT
from games_pkg.base import GameRuleError
from boardgames.chess_dou.catalog import identity, can_act, NAMES, water_rectangles
from boardgames.gallery import read_resource


def move(fx, fy, tx, ty):
    return dict(fx=fx, fy=fy, tx=tx, ty=ty)


def test_atlas_rank_and_seat_are_exact_and_assets_served():
    assert NAMES == ("鼠", "猫", "狗", "狼", "豹", "虎", "狮", "象")
    for rank in range(1, 9):
        assert identity(rank) == (0, rank)
        assert identity(rank + 10) == (1, rank)
    assert identity(0) is None and identity(10) is None
    for name in ("dou-beastgirls.webp", "cover-dou.webp", "dou-terrain.webp"):
        data, mime = read_resource(name)
        assert len(data) > 10000 and mime == "image/webp"


def test_setup_terrain_and_camp_ownership_match():
    g = DouGame([1, 2])
    assert len(g.board) == 16 and len(WATER) == 12
    assert all((3, y) not in WATER for y in range(9))
    for side in (0, 1):
        assert sorted(a for p, a in g.board.values() if p == side) == list(range(1, 9))
        assert all((y < 3 if side == 0 else y > 5) for (x, y), (p, a) in g.board.items() if p == side)
        assert all(pos not in g.board for pos in TRAPS[side] | {DENS[side]})
    assert g.snapshot()["dens"] == {"0": [3, 0], "1": [3, 8]}
    assert water_rectangles(g.snapshot()["water"]) == [[1, 3, 2, 3], [4, 3, 2, 3]]
    assert water_rectangles([[True, False], [True, True], [False, True]]) == [[0, 0, 1, 1], [0, 1, 2, 1], [1, 2, 1, 1]]


@pytest.mark.parametrize("target", [(0, 0), (0, 1), (3, 0)])
def test_reject_same_square_own_piece_own_den_without_mutation(target):
    g = DouGame([1, 2]); g.board = {(0, 0): (0, DOG), (0, 1): (0, CAT), (3, 1): (0, DOG)}
    origin = (3, 1) if target == (3, 0) else (0, 0)
    before = copy.deepcopy(g.__dict__)
    with pytest.raises(GameRuleError):
        g.act(1, move(*origin, *target))
    assert g.board == before["board"] and g.turn == before["turn"]


def test_same_rank_capture_leaves_attacker_and_elephant_cannot_eat_rat():
    g = DouGame([1, 2]); g.board = {(0, 3): (0, CAT), (0, 2): (1, CAT)}
    g.act(1, move(0, 3, 0, 2)); assert g.board == {(0, 2): (0, CAT)}
    g = DouGame([1, 2]); g.board = {(0, 3): (0, ELEPHANT), (0, 2): (1, MOUSE)}
    with pytest.raises(GameRuleError): g.act(1, move(0, 3, 0, 2))


def test_trap_weakening_and_restoration():
    g = DouGame([1, 2]); g.board = {(1, 0): (0, MOUSE), (2, 0): (1, ELEPHANT)}
    g.act(1, move(1, 0, 2, 0)); assert g.board[(2, 0)] == (0, MOUSE)
    g = DouGame([1, 2]); g.board = {(2, 8): (0, ELEPHANT), (1, 8): (1, CAT)}
    with pytest.raises(GameRuleError): g.act(1, move(2, 8, 1, 8))
    g.act(1, move(2, 8, 2, 7)); g.turn = 0
    g.board[(1, 7)] = (1, CAT)
    g.act(1, move(2, 7, 1, 7)); assert g.board[(1, 7)] == (0, ELEPHANT)


@pytest.mark.parametrize("animal", [LION, TIGER])
def test_horizontal_jump_captures_and_rat_blocks(animal):
    g = DouGame([1, 2]); g.board = {(0, 4): (0, animal), (3, 4): (1, CAT)}
    g.act(1, move(0, 4, 3, 4)); assert g.board[(3, 4)] == (0, animal)
    g = DouGame([1, 2]); g.board = {(0, 4): (0, animal), (1, 4): (1, MOUSE)}
    with pytest.raises(GameRuleError): g.act(1, move(0, 4, 3, 4))


def test_every_advertised_move_is_accepted_and_identity_guard():
    g = DouGame([1, 2])
    for _ in range(40):
        uid = g.players[g.turn]
        legal = g.legal_moves(uid)
        if not legal or g.winner: break
        for m in legal:
            trial = copy.deepcopy(g)
            trial.act(uid, move(*m["from"], *m["to"]))
        m = legal[g.rng.randrange(len(legal))]
        g.act(uid, move(*m["from"], *m["to"]))
    st = DouGame([1, 2]).snapshot()
    assert can_act(st, 1) and not can_act(st, 2) and not can_act(st, 3)
    assert not can_act(st, 1, connected=False)
    assert not can_act(st, 1, {"status": "ended"})
