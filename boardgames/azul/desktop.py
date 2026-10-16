# -*- coding: utf-8 -*-
"""Azul 展示包桌面画师（spec §7 BGA 版面）。

信息条 / 左列工厂盘（竖排网格）+ 列底中央池 / 中部自己一块大板 + 对手缩略小板
/ 右侧圆形计分轨 + 分数清单。

- 所有位图入口走 `boardgames.shell` 的组件（其内部再走 client_gameui 的
  `_asset_*`，失败逐项矢量回退）；本模块不新增任何 `ImageTk.PhotoImage(master=cv)`。
- 素材键一律经 `KEYS` / 关键字参数外置，`boardgames/shell.py` 源码内不出现 `azul_`。
"""
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


def _paint_boards(cv, lay, players, me, rows_st, wall_st, fl_st, score, nick):
    """中部玩家板区：自己一块大板（active + 地板计数）+ 对手缩略小板。

    `me` 不在 `players` 里（旁观）时退化为 `layout` 的均匀网格，不做高亮。
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
        shell.board_panel(cv, cx0, cy0, me_w, ch_all, nick(me),
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
        return
    cols, rows = lay["cols"], lay["rows"]
    cell_w, cell_h = lay["cell"]
    compact = cell_w < 190.0
    for i, u in enumerate(players):
        c, r = i % cols, i // cols
        shell.board_panel(cv, cx0 + c * cell_w, cy0 + r * cell_h, cell_w, cell_h,
                          nick(u), rows_st.get(str(u), {}), wall_st.get(str(u), {}),
                          [], score.get(str(u), 0), KEYS,
                          wall_expected=_wall_target, compact=compact)


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
    for i, bowl in enumerate(offers):
        c, r = i % fcols, i // fcols
        shell.factory_disc(cv, lx0 + fcw * (c + 0.5), ly0 + fch * (r + 0.5) + 8.0,
                           fr, bowl, plate_key="azul_plate",
                           tile_key="azul_tile_{c}", colors=ACOL)
    pr = max(10.0, min((lx1 - lx0) * 0.42, pool_zone * 0.36))
    pcx = (lx0 + lx1) / 2.0
    pcy = ly0 + grid_h + pool_zone / 2.0
    _text(cv, pcx, pcy - pr - 7.0, "中央池", "#EAF2F7", (_FONT_F[0], 8))
    shell.factory_disc(cv, pcx, pcy, pr, center, plate_key="azul_plate_center",
                       tile_key="azul_tile_{c}", center=True, colors=ACOL)

    # 4) 中部：所有玩家板（自己大板高亮 + 对手缩略）
    _paint_boards(cv, lay, players, me, rows_st, wall_st, fl_st, score, nick)

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
