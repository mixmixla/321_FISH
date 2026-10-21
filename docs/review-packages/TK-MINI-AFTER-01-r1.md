# TK-MINI-AFTER-01 r1 — MiniBar 更新任务销毁

2026-10-21：**AI_ACCEPTED_MINI_TIMER_ONLY / FULL_PASSED / READY_FOR_INTEGRATION / R3_GUI_NOT_RUN**。
[Task v1.2](../task-packages/TK-MINI-AFTER-01.md) / [结构化结果与原件hash索引](../review-assets/TK-MINI-AFTER-01/evidence.json)。root实现，gate_review独立只读；普通模型/Standard。本批只一个小缺陷；此检查点尚未push/merge/发布。用户在唯一full期间新增本周有界持续公开/合并授权，仅验收代码、测试、项目文档、脱敏摘要，不含raw/本机用户名/私人数据/密钥，不发布；不复用旧10文件许可。交付权限变化未改源码或重启full；Task v1.2另记环境中断后同run续跑。

## 复现、归属与修复

base/main f057efa1a6d21c23f3fc8b448459eb7ec3389f50/clean，分支fix/mini-timer-lifetime-20261021，代码b4c9de2c7056f77c4aeb8dc1e0fed3625ac83435。client.py仅MiniBar18+/2-：首次更新前初始化唯一job与destroyed标记；真实owner Destroy用add='+'且严格event.widget identity，取走清空ID后通过原owner取消。更新开始清已执行ID，接触Tk和重排前均判未销毁；保留1000ms周期，hide/show不加/删循环，tooltip子Destroy不误取消。
原先widget.destroy删除Python Tcl命令，但解释器after脚本仍存在；同一存活root一秒后实际invalid command。不能靠Python winfo_exists guard解决尚未进入回调就失败的命令查找。没有全局after清扫、共享引用缓存，未改Boss/GameWindow/BoardFocus/quit_app/tkguard/conftest/协议/规则/依赖或旧测试。
正式quit_app已在组件销毁后全局取消解释器任务，不能从本组件诊断推断整个应用自然退出失败或已修好。验证仅真实Tk控件/计时/事件循环、合成core/files/prefs，不是完整GUI/网络验收。

## 原始失败及领域

原件均在项目根`_tmp_gui/test-gate/<run_id>`，项目.venv Python3.14.5调用run.py test-all，逐文件source/profile/private desktop/loopback隔离。

| 步骤 | run_id | 实际结果 |
| --- | --- | --- |
| Mini/Boss归属probe | mini-boss-diagnosis-20261021-163734-09d8744468 | 1P1F：Mini一条_update pending且自然报错；Boss两条_tick/lambda pending，但1700ms窗口内bgerror=[]，未满足预期，原失败保留 |
| 原生产同字节RED | mini-timer-red-20261021-163833-e850928527 | 6F2P/exit1，首次tick前后、自然bgerror、重复销毁、root销毁、更新中重入销毁失败；隐藏/tooltip原已通过 |
| 首修及领域 | mini-timer-domain-20261021-163934-79ce6a7bc8 | 7文件56P0F0S/exit0，新8case全过，未改测试或放宽时序 |

oneoff probe源保存在本地ignored mini-timer目录，已从最终suite移出；原run487输入与后续486区分，probe失败不被green覆盖。领域首次命令误写不存在test_r61_details.py，runner拒绝且未运行测试；查实际test_r61_features.py后执行上述完整领域，不能记为应用测试已通过或抹掉错误入口。
RED/领域均486输入且仅client.py不同；最终测试SHA `edab67973f4ea55797f272ded47e72b4d18fae63aa021a98ea15819f92345c3d`，全量字节相同。8case覆盖自然tick前后、自然1150ms bgerror窗口、另一Mini/sentinel保持、hide/show两轮真实状态更新、tooltip子销毁后真实tick、6轮queue/weakref释放、父root销毁及实际更新中重入销毁。

## 唯一最终全量

初始命令`run.py test-all --label mini-timer-full`：唯一run `mini-timer-full-20261021-164222-11a3ea9ec6`，**209文件、2930P/0F/20原opt-in S，最终exit0**。
执行连接中断时125文件已完成、r33原raw只有部分输出；driver/child均由门禁process_state确认exited，原summary不存在，不记原attempt完成。保存原progress/partialraw/hash后，经独立恢复策略审查使用`run.py test-all --resume <上述原run>`仅续剩余84，不新建full。最终125完成行逐字段/原hash/attempt完全不变；r33 attempt1保留interrupted且无真实pytest完成exit，attempt2才9P完整完成，另外208文件各一次完整attempt。框架补写的中断cleanup字段不是当次真实完整验证；未覆盖或删除原件。
summary.seconds=379.331秒仅表示续跑段；原run起止墙钟992.523秒包含断线/诊断，不能称连续运行耗时。486输入/source `f90cf605a636fe3890b98a5bcf01b02ace50f46f8e0abc0a8a1df5aa43b9bff3`，领域/当前/full snapshot逐hash相同；较此前485仅client+新test，旧208文件逐counts保留，只增8P。209完整raw SHA/exit/cleanup、1份中断partial原件、125行不变/无unexpectedskip及17项后验已核；skip精确r45硬件1+ux_visual_chat_shots18+visual_screenshot1，未启用visual/hardware或改旧断言/timeout。
summary SHA `8dba727ee341219a27f4b52e1839897b0fbe4b671f103a796bcf51f2ed35ea49`；索引保存所有209原raw hash及逐文件计数，没有新增原raw/完整summary/profile/EXE入库。

## 接受边界、当前交付与下一批

代码/领域及最终原full/资料/中断续跑/公开范围独立终审均0 MUST，主控记录AI_ACCEPTED_MINI_TIMER_ONLY；仅接受MiniBar自有更新生命周期。旗舰6P保持，领域raw3处lambda、full原raw3处诊断（此前full5处），不是全部干净销毁；Boss1700ms未捕获报错的负结果保留，不猜所有诊断全部归Boss。全局wheel等旧边界未修。完整native GUI/正常红退出/物理LAN/多机/其它真实DPI/硬件未测；未重建EXE，旧EXE不含本修复，不假放行R3。
下一批P1：Boss独立单进程/单解释器走真实1500ms置顶和3000ms tick时序，核command存在性/归属与bgerror；依赖本批已审源码和原probe，不依赖缺失native GUI。若无真实缺陷只记录，不为日志凑改动。P2：受支持native GUI工具恢复后，按有限R3清单构建新源码EXE并完成合成双客户端完整大厅/对局/聊天/自然退出；组件/协议不替代。物理LAN/其它DPI仍需对应真实环境，不能借机改网络安全设置或伪造通过。
按价值分批形成检查点，不以周额度耗尽为目标，不声称可读取剩余额度；此Task到本地交付终点停止实现，由后续调度选择下一批。

## 准确拟公开清单（本批尚未推送）

共9文件，仅以下路径和类别；使用用户新的本周有界授权，原10文件具体许可不复用。没有新原始日志/完整summary、绝对机器路径索引、本机用户名、运行profile、凭据、EXE或用户真实数据。全部新增文件及所有新提交历史均须审计；此检查点尚未push/merge尝试，也没有重试任何已拒操作。通过独立终审与公开边界检查后正常push/安全集成，fresh fetch/保护/required checks照常核，遇安全拒绝即停，不换路线，不强推/发布。

| 完整仓库相对路径 | 内容类别 |
| --- | --- |
| `client.py` | Product: MiniBar owner update timer only, 18 additions/2 removals |
| `tests/test_mini_timer_lifetime.py` | Eight real Tk regression cases with synthetic core |
| `docs/task-packages/TK-MINI-AFTER-01.md` | Frozen scope and observed diagnostic boundaries |
| `docs/review-packages/TK-MINI-AFTER-01-r1.md` | Reproduction, outcomes, review and acceptance limits |
| `docs/review-assets/TK-MINI-AFTER-01/evidence.json` | Structured result/hash index only; no raw logs or machine paths |
| `docs/AI_COMMAND_CENTER.md` | Current local checkpoint and next priorities |
| `docs/任务清单.md` | Generated command-center projection |
| `PROJECT_MEMORY.md` | Stable MiniBar destruction ownership fact |
| `.agents/skills/fish-assistant-dev/references/development.md` | Stable component validation guidance |

本地完整leaf/dirty与活动状态见Git和中心；恢复先中心→Task/本Review→Git/原fullsummary→实际进程。full已完成不重复运行，源码变化再核影响。

## 最终独立接受与公开审计

gate_review从原件核最终full、125完成行不变、r33两个attempt的边界、完整raw/退出/清理/skip及486当前/快照/领域绑定，独立终审0 MUST；原probe负结果/错误入口均保留，不改历史。主控只接受MiniBar组件定时生命周期，不升级Boss、GUI、自然应用退出、EXE或R3。
准确9文件及全部新提交历史/新文件blob审计：仅代码/测试/项目文档/结构化脱敏结果与SHA索引，没有新增raw日志、原始完整summary、机器用户名、私人数据、密钥、profile或二进制；索引无绝对机器路径，投影/链接/diffcheck通过。用户本周有界持续公开/集成授权适用；正常push/安全合并前fresh fetch核变化/保护/checks，拒绝立即停，无旁路/强推/发布。完整候选leaf见Git，源码486仍冻结，不为资料改动重跑full。
