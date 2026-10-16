# -*- coding: utf-8 -*-
"""玩家板归一化内几何：素材**预印凹槽**与画师**落子**共用同一坐标真源。

- 模块零 import（纯数值），headless 可测。
- 板内参考几何以 BOARD_W × BOARD_H 为单位；返回值为调用方给定的 (w, h) 像素坐标。
- 所有公式**一次齐次**（只乘系数、只取 min，不加减像素常数）⇒ 等比缩放浮点精确。
- 越界索引 / 非正尺寸一律返回 None，绝不抛异常。
"""
from __future__ import annotations

BOARD_W = 384
BOARD_H = 288
ROWS_N = 5
WALL_N = 5
FLOOR_N = 7

_NP = (10.0, 10.0, 158.0, 36.0)      # 铭牌
_ROWS = (12.0, 46.0, 178.0, 234.0)   # 花纹行带（左侧列）
_WALL = (188.0, 46.0, 374.0, 234.0)  # 5×5 墙带（右侧列）
_FLOOR = (12.0, 242.0, 374.0, 276.0) # 地板带（底部横条）

_ROW_W_F, _ROW_S_F, _ROW_STEP_F = 0.84, 0.86, 1.08
_WALL_S_F, _FLOOR_S_F = 0.86, 0.88


def _ok(w, h):
    return w > 0 and h > 0


def _rect(t, w, h):
    return (t[0] / BOARD_W * w, t[1] / BOARD_H * h,
            t[2] / BOARD_W * w, t[3] / BOARD_H * h)


def nameplate(w, h):
    """铭牌矩形（昵称位）。"""
    return _rect(_NP, w, h) if _ok(w, h) else None


def row_band(i, w, h):
    """第 i 花纹行的条带矩形（i: 0..4）。"""
    if not _ok(w, h) or not 0 <= i < ROWS_N:
        return None
    x0, y0, x1, y1 = _rect(_ROWS, w, h)
    pitch = (y1 - y0) / ROWS_N
    return (x0, y0 + i * pitch, x1, y0 + (i + 1) * pitch)


def row_cell_size(i, w, h):
    """第 i 行单格边长（正方形）。"""
    if not _ok(w, h) or not 0 <= i < ROWS_N:
        return None
    x0, y0, x1, y1 = _rect(_ROWS, w, h)
    s = min((x1 - x0) * _ROW_W_F / (i + 1), (y1 - y0) / ROWS_N * _ROW_S_F)
    return (s, s)


def row_slot(i, j, w, h):
    """第 i 行第 j 格的 (x, y, 边长)（j ∈ [0, i]，超出即 None）。"""
    if not _ok(w, h) or not 0 <= i < ROWS_N or not 0 <= j <= i:
        return None
    x0, y0, x1, y1 = _rect(_ROWS, w, h)
    n = i + 1
    s = row_cell_size(i, w, h)[0]
    step = s * _ROW_STEP_F
    off = ((x1 - x0) - (step * n - (step - s))) / 2.0     # 整行居中
    pitch = (y1 - y0) / ROWS_N
    return (x0 + off + j * step, y0 + i * pitch + (pitch - s) / 2.0, s)


def wall_band(w, h):
    """5×5 墙带矩形。"""
    return _rect(_WALL, w, h) if _ok(w, h) else None


def wall_cell_size(w, h):
    """墙格边长（正方形，取两向 pitch 较小者）。"""
    if not _ok(w, h):
        return None
    x0, y0, x1, y1 = _rect(_WALL, w, h)
    s = min((x1 - x0) / WALL_N, (y1 - y0) / WALL_N) * _WALL_S_F
    return (s, s)


def wall_slot(r, c, w, h):
    """第 r 行第 c 列墙格的 (x, y, 边长)。"""
    if not _ok(w, h) or not 0 <= r < WALL_N or not 0 <= c < WALL_N:
        return None
    x0, y0, x1, y1 = _rect(_WALL, w, h)
    s = wall_cell_size(w, h)[0]
    px, py = (x1 - x0) / WALL_N, (y1 - y0) / WALL_N
    return (x0 + c * px + (px - s) / 2.0, y0 + r * py + (py - s) / 2.0, s)


def floor_band(w, h):
    """地板线横条矩形。"""
    return _rect(_FLOOR, w, h) if _ok(w, h) else None


def floor_slot(i, w, h):
    """地板第 i 格（i: 0..6）的 (x, y, 边长)。"""
    if not _ok(w, h) or not 0 <= i < FLOOR_N:
        return None
    x0, y0, x1, y1 = _rect(_FLOOR, w, h)
    step = (x1 - x0) / FLOOR_N
    s = min(step, y1 - y0) * _FLOOR_S_F
    return (x0 + i * step + (step - s) / 2.0, y0 + (y1 - y0 - s) / 2.0, s)
