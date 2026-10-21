# TK-GAME-AFTER-01 r1 — 游戏窗口自有定时任务销毁

2026-10-21：**AI_ACCEPTED_GAME_WINDOW_TIMERS_ONLY / FULL_PASSED / LOCAL_ONLY / R3_GUI_NOT_RUN**。
[Task v1.1](../task-packages/TK-GAME-AFTER-01.md) / [结构化结果与原件hash索引](../review-assets/TK-GAME-AFTER-01/evidence.json)。root实现，gate_review独立只读；本轮只一个小增量，普通模型/Standard。

## 根因与最小实现

base/main 8f1595d77da3b2bfd531a1c535930de7b6bbf39f；分支fix/tk-destroy-callbacks-20261021，代码ab4a12eab0cf1896319916f312dbf0a92839f357。client.py仅24+/3-：GameWindow保存自有poll/三次延迟列表请求的after ID，执行前移除ID，关闭与调度均检查_closed；close通过原注册owner逐项取消并清空集合。hide/show仍按原200/600/1800/3500ms节奏工作，另一个窗口和root任务不取消，_sync重入close后不重排。
旧代码先destroy Tcl command，却保留解释器after脚本；_closed Python guard尚未进入就已报invalid command。单root存活真实复现，不能归咎于两个root串扰。正式ChatWindow.quit_app已有全局取消，未因此声称正式红退出本来坏或已修好。
未改MiniBar/Boss/BoardFocus、bind_all、tkguard、conftest、网络、协议、规则、依赖或已有测试。新增6case使用真实Tk/真实事件循环、合成core；没有OS输入/截图或实际网络，不能冒充完整GUI。

## RED、首次失败与引用链

所有原件位于项目根的`_tmp_gui/test-gate/<run_id>`，完整命令/退出码/原summary与raw SHA见索引；run.py test-all均由项目.venv Python3.14.5执行，Windows private desktop/合成profile/loopback沙箱。

| 步骤 | run_id | 实际结果 |
| --- | --- | --- |
| 初始RED | tk-game-red-20261021-154941-e4c604e1ad | 5F1P；close前/后首poll均留4任务，750ms自然事件报poll/lambda两次bgerror |
| 首修 | tk-game-green-20261021-155108-453924e295 | 5P1F；定时任务已过，整个窗口弱引用未释放，原失败保留 |
| 新/旧引用链探针 | tk-game-referrer-20261021-155308-1b3e942a24 / tk-game-old-referrer-20261021-155515-a9e554c665 | 各1P；均由root._tclCommands中的_dispatch_wheel保留，root.destroy后全窗口释放；新增4run闭包close后全部释放 |
| 最终测试早期副本 | tk-game-frozen-red-20261021-155531-9da07e0372 | 同测试5F1P；副本481输入，未包含.python-version/app.ico/tests/_run_all.py/tests/_smoke_excel_skin.py，不称完整同输入 |
| 最严同输入RED | tk-game-exact-red-20261021-155805-4edfab64b4 | 补独立git索引登记原白名单485路径，输入仅client.py与green不同；同测试5F1P，无旧原件覆盖 |
| 最终领域 | tk-game-domain-20261021-155553-598792674e | 8文件93P0F0S，exit0；旧旗舰/大厅/房卡/DPI布局/kick等保留 |

不是放宽产品断言：独立gc referrer证明既有root全局滚轮绑定，Task升v1.1将新增泄漏检查精确为24个调度闭包（6轮×4）close后全部释放、队列每轮归基线；root.destroy后仍要求6个完整GameWindow弱引用全部消失。root存活时旧全局绑定保留明确未修。最终测试SHA `b47d43cdbc77d7200a9b7a963e01b9ea30c9c9631f67a58b8e15f9aeae78a78f`，最严RED/领域/full字节一致。
close首次poll前/自然poll后、重复close、无关sentinel/另一真实窗口任务、自然bgerror、hide时实际600ms补发、全部3500ms补发后只剩poll、6轮重建和_sync重入关闭均覆盖。每次RED仅断言之后清理该测试自己的解释器；生产没有扫root队列或隐藏异常。

## 唯一最终全量

`run.py test-all --label tk-game-full`，run `tk-game-full-20261021-155942-cebee2ec16`：**208文件、2922 PASS / 0 FAIL / 20原opt-in SKIP、exit0、755.466秒**。
485输入/source `1b2ddbc38fe87056c8a8c5af1eee95f3f9e13ba53faade07e92a6ef25c16ab86`，领域/当前/snapshot逐hash一致；对先前TRIAL-JOB的484输入只改client.py并增本测试。旧207文件各计数不变，只新增6P。
全部208原日志SHA、单attempt、真实exit、cleanup/无unexpected skip已核；20skip精确r45硬件1+ux_visual_chat_shots18+visual_screenshot1，未启用visual/hardware或改变旧断言/timeout/skip。
原summary SHA `3fe3fdb21d3c380bb378e2538d3b130cdca47387de299169f6d4672d309c8b2a`；结构化索引保留全部208原日志hash、逐文件计数及15项后验，不复制原raw/大summary/profile/EXE到新公开批次。

## 接受边界与交付

gate_review代码/领域及最终full/资料独立终审均0 MUST；已逐项核208原raw、8组历史证据hash、485当前/快照、计数/skip/cleanup及资料投影。主控只接受此GameWindow.close定时所有权，不接受完整R3/用户或Pro里程碑。
旗舰组件原6P保持，raw仍5处_update/lambda诊断（此前11），不能称全部干净销毁。MiniBar/Boss及root滚轮绑定未修；rawwin.destroy、父root直destroy、BoardFocus after_idle不在本次API范围。
当前无node_repl/cua/sky/native GUI工具，不使用替代OS输入/截图；完整GUI、自然红退出、物理LAN/多机、其它真实DPI及硬件仍未测。既有EXE编译的是旧client.py，**不包含本修复**；未重新构建或发布，不外推其旧预检证据。
下一步建议先完成剩余MiniBar/Boss定时任务独立诊断，再以受支持native GUI工具补有限R3；本Task到此停止，不自动冻结下一项。
上一批42文件具体公开许可只绑定8f1595d，已正常push/FF并核远端main与旧分支同SHA；无可见CI不是CI通过。本批另列代码/测试/必要文档/结构化hash索引，不包含新的原始日志、绝对机器路径、运行profile、凭据或二进制；正常push和集成仍以适用授权/自动审批及fresh fetch/保护检查为准。拒绝即停止，不改路线，不强推/删除分支/发布。
恢复：AI_COMMAND_CENTER本段→Task/本Review→Git→本索引/原summary→实际进程；full已结束不重复跑，源码再变须重新审影响。

## 独立终审与交付候选

执行环境曾短暂transport disconnected，fetch/审查命令在CreateProcess前失败；连接恢复后只恢复原只读核验，无重复full、无测试原件覆盖。gate_review依据原件完成终审0 MUST，主控记录AI_ACCEPTED_GAME_WINDOW_TIMERS_ONLY。新批明确10文件：2个代码/测试、8个文档/技能/结构化结果索引；索引没有绝对机器路径，新增行无个人Users路径/姓名/私钥/token，无新原raw、完整summary、profile或二进制。公开范围审计、投影SHA、相对链接和diffcheck通过。
本地完整资料leaf见Git；source485冻结不变。fresh fetch已核origin/main仍8f1595d及origin正确，后续普通push/安全集成按适用授权与审批，实际结果另记回执；不将候选状态冒充已合并。
