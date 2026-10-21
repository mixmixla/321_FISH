# R3-INVENTORY-STRICT-01 v1.2 — 正式预检清单枚举失败可见

2026-10-21冻结READY；当前FULL_FAILED_GATE_BLOCKED / NOT_AI_ACCEPTED / NOT_MERGE_READY。用户明确推进；base/main8fc927d4236e588fdb70a7dc40681ab0cff10816 fresh fetch同SHA/clean；fix/inventory-strict-20261021。root唯一实现/执行/文档写入，gate_review独立只读，普通模型/Standard。本周仅代码/测试/项目文档/脱敏摘要公开与正常安全集成授权，排除raw/用户名/私人资料/密钥/profile/二进制，不发布/强推/绕保护/删分支。

## 实际归属和冻结范围

正式local_trial.py run调用run_candidate：运行前后profile清单均用_owned_inventory，_tree_fingerprint也复用此函数。当前Path.rglob可能吞掉OSError而返回部分列表；前序PACKAGE受限5/4/4视图与strict WinError5/正常上下文1020的原证据已保存，不能解释为文件删除。本批不是修改一次性控制器。
仅将该函数改为严格单次scandir遍历、枚举/分类/metadata原错误传播，保持相对路径/目录size0与sha null/文件size及SHA/根项固定首位、其余路径字典序、reparse拒绝和不跟随语义。目录枚举/迭代/读取失败不能返回部分清单或fingerprint。正式run运行前失败应在启动前非0且summary保留阶段/错误诊断；运行后失败不得写虚假空inventory_after或scoped=true，仍先清全部owned Job并返回非0/保留诊断。正常路径兼容，无新框架、业务/协议/GUI/构建/依赖/门禁/旧skip修改。

## 验收

先运行既有相关基线；新受控scandir夹具覆盖root、nested及枚举中途PermissionError（errno/filename原异常不丢失）、fingerprint失败、正常中文空格/空目录/排序hash、reparse拒绝不下降、读失败。只合成owned测试树，不动用户ACL/安全设置、不绕限制。正式run错误传播测试明确seam doubles，运行后路径使用真实owned Python Job及既有harness_scene，非EXE/GUI验收。
新最终测试同字节基线RED→最小实现→受影响领域回归/独立代码与原件审查→一次最终默认全量。不得用mock冒充真实EXE或GUI，不为工具修复重建/重跑已验EXE；包构建仍2e21156，完整GUI/自然退出/LAN/其它DPI/正常完整demo未测保持。
每步复用中心/本Task/Review，raw只本地ignored _tmp_gui/r3-inventory-strict-20261021及test-gate。本批公开local_trial、新专项测试、本Task/Review/脱敏索引、中心及其投影，必要稳定记忆/技能参考；最终逐精确路径及所有新commit历史审计。独立0 MUST、适用门禁通过后有限AI接受，再fresh fetch/保护/required checks核、正常push/安全FF及远端完整SHA/可见CI；无CI不是CI PASS。终点为这一小增量，不扩产品。

## 设计审查 v1.1

独立预审确认正式入口归属，但指出os.walk也会吞DirEntry.is_dir的OSError（1 MUST）。因此采用直接scandir上下文+不跟随stat分类的有界栈，逐项传播原错误而非onerror技术偏好；补分类失败回归，并保留reparse下降前拒绝。首RED7F3P保留，最终11case原代码RED8F3P；只普通技术修正，任务目标和公开边界不变。

## 兼容性与首门禁检查点 v1.2

首候选full inventory-full-20261021-202713-32bc343d2c完整结束2968P1F20原skip/exit1/795.091s，唯一r70:564中间榜单bob100/alice3原件保留，不能当绿。干净base488DCF owned worktree原r70一次25P，候选原r70一次25P，均未复现；静态有跨sender首个len2事件竞态，仍不是baseline已复现。无r70/业务/skip修改，不继续重复r70追绿。
另复核发现本实现把合法!.txt排到根项前，违背legacy根项固定首位。补真实内容/fingerprint兼容断言后，当前实现RED1F10P（同run原r7025P），原legacy生产最终同测试RED8F3P；只修return一行固定根项、其余全局相对路径排序。原始红绿/full记录全部保留，代码版本实际变化后才重新领域/独立复审/唯一最终候选full；若r70再失败则停止门禁/合并，不循环full。属于本清单兼容目标的普通技术整改，不扩大产品任务。

## 最终失败检查点

最终代码adeb83290085468425d974045df30601cec8c53e/489 sourcee8ecc2df345e7141a491c6a508f764fce11ba509149ff6043cc48146eb15a221，最终同测试原生产RED8F3P/领域87P和兼容整改独立复审0 MUST；首候选full2968P1F20S/795.091s保留，新候选full inventory-final-full-20261021-204930-84e2540b3b 再2968P1F20S/exit1/795.28s，均唯一原r70:564。命中预定停止条件：不再full/专项追绿，不改/skip r70，不AI接受/推送/合并/发布。session28195结束，无活动测试；最终失败事实/九路径资料独立终审0 MUST，仅完成本地保存；仍NOT_AI_ACCEPTED/NOT_MERGE_READY。完整GUI/自然退出/LAN等未测不变。下一R70等待契约需另冻结，不能混本批。
