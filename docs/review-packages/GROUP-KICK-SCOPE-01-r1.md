# GROUP-KICK-SCOPE-01 r1 — 群移除保持账号会话

2026-10-22 **AI_ACCEPTED_GROUP_SESSION_SCOPE_ONLY / FULL_PASSED / FINAL_REVIEW_0_MUST / READY_FOR_BRANCH_PUSH / NOT_MERGED**。
[Task v1.1](../task-packages/GROUP-KICK-SCOPE-01.md)。base `3a995e90996fe8d6bd7bac9248ffcf32a64b8347`，分支 `fix/group-kick-session-scope-20261022`；root 唯一实现/执行，r1_review 独立审查。父提交包含已审核的续连、门禁修复与离线退役诊断，原分支均保留；本批只包含下述群会话修复，可独立回退。

## 问题与行为

原群移除与管理员强制下线共用 `error/kicked`，导致 ClientCore、桌面和 Web 的生产处理器把群操作当作账号撤销。服务器只通知代表 Session，其他同 UID 客户端还会保留自动重入意图。

服务器现在向移除时已有的全部目标 Session 发送 `error/group_removed` 和 gid，不撤账号或 Web token。ClientCore 仅清该群的自动重入、成员、邀请码和群密钥；其他群与当前认证继续有效。管理员 kicked/deleted、认证期 retired 的终止行为保持。

独立设计审查发现两个相关竞态：群快照在锁内捕获后可能迟于移除送达，密钥 worker 也可能跨移除完成握手。Hub 在锁内分配运行态 group_revision，客户端修改缓存前过滤旧/重复通知；本地 generation 与已有发送锁阻止旧 worker 生成/分发密钥。WELCOME 只重置服务端 revision，本地 generation 保留；迟到密钥不能恢复已移除群。较新成员快照允许正常显式重新加入，不建立永久禁入语义，不改持久格式。

## 分阶段证据

- 原生产源码配新增回归的 RED `group-kick-red-20261022-20261022-123153-9d32015546`：3 文件 **6F / 14P，exit 1**。真实客户端因群 kicked 下线；旧快照、握手跨移除等失败均保留。
- 第一版修复领域 `group-kick-domain-20261022-20261022-123309-16f7de37af`：12 文件 **178P，exit 0，78.02 秒**。
- 独立审查要求补强测试屏障与清理，并补足已开启密钥、其他群消息及显式重入的证据。只有新测试文件变化；原领域其余 11 文件和生产依赖逐字节相同，其 **172P** 证据保留。
- 整改验证 `group-kick-review-fix-20261022-20261022-123554-639af3046e`：**6P，exit 0，2.414 秒**，summary SHA `c720e8d392017f0ac83744c8ce8d03ed5a48e60750648feb8ea5ae4d04fffa9a`。原 RED 属于强化前的测试版本，不能宣称最终测试红绿同字节。

最终用例等待原 `_on_welcome` 完整返回后发送同连接消息作为服务端有序屏障，再确认未自动重入；验证保留群真消息和正常显式重入。目标群真实 sender/peer 材料全部清除，另一群材料保持，迟到有效密钥信封被拒。所有自有资源逐项有界收尾，body 原异常保留，另核 Hub shutdown 与 managed threads。独立代码/证据复审 0 MUST。

## 最终门禁检查点

冻结 491 输入，source `eb6657d16db11502e281f7fb18546fdd4b899267636b1dafcf69c2fc7693b4ae`。唯一最终全量 `group-kick-full-20261022-20261022-123645-a11eebd8c1` 完成 **214 文件、2991P / 0F / 20 既有 skip，actual exit 0，777.502 秒**。执行会话 45448 已结束，无活动测试。summary SHA `d6a6a5c5c556d86a85e8ad09a2e8adb5bf0f71dbcb0d50a68f7adc479bcc4137`；33 后验全部通过，源与快照相同，逐文件日志计数/哈希、原 sandbox、单 attempt、清理和完整测试集合全部核验。旧基线、原失败及既有 skip 保持，r1_review 独立复算原日志、sandbox、manifest/progress、源快照、解释器/依赖/环境指纹与公开投影，终审 0 MUST；主控据此有限 AI 接受群移除会话范围。[脱敏计数与哈希](../review-assets/GROUP-KICK-SCOPE-01/evidence.json)。原件仅在本地 `_tmp_gui/group-kick-scope-20261022/` 与对应 test-gate run；将仅发布脱敏计数/哈希，不发布原始日志。

PR 创建先前由 `github_create_pull_request` 返回 403 `Resource not accessible by integration`，本批未重试、未直接推 main、未发布。最终门禁和独立终审已完成，还需审计全部新对象/提交，再按既有授权推干净功能分支；main 合并仍受 PR 写权限阻塞。当前没有 CI 通过证据。

这是合成 loopback 协议、核心和桌面/Web 生产处理器验证，不是可视 GUI、应用自然退出、跨机器 LAN 或新 EXE 验收。旧服务器仍发送歧义 kicked 时不按文本猜测，此修复需新服务端配合。不升级完整 R1/M1 里程碑。
