# Boardgame Modern Flat Azulejo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `azul`/`gemcity` 两个旗舰桌游的对局画面改造为「现代扁平 · 阿兹勒赫纹样」风，并现代化桌游相关窗口外壳；桌面端（Tkinter）与网页端（`web.py`）同时做，复用同一套位图素材。

**Architecture:** 三层素材架构复用既有链路：`_gen_boardgame.py`（Pillow 程序化生成，开发期运行）→ `assets/boardgame/*.png` + `_art_boardgame.py`（base64 data-URI 内嵌，`ASSETS` 字典）→ 消费层（桌面 `client_gameui.py` 的 `_asset_*` helpers / 网页 `web.py` 的 `@@UX_BG_ASSETS@@` 注入）。子系统互相独立、可分步交付：A（对局画面）→ B（对局窗外壳）→ C（网页版，依赖 A 素材就绪）。

**Tech Stack:** Python 3 / Tkinter / Pillow（`PIL.Image`、`ImageTk`）/ PyInstaller（`build.py`）；网页端为 Python 单文件内联模板（无框架，原生 JS + CSS）。

**Spec:** `docs/superpowers/specs/2026-10-13-boardgame-modern-flat-azulejo-design.md`（已批准）

## Global Constraints

- 不伪造完成；证据保护（不覆盖历史截图/审查证据）。
- 不改既有 FAIL 判定/断言/跳过；验证用合成资料、loopback、私有桌面。
- **不改** `ui_design.design_tokens()` golden digest（必须保持 `a137658af6f3f9899c2106a0e6020c1b1e6d2569bab462488bb7c42dc0eb4078`）。
- **不删** `_GAME_ICON` 既有键；**不破坏** `icon_svg` 字节兼容；**不改** `build.py`；**不改** 主聊天窗皮肤（桌面 `ChatWindow` 主体 + `web.py` 主聊天区 CSS/token）。
- 假画布桩下（`_real_cv(cv)` 为 False）**绝不调用** `ImageTk.PhotoImage(master=cv)`。
- 全部素材 **Pillow 程序化原创**；仅对标 BGA《Azul》**风格方向**，不复制任何素材/坐标/色彩采样。
- verify 目标为「**无新增 FAIL**」（pre-existing FAIL 不计）；`python build.py` 双 EXE 编译通过。
- **未经用户明确要求不 commit / push。** 本计划中标注的 `commit` 步骤仅在用户批准提交后才执行。
- 颜色语义单源：`client_gameui.THEME["azul"]` 的 `r/w/b/y/k`、`ui_design.RESOURCE_ICONS` 的 `o/d/r/e/s/g`（键名不可改）。

---

## Task 1: A · 素材层重绘/新增 + 生成器重生成

**Files:**
- Modify: `_gen_boardgame.py`（新增 `_star_pts`/`make_azulejo`/`make_azul_board`/`make_azul_score_track`；重绘 `make_azul_bowl`/`make_azul_tile`/`make_gem`/`make_card_frame`/`make_panel`；`build_all()` 增 3 键）
- Regenerate: `assets/boardgame/*.png`、`_art_boardgame.py`
- Test: `tests/test_boardgame_assets.py`（扩展 `_EXPECTED_WH` + 计数断言 + docstring）

**Interfaces:**
- Consumes: 既有 `_begin/_end/_mix/_star_pts`(新增)/`SS=4`/`_AZUL`/`_GEM`。
- Produces: `ASSETS` 新增键 `azulejo`(256×256)/`azul_board`(96×96)/`azul_score_track`(96×48)；全部值为完整 data-URI 字符串 `'data:image/png;base64,...'`；键总数 26 → **29**。

- [ ] **Step 1: 写失败测试**：编辑 `tests/test_boardgame_assets.py`
  - `_EXPECTED_WH` 追加：`"azulejo": (256, 256)`、`"azul_board": (96, 96)`、`"azul_score_track": (96, 48)`。
  - 将 `test_assets_module_exposes_exactly_expected_keys` 的 `assert len(_BG_ASSETS) == 26` 改为 `== 29`。
  - 更新模块 docstring 中「26 个键」为「29 个键」。
- [ ] **Step 2: 跑测试确认失败**：
  ```
  python -m pytest tests/test_boardgame_assets.py -q
  ```
  Expected: FAIL（集合少了 `azulejo`/`azul_board`/`azul_score_track`，计数 26 != 29）。
- [ ] **Step 3: 改 `_gen_boardgame.py`**
  - 新增 `_star_pts(cx, cy, r_out, r_in, n=8, rot=-math.pi/2)`：`for i in range(2*n): rr = r_out if i % 2 == 0 else r_in; a = rot + i*math.pi/n`，返回 `2n` 个**未缩放**顶点（调用方逐点 `R()`）。
  - 新增常量（模块级）：`_AZULEJO_BG="#F4F8FB"`、`_AZULEJO_BLUE="#3E7CB1"`、`_AZULEJO_DEEP="#2B5E8C"`、`_AZULEJO_GRID="#6FA8CE"`、`_AZULEJO_PETAL="#DCEAF4"`。
  - 新增 `make_azulejo(size=256)`：`P=size//4`，4×4 单元格；每格中心 `(i+0.5)*P,(j+0.5)*P`；先四瓣花（4 个重叠椭圆，`petal_r=0.20*P`，偏移 `0.18*P`，fill `_AZULEJO_PETAL`）→ 八角星（`_star_pts(cx, cy, P*0.30, P*0.13, 8)`，fill `_AZULEJO_BLUE`）→ 星芯（`r=0.07*P`，fill `_AZULEJO_DEEP`）；底 `_AZULEJO_BG`；网格细线用左/上对齐矩形 `for i in range(4): q=i*P; dr.rectangle((R(q),0,R(q)+wl,R(size)))` + 对称横向，`wl=max(1,int(1.0*s))`，色 `_AZULEJO_GRID`；最大外扩半径 ≈`0.38*P=24.3 < P/2=32` → 天然无缝。
  - 新增 `make_azul_board(size=96, border=14)`：浅底 `#EAF2F7` + 外描边 `#8FB6CE` + 内白描边 `#FBFDFE`，大圆角（`radius=R(border)`）。
  - 新增 `make_azul_score_track(w=96, h=48, border=14)`：深蓝底 `#2E4A63` + 外描边 `#101E2C` + 内描边 `#4A7096`，大圆角。
  - 重绘 `make_azul_bowl(size=128, seed=99)`（扁平）：外描边底圆 `#101E2C`（`(3,3,size-3,size-3)`）→ 16 个浅色小圆瓣滚边（fill `#EAF2F7`，`rr=size*0.075`，中心环 `c-6-rr`）→ 主体深蓝圆盘 `#2E4A63`（`(6,6,size-6,size-6)`）→ 内圈浅环 `#8FB6CE`（`0.20-0.80`，`width=4*s`）→ 内膛更深 `#1E3346`（`0.26-0.74`）→ 克制高光 alpha `46`（删除原 40 斑点写实处理）。
  - 重绘 `make_azul_tile(hexstr, size=44)`：保留圆角 + 内外描边逻辑，**降低**高光层 alpha（浅色 `120→64`、深色 `72→40`）使更扁平。
  - 重绘 `make_gem(hexstr, size=40)`：保留六边形结构，**减少**刻面线数量/提高高光对比（扁平高饱和），白底（`#eef2f4`）高光 alpha 保持最高。
  - 重绘 `make_card_frame(w=96, h=136)`：更大圆角 `radius=R(14)`，更干净留白（sheen 范围收窄）。
  - 重绘 `make_panel(size=60, border=12)`：**改浅底** `#F4F8FB` + 描边 `#DCE6E2`（与对局壳浅底一致）。
  - `build_all()` 在 dict 中追加 `"azulejo": make_azulejo()`、`"azul_board": make_azul_board()`、`"azul_score_track": make_azul_score_track()`。
- [ ] **Step 4: 重生成素材**：
  ```
  python _gen_boardgame.py
  ```
  Expected: 打印 `generated 29 assets -> assets/boardgame/ and _art_boardgame.py`；`assets/boardgame/` 出现 3 个新 PNG；`_art_boardgame.py` 的 `ASSETS` 含 29 键。
- [ ] **Step 5: 跑测试确认通过**：
  ```
  python -m pytest tests/test_boardgame_assets.py -q
  ```
  Expected: PASS（3 个测试全绿）。
- [ ] **Step 6: 回归**：
  ```
  python -m pytest tests/test_boardgame_asset_img.py -q
  ```
  Expected: PASS（素材 helper 对新键泛型可用，无回归）。
- [ ] **Step 7: commit**（待用户批准）：
  ```
  git add _gen_boardgame.py _art_boardgame.py assets/boardgame tests/test_boardgame_assets.py
  git commit -m "feat(boardgame): add azulejo/board/score-track assets and flatten component art"
  ```

---

## Task 2: A · `_p_azul` 重排（azulejo 底 + 扁平碗 + 玩家板 + 计分轨）

**Files:**
- Modify: `client_gameui.py`（`_p_azul`，L5226-5333）
- Test: `tests/test_boardgame_asset_img.py`（新增真 Tk 测试）

**Interfaces:**
- Consumes: Task 1 产出的 `azulejo`/`azul_board`/`azul_score_track`/`azul_bowl`/`azul_tile_*`；既有 `_asset_bg/_asset_at/_asset_nine_at/_asset_nine`；既有回退 `_rrect/_stone/create_oval/create_rectangle`。
- Produces: `_p_azul(cv, st, w, h, ...)` 渲染后 `cv._asset_img_cache` 含 `("azulejo", None)`、`cv._asset_nine_cache` 含 `azul_board`/`azul_score_track` 前缀键（真 Tk 下）。

- [ ] **Step 1: 写失败测试**：在 `tests/test_boardgame_asset_img.py` 末尾新增
  ```python
  def test_azul_painter_consumes_azulejo_and_boards():
      if cu._BG_ASSETS is None or cu._PILImage is None or cu._PILImageTk is None:
          pytest.skip("Pillow/Tk assets unavailable")
      root = tk.Tk()
      try:
          cv = tk.Canvas(root, width=800, height=560)
          cv.pack()
          root.update_idletasks()
          ui = {}
          cu.render(cv, "azul", _azul_state(), 7, lambda uid: f"P{uid}",
                    lambda m: None, lambda: None, ui, None,
                    cv.winfo_width(), cv.winfo_height())
          assert ("azulejo", None) in getattr(cv, "_asset_img_cache", {})
          nine_keys = {k[0] for k in getattr(cv, "_asset_nine_cache", {})}
          assert "azul_board" in nine_keys
          assert "azul_score_track" in nine_keys
      finally:
          try: root.destroy()
          except Exception: pass
  ```
- [ ] **Step 2: 跑测试确认失败**：
  ```
  python -m pytest tests/test_boardgame_asset_img.py::test_azul_painter_consumes_azulejo_and_boards -q
  ```
  Expected: FAIL（当前 `_p_azul` 用 `felt`，缓存无 `azulejo`/`azul_board`/`azul_score_track`）。
- [ ] **Step 3: 改 `_p_azul`**
  - 底：`_asset_bg(cv,"felt",0,47,w,h)` → `_asset_bg(cv,"azulejo",0,47,w,h)`（回退保留）。
  - 工厂碗：`_asset_at(cv,"azul_bowl",...)` 保持；碗内花砖 `azul_tile_{c}` 保持；新增玩家板衬底 `_asset_nine_at(cv,"azul_board", x, base_y, board_w, avh, border=14)`（回退 `_rrect` 浅底）。
  - 右侧计分轨：新增 `_asset_nine_at(cv,"azul_score_track", w-?, base_y, track_w, avh, border=14)`（回退 `_rrect` 深蓝底）。
  - **浅底改色**：原面向暗色毡布的文字/空槽改为 mist 深字/浅槽——`"花纹行"`/`"墙（上墙落瓦）"` 标题 `#cfe0d8` → `#213336`；`"碗{i}"` `#9fbfbf` → `#5F706A`；`"中央"` `#c0a0a0` → `#5F706A`；地板/分数 `#ffd75e` → `#16796C`；空槽 `#263a3a`/`#223236` → 浅槽 `#E5F3EE`（描边 `#8FB6CE`）。
- [ ] **Step 4: 跑测试确认通过**：
  ```
  python -m pytest tests/test_boardgame_asset_img.py -q
  ```
  Expected: PASS（新旧测试全绿）。
- [ ] **Step 5: commit**（待用户批准）：
  ```
  git add client_gameui.py tests/test_boardgame_asset_img.py
  git commit -m "feat(boardgame): reskin azul painter with azulejo ground and flat board"
  ```

---

## Task 3: A · `_p_gemcity` 同步（azulejo 底 + 扁平卡/宝石）

**Files:**
- Modify: `client_gameui.py`（`_p_gemcity`，L4944-5067）
- Test: `tests/test_boardgame_asset_img.py`（新增真 Tk 测试）

**Interfaces:**
- Consumes: Task 1 的 `azulejo`/`gem_*`/`panel`；既有 `_asset_bg/_asset_at/_asset_nine_at`；回退 `_rrect/_res_img/create_oval/create_rectangle`。
- Produces: `_p_gemcity` 渲染后 `cv._asset_img_cache` 含 `("azulejo", None)` 且**不含** `("felt", None)`。

- [ ] **Step 1: 写失败测试**：新增
  ```python
  def test_gemcity_painter_switches_felt_to_azulejo():
      if cu._BG_ASSETS is None or cu._PILImage is None or cu._PILImageTk is None:
          pytest.skip("Pillow/Tk assets unavailable")
      root = tk.Tk()
      try:
          cv = tk.Canvas(root, width=800, height=560); cv.pack(); root.update_idletasks()
          ui = {}
          cu.render(cv, "gemcity", _gemcity_state(), 7, lambda uid: f"P{uid}",
                    lambda m: None, lambda: None, ui, None,
                    cv.winfo_width(), cv.winfo_height())
          cache = getattr(cv, "_asset_img_cache", {})
          assert ("azulejo", None) in cache
          assert ("felt", None) not in cache
      finally:
          try: root.destroy()
          except Exception: pass
  ```
- [ ] **Step 2: 跑测试确认失败**：
  ```
  python -m pytest tests/test_boardgame_asset_img.py::test_gemcity_painter_switches_felt_to_azulejo -q
  ```
  Expected: FAIL（当前用 `felt`）。
- [ ] **Step 3: 改 `_p_gemcity`**
  - 底：`_asset_bg(cv,"felt",0,47,w,h)` → `_asset_bg(cv,"azulejo",0,47,w,h)`。
  - 市场卡：`_asset_nine_at(cv,"panel",...)` 保持（Task 1 已改浅底）；回退 `_rrect` 浅底。
  - 宝石：`_asset_at(cv,f"gem_{dk}",...)`/`_asset_at(cv,f"gem_{k}",...)` 保持。
  - **浅底改色**：市场标题 `#e8e0d0`/`#e8e8e8`/`#cfe0d8` → mist 深字 `#213336`/`#5F706A`；`+pts` `#ffd75e` → `#16796C`；玩家底 `#3a2f52` → 浅底 `#E5F3EE`（描边 `#8FB6CE`）；`🏆`/`贵宾` `#ffd75e` → `#16796C`；`nick` `#fff` → `#213336`。
- [ ] **Step 4: 跑测试确认通过**：
  ```
  python -m pytest tests/test_boardgame_asset_img.py -q
  ```
  Expected: PASS。
- [ ] **Step 5: commit**（待用户批准）：
  ```
  git add client_gameui.py tests/test_boardgame_asset_img.py
  git commit -m "feat(boardgame): reskin gemcity painter on azulejo ground"
  ```

---

## Task 4: B · `theme.game_shell_pal(skin)`

**Files:**
- Modify: `theme.py`（在 `_is_dark` 之后，约 L854 后新增）
- Test: 新建 `tests/test_game_shell_pal.py`

**Interfaces:**
- Consumes: 既有 `dialog_pal(skin)`、`_is_dark(hex)`。
- Produces: `game_shell_pal(skin: dict) -> dict`，键集 **⊇** `dialog_pal(skin)`（可直接替换 `self._pal`）；额外含 `card_bg`；不含 `titlebar_h`（标题栏高度回退 `theme.BASE["titlebar_h"]`）。

- [ ] **Step 1: 写失败测试**：新建 `tests/test_game_shell_pal.py`
  ```python
  import theme

  def _skins():
      return [theme.get_skin("mist"), theme.get_skin("mist_dark")]

  def test_keyset_superset_of_dialog_pal():
      for sk in _skins():
          gp = theme.game_shell_pal(sk)
          dp = theme.dialog_pal(sk)
          assert set(gp) >= set(dp)
          assert "card_bg" in gp

  def test_light_branch_tokens():
      gp = theme.game_shell_pal(theme.get_skin("mist"))
      assert gp["accent"].upper() == "#16796C"
      assert gp["accent_hover"].upper() == "#11685C"
      assert gp["soft_bg"].upper() == "#EEF4F2"
      assert gp["border"].upper() == "#DCE6E2"

  def test_dark_branch_tokens():
      gp = theme.game_shell_pal(theme.get_skin("mist_dark"))
      assert gp["accent"].upper() == "#86CDB3"
      assert gp["accent_hover"].upper() == "#9BDAC4"
      assert gp["soft_bg"].upper() == "#2B3C33"

  def test_does_not_mutate_dialog_pal():
      sk = theme.get_skin("mist")
      before = dict(theme.dialog_pal(sk))
      theme.game_shell_pal(sk)
      assert theme.dialog_pal(sk) == before
  ```
- [ ] **Step 2: 跑测试确认失败**：
  ```
  python -m pytest tests/test_game_shell_pal.py -q
  ```
  Expected: FAIL（`AttributeError: module 'theme' has no attribute 'game_shell_pal'`）。
- [ ] **Step 3: 改 `theme.py`**
  ```python
  def game_shell_pal(skin):
      """对局窗专用调色：在 dialog_pal 之上覆盖 mist-flat token 派生。"""
      pal = dict(dialog_pal(skin))
      panel = skin.get("panel_bg", "#ffffff") if skin else "#ffffff"
      if _is_dark(panel):
          pal.update({
              "accent": "#86CDB3", "accent_fg": "#15251F", "accent_hover": "#9BDAC4",
              "soft_bg": "#2B3C33", "border": "#395246",
              "card": "#1E3028", "card_bg": "#1E3028",
          })
      else:
          pal.update({
              "accent": "#16796C", "accent_fg": "#FFFFFF", "accent_hover": "#11685C",
              "soft_bg": "#EEF4F2", "border": "#DCE6E2",
              "card": "#FFFFFF", "card_bg": "#FFFFFF",
          })
      return pal
  ```
- [ ] **Step 4: 跑测试确认通过**：
  ```
  python -m pytest tests/test_game_shell_pal.py -q
  ```
  Expected: PASS。
- [ ] **Step 5: 回归**：
  ```
  python -m pytest tests/test_theme.py -q
  ```
  Expected: PASS（`game_shell_pal` 非 SKINS 条目，不影响 `test_all_skins_have_all_tokens`）。
- [ ] **Step 6: commit**（待用户批准）：
  ```
  git add theme.py tests/test_game_shell_pal.py
  git commit -m "feat(theme): add game_shell_pal derived palette for boardgame shell"
  ```

---

## Task 5: B · 桌面注入（`game_shell_pal` 接入 `GameWindow` + 标题栏/工具栏）

**Files:**
- Modify: `client.py`（import 块 L44-51；`open_game` L11116-11121；`_build_apple_bar` L12226-12259；工具栏 L12455-12478）
- Test: 新建 `tests/test_game_shell_wiring.py`

**Interfaces:**
- Consumes: `theme.game_shell_pal`；既有 `client._DEFAULT_PAL`、`GameWindow(app, pal=...)`。
- Produces: `GameWindow._build_apple_bar` 读 `self._pal`（不再直读全局皮肤）；标题栏 `bg == pal["win"]`、高度 `int(bar["height"]) == theme.BASE["titlebar_h"]`（=28）。

- [ ] **Step 1: 写失败测试**：新建 `tests/test_game_shell_wiring.py`
  ```python
  import types
  from unittest import mock
  import pytest
  import client as client_module
  import theme

  def _fake_app(root):
      return types.SimpleNamespace(
          root=root, core=None,
          _dp=client_module._DEFAULT_PAL,
          _frameless=False,
          _skin={"titlebar_bg": "#123456", "titlebar_h": 99,
                 "panel_bg": "#ffffff", "fg": "#000000", "sub": "#666666"},
          _camo_title=lambda: "synthetic",
      )

  def test_apple_bar_uses_injected_pal():
      tk = pytest.importorskip("tkinter")
      try:
          root = tk.Tk()
      except tk.TclError:
          pytest.skip("no display")
      try:
          root.withdraw()
          app = _fake_app(root)
          pal = theme.game_shell_pal(theme.get_skin("mist"))
          win = client_module.GameWindow(app, pal=pal)
          # 触发标题栏构建（frameless 路径）
          win._build_apple_bar(win._win if hasattr(win, "_win") else win.win) \
              if False else None
          bar = _force_apple_bar(win)
          assert bar["bg"].upper() == pal["win"].upper()
          assert int(bar["height"]) == int(theme.BASE["titlebar_h"])
      finally:
          try: root.destroy()
          except Exception: pass
  ```
  > 说明：实现者需按 `GameWindow` 实际属性名（`_win`/`win`）与 `_build` 流程触发标题栏构建；若内部字段名与上述假设不同，**以真实代码为准调整测试**，但断言保持不变：`bar["bg"]` 取注入 pal 的 `win`（非 fake skin 的 `#123456`）、高度取 `theme.BASE["titlebar_h"]`（非 fake skin 的 99）。
- [ ] **Step 2: 跑测试确认失败**：
  ```
  python -m pytest tests/test_game_shell_wiring.py -q
  ```
  Expected: FAIL（标题栏当前直读全局皮肤 → `bg==#123456`、`height==99`）。
- [ ] **Step 3: 改 `client.py`**
  - import 块：`from theme import (..., dialog_pal, game_shell_pal, ...)`（在 `dialog_pal,` 后追加 `game_shell_pal,`）。
  - `open_game` L11120：`GameWindow(self, pal=self._dp)` → `GameWindow(self, pal=game_shell_pal(getattr(self, "_skin", None) or get_skin(None)))`。
  - `_build_apple_bar`：
    ```python
    pal = self._pal
    bg = pal.get("titlebar_bg") or pal.get("win", "#ececee")
    fg = pal.get("titlebar_fg") or pal.get("fg", "#1d1d1f")
    btn_fg = pal.get("titlebar_btn") or pal.get("sub", "#86868b")
    hh = int(pal.get("titlebar_h") or BASE["titlebar_h"])
    ```
    （删除 `sk = getattr(self.app,"_skin",None) or get_skin(None)` 与直读 `sk.get("titlebar_*")`；红黄绿圆点交互语义、标题文本、右侧「聊」钮保持不变。）
  - 工具栏 L12455-12478：改为分段控件样式——`规则` 次级（`bg=pal["soft_bg"]`,`fg=pal["fg"]`）、`棋盘` accent 主（`bg=pal["accent"]`,`fg=pal["accent_fg"]`）、`专注窗` accent 次（`bg=pal["soft_bg"]`,`fg=pal["fg"]`），统一 `relief="flat"`、`activebackground=pal["accent_hover"]`；`act_btns`/`act_hint` 背景改 `pal["win"]`。
- [ ] **Step 4: 跑测试确认通过**：
  ```
  python -m pytest tests/test_game_shell_wiring.py -q
  ```
  Expected: PASS。
- [ ] **Step 5: 回归**：
  ```
  python -m pytest tests/test_flagship_gui.py -q
  ```
  Expected: PASS（`GameWindow(app, pal=_DEFAULT_PAL)` 契约不变）。
- [ ] **Step 6: commit**（待用户批准）：
  ```
  git add client.py tests/test_game_shell_wiring.py
  git commit -m "feat(client): inject game_shell_pal into boardgame windows"
  ```

> **注意**：`BoardFocusWindow`（L13803）无 pal 时继承 `host._pal`，**无需改动**；`MiniBar`（L13987）属主聊天窗隐藏迷你条，**不注入**。

---

## Task 6: C · `web.py` 注入同源位图（`@@UX_BG_ASSETS@@`）

**Files:**
- Modify: `web.py`（import L36-44；`_bg_assets_subset()` 新增；`_SERVED_PAGE` L51-73；模板 JS L3882 后）
- Test: 新建 `tests/test_web_boardgame_assets.py`

**Interfaces:**
- Consumes: `_art_boardgame.ASSETS`（完整 data-URI）。
- Produces: `web._bg_assets_subset() -> dict[str,str]`（仅对局子集）；`_SERVED_PAGE()` 输出中 `@@UX_BG_ASSETS@@` 被替换为 JS 字符串字面量；模板新增 `const BG=JSON.parse("<子集>");`。

- [ ] **Step 1: 写失败测试**：新建 `tests/test_web_boardgame_assets.py`
  ```python
  import json, re
  import web

  def _extract_bg_literal(html):
      m = re.search(r'const BG=JSON\.parse\("((?:[^"\\]|\\.)*)"\);', html)
      assert m, "BG literal not found"
      return json.loads(json.loads('"' + m.group(1) + '"'))

  def test_served_page_has_no_placeholder_and_bg_subset():
      html = web._SERVED_PAGE().decode("utf-8")
      assert "@@UX_BG_ASSETS@@" not in html
      bg = _extract_bg_literal(html)
      for k in ("azulejo", "azul_bowl", "azul_tile_r", "gem_o", "azul_board", "azul_score_track", "panel"):
          assert k in bg, k
          assert bg[k].startswith("data:image/png;base64,")

  def test_missing_assets_module_degrades_to_empty(monkeypatch):
      monkeypatch.setattr(web, "_bg_assets", None)
      html = web._SERVED_PAGE().decode("utf-8")
      assert "@@UX_BG_ASSETS@@" not in html
      assert _extract_bg_literal(html) == {}
  ```
- [ ] **Step 2: 跑测试确认失败**：
  ```
  python -m pytest tests/test_web_boardgame_assets.py -q
  ```
  Expected: FAIL（占位符残留 / `BG` 未定义）。
- [ ] **Step 3: 改 `web.py`**
  - import 段（L44 后）：`try: import _art_boardgame as _bg_assets except Exception: _bg_assets = None`。
  - 新增（`_SERVED_PAGE` 前）：
    ```python
    _BG_ASSET_KEYS = ("azulejo", "azul_board", "azul_score_track", "azul_bowl",
                      "azul_tile_r", "azul_tile_w", "azul_tile_b", "azul_tile_y", "azul_tile_k",
                      "gem_o", "gem_d", "gem_r", "gem_e", "gem_s", "gem_g",
                      "card_frame", "panel")

    def _bg_assets_subset():
        src = getattr(_bg_assets, "ASSETS", None) if _bg_assets is not None else None
        if not src:
            return {}
        return {k: src[k] for k in _BG_ASSET_KEYS if k in src}
    ```
  - `_SERVED_PAGE` L72 后：`page = page.replace('@@UX_BG_ASSETS@@', _js_json_literal(_bg_assets_subset()))`。
  - 模板 JS（L3882 后）：`const BG=JSON.parse("@@UX_BG_ASSETS@@");`。
- [ ] **Step 4: 跑测试确认通过**：
  ```
  python -m pytest tests/test_web_boardgame_assets.py -q
  ```
  Expected: PASS。
- [ ] **Step 5: JS 语法探针回归**：
  ```
  node tests/ux_visual_chat_probe.cjs
  ```
  Expected: 通过（新增 `const BG=...` 语法合法）。
- [ ] **Step 6: commit**（待用户批准）：
  ```
  git add web.py tests/test_web_boardgame_assets.py
  git commit -m "feat(web): inject boardgame bitmap assets subset via @@UX_BG_ASSETS@@"
  ```

---

## Task 7: C · `web.py` 对局面板 CSS + `GRENDER.azul`/`gemcity` 重写

**Files:**
- Modify: `web.py`（面板 CSS L504-527；`.vtile` L553-558；JS `bgImg` 于 L3882 后；`GRENDER.azul` L5066-5106；`GRENDER.gemcity` L4951-5010）
- Test: `tests/test_web_boardgame_assets.py`（追加重写标记断言）

**Interfaces:**
- Consumes: Task 6 的 `BG`、`_bg_assets_subset()`。
- Produces: 面板 CSS 新增 `body.hasBgArt #gpanel .card{...}`；JS 新增 `function bgImg(key, extra){...}`；`GRENDER.azul`/`GRENDER.gemcity` 使用 `bgImg("azul_bowl"|"azul_board"|"azul_score_track"|"panel")` 与 `BG["gem_"…]`/`BG["azul_tile_"…]`；**动作契约不变**（azul `take/place/floor`；gemcity `take/take2/buy/reserve/buy_res`）。

- [ ] **Step 1: 写失败测试**：追加到 `tests/test_web_boardgame_assets.py`
  ```python
  def test_panel_css_and_renderers_use_bitmaps():
      html = web._SERVED_PAGE().decode("utf-8")
      assert "body.hasBgArt #gpanel .card" in html
      assert "function bgImg(" in html
      for mark in ('bgImg("azul_bowl")', 'bgImg("azul_board")',
                   'bgImg("azul_score_track")', 'bgImg("panel")'):
          assert mark in html, mark
      assert 'BG["gem_' in html
      assert 'BG["azul_tile_' in html
      # 动作契约不回归
      assert '{op:"take"' in html and '{op:"place"' in html and '{op:"floor"' in html
      assert 'op:"take2"' in html and 'op:"buy"' in html and 'op:"reserve"' in html
  ```
- [ ] **Step 2: 跑测试确认失败**：
  ```
  python -m pytest tests/test_web_boardgame_assets.py::test_panel_css_and_renderers_use_bitmaps -q
  ```
  Expected: FAIL（无 `hasBgArt` / `bgImg` / `BG[...]` 标记）。
- [ ] **Step 3: 改 `web.py`**
  - CSS L506 后插入：
    ```css
    body.hasBgArt #gpanel .card{background-image:linear-gradient(rgba(255,255,255,.90),rgba(255,255,255,.90)),var(--azulejo);background-size:auto,256px 256px;background-repeat:no-repeat,repeat;background-position:center,top left}
    ```
  - `.gbtn`/`.gbtn.go` 扁平化（圆角对齐 mist `--r1`/`--r2`；选中态 accent 填充；禁用态语义不变）。
  - JS L3882 后新增：
    ```js
    function bgImg(key,extra){const u=BG[key];return u?("background:url('"+u+"') center/100% 100% no-repeat;border:none;"+(extra||"")):"";}
    ```
  - boot IIFE（`BG` 就绪后，判 `typeof document!=="undefined"` 与 `document.body`，失败静默）：若 `BG["azulejo"]` 存在则 `document.documentElement.style.setProperty("--azulejo","url('"+BG["azulejo"]+"')")` 且 `document.body.classList.add("hasBgArt")`。
  - `GRENDER.azul` 重写：`azTile(t)` 改 `<img src="BG["azul_tile_"+t.c]">`（回退原 `.vtile`）；工厂碗 `bgImg("azul_bowl")`；玩家板 `bgImg("azul_board")`；计分轨 `bgImg("azul_score_track")`。**动作/选择控件契约不变**.
  - `GRENDER.gemcity` 重写：`gmI(c,sz)` 改 `BG["gem_"+c]` 位图 `<img>`（回退 `resIcon`）；市场卡面 `bgImg("panel")`。**动作契约不变**。
- [ ] **Step 4: 跑测试确认通过**：
  ```
  python -m pytest tests/test_web_boardgame_assets.py -q
  ```
  Expected: PASS。
- [ ] **Step 5: JS 语法探针 + 视觉回归**：
  ```
  node tests/ux_visual_chat_probe.cjs
  python -m pytest tests/test_ux_visual_chat_regressions.py -q
  ```
  Expected: 探针通过；回归测试无**新增** FAIL（pre-existing FAIL 不计）。
- [ ] **Step 6: commit**（待用户批准）：
  ```
  git add web.py tests/test_web_boardgame_assets.py
  git commit -m "feat(web): modern flat azulejo panel shell and bitmap renderers"
  ```

---

## Self-Review

**1. Spec 覆盖检查**
- §5.1 素材新增（`azulejo`/`azul_board`/`azul_score_track`）→ Task 1。
- §5.1 素材重绘（`azul_bowl`/`azul_tile_*`/`gem_*`/`card_frame`/`panel`）→ Task 1。
- §5.2 `_p_azul` 重排 → Task 2；`_p_gemcity` 同步 → Task 3。
- §5.3 headless 零回归（`_real_cv` 守卫、缺 key 回退）→ Task 1/2/3 的回归步骤 + 既有测试保持。
- §4 子系统 B（`game_shell_pal` + 注入 + 标题栏/工具栏）→ Task 4/5。
- §6 子系统 C（注入同源素材 + 面板 CSS + `GRENDER` 重写）→ Task 6/7。
- §7 测试策略（扩展 `test_boardgame_assets.py`/`test_boardgame_asset_img.py`；新增 `test_game_shell_pal.py`/`test_web_boardgame_assets.py`）→ Task 1/2/3/4/6/7；`test_game_shell_wiring.py` 为 B 注入补充。
- §8 分期（一期 A + azul；二期 gemcity；三期 B；四期 C）→ Task 1-2 / Task 3 / Task 4-5 / Task 6-7。
- §9 红线 → Global Constraints。
- **已知偏差（有意）**：spec §5.2 提 gemcity 用 `card_frame`，但 gemcity 市场卡为宽卡，几何上 `panel` 9-slice 更合适；`card_frame` 仍在 Task 1 现代化，但**无画师消费**（`client_gameui.py` 经 Grep 确认无 `card_frame` 消费点）。此偏差不改变外观目标（扁平现代），仅选择更合适的组件。

**2. 占位符扫描**：无 `TODO`/`TBD`/`...`/「稍后补」；所有步骤含可执行命令或具体代码/键名/色值。

**3. 类型一致性检查**
- `_bg_assets_subset()` 返回 `dict[str,str]`（值=完整 data-URI）→ Task 6/7 一致。
- `game_shell_pal` 返回键集 ⊇ `dialog_pal` → Task 4 断言、Task 5 注入替换 `self._pal` 一致。
- `_asset_*` 缓存键：`_asset_img_cache[(key,size)]`、`_asset_nine_cache[(key,w,h,border)]` → Task 2/3 断言用 `k[0]` 取 key 一致。
- `bar["height"]`/`bar["bg"]` 与 `theme.BASE["titlebar_h"]` → Task 5 断言一致。

**4. 风险提示**
- Task 5 测试中的 `GameWindow` 内部字段名（`_win`/`win`）以真实代码为准，断言不变。
- Task 5 将桌游窗标题栏高度由 32（mist 皮肤）变为 28（`BASE["titlebar_h"]`）——属对局壳紧凑化，**不影响主聊天窗**。
- Task 6/7 注入 JS 必须语法合法（`ux_visual_chat_probe.cjs` 会拦截语法错误）。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-10-13-boardgame-modern-flat-azulejo.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration. Requires sub-skill `superpowers:subagent-driven-development`.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review.

**Which approach?**
