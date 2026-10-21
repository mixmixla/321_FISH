# TK-BOSS-AFTER-01 r1 — Boss 自有定时任务销毁

2026-10-21：**AI_ACCEPTED_BOSS_TIMERS_ONLY / FULL_PASSED / MERGED / R3_GUI_NOT_RUN**。
[Task v1.1](../task-packages/TK-BOSS-AFTER-01.md) / [脱敏结构化结果及原件hash索引](../review-assets/TK-BOSS-AFTER-01/evidence.json)。root唯一实现；gate_review独立只读；普通模型/Standard。仅本批一个真实组件缺陷，沿用用户本周有界公开/合并授权，不发布。

## 真实复现与最小修复

base/main7ff225763caa2360f571b6de3beec654f32fa77d，分支fix/boss-timer-lifetime-20261021，代码46e25087b588cbc10e38b6550ce7e468e178d347。Boss窗口销毁会删除其Python注册的Tcl命令，但未取消解释器内的after脚本；脚本到期先找不到命令，不能靠Python _alive guard解决。
独立进程单root/真实mainloop4190.81ms，37次heartbeat/maxgap113.04ms，root哨兵1882.33/3384.04ms，真实close276.19ms后winfo_exists=False且两个命令均消失、两个脚本仍pending；自然lambda1543.83ms和_tick3042.11ms产生bgerror，Python异常为空。probe的1P只证明观察器有效，不能当Boss通过。未缩短产品1500/3000ms。旧Mini批两root/1700ms未收到Boss bgerror的负结果与失败原件保留，不反写归因或猜全应用退出故障。
boss.py仅31+/4-：初始化自有ID集合；_build/_tick/show沿用原排程，经本类wrapper登记；执行前移除ID并检查alive；close和owner Destroy取消自有任务，event.widget严格identity忽略子Destroy；无全局扫队列、共享缓存或额外重排。tick中同步close后不再向死widget注册。保留hide/show/换肤活体排程，既有多tick和重复show置顶策略不修。
正式ChatWindow.quit_app已有解释器全局取消；本组件缺陷不能推导正式自然退出已坏或已验收。本批未改MiniBar/GameWindow/quit_app/tkguard/conftest/依赖/协议/旧断言/skip。

## RED、领域和唯一最终全量

项目.venv Python3.14.5/Tk8.6；run.py test-all逐文件真实Windows私有desktop、source/profile/loopback隔离。原件只在本地`_tmp_gui/test-gate/<run_id>`；公开索引不含raw/完整summary/绝对机器路径。

| 阶段 | run_id | 实际结果 |
| --- | --- | --- |
| 独立原代码诊断 | boss-single-diagnosis-20261021-171433-c2097c9160 | 1P；仅观察器有效，实际缺陷见上 |
| 同字节原代码RED | boss-timer-red-20261021-171942-0bcd97981e | 8F1P/exit1，原hide/show已过；销毁生命周期失败 |
| 修复及领域 | boss-timer-domain-20261021-172435-fce58f4cd1 | 7文件101P0F0S/exit0/65.042s |
| 唯一最终全量 | boss-timer-full-20261021-172649-12db730620 | 210文件2939P0F20原opt-in S/exit0/760.527s |

最终9case覆盖主循环内close并真实观察3500ms、1500/3000ms两deadline/root heartbeat；首次真实tick前后close/重复close；保留另一Boss和root哨兵；真实one-shot释放与隐藏tick；换肤子Destroy；六轮创建/销毁/weakref GC；父root/直接owner Destroy；真实tick重入close。RED/领域/full测试同字节SHA `bce9c136b621b2d870800a9cd7666aad058ccb1e8f3d2aee60fc70c8de3754b7`，487输入RED与green只boss.py不同，当前/领域/full snapshot逐hash匹配。
唯一full source `0a1d29967852b737d3aafa4ea8800d94da3e0747713bc616939e8ea7076052b7`，全210原始log SHA、单完整attempt、exit0/cleanup/no unexpectedskip已逐项核；此前209各counts不变，仅新增9P。20skip仍r45硬件1+ux_visual_chat_shots18+visual_screenshot1，无opt-in或额外pytest参数。15项后验全真。summary SHA `bb72b9290aa9fa644fabbc276dcb88d71fa31808099f7004a0eb06cb170260f2`。代码/领域独立审查0 MUST，最终full/资料由gate_review独立终审0 MUST后，主控记录AI_ACCEPTED_BOSS_TIMERS_ONLY，只接受本组件生命周期。
旗舰6P保持，full原件记录0处invalid-command诊断，只记录实际数量，不推断其它退出路径或R3放行。

## 准确拟公开范围与接受限制

仅9路径代码/测试/项目文档/脱敏结构化结果，全部新增提交history也须审计；未加入原始日志/完整summary/profile/EXE/本机用户名/私人数据/凭据。原件保留本地、公开摘要有hash可追溯，不为公开改原件。独立终审及边界审计通过后按本周授权正常push/安全集成，fresh fetch核变化/保护/required checks；遇安全拒绝停止，不旁路/强推/发布/删分支。

| 仓库相对完整路径 | 类别 |
| --- | --- |
| `boss.py` | Product: Boss owned timers only; 31 additions/4 removals |
| `tests/test_boss_timer_lifetime.py` | Nine real Tk regression cases using synthetic content |
| `docs/task-packages/TK-BOSS-AFTER-01.md` | Frozen scope and diagnostic facts |
| `docs/review-packages/TK-BOSS-AFTER-01-r1.md` | Reproduction, validation, review and boundaries |
| `docs/review-assets/TK-BOSS-AFTER-01/evidence.json` | Sanitized structured counts and hash index; no raw logs |
| `docs/AI_COMMAND_CENTER.md` | Authoritative checkpoint and next priorities |
| `docs/任务清单.md` | Generated roadmap projection |
| `PROJECT_MEMORY.md` | Stable Boss timer ownership fact |
| `.agents/skills/fish-assistant-dev/references/development.md` | Stable timer diagnostic guidance |

完整native GUI、新EXE、自然应用红退出、物理LAN/多机、其它真实DPI和硬件未测；真实Tk组件和协议不能代替完整界面验收，旧EXE不含近期修复。下一P1新源码三EXE构建并绑定hash、复用正式owned Job预检；P2在受支持native GUI入口下完成有限R3完整大厅/双客户端对局/聊天/自然退出。无工具覆盖的步骤明确未测，不无限追日志或消耗额度，不声称可见剩余额度。
恢复：AI_COMMAND_CENTER→本Task/Review→Git→唯一full原summary/实际进程。full已经完成，纯资料改动不重复运行。

## 最终独立接受与公开审计

gate_review从原件核唯一full210文件/单attempt/rawSHA/退出/cleanup/原skip、当前/领域/snapshot487绑定、RED仅boss差异、原209counts不变及资料边界，独立终审0 MUST。公开审计逐新增文件、每个新提交路径与添加行、新文件blob；准确9路径只代码/测试/项目文档/脱敏结构化结果，投影/链接/diffcheck通过，未增raw/完整summary/profile/EXE/机器用户名/私密或密钥。通过后正常提交、fresh fetch核保护/checks和他人变更，再按本周授权push/安全集成；初接受检查点尚未合并；随后已集成、未发布。纯资料改动不重跑同源full。

## 正常集成回执

全部新提交/准确9路径公开边界审计通过后，按本周有界授权普通push同名分支并设置upstream；fresh fetch核main仍7ff2257，无保护/required checks/rulesets后正常FF，ls-remote核main与fix/boss-timer-lifetime-20261021均4ce2cfe20dada7c3ed63078e10ddccd166a235b9，本地main同步、工作区clean。候选check-runs/statuses/Actions均0，不称CI通过。未强推/绕保护/提PR/删分支/发布。之后只在同9路径中更新四份纯文档回执，487源不变、无需重跑full；本段记已核候选，最终回执leaf完整SHA由Gitrefs及本地delivery-receipt记录。原始诊断/RED/领域/唯一full保留，完整GUI/新EXE/自然退出/LAN/其它DPI/硬件仍未测。

合并checkout后第一次raw源码后验失败：仅boss.py从已验收CRLF变为LF。核checkout字节、full快照按CRLF→LF归一化均精确等当前Git blob，才从已验收快照恢复原raw字节；无代码逻辑变化、无重跑full。恢复后487逐hash与原full一致、Git clean。原/恢复SHA与差异保留本地eol-checkpoint，公开仅脱敏结构化元数据，不覆盖原测试证据。
