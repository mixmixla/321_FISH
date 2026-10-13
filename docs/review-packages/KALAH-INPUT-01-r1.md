# KALAH-INPUT-01 UI/PAGE r1 — 独立交付

**IMPLEMENTED / READY_FOR_MAIN_REVIEW**，不是AI_ACCEPTED、整体任务或发布验收。[授权范围](../task-packages/KALAH-INPUT-01.md)。

commit **66f9ff8afc4e6a8e9db236f45aedf214d1095e81**，base **c5492396e01e7edc37333dc7a0694141b3110788**，branch `fix/kalah-input-20261013`，worktree `D:/Project/321_FISH/_tmp_gui/kalah-input-20261013` clean。6文件250新增/21删除。未推送/PR/合并/全量/构建，未改原目录应用或主治理文档。

## 已实现的映射和方向

| 本方洞号 | A wire | B wire |
| --- | --- | --- |
| 1..6 | 1..6 | 9..14 |

服务器仍使用cells全局index+1。A下排从左到右为local1..6/global0..5；B上排从左到右为local6..1/global13..8，沿播子环路反向。桌面/Web元数据携带globalindex，反序展示后仍按正确index提交，B本方1号位于上排右侧并发送9，6号在左侧发送14。规则/协议均保持不变。约定已直接发送主窗口，并再次告知client.py待整合部分。

- 桌面只有本人当前回合非空洞建立热区；点击重新检查状态、身份、轮次、洞索引和非空。大厅内嵌与专注窗复用同一painter/handle_click。
- 两行显示本方1..6号，正文保持种子数量；B最近操作的规则global8..13映射b_holes[index-8]。结束和局/观战/等待/本人回合提示明确。
- Web修空B slice，生成上下各六个原生button；只有本人当前回合非空洞启用。保留原生键盘语义。B DOM顺序对应wire14→9，A顺序1→6。
- Web callback捕获原room id，检查当前UID/回合/状态、当前snapshot对象、room_id与playing；陈旧房间/状态/身份/空洞按钮不发送。

## RED、最终验证与自审

真实基线RED三个新增文件：**9 FAIL / 2 PASS，exit1，15.710秒**。[原结果](../review-assets/KALAH-INPUT-01/red/summary.json)/`原attempt保存在ignored red/progress.json；公开summary含单attempt/cleanup/hash索引`保留。失败为B Tk发送A编号、非本人热区、空/结束和陈旧热区守卫、B最近标记及实际PAGE只六个A按钮，未修改RED断言或skip。

初次修复五文件green63PASS；之后自审补room_id守卫与逐项B DOM方向/陈旧snapshot/UID/结束/空洞的实际PAGE断言，形成新候选，最终五文件 **63 PASS / 0 FAIL / 0 SKIP，exit0，9.728秒**。各结果独立保存。

| 文件 | PASS | 验证内容 |
| --- | --- | --- |
| test_games_w2_logic.py | 19 | 既有规则回归，不改规则 |
| test_gomoku_fx.py | 33 | 既有动效/控制合同 |
| test_kalah_gui.py | 2 | 实际Tk Button-1，A/B各六洞，480×400 |
| test_kalah_input.py | 8 | 自然A→B、克隆真实规则接受全部六洞、方向、旁观/非本人/空/结束/陈旧热区、B最近标记 |
| test_kalah_web.py + kalah_web_probe.cjs | 1 | 整个PAGE脚本语法、实际GRENDER生成DOM、上下十二洞及逐项事件/数字方向、各种身份和陈旧上下文守卫 |

[最终汇总](../review-assets/KALAH-INPUT-01/final/summary.json)、`公开summary含逐文件单attempt/cleanup/hash索引；原progress保留ignored`、[核验](../review-assets/KALAH-INPUT-01/verification.json)。5文件单attempt、原log SHA256全部匹配、cleanup_ok全部true。source_content_id `0ce014c9154473942cbc3b81e40d2ec9b9cb72d360aaba5f73bfe284151aa8c9`，fingerprint `b5702dd2812dd86292ee4e8915ab3aab169e3a8699c3ddd742b0144e5feb8338`。

```powershell
& D:/Project/321_FISH/.venv/Scripts/python.exe -B -X utf8 run.py test-all tests/test_kalah_input.py tests/test_kalah_web.py tests/test_kalah_gui.py tests/test_games_w2_logic.py tests/test_gomoku_fx.py --run-dir D:/Project/321_FISH/_tmp_gui/kalah-evidence-20261013/final --label kalah-final
```

cwd是新独立工作树。自审0 MUST限于被分配的UI/PAGE范围；静态AST核对client_gameui.py仅_click_kalah/_p_kalah变动，web.py仅GRENDER.kalah变动。client.py/protocol.py/games_pkg/kalah.py/rooms.py/server.py与base归一化换行后逐字节一致。六受测文件与最终gate源码副本相同；git diff --check通过。这是实现者自审，不替代主窗口独立审查。

## 真实窗口截图

原样BoardFocusWindow与GameWindow._render_to，真实Tk Toplevel/Canvas，真实规则初始化→A1→自然B回合，另捕B9后的最近动作。合成宿主，无prefs/登录/网络。捕获仅owned HWND，Windows private desktop；双方都固定雾岸外层、11pt字体、alpha1，省略夹具拖动绑定，未修改产品client.py默认。Tk scaling=1.333333，本机100%；125%/150%、EXE/LAN未测。

| 场景 | 基线c549239 | 候选66f9ff8 |
| --- | --- | --- |
| A正常 | [前](../review-assets/KALAH-INPUT-01/screens/before-kalah-a-normal.png) | [后](../review-assets/KALAH-INPUT-01/screens/after-kalah-a-normal.png) |
| A窄窗 | [前](../review-assets/KALAH-INPUT-01/screens/before-kalah-a-compact.png) | [后](../review-assets/KALAH-INPUT-01/screens/after-kalah-a-compact.png) |
| B自然回合正常 | [前](../review-assets/KALAH-INPUT-01/screens/before-kalah-b-normal.png) | [后](../review-assets/KALAH-INPUT-01/screens/after-kalah-b-normal.png) |
| B自然回合窄窗 | [前](../review-assets/KALAH-INPUT-01/screens/before-kalah-b-compact.png) | [后](../review-assets/KALAH-INPUT-01/screens/after-kalah-b-compact.png) |
| B9最近动作正常 | [前](../review-assets/KALAH-INPUT-01/screens/before-kalah-b-last-normal.png) | [后](../review-assets/KALAH-INPUT-01/screens/after-kalah-b-last-normal.png) |
| B9最近动作窄窗 | [前](../review-assets/KALAH-INPUT-01/screens/before-kalah-b-last-compact.png) | [后](../review-assets/KALAH-INPUT-01/screens/after-kalah-b-last-compact.png) |

[前元数据](../review-assets/KALAH-INPUT-01/screens/before-capture.json)/[后元数据](../review-assets/KALAH-INPUT-01/screens/after-capture.json)记录源码hash、实际窗口/Canvas尺寸、PNG hash、原文本；hotspots字段均为空，不提供Kalah热区元数据证据。十二张PNG全部hash核验，after对应最终client_gameui源码。两次捕获均exit0，进程已结束。实际Tk输入是程序化事件，未声称物理键鼠；Web是实际PAGE+合成DOM，未声称真实浏览器键盘/视觉验收。

## 主窗口仍需完成

client.py不在本子任务所有权，保持原样：11512参数框仍提示1~6并原样发送；13184摘要仍固定A为“你”。主窗口应按已发送约定实现本方local n→A n/B n+8，参数返回后复核room/round/game/身份，并纠正A/B/观战摘要。否则整体桌面参数入口仍未闭合，不能把本提交记成KALAH全入口完成。

建议独立审查本diff与原证据后cherry-pick 66f9ff8afc4e6a8e9db236f45aedf214d1095e81，再与主窗口client.py修订做整合输入回归。需要的最终全量由主控唯一安排。既有购买full FAIL和当前发布边界保持，本领域通过不覆盖历史失败。无当前子任务技术阻塞，待主窗口整合/独立审查；没有扩大其他美化。

## 主控独立复核（2026-10-13）

AI_ACCEPTED_UI_PAGE_ONLY / READY_FOR_CONTROLLER_INTEGRATION。独立Sol读实际6文件diff、
376输入、RED/final原raw与12PNG身份，0 MUST；root实际读两生产diff并查看全部12张
PNG：正常/480窄窗A/B编号清晰，B上排从左6到右1，B9最近标记在上排右侧，等待/本方
提示与规则对应。归档时更正hotspots空字段的证据界限，保留程序化Tk点击和规则证明。
截图是66f9ff8 UI与原client.py，不是后继controller或最终整合版整窗实测。
实际调用链发现旧ui.state可落到新的core room，root Task v1.2加最终提交身份/版本守卫；
controller尚待独立审查/整合领域。此有限接受不等整个Kalah/全量/EXE/LAN/发布通过。

## Controller v1.2 独立代码与整合领域（后继版本）

root已完成client.py本方1..6参数→A1..6/B9..14、弹窗room/round/game/UID/座位变化
拒绝、返回后的最新turn/status/connected/players/非空校验；摘要按p0/p1真实昵称并只
标当前UID。最终_do_action再校验source_ui room-round/state对象/me与当前Core，旧Kalah
来源换game也提前拒绝，图形global wire不再二次local映射。

独立Sol对实际Task v1.2/差异/三轮RED/原104P及当前220P/source/cleanup终核0 MUST，
仅控制器本范围。[原始独立结论](../review-assets/FOLLOWUP-20261013/controller/independent-review.md)。
当前[12文件整合领域220P0F0S](../review-assets/FOLLOWUP-20261013/controller/controller-ui-domain/summary.json)，
其中参数58P含四真实GameWindow._render_to/两实际_on_click/A-B→规则链，旧round拒绝，
合法wire直接1或9，完整两入口闭合；所有原raw单attempt/hash/cleanup，379冻结输入已核。
领域后仅GATE-FIXTURE两测试更改，产品输入不变，最终full integration-full/session90958
正在运行。旧FULL FAIL保留，未全绿不得整体AI_ACCEPTED/merge-ready。
这些结果为合成规则/Tk事件/生产PAGE验证，不是最终EXE、自然退出或真实LAN/浏览器验收。


## 后继同版阶段门禁（2026-10-13，基于08）

新候选3877a5d的165文件2435P/0F/2原skip、exit0；原full FAIL/原RED与版本边界保持。详见[FOLLOWUP r1](FOLLOWUP-20261013-r1.md)。upstream52尚未整合，不能当新main验证；完整原证据独立终核与阶段交付回执见指挥中心。
