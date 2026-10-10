# UX-VISUAL-PR-01 v1 — 本轮视觉增量草稿 PR

2026-10-10（Asia/Shanghai）。用户明确要求“本轮可以先提交PR上去”。本批仅整理、验证和提交当前已有视觉增量，不将尚未完成的视觉工作改写为已验收。

## 范围和版本

- 开发工作区 HEAD c864234e09f97a32e3df871b5bd7c13312adeed7，原分支/未提交资料完整保留，不 pull/reset/stash 或自动提交继承的账号/存储实现。
- 已核 PR #6 与 #7 均 merged；目标为最新 main 7d6a98cbdd8c62f5d5af4d5b9a4a7e6be0663758。使用独立 checkout，分支 codex/ux-visual-chat-20261010。
- 仅转移 [UX-VISUAL-CHAT-01 v1.5](UX-VISUAL-CHAT-01.md) 相对入场的视觉增量。七个既有生产/门禁文件的入场版本与最新 main 经 CRLF→LF 比较均一致，可直接转移当前文件；新统一样式/图标模块、四个专项测试、两份生产 JS 探针与必要设计/证据随行。
- main 尚无 local_prefs.py 与 test_local_prefs_rules.py；不为视觉 PR 携入未接线账号模块或该独立模块测试的引用数修订。此本地修订仍保留在开发工作区。
- 保留最新 main 的朋友试用/便携入口及其资料；指挥中心只追加本批，不用旧开发中心覆盖远端历史。

## 授权和所有权

用户本次指令授权本批必要的 commit、普通 branch push 和创建 Draft PR。root 唯一实现/资料写入者，代理独立只读审查范围和公开安全；不改应用行为、不整改后继 UI、不恢复旧账号 Goal。旧 Goal paused 不变。

不 merge/自动合并/tag/Release/部署，不 force push/main push，不上传 EXE、真实 prefs/history/Store/凭据、运行状态、私有聊天或 TLS 私钥。只发布经审查的合成图片；阶段图片明确标版本，不能冒称最终版前后验收。没有读取凭据文件或要求扩展权限的必要。

## 检查与交付

- 保存开发入场公开文件逐字节身份，明确转移清单；检查独立分支相对 main 实际 diff，不混入继承的业务改动或删除已合并入口。
- 对独立 PR 源码运行视觉/主题/消息/会话/输入/设置/Excel/门禁相关领域验证，保存原退出码/日志哈希/候选身份。最终 full/EXE/原生矩阵尚未完成，不能用旧开发或 PR #7 结果证明本候选全绿。
- 草稿中公开两个未关闭导航 MUST、Python/Tk 合成预览 fatal 尚未定因、尚未完成的全部桌面页面/独立视觉/125%和150%/EXE/外机/LAN。保留旧失败，Draft 不是可合并或发布状态。
- 独立范围/敏感资料复核完成后提交明确路径，普通 push；创建后核本地/远端/PR head 与 draft/base 状态并 attach 当前聊天。
- 最终更新 [Review](../review-packages/UX-VISUAL-PR-01-r1.md) 和 [指挥中心](../AI_COMMAND_CENTER.md)，同步任务清单。本批到 PR 交付停止，后续视觉仍按原 Task 推进。
