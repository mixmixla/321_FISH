# R3-STRICT-PREFLIGHT-01 v1 — 现行严格清单驱动旧同哈希包

2026-10-21。base/main `6add1065c3ebc6f43242ca2b85fbb331be009680` clean；分支 `feature/r3-strict-preflight-20261021`。本批只验证主干当前 `local_trial.py run` 对旧构建七文件包的真实 EXE 正向路径，不改产品、工具、测试、依赖或构建，不重跑已通过的源码全量。不修改 ACL/安全设置，不绕过枚举拒绝；原始日志、profile、完整 summary、二进制只留 ignored 本地目录。

验收标准：原包保留；仅复制七白名单文件到新目录，并逐文件核原件/副本 SHA 与 `SHA256SUMS.txt` 的六条记录。明确三 EXE 构建基线 `2e2115647940a4025e99f7fcdd112e1fdc9ae416`，当前工具基线 `6add1065c3ebc6f43242ca2b85fbb331be009680`，不宣称重建。正式入口不传 exe override 或 mock，以隔离 profile/private desktop/loopback 启动实际 server.exe 与双 client.exe；initialize、TCP、HTTP、两个实际登录、现有 wire 两棋与双 peer 清理通过；before/after profile 严格清单成功、无 `profile_inventory_error`；四 owned Job active_after=0 且 close 成功，工作包七文件不变。任何访问/枚举错误须报告原阶段和错误，不将不完整清单当通过。强制清理不记自然退出。完整 GUI、自然退出、物理 LAN、异机/其他 DPI、新 EXE 不在本批接受范围。

实际仅执行一次 `run`：`run-20261021-141629-740d2eb77b` exit0，六项启动/协议探针均 true；wire welcome、双 chat、gomoku/connect4 完整流程及两个 peer 清理通过。server/client/client_beta after_wait 均运行，四 owned Job active_after0/close true，profile before 各5条、after 为1081/1076/1076条，strict 扫描未报错。本工具对无源码包的 source manifest 仅覆盖一项，`source_unchanged` 不代表整包完整性；独立七文件逐 SHA 校验补足本批整包绑定。原始 `summary.json` SHA `96df4c882d9e9094de38a775c7aceb842ef0f2ed874cd19b9373ede7d8402818`，原件路径 `_tmp_gui/r3-strict-preflight-20261021/runs/run-20261021-141629-740d2eb77b`。这是合成双客户端/协议预检，并非 GUI 或自然退出验收。无代码改动，不重复全量。

有限验收和独立审查结论见 [Review r1](../review-packages/R3-STRICT-PREFLIGHT-01-r1.md) 与 [脱敏索引](../review-assets/R3-STRICT-PREFLIGHT-01/evidence.json)。公开仅本 Task、Review、脱敏索引、现有 AI_COMMAND_CENTER 和任务清单；全部新增历史审计后按本周有界授权正常推送与安全快进 main，不上传原始证据/包，不发布、不强推。若检查不满足则停止集成。

独立只读终审核原 summary、七文件 SHA/校验单、五份拟公开资料与任务优先级：**0 MUST**。主控仅 AI_ACCEPTED_ACTUAL_OLD_BUILD_EXE_PREFLIGHT_ONLY；正式质量通过不等于远端集成，Git/CI 回执待后补。
