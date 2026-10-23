# ADMIN-GROUP-REMOVE-SCOPE-01 r1

2026-10-23 AI_ACCEPTED_ADMIN_GROUP_REMOVE_ONLY / FINAL_FULL_PASSED / INDEPENDENT_FINAL_TECH_REVIEW_0_MUST / PUBLIC_REVIEW_0_MUST / MERGED_MAIN / REMOTE_VERIFIED。
[Task v1.1](../task-packages/ADMIN-GROUP-REMOVE-SCOPE-01.md)，base087b6e92857093d69728c25f4aa1b97bff7d62bf。session_scout隔离实现，flagship_scout独立设计/代码/五run与最终full原件审查0 MUST；root唯一资料/组合门禁与有限技术验收，实现者不自验收。

管理员remove原先锁外cur+锁内pop，同UID重复请求可KeyError；成功移出缺全部目标Session的group_removed与该群语音清理。仅server.py remove与新tests/test_admin_group_remove_scope.py：锁内同群/成员权威决定，恰一次移除/admin与mutes清理、群主转让或空群解散、revision/目标会话快照；锁外拒绝、持久化/广播/审计、逐目标容错通知。只处理group:{gid}语音名册，账号/token/其他群与资源保持，仍可按原权限显式加入。显式op=dissolve、客户端/GUI/视频均未修改。

设计初审唯一MUST为确定性门应在_known_names首次读锁后的第二次remove写锁acquire之前；v1.1已澄清，独立复核关闭。原版门后确定KeyError(2)，线程异常传播至测试主线程，owned线程有界join；不靠sleep竞态或压力追绿。

| 阶段 | 实际结果 | run |
| --- | --- | --- |
| 首次RED（含一项测试前置错误） | 1文件4F，actual exit1，5.242s | admin-remove-red-20261023-20261023-175545-e99bb40403 |
| 缩短合成群名后Core-only原版RED | 1文件1F、3 deselected，actual exit1 | admin-remove-core-red-20261023-20261023-175621-7223591d39 |
| 新增controls-only原版选测 | 1文件1F1P、4 deselected，actual exit1 | admin-remove-controls-red-20261023-20261023-175705-2ca72fdf9b |
| 最终新test首GREEN | 1文件6P，actual exit0，2.454s | admin-remove-green-20261023-20261023-175755-d65be05231 |
| 必要既有领域 | 6文件82P，actual exit0，33.685s | admin-remove-domain-20261023-20261023-175814-2c9463fd12 |

首RED前三为旧行为缺陷（包括KeyError及群语音残留），第四群名超过配置长度被截断，未进入目标，不算产品失败。纠正后只选真实Core案，已进入目标但缺group_removed；再补冻结控制，仅选新增owner/send失败与rejections原版对照。最终controls-RED与GREEN test逐字节相同，二者仅server.py不同；早两版test单独保留SHA，不冒称全部RED同字节最终test。

最终GREEN/domain同source `5c9f37e256a77323bfe8c0d8f5c256ca3a3141d4df5a02782210533d198169bc`；领域summary SHA `2fa548dfd60274b396961b7657feb861e980a095a9c2359207cf712fa2bef7de`。领域为admin_groups/admin_groups_web、kick/leave、capacity、R72，未重复同版已绿新test。全部五run原manifest/progress、快照、log SHA/计数、sandbox、单attempt/cleanup与身份通过；actual exec73818/42669/6438/30065/82286均结束。

真实双Core证明两端清对应加入态/成员/邀请/E2EE材料，保持另一群密钥与连接epoch，有序重连不自动重入、另一群消息可用且允许显式重新加入。合成TCP/WebSession用真实Hub handler证明全部目标通知、Web token与账号保持、owner转让/最后成员群语音清理、一目标send失败不阻塞其他目标、非admin/member/group拒绝。动态跨线程锁probe只覆盖拒绝_error；成功send/persist/broadcast/audit在锁外由实际代码独立审查，不冒称动态覆盖全部成功IO。

## 最终组合门禁与技术结论

worker提交3bf61cfdd0fc6ef39ce2f9c2d427b127d491a4a2无冲突集成主控57ef3973fbf63254a352c0e367ef36760f5c7dc0，两blob逐字节相同。495输入source `fe6c061356dbd80855e0856d43b5c2e9e1da52c8d93ccbe82d8123f73796cb4a`，相对已验收base只server.py与newtest输入变化，client/client_core/vmemo_api不变，4759非祖先。

唯一最终full `agr23-final-01`：218文件3009P/0F/20既有skip，actual exit0，793.168s；summary SHA `409a289575413d535a3bb5d0c49368952f5228c6957646e9313c394b49904fa7`。使用既有短--run-dir入口，未改系统/Git/依赖/安全设置。主控28后验全true：当前/冻结/快照、完整218集合、全部原log/sandbox/cleanup、单attempt、解释器依赖、既有217文件计数与20skip不变、所有阶段与历史失败原件保持。exec57370已结束，无活动Python测试。

flagship_scout已独立复算218文件与495源、解释器/依赖及旧计数/skip/历史失败，最终技术0 MUST；root据此有限AI_ACCEPTED本Task。公开资料及全部38新增可达Git对象/metadata独立审计0 MUST，已普通main集成并核远端，回执见下，不重复全量。[脱敏证据](../review-assets/ADMIN-GROUP-REMOVE-20261023/evidence.json)。原始日志/身份/二进制只本地ignored，不入公开仓库。

视频分支4759原生失败、上一批长路径失败均保留exit1未改判；视频暂停不诊断/合并。显式dissolve仅只读候选，不视作本Task已修复。未验收CI、可视GUI、自然应用退出、跨机器LAN、新EXE、完整R1或发布。

## 远端交付回执

全部38新对象/metadata独立审计0 MUST后，正常快进main并非强制推送；Git ls-remote与GitHub API双核完整SHA `5fd67595fe40223e5b40cfc7e3965fe48382752f`，495源仍与最终full逐字节一致、无活动测试。首次TLS握手错误经双核确认未更新后，同通道恢复仅一次有界重试成功，未改身份/证书/网络/安全设置。该提交check-runs/status contexts/Actions均0（aggregate pending/total0），不称CI通过。本回执仅四份公开资料增量，最终leaf以Git refs为准、原件本地ignored；无新源码、不重测/发布，视频仍暂停。
