# -*- coding: utf-8 -*-
"""玩家板归一化内几何：归一回、越界、包含性与 ×2 线性精确。"""
import pytest

from boardgames import geom


def test_board_constants_match_spec():
    assert (geom.BOARD_W, geom.BOARD_H) == (384, 288)
    assert (geom.ROWS_N, geom.WALL_N, geom.FLOOR_N) == (5, 5, 7)


def test_non_positive_size_returns_none():
    for w, h in ((0, 288), (384, 0), (-1, 100)):
        assert geom.nameplate(w, h) is None
        assert geom.row_band(0, w, h) is None
        assert geom.row_cell_size(0, w, h) is None
        assert geom.row_slot(0, 0, w, h) is None
        assert geom.wall_band(w, h) is None
        assert geom.wall_cell_size(w, h) is None
        assert geom.wall_slot(0, 0, w, h) is None
        assert geom.floor_band(w, h) is None
        assert geom.floor_slot(0, w, h) is None


def test_out_of_range_index_returns_none():
    W, H = geom.BOARD_W, geom.BOARD_H
    assert geom.row_band(5, W, H) is None
    assert geom.row_band(-1, W, H) is None
    assert geom.row_cell_size(5, W, H) is None
    assert geom.row_slot(0, 1, W, H) is None        # 第 0 行只有 1 格
    assert geom.row_slot(2, 3, W, H) is None        # 第 2 行只有 3 格（j∈[0,2]）
    assert geom.wall_slot(5, 0, W, H) is None
    assert geom.wall_slot(0, 5, W, H) is None
    assert geom.floor_slot(7, W, H) is None


def test_geometry_is_contained_and_ordered():
    W, H = geom.BOARD_W, geom.BOARD_H
    rb, wb, fb = geom.row_band(0, W, H), geom.wall_band(W, H), geom.floor_band(W, H)
    assert wb[0] > rb[2]                    # 墙带在花纹行带右侧
    assert wb[3] <= H and fb[3] <= H and fb[2] <= W
    for i in range(geom.ROWS_N):
        band = geom.row_band(i, W, H)
        cs = geom.row_cell_size(i, W, H)[0]
        for j in range(i + 1):
            x, y, sz = geom.row_slot(i, j, W, H)
            assert sz == cs
            assert band[0] <= x and x + sz <= band[2] + 1e-6
            assert band[1] <= y and y + sz <= band[3] + 1e-6
    for r in range(geom.WALL_N):
        for c in range(geom.WALL_N):
            x, y, sz = geom.wall_slot(r, c, W, H)
            assert wb[0] <= x and x + sz <= wb[2] + 1e-6
            assert wb[1] <= y and y + sz <= wb[3] + 1e-6
    prev = -1.0
    for i in range(geom.FLOOR_N):
        x, y, sz = geom.floor_slot(i, W, H)
        assert x > prev and x + sz <= fb[2] + 1e-6
        assert fb[1] <= y and y + sz <= fb[3] + 1e-6
        prev = x


def test_scaling_is_exactly_linear():
    W, H = geom.BOARD_W, geom.BOARD_H
    for fn, args in ((geom.nameplate, ()), (geom.row_band, (3,)),
                     (geom.wall_band, ()), (geom.floor_band, ())):
        a, b = fn(*args, W, H), fn(*args, 2 * W, 2 * H)
        assert b == tuple(2 * v for v in a)
    for args in ((0,), (2,), (4,)):
        a, b = geom.row_cell_size(*args, W, H), geom.row_cell_size(*args, 2 * W, 2 * H)
        assert b == (2 * a[0], 2 * a[1])
    a, b = geom.wall_cell_size(W, H), geom.wall_cell_size(2 * W, 2 * H)
    assert b == (2 * a[0], 2 * a[1])
    for args in ((0, 0), (2, 1), (4, 4)):
        a, b = geom.row_slot(*args, W, H), geom.row_slot(*args, 2 * W, 2 * H)
        assert b == tuple(2 * v for v in a)
    for args in ((0, 1), (4, 4)):
        a, b = geom.wall_slot(*args, W, H), geom.wall_slot(*args, 2 * W, 2 * H)
        assert b == tuple(2 * v for v in a)
    for i in range(geom.FLOOR_N):
        a, b = geom.floor_slot(i, W, H), geom.floor_slot(i, 2 * W, 2 * H)
        assert b == tuple(2 * v for v in a)
