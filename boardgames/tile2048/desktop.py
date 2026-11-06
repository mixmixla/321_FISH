# -*- coding: utf-8 -*-
"""2048 桌面画师。

画师只负责把公开快照画成清晰的棋盘；方向按钮由宿主 GameWindow 的动作面板
接入 ``submit({"op": "move", "dir": direction})``，因此这里不重复绑定 Tk 事件。
"""
from __future__ import annotations


_BOARD_BG = "#14283A"
_CELL_BG = "#203A50"
_TEXT = "#F4F7FB"
_MUTED = "#AFC1D1"
_ACCENT = "#FFD166"
_TILES = {
    0: "#203A50", 2: "#F5E9D0", 4: "#F4D7A4", 8: "#F6B26B",
    16: "#F28C63", 32: "#ED705B", 64: "#E6534E", 128: "#E9C764",
    256: "#E2BD45", 512: "#D9B635", 1024: "#C99E32", 2048: "#B8862D",
}


def _tile_color(value):
    if value in _TILES:
        return _TILES[value]
    return "#9D6D35" if value > 2048 else _CELL_BG


def _text_color(value):
    return "#3D3022" if value in (2, 4) else _TEXT


def _font_size(value, cell):
    digits = len(str(value)) if value else 1
    scale = 0.30 if digits <= 2 else (0.25 if digits == 3 else 0.19)
    return max(10, int(cell * scale))


def paint(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    """Render the 4×4 board into the existing GameWindow canvas."""
    state = st or {}
    board = state.get("board") or []
    board = [list(row[:4]) + [0] * max(0, 4 - len(row)) for row in board[:4]]
    board += [[0] * 4 for _ in range(4 - len(board))]

    ui["game"] = "tile2048"
    # Keep this rectangle generous enough for the dark canvas and readable at the
    # compact GameWindow size; the host already clears the canvas before calling us.
    cv.create_rectangle(0, 0, w, h, fill="#0B1B2A", outline="")
    cv.create_text(18, 22, text="2048 · 方块合成", anchor="w", fill=_TEXT,
                   font=("Segoe UI", max(13, min(20, int(w / 26))), "bold"))
    cv.create_text(18, 45, text="单人挑战 · 每次有效滑动生成一块新砖", anchor="w",
                   fill=_MUTED, font=("Segoe UI", max(8, min(10, int(w / 42)))))

    score = int(state.get("score") or 0)
    cv.create_rectangle(max(0, w - 128), 11, max(0, w - 18), 48,
                        fill="#1E3B52", outline="#4F7591", width=1)
    cv.create_text(w - 73, 20, text="分数", fill=_MUTED,
                   font=("Segoe UI", 8, "bold"))
    cv.create_text(w - 73, 36, text=str(score), fill=_ACCENT,
                   font=("Segoe UI", 13, "bold"))

    side = max(128, min(float(w - 34), float(h - 104)))
    x0 = (float(w) - side) / 2.0
    y0 = 61.0 + max(0.0, (float(h) - 104.0 - side) / 2.0)
    ui["tile2048_board"] = (x0, y0, x0 + side, y0 + side)
    gap = max(4.0, side * 0.024)
    cell = (side - gap * 5.0) / 4.0
    cv.create_rectangle(x0, y0, x0 + side, y0 + side,
                        fill=_BOARD_BG, outline="#456A84", width=2)
    for row in range(4):
        for col in range(4):
            value = int(board[row][col] or 0)
            left = x0 + gap + col * (cell + gap)
            top = y0 + gap + row * (cell + gap)
            right, bottom = left + cell, top + cell
            cv.create_rectangle(left, top, right, bottom,
                                fill=_tile_color(value), outline="")
            if value:
                cv.create_text((left + right) / 2.0, (top + bottom) / 2.0,
                               text=str(value), fill=_text_color(value),
                               font=("Segoe UI", _font_size(value, cell), "bold"))

    status = state.get("status", "playing")
    if status == "won":
        message, color = "🏆 达成 2048！", "#2D7A64"
    elif status == "lost":
        message, color = "💥 无路可走", "#8B4F52"
    else:
        message, color = "使用下方方向按钮继续", "#1E3B52"
    banner_y = y0 + side + 12
    cv.create_rectangle(x0, banner_y, x0 + side, min(h - 5, banner_y + 26),
                        fill=color, outline="")
    cv.create_text(x0 + side / 2.0, banner_y + 13, text=message,
                   fill="#FFFFFF", font=("Segoe UI", 10, "bold"))
