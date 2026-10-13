# 拉密/Kalah controller 独立只读阶段复核（2026-10-13）

**IMPLEMENTATION_NOT_READY / TESTS_REVIEWED_STATICALLY**。未对新实现给通过或AI_ACCEPTED；未审自己实现的client_gameui.py/Web部分冒充独立审查。

## 当前版本与证据边界

主窗口：`D:/Project/321_FISH/_tmp_gui/gate-collection-20261013`，branch fix/gemcity-purchase-20261013，HEAD **bb8496786f54f40118a9eae49610979d9811da97**。两次核对client.py diff均为空，SHA256 **8c819641ab066a52a6706831c7ba68058e7a19759cb5bc8846d89de12f234eaf**。生产新实现尚未落地。

后续主窗口并行新增tests/test_rummikub_selection.py、tests/test_kalah_parameters.py，仍未提交。最后读取的测试hash分别为：

- rummikub：08dcc3026a901dc323bb3ddf101303ebbf670cc9ad0ecca0db2a82035d90ae01
- kalah：5ec05dcdb0c0926344554cf08454d5214a3f95289942e637020e1fa6dd9bab37

测试在本轮编写过程中变化，结论只适用上述读取范围，不冻结主窗口后续写入。未来代码/测试/HEAD变化必须重新绑定审查。

## 已读范围

RUMMIKUB-SELECTION-01 v1与KALAH-INPUT-01 v1.1冻结合同、当前GameWindow._board_uis/_submit_sel/_ask_params/_parse_action入口、两份controller专属新增测试。静态阅读覆盖：

- 拉密两向真实Tk选择→取消、最近空选择权威、规则完整状态/RNG不变、合法默认源、双方候选清理与无选择不打开接续弹窗。
- Kalah真实规则自然A→B、双方本方1..6→A1..6/B9..14、room/round/game/UID/座位互换的弹窗上下文、旁观/轮次/room-ended/和局/胜局/空洞/断线/非座位/错state的before/during条件、非法0/7/9/-1/非整数/取消、真实双方/观战摘要、其它整数参数不变。
- 主窗口已开始补直接global wire从最新core复核的测试；该尾段仍在编写，本轮未对其未来实现或完整结果给通过结论。

未执行这些新增测试，因为主窗口负责RED/实现/相关门禁；未启动网络服务、应用、全量、构建，未写主窗口文件。

## 仍待实现审查的旧行为

client.py:13445仍扫描候选的首个非空选择，会在最近棋盘取消最后一项后回取另一棋盘旧牌。client.py:13523仍原样int(text)，13492/13515仍原样parse/发送，11512仍提示本方1~6，未见Kalah映射/最新状态守卫；13184摘要仍固定A下排称“你”。这些是已冻结的旧问题，不作为“新修复引入缺陷”。

新实现落地后必须核：只取首候选，包括空；两棋盘切换与默认源不回退；Kalah本方n映射A n/B n+8并拒绝用户直接wire9；弹窗返回时身份/context和可操作最新状态再核；旁观/结束/空洞/非法值不调用game_action；摘要按p0/p1和真实UID输出。

## 初读问题的版本核对与撤回

初次读取中的拉密默认源测试把inactive focus也要求清空，超出冻结“候选清理保持”合同。精确AST轻探针确认last=None/focus inactive时_board_uis只返回lobby，提交会清lobby而保留focus的[42]。随后重新读取当前文件，:91..95已按if active/else正确处理。已直接向主窗口撤回当前测试MUST判断；当前版本没有这条问题。

初读Kalah“latest state”测试只在弹窗前mutate；随后当前版本:83..116已增加phase=before/during并在输入回调中mutate。覆盖建议已落入当前测试，不再列当前缺口。

唯一执行的轻探针为标准库AST提取当前_board_uis/_submit_sel，合成dict与录制发送回调；不创建Tk或导入账号/网络模块。结果：candidate_count1，inactive_focus_is_candidate=false，sent meld18/20/22，lobby清空、focus保留42。该探针核实候选生命周期，不替代实现/正式测试验收。

## 本轮结论与下一动作

当前两份测试静态读取范围未发现仍有效的确定阻断；**新生产代码未就绪，不能做独立实现审查通过**。主窗口继续其RED/实现与领域验证；在新client.py diff、确定测试版本和原证据齐备后，再分配独立审查。此次不无期限等待、不重复测试；自己的UI/PAGE提交仍由其他审查者/主窗口独立评估。