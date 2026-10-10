# UX-VISUAL-PR-01 — Draft PR 交付记录

2026-10-10，依 [Task v1](../task-packages/UX-VISUAL-PR-01.md)，实际状态见 [指挥中心](../AI_COMMAND_CENTER.md)。用户要求先提交本轮 PR，原开发目录/未提交资料保留。

远端只读核对 PR #6/#7 已 merged，main=7d6a98cbdd8c62f5d5af4d5b9a4a7e6be0663758。PR #7 的2247 PASS/2 opt-in与便携包不作为新视觉候选测试结果。七个既有转移文件在视觉入场与 main 的 LF 规范化版本一致；本 PR 只转移视觉增量及必要资料。未接线 CP4 模块、其本地测试和账号/存储 dirty 原样保留，不随视觉 PR 发布。

已有开发源码的领域 r5 171 PASS/1 FAIL，r6 探针/门禁修订25 PASS已记录在[视觉 Review](UX-VISUAL-CHAT-01-r1.md)；这些属于开发版本历史。独立 main 候选的验证、公开边界复核、commit/head、push/PR URL 待实际完成后补录。

已知两个导航 MUST、预览 Python/Tk fatal、完整视觉/全量/EXE/DPI矩阵未完成继续保持；本交付不记录 AI_ACCEPTED/可合并/发布或用户审美认可。

## 独立候选验证和边界

独立PR候选领域18文件165 PASS/1 FAIL/0 SKIP，exit1/418.967秒；source f13f45bf068641eb3e6135fca6c0eab9956e121259ee2e4a8a1d0d9f9aa0cb42。18个单attempt、raw日志SHA/cleanup/no unexpected skip已核。不是最终full/EXE/视觉接受。唯一FAIL为test_gate_preserves_timeout_and_collection_empty_statuses：嵌套3秒门禁的broken语法用例实际timeout、期望collection；原因尚未定，不改断言/跳过或重试覆盖。保留本FAIL，Draft不可合并。详见[领域证据](../review-assets/UX-VISUAL-PR-01/domain-evidence.json)。

[范围审查](../review-assets/UX-VISUAL-PR-01/scope-review.md)确认有限delta及描述边界；[公开资料审计](../review-assets/UX-VISUAL-PR-01/public-audit.md)未发现本增量秘密值/非合成截图。[阶段图片与当时源码SHA](../review-assets/UX-VISUAL-PR-01/stage-screenshots.md)保留真实版本差异，不当最终11pt/DPI/EXE对照。main中心历史保留，仅新增视觉/交付块，并从状态源再生任务清单。

managed worktree创建持续creating、attach归属失败，未使用/修改/删除其checkout；实际候选在ignored目录独立clone完成，不改原HEAD/分支/业务dirty。提交和远端事实在完成后另补。
