# ADMIN-GROUP-DISSOLVE-SCOPE-01 r1

2026-10-23 AI_ACCEPTED_ADMIN_GROUP_DISSOLVE_ONLY / FINAL_FULL_PASSED / INDEPENDENT_FINAL_TECH_REVIEW_0_MUST / PUBLIC_REVIEW_0_MUST / NOT_INTEGRATED。
[Task v1](../task-packages/ADMIN-GROUP-DISSOLVE-SCOPE-01.md)，base7dbbd28cd9b608657c04e6444a75230cd6bdcd0a。session_scout隔离实现，flagship_scout独立设计/代码/专项与最终full原件审查0 MUST，root唯一资料/组合验证与有限AI技术验收；实现者不自验。

管理员显式dissolve原先只删群/发目录，未清群语音或通知原成员Core清加入态/成员/邀请/E2EE材料。仅server.py该分支新增13行与newtest：同Hub锁内快照原成员全部已有Session、取得revision、删群与group:{gid}语音名册，锁外逐目标send容错及原force persist/system/list/audit。账号/token/其他群资源保持，离线成员无Session则无目标可通知；不对离线客户端后续恢复作新承诺。无普通owner显式dissolve协议，owner leave有余人转让、最后成员才解散作为既有对照，不新增入口/变权限、add/remove或客户端/视频。

| 阶段 | 实际结果 | run |
| --- | --- | --- |
| 原产品RED | 4F1P，actual exit1，5.548s | admin-dissolve-red-20261023-20261023-182831-eedb131244 |
| 首GREEN | 5P，actual exit0，2.495s | admin-dissolve-green-20261023-20261023-182905-0f4a753a9d |
| 必要旧领域 | 7文件88P，actual exit0，35.964s | admin-dissolve-domain-20261023-20261023-182921-25ff8505b2 |

RED四失败直达voice残留/未通知/revision/真实Core，无fixture前置错。test三阶段逐字节相同，RED→GREEN manifest只server.py不同，保留首次失败。GREEN/domain同source `ee7ba9c7d71979bf948a7f094351b90d5e80761f95a2f21b37d86457c6274428`，domain summary SHA `1c999d4ea7a1dab8cac20418bb74c01033d493bfa847ac26c6720d95344b376b`。领域为admin_groups/web、admin_remove、leave/kick、capacity、R72，未重复同版已绿newtest；三run源快照/log SHA/计数/sandbox/progress/单attempt/cleanup均核，actual exec43616/39022/67675结束exit1/0/0。

新test验证原群主与成员两个UID（成员同UID双Core）、合成Web多会话/token、其他群语音和密钥/连接epoch保留；真实协议按actual GROUP_JOIN handler记录、重连welcome处理完成和该连接后续chat顺序屏障，证明不再尝试已解散gid自动重入、另一群消息仍可用，未把服务器群已删误作无请求证据。首次Hub锁前门使并发两请求越过旧群对象预读且恰一次revision/通知/审计；owned线程有界join、原异常传播。单目标send失败不阻塞其他成员，非admin/缺群拒绝不改变状态。成功IO锁外由独立代码结构证明，无动态成功IO探针声明；普通最后成员leave由既有域覆盖，不改变其行为。

## 唯一最终组合门禁

worker0413c96faa9a4c87cdd810dc214d57cfc59b13b2无冲突集成为235fd71be1b8676cd3e198341e41ba74303e21d8，两blob等worker。496输入source `ebbf84676b7ca566123ec9247dc65939a8d14218972cfa4768b76d36024ad91d`，相对上一已验收base只server与newtest输入变，client/client_core/vmemo_api不变，视频4759非祖先。

唯一full `agd23-final-01`：219文件3014P/0F/20既有skip，actual exit0，789.681s，summary SHA `5b45a74ff4807e83b9bb57464d790ac7bc8442cc3967ffe3c3a94dceabe8b074`。既有短--run-dir入口，未改系统/Git/依赖/安全设置，exec21440已结束，无自有测试活动。最初本地后验复制模板仍预期上一批remove文件名，full_complete_file_set断言失败；原报告与hash保留。独立实核manifest/summary仅新增dissolve test，无旧218文件缺失，纠正两处预期路径后28项全true；只重算只读证据，没有源/测试变化或重跑全量，不能把后验脚本错误写成产品full失败或抹去原错误。

flagship_scout独立复算219原始记录、496当前/冻结/快照、解释器/依赖、runner/sandbox、旧218计数和20skip、上述后验修正，最终技术0 MUST。root据此有限AI_ACCEPTED本Task；公开资料独立终审0 MUST；全部新增可达Git对象/metadata脱敏及普通main集成/核远端仍待。[脱敏证据](../review-assets/ADMIN-GROUP-DISSOLVE-20261023/evidence.json)。原始日志/本机身份/二进制只ignored本地，不公开。

视频原生失败与旧长路径失败均原位exit1未改判，视频仍暂停不诊断/合并/开真实设备。后继普通leave管理员资格残留仅只读候选，mutes策略不改。无CI、可视GUI、自然应用退出、物理LAN、新EXE、完整R1或发布验收。
