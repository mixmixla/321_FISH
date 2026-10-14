# -*- coding: utf-8 -*-
"""Azul 展示包素材生成器（程序化原创，仅风格对标，无外部素材依赖）。

产物：
  boardgames/azul/assets/*.png   —— 15 个 PNG 源文件（可提交）
  boardgames/azul/_art.py        —— base64 内嵌模块（ASSETS = {...}）

用法（开发期运行一次）：
  python -m boardgames.azul.sprites

设计：本模块自包含（不 import 共享生成器），沿用 4× 超采样（SS=4）与
_begin/_end/_mix 惯例；所有坐标在超采样画布上按 R(v)=v*SS 缩放，
最后 LANCZOS 收敛到目标尺寸。
"""
from __future__ import annotations

import base64
import io
import math
from pathlib import Path

from PIL import Image, ImageDraw

SS = 4
HERE = Path(__file__).resolve().parent
ASSETS_DIR = HERE / "assets"
ART_MODULE = HERE / "_art.py"

# ---------------------------------------------------------------- 调色（程序化原创，仅风格对标）
_TABLE_BG = "#16232E"
_TABLE_STRIPE = "#1B2C3A"
_BOARD_BG = "#F7FAFC"
_BOARD_PETAL = "#DCEAF4"
_BOARD_STAR = "#3E7CB1"
_BOARD_CORE = "#2B5E8C"
_CELL_BG = "#F2F6F8"
_CELL_EDGE = "#DCE6E2"
_PLATE_BODY = "#F7FAFC"
_PLATE_EDGE = "#2E4A63"
_PLATE_RING = "#8FB6CE"
_PLATE_BORE = "#E6EFF5"
_TRACK_BG = "#24405A"
_TRACK_OUT = "#101E2C"
_TRACK_IN = "#4A7096"
_FLOOR_BG = "#F2F6F8"
_FLOOR_EDGE = "#8FB6CE"
_TILE = {"r": "#D2534F", "w": "#F0F0F0", "b": "#4A7DE0", "y": "#E0B33C", "k": "#3A3A3A"}


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


def _star_pts(cx, cy, r_out, r_in, n=8, rot=-math.pi / 2):
    """星形顶点：交替内外半径的 2n 个未缩放顶点（调用方逐点缩放）。"""
    pts = []
    for i in range(2 * n):
        rr = r_out if i % 2 == 0 else r_in
        a = rot + i * math.pi / n
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def _datauri(img):
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return "data:image/png;base64," + b64


# ---------------------------------------------------------------- 素材
def make_table(size=128):
    """深蓝灰桌布 + 极淡斜纹；纹样周期整除边长，四边无缝可平铺。"""
    img, dr, s = _begin(size, size)

    def R(v):
        return v * s

    dr.rectangle((0, 0, R(size), R(size)), fill=_rgba(_TABLE_BG))
    step = size // 8                 # 16 → 整除 128，保证平铺无缝
    wl = max(1, int(1.0 * s))
    for c in range(-size, 2 * size, step):
        dr.line((R(c), 0, R(c + size), R(size)),
                fill=_rgba(_TABLE_STRIPE), width=wl)
    return _end(img, size, size)


def make_boardface(size=256):
    """阿兹勒赫密铺：4×4 单元（四瓣花 + 八角星 + 星芯），不画网格线。"""
    img, dr, s = _begin(size, size)

    def R(v):
        return v * s

    P = size // 4
    dr.rectangle((0, 0, R(size), R(size)), fill=_rgba(_BOARD_BG))
    petal_r = 0.20 * P
    off = 0.18 * P                  # 花瓣最大外扩 off+petal_r=0.38P < 半单元宽 0.5P
    for j in range(4):
        for i in range(4):
            cx = (i + 0.5) * P
            cy = (j + 0.5) * P
            for dx, dy in ((off, 0), (-off, 0), (0, off), (0, -off)):
                px, py = cx + dx, cy + dy
                dr.ellipse((R(px - petal_r), R(py - petal_r),
                            R(px + petal_r), R(py + petal_r)),
                           fill=_rgba(_BOARD_PETAL))
            star = _star_pts(cx, cy, P * 0.30, P * 0.13, 8)
            dr.polygon([(R(x), R(y)) for (x, y) in star], fill=_rgba(_BOARD_STAR))
            cr = 0.07 * P
            dr.ellipse((R(cx - cr), R(cy - cr), R(cx + cr), R(cy + cr)),
                       fill=_rgba(_BOARD_CORE))
    return _end(img, size, size)


def make_plate(size=128):
    """亮色陶瓷盘：深边 → 盘身 → 内环 → 内膛 → 克制高光；四角透明（RGBA）。"""
    img, dr, s = _begin(size, size)

    def R(v):
        return v * s

    dr.ellipse((R(3), R(3), R(size - 3), R(size - 3)), fill=_rgba(_PLATE_EDGE))
    dr.ellipse((R(5), R(5), R(size - 5), R(size - 5)), fill=_rgba(_PLATE_BODY))
    dr.ellipse((R(size * 0.20), R(size * 0.20), R(size * 0.80), R(size * 0.80)),
               outline=_rgba(_PLATE_RING), width=max(1, int(4 * s)))
    dr.ellipse((R(size * 0.26), R(size * 0.26), R(size * 0.74), R(size * 0.74)),
               fill=_rgba(_PLATE_BORE))
    hl = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse(
        (R(size * 0.28), R(size * 0.26), R(size * 0.52), R(size * 0.44)),
        fill=(255, 255, 255, 46))
    img = Image.alpha_composite(img, hl)
    return _end(img, size, size)


def make_track(w=96, h=48, border=14):
    """计分轨底：深蓝 + 外深/内浅描边，大圆角，供九宫格拉伸（刻度由画布端绘制）。"""
    img, dr, s = _begin(w, h)

    def R(v):
        return v * s

    dr.rounded_rectangle((R(2), R(2), R(w - 2), R(h - 2)), radius=R(border),
                         fill=_rgba(_TRACK_BG), outline=_rgba(_TRACK_OUT),
                         width=max(1, int(1.6 * s)))
    dr.rounded_rectangle((R(5), R(5), R(w - 5), R(h - 5)), radius=R(border - 4),
                         outline=_rgba(_TRACK_IN), width=max(1, int(1.2 * s)))
    return _end(img, w, h)


def make_floor(size=48):
    """地板槽：浅底 + 描边，圆角。"""
    img, dr, s = _begin(size, size)

    def R(v):
        return v * s

    dr.rounded_rectangle((R(2), R(2), R(size - 2), R(size - 2)), radius=R(8),
                         fill=_rgba(_FLOOR_BG), outline=_rgba(_FLOOR_EDGE),
                         width=max(1, int(1.6 * s)))
    return _end(img, size, size)


def make_wall_cell(color, size=48):
    """空墙格：米白底 + 内描边 + 该色淡印星纹（alpha≈64，示意该格花色）。"""
    img, dr, s = _begin(size, size)

    def R(v):
        return v * s

    dr.rounded_rectangle((R(2), R(2), R(size - 2), R(size - 2)), radius=R(7),
                         fill=_rgba(_CELL_BG))
    dr.rounded_rectangle((R(6), R(6), R(size - 6), R(size - 6)), radius=R(5),
                         outline=_rgba(_CELL_EDGE), width=max(1, int(1.4 * s)))
    r, g, b, _ = _rgba(_TILE[color])
    tint = Image.new("RGBA", img.size, (0, 0, 0, 0))
    star = _star_pts(size / 2, size / 2, size * 0.22, size * 0.10, 8)
    ImageDraw.Draw(tint).polygon([(R(x), R(y)) for (x, y) in star],
                                 fill=(r, g, b, 64))
    img = Image.alpha_composite(img, tint)
    return _end(img, size, size)


def make_tile(color, size=44):
    """圆角花砖（较旧版更饱和）：主体该色 + 顶部高光 alpha 64 + 外描边 _mix(color,-0.30)。"""
    hexstr = _TILE[color]
    img, dr, s = _begin(size, size)

    def R(v):
        return v * s

    dr.rounded_rectangle((R(1), R(1), R(size - 1), R(size - 1)), radius=R(6),
                         fill=_rgba(hexstr))
    gl = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(gl).rounded_rectangle(
        (R(5), R(4), R(size - 5), R(size * 0.42)), radius=R(4),
        fill=(255, 255, 255, 64))
    img = Image.alpha_composite(img, gl)
    ImageDraw.Draw(img).rounded_rectangle(
        (R(1), R(1), R(size - 1), R(size - 1)), radius=R(6),
        outline=_mix(hexstr, -0.30), width=max(1, int(1.5 * s)))
    return _end(img, size, size)


# ---------------------------------------------------------------- 汇总 / 输出
def _build_images():
    imgs = {
        "azul_table": make_table(),
        "azul_boardface": make_boardface(),
        "azul_plate": make_plate(),
        "azul_track": make_track(),
        "azul_floor": make_floor(),
    }
    for c in "rwbyk":
        imgs[f"azul_wall_cell_{c}"] = make_wall_cell(c)
        imgs[f"azul_tile_{c}"] = make_tile(c)
    return imgs


def build_all():
    """返回 15 个素材的 PNG data URI（键序无关）。"""
    return {key: _datauri(img) for key, img in _build_images().items()}


def main():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    imgs = _build_images()
    lines = [
        "# -*- coding: utf-8 -*-",
        "# Azul 展示包内嵌原创素材（由 boardgames/azul/sprites.py 程序化生成，无外部素材依赖）。",
        "# 重生成：python -m boardgames.azul.sprites",
        "ASSETS = {",
    ]
    for key in sorted(imgs):
        img = imgs[key]
        img.save(ASSETS_DIR / f"{key}.png")
        lines.append(f"    {key!r}: {_datauri(img)!r},")
    lines.append("}")
    lines.append("")
    ART_MODULE.write_text("\n".join(lines), encoding="utf-8")
    print(f"generated {len(imgs)} azul assets")


if __name__ == "__main__":
    main()
