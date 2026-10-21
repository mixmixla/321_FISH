# R3-LOCAL-01 r1 — v2 最新源码产物刷新

2026-10-21 **AI_ACCEPTED_BUILD_PREFLIGHT_WIRE_ONLY / READY_FOR_INTEGRATION / NOT_R3_ACCEPTED**。
[当前Task v2](../task-packages/R3-LOCAL-01.md) / [本次脱敏结构化摘要与原件hash索引](../review-assets/R3-LOCAL-01/rebuild-20261021.json)。root唯一执行/资料写入，gate_review独立只读，普通模型/Standard。以下旧v1历史原样保留，旧原件不作为本次新EXE证明。

## 本次源码与三产物

base/main `2e2115647940a4025e99f7fcdd112e1fdc9ae416`，fresh fetch核同SHA/clean，新分支feature/r3-rebuild-20261021。复用Boss唯一full `boss-timer-full-20261021-172649-12db730620`：210文件2939P0F20原skip/exit0，487输入 `0a1d29967852b737d3aafa4ea8800d94da3e0747713bc616939e8ea7076052b7`；本批无应用/测试/构建/harness/依赖代码变更，不重复full。
`local_trial.py build --source-dir . --output-root _tmp_gui/r3-rebuild-20261021`实际exit0/50.604s，run `build-20261021-095153-7b5c83262b`；同白名单副本按朋友候选现有PyInstaller样例构建StartTrial，实际exit0/9.076s。副本487原输入全部存在，485原字节不变，只client.spec/server.spec正常再生成且各SHA留索引，app.ico不变。32桌游输入、两EXE必需PYZ模块核在；client PYZ含Boss新helper/GameWindow调度/Mini Destroy符号，不能据此声称完整界面通过。
runtime非Git fallback只重新发现483输入 `dc151b377bed85914754d0eb36d4e6eae38eb589257adcd564dff50498eea133`，未重新发现.python-version/app.ico/tests/_run_all.py/tests/_smoke_excel_skin.py四项，但四文件仍存在并已在完整487映射逐hash核；完整绑定和483运行前后不变证据分别记录，不混用。

| 产物 | bytes | SHA256 |
| --- | ---: | --- |
| server.exe | 26084183 | `cbd87c141c1dd50f1e8df8ed87856ec743f94f1e69e466751a66a6e4efce1cb4` |
| client.exe | 27344653 | `ee2208a24b9e69deff0307b8fe0c88618ec8b896d1ed6b1ef55a2412a3e9d0ab` |
| StartTrial.exe | 9738961 | `aaa37fe82b003da011046e6402f69a9c91b06c5f6323d156822ec94e0d169bff` |

已有Python3.14.5/PyInstaller6.22.3，无软件/依赖/模型安装。Vosk和模型均缺，语音转写未验证，构建成功不代表完整功能可用。

## 正式双EXE与独立协议

正式无adapter命令 `local_trial.py run --source-dir <本次build/source> --run-root _tmp_gui/r3-rebuild-20261021/preflight`，实际run `run-20261021-095310-b2a8476d44`/exit0；直接默认suspended→owned unnamed Job→resume。fresh三profile、private desktop/loopback、禁发现/托盘/热键/设备/HTTPS：显式initialize自然root0、HTTP200、两个实际client.exe登录audit uid1/2、短时双方和server存活且映像匹配。4Job cleanup全部active_after0/close_ok，483源前后相同/profile scoped；client/open server是Job强停，不算自然退出或GUI登录。
独立协议run `wire-20261021-100233-7ea434c6c8`/exit0，实际本次server.exe显式initialize/open/HTTP200/映像与构建SHA前后匹配；两任务级客户端真实加密TCP握手/welcome UID，唯一合成聊天双方echo同seq且递增。五子棋9手/四子棋7手双方每步严格room/round/stone count/turn/winner，真实ENDED→CREATED且state=None→round+1空棋盘→双方离房确认/列表缺房。9步均通过，两socket/reader已关闭，2Job全归零close。没有源码Hub替代EXE，也没有操控实际client.exe界面；仅有限协议验收。
StartTrial实际help/demo dry-run run `cli-20261021-100234-3018361445`/exit0，两根退出码0，2Job清理后0/close成功；清理前仍各1个active条目，不能写成整树自然退出。没有运行完整compiled demo。共8个本批owned Job结果原样记录，强停与自然root退出分开。
任务级控制器仅本地；执行前独立审查发现并关闭两MUST：entry缺产物时summary与实际exit5一致；socket.close异常仍finally join reader并报告失败。构建/CLI/协议各执行一次成功，无失败重试或旧full重跑。原始构建/运行/控制器日志与完整summary/profile只在ignored根，公开仅结构化结果与hash，不复制原件。

## 本地待验包、限制与下一候选

本地 `_tmp_gui/r3-rebuild-20261021/bundle-main2e21156-pending-gui` 精确7文件：StartTrial.exe、dist/server.exe、dist/client.exe、LICENSE、README.md、VERIFICATION.json、SHA256SUMS.txt。三EXE同原构建hash；无源码/profile/store/audit/密钥/日志，未压缩/上传/发布。SHA256SUMS覆盖另六文件，自身hash由公开结构化索引保存。包只是搬移同hash产物，未运行搬移后完整demo。
当前ALL_TOOLS再次核无node_repl/cua/sky/native desktop工具，不绕行输入/截图。完整大厅/邀请接受/可视对局/红色自然退出、物理LAN/多机/其它Windows与真实DPI、硬件、STT未测。已有组件/协议不冒充完整GUI或R3/M1通过，不要求用户现在人工补验才能继续独立工作。
下一候选 **R3-WIRE-SMOKE-01 DRAFT**：正式local_trial.run仍只有启动/登录/HTTP探针，将本批已证实可行的真实EXE聊天/两棋生命周期探针纳入正式预检，补错误传播、错序/旧轮次拒绝和全部资源清理回归。它不依赖人工GUI、不增加产品功能；需独立Task冻结后才实施，本批不改源。

## 公开与恢复

本周有界授权只公开5路径：现Task、现Review、现AI_COMMAND_CENTER/任务清单、rebuild-20261021.json。全部新文件及新commit history审计，排除raw/完整summary/控制器源码/profile/EXE/本机用户名/私密数据/密钥；旧v1原件不重写或再上传。gate_review最终独立证据/资料审查0 MUST，主控仅记AI_ACCEPTED_BUILD_PREFLIGHT_WIRE_ONLY；5路径新增文件/添加行与全新history公开审计通过，尚未推送或合并。审查通过后正常push/安全FF，fresh fetch/保护/required checks照常核，安全拒绝即停、不强推/绕过/删分支/发布；无可见CI不当CI通过。
当前所有构建/预检/CLI/协议均结束，无活动测试，不重启已完成操作。恢复：AI_COMMAND_CENTER当前v2→Task/本Review→Git→本地baseline/各summary/实际进程。精确本地路径、原件hash和本次产物见结构化摘要；以下为v1历史。

---

# R3-LOCAL-01 r1 — 有限构建与真实双 EXE 启动预检

2026-10-21：**AI_ACCEPTED_BUILD_PREFLIGHT_ONLY / BUILD_PASSED / DUAL_EXE_PREFLIGHT_PASSED / GUI_TOOL_BLOCKED / NOT_R3_ACCEPTED**。
[Task v1](../task-packages/R3-LOCAL-01.md)。本批无应用/测试/构建/harness源码变更；只增加任务级复现控制器及治理证据。不是完整R3、R1/M1、用户验收或发布。

## 集成与输入

用户授权质量达标可合并主分支并继续有限R3。fetch核main仍84444b5，候选ab6cb77为其后继、六提交链完整；仓库main API显示无保护/required checks、rulesets空。
先按仓库PR约定请求draft PR，自动审批拒绝（认为未授权公开PR且建议普通FF），未创建PR；依用户本轮明确“主分支未变化且候选一致可正常快进并推送”条件，普通FF main→ab6cb77f3b806ad16f717e08d4bdda6b9a5c625e，ls-remote已核。原fix/room-icon-lifetime-20261021保留、不强推、不发布。
分支feature/r3-local-acceptance-20261021。该提交当前0 Actions runs、0 status contexts、0 check runs；没有可见CI不是CI通过。

checkout main曾因core.autocrlf把5个新改文件LF转CRLF，造成raw ID 1f0729…；逐个证明与HEAD blob/原accepted快照仅EOL差异后只恢复这5文件原raw。
[输入绑定](../review-assets/R3-LOCAL-01/input-identity.json)保留5组原/后SHA、483全部输入。source回到原full标识 `2dc0c20008aa8288b8746eb2f65a497fe1ee1910da022ab02a16a67dc039e588`，与前阶段206文件2910P/0F/20原opt-in S/exit0完全同源；无源码内容diff，不重复全量。

## 构建与产物

Python3.14.5 / PyInstaller6.22.3，已有.venv，无安装系统软件/新依赖。一次 `python local_trial.py build --source-dir . --output-root _tmp_gui/r3-local-20261021`：exit0、48.837秒。
原目录 `_tmp_gui/r3-local-20261021/build-20261021-053415-73699e80d8`；白名单source副本483输入逐字节映射，仅client.spec/server.spec因绝对构建路径正常生成，app.ico不变。32个boardgames输入在白名单；实际server/client PYZ中registry/shell/azul/desktop/web/_art/geom均存在。
同副本依朋友候选既有样例构建StartTrial，exit0。原日志/摘要保留在[证据目录](../review-assets/R3-LOCAL-01/)。

| 产物 | bytes | SHA256 |
| --- | ---: | --- |
| server.exe | 26083980 | f47f843a0975e10816d228442d9ae2ac864f880b03b0c5b5158f18fbae591335 |
| client.exe | 27342294 | c65c4a776015bffcdd804849773c57a0dcbfcfca0a8709cc3b79d08f309808ab |
| StartTrial.exe | 9739166 | 0953a1323ba42c4cc31d83a367ec3116654661d0f32ade35510be52adbcbdc18 |

build.log明确缺Vosk与am/final.mdl，未安装/下载模型；不宣称转写可用。PYZ存在只证明收集，不证明完整美术/所有游戏已运行。

## 实际双 EXE 预检与清理

独立gate_review预审指出旧local_trial默认DesktopProcess按数值PID taskkill（含已结束initializer），本轮禁止原样运行。
[reproduce.py](../review-assets/R3-LOCAL-01/reproduce.py)仅任务局部绑定 `local_trial.launch_process = recorded_launch`，实际调用现有friend_trial_process.launch_owned：先suspended、赋unnamed Job再resume，kill-on-close；产品/harness未改。
初审两个MUST（launch后查询异常泄漏、CLI强停异常跳过close/失败摘要）已在执行前修正，经独立复审全部关闭。

一次preflight run `run-20261021-053743-a3a19424c2`，真实exit0，private desktop、fresh三profile、TCP6753/Web6754均127.0.0.1，发现/托盘/热键/设备/HTTPS关闭，无pytest guard。
server.exe显式initialize-new自然exit0后open；HTTP200；两个实际client.exe --nick分别经TCP登录uid1/2（REL_trial_client/REL_trial_beta，peer127.0.0.1），双方及server短时同时存活、映像匹配本次产物。
4个Job清理后active_count全0、close_ok全true；initialize清理前active0，其余由owned Job强停，不触及无关PID。它是启动预检，**不是GUI登录交互或自然退出**。
runtime479个可发现源输入前后同 `9d8d9625ad67db943be4a54659fad8ec24b4fc969e426d4c42ba771b50c52c00`；此副本子集不混同原483完整输入，构建生成两spec已另绑定。三合成profile before均5项，after1081/1075/1075（含onefile运行库）；只读本次profile的crash.log均boot行，无traceback。
[预检摘录](../review-assets/R3-LOCAL-01/preflight-evidence.json)保留实际探针/进程/清理和原summary SHA，省略合成profile逐文件大清单；原件只在ignored run目录，避免重复巨量资料。

StartTrial.exe实际--help及--mode demo --dry-run均exit0，2个Job清理后active0/close成功；plan为fresh loopback、无网络/防火墙/真实资料变动。它没有启动compiled demo，不证明入口完整使用或自然退出。

## 本地待验目录与阻塞

本地 `_tmp_gui/r3-local-20261021/bundle-ab6cb77-pending-gui` 精确7文件：根StartTrial.exe、dist/server.exe、dist/client.exe、LICENSE、README.md、VERIFICATION.json、SHA256SUMS.txt。
3个EXE与原产物同hash，只有白名单文件，无profile/store/audit/密钥/源码副本。README提供同机模式、完整一局/再开/聊天/两client红色退出自然码0的人工步骤；入口返回及server owned Job强停另记，不能证明server自然退出，后者仍未验。目录未实际运行完整demo，未ZIP/上传/发布。

Computer Use SKILL及guidance/confirmations/api已读；规定“Use node_repl JavaScript for all Computer Use actions.”，但本次工具清单没有node_repl，cua另明确Native computer APIs disabled。未绕行自造UI自动化；完整大厅/邀请接受落子结束再开/聊天/红色按钮自然退出均 **BLOCKED / NOT_RUN**，需支持的真实Windows交互工具或人工续验。
物理LAN/多机/其它Windows/其它真实DPI/硬件/完整转写未运行，未改系统网络、防火墙或安全设置，未读取真实用户资料。未发现本轮预检中的可复现产品缺陷，故不新增修复或扩大范围。

## 独立审查与恢复

gate_review只读核Task、483输入、EOL证据、构建副本/PYZ/三产物、控制器异常与Job边界；执行前MUST全部关闭。运行原件/公开摘录/PYZ/全部Job/7文件目录/退出边界及最终资料独立终审0 MUST；有限AI接受只覆盖构建、实际启动预检、入口CLI与交接，不是完整R3或自然退出接受。可仅提交并普通推送资料分支，main仍ab6cb77时按本轮授权普通FF纳入记录；不删除分支、不发布，最终资料leaf与远端SHA以Git为准。
恢复：指挥中心本Task首段→Task/本Review→source Git与进程→上述ignored summary。构建/预检均结束，不重复运行已通过全量；下一阶段仅解除GUI工具缺口后完成既定人工清单，按现有证据判断小修，未验不记PASS。
