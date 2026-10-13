# TRIAL-EVIDENCE-REFRESH-01 v1 — 试用证据与游戏分类资料校正

2026-10-13。用户明确授权本资料任务写入独立 worktree、校对后 commit，交主窗口整合；不单独 push/PR。冻结基线 `08d263b2a78b7a6df0b888616e2fbf44793182b8`，分支 `docs/trial-evidence-refresh-20261013`。执行状态与队列仍由主窗口的[指挥中心](../AI_COMMAND_CENTER.md)维护，本包不新增第二套 READY 队列。

## 目标与所有权

根据当前源码，撤下已失效的桌面拦截、动作缺失与旧 Web outerHTML 标签；区分源码入口覆盖、历史分层实验、当版完整交互、EXE、外机和发布接受。保留仍能由当前源码确定的缺口，不把解除拦截等同完整可玩。

本窗口仅写以下资料：

- `docs/游戏完成度地图.md`
- `docs/游戏UI与资源现代化-任务清单.md`
- `docs/试用验收分类_2026-10-13.md`
- 本 Task、`docs/review-packages/TRIAL-EVIDENCE-REFRESH-01-r1.md`
- `docs/review-assets/TRIAL-EVIDENCE-REFRESH-01/static-audit.json`

主窗口独占 GemCity 生产代码、购买测试及门禁证据，治理文档 `AI_COMMAND_CENTER.md`、`任务清单.md`、`PROJECT_MEMORY.md` 也由主窗口维护。本窗口不改原目录未提交内容；本 worktree 不带入 GemCity 未提交修订或 CP4 实验模块。

## 冻结行为

1. 以 AST/源码文本核对47项标签、动作配置、点击分发、画师、Web renderer及空拦截集，记录基线、行号、源文件哈希与核对方法。仅解释静态覆盖，不执行项目模块或玩法。
2. 当版地图不沿用10月3日14项桌面禁入/2项Web旧原因；两旗舰旧实验结果单列历史，当前完整GUI/EXE未验保持。仍存在的Kalah第二方洞映射、Balatro私有文本等具体缺口保留。
3. 现代化清单作为规划与源码覆盖视图，注明后续提交已覆盖哪些旧事实；去掉其它机器的 file 链接。不将P0/P1/P2整章置为实施授权或验收完成。
4. 新验收分类表保存旧朋友候选的2247P/0F/2原skip、三EXE/便携包等版本边界；不把它们作为08d263b通过证据。PR7/8合并与旧403记录分开，原Review不改写。
5. 保留历史gate FAIL、CP4根因未定、完整EXE键鼠/自然退出、125%/150%环境、非开发Windows及物理LAN待验。主控当前GemCity full不由本任务归档或改判。

## 验证与交付

- 纯文档检查：47 key集合及行数与静态JSON一致；分类计数准确；源码/证据链接存在；基线精确；相对链接可用；不含另一机器file URI、真实资料、原始运行日志或秘密。
- `git diff --check`；差异只含上述6资料，所有生产/测试/依赖、治理文档和旧Review保持基线。
- 独立只读审查从本Task、实际diff、源码与既有证据开始；整改MUST后记录结论。实现者不自行写AI_ACCEPTED，技术接受/整合由主窗口决定。
- commit到本独立分支，交付SHA与文件清单；不push、PR、merge、发布、构建、运行应用或应用测试。
- 15:00北京时间前收尾，14:30后不开大任务。
