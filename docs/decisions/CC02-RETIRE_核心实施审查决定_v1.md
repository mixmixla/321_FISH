# CC02-RETIRE — 核心实施审查决定 v1

2026-10-02（Asia/Shanghai）。依据用户提供的[Pro审查结论](https://chatgpt.com/s/t_6abf1a903d848191987d368fd37ee100)，以及用户直接答复“我批准按此结论实施”。
网页工具只取得登录页；已通过Codex对“项目接管审查”聊天的只读访问取得对应最新审查正文。未发送任何消息。
本文只归档技术决定及执行映射，不归档私有聊天全文。选定审查回答的原文证据限本机ignored目录；UTF8 SHA256为`0ad7e455d788350d853858e4d73f78c1f161f21d1ef2e2c9bfef43f3b06d6197`。

## 审查结论与批次映射

设计方向通过，但完整RETIRE草案不能一次执行。先冻结小批次，仅server.py、最少量server_store.py和tests；不改UI/web.py，不开始资源/全119 handler或部署恢复重构。
原CC-02A PROFILE→RESTORE→KICK已验收，不能复用该ID覆盖历史Task；新批次命名为[CC-02A-RETIRE-CORE v1](../task-packages/CC-02A-RETIRE-CORE.md)。
实施授权来自本聊天的直接用户批准；审查正文是技术输入，不额外授予Git发布或真实数据权限。

| 决策 | 冻结到本批/延期范围 |
| --- | --- |
| P1 | M1保留UID/昵称占用，t0屏障与最终C区分。首批登录/attach/claim/token、CHAT、DRAFT、SCHED（含已摘due）、PROFILE及必要本人私有元数据；不改全部119 handler |
| P2 | save失败不得假成功、旧写不得覆盖新状态是退役确认必要的两项最小前置。仅错误传播/确认和运行态写顺序；完整writer/revision/hash-proof系统另批，不新增持久revision/schema迁移 |
| P3 | 首次持久提交失败时保留当前进程阻断，不能保证崩溃后旧有效JSON仍保留退役；有效成功JSON重启才确认。禁止把内存撤权/旧服务降级当可靠退役 |
| P4 | 服务端区分pending/failed/unknown/confirmed，同UID/op_id查询与重试，成功才报告持久完成。当前客户端乐观删除和失效交互延期，本批不得声称UI已完整支持四阶段 |
| P5 | 保护当前认证管理员UID、默认/当前有效管理员保留名及BOT_BY_UID；不猜历史管理员、不加入bot昵称永久预留。分配不得复用退役UID或覆盖实际botUID |
| P6 | 逻辑清本人known/draft/sched/blocks/reads等必要记录，沿既有作者消息/移群规则；共享引用/完成附件/动态/审计/备份/副本保留，无广泛物理擦除 |
| P7 | 新retired字段必要严格恢复，旧字段缺失不推断已退役；marker、整体load状态机、InitializeNew、durable intent均延期CC-05存储加固，不在本批创建这些设施 |

## 必要依赖的执行解释

审查正文一处建议首批含cloud，最终文件边界又明确cloud/bot/preview后续处理；**以最终收窄范围为准**，本批不改资源处理。
正文将完整STORE-COMMIT列第二批，又要求第一批删除流程有persist receipt。核心若仍吞IO错误/允许旧快照覆盖，就无法满足成功重启验收。
因此本批在允许的server_store.py“尽量少”边界内只落实两项最小前置，不实施ServerStore V2；独立审查同时核对这条范围限制。
核心C采用已有Hub锁内纯内存最终检查，不引入UID/resource gate全体系；准备/哈希/通知/网络/磁盘在锁外。
必要blocks/reads最终拒绝及known资料辅助纳入本人私有记录清理，不能用本批扩大媒体/房间/游戏处理。

## 权限与保留风险

用户批准核心代码/测试、合成隔离验证、独立审查及必要文档；沿既有Goal偏好持续到这个有限批次完成。
未授权commit/push/新PR/merge/release、修改真实用户数据、外部/Pro/其它聊天消息或恢复heartbeat；当前未提交设计材料全部保留。
CORE验收不等于完整RETIRE资源边界关闭、UI承诺修复或Pro R1里程碑通过。资源晚到IO、客户端乐观缓存、整体loader损坏/丢失状态及恢复/迁移均明确延期。
