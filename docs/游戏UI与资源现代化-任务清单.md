# 游戏 UI 与资源现代化 · 任务清单

- 日期：2026-10-10
- 范围：**桌面端（Tkinter）+ Web 端** 双端，含**美术资源/体验全量**
- 力度：**全量重设计**（47 款逐一纳入）
- 资源形态：**程序化矢量绘制**（沿用现有画师体系，离线可用、零外部图片依赖）
- 本文档性质：**审计 + 任务清单**（本轮不写实现代码）

> 本清单基于对 `client.py`、`client_gameui.py`、`web.py`、`games_pkg/*.py` 的逐款只读审计，所有结论均带代码行号证据。

---

## 一、评估口径与判定维度

每款游戏从 5 个维度判定"缺什么"：

| 维度 | 含义 | 主要取证位置 |
|---|---|---|
| 桌面交互 | 桌面端能否操作 | `_GAME_ACTIONS`（按钮）、`_CLICKS`（画布点击）、`_DESKTOP_UNSUPPORTED_GAMES`（拦截） |
| Web 交互 | Web 端能否操作 | `web.py` `GRENDER[<game>]`（按钮/onclick/输入框） |
| 视觉美术 | 是否矢量图形、信息是否成图 | 桌面画师 `_p_<game>`、Web `GRENDER`、`GART` SVG |
| 资源呈现 | 卡面/棋子/图标是否具备 | `assets/`、`_GAME_ICON`/`_GAME_GRAD`、卡面绘制函数 |
| 规则覆盖 | 规则支持但 UI 未暴露的动作 | `games_pkg/<game>.py` 的 `act()` |

---

## 二、现状总览（关键数据）

- 画师：`client_gameui.py` 有 **47** 个 `@_register`，47 款全覆盖。
- Web 渲染：`web.py` `GRENDER` 有 **47** 个函数，全覆盖。
- 桌面按钮 `_GAME_ACTIONS`：仅覆盖 **31 款**（[client.py#L11459-L11576](file:///c:/Users/Administrator/Documents/trae_projects/AI/learn_demos/321_%E5%B1%80%E5%9F%9F%E7%BD%91%E6%91%B8%E9%B1%BC%E5%8A%A9%E6%89%8B_%E8%81%8A%E5%A4%A9%E6%96%87%E4%BB%B6%E6%B8%B8%E6%88%8F/client.py#L11459-L11576)）。
- 桌面点击 `_CLICKS`：仅覆盖 **19 款**（[client_gameui.py#L963-L973](file:///c:/Users/Administrator/Documents/trae_projects/AI/learn_demos/321_%E5%B1%80%E5%9F%9F%E7%BD%91%E6%91%B8%E9%B1%BC%E5%8A%A9%E6%89%8B_%E8%81%8A%E5%A4%A9%E6%96%87%E4%BB%B6%E6%B8%B8%E6%88%8F/client_gameui.py#L963-L973)）。
- **桌面端零交互的 11 款**（既无按钮也无点击，被拦截）：`azul, bolan, chengzhu, gemcity, gongfang, kaituo, lingdi, nimmt, siji, tielu, yahtzee`（[client.py#L11669-L11672](file:///c:/Users/Administrator/Documents/trae_projects/AI/learn_demos/321_%E5%B1%80%E5%9F%9F%E7%BD%91%E6%91%B8%E9%B1%BC%E5%8A%A9%E6%89%8B_%E8%81%8A%E5%A4%A9%E6%96%87%E4%BB%B6%E6%B8%B8%E6%88%8F/client.py#L11669-L11672)）。
- Web 端仅 **3 款**用 `<canvas>` 绘制（gomoku / go / drawguess），其余多为 HTML 文字/色块。
- 美术资源 `assets/` 仅 **3 张通用图**（hero_banner / mascot / excel-skin-preview），**无任何逐游戏美术**。
- 图标：`_GAME_ICON`（emoji）+ `_GAME_GRAD`（渐变）47 款齐全，但仅用于大厅卡片，**未进游戏内**。
- **已确认缺陷**：`web.py` 中 `nimmt`（L5006）与 `kalah`（L5061/5062）用 `b.outerHTML` 返回按钮，`onclick` 被剥离 → Web 端按钮失效。

---

## 三、主题分章任务

### 主题 A：桌面端交互补齐（优先级 P0）

| 编号 | 任务 | 涉及游戏 | 说明 | 证据 |
|---|---|---|---|---|
| A1 | 解除拦截并补齐桌面操作 | azul, yahtzee, nimmt, kaituo, lingdi, tielu, gongfang, chengzhu, gemcity, siji, bolan（11 款） | 从 `_DESKTOP_UNSUPPORTED_GAMES` 移除→在 `_GAME_ACTIONS` 补按钮→`_CLICKS` 补点击（如适用） | client.py L11669 |
| A2 | 点棋盘类补按钮动作 | chess, xiangqi, shogi, junqi, dou（5 款） | 有 `_CLICKS` 但无任何按钮，缺操作入口 | client.py `_GAME_ACTIONS` 无键 |
| A3 | blokus 桌面补点击落子 + 跳过 | blokus | `_CLICKS` 无 blokus，仅能文本输入；Web 端已有点击/预览/跳过 | client_gameui.py L963-973 |
| A4 | 补"弃牌"按钮 | balatro, balatro_solo | 规则支持 `discard`（balatro.py L270），桌面无入口 | client.py L11569 |
| A5 | 桌面鼠标作画 + 清空 | drawguess | 现仅文本输入 `x1,y1,x2,y2`；规则支持 `clear` 但桌面未暴露 | client.py L11481-L11484 |
| A6 | 通用动作层：认输 / 悔棋 / 求和 | 全棋类 | 全库检索"认输/悔棋/求和"**无任何实现**，需规则+UI 双层支持 | 全库未找到 |
| A7 | 清理误导文案 | 8 款德式 | painter 底部"→ 按钮区"但实际无按钮（3431/3499 等） | client_gameui.py L3431、L3499 |

### 主题 B：Web 端缺陷与交互修复（优先级 P0）

| 编号 | 任务 | 涉及游戏 | 说明 | 证据 |
|---|---|---|---|---|
| B1 | 修复按钮失效 | nimmt, kalah | `b.outerHTML` 剥离 onclick，改用 DOM 节点 append | web.py L5006、L5061 |
| B2 | 补规则未暴露项 | kaituo（trade）、chengzhu（pass）、gemcity（buy_res + take2 其余颜色）、onewolf（看中心自选两张）、lingdi（坐标米宝）、siji（按钮标签与动作不符） | 规则支持但两端/Web 无入口 | 见各游戏审计 |

### 主题 C：视觉设计系统统一（优先级 P1）

- 落地既有 `docs/design/UX-01-design-system.md`（「雾岸」）：颜色、字体、间距、状态色、圆角、阴影 Token。
- 桌面侧：统一 47 个画师的底色/线宽/字体/选中态/禁用态/动效节奏。
- Web 侧：统一 CSS 变量与组件（`.gbtn`、`.gsec`、卡牌、面板）。

### 主题 D：卡牌 / 棋盘 矢量美术（优先级 P1）

| 子项 | 任务 | 涉及游戏 |
|---|---|---|
| D1 | 统一卡面规范（圆角、花色/点数、背面、选中描边） | uno, blackjack, rummikub, davinci, lovelove, nimmt, halloween, matchpairs |
| D2 | calc24 卡面由白矩形改矢量卡面 | calc24 |
| D3 | 棋盘坐标 + 星位 | gomoku（无坐标/星位）、go（星位仅 ~4 点，19 路应 9 星） |
| D4 | 棋子造型（替代纯文字） | chess, xiangqi, shogi, junqi, dou（现为 unicode/文字） |
| D5 | 骰子图形与掷骰动画 | yahtzee, ludo, coc |
| D6 | Web 端卡面/棋子图形化 | uno, blackjack, calc24, matchpairs, rummikub, davinci, lovelove, nimmt, halloween, azul（现多纯文字） |

### 主题 E：图标 / 资源体系（优先级 P2）

| 子项 | 任务 | 涉及游戏 |
|---|---|---|
| E1 | 逐游戏矢量图标集（替换/统一大厅 emoji，并引入游戏内） | 全部 47 款 |
| E2 | 角色卡 / 身份卡美术 | spy, werewolf, onewolf, avalon, liar, coc |
| E3 | 资源/宝石/金币图标 | kaituo, chengzhu, gemcity, siji |
| E4 | 大厅卡片封面图（assets 仅 3 张通用图） | 全部 47 款 |

### 主题 F：信息呈现与反馈（优先级 P1）

| 子项 | 任务 | 涉及游戏 | 证据 |
|---|---|---|---|
| F1 | 最近一步标记（last_move）补齐 | go, chess, xiangqi, shogi, junqi, dou, blokus, ludo | client_gameui.py L1668（围棋显式降级） |
| F2 | 合法落点 / 可跳点提示 | othello（合法位）、halma（跳点）、checkers（连跳路径） | 规则已提供，UI 未标 |
| F3 | 将军 / 攻击 / 克制结果提示 | xiangqi（将军）、dou（克制）、junqi（炸弹/挖雷） | 规则已判，UI 无反馈 |
| F4 | 对战结果可视化 | rps（桌面仅打印"请见日志"，state 有 matches） | client_gameui.py L1831 |
| F5 | 撒播逐洞动画 | kalah | 现仅整体特效 |
| F6 | 阶段 / 轮次 / 计分 / 胜负统一组件 | 全部 | — |

---

## 四、优先级与分期建议

- **P0（桌面可玩性，先做）**：主题 A（A1-A7）+ 主题 B（B1-B2）。目标：双端 47 款**均可操作**，消除"只有画面无交互"与按钮失效。
- **P1（视觉与反馈）**：主题 C + D + F。目标：统一设计系统落地、关键棋盘/卡牌矢量美术、交互反馈补齐。
- **P2（资源体系）**：主题 E。目标：图标/封面/角色卡资源体系化。

---

## 五、附录 A：47 款总表

> 桌面交互列：`按钮`=有 `_GAME_ACTIONS`；`点击`=有 `_CLICKS`；`拦截`=在 `_DESKTOP_UNSUPPORTED_GAMES`。
> 优先级：该游戏最关键缺口所属层级。

| # | 游戏 | 中文名 | 桌面交互 | Web 交互 | 美术现状 | 主要缺口 | 优先级 |
|---|---|---|---|---|---|---|---|
| 1 | gomoku | 五子棋 | 按钮+点击 | canvas 完整 | 矢量 | 坐标/星位；认输/悔棋/求和 | P1 |
| 2 | connect4 | 四子棋 | 按钮+点击 | 完整 | 矢量 | 落点预览；认输/悔棋/求和 | P2 |
| 3 | othello | 奥赛罗 | 按钮+点击 | 文字 | 矢量/Web 文字 | 合法落点提示；认输/悔棋/求和 | P1 |
| 4 | tictactoe | 井字棋 | 按钮+点击 | 文字 | 矢量/Web 文字 | 认输/悔棋/求和；Web 棋子图形 | P2 |
| 5 | kalah | 非洲播棋 | 按钮+点击 | 按钮失效 | 矢量 | **Web onclick 修复**；撒播动画 | P0 |
| 6 | chess | 国际象棋 | 仅点击 | 完整 | unicode 文字 | 升变选择；认输/悔棋/求和；坐标；last_move | P1 |
| 7 | xiangqi | 中国象棋 | 仅点击 | 完整 | 文字棋子 | 将军提示；认输/悔棋/求和；坐标 | P1 |
| 8 | go | 围棋 | 按钮+点击 | canvas 完整 | 矢量 | last_move；完整星位；坐标；打劫/禁着提示 | P1 |
| 9 | shogi | 将棋 | 仅点击 | 完整 | 文字符号 | 升变选择；打入按钮；认输/悔棋/求和；坐标 | P1 |
| 10 | junqi | 军棋 | 仅点击 | 完整 | 圆+文字 | 认输/悔棋/求和；坐标；攻击反馈 | P2 |
| 11 | dou | 斗兽棋 | 仅点击 | 完整 | 圆+emoji | 认输/悔棋/求和；坐标；克制反馈 | P2 |
| 12 | checkers | 国际跳棋 | 按钮+点击 | 完整 | 矢量 | 连跳路径提示；坐标；认输/悔棋/求和 | P2 |
| 13 | halma | 跳棋 | 按钮+点击 | 完整 | 矢量 | 可跳点提示；坐标；认输/悔棋/求和 | P2 |
| 14 | blokus | 角斗士棋 | 仅按钮 | 完整 | 矢量 | **桌面点击落子+跳过**；拼块预览；胜利动效 | P1 |
| 15 | ludo | 飞行棋 | 按钮+点击 | 完整 | 矢量 | 掷骰动画；移动高亮；认输 | P2 |
| 16 | uno | UNO | 按钮+点击 | 文字 | 矢量卡面 | 万能牌点击选色；Web 卡面；UNO 喊牌 | P1 |
| 17 | blackjack | 21点 | 按钮 | 按钮 | 矢量牌面 | Web 卡面图形 | P2 |
| 18 | calc24 | 24点 | 按钮 | 完整 | **白矩形+数字** | 矢量卡面 | P2 |
| 19 | matchpairs | 抽牌配对 | 按钮 | 按钮 | 矢量小卡 | Web 卡面 | P2 |
| 20 | rummikub | 拉密 | 按钮+点击 | 文字 | 矢量小卡 | 桌面点桌面组；Web 卡面 | P1 |
| 21 | yahtzee | 快艇骰子 | **拦截** | 文字 | 矢量骰 | **桌面全部操作**；Web 骰面图形 | P0 |
| 22 | nimmt | 牛头王 | **拦截** | **按钮失效** | 矢量小卡 | **桌面全部操作 + Web onclick 修复** | P0 |
| 23 | davinci | 达芬奇密码 | 按钮 | 完整 | 矢量牌 | Web 牌面 | P2 |
| 24 | lovelove | 情书 | 按钮 | 完整 | 矢量牌 | Web 牌面 | P2 |
| 25 | halloween | 德国心脏病 | 按钮 | 完整 | 矢量+emoji | Web 图形；拍铃视觉 | P2 |
| 26 | azul | 花砖物语 | **拦截** | 完整 | 矢量 | **桌面全部操作**；Web 瓷砖图形 | P0 |
| 27 | balatro | 小丑牌 | 按钮+点击 | 完整 | 矢量/CSS 卡 | 桌面"弃牌"按钮 | P2 |
| 28 | balatro_solo | 小丑牌·单人 | 按钮+点击 | 完整 | 矢量/CSS 卡 | 桌面"弃牌"按钮 | P2 |
| 29 | betrayal | 山屋惊魂 | 按钮 | 完整 | 矢量地图 | 桌面地图点击；房间卡插画 | P2 |
| 30 | kaituo | 开拓 | **拦截** | 缺 trade | 矢量 | **桌面全部操作**；trade（双端） | P0 |
| 31 | lingdi | 领地 | **拦截** | 缺坐标米宝 | 矢量 | **桌面全部操作**；坐标米宝 | P0 |
| 32 | tielu | 铁路 | **拦截** | 完整 | 矢量 | **桌面全部操作** | P0 |
| 33 | gongfang | 工坊 | **拦截** | 完整 | 矢量 | **桌面全部操作** | P0 |
| 34 | chengzhu | 我是城主 | **拦截** | 缺 pass | 矢量 | **桌面全部操作**；pass（双端） | P0 |
| 35 | gemcity | 璀璨宝石 | **拦截** | 缺 buy_res/take2 色 | 矢量 | **桌面全部操作**；buy_res | P0 |
| 36 | siji | 四季物语 | **拦截** | 标签与动作不符 | 矢量 | **桌面全部操作**；修正按钮标签 | P0 |
| 37 | bolan | 波兰大选 | **拦截** | 完整 | 矢量 | **桌面全部操作** | P0 |
| 38 | coc | 克苏鲁呼唤 | 按钮+点击 | 完整 | 矢量卡片 | play 阶段图形；调查员立绘；骰子动画 | P2 |
| 39 | guess_number | 猜数字 | 按钮 | 完整 | 文字（设计如此） | 无 | P3 |
| 40 | rps | 石头剪刀布 | 按钮 | 完整 | 矢量+emoji | 桌面对战结果可视化 | P1 |
| 41 | spy | 谁是卧底 | 按钮 | 完整 | 矢量卡片 | 点卡片投票；角色头像 | P2 |
| 42 | drawguess | 你画我猜 | 按钮 | canvas 完整 | 白板+线 | **桌面鼠标作画 + 清空** | P1 |
| 43 | werewolf | 狼人杀 | 按钮（手输 uid） | 完整 | 矢量卡片 | 点卡片操作；角色立绘 | P2 |
| 44 | onewolf | 一夜狼人 | 按钮（看中心固定） | 同 | 矢量卡片（狼头 SVG） | 看中心自选两张；点卡片 | P2 |
| 45 | avalon | 阿瓦隆 | 按钮（全输入） | 完整 | 矢量卡片（盾牌 SVG） | 点选组队；任务卡 | P2 |
| 46 | liar | 骗子酒馆 | 按钮 | 完整 | 文字方块手牌 | 牌面/轮盘视觉 | P2 |
| 47 | ninja | 忍者之夜 | 按钮 | 完整 | emoji 心形 | 攻击动画；忍着头像 | P2 |

---

## 六、附录 B：验收标准（建议）

P0 完成时，双端应满足：
1. 47 款在桌面端均可建房、加入并完成一轮操作（无"本端只读"拦截）。
2. Web 端无失效按钮（nimmt/kalah 修复后可点击并生效）。
3. 每款游戏规则支持的动作均能在至少一端触发。

P1 完成时：
1. 47 个画师与 Web 渲染均套用「雾岸」Token（色/字/间距/状态）。
2. 所有棋盘具备坐标；所有卡牌为矢量卡面；关键交互具备反馈（last_move、合法点、胜负）。

P2 完成时：
1. 47 款各有独立矢量图标，并可在大厅与游戏内复用。
2. 角色卡/资源图标/封面图成体系。

---

## 七、备注

- 本清单仅规划、不含实现；实施建议按 P0 → P1 → P2 分期，P0 内部可先做主题 A 与 B1。
- 相关既有文档：`docs/游戏完成度地图.md`（2026-10-03，部分内容已被本清单覆盖）、`docs/design/UX-01-design-system.md`（视觉 Token 源）。
