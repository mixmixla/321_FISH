# Project Memory — 321_FISH 摸鱼助手

## Snapshot

- 用途：Windows 局域网聊天、文件/媒体、网页端与桌游；Tkinter 桌面客户端。
- 栈与入口：Python 3.14.5，`dev.ps1` / `run.py`；Hub 加密 TCP，网页 HTTP(S)/SSE。
- 最近源码核对：2026-10-03；有限RESOURCE数值资格补正、Windows旗舰与本地试用配置已整合，
  版本及实际验收见本轮Review/指挥中心；完整RETIRE其它资源/UI及R1仍未关闭。
  Web legacy metadata不含owner/target，完成附件GET沿有效认证+已知fid；新增owner/op字段是归属/结果证据，不是私聊/群ACL。
  当前任务、版本和测试结果统一见 [AI_COMMAND_CENTER](docs/AI_COMMAND_CENTER.md)。
- 当前机器路径 `D:\Project\321_FISH`，迁移后以任务工作区为准。
- 个人开发技能：`$fish-assistant-dev`；源码事实优先于技能旧索引。

## Portable trial boundary

- `friend_trial_start` 是独立便携入口：每次新建分开的合成资料，默认回环，LAN仅接明确RFC1918数字IPv4；不导入已有账号、偏好或历史。
- `friend_trial_process` 仅把本次新建的suspended子进程赋给unnamed Job后恢复，非继承handle和kill-on-close限制所属子孙；无existing PID接管。
- 本核心版本包含凭据回执、退役状态及显式Store恢复边界，但未接入独立实验local_owner/auth/session/work链。CP4历史registry WinError5/errno13根因未定，本入口清理证据不替代其修复。
- 便携构建和私有桌面登录不证明完整EXE对局、自然窗口退出、物理LAN或非开发机可用；确切版本/结果只放Task/Review和指挥中心。

## Architecture

- `client.py:ChatWindow` 管 Tk UI；`client_core.py:ClientCore` 管网络、状态、API 与
  本地历史。后台 events 队列由 `_poll/_handle` 在主线程处理。
- `protocol.MsgType/FrameReader` 管 JSON header + binary body 帧；`crypto` 管
  X25519/HKDF/AES-GCM 加密通道；`crypto_e2ee` 管消息层端到端密聊与 ratchet。
- `server.Hub.dispatch/_on_*` 是权威业务入口；`ChatBus` 管频道历史与全局 seq。
  `_uid_clients` 是同 uid 的全部端，`sessions` 是代表端，Web token 绑定原已认证会话。
- `web.PAGE/_Handler/_sse_loop` 是内嵌网页与 HTTP/SSE；REST 复用 Hub 权限/业务，
  没有独立 npm 前端。`discovery` 管 UDP 发现，`tls_cert` 管自签 HTTPS。
- `ServerStore` 保存启用持久化时的最新全量快照；audit 只记元数据。云历史在
  客户端加密，服务器存不透明 blob；本地 JSONL/prefs 仍含实际用户内容。
- `games_pkg` 注册 47 个当前游戏类，`RoomManager` 管房间，`BaseGame` 的
  snapshot/private/act/tick/ended 管公开、私有与规则；桌面 painter/点击/按钮
  分别在 `client_gameui`、`client._GAME_ACTIONS`，注册不等于 UI 完整可玩。
- 两旗舰桌面输入以最新Core的connected/player/turn/winner和room-round上下文复查，
  五子棋交点、四子棋列输入与hover共用几何；胜线以最终board/last_move计算。GameWindow/BoardFocus
  各自持有有限after；mini/boss保存窗口对象与可见性，手动隐藏/离房可取消恢复资格。
  14项已确认无完整桌面操作的游戏被标识并阻止误入；精确分类与证据见[游戏完成度地图](docs/游戏完成度地图.md)。
- 公共房间只允许CREATED开始；leave/最后UID端断线承接既有player_left，观战退出不触发玩家规则。
  finish/reset与action/tick公开snapshot以room/gs/round身份校验，ENDED保留公开结果但不再分发private，
  复位保留房间成员供房主再开。人数不足且无native结果时公共层中止，不新增winner/奖励。
- 游戏状态与匹配离房ACK按UID发给全部存活端；客户端清离房room/public/private/events并忽略迟到帧，
  显式join/spectate发请求前解除旧房间fence，失败恢复。桌面/Web终局保留公开棋盘并阻止继续动作。
- `FileManager` 管 P2P 优先与服务器回退，`filexfer` 是分块/PartFile 数据层；
  群文件库另走 Hub 权限路径。通话/语音房使用加密 UDP；位置、VMA1、WAV
  有各自 TTL/缓存与 UI 流程。
- `theme/ExcelChrome/ExcelSheet` 是桌面可编辑工作表；`_sync_excel_layout` 复用旧
  聊天控件，`_send_excel_text` 仍进入统一聊天发送，工作表值在 `Prefs.excel_cells`。
- 本地历史/媒体/身份按 `_nick_history_dir` 隔离，首个新账号可能认领旧顶层资源；
  显式 history_dir 需调用者隔离。下载目录仍为全局 `_log_dir()/downloads`。
- 当前本地历史键只含安全昵称，不含服务器/UID/身份代际；首次旧资源迁移仅覆盖顶层JSONL、voice和stickers_custom，
  不含vmemo或旧E2EE身份。Prefs账号档案只切换pinned/muted/archived/drafts/stars/unread_marks六项；excel_cells仍设备共享。
- 云历史是独立`cloud/{uid}.bin`，不在state.json；客户端解密restore直接merge，当前不校验包内UID/昵称/服务器/身份代际。
  服务器快照包含group_files/moments等部分索引，独立媒体本体与Web fid元数据不等于快照事务。
- `_attach/unregister`按字段存在性保留known的pwd/sign/avatar/invisible/status/remarks，空值/False同样保留；
  正常最后端更新last_online，在线与否仍取存活会话，退群/转群主等既有语义不变。
- JSON恢复仅对冻结的groups身份结构、reads内部UID键做严格规范化；非法或冲突组拒该组，reads拒该会话映射，
  不把昵称/频道/资源字符串递归int化；burn及其它原有持久化格式保持。
- KICK在锁内撤销目标UID当时全部现有Session/token，锁外承接原注销/通知/关闭；允许之后正常认证，新端不被旧清理误伤。
  t0前已接受操作不追溯取消；Core/Tk/Web收到失效后回手动登录，普通暂断重连与单端logout隔离保持。
- 当前CORE使用独立retired UID→nick/retired_at/operation_id JSON字段，保留昵称映射并阻止旧身份重登/UID复用；
  t0清活跃known/本人draft/sched/blocks/reads、撤全旧端/token，CHAT/burn、due、PROFILE等核心C与t0在Hub→bus纯内存边界内排序。
- 持久确认保留ServerStore.save bool兼容外形，实际writer在cutoff前后固定Hub→bus的state/op捕获，严格一次UTF8 bytes/SHA、阶段typed结果及统一ack，运行态请求代次保留后到dirty；
  运行态receipt/unknown及known前后序对账不增持久revision/hash-proof/marker；confirmed来源written/reconciled_current_json/restored_valid_json分开，旧合法JSON恢复无历史SHA。证据与版本见[STORE Review](docs/review-packages/CC-02B-STORE-r1.md)。
- 有限CLOUD/Web文件资源采用运行态op/不可变attempt、stage前quota、资源锁→短Hub发布许可C→锁外独立IO→匹配attempt完成；t0不等资源锁。latest许可防旧failed重试，current已证index决定GET及superseded/withdrawn；state.json receipt不替代文件结果。
- 新Webmanifest版本/任一新专属字段必须严格校验body/hash/length/owner/op，body先manifest后；上传/CHAT/GET共用实际资格，读响应为不可变bytes。完成/legacy附件仍有效认证+fid共享，不新增ACL/扫描迁移；部分body孤儿不等完整publication。
- bot回复/提醒/Agent结果最终Hub→bus复查owner/私聊target退役；提醒enqueue/take/cancel同短锁，仍内存态；外部Agent工具不承诺取消。preview先释放cache锁后最终上下文/URL/deleted/fence匹配，edit/del仅窄bus桥接，不加全handler退休gate/generation，U→V→U最终匹配可接受。

## Conventions and constraints

- 所有 Windows shell 用 PowerShell 7。以 `.python-version` 和 requirements 为准，
  推荐 `.\dev.ps1` 避开系统旧 Python；先 server 后 client。
- 运行依赖 cryptography/Pillow/pystray；测试与打包 pytest/PyInstaller。
  vosk/模型、翻译、Lottie 为可选扩展，不默认视为全部已具备。
- 分支 `feature/` / `fix/`，提交 `类型: 一句话`；main 禁止直接 push，走 PR。
  协议/架构不兼容变化同步 PROTOCOL_VERSION；发布版本在 tag 时确定。
- Tk 仅主线程操作，保留 tkguard；注入 Core.on_event 或录制回调仍可能在后台。
- 保护 prefs/history/audit/server_state/web_tls/downloads，不入提交/技能/截图。
  当前仓库已公开；管理员密码只来自部署配置，不复制实际口令值。
- 门禁：`.\dev.ps1`；专项 `.\dev.ps1 test -k 关键词`；可加
  `-o faulthandler_timeout=60`。默认合成媒体，真机/截图需显式选项。
  按 COLLABORATION 的日常/领域/最终全量分层；VB-01已提供默认/test-all隔离逐文件候选入口，
  精确验收见指挥中心及VB Review。显式test仍为旧单进程调试，未启用源码/profile/网络/desktop隔离。
- 一对一文件权限取认证 `Session.uid` 与 `TransferMeta.sender_uid/receiver_uid`；
  `file_id` 与请求头身份字段不能授权。REJECT/VERIFY 只允许接收者，CANCEL 允许双方，
  身份校验与删除记录在同一锁内完成，拒绝请求不改状态/不通知合法双方；
  DIRECT_OK 只允许发送者，继续沿用同 UID 多端语义。
- Web显式退出走POST `/api/logout`，沿Cookie优先的原认证Session解析；只撤销当前端token，
  Origin存在时验证同源，成功/失效清Cookie，正常SSE断开/刷新仍只detach并可恢复。
  本端退出清SSE/重连和登录/游戏视图，旧ES对象与旧回调不能恢复已退出认证。
- `run.py` 用独立项目临时目录和 pytest 子进程，父进程清理/透传退出码；
  conftest 通过 sessionfinish 保留真实退出状态，再避开 Tcl 关闭阶段。
- `test_gate.py/test_sandbox.py`将源码快照、每文件副本/profile/日志/真实exit、候选fingerprint、
  private desktop和loopback映射证据绑定；同候选resume保留失败，进程退出不确定/路径reparse拒绝，
  清理失败停止后续文件。它是受控测试防护，不是对恶意代码的OS安全沙箱，不能证明产品默认绑定loopback。
- 门禁拒绝非原visual/hardware opt-in的意外skip；GUI文件使用sys捕获，parent仍保存原生stdout/stderr，
  非GUI保留fd捕获。source manifest包括未提交Python输入、排除docs/runtime，driver另有独立hash。
- `local_trial.py`复用批准source manifest构建独立副本并核对双EXE，使用新profile/private desktop验证
  实际client.exe登录及清理；`trial_start.ps1`供用户手动同机双客户端试用。进程级
  MOYU_BIND_HOST/DISCOVERY/TRAY/GLOBAL_HOTKEYS/HARDWARE可禁用相关行为，默认仍兼容原应用。
  试用脚本设loopback/禁设备和发现；source指纹不是全系统IO审计，EXE启动不等于真机/LAN/GUI全对局验收。

## Decisions

- 2026-10-03 — 用户将本轮本地试用目标内的任务冻结/技术决策/独立验收授权主控，Pro不再默认审批；
  真实数据、远端写入/发布、资金/系统级权限不继承 — [自治决定](docs/decisions/LOCAL-AUTONOMY-20261003.md)。
- 2026-09-30 — 统一运行环境与依赖清单，保留系统旧 Python — 避免 PATH 冲突 —
  证据：`.python-version`, `requirements*.txt`, `dev.ps1`, `docs/开发环境.md`。
- 2026-09-30 — 本地可编辑工作表与服务器聊天记录分开；Enter 保存、Ctrl+Enter
  发送；旧聊天视图与草稿保留 — 证据：`widgets/excel_chrome.py`, `widgets/excel_sheet.py`,
  `ChatWindow._send_excel_text` 与 `tests/test_excel*`。
- 2026-09-30 — 音频 callback 只入队，普通线程执行 wave API；保留 native buffer
  生命周期 — 证据：`voice_api.py`, `tests/test_audit_audio_callbacks.py`。
- 2026-09-30 — 独立登录窗不 transient 到 withdrawn 宿主，映射后才 grab/聚焦；
  原生置顶操作 GA_ROOT 顶层 HWND，重试保留密码框焦点；退出清理 grab/定时任务。
  不修改其它弹窗的 `_hide_owner` — 证据：`widgets/login_box.py`, `tests/test_login_*.py`。
- 2026-10-01 — 架构技术决定选M1退役旧UID/保留昵称，不开放同名重注册；首批仅PROFILE→RESTORE→KICK。
  RETIRE含可靠持久提交、CREDENTIAL及LOCAL/CLOUD仍需独立冻结/授权；技术选择不等于已实现 —
  证据：[决定v1](docs/decisions/CC-02_架构审查决定_v1.md)、[CC-02A Task](docs/task-packages/CC-02A.md)。
- 2026-10-02 — Pro将下一实施拆为退役CORE与后续STORE/RESOURCE/存储加固，用户直接批准CORE；
  仅后端/最少store/tests，不改UI/资源/整体loader；只保护当前管理员/默认有效保留名/实际BOT UID，不永久保留bot昵称或猜历史角色 —
  证据：[最新决定](docs/decisions/CC02-RETIRE_核心实施审查决定_v1.md)、[CORE Task](docs/task-packages/CC-02A-RETIRE-CORE.md)。

## Current work

- 仅引用 [指挥中心](docs/AI_COMMAND_CENTER.md) 的当前任务与下一动作；本文件不维护执行状态。
- 冻结需求/版本与测试证据分别保存在 `docs/task-packages/`、`docs/review-packages/`。
  连续生命周期范围见 [BATCH-R1](docs/task-packages/BATCH-R1.md)与各子Task/Review，状态只由指挥中心维护。
  一对一文件边界见 [FILE-AUTH-01 Task](docs/task-packages/FILE-AUTH-01.md) /
  [Review](docs/review-packages/FILE-AUTH-01-r1.md)；CC-01A 原交接摘要见
  [Task](docs/task-packages/CC-01A.md)，历史缺口/补正分别见
  [r1](docs/review-packages/CC-01A-r1.md)、[r2](docs/review-packages/CC-01A-r2.md)。早期 Excel/登录验证摘要迁入
  [资料批次 Review](docs/review-packages/COORD-01-r1.md)，均不代表当前工作树门禁结果。

## Established delivery facts

- Excel/环境/审核改动经 PR #1，前台唤起改动经 PR #2，隐藏宿主登录窗修复经 PR #3
  合入 main；登录窗合并记录为 `fbdd915`。这些是既有交付索引，不推导新任务通过。
- 当前管理员工作树使用部署环境变量、未配置 fail closed、保留管理员昵称；
  Web token 绑定认证会话并逐会话撤销。行为/未提交版本边界见 CC-01A Task/Review。
- 发布 EXE、全部游戏 UI 可达性、完整可选扩展、真实音频长期稳定性仍需后续专门证据。
- REL-01以白名单源码副本实际构建双EXE，private desktop下两个合成client.exe同时登录/存活，
  harness停止owned进程树并确认退出；这不是EXE界面操作、物理LAN或真实数据验收。
  版本/边界见[REL Review](docs/review-packages/REL-01-r1.md)，源代码单测不替代实际产物证据。

## Risks and follow-ups

- R26 测试读群摘要须等 `group_list`，不能仅等 `group_state`；干净 `fbdd915` 与 CC 候选
  在相同测试侧事件屏障下均复现原等待竞态，测试侧同步修复见 [CC-01A r2](docs/review-packages/CC-01A-r2.md)。
- R43A 淡入时序仍待核验：首次窗口映射后可能读不到 90ms 中间帧；历史观察见 CC-01A r1，
  本次没有扩展为 R43A 的干净基线对照或修复，不由 R26 证据推导其归因。
- Web关闭页面/SSE断开仍仅detach，显式logout通过新POST入口注销当前Session；
  未显式退出的闲置会话沿用原清理，当前端token不能借另一在线端续权。
- UID资源清理与下线通知必须在真正最后端且提交时仍离线的边界执行；重登取消旧待发送通知，
  新端已建立的资源不能被旧注销清理，空群回收要复查是否已经有新成员。
- 一对一 FILE_ACCEPT 合法接收确认后发送者离线的可用性/状态阶段竞态待单独核验，
  不把参与者鉴权修复扩大为整套传输状态机重写。
- CORE已用retired阻止旧UID/昵称复活，逻辑清本人草稿/定时/活跃私有记录；有限RESOURCE只补CLOUD/Web upload-file/bot/提醒/Agent/preview，不据此宣称其它媒体/全部写入面或UI闭合。
  文件C是最后发布许可，C<t0的在途IO可完成；不保证t0后零物理写/跨文件JSON事务或物理擦除。有效JSON身份边界和源码证据见CORE/RESOURCE Review。
- 删号清消息只移除目标作者UID的记录，对方私聊消息仍留；正常最后端注销还会退群/转群主/空群解散，
  资料保持与离线退群是两项边界，不由注销修复推导删号完整。
- CORE的sched最终发布复查退役并取消本人队列/已摘due；正常离线定时仍按原群/屏蔽规则，不将KICK改成封禁。
- `_restore`的groups/reads字符串UID缺口已按白名单补正并有真实JSON后权限/禁言/已读证据；
  未因此宣称全部快照格式、物理文件/索引或旧服务回滚可靠性已验证。
- STORE只有严格候选预校验及真实bytes写入/flush/fsync/close/replace成功才确认；post-write ACK/回执异常先unknown再对账，不假称旧file。实际writer/fresh capture与请求代次保护旧snapshot和后到dirty。
  普通凭据CAS仍未实现；首次退役提交从未成功时不保证旧有效JSON重启后阻断，禁止用内存成功或未经审查降级/旧备份回滚替代持久确认。
- snapshot核心一致捕获/deep remarks及burn.pend→既有恢复UID列表的必要适配已纳CORE；不等于全面JSON格式重写。
  ServerStore.load仍将坏JSON/读取失败返回{}，整体loader/初始化marker/丢失状态恢复与durable intent明确延期CC-05存储加固。
- 有限资源结果的confirmed是目标结果证据；opaque CLOUD对账同bytes只证明当前目标内容，可以confirmed+uncertain+reconciled_current_resource，不伪造某次replace唯一发生；确定preReplace失败不会因本来相同而改成功。资源IO/send失败/历史成功/当前可见分开。
  资源op/unknown/fence是当前进程运行态；CLOUD已有身份恢复后过滤retired，重启非retired文件扫描仅访问事实，旧op/unknown屏障丢失，新显式PUT可覆盖。首无op响应全丢/淘汰/重启不自动猜latest、去重或重放；持久intent/整体loader仍CC-05。
  CORE sched due与bot内存提醒不合并；Agent仅禁止迟到本仓库结果，不推导外部工具取消；Web共享访问与owner操作查询是两套权限，admin只有限结果不blob/不复开retiredcloud。实际候选证据见[RESOURCE Review](docs/review-packages/CC-02C-RESOURCE-r1.md)。
  管理员UID不是固定号，实际bot保护按BOT_BY_UID；普通分配器已跳过retired/known/实际botUID，同名bot登录字符串/历史管理员角色不能猜测迁移。
- 现有ClientCore.send_admin_user_del在发送前乐观pop known/roster；RETIRE管理结果需要区分已提交、运行阻断、失败/未知与真正JSON确认。
  UI仍未改，不能从服务端四态回执推导当前客户端已支持失败/重试或停止deleted自动重连；完整设计与延期边界见[RETIRE材料](docs/CC02-RETIRE_Pro审查材料.md)及CORE Task。
- `optional.has_lottie` 探测 rlottie、renderer 导入 rlottie_python；涉及该扩展先核对。
- VmemoRecorder 后台 on_done/on_error 当前直接进入 GUI 预览/Toast 接线；相关
  开发需主线程移交，尚未真机复现，本次技能整理不修改业务代码。
- 部分游戏 painter 与 _CLICKS/_GAME_ACTIONS 路由未齐；新增/启用时验证动作可达，
  不把纯规则测试等同完整玩法交付。
- 昵称安全目录替换/截断可能碰撞，下载目录全局；迁移/多账号任务需针对验证。
- `.spec` 含旧机器绝对 icon 路径且缺 build.py 的 Vosk 模型逻辑；打包入口不等价。
- docs/优化清单.md 属于另一个 Ollama IDE 项目；旧 UI 文档可能只记录早期状态。
- 链接预览目前拒绝 3xx，部分跳转网页没有卡片；正文与链接正常可用。

- STORE fingerprint与真正写入使用同一严格编码bytes SHA，拒绝键冲突/非有限值/非法字符串，不使用default=str/repr。
  sync/worker/flush及活动Hub兼容save/save_bytes都进同一writer；pending/inflight纯结果不误等unknown，unknown全入口先对账，known前后序/实际操作清理绑定，错expected-op纯内存拒绝无IO。
  正式冻结与版本化实施证据见[STORE Task](docs/task-packages/CC-02B-STORE.md)/[Review](docs/review-packages/CC-02B-STORE-r1.md)，历史[Pro材料](docs/CC-02B-STORE_Pro审查材料.md)/[草案](docs/task-packages/CC-02B-STORE-DRAFT.md)仍保留，状态只看指挥中心。

## Evidence index

- [RESOURCE Pro材料](docs/CC-02C-RESOURCE_Pro审查材料.md) / [有限草案](docs/task-packages/CC-02C-RESOURCE-DRAFT.md) — HEAD0bf1d26资源静态事实、独立文件与state.json确认边界、C/t0候选、待决定接口/legacy策略及全部未执行矩阵；不是已实现保证。
- [RESOURCE新决定](docs/decisions/CC-02C-RESOURCE_设计审查决定_v1.md) / [正式Task](docs/task-packages/CC-02C-RESOURCE.md) / [实施Review](docs/review-packages/CC-02C-RESOURCE-r1.md) — 选定R1/Q1–Q4/M01–M04、有限候选/原红/中间失败/实际IO与网络JSON、阶段及最终独立验收；当前执行状态只看中心。

- `COLLABORATION.md`, `README.md`, `docs/开发环境.md` — 当前约定与启动方式。
- `AGENTS.md`, `docs/AI_COMMAND_CENTER.md`, `docs/task-packages/`, `docs/review-packages/` —
  启动/恢复、唯一状态队列、冻结需求与版本化证据。
- `protocol.py`, `crypto.py`, `crypto_e2ee.py` — 帧、握手、消息 E2EE。
- `client.py`, `client_core.py`, `prefs.py` — 主线程 UI、网络事件、本地状态。
- `server.py`, `web.py`, `server_store.py`, `audit.py` — Hub、网页、权威快照与审计。
- `games_pkg/base.py`, `games_pkg/rooms.py`, `games_pkg/__init__.py`, `client_gameui.py` — 游戏各层。
- `file_client.py`, `voice_call.py`, `voice_room.py`, `voice_api.py`, `vmemo_api.py` — 文件/媒体链。
- `Hub._on_file_reject/_on_file_verify/_on_file_cancel`, `tests/test_audit_file_auth.py` —
  一对一传输身份检查顺序、无状态副作用、请求头防冒充、合法多端及取消通知方向。
- `web._Handler._logout`, `tests/test_web_logout.py`, `tests/test_session_cleanup.py`,
  `tests/test_game_lifecycle.py` — 退出会话隔离、UID清理边界与公共房间状态回归，完整证据见R1 Review。
- `tests/test_server_game_lifecycle.py`, `tests/test_game_client_lifecycle.py` — 公共终局/旧轮身份/同UID退出ACK与客户端清理重入。
- [CC-02架构材料](docs/CC-02_用户会话与数据边界审查.md) — 版本化身份/持久数据事实、静态风险、候选与待决问题；
  原v1为d07b295的历史观察；后续决定与切分见[修订草案](docs/task-packages/CC-02-IMPLEMENTATION-DRAFT.md)，执行状态仍只在指挥中心。
- [CC-02A Review](docs/review-packages/CC-02A-r1.md) — 当前首批候选的原红/修绿、独立审查、真实Tk/Web和最终同版门禁证据。
- `widgets/excel_chrome.py`, `widgets/excel_sheet.py` — 可编辑工作簿与发送接入。
- `build.py`, `client.spec`, `server.spec`, `optional.py` — 打包入口和能力降级。
- `docs/项目审核_2026-09-30.md`, `tests/test_audit_*.py`, `tests/test_excel*` — 审核/工作表证据。
