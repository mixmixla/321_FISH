# -*- coding: utf-8 -*-
"""收尾优化回归：拉密暂存可见/摸牌规则、阿瓦隆按钮过滤、跳棋结算文案、宝石平分。"""
from games_pkg.gemcity import GemCityGame
from games_pkg.halma import HalmaGame
from games_pkg.rummikub import RummikubGame, color_of, num_of


def _tid(color, num, skip=0):
    hits = [i for i in range(len(color_of))
            if color_of[i] == color and num_of[i] == num]
    return hits[skip]


# ---------------------------------------------------------------- 拉密
def test_rummikub_private_exposes_staged_tiles_and_points():
    """回归：此前暂存牌既不在快照也不在私密信息里，玩家看不到首任累计进度。"""
    g = RummikubGame([1, 2], seed=1)
    tiles = [_tid(0, 1), _tid(0, 2), _tid(0, 3)]
    g.rack[1] = list(tiles)
    g.turn = 0
    g.act(1, {"op": "meld", "tiles": tiles})
    priv = g.private(1)
    assert priv["staged_pts"] == 6
    assert len(priv["staged"]) == 1
    assert [t["n"] for t in priv["staged"][0]] == [1, 2, 3]
    assert priv["hand"] == []


def test_rummikub_done_without_play_draws_one_tile():
    """回归：此前未出牌也能直接结束回合，导致牌数偏少；现在按规则摸一张。"""
    g = RummikubGame([1, 2], seed=1)
    tiles = [_tid(0, 1), _tid(0, 2), _tid(0, 3)]
    g.rack[1] = list(tiles)
    g.turn = 0
    bag_before = len(g.bag)
    g.act(1, {"op": "meld", "tiles": tiles})       # 首任不足，进入暂存
    msgs = g.act(1, {"op": "done"})
    assert len(g.rack[1]) == 4                     # 3 张收回 + 摸 1 张
    assert len(g.bag) == bag_before - 1
    assert any("摸一张" in m for m in msgs)


def test_rummikub_done_after_real_play_does_not_draw():
    """已经成功把牌打上桌时，结束回合不应再摸牌。"""
    g = RummikubGame([1, 2], seed=1)
    g.initial_ok[1] = True
    g.rack[1] = [_tid(1, 9)]
    g.placed_turn = 1
    g.turn = 0
    bag_before = len(g.bag)
    g.act(1, {"op": "done"})
    assert len(g.rack[1]) == 1
    assert len(g.bag) == bag_before


# ---------------------------------------------------------------- 阿瓦隆
def test_avalon_actions_are_filtered_by_role():
    """回归：此前忠臣也能看到「任务失败」，点击只会收到服务端拒绝。"""
    from client import _actions_for

    def labels(priv):
        return [row[0] for row in _actions_for("avalon", priv)]

    loyal = labels({"role": 0})
    assert not any("任务失败" in x for x in loyal)
    assert not any("指认梅林" in x for x in loyal)
    assert any("任务成功" in x for x in loyal)

    assassin = labels({"role": 2})
    assert any("任务失败" in x for x in assassin)
    assert not any("指认梅林" in x for x in assassin)

    final = labels({"role": 2, "guess_required": True})
    assert any("指认梅林" in x for x in final)

    mordred = labels({"role": 3})
    assert any("任务失败" in x for x in mordred)


# ---------------------------------------------------------------- 跳棋
def test_halma_solo_survivor_has_end_detail():
    """回归：掉线后只剩一人判胜时 detail 为空，结算面板没有说明。"""
    g = HalmaGame([1, 2], seed=1)
    g.player_left(2)
    end = g.ended()
    assert end and end["winner_uid"] == 1
    assert "离开" in end["detail"]


# ---------------------------------------------------------------- 璀璨宝石
def test_gemcity_tie_break_prefers_fewer_cards():
    """官方平分规则：同分时发展卡更少者胜。"""
    g = GemCityGame([1, 2], seed=1)
    g.score = {1: 16, 2: 16}
    g.cards = {1: [{"pts": 1}] * 3, 2: [{"pts": 1}]}
    g._finish()
    assert g.winner == 2

    g2 = GemCityGame([1, 2], seed=1)
    g2.score = {1: 16, 2: 16}
    g2.cards = {1: [{"pts": 1}], 2: [{"pts": 1}]}
    g2._finish()
    assert g2.winner == 1                          # 仍相同按座次
