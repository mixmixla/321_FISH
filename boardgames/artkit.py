# -*- coding: utf-8 -*-
"""桌游展示层共享精致绘制工具箱（纯 Pillow、无 Tk、无游戏语义，可 headless 测试）。

约定：
- 坐标一律以「最终尺寸」给出，内部乘 s（超采样倍率）；越界/反框/宽高<1px 的框安全退化。
- 颜色接受 "#rrggbb" 或 (r,g,b[,a])；非法输入回退不透明黑。
- 画布型（draw 参数）就地绘制、返回 None；图像型（img 参数）返回**新图像**。
- 本模块**不得** import tkinter —— 素材生成器与画师都依赖它在无显示环境可用。
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

SS = 4


def color(c):
    """颜色归一化 → (r,g,b,a)；非法输入回退 (0,0,0,255)。"""
    if isinstance(c, str):
        try:
            h = c.lstrip("#")
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
        except Exception:
            return (0, 0, 0, 255)
    if isinstance(c, (tuple, list)) and len(c) >= 3:
        try:
            r, g, b = int(c[0]), int(c[1]), int(c[2])
            a = int(c[3]) if len(c) > 3 else 255
        except Exception:
            return (0, 0, 0, 255)
        return (r, g, b, a)
    return (0, 0, 0, 255)


_norm = color  # chip/gem 的形参名 color 会遮蔽全局函数


def _clamp(v):
    return 0 if v < 0 else (255 if v > 255 else int(v))


def _mix(c, f):
    """f>0 朝白提亮，f<0 朝黑压暗，返回带 alpha 元组。"""
    r, g, b, a = color(c)
    if f >= 0:
        r, g, b = r + (255 - r) * f, g + (255 - g) * f, b + (255 - b) * f
    else:
        r, g, b = r * (1 + f), g * (1 + f), b * (1 + f)
    return (_clamp(r), _clamp(g), _clamp(b), a)


def _lerp(c0, c1, t):
    """两色线性插值（含 alpha）。"""
    a0, a1 = color(c0), color(c1)
    return (_clamp(a0[0] + (a1[0] - a0[0]) * t),
            _clamp(a0[1] + (a1[1] - a0[1]) * t),
            _clamp(a0[2] + (a1[2] - a0[2]) * t),
            _clamp(a0[3] + (a1[3] - a0[3]) * t))


def _px_box(box, s=1):
    """(x0,y0,x1,y1)×s → 像素整型框；非法/反框/宽高<1px → None。"""
    try:
        x0, y0, x1, y1 = [float(v) * s for v in box]
    except Exception:
        return None
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    px = (int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1)))
    if px[2] - px[0] < 1 or px[3] - px[1] < 1:
        return None
    return px


def _radius(r, px, s):
    """把圆角半径夹到「不超过框半宽/半高」，避免 PIL 退化。"""
    x0, y0, x1, y1 = px
    try:
        want = int(round(float(r) * s))
    except Exception:
        want = 0
    return max(0, min(want, (x1 - x0) // 2, (y1 - y0) // 2))


def canvas(w, h, ss=SS):
    """RGBA 超采样画布 → (img, draw, ss)；绘制时把 ss 当 s 传给各函数。"""
    w = max(1, int(round(w)))
    h = max(1, int(round(h)))
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), ss


def finish(img, w, h):
    """LANCZOS 收敛到最终尺寸（已是目标尺寸则原样返回）。"""
    w = max(1, int(round(w)))
    h = max(1, int(round(h)))
    if img.size == (w, h):
        return img
    return img.resize((w, h), Image.Resampling.LANCZOS)


def rrect(draw, box, r, *, s=1, fill=None, outline=None, width=1):
    """圆角矩形（**画布型**，就地绘制）。框非法或 fill/outline 全 None → 静默跳过。"""
    px = _px_box(box, s)
    if px is None or (fill is None and outline is None):
        return
    kw = {}
    if fill is not None:
        kw["fill"] = color(fill)
    if outline is not None:
        kw["outline"] = color(outline)
        kw["width"] = max(1, int(round(width * s)))
    draw.rounded_rectangle(px, radius=_radius(r, px, s), **kw)


def _edge(img, px, r, s, light_c, dark_c, depth, invert=False):
    """在圆角框**内缘**画四条带：invert=False → 上/左亮、下/右暗；True 反之。"""
    out = img.copy()
    dr = ImageDraw.Draw(out)
    x0, y0, x1, y1 = px
    rr = _radius(r, px, s)
    d = max(1, int(round(depth * s)))
    lt, dk = color(light_c), color(dark_c)
    if invert:
        top, left, bottom, right = dk, dk, lt, lt
    else:
        top, left, bottom, right = lt, lt, dk, dk
    dr.line((x0 + rr, y0 + d // 2, x1 - rr, y0 + d // 2), fill=top, width=d)
    dr.line((x0 + d // 2, y0 + rr, x0 + d // 2, y1 - rr), fill=left, width=d)
    dr.line((x0 + rr, y1 - d // 2, x1 - rr, y1 - d // 2), fill=bottom, width=d)
    dr.line((x1 - d // 2, y0 + rr, x1 - d // 2, y1 - rr), fill=right, width=d)
    return out


def rrect_bevel(img, box, r, fill=None, *, s=1, light=None, dark=None, depth=2):
    """斜面圆角块：上/左内缘高光、下/右内缘暗边（**图像型**，返回新图）。"""
    px = _px_box(box, s)
    if px is None:
        return img
    out = img.copy()
    ImageDraw.Draw(out).rounded_rectangle(px, radius=_radius(r, px, s),
                                          fill=color(fill))
    light = color(light) if light is not None else _mix(fill, 0.35)
    dark = color(dark) if dark is not None else _mix(fill, -0.35)
    return _edge(out, px, r, s, light, dark, depth)


def recess(img, box, r, base, *, s=1, depth=3):
    """内凹槽：上/左内缘暗、下/右内缘亮，形成「凹进去」的错觉（**图像型**）。"""
    px = _px_box(box, s)
    if px is None:
        return img
    out = img.copy()
    ImageDraw.Draw(out).rounded_rectangle(px, radius=_radius(r, px, s),
                                          fill=color(base))
    return _edge(out, px, r, s, _mix(base, 0.30), _mix(base, -0.32), depth,
                 invert=True)


def shadow(img, box, r, *, s=1, spread=6, alpha=70, offset=(0, 3)):
    """高斯投影：在框外（尤其下方）产生 0<alpha<255 的半透明暗像素（**图像型**）。"""
    px = _px_box(box, s)
    if px is None:
        return img
    out = img.copy()
    w, h = out.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(px, radius=_radius(r, px, s), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(0.5, float(spread) * s)))
    shifted = Image.new("L", (w, h), 0)
    shifted.paste(mask, (int(round(offset[0] * s)), int(round(offset[1] * s))))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    layer.putalpha(shifted.point(lambda v: int(v * float(alpha) / 255.0)))
    return Image.alpha_composite(out, layer)


def _mask_like(img, box, r, s):
    """L 掩膜（圆角框内 255、外 0）+ 像素框；框非法 → (None, None)。"""
    px = _px_box(box, s)
    if px is None:
        return None, None
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle(px, radius=_radius(r, px, s), fill=255)
    return m, px


def _star_pts(cx, cy, r_out, r_in, n=8, rot=-math.pi / 2):
    """星形 2n 个顶点（调用方负责缩放）。"""
    pts = []
    for i in range(2 * n):
        rr = r_out if i % 2 == 0 else r_in
        a = rot + i * math.pi / n
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def gradient(img, box, r, c0, c1, *, s=1, direction="v"):
    """线性渐变，裁进圆角框（**图像型**）。direction="v" 上起 c0 下至 c1，"h" 左起。"""
    m, px = _mask_like(img, box, r, s)
    if m is None:
        return img
    x0, y0, x1, y1 = px
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    if direction == "h":
        span = max(1, x1 - x0)
        for x in range(x0, x1 + 1):
            dr.line((x, y0, x, y1), fill=_lerp(c0, c1, (x - x0) / float(span)))
    else:
        span = max(1, y1 - y0)
        for y in range(y0, y1 + 1):
            dr.line((x0, y, x1, y), fill=_lerp(c0, c1, (y - y0) / float(span)))
    layer.putalpha(m)                     # 用掩膜当 alpha ⇒ 自动裁圆角、框外透明
    out = img.copy()
    out.alpha_composite(layer)
    return out


def radial(img, box, c_in, c_out, *, s=1):
    """径向渐变椭圆盘：中心 c_in、边缘 c_out（**图像型**）。"""
    px = _px_box(box, s)
    if px is None:
        return img
    x0, y0, x1, y1 = px
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    rx, ry = max(1.0, (x1 - x0) / 2.0), max(1.0, (y1 - y0) / 2.0)
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).ellipse(px, fill=255)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    steps = max(2, int(min(rx, ry)))
    for k in range(steps, 0, -1):
        t = k / float(steps)               # 大椭圆先画=c_out，小椭圆后画=c_in ⇒ 中心亮
        dr.ellipse((cx - rx * k / steps, cy - ry * k / steps,
                    cx + rx * k / steps, cy + ry * k / steps),
                   fill=_lerp(c_in, c_out, t))
    layer.putalpha(m)
    out = img.copy()
    out.alpha_composite(layer)
    return out


def linen(img, box, r, base, *, s=1, amount=6, seed=7):
    """亚麻/瓷砖噪点质感：圆角底 + 确定性随机点（**图像型**）。"""
    m, px = _mask_like(img, box, r, s)
    if m is None:
        return img
    out = img.copy()
    dr = ImageDraw.Draw(out)
    x0, y0, x1, y1 = px
    dr.rounded_rectangle(px, radius=_radius(r, px, s), fill=color(base))
    rnd = random.Random(seed)
    n = max(0, int(amount)) * (x1 - x0) * (y1 - y0) // 64
    jit = (-0.10, -0.05, 0.05, 0.10)
    for _ in range(n):
        x = rnd.randrange(max(0, x0), min(x1, img.size[0] - 1) + 1)
        y = rnd.randrange(max(0, y0), min(y1, img.size[1] - 1) + 1)
        if m.getpixel((x, y)):
            dr.point((x, y), fill=_mix(base, rnd.choice(jit)))
    return out


def ornament_tile(size, bg, fg1, fg2, *, cells=2, ss=SS):
    """阿兹勒赫密铺贴片（四瓣花 + 八角星）：`size % cells == 0` 时无缝。"""
    size = max(1, int(size))
    cells = max(1, int(cells))
    while size % cells:
        cells = 1                          # 周期必须整除边长，否则退化为单胞
    img, dr, s = canvas(size, size, ss)
    p = size // cells
    dr.rectangle((0, 0, size * s, size * s), fill=color(bg))
    petal_r, off = 0.20 * p, 0.18 * p
    for j in range(cells):
        for i in range(cells):
            cx, cy = (i + 0.5) * p, (j + 0.5) * p
            for dx, dy in ((off, 0), (-off, 0), (0, off), (0, -off)):
                dr.ellipse((round((cx + dx - petal_r) * s), round((cy + dy - petal_r) * s),
                            round((cx + dx + petal_r) * s), round((cy + dy + petal_r) * s)),
                           fill=color(fg1))
            pts = _star_pts(cx * s, cy * s, p * 0.30 * s, p * 0.13 * s, 8)
            dr.polygon(pts, fill=color(fg2))
            cr = 0.07 * p * s
            dr.ellipse((cx * s - cr, cy * s - cr, cx * s + cr, cy * s + cr),
                       fill=_mix(fg2, 0.25))
    return finish(img, size, size)


def disc(img, box, rim, body, *, s=1, ring=None, highlight=True):
    """有厚度的陶瓷盘：深色厚边 → 盘面 → 内环 → 克制高光（**图像型**）。"""
    px = _px_box(box, s)
    if px is None:
        return img
    x0, y0, x1, y1 = px
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    rx, ry = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    out = img.copy()
    dr = ImageDraw.Draw(out)

    def ell(fx, fy, fill=None, outline=None, width=1):
        b = (round(cx - rx * fx), round(cy - ry * fy),
             round(cx + rx * fx), round(cy + ry * fy))
        if fill is not None:
            dr.ellipse(b, fill=color(fill))
        else:
            dr.ellipse(b, outline=color(outline), width=max(1, int(round(width * s))))

    ell(1.00, 1.00, fill=rim)
    ell(0.80, 0.80, fill=body)
    if ring is not None:
        ell(0.86, 0.86, outline=ring, width=1.5)
    ell(0.92, 0.92, outline=_mix(rim, 0.25), width=1)
    if highlight:
        hl = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(hl).ellipse(
            (round(cx - rx * 0.55), round(cy - ry * 0.70),
             round(cx + rx * 0.05), round(cy - ry * 0.28)),
            fill=(255, 255, 255, 52))
        out.alpha_composite(hl)
    return out


def chip(img, box, color, *, s=1, label=None):
    """分数筹码：深色轮缘 + 实色圆面 + 浅描内环 + 可选文本（**图像型**）。"""
    px = _px_box(box, s)
    if px is None:
        return img
    x0, y0, x1, y1 = px
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    rx, ry = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    c = _norm(color)
    out = img.copy()
    dr = ImageDraw.Draw(out)
    dr.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=_mix(c, -0.34))
    dr.ellipse((cx - rx * 0.86, cy - ry * 0.86, cx + rx * 0.86, cy + ry * 0.86), fill=c)
    dr.ellipse((cx - rx * 0.62, cy - ry * 0.62, cx + rx * 0.62, cy + ry * 0.62),
               outline=_mix(c, 0.38), width=max(1, int(round(1.4 * s))))
    if label:
        try:
            from PIL import ImageFont
            f = ImageFont.load_default()
            bb = dr.textbbox((0, 0), str(label), font=f)
            tl = Image.new("RGBA", img.size, (0, 0, 0, 0))   # 文本画在独立层再合成，
            ImageDraw.Draw(tl).text((cx - (bb[2] - bb[0]) / 2.0 - bb[0],  # 保留中心不透明度
                                     cy - (bb[3] - bb[1]) / 2.0 - bb[1]),
                                    str(label), font=f, fill=(255, 255, 255, 235))
            out.alpha_composite(tl)
        except Exception:
            pass
    return out


def gem(img, box, color, *, s=1, shape="tile"):
    """立体花砖：竖向渐变（上亮下暗）+ 斜边内缘；`shape="marker"` 走瓷盘外形。"""
    px = _px_box(box, s)
    if px is None:
        return img
    c = _norm(color)
    if shape == "marker":
        return disc(img, box, _mix(c, -0.35), c, s=s, highlight=True)
    rad = (px[2] - px[0]) * 0.18 / float(s)
    out = gradient(img, box, rad, _mix(c, 0.28), _mix(c, -0.22), s=s, direction="v")
    return _edge(out, _px_box(box, s), rad, s, _mix(c, 0.45), _mix(c, -0.45), 2)
