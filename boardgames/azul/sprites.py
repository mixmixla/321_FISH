# -*- coding: utf-8 -*-
"""Azul 展示包素材生成器（22 键；在共享 artkit + geom 之上程序化原创，无外部素材）。

产物：
  boardgames/azul/assets/*.png   —— 22 个 PNG 源文件（可提交）
  boardgames/azul/_art.py        —— base64 内嵌模块（ASSETS = {...}）

用法（开发期运行一次）：python -m boardgames.azul.sprites
"""
from __future__ import annotations

import base64
import io
import math
from pathlib import Path

from PIL import Image, ImageDraw

from boardgames import artkit as ak
from boardgames import geom

HERE = Path(__file__).resolve().parent
ASSETS_DIR = HERE / "assets"
ART_MODULE = HERE / "_art.py"

# 调色（程序化原创，仅风格对标；花砖 5 色沿用引擎）
TILE = {"r": "#D2534F", "w": "#F0F0F0", "b": "#4A7DE0", "y": "#E0B33C",
        "k": "#3A3A3A"}
_ORDER = "rwbyk"                 # 墙色循环顺序（花砖 5 色）
_WALL_BG = "#F7FAFC"
_WALL_BLUE = "#4A7DE0"
_WALL_DEEP = "#2B5E8C"
_BOARD_BG = "#F6F1E7"
_BOARD_STRIPE = "#EFE7D6"
_BOARD_BAND = "#3E7CB1"
_SLOT_BG = "#E4D9C3"
_SLOT_BD = "#CDBE9C"
_PLATE_RIM = "#2E4A63"
_PLATE_BODY = "#F7FAFC"
_PLATE_GOLD = "#C9A227"
_RING_RIM = "#16232E"
_RING_BODY = "#24405A"
_RING_TICK = "#BBD3E6"
_FLOOR_BG = "#F2F6F8"
_FLOOR_BD = "#8FB6CE"
_CHIP = "#F3E3B0"


def _datauri(img):
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _blank(w, h):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def make_wall_bg(size=512):
    """瓷砖墙背景：4×4 大尺度阿兹勒赫，蓝/白两色，周期 128 整除 512 ⇒ 无缝。"""
    return ak.ornament_tile(size, _WALL_BG, _WALL_BLUE, _WALL_DEEP, cells=4)


def make_plate(size=160, center=False):
    """陶瓷工厂盘：深蓝厚边 + 盘面 + 内环 + 底部投影；中央池加金边。"""
    img = _blank(size, size)
    r = size * 0.44
    img = ak.shadow(img, (size * 0.06, size * 0.09, size * 0.94, size * 0.94),
                    r * 0.5, spread=4, alpha=80, offset=(0, 2))
    img = ak.disc(img, (size * 0.05, size * 0.05, size * 0.95, size * 0.95),
                  _PLATE_RIM, _PLATE_BODY,
                  ring=_PLATE_GOLD if center else _WALL_DEEP)
    return img


def make_tile(color, size=48):
    """立体花砖：上亮下暗的竖向渐变 + 斜边内缘。"""
    return ak.gem(_blank(size, size), (2, 2, size - 2, size - 2), TILE[color],
                  shape="tile")


def make_marker(color, size=40):
    """计分轨玩家棋子（瓷盘外形 + 该色实心）。"""
    return ak.gem(_blank(size, size), (2, 2, size - 2, size - 2), TILE[color],
                  shape="marker")


def make_chip(size=64):
    """分数筹码：深色轮缘 + 实色圆面 + 浅描内环（超采样后收敛）。"""
    img, _dr, s = ak.canvas(size, size)
    img = ak.chip(img, (3, 3, size - 3, size - 3), _CHIP, s=s)
    return ak.finish(img, size, size)


def make_wall_cell(color, size=48):
    """墙位预印目标色：内凹槽 + 该色淡印八角星（alpha≈70）。"""
    img = _blank(size, size)
    box = (2, 2, size - 2, size - 2)
    img = ak.recess(img, box, size * 0.16, _SLOT_BG, depth=2)
    dr = ImageDraw.Draw(img)
    pts = ak._star_pts(size / 2.0, size / 2.0, size * 0.26, size * 0.12, 8)
    r, g, b, _ = ak.color(TILE[color])
    dr.polygon(pts, fill=(r, g, b, 70))
    return img


def make_floor(size=48):
    """地板槽：内凹 + 冷灰描边，提示「扣分行」。"""
    img = _blank(size, size)
    return ak.recess(img, (2, 2, size - 2, size - 2), size * 0.14, _FLOOR_BG, depth=3)


def make_board(w=384, h=288):
    """玩家板：奶油底 + 细斜纹 + 左侧彩布边 + 铭牌照 + 5 条花纹凹槽
    + 5×5 墙位（预印目标色）+ 底部 7 格地板线；用 geom 保证与落子坐标一致。"""
    img, _dr, s = ak.canvas(w, h)
    img = ak.linen(img, (0, 0, w, h), w * 0.05, _BOARD_BG, s=s, amount=5, seed=11)
    dr = ImageDraw.Draw(img)
    step = w / 32.0
    for k in range(-1, 33):
        dr.line((k * step * s, 0, (k * step + h) * s, h * s),
                fill=ak.color(_BOARD_STRIPE), width=1)
    band = w * 0.008
    for i, c in enumerate(_ORDER):
        dr.rectangle((i * band * s, 0, (i + 1) * band * s, h * s),
                     fill=ak.color(TILE[c]))
    img = ak.rrect_bevel(img, geom.nameplate(w, h), h * 0.035, "#E7DCC4",
                         s=s, depth=2)
    for i in range(geom.ROWS_N):
        for j in range(i + 1):
            x, y, cs = geom.row_slot(i, j, w, h)
            img = ak.recess(img, (x, y, x + cs, y + cs), cs * 0.16, _SLOT_BG,
                            s=s, depth=2)
    for r in range(geom.WALL_N):
        for c in range(geom.WALL_N):
            x, y, cs = geom.wall_slot(r, c, w, h)
            img = ak.recess(img, (x, y, x + cs, y + cs), cs * 0.16, _SLOT_BG,
                            s=s, depth=2)
            rr, gg, bb, _ = ak.color(TILE[_ORDER[(c - r) % 5]])
            ImageDraw.Draw(img).polygon(
                ak._star_pts((x + cs / 2.0) * s, (y + cs / 2.0) * s,
                             cs * 0.26 * s, cs * 0.12 * s, 8), fill=(rr, gg, bb, 46))
    for i in range(geom.FLOOR_N):
        x, y, cs = geom.floor_slot(i, w, h)
        img = ak.recess(img, (x, y, x + cs, y + cs), cs * 0.14, _FLOOR_BG,
                        s=s, depth=2)
    wx0, wy0, _wx1, wy1 = geom.wall_band(w, h)
    ImageDraw.Draw(img).line((wx0 * 0.985 * s, wy0 * s, wx0 * 0.985 * s, wy1 * s),
                             fill=ak.color(_SLOT_BD), width=max(1, int(1.4 * s)))
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, img.size[0] - 1, img.size[1] - 1),
                                        radius=int(round(w * 0.05 * s)), fill=255)
    img.putalpha(m)                       # 统一裁圆角（内部全部不透明）
    return ak.finish(img, w, h)


def make_track_ring(size=512, steps=30):
    """圆形计分轨：外环厚边 + 31 格刻度（每 5 格加重、更长）。"""
    img, _dr, s = ak.canvas(size, size)
    img = ak.disc(img, (size * 0.04, size * 0.04, size * 0.96, size * 0.96),
                  _RING_RIM, _RING_BODY, s=s, ring="#4A7096", highlight=False)
    dr = ImageDraw.Draw(img)
    cx = cy = size / 2.0
    r_in, r_out = size * 0.30, size * 0.42
    for v in range(steps + 1):
        heavy = v % 5 == 0
        a = -math.pi / 2 + (v / float(steps)) * 2 * math.pi
        ln = (r_out - r_in) * (1.0 if heavy else 0.55)
        x0, y0 = cx + r_in * math.cos(a), cy + r_in * math.sin(a)
        x1, y1 = cx + (r_in + ln) * math.cos(a), cy + (r_in + ln) * math.sin(a)
        dr.line((x0 * s, y0 * s, x1 * s, y1 * s),
                fill=ak.color(_RING_TICK if heavy else "#6E90AE"),
                width=max(1, int((2.4 if heavy else 1.4) * s)))
    return ak.finish(img, size, size)


def _build_images():
    """22 键 → PIL 图像（键序无关）。"""
    imgs = {
        "azul_wall_bg": make_wall_bg(),
        "azul_plate": make_plate(center=False),
        "azul_plate_center": make_plate(center=True),
        "azul_board": make_board(),
        "azul_chip": make_chip(),
        "azul_track_ring": make_track_ring(),
        "azul_floor": make_floor(),
    }
    for c in _ORDER:
        imgs[f"azul_tile_{c}"] = make_tile(c)
        imgs[f"azul_wall_cell_{c}"] = make_wall_cell(c)
        imgs[f"azul_marker_{c}"] = make_marker(c)
    return imgs


def build_all():
    """返回全部素材的 PNG data URI（供测试与内嵌校验）。"""
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
