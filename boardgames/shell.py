# -*- coding: utf-8 -*-
"""桌游对局共用外壳：深色桌面底、标题·轮次横幅、玩家面板、栅格。

循环导入约定：client_gameui 在 import 期不 import boardgames（只在 render() 内
延迟 import）；本模块在 import 期 import client_gameui，故方向单一、无环。
"""
from client_gameui import (
    _text, _rrect, _turn_banner, _asset_bg,
    _FONT_B, _FONT_F, _UXC, _TXT, _WHITE, _PANEL_BD, _UXR_BIG,
)

TABLE_BG = "#16232E"
HEADER_H = 46


def table(cv, w, h, y0=HEADER_H):
    """铺深色桌面底：有 azul_table 素材则平铺，否则纯色回退。"""
    if not _asset_bg(cv, "azul_table", 0, y0, w, h):
        cv.create_rectangle(0, y0, w, h, fill=TABLE_BG, outline="")


def header(cv, w, title, accent, h=HEADER_H):
    _turn_banner(cv, w, h, title, accent)


def layout(w, h, y0=HEADER_H):
    """返回 (top_h, base_y, avh, rw, wlx, wcell)：工厂区高度 / 玩家板起点与可用高 /
    花纹列宽 / 墙起点 x / 墙格边长。窄窗时优先保住「花纹行 + 墙」。"""
    top_h = (h - y0) * 0.40
    base_y = y0 + top_h + 8
    avh = max(60, h - base_y - 20)
    rw = w * 0.30
    wlx = w * 0.36
    wcell = min(avh / 5, max(18, (w - wlx - 24) / 5))
    return top_h, base_y, avh, rw, wlx, wcell


def player_panel(cv, x, y, w, rows, me, nick):
    """BGA 式玩家面板：每行「色块 + 昵称 + 分数」，当前自己高亮。"""
    hh = 20
    _rrect(cv, x, y, x + w, y + hh * len(rows) + 10, _UXR_BIG,
           _UXC["surface"], _PANEL_BD)
    for i, (uid, score) in enumerate(rows):
        yy = y + 5 + i * hh + hh / 2
        cv.create_oval(x + 8, yy - 4, x + 16, yy + 4,
                       fill=_UXC["accent"] if uid == me else _UXC["border"], outline="")
        _text(cv, x + 22, yy, str(nick(uid)), _TXT, (_FONT_F[0], 9), anchor="w")
        _text(cv, x + w - 8, yy, str(score), _UXC["text_secondary"],
              (_FONT_F[0], 9), anchor="e")
