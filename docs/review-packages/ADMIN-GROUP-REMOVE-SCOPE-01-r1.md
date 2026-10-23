# ADMIN-GROUP-REMOVE-SCOPE-01 r1

2026-10-23 IMPLEMENTED / DOMAINS_PASSED / INDEPENDENT_CODE_REVIEW_0_MUST / PENDING_FULL / NOT_AI_ACCEPTED。[Task v1.1](../task-packages/ADMIN-GROUP-REMOVE-SCOPE-01.md)。base087b6e92857093d69728c25f4aa1b97bff7d62bf，冻结42f0d91。session_scout独立工作树只写server.py管理员remove与新test；flagship_scout独立设计/代码/原件审查，root唯一资料/最终组合验证与技术验收。

原实现锁外cur+锁内pop存在同UID重复移除KeyError，且成功移除缺目标全部会话group_removed与局部群语音清理。有限目标：权威锁内决定/版本及会话快照、锁外按gid通知/持久化/广播/审计；保留账号、其他群与资源。显式op=dissolve未纳入，视频批暂停不继承。

设计初审1 MUST：竞态屏障必须放在_known_names首次读锁之后、每目标线程第二次remove写锁获取之前；已纳入Task v1.1并独立复核关闭，设计0 MUST。2026-10-23已向A授予有限实施，先同test原生产RED，再修复/GREEN/必要域，root最终full用短run-dir；五次实际测试均已结束，实际shell退出码为1/1/1/0/0；尚未全量或产品验收。后续仅按真实启动/结束证据更新，不预写通过计数。原件仅本地ignored目录，公开摘要不含原日志或用户资料。

既有基线gcf23-final-01为217文件3003P/0F/20既有skip/exit0，source494/e8a95537d71600b4a38681534adeb0dd63aa5682b3f4c64c2306456f529b8dc7；主控冻结前逐输入等该已验收main。视频4759非祖先，原视频失败与上一批长路径失败仍保留，不因新批运行改判。无GUI/自然退出/跨机LAN/新EXE/完整R1或发布验收。

## 专项与领域原件

| 阶段 | 实际结果 | run |
| --- | --- | --- |
| 首次RED（含1项测试前置错误） | 1文件4F，actual exit1，5.242s | admin-remove-red-20261023-20261023-175545-e99bb40403 |
| 群名纠正后仅真实Core RED | 1文件1F，actual exit1，5.331s | admin-remove-core-red-20261023-20261023-175621-7223591d39 |
| 新增控制原产品选测 | 1文件1P/1F，actual exit1，2.133s | admin-remove-controls-red-20261023-20261023-175705-2ca72fdf9b |
| 最终新test首GREEN | 1文件6P，actual exit0，2.454s | admin-remove-green-20261023-20261023-175755-d65be05231 |
| 必要既有领域 | 6文件82P，actual exit0，33.685s | admin-remove-domain-20261023-20261023-175814-2c9463fd12 |

首次RED前三为实际旧行为缺陷（确定KeyError(2)、群语音残留），第四因合成群名超过配置长度截断，未进入目标，不算产品失败。缩短群名后仅真实Core案原产品负测已走到等不到group_removed；再补冻结控制只选新增owner/send失败与rejections，1F1P。最终test与该controls-RED逐字节相同，controls-RED到GREEN只server.py不同；早两版test各有SHA，不虚称全部同字节RED。

最终GREEN6P与既有领域6文件82P同source `5c9f37e256a77323bfe8c0d8f5c256ca3a3141d4df5a02782210533d198169bc`；领域summary SHA `2fa548dfd60274b396961b7657feb861e980a095a9c2359207cf712fa2bef7de`。领域选admin_groups/admin_groups_web、kick/leave、capacity、R72；未重复同版已绿新test。五run逐个核manifest/progress、source快照、原log SHA/计数、sandbox、单attempt/cleanup和版本指纹通过；当前worker源码等最终domain。实际exec73818/42669/6438/30065/82286均结束，无活动测试。

真实双ClientCore覆盖两端清已加入群/成员/邀请及该群E2EE状态、另一群密钥/在线epoch保留、有序重连不自动重入、另一群消息与显式重新加入；真实Hub合成TCP/WebSession覆盖同UID通知/Web token保留、owner转让/最后成员群语音清理、一个目标send抛错不阻塞其他目标、重复并发恰一次成功与非admin/member/group拒绝。动态跨线程锁探针只验证拒绝_error；成功send/persist/broadcast/audit锁外由实际代码独立审查，不能说有动态探针覆盖。[脱敏证据](../review-assets/ADMIN-GROUP-REMOVE-20261023/evidence.json)。

flagship_scout正式独立代码与五run原件复核0 MUST，当前worker两个文件与GREEN/domain原始快照SHA一致，可进入指定两文件提交/组合冻结；最终full与资料终审仍待完成，不提前验收。
