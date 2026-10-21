# R3-ENTRY-WIRE-01 r1 — compiled实际编排与owner死亡清理

2026-10-21 **AI_ACCEPTED_ENTRY_WIRE_OWNER_DEATH_ONLY / NOT_MERGED / NOT_R3_ACCEPTED**。
[Task v1](../task-packages/R3-ENTRY-WIRE-01.md) / [脱敏结果/hash索引](../review-assets/R3-ENTRY-WIRE-01/evidence.json)。base/main60569347ed3cf93a787a9e6b54bab226c3f4d77e，feature/r3-entry-wire-20261021；root唯一写入/执行，gate_review独立只读，普通模型/Standard。

## 版本与执行路线

本批仅验收资料，无产品/工具/测试/依赖/构建源码变化。根488/source `dcf9dfb850acd8530274165b6984655ef457ccc077d438978ffe1cdacbd18757`同已验211文件2958P0F20原skip/exit0 full，未重复full/build/help/dryrun/旧正式run。包仍base2e2115647940a4025e99f7fcdd112e1fdc9ae416、487/source0a1d29967852b737d3aafa4ea8800d94da3e0747713bc616939e8ea7076052b7，后续wire是外部开发驱动，不冒称旧EXE含新工具。原包保留，同hash七输入复制新`_tmp_gui/r3-entry-wire-20261021/入口编排 空格/便携包 321 FISH`；root/原包/副本七不可变文件前后全hash保持。
真实compiled StartTrial使用支持的--mode demo/--nick，默认从EXE所在目录定位包，从独立空cwd/OS-only PATH/private desktop/fresh synthetic env启动。它自行选随机loopback端口、initialize/open自己的server、启动两个actual client.exe并进入wait_clients。没有外部harness代启动server/client，没有GUI/控制台输入、截图、命令行内存读取或新启动/协议框架。初始化日志/新store存在且编排进入真实server和双client；未单独捕获initializer退出码，不虚构0。
私有outer containment Job覆盖入口和其nested inner Jobs；JobProcessIdList只枚举自身成员，Toolhelp只保留这些成员的父关系，OpenProcess句柄经IsProcessInJob验证。只记录own TCP行，用两个actual client组已建立连接remotePort与自己的server监听交集识别chat、剩余监听识别web，不猜端口/扫网或采集无关端点。HTTP200后复用根现有_wire_probe；Windows接口布局依[Job列表说明](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_process_id_list)与[TCP表说明](https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getextendedtcptable)核对。

## 实际结果与清理时序

一次真实compiled运行，controller exit0：原audit确认actual client uid1/2，wire双peer uid3/4；双chat seq1/2、gomoku9/connect4 7手终局/CREATED复位/round2空盘/离房精确七步，6.17s，两socketclose。入口/两client及server实际live roles在协议后仍活。
10个保留成员句柄：StartTrial2、server2、client4、系统conhost2，均Job成员；八个应用映像严格指新包，conhost为所属辅助进程。目标是父PID为本次直接持有bootloader根的唯一StartTrial worker，注入前再次同Job/alive核，TerminateProcess仅使用该稳定句柄/code125，不按PID kill、不先TermJob/Closeouter。
四个不可覆盖本地checkpoint顺序：pre-injection→injection-return→post-owner-observation→pre-outer-release。注入API成功后，在任何outer强停/关闭前，观察到10→0、全部10保留句柄signaled，worker125、bootloader125，独立sentinel仍活；外部tree fallback=False。再释放outer时active_before0/after0/close成功，sentinel单独Job强制3→0/close；所有额外句柄关闭。因owner进程死亡触发编译入口自己的kill-on-close子Job清理，这一有限结论有实际边界观察；不是entry正常finally或自然GUI退出。session-summary不存在是注入终止预期，不拿缺失当产品缺陷或成功凭证。
严格walk(onerror=raise)直接生成stat/hash清单，不再二次rglob；空cwd硬验、包新增仅唯一新trial_runs/trial UUID树，原七输入保持，捕获3248项只属本次owned树。它是时点记录，不承诺持续不变/全系统IO；不改ACL、系统网络/防火墙/真实资料/硬件。原profile/prefs/密钥/完整inventory及进程/端点原件仅本地，不公开。

## 独立审查、范围与下一项

执行前3 MUST（strict直接清单、cwd/唯一run硬验、操作边界x-checkpoint）均修后独立0 MUST才启动；本次实际原件/最终五docs独立终审0 MUST，主控仅有限AI接受入口编排/协议/owner死亡清理。全部23后验为真，四checkpoint与原audit/hash索引可追溯；controller源码是执行后provenance，不是密码学执行证明。97585已结束，无活动EXE/测试；未发现本范围产品缺陷，未制造代码改动。

| 精确公开路径 | 内容 |
| --- | --- |
| `docs/task-packages/R3-ENTRY-WIRE-01.md` | Frozen finite scope and control boundaries |
| `docs/review-packages/R3-ENTRY-WIRE-01-r1.md` | Actual compiled orchestration/owner-death evidence and review |
| `docs/review-assets/R3-ENTRY-WIRE-01/evidence.json` | Sanitized structured outcomes and local raw evidence hash index |
| `docs/AI_COMMAND_CENTER.md` | Authoritative status and recovery/next priority |
| `docs/任务清单.md` | Generated roadmap projection |

仅五项目文档/脱敏摘要，审新增文件及全部new commit history，无raw/完整inventory/控制器/用户名/私密/密钥/profile/EXE。按本周有界许可，最终独立0 MUST后仅接受compiled启动编排/协议/owner死亡清理；fresh fetch/保护/required checks后正常push/安全FF/核远端完整SHA和CI，无CI不当PASS，不强推/绕保护/删分支/发布。
完整GUI、自然client/red-button/open-server退出、正常完整compiled demo/finally/session-summary、物理LAN/多机、其它DPI/Windows、硬件/STT、无开发目录机器仍未测，R3不升级。下一P1 R3-INVENTORY-STRICT-01 DRAFT：既有local_trial inventory受限rglob会静默漏项的已见证据，单独红测/最小fail-closed改造/回归与审查，直接提高证据可信度，不造新框架或产品功能。本批只提出优先级，不顺手实施。恢复先AI_COMMAND_CENTER/Task/Review/Git/本地baseline/checkpoints/execution与实际进程，勿重复已有full/build/验收。

## 最终独立审查及有限接受

gate_review独立只读核实际原件、四操作边界checkpoint、成员句柄与worker身份、wire与原audit、全hash/strict清单、同源full及公开五路径，最终0 MUST。主控仅AI_ACCEPTED_ENTRY_WIRE_OWNER_DEATH_ONLY；没有本范围产品缺陷，不修改源码或重复full/build。完整GUI/自然退出/正常finally/完整demo/LAN等仍未测；提交后审全部newhistory，再fresh核远端保护与安全普通集成，当前未推送/合并。
