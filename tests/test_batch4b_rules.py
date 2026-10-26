# -*- coding: utf-8 -*-
"""第 4b 批德式桌游 P0 回归：开拓/领地/铁路/工坊/我是城主/璀璨宝石。

每条回归用例的 docstring 用「回归：此前……」说明被修掉的错误行为。
"""
import pytest

from games_pkg.base import GameRuleError
from games_pkg.chengzhu import DOM_PER_PLAYER, ChengZhuGame
from games_pkg.gemcity import COLORS, NOBLES, GemCityGame
from games_pkg.gongfang import GongfangGame
from games_pkg.kaituo import KaituoGame
from games_pkg.lingdi import DIRS, LingdiGame
from games_pkg.tielu import END_TARGET, TICKETS, TieluGame


# ================================================================ 开拓
def _kaituo_play(seed=1):
    g = KaituoGame([1, 2], seed=seed)
    g.phase = "play"
    g.turn = 0
    return g


def _road(g, uid, a, b):
    g.roads[tuple(sorted((a, b)))] = uid


def test_kaituo_longest_road_handles_road_cycle():
    """回归：此前最长路 DFS 只记「上一个顶点」，道路成环时无限递归 RecursionError。"""
    g = _kaituo_play()
    for a, b in (((0, 0), (0, 1)), ((0, 1), (1, 1)),
                 ((1, 1), (1, 0)), ((1, 0), (0, 0))):
        _road(g, 1, a, b)
    assert g._longest_road_len(1) == 4      # 环上最长简单路径 4 条边，不重复走同一段
    assert g._longest_road(1) == 0          # 未达 5 条，无奖励
    assert g._score(1) == 0                 # 不能抛异常


def test_kaituo_longest_road_is_awarded_to_the_unique_leader_only():
    """回归：此前只要自己道路 >=5 条就加 2 分，两人并列时双方都白拿奖励。"""
    g = _kaituo_play()
    for c in range(5):
        _road(g, 1, (0, c), (0, c + 1))
        _road(g, 2, (2, c), (2, c + 1))
    assert g._longest_road_len(1) == g._longest_road_len(2) == 5
    assert g._score(1) == 0 and g._score(2) == 0

    g.roads.pop(tuple(sorted(((2, 4), (2, 5)))))   # 玩家 2 只剩 4 条
    assert g._score(1) == 2 and g._score(2) == 0


def test_kaituo_road_build_can_win_with_longest_road_bonus():
    """回归：此前建路分支从不检查 10 分线，靠最长路达标的玩家永远赢不了。"""
    g = _kaituo_play(seed=5)
    for v in ((0, 0), (0, 1), (0, 2), (0, 3)):
        g.board[v] = {"owner": 1, "city": True}       # 4 城 = 8 分
    for c in range(4):
        _road(g, 1, (0, c), (0, c + 1))
    g.res[1]["wood"] = 1
    g.res[1]["brick"] = 1
    g.rolled = True                                # 建造需先掷骰

    msgs = g.act(1, {"op": "build", "kind": "road",
                     "i": 0, "j": 4, "b_i": 0, "b_j": 5})
    assert g._longest_road_len(1) == 5
    assert g.winner == 1
    assert "🏆" in msgs[0]
    assert g.ended()["winner_uid"] == 1
    with pytest.raises(GameRuleError):
        g.act(2, {"op": "roll"})


def test_kaituo_bad_trade_quantity_is_rejected_without_mutation():
    """回归：此前 exchange 的 n 直接 int()，非法输入抛 ValueError 而非 GameRuleError。"""
    g = _kaituo_play()
    g.res[1]["wood"] = 4
    g.rolled = True
    before = dict(g.res[1])
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "trade", "give": "wood", "want": "brick", "n": "abc"})
    assert g.res[1] == before and g.turn == 0


def test_kaituo_setup_round_invariants():
    g = KaituoGame([1, 2], seed=5)
    g.act(1, {"op": "setup", "i": 0, "j": 0, "b_i": 0, "b_j": 1})
    g.act(2, {"op": "setup", "i": 5, "j": 0, "b_i": 5, "b_j": 1})
    g.act(2, {"op": "setup", "i": 5, "j": 5, "b_i": 4, "b_j": 5})
    g.act(1, {"op": "setup", "i": 0, "j": 5, "b_i": 0, "b_j": 4})
    assert g.phase == "play" and g.turn == 0
    assert sum(1 for x in g.board.values() if x["owner"] == 1) == 2
    assert sum(1 for o in g.roads.values() if o == 1) == 2

    for _ in range(10):
        uid = g.players[g.turn]
        g.act(uid, {"op": "roll"})
        for u in g.players:
            assert all(v >= 0 for v in g.res[u].values())
            assert g._score(u) >= 0
        g.act(uid, {"op": "skip"})


# ================================================================ 领地
def _tile(main="f", **edges):
    e = {d: main for d in DIRS}
    e.update(edges)
    return {"edges": e, "owner": None}


def test_lingdi_adjacent_placement_matches_shared_edge():
    """回归：此前把邻接 dict 当元组解包直接 ValueError，第二块板块必崩；
    且共享边方向写反（拿邻块 d 边比新块 OPP[d] 边）。"""
    g = LingdiGame([1, 2], seed=1)
    g.board = {(4, 4): _tile("f", S="r")}
    g.current = _tile("f", N="r")
    g.turn = 0
    g.act(1, {"op": "place", "r": 5, "c": 4})
    assert (5, 4) in g.board

    g2 = LingdiGame([1, 2], seed=1)
    g2.board = {(4, 4): _tile("f", S="r")}
    g2.current = _tile("f", N="c")            # 共享边不匹配
    g2.turn = 0
    with pytest.raises(GameRuleError):
        g2.act(1, {"op": "place", "r": 5, "c": 4})
    assert (5, 4) not in g2.board


def test_lingdi_bad_meeple_rolls_back_the_placed_tile():
    """回归：此前先用掉板块再校验米宝，非法米宝会留下板块并让玩家白拿一块。"""
    g = LingdiGame([1, 2], seed=3)
    g.act(1, {"op": "place", "r": 4, "c": 4})
    g.board[(4, 4)]["edges"] = _tile("f")["edges"]
    g.current = _tile("f")
    g.turn = 1
    before_board = {p: dict(c) for p, c in g.board.items()}
    before_meeples = dict(g.meeples)

    with pytest.raises(GameRuleError):
        g.act(2, {"op": "place", "r": 4, "c": 5, "meeple": "9,9"})
    assert g.board == before_board
    assert g.placed == 1
    assert g.meeples == before_meeples
    assert g.current is not None and g.turn == 1

    # 同一块板块重试成功，不会复制出第二块
    g.act(2, {"op": "place", "r": 4, "c": 5, "meeple": "self"})
    assert g.placed == 2 and (4, 5) in g.board


def test_lingdi_closed_region_scores_even_without_new_meeple():
    """回归：此前只有「本回合放米宝」才调用连通区结算，别人补齐封口时既不计分也不退米宝。"""
    g = LingdiGame([1, 2], seed=1)
    g.board = {
        (4, 4): _tile("c", N="f"),                  # 米宝区（主导地型 城）
        (3, 4): _tile("f", S="f"),                  # 北
        (4, 5): _tile("f", W="c"),                  # 东
        (4, 3): _tile("f", E="c"),                  # 西
    }
    g.board[(4, 4)]["owner"] = 1
    g.meeples = {1: 2, 2: 3}
    g.score = {1: 0, 2: 0}
    g.turn = 1
    g.current = _tile("f", N="c")                   # 南，封住最后一口
    g.act(2, {"op": "place", "r": 5, "c": 4})

    assert g.score[1] == 1                          # 1 格 × 1
    assert g.meeples[1] == 3                        # 米宝收回
    assert g.board[(4, 4)]["owner"] is None


def test_lingdi_final_scoring_runs_exactly_once():
    """回归：此前抽出最后一块时先结算一次，放完最后一块再结算一次，米宝区分被重复计分。"""
    g = LingdiGame([1, 2], seed=1)
    g.board = {(0, 0): _tile("f")}
    g.board[(0, 0)]["owner"] = 1
    g.meeples = {1: 2, 2: 3}
    g.score = {1: 0, 2: 0}
    g.placed = 1
    g.deck = [_tile("f")]                           # 牌堆只剩一块
    g.current = _tile("f")
    g.turn = 0

    g.act(1, {"op": "place", "r": 0, "c": 1})       # 抽走最后一块，但还不能终局结算
    assert g.score[1] == 0
    assert g.players[g.turn] == 2
    assert g.current is not None

    g.act(2, {"op": "place", "r": 1, "c": 1})       # 放完最后一块 → 只结算一次
    assert g.score[1] == 3                          # 3 格 × 1，而不是 2+3
    assert g.winner is not None
    assert g.ended() is not None
    assert g.score[1] == 3                          # 再次读取成绩不会被重算


# ================================================================ 铁路
def test_tielu_ticket_draw_never_duplicates_and_rejects_when_exhausted():
    """回归：此前用 tuple 和 list 比较去重永远为真，同一张票证可无限重复抽到并重复计分。"""
    g = TieluGame([1, 2], seed=2)
    g.tickets[1] = [list(t) for t in TICKETS]
    g.turn = 0
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "ticket"})
    assert len(g.tickets[1]) == len(TICKETS)
    assert g.turn == 0

    g2 = TieluGame([1, 2], seed=2)
    g2.tickets = {1: [], 2: []}
    for _ in range(len(TICKETS)):
        g2.turn = 0
        g2.act(1, {"op": "ticket"})
    assert len({tuple(t) for t in g2.tickets[1]}) == len(TICKETS)
    with pytest.raises(GameRuleError):
        g2.turn = 0
        g2.act(1, {"op": "ticket"})


def test_tielu_starting_tickets_are_distinct():
    """回归：此前两张起手票证各自独立乱抽（seed=1 会抽到同一张），终局重复加分。"""
    for seed in range(6):
        g = TieluGame([1, 2], seed=seed)
        for u in g.players:
            assert len({tuple(t) for t in g.tickets[u]}) == 2


def test_tielu_hitting_target_player_starts_final_round():
    """回归：此前 END_TARGET 定义了却从未使用，超分后仍要等线路牌摸空才结算。"""
    g = TieluGame([1, 2, 3], seed=2)
    g.tickets = {u: [] for u in g.players}
    route = g.route_deck[0]
    L = route["length"]
    g.mine[2] = [(0, 1, END_TARGET - L)]            # 再认领一条即恰好 10 分
    g.hand[2][route["color"]] = L
    g.turn = 1                                      # 轮到玩家 2

    g.act(2, {"op": "claim", "a": route["a"], "b": route["b"]})
    assert g._score(2) == END_TARGET
    assert g.trigger_uid == 2
    assert g.players[g.turn] == 3                   # 补回合按座次：先玩家 3
    assert g.ended() is None                        # 补回合尚未走完

    g.act(3, {"op": "skip"})
    assert g.players[g.turn] == 1                   # 再玩家 1，且每人只补一次
    assert g.ended() is None
    g.act(1, {"op": "skip"})
    assert g.winner == 2
    assert g.ended()["winner_uid"] == 2
    with pytest.raises(GameRuleError):
        g.act(2, {"op": "draw"})


def test_tielu_final_scoring_counts_private_tickets():
    g = TieluGame([1, 2], seed=2)
    g.route_deck = []
    g.tickets = {1: [[0, 7, 5]], 2: []}
    g.mine[1] = [(0, 1, 2), (1, 2, 2), (2, 3, 2), (3, 7, 2)]
    assert g.ended()["winner_uid"] == 1
    assert g._total(1) == 8 + 5                     # 连通票证加分
    assert g._total(2) == 0


# ================================================================ 工坊
def test_gongfang_three_rounds_finish_with_consistent_scores():
    """整局不变量：3 轮后必须有胜者，总分等于各轮实际占到工位的分值之和。"""
    g = GongfangGame([1, 2], seed=1)
    expected = {1: 0, 2: 0}
    for _ in range(80):
        if g.winner is not None:
            break
        uid = g.players[g.turn]
        free = [s for s in g.spots if s["owner"] is None]
        if g.placed[uid] < 2 and free:
            before = g.score[uid]
            g.act(uid, {"op": "work", "id": free[0]["id"]})
            expected[uid] += g.score[uid] - before
            assert g.placed[uid] <= 2
        else:
            g.act(uid, {"op": "pass"})
    assert g.round_no == 3
    assert g.winner is not None
    assert g.score == expected
    assert g.winner == max(g.players, key=lambda u: g.score[u])


def test_gongfang_worker_limit_and_round_reset():
    g = GongfangGame([1, 2], seed=1)
    g.act(1, {"op": "work", "id": g.spots[0]["id"]})
    g.act(2, {"op": "work", "id": g.spots[1]["id"]})
    g.act(1, {"op": "work", "id": g.spots[2]["id"]})
    g.act(2, {"op": "work", "id": g.spots[3]["id"]})
    assert g.placed == {1: 2, 2: 2}
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "work", "id": g.spots[4]["id"]})   # 工人已用完
    g.act(1, {"op": "pass"})
    g.act(2, {"op": "pass"})
    assert g.round_no == 2
    assert g.placed == {1: 0, 2: 0}
    assert all(s["owner"] is None for s in g.spots)
    assert all(v >= 0 for v in g.score.values())


# ================================================================ 我是城主
def test_chengzhu_illegal_placement_does_not_consume_market_domino():
    """回归：此前先从市场 pop 再校验坐标，放错位置就永久丢掉一块板块。"""
    g = ChengZhuGame([1, 2], seed=4)
    ids = [d["id"] for d in g.market]
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "pick", "dom": 0, "x": 4, "y": 4, "rot": 0})   # 越界
    assert [d["id"] for d in g.market] == ids
    assert g.placed[1] == 0 and g.grid[1] == {} and g.pick_idx == 0

    g.act(1, {"op": "pick", "dom": 0, "x": 2, "y": 2, "rot": 0})
    g.act(2, {"op": "pick", "dom": 0, "x": 2, "y": 2, "rot": 0})
    ids = [d["id"] for d in g.market]
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "pick", "dom": 0, "x": 0, "y": 0, "rot": 0})   # 不同地型且不相邻
    assert [d["id"] for d in g.market] == ids
    assert g.pick_idx == 0


def test_chengzhu_game_ends_when_everyone_reaches_domino_cap():
    """回归：此前只看牌堆是否耗尽，每人放满 12 块后仍无限要求过牌，永远不结算。"""
    g = ChengZhuGame([1, 2], seed=4)
    g.placed = {1: DOM_PER_PLAYER, 2: DOM_PER_PLAYER}
    g.pick_idx = 0
    g.act(1, {"op": "pass"})
    g.act(2, {"op": "pass"})
    assert g.winner == 1
    assert g.ended() is not None
    assert g.score == {u: g._regions_score(u) for u in g.players}


def test_chengzhu_domino_count_is_conserved_across_a_round():
    g = ChengZhuGame([1, 2], seed=4)
    total = len(g.market) + len(g.piles)
    g.act(1, {"op": "pick", "dom": 0, "x": 2, "y": 2, "rot": 0})
    g.act(2, {"op": "pick", "dom": 0, "x": 2, "y": 2, "rot": 0})
    assert len(g.market) + len(g.piles) + sum(g.placed.values()) == total


def test_chengzhu_region_score_is_cells_times_crowns():
    g = ChengZhuGame([1, 2], seed=4)
    g.grid[1] = {
        (0, 0): {"terr": "fo", "crown": 2},
        (0, 1): {"terr": "fo", "crown": 1},
        (1, 0): {"terr": "fd", "crown": 3},
    }
    assert g._regions_score(1) == 2 * 3 + 1 * 3     # (2 格 × 3 冠) + (1 格 × 3 冠)


# ================================================================ 璀璨宝石
def _free_card(disc="s"):
    return {"tier": 1, "disc": disc, "pts": 0,
            "cost": {c: 0 for c in COLORS}}


def test_gemcity_all_qualified_nobles_are_awarded():
    """回归：此前边遍历 nobles_left 边删除，第二张达标贵宾被跳过、分数少计 3 分。"""
    g = GemCityGame([1, 2], seed=17)
    g.discount[1].update(o=4, d=4, r=4, e=4)         # 同时满足 NOBLES[0] 与 NOBLES[1]
    g.reserved[1] = [_free_card()]
    g.act(1, {"op": "buy_res", "idx": 0})
    assert g.nobles_cards[1] == [3, 3]
    assert len(g.nobles_left) == len(NOBLES) - 2
    assert g.score[1] == 6


def test_gemcity_trigger_uid_zero_still_finishes():
    """回归：此前用 `if not trigger_uid` 判断，0 号玩家达标被当成未触发，终局永远不结算。"""
    g = GemCityGame([0, 1], seed=17)
    g.score[0] = 14
    g.reserved[0] = [dict(_free_card(), pts=1)]
    g.turn = 0
    g.act(0, {"op": "buy_res", "idx": 0})
    assert g.trigger_uid == 0
    assert g.players[g.turn] == 1

    g.act(1, {"op": "take", "colors": ["o", "d", "r"]})
    assert g.winner == 0
    assert g.ended()["winner_uid"] == 0
    with pytest.raises(GameRuleError):
        g.act(0, {"op": "take", "colors": ["o", "d", "r"]})


def test_gemcity_final_round_gives_each_other_player_one_turn():
    """终局不变量：达标后其余每人恰好补一回合（按座次），走完才结算胜者。"""
    g = GemCityGame([1, 2, 3], seed=17)
    g.score[2] = 14
    g.reserved[2] = [dict(_free_card(), pts=1)]
    g.turn = 1                                       # 玩家 2 行动
    g.act(2, {"op": "buy_res", "idx": 0})
    assert g.trigger_uid == 2
    assert g.players[g.turn] == 3                    # 先轮到玩家 3

    g.act(3, {"op": "take", "colors": ["o", "d", "r"]})
    assert g.players[g.turn] == 1 and g.winner is None
    g.act(1, {"op": "take", "colors": ["o", "d", "r"]})
    assert g.winner == 2
    assert g.ended()["winner_uid"] == 2


def test_gemcity_token_supply_is_conserved_across_a_round():
    g = GemCityGame([1, 2], seed=1)

    def supply():
        return {c: g.bank[c] + sum(g.tokens[u][c] for u in g.players)
                for c in COLORS + ["g"]}

    before = supply()
    g.act(1, {"op": "take", "colors": ["o", "d", "r"]})
    g.act(2, {"op": "take2", "color": "s"})
    g.act(1, {"op": "reserve", "tier": 1, "idx": 0})
    assert supply() == before
    for u in g.players:
        assert all(v >= 0 for v in g.tokens[u].values())
