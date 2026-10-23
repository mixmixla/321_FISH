# GROUP-LEAVE-ADMIN-ROLE-01 r1

2026-10-23 IMPLEMENTED / DOMAIN_PASSED / INDEPENDENT_CODE_REVIEW_0_MUST / NOT_AI_ACCEPTED。[Task v1](../task-packages/GROUP-LEAVE-ADMIN-ROLE-01.md)，base004d2bd545d31e7a2e2686a92b62c4c42e91c181。root唯一资料/组合验证/集成，session_scout隔离server.py/newtest实现，flagship_scout独立设计/代码/原件/资料审查。

设计0 MUST：leave成功分支成员删除后同Hub锁discard对应admins即可；mutes保留现状，不改join/客户端/协议/其他群/账号。原用户不在群时无权限，真实缺陷是合法重入后旧管理员能力恢复。以实际授权handler授予、受保护invite handler验证原权限→leave→public rejoin→拒绝perm，再由当前owner重授后允许，至少loopback Core证实实际协议。另一群管理员与mutes不变、旧群主转让/最后成员和多会话通知由必要域保持。本批三个阶段已完成，组合全量及产品验收仍待，视频仍暂停未继承。

## 专项与领域证据

| 阶段 | 实际结果 | run |
| --- | --- | --- |
| 原产品RED | 2F1P，actual exit1，5.437s | leave-admin-role-red-20261023-20261023-185517-86e3c428b2 |
| 首GREEN | 3P，actual exit0，2.279s | leave-admin-role-green-20261023-20261023-185547-4bdb514e72 |
| 必要旧领域 | 6文件94P，actual exit0，44.496s | leave-admin-role-domain-20261023-20261023-185603-4b1665275b |

RED两失败均为旧权限实际恢复，无fixture前置错：合成Hub实际invite handler没有期望perm、真实loopback Core也未收到perm。修后两者都拒绝，当前owner重授后恢复允许；其他群管理员能力、Web token和账号在线保持。newtest从RED到domain SHA `cf0c771ae8cbaecac7937e1f81eb65391842de08e687e8caf2f5b7d9cce21b50` 不变，RED→GREEN只server.py变化。mutes仅保留合成旧值，不声称有效禁言或反逃避策略验证；普通成员leave/owner转让与既有最后成员/多会话控制保持。

GREEN/domain同source `8d187230e68527b3ad8e21108dd8951e4993c8f16f9ece58ce565dff6dff69d7`，domain summary SHA `d7b17c8c4cbf85a3952d333289fad41dbbe630481a6589750e5e3306ce8650bf`。旧域为leave/kick、admin remove/dissolve、R28/server，不重复同版newtest。三原run manifest/progress、快照、log SHA/计数、sandbox、单attempt/cleanup均核，actual exec59947/39886/58182结束exit1/0/0，当前源等domain；flagship_scout独立代码/三run原件0 MUST。只在leave成员删除后同锁加admins.discard一行，其他逻辑未动。[脱敏证据](../review-assets/GROUP-LEAVE-ADMIN-ROLE-20261023/evidence.json)。下一指定两文件提交、root等blob集成/冻结与唯一短run-dir full，不提前AI接受或main交付。
