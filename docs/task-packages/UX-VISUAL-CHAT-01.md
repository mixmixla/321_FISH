# UX-VISUAL-CHAT-01 v1.5 — 雾岸统一样式与聊天主窗

2026-10-09。用户在原视觉聊天要求继续视觉改造；按[Prompt v1.1](../后续开发Prompt_UX-TRIAL-01.md)及已接受的[A雾岸设计](../design/UX-01-design-system.md)推进。主控已核接管任务idle与实际进程，不重启账号存储任务。状态与唯一写入者只见[指挥中心](../AI_COMMAND_CENTER.md)。

v1.1仅补入MsgList装饰背景的语义开关：旧源码所有皮肤固定画涂鸦，统一主题必须能在雾岸关闭，不改变富文本、消息存储或传输。初始截图fixture未完成同UID历史加载，已修正fixture并保留首图；不能把fixture缺少bootstrap误当生产消息样式缺陷。

v1.2补齐同一语义来源的配对雾岸深色与强调色上的文字角色，避免深浅切换回旧暖粉体系。两端均验证文字对比；其余历史皮肤保留兼容，不在本片全面重做。

v1.3来源为用户补充“整个桌面端都粗糙且很糊”。独立源码/官方规范核对发现托盘先创建Tk、DPI声明晚到及-3误注SYSTEM_AWARE；补允许dpi.py仅修正声明常量、client.main的DPI/托盘顺序及ChatWindow直接构建前声明，保留显式dpi_aware关闭语义，不改变系统缩放或贸然引入未实现的跨屏PMv2。统一字体默认11pt/辅助10pt、会话几何按当前DPI缩放。新增已有dpi_aware读取使静态引用计数增加，仅允许test_local_prefs_rules按实际数量适配，59键/动态Counter断言保持。

v1.4加入生产PAGE实际函数的Node导航/主题行为探针；既有web_navigation_probe.cjs仅把新uxSelectNavigation纳入提取的真实依赖，不stub掉导航行为。独立审查的面板关闭/进入房间selected收束、字体同步、旧深色禁用和Web全语义变量均在本片整改。

v1.5源于领域门禁171 PASS/1 FAIL：Node探针未被隔离源码枚举收集，实际报MODULE_NOT_FOUND。仅允许test_gate.py把tests/*.cjs作为测试输入纳入同一快照/哈希/隔离副本，不改运行策略、重试、FAIL判定或任何既有门禁；保留原失败。此变更是让真实Web探针进入正式验收，不以直接运行替代隔离验证。

## 目标与完整路线

把已接受的雾岸方案落实到运行中的桌面/Web聊天主窗：清晰的三层布局、统一图标/组件、主要消息与输入空间、可读且不透明的默认入口。必须有明显布局/层级/组件改善，不能仅换色或新增一套闲置皮肤。

本批先闭合统一样式与聊天；后继有限批次继续大厅/两旗舰棋盘、登录/设置/Excel、窗口恢复和完整独立视觉验收。所有页面仍是原Prompt硬性目标，本批通过不等于整体视觉、R1或最终试用完成。

## 冻结范围

1. 原语义JSON token作为规范来源，生成可随EXE打包的Python消费/导出模块；Tk与Web实际消费同一份颜色、字体、间距、状态和线性图标。导出一致性校验，禁止各页独立堆另一套常量。
2. 新默认入口采用mist/雾岸；历史皮肤名称保留，用户已选皮肤不静默重写Prefs。默认窗体不透明；明确可选透明规则保留，不改变设备/系统设置。
3. 桌面聊天：导航带统一线性图标和持续名称，会话列留白与搜索/分组层级合理，消息区为主体；标题/连接/选中/未读/失败状态清晰。输入拥有独立空间，附件/表情等高频可发现，低频沿有名称的更多菜单；发送/只读/草稿/引用/编辑/Enter与Shift+Enter及Excel发送接线保持。
4. 初始化时应用完整样式，修复会话Canvas初始与主题不一致；换肤对新图标、输入、会话选择和焦点即时生效。统一default/hover/pressed/focus/selected/disabled，不能用仅颜色变化表示不可操作。
5. Web聊天：同版token导出，移除默认聊天区的大面积渐变/噪点/玻璃穿透，强化头部/会话/消息/输入层级；统一工具图标及可见名称、焦点/触控目标；保留已有伸缩、窄屏抽屉、独立消息滚动和输入稳定。
6. 当前所有认证/历史/收藏/权限/协议与CP4实现保持；不借视觉批次修改ClientCore、Prefs、server或迁移真实资料。Web只改PAGE前端视觉与视觉偏好，不改HTTP业务处理。

## 写入边界

root唯一实现写入者，代理只读独立核对。1079公开文件入场已备份，HEAD c864234e09f97a32e3df871b5bd7c13312adeed7、codex/local-trial-20261003，原dirty保持；source 5b500b25cec78aa1a38676d96887ec79b10f4fa37210b40de0c2fe53ba329e81/377输入。

- 允许：theme.py；client.py仅主窗构建/输入/导航/视觉状态/换肤及DPI/托盘启动顺序；dpi.py仅声明常量与诊断必要只读信息；widgets/session_list.py的视觉/DPI几何；widgets/msg_list.py仅视觉token消费/装饰背景，不改既有runs/数据/媒体逻辑；web.py仅PAGE前端及语义CSS注入；新ui_design.py与widgets/design_controls.py。
- 允许测试：新tests/test_ux_visual_chat*.py、tests/ux_visual_chat_probe.cjs；既有tests/web_navigation_probe.cjs仅补提取真实导航函数依赖；tests/test_theme.py及tests/test_session_list.py仅新默认/选择样式的直接合同适配；tests/test_r43c.py仅DPI矩阵/常量/时序；tests/test_local_prefs_rules.py仅静态读取总数适配，保留59键/动态Counter/全部其他断言。其它测试先记录最小Task修订。
- 允许资料：本Task/Review/assets、中心/投影、必要PROJECT_MEMORY稳定事实；UX-01.tokens.json可版本化补齐运行导出元数据；原设计/截图/历史TaskReview及接管证据保护。
- test_gate.py仅允许收集tests/*.cjs测试输入，保留全部隔离/失败/退出/恢复语义。build.py/spec/launcher/登录/设置/Excel/棋盘/认证/存储模块默认不改；若打包只需本静态Python导出，不新增资源收集。

## 证明与验收

- 新旧截图分别绑定实际源码，同合成数据/同尺寸；覆盖桌面/Web聊天、输入、导航、更多、离线/失败、普通与最小窗口、可用100%/125%/150%DPI。现存用户窗口不操作，另用fresh合成profile/loopback。
- 图标/状态对比与实际布局检查；消息/草稿/选择/编辑/回复/只读/键盘测试保持。颜色或静态截图不足以替代实际交互。
- 实际Tk/浏览器鼠标键盘验证；EXE按同版重新构建并绑定身份。工具/设备未具备的项具体待验，不能编造完成。认证弹窗不借视觉测试自动输入真实凭据。
- 受影响主题/会话/消息/键盘/Excel与Web领域；最终候选依仓库完成fresh完整门禁，保留当前历史完整FAIL及原2个opt-in，不将旧CP4故障改称已修。
- 独立代码与实际截图/原始证据视觉审查MUST闭合，比例、阅读层级、排版、配色、间距、状态、操作可发现性明显改善，才有限AI_ACCEPTED。不是用户审美认可或发布接受。

## 授权与Goal

用户当前请求恢复的是视觉工作。接管任务已idle，此处按新有限视觉Task接回唯一写入责任；旧账号Goal保持paused，不改变其目标、完成或未知存储结论。未获远端交付/真实数据/设备/系统设置/向其它聊天发消息权限；所有验证合成资料、loopback、pwsh及本项目.venv。

本聊天仍有未完成的暂停账号Goal，不能伪造完成来腾出Goal槽或把它重命名成视觉成功；当前视觉工作按此用户请求与有限Task执行，若工具拒绝新Goal如实记录，不以此停止已获授权的普通视觉实现。各有限批次完成后保存下一项，不自动恢复账号/ProcMon或发布。
