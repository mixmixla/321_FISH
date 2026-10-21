# R3-INVENTORY-STRICT-01 r1 — strict清单修复与失败门禁检查点

> 历史独立候选检查点：下列FULL_FAILED/NOT_ACCEPTED/未推合是原批次事实，原件保留。当前已由独立R70-BOARD-WAIT-01确定性诊断/最小修复和组合门禁关闭阻塞，有限AI接受、集成待执行；当前恢复入口见[指挥中心](../AI_COMMAND_CENTER.md)及[R70审查](../review-packages/R70-BOARD-WAIT-01-r1.md)。原inventory分支79bf不移动。

2026-10-21 **FULL_FAILED_GATE_BLOCKED / NOT_AI_ACCEPTED / NOT_MERGE_READY / NOT_R3_ACCEPTED**。
[Task v1.2](../task-packages/R3-INVENTORY-STRICT-01.md) / [脱敏证据/hash索引](../review-assets/R3-INVENTORY-STRICT-01/evidence.json)。base/main `8fc927d4236e588fdb70a7dc40681ab0cff10816`，分支fix/inventory-strict-20261021；初实现5c7c85862b0fefa7228e40f0bfdecbf453b7482d，兼容修正 `adeb83290085468425d974045df30601cec8c53e`。root唯一写入/执行，gate_review独立只读，普通模型/Standard。

## 结果和停止条件

正式清单缺陷已复现并实现：最终11新case全P、领域5文件87P/exit0/26.2s，设计/代码及兼容整改独立复审0 MUST。批次未验收：首full `inventory-full-20261021-202713-32bc343d2c` 2968P1F20原skip/exit1/795.091s，实际新候选final full `inventory-final-full-20261021-204930-84e2540b3b` 再2968P1F20原skip/exit1/795.28s，均212文件完整结束，唯一原tests/test_r70.py:564 1F24P。第二次命中预定停止条件，不再full或r70专项追绿、不改/弱化/skip断言，不推送/合并/发布。只读ls-remote核远端main仍8fc927d4236e588fdb70a7dc40681ab0cff10816、本批远端分支不存在；本地main同SHA，本轮无远端写入。候选未上传，不宣称远端CI。session99983与28195均结束，无活动测试/EXE/构建。
两次断言同为中间榜单bob100/alice3而期待alice7；r70/server/client_core/client/protocol与base/上一full字节相同。干净base原r70一次 `inventory-base-r70-20261021-204231-8bad4cd3f3` 25P/exit0，候选原r70一次compat-red内25P，未复现；同解释器/runner/sandbox/依赖已核。静态两sender无a4→b999服务端处理先后屏障、Collector首个len2匹配，符合合法中间榜单被提前取的时序解释；仍未完整定因，不能称baseline已复现或已证明产品缺陷。两failed full原log/summary/退出/清理均保留，不被控制组PASS抹去。下一只建议独立冻结R70-BOARD-WAIT-01，不混本批实现。

## 实际维护入口与最小实现

local_trial.run_candidate前后profile及_tree_fingerprint实际调用_owned_inventory，非仅一次性脚本；原rglob吞部分OSError返回不完整list。前序PACKAGE partial5/4/4与strict WinError5/正常上下文1020不能解释为删除，本批在owned合成树用可控scandir拒绝验证，不改用户ACL/安全设置或绕限制。
独立设计预审1 MUST发现os.walk同样吞DirEntry.is_dir错误，改直接scandir上下文/child.stat(follow_symlinks=False)/stat分类；metadata/枚举/迭代/读错误原样传播，reparse下降前拒绝，不返回部分list/digest。_is_reparse不再吞metadata错。正式before错误在启动前code5/summary诊断，after先清原四owned Jobs，再code5/scopedfalse/phase/errno/winerror/filename/message，无假空inventory_after；原诊断仅本地。
首strict实现还引入root-first排序边界，已承认并修复：合法!.txt不应先于根'.'。补真实内容及legacy fingerprint断言后compat RED1F10P，仅return一行固定根项、其余相对路径全局排序，正常中文空格/空目录/size/SHA/schema保持。最终生产相对base57+/31-，新11case；未改业务/GUI/协议/构建/依赖/门禁/旧测试/skip，不造框架。

## 版本化验证与原件

既有基线21P；首RED7F3P保留，增加分类/metadata reparse夹具后的旧11case RED8F3P/领域87P也保留。首full失败后，新兼容断言在当前实现RED1F10P（同run原r7025P）；最终同测试字节旧生产RED `inventory-original-final-red-20261021-204501-efcbfe3aa6` 8F3P/finally精确恢复，最终领域 `inventory-domain-final-20261021-204505-af8d4713b2` 87P。设计/代码/领域及root-first复审0 MUST后才提交兼容修正并启动新候选final full，非相同代码重复full。
最终489/source `e8ecc2df345e7141a491c6a508f764fce11ba509149ff6043cc48146eb15a221` 当前/领域/final snapshot逐SHA相等；最终旧生产RED同489仅local_trial.py不同，testSHA `e150c24dcb3d065a23f9262837c72c0234269c42c38129ed80c0e2c11ea37327`完全同字节。首full0e65输入与最终e8ecc输入只生产和test变化；旧211文件除r70仍与前次green full counts相同，新11P未减少旧覆盖。
最终全212各单attempt/原log SHA/真实exit（r70=1，其余0）/cleanup/sandbox JSON/artifact已核；无cleanup失败，20skip仍r45硬件1+ux_visual_chat_shots18+visual_screenshot1，未开opt-in或额外参数。21后验仅验证证据一致，不代表门禁通过；summary SHA `f064208d56a503de0b4f414d57ee8b5ff0a2a6ada58e0972464183cd17e7b787`。故障正式run测试明确seam doubles+4真实owned Python Jobs，不冒充实际EXE/GUI。旧EXE仍2e21156构建，本批未重建/重跑，GUI/自然退出/LAN/其它DPI/正常完整demo等未测，R3未放行。
首次scratch准备相对路径错误未执行，基线仍仅一次；基线worktree创建后八文件仅checkout EOL差异，逐normalized==Gitblob/已验raw并write-tree不变/clean后恢复为488DCF，测试才启动。保存最终绑定有一次CreateProcess前自动审批超时，工具允许的一次重试成功，无额外测试/未决审批。原件O=_tmp_gui/r3-inventory-strict-20261021，包含原/最终binding、双full记录、root-first-fix和owned base-r70-comparison；不改写失败原件。

## 独立审查、拟公开边界和恢复

设计/代码/领域/兼容整改独立0 MUST，最终失败事实/九路径资料独立终审0 MUST，仅允许本地保存事实，不构成AI_ACCEPTED/合并就绪。当前代码和资料仅本地，检查点提交后完整SHA见Gitrefs/ignored delivery-receipt。

| 精确拟公开路径 | 内容 |
| --- | --- |
| `local_trial.py` | Strict formal inventory and local failure diagnostics |
| `tests/test_local_trial_inventory.py` | 11 controlled fault/normal compatibility/formal-run tests |
| `docs/task-packages/R3-INVENTORY-STRICT-01.md` | Frozen scope and versioned correction/stop condition |
| `docs/review-packages/R3-INVENTORY-STRICT-01-r1.md` | Actual results, failed gate, independent review and recovery |
| `docs/review-assets/R3-INVENTORY-STRICT-01/evidence.json` | Sanitized outcomes/raw hash index |
| `docs/AI_COMMAND_CENTER.md` | Authoritative blocked state and next priority |
| `docs/任务清单.md` | Generated roadmap projection |
| `PROJECT_MEMORY.md` | Implemented candidate inventory contract |
| `.agents/skills/fish-assistant-dev/references/development.md` | Existing strict-inventory development guidance |

本周许可仅代码/测试/项目文档/脱敏摘要，准确9路径及全部新commit历史需审；原日志/完整summary/profile/inventory/控制器/用户名/私密/密钥/二进制不公开。本轮不推送/合并/PR/发布，不绕保护或删分支。下一P1 R70-BOARD-WAIT-01 DRAFT：确定性复现等待竞态、保留全部积分/排序/快照断言再作最小整改，需单独冻结；门禁解决后P2 R3-STRICT-PREFLIGHT-01新工具+同hash包实际预检，不重建或造框架。恢复先AI_COMMAND_CENTER/本Task/Review/Git/双full原summary/progress与实际进程，不新启动测试追绿。

## R70组合关闭阻塞（后续检查点）

独立R70代码9d6d1de92998e85d73923ff91acb45a46ee0320f，从79bf依赖分支推进且不改inventory代码/测试；受控真实RED确认原wait提前选合法中间榜单，保留所有语义断言后最小整改。组合唯一full r70-wait-full-20261021-214111-6d59409cd3 213文件2971P0F20原skip/exit0、490输入当前/领域/snapshot相同，最终独立原件/资料0 MUST。主控仅有限AI接受两项组合，尚待安全集成，不改变本文件原双failed结果及旧control未复现事实。
