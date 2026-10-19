# -*- coding: utf-8 -*-
"""桌游对局共用外壳：深色桌面底、标题·轮次横幅、信息条、工厂盘、玩家板、计分环。

循环导入约定：client_gameui 在 import 期不 import boardgames（只在 render() 内延迟
import）；本模块在 import 期 import client_gameui，故方向单一、无环。

组件一律**不含游戏规则语义**：素材键由调用方通过 keys 参数传入，故本模块源码内
不出现任何具体游戏的素材键名（由 tests/test_shell_components.py 锁住）。
"""
import math

from client_gameui import (
    _text, _rrect, _turn_banner, _asset_bg, _asset_at, _disc, _stone,
    _FONT_F, _UXC, _TXT, _PANEL_BD, _UXR_BIG,
)
from boardgames import geom

TABLE_BG = "#16232E"
HEADER_H = 46
INFO_H = 30
SLOT_BG = "#E4D9C3"
SLOT_BD = "#CDBE9C"
NAME_FG = "#2B3A46"
ROW_FG = "#9AA6B0"


def _key(keys, role, color=None):
    """把调用方的 keys 解析成素材键：str 直用 / dict（值可含 {c}）/ callable。

    任何异常或缺键都返回 None（调用方据此走矢量回退），绝不抛。
    """
    if keys is None:
        return None
    try:
        if isinstance(keys, str):
            return keys.format(c=color) if (color is not None and "{c}" in keys) else keys
        if callable(keys):
            return keys(role, color) if color is not None else keys(role)
        tpl = keys.get(role)
        if tpl is None:
            return None
        if color is not None and isinstance(tpl, str) and "{c}" in tpl:
            return tpl.format(c=color)
        return tpl
    except Exception:
        return None


def table(cv, w, h, y0=HEADER_H, *, bg_key=None):
    """铺桌面底：给了 bg_key 就平铺该位图（无缝素材），否则回退纯色 TABLE_BG。"""
    if bg_key and _asset_bg(cv, bg_key, 0, y0, w, h):
        return
    cv.create_rectangle(0, y0, w, h, fill=TABLE_BG, outline="")


def header(cv, w, title, accent, h=HEADER_H):
    _turn_banner(cv, w, h, title, accent)


def layout(w, h, y0=HEADER_H, n_players=2, info_h=INFO_H):
    """分区几何：信息条 / 左（工厂列 + 中央池）/ 中（玩家板行）/ 右（计分环）。

    返回 dict：info/left/center/right 为矩形，cell/cols/rows 为玩家板格尺寸与排布；
    另保留 legacy 标量 top_h/base_y/avh/rw/wlx/wcell：返回的是 dict，无法按旧
    元组解包，保留它们只为保持返回形状稳定，当前没有任何调用点消费这些键。
    """
    info = (0.0, float(y0), float(w), float(y0 + info_h))
    by0 = float(y0 + info_h)
    bh = max(1.0, h - by0)
    left_w, right_w = w * 0.26, w * 0.22
    cx0 = left_w
    cx1 = max(left_w + 1.0, w - right_w)
    left = (0.0, by0, left_w, by0 + bh)
    center = (cx0, by0, cx1, by0 + bh)
    right = (cx1, by0, float(w), by0 + bh)
    n = max(1, int(n_players))
    cols = n if n <= 3 else 3
    rows = (n + cols - 1) // cols
    cell = ((center[2] - center[0]) / cols, bh / rows)
    top_h = (h - y0) * 0.40
    base_y = y0 + top_h + 8
    avh = max(60, h - base_y - 20)
    rw = w * 0.30
    wlx = w * 0.36
    wcell = min(avh / 5, max(18, (w - wlx - 24) / 5))
    return {"info": info, "left": left, "center": center, "right": right,
            "cell": cell, "cols": cols, "rows": rows,
            "top_h": top_h, "base_y": base_y, "avh": avh,
            "rw": rw, "wlx": wlx, "wcell": wcell}


def info_bar(cv, w, y, h, round_no, turn_nick, bag, scores, me, *,
             bg_key=None, chip_key=None):
    """顶部信息条：轮次 / 回合 / 袋剩 + 各玩家分数（可带筹码位图，自己高亮）。"""
    if not (bg_key and _asset_bg(cv, bg_key, 0, y, w, y + h)):
        cv.create_rectangle(0, y, w, y + h, fill=TABLE_BG, outline="")
        cv.create_line(0, y + h, w, y + h, fill=_PANEL_BD)
    _text(cv, 8, y + h / 2.0,
          f"第 {round_no} 轮 · 回合 → {turn_nick}　🧱 袋剩 {bag}",
          "#EAF2F7", (_FONT_F[0], 9), anchor="w")
    x = float(w) - 8.0
    for uid, sc in reversed(list((scores or {}).items())):
        cs = h * 0.62
        if chip_key and _asset_at(cv, chip_key, x - cs, y + (h - cs) / 2.0, int(cs)):
            _text(cv, x - cs / 2.0, y + h / 2.0, str(sc), "#2B3A46", (_FONT_F[0], 9))
        else:
            _text(cv, x, y + h / 2.0, str(sc),
                  _UXC["accent"] if str(uid) == str(me) else "#EAF2F7", (_FONT_F[0], 9),
                  anchor="e")
        x -= h * 1.05


def factory_disc(cv, cx, cy, r, tiles, *, plate_key=None, tile_key=None,
                 center=False, colors=None):
    """工厂盘 / 中央池：盘位图（回退矢量瓷盘）+ 盘内花砖环形均布。"""
    items = list(tiles or [])[:10]
    if not (plate_key and _asset_at(cv, plate_key, cx - r, cy - r, int(r * 2))):
        _disc(cv, cx, cy, r, "#FFF6D8" if center else "#F7FAFC",
              outline="#2E4A63")
    m = len(items)
    if not m:
        return
    ts = max(6.0, min(r * 0.62, 22.0))
    ring = r * 0.52
    pal = colors or {}
    for k, it in enumerate(items):
        c = it.get("c", "k") if isinstance(it, dict) else it
        a = -math.pi / 2 + k * 2 * math.pi / m
        px, py = cx + ring * math.cos(a), cy + ring * math.sin(a)
        key = _key(tile_key, "tile", c)
        if key and _asset_at(cv, key, px - ts / 2.0, py - ts / 2.0, int(ts)):
            continue
        _stone(cv, px, py, ts * 0.42, pal.get(c, "#888"))


def _row_items(rows, i):
    """花纹行取第 i 行（兼容 dict 的 str 键与 int 键）。"""
    if not rows or not hasattr(rows, "get"):
        return []
    return list(rows.get(str(i)) or rows.get(i) or [])


def board_panel(cv, x, y, w, h, name, rows, wall, floor, score, keys, *,
                wall_expected=None, active=False, compact=False, note=None):
    """按 4:3 内接 + geom 缩放画一整块玩家板：铭牌 + 花纹行 + 5×5 墙 + 地板线 + 分数。

    keys：角色→键名（board / tile（含 {c}）/ wall_cell（含 {c}）/ floor / chip /
    color（色键→十六进制，供矢量回退））；缺键或缺位图时逐项矢量回退。
    wall_expected(r, c)：空格应显的目标色键（由调用方给，shell 不掺入拉丁方规则）。
    compact=True 时略去花纹行号文字（窄板）；note 为可选角标（如「地板 N」）。
    返回板面几何 `{"bx","by","bw","bh"}`（4:3 内接后的实际矩形，居中内缩后的原点），
    供调用方按 geom.row_band/floor_band 反算热区（画与命中同源，不重复缩放公式）。
    """
    pal = _key(keys, "color") or {}
    bw = min(w, h * geom.BOARD_W / float(geom.BOARD_H))
    bh = bw * geom.BOARD_H / float(geom.BOARD_W)
    bx, by = x + (w - bw) / 2.0, y + (h - bh) / 2.0
    bkey = _key(keys, "board")
    if not (bkey and _asset_at(cv, bkey, bx, by, (bw, bh))):
        _rrect(cv, bx, by, bx + bw, by + bh, bw * 0.05, fill="#F6F1E7",
               outline=SLOT_BD)
    if active:
        _rrect(cv, bx - 2, by - 2, bx + bw + 2, by + bh + 2, bw * 0.06,
               fill="", outline=_UXC["accent"], width=2)
    np_ = geom.nameplate(bw, bh)
    _text(cv, bx + np_[0] + bw * 0.02, by + (np_[1] + np_[3]) / 2.0, str(name),
          NAME_FG, (_FONT_F[0], 9), anchor="w")
    if note:
        _text(cv, bx + bw * 0.5, by + bh * 0.972, str(note),
              ROW_FG, (_FONT_F[0], 8))
    for i in range(geom.ROWS_N):
        band = geom.row_band(i, bw, bh)
        if not compact:
            _text(cv, bx + bw * 0.03, by + (band[1] + band[3]) / 2.0, str(i + 1),
                  ROW_FG, (_FONT_F[0], 8))
        row = _row_items(rows, i)
        for j in range(i + 1):
            sx, sy, cs = geom.row_slot(i, j, bw, bh)
            px, py = bx + sx, by + sy
            c = row[j] if j < len(row) else None
            tkey = _key(keys, "tile", c) if c else None
            if c and tkey and _asset_at(cv, tkey, px, py, max(4, int(cs))):
                continue
            _rrect(cv, px + 1, py + 1, px + cs - 1, py + cs - 1, cs * 0.18,
                   fill=pal.get(c, "#888") if c else SLOT_BG, outline=SLOT_BD)
    for r in range(geom.WALL_N):
        for c in range(geom.WALL_N):
            sx, sy, cs = geom.wall_slot(r, c, bw, bh)
            px, py = bx + sx, by + sy
            v = (wall.get(f"{r},{c}") or wall.get((r, c))) if wall else None
            if v:
                tkey = _key(keys, "tile", v)
                if tkey and _asset_at(cv, tkey, px, py, max(4, int(cs))):
                    continue
                fill = pal.get(v, "#888")
            else:
                exp = wall_expected(r, c) if wall_expected else None
                wkey = _key(keys, "wall_cell", exp)
                if wkey and _asset_at(cv, wkey, px, py, max(4, int(cs))):
                    continue
                fill = SLOT_BG
            _rrect(cv, px, py, px + cs, py + cs, cs * 0.16, fill=fill,
                   outline=SLOT_BD)
    flist = list(floor or [])
    for i in range(geom.FLOOR_N):
        sx, sy, cs = geom.floor_slot(i, bw, bh)
        px, py = bx + sx, by + sy
        c = flist[i] if i < len(flist) else None
        tkey = _key(keys, "tile", c) if c else None
        if c and tkey and _asset_at(cv, tkey, px, py, max(4, int(cs))):
            continue
        fkey = _key(keys, "floor")
        if fkey and _asset_at(cv, fkey, px, py, max(4, int(cs))):
            continue
        _rrect(cv, px + 1, py + 1, px + cs - 1, py + cs - 1, cs * 0.16,
               fill=pal.get(c, SLOT_BG) if c else SLOT_BG, outline=SLOT_BD)
    cs2 = min(bh * 0.18, bw * 0.14)
    sx_ = bx + bw - cs2 - 4.0
    sy_ = by + np_[1] + np_[3] / 2.0 - cs2 / 2.0
    ckey = _key(keys, "chip")
    if not (ckey and _asset_at(cv, ckey, sx_, sy_, max(6, int(cs2)))):
        _rrect(cv, sx_, sy_, sx_ + cs2, sy_ + cs2, cs2 * 0.5, fill="#E3CF9A",
               outline="#C9A227")
    _text(cv, sx_ + cs2 / 2.0, sy_ + cs2 / 2.0, str(score), "#2B3A46",
          (_FONT_F[0], 9))
    return {"bx": bx, "by": by, "bw": bw, "bh": bh}


def score_ring(cv, cx, cy, r, scores, me, markers=None, *, ring_key=None,
               marker_key=None, steps=30, colors=None):
    """圆形计分轨：ring_key 位图打底（回退矢量厚边圆）+ 各玩家棋子按分数落位。"""
    if not (ring_key and _asset_at(cv, ring_key, cx - r, cy - r, int(r * 2))):
        _disc(cv, cx, cy, r, "#24405A", outline="#101E2C")
    pal = colors or {}
    mk = markers or {}
    for uid, v in list((scores or {}).items()):
        vv = max(0, min(int(steps), int(v or 0)))
        a = -math.pi / 2 + (vv / float(steps)) * 2 * math.pi
        px, py = cx + r * 0.72 * math.cos(a), cy + r * 0.72 * math.sin(a)
        c = mk.get(uid) or mk.get(str(uid))
        ms = max(10.0, r * 0.22)
        key = _key(marker_key, "marker", c)
        if not (key and _asset_at(cv, key, px - ms / 2.0, py - ms / 2.0, int(ms))):
            _disc(cv, px, py, ms / 2.0, pal.get(c, "#C9D8E6"), outline="#0E1B28")
        if str(uid) == str(me):
            cv.create_oval(px - ms * 0.7, py - ms * 0.7, px + ms * 0.7,
                           py + ms * 0.7, outline="#FFD977", width=2)


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
