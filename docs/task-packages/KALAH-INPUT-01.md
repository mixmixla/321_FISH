# KALAH-INPUT-01 v1.2 — 播棋第二方输入与自身编号

2026-10-13。用户本轮明确授权root与UI窗按只读证据修复第二方输入；协议保持不变。
执行状态/版本/进程见[指挥中心](../AI_COMMAND_CENTER.md)。

## 依据与冻结合同

原08d263b正常A首洞后，B只接受内部index8..13（wire hole9..14），但桌面只有A
鼠标热区、参数框1..6原样发送；Web上排slice(13,7)为空且全部按钮发送1..6。
实际规则/索引证据与只读计划由UI窗保存，交付时归档，不改服务器act。

- wire `action.hole`恒为cells全局index+1。
- 本方显示编号local1..6按逻辑index升序：A local n→global n-1→wire n；
  B local n→global n+7→wire n+8（9..14）。
- 固定棋盘A下排从左至右local1..6；B上排环路反向，左至右local6..1（global13..8）。
  热区/按钮保留global index，点击发送global+1，不能从反向位置j再次猜编号。
- 第二方摘要、bank/回合与最近步按真实UID/index：B last index8..13→b_holes[index-8]。
- 结束、观战、非本人回合或空穴不提交；参数弹窗前后room/round/game/UID必须一致。

## 文件所有权

root：client.py，仅Kalah参数框本方1..6映射/上下文守卫及对应新测试，仍是该核心模块
唯一作者（拉密另有Task）；治理、Review、集成证据、PROJECT_MEMORY由root维护。
v1.1按用户最新补充，root同时修摘要固定“你/对手”的身份倒置：按p0/p1真实昵称
并只对当前UID标记“你”，观战不自称；银行索引6/7和双方显示洞序保持。
v1.2主控实际调用链复核：图形热区重查ui.state仍可能是旧snapshot，submit闭包调用
当前core room；故client.py _do_action须加Kalah专属最终global wire守卫，图形来源的
room/round、state对象与me必须等于当前core，实时身份/轮到/结束/连线/非空再次检查。
参数已独立复核弹窗身份，无图形来源；global wire不得再次按local映射。增加真实
宿主与规则的旧热区→新core状态/房间/轮次/UID拒绝和合法直传回归，不改公共协议。
UI窗：client_gameui.py、web.py，仅本播棋输入/编号/摘要/最近步修订及Kalah专属新测试，
从其已交c549239另开独立分支/worktree。root交付齐备前不改这些两个核心模块。
不改games_pkg/kalah.py、协议/数据/其它游戏、美术全局或CP4；不构建、发布或改系统。

## 验证与接受

- RED原实现证明双方输入不对称；真实Kalah规则正常A首步后，B每个非空洞能以本方
  local1..6正确映射/点击；渲染方向、标签、last_move与规则状态一致。
- 真实Tk/生产PAGE合成输入，双方/非轮到/观战/终局/空洞、换room/round/game/UID
  弹窗回调拒绝；不stub掉导航或动作，不操作真实账号/设备。
- UI窗仅轻领域、原日志/hash/source/单attempt/cleanup与实际画面证据交主控；不重复full。
- root独立读实际diff/证据/画面再整合，相关领域与适用完整门禁由root唯一协调。
  现有full2323P/3F/2S原FAIL保留，未全绿不得记录整体AI_ACCEPTED/merge-ready。
- 仅commit/普通任务分支push/Draft（若连接可用）；不merge/release/main push。
  14:30不新开大任务、15:00前收尾。
