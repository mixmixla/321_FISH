# 桌游现代化改造设计（现代扁平 · 阿兹勒赫纹样 + 对局窗口外壳）

- 日期：2026-10-13
- 状态：待用户评审（评审通过后进入 writing-plans）
- 关联权威清单：`docs/游戏UI与资源现代化-任务清单.md` 主题 C（视觉设计系统统一）、D（卡牌/棋盘矢量美术）、F（信息呈现与反馈）
- 参考：Board Game Arena《Azul》教程画面（用户提供截图）——**仅对标其"风格方向"，不复制任何素材**。
- 上一阶段（已完成）：`docs/superpowers/specs/2026-10-13-boardgame-art-upgrade-design.md`（组件库 + 主题素材包，已落地为 `_gen_boardgame.py` / `_art_boardgame.py` / `assets/boardgame/` 与 `_p_azul`/`_p_gemcity` 接入）。

## 1. 背景与目标

上一阶段让对局内用上了位图素材（木纹/毡布/陶瓷碗/釉面花砖），但整体观感仍是**写实暗色毡布**，与市面现代商业桌游（如 BGA Azul 的浅蓝白阿兹勒赫瓷砖 + 扁平高对比组件）差距明显。

**目标（本期）**
1. 把 `azul`、`gemcity` 两个旗舰的**对局画面**改为**现代扁平 · 阿兹勒赫纹样**风：浅蓝白花纹壁纸打底、扁平深蓝圆盘 + 波浪滚边、粉彩马赛克玩家板、圆角计分轨、扁平高对比花砖/宝石。
2. **现代化桌游相关窗口外壳**：对局窗口 / 专注窗的标题栏、工具栏、按钮、面板统一为现代扁平观感，与 mist 设计系统对齐。
3. **桌面端与网页端同时做**：网页版（`web.py`）对局画面与面板外壳同步现代化，**复用桌面同一套位图素材**（`_art_boardgame`）以 data-URI 注入，实现双端观感一致。

**非目标（本期不做）**
- 不改**主聊天窗**皮肤（`theme.py` 既有皮肤集、`ChatWindow` 主体外观不动；`web.py` 主聊天区 CSS/主题 token 不动）。
- 不改 `_DEFAULT_PAL`（app 兜底调色，影响面过大）；对局外壳改用**专用派生调色**（见 §4）。
- 不改 `build.py`；不改 `ui_design.design_tokens()` golden digest；不删 `_GAME_ICON` 既有键；不破坏 `icon_svg` 字节兼容。
- 其余 45 款对局画师**不在本期范围**（后续分批沿用同一套底盘与组件）。
- 不引入任何外部/网络素材或他人版权图。

## 2. 版权红线

BGA 的 Azul 美术、瓷砖花纹、图标、版式均受版权保护。本期**只对标风格方向**（配色气质、扁平化、圆角统一、阿兹勒赫几何母题的抽象），**全部位图由 Pillow 程序化原创生成**，几何纹样为通用八角星/四瓣花等公共装饰母题的自主绘制，不使用任何 BGA 具体图案、坐标或色彩采样。

## 3. 范围分解

| 子系统 | 主要文件 | 变更类型 |
|---|---|---|
| A 对局画面现代化（桌面） | `_gen_boardgame.py`（重绘/新增素材）、`_art_boardgame.py` + `assets/boardgame/*.png`（重生成）、`client_gameui.py`（`_p_azul`/`_p_gemcity` 重排） | 有界改造 |
| B 对局窗口外壳现代化（桌面） | `theme.py`（新增派生函数）、`client.py`（对局窗/专注窗注入专用配色） | 有界改造 |
| C 网页版对局现代化（web） | `web.py`（`_SERVED_PAGE` 注入同源位图 + 对局面板 CSS 现代化 + `GRENDER.azul`/`gemcity` 重写） | 有界改造 |

三子系统独立可测，可分步交付；C 复用 A 产出的同源位图素材（先做 A 再做 C）。

## 4. 子系统 B · 对局窗口外壳（先定清，避免误伤主窗）

### 现状
- `GameWindow`（`client.py` L12152）与 `BoardFocusWindow`（L13803）、`MiniBar`（L13987）的配色来自 `pal=self._dp`，而 `_dp = dialog_pal(self._skin)`（`theme.py` L803）。
- 标题栏 `_build_apple_bar`（L12228）**直接读全局皮肤** `theme.get_skin()` 的 `titlebar_*`。
- `dialog_pal` 被**所有弹窗共用**，直接改它会波及全应用对话框 → 不可取。

### 设计
1. 在 `theme.py` 新增 `game_shell_pal(skin) -> dict`：从 mist 系统派生**对局壳专用**配色（浅色面板近 `#F4F7F6`、accent 用 mist `#16796C`、扁平 hover、统一圆角相关的色阶），**只含对局窗需要的键**（沿用 `dialog_pal` 的键名以便直接替换 `self._pal`）。
2. `client.py`：`GameWindow.__init__` / `BoardFocusWindow` / `MiniBar` 构造时以 `game_shell_pal(self._skin)` 作为 `self._pal`（保持 `pal=` 注入契约，主窗与此无关）。
3. `_build_apple_bar` 改为**接收对局壳色**（不再直读全局皮肤）：标题栏扁平化；红黄绿圆点**保留原有交互语义**（拖动/最大化/收起位置与行为不变）；字号/间距按 mist 规范微调。
4. 工具栏（规则/棋盘/专注窗，L12455 起）改为**现代分段控件**样式：统一圆角观感、选中态 accent 填充，`规则` 用次级样式、`棋盘/专注窗` 用 accent 主/次区分。
5. 面板与嵌套容器背景统一取自对局壳调色，消除"深色毡布窗 + 浅色控件"的割裂。

### 影响面控制
- 仅注入到桌游相关窗口；主聊天窗与其余弹窗外观**不变**。
- 深色皮肤下 `game_shell_pal` 亦需给出深色分支（沿用 `_is_dark` 判定），保持"除聊天区都换肤"不回退。

## 5. 子系统 A · 对局画面现代化

### 5.1 素材层（改 `_gen_boardgame.py` → 重生成 `_art_boardgame.py` + `assets/boardgame/*.png`）

**新增**
| key | 尺寸 | 说明 |
|---|---|---|
| `azulejo` | 256×256（可平铺） | 浅蓝白阿兹勒赫壁纸：双色瓷砖 + 八角星/四瓣花几何纹，无缝平铺，用作对局底 |
| `azul_board` | 96×96（9-slice，border≈14） | 粉彩马赛克玩家板底（5 斜行 + 5×5 墙 + 地板槽的衬底） |
| `azul_score_track` | 96×48（9-slice） | 右侧圆角计分轨底板（深色圆角条 + 分格） |

**重绘（扁平化，去写实）**
| key | 变化 |
|---|---|
| `azul_bowl` | 陶瓷碗 → **扁平深蓝圆盘 + 浅色波浪(scallop)滚边 + 内圈浅环** |
| `azul_tile_r/w/b/y/k` | 更扁平干净的圆角瓦片，保留**克制**釉面高光 |
| `gem_o/d/r/e/s/g` | 扁平高饱和刻面微调，白底高对比 |
| `card_frame` / `panel` | 更现代的大圆角、更干净的留白 |

> 颜色键仍严格对齐既有语义单源：`ui_design.RESOURCE_ICONS` 的 `o/d/r/e/s/g` 与 `client_gameui.THEME["azul"]` 的 `r/w/b/y/k`。

### 5.2 画师层（改 `client_gameui.py`）

**`_p_azul`（L5226-5334）重排**：`azulejo` 平铺底 → 工厂**扁平圆盘**（`azul_bowl`）+ 花砖绕圈 → 中央池 → 玩家板（`azul_board` 衬底 + 花砖 5 斜行 + 5×5 墙 + 地板）→ 右侧 `azul_score_track` 计分轨 → 底部干净信息条。删除现在的暗色毡布底与写实碗观感。

**`_p_gemcity`（L≈4960-5060）同步**：桌面底复用 `azulejo`（保持双旗舰视觉统一）+ 扁平卡面（`card_frame`）+ 扁平宝石（`gem_*`）+ 圆角面板（`panel` 9-slice）。

### 5.3 零回归 / headless 安全（沿用既有契约，不得破坏）
- 一切位图经 `_asset_img`/`_asset_at`/`_asset_nine_at`/`_asset_bg` 消费；**缺 Pillow / 缺 key / 假画布桩**（`_real_cv(cv)` 为 False）→ 返回 `None`，画师**回退到既有矢量画法**。
- 假画布桩下**绝不调用** `ImageTk.PhotoImage(master=cv)`。
- `_real_cv(cv)` 时序契约不变（仅 `render()` 后为真）。

## 6. 子系统 C · 网页版对局现代化（`web.py`）

### 现状（`web.py`，8226 行）
- 单文件内联模板 `PAGE`（L100 起）；`:root` 多主题 token（`mist/dark/flat/flat-dark`，L107-）；游戏面板 DOM/CSS 见 L504-558（`#gpanel/.card/#ghead/#gmain/#gpriv/#glog/.gbtn/.gsec/.vtile`）。
- 页面注入：`_SERVED_PAGE()`（L52-73）做占位符替换（`@@HERO@@/@@MASCOT@@/@@UX_CHAT_CSS@@/@@UX_ICON_*@@/@@UX_GAME_ICONS@@/@@UX_ROLE_ICONS@@/@@UX_RESOURCE_ICONS@@`）；CSP 已放行 `img-src 'self' data: blob:`（L81-91）→ **可直接内联 data-URI 位图**。
- 对局渲染：`renderGamePanel()`（L4127）建 `#ghead`+`#gmain`，调 `GRENDER[gname](main,s)`（渲染器表 L4184）；动作按钮工厂 `gHeadBtn/gBtn`（L4104）；旗舰渲染器 `azul(box,s)`（L5066）、`gemcity(box,s)`（L4951）。
- 网页端**当前完全用矢量/SVG**（`game_icon_svg`/`resource_icon_svg`）与 CSS 纯色 `.vtile`，**未使用任何位图素材**，与桌面端「位图对局美术」存在风格分歧。

### 设计（与桌面端**同源素材**，观感一致）
1. **素材注入（复用桌面的 `_art_boardgame.ASSETS`，单源）**
   - `web.py` 顶部新增 `try: import _art_boardgame as _bg_assets except Exception: _bg_assets=None`（仿 `_art` 注入，L42-45）。
   - `_SERVED_PAGE()` 新增占位符 `@@UX_BG_ASSETS@@`，注入**仅对局所需子集**（`azulejo`/`azul_board`/`azul_score_track`/`azul_bowl`/`azul_tile_r|w|b|y|k`/`gem_o|d|r|e|s|g`/`card_frame`/`panel`）为 `{name:"data:image/png;base64,…"}` 的 JS 字面量（经 `_js_json_literal`，配合模板内 `JSON.parse("…")`）。只注入子集（非全部 26 键）以控制内联体积。
   - `_bg_assets` 缺失 → 注入 `{}`，模板侧 `const BG={}`，面板**静默回退当前观感**（不报错）。
2. **对局面板外壳 CSS（L504-558）现代化**
   - `#gpanel .card`：底纹改用 `azulejo`（`background-image` 平铺 + 半透明白罩层保证文字对比）；圆角/阴影对齐 mist。
   - `.vtile.r/.w/.b/.y/.k`：由 CSS 纯色改为 `azul_tile_*` 位图（`background-image`）；`gemcity` 宝石改用 `gem_*` 位图。
   - `.gbtn`/`.gbtn.go`/`#ghead`：扁平圆角 + accent 选中态，与桌面分区控件观感一致；**禁用态与动作语义不变**。
3. **`GRENDER.azul`（L5066）重写为现代扁平 DOM**
   - 工厂碗 → `azul_bowl` 位图（+ 花砖绕圈）；玩家板 → `azul_board` 9-slice 衬底（`border-image`）+ 花砖；右侧 `azul_score_track` 计分轨；`azTile(t)` 改为位图 `<img>`。
   - **动作契约不变**：`{op:"take",src,col}` / `{op:"place",row}` / `{op:"floor"}` 与选择控件语义保持。
4. **`GRENDER.gemcity`（L4951）重写**：市场卡面 → `card_frame`；宝石 → `gem_*` 位图；面板 → `panel` 9-slice；**动作契约不变**（`take/take2/buy/reserve/buy_res`）。

### 零回归 / 安全
- 注入为纯字符串替换、无 Tk 依赖 → **headless 安全**。
- `_bg_assets` 缺失或子集缺键 → 对应装饰**静默回退**（落到既有纯色/SVG），功能不受影响。
- 不改动既有 `GRENDER` 其余 45 款渲染器与动作协议；不改 CSP（已放行 `data:`）；不改 `web.py` 主聊天区外观。
- 对局美术底（`azulejo`/`board`）为固定浅色，与桌面一致；面板外壳（按钮/标题/边框）仍走主题 token，深色主题下保持可用对比。

## 7. 测试策略

- **扩展** `tests/test_boardgame_assets.py`：新增 key（`azulejo`/`azul_board`/`azul_score_track`）齐备；每个值 base64 可解码为合法 PNG。
- **扩展** `tests/test_boardgame_asset_img.py`：新 key 在真 Tk 桩下返回 `PhotoImage`、命中缓存、缺 key 不抛异常。
- **新增** `tests/test_game_shell_pal.py`：`game_shell_pal(skin)` 键完整且与 `dialog_pal` 键集兼容（可直接替换 `self._pal`）；浅/深皮肤分支均有效；纯函数、headless 安全。
- **新增** `tests/test_web_boardgame_assets.py`：`web._SERVED_PAGE()` 输出**无残留 `@@UX_BG_ASSETS@@` 占位符**；注入的 `BG` 含对局所需子集（至少 `azulejo`/`azul_bowl`/`azul_tile_r`/`gem_o`）；`_bg_assets` 缺失（monkeypatch 为 `None`）时退化为 `{}` 且 `_SERVED_PAGE()` 不抛异常。
- **视觉回归**：以合成资料 + loopback 渲染 azul/gemcity 快照（沿用既有快照测试范式），确认新素材生效且不崩。
- **verify**：跑 `tests/_run_all.py`，目标=**无新增 FAIL**（pre-existing FAIL 不计）；`python build.py` 双 EXE 编译通过。

## 8. 分期与验收

- **一期**：A 素材层重绘/新增 + 生成器重生成；`_p_azul` 重排。
- **二期**：`_p_gemcity` 同步。
- **三期**：B 对局窗口外壳现代化（`game_shell_pal` + 注入 + 标题栏/工具栏改造）。
- **四期**：C 网页版对局现代化（`_SERVED_PAGE` 注入同源位图 + 面板 CSS + `GRENDER.azul`/`gemcity` 重写；依赖一期素材就绪）。

**验收标准**
1. azul / gemcity 对局画面呈现现代扁平 · 阿兹勒赫风，与 BGA 参考同气质（不复制素材）。
2. 桌游相关窗口外壳现代扁平且统一，**主聊天窗外观不受影响**。
3. 网页版 azul / gemcity 与桌面端**同源素材**、观感一致；网页主聊天区外观不受影响。
4. `tests/_run_all.py` 无新增 FAIL；`build.py` 双 EXE 编译通过。
5. 无外部素材引入。

## 9. 约束（红线）

- 不伪造完成；证据保护（不覆盖历史截图/审查证据）。
- 不改既有 FAIL 判定/断言/跳过；验证用合成资料、loopback、私有桌面。
- 不改 `design_tokens()` golden digest（`a137658af6f3f9899c2106a0e6020c1b1e6d2569bab462488bb7c42dc0eb4078`）、不删 `_GAME_ICON` 既有键、不破坏 `icon_svg` 字节兼容、不改 `build.py`、不改主聊天窗皮肤。
- 假画布桩下绝不调用 `ImageTk.PhotoImage(master=cv)`。
- 仅对标 BGA 风格方向，全部素材原创程序化生成。
- **未经用户明确要求不 commit/push。**
