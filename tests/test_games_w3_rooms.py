# -*- coding: utf-8 -*-
"""W3 游戏在房间管理下的端到端可用性：创建→加入→开局→动作→快照"""
import pytest
from games_pkg import GAME_TYPES
from games_pkg.base import GameRuleError
from games_pkg.halma import VALID
from games_pkg.rooms import RoomManager


@pytest.fixture()
def mgr():
    return RoomManager(GAME_TYPES)


def _new(mgr, name, n):
    room = mgr.create(1, name)
    for u in range(2, n + 1):
        mgr.join(u, room.room_id)
    mgr.start(1, room.room_id)
    return room


def test_w3_games_are_registered():
    for name in ("tictactoe", "halma", "checkers", "blokus", "ludo"):
        assert name in GAME_TYPES


def test_w3_game_list_meta(mgr):
    for name in ("tictactoe", "halma", "checkers", "blokus", "ludo"):
        room = mgr.create(1, name)
        assert room.game_name == name


def test_tictactoe_room_full_game(mgr):
    room = _new(mgr, "tictactoe", 2)
    mgr.handle_action(1, room.room_id, {"x": 0, "y": 0})
    mgr.handle_action(2, room.room_id, {"x": 1, "y": 0})
    assert room.gs.snapshot()["board"][0][0] == 1


def test_halma_room_full_game(mgr):
    room = _new(mgr, "halma", 2)
    g = room.gs
    uid = g.players[g.turn]
    moved = False
    for (fx, fy), (o, arm) in list(g.board.items()):
        if o != uid:
            continue
        for dx, dy in [(0, 1), (1, 1), (1, 0), (-1, 1)]:
            tx, ty = fx + dx, fy + dy
            if (tx, ty) in g.board or (tx, ty) not in VALID:
                continue
            mgr.handle_action(uid, room.room_id,
                              {"fx": fx, "fy": fy, "tx": tx, "ty": ty})
            moved = True
            break
        if moved:
            break
    assert moved


def test_checkers_room_full_game(mgr):
    room = _new(mgr, "checkers", 2)
    g = room.gs
    uid = g.players[g.turn]
    for r in range(5):
        for c in range(8):
            if g.board[r][c] != 1 or (r + c) % 2 != 1:
                continue
            for dc in (-1, 1):
                nc = c + dc
                if 0 <= nc < 8 and g.board[r + 1][nc] == 0:
                    mgr.handle_action(uid, room.room_id,
                                      {"fx": c, "fy": r, "tx": nc, "ty": r + 1})
                    return
    raise AssertionError("未找到合法国际跳棋首步")


def test_blokus_room_full_game(mgr):
    room = _new(mgr, "blokus", 2)
    mgr.handle_action(1, room.room_id, {"op": "place", "piece": "D",
                                        "oi": 0, "x": 0, "y": 0})
    mgr.handle_action(2, room.room_id, {"op": "pass"})
    assert room.gs.placed.get(1, 0) == 2


def test_ludo_room_full_game(mgr):
    room = _new(mgr, "ludo", 2)
    g = room.gs
    uid = g.players[g.turn]
    g.dice, g.need_roll = 6, False
    mgr.handle_action(uid, room.room_id, {"op": "move", "idx": 0})
    assert g.miles[uid][0] == 0