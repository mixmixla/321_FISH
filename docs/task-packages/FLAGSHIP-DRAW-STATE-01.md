# FLAGSHIP-DRAW-STATE-01 v1

2026-10-23，READY，属于本次两项有限并行批次；设计审查通过后方可修改产品。base `8cd76a3ae52c946206805194ef4b0b053fa6e9e9`。沿用用户本周公开干净交付和正常直接集成 main 的授权，不发布。

## 问题与产出

五子棋、四子棋平局 snapshot 仍带 turn_uid；GameWindow 的文字摘要先显示轮到某人再显示平局，与已阻止落子并优先显示平局的图形状态矛盾。本批让两棋平局公开快照的 turn_uid 为 None，并使桌面摘要对旧的 draw+turn_uid 快照也优先呈现终局。保留非终局轮次、胜局、规则判定、玩家/观战权限、重开与光晕参数，不扩其他游戏或视觉设计。

## 所有权与隔离

flagship_scout 唯一编码，分支 fix/flagship-draw-state-20261023，worktree `_tmp_gui/worktrees/flagship-draw-20261023`。允许 games_pkg/gomoku.py、games_pkg/connect4.py、client.py 的相应 snapshot/摘要最小差异，tests/test_gomoku_rules.py、现有 Connect4 回归所在 tests/test_games_new.py，及新增 tests/test_flagship_draw_state.py。不得修改 server.py/client_core.py/另一线测试或主工作区。主控独占文档；session_scout 对此补丁独立审查，不能参与实现。

## 验收

先原产品配新断言确定性 RED，保留失败。两棋真实规则形成的平局公开快照均无可行动 turn_uid，且 ended 正常；胜局与未终局轮次保持。桌面摘要对真实平局及带旧 turn_uid 的平局都不出现轮到提示，正确显示平局；补真实 Tk 组件状态更新所见文字和必要终局再开/动作拒绝对照。可以使用合成规则状态完成最后合法一步，不伪称完整人工对局。无需改协议版本、Web、glow 或规则玩法。

只运行该线 RED、受影响选测与必要领域，不启动全量。沿用根项目 .venv 的 Python 3.14.5，以工作树为 cwd 运行 run.py test-all 隔离门禁；不新建环境、不碰真实配置/历史/设备。root 与另一线统一门禁前不得重复测试同一个候选。逐项清理自有 Tk/线程，保留原失败与既有 skip。

独立设计/代码/原证据审查 0 MUST 后，由主控一次组合全量、终审、全部新对象脱敏审计和普通集成 main。公开仅必要代码/测试/文档/脱敏摘要，原日志与二进制仅本地。真实 Tk 文本回归不等于完整可视 GUI、自然退出、LAN 或新 EXE 验收，不升级整个 R2 里程碑。
