# COORD-01 — 协作入口与交接资料

任务包版本：v1，2026-10-01（Asia/Shanghai）。本文件只保存冻结需求；执行状态见
[AI_COMMAND_CENTER](../AI_COMMAND_CENTER.md)。

## 目标与授权依据

用户要求按《321_FISH 协作与持续开发方案》（2026-10-01）进行，本批采用其第十节
“最小落地批次”：建立文件入口、迁移脱敏 CC-01A 材料、分离状态与长期记忆，
验证新上下文只依靠文件可以恢复。原方案在本机可读，仓库保存整理后的需求而非私有聊天全文。

批准批次仅含本任务。后续代码、Goal、heartbeat、对 Pro 聊天发消息分别需要明确启动。

## 基线与保护边界

- 工作区：`D:/Project/321_FISH`；分支 `fix/cc-01a-admin-credentials`。
- HEAD / 本地 `origin/main`：`fbdd915e8fd5947e01b6f4d371b3cd1e37020729`；未 fetch。
- 入场为 dirty：20 个 tracked 修改、2 个 untracked 新文件；22 文件清单/内容 hash
  迁入 [CC-01A 基线](../review-packages/CC-01A-baseline.md)。
- 入场完整补丁 SHA-256：`49e1f238774a25c8557c9465ba28b00013322bce5f2f096c3a8ccba189ad8c6e`。
- 入场内容集合 SHA-256：`607471b077692fb1ff17b836904b6556501ad5e66ccdb6da06cbbe4ec7d43d6d`。
- 原始补丁/manifest 在 ignored 的 `_tmp_gui/coord-01/`，不作为状态权威，不入公开资料。

## 范围与文件所有权

| 文件 | 责任 |
| --- | --- |
| `AGENTS.md`, `docs/AI_COMMAND_CENTER.md` | 主控建立启动/恢复与队列 |
| `docs/task-packages/COORD-01.md`, `docs/review-packages/COORD-01-r1.md` | 主控冻结本批需求、汇总证据 |
| `docs/task-packages/CC-01A.md`, `docs/review-packages/CC-01A-r1.md`, `docs/review-packages/CC-01A-baseline.md` | 资料实现代理迁移历史需求/证据，标明缺口 |
| `PROJECT_MEMORY.md` | 主控迁出临时状态/测试数字，保留稳定事实与证据索引 |
| `COLLABORATION.md` | 主控补充角色/状态权威、测试分层与 dirty 恢复规则 |

不修改应用源码、测试或运行入口；不自动验收 CC-01A，不处理 R26/R43A 代码，
不执行候选开发、不删测试、不修改真实用户数据。其它已有文件必须与入场内容一致。
`PROJECT_MEMORY.md` 与 `COLLABORATION.md` 的本批增量单独保存，保留原有 CC-01A 交付内容或迁移出处。

## 允许操作与交付

允许只读源码/日志、上述文档编辑、本机 ignored 补丁/检查报告、只读独立代理审查。
本批不自动本地 commit、不推送、不创建 PR、不合并、不发布、不发外部消息。
未提交资料绑定入场基线 + 本批文档内容清单/补丁 hash，明确 dirty；与 CC-01A 分开记录。

## 验证与验收条件

1. 从 AGENTS → 指挥中心 → 当前 Task/Review → git 差异能确定目标、边界、版本和下一动作。
2. 状态只有指挥中心维护；CC-01A 的历史全量失败、待验收、未提交/推送/合并均明确保留。
3. 历史材料包含测试命令、环境、数量、失败、复测与来源；无法证实的版本绑定/基线归因标为缺口。
4. 相对文档链接存在，`git diff --check` 通过，资料不复制真实凭据或用户数据。
5. 除明确允许修改的两份既有文档，其余 20 个入场文件逐字节不变；无新增应用/测试修改。
6. 新上下文只读独立审查完成，无未关闭必须修复项；证据绑定可识别的资料版本。

纯文档批次不运行应用全量。检查脚本留本地，脱敏结果进入 Review Package。
文档检查通过只证明本任务，不能使 CC-01A 门禁或 R0 里程碑通过。

## 需求变更

v1 为用户方案中第一批的具体化。扩展范围必须记录 v2 与新的用户决定；
审查修正文案/证据缺口不扩展应用需求。
