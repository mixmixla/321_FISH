# REL-01 v1.1 — 本地构建与合成试用证据

**最终结论（2026-10-03）：AI_ACCEPTED，限本轮本地技术范围。** resource_review独立终审无must，主控据最终1daea66/full1669-0-2与对应分层/产物证据裁决；非Pro/用户验收、整个R1/RETIRE通过或发布。以下阶段未完成/失败记录按历史保留。


Task：[REL-01](../task-packages/REL-01.md)。当前REVIEWING；最终全量、实际EXE构建与smoke尚未完成。
授权来自[本轮自治](../decisions/LOCAL-AUTONOMY-20261003.md)，仅本地提交/试用候选，不是发布。

## 实现与审查

gate_impl独立worktree从6543e00实施薄进程配置，root负责主树整合与补正；resource_review未参与实现。
新增MOYU_BIND_HOST/DISCOVERY/TRAY/GLOBAL_HOTKEYS/HARDWARE默认兼容原行为，禁用时覆盖服务端/客户端
发现、托盘早期启动、全局热键注册、MF设备枚举和音频设备入口；loopback不做外部路由探测。
不改变身份、协议、资源保留和实际用户profile模型。

local_trial.py在独立源码副本调用现有build.py；实际EXE smoke使用private Windows desktop，
新合成profile、随机loopback端口、关闭发现/托盘/热键/设备/HTTPS（仅本机HTTP验证），不注入pytest guard。
独立初审三must为：须验证实际client.exe登录而非Python探针；记录profile写入及source前后清单；
只有双EXE非空且哈希齐全才构建通过。整改后原REL12项通过、独立窄审无must，允许整合。
worktree提交8b1d479，主树整合6e23e72；具体全量/产物另记，不能据源码专项宣布EXE可用。

## 构建前数据边界补正

root在启动实际构建前发现旧_safe_copy_tree遍历整个source，可能带入ignored .env、IDE设置、boot.log；
旧_tree_fingerprint也会读取整个树。仅用新合成敏感占位文件复现，未读取真实运行文件。
同测试负例`rel-source-boundary-negative-20261003-130216-09c9d32d10`：1failed/12deselected、exit1。

修复：源码复制和source指纹只复用test_gate.source_manifest白名单；复制前检查reparse边界与已记录hash。
构建使用新build-profile/CREATE_NO_WINDOW，HOMEPATH保留盘符后的反斜杠。
_owned_inventory只处理本次创建的profile；报告明确source指纹不是全系统IO轨迹，不推定OS全局无读写。
联合专项`integrated-prebuild-20261003-130541-32a3e6a8fa`中的REL13项全部通过；
整体因另一个wire测试失败exit1，该失败与修订见[GUI Review](GAME-UI-01-r1.md)，没有隐藏为全绿。

关键补正候选SHA256：local_trial.py `2a2a00df163611f10d5cdb2c581b8ded112ba2741ec2408c695eeab9e67f90a1`；
tests/test_rel01_local_trial.py `70769508e9c4b42040d59a120fea035ee6a953dd16dc017af915a7229dad1ee7`。

## 用户手动试用入口

trial_start.ps1在包根目录寻找dist/server.exe、dist/client.exe。每次创建新profile并预置两个合成昵称；
server隐藏、两个客户端正常窗口；关闭客户端或Ctrl+C清理本次持有的Process对象。
自动工作只执行AST/DryRun/隔离函数测试，没有启动此可见入口。
初版四缺陷（空Arguments绑定、alpha登记时机、WaitForExit污染bool返回、StrictMode集合计数）修正后：
PS7.6.5 AST0error、DryRun通过、missing-owned.exe在成功参数绑定后正常失败、清理函数单Boolean返回、
0/1/2集合与alpha登记顺序验证通过。树清理失败不能回退父进程后谎报成功。
候选hash `39309244fe2e47d3a618b9fa10b0d6d70636979b6dbebc428f0a001779ec621e`，独立窄审待补。

## 可复现入口与限制

项目Python3.14.5/.venv，PowerShell7，PyInstaller6.22.3；不安装新运行环境。

```powershell
& ./.venv/Scripts/python.exe test_gate.py tests/test_rel01_local_trial.py --label rel-domain
& ./.venv/Scripts/python.exe local_trial.py build
& ./.venv/Scripts/python.exe local_trial.py run --source-dir <上一步输出的source_copy>
pwsh -NoProfile -File ./trial_start.ps1 -DryRun
```

实际运行输出独立run目录；summary保留命令/解释器、退出码、进程映像/desktop/session、登录audit来源、
HTTP与TCP结果、双EXE哈希、profile相对路径清单和清理结果。原始日志可ignored，必要检查与复现代码随仓库保存。
这不验证非开发Windows、物理LAN/防火墙/HTTPS、多机文件传输、真实麦克风/摄像头/托盘/热键或真实用户迁移。
当前打包机无vosk及内置模型，候选语音转写不可用；保留警告，不下载模型或自动增加依赖。

## 第一版实际EXE证据与后续必要补正

1caf9ab构建`build-20261003-051538-c0ad0d3262`：exit0、126.312秒。
server.exe 25,235,673 bytes，SHA256 `2c63c3993dcf18249bec82b4f79f2fff1c84f8e871f9e8cb9ec0a3a032386958`；
client.exe 26,579,248 bytes，SHA256 `1a22a6db87fb305d5d7da7ba2ae1f6e59d9ca1f8853c42d389227f13d13117ba`。
build.log明确警告vosk与模型缺失，未因build退出0声称具备转写。
主树330白名单输入逐字节比对构建副本，只有build.py正常重新生成的client.spec/server.spec不同；
其余输入无差异，记录在该build/source-identity.json。运行source指纹326项，不包含非Git副本枚举不到的
.python-version/app.ico/tests/_run_all.py/tests/_smoke_excel_skin.py；不能混同主树330输入ID。

`run-20261003-051910-298ae0973e`：单client实际EXE smoke exit0；TCP可达、HTTP200、实际client.exe
合成audit login、映像/desktop/source前后及退出清理均通过。原始证据位于`_tmp_gui/local-trial-runs/`。
随后确认USERNAME单例锁边界（client用USERNAME或user作锁键）：原Pythonharness继承宿主用户名，
原PS launcher未设用户名，两客户端可能碰锁。只用合成env测试复现：
`trial-mutex-negative-20261003-132133-b0d93cc1ad` 2failed/13deselected、exit1。

修复仅设置每owned profile的规范绝对路径SHA256前20为子进程USERNAME=trial_…，不改父/系统环境、
生产mutex或账号。Pythonharness扩为两个client，分别核对真实TCP登录、同时存活/正确映像并全部清理，
立即登记启动的进程以覆盖后续异常；CLI精简输出而summary仍保存完整inventory。独立resource_review认可设计与实现，无must。

新harness搭配原1caf9ab产物的`run-20261003-052335-680cdc31bf`真实exit0：两个合成昵称/uid1、2
各自登录，两client和server映像正确且同时存活，三者清理成功，source前后一致。
证据在`_tmp_gui/trial-recovery-fix/_tmp_gui/local-trial-runs/`；它证明双实例隔离，不证明后续Boss恢复代码已打包。
最终修正版仍须重新全量、构建和双EXE smoke，旧产物不作为最终包交付。

补正最终专项`trial-rel-kick-final-20261003-133300-2e600262f7`：REL15+kicked6=21passed、exit0，
source `784f1d8b2a3cda2c0af41d0294898ed375bcb09ba40331cc63b113e2b1c52065`；
与同source真Tk5passed一起独立复审无must，主树整合1daea66。旧kick fake补齐真实初始化的_disco字段，
并参数化None/存在两态，原after取消→destroy→core.stop顺序没有削弱。
主树330原字节输入source `f224f73b20e72ee1494f7fff096d7751c20fb6757d8c5b41434964431b4867f6`，
最终重新构建/全量/EXE证据正在生成，未提前AI_ACCEPTED。

## 最终候选构建

主树1daea66，Python3.14.5/PyInstaller6.22.3，`python local_trial.py build`：
`build-20261003-053443-b7259b1384`，真实exit0、115.158秒，双EXE均存在且非空。

| 文件 | bytes | SHA256 |
| --- | --- | --- |
| server.exe | 25235416 | cae2833e8a7e870e6f305c0f0ad2f7e3ea251ab438c1f3435fa7edbe7d6a16ff |
| client.exe | 26579400 | 410ee1e86905ee3ba889b96878475523114c9d9e6387ddfd3d926f11eabe6414 |

同目录source-identity.json比对主树330输入，除了build.py重新生成的两个spec外全部原字节一致，
没有其它差异；固定source f224f73b…与最终门禁身份相同。未复制运行目录/真实用户配置；
vosk/模型警告仍保持。非开发机器环境不由构建exit0推定可部署。

主树关键原字节SHA256（Git树与独立补正提交相同，checkout换行已另绑定）：

| 输入 | SHA256 |
| --- | --- |
| client.py | 51a2a27897713b01ba40263d49f05bce181e03e4e11c4d9c253aa5788a942a87 |
| client_gameui.py | c58f4d52d472a06432784940855aea0b1e8feded0dee828743f986ac957e8163 |
| tests/test_flagship_board.py | 6a29bbf5428fa825c6506eca33332b9b685d80c067019aa5ef03dc969f04db2a |
| tests/test_flagship_gui.py | bb535a523211162bcb6573ff6d2d1062ad0ab019e46c6b4e57546ea4ee07c0e0 |
| tests/test_flagship_game_wire.py | 4d8931c4e357d627e134ec10bb9bed5474b25a927b40327380577e14146819c9 |
| local_trial.py | ad7d96e9549dcf4c19f9c41bba79dd7508614c4356bb8491375f9d71e4ccf84e |
| trial_start.ps1 | 2806d78f11aabce55771b8f280224b2e2159e1b38a40b97984892069bc1e8a7c |
| test_gate.py | 0912b13350bee8ec1a7c010d1b22a39456e803e0f1d572361d685a75a7962a10 |
| test_sandbox.py | 348dfbee8df95883a8aebf2e809ed7f18ae305bbf39387e19da5598f839cbd34 |

## 最终双EXE实际运行

`python local_trial.py run --source-dir <上述最终build/source>`，run
`run-20261003-053741-15087532a7`，session98588已结束，真实exit0。
TCP13423/Web13424，显式127.0.0.1；HTTP200；实际client.exe合成昵称REL_trial_client/REL_trial_beta
分别以uid1/2经TCP登录，审计来源peer127.0.0.1。server/client/client_beta运行中映像均匹配最终EXE，
两client同时存活；三个owned进程树停止后全部确认exited，cleanup_ok=true。
全部位于本次创建的private desktop，未向用户鼠标键盘发送输入、未启用设备/托盘/全局热键。

三个fresh profile before均5项，after依次1079/1075/1075（包含onefile临时解包运行库），
只保存相对路径/大小/sha256清单；运行source326项前后相同：
`24e3e7c60227eb47fb119989cc6cdb83b388037b082ee716d0f983760c720ca8`。
此运行子集与主树330输入ID范围不同，主树到构建的完整映射见source-identity.json；不冒称全系统IO追踪。

实际退出证据是harness停止owned进程树并确认结束；没有自动操作EXE内退出按钮或Boss/game界面。
纯Tk退出/窗口恢复和实际EXE启动分别列证据，不能混合声称完整GUI端到端或非开发机稳定性。

## 最终全量与实际包

最终同源127文件1669passed/0failed/2原opt-in，真实exit0，827.261秒；身份、命令和原失败见[VB Review](VB-01-r1.md)。
一次性本地打包检查逐一确认：source ID不变、测试文件集合完整、每文件exit/status/skip合规、最终build与smoke均成功，
smoke flags精确loopback/全禁用、两个昵称/uid/via/peer、EXE hash与input映射一致才写包。

实际包`_tmp_gui/321_FISH-local-trial-20261003-1daea66.zip`，51,326,407 bytes，SHA256
`74b543e8cc391e99671a326330155301f1b8fd105aa02252d6cc93f221968c89`。
同名目录为可展开试用目录。ZIP CRC自检通过，精确8个文件：dist内双EXE、trial_start.ps1、README.md、
游戏完成度地图.md、LICENSE、VERIFICATION.json、SHA256SUMS.txt。
没有打包source副本、profile、audit/history/prefs/crash、_MEI、TLS私钥或其它运行数据。
README实际命令为`pwsh -NoProfile -File .\trial_start.ps1`；打包只收尾文档和已验证产物，未自动运行用户可见入口。
包内VERIFICATION保留全部330相对输入路径/hash与运行摘要，实际repo跟踪的harness/tests可复现验证，
不把ignored大日志或一次性打包脚本当作唯一交接来源。
