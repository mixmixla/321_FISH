# GAME-UI-01 v1.2 — Windows 旗舰与收起恢复

**最终结论（2026-10-03）：AI_ACCEPTED，限本轮本地技术范围。** resource_review独立终审无must，主控据最终1daea66/full1669-0-2与对应分层/产物证据裁决；非Pro/用户验收、整个R1/RETIRE通过或发布。以下阶段未完成/失败记录按历史保留。


Task：[GAME-UI-01](../task-packages/GAME-UI-01.md)。当前已本地整合、REVIEWING，最终全量待完成。
resource_review独立设计审查认可桌面v1.1契约；主控将Web移出冻结v1.2，保留Windows优先方向。
13项最初桌面缺口与后续47双端静态初筛另见[完成度地图](../游戏完成度地图.md)。

实现位置：独立worktree `_tmp_gui/game-ui-01/`、branch codex/game-ui-01，从已审本地资源提交9baffbb分出。
主树业务源码未变。root先写纯棋盘逻辑/测试和部分painter，随后明确停止代码写入并交gate_impl唯一接手；
root负责主树资料/版本/验证调度，resource_review不参与实现、负责独立审查。

## 纯棋盘切片的真实对照

`python -m pytest -q tests/test_flagship_board.py --basetemp <本轮独立目录>`，
项目.venv/Python3.14.5，子进程仅OS启动环境键+合成profile，cwd为上述隔离checkout。
本文件只导入client_gameui并调用纯函数/点击字典，不实例化Tk、不访问网络/设备/外部工具或真实数据。

- 原client_gameui：24 failed / 8 passed，exit1，0.63秒。
- 相同32项测试+第一版helpers/点击修复：32 passed，exit0，0.31秒。
- 其中11个原失败覆盖现有点击/只读/占点/范围/满列错误；13个原失败表示新胜线/状态函数缺失，
  不冒称24种生产缺陷。负例/正例日志与代码/测试hash分别在`_tmp_gui/game-ui-evidence/board-*.{log,json}`。

之后root继续修改painter（静态胜线/最后落子、有限pulse、较淡棋盘配色）并交接，
该增量尚未重测，32通过仅绑定前一版helper源码，不能作为当前完整UI绿灯。

## 交接时未完成

client.py尚未接入ui.state/can_move/room-round上下文及最终_do_action门禁，窗口快照与after取消也未实现。
当前worktree是WIP，不能整合为可用候选。接手者须完成Task所有桌面契约、双方/观战/异常/再开、
真Tk正常与最小窗口/事件绑定/收起恢复、相关领域与独立代码审查，再统一集成全量。
Web、真实设备、真实LAN和EXE不由纯逻辑测试推定完成。

## 完整桌面实现与独立复审

后续gate_impl完成最新Core状态/room-round门禁、执色/只读提示、两窗口独立有限动画和隐藏取消，
以及root/mini/GameWindow/BoardFocus对象身份与可见性快照。主控保留前述阶段记录，不把32项追溯为完整验收。
独立resource_review初审发现root_visible/mini丢失、GameWindow hide_reason未使用两must；
真实Tk对照1failed/2passed，修后3passed。手动隐藏/离房/关闭会撤销恢复资格，隐藏中更新终局后恢复显示最新态。

主控查看真实合成窗口截图又发现640×480工具条右按钮文字裁切；已改规则/棋盘/专注窗等宽三列，
测试核对实际宽度≥请求宽度。长昵称Canvas省略，状态文字保留完整昵称。
六张最终PNG（两棋normal/minimum/focus）位于`_tmp_gui/gui-qa/visual-qa-20261003-044736-9152868615/captures/`，
主控逐张查看；原裁切图`visual-qa-20261003-042722-fdbfd7bd92`保留。
截图验证布局，不能替代规则/真实对局证据，合成四子棋布局样例last_move与空格不一致亦不拿来证明落子规则。

最终实现worktree提交`9263f773bbdd483e83d96e84ad23aeea0858538d`，主树cherry-pick为`806c5ed`。
该候选独立复审无must，允许本地整合；测试bridge仅注释与主树不同，AST等价，未混入GUI提交。
候选source `f2dbdd35e75e0dafd15a469f9bdc5a7763e759a1a398fa6f2c82c24c99ef2616`：

- `gui-layout-final-20261003-124716-f81e931614`：真Tk 3passed，exit0。
- `gui-layout-flagship-final-20261003-124805-3595c5e61d`：board36/wire2 passed，exit0。
- 原始summary/log/sandbox在`_tmp_gui/local-trial-build/_tmp_gui/test-gate/`；
  复现入口为正式门禁执行`tests/test_flagship_board.py tests/test_flagship_gui.py tests/test_flagship_game_wire.py`。

## 整合专项暴露的测试确认竞态

主树806c5ed加REL构建边界补正后，`integrated-prebuild-20261003-130541-32a3e6a8fa`真实exit1：
board36p/Tk3p/REL13p/wire1p1f。四子棋等不到终局，原日志完整保留。
原wire `_state_for`只匹配room/status，队列里上一手playing帧会被误当当前确认，导致下一手在服务端处理前发出。
修订仅测试：双方逐手确认相同round、准确棋子数和预期turn/winner，再发下一手；开始/再开要求空棋盘/新轮，
终局/复位语义断言保留；fixture显式loopback/禁discovery，退出shutdown并join本次reader。
新增队列反例证明旧手、旧轮都不能充当当前ack。

`wire-state-ack-fix-20261003-131121-46669e23a5`：真TCP两局+反例共3passed、exit0，11.129秒，
source `8ca1af5afdffbef7c601d1dfc8bb5ca314442ce065cc08313937134c985d97ce`。
此测试修订独立审查与最终全量仍须完成，不能把原失败改写为通过。

## 试用模式恢复补正与最终专项

第一版实际EXE构建后核实：双禁托盘/热键时，设置进入假工作窗后WM_DELETE只hide，失去可见恢复入口。
已按Task必要邻接边界，仅在双flag禁用时绑定关闭到现有_toggle_boss退出分支，调用静默退出和窗口快照恢复；
退出后复原原hide协议，下次进入再绑定。默认行为保持，双禁用提示改为关闭伪装工作窗恢复。

原client真Tk负例`trial-boss-negative4-20261003-132453-24374a1082`：1failed/3deselected，
关闭Boss后root仍withdrawn。修后`trial-boss-fixed2-20261003-132527-ffca939312` 1passed/3deselected。
完整GUI阶段4passed后追加默认协议/status/提示覆盖，以及时钟seam收口。
旧full内GUI after断言失败和`trial-boss-gui-final-20261003-132930-cebca2f7bd` 1failed/4passed保留；
后者证明redraw不会消费已排队timer，不能为测试更改产品render。
最终只给client_gameui.time局部可控monotonic对象，通过Tcl after info/cancel取得并执行真实_tick，
核对pending、隐藏取消、超过0.9秒后不续排。没有更改整个Python进程共享time模块或减弱输入门禁。

最终source `784f1d8b2a3cda2c0af41d0294898ed375bcb09ba40331cc63b113e2b1c52065`：

- `trial-boss-gui-final3-20261003-133130-56f352c164`：真Tk5passed，exit0。
- `trial-rel-kick-final-20261003-133300-2e600262f7`：REL15/kick6passed，exit0，13.17秒。
- 所有raw run在主树`_tmp_gui/test-gate/`；原负例及中间失败未覆盖。

resource_review独立窄审：Boss限定条件/静默退出/快照恢复/默认保持与测试修订无must；
ROOT另四文件单例隔离/双EXEharness/fixture修订也已独立通过。主控批准整合：独立提交3e7ef6b，
主树1daea66，Git树完全相同；主树checkout原字节source变为f224f73b…，重新最终全量/构建，不沿用旧全量。
新Boss的真实EXE界面操作未单独自动化，证据是源码真Tk，不将EXE登录证明当作该UI流程证据。

## 最终整合验证

主树1daea66，330输入source f224f73b20e72ee1494f7fff096d7751c20fb6757d8c5b41434964431b4867f6，
完整127文件1669passed/0failed/2原opt-in，exit0，827.261秒。36board/5真实Tk/3wire均实际执行通过；
原失败和所有追加断言保留，详细运行身份见[VB Review](VB-01-r1.md)。
两旗舰在完成度地图继续列实验，证据分层边界未因全量通过而升级为EXE完整UI稳定验收。
