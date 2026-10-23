# GROUP-LEAVE-SCOPE-01 v1.1

2026-10-23，READY，属于本次两项有限并行批次；设计审查通过后方可修改产品。base `8cd76a3ae52c946206805194ef4b0b053fa6e9e9`。沿用用户本周公开干净交付和正常直接集成 main 的授权，不发布、不改保护或凭据、不强推。

## 问题与产出

显式 GROUP_LEAVE 删除的是 UID 级成员，但只向剩余成员发 group_state。调用端只清自己的自动重入集合，另一同 UID 端仍可在续连时自动加入公共群；目标群成员/邀请/密钥也可能残留。本批使服务端已接受的退群向当时该 UID 全部现有 Session 通知，复用已有 group_removed/gid 与运行态 group_revision、本地 generation 清理机制，不撤账号或 Web token，不改变显式重新加入权限。

在 Hub 锁内完成原成员修改、分配移除 revision、捕获目标 Session；网络 IO 在锁外。非成员/非法请求保持原拒绝且无额外副作用；最后成员离开导致解散也必须清目标会话。较早群快照不能恢复已退群状态，确认后握手中的旧 worker/迟到有效密钥信封不能复活它。保留其他群、其他用户和当前账号连接，不新增永久禁入或数据删除承诺，不修改认证/持久格式。

v1.1 独立设计整改：现有成员判断在锁外，同 UID 两 Session 可同时通过再在锁内重复 del。实现必须将群对象/成员资格的权威重核与删除放在同一 Hub 锁内，拒绝通知仍在锁外；确定性并发回归应证明一次有效移除、另次原 group 错误拒绝、无 KeyError/重复移除 revision，不用 sleep 追逐时序。仅修该退群入口的必要前置，不扩其他 handler。

## 所有权与隔离

session_scout 为唯一编码者，分支 fix/group-leave-scope-20261023，worktree `_tmp_gui/worktrees/group-leave-20261023`。允许改 server.py，以及新增 tests/test_group_leave_scope.py；只有独立设计证明确有必要且主控更新范围后才改 client_core.py。不得修改其他任务的文件或主工作区。主控 root 独占所有项目文档和最终集成；flagship_scout 独立审查，不能参与该补丁实现。

## 验收

先以未修改产品运行新增确定性回归并保留 RED。真实合成 Hub、公共群、同 UID 双 ClientCore 和旁观者：退群后两端保持在线/同 epoch、只清目标群、保留其他群消息；等原 _on_welcome 完整返回后用同连接消息屏障证明续连不会自动重入；正常显式重新加入仍成功。补全部目标 Session 含 Web token、最后成员解散、非成员无副作用、旧快照/握手 worker/迟到密钥的必要覆盖。复用已有夹具/清理约束，所有自有线程/Hub 逐项有界清理且不覆盖原失败，不靠 sleep 判断成功。

只运行该线的 RED/受影响选测和必要领域；不得启动全量。原始日志和合成数据留 ignored 本地；记录命令、退出码、run 和 source 身份供主控引用。独立设计/代码/原证据审查 0 MUST 后，主控合并两条已验候选、冻结最终组合并只跑一次适用全量，再终审/审计全部新增对象/正常集成。遇失败保存证据并查因，不 retry-to-green，不增加 skip。

这不是可视 GUI、应用自然退出、跨机器 LAN 或新 EXE 验收，不升级整个 R1/M1。
