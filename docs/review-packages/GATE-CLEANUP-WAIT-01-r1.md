# GATE-CLEANUP-WAIT-01 r1 — 等待自有进程实际退出

2026-10-22 **AI_ACCEPTED_RECONNECT_AND_OWNED_EXIT_ONLY / FULL_PASSED / FINAL_REVIEW_0_MUST / BRANCH_PUSHED / PR_CREATE_BLOCKED_403**。
[Task v1](../task-packages/GATE-CLEANUP-WAIT-01.md)。base ddf1c79b0143890a4c98941b6b5b500b6909e761；交付HEAD以Git refs为准，feature/r1-restart-reconnect-20261021。root唯一实现/执行，r1_review独立设计与代码审查。

## 问题与变更

R1正常重启续连回归的原完整全量2971P1F20S/exit1，唯一失败是内层超时清理无法确认，原日志只记录cleanup false。它没有记录taskkill或Win32各分支细节，不能断言原失败精确归因。原失败、恢复前189完整记录及人工中断的test_server attempt均保留，见[R1 Review](R1-RESTART-RECONNECT-01-r1.md)。

源码存在独立可证实的时序缺陷：Popen.kill或TerminateProcess发出终止请求后立即poll，在进程尚未退出时返回false。最小修改只在已持有的对象/句柄上wait(timeout=10)，再校验最终poll和原先观察到的全部子进程。wait异常/超时、退出状态未知和descendant未确认退出仍失败；不扩大kill范围、改权限/ACL、弱化assert或新增skip。

## 验证与独立审查

受控回归覆盖Popen/native各自的延迟退出、等待超时、等待异常、退出未知和descendant未知；另两项使用真实合成自有进程，在taskkill不可用替身下验证持有句柄回退清理。夹具finally恢复taskkill后完成自有收口，清理异常保留于原失败。

旧实现配同字节最终测试的RED `cleanup-wait-red-20261022-20261022-115644-c8fb9b86a8` 为11F9P/exit1：两种受控exited和真实Popen返回失败；8个负路径因未执行有界等待断言失败，不表示旧实现误判成功；真实native旧实现当次通过。RED/current490输入仅test_sandbox.py不同。

六文件领域 `cleanup-wait-domain-20261022-20261022-115709-e290982259` 为78P/exit0/41.338s，source `5da85d93290d1d794f83fb3415777b306aae14bf563d10ade49e699197db972f`；包含client_core、gate_boardgames、test_gate、test_gate_safety、test_gate_skips、test_runner_exitcodes。独立设计/代码/RED审查0 MUST。唯一新组合全量已完成；独立原件和拟公开资料终审0 MUST，主控据此有限AI接受正常重启续连与自有测试进程退出确认。

原件仅本地 `_tmp_gui/gate-cleanup-wait-20261022/` 和 `_tmp_gui/test-gate/` 对应run。仅公开脱敏摘要与哈希，不公开原始日志、profile、用户名、密钥、二进制。

## 历史审计与范围

历史审计的具体发现仅在本地报告，不复制私人路径或凭据内容。相关问题已存在于本轮开始前的远端main祖先，发现时本任务未提交或推送；后续边界澄清允许与既有问题无关且完整审计干净的新增代码与脱敏摘要按原授权集成；不重传含敏感内容的对象、不重写历史、不轮换部署凭据。新增待交付路径及完整新增commit历史仍须独立审计。

本批只修门禁退出确认并补R1正常重开续连证据。真实Tk/协议不等于可视GUI、自然应用退出、跨机器LAN或新EXE验证，不升级R1/M1/R3或发布状态。


## 完整组合门禁与有限验收

唯一新full `cleanup-wait-full-20261022-20261022-115804-1d35944577`：213文件 **2984P/0F/20既有skip，actual exit0，799.928s**。当前/领域/快照490输入逐SHA相同，source 5da85d93290d1d794f83fb3415777b306aae14bf563d10ade49e699197db972f；全部213单attempt、logSHA、sandbox、cleanup、artifact及15项后验均通过。未受影响文件counts和全部既有skip保持；新增12个清理case，原门禁自测恢复通过。原R1 failed summary SHA仍e8ff6d805cdb7b3897979bc2408a5e03300e60c39237b2b1bd6b2a0475e23e69，189原通过记录及所有恢复前日志未改。

完整summary SHA `050127fa0bc0e93d4680786fef4b0423c53d9b33cb246c14e8eff92824b7622b`；[脱敏结果/逐文件哈希](../review-assets/GATE-CLEANUP-WAIT-01/evidence.json)，原完整summary及final-validation仅本地。session55738已结束，无活动测试；r1_review独立重算上述原件、490输入、213公开投影、原失败保留和文档边界，终审0 MUST；主控记录AI_ACCEPTED_RECONNECT_AND_OWNED_EXIT_ONLY，不代表用户/Pro或R1/M1/R3整体验收。下一核全部新增对象、提交元数据和远端策略，再正常PR集成；不重复全量。

## 交付检查点（2026-10-22）

交付候选24c65c26b7d8284a595729f292ba97fbf5104b06已普通push到feature/r1-restart-reconnect-20261021，ls-remote核一致；main仍ddf1c79b0143890a4c98941b6b5b500b6909e761。全部26新增对象（1commit/12tree/13blob）和元数据独立审计0 MUST，490输入保持已验字节。创建PR的GitHub连接器返回403 Resource not accessible by integration；只读查询同head的open PR为空，未创建PR/未合并，未重试或直接push main。候选check-runs/status contexts/Actions均0，aggregate pending/total0，不称CI通过。下一需恢复具有PR写权限的受支持连接，再核分支/保护/未重复PR后正常创建与合并；无需重跑测试或重建。仅本次脱敏交付回执继续提交到同分支，最终leaf以Git refs为准；没有活动测试。
