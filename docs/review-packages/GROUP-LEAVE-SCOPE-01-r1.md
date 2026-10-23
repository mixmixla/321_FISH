# GROUP-LEAVE-SCOPE-01 r1

2026-10-23 **AI_ACCEPTED_TASK_SCOPE_ONLY / COMBINED_FULL_PASSED / FINAL_REVIEW_0_MUST / MERGED_MAIN / REMOTE_VERIFIED**。
[Task v1.1](../task-packages/GROUP-LEAVE-SCOPE-01.md)，base `8cd76a3ae52c946206805194ef4b0b053fa6e9e9`。session_scout 在独立工作树唯一写 server.py 和新回归，flagship_scout 独立设计/代码/原件审查；root 统一集成与验收。

主动退群修改 UID 级成员关系，却没有清另一同 UID 会话的自动重入意图；该会话续连后可重新加入公共群。修复仅在 `_on_group_leave` 的 Hub 锁内重核群/成员、完成一次删除、取得 group_revision 并捕获当时全部目标 Session，锁外发送现有 group_removed/gid。账号与 Web token 保持有效，最后成员离开导致解散也通知。现有 Core 的 revision/generation/密钥清理机制复用，不改认证、持久格式或显式重新加入权限。

设计审查还发现两 Session 可先通过锁外成员判断，再重复 del。v1.1 将判断与删除统一在锁内；原 group 错误拒绝仍在锁外，拒绝不再分配移除 revision。新测试用每个目标 worker 首次获取 Hub 锁前的受控门确保原竞态发生，不靠 sleep。

| 阶段 | 实际结果 | run |
| --- | --- | --- |
| 首次原实现 RED（早版测试） | 3F，exit1 | group-leave-red-20261023-20261023-153519-b2ef1fbb24 |
| 首 GREEN（早版测试） | 3P，exit0 | group-leave-green-20261023-20261023-153627-23eea24cae |
| 强化后领域 | 5文件40P，exit0，26.544s | group-leave-domain-20261023-20261023-153652-bc52e0e33e |
| 强化并发门配旧实现负测 | 1F，另3项deselected，exit1，KeyError(2) | group-leave-race-red-20261023-20261023-153751-74242bc524 |

最终领域 source `2dffdb75933c32cb78be96829aec86ceb4290d6b7290d646bbbcd5fc1126b2a3`，summary SHA `8b6db2aea15836881f6886739be9b455f2a1be1249d36991ed2b7af01fec39fd`。原始日志、快照、sandbox、计数、单 attempt 和清理均经交叉独立复核。首次 RED 的原 server 与基线仅 CRLF/LF 不同，归一化全文相同；强化后的测试不能称与首次 RED 同字节。受控并发负测 finally 已恢复修复版并核 SHA，无活动测试。

真实合成双 ClientCore 核退群后同 epoch 在线、只清目标成员/邀请/密钥、保留另一群材料与消息；WELCOME 完整返回后的同连接响应屏障证明无自动重入，正常显式重入成功。另核全部目标 Session、Web token、最后成员解散、旧快照反序；领域包含既有旧密钥 worker 与迟到信封回归。独立设计整改、代码和原件审查均 0 MUST。领域阶段未作最终AI验收，完整组合结果与终审见下。

原始证据仅在隔离工作树的 ignored `_tmp_gui/test-gate/`；公开仅必要结果与哈希。最终组合已并入双棋平局修复，版本不同于单线领域，另行冻结一次完整门禁（见下）。不是 GUI、自然应用退出、LAN、新 EXE 或整个 R1/M1 验收。

## 最终组合门禁

唯一组合全量 `parallel-r1-r2-full-20261023-20261023-154204-a506b872c4`：**216文件，2998P/0F/20既有skip，actual exit0，804.698s**。493输入冻结source `e51c01b234b0d71490b784efb332b21a8074bcccb62101196e0dae0a025e5444`；summary SHA `c5e84488af4482d6e90acbc57738d112b2bb45d8d5bda41f061f6afa4a1a1e54`。26项后验全部通过，216逐原日志/计数/sandbox/单attempt/清理、完整测试集合、源快照与历史证据保持均核验。exec6697结束，无活动测试；session_scout独立重算全部原件/解释器依赖/源身份及公开投影和资料，终审0 MUST；主控据此有限AI接受本Task范围。[脱敏摘要](../review-assets/PARALLEL-R1-R2-20261023/evidence.json)。

## 交付回执

main已正常快进并非强制推送至 `5a2cebb5a152f15fd0e1363baef0ff0edf74065f`，ls-remote/API双核一致。全部49新增对象及metadata独立审计0 MUST，最终493源仍等full，无活动测试。该提交check-runs/status contexts/Actions均0，不称CI通过。本回执纯文档，最终leaf以Git refs为准；没有发布，也未升级完整里程碑或未测GUI/LAN/EXE边界。
