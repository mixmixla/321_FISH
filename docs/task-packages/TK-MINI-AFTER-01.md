# TK-MINI-AFTER-01 v1.2 — MiniBar 自有更新任务销毁

2026-10-21 READY。base/main f057efa1a6d21c23f3fc8b448459eb7ec3389f50/clean，独立分支fix/mini-timer-lifetime-20261021。root唯一写入与验证，gate_review独立只读；普通模型/Standard。用户要求剩余MiniBar/Boss独立诊断，本批仅一个有真实证据的小缺陷。v1初始仅本地交付；v1.1依据用户最新本周有界持续公开/集成授权更新交付范围，不扩大产品范围或发布权限。

## 选择、证据门槛与范围

先用同一存活Tk root分别创建真实MiniBar/Boss、记录after归属与自然bgerror。MiniBar在win.destroy后若留下_update脚本并实际报失效命令才修；Boss只隔离诊断，不混修skin重建/tick/置顶。正式ChatWindow.quit_app已在组件销毁后全局取消解释器任务，不能从组件探针或旧stderr认定整个应用退出坏了。
只允许client.py MiniBar持有唯一更新任务并在其owner真实Destroy时取消：add='+'且event.widget严格为self.win；首次调度前初始化ID/销毁标记；已执行任务移除ID，已销毁不接触Tk也不重排；hide/show保持原1000ms节奏且不产生第二循环。不改Boss/GameWindow/BoardFocus/quit_app、tkguard/conftest、协议/规则/依赖，不清空root队列，不引入全局引用。

## 验收与停止点

1. 最终同字节真实Tk回归在原代码先RED，覆盖首次tick前/自然tick后销毁、自然bgerror、无关sentinel/另一MiniBar、tooltip子Destroy、hide/show、重复6轮销毁释放、父root销毁和更新中重入销毁。合成core/files/prefs，不用mock Tk或改产品时序冒充真实GUI。
2. 确认后最小修复，同回归green及受影响旗舰/游戏timer/大厅/tooltip/布局/退出等逐文件领域；独立审查Task/diff/原raw后冻结唯一最终默认run.py test-all。保留所有历史失败，不改旧断言/skip/timeout，不启用visual/hardware。
3. 独立终审核当前/领域/full源标识、每份原raw/hash/单attempt/exit/cleanup/默认skip；本地提交并更新现有中心/任务投影/Review/稳定事实。原始运行数据仅本地ignored；新拟公开仅代码/回归、必要文档与结构化结果/hash索引，给出准确路径和类别，并核所有新增文件与全部新提交历史，排除原始运行日志、本机用户名、私密数据、密钥、运行profile/EXE；按最新有界授权正常push和安全集成。fresh fetch核其它改动/保护/required checks，不强推/绕过、不发布；安全拒绝就停，不换路线。
4. 完整native GUI/新EXE/正常红退出/LAN/其它真实DPI/硬件仍未测；旧EXE不含本修复。Boss、全局wheel等未修不假放行。此批终点停止实现，提供下一批优先级/依赖供调度；不声称可读取剩余周额度，不为消耗用量制造任务。
恢复先中心本段→Task/Review→Git/活动进程→原summary；长测只有一个，记录确切run，不重复启动。

## 原始诊断检查点

归属probe mini-boss-diagnosis-20261021-163734-09d8744468为1P1F：Mini在同一存活root销毁后留下_update，真实一秒事件触发invalid command；Boss留下_tick与lambda两项，但1700ms窗口内bgerror为0，未满足探针预期，不称Boss实际报错已确认，原失败及probe源保留在本地。oneoff仅诊断，已从最终suite移出。
最终同字节8case原生产RED6F2P（mini-timer-red-20261021-163833-e850928527）；只改MiniBar18+/2-，首修即8P。领域7文件56P0F0S（mini-timer-domain-20261021-163934-79ce6a7bc8），486输入/source f90cf605a636fe3890b98a5bcf01b02ace50f46f8e0abc0a8a1df5aa43b9bff3，RED/green输入仅client.py差异。领域首次命令含误写不存在的test_r61_details.py，runner在测试前拒绝，查实际文件test_r61_features.py后执行上述完整领域；不作失败应用case或已通过记录。

## v1.1 交付授权更新

本批唯一full运行期间，用户明确允许本周持续将通过验收的代码、测试、项目文档、脱敏测试摘要推送到公开仓库mixmixla/321_FISH并合并main；不含原始运行日志、本机用户名、私人数据或密钥，不发布版本。使用此有界新授权，不复用此前10文件具体许可；原证据保留本地且不因公开改动。新增文件及新提交历史均须审计，摘要保持可追溯、诚实。此次只调整交付条件，代码/测试/时序/环境/唯一full不变，不重新启动测试。遇安全拒绝立即停止该动作并报告，不能换路线规避。

## v1.2 原全量环境中断后的同run续跑

原full在125文件完成、test_r33未完成时遭exec-server transport disconnected；driver37784和记录child9640均由门禁process_state确认exited，summary不存在，r33 raw仅部分输出，不能记通过或产品失败。已在本地保存原progress/partialraw SHA与125完成记录。使用既有run.py test-all --resume原run，只续未完成84文件，不另建/重跑full，不覆盖attempt1。门禁若发现PID活跃/unknown则拒绝，不kill旧PID。
源码/测试/依赖/环境/命令未变。验收须明确r33 attempt1是环境interrupted且没有完成退出码，attempt2才是完整测试；其余208文件单完整attempt，125已完成记录逐hash/attempt不变。不得宣称所有attempt单次或把中断算PASS，最终逐文件真实exit/cleanup/默认skip仍必须通过。summary.seconds是续跑段，另记原run起止wall时长（含断线），不混作连续全量耗时。此为恢复策略调整，不弱化测试、不重启原诊断或125完成文件。
