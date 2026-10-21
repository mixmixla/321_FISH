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
