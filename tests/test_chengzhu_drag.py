# -*- coding: utf-8 -*-
"""我是城主（Kingdomino）：引擎旋转校验 + 桌面拖拽投放规则的回归测试。"""
import pathlib

import pytest

import client_gameui as cu
from games_pkg.base import GameRuleError
from games_pkg.chengzhu import ChengZhuGame

ROOT = pathlib.Path(__file__).resolve().parents[1]

DOM_FD = {"id": 0, "A": {"terr": "fd", "crown": 0},
          "B": {"terr": "fd", "crown": 0}}


def _fresh():
    """干净领地：避免随机市场/牌堆干扰 _place 的规则判定。"""
    g = ChengZhuGame([1, 2], seed=4)
    g.grid = {1: {}, 2: {}}
    g.placed = {1: 0, 2: 0}
    return g


# ---------------------------------------------------------------- 引擎：旋转
def test_engine_rot0_occupies_right_cell():
    g = ChengZhuGame([1, 2], seed=4)
    g.act(1, {"op": "pick", "dom": 0, "x": 2, "y": 2, "rot": 0})
    assert set(g.grid[1]) == {(2, 2), (2, 3)}
    assert g.placed[1] == 1


def test_engine_rot1_occupies_lower_cell():
    g = ChengZhuGame([1, 2], seed=4)
    g.act(1, {"op": "pick", "dom": 0, "x": 2, "y": 2, "rot": 1})
    assert set(g.grid[1]) == {(2, 2), (3, 2)}


def test_engine_invalid_rot_rejected_without_state_change():
    g = ChengZhuGame([1, 2], seed=4)
    ids = [d["id"] for d in g.market]
    with pytest.raises(GameRuleError, match="旋转参数无效"):
        g.act(1, {"op": "pick", "dom": 0, "x": 2, "y": 2, "rot": 2})
    assert g.grid[1] == {} and g.placed[1] == 0
    assert [d["id"] for d in g.market] == ids
    assert g.pick_idx == 0


# ---------------------------------------------------------------- 引擎：放置
def test_engine_first_domino_anywhere():
    g = _fresh()
    g._place(1, DOM_FD, {"x": 0, "y": 0, "rot": 0})
    assert set(g.grid[1]) == {(0, 0), (0, 1)}
    g2 = _fresh()
    g2._place(1, DOM_FD, {"x": 4, "y": 3, "rot": 0})       # 贴右下角
    assert set(g2.grid[1]) == {(4, 3), (4, 4)}
    g3 = _fresh()
    g3._place(1, DOM_FD, {"x": 3, "y": 4, "rot": 1})       # 竖放贴下边
    assert set(g3.grid[1]) == {(3, 4), (4, 4)}


def test_engine_second_domino_needs_same_terrain_neighbor():
    g = _fresh()
    g.grid[1][(0, 1)] = {"terr": "fd", "crown": 0}
    g.placed[1] = 1
    dom = {"id": 1, "A": {"terr": "fo", "crown": 0},
           "B": {"terr": "fd", "crown": 0}}
    g._place(1, dom, {"x": 1, "y": 0, "rot": 0})
    assert g.grid[1][(1, 0)]["terr"] == "fo"
    assert g.grid[1][(1, 1)]["terr"] == "fd"
    assert g.placed[1] == 2


def test_engine_second_domino_different_terrain_rejected():
    g = _fresh()
    g.grid[1][(0, 0)] = {"terr": "wa", "crown": 0}
    g.placed[1] = 1
    dom = {"id": 1, "A": {"terr": "fo", "crown": 0},
           "B": {"terr": "fd", "crown": 0}}
    with pytest.raises(GameRuleError, match="必须与同地型相邻"):
        g._place(1, dom, {"x": 1, "y": 0, "rot": 0})
    assert set(g.grid[1]) == {(0, 0)}
    assert g.placed[1] == 1


def test_engine_out_of_bounds_and_occupied_rejected():
    g = _fresh()
    with pytest.raises(GameRuleError, match="越界"):
        g._place(1, DOM_FD, {"x": 4, "y": 4, "rot": 0})
    with pytest.raises(GameRuleError, match="越界"):
        g._place(1, DOM_FD, {"x": 4, "y": 0, "rot": 1})
    g.grid[1][(1, 1)] = {"terr": "gr", "crown": 0}
    with pytest.raises(GameRuleError, match="位置已被占用"):
        g._place(1, DOM_FD, {"x": 1, "y": 1, "rot": 0})
    assert g.placed[1] == 0


# ---------------------------------------------------------------- 客户端镜像
def _cz_st(market=None, grid=None, placed=0, uid=1):
    return {"size": 5, "grid": {str(uid): dict(grid or {})},
            "placed": {str(uid): placed},
            "market": [DOM_FD] if market is None else market}


def test_cz_legal_first_domino_anywhere():
    st = _cz_st()
    assert cu._cz_legal(st, 1, 0, 0, 0, 0) is True
    assert cu._cz_legal(st, 1, 0, 4, 3, 0) is True


def test_cz_legal_out_of_bounds():
    st = _cz_st()
    assert cu._cz_legal(st, 1, 0, 4, 4, 0) is False     # 右半出界
    assert cu._cz_legal(st, 1, 0, 4, 0, 1) is False     # 下半出界
    assert cu._cz_legal(st, 1, 0, -1, 0, 0) is False


def test_cz_legal_occupied():
    st = _cz_st(grid={"2,2": {"terr": "wa", "crown": 0}})
    assert cu._cz_legal(st, 1, 0, 2, 2, 0) is False
    assert cu._cz_legal(st, 1, 0, 2, 1, 0) is False     # 第二半被占


def test_cz_legal_rejects_without_same_terrain():
    st = _cz_st(grid={"0,0": {"terr": "wa", "crown": 0}}, placed=1)
    assert cu._cz_legal(st, 1, 0, 1, 0, 0) is False


def test_cz_legal_accepts_same_terrain_neighbor():
    st = _cz_st(grid={"1,2": {"terr": "fd", "crown": 0}}, placed=1)
    assert cu._cz_legal(st, 1, 0, 0, 1, 0) is True       # (0,2) 邻 (1,2)


def test_cz_legal_rot1_second_half_match():
    dom = {"id": 0, "A": {"terr": "fo", "crown": 0},
           "B": {"terr": "fd", "crown": 0}}
    st = _cz_st(market=[dom], grid={"3,0": {"terr": "fd", "crown": 0}},
                placed=1)
    assert cu._cz_legal(st, 1, 0, 1, 0, 1) is True      # 下半 (2,0) 邻 (3,0)
    assert cu._cz_legal(st, 1, 0, 1, 0, 0) is False     # 横放两半都不相邻


# ---------------------------------------------------------------- 静态接线
def test_handle_drag_dispatches_chengzhu():
    src = (ROOT / "client_gameui.py").read_text(encoding="utf-8")
    start = src.index("def handle_drag(")
    end = src.index("\ndef ", start + 10)
    body = src[start:end]
    assert '"chengzhu"' in body
    assert "_chengzhu_drag" in body


def test_desktop_chengzhu_drag_symbols_present():
    src = (ROOT / "client_gameui.py").read_text(encoding="utf-8")
    for mark in ("_chengzhu_drag", "cz_cells", "cz_market", "cz_sel",
                 "cz_rot", "_cz_legal"):
        assert mark in src, mark


def test_web_chengzhu_drag_and_rotation_present():
    src = (ROOT / "web.py").read_text(encoding="utf-8")
    for mark in ("data-czr", "state.czrot", "state.czsel", "czLegal", "x:r"):
        assert mark in src, mark
