# ADMIN-GROUP-DISSOLVE-SCOPE-01 r1

2026-10-23 READY / INDEPENDENT_DESIGN_REVIEW_0_MUST / NOT_IMPLEMENTED。[Task v1](../task-packages/ADMIN-GROUP-DISSOLVE-SCOPE-01.md)，base7dbbd28cd9b608657c04e6444a75230cd6bdcd0a。root唯一资料/组合验证与集成，session_scout隔离工作树仅server.py显式dissolve/newtest，flagship_scout独立设计/代码/原件/公开审查。

独立设计0 MUST：无普通owner显式dissolve协议，owner leave最后成员解散作对照，不新增入口。显式admin dissolve在_known_names前，确定性双线程门在首次Hub锁acquire前；保留现有对象身份guard及已消失无操作语义，不要求扩展错误协议。锁内原成员全部已有Session快照/revision/删群与该gid voice，锁外逐目标容错通知及原持久化/广播/审计；账号token/其他群密钥与资源保持。重连使用实际GROUP_JOIN记录+同连接chat顺序屏障，不以群已删推导无旧重入尝试。当前未运行本批测试，不提前记通过或产品验收；视频4759仍暂停未继承。
