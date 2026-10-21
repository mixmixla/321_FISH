# UI-ROOM-ICON-01 r1 — 房间图标存活与释放

2026-10-21。**AI_ACCEPTED_TK_COMPONENT_ONLY / FULL_PASSED / LOCAL_ONLY / STOP_AFTER_DELIVERY**。
[Task v1.1](../task-packages/UI-ROOM-ICON-01.md)，base f693653，分支fix/room-icon-lifetime-20261021。
保留提交链84444b5→10caf9f门禁补包→25998f5资料→ee487cb聊天DPI测试→f693653资料；
本轮不重做/回退这些工作。root唯一实现/治理，gate_review独立只读、未写源码或启动第二套测试。

## 实际根因与最小修复

_RoomCard临时game_icon_image传入tk.Label后没有Python强引用。实际factory每次创建新
ImageTk.PhotoImage，Label只保留Tcl名字；Python对象析构删掉native image。tkguard仅守护
线程销毁，不是图片缓存，不能保持图片存活。
最终新5case配原生产代码真实RED5F/exit1：4项明确Label仍有pyimage名字但Tcl image已删除；
生产GameWindow._refresh_rooms调用_highlight_room配置Label时亦出现`image ... doesn't exist`。
这不是只读推断或假factory模拟。

仅client.py的_RoomCard把原factory结果保存在self._room_icon_image，再传原Label。
实际生产diff4+/3-，无全局缓存、无Destroy钩子、无shared guard或图形/颜色/规则/依赖改动。
每张卡片各自拥有图片；正常destroy并释放卡片后，主线程GC释放Python/Tcl图像。
仍被外部Python引用保留的card保持自身image属于所有权范围，不声称destroy本身强制清空外部引用。

## 回归与原始证据

同机Windows10 19045、pwsh7.6.7、项目Python3.14.5/.venv/锁定依赖；统一安全runner，
合成profile/loopback/private desktop，visual/hardware均false。真实Tk不可用会失败而非环境skip。
新测试tests/test_room_icon_lifecycle.py不patch图标factory、不使用fake图片；实际Label映射、
native image15×15及非透明像素存在，3次GC后保持，Tk event_generate点击仍触发原绑定。
重复同game卡片image名字独立；销毁释放其中一张不影响另一张，最后Tcl image数回到baseline。
组件host使用GameWindow.__new__、synthetic room/core输入，但filter/refresh/highlight均为生产方法，
实际创建/销毁真实Tk卡片；12轮状态变化刷新，容器destroy/rebuild及空房间清空，旧card weakref
均回None，native image总量每轮仅baseline+当前2张；另覆盖Tk root解释器destroy/rebuild。
不把组件事件/host测试称OS鼠标、完整大厅/游戏流程或GUI自然退出验收。

| 阶段 | 结果 | 原run（`_tmp_gui/test-gate/`下） |
| --- | --- | --- |
| 最终新测试配原代码RED | 5F/exit1，4.223秒 | room-icon-red-20261021-112519-c96fe2f105 |
| 同5case修绿 | 5P0F0S/exit0，4.055秒 | room-icon-green-20261021-112559-03043d3d37 |
| 领域9文件 | 57P0F0S/exit0，34.945秒 | room-icon-domain-20261021-112651-f1896635b1 |

[公开原证据](../review-assets/UI-ROOM-ICON-01/)保留RED/green/domain原summary与目标raw。
RED后测试字节未动，SHA256 `02e669c17c3a89f1d682581861a51ba69175710e72ca9feda1637fa4b5037ac7`。
green/domain source `2dc0c20008aa8288b8746eb2f65a497fe1ee1910da022ab02a16a67dc039e588`，483输入。
命令均`.venv/Scripts/python.exe run.py test-all ...`；RED/green只选tests/test_room_icon_lifecycle.py，
label分别room-icon-red/room-icon-green。domain选择room_icon_lifecycle、game_shell_wiring、
game_shell_pal、gameui_compact_gui、rooms、boardgame_asset_img、ux_visual_chat_design、
ux_visual_chat_regressions、gate_boardgames九文件，label room-icon-domain。
gate_review已独立核对Task/diff/原5F→5P字节及生命周期边界，代码/专项/领域/最终full原证据终核0 MUST。

## 冻结候选与终点

全量前阶段约定（现已完成）：仅此生产/测试本地提交后，唯一同版206文件完整门禁与独立原证据终核。
不覆盖前两项旧FAIL/新full，不修改skip/断言/超时，不盲目重复全量。
本轮终点为本Task局部修复/验证/资料提交；不push/PR/merge/发布或自动新增功能。
完整EXE、物理LAN、其它真实DPI、OS鼠标完整大厅/游戏与GUI自然退出仍未验。

## 最终完整门禁与独立接受

生产/测试提交`c8377f8`，仅client局部4+/3-及新171行回归。
命令：`.\.venv\Scripts\python.exe run.py test-all --label room-icon-full`。
206文件2910P/0F/20原opt-in S，exit0，729.549秒。原run：`D:\project\321_FISH\_tmp_gui\test-gate\room-icon-full-20261021-112910-13b665dd0e`。
source `2dc0c20008aa8288b8746eb2f65a497fe1ee1910da022ab02a16a67dc039e588` / 483输入，与green/domain/当前/snapshot逐hash一致。
summary SHA256 `2748e014cf9b0eff7f149932a109e54ebc30161058d381e99949cf239cedb9f7`。
[完整summary](../review-assets/UI-ROOM-ICON-01/full-summary.json) / [后验检查](../review-assets/UI-ROOM-ICON-01/verification.json) /
[全量目标raw](../review-assets/UI-ROOM-ICON-01/full-room-icon.txt)。
206条均单attempt/cleanup true，原日志逐SHA/退出码一致；visual/hardware flags均false，无unexpected skip。
20原opt-in仅r45硬件1、shots视觉18、visual_screenshot视觉1；旧205文件与2925case完整保留，
只新增此5case（总2930），与上一全量输入差异仅client.py和新增test_room_icon_lifecycle.py。
门禁test_gate.py/其新回归及聊天DPI测试的hash保持不变，没有删改前两项交付或覆盖旧FAIL。
gate_review独立核对Task/diff/RED/green/domain/full原raw、快照与公开字节，未参与实现或另起测试，0 MUST。

主控据独立证据有限技术接受本项真实Tk组件图标存活/释放和当前组合源码门禁。
不等于用户/Pro/完整大厅或游戏流程、整个R1/R3、EXE或发布接受。

## 交付、边界与整体下一阶段

最终资料leaf以本分支Git log为准；本轮只本地提交，不push/PR/merge/发布。
所有本批应用/测试/构建已结束，资料/工作树检查与本地提交后停止，不无限新增任务。
本次无构建；OS鼠标完整大厅/游戏、完整EXE/自然GUI退出、物理LAN/外机/其它真实DPI未验证。
恢复入口：`D:\project\321_FISH\AGENTS.md` → `docs/AI_COMMAND_CENTER.md` → 本Task/Review → Git与实际进程。
下一阶段建议：按当前冻结源码准备有限R3交付验收Task，白名单构建server/client/StartTrial三EXE，
用fresh合成资料完成本机两客户端一局→结束再开→返回聊天→自然退出，并记录可选能力/产物哈希/已知边界。
真实交互工具或人工未具备时保留未验，不用协议探针/强停替代；外机/物理LAN另定范围。
该阶段仅PROPOSED，不是READY或本轮自动执行；不以当前全绿证明完整R1/M1或发布完成。
