# 桌游展示层「BGA 级精致度」实现计划 · 第一批（artkit + Azul 素材重做 + 桌面版面重排）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立纯 Pillow 的共享精致绘制工具箱 `boardgames/artkit.py`，在它之上重做 Azul 全部素材（**25 键 = 22 新增/改尺寸 + 3 沿用**），并把 Azul 桌面版面重排为 BGA 结构（信息条 / 左工厂列+中央池 / 中所有玩家板 / 右圆形计分轨），产出可目视的样张。

**Architecture:** `artkit.py` 只提供无游戏语义的绘制原语（渐变/斜面/内凹/投影/质感/纹样/盘/筹码/花砖），坐标一律「最终尺寸 + 内部 4× 超采样」。`boardgames/geom.py` 存放**归一化玩家板内几何**（5 花纹行 / 5×5 墙 / 7 格地板线），被素材预印（`azul/sprites.py`）与桌面落子（`shell.board_panel` / `azul/desktop.py`）**共用**，避免两处坐标漂移。`boardgames/shell.py` 新增游戏无关的 `table/board_panel/score_ring/info_bar/factory_disc/layout` 组件，素材键一律由调用方传入（Azul 传 `azul_*`）。`boardgames/azul/desktop.py` 用 `shell.layout` 的分区重排为 BGA 版面。网页端本轮**只做键名同步**（不改版面结构），完整网页版面重排属第二批。

**Tech Stack:** Python 3.14.5 / Pillow（程序化原创素材、base64 内嵌）/ Tkinter（仅绘制期）/ pytest / node（JS 语法探针）。

**Spec:** `docs/superpowers/specs/2026-10-14-boardgame-bga-fidelity-artkit-design.md`

## Global Constraints

- 全部素材 **Pillow 程序化原创**；仅对标 BGA 的**风格方向**，不复制任何素材/坐标/色彩采样。
- **不改** `ui_design.design_tokens()` golden digest：`a137658af6f3f9899c2106a0e6020c1b1e6d2569bab462488bb7c42dc0eb4078`。
- **不删** `_GAME_ICON` 既有键；**不破坏** `icon_svg` 字节兼容；**不改**主聊天窗（`ChatWindow`）皮肤与 `web.py` 主聊天区 CSS/token。
- 假画布桩下（`_real_cv(cv)` 为 False）**绝不调用** `ImageTk.PhotoImage(master=cv)`；`artkit` / `geom` 必须 **不 import tkinter**（headless 可测、素材生成无需显示器）。
- `boardgames/azul/desktop.py` 保持现有 headless 契约：所有位图入口走 `client_gameui` 的 `_asset_*`（自带 `_real_cv` 守卫与矢量回退）。
- azul 动作契约 `take/place/floor` 不变；网页注入后整页 JS 必须语法合法（`node tests/ux_visual_chat_probe.cjs` 通过）。
- 未迁移的 46 款游戏**行为与外观零变化**；`_PAINTERS` 与内联 `GRENDER` 对它们保持原样。
- 不改 `_art_boardgame.py` / `_gen_boardgame.py` / `assets/boardgame/**`（其内嵌 `ASSETS` **不含** `azul_table` / `azul_boardface` / `azul_track`，故这 3 个沿用键必须由包内继续生成，供本批未改的网页端使用）。
- verify 目标为「**无新增 FAIL**」；本机 Tk 缺 tcl 导致的 `TclError` 属环境问题，`pytest.skip` 即可。
- 全量回归必须走 `python tests/_run_all.py`（逐文件独立子进程；单进程批跑会偶发原生崩溃 0x80000003），单文件用 `python -m pytest <file> -q`。
- **未经用户明确要求不 commit / push**：各任务以「定向测试通过」收尾，改动留在工作区待评审；最终是否提交由用户决定。
- 本轮只做第一批：**网页版面重排 + 打包 + 全量回归收尾属第二批**，不得在本轮引入。

---

## 文件结构

**新增**
- `boardgames/artkit.py` — 共享精致绘制原语（纯 Pillow，无 Tk / 无游戏语义）。
- `boardgames/geom.py` — 玩家板**归一化内几何**（纯数值，无 import 依赖）。
- `tests/test_artkit.py` — artkit 原语的尺寸/alpha/明暗/无缝断言。
- `tests/test_board_geom.py` — geom 的归一回、越界与缩放不变性断言。
- `tests/test_shell_components.py` — 新增 shell 组件在桩画布上的安全与键名契约断言。
- `_azul_preview.py` — 开发期样张脚本（仓库根，下划线前缀与 `_gen_boardgame.py` 惯例一致）：开 1280×760 窗口展示 Azul 桌面版面并**存 PNG 到 `.trae/tmp/azul_desktop_preview.png`**。

**重做（内容替换，路径不变）**
- `boardgames/azul/sprites.py` — 25 键素材生成器（改用 artkit + geom；含 3 个沿用键 `make_legacy_table` / `make_legacy_boardface` / `make_legacy_track`）。
- `boardgames/azul/_art.py` — 生成产物（由 `python -m boardgames.azul.sprites` 覆写）。
- `boardgames/azul/assets/*.png` — 生成产物 PNG（键集：**新增 8 键 + 保留 3 个沿用键**）。
- `boardgames/azul/desktop.py` — BGA 版面重排。
- `boardgames/shell.py` — 追加 5 个新组件 + `layout` 改签名（返回分区 dict）。

**测试同步（第一批改）**
- `tests/test_azul_package_assets.py` — `_EXPECTED_WH` 改为 25 键。
- `tests/test_boardgame_asset_img.py` — 新键进入缓存断言 + headless 键序遥测。

**第一批不动（第二批才改）**
- `boardgames/azul/web.py` — 网页渲染器与素材键字面量（第一批保持原样）。
- `web.py` — `_BG_ASSET_KEYS` 与主聊天区 CSS/token（第一批保持原样）。
- `tests/test_web_boardgame_assets.py` — 网页断言（第一批保持原样）。

**键集（25 键 = 22 新增/改尺寸 + 3 沿用）**

| key | 尺寸 | 处置 |
|---|---|---|
| `azul_wall_bg` | 512×512 | 新（桌面底无缝瓷砖墙） |
| `azul_plate` | 160×160 | 改尺寸（128→160） |
| `azul_plate_center` | 160×160 | 新 |
| `azul_board` | 384×288 | 改尺寸（256×256→384×288） |
| `azul_tile_{r,w,b,y,k}` | 48×48 | 改尺寸（44→48） |
| `azul_wall_cell_{r,w,b,y,k}` | 48×48 | 尺寸不变、观感重做 |
| `azul_marker_{r,w,b,y,k}` | 40×40 | 新 |
| `azul_chip` | 64×64 | 新 |
| `azul_track_ring` | 512×512 | 新 |
| `azul_floor` | 48×48 | 尺寸不变、观感重做 |
| `azul_table` | 128×128 | **沿用**（网页端仍引用；第一批继续生成） |
| `azul_boardface` | 256×256 | **沿用**（同上） |
| `azul_track` | 96×48 | **沿用**（同上） |

> **为何保留这 3 个沿用键**：仓库根 `_art_boardgame.py` 的内嵌 `ASSETS` 里**并不存在** `azul_table` / `azul_boardface` / `azul_track`（只有 `azul_board`）。若第一批就把它们从包内删掉，本批**未改**的网页端（仍引用这三个键）会取不到位图。故第一批继续由包内生成这 3 键（沿用旧尺寸、观感照旧），**删除它们 + 网页版面重排一并留到第二批**。

---

## Task 1: artkit 基础原语（canvas / finish / rrect / rrect_bevel / recess / shadow）

**Files:**
- Create: `boardgames/artkit.py`
- Test: `tests/test_artkit.py`

**Interfaces:**
- Produces（后续所有任务依赖这些签名）：
  - `artkit.SS = 4`
  - `artkit.canvas(w, h, ss=SS) -> (PIL.Image, PIL.ImageDraw, s)`（RGBA 超采样画布）
  - `artkit.finish(img, w, h) -> PIL.Image`（LANCZOS 收敛到最终尺寸）
  - `artkit.rrect(draw, box, r, *, s=1, fill=None, outline=None, width=1) -> None`（**画布型**，就地绘制）
  - `artkit.rrect_bevel(img, box, r, fill=None, *, s=1, light=None, dark=None, depth=2) -> Image`（**图像型**，返回新图）
  - `artkit.recess(img, box, r, base, *, s=1, depth=3) -> Image`
  - `artkit.shadow(img, box, r, *, s=1, spread=6, alpha=70, offset=(0, 3)) -> Image`
  - `artkit.color(c) -> (r,g,b,a)`
  - 约定：`box = (x0,y0,x1,y1)` 为**最终尺寸**坐标；非法/反向/空框 → 画布型静默跳过、图像型原样返回，**绝不抛异常**。

- [ ] **Step 1: 写失败测试** `tests/test_artkit.py`

```python
# -*- coding: utf-8 -*-
"""artkit 共享绘制原语：尺寸、alpha、明暗关系、异常安全。"""
import pytest

pytest.importorskip("PIL")
from PIL import Image

from boardgames import artkit


def _lum(px):
    return 0.299 * px[0] + 0.587 * px[1] + 0.114 * px[2]


def test_no_tkinter_import():
    import sys
    assert "tkinter" not in sys.modules


def test_canvas_supersamples_and_finish_converges():
    img, dr, s = artkit.canvas(24, 16)
    assert s == artkit.SS
    assert img.size == (24 * s, 16 * s)
    assert img.mode == "RGBA"
    assert artkit.finish(img, 24, 16).size == (24, 16)


def test_color_normalizes_hex_tuple_and_junk():
    assert artkit.color("#FF8000") == (255, 128, 0, 255)
    assert artkit.color((1, 2, 3)) == (1, 2, 3, 255)
    assert artkit.color((1, 2, 3, 4)) == (1, 2, 3, 4)
    assert artkit.color("nonsense") == (0, 0, 0, 255)


def test_rrect_fills_and_respects_reverse_box():
    img, dr, s = artkit.canvas(20, 20)
    artkit.rrect(dr, (2, 2, 18, 18), 4, s=s, fill="#3366FF")
    assert artkit.finish(img, 20, 20).getpixel((10, 10)) == (51, 102, 255, 255)
    # 反向/空框：静默跳过，不抛
    artkit.rrect(dr, (10, 10, 4, 4), 3, s=s, fill="#fff")
    artkit.rrect(dr, None, 3, s=s, fill="#fff")


def test_rrect_bevel_top_edge_is_brighter_than_bottom():
    img, _dr, s = artkit.canvas(60, 60)
    img = artkit.rrect_bevel(img, (6, 6, 54, 54), 8, "#8899AA", s=s, depth=2)
    out = artkit.finish(img, 60, 60)
    assert _lum(out.getpixel((30, 7))) > _lum(out.getpixel((30, 52)))


def test_recess_top_inner_edge_is_darker_than_bottom():
    img, _dr, s = artkit.canvas(60, 60)
    img = artkit.recess(img, (6, 6, 54, 54), 8, "#BFB6A4", s=s, depth=2)
    out = artkit.finish(img, 60, 60)
    assert _lum(out.getpixel((30, 7))) < _lum(out.getpixel((30, 52)))


def test_shadow_makes_translucent_pixels_outside_box():
    img = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
    img = artkit.shadow(img, (20, 20, 60, 60), 8, spread=4, alpha=90,
                        offset=(0, 3))
    assert img.size == (80, 80)
    a = img.getpixel((40, 66))[3]
    assert 0 < a < 255
    assert img.getpixel((2, 2))[3] == 0


def test_image_ops_return_new_image_and_keep_input():
    src = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    out = artkit.shadow(src, (8, 8, 32, 32), 6, spread=3, alpha=60)
    assert out is not src
    assert src.getpixel((20, 20)) == (0, 0, 0, 0)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_artkit.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'boardgames.artkit'`）

- [ ] **Step 3: 新建** `boardgames/artkit.py`（第 1 段：基础工具 + 画布 + `rrect`）

```python
# -*- coding: utf-8 -*-
"""桌游展示层共享精致绘制工具箱（纯 Pillow、无 Tk、无游戏语义，可 headless 测试）。

约定：
- 坐标一律以「最终尺寸」给出，内部乘 s（超采样倍率）；越界/反框/宽高<1px 的框安全退化。
- 颜色接受 "#rrggbb" 或 (r,g,b[,a])；非法输入回退不透明黑。
- 画布型（draw 参数）就地绘制、返回 None；图像型（img 参数）返回**新图像**。
- 本模块**不得** import tkinter —— 素材生成器与画师都依赖它在无显示环境可用。
"""
from __future__ import annotations

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
```

- [ ] **Step 3（续）：追加** `boardgames/artkit.py`（第 2 段：斜面 / 内凹 / 投影）

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_artkit.py -q`
Expected: `8 passed`（注意：本机若缺 tcl 不影响本文件——artkit 不碰 Tk）。

- [ ] **Step 5: 收尾（不提交）**

改动留在工作区待评审；**不要** `git add` / `git commit` / `git push`（用户红线）。

---

## Task 2: artkit 装饰与质感原语（gradient / radial / linen / ornament_tile / disc / chip / gem）

**Files:**
- Modify: `boardgames/artkit.py`（追加，接在 `shadow` 之后）
- Test: `tests/test_artkit.py`（追加用例，接在 `test_image_ops_return_new_image_and_keep_input` 之后）

**Interfaces:**
- Produces：
  - `artkit.gradient(img, box, r, c0, c1, *, s=1, direction="v") -> Image`
  - `artkit.radial(img, box, c_in, c_out, *, s=1) -> Image`
  - `artkit.linen(img, box, r, base, *, s=1, amount=6, seed=7) -> Image`
  - `artkit.ornament_tile(size, bg, fg1, fg2, *, cells=2, ss=SS) -> Image`（返回 `size×size`；`size % cells == 0` 时纹样周期 `P=size//cells` **整除边长** ⇒ 无缝）
  - `artkit.disc(img, box, rim, body, *, s=1, ring=None, highlight=True) -> Image`
  - `artkit.chip(img, box, color, *, s=1, label=None) -> Image`
  - `artkit.gem(img, box, color, *, s=1, shape="tile") -> Image`（`shape="marker"` 为计分棋子外形）
- 依赖：Task 1 的 `_px_box` / `_radius` / `_mix` / `_lerp` / `color` / `_edge`。

- [ ] **Step 1: 追加失败测试**

```python
def test_gradient_is_vertical_by_default_and_clear_outside_box():
    img = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    out = artkit.gradient(img, (4, 4, 44, 44), 6, "#FFFFFF", "#202020")
    assert out.size == (48, 48)
    assert _lum(out.getpixel((24, 8))) > _lum(out.getpixel((24, 40)))
    assert out.getpixel((1, 1))[3] == 0


def test_gradient_horizontal_direction():
    img = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    out = artkit.gradient(img, (4, 4, 44, 44), 6, "#FFFFFF", "#202020",
                          direction="h")
    assert _lum(out.getpixel((8, 24))) > _lum(out.getpixel((40, 24)))


def test_radial_center_brighter_than_far_edge():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    out = artkit.radial(img, (4, 4, 60, 60), "#FFFFFF", "#101820")
    assert _lum(out.getpixel((32, 32))) > _lum(out.getpixel((10, 32)))
    assert out.getpixel((0, 0))[3] == 0


def test_linen_is_deterministic_and_keeps_outside_clear():
    img = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    kw = dict(s=1, amount=6, seed=7)
    a = artkit.linen(img, (4, 4, 36, 36), 6, "#C8BE9E", **kw)
    b = artkit.linen(img, (4, 4, 36, 36), 6, "#C8BE9E", **kw)
    assert a.tobytes() == b.tobytes()
    assert a.getpixel((20, 20))[3] == 255
    assert a.getpixel((1, 1))[3] == 0
    c = artkit.linen(img, (4, 4, 36, 36), 6, "#C8BE9E", s=1, amount=6, seed=8)
    assert c.tobytes() != a.tobytes()


def test_ornament_tile_is_seamless_when_cells_divide_size():
    size, cells = 64, 2
    tile = artkit.ornament_tile(size, "#F7FAFC", "#4A7DE0", "#2B5E8C", cells=cells)
    assert tile.size == (size, size)
    assert size % cells == 0
    p = size // cells
    # 取样必须远离画布边缘（重采样核会越界，边缘像素不满足周期相等）
    for x, y in ((8, 8), (12, 17), (24, 28), (28, 5)):
        assert tile.getpixel((x, y)) == tile.getpixel((x + p, y))
        assert tile.getpixel((x, y)) == tile.getpixel((x, y + p))


def test_disc_has_bright_center_and_transparent_corner():
    img = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    out = artkit.disc(img, (2, 2, 46, 46), "#2E4A63", "#F7FAFC")
    assert out.getpixel((1, 1))[3] == 0          # 四角透明
    assert out.getpixel((24, 24))[3] == 255      # 盘面不透明
    assert _lum(out.getpixel((24, 24))) > _lum(out.getpixel((24, 5)))   # 中心亮于边缘


def test_chip_is_opaque_in_center_and_transparent_at_corner():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    out = artkit.chip(img, (2, 2, 62, 62), "#4A7DE0", label="3")
    assert out.size == (64, 64)
    assert out.getpixel((32, 32))[3] == 255
    assert out.getpixel((0, 0))[3] == 0


def test_gem_tile_and_marker_shapes():
    tile = artkit.gem(Image.new("RGBA", (48, 48), (0, 0, 0, 0)), (3, 3, 45, 45),
                      "#D2534F", shape="tile")
    assert tile.getpixel((0, 0))[3] == 0
    assert tile.getpixel((24, 24))[3] == 255
    assert _lum(tile.getpixel((24, 9))) > _lum(tile.getpixel((24, 39)))
    mk = artkit.gem(Image.new("RGBA", (40, 40), (0, 0, 0, 0)), (2, 2, 38, 38),
                    "#3A3A3A", shape="marker")
    assert mk.size == (40, 40)
    assert mk.getpixel((20, 20))[3] == 255
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_artkit.py -q`
Expected: FAIL — `AttributeError: module 'boardgames.artkit' has no attribute 'gradient'`（后续用例同理）。

- [ ] **Step 3: 追加实现**（先在 `boardgames/artkit.py` 头部 import 段加 `import math` 与 `import random`，并在 `color()` 定义之后加一行别名 `_norm = color  # chip/gem 的形参名 color 会遮蔽全局函数`；再把下面代码追加到文件末尾）

```python
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
        t = 1.0 - k / float(steps)
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
        x = rnd.randrange(x0, x1 + 1)
        y = rnd.randrange(y0, y1 + 1)
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
            dr.text((cx - (bb[2] - bb[0]) / 2.0 - bb[0],
                     cy - (bb[3] - bb[1]) / 2.0 - bb[1]),
                    str(label), font=f, fill=(255, 255, 255, 235))
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_artkit.py -q`
Expected: `16 passed`。

- [ ] **Step 5: 收尾（不提交）**

改动留在工作区待评审；不要 git add/commit/push。

---

## Task 3: `boardgames/geom.py` 共享玩家板几何

**Files:**
- Create: `boardgames/geom.py`
- Test: `tests/test_board_geom.py`

**Interfaces:**
- Produces（Task 4 的素材预印、Task 5/6 的落子都只用这套坐标，避免漂移）：
  - 常量 `BOARD_W=384`、`BOARD_H=288`、`ROWS_N=5`、`WALL_N=5`、`FLOOR_N=7`
  - `nameplate(w, h) -> (x0, y0, x1, y1)`、`row_band(i, w, h) -> (x0, y0, x1, y1)`
  - `row_cell_size(i, w, h) -> (cw, ch)`、`row_slot(i, j, w, h) -> (x, y, s)`
  - `wall_band(w, h) -> (x0, y0, x1, y1)`、`wall_cell_size(w, h) -> (cw, ch)`、`wall_slot(r, c, w, h) -> (x, y, s)`
  - `floor_band(w, h) -> (x0, y0, x1, y1)`、`floor_slot(i, w, h) -> (x, y, s)`
- 约束：模块**零 import**；板内参考几何（`384×288` 单位）为唯一真源——铭牌 `(10,10,158,36)`、花纹行带 `(12,46,178,234)`、墙带 `(188,46,374,234)`、地板带 `(12,242,374,276)`；**所有公式一次齐次**（只允许乘系数与 `min`，不得加减像素常数），因此 ×2 缩放浮点精确；越界索引 / `w<=0 或 h<=0` → `None`。
- 关键系数（写实现时照抄）：行 `s = min(行带宽*0.84/n, 行间距*0.86)`（`n=i+1`）、`step = s*1.08`、`off = (行带宽 - (step*n - (step-s)))/2`；墙 `s = min(墙带宽/5, 墙带高/5)*0.86`，居中留白 `(pitch-s)/2`；地板 `s = min(地板带宽/7, 地板带高)*0.88`，同理居中。

- [ ] **Step 1: 写失败测试** `tests/test_board_geom.py`

```python
# -*- coding: utf-8 -*-
"""玩家板归一化内几何：归一回、越界、包含性与 ×2 线性精确。"""
import pytest

from boardgames import geom


def test_board_constants_match_spec():
    assert (geom.BOARD_W, geom.BOARD_H) == (384, 288)
    assert (geom.ROWS_N, geom.WALL_N, geom.FLOOR_N) == (5, 5, 7)


def test_non_positive_size_returns_none():
    for w, h in ((0, 288), (384, 0), (-1, 100)):
        assert geom.nameplate(w, h) is None
        assert geom.row_band(0, w, h) is None
        assert geom.row_cell_size(0, w, h) is None
        assert geom.row_slot(0, 0, w, h) is None
        assert geom.wall_band(w, h) is None
        assert geom.wall_cell_size(w, h) is None
        assert geom.wall_slot(0, 0, w, h) is None
        assert geom.floor_band(w, h) is None
        assert geom.floor_slot(0, w, h) is None


def test_out_of_range_index_returns_none():
    W, H = geom.BOARD_W, geom.BOARD_H
    assert geom.row_band(5, W, H) is None
    assert geom.row_band(-1, W, H) is None
    assert geom.row_cell_size(5, W, H) is None
    assert geom.row_slot(0, 1, W, H) is None        # 第 0 行只有 1 格
    assert geom.row_slot(2, 3, W, H) is None        # 第 2 行只有 3 格（j∈[0,2]）
    assert geom.wall_slot(5, 0, W, H) is None
    assert geom.wall_slot(0, 5, W, H) is None
    assert geom.floor_slot(7, W, H) is None


def test_geometry_is_contained_and_ordered():
    W, H = geom.BOARD_W, geom.BOARD_H
    rb, wb, fb = geom.row_band(0, W, H), geom.wall_band(W, H), geom.floor_band(W, H)
    assert wb[0] > rb[2]                    # 墙带在花纹行带右侧
    assert wb[3] <= H and fb[3] <= H and fb[2] <= W
    for i in range(geom.ROWS_N):
        band = geom.row_band(i, W, H)
        cs = geom.row_cell_size(i, W, H)[0]
        for j in range(i + 1):
            x, y, sz = geom.row_slot(i, j, W, H)
            assert sz == cs
            assert band[0] <= x and x + sz <= band[2] + 1e-6
            assert band[1] <= y and y + sz <= band[3] + 1e-6
    for r in range(geom.WALL_N):
        for c in range(geom.WALL_N):
            x, y, sz = geom.wall_slot(r, c, W, H)
            assert wb[0] <= x and x + sz <= wb[2] + 1e-6
            assert wb[1] <= y and y + sz <= wb[3] + 1e-6
    prev = -1.0
    for i in range(geom.FLOOR_N):
        x, y, sz = geom.floor_slot(i, W, H)
        assert x > prev and x + sz <= fb[2] + 1e-6
        assert fb[1] <= y and y + sz <= fb[3] + 1e-6
        prev = x


def test_scaling_is_exactly_linear():
    W, H = geom.BOARD_W, geom.BOARD_H
    for fn, args in ((geom.nameplate, ()), (geom.row_band, (3,)),
                     (geom.wall_band, ()), (geom.floor_band, ())):
        a, b = fn(*args, W, H), fn(*args, 2 * W, 2 * H)
        assert b == tuple(2 * v for v in a)
    for args in ((0,), (2,), (4,)):
        a, b = geom.row_cell_size(*args, W, H), geom.row_cell_size(*args, 2 * W, 2 * H)
        assert b == (2 * a[0], 2 * a[1])
    a, b = geom.wall_cell_size(W, H), geom.wall_cell_size(2 * W, 2 * H)
    assert b == (2 * a[0], 2 * a[1])
    for args in ((0, 0), (2, 1), (4, 4)):
        a, b = geom.row_slot(*args, W, H), geom.row_slot(*args, 2 * W, 2 * H)
        assert b == tuple(2 * v for v in a)
    for args in ((0, 1), (4, 4)):
        a, b = geom.wall_slot(*args, W, H), geom.wall_slot(*args, 2 * W, 2 * H)
        assert b == tuple(2 * v for v in a)
    for i in range(geom.FLOOR_N):
        a, b = geom.floor_slot(i, W, H), geom.floor_slot(i, 2 * W, 2 * H)
        assert b == tuple(2 * v for v in a)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_board_geom.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'boardgames.geom'`）

- [ ] **Step 3: 新建** `boardgames/geom.py`

```python
# -*- coding: utf-8 -*-
"""玩家板归一化内几何：素材**预印凹槽**与画师**落子**共用同一坐标真源。

- 模块零 import（纯数值），headless 可测。
- 板内参考几何以 BOARD_W × BOARD_H 为单位；返回值为调用方给定的 (w, h) 像素坐标。
- 所有公式**一次齐次**（只乘系数、只取 min，不加减像素常数）⇒ 等比缩放浮点精确。
- 越界索引 / 非正尺寸一律返回 None，绝不抛异常。
"""
from __future__ import annotations

BOARD_W = 384
BOARD_H = 288
ROWS_N = 5
WALL_N = 5
FLOOR_N = 7

_NP = (10.0, 10.0, 158.0, 36.0)      # 铭牌
_ROWS = (12.0, 46.0, 178.0, 234.0)   # 花纹行带（左侧列）
_WALL = (188.0, 46.0, 374.0, 234.0)  # 5×5 墙带（右侧列）
_FLOOR = (12.0, 242.0, 374.0, 276.0) # 地板带（底部横条）

_ROW_W_F, _ROW_S_F, _ROW_STEP_F = 0.84, 0.86, 1.08
_WALL_S_F, _FLOOR_S_F = 0.86, 0.88


def _ok(w, h):
    return w > 0 and h > 0


def _rect(t, w, h):
    return (t[0] / BOARD_W * w, t[1] / BOARD_H * h,
            t[2] / BOARD_W * w, t[3] / BOARD_H * h)


def nameplate(w, h):
    """铭牌矩形（昵称位）。"""
    return _rect(_NP, w, h) if _ok(w, h) else None


def row_band(i, w, h):
    """第 i 花纹行的条带矩形（i: 0..4）。"""
    if not _ok(w, h) or not 0 <= i < ROWS_N:
        return None
    x0, y0, x1, y1 = _rect(_ROWS, w, h)
    pitch = (y1 - y0) / ROWS_N
    return (x0, y0 + i * pitch, x1, y0 + (i + 1) * pitch)


def row_cell_size(i, w, h):
    """第 i 行单格边长（正方形）。"""
    if not _ok(w, h) or not 0 <= i < ROWS_N:
        return None
    x0, y0, x1, y1 = _rect(_ROWS, w, h)
    s = min((x1 - x0) * _ROW_W_F / (i + 1), (y1 - y0) / ROWS_N * _ROW_S_F)
    return (s, s)


def row_slot(i, j, w, h):
    """第 i 行第 j 格的 (x, y, 边长)（j ∈ [0, i]，超出即 None）。"""
    if not _ok(w, h) or not 0 <= i < ROWS_N or not 0 <= j <= i:
        return None
    x0, y0, x1, y1 = _rect(_ROWS, w, h)
    n = i + 1
    s = row_cell_size(i, w, h)[0]
    step = s * _ROW_STEP_F
    off = ((x1 - x0) - (step * n - (step - s))) / 2.0     # 整行居中
    pitch = (y1 - y0) / ROWS_N
    return (x0 + off + j * step, y0 + i * pitch + (pitch - s) / 2.0, s)


def wall_band(w, h):
    """5×5 墙带矩形。"""
    return _rect(_WALL, w, h) if _ok(w, h) else None


def wall_cell_size(w, h):
    """墙格边长（正方形，取两向 pitch 较小者）。"""
    if not _ok(w, h):
        return None
    x0, y0, x1, y1 = _rect(_WALL, w, h)
    s = min((x1 - x0) / WALL_N, (y1 - y0) / WALL_N) * _WALL_S_F
    return (s, s)


def wall_slot(r, c, w, h):
    """第 r 行第 c 列墙格的 (x, y, 边长)。"""
    if not _ok(w, h) or not 0 <= r < WALL_N or not 0 <= c < WALL_N:
        return None
    x0, y0, x1, y1 = _rect(_WALL, w, h)
    s = wall_cell_size(w, h)[0]
    px, py = (x1 - x0) / WALL_N, (y1 - y0) / WALL_N
    return (x0 + c * px + (px - s) / 2.0, y0 + r * py + (py - s) / 2.0, s)


def floor_band(w, h):
    """地板线横条矩形。"""
    return _rect(_FLOOR, w, h) if _ok(w, h) else None


def floor_slot(i, w, h):
    """地板第 i 格（i: 0..6）的 (x, y, 边长)。"""
    if not _ok(w, h) or not 0 <= i < FLOOR_N:
        return None
    x0, y0, x1, y1 = _rect(_FLOOR, w, h)
    step = (x1 - x0) / FLOOR_N
    s = min(step, y1 - y0) * _FLOOR_S_F
    return (x0 + i * step + (step - s) / 2.0, y0 + (y1 - y0 - s) / 2.0, s)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_board_geom.py -q`
Expected: `5 passed`。

- [ ] **Step 5: 收尾（不提交）**

改动留在工作区待评审；不要 git add/commit/push。

---

## Task 4: Azul 素材 25 键重做（22 新增/改尺寸 + 3 沿用 · artkit + geom 之上）

**Files:**
- Modify: `boardgames/azul/sprites.py`（内容替换：15 键 → 25 键）
- Modify: `tests/test_azul_package_assets.py`（键集 + 尺寸 + 无缝断言）
- Run（生成产物，**不要手写**）：`python -m boardgames.azul.sprites` → 覆写 `boardgames/azul/assets/*.png` 与 `boardgames/azul/_art.py`

**Interfaces:**
- Consumes：`artkit.canvas/finish/color/rrect/rrect_bevel/recess/shadow/gradient/radial/linen/ornament_tile/disc/chip/gem/_mix/_star_pts`；`geom.BOARD_W/BOARD_H/ROWS_N/WALL_N/FLOOR_N/nameplate/row_band/row_cell_size/row_slot/wall_band/wall_cell_size/wall_slot/floor_band/floor_slot`。
- Produces：`sprites.build_all() -> dict[str, str]`（25 个 PNG data URI）；`sprites.main()` 写出 `assets/<key>.png` 与内嵌 `_art.py`（`ASSETS = {...}`，键序按 `sorted()`，与现状一致）。
- 键集（25 = 22 新增/改尺寸 + 3 沿用）：`azul_wall_bg` 512²、`azul_plate` 160²、`azul_plate_center` 160²、`azul_board` 384×288、`azul_tile_{r,w,b,y,k}` 48²、`azul_wall_cell_{r,w,b,y,k}` 48²、`azul_marker_{r,w,b,y,k}` 40²、`azul_chip` 64²、`azul_track_ring` 512²、`azul_floor` 48²；**沿用键**（第一批仍生成、仅供网页端，第二批网页重排后删除）：`azul_table` 128²、`azul_boardface` 256²、`azul_track` 96×48。仓库根 `_art_boardgame.py` 的内嵌 `ASSETS` **并无**这三个键，故必须由包内生成，否则本批未改的网页端会取不到位图。
- 调色（程序化原创，沿用引擎）：红 `#D2534F`、白 `#F0F0F0`、蓝 `#4A7DE0`、黄 `#E0B33C`、黑 `#3A3A3A`；墙底 `#F7FAFC` / 主蓝 `#4A7DE0` / 深蓝 `#2B5E8C`；板底奶油 `#F6F1E7`、槽底 `#E4D9C3`、槽边 `#CDBE9C`、深蓝厚边 `#2E4A63`、金边 `#C9A227`。

- [ ] **Step 1: 更新素材测试**

把 `tests/test_azul_package_assets.py` 的 `_EXPECTED_WH` 与计数断言改为：

```python
_EXPECTED_WH = {
    "azul_wall_bg": (512, 512), "azul_plate": (160, 160),
    "azul_plate_center": (160, 160), "azul_board": (384, 288),
    "azul_track_ring": (512, 512), "azul_chip": (64, 64), "azul_floor": (48, 48),
    "azul_table": (128, 128), "azul_boardface": (256, 256), "azul_track": (96, 48),
    **{f"azul_tile_{c}": (48, 48) for c in "rwbyk"},
    **{f"azul_wall_cell_{c}": (48, 48) for c in "rwbyk"},
    **{f"azul_marker_{c}": (40, 40) for c in "rwbyk"},
}

def test_azul_assets_expose_exactly_expected_keys():
    assert set(_art.ASSETS) == set(_EXPECTED_WH)
    assert len(_art.ASSETS) == 25

def test_azul_legacy_web_keys_survive_this_batch():
    """第一批网页端仍引用这三个旧键（第二批才改），故包内必须继续生成。"""
    for k in ("azul_table", "azul_boardface", "azul_track"):
        assert k in _art.ASSETS, k
        assert _art.ASSETS[k].startswith("data:image/png;base64,")

def test_azul_wall_bg_is_seamless():
    raw = base64.b64decode(_art.ASSETS["azul_wall_bg"].split(",", 1)[1])
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    p = 512 // 4                      # ornament_tile(cells=4) ⇒ 周期 128
    for x, y in ((64, 64), (96, 160), (128, 224)):     # 取样远离边缘
        assert img.getpixel((x, y)) == img.getpixel((x + p, y))
        assert img.getpixel((x, y)) == img.getpixel((x, y + p))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_azul_package_assets.py -q`
Expected: FAIL —— `test_azul_assets_expose_exactly_expected_keys` 的键集与 25 不符（现有 `_art.ASSETS` 仍是 15 键），且 `azul_wall_bg` 不存在。

- [ ] **Step 3: 重写** `boardgames/azul/sprites.py`（第 1 段：调色 + 生成器函数）

```python
# -*- coding: utf-8 -*-
"""Azul 展示包素材生成器（25 键 = 22 新增/改尺寸 + 3 沿用；在共享 artkit + geom 之上程序化原创，无外部素材）。

产物：
  boardgames/azul/assets/*.png   —— 25 个 PNG 源文件（可提交）
  boardgames/azul/_art.py        —— base64 内嵌模块（ASSETS = {...}）

用法（开发期运行一次）：python -m boardgames.azul.sprites
"""
from __future__ import annotations

import base64
import io
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
```

- [ ] **Step 3（续）：追加** `boardgames/azul/sprites.py`（第 2 段：板 / 计分环 / 汇总与输出）

```python
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


def make_legacy_table(size=128):
    """沿用键（第一批过渡）：网页端仍引用的 `azul_table` 桌面底，无缝瓷砖小样。"""
    return ak.ornament_tile(size, _WALL_BG, _WALL_BLUE, _WALL_DEEP, cells=2)


def make_legacy_boardface(size=256):
    """沿用键（第一批过渡）：网页端仍引用的 `azul_boardface`，复用新版玩家板画法。"""
    return make_board(size, size)


def make_legacy_track(w=96, h=48):
    """沿用键（第一批过渡）：网页端仍引用的 `azul_track`，深色计分条 + 刻度。"""
    img, _dr, s = ak.canvas(w, h)
    img = ak.rrect_bevel(img, (0, 0, w, h), h * 0.22, _RING_BODY, s=s, depth=2)
    dr = ImageDraw.Draw(img)
    for i in range(1, 5):
        x = w * i / 5.0
        dr.line((x * s, h * 0.18 * s, x * s, h * 0.82 * s),
                fill=ak.color(_RING_TICK), width=max(1, int(1.4 * s)))
    return ak.finish(img, w, h)


def _build_images():
    """25 键 → PIL 图像（键序无关）。"""
    imgs = {
        "azul_wall_bg": make_wall_bg(),
        "azul_plate": make_plate(center=False),
        "azul_plate_center": make_plate(center=True),
        "azul_board": make_board(),
        "azul_chip": make_chip(),
        "azul_track_ring": make_track_ring(),
        "azul_floor": make_floor(),
        "azul_table": make_legacy_table(),
        "azul_boardface": make_legacy_boardface(),
        "azul_track": make_legacy_track(),
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
```

- [ ] **Step 4: 重新生成产物 + 跑测试**

```bash
python -m boardgames.azul.sprites
python -m pytest tests/test_azul_package_assets.py -q
```

Expected: 生成输出 `generated 25 azul assets`；测试全绿（25 键 + 尺寸 + `azul_wall_bg` 无缝 + 3 沿用键存在）。

- [ ] **Step 5: 收尾（不提交）**

改动留在工作区待评审；不要 git add/commit/push。

---

## Task 5: `boardgames/shell.py` 新增游戏无关组件（键全部外置）

**Files:**
- Modify: `boardgames/shell.py`
- Modify: `boardgames/azul/desktop.py`（**仅第 61 行的 `shell.layout` 调用点**机械适配，见 Step 3 末）
- Test: `tests/test_shell_components.py`

**Interfaces:**
- Consumes：`client_gameui` 的 `_asset_at(cv, key, x, y, size, anchor="nw")`（`size` 可为 `int` 或 `(w, h)` 元组 ⇒ 非正方形拉伸）、`_asset_bg`、`_disc`、`_stone`、`_text`、`_rrect`、`_turn_banner`、`_UXC`、`_TXT`、`_PANEL_BD`、`_FONT_F`；`boardgames.geom`。
- Produces（**不含任何游戏规则语义**；素材键一律由调用方传入）：
  - 常量 `INFO_H=30`、`SLOT_BG="#E4D9C3"`、`SLOT_BD="#CDBE9C"`、`NAME_FG="#2B3A46"`、`ROW_FG="#9AA6B0"`
  - `_key(keys, role, color=None) -> str|None`（`keys` 可为 `str` / `dict`（模板含 `{c}`）/ callable；异常与缺键都返回 `None`）
  - `table(cv, w, h, y0=HEADER_H, *, bg_key=None)`、`info_bar(cv, w, y, h, round_no, turn_nick, bag, scores, me, *, bg_key=None, chip_key=None)`、`factory_disc(cv, cx, cy, r, tiles, *, plate_key=None, tile_key=None, center=False, colors=None)`、`board_panel(cv, x, y, w, h, name, rows, wall, floor, score, keys, *, wall_expected=None, active=False, compact=False, note=None)`、`score_ring(cv, cx, cy, r, scores, me, markers=None, *, ring_key=None, marker_key=None, steps=30, colors=None)`
  - `layout(w, h, y0=HEADER_H, n_players=2, info_h=INFO_H) -> dict`：**新增分区键** `info` / `left` / `center` / `right`（各区矩形 `(x0, y0, x1, y1)`）、`cell` / `cols` / `rows`；**并保留 6 个 legacy 标量键** `top_h` / `base_y` / `avh` / `rw` / `wlx` / `wcell`（值与原元组版**逐字相同**），使 Task 5 里 `azul/desktop.py` 的改动只是机械解包、行为零变化（Task 6 再删 legacy 键）。
  - `player_panel` **保持原样不动**。
- 硬约束：`boardgames/shell.py` 源码内**不得出现 `azul_` 字面量**（由测试锁住）。

- [ ] **Step 1: 写失败测试** `tests/test_shell_components.py`

```python
# -*- coding: utf-8 -*-
"""共用外壳新组件：桩画布安全、分区字典契约、键名外置（不得硬编码 azul_*）。"""
from pathlib import Path

from boardgames import shell

ROOT = Path(__file__).resolve().parents[1]

FAKE_KEYS = {
    "board": "fake_board",
    "tile": "fake_tile_{c}",
    "wall_cell": "fake_wall_{c}",
    "floor": "fake_floor",
    "chip": "fake_chip",
    "marker": "fake_marker_{c}",
    "color": {"r": "#D2534F", "w": "#F0F0F0", "b": "#4A7DE0",
              "y": "#E0B33C", "k": "#3A3A3A"},
}


class _Stub:
    """最小画布桩：任何绘制入口都记录调用并返回 None（不实例化 tk / ImageTk）。"""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _call(*a, **k):
            self.calls.append((name, a, k))
            return None
        return _call


def test_table_falls_back_to_flat_color_without_key():
    cv = _Stub()
    shell.table(cv, 800, 600)
    assert any(n == "create_rectangle" for n, _a, _k in cv.calls)


def test_layout_returns_zone_dict_and_legacy_scalars():
    d = shell.layout(1280, 720, n_players=3)
    for key in ("info", "left", "center", "right", "cell", "cols", "rows",
                "top_h", "base_y", "avh", "rw", "wlx", "wcell"):
        assert key in d, key
    for key in ("info", "left", "center", "right"):
        x0, y0, x1, y1 = d[key]
        assert x1 > x0 and y1 > y0
    assert d["right"][0] >= d["center"][2]
    assert d["info"][3] <= d["left"][1]


def test_info_bar_renders_without_any_key():
    cv = _Stub()
    shell.info_bar(cv, 900, shell.HEADER_H, shell.INFO_H, 3, "P7", 21,
                   {"7": 5, "8": 3}, 7)
    assert cv.calls


def test_factory_disc_draws_plate_and_tiles():
    cv = _Stub()
    tiles = [{"c": "r"}, {"c": "b"}, {"c": "r"}]
    shell.factory_disc(cv, 120, 160, 44, tiles, plate_key="fake_plate",
                       tile_key="fake_tile_{c}", colors=FAKE_KEYS["color"])
    assert cv.calls
    holes = _Stub()
    shell.factory_disc(holes, 120, 160, 40, tiles, center=True,
                       plate_key="fake_plate_c", tile_key="fake_tile_{c}")


def test_board_panel_draws_rows_wall_floor_and_score():
    cv = _Stub()
    shell.board_panel(cv, 0, 0, 384, 288, "P7",
                      rows={"0": ["r"], "1": ["b", "b"]},
                      wall={"0,0": "b"}, floor=["k", "r"], score=5,
                      keys=FAKE_KEYS, wall_expected=lambda r, c: "rwbyk"[(c - r) % 5],
                      active=True)
    assert cv.calls
    assert any(n == "create_text" for n, _a, _k in cv.calls)


def test_score_ring_places_one_marker_per_player():
    cv = _Stub()
    shell.score_ring(cv, 500, 300, 90, {"7": 5, "8": 30}, 7,
                     markers={"7": "b", "8": "k"}, ring_key="fake_ring",
                     marker_key="fake_marker_{c}", colors=FAKE_KEYS["color"])
    assert cv.calls


def _create_text_args(cv):
    return [a for n, a, _k in cv.calls if n == "create_text"]


def test_board_panel_compact_skips_row_labels_and_keeps_note():
    compact = _Stub()
    shell.board_panel(compact, 0, 0, 384, 288, "P7", rows={}, wall={}, floor=[],
                      score=0, keys=FAKE_KEYS, active=False, compact=True,
                      note="地板 3")
    txt = [str(v) for a in _create_text_args(compact) for v in a]
    assert "1" not in txt and "2" not in txt and "5" not in txt
    assert any("地板 3" in t for t in txt)

    wide = _Stub()
    shell.board_panel(wide, 0, 0, 384, 288, "P7", rows={}, wall={}, floor=[],
                      score=0, keys=FAKE_KEYS, active=False)
    wtxt = [str(v) for a in _create_text_args(wide) for v in a]
    assert "1" in wtxt and "5" in wtxt


def test_shell_does_not_hardcode_azul_keys():
    src = (ROOT / "boardgames" / "shell.py").read_text(encoding="utf-8")
    assert "azul_" not in src
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_shell_components.py -q`
Expected: FAIL —— `AttributeError: module 'boardgames.shell' has no attribute 'info_bar'`（`test_shell_does_not_hardcode_azul_keys` 也会因为现有 `table()` 里的 `azul_table` 字面量而 FAIL）。

- [ ] **Step 3: 改写** `boardgames/shell.py`（整文件替换；`player_panel` 原样保留在文件末尾）

```python
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
    另保留 legacy 标量 top_h/base_y/avh/rw/wlx/wcell（与旧元组版逐字相同），
    供尚未迁移的调用点机械解包（Task 6 迁移完成后删除）。
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
                  _UXC["accent"] if uid == me else "#EAF2F7", (_FONT_F[0], 9),
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
        if uid == me:
            cv.create_oval(px - ms * 0.7, py - ms * 0.7, px + ms * 0.7,
                           py + ms * 0.7, outline="#FFD977", width=2)
```

`player_panel`（文件末尾）**逐字保留**，不要改动。

同一 Step 里对 `boardgames/azul/desktop.py` 做**两处机械改动**（保持行为零变化的过渡）：

```python
    # 原第 57 行
    shell.table(cv, w, h, bg_key="azul_table")      # 过渡：Task 6 会改为 azul_wall_bg
    # 原第 61 行（元组解包 → dict 取 legacy 键）
    lay = shell.layout(w, h)
    top_h, base_y, avh, rw, wlx, wcell = (lay[k] for k in
                                          ("top_h", "base_y", "avh", "rw", "wlx", "wcell"))
```

- [ ] **Step 4: 跑定向测试**

```bash
python -m pytest tests/test_shell_components.py -q
python -m pytest tests/test_boardgame_asset_img.py -q
python -m pytest tests/test_game_packages.py tests/test_game_shell_pal.py tests/test_game_shell_wiring.py -q
```

Expected: `tests/test_shell_components.py` **8 passed**；`test_boardgame_asset_img.py` 无新增 FAIL（本机缺 tcl 时真 Tk 用例 `skip`）；其余无新增 FAIL。若 `test_game_shell_pal.py` / `test_game_shell_wiring.py` 不存在则跳过该行。

- [ ] **Step 5: 收尾（不提交）**

改动留在工作区待评审；不要 git add/commit/push。

---

## Task 6: Azul 桌面版面重排为 BGA 结构

**Files:**
- Modify: `boardgames/azul/desktop.py`（`paint` 整体重排；删除暂行的 legacy 解包）
- Modify: `tests/test_boardgame_asset_img.py`（第 168-172 行断言换新键）
- 依赖：Task 4 的 25 键素材（其中 3 个沿用键仅供网页端）、Task 5 的 shell 组件与 `layout` 分区。

**Interfaces:**
- Consumes：`shell.header/table/layout/info_bar/factory_disc/board_panel/score_ring/player_panel/HEADER_H/INFO_H`；`client_gameui` 的 `THEME/_text/_disc/_FONT_F/_UXC`；`boardgames/azul/sprites.py` 的键集（不 import，只用键字符串）。
- Produces：`KEYS`（角色→Azul 键）、`_wall_target(r, c)`（引擎拉丁方目标色 `COLORS[(c - r) % 5]`）、`_marker_map(players)`（uid→色键，按玩家序号轮转 `"rwbyk"`）、`paint(...)` 签名与 `take/place/floor` 动作契约**保持不变**。
- 版面（spec §7）：信息条 / 左列工厂盘（竖排）+ 中央池 / 中部横排**所有玩家板**（自己 `active=True`，对手缩略）/ 右侧圆形计分轨 + 分数清单。
- 窄窗规则（写死，不要"视情况而定"）：`cols = layout(...)["cols"]`（≤3 人恒 1 列；4 人以上 3 列换行）；当 `cell` 宽 < 190px 时对手板不再画花纹行文字标签与地板文字，只画位图板面 + 跟踪格（`compact = cell[0] < 190`）。

- [ ] **Step 1: 更新素材契约测试** `tests/test_boardgame_asset_img.py`

**(a)** 把 `test_azul_painter_consumes_package_assets` 里当前第 168-170 行的三条断言整段替换为：

```python
        assert "azul_wall_bg" in img_keys       # 桌面底：无缝瓷砖墙（_asset_bg 走 img 缓存）
        assert "azul_board" in img_keys         # 玩家板面（元组尺寸 → 非正方形拉伸）
        assert "azul_plate" in img_keys         # 工厂盘
        assert "azul_plate_center" in img_keys  # 中央池
        assert "azul_track_ring" in img_keys    # 圆形计分轨
        assert "azul_marker_r" in img_keys      # 计分棋子（uid 7 → "r"）
        assert "azul_chip" in img_keys          # 分数筹码（信息条 + 板面铭牌行）
        assert "azul_floor" in img_keys         # 地板槽
        assert "azul_tile_r" in img_keys        # 花砖（自己第 1 行有红砖、工厂盘里也有）
```

**(b)** 在同文件末尾（`test_gemcity_painter_switches_felt_to_azulejo` 之后）追加 headless 键序遥测 —— 本机缺 tcl 时真 Tk 用例会整体 `skip`，这条不依赖 Tk / 不依赖 Pillow，必须能独立证明「新画师取的是新键」：

```python
# ------------------------------------------------- headless 键序遥测（新画师契约）
class _ProbeCanvas:
    """接收任意绘制调用的画布桩：只兜住属性、不做记录断言。"""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _call(*a, **k):
            self.calls.append(name)
            return None
        return _call


def test_azul_headless_painter_requests_all_new_keys(monkeypatch):
    """无 Tk / 无显示也验证：Azul 画师确实按新键集取材，且不再请求旧三键（本批仍生成、仅供网页端）。

    shell 组件是 `from client_gameui import _asset_at` 的**直接引用**，故必须同时
    打桩 `boardgames.shell` 与 `client_gameui` 两处，否则拿不到调用遥测。
    """
    from boardgames import shell as bshell

    asked = []

    def _rec_at(cv, key, x, y, size, anchor="nw"):
        asked.append(key)
        return False                     # 立刻失败 → 矢量回退，不触碰 ImageTk

    def _rec_bg(cv, key, x0, y0, x1, y1):
        asked.append(key)
        return False

    monkeypatch.setattr(bshell, "_asset_at", _rec_at)
    monkeypatch.setattr(bshell, "_asset_bg", _rec_bg)
    monkeypatch.setattr(cu, "_asset_at", _rec_at)
    monkeypatch.setattr(cu, "_asset_bg", _rec_bg)
    cv = _ProbeCanvas()
    cu.render(cv, "azul", _azul_state(), 7, lambda uid: f"P{uid}",
              lambda msg: None, lambda: None, {}, None, 900, 640)
    for k in ("azul_wall_bg", "azul_board", "azul_plate", "azul_plate_center",
              "azul_track_ring", "azul_marker_r", "azul_chip", "azul_floor",
              "azul_tile_r", "azul_wall_cell_b"):
        assert k in asked, k
    for k in ("azul_table", "azul_boardface", "azul_track"):
        assert k not in asked, k
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_boardgame_asset_img.py -q -k "requests_all_new_keys"`
Expected: FAIL —— 旧画师只请求 `azul_table`/`azul_boardface`/`azul_track`/`azul_floor`/`azul_plate`/`azul_tile_*`/`azul_wall_cell_*`，`azul_wall_bg` 与 `azul_track_ring`、`azul_marker_r`、`azul_chip`、`azul_plate_center` 都不在 `asked` 里，首个 `assert "azul_wall_bg" in asked` 即失败。

（同文件里真 Tk 的 `test_azul_painter_consumes_package_assets` 本机因缺 tcl 会 `skip`，不作为本步的失败证据。）

- [ ] **Step 3: 重写** `boardgames/azul/desktop.py`（整文件替换）

```python
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
    """uid → 计分棋子色键（按座位顺序轮转 rwbyk；双端同源，桌面与网页一致）。"""
    return {u: _MARKERS[i % len(_MARKERS)] for i, u in enumerate(players or [])}


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
```

旧的 `_plate` / `_tiles` / `_EMPTY` / `_SLOT_BD` / `math` 依赖与 `_asset_nine_at` 调用**全部删除**（盘 / 砖 / 板面渲染已迁入 `shell` 组件）。`submit` / `repaint` / `priv` 仍是既有签名参数、本画师不使用（动作按钮由画布端既有机制提交，契约 `take/place/floor` 不变）。

- [ ] **Step 4: 跑定向测试**

```bash
python -m pytest tests/test_boardgame_asset_img.py -q
python -m pytest tests/test_shell_components.py -q
python -m pytest tests/test_azul_package_assets.py tests/test_board_geom.py tests/test_artkit.py -q
python -m pytest tests/test_game_packages.py tests/test_desktop_gameui_registry.py -q
```

Expected: `test_boardgame_asset_img.py` 全绿（真 Tk 用例本机 `skip`，headless 遥测用例 PASS）；`test_shell_components.py` 8 passed；其余无新增 FAIL。若 `tests/test_desktop_gameui_registry.py` 不存在则跳过最后一行。

- [ ] **Step 5: 收尾（不提交）**

改动留在工作区待评审；不要 git add/commit/push。

---

## Task 7: 开发期样张（BGA 桌面版面目视）+ 定向回归

**Files:**
- Create: `_azul_preview.py`（仓库根）
- Run（产样张）: `python _azul_preview.py` → `.trae/tmp/azul_desktop_preview.png`
- Run（定向回归，逐文件独立进程）

**Interfaces:**
- Consumes：`client_gameui.render(cv, "azul", st, me, nick, submit, repaint, ui, priv, w, h)`、`boardgames.azul.sprites` 的 25 键。
- Produces：窗口内 Azul 桌面版面 + 落盘样张 `.trae/tmp/azul_desktop_preview.png`（供用户目视评审第一批观感）。

- [ ] **Step 1: 新建** `_azul_preview.py`

```python
# -*- coding: utf-8 -*-
"""开发期样张：在真 Tk 画布上渲染 Azul 的 BGA 桌面版面并存 PNG。

用法：python _azul_preview.py   →  .trae/tmp/azul_desktop_preview.png
不入库、不参与打包（下划线前缀与 _gen_boardgame.py 惯例一致）。
"""
from pathlib import Path

import tkinter as tk

OUT = Path(".trae/tmp/azul_desktop_preview.png")
W, H = 1280, 760


def _mock_state():
    """3 人对局 · 第 3 轮 · 袋剩 21 · 5 个工厂盘 + 中央池（墙按拉丁方部分已落）。"""
    cols = list("rwbyk")
    def wall(rows, shift=0):
        return {f"{r},{c}": cols[(c - r + shift) % 5]
                for r in range(rows) for c in range(5)}
    offers = [
        [{"c": "r"}, {"c": "b"}, {"c": "w"}, {"c": "k"}],
        [{"c": "y"}, {"c": "y"}, {"c": "b"}],
        [{"c": "r"}, {"c": "r"}, {"c": "k"}],
        [{"c": "w"}, {"c": "b"}],
        [{"c": "k"}, {"c": "y"}],
    ]
    return {
        "players": [7, 8, 9],
        "round": 3,
        "bag": 21,
        "turn_uid": 8,
        "winner_uid": None,
        "score": {"7": 5, "8": 12, "9": 3},
        "rows": {"7": {"0": ["r"]}, "8": {"0": ["b", "b"], "2": ["y"]}, "9": {}},
        "wall": {"7": wall(1), "8": wall(2), "9": wall(1, shift=1)},
        "floor": {"7": 1, "8": 0, "9": 2},
        "offers": offers,
        "center": [{"c": "r"}, {"c": "k"}],
    }


def main():
    import client_gameui as cu

    root = tk.Tk()
    root.title("Azul 桌面版面样张")
    root.geometry(f"{W}x{H}")
    cv = tk.Canvas(root, width=W, height=H, highlightthickness=0, bg="#000000")
    cv.pack()

    cu.render(cv, "azul", _mock_state(), 7, lambda uid: f"P{uid}",
              lambda msg: None, lambda: None, {}, None, W, H)
    root.update_idletasks()
    root.update()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import ImageGrab
        x0, y0 = root.winfo_rootx(), root.winfo_rooty()
        ImageGrab.grab((x0, y0, x0 + W, y0 + H)).save(OUT)
        print("saved", OUT)
    except Exception as exc:                      # 无 Pillow / 无显示时仍展示窗口
        print("grab failed:", exc)
    root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 逐文件定向回归（每个文件独立进程）**

```bash
python -m pytest tests/test_artkit.py -q
python -m pytest tests/test_board_geom.py -q
python -m pytest tests/test_azul_package_assets.py -q
python -m pytest tests/test_shell_components.py -q
python -m pytest tests/test_boardgame_asset_img.py -q
python -m pytest tests/test_web_boardgame_assets.py -q
python -m pytest tests/test_boardgame_assets.py -q
python -m pytest tests/test_game_packages.py -q
python -m pytest tests/test_game_shell_pal.py -q
python -m pytest tests/test_game_shell_wiring.py -q
python -m pytest tests/test_theme.py -q
```

Expected：全部**无新增 FAIL**（本机缺 tcl 时真 Tk 用例 `skip`）。`tests/test_web_boardgame_assets.py` 本批**未改**，应保持原结论（原本 PASS 则仍 PASS）。文件不存在则跳过该行。

- [ ] **Step 3: 目视样张**

打开 `.trae/tmp/azul_desktop_preview.png`，对照 spec §7 的 BGA 版面：信息条 / 左工厂列 + 中央池 / 中部自己大板 + 对手缩略 / 右侧圆形计分轨 + 分数清单。把样张交给用户评审第一批观感；**第二批（网页版面重排 + 全量回归 + 打包）待用户确认后再启动**。

- [ ] **Step 4: 收尾（不提交）**

改动留在工作区待评审；不要 git add/commit/push。全量回归 `python tests/_run_all.py` 与双 EXE 打包 `python build.py` 属第二批。

## Self-Review（写入计划的最后一步自查）

- [ ] **Spec 覆盖**（spec §3–§11）
  - §3 红线：artkit/geom 不 import tkinter（Task 1/2/3 测试锁住）；不改 `design_tokens()` golden digest；不改主聊天窗 CSS/token；不删 `_GAME_ICON` 既有键。
  - §4 artkit：Task 1（基础原语）+ Task 2（装饰与质感原语）覆盖 spec 列表全部函数。
  - §5 Azul 素材：Task 4 生成 25 键（22 新增/改尺寸 + 3 沿用）。
  - §6 外壳扩展：Task 5 新增 `table` / `info_bar` / `factory_disc` / `board_panel` / `score_ring` + `layout` 分区。
  - §7 桌面版面：Task 6 重排 + Task 7 样张。
  - §8 网页版面：**本批不做**（列在文末「第二批」）。
  - §10 测试策略：Task 1/2/3/5/6 各带失败测试；Task 7 定向回归。
  - §11 风险：窄窗（`compact`）与无缝纹样（`test_azul_wall_bg_is_seamless`）均有对应断言。
- [ ] **占位符扫描**：无 TBD / TODO / 「稍后补」；每个 Step 都有可执行命令或完整代码。
- [ ] **类型一致性**：`_key` 返回 `str|None`；`layout` 返回 dict，键集在 Task 5 与 Task 6 一致；`board_panel` 的 `compact` / `note` 在 Task 5 定义、Task 6 使用，签名与 Task 7 遥测不冲突。
- [ ] **任务独立性**：Task 1→2 依赖 artkit；Task 3 独立；Task 4 依赖 artkit + geom；Task 5 依赖 geom；Task 6 依赖 Task 4/5；Task 7 依赖全部。
- [ ] **沿用键说明**：本批保留 `azul_table` / `azul_boardface` / `azul_track`（网页端未改，仍引用），故包内必须继续生成；第二批网页重排后随 `_BG_ASSET_KEYS` 一并删除。
- [ ] **不提交**：每个 Task 以「定向测试通过 + 改动留工作区待评审」收尾。

## 第二批（不在本计划内）

- 网页版面重排：`azul(box,s)` 遍历 `s.players` 画**所有玩家板**（修掉「只画一块板」）+ CSS grid 复刻 BGA 结构。
- `boardgames/azul/web.py` / `web.py._BG_ASSET_KEYS` / `tests/test_web_boardgame_assets.py` 键名与结构标记同步。
- 删除 3 个沿用键（`azul_table` / `azul_boardface` / `azul_track`）及其生成函数 `make_legacy_*`。
- 全量回归 `python tests/_run_all.py` + 双 EXE 打包 `python build.py` + EXE 配对烟雾测试。
- 其余 45 款游戏的可选迁移（超出本轮范围）。
