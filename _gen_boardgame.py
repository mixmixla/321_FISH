# -*- coding: utf-8 -*-
"""程序化生成桌游对局内美术素材（原创，无外部/网络素材依赖）。

产物：
  assets/boardgame/*.png   —— PNG 源文件（可提交、可复用）
  _art_boardgame.py        —— base64 内嵌模块（仿 _art.py，随源码打包）

用法（开发期运行一次）：
  python _gen_boardgame.py
"""
import base64
import io
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter

OUT_DIR = os.path.join("assets", "boardgame")
OUT_MODULE = "_art_boardgame.py"
SS = 4          # 矢量组件超采样倍数
TAU = math.tau


# ---------------------------------------------------------------- 基础工具
def _clamp(v):
    return 0 if v < 0 else (255 if v > 255 else int(v))


def _rgba(hexstr, a=255):
    h = hexstr.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def _mix(hexstr, f):
    """f>0 提亮，f<0 压暗，返回带 alpha 的元组。"""
    r, g, b, _ = _rgba(hexstr)
    if f >= 0:
        r = r + (255 - r) * f
        g = g + (255 - g) * f
        b = b + (255 - b) * f
    else:
        r *= (1 + f)
        g *= (1 + f)
        b *= (1 + f)
    return (_clamp(r), _clamp(g), _clamp(b), 255)


def _begin(w, h, scale=SS):
    img = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), scale


def _end(img, w, h):
    return img.resize((w, h), Image.Resampling.LANCZOS)


# 可平铺值噪声：period×period 随机格 + 双线性插值（环绕），保证四边无缝。
def _noise_grid(period, seed):
    rnd = random.Random(seed)
    return [[rnd.random() for _ in range(period)] for _ in range(period)]


def _sample(grid, u, v):
    p = len(grid)
    x = (u % 1.0) * p
    y = (v % 1.0) * p
    x0 = int(math.floor(x))
    y0 = int(math.floor(y))
    fx = x - x0
    fy = y - y0
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    x0 %= p
    y0 %= p
    x1 = (x0 + 1) % p
    y1 = (y0 + 1) % p
    a = grid[y0][x0]
    b = grid[y0][x1]
    c = grid[y1][x0]
    d = grid[y1][x1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def _star_pts(cx, cy, r_out, r_in, n=8, rot=-math.pi / 2):
    """星形顶点：交替内外半径的 2n 个未缩放顶点（调用方逐点缩放）。"""
    pts = []
    for i in range(2 * n):
        rr = r_out if i % 2 == 0 else r_in
        a = rot + i * math.pi / n
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


# ---------------------------------------------------------------- A 类 · 材质底纹
def make_wood(size=256, seed=7):
    """木纹。纵向纹理条带 + 低频扭曲，四边可平铺。"""
    img = Image.new("RGBA", (size, size))
    px = img.load()
    base = (150, 103, 60)
    warp = _noise_grid(18, seed)
    fine = _noise_grid(72, seed + 5)
    rings = 12.0
    for y in range(size):
        v = y / size
        for x in range(size):
            u = x / size
            w = _sample(warp, u, v)
            f = _sample(fine, u * 3, v * 3)
            band = 0.5 + 0.5 * math.sin((u * rings + w * 1.7) * TAU)
            s = 0.78 + 0.28 * band + 0.09 * (f - 0.5)
            px[x, y] = (_clamp(base[0] * s), _clamp(base[1] * s),
                        _clamp(base[2] * s), 255)
    return img.filter(ImageFilter.GaussianBlur(0.4))


def make_felt(size=256, seed=11):
    """毡布绒面。低对比颗粒噪声。"""
    img = Image.new("RGBA", (size, size))
    px = img.load()
    base = (44, 86, 80)
    n1 = _noise_grid(26, seed)
    n2 = _noise_grid(96, seed + 3)
    for y in range(size):
        v = y / size
        for x in range(size):
            u = x / size
            f = (_sample(n1, u, v) - 0.5) * 12 + (_sample(n2, u, v) - 0.5) * 7
            px[x, y] = (_clamp(base[0] + f), _clamp(base[1] + f),
                        _clamp(base[2] + f), 255)
    return img.filter(ImageFilter.GaussianBlur(0.5))


def make_paper(size=256, seed=23):
    """纸面纤维。暖白底 + 纵向细纤维。"""
    img = Image.new("RGBA", (size, size))
    px = img.load()
    base = (240, 232, 214)
    n1 = _noise_grid(30, seed)
    n2 = _noise_grid(120, seed + 9)
    for y in range(size):
        v = y / size
        for x in range(size):
            u = x / size
            f = (_sample(n1, u, v) - 0.5) * 8 + (_sample(n2, u, v) - 0.5) * 6
            fib = math.sin(u * 180 * math.pi) * 1.2   # 90 周期 → 可平铺
            px[x, y] = (_clamp(base[0] + f + fib), _clamp(base[1] + f + fib),
                        _clamp(base[2] + f + fib), 255)
    return img.filter(ImageFilter.GaussianBlur(0.4))


# ---------------------------------------------------------------- B 类 · 通用组件
def make_card_frame(w=96, h=136):
    """卡牌正框（扁平）：奶咖纸面 + 双描边 + 收敛的顶部高光。"""
    img, dr, s = _begin(w, h)

    def R(v):
        return v * s

    dr.rounded_rectangle((R(2), R(2), R(w - 2), R(h - 2)), radius=R(14),
                         fill=_rgba("#f6efe0"))
    sheen = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sheen).rounded_rectangle(
        (R(8), R(8), R(w - 8), R(h * 0.22)), radius=R(10), fill=(255, 255, 255, 64))
    img = Image.alpha_composite(img, sheen)
    dr2 = ImageDraw.Draw(img)
    dr2.rounded_rectangle((R(7), R(7), R(w - 7), R(h - 7)), radius=R(10),
                          outline=_rgba("#c9b48f"), width=max(1, int(1.2 * s)))
    dr2.rounded_rectangle((R(2), R(2), R(w - 2), R(h - 2)), radius=R(14),
                          outline=_rgba("#b0966e"), width=max(1, int(1.7 * s)))
    return _end(img, w, h)


def make_card_back(w=96, h=136):
    """卡背：深青斜纹 + 中央徽章。"""
    s = SS
    W, H = w * s, h * s

    def R(v):
        return v * s

    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (R(2), R(2), R(w - 2), R(h - 2)), radius=R(10), fill=255)
    face = Image.new("RGBA", (W, H), _rgba("#22404a"))
    fd = ImageDraw.Draw(face)
    step = R(12)
    for i in range(-H, W + H, step):
        fd.line((i, 0, i + H, H), fill=_rgba("#3f737d"), width=max(1, int(1.1 * s)))
        fd.line((i, 0, i - H, H), fill=_rgba("#2c5660"), width=max(1, int(1.1 * s)))
    face = face.filter(ImageFilter.GaussianBlur(0.3 * s))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.paste(face, (0, 0), mask)
    od = ImageDraw.Draw(out)
    od.rounded_rectangle((R(2), R(2), R(w - 2), R(h - 2)), radius=R(10),
                         outline=_rgba("#7faeae"), width=max(1, int(1.6 * s)))
    cx, cy = W * 0.5, H * 0.5
    od.ellipse((cx - R(15), cy - R(15), cx + R(15), cy + R(15)),
               fill=_rgba("#1a323a"), outline=_rgba("#9fc9c0"), width=max(1, int(1.4 * s)))
    od.ellipse((cx - R(7), cy - R(7), cx + R(7), cy + R(7)), fill=_rgba("#c9e2da"))
    return _end(out, w, h)


def make_coin(size=48):
    """立体金币/筹码：同心圈 + 顶部高光 + 中央星徽。"""
    img, dr, s = _begin(size, size)

    def R(v):
        return v * s

    dr.ellipse((R(2), R(2), R(size - 2), R(size - 2)), fill=_rgba("#d6a83c"))
    dr.ellipse((R(5), R(5), R(size - 5), R(size - 5)), outline=_rgba("#f6dc8c"),
               width=max(1, int(1.6 * s)))
    dr.ellipse((R(8), R(8), R(size - 8), R(size - 8)), outline=_rgba("#a97c28"),
               width=max(1, int(1.1 * s)))
    hl = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse((R(9), R(7), R(22), R(15)), fill=(255, 255, 255, 90))
    img = Image.alpha_composite(img, hl)
    dd = ImageDraw.Draw(img)
    dd.ellipse((R(2), R(2), R(size - 2), R(size - 2)), outline=_rgba("#8a6522"),
               width=max(1, int(1.6 * s)))
    cx = cy = size / 2
    star = []
    for i in range(10):
        rr = size * 0.20 if i % 2 == 0 else size * 0.09
        a = -math.pi / 2 + i * math.pi / 5
        star.append((R(cx + rr * math.cos(a)), R(cy + rr * math.sin(a))))
    dd.polygon(star, fill=_rgba("#fdf0c0"), outline=_rgba("#9c7222"))
    return _end(img, size, size)


def make_token(size=40):
    """通用指示物：深灰圆牌 + 内环 + 高光。"""
    img, dr, s = _begin(size, size)

    def R(v):
        return v * s

    dr.ellipse((R(2), R(2), R(size - 2), R(size - 2)), fill=_rgba("#4a4a58"))
    dr.ellipse((R(6), R(6), R(size - 6), R(size - 6)), fill=_rgba("#5c5c6e"))
    dr.ellipse((R(9), R(9), R(size - 9), R(size - 9)), outline=_rgba("#8f8fa6"),
               width=max(1, int(1.2 * s)))
    hl = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse((R(8), R(6), R(18), R(13)), fill=(255, 255, 255, 80))
    img = Image.alpha_composite(img, hl)
    ImageDraw.Draw(img).ellipse((R(2), R(2), R(size - 2), R(size - 2)),
                                outline=_rgba("#20202a"), width=max(1, int(1.5 * s)))
    return _end(img, size, size)


def make_panel(size=60, border=12):
    """9-slice 面板底（浅底）：圆角恰好落在 border 内，中心区域平整可拉伸。"""
    img, dr, s = _begin(size, size)

    def R(v):
        return v * s

    dr.rounded_rectangle((R(1), R(1), R(size - 1), R(size - 1)), radius=R(border),
                         fill=_rgba("#F4F8FB"), outline=_rgba("#DCE6E2"),
                         width=max(1, int(1.4 * s)))
    return _end(img, size, size)


_DIE_PIPS = {
    1: [(0.5, 0.5)],
    2: [(0.30, 0.30), (0.70, 0.70)],
    3: [(0.28, 0.28), (0.50, 0.50), (0.72, 0.72)],
    4: [(0.30, 0.30), (0.30, 0.70), (0.70, 0.30), (0.70, 0.70)],
    5: [(0.30, 0.30), (0.30, 0.70), (0.70, 0.30), (0.70, 0.70), (0.50, 0.50)],
    6: [(0.32, 0.28), (0.32, 0.50), (0.32, 0.72), (0.68, 0.28), (0.68, 0.50), (0.68, 0.72)],
}


def make_die_face(n, size=48):
    """六面骰面：倒角白方 + 点数。"""
    img, dr, s = _begin(size, size)

    def R(v):
        return v * s

    dr.rounded_rectangle((R(2), R(2), R(size - 2), R(size - 2)), radius=R(9),
                         fill=_rgba("#f8f5ee"))
    bev = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(bev)
    bd.rounded_rectangle((R(4), R(4), R(size - 4), R(size * 0.5)), radius=R(7),
                         fill=(255, 255, 255, 70))
    bd.rounded_rectangle((R(4), R(size * 0.62), R(size - 4), R(size - 4)), radius=R(7),
                         fill=(0, 0, 0, 40))
    img = Image.alpha_composite(img, bev)
    dd = ImageDraw.Draw(img)
    pr = size * 0.088
    for fx, fy in _DIE_PIPS[n]:
        x, y = fx * size, fy * size
        dd.ellipse((R(x - pr), R(y - pr), R(x + pr), R(y + pr)), fill=_rgba("#33333f"))
        dd.ellipse((R(x - pr * 0.6), R(y - pr * 0.75), R(x + pr * 0.1), R(y - pr * 0.1)),
                   fill=_rgba("#6a6a7a"))
    dd.rounded_rectangle((R(2), R(2), R(size - 2), R(size - 2)), radius=R(9),
                         outline=_rgba("#9a8f79"), width=max(1, int(1.6 * s)))
    return _end(img, size, size)


# ---------------------------------------------------------------- C 类 · 主题专属
_AZUL = {"r": "#d2534f", "w": "#f0f0f0", "b": "#4a7de0", "y": "#e0b33c", "k": "#3a3a3a"}
_GEM = {"o": "#3a3a3a", "d": "#eef2f4", "r": "#d2534f", "e": "#3a9b5f",
        "s": "#4a7de0", "g": "#e0b33c"}
_AZULEJO_BG = "#F4F8FB"
_AZULEJO_BLUE = "#3E7CB1"
_AZULEJO_DEEP = "#2B5E8C"
_AZULEJO_GRID = "#6FA8CE"
_AZULEJO_PETAL = "#DCEAF4"


def make_azulejo(size=256):
    """现代扁平花砖：4×4 单元四瓣花 + 八角星，四边天然无缝。"""
    img, dr, s = _begin(size, size)

    def R(v):
        return v * s

    P = size // 4
    dr.rectangle((0, 0, R(size), R(size)), fill=_rgba(_AZULEJO_BG))
    wl = max(1, int(1.0 * s))
    for i in range(4):
        q = i * P
        dr.rectangle((R(q), 0, R(q) + wl, R(size)), fill=_rgba(_AZULEJO_GRID))
        dr.rectangle((0, R(q), R(size), R(q) + wl), fill=_rgba(_AZULEJO_GRID))
    petal_r = 0.20 * P
    off = 0.18 * P
    for j in range(4):
        for i in range(4):
            cx = (i + 0.5) * P
            cy = (j + 0.5) * P
            for dx, dy in ((off, 0), (-off, 0), (0, off), (0, -off)):
                px, py = cx + dx, cy + dy
                dr.ellipse((R(px - petal_r), R(py - petal_r),
                            R(px + petal_r), R(py + petal_r)),
                           fill=_rgba(_AZULEJO_PETAL))
            star = _star_pts(cx, cy, P * 0.30, P * 0.13, 8)
            dr.polygon([(R(x), R(y)) for (x, y) in star], fill=_rgba(_AZULEJO_BLUE))
            cr = 0.07 * P
            dr.ellipse((R(cx - cr), R(cy - cr), R(cx + cr), R(cy + cr)),
                       fill=_rgba(_AZULEJO_DEEP))
    return _end(img, size, size)


def make_azul_board(size=96, border=14):
    """对局底板：浅底 + 外深描边 + 内白描边，大圆角。"""
    img, dr, s = _begin(size, size)

    def R(v):
        return v * s

    dr.rounded_rectangle((R(2), R(2), R(size - 2), R(size - 2)), radius=R(border),
                         fill=_rgba("#EAF2F7"), outline=_rgba("#8FB6CE"),
                         width=max(1, int(1.6 * s)))
    dr.rounded_rectangle((R(5), R(5), R(size - 5), R(size - 5)),
                         radius=R(border - 4), outline=_rgba("#FBFDFE"),
                         width=max(1, int(1.2 * s)))
    return _end(img, size, size)


def make_azul_score_track(w=96, h=48, border=14):
    """计分轨：深蓝底 + 外深描边 + 内浅描边，大圆角。"""
    img, dr, s = _begin(w, h)

    def R(v):
        return v * s

    dr.rounded_rectangle((R(2), R(2), R(w - 2), R(h - 2)), radius=R(border),
                         fill=_rgba("#2E4A63"), outline=_rgba("#101E2C"),
                         width=max(1, int(1.6 * s)))
    dr.rounded_rectangle((R(5), R(5), R(w - 5), R(h - 5)),
                         radius=R(border - 4), outline=_rgba("#4A7096"),
                         width=max(1, int(1.2 * s)))
    return _end(img, w, h)


def make_azul_tile(hexstr, size=44):
    """花砖：圆角釉面 + 内嵌描边 + 高光带。"""
    img, dr, s = _begin(size, size)

    def R(v):
        return v * s

    light = hexstr == "#f0f0f0"
    dr.rounded_rectangle((R(1), R(1), R(size - 1), R(size - 1)), radius=R(6),
                         fill=_rgba(hexstr))
    dr.rounded_rectangle((R(4), R(4), R(size - 4), R(size - 4)), radius=R(4),
                         outline=_mix(hexstr, -0.18 if light else -0.25),
                         width=max(1, int(1.2 * s)))
    gl = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(gl).rounded_rectangle(
        (R(5), R(4), R(size - 5), R(size * 0.40)), radius=R(4),
        fill=(255, 255, 255, 64 if light else 40))
    img = Image.alpha_composite(img, gl)
    ImageDraw.Draw(img).rounded_rectangle(
        (R(1), R(1), R(size - 1), R(size - 1)), radius=R(6),
        outline=_mix(hexstr, -0.22 if light else -0.38), width=max(1, int(1.5 * s)))
    return _end(img, size, size)


def make_azul_bowl(size=128, seed=99):
    """工厂碗（扁平）：浅色滚边 + 深蓝内膛 + 克制高光。"""
    img, dr, s = _begin(size, size)

    def R(v):
        return v * s

    c = size / 2
    dr.ellipse((R(3), R(3), R(size - 3), R(size - 3)), fill=_rgba("#101E2C"))
    rr = size * 0.075
    ring = c - 6 - rr
    for i in range(16):
        a = i * TAU / 16
        px = c + ring * math.cos(a)
        py = c + ring * math.sin(a)
        dr.ellipse((R(px - rr), R(py - rr), R(px + rr), R(py + rr)),
                   fill=_rgba("#EAF2F7"))
    dr.ellipse((R(6), R(6), R(size - 6), R(size - 6)), fill=_rgba("#2E4A63"))
    dr.ellipse((R(size * 0.20), R(size * 0.20), R(size * 0.80), R(size * 0.80)),
               outline=_rgba("#8FB6CE"), width=max(1, int(4 * s)))
    dr.ellipse((R(size * 0.26), R(size * 0.26), R(size * 0.74), R(size * 0.74)),
               fill=_rgba("#1E3346"))
    hl = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse(
        (R(size * 0.28), R(size * 0.26), R(size * 0.52), R(size * 0.44)),
        fill=(255, 255, 255, 46))
    img = Image.alpha_composite(img, hl)
    return _end(img, size, size)


def make_gem(hexstr, size=40):
    """宝石：六角刻面 + 台面 + 高光。"""
    img, dr, s = _begin(size, size)

    def R(v):
        return v * s

    c = size / 2

    def hexagon(rr):
        return [(R(c + rr * math.cos(math.radians(a))),
                 R(c + rr * math.sin(math.radians(a))))
                for a in (90, 150, 210, 270, 330, 30)]

    outer = hexagon(size * 0.46)
    inn = hexagon(size * 0.28)
    dr.polygon(outer, fill=_mix(hexstr, -0.10))
    dr.polygon(inn, fill=_mix(hexstr, 0.22))
    for i in range(0, 6, 2):
        dr.line((outer[i][0], outer[i][1], inn[i][0], inn[i][1]),
                fill=_mix(hexstr, -0.30), width=max(1, int(0.9 * s)))
    for i in range(0, 6, 2):
        dr.line((inn[i][0], inn[i][1], inn[(i + 1) % 6][0], inn[(i + 1) % 6][1]),
                fill=_mix(hexstr, 0.38), width=max(1, int(0.9 * s)))
    dr.polygon(outer, outline=_mix(hexstr, -0.42))
    hl = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse(
        (R(c - size * 0.16), R(c - size * 0.20), R(c - size * 0.02), R(c - size * 0.06)),
        fill=(255, 255, 255, 200 if hexstr == "#eef2f4" else 140))
    img = Image.alpha_composite(img, hl)
    return _end(img, size, size)


# ---------------------------------------------------------------- 汇总 / 输出
def build_all():
    assets = {
        "wood": make_wood(),
        "felt": make_felt(),
        "paper": make_paper(),
        "card_frame": make_card_frame(),
        "card_back": make_card_back(),
        "coin": make_coin(),
        "token": make_token(),
        "panel": make_panel(),
    }
    for n in range(1, 7):
        assets[f"die_face{n}"] = make_die_face(n)
    for k, hx in _AZUL.items():
        assets[f"azul_tile_{k}"] = make_azul_tile(hx)
    assets["azul_bowl"] = make_azul_bowl()
    assets["azulejo"] = make_azulejo()
    assets["azul_board"] = make_azul_board()
    assets["azul_score_track"] = make_azul_score_track()
    for k, hx in _GEM.items():
        assets[f"gem_{k}"] = make_gem(hx)
    return assets


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    assets = build_all()
    lines = [
        "# -*- coding: utf-8 -*-",
        "# 内嵌原创桌游对局美术（由 _gen_boardgame.py 程序化生成，无外部/网络素材依赖）。",
        "# 重生成：python _gen_boardgame.py",
        "ASSETS = {",
    ]
    for key in sorted(assets):
        img = assets[key]
        img.save(os.path.join(OUT_DIR, key + ".png"))
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        lines.append(f"    {key!r}: 'data:image/png;base64,{b64}',")
    lines.append("}")
    lines.append("")
    with open(OUT_MODULE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"generated {len(assets)} assets -> {OUT_DIR}/ and {OUT_MODULE}")


if __name__ == "__main__":
    main()
