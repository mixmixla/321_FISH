# GROUP-LEAVE-ADMIN-ROLE-01 r1

2026-10-23 AI_ACCEPTED_GROUP_LEAVE_ADMIN_ROLE_ONLY / FINAL_FULL_PASSED / INDEPENDENT_FINAL_TECH_REVIEW_0_MUST / PUBLIC_REVIEW_0_MUST / NOT_INTEGRATED。
[Task v1](../task-packages/GROUP-LEAVE-ADMIN-ROLE-01.md)，base004d2bd545d31e7a2e2686a92b62c4c42e91c181。session_scout隔离实现，flagship_scout独立设计/代码/三run及full原件0 MUST，root唯一资料/组合验证和有限AI技术验收，实现者不自验。

旧普通leave只删members，原群管理员在离群期间确无权限，但合法公共重入后旧admins资格恢复。产品只在leave成功分支成员删除后同Hub锁加一行admins.discard；其他群管理员、加入许可、owner转让、revision/通知/语音、账号/token与其他handler/Core不变。mutes保留现状，不定义反逃避政策或扩大有效禁言验收。

| 阶段 | 实际结果 | run |
| --- | --- | --- |
| 原产品RED | 2F1P，actual exit1，5.437s | leave-admin-role-red-20261023-20261023-185517-86e3c428b2 |
| 首GREEN | 3P，actual exit0，2.279s | leave-admin-role-green-20261023-20261023-185547-4bdb514e72 |
| 必要旧领域 | 6文件94P，actual exit0，44.496s | leave-admin-role-domain-20261023-20261023-185603-4b1665275b |

两RED失败均触达目标权限，无fixture前置错：由真实owner handler授予后实际invite handler可用，leave/public rejoin后旧版没有期望perm；真实loopback Core亦证实同链。修后先拒绝，现任owner重授后成功；另一群管理能力/Web token/账号保持。test三阶段SHA `cf0c771ae8cbaecac7937e1f81eb65391842de08e687e8caf2f5b7d9cce21b50` 不变，RED→GREEN仅server.py一行变。mutes只断合成旧值不变，未测试完整有效禁言策略。

GREEN/domain同source `8d187230e68527b3ad8e21108dd8951e4993c8f16f9ece58ce565dff6dff69d7`，domain summary SHA `d7b17c8c4cbf85a3952d333289fad41dbbe630481a6589750e5e3306ce8650bf`。领域为leave/kick、admin remove/dissolve、R28/server，未重复同版newtest；三run快照/log SHA计数/sandbox/progress/单attempt/cleanup均核，actual exec59947/39886/58182结束exit1/0/0。独立代码/原件0 MUST。

## 唯一最终组合门禁

worker82945b761fb0f5d4ccdda5e08324d0b3348d176f无冲突集成为c6a0106f3e162b442550696258aa6eb9b15550c4，两个blob相同。497输入source `3f89ac55c725b553a7c954ca92b67c68cadff066aa781a22c8335109233586bc`，相对已验收base只server/newtest输入变，client/client_core/vmemo_api等base、视频4759非祖先。

唯一full `gla23-final-01`：220文件3017P/0F/20既有skip，actual exit0，795.364s，summary SHA `310f18fd50a6651aad3499b3d92027925b4e1b38e5a7c5d25fd68b439c3ca65c`。现有短--run-dir入口，未改系统/Git/依赖/安全设置，exec3711已结束，无活动测试。root首次28后验全true，含当前/冻结/快照、完整220集合、全原log/sandbox/cleanup/单attempt、解释器依赖、旧219计数和20skip不变、阶段及旧失败保持。

flagship_scout独立复算全220原件/497源和身份/旧计数跳过，最终技术0 MUST；root据此有限AI_ACCEPTED本Task。公开资料独立终审0 MUST；全部新增可达Git对象/metadata脱敏与普通main集成核远端仍待。[脱敏证据](../review-assets/GROUP-LEAVE-ADMIN-ROLE-20261023/evidence.json)。原日志/用户身份/二进制只本地ignored，不上传。

视频及旧群容量首次长路径失败均exit1原位保留，视频继续暂停不诊断/合并/开硬件。后继群语音迟到join权限竞态只读候选未冻结，不叠加本批。未验收CI、可视GUI、自然退出、物理LAN、新EXE、完整R1或发布。
