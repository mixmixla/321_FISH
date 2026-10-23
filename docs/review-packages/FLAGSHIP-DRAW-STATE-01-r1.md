# FLAGSHIP-DRAW-STATE-01 r1

2026-10-23 **IMPLEMENTED / DOMAIN_PASSED / INDEPENDENT_REVIEW_0_MUST / COMBINED_FULL_PENDING**。
[Task v1](../task-packages/FLAGSHIP-DRAW-STATE-01.md)，base `8cd76a3ae52c946206805194ef4b0b053fa6e9e9`。flagship_scout 在独立工作树编码，session_scout 独立设计/代码/原件审查；root 统一集成。

两棋平局公开 snapshot 仍有 turn_uid，桌面文字先显示轮到某人再显示平局，与图形终局状态矛盾。最小修复仅让 Gomoku/Connect4 的胜局或平局 snapshot 都无行动人，并让 GameWindow 两棋文字对旧 draw+turn_uid 快照也以终局优先。保留玩法、胜局、未终局回合、房间权限、光晕和协议版本。

| 阶段 | 实际结果 | run |
| --- | --- | --- |
| 原实现 RED | 27P4F，exit1 | flagship-draw-20261023-red-20261023-153501-51ffb05c6f |
| 首 GREEN | 31P，exit0 | flagship-draw-20261023-green-20261023-153617-afc50f701a |
| 仅新 Tk 测试清理强化后复核 | 2P，exit0 | flagship-draw-20261023-tk-cleanup-20261023-153651-03e10f443c |
| 既有输入/真实 wire/规则领域 | 3文件67P，exit0，12.321s | flagship-draw-20261023-domain-20261023-153716-b6726dbf74 |

最终 source `b9e5e414722e2a252bb5325f0e74ddabfe0ba6a2755e15bc572c4feb74caa0cd`，领域 summary SHA `e115aa1604a4eab1e8d3bd24e303b3c4376dc821d837d73d1f86e6826d51279d`。首次 RED/GREEN 只有三产品文件变化；随后只强化新 Tk 测试的原异常保留，原 RED 不是最终该测试字节。另两规则文件回归字节保持，已有通过证据有效，无需重复运行。tests/test_games_new.py 原缺末尾换行被补齐，是非语义差异。

两规则通过合成棋盘的最后合法落子形成真实 draw，核 snapshot/ended/拒绝后续动作；不是从初盘人工完整对局。真实 Tk.Text 经 GameWindow._render_state 核真实平局、旧 draw+turn_uid 和新轮文字；既有真实加密 wire 回归核终局/reset/restart，输入与棋盘回归保持。交叉独立核原始日志 SHA/计数、sandbox、单 attempt、清理及当前源码快照，0 MUST，无活动测试。主控尚待最终组合全量和终审，不提前 AI_ACCEPTED。

原件仅在隔离工作树 ignored `_tmp_gui/test-gate/`；不公开原始日志、私人资料或二进制。最终组合另行冻结一次全量。真实 Tk 文本回归不等于完整可视 GUI、自然退出、LAN、新 EXE 或整个 R2 里程碑验收。
