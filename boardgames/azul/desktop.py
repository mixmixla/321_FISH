# -*- coding: utf-8 -*-
"""Azul 展示包桌面画师（spec §10 版面）。

深色桌面底 + 浅色玩家板：工厂盘/中央池（环形均布）+ 花纹行 + 5×5 墙 + 地板线 + 计分轨。

保持既有回退与 headless 契约：所有位图入口走 client_gameui 的 _asset_*（天然带
_real_cv 守卫，失败回退矢量画法）；本模块不新增任何 ImageTk.PhotoImage(master=cv)。
"""
import math

import client_gameui as _cu
from client_gameui import (
    THEME, _text, _rrect, _disc, _stone, _asset_at, _asset_nine_at, _FONT_F,
)
from boardgames import shell
from boardgames.azul import _art as _azul_art

# spec §7：把本包素材并入全局素材表（包优先），使 _asset_* 能解析 azul 新键。
# 必须替换为「副本」——client_gameui._BG_ASSETS 与 _art_boardgame.ASSETS 是同一对象，
# 就地 update 会污染共享素材表（tests/test_boardgame_assets.py 断言其恰为 29 键）。
if isinstance(_cu._BG_ASSETS, dict):
    _merged = dict(_cu._BG_ASSETS)
    _merged.update(getattr(_azul_art, "ASSETS", {}) or {})
    _cu._BG_ASSETS = _merged

COLORS = ["r", "w", "b", "y", "k"]                 # 引擎墙拉丁方用色序
ACOL = {"r": "#D2534F", "w": "#F0F0F0", "b": "#4A7DE0",
        "y": "#E0B33C", "k": "#3A3A3A"}            # 花砖实色（回退用）
_EMPTY = "#E5F3EE"                                 # 空槽浅底
_SLOT_BD = "#CBE0EA"                               # 槽描边


def _plate(cv, cx, cy, r):
    """亮色陶瓷盘：azul_plate 位图（失败回退 _disc）。"""
    if not _asset_at(cv, "azul_plate", cx - r, cy - r, int(r * 2)):
        _disc(cv, cx, cy, r, "#F7FAFC", outline="#2E4A63")


def _tiles(cv, cx, cy, r, items):
    """盘内花砖沿盘心小环均匀摆放（失败回退 _stone）。"""
    show = list(items[:8])
    m = len(show)
    if not m:
        return
    ts = max(6, int(min(r * 0.62, 22)))
    ring = r * 0.52
    for k, it in enumerate(show):
        c = it.get("c", "k") if isinstance(it, dict) else it
        a = -math.pi / 2 + k * 2 * math.pi / m
        px = cx + ring * math.cos(a)
        py = cy + ring * math.sin(a)
        if not _asset_at(cv, f"azul_tile_{c}", px - ts / 2, py - ts / 2, ts):
            _stone(cv, px, py, ts * 0.42, ACOL.get(c, "#888"))


def paint(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["azul"][1]
    title = "🧱 花砖物语·拼花"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 墙分最高"
    elif st.get("turn_uid") is not None:
        title += f"　第 {st.get('round', 1)} 轮 · 轮到 {nick(st['turn_uid'])}"

    # 1) 标题横幅  2) 深色桌面底
    shell.header(cv, w, title, accent)
    ui.update(game="azul")
    shell.table(cv, w, h)

    players = st.get("players") or []
    score = st.get("score") or {}
    top_h, base_y, avh, rw, wlx, wcell = shell.layout(w, h)

    # 8) 玩家面板：工厂带右上；宽不足时缩窄
    panel_w = min(190.0, max(120.0, w * 0.22))
    fac_right = w - panel_w - 20
    shell.player_panel(cv, w - panel_w - 8, shell.HEADER_H + 8, panel_w,
                       [(u, score.get(str(u), 0)) for u in players], me, nick)

    # 3/4) 工厂盘 + 中央池（环形均布，中央独立成盘）
    offers = st.get("offers") or []
    center = st.get("center") or []
    cx_f = max(90.0, fac_right / 2)
    cy_f = shell.HEADER_H + top_h / 2
    ring = max(34.0, min(top_h * 0.30, cx_f * 0.72, 96.0))
    pr = max(16.0, min(ring * 0.52, 34.0))
    n = len(offers)
    for i, bowl in enumerate(offers):
        a = -math.pi / 2 + i * 2 * math.pi / max(n, 1)
        px = cx_f + ring * math.cos(a)
        py = cy_f + ring * math.sin(a)
        _plate(cv, px, py, pr)
        _tiles(cv, px, py, pr, bowl)
    cr = max(18.0, min(ring * 0.52, 30.0))
    _plate(cv, cx_f, cy_f, cr)
    _tiles(cv, cx_f, cy_f, cr, center)

    # 5) 玩家板：花纹行 + 5×5 墙
    bx = 8
    floor_h = 20.0
    wall_gap = 6.0
    wall_h = max(40.0, avh - floor_h - wall_gap)
    wc = min(wcell, wall_h / 5)
    bw = (wlx + 5 * wc + 8) - bx
    if not _asset_nine_at(cv, "azul_boardface", bx, base_y, bw, avh, border=14):
        _rrect(cv, bx, base_y, bx + bw, base_y + avh, 14,
               fill="#EAF2F7", outline="#8FB6CE")

    rows = st.get("rows") or {}
    myr = rows.get(str(me), {}) or {}
    wall = st.get("wall") or {}
    myw = wall.get(str(me), {}) or {}
    top = base_y + wall_gap
    rh = wall_h / 5
    slot = max(10.0, min((wlx - bx - 30) / 5, rh * 0.62))
    for i in range(5):
        cyy = top + i * rh + rh / 2
        _text(cv, bx + 15, cyy, str(i + 1), "#7F98A8", (_FONT_F[0], 8))  # 行首容量
        row = myr.get(str(i), []) or []
        for j in range(i + 1):
            x = bx + 24 + j * slot
            y = cyy - slot / 2
            if j < len(row):
                c = row[j]
                if not _asset_at(cv, f"azul_tile_{c}", x + 1, y + 1, int(slot - 2)):
                    cv.create_rectangle(x, y, x + slot, y + slot,
                                        fill=ACOL.get(c, "#888"), outline=_SLOT_BD)
            else:
                _rrect(cv, x + 1, y + 1, x + slot - 1, y + slot - 1, 4,
                       fill=_EMPTY, outline=_SLOT_BD)

    inner = int(wc - 4)
    for r in range(5):
        for c in range(5):
            x0 = wlx + c * wc + 2
            y0 = top + r * rh + 2
            cell = myw.get(f"{r},{c}")
            if cell:
                if not _asset_at(cv, f"azul_tile_{cell}", x0, y0, inner):
                    cv.create_rectangle(x0, y0, x0 + inner, y0 + inner,
                                        fill=ACOL.get(cell, "#888"), outline=_SLOT_BD)
            else:
                exp = COLORS[(c - r) % 5]      # 该格应有的花色（引擎拉丁方）
                if not _asset_at(cv, f"azul_wall_cell_{exp}", x0, y0, inner):
                    cv.create_rectangle(x0, y0, x0 + inner, y0 + inner,
                                        fill=_EMPTY, outline=_SLOT_BD)

    # 6) 地板线 7 格
    fl = st.get("floor") or {}
    fcell = min((bw - 16) / 7, floor_h - 2)
    fy = base_y + avh - floor_h + 1
    for i in range(7):
        fx = bx + 8 + i * fcell
        if not _asset_at(cv, "azul_floor", fx + 1, fy + 1, int(fcell - 2)):
            cv.create_rectangle(fx + 1, fy + 1, fx + fcell - 1, fy + fcell - 1,
                                fill="#EDF3F7", outline="#8FB6CE")
    _text(cv, bx + 8 + 7 * fcell + 6, fy + fcell / 2,
          f"地板 {fl.get(str(me), 0)}", "#5F706A", (_FONT_F[0], 8), anchor="w")

    # 7) 计分轨：0..30 刻度（每 5 格加重）+ 各玩家棋子（自己 accent 高亮）
    track_x = bx + bw + 12
    track_w = min(96.0, w - 12 - track_x)
    if track_w >= 44:
        if not _asset_nine_at(cv, "azul_track", track_x, base_y, track_w, avh,
                              border=14):
            _rrect(cv, track_x, base_y, track_x + track_w, base_y + avh, 14,
                   fill="#24405A", outline="#101E2C")
        ty0 = base_y + 14
        ty1 = base_y + avh - 14
        for v in range(0, 31):
            ty = ty1 - (v / 30.0) * (ty1 - ty0)
            heavy = v % 5 == 0
            cv.create_line(track_x + 6, ty, track_x + (20 if heavy else 13), ty,
                           fill="#BBD3E6" if heavy else "#6E90AE",
                           width=2 if heavy else 1)
            if heavy:
                _text(cv, track_x + 24, ty, str(v), "#EAF2F7",
                      (_FONT_F[0], 7), anchor="w")
        for u in players:
            v = max(0, min(30, int(score.get(str(u), 0))))
            ty = ty1 - (v / 30.0) * (ty1 - ty0)
            px = track_x + track_w - 13
            _disc(cv, px, ty, 6, accent if u == me else "#C9D8E6",
                  outline="#0E1B28")
            if u == me:
                cv.create_oval(px - 8, ty - 8, px + 8, ty + 8,
                               outline="#FFD977", width=2)
