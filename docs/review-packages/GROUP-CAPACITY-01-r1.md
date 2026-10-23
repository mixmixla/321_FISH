# GROUP-CAPACITY-01 r1

2026-10-23 AI_ACCEPTED_GROUP_CAPACITY_ONLY / FINAL_FULL_PASSED / FINAL_REVIEW_0_MUST / NOT_MERGED。
[Task v1.1](../task-packages/GROUP-CAPACITY-01.md)，base9d12a5863102ae0e8302f2b7bb1315350a250669。session_scout隔离实现，flagship_scout独立设计/代码/原件审查均0 MUST，root唯一资料、组合门禁及技术验收。

公开群加入与管理员加人原先仅锁外检查容量，最后一席可被同时占用；管理员同UID竞争还重复成功审计。仅server.py两入口改为锁内一次决定群对象、成员、权限、容量及写入，错误和原持久化/广播/审计在锁外。邀请码和其他路径不改，保留原错误码与权限。

| 阶段 | 实际结果 | run |
| --- | --- | --- |
| 原产品RED | 4F1P，exit1，1.908s | group-capacity-red-20261023-20261023-170427-290085286a |
| 首GREEN | 5P，exit0，1.844s | group-capacity-green-20261023-20261023-170509-1f48ab3930 |
| 必要既有领域 | 3文件22P，exit0，13.428s | group-capacity-domain-20261023-20261023-170521-1dad758a1c |

GREEN/领域同source `e5bece03bde87bd53994ff5ef87c77f0fe7e6f4dc56c94b442126bcf27d3f21e`，领域summary SHA `2ee6a42c7e13738a6dc0ccf01e571585f8cc4903df45174672a31ce629aa56f6`。新test从RED到最终域逐字节相同，原RED四失败均为目标竞态。领域为kick6/leave4/R28管理12，不重复已过同版新文件。原RED保留，不以绿抹红。

受控门在真实Hub锁获取前，公开入口第一次、管理员在_known_names读锁后的第二次，不持Hub锁等屏障。真实Hub及合成Session回调覆盖三种双UID组合只一个成功、同UID只一次成功审计；拒绝回调由另一线程取得同一RLock证明锁外，私有群/邀请/正常与已满对照保持。owned线程有界join，原异常及清理证据保留。

主控十项worker后验与独立复算通过：manifest/progress、快照、日志SHA/计数、sandbox、单attempt/cleanup、当前源等最终域。原始日志仅留本地ignored目录，不上传本机身份、用户数据、原日志或二进制。组合239d17c已冻结494输入，首次full已自然结束（exec99791），217文件2999P/4F/20skip/actual exit1，仅门禁自身Git临时对象路径过长四失败；summary SHAc16d835cd0b952b96fb144a0575b83b21cf12ae45581499d0deb6f97db453250。随后已按Task v1.1验证短目录对照并完成最终full，结果见下；B独立终审0 MUST、root有限AI接受本Task，尚未合并。

本批源自已验收main，未继承暂停视频分支4759a01e的修改。视频full原生崩溃失败仍保留、未接受，不因本Task运行而关闭。本批不验证视频、可视GUI、自然退出、跨机器LAN、新EXE、完整R1或发布。

## 运行目录对照

首次full217文件2999P/4F/20skip，actual exit1，仅test_gate_boardgames.py四项合成Git对象路径Filename too long，失败保留。Task v1.1未改源码或系统/Git设置；同494冻结候选使用现有--run-dir短目录gcf23-short-01，对照4P/actual exit0/6.199s，summary SHA `4a11715d8d2c89a30ba1834f00116dc1452aa967cb2cd1b44dd1f356395646c5`。解释器/依赖/源一致、原sandbox/清理及日志完整，12后验true；对象路径实测max181字符，原失败275字符。单文件对照不能替代full，独立原件复核0 MUST后，已在另一个短目录gcf23-final-01完成最终全量（exec94569已结束），源494不变，实际结果与后验见下；独立终审0 MUST；有限接受结论见最终组合门禁。

## 最终组合门禁

纠正布局后的唯一最终full `gcf23-final-01`：217文件3003P/0F/20既有skip，actual exit0，813.007s。冻结494输入source `e8a95537d71600b4a38681534adeb0dd63aa5682b3f4c64c2306456f529b8dc7`，summary SHA `4eb218c964d84e0924a651c774c180a03f625eba8dfda24ac5099c92c571b915`。主控30后验全true：当前/冻结/full快照、解释器依赖、完整217文件集合、原日志SHA/计数/sandbox、单attempt/cleanup和既有skip/历史失败均核；视频4759非祖先，两视频blob等base。exec94569已结束，无活动测试。首次长路径失败未改判，4P对照仅为必要环境纠正证明。[脱敏证据](../review-assets/GROUP-CAPACITY-20261023/evidence.json)。flagship_scout独立复算全部原件与公开资料，最终技术/资料终审均0 MUST；session_scout仅辅助机械证据核查，不验收自己的实现。root据此有限AI_ACCEPTED本Task；仍须全部新增对象及metadata审计，再正常main集成并核远端，不扩大里程碑或视频范围。
