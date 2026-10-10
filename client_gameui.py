# -*- coding: utf-8 -*-
"""桌面端桌游对局 Canvas 图形化渲染（纯 Tkinter，仅客户端使用）。

render() 按游戏名分派到对应 painter；未覆盖的游戏走 _generic 美化兜底，
保证任何一款都不再显示成裸文本。

交互模型：
  - 棋盘类（gomoku/connect4/othello/tictactoe/xiangqi/chess/go/kalah）
    点击格子直接落子/走子；走子类（象棋/围棋）先点己方子选中、再点落点。
  - 手牌/选卡类（uno/coc setup）点击卡片直接提交。
  - 其余交互（rps/blackjack/calc24/werewolf/avalon/spy 的投票、技能、出拳等）
    仍复用底层 _GAME_ACTIONS 按钮区，本模块只负责把局面画好看。

点击坐标→动作由 handle_click() 统一分发，client 绑定一个 Canvas 单击即可。
"""
import tkinter as tk
import math
import time
import random

# ---- 基础字号（客户端窗口用，此处保持一致即可）----
_FONT_F  = ("Microsoft YaHei UI", 10)
_FONT_B  = ("Microsoft YaHei UI", 12, "bold")
_FONT_H  = ("Microsoft YaHei UI", 14, "bold")
_FONT_BIG = ("Microsoft YaHei UI", 18, "bold")

# 每款游戏的主题渐变色（上→下），对齐 client._GAME_GRAD 的观感
THEME = {
    "gomoku":   ("#8a5a2b", "#5f3d1d"),
    "connect4": ("#2955b8", "#1c3d82"),
    "othello":  ("#26292f", "#14161a"),
    "tictactoe":("#2955b8", "#1c3d82"),
    "kalah":    ("#6a45a0", "#48307a"),
    "xiangqi":  ("#6b4a2a", "#452f18"),
    "chess":    ("#232a33", "#161c24"),
    "go":       ("#1d2736", "#0f1720"),
    "uno":      ("#c2362c", "#8c1f17"),
    "blackjack":("#1f5236", "#123420"),
    "rps":      ("#c24a33", "#8c2f1f"),
    "calc24":   ("#c38427", "#8c5f14"),
    "coc":      ("#123022", "#0a1d13"),
    "werewolf": ("#3c1826", "#260f18"),
    "avalon":   ("#355c7d", "#1f3b58"),
    "spy":      ("#5d4592", "#3f2f6b"),
    "halma":    ("#3f6fe0", "#274b9e"),
    "checkers": ("#232a33", "#161c24"),
    "junqi":    ("#8c2f1f", "#5c1a10"),
    "dou":      ("#2f7d3a", "#1e5226"),
    "shogi":    ("#8a5a2b", "#5f3d1d"),
    "blokus":   ("#3ba55d", "#1f5c36"),
    "ludo":     ("#c2362c", "#8c1f17"),
    "rummikub": ("#3f8f6a", "#2a6b4d"),
    "yahtzee":  ("#e0a13c", "#c38427"),
    "nimmt":    ("#8a5a2b", "#6a4121"),
    "davinci":  ("#5b6ca8", "#42528a"),
    "lovelove": ("#e08ac0", "#c265a4"),
    "matchpairs":("#37a25f", "#21804a"),
    "liar":     ("#c9853e", "#8a5a2b"),
    "halloween":("#e05555", "#c2362c"),
    "ninja":    ("#33415a", "#1d2736"),
    "onewolf":  ("#4a3b6b", "#32264d"),
    "guess_number":("#5b8def", "#3b6fd4"),
    "drawguess":("#e08ac0", "#c265a4"),
    "kaituo":   ("#c98a3d", "#a96a28"),
    "lingdi":   ("#4f7a54", "#37603c"),
    "tielu":    ("#3d5a86", "#2c4366"),
    "gongfang": ("#8a6f4a", "#6a5336"),
    "chengzhu": ("#7f5b3f", "#5f422c"),
    "gemcity":  ("#8a5fbf", "#6a45a0"),
    "siji":     ("#3f8f6a", "#2a6b4d"),
    "bolan":    ("#5b6ca8", "#42528a"),
    "azul":     ("#3f8f8a", "#2f6f70"),
    "betrayal": ("#5a3f78", "#3e2a56"),
    "balatro":  ("#5b1f2a", "#2a1030"),
}

_WHITE = "#ffffff"
_PANEL = "#fdf8ee"     # 面板底色（奶白暖粉）
_PANEL_BD = "#f0e2cc"   # 面板描边（浅咖）
_MUTED = "#b39378"      # 弱化文字（暖灰咖）
_WARMTXT = "#4a3b32"    # 正文（暖棕）
_ACCENT = "#ff8a5c"     # 珊瑚（主强调）
_ACCENT2 = "#8f9bff"    # 浅紫蓝（次强调）
_SUN = "#ffd166"        # 向日葵黄
_MINT = "#6fcba0"       # 薄荷绿


def _hex2rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:                    # 兼容 "#fff" / "#111" 三位简写
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb2hex(r, g, b):
    return "#%02x%02x%02x" % (max(0, min(255, int(r))),
                              max(0, min(255, int(g))),
                              max(0, min(255, int(b))))


def _shade(h, f):
    """f>0 变亮，f<0 变暗，f∈[-1,1]"""
    r, g, b = _hex2rgb(h)
    if f >= 0:
        return _rgb2hex(r + (255 - r) * f, g + (255 - g) * f, b + (255 - b) * f)
    return _rgb2hex(r * (1 + f), g * (1 + f), b * (1 + f))


def _luma(h):
    r, g, b = _hex2rgb(h)
    return 0.299 * r + 0.587 * g + 0.114 * b


def _grad(cv, x0, y0, x1, y1, c1, c2, steps=32):
    r1, g1, b1 = _hex2rgb(c1)
    r2, g2, b2 = _hex2rgb(c2)
    for i in range(steps):
        t = i / (steps - 1)
        col = _rgb2hex(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t)
        yy = y0 + (y1 - y0) * i / steps
        yy2 = y0 + (y1 - y0) * (i + 1) / steps
        cv.create_rectangle(x0, yy, x1, yy2, fill=col, outline=col, width=0)


def _rrect_pts(x0, y0, x1, y1, r=10):
    r = max(r, 1)
    return [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r,
            x1, y1, x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r]


def _rrect(cv, x0, y0, x1, y1, r=10, fill=_WHITE, outline=_PANEL_BD,
           width=1, tags=""):
    """圆角矩形：卡片统一走这里。浅色奶咖填充加暖色描边+顶部高光，深色填充只加顶部提亮。"""
    is_hex = isinstance(fill, str) and len(fill) == 7 and fill[0] == "#"
    cv.create_polygon(_rrect_pts(x0, y0, x1, y1, r), fill=fill,
                      outline=outline, width=width, smooth=True,
                      splinesteps=24, tags=tags)
    if is_hex:
        lum = _luma(fill)
        if lum < 240:
            cv.create_line(x0 + r, y0 + 1.5, x1 - r, y0 + 1.5,
                           fill=_shade(fill, 0.28), width=1)
        elif lum >= 240:                     # 浅色卡片：顶部一道柔和亮边，衬出手绘浮雕感
            cv.create_line(x0 + r, y0 + 1.0, x1 - r, y0 + 1.0,
                           fill="#fff2df", width=1)


def _soft_shadow(cv, x0, y0, x1, y1, r=10, dy=3, col="#3a332a"):
    """半透明柔和投影：置于卡片下方一层（用 stipple 模拟半透明）。"""
    cv.create_polygon(_rrect_pts(x0, y0 + dy, x1, y1 + dy, r), fill=col,
                      outline="", smooth=True, splinesteps=24,
                      stipple="gray50", tags="_shadow")


def _paper_board(cv, x0, y0, x1, y1, base="#c89b5f", edge="#8a5a2b",
                 grain="#ffffff"):
    """细腻纸面木纹底板：柔和渐变 + 木纹线条 + 内衬描边。
    供网格/矩阵类桌游作为棋盘衬底，视觉更温润（替代单一平涂木色）。
    纯函数式绘制：仅画当前帧，无状态、无 after。"""
    # 衬底渐变（上暗下亮，模拟裁切面受光）
    _grad(cv, x0, y0, x1, y1, _shade(base, -0.07), _shade(base, 0.10))
    # 木纹：纵向细波纹（两侧浅、中央深，密度随宽度自适应）
    n = min(int((x1 - x0) / 14) + 1, 22)
    step = (x1 - x0) / (n + 1)
    for i in range(1, n + 1):
        xx = x0 + i * step
        off = ((i % 3) - 1) * 3
        cv.create_line(xx, y0 + 2, xx + off, y1 - 2,
                       fill=_shade(base, 0.06 if i % 2 else -0.06),
                       width=1, tags="_paper")
    # 极细高光横纹（纸张质感）
    for fy in range(int(y0) + int((y1 - y0) * 0.28), int(y1 - 2), 9):
        cv.create_line(x0 + 2, fy, x1 - 2, fy + 1,
                       fill=_shade(base, 0.18),
                       stipple="gray50", width=1, tags="_paper")
    # 内衬浅描边 + 外加深描边（层次感）
    cv.create_line(x0 + 1, y0 + 1, x1 - 1, y0 + 1, x1 - 1, y1 - 1,
                   x0 + 1, y1 - 1, x0 + 1, y0 + 1,
                   fill=_shade(base, 0.22), width=1, tags="_paper")


def _etch_cell(cv, x0, y0, x1, y1, fill, outline):
    """逐格刻纹：单个棋盘格填充 + 内嵌木纹细线 + 上沿高光/下沿暗纹 + 虚实描边。
    用于棋盘格类（chess/xiangqi）与逐格落子类（connect4），替代平涂格子，
    提升"木质棋盘格"观感。纯函数绘制，无状态无 after。"""
    cv.create_rectangle(x0, y0, x1, y1, fill=fill, outline="")
    ch = y1 - y0
    # 内嵌木纹细线（随格高自适应间距）
    gap = max(5, int(ch / 6))
    for yy in range(int(y0) + gap, int(y1) - 1, gap):
        cv.create_line(x0 + 1, yy, x1 - 1, yy, fill=_shade(fill, 0.05),
                       width=1, stipple="gray50")
    # 上沿高光 + 下沿暗纹（立体）
    cv.create_line(x0 + 1, y0 + 1, x1 - 1, y0 + 1, fill=_shade(fill, 0.18),
                   width=1)
    cv.create_line(x0 + 1, y1 - 1, x1 - 1, y1 - 1, fill=_shade(fill, -0.12),
                   width=1)
    # 左右虚线描边（弱化硬框，接缝自然）
    cv.create_line(x0, y0, x0, y1, fill=outline, width=1, stipple="gray50")
    cv.create_line(x1, y0, x1, y1, fill=outline, width=1, stipple="gray50")


def _icon_badge(cv, cx, cy, rad, emoji, accent, font_size=14):
    """大圆钮（任天堂式）：渐变圆底 + 顶光 + 内嵌 emoji。"""
    _disc(cv, cx, cy, rad, accent, top_bright=0.30, bot_dark=-0.18)
    cx_r = rad * 0.46
    cv.create_oval(cx - cx_r, cy - rad * 0.62, cx + cx_r, cy - rad * 0.10,
                   fill=_shade(accent, 0.55), outline="")
    cv.create_text(cx, cy + 1, text=emoji,
                   font=(_FONT_F[0], font_size), anchor="center")


def _disc(cv, cx, cy, r, color, top_bright=0.32, bot_dark=-0.18,
          steps=14, outline=None, outline_w=1, glow=False, gint=0.0):
    """渐变圆片：竖条裁剪到圆内，呈现上亮下暗的立体观感。
    glow=True 时在外缘叠同色系呼吸辉光（复用 _g_piece_glow），供 shogi/junqi
    等用 _disc 画子的桌游接用；默认 False 不影响既有调用。"""
    if glow:
        _g_piece_glow(cv, cx, cy, r, color, gint)
    hi, lo = _shade(color, top_bright), _shade(color, bot_dark)
    r1, g1, b1 = _hex2rgb(hi)
    r2, g2, b2 = _hex2rgb(lo)
    for i in range(steps):
        t1 = i / steps
        t2 = (i + 1) / steps
        y1, y2 = cy - r + 2 * r * t1, cy - r + 2 * r * t2
        yc = cy - r + 2 * r * ((t1 + t2) / 2)
        s = 1 - ((yc - cy) / r) ** 2
        xw = r * math.sqrt(s) if s > 0 else 0.0
        col = _rgb2hex(r1 + (r2 - r1) * t1, g1 + (g2 - g1) * t1,
                       b1 + (b2 - b1) * t1)
        cv.create_rectangle(cx - xw, y1, cx + xw, y2, fill=col,
                            outline=col, width=0)
    if outline:
        cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline=outline,
                       width=outline_w)


def _text(cv, x, y, s, fill="#4a3b32", font=_FONT_F, anchor="center", tags=""):
    cv.create_text(x, y, text=s, fill=fill, font=font, anchor=anchor, tags=tags)


# ---------------------------------------------------------------------------
# 《五子棋》辉光 / 落子 / 胜利粒子 —— 纯逻辑层（不触 Canvas，便于单测）
#
# 动画一律"纯时间推导"：输入 time.monotonic() 时间戳 + 粒子参数 → 输出要在
# canvas 上画的形状；不依赖 after/线程/全局计时器。帧推进只借 ui['repaint']()
# 的既有重绘链（同 Balatro 范式），draw 层在粒子生命周期结束后自动停帧。
# _g_stipple 同时被 _stone 的辉光使用，故放在 _stone 之前定义。
# ---------------------------------------------------------------------------
_G_PART_BURST_MAX = 16      # 落子微粒子数上限
_G_PART_WIN_MAX   = 48      # 胜利星点粒子数上限
_G_LAST_DUR   = 0.9         # 落子光晕/粒子总时长（秒）
_G_BREATH_W   = 2.6         # 辉光呼吸角速度 (rad/s)
_G_BREATH_LO  = 0.45        # 辉光呼吸强度下界
_G_BREATH_AMP = 0.30        # 呼吸摆幅 → 强度 ∈ [LO, LO+AMP]


def _g_stipple(a):
    """把 [0,1] 不透明度映射到 tk stipple 图案（点密度模拟 alpha，画布无真透明）。"""
    a = 0.0 if (a is None or a < 0) else (1.0 if a > 1 else a)
    if a >= 0.80:
        return ""
    if a >= 0.55:
        return "gray75"
    if a >= 0.30:
        return "gray50"
    if a >= 0.12:
        return "gray25"
    return "gray12"


def _g_breath(now):
    """辉光呼吸强度因子，有界于 [_G_BREATH_LO, _G_BREATH_LO+_G_BREATH_AMP]。
    纯时间推导：idle 状态下的'唯一视觉增量'，让静止棋盘也能微微脉动。"""
    s = 0.5 + 0.5 * math.sin(now * _G_BREATH_W)
    return _G_BREATH_LO + _G_BREATH_AMP * s


def _g_glow_stipple(k, gint):
    """按辉光层索引 k(0..2) 与呼吸因子 gint 计算外缘光晕的 stipple（点密度）。
    纯函数：仅由参数推导、值恒落在合法 stipple 集内，供 headless 单测窗密封顶。"""
    a = max(0.05, min(0.32, 0.10 + 0.20 * k * (0.35 + 0.65 * gint)))
    return _g_stipple(a)


def _g_piece_glow(cv, cx, cy, r, color, gint):
    """通用棋子辉光：在棋子外缘叠 3 层同色系柔和光晕（stipple 模拟半透明），
    强度随呼吸因子 gint(∈[0,1]) 微变。供 _disc / _stone / 手绘棋子(create_oval
    、字符) 等多类棋子共用，做到"一处辉光逻辑，四处接用"。纯时间推导无副作用。"""
    for k, mul in enumerate((1.18, 1.36, 1.58)):
        gg = _shade(color, 0.14 + 0.16 * k)            # 同色系逐层提亮
        cv.create_oval(cx - r * mul, cy - r * mul, cx + r * mul,
                       cy + r * mul, fill=gg, outline="",
                       stipple=_g_glow_stipple(k, gint), tags="_gpiece_glow")


def _g_halo(now, t0, dur, base_r):
    """落子金色光晕：膨胀 + 渐隐。返回 (半径, alpha)；结束返回 (0, 0)。
    纯时间推导，无副作用。"""
    age = now - t0
    if age < 0 or age >= dur:
        return 0.0, 0.0
    p = age / dur
    e = 1 - (1 - p) ** 2              # ease-out：先快后慢膨胀
    return base_r * (1 + 1.5 * e), 1.0 - p


def _g_spawn_burst(cx, cy, n, seed=None):
    """生成 n 粒落子微粒子（方向/速度/寿命随机）。seed 固定则结果确定性（便于单测）。"""
    rng = random.Random(seed)
    return [{
        "ang": rng.uniform(0.0, 2 * math.pi),
        "spd": rng.uniform(28.0, 95.0),      # px/s
        "life": rng.uniform(0.5, _G_LAST_DUR),
        "cx": cx, "cy": cy,
    } for _ in range(int(n))]


def _g_step_burst(parts, t0, now):
    """时间推导落子微粒子当前位置/尺寸/不透明度。
    返回 ([(x, y, size, alpha), ...], alive)。纯函数：不改入参、不触 Canvas。"""
    drawn, alive = [], False
    for p in parts:
        age = now - t0
        if age < 0 or age >= p["life"]:
            continue                       # 生命周期结束 → 不再绘制（不残留）
        k = age / p["life"]
        d = p["spd"] * age
        drawn.append((p["cx"] + math.cos(p["ang"]) * d,
                      p["cy"] + math.sin(p["ang"]) * d,
                      1.2 + 0.8 * (1 - k), 1.0 - k))
        alive = True
    return drawn, alive


def _g_spawn_star(cx, cy, seed=None):
    """单个胜利星点：随机方向/速度/寿命。seed 固定则确定性（便于单测）。"""
    rng = random.Random(seed)
    return {
        "ang": rng.uniform(0.0, 2 * math.pi),
        "spd": rng.uniform(18.0, 72.0),
        "life": rng.uniform(0.9, 1.8),
        "cx": cx, "cy": cy,
    }


def _g_step_star(p, t0, now):
    """胜利星点时间推导：上飘 + 沿方向散开 + 渐隐。
    返回 (x, y, size, alpha, alive)。纯函数。"""
    age = now - t0
    if age < 0 or age >= p["life"]:
        return 0.0, 0.0, 0.0, 0.0, False
    k = age / p["life"]
    rise = (1 - (1 - k) ** 2) * 22         # 缓出上飘
    d = p["spd"] * age
    return (p["cx"] + math.cos(p["ang"]) * d,
            p["cy"] + math.sin(p["ang"]) * d - rise,
            1.6 + 1.4 * (1 - k), 0.9 * (1 - k), True)


def _stone(cv, cx, cy, r, color, outline="#000", last=False, glow=False,
           gint=0.0):
    """立体棋子：渐变底 + 玻璃高光；last 为最近一步时加金色光晕环。

    glow=True 时在棋子外缘叠 2~3 层同色系柔和浅辉光（用 stipple 模拟半透明），
    强度 gint∈[0,1] 随呼吸正弦（纯时间推导）微变，让棋子活起来。
    glow 默认 False，其它桌游调用不受影响（保持原样）。
    """
    if glow:
        # 外缘辉光：与 _disc/shard 共用 _g_piece_glow 一处逻辑（行为与原实现一致）
        _g_piece_glow(cv, cx, cy, r, color, gint)
    _disc(cv, cx, cy, r, color, outline=outline)
    # 玻璃反光：左上小亮斑
    cv.create_oval(cx - r * 0.56, cy - r * 0.64, cx - r * 0.02, cy - r * 0.10,
                   fill=_shade(color, 0.62), outline="")
    if last:
        cv.create_oval(cx - r * 1.22, cy - r * 1.22, cx + r * 1.22,
                       cy + r * 1.22, fill="", outline="#ffd75e", width=2,
                       tags="_lastglow")


# ---------------------------------------------------------------------------
# 通用布局
# ---------------------------------------------------------------------------
def _fit(n, w, h, header=46, pad=14):
    """在 (w,h) 可用区里放一个 n×n 方格棋盘，返回 (ox, oy, cell)"""
    avail = max(40, min(w - pad * 2, h - header - pad * 2))
    cell = max(avail / n, 8)
    size = cell * n
    ox = (w - size) / 2
    oy = header + (h - header - size) / 2
    return ox, oy, cell


def _turn_banner(cv, w, header_h, text, accent, ypad=8):
    """顶栏精致化：柔和渐变卡 + 顶/底描边 + 标题投影。"""
    base = accent
    _grad(cv, 0, 0, w, header_h, _shade(base, 0.42), _shade(base, -0.10))
    cv.create_line(0, 1, w, 1, fill=_shade(base, 0.6), width=1)
    cv.create_line(0, int(header_h) - 1, w, int(header_h) - 1,
                   fill=_shade(base, -0.32), width=1)
    _text(cv, w / 2 + 1, header_h / 2 + 1, text, _shade(base, -0.45), _FONT_B)
    _text(cv, w / 2, header_h / 2, text, _WHITE, _FONT_B)


def _hover_overlay(cv, ui):
    """按 ui['_hover'] 给当前悬停格画淡白高亮（render 收尾统一调用）。"""
    if ui.get("game") in ("gomoku", "connect4"):
        _flagship_hover(cv, ui)
        return
    h = ui.get("_hover")
    if not h:
        return
    ox, oy, cell, n = ui.get("ox"), ui.get("oy"), ui.get("cell"), ui.get("n")
    if ox is None or oy is None or cell is None or n is None:
        ui.pop("_hover", None)
        return
    cols, rows = ui.get("cols", n), ui.get("rows", n)
    if not (0 <= h[0] < cols and 0 <= h[1] < rows):
        ui.pop("_hover", None)
        return
    x0, y0 = ox + h[0] * cell, oy + h[1] * cell
    cv.create_polygon(_rrect_pts(x0 + 3, y0 + 3, x0 + cell - 3, y0 + cell - 3,
                                 5),
                      fill="#ffffff", outline="", smooth=True,
                      splinesteps=24, stipple="gray25", tags="_hover")
    cv.create_polygon(_rrect_pts(x0 + 3, y0 + 3, x0 + cell - 3, y0 + cell - 3,
                                 5),
                      fill="", outline="#d8cfc0", width=2, smooth=True,
                      splinesteps=24, tags="_hover")


# ---------------------------------------------------------------------------
# 第二轮：可交互发现性 + 微观细节 通用微件
# （新增 helper，复用给多数游戏；不触碰点击分发/几何）
# ---------------------------------------------------------------------------

def _text_w(s, fsize=12):
    """按全角/半角近似估算文本像素宽（避免依赖 tk.font，冒烟脚本可跑）。"""
    w = 0.0
    for ch in s:
        w += fsize if ord(ch) > 0x2e80 else fsize * 0.56
    return w


def _hov_rects(ui, rects):
    """登记一批可点矩形区 (x0,y0,x1,y1)，供 client._on_cv_motion 算悬停索引。"""
    ui["_hov"] = rects
    hi = ui.get("_hov_idx")
    if hi is not None and not (0 <= hi < len(rects)):
        ui.pop("_hov_idx", None)


def _hov_idx(ui):
    return ui.get("_hov_idx")


def _anim_need(ui, repaint, gap=0.05, cap=60):
    """动画续帧泵：请求一次 ui['repaint']() 让下一帧渲染（节流 + 深度保护）。

    painter 是纯函数式重绘（禁 after/线程/全局计时器），只能借
    ui['repaint']() 的既有重绘链推进多帧：时间节流保证单条同步调用链
    只推进 1~2 帧，其余帧由真实事件（鼠标移动/状态推送）触发的渲染自然推进。
    """
    now = time.monotonic()
    if now - ui.get("_anim_last", 0.0) < gap:
        return
    depth = ui.get("_anim_depth", 0)
    if depth >= cap:
        return
    ui["_anim_last"] = now
    ui["_anim_depth"] = depth + 1
    try:
        repaint()
    finally:
        ui["_anim_depth"] = depth


def _lift(cv, ui, idx, x0, y0, x1, y1, lift=9, glow="#ffffff"):
    """可点卡悬停上浮：命中时加光圈并把该卡上移 lift 像素。
    命中返回 (True, dy)，调用方把 dy 加到自身绘制 y 上；未命中间补 dy = 0。"""
    on = _hov_idx(ui) == idx
    dy = -lift if on else 0
    if on:
        r = 9
        cv.create_polygon(_rrect_pts(x0 - 3, y0 + dy - 3, x1 + 3, y1 + dy + 3, r),
                          fill="", outline=glow, width=2, smooth=True,
                          splinesteps=24)
    return on, dy


def _sel_mark(cv, cx, cy, r, color="#ff9800"):
    """选中子指示：外圈光圈 + 上方小三角 + 四角微点（比裸描边更醒目）。"""
    cv.create_oval(cx - r * 1.34, cy - r * 1.34, cx + r * 1.34, cy + r * 1.34,
                   fill="", outline=color, width=2)
    tr = r * 0.30
    cv.create_polygon(cx - tr, cy - r * 1.55, cx + tr, cy - r * 1.55,
                      cx, cy - r * 1.95 - tr, fill=color, outline=color)
    for sx, sy in ((-1, 0), (1, 0), (0, 0.9), (0, 1.0)):
        cv.create_oval(cx + sx * r * 0.95 - 2.5, cy + sy * r - 2.5,
                       cx + sx * r * 0.95 + 2.5, cy + sy * r + 2.5,
                       fill=color, outline="")


def _hover_hint(cv, ui):
    """在你轮且悬停空格时画一粒淡白虚点，示意“这里可落”（无私有规则的统一提示）。"""
    ox, oy, cell, n = ui.get("ox"), ui.get("oy"), ui.get("cell"), ui.get("n")
    if ox is None or cell is None:
        return
    cols, rows = ui.get("cols", n), ui.get("rows", n)
    h = ui.get("_hover")
    if not h or not (0 <= h[0] < cols and 0 <= h[1] < rows):
        return
    hx, hy = h
    cv.create_oval(ox + hx * cell + cell / 2 - 3.5, oy + hy * cell + cell / 2 - 3.5,
                   ox + hx * cell + cell / 2 + 3.5, oy + hy * cell + cell / 2 + 3.5,
                   fill="#ffffff", outline="", stipple="gray50")


def _strip(cv, w, y, text, kind="info", accent="#c99a6d"):
    """柔和状态提示条：圆角卡 + 图标。kind ∈ ok/warn/info/danger。"""
    col = {"ok": "#4caf50", "warn": "#ff9800", "info": "#b39378",
           "danger": "#e0535a"}.get(kind, "#b39378")
    ic = {"ok": "✅", "warn": "⚠️", "info": "ℹ️", "danger": "⛔"}.get(kind, "ℹ️")
    _rrect(cv, w * 0.06, y, w * 0.94, y + 30, 15, _shade(col, 0.85),
           _shade(col, -0.12))
    _icon_badge(cv, w * 0.12, y + 15, 11, ic, col, 10)
    _text(cv, w * 0.185, y + 15, text, "#3a3a3a", _FONT_B, anchor="w")


def _score_chips(cv, w, y, items, accent):
    """右对齐圆角计分/资源小卡。items: [(标签(含图标), 数值, is_me), ...] 右到左排。
    我(me)那张用强调色高亮；未指定的灰白。"""
    x = w - 12
    hh = 24
    for tag, val, is_me in items:
        text = f"{tag} {val}"
        tw = _text_w(text)
        x0 = x - tw - 20
        fill = _shade(accent, 0.80) if is_me else "#f0eee7"
        oc = _shade(accent, -0.2) if is_me else _PANEL_BD
        cv.create_polygon(_rrect_pts(x0, y - hh / 2, x, y + hh / 2, hh / 2),
                          fill=fill, outline=oc, smooth=True, splinesteps=24)
        if is_me:
            cv.create_line(x0 + hh / 2, y - hh / 2 + 2, x - hh / 2,
                           y - hh / 2 + 2, fill=_shade(fill, 0.45), width=1)
        _text(cv, x0 + 12, y, text, ("#3a3a3a" if not is_me or _luma(fill) > 150
                                     else "#ffffff"), _FONT_B, anchor="w")
        x = x0 - 6
    return x


# ---------------------------------------------------------------------------
# 点击分发
# ---------------------------------------------------------------------------
def handle_click(ui, x, y):
    game = ui.get("game")
    fn = _CLICKS.get(game)
    if fn:
        fn(ui, x, y)


def _cell_of(ui, x, y):
    if ui.get("game") == "gomoku":
        return _intersection_of(ui, x, y)
    if ui.get("game") == "connect4":
        return _connect4_column_of(ui, x, y)
    ox, oy, cell = ui.get("ox"), ui.get("oy"), ui.get("cell")
    n = ui.get("n")
    if None in (ox, oy, cell, n):
        return None
    # 矩形棋盘（junqi/dou）用 cols/rows 限定边界，缺省回退为方阵 n
    cols = ui.get("cols", n)
    rows = ui.get("rows", n)
    cx, cy = (x - ox) / cell, (y - oy) / cell
    if cx < 0 or cy < 0 or cx >= cols or cy >= rows:
        return None
    return int(cx), int(cy)


def _connect4_column_of(ui, x, y):
    """Shared Connect Four column hit geometry for board and prompt strip.

    The strip immediately above the board is part of the same column hit box;
    it returns ``(column, -1)`` so hover and click use identical bounds while
    the painter resolves the preview to the actual lowest empty row.
    """
    ox, oy, cell = ui.get("ox"), ui.get("oy"), ui.get("cell")
    cols, rows = ui.get("cols", ui.get("n")), ui.get("rows")
    if None in (ox, oy, cell, cols, rows) or cell <= 0:
        return None
    if not (ox <= x < ox + cols * cell and oy - cell <= y < oy + rows * cell):
        return None
    col = int((x - ox) // cell)
    row = -1 if y < oy else int((y - oy) // cell)
    return col, row


def _intersection_of(ui, x, y):
    """Five-in-a-row uses intersections, including half a cell at each edge."""
    ox, oy, cell, n = (ui.get(k) for k in ("ox", "oy", "cell", "n"))
    if None in (ox, oy, cell, n) or cell <= 0:
        return None
    cx, cy = (x - ox) / cell, (y - oy) / cell
    if not (-0.5 <= cx < n - 0.5 and -0.5 <= cy < n - 0.5):
        return None
    return math.floor(cx + 0.5), math.floor(cy + 0.5)


def flagship_status(game, st, me, nick):
    """Player colour is fixed by seat, independently of whose turn it is."""
    players = st.get("players") or []
    colours = ("黑", "白") if game == "gomoku" else ("红", "黄")
    seat = players.index(me) if me in players else -1
    identity = f"你执{colours[seat]}" if 0 <= seat < 2 else "观战"
    def _status_nick(uid):
        value = str(nick(uid))
        return value if len(value) <= 8 else value[:7] + "…"
    winner = st.get("winner_uid")
    if winner is not None:
        status = f"{_status_nick(winner)} 获胜"
    elif st.get("draw"):
        status = "平局"
    elif st.get("turn_uid") == me and seat >= 0:
        status = "轮到你"
    else:
        status = f"等待 {_status_nick(st.get('turn_uid'))} 落子"
    return f"{identity} · {status}"


def flagship_can_move(room, st, me, connected):
    room, st = room or {}, st or {}
    return bool(connected and room.get("status") == "playing"
                and me in (room.get("players") or [])
                and me not in (room.get("spectators") or [])
                and st.get("turn_uid") == me
                and st.get("winner_uid") is None and not st.get("draw"))


def _flagship_hover(cv, ui):
    hover = ui.get("_hover")
    board = (ui.get("state") or {}).get("board") or []
    if not ui.get("can_move") or not hover or not board:
        return
    x, y = hover
    if ui["game"] == "connect4":
        if not 0 <= x < len(board[0]) or board[0][x]:
            return
        y = next(row for row in range(len(board) - 1, -1, -1) if not board[row][x])
        offset = 0.5
    else:
        if not (0 <= y < len(board) and 0 <= x < len(board[y])) or board[y][x]:
            return
        offset = 0.0
    cell = ui["cell"]
    cx, cy = ui["ox"] + (x + offset) * cell, ui["oy"] + (y + offset) * cell
    r = cell * 0.35
    cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#4b7c72",
                   width=2, dash=(3, 2), tags="_hover")


def _flagship_feedback(cv, ui, st, needed, now, lastpx):
    """A fixed last-move marker, finite pulse and static winning line."""
    last = st.get("last_move")
    key = (ui.get("_room_context"), tuple(last) if last else None)
    if key != ui.get("_flagship_move"):
        ui["_flagship_move"] = key
        ui["_flagship_t0"] = now
    age = now - ui.get("_flagship_t0", now)
    ui["_flagship_animate"] = bool(lastpx and 0 <= age < 0.9)
    if lastpx:
        cx, cy = lastpx
        r = max(3, ui["cell"] * 0.12)
        cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#c45e32",
                       width=2, tags="flagship-last")
        if ui["_flagship_animate"]:
            pulse = ui["cell"] * (0.42 + 0.2 * age / 0.9)
            cv.create_oval(cx - pulse, cy - pulse, cx + pulse, cy + pulse,
                           outline="#aa9d75", width=1, tags="flagship-pulse")
    line = flagship_win_line(st, needed)
    if line:
        offset = 0.0 if ui["game"] == "gomoku" else 0.5
        start, end = line[0], line[-1]
        cv.create_line(ui["ox"] + (start[0] + offset) * ui["cell"],
                       ui["oy"] + (start[1] + offset) * ui["cell"],
                       ui["ox"] + (end[0] + offset) * ui["cell"],
                       ui["oy"] + (end[1] + offset) * ui["cell"],
                       fill="#c45e32", width=3, tags="flagship-win")
    # Flagship feedback is finite.  The owning window supplies a cancellable
    # after scheduler; no global timer or idle breathing loop is introduced.
    if ui.get("_flagship_animate") and ui.get("_schedule_repaint"):
        ui["_schedule_repaint"](40)


def flagship_win_line(st, needed):
    """First winning direction's full contiguous run through the final move."""
    board, last = st.get("board") or [], st.get("last_move")
    players, winner = st.get("players") or [], st.get("winner_uid")
    if st.get("draw") or winner is None or winner not in players or not last or len(last) != 2:
        return []
    x, y = last
    if type(x) is not int or type(y) is not int:
        return []
    stone = players.index(winner) + 1

    def matches(px, py):
        return (0 <= py < len(board) and 0 <= px < len(board[py])
                and board[py][px] == stone)

    if not matches(x, y):
        return []
    for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
        before, after = [], []
        px, py = x - dx, y - dy
        while matches(px, py):
            before.append((px, py))
            px, py = px - dx, py - dy
        px, py = x + dx, y + dy
        while matches(px, py):
            after.append((px, py))
            px, py = px + dx, py + dy
        line = list(reversed(before)) + [(x, y)] + after
        if len(line) >= needed:
            return line
    return []


def _click_xy(ui, x, y):
    c = _cell_of(ui, x, y)
    if not c:
        return
    if ui.get("game") == "gomoku":
        board = (ui.get("state") or {}).get("board") or []
        if (not ui.get("can_move") or c[1] >= len(board)
                or c[0] >= len(board[c[1]]) or board[c[1]][c[0]]):
            return
    ui["submit"]({"x": c[0], "y": c[1]})


def _click_col(ui, x, y):
    n = ui.get("n")
    if n is None or not ui.get("can_move"):
        return
    board = (ui.get("state") or {}).get("board") or []
    c = _connect4_column_of(ui, x, y)
    if not board or c is None:
        return
    col = c[0]
    if 0 <= col < n and col < len(board[0]) and not board[0][col]:
        ui["submit"]({"col": col})


def _click_move(ui, x, y):
    """象棋/围棋：点己方子选中，点目标落点走子"""
    c = _cell_of(ui, x, y)
    if not c:
        return
    sel = ui.get("sel") or {}
    if sel.get("game") == ui["game"] and "fx" in sel:
        ui["submit"]({"fx": sel["fx"], "fy": sel["fy"],
                      "tx": c[0], "ty": c[1]})
        sel.clear()
    else:
        sel["game"] = ui["game"]
        sel["fx"], sel["fy"] = c[0], c[1]
    ui["repaint"]()


def _click_go(ui, x, y):
    """围棋：单击交叉点直接落子（GoGame.act 期望 {"x","y"}，无需两段式选子）。"""
    st = ui.get("state") or {}
    if st.get("over") or st.get("winner_uid") is not None:
        return
    c = _cell_of(ui, x, y)
    if not c:
        return
    board = st.get("board") or []
    if c[1] >= len(board) or c[0] >= len(board[c[1]]) or board[c[1]][c[0]]:
        return
    ui["submit"]({"x": c[0], "y": c[1]})


def _click_kalah(ui, x, y):
    """6 洞播棋：点己方洞（1~6）"""
    me = ui["me"]
    holes = ui["holes"]           # [(ox,oy,cell,hole_idx_local0to5)]
    for ox, oy, cell, local in holes:
        if ((x - ox) ** 2 + (y - oy) ** 2) <= (cell * 0.62) ** 2:
            ui["submit"]({"hole": local + 1})
            return


def _click_uno(ui, x, y):
    """点击手牌出牌：由 priv.hand_ids 推断 id"""
    cards = ui.get("cards")       # [(cx0,cy0,cx1,cy1,id)]
    if not cards:
        return
    for c0x, c0y, c1x, c1y, cid in cards:
        if c0x <= x <= c1x and c0y <= y <= c1y:
            ui["submit"]({"card": cid})
            return


def _click_coc_deck(ui, x, y):
    cards = ui.get("cards")
    if not cards:
        return
    for c0x, c0y, c1x, c1y, cid in cards:
        if c0x <= x <= c1x and c0y <= y <= c1y:
            ui["submit"]({"op": "choose_card", "card_id": cid})
            return


def _click_shogi(ui, x, y):
    """将棋：既能两段式走子，也能先点底部手牌卡、再点空位打入。"""
    game = ui["game"]
    sel = ui.get("sel") or {}
    hands = ui.get("hands") or []       # [(x0,y0,x1,y1,type)]
    # 已处于“选打入手牌”状态：点子=打入空位，点手牌卡=换一枚，点外=取消
    if sel.get("game") == game and "drop" in sel:
        c = _cell_of(ui, x, y)
        if c:
            ui["submit"]({"op": "drop", "t": sel["drop"],
                          "x": c[0], "y": c[1]})
            sel.clear()
        else:
            # 命中另一张手牌则切换，否则清空打入态
            hit = False
            for hx0, hy0, hx1, hy1, t in hands:
                if hx0 <= x <= hx1 and hy0 <= y <= hy1:
                    sel["drop"] = t
                    hit = True
                    break
            if not hit:
                sel.pop("drop", None)
        ui["repaint"]()
        return
    # 未处于打入态：先看是否点到手牌卡 → 进入打入态
    for hx0, hy0, hx1, hy1, t in hands:
        if hx0 <= x <= hx1 and hy0 <= y <= hy1:
            sel.clear()
            sel["game"] = game
            sel["drop"] = t
            ui["repaint"]()
            return
    # 否则沿用两段式走子
    c = _cell_of(ui, x, y)
    if not c:
        if sel.get("game") == game:
            sel.clear()
            ui["repaint"]()
        return
    if sel.get("game") == game and "fx" in sel:
        ui["submit"]({"fx": sel["fx"], "fy": sel["fy"],
                      "tx": c[0], "ty": c[1]})
        sel.clear()
    else:
        sel["game"] = game
        sel["fx"], sel["fy"] = c[0], c[1]
    ui["repaint"]()


def _click_ludo(ui, x, y):
    """飞行棋：点自己的一架机（未完成）提交移动。"""
    tokens = ui.get("tokens") or []     # [(cx,cy,idx,r)]
    for cx, cy, idx, r in tokens:
        if cx is None:
            continue
        if (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2:
            ui["submit"]({"op": "move", "idx": idx})
            return


def _click_rummikub(ui, x, y):
    """拉密：点击手牌切换高亮收集（真正出牌提交走下方按钮 meld/extend）。"""
    cards = ui.get("cards")
    if not cards:
        return
    for c0x, c0y, c1x, c1y, cid in cards:
        if c0x <= x <= c1x and c0y <= y <= c1y:
            sel = ui.setdefault("sel", {})
            pool = set(sel.get("rmk", []))
            pool ^= {cid}
            sel["rmk"] = list(pool)
            ui["repaint"]()
            return


def _click_balatro(ui, x, y):
    """小丑牌：点出战区已出战的牌 → unselect；点手牌 → select（cid 反查自 ui）。"""
    for c0x, c0y, c1x, c1y, cid in ui.get("balatro_sel") or ():
        if c0x <= x <= c1x and c0y <= y <= c1y:
            ui["submit"]({"op": "unselect", "cid": cid})
            return
    for c0x, c0y, c1x, c1y, cid in ui.get("balatro_cards") or ():
        if c0x <= x <= c1x and c0y <= y <= c1y:
            ui["submit"]({"op": "select", "cid": cid})
            return


def _toggle_solo_use(ui, slot):
    """点击某消耗品槽：需目标的消耗品进入待选目标态；无需目标（塔罗星球列表外的
    level/destroy_cash）直接用。再点同一槽取消。「需求看图」从 CONS_DEFS 判定。"""
    cids = ui.get("solo_cons_cids") or []
    if not (0 <= slot < len(cids)):
        ui["_solo_use"] = None
        return
    if ui.get("_solo_use") == slot:
        ui["_solo_use"] = None
        return
    from games_pkg.balatro import CONS_DEFS
    _name, _cat, _d, eff, _price = CONS_DEFS.get(cids[slot], (None, None, None, {}, None))
    if eff.get("op") in ("level", "destroy_cash"):
        ui["submit"]({"op": "use", "slot": slot, "cid": None})
        return
    ui["_solo_use"] = slot


def _click_balatro_solo(ui, x, y):
    """单人版点击分发：商店面板 / 消耗品槽 / 消耗品指定手牌，再回退到 select/unselect。"""
    # 商店：继续 / 刷新 / 商品格
    rect = ui.get("solo_shop_continue")
    if rect and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
        ui["submit"]({"op": "next"})
        return
    rect = ui.get("solo_shop_reroll")
    if rect and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
        ui["submit"]({"op": "reroll"})
        return
    for x0, y0, x1, y1, idx in ui.get("solo_shop_jokers") or ():
        if x0 <= x <= x1 and y0 <= y <= y1:
            ui["submit"]({"op": "buy", "what": "joker", "idx": idx})
            return
    for x0, y0, x1, y1, idx in ui.get("solo_shop_cons") or ():
        if x0 <= x <= x1 and y0 <= y <= y1:
            ui["submit"]({"op": "buy", "what": "cons", "idx": idx})
            return
    # 消耗品槽
    for x0, y0, x1, y1, slot in ui.get("solo_cons") or ():
        if x0 <= x <= x1 and y0 <= y <= y1:
            _toggle_solo_use(ui, slot)
            return
    # 待选目标态：点手牌 → 对目标卡使用消耗品
    pending = ui.get("_solo_use")
    if pending is not None:
        for x0, y0, x1, y1, cid in ui.get("balatro_cards") or ():
            if x0 <= x <= x1 and y0 <= y <= y1:
                ui["_solo_use"] = None
                ui["submit"]({"op": "use", "slot": pending, "cid": cid})
                return
    # 原 select/unselect 逻辑原样保留
    for c0x, c0y, c1x, c1y, cid in ui.get("balatro_sel") or ():
        if c0x <= x <= c1x and c0y <= y <= c1y:
            ui["submit"]({"op": "unselect", "cid": cid})
            return
    for c0x, c0y, c1x, c1y, cid in ui.get("balatro_cards") or ():
        if c0x <= x <= c1x and c0y <= y <= c1y:
            ui["submit"]({"op": "select", "cid": cid})
            return


_CLICKS = {
    "gomoku": _click_xy, "othello": _click_xy, "tictactoe": _click_xy,
    "go": _click_go, "xiangqi": _click_move, "chess": _click_move,
    "connect4": _click_col, "kalah": _click_kalah,
    "uno": _click_uno, "coc": _click_coc_deck,
    "halma": _click_move, "checkers": _click_move,
    "junqi": _click_move, "dou": _click_move,
    "shogi": _click_shogi, "ludo": _click_ludo,
    "rummikub": _click_rummikub, "balatro": _click_balatro,
    "balatro_solo": _click_balatro_solo,   # 单人版：商店/消耗品 + select/unselect
}


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------
def render(cv, game, st, me, nick, submit, repaint, ui, priv, w, h):
    if w < 80 or h < 80:
        return
    cv.delete("all")
    painter = _PAINTERS.get(game)
    if painter:
        painter(cv, st, me, nick, submit, repaint, ui, priv, w, h)
    else:
        _generic(cv, game, st, me, nick, w, h, priv)
    _hover_overlay(cv, ui)      # 悬停高亮统一收尾（网格类游戏生效）


_PAINTERS = {}


def _register(name):
    def deco(fn):
        _PAINTERS[name] = fn
        return fn
    return deco


# ---------------------------------------------------------------------------
# 各游戏 painter
# ---------------------------------------------------------------------------

def _g_draw_last(cv, ui, now, key, cell):
    """落子（最近一步）动效：金色光晕膨胀渐隐 + ≤16 粒微粒子四散。
    仅作用于 last_move（key = 该子像素中心），避免每帧全盘重算。
    粒子结束后不再绘制（保留状态防重复生成），直到落下一步走子。"""
    if key is None:
        ui.pop("_g_burst", None)
        ui.pop("_g_lastpx", None)          # UI 更新/清盘：清理状态
        return
    if ui.get("_g_lastpx") != key:          # 最近一步变更 → 只重建一次粒子
        ui["_g_burst"] = {
            "parts": _g_spawn_burst(key[0], key[1], _G_PART_BURST_MAX),
            "t0": now,
        }
        ui["_g_lastpx"] = key
    burst = ui.get("_g_burst")
    if not burst:
        return
    cx, cy, t0 = key[0], key[1], burst["t0"]
    hr, ha = _g_halo(now, t0, _G_LAST_DUR, cell * 0.42)
    if ha > 0:
        cv.create_oval(cx - hr, cy - hr, cx + hr, cy + hr, fill="",
                       outline=_shade("#ffd75e", 0.05), width=2,
                       stipple=_g_stipple(ha), tags="_g_last_halo")
    drawn, _alive = _g_step_burst(burst["parts"], t0, now)
    for (x, y, s, a) in drawn:
        cv.create_oval(x - s, y - s, x + s, y + s, fill="#ffd75e",
                       outline="", stipple=_g_stipple(a), tags="_g_last_parts")


def _g_draw_win(cv, ui, now, w, anchors, breathing, on):
    """胜利动效：在棋子锚点上撒 ≤48 粒金色星点，循环复用持续飘升；
    顶栏 🏆 加一圈呼吸辉光。on=False（未获胜/平局）时清空状态。"""
    if not on:
        ui.pop("_g_win", None)
        return
    # 顶栏 🏆 光圈（呼吸辉光）
    ty = 23
    for k, mul in enumerate((1.0, 0.76, 0.52)):
        gg = _shade("#ffc93c", -0.10 + 0.14 * k)
        rr = 16 + 11 * mul
        cv.create_oval(w / 2 - rr, ty - rr, w / 2 + rr, ty + rr, fill="",
                       outline=gg, width=1,
                       stipple=_g_stipple(0.08 + 0.20 * mul * breathing),
                       tags="_g_win_ring")
    if not anchors:
        return
    lst = ui.get("_g_win")
    if lst is None:                        # 首次进入获胜状态 → 生成并交错首发
        lst = []
        for i in range(_G_PART_WIN_MAX):
            ax, ay = anchors[i % len(anchors)]
            p = _g_spawn_star(ax, ay, seed=i * 13 + 7)
            p["t0"] = now - (i % 12) * 0.05
            lst.append(p)
        ui["_g_win"] = lst
    for i, p in enumerate(lst):
        x, y, s, a, alive = _g_step_star(p, p["t0"], now)
        if not alive:                      # 生命周期结束 → 循环复用、换锚点重生
            ax, ay = anchors[i % len(anchors)]
            np_ = _g_spawn_star(ax, ay)
            np_["t0"] = now
            lst[i] = np_
            continue
        cv.create_oval(x - s, y - s, x + s, y + s, fill="#ffd75e",
                       outline="", stipple=_g_stipple(0.6 * a),
                       tags="_g_win_parts")


# ---------------------------------------------------------------------------
# 《卡牌质感》—— 出牌淡金描边 / 金色星点反馈 / 选牌呼吸
#
# 与棋子粒子同源：一律"纯时间推导"（输入 time.monotonic() 时间戳 + 粒子参数 →
# 输出要在 canvas 上画的形状），禁 after/线程/全局计时器，帧推进只借 ui['repaint']
# 的既有重绘链。状态（上次 key 触发串、星点粒子、计时 t0）跨帧存 ui dict，寿命
# 结束后自动清理、不残留；idle 无出牌时视觉与现状一致（不产生常驻辉光）。
# ---------------------------------------------------------------------------
_G_CARD_GLOW_DUR = 1.6        # 淡金描边辉光渐隐总时长（秒）
_G_CARD_STAR_MAX = 14         # 出牌/成组金色星点一簇数量上限（≤20，比胜利克制）
_G_CARD_STAR_DUR = 1.9        # 星点一簇最长寿命（覆盖 _g_spawn_star 最大 life）


def _g_card_gold_rect(cv, x0, y0, x1, y1, o_ring, i_ring, width):
    """在卡片外沿叠 2 层淡金描边（stipple 模拟半透明）+ 细亮边 —— 牌面浮雕浮起。
    纯绘制，无副作用。"""
    for ring, wgt in ((o_ring, width), (i_ring, width)):
        if not ring:
            continue
        cv.create_polygon(_rrect_pts(x0 - 5, y0 - 5, x1 + 5, y1 + 5, 9),
                          fill="", outline="#ffd75e", width=wgt,
                          smooth=True, splinesteps=24, stipple=ring,
                          tags="_pfx_gold")
    cv.create_polygon(_rrect_pts(x0 - 2, y0 - 2, x1 + 2, y1 + 2, 9),
                      fill="", outline="#ffcf6e", width=1, smooth=True,
                      splinesteps=24, tags="_pfx_gold_edge")


def _g_gold_edge(now, t0, dur=_G_CARD_GLOW_DUR):
    """刚出牌的淡金描边辉光强度：随年龄从亮到暗渐隐（并叠加轻微呼吸）。
    返回 (外层晕 stipple, 内层晕 stipple, 描边宽, alive)；结束后四者返回空/0/False。
    纯时间推导、恒落在合法 stipple 集，无副作用。"""
    age = now - t0
    if age < 0 or age >= dur:
        return "", "", 0, False
    k = 1.0 - age / dur                                  # 1→0 线性渐隐
    breath = 0.5 + 0.5 * math.sin(now * _G_BREATH_W)     # 呼吸微动
    return (_g_stipple(k * (0.16 + 0.16 * breath)),
            _g_stipple(k * (0.30 + 0.20 * breath)),
            2 if k > 0.35 else 1, True)


def _g_play_fx(cv, ui, now, key, cx, cy, cw, ch, repaint,
               glow_dur=_G_CARD_GLOW_DUR, stars=_G_CARD_STAR_MAX, base=0,
               glow=True):
    """出牌/成组卡牌质感：淡金描边渐隐 + 金色星点一簇（≤stars）。
    当 key（上一手/上一组的标识）变化 → 重建并计时；跨帧存 ui dict，
    寿命结束自动清理、不残留。纯时间推导，无 after/线程。"""
    # ---- 触发检测：key 变化才重建（避免每帧重生成）----
    if ui.get("_pfx_key") != key:
        ui["_pfx_key"] = key
        ui["_pfx_t0"] = now
        ui["_pfx_star"] = [_g_spawn_star(cx + cw / 2, cy + ch / 2,
                                         seed=base + i)
                           for i in range(min(int(stars), _G_CARD_STAR_MAX))]
        ui["_pfx_star_t0"] = now
    t0 = ui.get("_pfx_t0", now)
    any_glow = any_star = False
    # ---- 1) 淡金描边（渐隐 + 呼吸）----
    if glow:
        o_ring, i_ring, width, alive = _g_gold_edge(now, t0, glow_dur)
        if alive:
            _g_card_gold_rect(cv, cx, cy, cx + cw, cy + ch,
                              o_ring, i_ring, width)
            any_glow = True
    # ---- 2) 金色星点反馈 ----
    sp = ui.get("_pfx_star")
    if sp:
        st0 = ui["_pfx_star_t0"]
        for p in sp:
            x, y, s, a, al = _g_step_star(p, st0, now)
            if not al:
                continue
            cv.create_oval(x - s, y - s, x + s, y + s, fill="#ffd75e",
                           outline="", stipple=_g_stipple(0.7 * a),
                           tags="_pfx_star")
            any_star = True
        if not any_star and now - st0 > _G_CARD_STAR_DUR:
            ui.pop("_pfx_star", None)       # 全灭且超时 → 清理（防重复生成靠 _pfx_key）
    if (any_glow or any_star) and repaint is not None:
        _anim_need(ui, repaint, gap=0.04, cap=160)


def _g_card_breath_ring(cv, now, x0, y0, x1, y1, r=8):
    """可选/已选牌的外圈呼吸光环（复用 _g_breath 作轻微脉动，辅助视觉）。
    纯时间推导、无副作用；只在调用方显式传入时绘制（有 hover/选中交互的桌游）。"""
    b = _g_breath(now)
    pad = 5 + 2 * b
    cv.create_polygon(_rrect_pts(x0 - pad, y0 - pad, x1 + pad, y1 + pad, r),
                      fill="", outline="#ffd75e", width=2, smooth=True,
                      splinesteps=24, stipple=_g_stipple(0.12 + 0.28 * b),
                      tags="_selbreath")


def _g_rmk_table_change(prev_sig, table):
    """检测拉密桌面组变化：返回 (row_idx, is_new) 或 None。
    is_new=True 表示新增一行（新组），False 表示已有行接续变长。
    prev_sig 为上一帧每行张数的元组；首帧 prev 缺失不误发。纯函数。"""
    if prev_sig is None:
        return None
    cur = [len(r) for r in (table or [])]
    if len(cur) > len(prev_sig):                       # 新增一组：抽牌堆 append 到末尾
        return (len(prev_sig), True)
    for i in range(len(prev_sig)):
        if i >= len(cur):
            break
        if cur[i] != prev_sig[i]:                       # 已有行变长：接续入该组
            return (i, False)
    return None


# ---- kalah（播棋）板面动效：纯逻辑 + 纯时间推导，禁 after/线程 ----
def _g_kalah_pit_center(gi, a_holes, b_holes):
    """全局坑下标 gi → 画布中心像素：0..5=A洞(下排)、8..13=B洞(上排)；库(6/7)返回 None。
    纯查表函数，geometry 由调用方注入以便 headless 单测。"""
    if 0 <= gi < 6:
        return a_holes[gi]
    if 8 <= gi <= 13:
        return b_holes[gi - 8]
    return None


def _g_kalah_pit_change(prev, cur):
    """返回首个"子数"变化的坑位全局下标；无变化（或 prev 缺失）返回 None。纯函数。"""
    if prev is None:
        return None
    for i in range(min(len(prev), len(cur))):
        if prev[i] != cur[i]:
            return i
    return None


def _g_kalah_board_fx(cv, ui, now, cells, a_holes, b_holes, holeR, breathing,
                      last_center):
    """kalah 板面动效（纯时间推导，不做落子粒子）：
      1) 每坑一圈柔和呼吸辉光 —— idle 唯一视觉增量；
      2) 最近操作洞金色柔光高亮；
      3) 坑内子数变化时在对应坑发一个 0.45s 膨胀-渐隐小脉冲。"""
    # 1) 呼吸辉光环（12 坑）
    for (hx, hy) in list(a_holes) + list(b_holes):
        rr = holeR
        cv.create_oval(hx - rr * 1.25, hy - rr * 1.25, hx + rr * 1.25,
                       hy + rr * 1.25, fill="", outline=_shade("#ffd166", 0.85),
                       width=1, stipple=_g_stipple(0.05 + 0.10 * breathing),
                       tags="_k_glow")
    # 2) 子数变化 → 小脉冲（复用 _g_halo 膨胀渐隐）
    prev = ui.get("_k_counts")
    gi = _g_kalah_pit_change(prev, cells)
    ui["_k_counts"] = tuple(cells)
    if gi is not None:
        pc = _g_kalah_pit_center(gi, a_holes, b_holes)
        if pc is not None:
            ui["_k_pulse"] = {"cx": pc[0], "cy": pc[1], "t0": now}
    pul = ui.get("_k_pulse")
    if pul:
        PR, Pa = _g_halo(now, pul["t0"], 0.45, holeR)
        if Pa > 0:
            cv.create_oval(pul["cx"] - PR, pul["cy"] - PR,
                           pul["cx"] + PR, pul["cy"] + PR,
                           fill="", outline="#ffc93c", width=2,
                           stipple=_g_stipple(Pa), tags="_k_pulse")
        else:
            ui.pop("_k_pulse", None)
    # 3) 最近操作洞金色柔光高亮（持续呼吸，直到下一次操作）
    if last_center:
        lx, ly = last_center
        cv.create_oval(lx - holeR * 1.35, ly - holeR * 1.35,
                       lx + holeR * 1.35, ly + holeR * 1.35,
                       fill="", outline="#ffd75e", width=2,
                       stipple=_g_stipple(0.25 + 0.35 * breathing),
                       tags="_k_last")


@_register("gomoku")
def _p_gomoku(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["gomoku"][1]
    n = st.get("size") or 15
    title = flagship_status("gomoku", st, me, nick)
    _turn_banner(cv, w, 46, title, accent)
    ox, oy, cell = _fit(n, w, h, header=46)
    ui.update(ox=ox, oy=oy, cell=cell, n=n, rows=n, cols=n, game="gomoku")
    # 棋盘（纸面木纹底）加柔和投影
    _soft_shadow(cv, ox - 12, oy - 8, ox + n * cell + 8, oy + n * cell + 8,
                 6, 5)
    _paper_board(cv, ox - 10, oy - 10, ox + n * cell + 10, oy + n * cell + 10,
                 base="#f6f3e9", edge="#c8c2b0")
    for i in range(n):
        cv.create_line(ox, oy + i * cell, ox + (n - 1) * cell, oy + i * cell,
                       fill="#8a5a2b")
        cv.create_line(ox + i * cell, oy, ox + i * cell, oy + (n - 1) * cell,
                       fill="#8a5a2b")
    board = st.get("board") or []
    last = st.get("last_move")
    if isinstance(last, list) and len(last) == 2:
        last = tuple(last)                # 服务端可能是 list，统一成 tuple 便于比较
    now = time.monotonic()
    breathing = 0.0
    lastpx = None
    stone_anchors = []                     # 所有棋子中心，作胜利星点锚点
    if last and last[0] >= 0 and last[1] >= 0 and last[0] < n and last[1] < n:
        lastpx = (ox + last[0] * cell, oy + last[1] * cell)
    brd_h = len(board)
    for y in range(brd_h):
        for x in range(len(board[y])):
            v = board[y][x]
            if not v:
                continue
            cx, cy = ox + x * cell, oy + y * cell
            stone_anchors.append((cx, cy))
            _stone(cv, cx, cy, cell * 0.42,
                   "#111" if v == 1 else "#fff", "#888",
                   last == (x, y), glow=False, gint=breathing)
    _flagship_feedback(cv, ui, st, 5, now, lastpx)


@_register("connect4")
def _p_connect4(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["connect4"][1]
    board = st.get("board") or []
    cols = st.get("cols") or (len(board[0]) if board else 7)
    rows = len(board)
    title = flagship_status("connect4", st, me, nick)
    _turn_banner(cv, w, 46, title, accent)
    ox, oy, cell = _fit(cols, w, h, header=46)
    ui.update(ox=ox, oy=oy, cell=cell, n=cols, rows=rows, cols=cols, game="connect4")
    pad = cell * 0.08
    now = time.monotonic()
    breathing = 0.0
    last = st.get("last_move")             # (col, row)，board[y][x]
    lastpx = None
    stone_anchors = []                     # 棋子中心，作胜利星点锚点
    if last and len(last) == 2:
        c0, r0 = int(last[0]), int(last[1])
        if 0 <= c0 < cols and 0 <= r0 < rows:
            lastpx = (ox + c0 * cell + cell / 2, oy + r0 * cell + cell / 2)
    for x in range(cols):
        _text(cv, ox + (x + 0.5) * cell, oy - 8, str(x),
              "#45635b" if ui.get("can_move") and board and not board[0][x] else _MUTED)
        for y in range(rows):
            cx0, cy0 = ox + x * cell + pad, oy + y * cell + pad
            _etch_cell(cv, cx0, cy0, ox + (x + 1) * cell - pad,
                       oy + (y + 1) * cell - pad,
                       "#708798", "#596f80")
            v = board[y][x]
            rr = (cell - pad * 2) / 2 - 1
            cxc, cyc = cx0 + (cell - pad * 2) / 2, cy0 + (cell - pad * 2) / 2
            if v == 1:
                stone_anchors.append((cxc, cyc))
                _stone(cv, cxc, cyc, rr, "#e05555", "#a02f2f",
                       glow=False, gint=breathing)
            elif v == 2:
                stone_anchors.append((cxc, cyc))
                _stone(cv, cxc, cyc, rr, "#f2c844", "#b08a14",
                       glow=False, gint=breathing)
    _flagship_feedback(cv, ui, st, 4, now, lastpx)


@_register("othello")
def _p_othello(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["othello"][1]
    n = st.get("size") or 8
    title = "◐ 奥赛罗"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 获胜"
    elif st.get("turn_uid"):
        title += f"　轮到 {nick(st['turn_uid'])}" + (
                    "（对手无处可下，你续盘）" if st.get("passing") else "")
    _turn_banner(cv, w, 46, title, accent)
    ox, oy, cell = _fit(n, w, h, header=46)
    ui.update(ox=ox, oy=oy, cell=cell, n=n, game="othello")
    cv.create_rectangle(ox - 6, oy - 6, ox + n * cell + 6, oy + n * cell + 6,
                        fill="#2f7d3a", outline="#1e5226", width=2)
    board = st.get("board") or []
    now = time.monotonic()
    breathing = _g_breath(now)             # 呼吸辉光强度（纯时间推导）
    last = st.get("last_move")             # (x, y)，board[y][x]
    lastpx = None
    stone_anchors = []                     # 棋子中心，作胜利星点锚点
    if last and len(last) == 2:
        lx, ly = int(last[0]), int(last[1])
        if 0 <= lx < n and 0 <= ly < n:
            lastpx = (ox + lx * cell + cell / 2, oy + ly * cell + cell / 2)
    for y in range(n):
        for x in range(n):
            cv.create_rectangle(ox + x * cell, oy + y * cell,
                                ox + (x + 1) * cell, oy + (y + 1) * cell,
                                fill="", outline="#1e5226")
            v = board[y][x]
            if v:
                cx, cy = ox + x * cell + cell / 2, oy + y * cell + cell / 2
                stone_anchors.append((cx, cy))
                _stone(cv, cx, cy, cell * 0.42,
                       "#111111" if v == 1 else "#ffffff", "#999999",
                       glow=True, gint=breathing)
    if st.get("scores"):
        vals = list(st["scores"].values())
        if len(vals) == 2:
            _text(cv, w - ox - 6, oy - 2, f"⚫{vals[0]}　⚪{vals[1]}",
                  _WHITE, _FONT_F, anchor="ne")
    # ---- 动效：落子光晕/微粒子 + 胜利星点（同 gomoku 范式，数量封顶）----
    on_win = st.get("winner_uid") is not None
    _g_draw_last(cv, ui, now, lastpx, cell)
    _g_draw_win(cv, ui, now, w, stone_anchors, breathing, on_win)
    _anim_need(ui, repaint, gap=0.04, cap=180)


@_register("tictactoe")
def _p_tictactoe(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["tictactoe"][1]
    n = 3
    title = "⭕ 井字棋"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 获胜"
    elif st.get("draw"):
        title = "平局"
    elif st.get("turn_uid"):
        title += f"　轮到 {nick(st['turn_uid'])}"
    _turn_banner(cv, w, 46, title, accent)
    ox, oy, cell = _fit(n, w, h, header=46)
    ui.update(ox=ox, oy=oy, cell=cell, n=n, game="tictactoe")
    _paper_board(cv, ox - 6, oy - 6, ox + n * cell + 6, oy + n * cell + 6,
                 base="#f6f4ee", edge="#bbbbbb")
    board = st.get("board") or []
    now = time.monotonic()
    breathing = _g_breath(now)             # 呼吸辉光强度（纯时间推导，idle 唯一增量）
    last = st.get("last_move")             # (x, y)
    lastpx = None
    anchors = []                           # 棋子中心，作胜利星点锚点
    if last and len(last) == 2:
        lx, ly = int(last[0]), int(last[1])
        if 0 <= lx < n and 0 <= ly < n:
            lastpx = (ox + lx * cell + cell / 2, oy + ly * cell + cell / 2)
    for i in range(1, n):
        cv.create_line(ox + i * cell, oy, ox + i * cell, oy + n * cell,
                       fill="#555555", width=2)
        cv.create_line(ox, oy + i * cell, ox + n * cell, oy + i * cell,
                       fill="#555555", width=2)
    for y in range(n):
        for x in range(n):
            v = board[y][x]
            cxc, cyc = ox + x * cell + cell / 2, oy + y * cell + cell / 2
            r = cell * 0.34
            if v == 1:
                anchors.append((cxc, cyc))
                _stone(cv, cxc, cyc, r, "#111111", "#888888",
                       glow=True, gint=breathing)
            elif v == 2:
                anchors.append((cxc, cyc))
                _g_piece_glow(cv, cxc, cyc, r, "#e05555", breathing)
                cv.create_oval(cxc - r, cyc - r, cxc + r, cyc + r,
                               fill=_shade("#e05555", 0.10), outline="#e05555",
                               width=int(cell * 0.12))
                cv.create_oval(cxc - r * 0.55, cyc - r * 0.68,
                               cxc + r * 0.55, cyc - r * 0.05,
                               fill=_shade("#e05555", 0.45), outline="")
    # ---- 动效：落子光晕/微粒子 + 胜利星点（纯时间推导，数量封顶）----
    _g_draw_last(cv, ui, now, lastpx, cell)
    _g_draw_win(cv, ui, now, w, anchors, breathing,
                st.get("winner_uid") is not None)
    _anim_need(ui, repaint, gap=0.04, cap=180)


@_register("kalah")
def _p_kalah(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["kalah"][1]
    p0, p1 = st.get("p0"), st.get("p1")
    cells = st.get("cells") or []
    title = "🥜 非洲播棋"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 获胜"
    else:
        title += f"　轮到 {nick(st['turn']) }"
    _turn_banner(cv, w, 46, title, accent)
    # 布局：上排 B(13..8)+B库，下排 A库+A洞(0..5)
    storeW = 78
    holeR = min(30, (w - storeW * 2 - 60) / 12)
    if holeR < 8:
        holeR = 8
    topY, botY = 96, h - 120
    cx_start = storeW + 30
    span = holeR * 12
    start = (w - span) / 2
    holes = []
    # A 洞底部（0..5，玩家 A 视角），点自己的洞
    a_holes = [(start + i * holeR * 2 + holeR, botY) for i in range(6)]
    b_holes = [(start + i * holeR * 2 + holeR, topY) for i in range(6)]
    for label, cy, is_p0, is_p1 in (
            ("A", botY, True, False), ("B", topY, False, True)):
        who = p0 if is_p0 else p1
        own = who == me
        nm = nick(who)
        if len(nm) > 10:
            nm = nm[:9] + "…"
        tag = f"{label}·{nm}" + ("（你）" if own else "")
        tw = 14 + len(tag) * 9
        fill = _shade("#8a5fbf", 0.28) if st.get("turn") == who else _PANEL
        if is_p0:                        # A 行：左缘（右端是 A 库）
            x0 = 8
        else:                             # B 行：右缘（左端是 B 库）
            x0 = w - 8 - tw
        cv.create_rectangle(x0, cy - 11, x0 + tw, cy + 11, fill=fill,
                            outline=_PANEL_BD, width=1)
        _text(cv, x0 + tw / 2, cy, tag,
              "#8a5fbf" if own else "#4a3b32", (_FONT_F[0], 9))
    # 库（竖向胶囊，附顶部反光）
    cv.create_oval(start - storeW, topY - holeR, start - 40, topY + holeR,
                   fill=_PANEL, outline=_PANEL_BD, width=2)
    cv.create_oval(start - storeW + 5, topY - holeR + 3, start - 40 - 6,
                   topY - holeR // 3, fill=_shade(_PANEL, 0.45), outline="")
    _text(cv, start - 40 - 19, topY, str(cells[7]) if len(cells) > 7 else "0",
          "#333", _FONT_B)
    _text(cv, start - 40 - 19, topY + 26, f"B（{nick(p1)}）", _MUTED, (_FONT_F[0], 8))
    cv.create_oval(w - start + 40, botY - holeR, w - start + storeW, botY + holeR,
                   fill=_PANEL, outline=_PANEL_BD, width=2)
    cv.create_oval(w - start + 40 + 5, botY - holeR + 3, w - start + storeW - 6,
                   botY - holeR // 3, fill=_shade(_PANEL, 0.45), outline="")
    _text(cv, w - start + 40 + 19, botY, str(cells[6]) if len(cells) > 6 else "0",
          "#333", _FONT_B)
    _text(cv, w - start + 40 + 19, botY + 26, f"A（{nick(p0)}）", _MUTED, (_FONT_F[0], 8))

    for i, (hx, hy) in enumerate(a_holes):
        mine = (st.get("turn") == me and me == p0)
        fill = _shade("#8a5fbf", 0.25) if mine and i < 6 else _PANEL
        _disc(cv, hx, hy, holeR, fill, outline=_PANEL_BD)
        v = cells[i] if len(cells) > i else 0
        _text(cv, hx, hy, str(v), "#333", _FONT_B)
        holes.append((hx, hy, holeR, i))
    for j, (hx, hy) in enumerate(b_holes):
        idx = 8 + j
        mine = (st.get("turn") == me and me == p1)
        fill = _shade("#8a5fbf", 0.25) if mine and len(cells) > idx else _PANEL
        _disc(cv, hx, hy, holeR, fill, outline=_PANEL_BD)
        v = cells[idx] if len(cells) > idx else 0
        _text(cv, hx, hy, str(v), "#333", _FONT_B)
    ui.update(game="kalah", me=me, holes=holes)

    # ---- 板面动效（纯时间推导，复用 _g_breath/_g_halo，粒子全部复用胜利星点）----
    now = time.monotonic()
    breathing = _g_breath(now)
    # 「最近操作洞」：last = (pid, hole, ...)，pid 侧对洞位 calc
    lastc = None
    _lmv = st.get("last")
    if _lmv and len(_lmv) >= 2 and _lmv[1] is not None:
        _pid, _hole = _lmv[0], _lmv[1]
        if _pid == p0 and 0 <= _hole < 6:
            lastc = a_holes[_hole]
        elif _pid == p1 and 0 <= _hole < 6:
            lastc = b_holes[_hole]
    _g_kalah_board_fx(cv, ui, now, cells, a_holes, b_holes, holeR, breathing,
                      lastc)
    # 胜利：在获胜方一侧(坑位)撒金色星点 + 🏆 光环
    on_win = st.get("winner_uid") is not None
    w_anchors = []
    if on_win:
        wid = st.get("winner_uid")
        if wid == p0:
            w_anchors = a_holes
        elif wid == p1:
            w_anchors = b_holes
        else:
            w_anchors = list(a_holes) + list(b_holes)
    _g_draw_win(cv, ui, now, w, w_anchors, breathing, on_win)
    _anim_need(ui, repaint, gap=0.04, cap=180)


@_register("chess")
def _p_chess(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    _xiangqi_chess(cv, st, me, nick, submit, repaint, ui, priv, w, h,
                   kind="chess")


@_register("xiangqi")
def _p_xiangqi(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    _xiangqi_chess(cv, st, me, nick, submit, repaint, ui, priv, w, h,
                   kind="xiangqi")


def _xiangqi_chess(cv, st, me, nick, submit, repaint, ui, priv, w, h, kind="xiangqi"):
    accent = THEME[kind][1]
    board = st.get("board") or []
    if kind == "xiangqi":
        n = st.get("cols") or 9
        m = st.get("rows") or len(board)
        title = "♟ 中国象棋"
        board_color, grid = "#ebd3a8", "#7a5a2a"
    else:
        n = m = st.get("size") or 8
        title = "♞ 国际象棋"
        board_color, grid = "#c89b7a", "#000"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 获胜"
    elif st.get("turn_uid"):
        title += f"　轮到 {nick(st['turn_uid'])}"
    _turn_banner(cv, w, 46, title, accent)
    ox, oy, cell = _fit(n, w, h, header=46)
    ui.update(ox=ox, oy=oy, cell=cell, n=n, game=kind)
    sel = (ui.get("sel") or {}).get("game") == kind and (
        ui.get("sel", {}).get("fx"), ui.get("sel", {}).get("fy"))
    for y in range(m):
        for x in range(n):
            cx0, cy0 = ox + x * cell, oy + y * cell
            if kind == "chess" and (x + y) % 2 == 0:
                _etch_cell(cv, cx0, cy0, cx0 + cell, cy0 + cell,
                           "#d9b38c", grid)
            elif kind == "xiangqi" and (x + y) % 2 == 0:
                # 象棋单色格加极淡棋盘微差，提升格感而不破坏楚河汉界辨识
                _etch_cell(cv, cx0, cy0, cx0 + cell, cy0 + cell,
                           _shade(board_color, 0.045), grid)
            else:
                _etch_cell(cv, cx0, cy0, cx0 + cell, cy0 + cell,
                           board_color, grid)
    if kind == "xiangqi":
        for i in range(1, n):
            cv.create_line(ox + i * cell, oy, ox + i * cell, oy + m * cell,
                           fill=grid)
        for i in range(1, m):
            cv.create_line(ox, oy + i * cell, ox + n * cell, oy + i * cell,
                           fill=grid)
    piece_name = {1: "帅", 2: "仕", 3: "相", 4: "马", 5: "车", 6: "炮", 7: "兵",
                  11: "将", 12: "士", 13: "象", 14: "马", 15: "车", 16: "炮", 17: "卒"}
    now = time.monotonic()
    breathing = _g_breath(now)             # 呼吸辉光强度（纯时间推导，idle 唯一增量）
    anchors = []                           # 棋子中心，作胜利星点锚点（降级：棋无 last_move）
    for y in range(m):
        for x in range(n):
            v = board[y][x]
            if not v:
                continue
            cx, cy = ox + x * cell + cell / 2, oy + y * cell + cell / 2
            anchors.append((cx, cy))
            if (x, y) == sel:
                _sel_mark(cv, cx, cy, cell * 0.46, "#ff9800")
            if kind == "xiangqi":
                name = piece_name.get(v, str(v % 10 or v))
                fg = "#c0392b" if v <= 10 else "#1b1b1b"
                _g_piece_glow(cv, cx, cy, cell * 0.4, "#f7e9cd", breathing)
                cv.create_oval(cx - cell * 0.4, cy - cell * 0.4,
                               cx + cell * 0.4, cy + cell * 0.4,
                               fill="#f7e9cd", outline=fg, width=2)
                _text(cv, cx, cy, name, fg, (_FONT_B[0], int(cell * 0.46)))
            else:
                sym = {1: "♚", 2: "♛", 3: "♜", 4: "♝", 5: "♞", 6: "♟",
                       11: "♔", 12: "♕", 13: "♖", 14: "♗", 15: "♘", 16: "♙"}.get(v, "")
                _g_piece_glow(cv, cx, cy, cell * 0.5,
                              "#ffffff" if v <= 6 else "#1b1b1b", breathing)
                _text(cv, cx, cy, sym, "#1b1b1b"
                      if v <= 6 else "#ffffff", (_FONT_BIG[0], int(cell * 0.7)))
    # ---- 动效（降级）：只做辉光 + 胜利星点（数量封顶 ≤48）----
    _g_draw_win(cv, ui, now, w, anchors, breathing,
                st.get("winner_uid") is not None)
    _anim_need(ui, repaint, gap=0.04, cap=180)


@_register("go")
def _p_go(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["go"][1]
    n = st.get("size") or 19
    title = "⚫⚪ 围棋"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 获胜"
    elif st.get("over"):
        title = "终局"
    elif st.get("turn_uid"):
        title += f"　轮到 {nick(st['turn_uid'])}"
    capt = st.get("captured") or [0, 0]
    if isinstance(capt, (list, tuple)) and len(capt) == 2:
        cap = f"黑吞{capt[0]} · 白吞{capt[1]}"
    elif isinstance(capt, dict) and capt:
        cap = "　·　".join(
            f"{nick(int(u))} 吃{c}c" for u, c in sorted(capt.items()))
    else:
        cap = ""
    if cap:
        title += ("　" + cap)
    _turn_banner(cv, w, 46, title, accent)
    ox, oy, cell = _fit(n, w, h, header=46)
    ui.update(ox=ox, oy=oy, cell=cell, n=n, game="go")
    _paper_board(cv, ox - cell, oy - cell, ox + n * cell + cell,
                 oy + n * cell + cell, base="#e4bf72", edge="#c9a05a")
    for i in range(n):
        cv.create_line(ox, oy + i * cell, ox + (n - 1) * cell, oy + i * cell,
                       fill="#7a5a2a")
        cv.create_line(ox + i * cell, oy, ox + i * cell, oy + (n - 1) * cell,
                       fill="#7a5a2a")
    if n in (9, 13, 19):
        for y in (3, n - 4 if n > 9 else n // 2):
            for x in (3, n - 4 if n > 9 else n // 2):
                cv.create_oval(ox + x * cell - 2, oy + y * cell - 2,
                               ox + x * cell + 2, oy + y * cell + 2, fill="#7a5a2a")
    cv.create_text(ox - 14, oy + n * cell + cell / 2,
                   text="点交叉点落子 · 过一手", anchor="w", font=(_FONT_F[0], 9),
                   fill=_MUTED)
    board = st.get("board") or []
    now = time.monotonic()
    breathing = _g_breath(now)             # 呼吸辉光强度（纯时间推导，idle 唯一增量）
    anchors = []                           # 棋子中心，作胜利星点锚点（降级：围棋无 last_move）
    for y in range(n):
        for x in range(n):
            v = board[y][x]
            if not v:
                continue
            cx, cy = ox + x * cell, oy + y * cell
            anchors.append((cx, cy))
            _stone(cv, cx, cy, cell * 0.44,
                   "#111111" if v == 1 else "#ffffff", "#888888",
                   glow=True, gint=breathing)
    # ---- 动效（降级）：缺 last_move 只做辉光 + 胜利星点（数量封顶 ≤48）----
    _g_draw_win(cv, ui, now, w, anchors, breathing,
                st.get("winner_uid") is not None)
    _anim_need(ui, repaint, gap=0.04, cap=180)


@_register("uno")
def _p_uno(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["uno"][1]
    title = "🃏 UNO"
    if st.get("match_winner"):
        title = f"🏆 {nick(st['match_winner'])} 赢得整局"
    elif st.get("winner_uid"):
        title = f"🏆 {nick(st['winner_uid'])} 出完手牌"
    elif st.get("current_uid"):
        title += f"　轮到 {nick(st['current_uid'])}"
    _turn_banner(cv, w, 46, title, accent)
    ccmap = {"red": "#e05555", "yellow": "#f2c94c", "green": "#4a9b5f",
             "blue": "#4a7de0"}
    # 弃牌堆顶
    top = st.get("top")
    _text(cv, w / 2 - 130, 100, "弃牌堆顶", _MUTED, _FONT_F)
    if top:
        # 卡牌浮雕：弃牌堆顶加柔和投影，让牌在桌面上更"浮起"
        _soft_shadow(cv, w / 2 - 150, 96, w / 2 - 150 + 100, 96 + 140, 10, 3)
        _draw_uno_card(cv, w / 2 - 150, 96, 100, 140, top, ccmap, _FONT_BIG)
        # 刚出的牌（top 即上一手）：淡金描边呼吸渐隐 + 金色星点一簇（≤14，纯时间推导）
        _g_play_fx(cv, ui, time.monotonic(), top,
                   w / 2 - 150, 96, 100, 140, repaint, base=3)
    _text(cv, w / 2 + 60, 100, "方向 " + st.get("direction", "→"), _MUTED, _FONT_F)
    hc = st.get("hand_counts") or {}
    _text(cv, w / 2 + 60, 130, "牌数：" + "　".join(
        f"{nick(int(u))}:{c}" for u, c in sorted(hc.items())), _MUTED, _FONT_F)
    # 手牌（私有）
    hand = []
    hand_ids = []
    if priv and isinstance(priv.get("hand"), list):
        hand = priv["hand"]
        hand_ids = priv.get("hand_ids") or list(range(len(hand)))
    if hand:
        _text(cv, w / 2, h - 40, "你的手牌（点击出牌）", _MUTED, _FONT_F)
        cw, ch = 64, 92
        gap = 6
        total = len(hand) * (cw + gap) - gap
        x0 = (w - total) / 2
        cards = []
        rects = []
        for i, cstr in enumerate(hand):
            cx0 = x0 + i * (cw + gap)
            y0 = h - 150
            _soft_shadow(cv, cx0, y0 + 2, cx0 + cw, y0 + ch, 8, 3)
            on, dy = _lift(cv, ui, i, cx0, y0, cx0 + cw, y0 + ch, 9, "#ffd75e")
            if on:                     # 悬停牌加轻微呼吸光环辅助视觉（复用 _g_breath）
                _g_card_breath_ring(cv, time.monotonic(), cx0, y0,
                                    cx0 + cw, y0 + ch)
            _draw_uno_card(cv, cx0, y0 + dy, cw, ch, cstr, ccmap, _FONT_B)
            cards.append((cx0, y0, cx0 + cw, y0 + ch, hand_ids[i]))
            rects.append((cx0, y0 - 18, cx0 + cw, y0 + ch))
        _hov_rects(ui, rects)
        ui.update(game="uno", cards=cards)
    ui.update(me=me)


def _draw_uno_card(cv, x0, y0, w, h, cstr, ccmap, font):
    col = "#2c2c2c"
    sym = cstr or "?"
    if cstr:
        head = cstr[0]
        if head in ccmap:
            col = ccmap[head]
            sym = cstr[1:]
    fg = "#fff" if _luma(col) < 150 else "#222"
    cv.create_rectangle(x0, y0, x0 + w, y0 + h, fill=col, outline="#fff",
                        width=2)
    cv.create_oval(x0 + w * 0.14, y0 + h * 0.14, x0 + w * 0.86,
                   y0 + h * 0.86, outline="#fff", width=2)
    _text(cv, x0 + w / 2, y0 + h / 2, sym, fg, font)


@_register("blackjack")
def _p_blackjack(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["blackjack"][1]
    title = "🂠 21点"
    if st.get("results"):
        _text(cv, w / 2, 30, "结算：" + "，".join(
            f"{nick(int(u))} {'胜' if r=='win' else '平' if r=='draw' else '负'}"
            for u, r in st["results"].items()), _WHITE, _FONT_B)
    _turn_banner(cv, w, 46, title, accent)
    hands = st.get("hands") or {}
    y = 150
    # 庄家
    _text(cv, 30, y - 14, "庄家", _MUTED, _FONT_F, anchor="w")
    deal = st.get("dealer") or []
    for i, c in enumerate(deal):
        _draw_poker(cv, 30 + i * 62, y, c, i == 0)
    y += 92
    for u, cards in hands.items():
        who = "我" if int(u) == me else nick(int(u))
        _text(cv, 30, y - 6, who + f"（{st.get('hand_values', {}).get(u,'')}点）",
              _MUTED, _FONT_F, anchor="w")
        for i, c in enumerate(cards):
            _draw_poker(cv, 30 + i * 58, y, c, False)
        y += 88


def _draw_poker(cv, x, y, cstr, face_down=False):
    w, h = 52, 78
    _soft_shadow(cv, x, y + 2, x + w, y + h, 6, 2)
    if face_down:
        _rrect(cv, x, y, x + w, y + h, 6, "#3a5aa0", "#27457d", 1)
        _text(cv, x + w / 2, y + h / 2, "🂠", "#ffffff", _FONT_B)
        return
    rank = cstr[0] if cstr else ""
    suit = cstr[1] if len(cstr) > 1 else ""
    red = rank in ("♠", "♣") or suit in ("♠", "♣")
    fg = "#c0392b" if red else "#1b1b1b"
    _rrect(cv, x, y, x + w, y + h, 6, "#ffffff", "#cccccc", 1)
    _text(cv, x + 8, y + 8, rank, fg, (_FONT_B[0], 14), anchor="nw")
    _text(cv, x + w / 2, y + h / 2, suit, fg, (_FONT_B[0], 20))


@_register("rps")
def _p_rps(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["rps"][1]
    phase = st.get("phase", "collecting")
    title = "✊✌️✋ 石头剪刀布"
    if phase == "collecting":
        title += f"　已出拳 {len(st.get('submitted') or [])}/{len(st.get('players') or [])}"
    else:
        title += "　揭晓中…"
    _turn_banner(cv, w, 46, title, accent)
    icons = ["✊", "✋", "✌️"]
    sizes = [("石头", 0), ("剪刀", 1), ("布", 2)]
    gap = 90
    bgx = (w - (gap * 3)) / 2 + gap / 2
    y = h / 2 + 20
    # 三个大图标展示
    for i, (name, code) in enumerate(sizes):
        cx = bgx + i * gap
        f = _shade(accent, 0.35)
        cv.create_oval(cx - 44, y - 44, cx + 44, y + 44, fill=f, outline=_WHITE,
                       width=2)
        _text(cv, cx, y, icons[code], _WHITE, (_FONT_BIG[0], 30))
        _text(cv, cx, y + 64, name, _MUTED, _FONT_F)
    # 已出拳名单
    subm = st.get("submitted") or []
    if subm:
        _text(cv, w / 2, y - 100, "已出拳：" + "　".join(nick(int(u)) for u in subm),
              _MUTED, _FONT_F)
    # 最近战报
    matches = st.get("matches")
    if matches:
        _text(cv, w / 2, h - 30, "上轮：请见日志", _MUTED, _FONT_F)


@_register("calc24")
def _p_calc24(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["calc24"][1]
    title = "➗ 24点"
    if st.get("solved_uid") is not None:
        title = f"🎉 {nick(st['solved_uid'])} 答对！{st.get('win_expr','')}"
    else:
        title += f"　第 {st.get('round',1)} 轮"
    _turn_banner(cv, w, 46, title, accent)
    cards = st.get("cards") or []
    cw, ch = 86, 120
    total = len(cards) * (cw + 16) - 16
    x0 = (w - total) / 2
    for i, v in enumerate(cards):
        cx = x0 + i * (cw + 16)
        cv.create_rectangle(cx, h / 2 - 60, cx + cw, h / 2 - 60 + ch,
                            fill="#fff", outline="#ccc", width=2)
        _text(cv, cx + cw / 2, h / 2 - 60 + ch / 2, str(v), "#333", _FONT_BIG)
    _text(cv, w / 2, h / 2 - 95, "用 + - × ÷ 凑出 24（答案写进下方输入框）",
          _MUTED, _FONT_F)
    sc = st.get("scores") or {}
    if sc:
        _text(cv, w / 2, h - 40, "积分：" + "　".join(
            f"{nick(int(u))}:{v}" for u, v in sorted(sc.items())), _MUTED, _FONT_F)


@_register("coc")
def _p_coc(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["coc"][1]
    phase = st.get("phase", "setup")
    kp = st.get("kp_uid")
    title = "🔮 克苏鲁呼唤"
    if kp is not None:
        title += f"　KP：{nick(kp)}"
    _turn_banner(cv, w, 46, title, accent)
    if phase == "play" and priv and priv.get("card"):
        c = priv["card"]
        _text(cv, w / 2, 90, f"{c.get('emoji','')} 调查员：{c['name']}",
              "#333", _FONT_B)
        attrs = c.get("attrs") or {}
        y = 130
        _text(cv, w / 2, y, "属性：" + "　".join(f"{k} {v}" for k, v in attrs.items()),
              "#444", _FONT_F)
        sig = c.get("sig") or {}
        y += 34
        _text(cv, w / 2, y, "技能：" + "　".join(f"{k} {v}" for k, v in sig.items()),
              "#444", _FONT_F)
        _text(cv, w / 2, y + 50, "场景：", _MUTED, _FONT_F, anchor="center")
        _text(cv, w / 2, y + 80, st.get("scene") or "（KP 尚未发布）",
              "#555", _FONT_F, anchor="center")
    elif phase == "setup" and priv and priv.get("deck"):
        deck = priv["deck"]
        _text(cv, w / 2, 80, "选择你的调查员（点击卡片）", _MUTED, _FONT_F)
        cw, ch = 150, 84
        gap = 16
        per = max(1, int((w - 40) / (cw + gap)))
        cards = []
        for i, c in enumerate(deck):
            row, col = divmod(i, per)
            cx0 = (w - (min(per, len(deck) - row * per)) * (cw + gap) - gap) / 2 \
                if col == 0 else None
            if col == 0:
                cards_row = deck[row * per: row * per + per]
                base = (w - (len(cards_row) * (cw + gap) - gap)) / 2
            cx = base + col * (cw + gap)
            cy = 120 + row * (ch + gap)
            cores = st.get("picked") or {}
            taken = any(v == c["id"] for v in cores.values())
            fill = "#efefef" if taken else "#fff"
            _rrect(cv, cx, cy, cx + cw, cy + ch, 10, fill, _PANEL_BD)
            _text(cv, cx + cw / 2, cy + 22, f"{c.get('emoji','')} {c['name']}",
                  "#333", _FONT_B)
            _text(cv, cx + cw / 2, cy + 46, c.get("desc") or "", _MUTED,
                  (_FONT_F[0], 8), anchor="center")
            if taken:
                _text(cv, cx + cw - 12, cy + 12, "已选", "#c0392b", (_FONT_F[0], 9),
                      anchor="ne")
            cards.append((cx, cy, cx + cw, cy + ch, c["id"]))
        ui.update(game="coc", cards=cards)


@_register("werewolf")
def _p_werewolf(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["werewolf"][1]
    phase = st.get("phase", "")
    title = f"🐺 狼人杀 · 第 {st.get('night',1)} 夜"
    # 阶段文案与 client.py 的 werewolf 统计保持一致（内部阶段名：night_seer/night_wolf/night_witch/shoot/day/done）
    ph = {"night_seer": "预言家验人", "night_wolf": "狼人刀人",
          "night_witch": "女巫用药", "shoot": "猎人开枪",
          "day": "白天投票", "done": "已结束"}.get(phase, phase)
    title += f"　【{ph}】"
    if st.get("winner") is not None:
        title = f"🏆 {nick(st['winner'])} 阵营获胜"
    _turn_banner(cv, w, 46, title, accent)
    if priv and priv.get("name"):
        _text(cv, w / 2, 92, f"你的身份：{priv['name']}", "#333", _FONT_B)
    alive = st.get("alive") or []
    players = st.get("players") or []
    need = set(st.get("need") or [])
    cw, ch = 118, 66
    gap = 14
    per = max(1, int((w - 40) / (cw + gap)))
    y0 = 150
    for i, u in enumerate(players):
        row, col = divmod(i, per)
        cards_row = players[row * per: row * per + per]
        base = (w - (len(cards_row) * (cw + gap) - gap)) / 2
        cx = base + col * (cw + gap)
        cy = y0 + row * (ch + gap)
        alive_now = u in alive
        acting = u in need
        fill = "#5e1f2e" if alive_now else "#3a3a3a"
        if acting:
            fill = _shade("#c0392b", 0.3)
        _rrect(cv, cx, cy, cx + cw, cy + ch, 10, fill,
               "#ffd75e" if u == me else _PANEL, 2 if u == me else 1)
        _text(cv, cx + cw / 2, cy + 24,
              nick(u) + ("（我）" if u == me else ""), "#fff", _FONT_B,
              anchor="center")
        _text(cv, cx + cw / 2, cy + 46, "存活" if alive_now else "死亡",
              "#ffd75e" if alive_now else "#999", (_FONT_F[0], 9))
        if acting:
            _text(cv, cx + cw - 10, cy + 10, "行动", "#ffd75e", (_FONT_F[0], 9),
                  anchor="ne")
    # 当前需要行动者提示
    if need:
        _text(cv, w / 2, h - 24, "需行动：" + "　".join(nick(int(u)) for u in need),
              _MUTED, _FONT_F)


@_register("avalon")
def _p_avalon(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["avalon"][1]
    title = f"⚔️ 阿瓦隆 · 第 {st.get('quest',1)} 任务（尝试 {st.get('attempt',1)}）"
    if st.get("winner") is not None:
        title = f"🏆 胜利：{nick(st['winner'])}"
    _turn_banner(cv, w, 46, title, accent)
    if priv and priv.get("name"):
        _text(cv, w / 2, 88, f"你的身份：{priv['name']}", "#333", _FONT_B)
    leader = st.get("leader")
    if leader is not None:
        _text(cv, w / 2, 112, f"领袖：{nick(leader)}", _MUTED, _FONT_F)
    team = st.get("team") or []
    if team:
        _text(cv, w / 2, 136, f"团队：{'、'.join(nick(int(u)) for u in team)}",
              "#444", _FONT_F)
    players = st.get("players") or []
    cw, ch = 108, 64
    gap = 14
    per = max(1, int((w - 40) / (cw + gap)))
    y0 = 176
    for i, u in enumerate(players):
        row, col = divmod(i, per)
        cards_row = players[row * per: row * per + per]
        base = (w - (len(cards_row) * (cw + gap) - gap)) / 2
        cx = base + col * (cw + gap)
        cy = y0 + row * (ch + gap)
        in_team = u in team
        fill = "#3f5c7d" if in_team else "#55637a"
        _rrect(cv, cx, cy, cx + cw, cy + ch, 10, fill,
               "#ffd75e" if u == me else _PANEL, 2 if u == me else 1)
        _text(cv, cx + cw / 2, cy + 26, nick(u) + ("（我）" if u == me else ""),
              "#fff", _FONT_B)
        _text(cv, cx + cw / 2, cy + 46, "在队" if in_team else "是否赞成？",
              _MUTED, (_FONT_F[0], 9))
    # 任务结果
    results = st.get("results") or []
    if results:
        _text(cv, w / 2, h - 24, "任务结果：" + " ".join(
            f"{st and '✔' if r else '✘'}" for r in results), _MUTED, _FONT_F)


@_register("spy")
def _p_spy(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["spy"][1]
    phase = st.get("phase", "")
    title = "🕵️ 谁是卧底"
    ph = {"dealing": "发牌中", "describing": "描述中", "voting": "投票中",
          "checking": "统计票数", "reveal": "身份揭晓"}.get(phase, phase)
    title += f"　【{ph}】"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])}"
    _turn_banner(cv, w, 46, title, accent)
    if priv and priv.get("word"):
        role = priv.get("role")
        fg = "#c0392b" if role == "spy" else "#1f5236"
        _text(cv, w / 2, 92, f"你：{role == 'spy' and '🕵️ 卧底' or '😇 平民'}"
                             f" · 词：{priv['word']}", fg, _FONT_B)
    if st.get("speaker_uid") is not None:
        _text(cv, w / 2, 118, f"当前描述：{nick(st['speaker_uid'])}", _MUTED, _FONT_F)
    alive = st.get("alive") or []
    cw, ch = 96, 60
    gap = 14
    per = max(1, int((w - 40) / (cw + gap)))
    y0 = 158
    for i, u in enumerate(alive):
        row, col = divmod(i, per)
        cards_row = alive[row * per: row * per + per]
        base = (w - (len(cards_row) * (cw + gap) - gap)) / 2
        cx = base + col * (cw + gap)
        cy = y0 + row * (ch + gap)
        _rrect(cv, cx, cy, cx + cw, cy + ch, 10,
               _shade("#5d4592", 0.35), "#5d4592" if u == me else _PANEL,
               2 if u == me else 1)
        _text(cv, cx + cw / 2, cy + 26, nick(u) + ("（我）" if u == me else ""),
              "#fff", _FONT_B)
    # 得分
    sc = st.get("scores") or {}
    if sc:
        _text(cv, w / 2, h - 24, "积分：" + "　".join(
            f"{nick(int(u))}:{v}" for u, v in sorted(sc.items())), _MUTED, _FONT_F)


# ---------------------------------------------------------------------------
# 棋盘走子类游戏（halma/checkers/junqi/dou/shogi/blokus/ludo）
# ---------------------------------------------------------------------------
_HALMA_COL = ["#e05555", "#3f6fe0", "#f2c94c", "#3ba55d"]
_DOU_EMO = {1: "🐭", 2: "🐱", 3: "🐶", 4: "🐺", 5: "🐆", 6: "🐅", 7: "🦁", 8: "🐘"}
_DOU_CN = {1: "鼠", 2: "猫", 3: "狗", 4: "狼", 5: "豹", 6: "虎", 7: "狮", 8: "象"}
_SHOGI_SYM = {1: "玉", 2: "飛", 3: "角", 4: "金", 5: "銀", 6: "桂", 7: "香",
              8: "歩", 9: "龍", 10: "馬"}
_SHOGI_CN = {1: "王", 2: "飛車", 3: "角行", 4: "金", 5: "銀", 6: "桂", 7: "香",
             8: "兵", 9: "龍", 10: "馬"}


@_register("halma")
def _p_halma(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["halma"][1]
    n = st.get("size") or 9
    title = "⚫ 跳棋 · 率先把全部子渡入对岸"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 获胜"
    elif st.get("turn_uid"):
        title += f"　轮到 {nick(st['turn_uid'])}"
    _turn_banner(cv, w, 46, title, accent)
    ox, oy, cell = _fit(n, w, h, header=46)
    ui.update(ox=ox, oy=oy, cell=cell, n=n, game="halma")
    _paper_board(cv, ox - 8, oy - 8, ox + n * cell + 8, oy + n * cell + 8,
                 base="#e7cf9e", edge="#8a5a2b")
    valid = st.get("valid") or []
    arms = st.get("arms") or []
    players = st.get("players") or []
    # 营区底色按拥有者染色（淡色填充）
    arm_owner = [None] * 4
    owners = st.get("owners") or {}
    for u, a in owners.items():
        try:
            arm_owner[int(a)] = u
        except (TypeError, ValueError):
            pass
    for a in range(4):
        cells = arms[a] if a < len(arms) else []
        col = (players.index(arm_owner[a]) if arm_owner[a] in players
               else (a if a < len(players) else 0)) % len(_HALMA_COL)
        base = _HALMA_COL[col]
        for y in range(n):
            for x in range(n):
                if cells and (y < len(cells) and x < len(cells[y])) and cells[y][x]:
                    cv.create_rectangle(ox + x * cell, oy + y * cell,
                                        ox + (x + 1) * cell, oy + (y + 1) * cell,
                                        fill=_shade(base, 0.55),
                                        outline=_shade(base, 0.25))
    # 非营格淡灰，棋盘线
    for y in range(n):
        for x in range(n):
            if not (valid and y < len(valid) and x < len(valid[y]) and valid[y][x]):
                cv.create_rectangle(ox + x * cell, oy + y * cell,
                                    ox + (x + 1) * cell, oy + (y + 1) * cell,
                                    fill=_shade("#e7cf9e", -0.06), outline="")
    for i in range(n + 1):
        cv.create_line(ox + i * cell, oy, ox + i * cell, oy + n * cell,
                       fill="#c9a860")
        cv.create_line(ox, oy + i * cell, ox + n * cell, oy + i * cell,
                       fill="#c9a860")
    board = st.get("board") or []
    sel = (ui.get("sel") or {}).get("game") == "halma" and (
        ui.get("sel", {}).get("fx"), ui.get("sel", {}).get("fy"))
    now = time.monotonic()
    breathing = _g_breath(now)             # 呼吸辉光强度（纯时间推导，idle 唯一增量）
    _lm = st.get("last_move")              # ((fx,fy),(tx,ty)) 或 None
    lastpx = None
    anchors = []                           # 棋子中心，作胜利星点锚点
    if _lm and len(_lm) == 2 and _lm[1]:
        tx, ty = int(_lm[1][0]), int(_lm[1][1])
        if 0 <= tx < n and 0 <= ty < n:
            lastpx = (ox + tx * cell + cell / 2, oy + ty * cell + cell / 2)
    for y in range(n):
        for x in range(n):
            v = board[y][x]
            if not v:
                continue
            col = players.index(v) % len(_HALMA_COL) if v in players else 0
            color = _HALMA_COL[col]
            cx, cy = ox + x * cell + cell / 2, oy + y * cell + cell / 2
            anchors.append((cx, cy))
            _stone(cv, cx, cy, cell * 0.40, color, _shade(color, -0.35),
                   glow=True, gint=breathing)
            if (x, y) == sel:
                cv.create_oval(cx - cell * 0.46, cy - cell * 0.46,
                               cx + cell * 0.46, cy + cell * 0.46,
                               outline="#ff9800", width=3)
    # ---- 动效：落子光晕/微粒子 + 胜利星点（纯时间推导，数量封顶）----
    _g_draw_last(cv, ui, now, lastpx, cell)
    _g_draw_win(cv, ui, now, w, anchors, breathing,
                st.get("winner_uid") is not None)
    _anim_need(ui, repaint, gap=0.04, cap=180)


@_register("checkers")
def _p_checkers(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["checkers"][1]
    n = st.get("size") or 8
    title = "☬ 国际跳棋"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 获胜"
    elif st.get("turn_uid"):
        title += f"　轮到 {nick(st['turn_uid'])}"
    _turn_banner(cv, w, 46, title, accent)
    ox, oy, cell = _fit(n, w, h, header=46)
    ui.update(ox=ox, oy=oy, cell=cell, n=n, game="checkers")
    _paper_board(cv, ox - 6, oy - 6, ox + n * cell + 6, oy + n * cell + 6,
                 base="#8a5a2b", edge="#b89662")
    board = st.get("board") or []
    for y in range(n):
        for x in range(n):
            dark = (x + y) % 2 == 1
            cv.create_rectangle(ox + x * cell, oy + y * cell,
                                ox + (x + 1) * cell, oy + (y + 1) * cell,
                                fill="#" + ("8a5a2b" if dark else "e7cf9e"),
                                outline="#b89662")
    sel = (ui.get("sel") or {}).get("game") == "checkers" and (
        ui.get("sel", {}).get("fx"), ui.get("sel", {}).get("fy"))
    now = time.monotonic()
    breathing = _g_breath(now)             # 呼吸辉光强度（纯时间推导，idle 唯一增量）
    _lm = st.get("last_move")              # ((fx,fy),(tx,ty)) 或 None
    lastpx = None
    anchors = []                           # 棋子中心，作胜利星点锚点
    if _lm and len(_lm) == 2 and _lm[1]:
        tx, ty = int(_lm[1][0]), int(_lm[1][1])
        if 0 <= tx < n and 0 <= ty < n:
            lastpx = (ox + tx * cell + cell / 2, oy + ty * cell + cell / 2)
    for y in range(n):
        for x in range(n):
            v = board[y][x]
            if not v:
                continue
            cx, cy = ox + x * cell + cell / 2, oy + y * cell + cell / 2
            black = v in (1, 3)
            king = v in (3, 4)
            color = "#1b1b1b" if black else "#e05555"
            anchors.append((cx, cy))
            _stone(cv, cx, cy, cell * 0.40, color, "#000",
                   last=(x, y) == sel and "sel", glow=True, gint=breathing)
            # 用红色中心点标示 help（last 参数复用也行）；这里直接画皇冠
            if king:
                cv.create_oval(cx - cell * 0.18, cy - cell * 0.18,
                               cx + cell * 0.18, cy + cell * 0.18,
                               fill="#f2c94c", outline="")
            if (x, y) == sel:
                cv.create_oval(cx - cell * 0.46, cy - cell * 0.46,
                               cx + cell * 0.46, cy + cell * 0.46,
                               outline="#ff9800", width=3)
    # ---- 动效：落子光晕/微粒子 + 胜利星点（纯时间推导，数量封顶）----
    _g_draw_last(cv, ui, now, lastpx, cell)
    _g_draw_win(cv, ui, now, w, anchors, breathing,
                st.get("winner_uid") is not None)
    _anim_need(ui, repaint, gap=0.04, cap=180)


def _p_rectgrid(cv, st, me, nick, submit, repaint, ui, priv, w, h,
                game, rows, cols, title, cell_painter):
    """通用矩形棋盘渲染：junqi(10x5)、dou(9x7)。cell_painter(y,x,code,x0,y0,cell)"""
    accent = THEME[game][1]
    t = title
    if st.get("winner_uid") is not None:
        t = f"🏆 {nick(st['winner_uid'])} 获胜"
    elif st.get("turn_uid"):
        t += f"　轮到 {nick(st['turn_uid'])}"
    _turn_banner(cv, w, 46, t, accent)
    pad = 12
    cell = max(8, min((w - pad * 2) / cols, (h - 46 - pad * 2) / rows))
    ox = (w - cols * cell) / 2
    oy = 46 + (h - 46 - rows * cell) / 2
    ui.update(ox=ox, oy=oy, cell=cell, n=rows, cols=cols, rows=rows, game=game)
    board = st.get("board") or []
    for y in range(rows):
        for x in range(cols):
            x0, y0 = ox + x * cell, oy + y * cell
            cv.create_rectangle(x0, y0, x0 + cell, y0 + cell,
                                fill=_PANEL, outline=_PANEL_BD)
            code = board[y][x] if y < len(board) and x < len(board[y]) else 0
            cell_painter(cv, y, x, code, x0, y0, cell)
    sel = (ui.get("sel") or {}).get("game") == game and (
        ui.get("sel", {}).get("fx"), ui.get("sel", {}).get("fy"))
    if sel:
        sx, sy = sel
        if 0 <= sx < cols and 0 <= sy < rows:
            cv.create_rectangle(ox + sx * cell + 2, oy + sy * cell + 2,
                                ox + (sx + 1) * cell - 2,
                                oy + (sy + 1) * cell - 2,
                                outline="#ff9800", width=3)


@_register("junqi")
def _p_junqi(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    rows = st.get("rows") or 10
    cols = st.get("cols") or 5
    legend = st.get("legend") or {}
    now = time.monotonic()
    breathing = _g_breath(now)             # 呼吸辉光强度（纯时间推导，idle 唯一增量）
    anchors = []                           # 棋子中心，作胜利星点锚点（降级：军棋无 last_move）

    def pt(cv, y, x, code, x0, y0, cell):
        if not code:
            return
        side = 1 if code >= 40 else 0
        rank = code - 40 if code >= 40 else code - 10
        cn = legend.get(str(rank), str(rank))
        side_col = ("#e05555" if side == 0 else "#2c2c2c")
        cx, cy = x0 + cell / 2, y0 + cell / 2
        anchors.append((cx, cy))
        _disc(cv, cx, cy, cell * 0.42, side_col,
              outline=_shade(side_col, -0.35), glow=True, gint=breathing)
        fs = max(8, int(cell * 0.26))
        cv.create_text(cx, cy, text=cn, fill="#ffffff",
                       font=(_FONT_F[0], fs), anchor="center")

    _p_rectgrid(cv, st, me, nick, submit, repaint, ui, priv, w, h,
                "junqi", rows, cols, "⚔ 军棋（明棋）", pt)
    # ---- 动效（降级）：只做辉光 + 胜利星点（数量封顶 ≤48）----
    _g_draw_win(cv, ui, now, w, anchors, breathing,
                st.get("winner_uid") is not None)
    _anim_need(ui, repaint, gap=0.04, cap=180)


@_register("dou")
def _p_dou(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    rows = st.get("rows") or 9
    cols = st.get("cols") or 7
    water = st.get("water") or []

    def pt(cv, y, x, code, x0, y0, cell):
        inw = water and y < len(water) and x < len(water[y]) and water[y][x]
        if inw:
            cv.create_rectangle(x0, y0, x0 + cell, y0 + cell,
                                fill="#3f8fe0", outline="#2f6bc0", width=2)
        cx, cy = x0 + cell / 2, y0 + cell / 2
        if not code:
            return
        if code >= 10:
            a, side = code - 10, 1
        else:
            a, side = code, 0
        # 营格标红底
        if (x, y) in ((3, 0), (3, 8)):
            _disc(cv, cx, cy, cell * 0.44, "#a02f2f", outline="#7a1f1f")
        else:
            _disc(cv, cx, cy, cell * 0.42, "#f6f4ee", outline=_PANEL_BD)
        emo = _DOU_EMO.get(a, "")
        cn = _DOU_CN.get(a, "")
        fs = max(9, int(cell * 0.30))
        cv.create_text(cx, cy - cell * 0.12, text=emo,
                       font=(_FONT_F[0], fs), anchor="s")
        cv.create_text(cx, cy + cell * 0.06, text=cn,
                       fill="#333", font=(_FONT_F[0], max(8, int(cell * 0.16))),
                       anchor="n")

    _p_rectgrid(cv, st, me, nick, submit, repaint, ui, priv, w, h,
                "dou", rows, cols, "🐭 斗兽棋", pt)


@_register("shogi")
def _p_shogi(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["shogi"][1]
    n = st.get("size") or 9
    title = "♟ 将棋"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 获胜"
    elif st.get("turn_uid"):
        title += f"　轮到 {nick(st['turn_uid'])}"
    _turn_banner(cv, w, 46, title, accent)
    header, hand_h = 46, 70
    avail = max(40, min(w - 28, h - header - hand_h - 14))
    cell = avail / n
    ox = (w - n * cell) / 2
    oy = header + (h - header - hand_h - n * cell) / 2
    ui.update(ox=ox, oy=oy, cell=cell, n=n, cols=n, rows=n, game="shogi")
    _paper_board(cv, ox - 8, oy - 8, ox + n * cell + 8, oy + n * cell + 8,
                 base="#ebd3a8", edge="#7a5a2a")
    for y in range(n + 1):
        cv.create_line(ox + y * cell, oy, ox + y * cell, oy + n * cell,
                       fill="#7a5a2a")
        cv.create_line(ox, oy + y * cell, ox + n * cell, oy + y * cell,
                       fill="#7a5a2a")
    board = st.get("board") or []
    sel = ui.get("sel") or {}
    drop_sel = sel.get("game") == "shogi" and sel.get("drop")
    mv_sel = (sel.get("game") == "shogi" and "fx" in sel
              and (sel["fx"], sel["fy"]))
    now = time.monotonic()
    breathing = _g_breath(now)             # 呼吸辉光强度（纯时间推导，idle 唯一增量）
    anchors = []                           # 棋子中心，作胜利星点锚点（降级：将棋无 last_move）
    for y in range(n):
        for x in range(n):
            c = board[y][x]
            if not c:
                continue
            t = c % 10 if c else 0
            p = 0 if c <= 10 else 1
            cx, cy = ox + x * cell + cell / 2, oy + y * cell + cell / 2
            if p == 0:
                fcol, ocol = "#f7e9cd", "#c0392b"
            else:
                fcol, ocol = "#f7e9cd", "#1b1b1b"
            anchors.append((cx, cy))
            _disc(cv, cx, cy, cell * 0.42, fcol, outline=ocol,
                  glow=True, gint=breathing)
            _text(cv, cx, cy, _SHOGI_SYM.get(t, str(t)), ocol,
                  (_FONT_BIG[0], int(cell * 0.5)))
            if (x, y) == mv_sel:
                _disc(cv, cx, cy, cell * 0.46, fcol, outline="#ff9800",
                      outline_w=3)
    # 手牌区（底部）
    players = st.get("players") or []
    my_pl = players.index(me) if me in players else 0
    hand = st.get("hand") or {}
    my_hand = hand.get(str(my_pl)) or []
    opp_hand = hand.get(str(1 - my_pl)) or []
    hy = h - hand_h + 6
    _text(cv, 12, hy + 8, f"♟ 我（{nick(me)}）持驹", "#333", _FONT_F, anchor="w")
    _text(cv, w - 12, hy + 8, f"对方持驹 {len(opp_hand)} 枚", _MUTED, _FONT_F,
          anchor="e")
    cw = 56
    gap = 8
    cards = []
    available = w - 24
    per = max(1, int(available / (cw + gap)))
    for i, t in enumerate(my_hand[:per]):
        cx0 = 12 + i * (cw + gap)
        cy0 = hy + 24
        fcol = "#f7e9cd"
        ocol = "#ff9800" if drop_sel == t else "#7a5a2a"
        _rrect(cv, cx0, cy0, cx0 + cw, cy0 + cw, 8, fcol,
               ocol, 3 if drop_sel == t else 1)
        _text(cv, cx0 + cw / 2, cy0 + cw / 2 - 8, _SHOGI_SYM.get(t, str(t)),
              "#1b1b1b", _FONT_BIG)
        _text(cv, cx0 + cw / 2, cy0 + cw / 2 + 14, _SHOGI_CN.get(t, ""),
              "#555", (_FONT_F[0], 9))
        cards.append((cx0, cy0, cx0 + cw, cy0 + cw, t))
    ui.update(hands=cards)

    if drop_sel:
        _text(cv, w / 2, hand_h + 10, f"已选「{_SHOGI_CN.get(drop_sel,'')}」，点击棋盘空位打入",
              "#c0392b", _FONT_F)
    # ---- 动效（降级）：只做辉光 + 胜利星点（数量封顶 ≤48）----
    _g_draw_win(cv, ui, now, w, anchors, breathing,
                st.get("winner_uid") is not None)
    _anim_need(ui, repaint, gap=0.04, cap=180)


@_register("blokus")
def _p_blokus(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["blokus"][1]
    n = st.get("size") or 20
    title = "🧩 角斗士棋"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 获胜"
    elif st.get("turn_uid"):
        title += f"　轮到 {nick(st['turn_uid'])}"
    _turn_banner(cv, w, 46, title, accent)
    board = st.get("board") or []
    players = st.get("players") or []
    colors = st.get("colors") or ["#e05555", "#3f6fe0", "#3ba55d", "#e8b93c"]
    placed = st.get("placed") or {}
    has_piece = st.get("has_piece") or {}
    panel_w = max(150, int(w * 0.22))
    cell = max(4, min((w - panel_w - 24) / n, (h - 46 - 24) / n))
    bx = 10
    by = 46 + (h - 46 - n * cell) / 2
    ui.update(ox=bx, oy=by, cell=cell, n=n, game="blokus")
    cv.create_rectangle(bx - 4, by - 4, bx + n * cell + 4, by + n * cell + 4,
                        fill="#f0ead8", outline="#888", width=2)
    for y in range(n):
        for x in range(n):
            v = board[y][x]
            fill = "#f0ead8"
            if v is not None and v in players:
                ci = players.index(v)
                fill = _shade(colors[ci % len(colors)], 0.08) if v != me \
                    else _shade(colors[ci % len(colors)], 0.3)
            cv.create_rectangle(bx + x * cell, by + y * cell,
                                bx + (x + 1) * cell, by + (y + 1) * cell,
                                fill=fill, outline="#d8d0b8", width=1)
    _text(cv, bx + n * cell / 2, h - 12,
          "放置拼块：用下方按钮区选择拼块/方向/落点", "#666", (_FONT_F[0], 9))
    # 右侧面板：各方剩余拼块与已占面积
    px = bx + n * cell + 14
    py = by + 4
    _text(cv, px, py, "战况", "#333", _FONT_B, anchor="w")
    py += 26
    for i, u in enumerate(players):
        col = colors[i % len(colors)]
        _text(cv, px, py, f"● {nick(u)}" + ("（我）" if u == me else ""),
              col, _FONT_B, anchor="w")
        py += 20
        _text(cv, px + 8, py, f"已占 {placed.get(str(u), 0)} 格", "#555",
              _FONT_F, anchor="w")
        py += 18
        pieces = has_piece.get(str(u)) or []
        # 拼块名两两一行分列
        line = " ".join(pieces)
        lines = [line[i:i + 24] for i in range(0, len(line), 24)] or [""]
        for ln in lines:
            _text(cv, px + 8, py, ln, "#777", (_FONT_F[0], 9), anchor="w")
            py += 14
        py += 8


@_register("ludo")
def _p_ludo(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["ludo"][1]
    players = st.get("players") or []
    stt = st.get("starts") or {}            # {uid_str: 起点格号}
    pos = st.get("positions") or {}
    dice = st.get("dice")
    stones = st.get("stones") or ["✈️", "🚢", "🚗", "🚁"]
    track = st.get("track") or 40
    title = "🎲 飞行棋"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 获胜"
    elif st.get("turn_uid"):
        title += f"　轮到 {nick(st['turn_uid'])}"
    _turn_banner(cv, w, 46, title, accent)
    header, note_h = 46, 30
    avail = max(60, min(w - 24, h - header - note_h - 24))
    cx = w / 2
    cy = header + note_h + (h - header - note_h - 20) / 2
    R = avail / 2 - 8                      # 环中心线半径

    def ring_pt(i):
        i = i % track
        side = i // 10
        t = (i % 10) / 9.0
        if side == 0:
            return (cx - R + t * 2 * R, cy - R)
        elif side == 1:
            return (cx + R, cy - R + t * 2 * R)
        elif side == 2:
            return (cx + R - t * 2 * R, cy + R)
        return (cx - R, cy + R - t * 2 * R)

    step = (2 * R) / 9.0
    csz = step * 0.86
    corner_dx = [( -1, -1), (1, -1), (1, 1), (-1, 1)]
    # 各 player 的颜色
    pcol = ["#e05555", "#3f6fe0", "#3ba55d", "#f2c94c"]
    # 轨道环底框
    cv.create_rectangle(cx - R - 4, cy - R - 4, cx + R + 4, cy + R + 4,
                        fill="#efe6cd", outline="#b9986a", width=2)
    # 画 40 个轨道格
    for i in range(track):
        x0, y0 = ring_pt(i)
        mine_start = any(str(stt[sk]) == str(i) for sk in stt) if stt else False
        cv.create_rectangle(x0 - csz / 2, y0 - csz / 2,
                            x0 + csz / 2, y0 + csz / 2,
                            fill=_shade("#efe6cd", 0.35 if not mine_start else 0.6),
                            outline="#c9ad7e")
    # 画机棚 & 放子
    tokens = []                            # [(cx,cy,idx,r)] 我的可动机
    mono_x = {i: 0 for i in range(track)}
    for pi, u in enumerate(players):
        ci = pi % 4
        col = pcol[ci]
        ddx, ddy = corner_dx[pi % 4]
        hx = cx + ddx * R * 0.55
        hy = cy + ddy * R * 0.55
        # 机棚框
        cv.create_rectangle(hx - csz - 4, hy - csz - 4,
                            hx + csz + 4, hy + csz + 4,
                            fill=_shade(col, 0.5), outline=col, width=2)
        vals = pos.get(str(u)) or []
        h_slot = 0
        for idx, v in enumerate(vals):
            if v == -1:                      # 机棚
                sx = hx + (h_slot % 2 - 0.5) * csz
                sy = hy + (h_slot // 2 - 0.5) * csz
                h_slot += 1
                tw = stones[idx] if u == me else "●"
                cv.create_oval(sx - csz / 2 + 1, sy - csz / 2 + 1,
                               sx + csz / 2 - 1, sy + csz / 2 - 1,
                               fill=col, outline=_shade(col, -0.35))
                _text(cv, sx, sy, tw, "#fff" if u != me else "#fff",
                      (_FONT_B[0], int(csz * 0.5)))
                if u == me:
                    tokens.append((sx, sy, idx, max(14, csz * 0.9)))
            elif v == "FIN":                 # 完成
                sx = cx + ddx * R * 0.76
                sy = cy + ddy * R * 0.76
                cv.create_text(sx, sy, text="🏁" if u == me else "✓",
                               fill=col, font=(_FONT_B[0], int(csz * 0.6)))
            else:                            # 轨道格
                try:
                    s = int(v) % track
                except (TypeError, ValueError):
                    continue
                bx0, by0 = ring_pt(s)
                off = mono_x[s]
                mono_x[s] += 1
                sx = bx0 + (off - 0.5) * csz * 0.5
                sy = by0 + (off - 0.5) * csz * 0.5
                tw = stones[idx] if u == me else "●"
                cv.create_oval(sx - csz / 2 + 1, sy - csz / 2 + 1,
                               sx + csz / 2 - 1, sy + csz / 2 - 1,
                               fill=col, outline=_shade(col, -0.35))
                _text(cv, sx, sy, tw, "#fff", (_FONT_B[0], int(csz * 0.5)))
                if u == me:
                    tokens.append((sx, sy, idx, max(14, csz * 0.9)))
    ui.update(game="ludo", tokens=tokens, me=me)
    # 提示 / 骰面
    note = f"🎲 骰面：{dice}" if dice is not None else "🎲 尚未掷骰（点下方「掷骰」）"
    if st.get("turn_uid") == me and dice is not None:
        note += "　点你一架机前进"
    elif st.get("turn_uid") != me:
        note += f"　等待 {nick(st.get('turn_uid'))}"
    _text(cv, w / 2, header + note_h / 2, note, "#333", _FONT_B)


# ---------------------------------------------------------------------------
# 手牌/卡牌/骰子小游戏（rummikub/yahtzee/nimmt/davinci/lovelove/matchpairs/
# liar/halloween/ninja/onewolf/guess_number/drawguess）
# ---------------------------------------------------------------------------
_RMK_COL = {"红": "#e05555", "黄": "#f2c94c", "蓝": "#3f6fe0", "黑": "#3a3a3a"}


@_register("rummikub")
def _p_rummikub(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["rummikub"][1]
    title = "🂠 拉密 Rummikub"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 率先清空手牌"
    elif st.get("turn_uid"):
        title += f"　轮到 {nick(st['turn_uid'])}"
    _turn_banner(cv, w, 46, title, accent)
    # 牌堆余量
    _text(cv, w / 2, 76, f"牌堆余 {st.get('bag', 0)} 张", _MUTED, _FONT_F)
    # 大众公开手牌数（右缘）
    rs = st.get("rack_size") or {}
    _text(cv, w - 12, 76, "手牌数：" + "　".join(
        f"{nick(int(u))}×{c}" for u, c in sorted(rs.items(), key=lambda kv: int(kv[0]))),
        _MUTED, _FONT_F, anchor="e")
    # 桌面组（每组小卡一行）
    table = st.get("table") or []
    now = time.monotonic()
    # 成组触发检测：桌面组状态变化 → 那组做淡金辉光 + 金色星点（纯时间推导）
    rmk_sig = tuple(len(r) for r in table) if table else ()
    rmk_chg = _g_rmk_table_change(ui.get("_rmk_sig"), table)
    ui["_rmk_sig"] = rmk_sig
    ty = 104
    if table:
        _text(cv, w / 2, ty - 8, "— 桌面已出组 —", _MUTED, _FONT_F)
        ty += 10
        cw, ch = 34, 52
        gap = 5
        fx_rect = None
        for ri, row in enumerate(table):
            total = len(row) * (cw + gap) - gap
            rx = (w - total) / 2
            _text(cv, 24, ty + ch / 2, f"第{ri + 1}组", _MUTED, _FONT_F, anchor="w")
            for j, tl in enumerate(row):
                col = _RMK_COL.get(tl.get("c", ""), "#888")
                x0 = rx + j * (cw + gap)
                fg = "#fff" if _luma(col) < 150 else "#222"
                _soft_shadow(cv, x0, ty + 2, x0 + cw, ty + ch, 5, 2)
                _rrect(cv, x0, ty, x0 + cw, ty + ch, 5, col, _shade(col, -0.3))
                _text(cv, x0 + cw / 2, ty + ch / 2, str(tl.get("n", "?")),
                      fg, _FONT_B)
            # 记录发生变化的组行矩形，供成组反馈定位
            if rmk_chg is not None and rmk_chg[0] == ri:
                fx_rect = (rx, ty, rx + total, ty + ch)
            ty += ch + gap + 6
        # 成组即撒一簇金色星点 + 淡金描边（key=桌面组签名，变化才触发）
        if fx_rect is not None:
            fx0, fy0, fx1, fy1 = fx_rect
            _g_play_fx(cv, ui, now, rmk_sig, fx0, fy0, fx1 - fx0, fy1 - fy0,
                       repaint, base=5)
    else:
        _text(cv, w / 2, ty, "（桌面为空，请出牌）", _MUTED, _FONT_F)
        ty += 30
    # 我的手牌（底部，点击高亮）
    hand = []
    hand_ids = []
    if priv and isinstance(priv.get("hand"), list):
        hand = priv["hand"]
        hand_ids = [t.get("id") for t in hand]
    if hand:
        hcy = h - 130
        _text(cv, w / 2, hcy - 26, "我的手牌（点击高亮）", _MUTED, _FONT_F)
        cw, ch = 46, 68
        gap = 6
        per = max(1, (w - 24) // (cw + gap))
        sel = set((ui.get("sel") or {}).get("rmk", []))
        cards = []
        for i, t in enumerate(hand):
            row, col = divmod(i, per)
            if col == 0:
                row_cards = hand[row * per: row * per + per]
                base = (w - (len(row_cards) * (cw + gap) - gap)) / 2
            cx = base + col * (cw + gap)
            cy = hcy + row * (ch + gap)
            col_c = _RMK_COL.get(t.get("c", ""), "#888")
            is_sel = hand_ids[i] in sel
            fill = _shade(col_c, 0.25) if is_sel else col_c
            outl = "#ff9800" if is_sel else _shade(col_c, -0.3)
            _soft_shadow(cv, cx, cy + 2, cx + cw, cy + ch, 6, 2)
            _rrect(cv, cx, cy - (8 if is_sel else 0), cx + cw,
                   cy + ch - (8 if is_sel else 0), 6, fill, outl,
                   3 if is_sel else 1)
            _text(cv, cx + cw / 2, cy + ch / 2 - (8 if is_sel else 0),
                  f"{t.get('c', '')}{t.get('n', '?')}",
                  "#fff" if _luma(fill) < 150 else "#222", _FONT_B)
            if is_sel:                # 被选牌加轻微呼吸光环（复用 _g_breath）
                _g_card_breath_ring(cv, now, cx, cy - (8 if is_sel else 0),
                                    cx + cw, cy + ch - (8 if is_sel else 0))
            cards.append((cx, cy - 8, cx + cw, cy + ch - 8, hand_ids[i]))
        _hov_rects(ui, [(c[0], c[1] - 6, c[2], c[3]) for c in cards])
        hi = _hov_idx(ui)
        if hi is not None and 0 <= hi < len(cards):
            c = cards[hi]
            cv.create_polygon(_rrect_pts(c[0] - 3, c[1] - 3, c[2] + 3, c[3] + 3,
                                         8), fill="", outline="#ffd75e", width=2,
                              smooth=True, splinesteps=24)
        ui.update(game="rummikub", cards=cards, me=me)
    else:
        _text(cv, w / 2, h - 60, "（已清空手牌）", _MUTED, _FONT_F)


def _draw_die(cv, cx, cy, s, val, accent):
    _soft_shadow(cv, cx - s, cy - s, cx + s, cy + s, s * 0.3, 2)
    _rrect(cv, cx - s, cy - s, cx + s, cy + s, s * 0.28,
           _shade("#ffffff", 0.15), "#b0b0b0", 1)
    cv.create_line(cx - s + s * 0.3, cy - s + 2, cx + s - s * 0.3, cy - s + 2,
                   fill="#ffffff", width=2)
    s0 = s * 0.24
    positions = {1: [(0, 0)],
                 2: [(-1, -1), (1, 1)],
                 3: [(-1, -1), (0, 0), (1, 1)],
                 4: [(-1, -1), (1, -1), (-1, 1), (1, 1)],
                 5: [(-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)],
                 6: [(-1, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (1, 1)]}
    for px, py in positions.get(int(val), []):
        cv.create_oval(cx + px * s0 - s0 * 0.55, cy + py * s0 - s0 * 0.55,
                       cx + px * s0 + s0 * 0.55, cy + py * s0 + s0 * 0.55,
                       fill=_shade(accent, -0.45), outline="")


@_register("yahtzee")
def _p_yahtzee(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["yahtzee"][1]
    title = "🎲 快艇骰子"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 总分最高"
    elif st.get("turn_uid"):
        title += f"　轮到 {nick(st['turn_uid'])} · 第 {st.get('round',1)} 轮"
    _turn_banner(cv, w, 46, title, accent)
    # 骰面 5 枚
    dice = st.get("dice") or [None] * 5
    gap = w * 0.06
    die_s = min(44, int((w - gap * 6) / 5 / 2))
    x0 = (w - (die_s * 2 * 5 + gap * 4)) / 2
    y0 = 90
    _text(cv, w / 2, y0 - 30, "本回合骰面" + (f"（还可重掷 {st.get('rolls_left',0)} 次）"
          if st.get("rolls_left") else ""), _MUTED, _FONT_F)
    for i, d in enumerate(dice):
        cx = x0 + i * (die_s * 2 + gap) + die_s
        if d is None:
            cv.create_rectangle(cx - die_s, y0 - die_s, cx + die_s, y0 + die_s,
                                fill="#eee", outline="#ccc")
            _text(cv, cx, y0, "?", _MUTED, _FONT_B)
        else:
            _draw_die(cv, cx, y0 + die_s, die_s, d, accent)
    # 分类得分矩阵
    cats = st.get("cats") or {}
    players = st.get("players") or []
    order = ["1", "2", "3", "4", "5", "6", "three", "four", "house",
             "small", "large", "yahtzee", "chance"]
    scores = st.get("scores") or {}
    totals = st.get("totals") or {}
    my_row = players.index(me) if me in players else 0
    col_h = int((h - y0 - die_s * 2 - 70) / (len(order) + 2))
    col_h = max(15, col_h)
    tpy = y0 + die_s * 2 + 30
    col_w = (w - 30) / max(len(players), 1)
    # 表头
    _text(cv, 12, tpy + col_h / 2, "分类", _MUTED, (_FONT_F[0], 9), anchor="w")
    for i, u in enumerate(players):
        hx = 60 + i * col_w + col_w / 2
        who = "我" if u == me else nick(u)
        _text(cv, hx, tpy + col_h / 2, who, "#333", (_FONT_F[0], 9))
    _text(cv, 12, tpy + col_h / 2, "分类", _MUTED, (_FONT_F[0], 9), anchor="w")
    for ri, cat in enumerate(order):
        yy = tpy + (ri + 1) * col_h
        _text(cv, 14, yy + col_h / 2, cats.get(cat, cat), "#444",
              (_FONT_F[0], 9), anchor="w")
        for i, u in enumerate(players):
            v = (scores.get(str(u)) or {}).get(cat)
            hx = 60 + i * col_w + col_w / 2
            fg = "#333" if v is not None else _MUTED
            _text(cv, hx, yy + col_h / 2, "-" if v is None else str(v),
                  fg, (_FONT_F[0], 9))
    # 合计行
    yy = tpy + (len(order) + 1) * col_h
    cv.create_line(12, yy - 3, w - 12, yy - 3, fill=_PANEL_BD)
    _text(cv, 14, yy + col_h / 2, "合计", "#333", _FONT_B, anchor="w")
    for i, u in enumerate(players):
        hx = 60 + i * col_w + col_w / 2
        _text(cv, hx, yy + col_h / 2, str(totals.get(str(u), 0)), accent,
              _FONT_B)


@_register("nimmt")
def _p_nimmt(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["nimmt"][1]
    title = "🐮 牛头王 Nimmt"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 牛头最少"
    elif st.get("turn_uid"):
        title += f"　第 {st.get('round',1)} 轮 · 轮到 {nick(st['turn_uid'])}"
    _turn_banner(cv, w, 46, title, accent)
    bulls = st.get("bulls") or {}
    _text(cv, w - 12, 76, "牛头：" + "　".join(
        f"{nick(int(u))}:{c}" for u, c in sorted(bulls.items())),
        _MUTED, _FONT_F, anchor="e")
    table = st.get("table") or []
    cols = 4
    ch = 44
    gap = 4
    colw = (w - 36) / cols
    ty = 100
    _text(cv, w / 2, ty - 8, "— 桌面四列（每张上方数字为该牌值） —", _MUTED, _FONT_F)
    ty += 6

    def _bull_str(card):
        h = head_count = 1
        if card % 5 == 0:
            head_count = 2
        if card % 10 == 0:
            head_count = 3
        if card % 11 == 0:
            head_count = 5
        if card == 55:
            head_count = 7
        return "🐮" * head_count

    maxh = 6
    for ci in range(cols):
        col = table[ci] if ci < len(table) else []
        cx = 18 + ci * colw
        top_y = ty
        for k, card in enumerate(col):
            cy0 = top_y + k * (ch + gap)
            fill = _shade("#f7e9cd", 0.15) if (k == len(col) - 1) else "#efe6cd"
            _rrect(cv, cx, cy0, cx + colw - 10, cy0 + ch, 5, fill,
                   "#b9986a" if k == len(col) - 1 else _PANEL_BD)
            _text(cv, cx + (colw - 10) / 2, cy0 + ch / 2 - 6, str(card),
                  "#333", _FONT_B)
            _text(cv, cx + (colw - 10) / 2, cy0 + ch / 2 + 12, _bull_str(card),
                  "#c0392b", (_FONT_F[0], 8))
        _text(cv, cx + (colw - 10) / 2, top_y + maxh * (ch + gap) + 2,
              f"第{ci + 1}列", _MUTED, (_FONT_F[0], 8))
    # 我的手牌
    hand = []
    if priv and isinstance(priv.get("hand"), list):
        hand = priv["hand"]
    if hand:
        hy = ty + maxh * (ch + gap) + 40
        _text(cv, w / 2, hy - 22, "我的手牌（排序，暗选一张）", _MUTED, _FONT_F)
        cw = 40
        gap2 = 6
        per = max(1, (w - 24) // (cw + gap2))
        base = (w - (min(per, len(hand)) * (cw + gap2) - gap2)) / 2
        for i, card in enumerate(hand[:per]):
            cx = base + i * (cw + gap2)
            _rrect(cv, cx, hy, cx + cw, hy + 58, 6, "#fff", "#b9986a")
            _text(cv, cx + cw / 2, hy + 20, str(card), "#333", _FONT_B)
            _text(cv, cx + cw / 2, hy + 40, _bull_str(card), "#c0392b",
                  (_FONT_F[0], 8))
    else:
        _text(cv, w / 2, h - 60, "（本局手牌已出完）", _MUTED, _FONT_F)


@_register("davinci")
def _p_davinci(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["davinci"][1]
    title = "🔐 达芬奇密码"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 最后的达芬奇"
    elif st.get("turn"):
        title += f"　轮到 {nick(st['turn'])}"
    _turn_banner(cv, w, 46, title, accent)
    lbl = st.get("label") or {}
    hands = st.get("hands") or {}
    _text(cv, w - 12, 76, f"牌堆剩 {st.get('draw_left', 0)} 张", _MUTED, _FONT_F,
          anchor="e")
    cw, ch = 56, 78
    gap = 6
    y = 100

    def _label(v):
        return lbl.get(str(v), str(v)) if v is not None else "黑"

    for u, tiles in hands.items():
        me_flag = int(u) == me
        who = "我" if me_flag else nick(int(u))
        dead = int(u) in (st.get("dead") or [])
        if dead:
            who += "（出局）"
        _text(cv, 16, y + ch / 2, who, "#333" if not dead else _MUTED,
              _FONT_B, anchor="w")
        # 我自己的行：显示全部（含暗牌）用 priv 覆盖
        my_row = None
        if me_flag and priv and isinstance(priv.get("row"), list):
            my_row = priv["row"]
        cards = my_row if my_row is not None else tiles
        total = len(cards) * (cw + gap) - gap
        rx = (w - 120 - total) / 2 + 120
        for i, tl in enumerate(cards):
            x0 = rx + i * (cw + gap)
            open_it = tl.get("open")
            v = tl.get("v")
            if open_it:
                fill, fg = "#fff", "#333"
                sym = _label(v) if v is not None else "黑"
            elif me_flag and my_row is not None:
                fill, fg = _shade("#5b6ca8", 0.25), "#fff"
                sym = str(v) if v is not None else "黑"
            else:
                fill, fg = "#4a5a80", "#dfe6f0"
                sym = "?"
            _rrect(cv, x0, y, x0 + cw, y + ch, 6, fill, _shade("#5b6ca8", -0.3))
            _text(cv, x0 + cw / 2, y + ch / 2, sym, fg, _FONT_B)
        y += ch + gap + 14
    # 私密提示
    if priv and isinstance(priv.get("row"), list):
        _text(cv, w / 2, h - 26, "你的暗牌以高亮显示", _MUTED, (_FONT_F[0], 9))


@_register("lovelove")
def _p_lovelove(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["lovelove"][1]
    title = "💌 情书 Love Letter"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 成为最后的倾慕者"
    elif st.get("cur"):
        title += f"　轮到 {nick(st['cur'])}"
    _turn_banner(cv, w, 46, title, accent)
    _text(cv, w - 12, 76, f"牌堆剩 {st.get('deck_left', 0)} 张", _MUTED, _FONT_F,
          anchor="e")
    alive = st.get("alive") or []
    players = st.get("players") or []
    cw, ch = 118, 62
    gap = 14
    per = max(1, int((w - 40) / (cw + gap)))
    y0 = 110
    _text(cv, w / 2, y0 - 20, "存活玩家", _MUTED, _FONT_F)
    for i, u in enumerate(players):
        row, col = divmod(i, per)
        cards_row = players[row * per: row * per + per]
        base = (w - (len(cards_row) * (cw + gap) - gap)) / 2
        cx = base + col * (cw + gap)
        cy = y0 + row * (ch + gap)
        alive_now = u in alive
        acting = u == st.get("cur")
        fill = _shade("#c265a4", 0.35) if alive_now else "#444"
        if acting:
            fill = _shade("#c265a4", 0.05)
        _rrect(cv, cx, cy, cx + cw, cy + ch, 10, fill,
               "#ffd75e" if u == me else _PANEL, 2 if u == me else 1)
        _text(cv, cx + cw / 2, cy + 24, nick(u) + ("（我）" if u == me else ""),
              "#fff", _FONT_B)
        _text(cv, cx + cw / 2, cy + 46, "存活" if alive_now else "出局",
              "#ffd75e" if alive_now else "#999", (_FONT_F[0], 9))
    # 我的密信牌
    y_card = y0 + ((len(players) - 1) // per + 1) * (ch + gap) + 20
    _text(cv, w / 2, y_card - 18, "你的密信牌（单张）", _MUTED, _FONT_F)
    if priv and isinstance(priv.get("hand"), int):
        v = priv["hand"]
        names = {1: "护卫", 2: "牧师", 3: "男爵", 4: "侍女", 5: "王子",
                 6: "国王", 7: "伯爵夫人", 8: "公主"}
        cx = w / 2 - 32
        _rrect(cv, cx, y_card + 2, cx + 64, y_card + 90, 8,
               _shade("#c265a4", 0.5), "#c265a4")
        _text(cv, cx + 32, y_card + 34, str(v), "#fff", _FONT_BIG)
        _text(cv, cx + 32, y_card + 58, names.get(v, ""), "#fff",
              (_FONT_F[0], 9))
    # 弃牌堆简示
    disc = st.get("discard") or []
    if disc:
        _text(cv, w / 2, h - 20, "弃牌堆：" + "、".join(
            f"{nick(int(x[0]))}:{x[1]}" for x in disc[-10:]), _MUTED,
            (_FONT_F[0], 9))


@_register("matchpairs")
def _p_matchpairs(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["matchpairs"][1]
    title = "🃏 配对接龙（王八）"
    if st.get("loser_uid") is not None:
        title = f"🐢 {nick(st['loser_uid'])} 成为王八！"
    elif st.get("turn_uid"):
        title += f"　轮到 {nick(st['turn_uid'])} 摸下一家"
    _turn_banner(cv, w, 46, title, accent)
    safe = st.get("safe") or []
    players = st.get("players") or []
    hs = st.get("hand_size") or {}
    cw, ch = 118, 66
    gap = 14
    per = max(1, int((w - 40) / (cw + gap)))
    y0 = 110
    _text(cv, w / 2, y0 - 20, "玩家余牌", _MUTED, _FONT_F)
    for i, u in enumerate(players):
        row, col = divmod(i, per)
        cards_row = players[row * per: row * per + per]
        base = (w - (len(cards_row) * (cw + gap) - gap)) / 2
        cx = base + col * (cw + gap)
        cy = y0 + row * (ch + gap)
        is_safe = u in safe
        is_turn = u == st.get("turn_uid")
        fill = _shade("#21804a", 0.4) if is_safe else _shade("#37a25f", 0.28)
        if is_turn:
            fill = _shade("#37a25f", 0.05)
        _rrect(cv, cx, cy, cx + cw, cy + ch, 10, fill,
               "#ffd75e" if u == me else _PANEL, 2 if u == me else 1)
        _text(cv, cx + cw / 2, cy + 24, nick(u) + ("（我）" if u == me else ""),
              "#fff", _FONT_B)
        _text(cv, cx + cw / 2, cy + 46, f"余 {hs.get(str(u), 0)} 张" +
              (" · 安全" if is_safe else ""),
              "#ffd75e" if is_safe else "#dfe9df", (_FONT_F[0], 9))
    # 我的私密手牌
    hand = []
    if priv and isinstance(priv.get("hand"), list):
        hand = priv["hand"]
    hy = y0 + ((len(players) - 1) // per + 1) * (ch + gap) + 20
    _text(cv, w / 2, hy - 18, "我的手牌（供参考，摸牌走下方按钮）", _MUTED, _FONT_F)
    if hand:
        per2 = max(1, (w - 24) // 44)
        base = (w - min(per2, len(hand)) * 44 + 4) / 2
        for i, c in enumerate(hand[:per2]):
            cx = base + i * 44
            _rrect(cv, cx, hy + 2, cx + 40, hy + 58, 6, "#fff", "#37a25f")
            _text(cv, cx + 20, hy + 32, c, "#333", _FONT_B)
    else:
        _text(cv, w / 2, hy + 20, "（无手牌）", _MUTED, _FONT_F)


@_register("liar")
def _p_liar(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["liar"][1]
    title = "🎲 骗子酒馆"
    if st.get("done"):
        title = f"🏆 {nick(st.get('winner'))} 最后留在桌上"
    elif st.get("turn"):
        title += f"　轮到 {nick(st.get('turn'))}"
    _turn_banner(cv, w, 46, title, accent)
    pend = st.get("pending")
    if pend:
        _text(cv, w / 2, 76, f"🃏 {nick(pend['uid'])} 报数【{pend['claim']}】（真值保密）",
              "#c0392b", _FONT_B)
    else:
        _text(cv, w / 2, 76, "桌面空，请先出牌", _MUTED, _FONT_F)
    players = st.get("players") or []
    alive = st.get("alive") or []
    hs = st.get("hand_size") or {}
    drink = st.get("drink") or {}
    cw, ch = 118, 66
    gap = 14
    per = max(1, int((w - 40) / (cw + gap)))
    y0 = 100
    for i, u in enumerate(players):
        row, col = divmod(i, per)
        cards_row = players[row * per: row * per + per]
        base = (w - (len(cards_row) * (cw + gap) - gap)) / 2
        cx = base + col * (cw + gap)
        cy = y0 + row * (ch + gap)
        is_alive = u in alive
        is_target = pend and pend.get("uid") == u
        fill = _shade("#8a5a2b", 0.45) if is_alive else "#3a3a3a"
        if is_target:
            fill = _shade("#8a5a2b", 0.1)
        _rrect(cv, cx, cy, cx + cw, cy + ch, 10, fill,
               "#ffd75e" if u == me else _PANEL, 2 if u == me else 1)
        _text(cv, cx + cw / 2, cy + 22, nick(u) + ("（我）" if u == me else ""),
              "#fff", _FONT_B)
        _text(cv, cx + cw / 2, cy + 44, f"牌×{hs.get(str(u), 0)}  🍺{drink.get(str(u), 0)}" +
              ("　被挑战" if is_target else ""),
              "#ffd75e" if is_alive else "#999", (_FONT_F[0], 8))
    # 我的私密手牌
    hand = []
    if priv and isinstance(priv.get("hand"), list):
        hand = priv["hand"]
    hy = y0 + ((len(players) - 1) // per + 1) * (ch + gap) + 20
    _text(cv, w / 2, hy - 18, "我的手牌（值列表，出牌走下方按钮）", _MUTED, _FONT_F)
    if hand:
        per2 = max(1, (w - 24) // 44)
        base = (w - min(per2, len(hand)) * 44 + 4) / 2
        for i, v in enumerate(hand[:per2]):
            cx = base + i * 44
            _rrect(cv, cx, hy + 2, cx + 40, hy + 54, 6, "#fff", "#c9853e")
            _text(cv, cx + 20, hy + 28, str(v), "#333", _FONT_B)
    else:
        _text(cv, w / 2, hy + 20, "（无手牌）", _MUTED, _FONT_F)


@_register("halloween")
def _p_halloween(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["halloween"][1]
    title = "🔔 德国心脏病（慢棋版）"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 收牌最多"
    elif st.get("turn"):
        title += f"　轮到 {nick(st['turn'])}"
        if st.get("can_slap"):
            title += "　🔔 可拍铃！"
    _turn_banner(cv, w, 46, title, accent)
    # 桌面公共翻牌区
    area = st.get("area") or []
    counts = st.get("counts") or {}
    fruits = st.get("fruits") or ["🍓", "🍋", "🍊", "🍌", "🍎"]
    _text(cv, w / 2, 78, "— 公共翻牌区 —", _MUTED, _FONT_F)
    if area:
        per = max(1, (w - 24) // 74)
        base = (w - min(per, len(area)) * 74 + 4) / 2
        for i, f in enumerate(area[-per:]):
            cx = base + i * 74
            _rrect(cv, cx, 96, cx + 68, 132, 8, _shade("#c2362c", 0.25), "#c2362c")
            _text(cv, cx + 34, 114, f, "#fff", (_FONT_BIG[0], 22))
    else:
        _text(cv, w / 2, 118, "（空白，可翻牌）", _MUTED, _FONT_F)
    # 计数提示
    yc = 150
    _text(cv, w / 2, yc, "计数：" + "　".join(
        f"{f}×{counts.get(f, 0)}" for f in fruits if counts.get(f)), "#333",
        _FONT_F)
    if st.get("can_slap"):
        _text(cv, w / 2, yc + 22, "🔔 已有 5 个相同水果，可拍铃收牌！", "#c0392b",
              _FONT_B)
    # 玩家矩阵（得分 + 余牌）
    players = st.get("players") or []
    score = st.get("score") or {}
    left = st.get("left") or {}
    cw, ch = 118, 62
    gap = 14
    per2 = max(1, int((w - 40) / (cw + gap)))
    y0 = yc + 46
    for i, u in enumerate(players):
        row, col = divmod(i, per2)
        cards_row = players[row * per2: row * per2 + per2]
        base = (w - (len(cards_row) * (cw + gap) - gap)) / 2
        cx = base + col * (cw + gap)
        cy = y0 + row * (ch + gap)
        acting = u == st.get("turn")
        fill = _shade("#e05555", 0.4)
        if acting:
            fill = _shade("#e05555", 0.05)
        _rrect(cv, cx, cy, cx + cw, cy + ch, 10, fill,
               "#ffd75e" if u == me else _PANEL, 2 if u == me else 1)
        _text(cv, cx + cw / 2, cy + 24, nick(u) + ("（我）" if u == me else ""),
              "#fff", _FONT_B)
        _text(cv, cx + cw / 2, cy + 46,
              f"得 {score.get(str(u), 0)} · 余 {left.get(str(u), 0)}",
              _shade("#ffe0e0", 0.6), (_FONT_F[0], 9))


@_register("ninja")
def _p_ninja(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["ninja"][1]
    title = "🥷 忍者之夜"
    ph_txt = "暗选行动" if st.get("phase") == "pick" else "结算中"
    if st.get("done"):
        title = f"🏆 {nick(st.get('winner'))} 最后存活"
    else:
        title += f"　第 {st.get('round', 1)} 回合 · {ph_txt}"
    _turn_banner(cv, w, 46, title, accent)
    players = st.get("players") or []
    alive = st.get("alive") or []
    hp = st.get("hp") or {}
    picked = st.get("picked") or []
    cw, ch = 118, 68
    gap = 14
    per = max(1, int((w - 40) / (cw + gap)))
    y0 = 100
    for i, u in enumerate(players):
        row, col = divmod(i, per)
        cards_row = players[row * per: row * per + per]
        base = (w - (len(cards_row) * (cw + gap) - gap)) / 2
        cx = base + col * (cw + gap)
        cy = y0 + row * (ch + gap)
        is_alive = u in alive
        did_pick = u in picked
        fill = _shade("#33415a", 0.5) if is_alive else "#3a3a3a"
        if did_pick and is_alive:
            fill = _shade("#33415a", 0.05)
        _rrect(cv, cx, cy, cx + cw, cy + ch, 10, fill,
               "#ffd75e" if u == me else _PANEL, 2 if u == me else 1)
        _text(cv, cx + cw / 2, cy + 22, nick(u) + ("（我）" if u == me else ""),
              "#fff", _FONT_B)
        h = max(0, min(3, hp.get(str(u), 0)))
        hearts = "❤" * h + "🖤" * (3 - h)
        _text(cv, cx + cw / 2, cy + 44,
              ("存活" if is_alive else "出局") + "  " + hearts,
              "#ffd75e" if is_alive else "#999", (_FONT_F[0], 9))
        if did_pick:
            _text(cv, cx + cw - 10, cy + 10, "✓", "#7fff7f", (_FONT_F[0], 9),
                  anchor="ne")
    # 最近战报
    last = st.get("last")
    if last:
        _text(cv, w / 2, h - 40, "；".join(last[-3:]), _MUTED, (_FONT_F[0], 9))
    privhp = None
    if priv and isinstance(priv.get("hp"), int):
        privhp = priv["hp"]
    if privhp is not None:
        _text(cv, w / 2, h - 16,
              f"你的生命：{'❤' * max(0, min(3, privhp))}", "#c0392b",
              (_FONT_F[0], 9))


@_register("onewolf")
def _p_onewolf(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["onewolf"][1]
    ph_txt = {"night": "🌙 夜晚行动", "vote": "🗳️ 投票处决",
              "result": "🏁 身份揭晓"}.get(st.get("phase"), st.get("phase"))
    title = f"🐺 一夜狼人 · {ph_txt}"
    _turn_banner(cv, w, 46, title, accent)
    if priv and priv.get("name"):
        v = priv.get("name", "")
        extra = ""
        if priv.get("origin") and priv.get("origin") != priv.get("name"):
            extra = f"（初始：{priv['origin']}）"
        if priv.get("rob_seen") or priv.get("robbed_role"):
            extra += f" 换牌后：{priv.get('robbed_role') or priv.get('rob_seen')}"
        if priv.get("seer_center"):
            c = priv["seer_center"]
            extra += f" 中心：{c.get('role_a')}/{c.get('role_b')}"
        if priv.get("seer_view"):
            s = priv["seer_view"]
            extra += f" 见{s.get('name')}"
        won = st.get("winner")
        if st.get("phase") == "result":
            if won is True:
                _text(cv, w / 2, 78, "🎉 好人获胜", "#7fff7f", _FONT_B)
            else:
                _text(cv, w / 2, 78, "🐺 狼人获胜", "#c0392b", _FONT_B)
        _text(cv, w / 2, st.get("phase") == "result" and 104 or 78,
              f"你的身份：{v}{extra}", "#333", _FONT_F)
    players = st.get("players") or []
    need = st.get("need_act") or []
    acted = st.get("acted") or []
    voted = st.get("voted") or []
    dead = st.get("dead") or []
    reveal = st.get("reveal") or {}
    cw, ch = 118, 68
    gap = 14
    per = max(1, int((w - 40) / (cw + gap)))
    y0 = 130
    for i, u in enumerate(players):
        row, col = divmod(i, per)
        cards_row = players[row * per: row * per + per]
        base = (w - (len(cards_row) * (cw + gap) - gap)) / 2
        cx = base + col * (cw + gap)
        cy = y0 + row * (ch + gap)
        acting = u in need and u not in acted
        voted_ok = u in voted
        dead_ok = u in dead
        fill = "#3a3a3a" if dead_ok else _shade("#32264d", 0.5)
        if acting:
            fill = _shade("#c0392b", 0.3)
        elif voted_ok:
            fill = _shade("#32264d", 0.15)
        _rrect(cv, cx, cy, cx + cw, cy + ch, 10, fill,
               "#ffd75e" if u == me else _PANEL, 2 if u == me else 1)
        role_txt = reveal.get(str(u), "")
        _text(cv, cx + cw / 2, cy + 24, nick(u) + ("（我）" if u == me else ""),
              "#fff", _FONT_B)
        sub = "被处决" if dead_ok else \
            ("待行动" if acting else ("已行动" if voted_ok else ("已投票" if voted_ok else "")))
        if st.get("phase") == "result" and role_txt:
            sub = role_txt
        _text(cv, cx + cw / 2, cy + 48, sub,
              "#ffd75e" if acting else "#dfe2ea", (_FONT_F[0], 9))
        if acting:
            _text(cv, cx + cw - 10, cy + 10, "行动", "#ffd75e", (_FONT_F[0], 9),
                  anchor="ne")
    if not players:
        _text(cv, w / 2, y0, "对局已结束", _MUTED, _FONT_F)


@_register("guess_number")
def _p_guess_number(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["guess_number"][1]
    status = st.get("status", "await_secret")
    owner = st.get("owner_uid")
    title = "🔢 猜数字"
    if owner is not None:
        title += f"　出题者：{nick(owner)}" + ("（你）" if owner == me else "")
    _turn_banner(cv, w, 46, title, accent)
    low, high = st.get("low"), st.get("high")
    if low is None or high is None:
        low, high = 1, 100
    # 大字区间
    _text(cv, w / 2, 130, f"区间：{low} ~ {high}", accent, _FONT_BIG)
    if status == "await_secret":
        _text(cv, w / 2, 170, "等待出题者设定数字…", _MUTED, _FONT_F)
    elif status == "round_end":
        _text(cv, w / 2, 170, f"答案 {st.get('secret')}！", "#c0392b", _FONT_B)
    else:
        _text(cv, w / 2, 170, "大家开始猜（按钮区输入 / 猜）", _MUTED, _FONT_F)
    lg = st.get("last_guess")
    if lg:
        dir_txt = {"low": "低了 ↑", "high": "高了 ↓", "hit": "猜中 🎉"}.get(
            lg.get("dir"), "")
        _text(cv, w / 2, 210, f"上一位 {nick(lg['uid'])} 猜 {lg.get('val')}：{dir_txt}",
              "#333", _FONT_B)
    # 积分面板
    scores = st.get("scores") or {}
    if scores:
        y = 270
        _text(cv, w / 2, y, "积分榜", _MUTED, _FONT_F)
        y += 24
        for u, v in sorted(scores.items(), key=lambda kv: -kv[1]):
            hl = "#c0392b" if int(u) == me else "#333"
            _text(cv, w / 2, y, f"{nick(int(u))}：{v}", hl, _FONT_B)
            y += 26


@_register("drawguess")
def _p_drawguess(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["drawguess"][1]
    phase = st.get("phase", "drawing")
    drawer = st.get("drawer_uid")
    title = "🎨 你画我猜"
    if phase == "round_end":
        word = st.get("word") or ""
        title = f"🎉 答案揭晓：{word}"
    elif drawer is not None:
        title += f"　画手：{nick(drawer)}" + ("（你）" if drawer == me else "")
    _turn_banner(cv, w, 46, title, accent)
    # 画布区域：把已画的笔画重画出来
    canvas_x, canvas_y, canvas_w, canvas_h = 14, 70, w - 28, h - 150
    cv.create_rectangle(canvas_x, canvas_y, canvas_w,
                        canvas_y + canvas_h, fill="#fff", outline=_PANEL_BD)
    strokes = st.get("strokes") or []
    for s in strokes:
        if not isinstance(s, dict):
            continue
        if s.get("type") == "line":
            x1, y1 = s.get("x1", 0), s.get("y1", 0)
            x2, y2 = s.get("x2", canvas_w), s.get("y2", canvas_h)
            _col = s.get("color") or "black"
            _wid = s.get("width") or 3
            try:
                cv.create_line(x1, y1, x2, y2, fill=_col, width=int(_wid),
                               capstyle="round")
            except Exception:
                pass
    # 顶部信息
    if phase == "drawing":
        wlen = st.get("word_len")
        if drawer == me:
            wlen_txt = priv.get("word", "?") if priv and priv.get("word") else "?"
            _text(cv, w - 14, 60 + canvas_h + 10, f"你的词：{wlen_txt}",
                  "#c0392b", _FONT_B, anchor="e")
        else:
            _text(cv, w - 14, 60 + canvas_h + 10,
                  f"词长：{'■' * (st.get('word_len') or 0)}" if st.get("word_len")
                  else "画手中…", _MUTED, _FONT_F, anchor="e")
        gy = st.get("guessed_by")
        if gy is not None:
            _text(cv, 14, 60 + canvas_h + 10, f"已猜中：{nick(gy)}", "#37a25f",
                  _FONT_B, anchor="w")
    # 猜词日志 / 积分
    scores = st.get("scores") or {}
    _text(cv, 14, 60 + canvas_h + 30, "积分：" + "　".join(
        f"{nick(int(u))}:{v}" for u, v in sorted(scores.items())),
        "#555", (_FONT_F[0], 9), anchor="w")
    log = st.get("guess_log") or []
    if log:
        last = log[-2:]
        _text(cv, w - 14, 60 + canvas_h + 30, "最近：" + "；".join(
            f"{nick(x['uid'])}「{x['text']}」{'✓' if x.get('ok') else '✗'}"
            for x in last), _MUTED, (_FONT_F[0], 9), anchor="e")


# ---------------------------------------------------------------------------
# 德式策略组：面板 + 资源 + 棋盘，统一走下方按钮区操作，painter 只画状态
# ---------------------------------------------------------------------------
_PALETTE = ["#e0535a", "#4a7de0", "#37a25f", "#e0a13c", "#9a6fd0", "#26c6b0"]


def _pcolor(uid, players):
    """按玩家座位取固定色（同局稳定）。"""
    try:
        i = list(players).index(uid)
    except Exception:
        i = uid % len(_PALETTE)
    return _PALETTE[i % len(_PALETTE)]


def _pscore(st, u):
    sc = st.get("score") or {}
    return sc.get(str(u), 0)


# --------------------------------------------------------------------------
@_register("kaituo")
def _p_kaituo(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["kaituo"][1]
    players = st.get("players") or []
    title = "🏜️ 开拓·卡坦"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 率先 10 分获胜"
    elif st.get("turn_uid") is not None:
        title += f"　轮到 {nick(st['turn_uid'])}"
        if st.get("phase"):
            title += f"（{st['phase']}）"
    if st.get("last_roll"):
        title += f"　🎲上次 {st['last_roll']}"
    _turn_banner(cv, w, 46, title, accent)
    ui.update(game="kaituo")
    rcol = {"wood": "#6aa84f", "brick": "#c27f5a", "lamb": "#a9cc7e",
            "wheat": "#e4cd6b", "ore": "#9aa0ab", "desert": "#ecd9a0"}
    bw = w - 20
    bh = h - 46 - 96 - 20
    cell = min(bw / 6, bh / 6)
    ox = (w - cell * 6) / 2
    oy = 58
    tiles = st.get("tiles") or {}
    for key, t in tiles.items():
        r, c = key.split(",")
        r, c = int(r), int(c)
        x0, y0 = ox + c * cell, oy + r * cell
        col = rcol.get(t.get("res"), "#ddd")
        cv.create_rectangle(x0 + 1, y0 + 1, x0 + cell - 1, y0 + cell - 1,
                            fill=col, outline="#5a4a35", width=1)
        fs = max(8, int(cell * 0.30))
        if t.get("res") == "desert":
            _text(cv, x0 + cell / 2, y0 + cell / 2, "沙漠", "#a89a7f",
                  (_FONT_F[0], fs))
        elif t.get("num"):
            fg = "#fff" if _luma(col) < 150 else "#222"
            _text(cv, x0 + cell / 2, y0 + cell / 2, str(t["num"]), fg,
                  (_FONT_F[0], fs))
    for key, x in (st.get("board") or {}).items():
        i, j = key.split(",")
        i, j = int(i), int(j)
        px, py = ox + j * cell, oy + i * cell
        ac = _pcolor(x.get("owner"), players)
        if x.get("city"):
            _stone(cv, px, py, cell * 0.32, ac)
            _stone(cv, px, py, cell * 0.16, _shade(ac, 0.35))
        else:
            _stone(cv, px, py, cell * 0.23, ac)
    for key, o in (st.get("roads") or {}).items():
        a, b = key.split(">")
        i0, j0 = a.split(",")
        i1, j1 = b.split(",")
        x0, y0 = ox + int(j0) * cell, oy + int(i0) * cell
        x1, y1 = ox + int(j1) * cell, oy + int(i1) * cell
        cv.create_line(x0, y0, x1, y1, fill=_pcolor(o, players),
                       width=max(3, int(cell * 0.22)), capstyle="round")
    # 玩家资源面板（底部）
    res_order = [("wood", "🪵"), ("brick", "🧱"), ("lamb", "🐑"),
                 ("wheat", "🌾"), ("ore", "⛏️")]
    res_color = {"wood": "#6aa84f", "brick": "#c27f5a", "lamb": "#a9cc7e",
                 "wheat": "#e4cd6b", "ore": "#9aa0ab"}
    n = len(players)
    gap = 8
    pw = (w - gap * (n + 1)) / n if n else w
    py0 = h - 92
    resources = st.get("res") or {}
    for idx, u in enumerate(players):
        x0 = gap + idx * (pw + gap)
        cv.create_rectangle(x0, py0, x0 + pw, py0 + 80, fill="#33291d",
                            outline="#5a4a35", width=1)
        _text(cv, x0 + pw / 2, py0 + 14, nick(u) + ("（我）" if u == me else ""),
              "#fff", _FONT_B)
        _text(cv, x0 + pw - 10, py0 + 14, f"🏆 {_pscore(st, u)}", "#ffd75e",
              _FONT_B, anchor="e")
        res = resources.get(str(u), {})
        sw = pw - 16
        i = 0
        for rk, icon in res_order:
            cx0 = x0 + 8 + i * (sw / 5)
            cv.create_oval(cx0 + 2, py0 + 34, cx0 + 13, py0 + 45,
                           fill=res_color[rk], outline="")
            _text(cv, cx0 + 17, py0 + 39, str(res.get(rk, 0)), "#f0e6d8",
                  (_FONT_F[0], 9), anchor="w")
            i += 1
        _text(cv, x0 + pw / 2, py0 + 66, "掷骰·建房·贸易 → 按钮区", "#b0a48f",
              (_FONT_F[0], 8))


@_register("lingdi")
def _p_lingdi(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["lingdi"][1]
    players = st.get("players") or []
    title = "🏰 领地·拼贴"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 领地得分最高"
    elif st.get("turn_uid") is not None:
        title += f"　轮到 {nick(st['turn_uid'])} · 剩牌 {st.get('deck_left', 0)}"
    _turn_banner(cv, w, 46, title, accent)
    ui.update(game="lingdi")
    board = st.get("board") or {}
    feat_col = {"c": "#c05550", "r": "#a8a48f", "f": "#7fb069"}
    if board:
        keys = [k.split(",") for k in board]
        minr = min(int(k[0]) for k in keys)
        maxr = max(int(k[0]) for k in keys)
        minc = min(int(k[1]) for k in keys)
        maxc = max(int(k[1]) for k in keys)
    else:
        minr = minc = 0
        maxr = maxc = 8
    nrow, ncol = maxr - minr + 1, maxc - minc + 1
    bw = w - 24
    bh = h - 46 - 92 - 24
    cell = min(bw / ncol, bh / nrow, w / 9)
    ox = (w - ncol * cell) / 2
    oy = 58
    t = 3
    for key, cellx in board.items():
        r, c = key.split(",")
        r, c = int(r), int(c)
        cr, cc = r - minr, c - minc
        x0, y0 = ox + cc * cell, oy + cr * cell
        cv.create_rectangle(x0 + 1, y0 + 1, x0 + cell - 1, y0 + cell - 1,
                            fill="#efe9dc", outline="#b7ad96", width=1)
        edges = cellx.get("edges") or {}
        if edges.get("N"):
            cv.create_rectangle(max(1, int(x0 + 2)), y0, int(x0 + cell - 2),
                                int(y0 + t), fill=feat_col[edges["N"]], outline="")
        if edges.get("E"):
            cv.create_rectangle(int(x1 := x0 + cell - t), y0 + 2, x0 + cell,
                                int(y0 + cell - 2), fill=feat_col[edges["E"]], outline="")
        if edges.get("S"):
            cv.create_rectangle(int(x0 + 2), int(y0 + cell - t),
                                int(x0 + cell - 2), y0 + cell,
                                fill=feat_col[edges["S"]], outline="")
        if edges.get("W"):
            cv.create_rectangle(x0, y0 + 2, x0 + t, int(y0 + cell - 2),
                                fill=feat_col[edges["W"]], outline="")
        owner = cellx.get("owner")
        if owner is not None:
            _stone(cv, x0 + cell / 2, y0 + cell / 2, cell * 0.26,
                   _pcolor(owner, players))
    # 当前待放板块 + 玩家
    cur = st.get("current")
    py0 = h - 92
    if cur and isinstance(cur, dict):
        ed = cur.get("edges") or {}
        _text(cv, 16, py0 - 10,
              "当前板块：" + "→".join(
                  {"c": "城", "r": "路", "f": "场"}.get(ed[k], k)
                  for k in ("N", "E", "S", "W") if ed.get(k)),
              _MUTED, _FONT_F, anchor="w")
        _text(cv, w / 2, py0 - 10, "放板块·放米宝·过 → 按钮区", _MUTED,
              _FONT_F, anchor="center")
    score = st.get("score") or {}
    meeples = st.get("meeples") or {}
    n = len(players)
    gap = 8
    pw = (w - gap * (n + 1)) / n if n else w
    for idx, u in enumerate(players):
        x0 = 8 + idx * (pw + gap)
        cv.create_rectangle(x0, py0, x0 + pw, py0 + 58, fill="#2d3b2e",
                            outline=_shade(accent, 0.3), width=1)
        _text(cv, x0 + pw / 2, py0 + 15, nick(u) + ("（我）" if u == me else ""),
              "#fff", _FONT_B)
        _text(cv, x0 + pw - 8, py0 + 15, f"剩 {meeples.get(str(u), 0)} 米宝",
              "#cfe0cf", (_FONT_F[0], 8), anchor="e")
        _text(cv, x0 + pw / 2, py0 + 36, f"🏆 {score.get(str(u), 0)}",
              "#ffd75e", _FONT_F)


@_register("tielu")
def _p_tielu(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["tielu"][1]
    players = st.get("players") or []
    title = "🚆 铁路·连线"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 票证结算后总分最高"
    elif st.get("turn_uid") is not None:
        title += f"　轮到 {nick(st['turn_uid'])} · 线路剩 {st.get('route_left', 0)}"
    _turn_banner(cv, w, 46, title, accent)
    ui.update(game="tielu")
    ccmap = {"red": "#d2534f", "yellow": "#e0b33c", "green": "#4a9b5f",
             "blue": "#4a7de0", "purple": "#9a6fd0"}
    cities = st.get("cities") or {}
    order = [int(k) for k in cities] or list(range(st.get("cities_count", 8)))
    cx, cy = w / 2, 60 + (h - 46 - 92 - 60) / 2
    Rx = (w - 40) / 3.2
    Ry = (h - 46 - 92 - 40) / 3.2
    pos = {}
    n = max(1, len(order))
    for i, cid in enumerate(order):
        ang = i / n * 2 * math.pi - math.pi / 2
        pos[cid] = (cx + Rx * math.cos(ang), cy + Ry * math.sin(ang))
    routes = st.get("routes") or []
    for rt in routes:
        if (rt.get("a") not in pos) or (rt.get("b") not in pos):
            continue
        x0, y0 = pos[rt["a"]]
        x1, y1 = pos[rt["b"]]
        claimed = rt.get("claimed")
        col = ccmap.get(rt.get("color"), "#999") if not claimed else \
            _pcolor(claimed, players)
        width = (6 if claimed else 3) if claimed else (3 if rt.get("color") else 2)
        if claimed:
            width = 6
        cv.create_line(x0, y0, x1, y1, fill=col, width=width)
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        _text(cv, mx, my - 8, str(rt.get("length", "")), "#fff",
              (_FONT_F[0], 8))
    for cid, (px, py) in pos.items():
        cv.create_oval(px - 15, py - 15, px + 15, py + 15,
                       fill="#33415a", outline="#fff", width=2)
        _text(cv, px, py, str(cid), "#fff", (_FONT_F[0], 9))
        _text(cv, px, py + 24, cities.get(str(cid), ""), "#dfe6ef",
              (_FONT_F[0], 9))
    # 玩家手牌/分
    hc = st.get("hand_count") or {}
    n = len(players)
    gap = 8
    pw = (w - gap * (n + 1)) / n if n else w
    py0 = h - 92
    for idx, u in enumerate(players):
        x0 = gap + idx * (pw + gap)
        cv.create_rectangle(x0, py0, x0 + pw, py0 + 66, fill="#1e2c42",
                            outline=_shade(accent, 0.3), width=1)
        _text(cv, x0 + pw / 2, py0 + 16, nick(u) + ("（我）" if u == me else ""),
              "#fff", _FONT_B)
        _text(cv, x0 + pw / 2, py0 + 38, f"🎫手牌 {hc.get(str(u), 0)}",
              "#cfe0d8", _FONT_F)
        _text(cv, x0 + pw / 2, py0 + 55, f"🏆 {_pscore(st, u)} 分", "#ffd75e",
              (_FONT_F[0], 9))
    if priv and priv.get("hand"):
        hd = priv["hand"]
        _text(cv, w / 2, h - 20, "你的票卡：" + "  ".join(
            f"{c}:{v}" for c, v in sorted(hd.items())), "#dfe6ef",
            (_FONT_F[0], 8))


@_register("gongfang")
def _p_gongfang(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["gongfang"][1]
    players = st.get("players") or []
    title = "⚒️ 工坊·工放"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 三轮工分最高"
    elif st.get("turn_uid") is not None:
        title += (f"　第 {st.get('round', 1)} 轮 · 轮到 {nick(st['turn_uid'])}"
                  f"（已放 {st.get('placed', {}).get(str(me), 0)}/{st.get('workers', 2)}）")
    _turn_banner(cv, w, 46, title, accent)
    ui.update(game="gongfang")
    spots = st.get("spots") or []
    spots = sorted(spots, key=lambda s: s.get("id", 0))
    cw, chh = 88, 96
    gapx, gapy = 12, 12
    per = max(1, int((w - 40) / (cw + gapx)))
    y0 = 60
    for i, s in enumerate(spots):
        row, col = divmod(i, per)
        base = (w - (min(per, len(spots) - row * per)) * (cw + gapx) - gapx) / 2
        cx = base + col * (cw + gapx)
        cy = y0 + row * (chh + gapy)
        owner = s.get("owner")
        ex = s.get("exclusive")
        fill = "#efe9dc"
        bd = _PANEL
        if owner is not None:
            fill = _pcolor(owner, players)
            bd = "#fff"
        _rrect(cv, cx, cy, cx + cw, cy + chh, 10, fill, bd, 2 if owner else 1)
        _text(cv, cx + cw / 2, cy + 24, f"工位 {s.get('id')}", "#333",
              _FONT_B)
        _text(cv, cx + cw / 2, cy + 50, f"+{s.get('pts', 0)} 分",
              "#ffd75e" if owner is None else "#7c4a1f", _FONT_B)
        if ex:
            _text(cv, cx + cw - 8, cy + 12, "👑先手", "#c0392b",
                  (_FONT_F[0], 9), anchor="ne")
        if owner is not None:
            _text(cv, cx + cw / 2, cy + 74, nick(owner), "#fff",
                  (_FONT_F[0], 9))
    # 玩家
    n = len(players)
    gap = 8
    pw = (w - gap * (n + 1)) / n if n else w
    py0 = h - 96
    placed = st.get("placed") or {}
    done = st.get("done") or []
    for idx, u in enumerate(players):
        x0 = gap + idx * (pw + gap)
        cv.create_rectangle(x0, py0, x0 + pw, py0 + 70, fill="#4a3a20",
                            outline=_shade(accent, 0.3), width=1)
        _text(cv, x0 + pw / 2, py0 + 16, nick(u) + ("（我）" if u == me else ""),
              "#fff", _FONT_B)
        _text(cv, x0 + pw / 2, py0 + 38,
              f"工人 {placed.get(str(u), 0)}/{st.get('workers', 2)}"
              + (" · 过牌" if u in done else ""), "#e8ded0", _FONT_F)
        _text(cv, x0 + pw / 2, py0 + 56, f"🏆 {_pscore(st, u)} 分", "#ffd75e",
              (_FONT_F[0], 9))


@_register("chengzhu")
def _p_chengzhu(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["chengzhu"][1]
    players = st.get("players") or []
    picker = st.get("picker_uid")
    title = "👑 我是城主·领地扩"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 领地得分最高"
    elif picker is not None:
        title += f"　{picker == me and '你' or nick(picker)} 挑选板块"
    _turn_banner(cv, w, 46, title, accent)
    ui.update(game="chengzhu")
    tcol = {"fd": "#a7c97a", "fo": "#4f7a3c", "mo": "#9aa0ab",
            "wa": "#6aa8e0", "gr": "#c8d48a"}
    grid = st.get("grid") or {}
    myg = grid.get(str(me), {})
    # 左：我的 5x5 领地
    lx0, lx1 = 12, w * 0.52
    lw = lx1 - lx0
    lh = h - 46 - 24
    cell = lw / 5
    y0 = 64
    cv.create_text(w * 0.26, y0 - 8, text="我的领地 5×5", fill="#e8e0d0",
                   font=_FONT_B, anchor="w")
    for r in range(5):
        for c in range(5):
            x0 = lx0 + c * cell + 1
            yy0 = y0 + r * cell + 1
            gx = myg.get(f"{r},{c}")
            col = tcol.get(gx.get("terr"), "#eee") if gx else "#3a2c1e"
            cv.create_rectangle(x0, yy0, x0 + cell - 1, yy0 + cell - 1,
                                fill=col, outline="#5a4a35", width=1)
            if gx:
                crown = gx.get("crown", 0)
                if crown:
                    _text(cv, x0 + cell / 2, yy0 + cell / 2,
                          "👑" if crown else "", "#7c4a1f",
                          (_FONT_F[0], int(cell * 0.32)))
                    _text(cv, x0 + cell - 4, yy0 + 12, str(crown), "#7c4a1f",
                          (_FONT_F[0], int(cell * 0.22)), anchor="ne")
    # 右：市场板块（1x2 多米诺）
    market = st.get("market") or []
    mx = w * 0.56
    mw = w - mx - 12
    cv.create_text((mx + w) / 2, y0 - 8, text="市场板块（点选由按钮）", fill="#efe3d0",
                   font=_FONT_B, anchor="center")
    mcell = min(mw / 2 - 6, 40)
    yy = y0
    for i, dom in enumerate(market):
        A, B = dom.get("A") or {}, dom.get("B") or {}
        bx = mx + (mw - mcell * 2 - 6) / 2
        by = yy + i * (mcell + 10)
        cv.create_rectangle(bx, by, bx + mcell, by + mcell,
                            fill=tcol.get(A.get("terr"), "#eee"),
                            outline="#5a4a35", width=1)
        cv.create_rectangle(bx + mcell + 6, by, bx + mcell * 2 + 6,
                            by + mcell, fill=tcol.get(B.get("terr"), "#eee"),
                            outline="#5a4a35", width=1)
        cA, cB = A.get("crown", 0), B.get("crown", 0)
        if cA:
            _text(cv, bx + 6, by + 8, str(cA), "#7c4a1f",
                  (_FONT_F[0], int(mcell * 0.24)), anchor="nw")
        if cB:
            _text(cv, bx + mcell + 6, by + 8, str(cB), "#7c4a1f",
                  (_FONT_F[0], int(mcell * 0.24)), anchor="nw")
        _text(cv, bx + mcell + 3, by + mcell + 6, f"#{dom.get('id')}",
              "#dfe6ef", (_FONT_F[0], 8))
        if i == 4:
            break
    # 底：各玩家已放数
    n = len(players)
    placed = st.get("placed") or {}
    for idx, u in enumerate(players):
        _text(cv, lx0 + 60 + idx * 90, h - 20,
              f"{nick(u)}: {placed.get(str(u), 0)}板",
              "#e8e0d0", (_FONT_F[0], 9), anchor="w")


@_register("gemcity")
def _p_gemcity(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["gemcity"][1]
    players = st.get("players") or []
    title = "💎 璀璨宝石"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 总分最高"
    elif st.get("turn_uid") is not None:
        title += f"　轮到 {nick(st['turn_uid'])} · 目标 {15} 分"
    _turn_banner(cv, w, 46, title, accent)
    ui.update(game="gemcity")
    gcol = {"o": "#3a3a3a", "d": "#f0f0f0", "r": "#d2534f",
            "e": "#3a9b5f", "s": "#4a7de0", "g": "#e0b33c"}
    gtok = {"o": "⬛", "d": "⬜", "r": "🔴", "e": "🟢", "s": "🔵", "g": "🟡"}
    colors = ["o", "d", "r", "e", "s"]
    market = st.get("market") or {}
    # 市场 3 级 × 4
    chh = min(108, (h - 46 - 120) / 4)
    cw = (w - 40) / 4.5
    y0 = 58
    for tier in ("1", "2", "3"):
        cards = market.get(tier) or []
        _text(cv, 18, y0 + 14, f"{tier}级", "#e8e0d0", _FONT_B, anchor="w")
        for i, cd in enumerate(cards):
            x0 = 46 + i * (cw + 6)
            _rrect(cv, x0, y0, x0 + cw, y0 + chh, 8, "#2a2a35", "#44444f")
            _text(cv, x0 + cw - 8, y0 + 14, f"+{cd.get('pts', 0)}", "#ffd75e",
                  _FONT_B, anchor="ne")
            dc = gcol.get(cd.get("disc"), "#888")
            cv.create_oval(x0 + 8, y0 + 8, x0 + 26, y0 + 26, fill=dc,
                           outline="#fff")
            cost = cd.get("cost") or {}
            yy = y0 + 40
            for k in colors:
                v = cost.get(k, 0)
                if v:
                    _text(cv, x0 + 12, yy, f"{gtok[k]}×{v}", "#e8e8e8",
                          (_FONT_F[0], 9), anchor="w")
                    yy += 15
        y0 += chh + 14
    # 银行 + 贵宾
    bank = st.get("bank") or {}
    bx = 18
    py = y0 + 6
    _text(cv, bx, py, "宝石池：", "#e8e0d0", _FONT_B, anchor="w")
    xx = bx + 80
    for k in colors + ["g"]:
        cv.create_oval(xx, py - 8, xx + 16, py + 8, fill=gcol.get(k, "#888"),
                       outline="")
        _text(cv, xx + 22, py, str(bank.get(k, 0)), "#e8e8e8", _FONT_F,
              anchor="w")
        xx += 34
    nobles = st.get("nobles") or []
    if nobles:
        _text(cv, bx, py + 24, "贵宾：" + "  ".join(
            f"👑+3({'+'.join(f'{gtok.get(k,k)}{v}' for k, v in nb.items())})"
            for nb in nobles[:3]), "#ffd75e", (_FONT_F[0], 9), anchor="w")
    # 玩家（宝石/折扣/分）
    n = len(players)
    gap = 8
    pw = (w - gap * (n + 1)) / n if n else w
    ply = h - 74
    tokens = st.get("tokens") or {}
    for idx, u in enumerate(players):
        x0 = gap + idx * (pw + gap)
        cv.create_rectangle(x0, ply, x0 + pw, h - 10, fill="#3a2f52",
                            outline=_shade(accent, 0.3), width=1)
        _text(cv, x0 + pw / 2, ply + 14, nick(u) + ("（我）" if u == me else ""),
              "#fff", _FONT_B)
        _text(cv, x0 + pw - 6, ply + 14, f"🏆 {_pscore(st, u)}", "#ffd75e",
              _FONT_B, anchor="e")
        tk_tok = tokens.get(str(u), {})
        xx = x0 + 8
        for k in colors:
            cv.create_oval(xx, ply + 28, xx + 12, ply + 40,
                           fill=gcol.get(k, "#888"), outline="")
            _text(cv, xx + 16, ply + 34, str(tk_tok.get(k, 0)), "#e8e8e8",
                  (_FONT_F[0], 8), anchor="w")
            xx += 30
        disco = st.get("discount") or {}
        dd = disco.get(str(u), {})
        _text(cv, x0 + pw / 2, ply + 56,
              "折扣:" + " ".join(f"{k}→{dd.get(k,0)}" for k in colors),
              "#cfe0d8", (_FONT_F[0], 8))


@_register("siji")
def _p_siji(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["siji"][1]
    players = st.get("players") or []
    title = "🌸 四季物语·引擎"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 三季总分最高"
    elif st.get("turn_uid") is not None:
        title += (f"　第 {st.get('season', 1)}/3 季 · 轮到 {nick(st['turn_uid'])}"
                  f" · 余 {st.get('turns_left', 0)} 行动")
    _turn_banner(cv, w, 46, title, accent)
    ui.update(game="siji")
    kind_cn = {"crystal": "水晶", "apple": "金币", "vt": "胜利点"}
    # 我的引擎
    engine = st.get("engine") or {}
    my_eng = engine.get(str(me), [])
    y0 = 66
    _text(cv, w / 2, y0, f"我的引擎（{len(my_eng)}/6）", "#eff2e6", _FONT_B)
    cw, chh = 92, 70
    gap = 8
    n = len(my_eng)
    total = n * (cw + gap) - gap
    x0 = (w - total) / 2 if n else w / 2 - 30
    for i, c in enumerate(my_eng):
        cx = x0 + i * (cw + gap)
        filled = c.get("played")
        fill = "#3a4a3a" if not filled else "#1e2f24"
        _rrect(cv, cx, y0 + 24, cx + cw, y0 + 24 + chh, 8, fill, "#5a7a5a")
        _text(cv, cx + cw / 2, y0 + 44, c.get("name", "?"), "#fff", _FONT_B)
        _text(cv, cx + cw / 2, y0 + 64, f"⚙{kind_cn.get(c.get('kind'), '')}+{c.get('out','')}",
              "#cfe0c0", (_FONT_F[0], 9))
        _text(cv, cx + cw / 2, y0 + 82, "已激活" if filled else "待激活",
              "#9fbf9f", (_FONT_F[0], 8))
    # 我的资源
    yy = y0 + 24 + chh + 26
    cry = st.get("crystal") or {}
    gd = st.get("gold") or {}
    vp = st.get("vp") or {}
    _text(cv, w / 2, yy, f"💎施法 {cry.get(str(me), 0)}   💰金币 {gd.get(str(me), 0)}"
          f"   👑胜利 {vp.get(str(me), 0)}", "#eff2e6", _FONT_B)
    # 玩家矩阵
    n = len(players)
    gap = 8
    pw = (w - gap * (n + 1)) / n if n else w
    ply = h - 84
    for idx, u in enumerate(players):
        x0 = gap + idx * (pw + gap)
        cv.create_rectangle(x0, ply, x0 + pw, h - 12, fill="#274a36",
                            outline=_shade(accent, 0.3), width=1)
        _text(cv, x0 + pw / 2, ply + 14, nick(u) + ("（我）" if u == me else ""),
              "#fff", _FONT_B)
        _text(cv, x0 + pw / 2, ply + 34,
              f"💎{cry.get(str(u),0)} 💰{gd.get(str(u),0)}", "#cfe0d8", _FONT_F)
        _text(cv, x0 + pw / 2, ply + 54, f"👑 {vp.get(str(u), 0)}", "#ffd75e",
              _FONT_B)


@_register("bolan")
def _p_bolan(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["bolan"][1]
    players = st.get("players") or []
    title = "🗳️ 波兰大选·区域控制"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 选区票数最高"
    elif st.get("turn_uid") is not None:
        title += (f"　选举 {st.get('election_round', 1)} · 轮到 {nick(st['turn_uid'])}")
    _turn_banner(cv, w, 46, title, accent)
    ui.update(game="bolan")
    regions = st.get("regions") or {}
    board = st.get("board") or {}
    # 5 区卡片，两行
    cw = (w - 60) / 2
    chh = (h - 46 - 84) / 3
    y0 = 60
    for i in range(5):
        rid = str(i)
        row, col = divmod(i, 2)
        x0 = 16 + col * (cw + 16)
        yy = y0 + row * (chh + 12)
        if i == 4:
            col, row = 0, 2
            x0 = 16 + 0 * (cw + 16)
            yy = y0 + 2 * (chh + 12)
        _rrect(cv, x0, yy, x0 + cw, yy + chh, 10, "#333d5e", "#55638a")
        _text(cv, x0 + cw / 2, yy + 18,
              regions.get(rid, f"选区{i}"), "#fff", _FONT_B)
        counts = board.get(rid, {})
        maxv = max(counts.values()) if counts else 0
        # 每玩家柱子
        for pid, u in enumerate(players):
            v = counts.get(u, 0)
            bx = x0 + 30 + pid * ((cw - 60) / len(players))
            barw = (cw - 80) / len(players)
            barh = max(6, v * (chh - 60) / max(maxv, 1))
            cv.create_rectangle(bx, yy + chh - 24 - barh, bx + barw,
                                yy + chh - 24, fill=_pcolor(u, players),
                                outline="")
            _text(cv, bx + barw / 2, yy + chh - 14, str(v), "#e8e8e8",
                  (_FONT_F[0], 8))
        # 领先者
        if maxv:
            lead = [u for u, v in counts.items() if v == maxv]
            _text(cv, x0 + cw - 10, yy + 18,
                  "👑" + "、".join(nick(u) for u in lead), "#ffd75e",
                  (_FONT_F[0], 9), anchor="ne")
    # 玩家剩余影响力
    influence = st.get("influence") or {}
    n = len(players)
    gap = 8
    pw = (w - gap * (n + 1)) / n if n else w
    ply = h - 76
    for idx, u in enumerate(players):
        x0 = gap + idx * (pw + gap)
        cv.create_rectangle(x0, ply, x0 + pw, h - 12, fill="#2f3a58",
                            outline=_shade(accent, 0.3), width=1)
        _text(cv, x0 + pw / 2, ply + 16, nick(u) + ("（我）" if u == me else ""),
              "#fff", _FONT_B)
        _text(cv, x0 + pw / 2, ply + 36,
              f"影响力剩 {influence.get(str(u), 0)}", "#cfe0d8", _FONT_F)
        _text(cv, x0 + pw / 2, ply + 54, f"🏆 {_pscore(st, u)} 分", "#ffd75e",
              (_FONT_F[0], 9))


@_register("azul")
def _p_azul(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["azul"][1]
    players = st.get("players") or []
    title = "🧱 花砖物语·拼花"
    if st.get("winner_uid") is not None:
        title = f"🏆 {nick(st['winner_uid'])} 墙分最高"
    elif st.get("turn_uid") is not None:
        title += f"　第 {st.get('round', 1)} 轮 · 轮到 {nick(st['turn_uid'])}"
    _turn_banner(cv, w, 46, title, accent)
    ui.update(game="azul")
    acol = {"r": "#d2534f", "w": "#f0f0f0", "b": "#4a7de0",
            "y": "#e0b33c", "k": "#3a3a3a"}
    offers = st.get("offers") or []
    center = st.get("center") or []
    top_h = (h - 46) * 0.42
    # 工厂碗
    n = len(offers)
    r = min((w / max(n, 1) - 20) / 2, (top_h - 60) / 2, 46)
    bowl_cy = 60 + top_h / 3
    for i, bowl in enumerate(offers):
        bcx = w / 2 + (i - (n - 1) / 2) * (r * 2 + 8)
        cv.create_oval(bcx - r, bowl_cy - r, bcx + r, bowl_cy + r,
                       fill="#1f3036", outline="#4a7d8a", width=2)
        _text(cv, bcx, bowl_cy + r - 12, f"碗{i}", "#9fbfbf", (_FONT_F[0], 8))
        k = len(bowl)
        ang = 0
        for x in bowl[:6]:
            c = x.get("c", "k")
            px = bcx + (r * 0.55) * math.cos(ang % 6.28)
            py = bowl_cy - 6 + (r * 0.55) * math.sin(ang % 6.28)
            _stone(cv, px, py, r * 0.28, acol.get(c, "#888"))
            ang += math.pi / 2.3
    # 中央池
    ccx, ccy = w / 2, bowl_cy + r + 30
    cv.create_oval(ccx - r, ccy - r, ccx + r, ccy + r, fill="#17242a",
                   outline="#7d4a4a", width=2)
    _text(cv, ccx, ccy + r - 12, "中央", "#c0a0a0", (_FONT_F[0], 8))
    k = 0
    for x in center[:7]:
        c = x.get("c", "k")
        px = ccx + (r * 0.5) * math.cos(k * 1.4)
        py = ccy - 4 + (r * 0.5) * math.sin(k * 1.4)
        _stone(cv, px, py, r * 0.24, acol.get(c, "#888"))
        k += 1
    # 底部：我的 5 行 / 墙 / 地板
    rows = st.get("rows") or {}
    myr = rows.get(str(me), {})
    wall = st.get("wall") or {}
    myw = wall.get(str(me), {})
    base_y = 60 + top_h + 10
    avh = h - base_y - 24
    # 5 行（花纹行）
    rw = w * 0.34
    rh = math.floor(avh / 5)
    _text(cv, rw / 2, base_y + rh / 2 - 20, "花纹行", "#cfe0d8", _FONT_B)
    for i in range(5):
        cap = i + 1
        cnt = len(myr.get(str(i), []))
        x0 = 16
        yy = base_y + i * rh
        for j in range(cap):
            x = x0 + j * ((rw - 32) / cap)
            filled = j < cnt
            col = acol.get(myr.get(str(i), [])[j], "#888") if filled else "#263a3a"
            cv.create_rectangle(x, yy + rh * 0.25, x + (rw - 32) / cap - 3,
                                yy + rh * 0.75, fill=col, outline="#4a6a6a")
    # 墙 5x5
    wlx = w * 0.40
    wcell = min(avh / 5, (w - wlx - 60) / 5)
    _text(cv, wlx + wcell * 2.5, base_y - 10, "墙（上墙落瓦）", "#cfe0d8", _FONT_B)
    for r in range(5):
        for c in range(5):
            x0 = wlx + c * wcell
            yy0 = base_y + r * wcell
            col = acol.get(myw.get(f"{r},{c}"), "#223236") if \
                myw.get(f"{r},{c}") else "#223236"
            cv.create_rectangle(x0 + 1, yy0 + 1, x0 + wcell - 1, yy0 + wcell - 1,
                                fill=col, outline="#4a6a6a", width=1)
    # 地板/分数
    fl = st.get("floor") or {}
    _text(cv, w - 14, base_y + avh / 2,
          f"地板亏 {fl.get(str(me), 0)}\n🏆 {_pscore(st, me)} 分",
          "#ffd75e", (_FONT_F[0], 12), anchor="e")


@_register("betrayal")
def _p_betrayal(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    accent = THEME["betrayal"][1]
    players = st.get("players") or []
    phase = st.get("phase", "explore")
    title = "🏚️ 山屋惊魂"
    haunt = st.get("haunt")
    if st.get("winner_uid") is not None:
        title = f"🏆 对局结束（见日志）"
    elif haunt:
        title += (f" · 惊魂【{haunt.get('scenario')}】· 叛徒 {nick(haunt.get('traitor'))}")
    else:
        title += (f" · 探索 · 预兆 {st.get('omens', 0)}"
                  f" · 轮到 {st.get('turn_uid') is not None and nick(st['turn_uid']) or ''}")
    _turn_banner(cv, w, 46, title, accent)
    ui.update(game="betrayal")
    rooms = st.get("rooms") or {}
    pos = st.get("pos") or {}
    alive = set(st.get("alive") or [])
    exit_cell = (haunt or {}).get("exit")
    # 房间网格
    if rooms:
        keys = [k.split(",") for k in rooms]
        minx = min(int(k[0]) for k in keys)
        maxx = max(int(k[0]) for k in keys)
        miny = min(int(k[1]) for k in keys)
        maxy = max(int(k[1]) for k in keys)
        ncol = maxx - minx + 1
        nrow = maxy - miny + 1
        bw = w - 24
        bh = h - 46 - 148 - 24
        cell = min(bw / ncol, bh / nrow, 52)
        ox = (w - ncol * cell) / 2
        oy = 58
        for key, short in rooms.items():
            x, y = key.split(",")
            x, y = int(x), int(y)
            cx, cy = ox + (x - minx) * cell, oy + (y - miny) * cell
            is_exit = exit_cell and f"{x},{y}" == exit_cell
            fill = "#4a2f4a" if is_exit else "#33263b"
            cv.create_rectangle(cx + 1, cy + 1, cx + cell - 1, cy + cell - 1,
                                fill=fill, outline="#6a4a7a", width=1)
            _text(cv, cx + cell / 2, cy + cell / 2,
                  "🚪" if is_exit else short, "#e8dff0", _FONT_F)
        # 玩家位置
        for u in players:
            pc = pos.get(str(u))
            if not pc:
                continue
            px, py = pc.split(",")
            px, py = int(px), int(py)
            if not (minx <= px <= maxx and miny <= py <= maxy):
                continue
            cx = ox + (px - minx) * cell + cell / 2
            cy = oy + (py - miny) * cell + cell / 2
            r = max(6, cell * 0.26)
            if u == me:
                cv.create_oval(cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3,
                               outline="#fff", width=2)
            _stone(cv, cx, cy, r, _pcolor(u, players))
    else:
        _text(cv, w / 2, h / 2, "（尚未探索任何房间）", "#cfc0d8", _FONT_F)
    # 玩家属性面板
    stats = st.get("stats") or {}
    items = st.get("items") or {}
    dead = st.get("dead") or []
    stmap = {"might": "力", "speed": "速", "sanity": "理", "knowledge": "知"}
    n = len(players)
    gap = 8
    pw = (w - gap * (n + 1)) / n if n else w
    ply = h - 140
    for idx, u in enumerate(players):
        x0 = gap + idx * (pw + gap)
        is_dead = u in dead
        fill = "#4a3a3a" if is_dead else "#2b2440"
        cv.create_rectangle(x0, ply, x0 + pw, h - 10, fill=fill,
                            outline=_shade(accent, 0.3), width=1)
        tag = "（我）" if u == me else ""
        _text(cv, x0 + pw / 2, ply + 14,
              (nick(u) + tag) + (" · 阵亡" if is_dead else ""), "#fff", _FONT_B)
        pstats = (stats.get(str(u)) or {})
        _text(cv, x0 + pw / 2, ply + 34,
              "　".join(f"{stmap[k]}{pstats.get(k, 0)}"
                        for k in ("might", "speed", "sanity", "knowledge")),
              "#cfe0d8", _FONT_F)
        its = items.get(str(u), [])
        _text(cv, x0 + pw / 2, ply + 54,
              "道具：" + ("、".join(its) if its else "—"), "#e0c8a0",
              (_FONT_F[0], 8))
    _text(cv, w / 2, h - 2, "移动/结束/道具/攻击/撤离 → 按钮区", "#b0a8c0",
          (_FONT_F[0], 8))


# ---------------------------------------------------------------------------
# 小丑牌 Balatro（红黑怪诞复古机台：暗红→暗紫底、淡金描边、米白旧牌面）
# 交互：点手牌=select，点出战区=unselect；结算「出牌」走下方按钮。
# 纯渲染，不触碰其它游戏的点击/分发；cid 通过 ui["balatro_cards"/sel] 反查。
# ---------------------------------------------------------------------------
_BALATRO_SUIT = {"h": "♥", "s": "♠", "d": "♦", "c": "♣"}
_BALATRO_JOKER = {  # 与 games_pkg/balatro.py JOKER_DEFS 保持一致（仅渲染）
    # Type× 系列
    "pair": ("对子王", "打出对子时 得分×2"),
    "triple": ("三条锋芒", "打出三条时 得分×3"),
    "flush": ("同花狂热", "打出同花时 得分×3"),
    "straight": ("顺子推进", "打出顺子时 得分×3"),
    "sf": ("同花顺神", "开出同花顺时 得分×5"),
    "full": ("葫芦压阵", "开出葫芦时 得分×4"),
    "four": ("四条杀神", "开出四条时 得分×5"),
    # Suit× 系列
    "heart_x": ("红心领域", "出战含♥时 得分×2"),
    "spade_x": ("黑桃锋芒", "出战含♠时 得分×2"),
    "diamond_x": ("方块棱晶", "出战含♦时 得分×2"),
    "club_x": ("梅花壁垒", "出战含♣时 得分×2"),
    # 花色 +chips
    "heart": ("红心暖手", "有♥时 +30 chips"),
    "spade": ("黑桃猎手", "有♠时 +20 chips"),
    # Type+Chips 系列
    "pairadd": ("对子核心", "打出对子时 +30 chips"),
    "flushadd": ("同花洪流", "打出同花时 +90 chips"),
    "straightadd": ("顺子疾风", "打出顺子时 +60 chips"),
    # Card× / 全局 / 成长 / 弃牌 / 高牌 / 随机
    "face": ("脸牌大王", "出战含 J/Q/K 时 得分×3"),
    "xmult": ("万乘之灵", "所有牌型 得分×1.5"),
    "growth": ("枯木逢春", "每破一盲注 得分永久×1.1"),
    "discard": ("弃牌回收", "本盲注每弃一次 +40 chips"),
    "highcard": ("白手起家", "打出高牌时 +100 chips"),
    "random": ("命运骰子", "得分随机 ×2~×4"),
}
# 稀有度 → (文字, 描边色, 内芯色) 用于小丑牌金边色区分
_BALATRO_RARITY = {
    "common": ("白", "#d8d8d8", "#6a6a7a"),
    "uncommon": ("青", "#4fc3f7", "#1f5a86"),
    "rare": ("金", "#ffd54f", "#8a6a1c"),
}
_BALATRO_RARITY_OF = {  # 与 games_pkg JOKER_RARITY 保持一致
    "pair": "common", "triple": "common", "flush": "common", "straight": "common",
    "heart_x": "common", "spade_x": "common", "diamond_x": "common", "club_x": "common",
    "heart": "common", "spade": "common", "pairadd": "common",
    "full": "uncommon", "flushadd": "uncommon", "straightadd": "uncommon",
    "face": "uncommon", "discard": "uncommon", "random": "uncommon",
    "sf": "rare", "four": "rare", "xmult": "rare", "growth": "rare", "highcard": "rare",
}


# 本文件内牌桌专用字体族（完整元组由 family/size 或 family/size/weight 组成）
_FONT_BF = "Microsoft YaHei UI"          # 粗体族
_FONT_FB = "Microsoft YaHei UI"          # 常规族


def _draw_balatro_card(cv, x0, y0, cw, ch, card, gold=False):
    """《Balatro》风精致扑克：米白渐变牌面、圆角、印花+点数、左上/右下镜像。
    gold=True 表示已出战：金色描边 + 顶部金高光线 + 金三角提示。"""
    _soft_shadow(cv, x0, y0 + 3, x0 + cw, y0 + ch, 7, 3, col="#200d16")
    suit = card.get("s", "") if isinstance(card, dict) else ""
    rank = card.get("c", "?") if isinstance(card, dict) else "?"
    rank = {"T": "10"}.get(rank, rank)        # 后端用 T 表示 10
    red = suit in ("h", "d")
    fg = "#b03a2e" if red else "#1b1b1b"
    r = max(6, int(ch * 0.10))
    frame = "#e6b64c" if gold else "#8a7a55"
    fw = 2 if gold else 1
    # 纸牌基座（外描边）
    _rrect(cv, x0, y0, x0 + cw, y0 + ch, r, "#e7d7b4", frame, fw)
    # 渐变牌面：暖白→米黄（用横向逐层近似 + 顶部高光）
    for i in range(10):
        t = i / 9.0
        col = _rgb2hex(
            int(245 + (239 - 245) * t),
            int(236 + (227 - 236) * t),
            int(216 + (198 - 216) * t))
        xx = x0 + cw * t
        xx2 = x0 + cw * (t + 1 / 9.0)
        cv.create_rectangle(xx, y0 + 2, xx2, y0 + ch - 2, fill=col,
                            outline=col, width=0)
    # 上部玻璃高光（牌面被灯打亮）
    cv.create_line(x0 + r, y0 + 3, x0 + cw - r, y0 + 3,
                   fill=_shade("#f5ecd8", 0.12), width=1)
    if gold:
        # 已出战：金顶高光线 + 顶部金三角
        cv.create_line(x0 + r, y0 + 4, x0 + cw - r, y0 + 4,
                       fill="#e6b64c", width=2)
        ts = max(4, int(cw * 0.10))
        cv.create_polygon(x0 + cw / 2 - ts, y0 + 3,
                          x0 + cw / 2 + ts, y0 + 3,
                          x0 + cw / 2, y0 - 7, fill="#e6b64c", outline="")
    sym = _BALATRO_SUIT.get(suit, "")
    # 左上角：印花 + 点数（红黑正确配色，衬线大字号）
    cs = max(11, int(cw * 0.24))
    _text(cv, x0 + cw * 0.17, y0 + ch * 0.11, sym, fg,
          (_FONT_BF, cs), anchor="center")
    _text(cv, x0 + cw * 0.17, y0 + ch * 0.27, rank, fg,
          (_FONT_BF, max(10, cs)), anchor="center")
    # 居中：大点数 + 下方印花（经典扑克布局）
    _text(cv, x0 + cw * 0.50, y0 + ch * 0.52, rank, fg,
          (_FONT_BF, max(14, int(ch * 0.30))), anchor="center")
    _text(cv, x0 + cw * 0.50, y0 + ch * 0.72, sym, fg,
          (_FONT_BF, max(12, int(ch * 0.22))), anchor="center")
    # 右下角：镜像小印花+点数
    cs2 = max(7, int(cw * 0.16))
    _text(cv, x0 + cw * 0.83, y0 + ch * 0.90, rank + sym, fg,
          (_FONT_FB, cs2), anchor="center")
    # 中央水印：超大淡印花
    _text(cv, x0 + cw / 2, y0 + ch * 0.40, sym, _shade(fg, 0.30),
          (_FONT_BF, max(18, int(cw * 0.62))), anchor="center")
    # 版本（edition）霓虹/全息特效：箔饰=金描边，全息=青描边+斜向彩虹流光，多彩=彩描边
    edt = card.get("edt") if isinstance(card, dict) else None
    if edt in ("foil", "holo", "poly"):
        ec = {"foil": "#e6b64c", "holo": "#4fc3f7", "poly": "#e06ac8"}[edt]
        cv.create_polygon(_rrect_pts(x0, y0, x0 + cw, y0 + ch, r), fill="",
                          outline=ec, width=2, smooth=True, splinesteps=24)
        if edt != "foil":
            # 全息/多彩：整卡斜向彩虹流光（stipple 低可见、不遮点数）
            seed = (card.get("id") or 0)
            wid = 1
            for k, cc in enumerate(("#ff2a9d", "#ffd54f", "#4fc3f7", "#7ee081")):
                xsh = (x0 + cw + 20 * k - 30 + seed % 7)
                cv.create_line(x0 - 6, y0 - 2, xsh, y0 + ch + 2, fill=cc,
                               width=wid, stipple="gray12")
    # 强化层角标（单人闯关卡牌可带 edt 版本 / enh 增强 / seal 封印）
    if isinstance(card, dict) and (card.get("edt") or card.get("enh") or card.get("seal")):
        _draw_balatro_card_badges(cv, x0, y0, cw, ch, card)


def _draw_balatro_card_badges(cv, x0, y0, cw, ch, card):
    """在卡面四角画 版本(金描边)/增强(彩色圆点)/封印(菱形印章) 的 1-2 字角标。"""
    from games_pkg.balatro import EDITION_DEFS, ENH_DEFS, SEAL_DEFS
    fs = max(6, int(ch * 0.085))
    # 版本（edition）：右上金黄徽
    et = card.get("edt")
    if et and et in EDITION_DEFS:
        ab = EDITION_DEFS[et][0][:1]
        bw = max(14, int(cw * 0.24)); bh = max(12, int(ch * 0.15))
        bx, by = x0 + cw - bw - 3, y0 + 3
        _rrect(cv, bx, by, bx + bw, by + bh, max(4, int(bh / 2)),
               "#2a1f0e", "#e6b64c", 1)
        _text(cv, bx + bw / 2, by + 1 + bh / 2, ab, "#ffd75e",
              (_FONT_BF, fs, "bold"), anchor="center")
    # 增强（enhance）：左下彩色圆点
    ef = card.get("enh")
    if ef and ef in ENH_DEFS:
        ab = ENH_DEFS[ef][0][:1]
        r = max(5, int(ch * 0.085))
        cx0, cy0 = x0 + 4 + r, y0 + ch - 4 - r
        cv.create_oval(cx0 - r, cy0 - r, cx0 + r, cy0 + r,
                       fill="#1a5f8a", outline="#7fd1ff", width=1)
        _text(cv, cx0, cy0 + 1, ab, "#ffffff", (_FONT_BF, fs, "bold"), anchor="center")
    # 封印（seal）：右下菱形印章
    sl = card.get("seal")
    if sl and sl in SEAL_DEFS:
        ab = SEAL_DEFS[sl][0][:1]
        sx, sy = x0 + cw - 4, y0 + ch - 6
        sz = max(6, int(ch * 0.10))
        cv.create_polygon(sx, sy - sz, sx + sz, sy, sx, sy + sz, sx - sz, sy,
                          fill="#5e1230", outline="#ff6f91", width=1)
        _text(cv, sx, sy + 1, ab, "#ffc2d1", (_FONT_BF, fs, "bold"), anchor="center")


_RANKVAL = {"A": 11, "K": 10, "Q": 10, "J": 10, "T": 10, "10": 10,
            "9": 9, "8": 8, "7": 7, "6": 6, "5": 5, "4": 4, "3": 3, "2": 2}


def _balatro_best(played):
    """仅作展示：从已选牌近似判最强牌型，返回 (牌型名, 基础分=点数之和)。"""
    if not played:
        return "未选牌", 0
    vals = sorted([_RANKVAL.get(c.get("c", "?"), 0) for c in played],
                  reverse=True)
    base = sum(x for x in vals if x > 0)
    if not vals:
        return "—", 0
    suits = [c.get("s", "") for c in played]
    uniq = sorted(set(vals))
    from collections import Counter
    cnts = Counter(vals)
    maxc = max(cnts.values())
    pairs = sum(1 for v, k in cnts.items() if k == 2)
    flush = len(set(suits)) == 1 and len(vals) >= 5
    hi = max(uniq)
    uniq_low = [14, 5, 4, 3, 2] if max(uniq) == 14 and {14, 5, 4, 3, 2} <= set(
        vals) else None
    straight_seq = sorted(uniq_low if uniq_low else uniq)
    straight = (len(uniq) >= 5 and straight_seq[-1] - straight_seq[0] == 4)
    if straight and flush:
        n = "同花顺"
    elif maxc == 4:
        n = "四条"
    elif (maxc == 3 and pairs >= 1):
        n = "葫芦"
    elif flush:
        n = "同花"
    elif straight:
        n = "顺子"
    elif maxc == 3:
        n = "三条"
    elif pairs >= 2:
        n = "两对"
    elif pairs == 1:
        n = "对子"
    else:
        n = "高牌"
    return n, base


# ---- 《Balatro》原版风配色 ------------------------------
_B_GOLD = "#e6b64c"; _B_GOLD2 = "#d8a03c"
_B_HP = "#c0392b"; _B_BLNDT = "#ffe9b0"
_B_JKT = "#3a1c48"; _B_JKB = "#1a0d24"


def _p_balatro_bg(cv, w, h):
    """《Balatro》原版观感牌桌：暗靛/墨紫星云底 + 粉/青/紫霓虹光斑 + 全息暗角霓虹框。

    走【原版】那条暗色绚烂路线（夜店霓虹赌场），而非暖棕桌布——
    中央柔光保留"被吊灯照亮"的层次，四周压暗营造纵深；边框用霓虹青/粉双色描边。
    """
    _grad(cv, 0, 0, w, h, "#201442", "#0a0516")          # 靛→近黑（仿不同盲注星云）
    cx, cy = w * 0.50, h * 0.46
    # 三处霓虹氛围光斑（stipple 模拟低透明度）
    for gx, gy, sti, col, lit in (
            (cx + w * 0.22, cy - h * 0.34, "gray50", "#ff2a9d", 0.10),
            (cx - w * 0.24, cy + h * 0.34, "gray50", "#18d9c8", 0.09),
            (cx, cy + h * 0.02, "gray50", "#8f5bff", 0.08)):
        rr = w * 0.85
        cv.create_oval(gx - rr, gy - rr, gx + rr, gy + rr,
                       fill=_shade(col, lit), outline="", stipple=sti)
    # 中央"聚光"：多层渐减明暗椭圆，模拟被吊灯照亮（暗紫不显脏）
    for rr, sti, lit in ((1.15, "gray12", 0.10), (0.9, "gray25", 0.15),
                         (0.65, "gray50", 0.20)):
        cv.create_oval(cx - w * rr, cy - w * rr, cx + w * rr, cy + w * rr,
                       fill=_shade("#241548", lit), outline="", stipple=sti)
    # 全息暗角：四边层层压暗，形成暗色邮箱框
    for sp, lit in ((12, 0.30), (30, 0.22), (50, 0.15)):
        cv.create_rectangle(sp, sp, w - sp, h - sp,
                            outline=_shade("#0c0616", lit), width=1,
                            stipple="gray50")
    # 霓虹双色描边（青 外 / 粉 内），模拟发光灯管
    cv.create_rectangle(2, 2, w - 2, h - 2, outline="#18d9c8", width=1)
    cv.create_rectangle(5, 5, w - 5, h - 5, outline="#ff2a9d", width=1)
    cv.create_rectangle(8, 8, w - 8, h - 8, outline=_shade("#18d9c8", 0.15),
                        width=1)
    # 远处微节奏线（极淡的织物/星空氛围，几乎不可见）
    for sx in range(22, w, 22):
        cv.create_line(sx, 0, sx, h, fill=_shade("#3a2a6a", 0.1), width=1,
                       stipple="gray25")


def _p_balatro_top(cv, w, h, st, me, nick):
    """顶部：回合/盲注金边卡 + 轮到谁大字 + 玩家筹码/血量条。"""
    bw, bh = min(400, w - 20), 46
    bx0, by0 = (w - bw) / 2, 10
    _soft_shadow(cv, bx0, by0, bx0 + bw, by0 + bh, 10, 2, col="#1c0d16")
    _rrect(cv, bx0, by0, bx0 + bw, by0 + bh, 10, "#241a14", _B_GOLD2, 2)
    _rrect(cv, bx0 + 3, by0 + 3, bx0 + bw - 3, by0 + bh - 3, 8,
           "#2b1e16", "#5a3a22", 1)
    done = st.get("done")
    if done:
        line = f"🏆 {nick(st.get('winner'))} 通关盲注夺冠"
    else:
        bl = st.get("blind", 1)
        line = f"BLIND {bl} · ROUND  　盲注 {bl}"
    _text(cv, w / 2 + 1, by0 + bh / 2 + 1, line, "#8a5a20",
          (_FONT_BF, 15, "bold"))
    _text(cv, w / 2, by0 + bh / 2, line, _B_BLNDT, (_FONT_BF, 15, "bold"))
    turn = st.get("turn")
    pframe = []
    if not done and turn is not None:
        who = f"→ 轮到 {nick(turn)}" + ("（我）" if turn == me else "")
        _text(cv, w / 2, by0 + bh + 11, who, "#f0c86e", (_FONT_BF, 10))
    # 玩家筹码条（顶栏下，一排）
    players = st.get("players") or []
    alive = set(st.get("alive") or [])
    hp = st.get("hp") or {}
    scr = st.get("score") or {}
    cleared = st.get("cleared") or {}
    n = len(players)
    if n:
        pw = max(74, int((w - 32) / n))
        phh = 38
        py0 = 60 if (not done and turn is not None) else 74
        base = (w - (n * pw + (n - 1) * 8)) / 2
        for i, u in enumerate(players):
            x0 = base + i * (pw + 8)
            cur = (u == turn or u == me) and not done
            fill = _B_JKT if u in alive else "#1f1420"
            outline = _B_GOLD if cur else _shade("#b6485a", -0.25)
            ow = 2 if cur else 1
            _rrect(cv, x0, py0, x0 + pw, py0 + phh, 9, fill, outline, ow)
            tag = "（我）" if u == me else ""
            _text(cv, x0 + pw / 2, py0 + 9, nick(u) + tag, "#fff",
                  (_FONT_BF, 9, "bold"))
            _text(cv, x0 + pw / 2, py0 + 20,
                  f"{chr(9632)}{max(0, hp.get(str(u), 0))}",
                  _B_HP if u in alive else "#9a8a8a",
                  (_FONT_BF, 12, "bold"))
            _text(cv, x0 + pw / 2, py0 + 31,
                  f"🎯{scr.get(str(u), 0)}" + (" ✅" if cleared.get(str(u)) else ""),
                  _B_GOLD if u in alive else "#9a8a8a", (_FONT_FB, 8))
    return done, turn, players, alive, hp, scr, cleared


def _p_balatro_playarea(cv, w, h, priv, ui):
    """出战区：5 个柔金空卡位，放上已选牌（gold 高亮）；返回 sel 矩形与几何。"""
    plabel_y = 118
    _text(cv, w / 2, plabel_y, "⚔ 出战区（点已出战牌可放回）", _shade(_B_GOLD, 0.18),
          (_FONT_BF, 10, "bold"))
    cw, chh = 60, 82
    gcap = 10
    PLAY_MAX = 5
    total = PLAY_MAX * (cw + gcap) - gcap
    px0 = (w - total) / 2
    py = plabel_y + 12
    sel_ids = set(priv.get("sel") or []) if priv else set()
    hand = priv.get("hand") if priv and isinstance(priv.get("hand"), list) else []
    played = [c for c in hand if c["id"] in sel_ids][:PLAY_MAX]
    sel_rects = []
    for i in range(PLAY_MAX):
        x0 = px0 + i * (cw + gcap)
        if i < len(played):
            _draw_balatro_card(cv, x0, py, cw, chh, played[i], gold=True)
            sel_rects.append((x0, py, x0 + cw, py + chh, played[i]["id"]))
        else:
            # 半透明淡金空卡位（stipple 模拟半透明 + 极淡卡轮廓虚影）
            cv.create_polygon(_rrect_pts(x0, py, x0 + cw, py + chh, 8),
                              fill=_shade(_B_JKB, 0.08), outline="",
                              smooth=True, splinesteps=24, stipple="gray25")
            cv.create_polygon(_rrect_pts(x0, py, x0 + cw, py + chh, 8),
                              fill="", outline=_shade(_B_GOLD, -0.42), width=1,
                              smooth=True, splinesteps=24)
            _text(cv, x0 + cw / 2, py + chh / 2, f"{i + 1}", _shade(_B_GOLD, -0.3),
                  (_FONT_BF, 12, "bold"))
    ui["balatro_sel"] = sel_rects
    return sel_rects, played, cw, chh, py


def _p_balatro_sidepanel(cv, x0, y0, x1, y1, cap, col_body):
    """侧栏小面板：暗底 + 金框 + 顶装饰线，画完返回容器内高。"""
    _rrect(cv, x0, y0, x1, y1, 9, _B_JKB, _shade(_B_GOLD, -0.28), 1)
    cv.create_line(x0 + 10, y0 + 22, x1 - 10, y0 + 22,
                   fill=_shade(_B_GOLD, 0.55), width=1)
    _text(cv, (x0 + x1) / 2, y0 + 12, cap, _B_GOLD, (_FONT_BF, 9, "bold"))


def _p_balatro_blind(cv, w, me, st, top, bottom):
    """左栏：盲注进度迷你表（目标线 + 当前筹码进度）。"""
    pw = 104
    x0, x1 = 8, 8 + pw
    y0, y1 = top, max(top + 40, bottom)
    _p_balatro_sidepanel(cv, x0, y0, x1, y1, "BLIND 进度", None)
    bl = st.get("blind", 1)
    tgt = int(60 * (bl ** 1.2))
    cur = int((st.get("score") or {}).get(str(me), 0))
    _text(cv, (x0 + x1) / 2, y0 + 34, f"盲注 {bl}", _B_BLNDT,
          (_FONT_BF, 12, "bold"))
    _text(cv, (x0 + x1) / 2, y0 + 50, f"目标 {tgt}", "#c99aa0",
          (_FONT_FB, 8))
    bar_y = y1 - 26
    if bar_y > y0 + 60 and tgt > 0:
        # 进度条：目标线 + 当前筹码进度
        _text(cv, (x0 + x1) / 2, bar_y - 6, f"进度 {min(100, int(cur / tgt * 100))}%",
              _B_GOLD, (_FONT_FB, 8))
        bw = x1 - x0 - 16
        bx = x0 + 8
        cv.create_rectangle(bx, bar_y, bx + bw, bar_y + 7,
                            fill="#120a18", outline=_shade(_B_GOLD, -0.5),
                            width=1)
        cv.create_rectangle(bx, bar_y, bx + bw * min(1.0, cur / tgt),
                            bar_y + 7, fill=_B_GOLD, outline="")
        cv.create_line(bx + bw * min(1.0, cur / tgt), bar_y - 6,
                       bx + bw * min(1.0, cur / tgt), bar_y + 13,
                       fill="#ffe9b0", width=1)
    return x0, y0, x1, y1


def _p_balatro_score(cv, w, me, played, st, top, bottom, hlev=None):
    """右栏：本手结算窗（牌型名 + 基础分 + 小丑加成 + 累计）。
    hlev：dict 牌型->等级，非空时在面板底部附「已升级牌型」清单（单人版）。"""
    pw = 108
    x0, x1 = w - 8 - pw, w - 8
    y0, y1 = top, max(top + 40, bottom)
    _p_balatro_sidepanel(cv, x0, y0, x1, y1, "手牌结算", None)
    hname, base = _balatro_best(played)
    _text(cv, (x0 + x1) / 2, y0 + 33, hname, _B_GOLD,
          (_FONT_BF, 13, "bold"))
    _text(cv, (x0 + x1) / 2, y0 + 50, f"基础分  {base}", _B_BLNDT,
          (_FONT_FB, 9, "bold"))
    yy = y0 + 68
    jokers = ((st.get("jokers") or {}).get(str(me), []) or [])[:2]
    for jid in jokers:
        _, eff = _BALATRO_JOKER.get(jid, (jid, ""))
        _text(cv, (x0 + x1) / 2, yy, f"🎭 {eff}", _B_GOLD, (_FONT_FB, 8))
        yy += 15
    cv.create_line(x0 + 10, yy + 2, x1 - 10, yy + 2,
                   fill=_shade(_B_GOLD, -0.5), width=1)
    _text(cv, (x0 + x1) / 2, yy + 14,
          f"累计筹码 {int((st.get('score') or {}).get(str(me), 0))}",
          "#f0c86e", (_FONT_BF, 9, "bold"))
    if hlev:
        from games_pkg.balatro import HAND_CN
        lvl_s = "　".join(f"{HAND_CN.get(k, k)}Lv{v}" for k, v in hlev.items())
        _text(cv, (x0 + x1) / 2, yy + 30, "✨ " + lvl_s, "#7ee081",
              (_FONT_FB, 8, "bold"))


# ---- 《Balatro》动效参数（纯时间推导，不依赖 after/线程）----
_B_FX_DUR = 0.9          # 结算分上飘总时长（秒）
_B_FX_RISE = 46          # 上飘总位移（px）
_B_LIFT = 10             # 手牌 hover 上浮量（px）
_B_LIFT_DUR = 0.12       # 上浮/回落缓动时长（秒）


def _balatro_hand_layout(hand, sel_ids, w):
    """手牌布局纯计算（与绘制分离）：供 hover 索引偏移复用同一份几何。"""
    hcw, hchh, hgap = 62, 92, 8
    hper = max(1, (w - 20) // (hcw + hgap))
    row = [c for c in hand if c["id"] not in sel_ids][:hper]
    hy0 = (w - (len(row) * (hcw + hgap) - hgap)) / 2
    return row, hcw, hchh, hgap, hy0


def _p_balatro_fx_detect(ui, st, me, x, y):
    """结算加分检测：累计分增量时在 (x,y) 记一条上飘 fx（增量=本手得分）。"""
    cur = int((st.get("score") or {}).get(str(me), 0) or 0)
    prev = ui.get("_fx_lastscore")
    if prev is None:
        ui["_fx_lastscore"] = cur
        return
    if cur > prev:
        ui.setdefault("_fx", []).append({
            "txt": f"+{cur - prev}", "x": x, "y": y,
            "t0": time.monotonic()})
        ui["_fx_lastscore"] = cur


def _p_balatro_fx_draw(cv, ui, repaint):
    """画上飘文字：y 递减 + 颜色金→暗金→融底模拟淡出（create_text 无 alpha）。
    沿同一轨迹画主字 + 3 个残影，单帧也有"向上甩"的动势。"""
    now = time.monotonic()
    keep = []
    alive = False
    for fx in ui.get("_fx") or ():
        p = (now - fx["t0"]) / _B_FX_DUR
        if p >= 1.0:
            continue                     # 已淡出完毕，丢弃
        keep.append(fx)
        alive = True
        e = 1 - (1 - p) ** 2             # ease-out：先快后慢
        fy = fx["y"] - _B_FX_RISE * e
        fade = _shade("#ffd75e", -0.85 * p)       # 金 → 暗金 → 融底
        _text(cv, fx["x"], fy, fx["txt"], fade, (_FONT_BF, 17, "bold"))
        for j, (off, al) in enumerate(((10, 0.55), (20, 0.30), (30, 0.15))):
            _text(cv, fx["x"], fy + off, fx["txt"],
                  _shade(fade, -0.35 * (1 - al)), (_FONT_BF, 15 - j, "bold"))
    ui["_fx"] = keep
    if alive:
        _anim_need(ui, repaint)          # 续帧直到淡出完成


def _p_balatro_lift_state(ui):
    """hover 上浮状态机（纯时间推导）：检测 _hov_idx 变化，记录上浮/回落起始。
    返回 {"idx": 当前悬停, "t0": 上浮起始时刻, "dn": (idx, t0) 正在回落的卡}。"""
    cur = _hov_idx(ui)
    now = time.monotonic()
    st0 = ui.get("_lift_st")
    if st0 is None:
        st0 = ui["_lift_st"] = {"idx": cur, "t0": now, "dn": None}
    if cur != st0["idx"]:
        if st0["idx"] is not None:
            st0["dn"] = (st0["idx"], now)      # 旧卡开始回落
        st0["idx"] = cur
        st0["t0"] = now
    return st0


def _p_balatro_lift_dy(ui, i, lift=_B_LIFT, dur=_B_LIFT_DUR):
    """第 i 张手牌当前上浮位移（缓出），返回 (on, dy, 是否仍在动)。"""
    st0 = _p_balatro_lift_state(ui)
    now = time.monotonic()
    on, dy, alive = False, 0.0, False
    if st0["idx"] == i and st0["t0"] is not None:
        p = min(1.0, (now - st0["t0"]) / dur)
        dy = -lift * (1 - (1 - p) ** 3)        # 缓出上浮
        on = True
        alive = p < 1.0
    if st0.get("dn") and st0["dn"][0] == i:
        p = min(1.0, (now - st0["dn"][1]) / dur)
        dy = -lift * (1 - p) ** 3              # 缓出回落归零
        if p >= 1.0:
            st0["dn"] = None
        else:
            alive = True
    return on, dy, alive


def _p_balatro_jokers(cv, w, jy, st, me, ui, hbase=0):
    """我的小丑牌横排：三层卡（图案层/名字层/描述层），hover 金边发光。
    hbase = 手牌 hover 索引偏移（_hov 列表 = 手牌矩形 + 小丑矩形）。"""
    _text(cv, w / 2, jy, "🎭 我的小丑牌", _shade(_B_GOLD, 0.3),
          (_FONT_BF, 10, "bold"))
    jokers = ((st.get("jokers") or {}).get(str(me), []) or [])
    n = len(jokers)
    maxw = int((w - 40) / max(1, n))
    jcw = min(300, max(86, int((w - 320) / 3)))
    jcw = min(jcw, maxw)
    jchh = 62
    jx0 = (w - (n * jcw + max(0, n - 1) * 8)) / 2
    rects = []
    for i, jid in enumerate(jokers):
        nm, dc = _BALATRO_JOKER.get(jid, (jid, ""))
        rar = _BALATRO_RARITY_OF.get(jid, "common")
        _rar_lbl, r_edge, r_core = _BALATRO_RARITY.get(rar, _BALATRO_RARITY["common"])
        x0 = jx0 + i * (jcw + 8)
        on = _hov_idx(ui) == (hbase + i)      # 命中 → 稀有度色发光
        top, bot = jy + 8, jy + 8 + jchh
        # 常驻稀有度霓虹晕光：uncommon 青 / rare 金 隐隐外发光（含彩色小丑换霓虹粉）
        if rar in ("uncommon", "rare"):
            gc = "#ff2a9d" if rar == "rare" else "#4fc3f7"
            cv.create_polygon(_rrect_pts(x0 - 2, top - 2, x0 + jcw + 2,
                                         bot + 2, 10), fill="",
                              outline=_shade(gc, 0.3), width=1, smooth=True,
                              splinesteps=24, stipple="gray25")
        if on:
            for off, ow in ((6, 2), (4, 2), (2, 2)):
                _rrect(cv, x0 - off, top - off, x0 + jcw + off, bot + off,
                       12, fill="", outline=_shade(r_edge, 0.1 * (3 - off)),
                       width=ow)
        _soft_shadow(cv, x0, jy + 8, x0 + jcw, jy + 8 + jchh, 10, 2,
                     col="#1c0d16")
        # 稀有度描边：common 白 / uncommon 青 / rare 金
        _rrect(cv, x0, top, x0 + jcw, bot, 10, _B_JKT,
               _B_GOLD if on else r_edge, 3 if on else 2)
        _rrect(cv, x0 + 3, top + 3, x0 + jcw - 3, bot - 3, 9,
               _shade(_B_JKT, -0.2), _shade(r_core, -0.05), 1)
        # 稀有度角标（左上小字：白/青/金）
        cv.create_oval(x0 + 4, top + 4, x0 + 18, top + 18, fill=r_core,
                       outline=r_edge, width=1)
        _text(cv, x0 + 11, top + 10, _rar_lbl, "#fff",
              (_FONT_FB, 7, "bold"), anchor="center")
        # 图案层：顶部大 🎭（金边圆底徽）
        icx, icy = x0 + jcw / 2, top + 15
        _disc(cv, icx, icy, 12, _shade(_B_JKT, 0.25),
              top_bright=0.45, bot_dark=-0.1)
        cv.create_oval(icx - 12, icy - 12, icx + 12, icy + 12,
                       outline=_shade(_B_GOLD, -0.2), width=1)
        _text(cv, icx, icy + 1, "🎭", "#ffd75e", (_FONT_FB, 15), anchor="center")
        # 名字层：中间金氰字
        _text(cv, x0 + jcw / 2, top + 33, nm, "#ffd75e",
              (_FONT_BF, 10, "bold"), anchor="center")
        # 描述层：底部小字
        _text(cv, x0 + jcw / 2, top + 50, dc, "#d8b89a",
              (_FONT_FB, 8), anchor="center")
        rects.append((x0, top, x0 + jcw, bot, jid))
    return rects, jchh


def _p_balatro_hand(cv, w, card_y, hand, sel_ids, ui, repaint):
    """手牌：底部一排，点牌=select；hover 缓动上浮 + 金圈（时间推导）。
    点击矩形随实际绘制位置同步位移，保证点击几何一致。"""
    _text(cv, w / 2, card_y - 16, "我的手牌（点击加入出战区）", "#d8b89a",
          (_FONT_FB, 8))
    row, hcw, hchh, hgap, hy0 = _balatro_hand_layout(hand, sel_ids, w)
    cards = []
    rects = []
    alive = False
    for i, card in enumerate(row):
        cx0 = hy0 + i * (hcw + hgap)
        on, dy, mv = _p_balatro_lift_dy(ui, i)
        alive = alive or mv
        if on:
            r = 9
            cv.create_polygon(
                _rrect_pts(cx0 - 3, card_y + dy - 3, cx0 + hcw + 3,
                           card_y + hchh + dy + 3, r),
                fill="", outline=_B_GOLD, width=2, smooth=True,
                splinesteps=24)
        _draw_balatro_card(cv, cx0, card_y + dy, hcw, hchh, card)
        # 点击矩形随绘制位置位移（dy 一致）；hover 矩形向上留 lift+余量防抖
        cards.append((cx0, card_y + dy, cx0 + hcw, card_y + hchh + dy,
                      card["id"]))
        rects.append((cx0, card_y - 22 - _B_LIFT, cx0 + hcw, card_y + hchh))
    ui["balatro_cards"] = cards
    if alive:
        _anim_need(ui, repaint, gap=0)   # 缓动短(0.12s)，同步链一口气放完再停
    return rects


@_register("balatro")
def _p_balatro(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    _p_balatro_bg(cv, w, h)
    done, turn, players, alive, hp, scr, cleared = \
        _p_balatro_top(cv, w, h, st, me, nick)
    sel_rects, played, cw, chh, py = _p_balatro_playarea(cv, w, h, priv, ui)
    hand = priv.get("hand") if priv and isinstance(priv.get("hand"), list) else []
    # 结算加分检测：对比上次累计分，增量 → 在出战区位置触发上飘
    _p_balatro_fx_detect(ui, st, me, w / 2, py + chh / 2)
    # 我的小丑牌（常驻被动展示）；hbase = 手牌 hover 矩形数量
    jy = py + chh + 26
    hsel = set(priv.get("sel") or []) if priv else set()
    hrow, _h1, _h2, _h3, _h4 = _balatro_hand_layout(hand, hsel, w)
    joker_rects, jchh = _p_balatro_jokers(cv, w, jy, st, me, ui, len(hrow))
    ui["balatro_jokers"] = joker_rects
    # 提示语
    prog_y = jy + (8 if joker_rects else 0) + (jchh if joker_rects else 0) + 26
    if done:
        _text(cv, w / 2, prog_y, f"🏆 {nick(st.get('winner'))} 斩获本局胜利！",
              _B_BLNDT, (_FONT_BF, 12, "bold"))
    elif turn == me:
        _text(cv, w / 2, prog_y,
              f"点手牌选牌，凑好牌型后「出牌」（已选 {len(played)}/5）",
              _B_BLNDT, (_FONT_BF, 11, "bold"))
    else:
        _text(cv, w / 2, prog_y, f"等待 {nick(turn)}…", "#d8b89a",
              (_FONT_BF, 11, "bold"))
    # 手牌区（点牌=select；hover 缓动上浮）。高度计算保持原几何，方便鼠标对齐。
    card_y = max(prog_y + 18, h - 128)
    # 左右两侧：盲注进度 / 手牌结算（自上而下贴到手上方，不遮挡点击矩形）
    sidetop = py + chh + 14
    sidebot = card_y - 14
    if sidebot - sidetop >= 40 and w >= 560:
        _p_balatro_blind(cv, w, me, st, sidetop, sidebot)
        _p_balatro_score(cv, w, me, played, st, sidetop, sidebot)
    hand_rects = _p_balatro_hand(cv, w, card_y, hand, hsel, ui, repaint)
    # 上飘文字覆盖在最上层；hover 命中区 = 手牌矩形 + 小丑矩形
    _p_balatro_fx_draw(cv, ui, repaint)
    _hov_rects(ui, hand_rects + joker_rects)
    ui.update(game="balatro")


def _p_balatro_solo_top(cv, w, st, me):
    """单人顶部状态条：盲注/目标分 + ❤命数 + 出牌手数 + 累计进度。

    单人永远是自己行动，故不再显示"轮到谁"，改为更自然的中文状态。
    返回 (done, winner) 供主 painter 复用。
    """
    done = st.get("done", False)
    winner = st.get("winner")
    blind = st.get("blind", 1)
    max_blind = st.get("max_blind", 18)
    layer = st.get("blind_layer", "")
    ante = st.get("blind_ante", 1)
    tgt = st.get("blind_target", 0)
    lives = st.get("lives", 0)
    dollars = st.get("dollars", 0)
    hu = st.get("hands_used", 0)
    hm = st.get("hands_max", 4)
    cur = int((st.get("score") or {}).get(str(me), 0))
    passed = st.get("passed", False)
    bw, bh = min(430, w - 20), 44
    bx0, by0 = (w - bw) / 2, 10
    _soft_shadow(cv, bx0, by0, bx0 + bw, by0 + bh, 10, 2, col="#1c0d16")
    _rrect(cv, bx0, by0, bx0 + bw, by0 + bh, 10, "#241a14", _B_GOLD2, 2)
    _rrect(cv, bx0 + 3, by0 + 3, bx0 + bw - 3, by0 + bh - 3, 8,
           "#2b1e16", "#5a3a22", 1)
    if done and winner is not None:
        line = f"🏆 第 {blind} 桥 · 全部通关夺冠！"
    elif done:
        line = f"💀 第 {blind} 桥 · 生命归零，本局结束"
    else:
        line = f"第 {blind}/{max_blind} 桥 · {layer} · Ante {ante}"
    _text(cv, w / 2 + 1, by0 + bh / 2 + 1, line, "#8a5a20",
          (_FONT_BF, 15, "bold"))
    _text(cv, w / 2, by0 + bh / 2, line, _B_BLNDT, (_FONT_BF, 15, "bold"))
    # 状态条：❤命数 / 💰金币 / 已出牌手数 / 当前累计进度
    if not done:
        hearts = "❤" * max(0, int(lives)) + "🖤" * max(0, 3 - max(0, int(lives)))
        shop_tag = "　🛒商店中" if st.get("shop_phase") else ""
        status = (f"{hearts}  💰{dollars}金币  已出 {hu}/{hm} 手  "
                  f"🎯目标 {tgt}  累计 {cur}"
                  + ("  ✅已达标" if passed else "") + shop_tag)
        _text(cv, w / 2, by0 + bh + 13, status, "#f0c86e", (_FONT_BF, 10))
        # Boss 盲注 → 顶部红色警告条（Boss 名 + debuff 说明）
        if st.get("is_boss"):
            bname = st.get("boss_name") or "未知Boss"
            bdeb = st.get("boss_debuff") or ""
            _rrect(cv, bx0, by0 + bh + 20, bx0 + bw, by0 + bh + 44, 8,
                   "#5c1212", "#ff6b6b", 2)
            _text(cv, w / 2, by0 + bh + 32,
                  f"⚠ BOSS·{bname} {bdeb}", "#ff9d9d",
                  (_FONT_BF, 11, "bold"))
    return done, winner


_CON_CAT_COLOR = {"塔罗": "#6a4a12", "星球": "#165e5a", "灵体": "#5e1230"}


def _p_balatro_solo_cons(cv, w, priv, ui, row_y):
    """消耗品槽：手牌上方排一排可点图标（≤SOLO_CONS_SLOTS=2 槽）。
    pending=待选目标态（先点消耗品、再点手牌落地）；点击矩形存 ui["solo_cons"]。"""
    cids = (priv.get("cons") or []) if priv and isinstance(priv, dict) else []
    ui["solo_cons"] = []
    ui["solo_cons_cids"] = cids
    if not cids:
        return
    from games_pkg.balatro import CONS_DEFS
    pending = ui.get("_solo_use")
    n = len(cids)
    ic, gap = 74, 12
    total = n * ic + (n - 1) * gap
    x0 = (w - total) / 2
    y0 = row_y
    for i, cid in enumerate(cids):
        cx = x0 + i * (ic + gap)
        onc = (pending == i)
        _name, cat, _d, _eff, _price = CONS_DEFS.get(cid, (cid, "消耗", "", {}, 0))
        cc = _CON_CAT_COLOR.get(cat, "#3a3a3a")
        fill = _shade(cc, 0.15)
        outline = _B_GOLD if onc else _shade("#e6b64c", -0.3)
        _rrect(cv, cx, y0, cx + ic, y0 + 42, 9, fill, outline, 2 if onc else 1)
        _text(cv, cx + ic / 2, y0 + 11, cat, "#d9c6a5", (_FONT_FB, 8, "bold"),
              anchor="center")
        _text(cv, cx + ic / 2, y0 + 27, _name[:6], "#ffe9b0",
              (_FONT_BF, 9, "bold"), anchor="center")
        if onc:
            cv.create_oval(cx + 3, y0 + 3, cx + 13, y0 + 13,
                           fill="#e6b64c", outline="")
            _text(cv, cx + 8, y0 + 7, "✦", "#2a1f0e", (_FONT_BF, 8, "bold"),
                  anchor="center")
        ui["solo_cons"].append((cx, y0, cx + ic, y0 + 42, i))
    if pending is not None:
        _text(cv, w / 2, y0 - 14, "✨ 已选消耗品 → 点一张手牌使用（再点该消耗品取消）",
              "#7ee081", (_FONT_BF, 10, "bold"), anchor="center")


def _p_balatro_solo_shop(cv, w, h, st, ui):
    """商店面板：shop_phase 时在画面中下部弹框——左列 Joker、右列消耗品、
    右上刷新、底部「继续」。点击矩形分别存进 ui 供点击分发。"""
    shop = st.get("shop")
    ui["solo_shop_jokers"] = []
    ui["solo_shop_cons"] = []
    ui["solo_shop_reroll"] = None
    ui["solo_shop_continue"] = None
    if not shop:
        return
    px0, px1 = 16, w - 16
    ptop = max(130, int(h * 0.30))
    pbot = h - 10
    _soft_shadow(cv, px0, ptop, px1, pbot, 16, 2, col="#000000")
    _rrect(cv, px0, ptop, px1, pbot, 12, "#2b1f18", _B_GOLD2, 2)
    _rrect(cv, px0 + 3, ptop + 3, px1 - 3, pbot - 3, 10, "#221813", "#5a3a22", 1)
    _text(cv, (px0 + px1) / 2, ptop + 18, "🛒 商　店", "#ffd75e",
          (_FONT_BF, 15, "bold"))
    # 刷新按钮（右上）
    rw, rh = 158, 32
    rx0, ry0 = px1 - 12 - rw, ptop + 16
    _rrect(cv, rx0, ry0, rx0 + rw, ry0 + rh, 9, "#1c1430", "#a98af0", 2)
    _text(cv, rx0 + rw / 2, ry0 + rh / 2, f"刷新 ⟳ {shop.get('reroll_cost', 3)}💰",
          "#d9b8ff", (_FONT_BF, 10, "bold"), anchor="center")
    ui["solo_shop_reroll"] = (rx0, ry0, rx0 + rw, ry0 + rh)
    # 两列货架
    coltop = ptop + 54
    colw = int((px1 - px0 - 28) / 2)
    jx0, cxx0 = px0 + 8, px0 + 8 + colw + 12
    _text(cv, jx0 + colw / 2, coltop, "🎭 Joker 商品", _B_GOLD,
          (_FONT_BF, 10, "bold"), anchor="center")
    _text(cv, cxx0 + colw / 2, coltop, "🧪 消耗品", _B_GOLD,
          (_FONT_BF, 10, "bold"), anchor="center")
    yy0 = coltop + 16
    ith, igap = 46, 9
    for i, it in enumerate(shop.get("jokers") or []):
        y0 = yy0 + i * (ith + igap)
        sold = bool(it.get("sold"))
        _lab, r_edge, r_core = _BALATRO_RARITY.get(
            it.get("rarity", "common"), _BALATRO_RARITY["common"])
        fill = "#14141c" if sold else _shade(_B_JKT, -0.05)
        outline = _shade("#9a9a9a", -0.3) if sold else r_edge
        _rrect(cv, jx0, y0, jx0 + colw, y0 + ith, 8, fill, outline,
               2 if it.get("rarity") == "rare" else 1)
        _text(cv, jx0 + 9, y0 + ith / 2, "已购" if sold else (it.get("_nm") or it.get("id", "?")),
              "#9a9a9a" if sold else "#ffd75e", (_FONT_BF, 9, "bold"), anchor="w")
        _text(cv, jx0 + colw - 9, y0 + ith / 2, "" if sold else f"{it.get('price', 0)}💰",
              "#9a9a9a" if sold else "#ffe9b0", (_FONT_FB, 9, "bold"), anchor="e")
        ui["solo_shop_jokers"].append((jx0, y0, jx0 + colw, y0 + ith, i))
    for i, it in enumerate(shop.get("cons") or []):
        y0 = yy0 + i * (ith + igap)
        sold = bool(it.get("sold"))
        cat = it.get("cat", "")
        cc = _CON_CAT_COLOR.get(cat, "#3a3a3a")
        fill = "#14141c" if sold else _shade(cc, 0.12)
        outline = _shade("#9a9a9a", -0.3) if sold else "#e6b64c"
        _rrect(cv, cxx0, y0, cxx0 + colw, y0 + ith, 8, fill, outline, 1)
        _text(cv, cxx0 + 9, y0 + ith / 2, "已购" if sold else (it.get("_nm") or it.get("id", "?")),
              "#9a9a9a" if sold else "#ffe9b0", (_FONT_BF, 9, "bold"), anchor="w")
        _text(cv, cxx0 + colw - 9, y0 + ith / 2, "" if sold else f"{it.get('price', 0)}💰",
              "#9a9a9a" if sold else "#ffe9b0", (_FONT_FB, 9, "bold"), anchor="e")
        ui["solo_shop_cons"].append((cxx0, y0, cxx0 + colw, y0 + ith, i))
    # 继续按钮（底部居中）
    cbw, cbh = 200, 40
    cbx0, cby0 = (w - cbw) / 2, pbot - 54
    _rrect(cv, cbx0, cby0, cbx0 + cbw, cby0 + cbh, 11, "#1c4a1c", "#7ee081", 2)
    _text(cv, cbx0 + cbw / 2, cby0 + cbh / 2, "继续 ▶ 下一盲注", "#b0f0a0",
          (_FONT_BF, 13, "bold"), anchor="center")
    ui["solo_shop_continue"] = (cbx0, cby0, cbx0 + cbw, cby0 + cbh)


@_register("balatro_solo")
def _p_balatro_solo(cv, st, me, nick, submit, repaint, ui, priv, w, h):
    """小丑牌·单人闯关：复用多人版牌桌/手牌/出战区/小丑牌绘制，
    另加 卡面强化角标 / 消耗品槽 / 商店面板。单人永远是自己在行动。"""
    _p_balatro_bg(cv, w, h)
    done, winner = _p_balatro_solo_top(cv, w, st, me)
    sel_rects, played, cw, chh, py = _p_balatro_playarea(cv, w, h, priv, ui)
    hand = priv.get("hand") if priv and isinstance(priv.get("hand"), list) else []
    # 结算加分检测：累计分增量 → 出战区上飘 fx
    _p_balatro_fx_detect(ui, st, me, w / 2, py + chh / 2)
    # 我的小丑牌（常驻被动展示）；hbase = 手牌 hover 矩形数量
    jy = py + chh + 26
    hsel = set(priv.get("sel") or []) if priv else set()
    hrow, _h1, _h2, _h3, _h4 = _balatro_hand_layout(hand, hsel, w)
    joker_rects, jchh = _p_balatro_jokers(cv, w, jy, st, me, ui, len(hrow))
    ui["balatro_jokers"] = joker_rects
    # 行动提示（单人版：无"等待/轮到谁"分支）
    prog_y = jy + (8 if joker_rects else 0) + (jchh if joker_rects else 0) + 26
    if st.get("shop_phase"):
        pass   # 商店阶段：提示让给商店面板
    elif done and winner is not None:
        _text(cv, w / 2, prog_y, "🏆 通关全部盲注！", _B_BLNDT,
              (_FONT_BF, 12, "bold"))
    elif done:
        _text(cv, w / 2, prog_y, "💀 生命归零，本局结束", "#e0a0a0",
              (_FONT_BF, 12, "bold"))
    else:
        _text(cv, w / 2, prog_y,
              f"点手牌选牌，凑好牌型后「出牌」（已选 {len(played)}/5）",
              _B_BLNDT, (_FONT_BF, 11, "bold"))
    card_y = max(prog_y + 18, h - 128)
    # 左右两侧：盲注进度 / 手牌结算（贴到手上方，不遮挡点击矩形）
    sidetop = py + chh + 14
    sidebot = card_y - 14
    if sidebot - sidetop >= 40 and w >= 560:
        _p_balatro_blind(cv, w, me, st, sidetop, sidebot)
        _p_balatro_score(cv, w, me, played, st, sidetop, sidebot,
                         hlev=(st.get("hand_level") or {}))
    # 非商店阶段：画消耗品槽（手牌上方）；商店阶段：画商店面板覆盖中部
    if not st.get("shop_phase"):
        _p_balatro_solo_cons(cv, w, priv, ui, card_y - 58)
    else:
        _p_balatro_solo_shop(cv, w, h, st, ui)
        ui["_solo_use"] = None
    hand_rects = _p_balatro_hand(cv, w, card_y, hand, hsel, ui, repaint)
    # 上飘文字覆盖在最上层；hover 命中区 = 手牌矩形 + 小丑矩形
    _p_balatro_fx_draw(cv, ui, repaint)
    _hov_rects(ui, hand_rects + joker_rects)
    ui.update(game="balatro_solo")


# ---------------------------------------------------------------------------
# 兜底：美化卡片（未实现专属 painter 的游戏）
# ---------------------------------------------------------------------------
def _generic(cv, game, st, me, nick, w, h, priv):
    accent_t, accent_b = THEME.get(game, ("#4a4f5a", "#333842"))
    label = game
    _grad(cv, 0, 0, w, h, _shade(accent_t, 0.2), accent_b)
    _text(cv, w / 2, 60, f"🎮 {label}", "#fff", _FONT_H)
    status = st.get("status") if isinstance(st, dict) else None
    if status:
        _text(cv, w / 2, 104, f"状态：{status}", "#e8e8e8", _FONT_F)
    if isinstance(st, dict):
        # 每位玩家牌
        players = st.get("players") or []
        if players:
            _text(cv, w / 2, 150, "玩家：" + "　".join(
                nick(int(u)) + ("（我）" if int(u) == me else "") for u in players),
                "#fff", _FONT_F)
        turn = st.get("turn_uid") or st.get("current_uid")
        if turn is not None:
            _text(cv, w / 2, 190, f"轮到：{nick(int(turn))}",
                  "#ffd75e", _FONT_B)
        scores = st.get("scores") or {}
        if scores:
            _text(cv, w / 2, h - 40, "积分：" + "　".join(
                f"{nick(int(u))}:{v}" for u, v in sorted(scores.items())),
                "#e8e8e8", _FONT_F)
    _text(cv, w / 2, h - 16, "操作见下方按钮区", "#b0b0b0",
          (_FONT_F[0], 9))
