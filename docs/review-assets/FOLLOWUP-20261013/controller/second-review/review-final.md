# RUMMIKUB-SELECTION / KALAH controller 独立审查 r1（2026-10-13）

**CODE_REVIEW_PASS_LIMITED — 0 MUST，限client.py与两份controller测试**。这是独立审查主窗口实现，不是实现者自验；我的client_gameui.py/Web实现完全排除在本次独立实施审查之外。主控决定AI_ACCEPTED与整合/完整验收，本报告不作整体发布结论。

## 审查版本与变化

最初HEAD bb8496786f54f40118a9eae49610979d9811da97没有client.py差异，记录于[早期检查点](review-early.md)。收尾检查时主控实现落地，随即转而审新实际diff，没有继续用“未就绪”作当前结论。

复核时HEAD已推进至106ee93ffa2871b86ce675bd62e3cc62211d898b，client.py仍为dirty独立交付。所审client.py SHA256：

`e6b05f0e15157776aab2c45a39e5a3e9f0c62cb4b10a3efe2178041f6d344dee`

当前两测试输入hash：

- tests/test_rummikub_selection.py：`08dcc3026a901dc323bb3ddf101303ebbf670cc9ad0ecca0db2a82035d90ae01`
- tests/test_kalah_parameters.py：`f9303d64456673ed621fa1586c71ac01c43caa85328e23857a328cdb3a0f3c87`

controller实际diff为53新增/11删除，冻结RUMMIKUB-SELECTION-01 v1与KALAH-INPUT-01 v1.2。其余主窗口整合提交/治理资料不作为本次独立代码审查对象。结论绑定文件hash与下面同源门禁证据；代码/测试后续变化应重新核对。

## 结论依据

- client.py:13439 `_submit_sel`只取候选0，空选择直接提示并返回，不再扫描另一棋盘旧牌。两向取消最后选择、其它棋盘合法旧牌不泄漏；候选清理、默认来源、无选择不打开接续弹窗维持冻结合同。inactive非候选状态不被此次修复自动清理。
- :13478 `_ask_params`对Kalah参数捕获room/round/game/UID/p0/p1，输入返回后重新比较；调用单独转换器一次，不改变其它游戏int解析。
- :13526本方1..6分别映射A wire1..6/B wire9..14，拒绝0/7/9/-1/非整数/取消。与真实Kalah规则的自然A→B与12个六洞独立克隆结果一致；没有图形wire二次偏移。
- :13534最新core校验连线、有效Kalah房间、playing、无winner、真实p0/p1/座位/turn、十四格与己方非空洞。前置或弹窗期间的状态变化均不能产生game_action。
- :13691 `_do_action`的Kalah专属最终wire检查与来源room-round/state对象/me校验，拒绝原UI用于新room/round/game/snapshot/UID和结束/空洞等；合法global wire直接发送。
- :13184摘要按真实p0/p1昵称与当前UID标“你”；A/B/观战身份、上排13..8/库7、下排0..5/库6与规则一致。

没有发现当前被审代码的确定阻断或需要扩大批准范围的修改。审查不把测试通过当全面产品/并发/LAN保证。

## 独立轻量证据

[probe.py](probe.py)从所审client.py原样AST提取controller方法，使用真实Kalah规则及合成输入；不导入client登录/资料模块、不建Tk root、不启动网络服务或正式pytest/gate，不修改主窗口源码。67个有限用例均PASS，真实退出码0，运行前后client.py hash相同。

用例覆盖双方12个本方洞；before/during旁观/轮次/room-ended/和局/胜局/空/断线/非座位/错state；五类modal context变更；六种非法本地方号/取消；九种global来源情形与七种非法wire；三角色摘要；拉密两向取消、四种默认来源；其它整数参数控制。[原结果](probe.json)。这不替代真实Tk或原始正式门禁。

## 主控原始领域证据核验（没有重复执行）

实际原run-dir：`D:/Project/321_FISH/_tmp_gui/advance-20261013/controller-ui-domain`。

12文件**220 PASS / 0 FAIL / 0 SKIP、exit0**。本次只读原progress/summary及日志，逐一核12个single attempt、12个raw log SHA256、cleanup_ok均true与所有真实退出码0；未重跑测试。

所审client.py和两controller测试与该run/source逐字节一致。source_content_id `b81b266a532dcaedc1e86786e57f4ead1f31e10e4e73567dbad90924d89a378b`，fingerprint `9444112b4cd357fe70bd341e0089fbaf90c904a8f005f2d33b49376e9ed57739`。见[独立核验](domain-proof.json)。

其中主窗口controller专属：test_kalah_parameters.py 58 PASS（含四个实际GameWindow._render_to/两真实_on_click入口、双方A/B、旧round拒绝与规则合法wire）；test_rummikub_selection.py 7 PASS（含两向真实Tk选择/取消和完整规则/RNG不变）。已读两原日志尾部真实数量。其余领域项目的结果只作原证据完整性核对，不据此独立验收我的UI/PAGE生产实现。

初次测试读取过程里观察到inactive focus清理断言和仅pre-modal守卫覆盖问题，主窗口已在最终文件中分别改为active/非候选分支与before/during参数化。已向主窗口明确撤回当前MUST，不能把旧片段当当前缺陷。早期报告与版本变化保留，不覆盖失败历史。

## 范围与剩余事项

本轮已完成独立controller代码/测试/原领域证据审查，建议主窗口按上述范围记录技术接受。不要沿用最初“未就绪”状态；这是后来实际落地版本的审查结果。

自己的UI/PAGE实现由主窗口/其他独立审查者负责，本轮未重复自审冒充独立审查。未改主窗口文件/治理文档，未启动应用/网络服务/全量/构建。正式合并候选完整门禁、物理键鼠/当前controller真实整窗视觉、DPI/EXE/LAN/发布证据仍由主控按任务与当前状态安排，历史full FAIL保持。
最后观察：主控HEAD已成为3877a5d4cbbbf25364303210e1f0f74b4eeac542，worktree clean；client.py与两controller测试hash仍与本报告/领域源码相同。文件级审查结论因此保持，但本轮不审其余新增提交或新HEAD完整全量/发布状态，最终复核另由父线程安排。
