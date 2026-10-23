# ADMIN-GROUP-DISSOLVE-SCOPE-01 r1

2026-10-23 IMPLEMENTED / DOMAIN_PASSED / INDEPENDENT_CODE_REVIEW_0_MUST / NOT_AI_ACCEPTED。[Task v1](../task-packages/ADMIN-GROUP-DISSOLVE-SCOPE-01.md)，base7dbbd28cd9b608657c04e6444a75230cd6bdcd0a。root唯一资料/组合验证与集成，session_scout隔离工作树仅server.py显式dissolve/newtest，flagship_scout独立设计/代码/原件/公开审查。

独立设计0 MUST：无普通owner显式dissolve协议，owner leave最后成员解散作对照，不新增入口。显式admin dissolve在_known_names前，确定性双线程门在首次Hub锁acquire前；保留现有对象身份guard及已消失无操作语义，不要求扩展错误协议。锁内原成员全部已有Session快照/revision/删群与该gid voice，锁外逐目标容错通知及原持久化/广播/审计；账号token/其他群密钥与资源保持。重连使用实际GROUP_JOIN记录+同连接chat顺序屏障，不以群已删推导无旧重入尝试。三个阶段实际已结束，尚未组合全量或产品验收；视频4759仍暂停未继承。

## 原始专项与领域证据

| 阶段 | 实际结果 | run |
| --- | --- | --- |
| 原产品RED | 4F1P，actual exit1，5.548s | admin-dissolve-red-20261023-20261023-182831-eedb131244 |
| 首GREEN | 5P，actual exit0，2.495s | admin-dissolve-green-20261023-20261023-182905-0f4a753a9d |
| 必要既有领域 | 7文件88P，actual exit0，35.964s | admin-dissolve-domain-20261023-20261023-182921-25ff8505b2 |

原RED四失败分别触达群语音残留、未通知、revision未递增、真实Core收不到移除，无群名等前置失败。RED/GREEN newtest逐字节相同，两个manifest只server.py不同；原RED保留不以绿抹红。GREEN/domain同source `ee7ba9c7d71979bf948a7f094351b90d5e80761f95a2f21b37d86457c6274428`，domain summary SHA `1c999d4ea7a1dab8cac20418bb74c01033d493bfa847ac26c6720d95344b376b`。领域为admin_groups/web、admin_remove、leave/kick、capacity、R72，不重复同版已绿newtest。

三个run的manifest/progress、快照、原log SHA/计数、sandbox、单attempt/cleanup/指纹均核实，当前worker源等domain，actual exec43616/39022/67675均已结束exit1/0/0。真实Core采用两UID（群主及同UID双成员客户端），逐目标收到group_removed，成员缓存/邀请/群E2EE材料清理、其他群密钥和连接epoch保持；服务端实际GROUP_JOIN handler记录+重连welcome处理完成+该连接后续chat顺序屏障，证明不再尝试解散gid自动加入，另一群消息可达。合成Web多会话token、其他群语音、非成员无误通知、单目标send失败继续其他成员、并发一次成功及拒绝控制保持。锁外成功IO由代码独立结构审查，不声称动态成功IO探针。普通owner最后成员leave/管理员remove只作既有域对照，未改其实现。[脱敏证据](../review-assets/ADMIN-GROUP-DISSOLVE-20261023/evidence.json)。

flagship_scout独立代码/三run原件正式审查0 MUST，可指定两文件提交/组合冻结；当前尚未全量/AI接受或远端交付。
