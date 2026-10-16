# 桌游展示层「BGA 级精致度」设计（artkit 工具箱 + Azul 样板 · 第二批含网页）

> 状态：待评审（brainstorming 阶段产出，尚未进入实现）
> 日期：2026-10-14
> 关联：承接 `docs/superpowers/specs/2026-10-14-boardgame-per-game-packages-design.md`（已落地并合并）。上一轮建立了「每游戏独立展示包 + 共用外壳」；本轮把「精致度」沉淀为**可复用的绘制工具箱**，并让 Azul 成为它的第一个样板。

## 1. 背景与问题

上一轮交付后实测（用户在 EXE 与网页端查看）暴露两个问题：

1. **观感不够精致**：素材只用了纯色圆角矩形——没有渐变、斜面、投影、大尺度纹样；瓷砖墙是「密、小、发灰」的平铺；工厂盘是「塑料感平圆盘」；玩家板是浅色块 + 简单格子。与 BGA《Azul》的差距集中在**质感**与**布局**两处。
2. **网页端看起来空白**：经排查，渲染器确实注入并执行（`Object.assign(GRENDER,{azul(box,s){…}})` 在页面里、占位符无残留），但——
   - 我们的美术过于扁平、接近白色，铺开即"看起来空白"；
   - 网页只画了**自己一块玩家板**，没有对手板、没有地板线、没有圆形计分轨，信息架构不完整。

本设计定义第二轮：**建立共享精致绘制工具箱 `artkit`，在它之上重做 Azul 素材，并把两端版面重排为 BGA 结构**（左列工厂盘 + 中央池 / 顶部横排所有玩家板 / 右侧圆形计分轨 + 筹码 / 底部信息条）。

## 2. 目标 / 非目标

**目标**
- 新增 `boardgames/artkit.py`：纯 Pillow 的共享绘制原语（渐变、斜面、内凹、投影、质感、纹样印章、盘/筹码/砖）。
- 在 artkit 之上重做 Azul 素材：大尺度无缝瓷砖墙、有厚度的陶瓷工厂盘、奶油色格纹玩家板、立体花砖、圆形计分轨、玩家棋子与分数筹码。
- 扩展共用外壳：`board_panel` / `score_ring` / `info_bar` / `factory_disc` 等**不含游戏规则语义**的可复用组件。
- **桌面端与网页端**都重排为 BGA 结构；网页端修掉「只画自己一块板」。
- 其余 46 款游戏**零回归**（继续走旧路径与共享旧素材）。

**非目标**
- 不迁移规则层（仍在 `games_pkg/`）。
- 不重写 `web.py` 的单文件内联模板架构（仍走注入点 + 兜底）。
- 不引入 SVG/3D/外部素材管线（破坏 Pillow 程序化原创红线）。
- 不为其他 45 款游戏做素材（本轮只做 Azul 样板 + 可复用工具箱）。

## 3. 红线（沿用）

- 全部素材 **Pillow 程序化原创**；仅对标 BGA 的**风格方向**，不复制素材/坐标/色彩采样。
- **不改** `ui_design.design_tokens()` golden digest：`a137658af6f3f9899c2106a0e6020c1b1e6d2569bab462488bb7c42dc0eb4078`。
- **不删** `_GAME_ICON` 既有键；**不破坏** `icon_svg` 字节兼容；**不改**主聊天窗皮肤与其网页 CSS/token。
- 假画布桩下**绝不调用** `ImageTk.PhotoImage(master=cv)`。
- 网页注入后整页 JS 必须语法合法；azul 动作契约 `take/place/floor` 不变。
- 未迁移的 46 款行为与外观**零变化**。
- verify 目标为「**无新增 FAIL**」（本机 Tk 缺 tcl 属环境）。
- **未经用户明确要求不 commit / push。**

## 4. 架构：`boardgames/artkit.py`

纯 Pillow、无 Tk、无游戏语义，可 headless 测试。全部函数接收/返回 PIL 图像或 `ImageDraw`。

```python
canvas(w, h, ss=4) -> (img, draw, s)      # RGBA + 4× 超采样（坐标为最终尺寸，函数内乘 s）
finish(img, w, h) -> Image                 # LANCZOS 收敛到 (w,h)

rrect(draw, box, r, fill=None, outline=None, width=1)
rrect_bevel(img, box, r, fill, *, light=None, dark=None, depth=2)   # 斜面：上/左高光、下/右暗边
recess(img, box, r, base, *, depth=3)                                # 内凹槽：内阴影 + 内高光
shadow(img, box, r, *, spread=6, alpha=70, offset=(0,3))             # 高斯投影
gradient(img, box, r, c0, c1, *, direction="v")                      # 线性渐变，裁进圆角
radial(img, box, c_in, c_out)                                        # 径向渐变
linen(img, box, r, base, *, amount=6)                                # 亚麻/瓷砖噪点质感
ornament_tile(size, bg, fg1, fg2, *, cells=2) -> Image               # 阿兹勒赫单元（四瓣花 + 八角星）

disc(img, box, rim, body, *, ring=None, highlight=True) -> Image     # 有厚度的陶瓷盘
chip(img, box, color, *, label=None) -> Image                        # 分数筹码
gem(img, box, color, *, shape="tile") -> Image                       # 立体花砖（可扩展 shape="marker"）
```

所有颜色参数接受 `#rrggbb` 或 `(r,g,b[,a])`。所有函数对越界/空框**不抛异常**（返回原图）。

## 5. Azul 素材规格（`boardgames/azul/sprites.py` 重做）

| key | 尺寸 | 内容 |
|---|---|---|
| `azul_wall_bg` | 512×512 | 瓷砖墙背景：4×4 大尺度阿兹勒赫（蓝 `#4A7DE0` 系 / 白 `#F7FAFC` 系两色），**无缝**（纹样周期整除边长） |
| `azul_plate` | 160×160 | 陶瓷工厂盘：深蓝厚边 + 内凹槽 + 径向高光 + 底部投影；四角透明（RGBA） |
| `azul_plate_center` | 160×160 | 中央池：同盘，描金边以区分 |
| `azul_board` | 384×288 | 玩家板：奶油底 `#F6F1E7` + 细格纹 + 彩色布边 + 左上铭牌位 + 5 条花纹凹槽 + 5×5 墙位 + 底部 7 格地板线 |
| `azul_tile_{r,w,b,y,k}` | 48×48 | 立体花砖：渐变主体 + 顶高光 + 底暗边 + 轻投影 |
| `azul_wall_cell_{r,w,b,y,k}` | 48×48 | 墙位预印目标色（较现版对比更强） |
| `azul_marker_{r,w,b,y,k}` | 40×40 | 计分轨玩家棋子 |
| `azul_chip` | 64×64 | 分数筹码 |
| `azul_track_ring` | 512×512 | 圆形计分轨：外环 + 31 格刻度（每 5 格加重） |
| `azul_floor` | 48×48 | 地板槽 |

花砖 5 色沿用引擎：红 `#D2534F`、白 `#F0F0F0`、蓝 `#4A7DE0`、黄 `#E0B33C`、黑 `#3A3A3A`。
生成器仍为 `build_all() -> dict[str,str]` + `python -m boardgames.azul.sprites` 产出 `assets/*.png` 与 `_art.py`。

## 6. 共用外壳扩展（`boardgames/shell.py`）

新增（**不含游戏规则数值/合法性语义**；shell 只负责几何与排布，**具体素材键一律由调用方传入**，Azul 画师传 `azul_*`，后续游戏传自己的键即可复用）：

- `board_panel(cv, x, y, w, h, name, rows, wall, floor, score, keys, *, active=False, scale=1.0)`
  `keys` 为素材键映射（`tile` / `wall_cell` / `board` / `floor` / `chip` 的键名前缀或取值函数，如 `lambda c: "azul_tile_" + c`）；画一整块玩家板：铭牌 + 花纹行（第 i 行 i+1 格）+ 5×5 墙（空槽用 `wall_cell`、已落用 `tile`）+ 地板线 + 分数筹码；`active` 时加高亮描边。
- `score_ring(cv, cx, cy, r, scores, me, nick, ring_key)`：`ring_key`（Azul 传 `azul_track_ring`）打底 + 各玩家棋子按分数落位（自己高亮）。
- `info_bar(cv, w, y, h, round_no, turn_nick, bag, scores, me, *, bg_key=None)`：顶部信息条（瓷砖底 + 文字 + 筹码）；`bg_key` 缺省回退原深色底。
- `factory_disc(cv, cx, cy, r, tiles, *, center=False, plate_key=None)`：盘 + 盘内花砖环形均布；`plate_key` 由调用方给（Azul 传 `azul_plate` / `azul_plate_center`）。
- `table(cv, w, h, y0, *, bg_key=None)`：`bg_key` 给定时铺该键位图（Azul 传 `azul_wall_bg`，无缝平铺），否则维持原纯色 `TABLE_BG`（**旧调用方零变化**）。

签名细节在执行计划中锁定；组件内部只调 artkit 素材与既有 `_asset_*`/`_text`/`_rrect` 原语。

## 7. 桌面版面（BGA 结构）

```
┌ 信息条：第 N 轮 · 轮到 X · 袋剩 K · 分数筹码 ──────────────┐
├──────────────┬───────────────────────────┬───────────────┤
│ 左列：工厂盘  │ 顶部横排【所有玩家板】      │ 右侧：圆形计分轨│
│ （竖排成列）  │ 自己放大高亮、对手缩略      │ + 筹码         │
│ + 中央池      │                           │               │
└──────────────┴───────────────────────────┴───────────────┘
```

- 背景：`azul_wall_bg` 无缝平铺。
- 窄窗自适应：**优先保证自己那块板可读**（对手板按可用宽度缩略或换行）。
- 布局常量集中在 `shell.layout(w,h,n_players)`（返回各区矩形），便于测试与两端对齐。

## 8. 网页版面

以 CSS grid 复刻同一结构（信息条 / 左工厂列 / 中玩家板行 / 右计分环 / 底部动作条），位图经 `bgImg()` 复用同一批素材。
- **修掉「只画自己一块板」**：`azul(box,s)` 遍历 `s.players`，每人一块板（自己加高亮类）。
- 动作契约 `take/place/floor` **不变**。
- 约束：`WEB_JS` 内不得出现未转义三引号；不得在单引号属性里嵌单引号。

## 9. 分批交付（重要）

- **第一批（本设计的主交付）**：`artkit` + Azul 素材重做 + **桌面版面重排**，产出样张给用户看。
- **第二批**：**网页版面重排**（含修「只画一块板」）+ 全量收尾（打包、回归）。

用户确认第一批观感后再启动第二批；若第一批观感需要调整，先在第一批内迭代。

## 10. 测试策略

- 新增 `tests/test_artkit.py`：逐个原语的尺寸/alpha/关键像素断言（如 `recess` 让中心变暗、`rrect_bevel` 上边比下边亮、`shadow` 在框外产生半透明像素、`ornament_tile` 无缝）。
- 扩展 `tests/test_azul_package_assets.py`：新键集 + 尺寸 + `data:image/png;base64,` 前缀。
- 扩展 `tests/test_boardgame_asset_img.py`：真 Tk 渲染后新键进入 `_asset_img_cache` / `_asset_nine_cache`；桩画布安全。
- 扩展 `tests/test_web_boardgame_assets.py`：新键进入 `BG` 子集；结构标记（如「所有玩家板」循环）存在；动作契约字符串不变。
- 门禁：`node tests/ux_visual_chat_probe.cjs` 必须 `full_script_syntax:true`；`python build.py` 双 EXE 成功；46 款相关测试无新增 FAIL。

## 11. 能力天花板与风险

- **天花板**：Pillow 可做到渐变/斜面/投影/大尺度纹样，**布局与质感会明显贴近 BGA**；但**做不到** BGA 预渲染 3D 那种照片级宝石/铸件质感。此为硬上限，样张阶段会先暴露。
- **风险**：素材键改动会牵动 web 的 `_BG_ASSET_KEYS` 与两端渲染断言，需同步更新；`azul_board` 由 256² 变 384×288 属尺寸变更，相关断言须改。
- **风险**：桌面端「横排所有玩家板」在窄窗会拥挤；用 `shell.layout` 的自适应规则与缩略策略缓解，并在样张阶段确认。
- **风险**：纹样无缝性依赖「周期整除边长」，需在 `azul_wall_bg` 的单元尺寸上锁定约束并用测试兜住。
