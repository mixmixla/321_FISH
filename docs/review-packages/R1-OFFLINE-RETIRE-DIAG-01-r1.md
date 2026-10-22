# R1-OFFLINE-RETIRE-DIAG-01 r1

2026-10-22 **AI_ACCEPTED_OFFLINE_RETIRE_DIAGNOSTIC_ONLY / FINAL_REVIEW_0_MUST / NOT_MERGED**。[Task v1.1](../task-packages/R1-OFFLINE-RETIRE-DIAG-01.md)，base `4a94762d767a1f25e5886d20fc36731d09c04e7d`；分支feature/r1-offline-retire-diagnostic-20261022。root唯一执行/资料写入，r1_review独立设计与探针预审0 MUST。无产品或正式tests改动，不堆叠待合并代码；前批分支和PR403状态保持。

现有覆盖分别证明在线deleted、管理员重连查询、首次hello拒绝、直接Session重开后拒绝。本次补足原目标core离线期间被持久退役后，在新连接epoch停止自动重连，同时另一原core恢复身份与消息的联结场景。

唯一run `offline-retire-diag-20261022-20261022-122310-34311ba5f9`：**1P/0F/0S、actual exit0、3.042s**。Hub1正常停止；无监听Hub2通过真实认证后的控制接口退役目标并正常shutdown；Hub3从同Store重开、同端口提供真实加密TCP。原目标core此前未收deleted/retired通知，新epoch收到retired/manual_login_required后reconnector终止且无新welcome或账号复活；原旁观core以同UID新epoch恢复真实聊天。持久operation_id、retired UID/昵称占用保持，自有core/Hub线程/Store owner全部收口。

准备副本491项（原490+本地探针），实际非Git门禁fallback捕获487项：原486不变+探针；不含`.python-version`、`app.ico`、`tests/_run_all.py`、`tests/_smoke_excel_skin.py`。四项不是此探针执行输入；实际解释器3.14.5及依赖身份与完整基线相同。根490/准备副本490逐SHA保持，run/source与case两份487逐SHA匹配。首次后验脚本误期望491而断言失败，原验证器和失败说明保留；按实际manifest校正核验通过，未重跑探针。Task v1.1仅澄清绑定口径，不扩大验收目标。

单attempt，实际原日志1P、六项观察true、log SHA/原sandbox一致，cleanup true/artifact false，无skip、blocked或remap。该非GUI用例未创建private desktop，不声称可视GUI；随机合成口令不输出。原件与探针仅ignored `_tmp_gui/r1-offline-retire-diag-20261022/` 和对应test-gate run；[脱敏证据](../review-assets/R1-OFFLINE-RETIRE-DIAG-01/evidence.json)。summary SHA `6f86b60584bcf046aab368fa26b6f60280c1ee55be9b90dda5eb1b135eb8e8fd`，probe SHA `603c214beed89e9f98778103a60bed7383745462a21381a334f85e7a813f16d3`。

session36244结束，无活动测试。独立原件/输入绑定/最终五份公开资料终审0 MUST，主控有限AI接受这个诊断场景；不把一次诊断升级为产品修复、正式回归、完整R1/M1、GUI、自然应用退出、LAN或新EXE。已验2984P0F20S完整门禁保持原范围，不重复full。
