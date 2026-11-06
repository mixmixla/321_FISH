# -*- coding: utf-8 -*-
"""彩釉工坊素材出包器（22 键；原创 ImageGen atlas + 既有 artkit）。

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

from PIL import Image, ImageDraw, ImageEnhance

from boardgames import artkit as ak

HERE = Path(__file__).resolve().parent
ASSETS_DIR = HERE / "assets"
ART_MODULE = HERE / "_art.py"
ATLAS = ASSETS_DIR / "source" / "glaze-atlas.png"
_PANELS = {"b": (0, 0), "r": (1, 0), "y": (2, 0), "w": (0, 1), "k": (1, 1)}

# 五色键沿用规则引擎；辅件与缺图回退匹配生成的釉色。
TILE = {"r": "#B9361F", "w": "#F7EACB", "b": "#17469A", "y": "#EAB325",
        "k": "#192231"}
_ORDER = "rwbyk"                 # 墙色循环顺序（花砖 5 色）
_WALL_BG = "#17343D"
_WALL_BLUE = "#21454E"
_WALL_DEEP = "#1C3E48"
_PLATE_RIM = "#2E4A63"
_PLATE_BODY = "#F7FAFC"
_PLATE_GOLD = "#C9A227"
_RING_RIM = "#16232E"
_RING_BODY = "#24405A"
_RING_TICK = "#BBD3E6"
_FLOOR_BG = "#F2F6F8"
_CHIP = "#F3E3B0"


def _datauri(img):
    buf = io.BytesIO()
    # 游戏缩略图与低对比桌垫无需真彩噪点；保留 alpha 的索引 PNG 明显减小内嵌包。
    if img.size == (384, 288):
        # 独立选桌垫调色板，避免全图集/八叉树量化将浅釉压成大块色斑。
        packed = img.convert("RGB").quantize(colors=64).convert("RGBA")
        packed.putalpha(img.getchannel("A"))
    else:
        packed = img.quantize(colors=128, method=Image.Quantize.FASTOCTREE)
    packed.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _blank(w, h):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def _panel(col, row):
    """唯一生成源的六等分面板；不依赖开发机原图或 ImageGen 运行时。"""
    with Image.open(ATLAS) as atlas:
        if atlas.size != (384, 256):
            raise ValueError("glaze-atlas.png must be 384×256 (3×2 panels)")
        return atlas.crop((col * 128, row * 128, (col + 1) * 128,
                           (row + 1) * 128)).convert("RGBA")


def _rounded(img, radius):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1),
                                          radius=radius, fill=255)
    img.putalpha(mask)
    return img


def make_wall_bg(size=512):
    """低对比深青工坊桌面，周期 128 整除 512，衬托真实彩釉砖。"""
    pattern = ak.ornament_tile(size, _WALL_BG, _WALL_BLUE, _WALL_DEEP, cells=4)
    return Image.blend(Image.new("RGBA", (size, size), _WALL_BG), pattern, 0.22)


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
    """真实生成的五种粗轮廓陶瓷印花，48px 源供两端缩到 20/22px。"""
    face = _panel(*_PANELS[color]).resize((size, size), Image.Resampling.LANCZOS)
    return _rounded(face, max(2, size // 12))


def make_marker(color, size=40):
    """计分棋子沿用同色印花并裁圆，颜色与轮廓双重识别。"""
    return _rounded(make_tile(color, size), size // 2)


def make_chip(size=64):
    """分数筹码：深色轮缘 + 实色圆面 + 浅描内环（超采样后收敛）。"""
    img, _dr, s = ak.canvas(size, size)
    img = ak.chip(img, (3, 3, size - 3, size - 3), _CHIP, s=s)
    return ak.finish(img, size, size)


def make_wall_cell(color, size=48):
    """代码绘制的真实墙格：同花纹低饱和淡印，与已上墙饱和实砖明显分层。"""
    face = make_tile(color, size)
    face = ImageEnhance.Color(face).enhance(0.55)
    cell = Image.blend(Image.new("RGBA", (size, size), "#E4E5D3"), face, 0.24)
    ImageDraw.Draw(cell).rounded_rectangle((1, 1, size - 2, size - 2),
                                          radius=size // 12, outline="#9AAFA6", width=1)
    return _rounded(cell, max(2, size // 12))


def make_floor(size=48):
    """地板槽：内凹 + 冷灰描边，提示「扣分行」。"""
    img = _blank(size, size)
    return ak.recess(img, (2, 2, size - 2, size - 2), size * 0.14, _FLOOR_BG, depth=3)


def make_board(w=384, h=288):
    """干净浅青釉桌垫；不烧入任何文字、铭牌、行槽、墙格或按钮。"""
    # 避开生成面板边缘的光泽边线，真实格子/名字/分数由各端实时画出。
    img = _panel(2, 1).crop((9, 9, 119, 119))
    return _rounded(img.resize((w, h), Image.Resampling.LANCZOS), int(w * 0.04))


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
        "# 彩釉工坊原创 ImageGen 图集出包；源与提示见 ARTWORK.md。",
        "# 重生成：python -m boardgames.azul.sprites",
        "ASSETS = {",
    ]
    for key in sorted(imgs):
        img = imgs[key]
        uri = _datauri(img)
        (ASSETS_DIR / f"{key}.png").write_bytes(base64.b64decode(uri.split(",", 1)[1]))
        lines.append(f"    {key!r}: {uri!r},")
    lines.append("}")
    lines.append("")
    ART_MODULE.write_text("\n".join(lines), encoding="utf-8")
    print(f"generated {len(imgs)} azul assets")


if __name__ == "__main__":
    main()
