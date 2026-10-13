# RUMMIKUB-SELECTION-01 v1 — 最近棋盘取消选择不得提交旧牌

2026-10-13。用户已明确授权root处理client.py拉密残留，基线2826784及审阅后的UI
整合bb84967。状态只见[指挥中心](../AI_COMMAND_CENTER.md)。

## 实证与范围

08d263b独立复现：大厅选18/20/22，最近专注棋盘对42点选再取消到空；按钮的首个
非空扫描跳回大厅旧牌。真实RummikubGame接受并移走三张、留42。新测试必须证明
最近操作的空选择为权威，无动作、规则完整状态/RNG不变，提示先点选。

root唯一client.py作者，仅改GameWindow._submit_sel选择来源；不改client_gameui.py、
规则/协议/其它游戏或存储。新增test_rummikub_selection.py验证两向取消、无选择、
合法选择/默认来源、真实规则副作用及弹窗上下文合同。Kalah controller另Task协同
同一作者，不改UI窗持有模块。

实现：只取_board_uis返回的首个最近/默认候选，不再扫描另一棋盘非空数据。
未操作时默认顺序由原_board_uis保持，提交后清所有候选同名选择原行为保持。
不借此改自动跨窗同步、撤销、历史或选择生命周期。

验收：RED保存；修复后真实点击选择→取消与真实规则、必要Tk事件和现有来源/弹窗
回归通过；独立实际diff/原证据审查无MUST。最终整合门禁由root唯一安排，原full
2323P/3F/2S不抹掉，领域通过不等整体AI_ACCEPTED/发布。仅任务分支commit/push，
PR连接403不重复尝试；不merge/release/main push、真实资料/设备/公司项目/CP4。
