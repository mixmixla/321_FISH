# 桌游对局美术升级设计（组件库 + 主题素材包）

- 日期：2026-10-13
- 状态：设计已逐节获批，进入实施
- 关联权威清单：`docs/游戏UI与资源现代化-任务清单.md` 主题 C（视觉设计系统统一）、D（卡牌/棋盘美术）、F（信息呈现与反馈）
- 用户痛点：此前美术优化只覆盖大厅层（P2/主题E 图标与封面），**对局内画面仍是平涂矢量**，观感未达市面商业桌游水准。

## 1. 目标与非目标

### 目标
- 把桌游**对局内**画面提升到接近市面商业桌游的材质与层次：木纹棋盘、毡布桌面、纸面卡牌、宝石/花砖立体棋子、带厚度的圆形筹码与骰面。
- 建立一套**可复用组件库 + 主题素材包**，两款旗舰（花砖物语 azul、璀璨宝石 gemcity）先落地，其余 45 款分批接入。
- 保持**离线可用、零外部图片依赖**（与任务清单一致的资源形态约定）。

### 非目标（本期不做）
- 不改 `build.py`（素材以 base64 内嵌模块随源码打包，无需 `--add-data`）。
- 不改 `ui_design.py` 的 `design_tokens()`（golden digest 必须保持 `a137658af6f3f9899c2106a0e6020c1b1e6d2569bab462488bb7c42dc0eb4078`）。
- 不删除 `_GAME_ICON` 任何既有键（`_smoke_r21_games.py` 依赖）。
- 不重构 `icon_svg`（`test_ux_visual_chat_design.py` 断言字节兼容）。
- 不引入任何外部/网络素材或他人版权图；素材全部由 Pillow 程序化生成（原创）。

## 2. 三层架构

```
① 素材源层   _gen_boardgame.py        （Pillow 4× 超采样程序化生成；开发期运行一次）
     │  生成
     ▼
② 素材库层   assets/boardgame/*.png   （PNG 源文件，提交）
             _art_boardgame.py        （base64 内嵌 ASSETS: dict[str,str]，提交；仿 _art.py）
     │  惰性解码 + 按画布缓存
     ▼
③ 渲染层     client_gameui.py  _asset_img(cv, key, size) / _decode_asset(key, size)
             画师以 create_image() 消费；三级回退保证零回归、headless 安全
```

**为什么沿用 base64 内嵌模块（仿 `_art.py`）**：仓库既有范式是 `_art.py`（巨型 base64 常量 + 注释 `# 重生成：python _gen_art.py`）由 `web.py` 注入；运行时不读磁盘文件、`build.py` 无需打包 `assets/`、无 PyInstaller `_MEIPASS` 路径问题。

## 3. 组件库清单

### A 类 · 材质底纹（可平铺）
| key | 尺寸 | 说明 |
|---|---|---|
| `wood` | 256×256 | 木纹，可平铺；棋盘/桌面衬底 |
| `felt` | 256×256 | 毡布绒面；桌面/池底 |
| `paper` | 256×256 | 纸面纤维；卡面/纸板衬底 |

### B 类 · 通用组件
| key | 尺寸 | 说明 |
|---|---|---|
| `card_frame` | 96×136 | 卡牌正框（圆角、内衬、留白） |
| `card_back` | 96×136 | 卡背花纹 |
| `coin` | 48×48 | 立体金币/筹码 |
| `token` | 40×40 | 通用指示物 |
| `panel` | 60×60（9-slice，border=12） | 面板底 |
| `die_face1..6` | 48×48 | 六面骰面（带厚度与倒角） |

### C 类 · 主题专属
| key | 尺寸 | 说明 |
|---|---|---|
| `azul_tile_r/w/b/y/k` | 44×44 | 花砖五色（红/白/蓝/黄/黑），带立体釉面 |
| `azul_bowl` | 128×128 | 工厂碗（陶瓷质感，供碗与中央池复用） |
| `gem_o/d/r/e/s/g` | 40×40 | 宝石六色（黑曜/钻石/红宝/祖母绿/蓝宝/黄玉） |

> C 类颜色键严格对齐既有语义单源：`ui_design.RESOURCE_ICONS` 的 `o/d/r/e/s/g`（gemcity）与 `client_gameui.THEME["azul"]` 的 `r/w/b/y/k`。

## 4. 数据流与回退（零回归、headless 安全）

- **缺 Pillow**：`_art_boardgame.py` 导入或解码失败 → `ASSETS=None` / `_decode_asset` 返回 `None`。
- **缺 key**：`_asset_img` 返回 `None`。
- **假画布桩**（`_real_cv(cv)` 为 False，即 `cv._gkey` 非字符串）：`_asset_img` 直接返回 `None`，**绝不调用 `ImageTk.PhotoImage(master=cv)`**（假桩下会崩）。
- **解码异常**：`try/except` 吞掉，返回 `None`。
- **调用方契约**：所有画师在拿到 `None` 时**保留既有矢量画法**（`_paper_board`/`create_rectangle`/`_res_img` 等），因此本改动在无素材环境下与当前 HEAD 视觉等价。

## 5. 接入方式（每款游戏 2 步）

1. **铺底**：在棋盘/桌面区域先尝试 `_asset_img(cv, "wood"|"felt"|"paper", ...)`；为 `None` 时保持既有 `_paper_board` / 平涂。
2. **换组件**：把平涂 `create_rectangle`/`create_oval` 绘制的棋子/卡面/骰面替换为组件位图（`azul_tile_*`、`gem_*`、`card_frame` 等）；`None` 时保留原矢量画法。

旗舰接入点：
- `_p_azul`（`client_gameui.py` L5043）：工厂碗 → `azul_bowl`；`_stone` 花砖 → `azul_tile_*`；底部花纹行/墙 → `azul_tile_*`。
- `_p_gemcity`（`client_gameui.py` L4774）：卡面 → `card_frame`；宝石 o/d/r/e/s/g → `gem_*`。

## 6. 测试

- `test_boardgame_assets.py`：`_art_boardgame.ASSETS` 非空；每个值 base64 可解码为合法 PNG；key 齐备（A/B/C 清单全覆盖）。
- `test_boardgame_asset_img.py`：
  - 假画布桩下 `_asset_img` 返回 `None` 且**不触发** `ImageTk.PhotoImage`（以 monkeypatch 断言）。
  - 真 Tk 桩（Tk 可用时）返回 `PhotoImage`。
  - 同 key/size 二次调用命中缓存（返回同一对象）。
  - 缺 key / `ASSETS=None` 不抛异常。

## 7. 分期

- **一期（本任务）**：A+B+C 全部组件生成器 + `_asset_img` 渲染层 + `azul`/`gemcity` 旗舰接入 + 测试。
- **二期**：其余 45 款按"材质铺底 + 组件替换"分批接入。
- **三期**：扩展 C 类主题专属素材（更多游戏专属棋子/卡面）。

## 8. 约束（红线）

- 不伪造完成；证据保护（不覆盖历史截图/审查证据）。
- 不改既有 FAIL 判定/断言/跳过；验证用合成资料、loopback、私有桌面。
- 不改 `design_tokens()` golden digest、不删 `_GAME_ICON` 既有键、不破坏 `icon_svg` 字节兼容、不改 `build.py`。
- 假画布桩下绝不调用 `ImageTk.PhotoImage(master=cv)`。
- verify 目标为「无新增 FAIL」（pre-existing FAIL 不算）。
- **未经用户明确要求不 commit。**
