# GROUP-CAPACITY-01 r1

2026-10-23 IMPLEMENTED / INDEPENDENT_CODE_REVIEW_0_MUST / COMBINED_GATE_PENDING。
[Task v1](../task-packages/GROUP-CAPACITY-01.md)，base9d12a5863102ae0e8302f2b7bb1315350a250669。session_scout隔离实现，flagship_scout独立设计/代码/原件审查均0 MUST，root唯一资料、组合门禁及技术验收。

公开群加入与管理员加人原先仅锁外检查容量，最后一席可被同时占用；管理员同UID竞争还重复成功审计。仅server.py两入口改为锁内一次决定群对象、成员、权限、容量及写入，错误和原持久化/广播/审计在锁外。邀请码和其他路径不改，保留原错误码与权限。

| 阶段 | 实际结果 | run |
| --- | --- | --- |
| 原产品RED | 4F1P，exit1，1.908s | group-capacity-red-20261023-20261023-170427-290085286a |
| 首GREEN | 5P，exit0，1.844s | group-capacity-green-20261023-20261023-170509-1f48ab3930 |
| 必要既有领域 | 3文件22P，exit0，13.428s | group-capacity-domain-20261023-20261023-170521-1dad758a1c |

GREEN/领域同source `e5bece03bde87bd53994ff5ef87c77f0fe7e6f4dc56c94b442126bcf27d3f21e`，领域summary SHA `2ee6a42c7e13738a6dc0ccf01e571585f8cc4903df45174672a31ce629aa56f6`。新test从RED到最终域逐字节相同，原RED四失败均为目标竞态。领域为kick6/leave4/R28管理12，不重复已过同版新文件。原RED保留，不以绿抹红。

受控门在真实Hub锁获取前，公开入口第一次、管理员在_known_names读锁后的第二次，不持Hub锁等屏障。真实Hub及合成Session回调覆盖三种双UID组合只一个成功、同UID只一次成功审计；拒绝回调由另一线程取得同一RLock证明锁外，私有群/邀请/正常与已满对照保持。owned线程有界join，原异常及清理证据保留。

主控十项worker后验与独立复算通过：manifest/progress、快照、日志SHA/计数、sandbox、单attempt/cleanup、当前源等最终域。原始日志只留worker ignored目录，不上传本机身份、用户数据、原日志或二进制。下一组合冻结并唯一full，尚未AI_ACCEPTED/未合并。

本批源自已验收main，未继承暂停视频分支4759a01e的修改。视频full原生崩溃失败仍保留、未接受，不因本Task运行而关闭。本批不验证视频、可视GUI、自然退出、跨机器LAN、新EXE、完整R1或发布。
