# R3-STRICT-PREFLIGHT-01 r1 — 实际 EXE 正向预检

2026-10-21。base/main `6add1065c3ebc6f43242ca2b85fbb331be009680`；`feature/r3-strict-preflight-20261021`。**实际验证 PASS / 独立终审 0 MUST / NOT_R3_ACCEPTED**。本批无产品代码、测试、构建变化；仅五份项目文档及脱敏索引待审。沿用 prior 组合全量 2971P0F20S/exit0，不把它冒充本次 EXE 验收，也不无意义重跑。

旧包构建基线 `2e2115647940a4025e99f7fcdd112e1fdc9ae416`，本次驱动为 main `6add1065c3ebc6f43242ca2b85fbb331be009680`，不是新 EXE。七文件新副本与原包逐 size/SHA 相同，六个校验条目吻合；本次正式工具 `source_manifest` 只见一项，所以独立整包 SHA 校验不可省。正式 `local_trial.py run` 仅一次，run `run-20261021-141629-740d2eb77b`：实际 exit0，private desktop 可用、initialize0、TCP、HTTP、两实际 client 登录及 wire 均通过。wire 包括两 peer、双 chat、gomoku/connect4 终局/复位/离房，socket cleanup 均通过。server/client/client_beta after_wait 仍运行且映像匹配；四个自有 Job active_after0/close true。三个 profile 严格 before/after 清单均产生，`profile_inventory_error=null`，`profile_paths_scoped=true`；包七文件仍同哈希。原 summary SHA `96df4c882d9e9094de38a775c7aceb842ef0f2ed874cd19b9373ede7d8402818`，完整原件在 ignored `_tmp_gui/r3-strict-preflight-20261021`，公开只列脱敏字段和哈希。

验收边界：owned Job kill-on-close 是强制清理，不能称自然应用退出。loopback wire 与实际双客户端登录不等于完整 native GUI、物理 LAN、异机、其他 DPI、硬件/STT或新构建 EXE 通过；不升级 R3。无 ACL/安全设置变更、无软件安装。已通过源码全量不重复；本批独立原件/公开边界审查后才可有限 AI_ACCEPTED。

下一有用户价值的候选：R1 已列的 M1 客户端/重启异常边界仍延期；宜选一个真实断线或重启后数据/会话一致性失效条件，先做协议与持久化可控复现，再决定是否修复。它与 GUI 验收独立。31 项桌面游戏主要操作尚未验证、两旗舰 EXE 完整交互、自然退出、LAN/非开发机均依赖受支持原生 GUI 或外部设备，不能凭此预检转成已通过。SEC-01 历史凭据评估属另行权限/决策范围，当前不执行。

## 独立终审

独立审查者只读重算原 summary SHA、包七文件 size/SHA、校验单六项、原始运行的 TCP/HTTP/双登录/wire/owned Job/严格清单，并审五份公开文件及现有 backlog：**0 MUST**。可有限 AI 接受当前工具驱动旧构建 EXE 正向预检，不接受完整 R3；公开内容不含原始日志、用户名、私密数据、密钥或二进制。提交、推送、安全集成与 CI 状态另核。
