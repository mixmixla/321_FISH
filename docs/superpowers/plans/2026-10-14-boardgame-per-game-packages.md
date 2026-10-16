# 桌游展示层「每游戏独立包 + 共用外壳」实现计划（Azul 精修试点）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立「每款游戏独立展示包 + 共用外壳」框架（桌面与网页双端），并把 Azul（花砖物语·拼花）迁为第一个样板包并完成版面/美术精修。

**Architecture:** 新增 `boardgames/` 展示包根：`registry.py` 用**字符串引用 + 惰性 importlib** 解耦（包模块 import 期不得拉起 tkinter）；`shell.py` 提供共用外壳组件；`boardgames/<game>/{meta,desktop,web,sprites,_art}` 单款自成一体。桌面 `client_gameui.render()` 在旧 `_PAINTERS` 未命中时回落查注册表；网页 `web.py` 在模板留注入点，服务时把已迁移包的渲染器与 CSS 组装进单页。未迁移的 46 款走旧实现，零回归。

**Tech Stack:** Python 3 / Tkinter / Pillow（程序化生成素材，base64 内嵌）/ 原生 JS + CSS（web 单文件内联模板）/ pytest / node（JS 语法探针）/ PyInstaller。

**Spec:** `docs/superpowers/specs/2026-10-14-boardgame-per-game-packages-design.md`

## Global Constraints

- 全部素材 **Pillow 程序化原创**；仅对标 BGA 风格方向，不复制任何素材/坐标/色彩采样。
- **不改** `ui_design.design_tokens()` golden digest：`a137658af6f3f9899c2106a0e6020c1b1e6d2569bab462488bb7c42dc0eb4078`。
- **不删** `_GAME_ICON` 既有键；**不破坏** `icon_svg` 字节兼容；**不改** 主聊天窗（`ChatWindow`）皮肤与 `web.py` 主聊天区 CSS/token。
- 假画布桩下（`_real_cv(cv)` 为 False）**绝不调用** `ImageTk.PhotoImage(master=cv)`。
- **不改** `theme.py`、`games_pkg/**` 规则层、`client.py`（本轮不涉及）。
- 未迁移的 46 款游戏**行为与外观零变化**；`_PAINTERS` 与内联 `GRENDER` 对它们保持原样。
- verify 目标为「**无新增 FAIL**」（pre-existing FAIL 不计；本机 Tk 缺 tcl 库导致的 `TclError` 属环境，不是缺陷）。
- 网页注入后整页 JS 必须语法合法：`node tests/ux_visual_chat_probe.cjs` 必须通过。
- **未经用户明确要求不 commit / push。**

---

## File Structure

**新增**
- `boardgames/__init__.py` — 包根（空，仅声明包）。
- `boardgames/registry.py` — 展示包契约 `GamePackage`、注册/解析/合并。
- `boardgames/shell.py` — 桌面共用外壳（深色桌面底、横幅、玩家面板、操作条、栅格）。
- `boardgames/azul/__init__.py` — Azul 展示包登记（元数据 + 字符串引用，轻量）。
- `boardgames/azul/sprites.py` — Azul 素材生成（Pillow）。
- `boardgames/azul/_art.py` — 生成产物：`ASSETS: dict[str, str]`（data-URI）。
- `boardgames/azul/assets/*.png` — 生成产物 PNG（Azul 专属）。
- `boardgames/azul/desktop.py` — `paint(cv, st, me, nick, submit, repaint, ui, priv, w, h)`。
- `boardgames/azul/web.py` — `WEB_JS` / `WEB_CSS` 字符串（注入进单页）。
- `tests/test_game_packages.py`、`tests/test_azul_package_assets.py`。

**修改**
- `client_gameui.py` — `render()` 增加注册表回落（并删除 `_p_azul` 与 `@_register("azul")`，见 Task 6）。
- `web.py` — 模板加注入点；`_SERVED_PAGE()` 组装；`_bg_assets_subset()` 合并包素材；删除内联 `azul(box,s)`（见 Task 5）。
- `tests/test_web_boardgame_assets.py` — 适配「素材源变多」的降级断言。
- `build.py` — 仅追加 hidden-import 清单（Task 7）。

**不改动**：`_gen_boardgame.py` / `_art_boardgame.py` / `assets/boardgame/**`（共享素材保持原样；Azul 包用**新键**，旧 `azul_*` 键成为死键，留待后续清理）。

---

## Task 1: 展示包注册表与契约

**Files:**
- Create: `boardgames/__init__.py`, `boardgames/registry.py`
- Test: `tests/test_game_packages.py`

**Interfaces:**
- Produces:
  - `boardgames.registry.GamePackage(name, label, rules, icon=None, desktop=None, web_js=None, web_css=None, assets=None)`（`NamedTuple`，后四项为 `"mod:attr"` 字符串引用或 `None`）。
  - `register(pkg) -> GamePackage`；`load_all() -> None`（幂等，按 `PACKAGE_MODULES` 显式加载）。
  - `all_packages() -> list[GamePackage]`；`get(name) -> GamePackage | None`。
  - `desktop_painter(name)`；`web_parts() -> tuple[str, str]`；`package_assets() -> dict[str, str]`；`asset_keys() -> tuple[str, ...]`。
  - 解析失败一律返回 `None`/空（调用方走旧兜底），**绝不抛出**。
- 约束：`import boardgames.registry` **不得**拉起 tkinter/Pillow（包模块只导出元数据与字符串）。

- [ ] **Step 1: 写失败测试** `tests/test_game_packages.py`

```python
# -*- coding: utf-8 -*-
"""展示包注册表：契约、惰性解析、失败兜底。"""
import sys
import types

import pytest

from boardgames import registry as reg


def _fake_pkg(name="faketest"):
    return reg.GamePackage(name=name, label="假包", rules="games_pkg.azul:AzulGame",
                           icon="azul",
                           desktop="tests._fakepkg:PAINT_CALLS",
                           web_js="tests._fakepkg:WEB_JS",
                           web_css="tests._fakepkg:WEB_CSS",
                           assets="tests._fakepkg:ASSETS")


def _install_fakepkg():
    mod = types.ModuleType("tests._fakepkg")
    mod.PAINT_CALLS = []
    mod.WEB_JS = "Object.assign(GRENDER,{});"
    mod.WEB_CSS = ".fake{}"
    mod.ASSETS = {"fake_a": "data:image/png;base64,AAAA"}
    sys.modules["tests._fakepkg"] = mod
    return mod


def test_registry_import_headless_and_no_tkinter():
    assert "tkinter" not in sys.modules
    assert "PIL" not in sys.modules


def test_register_get_and_resolve():
    _install_fakepkg()
    pkg = reg.register(_fake_pkg())
    assert reg.get("faketest") is pkg
    assert reg.desktop_painter("faketest") is sys.modules["tests._fakepkg"].PAINT_CALLS
    js, css = reg.web_parts()
    assert "Object.assign(GRENDER" in js and ".fake{}" in css
    assert reg.package_assets()["fake_a"].startswith("data:image/png;base64,")
    assert "fake_a" in reg.asset_keys()


def test_missing_ref_and_unknown_name_degrade_to_none():
    assert reg.get("does_not_exist") is None
    assert reg.desktop_painter("does_not_exist") is None
    bad = reg.register(reg.GamePackage(name="badtest", label="坏包", rules="x:y",
                                       desktop="no.such.module:paint",
                                       assets="no.such.module:ASSETS"))
    assert reg.desktop_painter("badtest") is None
    assert "badtest" not in reg.package_assets()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_game_packages.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'boardgames'`）

- [ ] **Step 3: 实现** `boardgames/__init__.py`

```python
# -*- coding: utf-8 -*-
"""桌游展示包根：每款游戏的版面/渲染/素材自成一体（与规则层 games_pkg 并列）。"""
```

`boardgames/registry.py`

```python
# -*- coding: utf-8 -*-
"""展示包注册表：把「每款游戏的版面/渲染/素材」从巨石里解耦。

设计要点：
- 包模块必须轻量（只导出元数据与字符串引用），不得在 import 期拉起 tkinter；
  桌面画师 / 网页片段 / 素材模块都用 "mod:attr" 字符串引用，按需 importlib 解析。
- 未迁移的游戏不在注册表内，调用方走旧实现（零回归）。
- 任何解析失败都吞掉并返回 None/空，绝不让渲染路径抛异常。
"""
from __future__ import annotations

import importlib
from typing import NamedTuple, Optional


class GamePackage(NamedTuple):
    name: str
    label: str
    rules: str
    icon: Optional[str] = None
    desktop: Optional[str] = None
    web_js: Optional[str] = None
    web_css: Optional[str] = None
    assets: Optional[str] = None


PACKAGE_MODULES: tuple = ("boardgames.azul",)

_REGISTRY: dict = {}
_LOADED = False


def register(pkg: GamePackage) -> GamePackage:
    _REGISTRY[pkg.name] = pkg
    return pkg


def load_all() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    for mod in PACKAGE_MODULES:
        try:
            importlib.import_module(mod)
        except Exception:
            continue


def all_packages() -> list:
    load_all()
    return list(_REGISTRY.values())


def get(name: str) -> Optional[GamePackage]:
    load_all()
    return _REGISTRY.get(name)


def _resolve(ref: Optional[str]):
    if not ref or ":" not in ref:
        return None
    mod, attr = ref.split(":", 1)
    try:
        return getattr(importlib.import_module(mod), attr)
    except Exception:
        return None


def desktop_painter(name: str):
    pkg = get(name)
    return _resolve(pkg.desktop) if pkg else None


def web_parts() -> tuple:
    js, css = [], []
    for pkg in all_packages():
        j = _resolve(pkg.web_js)
        c = _resolve(pkg.web_css)
        if j:
            js.append(j)
        if c:
            css.append(c)
    return "\n".join(js), "\n".join(css)


def package_assets() -> dict:
    out: dict = {}
    for pkg in all_packages():
        a = _resolve(pkg.assets)
        if isinstance(a, dict):
            out.update(a)
    return out


def asset_keys() -> tuple:
    keys: list = []
    for pkg in all_packages():
        a = _resolve(pkg.assets)
        if isinstance(a, dict):
            keys.extend(a.keys())
    return tuple(keys)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_game_packages.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add boardgames/__init__.py boardgames/registry.py tests/test_game_packages.py
git commit -m "feat(boardgames): add presentation-package registry and contract"
```

---

## Task 2: 桌面接线（`render()` 回落注册表）

**Files:**
- Modify: `client_gameui.py:1790-1799`（`render`）
- Test: `tests/test_game_packages.py`（追加）

**Interfaces:**
- Consumes: `boardgames.registry.desktop_painter(name)`（Task 1）。
- Produces: `client_gameui.render()` 在 `_PAINTERS` 未命中时查注册表；解析结果缓存于 `client_gameui._PKG_PAINTERS`（`game -> fn|False`），避免每帧 importlib。

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_game_packages.py`）

```python
def test_client_render_falls_back_to_package_painter():
    import client_gameui as cu
    calls = []
    reg.register(reg.GamePackage(
        name="faketest2", label="假包2", rules="x:y",
        desktop="tests._fakepkg2:PAINT"))
    mod = types.ModuleType("tests._fakepkg2")
    mod.PAINT = lambda cv, st, me, nick, submit, repaint, ui, priv, w, h: calls.append(w)
    sys.modules["tests._fakepkg2"] = mod
    cu._PKG_PAINTERS.pop("faketest2", None)

    class _Cv:
        def delete(self, *a): pass
        def create_text(self, *a, **k): pass
        def bind(self, *a, **k): pass

    cu.render(_Cv(), "faketest2", {}, 1, lambda u: str(u), lambda a: None,
              lambda: None, {}, None, 400, 300)
    assert calls == [400]


def test_client_render_unknown_game_uses_generic_not_package():
    import client_gameui as cu
    cu._PKG_PAINTERS.pop("nope", None)
    assert cu._pkg_painter("nope") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_game_packages.py -q`
Expected: FAIL（`KeyError`/`AttributeError`：`_PKG_PAINTERS` / `_pkg_painter` 不存在；注册表画师未被调用）

- [ ] **Step 3: 实现** —— 在 `client_gameui.py` 的 `render` 定义之前插入缓存与解析器，并改分派：

```python
_PKG_PAINTERS = {}          # 展示包画师缓存：game -> fn | False（False=已确认无）


def _pkg_painter(game):
    """查展示包注册表取画师；未命中/异常返回 None。结果缓存，避免每帧 importlib。"""
    if game in _PKG_PAINTERS:
        return _PKG_PAINTERS[game] or None
    fn = None
    try:
        from boardgames import registry as _registry
        fn = _registry.desktop_painter(game)
    except Exception:
        fn = None
    _PKG_PAINTERS[game] = fn or False
    return fn
```

把 `render` 中的分派改为：

```python
    painter = _PAINTERS.get(game) or _pkg_painter(game)
    if painter:
        painter(cv, st, me, nick, submit, repaint, ui, priv, w, h)
    else:
        _generic(cv, game, st, me, nick, w, h, priv)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_game_packages.py -q`
Expected: PASS

- [ ] **Step 5: 回归**（既有 47 款画师不受影响）

Run: `python -m pytest tests/test_flagship_gui.py tests/test_gemcity_purchase.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add client_gameui.py tests/test_game_packages.py
git commit -m "feat(client_gameui): fall back to presentation packages in render()"
```

---

## Task 3: 网页接线（注入点 + 素材源合并）

**Files:**
- Modify: `web.py`（`_bg_assets_subset` L62；`_SERVED_PAGE` L52-73；模板 `<style>` 末尾；`const GRENDER={...}` 字面量之后，约 L4211 起）
- Modify: `tests/test_web_boardgame_assets.py`
- Test: `tests/test_web_boardgame_assets.py`

**Interfaces:**
- Consumes: `boardgames.registry.web_parts()` / `package_assets()`（Task 1）。
- Produces:
  - `web._bg_assets_all() -> dict[str, str]`：合并内嵌美术与各展示包素材（包优先）。
  - `_SERVED_PAGE()` 输出中 `@@UX_GAME_RENDERERS@@` 与 `@@UX_GAME_CSS@@` 均被替换（无占位符残留）。
  - 模板新增 `@@UX_GAME_RENDERERS@@`（位于 `const GRENDER={...};` 之后，供包注入 `Object.assign(GRENDER,{...})`）与 `<style>` 末尾的 `@@UX_GAME_CSS@@`。

- [ ] **Step 1: 写失败测试**（`tests/test_web_boardgame_assets.py` 追加/修改）

```python
def test_served_page_has_no_game_injection_placeholders():
    html = web._SERVED_PAGE().decode("utf-8")
    assert "@@UX_GAME_RENDERERS@@" not in html
    assert "@@UX_GAME_CSS@@" not in html


def test_bg_subset_merges_package_assets(monkeypatch):
    monkeypatch.setattr(web, "_bg_assets_all",
                        lambda: {"azul_table": "data:image/png;base64,AAAA"})
    html = web._SERVED_PAGE().decode("utf-8")
    assert "@@UX_BG_ASSETS@@" not in html
```

并把既有降级用例改为同时屏蔽新素材源：

```python
def test_missing_assets_module_degrades_to_empty(monkeypatch):
    monkeypatch.setattr(web, "_bg_assets", None)
    monkeypatch.setattr(web, "_bg_assets_all", lambda: {})
    html = web._SERVED_PAGE().decode("utf-8")
    assert "@@UX_BG_ASSETS@@" not in html
    assert _extract_bg_literal(html) == {}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_web_boardgame_assets.py -q`
Expected: FAIL（`@@UX_GAME_RENDERERS@@` 残留；`_bg_assets_all` 不存在）

- [ ] **Step 3: 实现 `web.py`**

在 `_bg_assets_subset` 之前新增合并函数；`_bg_assets_subset` 改用它：

```python
def _bg_assets_all():
    """合并素材源：内嵌美术（_art_boardgame）+ 各展示包素材（包优先）。"""
    out = {}
    if _bg_assets is not None and getattr(_bg_assets, "ASSETS", None):
        out.update(_bg_assets.ASSETS)
    try:
        from boardgames.registry import package_assets
        out.update(package_assets() or {})
    except Exception:
        pass
    return out


def _bg_assets_subset():
    src = _bg_assets_all()
    if not src:
        return {}
    return {k: src[k] for k in _BG_ASSET_KEYS if k in src}
```

在 `_SERVED_PAGE()` 的 `return page.encode("utf-8")` 之前追加：

```python
    try:
        from boardgames.registry import web_parts
        _gjs, _gcss = web_parts()
    except Exception:
        _gjs, _gcss = "", ""
    page = page.replace('@@UX_GAME_RENDERERS@@', _gjs)
    page = page.replace('@@UX_GAME_CSS@@', _gcss)
```

模板：在 `<style>` 块结束（`</style>`）之前插入一行

```html
@@UX_GAME_CSS@@
```

在 `const GRENDER={ ... };` 这条字面量语句**结束之后**插入一行

```javascript
@@UX_GAME_RENDERERS@@
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_web_boardgame_assets.py -q`
Expected: PASS

- [ ] **Step 5: JS 语法探针**

Run: `node tests/ux_visual_chat_probe.cjs`
Expected: `full_script_syntax:true`

- [ ] **Step 6: Commit**

```bash
git add web.py tests/test_web_boardgame_assets.py
git commit -m "feat(web): add game renderer/CSS injection points and merge package assets"
```

---

## Task 4: Azul 素材层（sprites + 生成产物）

**Files:**
- Create: `boardgames/azul/sprites.py`, `boardgames/azul/_art.py`（生成）, `boardgames/azul/assets/*.png`（生成）
- Test: `tests/test_azul_package_assets.py`

**Interfaces:**
- Produces: `boardgames.azul._art.ASSETS: dict[str, str]`，键与尺寸：
  - `azul_table`(128,128)、`azul_boardface`(256,256)、`azul_plate`(128,128)、`azul_track`(96,48)、`azul_floor`(48,48)
  - `azul_wall_cell_{r,w,b,y,k}`(48,48) ×5、`azul_tile_{r,w,b,y,k}`(44,44) ×5
  - 共 **15** 键；值均为 `"data:image/png;base64,..."`。
- 调色（程序化原创，仅风格对标）：
  - 桌面 `#16232E`；板面底 `#F7FAFC` + 纹样 `#DCEAF4`/`#3E7CB1`；空墙格底 `#F2F6F8`；
  - 陶瓷盘身 `#F7FAFC` + 边 `#2E4A63`；计分轨底 `#24405A` + 刻度 `#F2F6F8`；
  - 花砖 5 色：红 `#D2534F`、白 `#F0F0F0`、蓝 `#4A7DE0`、黄 `#E0B33C`、黑 `#3A3A3A`。
- 复用共享生成器惯例：4× 超采样（`SS=4`）、`_begin/_end/_mix` 风格自持（本模块自包含，不 import `_gen_boardgame`）。

- [ ] **Step 1: 写失败测试** `tests/test_azul_package_assets.py`

```python
# -*- coding: utf-8 -*-
"""Azul 展示包素材：键集、尺寸、data-URI 形态、PNG 可解码。"""
import base64
import io

import pytest

pytest.importorskip("PIL")
from PIL import Image

from boardgames.azul import _art

_EXPECTED_WH = {
    "azul_table": (128, 128), "azul_boardface": (256, 256),
    "azul_plate": (128, 128), "azul_track": (96, 48), "azul_floor": (48, 48),
    **{f"azul_wall_cell_{c}": (48, 48) for c in "rwbyk"},
    **{f"azul_tile_{c}": (44, 44) for c in "rwbyk"},
}


def test_azul_assets_expose_exactly_expected_keys():
    assert set(_art.ASSETS) == set(_EXPECTED_WH)
    assert len(_art.ASSETS) == 15


@pytest.mark.parametrize("key,wh", sorted(_EXPECTED_WH.items()))
def test_azul_asset_is_png_data_uri_with_expected_size(key, wh):
    url = _art.ASSETS[key]
    assert url.startswith("data:image/png;base64,")
    raw = base64.b64decode(url.split(",", 1)[1])
    img = Image.open(io.BytesIO(raw))
    assert img.size == wh
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_azul_package_assets.py -q`
Expected: FAIL（`ModuleNotFoundError: boardgames.azul._art`）

- [ ] **Step 3: 实现 `boardgames/azul/sprites.py`**

要求（程序化原创）：
- `SS = 4` 超采样；`_begin(w,h)->(img,draw,s)`、`_end(img)->data-URI` 帮助函数自持。
- `make_table(size=128)`：深蓝灰底 + 极淡斜纹（`#1B2C3A`），需**无缝可平铺**（纹样周期整除边长的整数倍）。
- `make_boardface(size=256)`：阿兹勒赫密铺——4×4 单元，每单元「四瓣花（浅 `#DCEAF4`）+ 八角星（`#3E7CB1`）+ 星芯（`#2B5E8C`）」，**不画网格线**；最大外扩半径 < 半单元宽，天然无缝。
- `make_plate(size=128)`：亮色陶瓷盘——底圆 `#2E4A63` 描边 → 盘身 `#F7FAFC` → 内环 `#8FB6CE`（0.20–0.80，宽 4）→ 内膛 `#E6EFF5`（0.26–0.74）→ 克制高光（白 alpha 46）；四角透明（RGBA）。
- `make_track(w=96,h=48,border=14)`：深蓝底 `#24405A` + 外描边 `#101E2C` + 内描边 `#4A7096`，大圆角（`radius=border`），供九宫格拉伸；刻度在画布端绘制。
- `make_floor(size=48)`：地板槽——浅底 `#F2F6F8` + 描边 `#8FB6CE`，圆角。
- `make_wall_cell(color, size=48)`：米白格 `#F2F6F8` + 内描边 `#DCE6E2` + **该色淡印纹**（对应色 alpha≈64 的角标/星纹，示意该格应有花色）。
- `make_tile(color, size=44)`：圆角砖，**比旧版更饱和**：主体该色、顶部高光淡一档 alpha 64、外描边 `_mix(color,-0.30)`。
- `build_all() -> dict[str,str]`：返回上面 15 键（键序无关）。
- `if __name__ == "__main__":` 写出 `assets/*.png` 并生成 `_art.py`（`ASSETS = {...}`，每值完整 data-URI），打印 `generated 15 azul assets`。

- [ ] **Step 4: 生成产物**

Run: `python -m boardgames.azul.sprites`
Expected: 打印 `generated 15 azul assets`；`boardgames/azul/assets/` 出现 15 个 PNG；`boardgames/azul/_art.py` 含 15 键。

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/test_azul_package_assets.py -q`
Expected: PASS（16 passed）

- [ ] **Step 6: Commit**

```bash
git add boardgames/azul/sprites.py boardgames/azul/_art.py boardgames/azul/assets tests/test_azul_package_assets.py
git commit -m "feat(azul): add package-owned sprite layer (table/board/plate/track/wall/tiles)"
```

---

## Task 5: Azul 展示包登记 + 网页渲染器迁入（删模板内旧渲染器）

**Files:**
- Create: `boardgames/azul/__init__.py`, `boardgames/azul/web.py`
- Modify: `web.py`（把内联 `GRENDER` 里的 `azul(box,s){...}` 整段删除；`_BG_ASSET_KEYS` 追加 Azul 新键）
- Test: `tests/test_web_boardgame_assets.py`

**Interfaces:**
- Consumes: Task 1 注册表；Task 4 的素材键；Task 3 的注入点。
- Produces:
  - `boardgames.azul.PKG`（`GamePackage`，`web_js="boardgames.azul.web:WEB_JS"`、`web_css="boardgames.azul.web:WEB_CSS"`、`assets="boardgames.azul._art:ASSETS"`），并 `register(PKG)`。
  - `boardgames.azul.web.WEB_JS`：一个**自包含语句** `Object.assign(GRENDER,{azul(box,s){...}});`。
  - `boardgames.azul.web.WEB_CSS`：该游戏附加样式（可为空串）。
  - **动作契约不变**：azul 的 `take`/`place`/`floor` 原样。

- [ ] **Step 1: 写失败测试**（`tests/test_web_boardgame_assets.py` 追加）

```python
def test_azul_renderer_comes_from_package_not_inline_template():
    from web import PAGE
    # 模板里不再内联 azul 渲染器
    assert "azul(box,s){" not in PAGE
    html = web._SERVED_PAGE().decode("utf-8")
    # 由包注入
    assert "Object.assign(GRENDER,{" in html
    assert 'op:"take"' in html and 'op:"place"' in html and 'op:"floor"' in html
    for k in ("azul_table", "azul_boardface", "azul_plate", "azul_track"):
        assert k in html, k


def test_azul_web_js_is_a_single_selfcontained_statement():
    from boardgames.azul import web as azweb
    assert azweb.WEB_JS.strip().startswith("Object.assign(GRENDER,{")
    assert azweb.WEB_JS.strip().endswith(");")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_web_boardgame_assets.py -q`
Expected: FAIL（模板仍含 `azul(box,s){`；页面无 `Object.assign(GRENDER`）

- [ ] **Step 3: 实现**

`boardgames/azul/__init__.py`：

```python
# -*- coding: utf-8 -*-
"""Azul 展示包：花砖物语·拼花。版面/渲染/素材自成一体（规则仍在 games_pkg.azul）。"""
from games_pkg.azul import AzulGame  # noqa: F401  （对外自包含；规则复用现有实现）
from boardgames.registry import GamePackage, register

PKG = GamePackage(
    name="azul",
    label="花砖物语 · 拼花",
    rules="games_pkg.azul:AzulGame",
    icon="azul",
    desktop="boardgames.azul.desktop:paint",
    web_js="boardgames.azul.web:WEB_JS",
    web_css="boardgames.azul.web:WEB_CSS",
    assets="boardgames.azul._art:ASSETS",
)
register(PKG)
```

`boardgames/azul/web.py`：把**现有**内联 `azul(box,s){...}` 的实现整体搬来（先保功能、视觉在 Task 6/7 之后再精修其位图引用，本轮先把版面结构按 spec §10 调整为：`azul_table` 底、`azul_plate` 工厂盘、`azul_boardface` 板面、`azul_track` 计分轨、`azul_wall_cell_*` 空墙印纹），包成：

```python
WEB_JS = r"""
Object.assign(GRENDER,{
azul(box,s){
  /* 由 web.py 原内联实现迁出；div 结构改为：
     底 azul_table → 工厂盘行（azul_plate + azul_tile_*）→ 中央池
     → 玩家板（azul_boardface 面：左 5 花纹行、右 5×5 墙用 azul_wall_cell_* 印纹）
     → 计分轨（azul_track）→ 动作条（take/place/floor 契约不变，原样保留） */
},
});
"""
WEB_CSS = ""
```

> 说明：`WEB_JS` 内不得出现未转义的三引号；JS 里凡拼接 HTML 属性一律用**双引号属性或转义**，禁止在单引号属性里嵌单引号（本项目已被此坑咬过一次）。

`web.py`：
- 删除模板里 `azul(box,s){ ... }` 整段（保留 `GRENDER` 其余成员与前后逗号正确）。
- `_BG_ASSET_KEYS` 追加：`"azul_table","azul_boardface","azul_plate","azul_track","azul_floor"` 与 `azul_wall_cell_{r,w,b,y,k}`。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_web_boardgame_assets.py -q`
Expected: PASS

- [ ] **Step 5: JS 语法探针 + 注册表自检**

Run: `node tests/ux_visual_chat_probe.cjs`；`python -c "from boardgames import registry as r; print(r.get('azul'))"`
Expected: 探针 `full_script_syntax:true`；打印 Azul 的 `GamePackage`。

- [ ] **Step 6: Commit**

```bash
git add boardgames/azul/__init__.py boardgames/azul/web.py web.py tests/test_web_boardgame_assets.py
git commit -m "feat(azul): move web renderer into the package; drop inline GRENDER.azul"
```

---

## Task 6: 共用外壳 + Azul 桌面画师迁入（删 `_p_azul`）

**Files:**
- Create: `boardgames/shell.py`, `boardgames/azul/desktop.py`
- Modify: `client_gameui.py`（删除 `_p_azul` 及其 `@_register("azul")`）
- Test: `tests/test_boardgame_asset_img.py`（改造既有 azul 测试）

**Interfaces:**
- Consumes: 注册表（Task 1/2）；Azul 素材键（Task 4）；`client_gameui` 既有原语（`_text/_rrect/_disc/_stone/_turn_banner/_asset_*`、`_FONT_*/_UXC/_TXT/_WHITE/_PANEL_BD`）。
- Produces:
  - `boardgames.shell.table(cv, w, h, y0=47)`、`shell.header(cv, w, title, accent, h=46)`、`shell.layout(w, h)`、`shell.player_panel(cv, x, y, w, rows, me, nick)`。
  - `boardgames.azul.desktop.paint(cv, st, me, nick, submit, repaint, ui, priv, w, h)`。
- 接线：注册表 `desktop` 已指向 `boardgames.azul.desktop:paint`（Task 5 已登记）；`render()` 在 `_PAINTERS` 无 `azul` 时由包接管。

- [ ] **Step 1: 改造既有测试为「走包」**（`tests/test_boardgame_asset_img.py`）
  把 `test_azul_painter_consumes_azulejo_and_boards` 改为断言**新键**（包里才有）：

```python
def test_azul_painter_consumes_package_assets():
    if cu._BG_ASSETS is None or cu._PILImage is None or cu._PILImageTk is None:
        pytest.skip("Pillow/Tk assets unavailable")
    root = tk.Tk()
    try:
        cv = tk.Canvas(root, width=820, height=580)
        cv.pack(); root.update_idletasks(); root.update()
        ui = {}
        cu.render(cv, "azul", _azul_state(), 7, lambda uid: f"P{uid}",
                  lambda m: None, lambda: None, ui, None,
                  cv.winfo_width(), cv.winfo_height())
        img_keys = {k[0] for k in getattr(cv, "_asset_img_cache", {})}
        nine_keys = {k[0] for k in getattr(cv, "_asset_nine_cache", {})}
        assert "azul_table" in img_keys or "azul_table" in nine_keys
        assert "azul_boardface" in img_keys or "azul_boardface" in nine_keys
        assert "azul_tile_r" in img_keys
    finally:
        try: root.destroy()
        except Exception: pass
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_boardgame_asset_img.py -q`
Expected: FAIL（`_p_azul` 仍在用旧键 `azulejo`/`azul_board`，缓存无 `azul_table`/`azul_boardface`）

- [ ] **Step 3: 实现 `boardgames/shell.py`**（延迟绑定，避免循环导入）

```python
# -*- coding: utf-8 -*-
"""桌游对局共用外壳：深色桌面底、标题·轮次横幅、玩家面板、栅格。

循环导入约定：client_gameui 在 import 期不 import boardgames（只在 render() 内
延迟 import）；本模块在 import 期 import client_gameui，故方向单一、无环。
"""
from client_gameui import (
    _text, _rrect, _turn_banner, _asset_bg,
    _FONT_B, _FONT_F, _UXC, _TXT, _WHITE, _PANEL_BD, _UXR_BIG,
)

TABLE_BG = "#16232E"
HEADER_H = 46


def table(cv, w, h, y0=HEADER_H):
    """铺深色桌面底：有 azul_table 素材则平铺，否则纯色回退。"""
    if not _asset_bg(cv, "azul_table", 0, y0, w, h):
        cv.create_rectangle(0, y0, w, h, fill=TABLE_BG, outline="")


def header(cv, w, title, accent, h=HEADER_H):
    _turn_banner(cv, w, h, title, accent)


def layout(w, h, y0=HEADER_H):
    """返回 (top_h, base_y, avh, rw, wlx, wcell)：工厂区高度 / 玩家板起点与可用高 /
    花纹列宽 / 墙起点 x / 墙格边长。窄窗时优先保住「花纹行 + 墙」。"""
    top_h = (h - y0) * 0.40
    base_y = y0 + top_h + 8
    avh = max(60, h - base_y - 20)
    rw = w * 0.30
    wlx = w * 0.36
    wcell = min(avh / 5, max(18, (w - wlx - 24) / 5))
    return top_h, base_y, avh, rw, wlx, wcell


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
```

- [ ] **Step 4: 实现 `boardgames/azul/desktop.py`**（按 spec §10 重排）

`paint(...)` 结构（**必须**保持既有回退与 headless 契约）：
1. `shell.header(cv, w, title, accent)`；标题含轮次/轮到；终局显示胜者。
2. `shell.table(cv, w, h)` 铺深色桌面底。
3. 工厂盘：`_asset_at(cv,"azul_plate", ...)`（失败回退 `_disc`），盘内花砖 `azul_tile_{c}`（失败回退 `_stone`）；盘数 = `len(offers)`，环形均布。
4. 中央池：同盘位图 + `center` 花砖。
5. 玩家板：`_asset_nine_at(cv,"azul_boardface", bx, base_y, bw, avh, border=14)`（失败回退 `_rrect` 浅底）；左侧 5 条花纹行（第 i 行 i+1 格，行首标容量）；右侧 5×5 墙：
   - 空槽用 `azul_wall_cell_{该格应有色}`（应有色 = `COLORS[(c - r) % 5]`，`COLORS=["r","w","b","y","k"]`）；
   - 已落砖用 `azul_tile_{cell}`（失败回退 `create_rectangle` 实色）。
6. 地板线：7 格，用 `azul_floor`（失败回退浅槽）。
7. 计分轨：`_asset_nine_at(cv,"azul_track", ...)`（失败回退 `_rrect` 深蓝底），按 0..30 画刻度（每 5 格加重），并在对应刻度画各玩家棋子（自己用 accent 高亮）。
8. 玩家面板：`shell.player_panel(...)` 放右上或板下（按可用宽高自适应）。

约束：所有 `_asset_*` 调用天然带 `_real_cv` 守卫；不得新增 `ImageTk.PhotoImage(master=cv)`。

- [ ] **Step 5: 删除旧实现** —— 从 `client_gameui.py` 移除 `@_register("azul")` 装饰器与 `def _p_azul(...)` 整个函数（保持文件其余部分不变）。

- [ ] **Step 6: 跑测试确认通过**

Run: `python -m pytest tests/test_boardgame_asset_img.py tests/test_game_packages.py -q`
Expected: PASS

- [ ] **Step 7: 回归**（确认未迁移游戏不受影响）

Run: `python -m pytest tests/test_flagship_gui.py tests/test_gemcity_purchase.py tests/test_kalah_gui.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add boardgames/shell.py boardgames/azul/desktop.py client_gameui.py tests/test_boardgame_asset_img.py
git commit -m "feat(azul): move desktop painter into package with shared shell; drop _p_azul"
```

---

## Task 7: 端到端回归与打包

**Files:**
- Modify: `build.py`（仅追加 hidden-import 清单）
- Test: 全相关测试 + node 探针

**Interfaces:**
- Produces: `build.py` 的 `COMMON_HIDDEN` 追加 `--hidden-import=boardgames`、`--hidden-import=boardgames.registry`、`--hidden-import=boardgames.shell`、`--hidden-import=boardgames.azul`、`--hidden-import=boardgames.azul.desktop`、`--hidden-import=boardgames.azul.web`、`--hidden-import=boardgames.azul._art`、`--hidden-import=boardgames.azul.sprites`。

- [ ] **Step 1: 追加 hidden-import**（`build.py` 的 `COMMON_HIDDEN` 列表）

- [ ] **Step 2: 全相关测试**

Run:
```
python -m pytest tests/test_game_packages.py tests/test_azul_package_assets.py tests/test_web_boardgame_assets.py tests/test_boardgame_asset_img.py tests/test_boardgame_assets.py tests/test_flagship_gui.py tests/test_gemcity_purchase.py tests/test_theme.py -q
```
Expected: 无新增 FAIL。

- [ ] **Step 3: JS 语法探针**

Run: `node tests/ux_visual_chat_probe.cjs`
Expected: `full_script_syntax:true`

- [ ] **Step 4: 双 EXE 打包**

Run: `python build.py`
Expected: `dist/server.exe`、`dist/client.exe` 生成成功。

- [ ] **Step 5: Commit**

```bash
git add build.py
git commit -m "build: bundle boardgames presentation packages into both EXEs"
```

---

## Self-Review

**1. Spec 覆盖**
- §4 目录与包结构 → Task 1/4/5/6。
- §5 展示包契约 → Task 1。
- §6 共用外壳 → Task 6（`shell.py`）。
- §7 素材管线 → Task 4 + Task 3（合并）。
- §8 桌面接线 → Task 2；网页接线 → Task 3 + Task 5。
- §9 测试策略 → Task 1/3/4/6/7。
- §10 Azul 版面规格 → Task 4（素材）+ Task 6（桌面）+ Task 5（网页）。
- 「Azul 迁后删旧实现」→ Task 6 Step 5、Task 5 Step 3。
- 其余 46 款零回归 → Task 2/6/7 的回归步骤。

**2. 占位符扫描**：无 `TODO/TBD`；每个代码步骤均给出可执行内容或精确键名/色值/尺寸。

**3. 类型一致性**
- `GamePackage` 字段名在 Task 1/5 一致；`_bg_assets_all`/`_pkg_painter`/`_PKG_PAINTERS` 命名在 Task 2/3 一致。
- 素材键名在 Task 4（生成）、Task 5（web 引用 + `_BG_ASSET_KEYS`）、Task 6（desktop 引用）三处一致。
- 墙「应有色」公式 `COLORS[(c - r) % 5]` 与引擎 `_wall_col(ci, row) = (ci + row) % 5` 等价（同一拉丁方）。

**4. 已知取舍（记录在案）**
- 规则层仍在 `games_pkg/`（包内转发）；`web.py` 模板架构未重写（仅注入点）。
- 共享 `_art_boardgame.py` 的旧 `azul_*` 键成为死键，本轮不清理（避免动到 `test_boardgame_assets.py` 的既有断言），留作后续。
