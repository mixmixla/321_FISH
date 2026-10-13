# EXE-LOCAL-01 v1.1 — 当版三EXE构建、入口与本机安全退出

2026-10-13。父线程用户明确授权SYNC闭合后优先三EXE及本机安全验证。root冻结有限
Task；只有指挥中心将SYNC同版full/独立终核闭合并登记READY后实施。当前只准备，不
提前构建/启动应用，不继承旧2247/三EXE为当版证据。

## 来源与环境

基于SYNC最终源码commit与source_content_id（当前merge6c8bdf7/source13514b5d…，
若SYNC有整改，以其最终受测HEAD/410输入清单为准）。先读AGENTS/COLLAB、build.py、
local_trial.py与docs/朋友试用候选_2026-10-06.md构建说明。原项目.venv显式Python3.14.5，
root与worktree的.python-version均3.14.5；已装PyInstaller6.22.3，记录实际环境，不
切其它项目venv/升级/下载模型。用户15:00北京停止，14:30不新开大任务。

## 有限构建与所有权

三产物为server.exe、client.exe、StartTrial.exe（friend_trial_start.py），没有
friend_trial.spec。root唯一构建/运行/治理作者，先确认无旧构建/测试和原窗口作者。
用source_manifest白名单复制最终候选到本Task独立ignored目录，执行规范
local_trial.py build（内部build.py生成双EXE），再同一副本用已记载的OS-only环境
函数、PyInstaller --onefile --console构建StartTrial。不得在原工作树运行build.py覆盖
app.ico或spec；不使用上游含作者绝对路径的client.spec直接打包。

记录最终HEAD、完整白名单/源码hash、解释器/工具版本、实际命令/exit/原日志hash、
生成spec/app.ico差异、三EXE大小/SHA、收集的_art_boardgame/ui_design/入口Job依赖。
新位图与26PNG按实际收集/内嵌证据核实，不只凭源测试通过。二进制仅本地，不push
EXE/ZIP/运行资料到repo，不正式发布；公开Task/Review只保存可公开合成证据与hash。

本机缺Vosk包与models/vosk/am/final.mdl；规范build.py按已有可选合同警告后继续，
不得因此改可选合同或安装模型。转写依赖/内置模型不随包，明确未验/不声称可用。

## 本机入口、退出与边界

- 新合成profile/随机loopback端口/private desktop、严格OS-only环境，关闭发现、托盘、
  全局热键、设备和HTTPS；不读真实prefs/history/部署凭据，不借实验CP4模块。
- 复用既有owned Job/精确PID所有权；验证新Store、双客户端TCP合成登录、HTTP、
  路径隔离、中文空格包目录/OS-only PATH、StartTrial dry-run与正常菜单0退出。
- server initialize-new/inspect为实际CLI自然返回，可单独记录exit；服务态Ctrl+C
  只有先证明自有专用console/不广播用户console才测，否则列人工待验。
- client窗口X按现行产品合同只是hide_to_mini，真实退出为quit_app；旧terminate_tree/
  Job关闭只证明所属进程清理。只有在精确owned private desktop窗口安全激活既有
  退出命令、强停前观察client自然exit0/注销/零残留才记自然退出。禁global SendInput/
  Escape/屏幕抓取、禁注入自动退出钩子冒充真实流程；无法安全识别则明确BLOCKED。
- StartTrial等待两client exit0可自然返回，但finally仍强停server，不能据此证明
  server服务态自然退出。正常/强停/异常码分别记录，Tcl或fatal原日志保留。
- 所有检查仅本机合成/loopback，不称干净非开发Windows、物理LAN、完整EXE游戏
  对局/邀请/结束/再开或最终DPI/视觉验收。危险--run-visual截图模式继续禁用。

## 验收与交付

必要构建/入口选测和独立代码/原证据审查；运行前后源保护/实际进程与清理核对，
每个自然阶段给可恢复最终检查点，不一次半小时静默。若包失败，保留原失败/命令/
日志/身份，按具体范围另冻必要spec/产品整改后重建，不跳过常规测试藏失败。
没有产品/测试/依赖改变且源码与SYNC一致时引用其full；若改变则新适用领域/full。
AI_ACCEPTED仅实际完成部分，不当用户/Pro/发布验收；真实外机/用户交互列待办。
允许任务分支文档/必要有限代码commit/push，PR403不重试，不共享main merge/发布。

## v1.1 证据出版与实际绑定

绑定交付9803303与受测源码6c8bdf7/source13514b5d…/410输入。2026-10-13用户继续已READY范围，
只root构建/运行，安全观察失误自主修复；产品/测试/依赖/三EXE均未改。原运行4P2F与
相关2case复核1P1F保留，最终仅compiled case复核1P0F；不得改写成一次整体全绿。
修正仅零错误空desktop枚举、由current Job loopback表推断端口、精确归属自有Windows
conhost；新run/profile/中文包，不重做已通过case。自有连接表含client行，只有端口
推断另筛server loopback行。自然exit必须在Job关闭前证实，编译demo强停124仅清理。
只对本Task logs/*.txt增-text/-whitespace以原字节出版；不豁免产品/测试白空间检查。
