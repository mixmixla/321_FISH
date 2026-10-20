# -*- coding: utf-8 -*-
"""围棋：9/13/19 路统一入口、房间参数、贴目与展示层接线。"""
import pytest

import web
from games_pkg import GAME_META, GAME_TYPES
from games_pkg.base import GameRuleError
from games_pkg.go import GoGame, GoSoloGame
from games_pkg.rooms import RoomManager


def test_go_is_a_single_entry_with_size_choices():
    assert "go19" not in GAME_TYPES
    meta = GAME_META["go"]
    assert meta["options"]["size"] == [9, 13, 19]
    assert meta["default_options"]["size"] == 19
    assert "9 / 13 / 19" in meta["rules"]


@pytest.mark.parametrize("size", [9, 13, 19])
def test_go_builds_each_common_board_size(size):
    g = GoGame([1, 2], options={"size": size})
    assert g.size == size
    assert len(g.board) == size and all(len(row) == size for row in g.board)
    assert g.komi == GoGame.KOMI_BY_SIZE[size]
    g.act(1, {"x": size - 1, "y": size - 1})
    assert g.board[size - 1][size - 1] == 1


def test_go_defaults_to_19_and_rejects_unknown_sizes():
    assert GoGame([1, 2]).size == 19
    with pytest.raises(GameRuleError):
        GoGame([1, 2], options={"size": 11})
    with pytest.raises(GameRuleError):
        GoGame([1, 2], options={"size": "big"})


def test_go_komi_depends_on_board_size():
    g = GoGame([1, 2], options={"size": 9})
    g.board[0][0] = 1
    g.board[8][8] = 2
    g._score()
    assert g.scores[1] == 1 and g.scores[2] == 7.5


def test_room_carries_size_option_into_the_started_game():
    rm = RoomManager(GAME_TYPES)
    room = rm.create(1, "go", {"size": 13})
    assert room.options == {"size": 13}
    assert room.summary()["options"] == {"size": 13}
    rm.join(2, room.room_id)
    started = rm.start(1, room.room_id)
    assert started.gs.size == 13
    assert started.gs.komi == 7.5


def test_room_defaults_and_validates_size_option():
    rm = RoomManager(GAME_TYPES)
    assert rm.create(1, "go").options == {"size": 19}
    with pytest.raises(GameRuleError):
        rm.create(1, "go", {"size": 11})
    with pytest.raises(GameRuleError):
        rm.create(1, "go", "19")


def test_solo_practice_stays_on_9x9():
    g = GoSoloGame([1])
    assert g.size == 9 and g.komi == 6.5


def test_web_lobby_offers_size_picker_and_has_no_go19_entry():
    html = web._SERVED_PAGE().decode("utf-8")
    assert "go19(box,s)" not in html
    assert "g.options&&g.options.size" in html
    assert "payload.options={size:parseInt(optSel.value,10)}" in html
