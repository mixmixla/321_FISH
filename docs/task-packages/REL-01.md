# REL-01 v1.1 — Windows 合成本地试用候选

授权：[本轮自治](../decisions/LOCAL-AUTONOMY-20261003.md)。主控批准有限本地实现/构建，
resource_review已独立追踪启动链并提出薄配置方案；不等发布/部署批准。

目标：用实际构建的server.exe/client.exe完成合成profile、loopback、private desktop启动/认证验证，
交付EXE哈希、构建/运行证据、使用说明、完成度地图及已知/未验证事项。普通运行默认保持原行为。

基线6543e00，独立worktree实施；主树当前全量期间不得写其源码。范围：config.py、server.py、web.py、
client.py的启动与自动发现/托盘/热键点、widgets/login_box.py、voice_call.py/voice_api.py/video_api.py的
硬件探测/入口守卫、必要测试、新local_trial.py构建/启动harness及文档。不改数据格式/保留规则/身份迁移。

设计（独立事实依据已核对）：
- Cfg增加进程级MOYU_BIND_HOST（默认0.0.0.0，明确IPv4字面地址、非法/空值拒绝）、MOYU_DISCOVERY、
  MOYU_TRAY、MOYU_GLOBAL_HOTKEYS、MOYU_HARDWARE（后四默认启用，0禁用）；不改系统环境/防火墙。
- TCP/Web实际使用同一bind地址，loopback不执行8.8.8.8路由探测。discovery禁用时服务器不广播、
  登录框/ChatWindow不启动发现也不自动替换显式host；端口沿现有环境配置。
- 热键禁用时可保留空HotkeyManager对象，不能start/RegisterHotKey；tray禁用涵盖早期、主客户端和服务端。
  硬件禁用时不做MF摄像头预热/枚举，也不打开采集/播放设备；通常操作默认不变。
- 不新增profile产品模型：EXE沿已有expanduser路径，harness给每个进程独立新建USERPROFILE/
  HOMEDRIVE/HOMEPATH/APPDATA/LOCALAPPDATA/TEMP/TMP；只允许OS启动环境白名单，清除部署凭据/外部工具环境。
- 自动smoke只使用owned private desktop与合成账号，不发送用户鼠标/键盘、不触剪贴板或设备。
  合成prefs可关闭声音，正常用户profile不读取。外部harness复用launch_process，不向EXE注入test_sandbox/guard。
- 构建在新源码副本执行build.py，实际PyInstaller双产物；旧绝对路径spec不作为入口。vosk/模型缺失如实
  列为不可用，不下载/购买/增加付费API。打包只选EXE/启动脚本/说明/哈希，不带任何运行库/私钥/账号数据。

验证：配置默认兼容与禁用分支、真实socket绑定/无发现与热键/设备启动、领域回归；实际构建退出/警告/哈希；
真实EXE loopback TCP握手、HTTP(S)页面、client登录（仅合成audit元数据），进程归属与退出、写入profile清单。
认证/安全机制不关闭以掩盖错误；loopback HTTP测试明确不等HTTPS/真实LAN验收。源码合并后最终全量必须完成，
独立代码/产物/证据审核满足才AI_ACCEPTED本地候选。

不做：远端写入/PR/merge/tag/Release/部署、真用户迁移、真实账号/设备/物理LAN或非开发机器测试。
后者列发布前事项，不借本机EXE通过推定完成。本地提交可回退；只清理本任务明确创建的进程/目录。

v1.1内部补正（2026-10-03）：范围加入用户手动执行的trial_start.ps1，使用全新synthetic profiles与
loopback启动隐藏server及两个正常client，关闭硬件/发现/托盘/全局热键；主控不自动运行可见入口。
启动脚本必须正确处理空参数数组、第二客户端失败、0/1/2存活数和owned进程树清理失败。
构建复制和source前后核对复用门禁源码白名单，不能遍历读取真实运行目录、ignored配置或凭据；
复制前后核对选定源码hash。构建过程本身也使用独立synthetic profile。
产物附现有许可证副本（不改许可）、本地使用说明、已知限制与hash；不声称全系统IO审计或真实用户迁移已验证。

同日必要启动隔离补正：现有client单例锁以USERNAME为键；仅给独立profile而沿用同用户名仍会碰锁，
可能唤起另一个客户端。Python harness/PowerShell launcher须给每个owned profile的规范绝对路径计算
短SHA256，设为该子进程的synthetic USERNAME；不改父/系统环境、生产单例逻辑、账号或Prefs模型。
实际EXE smoke须证明两个不同合成昵称都经TCP登录并同时存活，及全部owned进程清理。
