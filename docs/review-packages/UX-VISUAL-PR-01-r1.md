# UX-VISUAL-PR-01 — Draft PR 交付记录

2026-10-10，依 [Task v1](../task-packages/UX-VISUAL-PR-01.md)，实际状态见 [指挥中心](../AI_COMMAND_CENTER.md)。用户要求先提交本轮 PR，原开发目录/未提交资料保留。

远端只读核对 PR #6/#7 已 merged，main=7d6a98cbdd8c62f5d5af4d5b9a4a7e6be0663758。PR #7 的2247 PASS/2 opt-in与便携包不作为新视觉候选测试结果。七个既有转移文件在视觉入场与 main 的 LF 规范化版本一致；本 PR 只转移视觉增量及必要资料。未接线 CP4 模块、其本地测试和账号/存储 dirty 原样保留，不随视觉 PR 发布。

已有开发源码的领域 r5 171 PASS/1 FAIL，r6 探针/门禁修订25 PASS已记录在[视觉 Review](UX-VISUAL-CHAT-01-r1.md)；这些属于开发版本历史。独立 main 候选的验证、公开边界复核、commit/head、push/PR URL 待实际完成后补录。

已知两个导航 MUST、预览 Python/Tk fatal、完整视觉/全量/EXE/DPI矩阵未完成继续保持；本交付不记录 AI_ACCEPTED/可合并/发布或用户审美认可。

## 独立候选验证和边界

独立PR候选领域18文件165 PASS/1 FAIL/0 SKIP，exit1/418.967秒；source f13f45bf068641eb3e6135fca6c0eab9956e121259ee2e4a8a1d0d9f9aa0cb42。18个单attempt、raw日志SHA/cleanup/no unexpected skip已核。不是最终full/EXE/视觉接受。唯一FAIL为test_gate_preserves_timeout_and_collection_empty_statuses：嵌套3秒门禁的broken语法用例实际timeout、期望collection；原因尚未定，不改断言/跳过或重试覆盖。保留本FAIL，Draft不可合并。详见[领域证据](../review-assets/UX-VISUAL-PR-01/domain-evidence.json)。

[范围审查](../review-assets/UX-VISUAL-PR-01/scope-review.md)确认有限delta及描述边界；[公开资料审计](../review-assets/UX-VISUAL-PR-01/public-audit.md)未发现本增量秘密值/非合成截图。[阶段图片与当时源码SHA](../review-assets/UX-VISUAL-PR-01/stage-screenshots.md)保留真实版本差异，不当最终11pt/DPI/EXE对照。main中心历史保留，仅新增视觉/交付块，并从状态源再生任务清单。

managed worktree创建持续creating、attach归属失败，未使用/修改/删除其checkout；实际候选在ignored目录独立clone完成，不改原HEAD/分支/业务dirty。提交和远端事实在完成后另补。

## 实际PR交付（2026-10-10）

- 明确42路径提交19e1fa10685e70abcc37c3ca23d161dc484e7ebf，369受测输入逐路径按Git实际filter映射与index一致；没有代码/测试修改。普通push codex/ux-visual-chat-20261010成功，remote HEAD一致、main保持7d6a98c。
- 连接器创建返回403 Resource not accessible by integration；没有读取凭据或扩大权限。已有Chrome登录会话正常页面填写准确正文并选择Draft，实际创建[PR #8](https://github.com/mixmixla/321_FISH/pull/8)，随后read-only connector核open/draft=true/merged=false/base main/head19e1fa1，已attach当前聊天。
- 领域原165P/1F/0skip/exit1保持。只读诊断核嵌套broken已打印SyntaxError/1 error in1.53s、empty已打印no tests ran，子进程未在3秒期限内结束，runner依真实timeout强制清理；为何未及时退出仍UNDETERMINED，不把历史r6绿替代或认定UI根因。
- 后续本交付记录只更改资料/状态源及投影，不重新测试不变输入，不改Draft为ready，不merge/tag/Release/部署或上传二进制。原开发HEAD c864234/branch/应用测试与全部继承dirty保持，旧账号Goal paused。

[结构化回执](../review-assets/UX-VISUAL-PR-01/delivery-receipt.json)保存创建身份和截图hash；截图仅本地，浏览器页面已保留为可查看结果。后继仍从当前视觉Task闭两导航MUST和门禁FAIL，再完成full/同版EXE/独立实际视觉及其他桌面页面，不将本次PR交付当产品接受。
