# 321_FISH 项目与数据流地图

## 来源与身份

2026-09-30 对本地源码的提炼。原始仓库 `mixmixla/321_FISH`，当前本地通常在
`D:\Project\321_FISH`。识别入口为 `run.py`、`COLLABORATION.md`、`client_core.py`
和 `games_pkg/`。本快照包含审核修复与可编辑工作表改动，后续以当前源码和
`PROJECT_MEMORY.md` 更新事实，不把本页当成远端发布清单。

## 核心链路

```text
桌面 ChatWindow
  → ClientCore（网络线程/事件队列/本地历史）
  → CryptoChannel → protocol 帧
  → TCP _handle_tcp → Hub.dispatch → _on_* → ChatBus/RoomManager/状态
  → Session.send → ClientCore.events → ChatWindow._poll/_handle

浏览器 HTTP(S)
  → web._Handler 鉴权与 REST 组装 → 同一 Hub.dispatch/状态
  → Web Session 连接级队列 → _sse_loop → EventSource
```

`client.py`、`server.py`、`web.py` 是大模块，不是多个互不相关应用。
网页 HTML/CSS/JavaScript 内嵌在 `web.PAGE`；没有单独 npm 前端工程。

## 模块分工与变更路由

| 功能域 | 主要源码与锚点 | 联动与验证 |
| --- | --- | --- |
| 启动/环境 | `run.main`, `dev.ps1`, `launcher.launch`, `client.main`, `server.main` | 源码启动、登录/切账号与真实 Tk；读取当前 manifests |
| 桌面事件/发送 | `ChatWindow._poll/_handle/_send/_switch_view`, `ClientCore` | 业务发送/接收与 UI 两侧联动，保持频道和状态；`test_client_core.py` |
| 协议/加密通道 | `MsgType`, `encode_frame`, `FrameReader`, `CryptoChannel` | 半包/粘包/上限、方向与重放；`test_protocol.py/test_crypto.py` |
| Hub/历史/路由 | `Hub.dispatch/_on_*`, `ChatBus.publish/find/discard`, `_route` | 校验→修改权威状态→广播；`test_server.py` 及功能专项 |
| 多端与账号 | `auth`, `_attach`, `unregister`, `login_web`, `session_by_token` | TCP/Web 同 uid 全部在线端、token/密码；`test_multisession.py/test_r47.py` |
| 网页/安全/TLS | `_Handler.do_GET/do_POST/_session`, `_events/_sse_loop`, `tls_cert.ensure_cert` | Cookie、REST/SSE、TLS、成员权限；`test_p0_web_security.py` |
| 持久化/审计 | `Hub._snapshot_state/_restore/_persist`, `ServerStore`, `AuditLog` | 权威快照与审计不同；重启/原子替换/元数据验证 |
| 发现/托盘/隐藏 | `discovery`, `hotkey`, `boss.BossWindow`, `widgets.tray/server_tray` | 局域网目标、后台回调进 UI、可选依赖降级 |
| 主题/工作表 | `theme`, `ExcelChrome`, `ExcelSheet`, `_sync_excel_layout/_send_excel_text` | token、旧视图回退、单元格本地保存和发送；详见不变量 |
| 客户端本地状态 | `prefs.Prefs`, `ClientCore.history/history_tail`, `cloud_history` | 账号隔离、草稿/收藏/会话状态、加密备份；不要覆盖用户数据 |
| Bots/可选 Agent | `bots.BotDef`, `_bot_dispatch`, `bot_say`, `agent_bot._run_async` | bot 保留 uid、私聊 CHAT、异步执行；`test_r35.py` |

## 帧与账号

明文帧：`[4B 大端 header_len][UTF-8 JSON header（含 body_len）][二进制 body]`。
`FrameReader.feed` 处理半包/粘包和长度/类型错误。密文通道整体封装该帧：
`[4B ciphertext_len][12B nonce][AES-GCM ciphertext/tag]`。
X25519/HKDF 派生方向独立 key，nonce 方向与单调 counter 参与防重放。

TCP 握手后 `uid=0` Session 只接受 HELLO；`_on_hello/_attach` 校验昵称与密码并
复用稳定 uid。`_uid_clients` 包含全部 TCP/Web 端，`sessions` 为代表会话。
welcome 初始化名单、群、历史及关联状态；最后一个端离线才做 uid 下线清理。

Web 登录包含站点口令限速和昵称密码两个层次；`login_web` 创建绑定原 Web Session 的 token。
管理员走同一个登录校验，密码来自部署环境 `MOYU_ADMIN_PASSWORD`，未配置时拒绝登录，
管理员昵称不允许普通账号认领。参见 `docs/管理员凭据与公开仓库安全.md`。
`mt_token` Cookie 是优先入口，HttpOnly、SameSite=Strict，TLS 下 Secure；旧
query/body token 仍作为兼容入口。REST 不能另造与 Hub 不同的业务权限规则。

## 数据权威与落盘

- `ChatBus`：内存环形频道历史，全局 seq；消息在编辑/撤回/回应等场景更新。
- `ServerStore`：只在 Hub 配置 store_dir 时启用的最新全量状态快照，包含正文；
  `.tmp`、fsync、os.replace 写入，Hub 负责快照复制、节流与恢复。
- `audit`：按日 JSONL 元数据，不存聊天正文，与快照职责不同。
- 客户端 Prefs/历史/E2EE 本地历史是实际用户数据，账号目录按当前代码隔离；
  传输 E2EE 不代表本地 JSONL 加密。
- 云历史：客户端用密码派生 key 并 AES-GCM 打包；Hub 存每 uid 不透明密文 blob，
  不在服务器解密/合并。测试见 `test_r37.py/test_r39b.py`。
- Server SCHED 定时消息、bot 内存提醒、本地提醒不是同一个生命周期。

## 新功能的联动入口

新增帧通常按 `MsgType → Hub.dispatch/handler → ClientCore 发收 → ChatWindow`
展开；需求包含 Web 时再同步 REST 映射、SSE 与网页 UI。协议/架构不兼容变化
核对 `PROTOCOL_VERSION` 和仓库版本规范。

新增服务器状态同时核对 `_snapshot_state/_restore/_persist`；新增独立文件同时
核对用户/群归属、路径解析、读取权限、重启恢复与删除清理。

新增 UI 先找主题、组件和现有 `_send/_switch_view/_handle`；不要另起 socket 或
直接修改服务器历史副本。新增 Bot 优先复用 CHAT 和异步处理，不另造独立协议。

## 桌游规则、房间与 UI

当前实际导入 `GAME_TYPES` 为 47 个 key/47 个具体类；数量会随源码变化。
规则运行于服务器，`BaseGame` 只有逻辑、无 IO：`snapshot()` 公共快照、
`private(uid)` 私有状态、`act(uid, action)`、`tick(now)`、`ended()`、
`player_left(uid)`。非法动作抛 `GameRuleError`，不能先改状态再抛错误。

`games_pkg.__init__` 显式注册 `GAME_TYPES/GAME_META`；`RoomManager` 管生命周期，
Hub 的游戏 handler 与 tick 推进状态、按玩家分发私有内容。桌面 `GameWindow`
将公开/私有状态交给 `client_gameui.render/handle_click`；点击或按钮最终走
`ClientCore.game_action()`。

新游戏需核对规则类与注册/元数据、房间参数、公开/私有快照、painter、
`_CLICKS` 点击路由或 `client._GAME_ACTIONS` 动作按钮、图标/配色及 Web 对等支持。
网页端还需核对 `web.py:GICON/GART/GRENDER/gameAPI/renderGamePanel`，两端共享
服务器协议但拥有各自渲染和动作入口；未加入 GRENDER 的游戏有“不支持渲染”降级。
纸牌私有手牌只进 `private(uid)`，不得混入公开 snapshot/观战内容。
规则测试过、能渲染画布均不代表客户端能提交合法动作。当前部分 painter 写
“按钮区”，但对应 key 在动作表/点击表未齐；涉及该游戏先核对实际 UI 可达性，
不要单凭注册清单承诺所有桌游可玩。

## 文件与媒体

- `file_client.FileManager` 管发送/接收状态机；Hub 为 FILE_OFFER 等搭桥，优先
  P2P AES-GCM 直连，失败可转服务器分块中转。`filexfer` 的 TransferMeta、
  ChunkPlanner、PartFile、MD5 是纯数据/分块层，不是另一网络服务。
- 图片扩展名可自动接收，完成后 Core image 事件回到 GUI。群文件库是另一条
  Hub/group-file 路径，不能直接套用 1v1 文件确认/权限模型。
- 语音消息是 WAV body，Core 落本地 voice 缓存，服务器仅限量/TTL 保存媒体。
  视频留言是 VMA1（`vmemo_api`），本地 vmemo 缓存；图片/语音历史可能只剩
  元数据墓碑，需要符合现有降级显示。
- `voice_call` 管一对一信令和加密 UDP；`voice_room` 管多人 UDP mesh，服务器
  只维护名册/IP/端口。实时视频分片走现有加密 UDP，`video_api` 用 Windows
  Media Foundation/抓屏；普通回归用合成数据。
- `geo_api.parse` 与 GUI 发位置，Hub 广播；实时位置按 TTL，不当成永久聊天历史。
- `stickers` 与 sticker_shop/lottie_label 管贴纸资源和缓存。可选包、内置模型与
  打包资源不是标准库“装 Python 即都有”的能力。

## 客户端路径与线程

`launcher.launch/run_chat` 控制登录、解锁、切账号，`ClientCore.start` 起网络线程。
`ClientCore._dispatch/_push` 更新状态并向 events 队列投递，`ChatWindow._poll`
每约 120ms 在主线程处理；注入的 `on_event` 回调自身仍可在后台线程执行。

`_nick_history_dir` 将历史、voice/vmemo、贴纸缓存、E2EE 身份按安全昵称目录隔离；
首次账号目录可迁移旧顶层历史资源。注入显式 history_dir 时需自己做隔离，
不要让 smoke 或测试认领真实账号旧数据。下载目录仍是全局 `_log_dir()/downloads`。
`config._log_dir` 在源码模式用项目目录，EXE 用用户可写目录。

`vmemo_api.VmemoRecorder` 的 on_done/on_error 在后台回调；当前 GUI 预览入口
存在直接触 Tk 的接线，需要相关任务核查并移交主线程，见不变量的待验证项。
