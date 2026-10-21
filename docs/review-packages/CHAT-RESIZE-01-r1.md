# CHAT-RESIZE-01 r1 — DPI窗口前提与真实布局同步修正

2026-10-21。**AI_ACCEPTED_TEST_BASELINE_ONLY / FULL_PASSED / LOCAL_ONLY / STOP_AFTER_DELIVERY**。
[Task v1](../task-packages/CHAT-RESIZE-01.md)。入场25998f5，原主干84444b5，保留门禁10caf9f。
分支fix/chat-resize-20261021。本聊天唯一实现/治理；gate_review独立只读，静态与领域0 MUST。

## 根因与对照

同机Windows10 19045、pwsh7.6.7、项目Python3.14.5/.venv/锁定依赖，所有run使用修正后的
同一隔离runner（SHA aec66d5d…）、合成profile/loopback/Tk私有桌面，visual/hardware均false。
原主干84444b5与25998f5由Git archive导出独立副本；只有runner/已有新回归不同，
client.py、widgets/msg_list.py、dpi.py与原测试两侧SHA相同。两侧共同使用10caf9f的执行runner，
不把这个编排补正冒称原主干runner自身已通过。没有启动第二套并行全量。

本机实测系统DPI144、app._dpi_scale1.5、Tk scaling2.0009847。client按scale设置最小680×480逻辑窗，
故实际minimum1020×720。旧测试硬编码680×480→1000×700物理像素，两者均低于minimum，
实际一直1020×720；消息区524×325、内容490，600ms后仍一样。因此原“放大”前提未成立，
不是新门禁修复引入的产品行为，也不只是稍等就能通过。

第二有限探针将目标按同一逻辑尺寸换算成1500×1050，实际消息区1004×655；原缓存490在早期
尚未失效，不能仅靠490<655判断通过。120ms resize防抖与真实回调后wrap490→970、内容490→310，
first_visible0/canvasy(0)0，并保持到后续600ms。仅等待100ms不足以证明实际完成重排。
诊断探针仅包装自然触发的resize回调作测量，不主动触发flush或滚动纠正。测量JSON与原raw均保存于
[本任务证据](../review-assets/CHAT-RESIZE-01/)，两个探针源码也随库保存供复核。

## 最小修订与验证

只修改tests/test_ux_visual_chat_regressions.py：初始/目标geometry按实际app scale换算；
新增根窗口和消息区宽高确实增长的断言；2秒上限事件循环只等目标geometry、resize_job结束、
wrap匹配当前宽度、cum非dirty，不轮询原三行为断言。随后保留原三断言逐字不动，
没有改产品代码、skip、pytest超时或数据。真实增长+缓存重排条件使测试比原固定睡100ms更严格。
不同系统DPI可能改变物理尺寸，因此修正同一逻辑交互前提，不能声称其它真实DPI已验。

| 阶段 | 实际结果 | 原run（`_tmp_gui/test-gate/`下） |
| --- | --- | --- |
| 原base测试+观测 | 13P1F，exit1；原测试文件12P1F | chat-resize-base-20261021-105935-8cff086271 |
| 原current测试+同观测 | 13P1F，exit1；原测试文件12P1F | chat-resize-current-20261021-110019-c3dba51141 |
| DPI归一观测 | 1P/exit0；只说明测量过程完成 | chat-resize-scaled-probe-20261021-110105-aa7fa203ec |
| base产品+相同修正测试 | 13P0F0S/exit0，12.3秒 | chat-resize-base-corrected-20261021-110235-eb3aa69843 |
| 当前领域7文件 | 68P0F0S/exit0，39.078秒 | chat-resize-domain-20261021-110305-23131deb95 |

各次独立新run，无失败覆盖。正式测试入口为`.venv/Scripts/python.exe run.py test-all`；
对照加`--source-dir _tmp_gui/chat-resize-20261021/base`或`current`；选tests/test_chat_layout_probe.py
与tests/test_ux_visual_chat_regressions.py。scaled版本选test_chat_layout_scaled_probe.py。
领域选择test_ux_visual_chat_regressions、ux_visual_chat_dpi、ux_visual_chat_design、ux_repair、
msg_list、msglist_group、settings_nav七文件，`--label chat-resize-domain`。
修订test SHA256 `5fb6261af89eac2ec35ec88e8f347931c52069f0047bb9aa45cd869aca4b62d2`；
领域source `d9b482adbc3b24cb54a5e2784d89cb0d421265c127b1eec9f38adfc668560d1c`。
gate_review核对实际diff、原三断言、两版原失败/修正base/领域raw、单attempt/cleanup/hash，0 MUST。

全量前阶段约定（现已完成）：仅此测试候选本地提交、同版唯一最终全量与原证据独立终核。旧GATE-BOARDGAMES-01
2904P1F20S/exit1保留历史，不以专项通过改判；不push/PR/merge/发布。不改系统DPI、不执行设备/截图。
完整EXE/物理LAN/其它真实DPI/完整GUI自然退出仍未验证。

## 原失败复现入口

两版原样输入保存在对应run的`source`快照；后来的base工作副本已替换为修正测试供对照，
不能将工作副本当成原样失败输入。必要时可从项目根目录对原快照启动新的有限run：

```powershell
.\.venv\Scripts\python.exe run.py test-all --source-dir _tmp_gui/test-gate/chat-resize-base-20261021-105935-8cff086271/source tests/test_ux_visual_chat_regressions.py --label chat-resize-repro-base
.\.venv\Scripts\python.exe run.py test-all --source-dir _tmp_gui/test-gate/chat-resize-current-20261021-110019-c3dba51141/source tests/test_ux_visual_chat_regressions.py --label chat-resize-repro-current
```

这两条是接手者可用的复现命令，本轮没有重复执行；原run及日志没有被覆盖。

## 最终完整门禁与独立终核

测试提交`ee487cb`，只1测试文件24+/4-；产品client/msg_list/dpi与原主干保持，门禁10caf9f保留。
命令：`.\.venv\Scripts\python.exe run.py test-all --label chat-resize-full`。
205文件2905P/0F/20原opt-in S，exit0，737.026秒。run：`D:\project\321_FISH\_tmp_gui\test-gate\chat-resize-full-20261021-110511-e3c3b76ae4`。
source `d9b482adbc3b24cb54a5e2784d89cb0d421265c127b1eec9f38adfc668560d1c` / 482输入，与领域/当前/snapshot逐hash一致。
summary SHA256 `171758b3ba63ca92a96267310e4055e86e137cfe85b21db17652d5c0f09958f2`。
[完整summary](../review-assets/CHAT-RESIZE-01/full-summary.json) / [后验检查](../review-assets/CHAT-RESIZE-01/verification.json) / [目标原日志](../review-assets/CHAT-RESIZE-01/full-regressions.txt)。
205条全单attempt/cleanup true，原raw SHA逐项匹配；无unexpected skip，visual/hardware flags均false。
跳过仅r45硬件1项、shots视觉18项、visual_screenshot视觉1项；未改变skip、pytest超时或原三条行为断言。
gate_review独立代码/领域/最终原证据与资料核对0 MUST；没有参与写入或启动第二套测试。

主控据独立证据技术接受本次测试几何/异步同步修正与当前组合源码门禁基线。
此前2904P1F20S及两版对照FAIL保持失败历史；本次新source/新full全绿不覆盖旧记录，
也不回溯解释其它旧环境的不同断言。此结论不是用户/Pro产品验收、完整R1或发布接受。

## 本地交付与恢复

本分支`fix/chat-resize-20261021`，最终资料leaf见Git log。工作区及原证据字节检查完成后本地提交即停止，
不push/PR/merge/发布，无本批活动应用/测试/构建或待恢复进程。
实际只验证本机144DPI的真实Tk窗口增长与重排；100%/125%/跨屏DPI、EXE/物理LAN、
完整GUI自然退出均未验证，7项DPI单测契约不替代真实矩阵。系统缩放/真实资料未改。
恢复入口：`D:\project\321_FISH\AGENTS.md` → `docs/AI_COMMAND_CENTER.md` → 本Task/Review → Git及实际进程。
下一最高优先级小候选：UI-ROOM-ICON-01（已静态确认房间卡片缺PhotoImage强引用）；
仍为DRAFT，下一批先真实Tk复现/冻结，再最小修复。本轮到此停止，不自动扩展。
