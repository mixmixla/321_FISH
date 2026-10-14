# 桌游展示层「每游戏独立包 + 共用外壳」设计（Azul 精修试点）

> 状态：待评审（brainstorming 阶段产出，尚未进入实现）
> 日期：2026-10-14
> 关联：沿用并取代 `docs/superpowers/specs/2026-10-13-boardgame-modern-flat-azulejo-design.md` 中「对局美术」部分的方向（本次把「换素材」升级为「展示层按游戏拆包 + 逐款对标」）。

## 1. 背景与问题

现状：
- 规则层尚可：`games_pkg/` 有 47 款游戏，各自实现 `BaseGame`（`snapshot/private/act/tick/ended/player_left`），纯逻辑、零 IO。
- 展示层是巨石：**47 个桌面画师集中在一个 `client_gameui.py`**；**45 个网页渲染器集中在一个 `web.py` 的内联 JS 模板**。素材另由 `_gen_boardgame.py` 统一生成、`_art_boardgame.py` 统一内嵌。

要「全面对标 BGA」（每款有定制版面与美术、统一外壳），当前结构无法支撑：改一款要动数千行的共享文件，没有「单款游戏自己的版面模块」这一层。

本文定义第一波：**建立「每游戏独立展示包 + 共用外壳」框架，并把 Azul 作为精修样板做到位**。其余 46 款保持现状（零回归），后续按同一模式逐款迁移。

## 2. 目标 / 非目标

**目标**
- 引入 `boardgames/<game>/` 展示包：单款游戏的版面/画师/网页渲染/素材自成一体，可单独改、单独验。
- 引入共用外壳，统一「深色桌面底 + 标题·轮次横幅 + 玩家面板 + 操作条 + 计分/地板条」与响应式栅格。
- 桌面与网页**共用同一套位图素材与同一套版面语义**。
- Azul 作为第一个样板包，版面结构对齐真实 Azul（花纹行 / 5×5 墙 / 地板线 / 工厂盘 / 计分轨）。
- 未迁移的 46 款**零回归**；`build.py` 双 EXE 仍可打包。

**非目标（本期不做）**
- 不重写 `web.py` 的「单文件内联模板」架构（页面仍为单个内联页）；但**每款游戏的网页渲染器要从 `web.py` 搬进各自展示包**（代码级分离），`web.py` 只留外壳与组装。运行期独立 `.js` 文件按需加载不做。
- 不迁移 `games_pkg/` 规则层（展示包通过转发引用规则，保持对外自包含）。
- 不对 47 款一次性全量迁移。
- 不追求 BGA 的手绘插画质感（那是画师工作量）；目标是「干净、明亮、结构清晰的扁平风，版面结构与层次对得上真实桌游」。

## 3. 红线（沿用项目既有约束）

- 全部素材 **Pillow 程序化原创**；仅对标 BGA 风格方向，不复制任何素材/坐标/色彩采样。
- **不改** `ui_design.design_tokens()` golden digest（`a137658af6f3f9899c2106a0e6020c1b1e6d2569bab462488bb7c42dc0eb4078`）。
- **不删** `_GAME_ICON` 既有键；**不破坏** `icon_svg` 字节兼容；**不改** 主聊天窗皮肤。
- 假画布桩下（`_real_cv(cv)` 为 False）**绝不调用** `ImageTk.PhotoImage(master=cv)`。
- verify 目标为「**无新增 FAIL**」（pre-existing FAIL 不计）。
- 网页注入后整页 JS 必须语法合法（`node tests/ux_visual_chat_probe.cjs` 为闸门）。
- **未经用户明确要求不 commit / push。**

## 4. 目录与包结构

新增展示包根 `boardgames/`（与规则层 `games_pkg/` 并列，命名避免混淆）：

```
boardgames/
  __init__.py
  registry.py          # 展示包注册与发现；含旧画师兜底查询
  shell.py             # 共用外壳（桌面）
  shell_web.py         # 共用外壳（网页：CSS 变量 + JS 助手）
  azul/                # ← 第一个样板包
    __init__.py        # 导出 GamePackage
    meta.py            # 名称/标签/图标键/人数
    desktop.py         # Tk 画师 paint(cv, st, me, nick, submit, repaint, ui, priv, w, h)
    web.py             # 网页渲染片段（JS 函数 + 附加 CSS）
    sprites.py         # Azul 素材生成（自 _gen_boardgame.py 拆出）
    assets/            # 生成的 PNG（Azul 专属）
    _art.py            # 内嵌 base64（生成产物）
```

`boardgames/azul/__init__.py` 内 `from games_pkg.azul import AzulGame` 转发规则，使包对外自包含；规则层迁移留作后续。

Azul 迁移完成后，**旧的 `client_gameui.py::_p_azul` 与 `web.py` 内联模板里的 `GRENDER.azul` 一并移除**，改由展示包提供——以此证明「展示层已独立」。其余 46 款不动。

## 5. 展示包契约

```python
class GamePackage:
    name: str                  # "azul"
    label: str                 # "花砖物语 · 拼花"
    rules: str                 # "games_pkg.azul:AzulGame"
    icon: str | None           # 图标键（复用 ui_design.GAME_ICONS）
    desktop: Callable | None   # paint(cv, st, me, nick, submit, repaint, ui, priv, w, h)
    web_js: str | None         # 渲染片段（内联 JS），注册进 GRENDER
    web_css: str | None        # 该游戏附加样式
    assets: dict[str, str]     # key -> data-URI（由 _art.py 生成）
```

契约字段全部可选（缺省即「未迁移」），注册表据此判定走包内实现还是旧兜底。

## 6. 共用外壳职责

- **桌面 `shell.py`**：统一「深色桌面底 + 标题·轮次横幅」；**玩家面板**（BGA 式：配色块 / 昵称 / 分数 / 当前行动高亮 / 观战位）；操作条；地板/计分条；`layout(w, h)` 断点与栅格常量。
- **网页 `shell_web.py`**：对等的一套 CSS 变量与 JS 助手（`bgImg`、玩家面板、动作条）。
- 外壳**只提供组件与布局，不含任何单款游戏的规则语义**。

## 7. 素材管线

- 每款游戏自带生成脚本（`sprites.py`）与内嵌模块（`_art.py`）；生成物落在该包 `assets/`。
- 启动/构建时把各包 `assets` 合并进全局素材表；沿用既有 `_asset_img/_asset_at/_asset_nine_at/_asset_bg` 的缓存与 headless 守卫。
- 现有 `_gen_boardgame.py` / `_art_boardgame.py` 继续服务未迁移的游戏（本期不删）。

## 8. 接线（两处关键风险）

- **桌面**：`client_gameui._register` 全部保留作兜底；新增加载器——`render()` 先查 `boardgames.registry`，命中包内画师则用之，否则回落旧画师。**未迁移的 46 款零影响**。
- **网页（与桌面对等，代码级分离）**：每款游戏的渲染器是 `boardgames/<game>/web.py` 里的独立模块；`web.py` 模板新增**注入点**，服务时按注册表把**已迁移款**的渲染器与附加 CSS 组装进页面的 `GRENDER` / 样式（同名键以包内为准）；**未迁移款暂时仍留在内联模板里，逐款搬空**。页面仍是单个内联页；注入后必须保持整页 JS 语法合法。

## 9. 测试策略

- 新增 `tests/test_game_packages.py`：注册表完整性、契约字段齐全、包内画师在桩画布与真画布均可渲染、网页片段语法（`node` 探针）。
- 迁移一款 = 包内新增画师 + 旧注册改为指向包（或删除旧函数）。
- 门禁：迁移前后 47 款既有测试全绿；`python build.py` 双 EXE 编译通过。
- 扩展 `tests/test_boardgame_assets.py` 以覆盖新键计数（若 Azul 素材键集变化）。

## 10. Azul 样板的美术/版面规格（本轮交付核心）

版面结构（对齐真实 Azul）：
- **底**：深色桌面底（暗蓝灰系），玩家板与工厂盘「浮」在其上。
- **玩家板**（浅色）：左侧 **5 条花纹行**（第 i 行 i+1 格，行首标容量 1..5）；右侧 **5×5 墙**，空槽按引擎拉丁方 `_wall_col = (颜色序号 + 行号) % 5`（`COLORS = ["r","w","b","y","k"]`）**淡印出该格应有的花色**，已落砖画实色花砖；底部 **地板线 7 格**（含扣分刻度）。
- **工厂盘**：亮色陶瓷盘（米白盘身 + 深色描边），盘内花砖沿盘边均匀摆放；**中央池**独立成盘。
- **计分轨**：**带刻度**（起点 0，每 5 格加重；上限取整为 30 格以便窄窗可读），并放置各玩家棋子（自己高亮）。
- **花砖**：5 色（红/白/蓝/黄/黑），饱满圆角砖 + 顶部轻高光。

网页端以 CSS grid 复刻同一版面，复用同一套位图；**动作契约不变**：`take / place / floor`。

## 11. 迁移与分期

1. **第一波（本次）**：搭 `boardgames/` 框架（registry + shell + 接线 + 测试骨架），Azul 迁为样板包并完成版面/美术精修，桌面 + 网页双端。
2. **后续**：按同一模式逐款迁移与精修——**桌面画师与网页渲染器一并搬进包**，`client_gameui.py` / `web.py` 的旧实现逐款搬空；再评估把 `games_pkg/` 规则层与 `web.py` 模板架构一并收拢。

## 12. 风险与取舍

- **网页注入**是最大风险点：单文件内联模板 + 语法闸门；本期只做注入 + 兜底，不动模板架构。
- **新旧并存**：过渡期两套渲染路径同时存在；由「注册表判定 + 旧兜底」把风险限制在单款。
- **规则层未搬**：包对外自包含靠转发实现，静态上仍是两处；留作后续。
- **观感预期**：扁平结构风，非 BGA 手绘质感；在此预期内对齐版面与层次。
