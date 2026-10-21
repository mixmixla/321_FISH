# -*- coding: utf-8 -*-
"""桌面端合法落点高亮 _legal_marks 纯逻辑单测（不创建 Tk 窗口）。

覆盖：走子类仅在选中同源格时给出目标、落子类全量返回、
连四按列自底向上转行（无棋盘回落列顶）、将棋打入仅在选中持子时出现、
非法/空 legal 返回空列表。
"""
import client_gameui as cu

OX, OY, CELL = 10.0, 46.0, 40.0


def px(x, y):
    return (OX + x * CELL + CELL / 2, OY + y * CELL + CELL / 2)


def test_move_marks_require_matching_selection():
    priv = {"legal": [{"from": [1, 2], "to": [3, 4]},
                      {"from": [5, 6], "to": [7, 8]}]}
    assert cu._legal_marks({"sel": {"game": "chess", "fx": 1, "fy": 2}},
                           priv, "chess", OX, OY, CELL) == [px(3, 4)]
    assert cu._legal_marks({"sel": {"game": "chess", "fx": 5, "fy": 6}},
                           priv, "chess", OX, OY, CELL) == [px(7, 8)]
    # 选中别的源格 / 别的游戏 / 完全没有选中 → 不提示
    assert cu._legal_marks({"sel": {"game": "chess", "fx": 9, "fy": 9}},
                           priv, "chess", OX, OY, CELL) == []
    assert cu._legal_marks({"sel": {"game": "xiangqi", "fx": 1, "fy": 2}},
                           priv, "chess", OX, OY, CELL) == []
    assert cu._legal_marks({}, priv, "chess", OX, OY, CELL) == []


def test_place_marks_all_and_dedup():
    priv = {"legal": [{"x": 0, "y": 0}, {"x": 1, "y": 2}, {"x": 1, "y": 2}]}
    assert cu._legal_marks({}, priv, "tictactoe", OX, OY, CELL) == [
        px(0, 0), px(1, 2)]
    assert cu._legal_marks({"sel": {"game": "junqi"}},
                           priv, "junqi", OX, OY, CELL) == [px(0, 0), px(1, 2)]


def test_connect4_col_to_bottom_most_empty_row():
    st = {"board": [[0, 0, 0], [0, 0, 0], [0, 1, 0]]}
    priv = {"legal": [{"col": 0}, {"col": 1}, {"col": 2}]}
    assert cu._legal_marks({}, priv, "connect4", OX, OY, CELL, st) == [
        px(0, 2), px(1, 1), px(2, 2)]


def test_connect4_full_col_skipped_and_no_board_falls_back_to_top():
    st = {"board": [[1, 0], [1, 0]]}
    assert cu._legal_marks({}, {"legal": [{"col": 0}, {"col": 1}]},
                           "connect4", OX, OY, CELL, st) == [px(1, 1)]
    # 拿不到棋盘 → 列顶部（首行中心）
    assert cu._legal_marks({}, {"legal": [{"col": 3}]},
                           "connect4", OX, OY, CELL, {}) == [px(3, 0)]


def test_shogi_drop_only_when_matching_piece_selected():
    priv = {"legal": [{"drop": 8, "x": 1, "y": 2},
                      {"drop": 9, "x": 3, "y": 4}]}
    sel = {"sel": {"game": "shogi", "drop": 8}}
    assert cu._legal_marks(sel, priv, "shogi", OX, OY, CELL) == [px(1, 2)]
    # 未选持子 / 选中别的子 / 选中的是走子源格 → 不显示打入点
    assert cu._legal_marks({}, priv, "shogi", OX, OY, CELL) == []
    assert cu._legal_marks({"sel": {"game": "shogi", "drop": 7}},
                           priv, "shogi", OX, OY, CELL) == []
    assert cu._legal_marks({"sel": {"game": "shogi", "fx": 0, "fy": 0}},
                           priv, "shogi", OX, OY, CELL) == []


def test_invalid_or_empty_legal_returns_empty():
    assert cu._legal_marks({}, None, "chess", OX, OY, CELL) == []
    assert cu._legal_marks({}, {}, "junqi", OX, OY, CELL) == []
    assert cu._legal_marks({}, {"legal": None}, "dou", OX, OY, CELL) == []
    assert cu._legal_marks({}, {"legal": []}, "shogi", OX, OY, CELL) == []
    bad = {"legal": ["junk", {"foo": 1}, {"from": [1, 2]},
                     {"x": "a", "y": 1}, {"col": -1}]}
    assert cu._legal_marks({"sel": {"game": "chess", "fx": 1, "fy": 2}},
                           bad, "chess", OX, OY, CELL) == []
