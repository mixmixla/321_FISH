# R3-PACKAGE-WIRE-01 r1 — 七文件包搬移预检

2026-10-21 **AI_ACCEPTED_RELOCATED_PREFLIGHT_ONLY / NOT_MERGED / NOT_R3_ACCEPTED**。
[Task v1](../task-packages/R3-PACKAGE-WIRE-01.md) / [脱敏结果/hash索引](../review-assets/R3-PACKAGE-WIRE-01/evidence.json)。base/main `cd4818313ee58c76565d068d9523eb3f10d86ce8`，feature/r3-package-wire-20261021；root唯一执行/写入，gate_review独立只读，普通模型/Standard。本周有界公开及正常集成许可适用，不发布。

## 真实版本与最小范围

本批无产品/工具/测试/依赖/构建源码改动，仅验收资料。原包`_tmp_gui/r3-rebuild-20261021/bundle-main2e21156-pending-gui`是base2e2115647940a4025e99f7fcdd112e1fdc9ae416的三EXE、487/source0a1d29967852b737d3aafa4ea8800d94da3e0747713bc616939e8ea7076052b7；逐size/SHA及SHA256SUMS覆盖其它六文件已核。后续正式wire只是外部开发harness变化，不冒称旧EXE含新工具。当前根488/source `dcf9dfb850acd8530274165b6984655ef457ccc077d438978ffe1cdacbd18757`与2958P0F20原skip/exit0唯一full逐hash同一；旧487相比只local_trial改变/新增wire test，业务代码不变，不重建或重复full。
精确七文件复制到新的`_tmp_gui/r3-package-wire-20261021/搬移验收 空格/便携包 321 FISH`，原包保留。只复制LICENSE/README/VERIFICATION/SHA256SUMS/StartTrial.exe及dist两EXE，副本无源码/.git/.venv。复制前/复制后/执行后原包与副本全七size/SHA保持，包内无新增runtime文件。父链直到盘根拒绝junction/reparse、resolve containment、mkdir/copy/launch前后核，目标拒已存在，不删除或覆盖用户文件。

## 失败原件与实际执行

不是“全批一次成功”：首控制器在os_env读取普通dict的SystemRoot键时KeyError，真实键为SYSTEMROOT，launch_owned尚未调用、jobs=[]，正式预检/CLI均NOT_RUN。原execution.json SHA `6fb0307d82a81876af5df9cb17c244cdb017afa260a3982c72a9f666f01549fa`及首控制器/恢复记录保留，未覆盖。仅修本地控制器case-insensitive查键，复用已核副本/空cwd/sentinel，另建拒复用的attempt-2全新profiles/logs；恢复控制器独立0 MUST后执行。未改产品或为此重复任何源码全量。
第二控制器的一次实际正式CLI `run-20261021-112319-f614b290c5`：从独立无源码空工作目录、OS-only PATH启动根最新local_trial.py run，source-dir指搬移包，没有mock/exe override。实际server/client命令及映像指副本，子cwd沿原harness为副本；同机中文与空格路径通过。旧build仍存在，未追踪全系统IO，不能因此推导所有绝对路径依赖已排除或非开发机通过。
actual CLI/process0，initialize0、HTTP200，原audit确认实际双client uid1/2；wire双peer uid3/4，chat seq1/2，两棋gomoku9/connect4 7手终局/CREATED复位/round2空盘/离房精确7步，6.206s、两socketclose。三actual EXE after_wait仍运行/映像符合。四inner Job before2/2/3/0→after全0/close，外formal driver Job根0但active_before1→after0/close；两compiled CLI根0且各before1→after0/close。总七Job清理成功；根退出码0不等于进程树自然退出，强停不记应用自然退出。
搬移StartTrial.exe从同一独立cwd运行help及`--mode demo --dry-run`，均root0，未传bundle-dir；dry-plan的bundle/client/server严格指EXE所在搬移包，新run/profiles只计划在其trial_runs且未创建，自动端口/fresh-only/loopback正确。实际环境与formal summary另核安全flags，plan本身无flags。只接受compiled CLI路径解析，未运行完整compiled demo。

## 数据与证据边界

正式三profile运行前文件均0，运行后各1020文件（包含onefile解包runtime，不能当聊天文件数），控制器在归属Job清完后的一次核对与原捕获相等，root位于本次run；不承诺持续稳定；三个driver/CLI profile前后文件均0。包仍七文件，独立启动cwd仍空，owned sentinel不变；发现/托盘/热键/硬件/HTTPS关闭，只loopback，不导入真实数据或修改网络/防火墙。保留新合成资料作本地证据，不声称全系统零写或自然清空磁盘资料。
正式无源码包的manifest前后实际只有SHA256SUMS.txt一项/source `d5d14b5fdabd336a1f0fc164fe0b8de7382471c588da44a6d95b216761905d70`，不是七文件或487/488源码身份。独立七文件全hash及根488/source另分别绑定，所有20项后验通过；formal打印JSON与原summary除刻意省略profiles外一致，原audit和全部log/source/controller SHA列在脱敏索引。所有raw/完整summary/控制器/profile/EXE仅本地ignored目录；控制器源码是执行后provenance，不是密码学执行证明。
执行前路径MUST已补整条父链/resolve/重核；首次零进程环境KeyError恢复后独立快审0 MUST。本次实际原件与最终资料独立终审待完成，不提前AI接受；session72333/20920均结束，无活动EXE/测试。本批纯验收，不适用新增产品红绿，不重复已验full/构建。

## 准确公开范围与下一项

| 仓库相对路径 | 内容 |
| --- | --- |
| `docs/task-packages/R3-PACKAGE-WIRE-01.md` | Frozen finite scope and controller recovery checkpoint |
| `docs/review-packages/R3-PACKAGE-WIRE-01-r1.md` | Actual relocated package evidence, review and limits |
| `docs/review-assets/R3-PACKAGE-WIRE-01/evidence.json` | Sanitized structured results and raw evidence hash index |
| `docs/AI_COMMAND_CENTER.md` | Authoritative recovery/next candidate |
| `docs/任务清单.md` | Generated roadmap projection |

仅五份项目文档/脱敏摘要；新增文件与全部新commit history都审，无raw/完整summary/用户名/私密/密钥/profile/EXE。独立0 MUST后有限接受搬移正式启动/协议/CLI解析，按周授权fresh fetch/保护/required checks后正常push/安全FF、核远端完整SHA；无CI不等于CI PASS，不强推/绕保护/删分支/发布。
完整native GUI、自然client/open-server退出、完整compiled demo、物理LAN/多机器、其它DPI/Windows、硬件/STT、原build/project缺失的非开发机及全系统IO未测，R3不升级。下一P1候选R3-ENTRY-WIRE-01 DRAFT：真正执行compiled StartTrial demo编排的有限启动/现有wire/owner Job清理，补当前只直接harness启动server/client的入口覆盖缺口；可自主进行且不依赖GUI，但先单独冻结/独立审查，不在本批顺手执行。恢复先AI_COMMAND_CENTER/Task/Review/Git/本地baseline、两attempt原件与实际进程，不重复已完成验收/全量。

## Profile枚举视图复核（原件保留）

独立审查默认受限读取最初只枚举到server5/client4/beta4文件，不能据此推断Temp删除。strict os.walk(onerror=raise)在三个_MEI目录均WinError5；按原路径直接读取已知runtime文件仍同SHA。正常验收工具上下文的完整只读strict遍历均1020，所有路径/size/SHA与原capture相等。独立审查也在相同权限对照复核此结论，无ACL修改、无EXE/测试重跑。
原summary及两控制器原件不改；先前本地post观察为三者0delta，却有通用disappearance归因文字，该归因不受数据支持，补充profile-visibility-followup明确纠正并索引原SHA。只接受捕获时、控制器当时一次相等及后续完整复核时相等，不承诺时间上的不变或全系统IO。受限rglob枚举会静默跳过目录，不得当完整性证据；可另批考虑strict诊断，不扩本批产品。资料MUST修正后待独立关闭。

## 独立最终技术接受

gate_review独立核原包/副本全七hash、首控制器零进程失败及恢复分类、正式actual EXE/原audit/两个compiled CLI、全部七Job/隔离inventory/根488、五docs公开范围，最终0 MUST。主控仅AI_ACCEPTED_RELOCATED_PREFLIGHT_ONLY；前段待终审是历史检查点，现闭合。完整GUI/自然退出/LAN/完整compiled demo等不接受。纯资料不重跑full/build，正常集成尚待fresh远端/保护及全部newhistory核查；不把接受当合并或发布。
