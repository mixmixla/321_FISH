# -*- coding: utf-8 -*-
"""规则收尾 C：开拓 / 工坊 / 领地 / 我是城主 的掉线善后（player_left）。

每条回归用例的 docstring 用「回归：此前……」说明被修掉的错误行为。
"""
from games_pkg.chengzhu import ChengZhuGame
from games_pkg.gongfang import GongfangGame
from games_pkg.kaituo import KaituoGame
from games_pkg.lingdi import DIRS, LingdiGame


def _tile(owner=None, main="f"):
    return {"edges": {d: main for d in DIRS}, "owner": owner}


# ================================================================ 开拓
def test_kaituo_player_left_passes_turn_to_next_alive():
    """回归：此前开拓掉线者仍占着座位与回合，下一位存活者永远轮不到。"""
    g = KaituoGame([1, 2, 3], seed=1)
    g.phase = "play"
    g.turn = g.players.index(2)
    g.player_left(2)

    assert g.players == [1, 3]
    assert g.players[g.turn] == 3
    g.act(3, {"op": "skip"})
    assert g.players[g.turn] == 1


def test_kaituo_player_left_clears_resources_villages_and_roads():
    """回归：此前离场者的资源、村庄、道路留在场上继续占位并参与计分。"""
    g = KaituoGame([1, 2, 3], seed=1)
    g.phase = "play"
    g.turn = 0
    g.res[2]["wood"] = 4
    g.board[(0, 0)] = {"owner": 2, "city": True}
    g.board[(0, 1)] = {"owner": 2, "city": False}
    g.board[(2, 2)] = {"owner": 1, "city": False}
    g.roads[((0, 0), (0, 1))] = 2
    g.roads[((2, 2), (2, 3))] = 1

    g.player_left(2)

    assert 2 not in g.res
    assert g.board == {(2, 2): {"owner": 1, "city": False}}
    assert g.roads == {((2, 2), (2, 3)): 1}
    snap = g.snapshot()
    assert "2" not in snap["res"] and "2" not in snap["score"]
    assert snap["turn_uid"] == 1


def test_kaituo_player_left_during_setup_enters_play_phase():
    """回归：此前布置轮按原人数轮转，掉线后 setup_count 错位，回合无法推进。"""
    g = KaituoGame([1, 2, 3], seed=1)
    g.turn = 1

    g.player_left(2)

    assert g.players == [1, 3]
    assert g.phase == "play"
    assert g.players[g.turn] == 1
    g.act(1, {"op": "skip"})
    assert g.players[g.turn] == 3


def test_kaituo_player_left_single_winner_then_draw():
    """回归：此前剩 1 人也不判胜，全员离开后 ended() 仍为 None。"""
    g = KaituoGame([1, 2, 3], seed=1)
    g.phase = "play"
    g.turn = 1

    g.player_left(1)
    assert g.players == [2, 3] and g.winner is None
    g.player_left(3)
    assert g.players == [2] and g.winner == 2
    assert g.ended()["winner_uid"] == 2

    g.player_left(2)
    assert g.players == [] and g.winner is None
    assert g.ended()["winner_uid"] is None
    assert g.snapshot()["turn_uid"] is None


def test_kaituo_player_left_is_idempotent():
    """回归：此前重复调用可能再次改回合/重复扣状态，未知 uid 也可能抛异常。"""
    g = KaituoGame([1, 2, 3], seed=1)
    g.phase = "play"
    g.turn = 2
    g.res[1]["ore"] = 3
    g.player_left(1)
    snap = g.snapshot()

    assert g.player_left(1) == []
    assert g.player_left(999) == []
    assert g.snapshot() == snap


# ================================================================ 工坊
def test_gongfang_player_left_frees_spot_and_advances_turn():
    """回归：此前离场者工人永久占着工位，回合也停在他身上。"""
    g = GongfangGame([1, 2, 3], seed=1)
    g.turn = 0
    g.act(1, {"op": "work", "id": g.spots[0]["id"]})
    g.act(2, {"op": "work", "id": g.spots[1]["id"]})
    g.act(3, {"op": "pass"})
    assert g.players[g.turn] == 1

    g.player_left(1)

    assert g.players == [2, 3]
    assert g.spots[0]["owner"] is None
    assert g.spots[1]["owner"] == 2
    assert g.players[g.turn] == 2
    assert 1 not in g.placed and 1 not in g.score
    g.act(2, {"op": "work", "id": g.spots[2]["id"]})
    assert g.spots[2]["owner"] == 2


def test_gongfang_player_left_closes_round_when_remaining_all_done():
    """回归：此前只剩已过牌的玩家时，回合仍会停在离场者身上不结束本轮。"""
    g = GongfangGame([1, 2, 3], seed=1)
    g.done = {1, 2}
    g.turn = 2

    g.player_left(3)

    assert g.players == [1, 2]
    assert g.round_no == 2
    assert g.done == set()
    assert g.players[g.turn] in (1, 2)


def test_gongfang_player_left_single_winner_then_draw():
    """回归：此前剩 1 人不判胜，全员离开后 ended() 仍为 None。"""
    g = GongfangGame([1, 2, 3], seed=1)

    g.player_left(1)
    assert g.players == [2, 3] and g.winner is None
    g.player_left(3)
    assert g.players == [2] and g.winner == 2
    assert g.ended()["winner_uid"] == 2

    g.player_left(2)
    assert g.players == [] and g.winner is None
    assert g.ended()["winner_uid"] is None
    assert g.snapshot()["turn_uid"] is None


def test_gongfang_player_left_is_idempotent():
    """回归：此前重复调用可能重复回收工位/改回合，未知 uid 也可能抛异常。"""
    g = GongfangGame([1, 2, 3], seed=1)
    g.turn = 1
    g.player_left(2)
    snap = g.snapshot()

    assert g.player_left(2) == []
    assert g.player_left(999) == []
    assert g.snapshot() == snap


# ================================================================ 领地
def test_lingdi_player_left_moves_turn_off_the_leaver():
    """回归：此前只对回合下标取模，离场者原位不动，回合仍落在他身上。"""
    g = LingdiGame([1, 2, 3], seed=1)
    g.turn = 1

    g.player_left(2)

    assert g.players == [1, 3]
    assert g.players[g.turn] == 3
    g.act(3, {"op": "pass"})
    assert g.players[g.turn] == 1


def test_lingdi_player_left_clears_meeples_without_scoring():
    """回归：此前离场者米宝仍在场上，关闭区域时还会给他计分。"""
    g = LingdiGame([1, 2, 3], seed=1)
    g.board = {
        (4, 4): _tile(owner=2),
        (0, 0): _tile(owner=1),
    }
    g.meeples = {1: 2, 2: 0, 3: 3}
    g.score = {1: 5, 2: 3, 3: 1}

    g.player_left(2)

    assert 2 not in g.meeples and 2 not in g.score
    assert g.score == {1: 5, 3: 1}          # 不清算、不转给他人
    assert g.board[(4, 4)]["owner"] is None
    assert g.board[(0, 0)]["owner"] == 1
    snap = g.snapshot()
    assert "2" not in snap["meeples"] and "2" not in snap["score"]


def test_lingdi_player_left_single_winner_then_draw():
    """回归：此前剩 1 人不判胜，全员离开后 ended() 仍为 None。"""
    g = LingdiGame([1, 2, 3], seed=1)

    g.player_left(1)
    assert g.players == [2, 3] and g.winner is None
    g.player_left(3)
    assert g.players == [2] and g.winner == 2
    assert g.ended()["winner_uid"] == 2

    g.player_left(2)
    assert g.players == [] and g.winner is None
    assert g.ended()["winner_uid"] is None
    assert g.snapshot()["turn_uid"] is None


def test_lingdi_player_left_is_idempotent():
    """回归：此前重复调用会再次移动回合下标，未知 uid 也可能抛异常。"""
    g = LingdiGame([1, 2, 3], seed=1)
    g.turn = 2
    g.player_left(1)
    snap = g.snapshot()

    assert g.player_left(1) == []
    assert g.player_left(999) == []
    assert g.snapshot() == snap


# ================================================================ 我是城主
def test_chengzhu_player_left_current_picker_hands_over_immediately():
    """回归：此前只移除挑选者，pick_idx 未修正，下一位会被跳过或本轮卡死。"""
    g = ChengZhuGame([1, 2, 3], seed=4)
    g.act(1, {"op": "pick", "dom": 0, "x": 2, "y": 2, "rot": 0})
    assert g._current_picker() == 2

    g.player_left(2)

    assert g.players == [1, 3]
    assert g.pick_order == [1, 3]
    assert g._current_picker() == 3
    assert len(g.market) == 1               # 离场者未挑的板块一并移出
    g.act(3, {"op": "pick", "dom": 0, "x": 2, "y": 2, "rot": 0})
    # 本轮所有存活玩家都挑过 → 正常补牌进入下一轮
    assert g.pick_idx == 0 and g.pick_order == [1, 3]
    assert len(g.market) == 2


def test_chengzhu_player_left_clears_board_and_shifts_pick_cursor():
    """回归：此前离场者棋盘仍参与终局计分，已挑选留下的游标会错位。"""
    g = ChengZhuGame([1, 2, 3], seed=4)
    g.act(1, {"op": "pick", "dom": 0, "x": 2, "y": 2, "rot": 0})
    g.act(2, {"op": "pick", "dom": 0, "x": 2, "y": 2, "rot": 0})
    assert g.placed[2] == 1 and g.grid[2]

    g.player_left(2)

    assert 2 not in g.grid and 2 not in g.placed and 2 not in g.score
    assert g.pick_idx == 1 and g._current_picker() == 3
    assert len(g.market) == 1               # 玩家 1、2 已各挑一块


def test_chengzhu_player_left_single_winner_then_draw():
    """回归：此前剩 1 人不判胜，全员离开后 ended() 仍为 None。"""
    g = ChengZhuGame([1, 2, 3], seed=4)

    g.player_left(1)
    assert g.players == [2, 3] and g.winner is None
    g.player_left(3)
    assert g.players == [2] and g.winner == 2
    assert g.ended()["winner_uid"] == 2

    g.player_left(2)
    assert g.players == [] and g.winner is None
    assert g.ended()["winner_uid"] is None
    assert g.snapshot()["picker_uid"] is None


def test_chengzhu_player_left_is_idempotent():
    """回归：此前重复调用会再次动市场与挑选游标，未知 uid 也可能抛异常。"""
    g = ChengZhuGame([1, 2, 3], seed=4)
    g.player_left(3)
    snap = g.snapshot()

    assert g.player_left(3) == []
    assert g.player_left(999) == []
    assert g.snapshot() == snap
