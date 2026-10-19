# -*- coding: utf-8 -*-
"""Azul 展示包桌面画师（spec §7 BGA 版面）。

信息条 / 左列工厂盘（竖排网格）+ 列底中央池 / 中部自己一块大板 + 对手缩略小板
/ 右侧圆形计分轨 + 分数清单。

- 所有位图入口走 `boardgames.shell` 的组件（其内部再走 client_gameui 的
  `_asset_*`，失败逐项矢量回退）；本模块不新增任何 `ImageTk.PhotoImage(master=cv)`。
- 素材键一律经 `KEYS` / 关键字参数外置，`boardgames/shell.py` 源码内不出现 `azul_`。
- 拖拽取砖：本模块把取砖热区写进 `ui["azul_src"]`、落砖热区写进 `ui["azul_dst"]`，
  合法落点写进 `ui["azul_ok"]`（画与命中同源）；点击分发见 client_gameui，
  动作仍走既有 take / place / floor 契约，不开新通路。
"""
import math

from client_gameui import THEME, _text, _FONT_F
from boardgames import geom, shell

COLORS = ["r", "w", "b", "y", "k"]                 # 引擎墙拉丁方用色序
ACOL = {"r": "#D2534F", "w": "#F0F0F0", "b": "#4A7DE0",
        "y": "#E0B33C", "k": "#3A3A3A"}            # 花砖实色（矢量回退用）
_MARKERS = "rwbyk"                                 # 计分棋子色序（按玩家序号轮转）
KEYS = {                                           # 角色 → Azul 素材键（含 {c} 模板）
    "board": "azul_board",
    "tile": "azul_tile_{c}",
    "wall_cell": "azul_wall_cell_{c}",
    "floor": "azul_floor",
    "chip": "azul_chip",
    "color": ACOL,
}


def _wall_target(r, c):
    """墙格 (r, c) 应落的花色：引擎拉丁方 `_wall_col(ci, row) = (ci + row) % 5`。"""
    return COLORS[(c - r) % 5]


def _marker_map(players):
    """uid → 计分棋子色键（按座位顺序轮转 rwbyk；双端同源，桌面与网页一致）。

    键用 `str(uid)`：引擎 status 的 `score` 即为 `{str(uid): ...}`，shell.score_ring
    也按 `score` 的同一键集查表（`mk.get(uid) or mk.get(str(uid))`）。
    """
    return {str(u): _MARKERS[i % len(_MARKERS)] for i, u in enumerate(players or [])}


def _tile_color(it):
    """盘内一片砖的色键（引擎快照给 {"c","n"}，旧格式可能直接是色键字符串）。"""
    return it.get("c", "k") if isinstance(it, dict) else it


def _ring_pos(cx, cy, r, m, k):
    """盘内第 k / m 片砖的 (x, y, 边长, 极角)——与 shell.factory_disc 同一公式。"""
    ts = max(6.0, min(r * 0.62, 22.0))
    a = -math.pi / 2 + k * 2 * math.pi / max(1, m)
    return cx + r * 0.52 * math.cos(a), cy + r * 0.52 * math.sin(a), ts, a


def _ring_hits(cx, cy, r, items, src):
    """取砖热区：盘内每片砖一个方形区（画砖位置反算，多砖同色即同源）。"""
    m = len(items)
    out = []
    for k, it in enumerate(items):
        px, py, ts, _a = _ring_pos(cx, cy, r, m, k)
        h = max(8.0, ts * 0.6)
        out.append((px - h, py - h, px + h, py + h, src, _tile_color(it)))
    return out


def _pile(tiles):
    """中央池按色归堆：同色合并计数（引擎中央池是散砖，Azul 实为各色砖堆）。

    归堆后盘内至多 5 片（每色一片），色数不再受 factory_disc 的 10 片上限截断，
    保证任意色都能被拖到；计数以角标呈现。
    """
    n = {}
    for it in tiles or []:
        c = _tile_color(it)
        n[c] = n.get(c, 0) + 1
    return [{"c": c, "n": n[c]} for c in COLORS if n.get(c)]


def _dst_hits(g):
    """本方板落砖热区：5 条花纹行（row 0~4）+ 地板线（row -1）；无我方板 → []。"""
    if not g:
        return []
    bx, by, bw, bh = g["bx"], g["by"], g["bw"], g["bh"]
    out = []
    for i in range(geom.ROWS_N):
        band = geom.row_band(i, bw, bh)
        if band:
            x0, y0, x1, y1 = band
            out.append((bx + x0, by + y0, bx + x1, by + y1, i))
    fb = geom.floor_band(bw, bh)
    if fb:
        x0, y0, x1, y1 = fb
        out.append((bx + x0, by + y0, bx + x1, by + y1, -1))
    return out


def _row_ok(rows, wall, r, col):
    """第 r 行能否收下此色砖：行内同色（或空）且该色在墙上的落格未被占用。"""
    row = rows.get(str(r)) or rows.get(r) or []
    if row and row[0] != col:
        return False
    try:
        ci = COLORS.index(col)
    except ValueError:
        return False
    return wall.get(f"{r},{(ci + r) % 5}") in (None, "")


def _paint_drag(cv, ui, src_hits, dst_hits, rows_st, wall_st, me):
    """拖拽反馈：源砖金框 + 可落行虚线框 + 悬停留点着色 + 随指针的幽灵砖。

    `_azul_drag` 由 client_gameui 在按下/移动时维护（本模块只读），gx/gy 回写供
    拖动中 cv.move("azul_ghost", ...) 平移幽灵，避免每次都整屏重绘。
    """
    d = ui.get("_azul_drag")
    if not d:
        return
    col = d.get("col")
    if col not in ACOL:
        return
    for (x0, y0, x1, y1, src, c) in src_hits:
        if src == d.get("src") and c == col:
            cv.create_rectangle(x0, y0, x1, y1, outline="#FFD977", width=2)
    rows = (rows_st or {}).get(str(me)) or {}
    wall = (wall_st or {}).get(str(me)) or {}
    ok = [row for _x0, _y0, _x1, _y1, row in dst_hits
          if row < 0 or _row_ok(rows, wall, row, col)]
    ui["azul_ok"] = ok
    sel = d.get("row")
    for (x0, y0, x1, y1, row) in dst_hits:
        if row in ok:
            cv.create_rectangle(x0, y0, x1, y1, outline=THEME["azul"][1],
                                dash=(4, 3), width=1)
        if row == sel:
            cv.create_rectangle(x0, y0, x1, y1, fill=ACOL[col],
                               stipple="gray25", outline="")
    gx, gy = d.get("x"), d.get("y")
    if gx is None:
        return
    cv.create_oval(gx - 13.0, gy - 13.0, gx + 13.0, gy + 13.0, fill=ACOL[col],
                   outline="#FFFFFF", width=2, tags="azul_ghost")
    d["gx"], d["gy"] = gx, gy


def _paint_boards(cv, lay, players, me, rows_st, wall_st, fl_st, score, nick):
    """中部玩家板区：自己一块大板（active + 地板计数）+ 对手缩略小板。

    `me` 不在 `players` 里（旁观）时退化为 `layout` 的均匀网格，不做高亮。
    返回自己大板的几何（`shell.board_panel` 的返回值），供落砖热区反算；无我方板 → None。
    """
    cx0, cy0, cx1, cy1 = lay["center"]
    cw_all, ch_all = cx1 - cx0, cy1 - cy0
    if players and me in players:
        me_w = min(cw_all * 0.55, ch_all * geom.BOARD_W / float(geom.BOARD_H))
        others = [u for u in players if u != me]
        o_x0 = cx0 + me_w + 8.0
        o_w = max(1.0, cx1 - o_x0)
        ocols = 2 if o_w >= 380.0 else 1
        orows = max(1, (len(others) + ocols - 1) // ocols)
        o_cw, o_ch = o_w / ocols, ch_all / orows
        compact = o_cw < 190.0
        mine = shell.board_panel(cv, cx0, cy0, me_w, ch_all, nick(me),
                                 rows_st.get(str(me), {}), wall_st.get(str(me), {}),
                                 [], score.get(str(me), 0), KEYS,
                                 wall_expected=_wall_target, active=True,
                                 note=f"地板 {int(fl_st.get(str(me), 0))}")
        for i, u in enumerate(others):
            c, r = i % ocols, i // ocols
            shell.board_panel(cv, o_x0 + c * o_cw, cy0 + r * o_ch, o_cw, o_ch,
                              nick(u), rows_st.get(str(u), {}),
                              wall_st.get(str(u), {}), [], score.get(str(u), 0),
                              KEYS, wall_expected=_wall_target, compact=compact)
        return mine
    cols, rows = lay["cols"], lay["rows"]
    cell_w, cell_h = lay["cell"]
    compact = cell_w < 190.0
    for i, u in enumerate(players):
        c, r = i % cols, i // cols
        shell.board_panel(cv, cx0 + c * cell_w, cy0 + r * cell_h, cell_w, cell_h,
                          nick(u), rows_st.get(str(u), {}), wall_st.get(str(u), {}),
                          [], score.get(str(u), 0), KEYS,
                          wall_expected=_wall_target, compact=compact)
    return None


def paint(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["azul"][1]
    title = "🧱 花砖物语·拼花"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 墙分最高"
    elif st.get("turn_uid") is not None:
        title += f"　第 {st.get('round', 1)} 轮 · 轮到 {nick(st['turn_uid'])}"

    shell.header(cv, w, title, accent)
    ui.update(game="azul")

    players = st.get("players") or []
    score = st.get("score") or {}
    rows_st = st.get("rows") or {}
    wall_st = st.get("wall") or {}
    fl_st = st.get("floor") or {}
    offers = st.get("offers") or []
    center = st.get("center") or []
    turn_uid = st.get("turn_uid")

    # 1) 桌面底（无缝瓷砖墙，失败回退纯色）+ 分区几何
    shell.table(cv, w, h, bg_key="azul_wall_bg")
    lay = shell.layout(w, h, n_players=len(players))

    # 2) 信息条：第 N 轮 · 轮到谁 · 袋剩 + 各玩家分数筹码
    shell.info_bar(cv, w, lay["info"][1], shell.INFO_H, st.get("round", 1),
                   nick(turn_uid) if turn_uid is not None else "—",
                   st.get("bag", 0), score, me,
                   bg_key="azul_wall_bg", chip_key="azul_chip")

    # 3) 左列：工厂盘竖排网格（≤3 个单列，否则双列）+ 列底中央池
    lx0, ly0, lx1, ly1 = lay["left"]
    lh = ly1 - ly0
    pool_zone = lh * 0.30
    grid_h = max(1.0, lh - pool_zone)
    n_f = len(offers)
    fcols = 1 if n_f <= 3 else 2
    frows = max(1, (n_f + fcols - 1) // fcols)
    fcw, fch = (lx1 - lx0) / fcols, grid_h / frows
    fr = max(10.0, min(fcw, fch) * 0.42)
    _text(cv, lx0 + 6.0, ly0 + 8.0, "工厂盘", "#EAF2F7", (_FONT_F[0], 8), anchor="w")
    src_hits = []
    for i, bowl in enumerate(offers):
        c, r = i % fcols, i // fcols
        fcx = lx0 + fcw * (c + 0.5)
        fcy = ly0 + fch * (r + 0.5) + 8.0
        shell.factory_disc(cv, fcx, fcy, fr, bowl, plate_key="azul_plate",
                           tile_key="azul_tile_{c}", colors=ACOL)
        src_hits += _ring_hits(fcx, fcy, fr, bowl, i)
    pr = max(10.0, min((lx1 - lx0) * 0.42, pool_zone * 0.36))
    pcx = (lx0 + lx1) / 2.0
    pcy = ly0 + grid_h + pool_zone / 2.0
    _text(cv, pcx, pcy - pr - 7.0, "中央池", "#EAF2F7", (_FONT_F[0], 8))
    pile = _pile(center)                      # 按色归堆 → 任意色都可被抓（见 _pile）
    shell.factory_disc(cv, pcx, pcy, pr, pile, plate_key="azul_plate_center",
                       tile_key="azul_tile_{c}", center=True, colors=ACOL)
    for k, it in enumerate(pile):
        _px, _py, _ts, a = _ring_pos(pcx, pcy, pr, len(pile), k)
        _text(cv, pcx + pr * 0.88 * math.cos(a), pcy + pr * 0.88 * math.sin(a),
              f"×{it['n']}", "#EAF2F7", (_FONT_F[0], 8))
    src_hits += _ring_hits(pcx, pcy, pr, pile, "center")
    ui["azul_src"] = src_hits

    # 4) 中部：所有玩家板（自己大板高亮 + 对手缩略）
    mine = _paint_boards(cv, lay, players, me, rows_st, wall_st, fl_st, score, nick)
    dst_hits = _dst_hits(mine)
    ui["azul_dst"] = dst_hits
    ui.pop("azul_ok", None)
    _paint_drag(cv, ui, src_hits, dst_hits, rows_st, wall_st, me)

    # 5) 右侧：圆形计分轨（31 刻度）+ 分数清单（沿用既有 player_panel）
    rx0, ry0, rx1, ry1 = lay["right"]
    rwide = rx1 - rx0
    rr = max(24.0, min(rwide * 0.42, (ry1 - ry0) * 0.36))
    ccx, ccy = (rx0 + rx1) / 2.0, ry0 + 18.0 + rr
    _text(cv, ccx, ry0 + 8.0, "计分轨（0–30）", "#EAF2F7", (_FONT_F[0], 8))
    shell.score_ring(cv, ccx, ccy, rr, score, me, _marker_map(players),
                     ring_key="azul_track_ring", marker_key="azul_marker_{c}",
                     steps=30, colors=ACOL)
    shell.player_panel(cv, rx0 + 8.0, ccy + rr + 12.0, max(60.0, rwide - 16.0),
                       [(u, score.get(str(u), 0)) for u in players], me, nick)
