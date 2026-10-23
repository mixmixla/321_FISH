# GROUP-LEAVE-ADMIN-ROLE-01 r1

2026-10-23 READY / INDEPENDENT_DESIGN_REVIEW_0_MUST / NOT_IMPLEMENTED。[Task v1](../task-packages/GROUP-LEAVE-ADMIN-ROLE-01.md)，base004d2bd545d31e7a2e2686a92b62c4c42e91c181。root唯一资料/组合验证/集成，session_scout隔离server.py/newtest实现，flagship_scout独立设计/代码/原件/资料审查。

设计0 MUST：leave成功分支成员删除后同Hub锁discard对应admins即可；mutes保留现状，不改join/客户端/协议/其他群/账号。原用户不在群时无权限，真实缺陷是合法重入后旧管理员能力恢复。以实际授权handler授予、受保护invite handler验证原权限→leave→public rejoin→拒绝perm，再由当前owner重授后允许，至少loopback Core证实实际协议。另一群管理员与mutes不变、旧群主转让/最后成员和多会话通知由必要域保持。当前尚未本批测试或产品验收，视频仍暂停未继承。
