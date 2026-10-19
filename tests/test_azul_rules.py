# -*- coding: utf-8 -*-
"""Azul P0 规则对齐 BGA/官方规则。

覆盖：工厂数量、回合末统一上墙、每轮地板结算、起始玩家标记/下轮先手、
终局时机、终局 +2/+7/+10、平局判定、盒盖回填、地板溢出上限、快照字段。
"""
import pytest

from games_pkg.azul import COLORS, MARKER, AzulGame, _wall_col


def _game(n=2, seed=1):
    return AzulGame(list(range(1, n + 1)), seed=seed)


def _empty_tables(g):
    """模拟工厂与中央都已取空（直接触发回合末结算）。"""
    g.offers = [[] for _ in g.offers]
    g.center = []


# 1) 工厂盘数量 = 2×人数+1
@pytest.mark.parametrize("n,count", [(2, 5), (3, 7), (4, 9)])
def test_factory_count_is_two_per_player_plus_one(n, count):
    g = _game(n)
    assert len(g.offers) == count
    assert all(len(bowl) == 4 for bowl in g.offers)


# 2) 花纹行满了不立即上墙，留到回合末
def test_complete_line_waits_for_round_end():
    g = _game()
    g.pending = ["r", "r"]
    g._place(1, {"row": 1})                  # 第 2 行容量 2 → 满
    assert len(g.rows[1][1]) == 2
    assert g.wall[1][(1, _wall_col(0, 1))] is None
    assert g.pending is None


# 3) 回合末统一上墙并立即计分
def test_wall_tiling_happens_at_round_end_and_scores():
    g = _game()
    g.rows[1][1] = ["r", "r"]
    g.rows[1][0] = ["b"]
    _empty_tables(g)
    msgs = g._end_round()
    assert g.wall[1][(1, _wall_col(0, 1))] == "r"
    assert g.wall[1][(0, _wall_col(2, 0))] == "b"
    assert g.rows[1][0] == [] and g.rows[1][1] == []
    assert g.score[1] >= 2
    assert any("上墙" in m for m in msgs)


# 4) 地板每轮结算并清空，0 分保底
def test_floor_penalty_is_per_round_and_cleared():
    g = _game()
    g.floor[1] = ["r", "r", "b"]             # -1-1-2 = -4
    g.score[1] = 10
    _empty_tables(g)
    g._end_round()
    assert g.floor[1] == []
    assert g.score[1] == 6

    g2 = _game()
    g2.floor[1] = list("rrb")
    g2.score[1] = 0
    _empty_tables(g2)
    g2._end_round()
    assert g2.score[1] == 0                  # 不会扣成负数


# 5) 首取中央拿起始玩家标记，并成为下一轮先手
def test_first_center_take_gets_marker_and_next_round_start():
    g = _game()
    g.center = ["r"]
    g.offers = [[] for _ in g.offers]
    g.turn = 1                               # 2 号先行动
    msgs = g.act(2, {"op": "take", "src": "center", "col": "r"})
    assert g.marker_uid == 2
    assert MARKER in g.floor[2]
    assert any("起始玩家标记" in m for m in msgs)
    g.act(2, {"op": "floor"})                # 落完 → 工厂/中央空 → 回合末
    assert g.round == 2
    assert g.start_uid == 2
    assert g.turn == 1                       # players=[1,2] 中 2 的座位序
    assert g.marker_uid is None              # 新轮标记回到中央


# 6) 终局发生在本轮 Wall-tiling 之后，而不是拼满当下
def test_game_ends_after_wall_tiling_not_mid_place():
    g = _game()
    for c in range(1, 5):                    # 墙第 1 行只差 (0,0) 的红砖
        g.wall[1][(0, c)] = COLORS[c]
    g.rows[1][0] = ["r"]
    _empty_tables(g)
    assert g.winner is None
    g._end_round()
    assert g.wall[1][(0, 0)] == "r"
    assert g.winner == 1


# 7) 终局加分：整行 +2 / 整列 +7 / 集齐一色 +10
def test_finish_counts_row_column_and_color_bonuses():
    g = _game()
    for r in range(5):
        for c in range(5):
            g.wall[1][(r, c)] = COLORS[(c - r) % 5]
    g.score[1] = g.score[2] = 0
    g._finish()
    assert g.score[1] == 5 * 2 + 5 * 7 + 5 * 10


# 8) 平局先比完整行数；仍平则共享胜利
def test_finish_tie_break_by_rows_then_shared_win():
    g = _game()
    for c in range(5):
        g.wall[1][(0, c)] = COLORS[c]
    g.score[1], g.score[2] = 0, 2            # 1 号 +2 后与 2 号同分
    g._finish()
    assert g.winners == [1]

    g2 = _game()
    g2.score[1] = g2.score[2] = 7
    g2._finish()
    assert set(g2.winners) == {1, 2}
    assert "平局" in g2.ended()["detail"]


# 9) 袋空时用盒盖弃砖回填
def test_empty_bag_refills_from_lid():
    g = _game()
    g.bag = []
    g.lid = ["r"] * 30
    g._replenish()
    assert sum(len(b) for b in g.offers) == 20
    assert len(g.bag) == 10


# 10) 地板最多 7 格，多余回盒盖
def test_floor_overflow_caps_at_seven_and_rest_to_lid():
    g = _game()
    g.floor[1] = ["r"] * 6
    g._to_floor(1, ["b"] * 4)
    assert len(g.floor[1]) == 7
    assert g.lid.count("b") == 3


# 11) 快照暴露 pending / 先手 / 地板砖（UI 需要）
def test_snapshot_exposes_pending_marker_and_floor_tiles():
    g = _game()
    g.pending = ["r"]
    g.floor[1] = ["r", MARKER]
    s = g.snapshot()
    assert s["pending"] == ["r"]
    assert s["start_uid"] == 1 and s["marker_uid"] is None
    assert s["floor_tiles"]["1"] == ["r"]
    assert s["floor"]["1"] == 2


# 12) 全流程随机对局：2/3/4 人都能正常结束，地板不越界
@pytest.mark.parametrize("n", [2, 3, 4])
def test_random_games_terminate_with_valid_state(n):
    import random

    rnd = random.Random(100 + n)
    g = _game(n, seed=7)
    for _step in range(20000):
        if g.winner:
            break
        uid = g._cur()
        choices = []
        for i, bowl in enumerate(g.offers):
            for col in sorted(set(bowl)):
                choices.append((i, col))
        for col in sorted(set(g.center)):
            choices.append(("center", col))
        assert choices, "回合进行中不该无砖可取"
        src, col = rnd.choice(choices)
        g.act(uid, {"op": "take", "src": src, "col": col})
        placed = False
        for row in range(5):
            c = _wall_col(COLORS.index(col), row)
            line = g.rows[uid][row]
            if (g.wall[uid][(row, c)] is None and len(line) < row + 1
                    and (not line or line[0] == col)):
                g.act(uid, {"op": "place", "row": row})
                placed = True
                break
        if not placed:
            g.act(uid, {"op": "floor"})
        assert all(len(g.floor[u]) <= 7 for u in g.players)
    assert g.winner is not None, "对局应在有限步内结束"

