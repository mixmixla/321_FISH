# Project Memory — 321_FISH 摸鱼助手

## Snapshot

- 用途：Windows 局域网聊天、文件/媒体、网页端与桌游；Tkinter 桌面客户端。
- 栈与入口：Python 3.14.5，`dev.ps1` / `run.py`；Hub 加密 TCP，网页 HTTP(S)/SSE。
- 最近核对：2026-09-30，从 `origin/main` 的 `c8f2860` 拉取登录窗反馈与协作任务清单。
- 当前机器路径 `D:\Project\321_FISH`，迁移后以任务工作区为准。
- 个人开发技能：`$fish-assistant-dev`；源码事实优先于技能旧索引。

## Architecture

- `client.py:ChatWindow` 管 Tk UI；`client_core.py:ClientCore` 管网络、状态、API 与
  本地历史。后台 events 队列由 `_poll/_handle` 在主线程处理。
- `protocol.MsgType/FrameReader` 管 JSON header + binary body 帧；`crypto` 管
  X25519/HKDF/AES-GCM 加密通道；`crypto_e2ee` 管消息层端到端密聊与 ratchet。
- `server.Hub.dispatch/_on_*` 是权威业务入口；`ChatBus` 管频道历史与全局 seq。
  `_uid_clients` 是同 uid 的全部端，`sessions` 是代表端，Web token 按 uid 映射。
- `web.PAGE/_Handler/_sse_loop` 是内嵌网页与 HTTP/SSE；REST 复用 Hub 权限/业务，
  没有独立 npm 前端。`discovery` 管 UDP 发现，`tls_cert` 管自签 HTTPS。
- `ServerStore` 保存启用持久化时的最新全量快照；audit 只记元数据。云历史在
  客户端加密，服务器存不透明 blob；本地 JSONL/prefs 仍含实际用户内容。
- `games_pkg` 注册 47 个当前游戏类，`RoomManager` 管房间，`BaseGame` 的
  snapshot/private/act/tick/ended 管公开、私有与规则；桌面 painter/点击/按钮
  分别在 `client_gameui`、`client._GAME_ACTIONS`，注册不等于 UI 完整可玩。
- `FileManager` 管 P2P 优先与服务器回退，`filexfer` 是分块/PartFile 数据层；
  群文件库另走 Hub 权限路径。通话/语音房使用加密 UDP；位置、VMA1、WAV
  有各自 TTL/缓存与 UI 流程。
- `theme/ExcelChrome/ExcelSheet` 是桌面可编辑工作表；`_sync_excel_layout` 复用旧
  聊天控件，`_send_excel_text` 仍进入统一聊天发送，工作表值在 `Prefs.excel_cells`。
- 本地历史/媒体/身份按 `_nick_history_dir` 隔离，首个新账号可能认领旧顶层资源；
  显式 history_dir 需调用者隔离。下载目录仍为全局 `_log_dir()/downloads`。

## Conventions and constraints

- 所有 Windows shell 用 PowerShell 7。以 `.python-version` 和 requirements 为准，
  推荐 `.\dev.ps1` 避开系统旧 Python；先 server 后 client。
- 运行依赖 cryptography/Pillow/pystray；测试与打包 pytest/PyInstaller。
  vosk/模型、翻译、Lottie 为可选扩展，不默认视为全部已具备。
- 分支 `feature/` / `fix/`，提交 `类型: 一句话`；main 禁止直接 push，走 PR。
  协议/架构不兼容变化同步 PROTOCOL_VERSION；发布版本在 tag 时确定。
- Tk 仅主线程操作，保留 tkguard；注入 Core.on_event 或录制回调仍可能在后台。
- 保护 prefs/history/audit/server_state/web_tls/downloads，不入提交/技能/截图。
  当前仓库私有，默认保留可见性，不复制配置口令值。
- 门禁：`.\dev.ps1`；专项 `.\dev.ps1 test -k 关键词`；可加
  `-o faulthandler_timeout=60`。默认合成媒体，真机/截图需显式选项。
- `run.py` 用独立项目临时目录和 pytest 子进程，父进程清理/透传退出码；
  conftest 通过 sessionfinish 保留真实退出状态，再避开 Tcl 关闭阶段。

## Decisions

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

## Current work

- Excel/环境/审核改动已通过 PR #1 合入 main；后续前台唤起改动通过 PR #2 合入。
- 当前修复分支 `fix/login-hidden-root`：处理隐藏宿主导致登录窗不渲染的反馈，
  修复与独立回归已完成，走 PR 交付，远端合并与发布状态以 GitHub 记录为准。
- 已完成：测试误报修复、成员/上传归属、多端删号/ token、动态图片权限、链接预览
  SSRF、E2EE 计数窗口、音频 callback/PCM 指针/池回收及可编辑 Excel 皮肤。
- 最近验证：可编辑工作表修订全量 1228 passed / 2 默认跳过；最终工作表专项
  8 passed，真实 GUI 与 680×480 冒烟通过。这是历史结果，后续改动需重新核对。
- 登录修复验证：101 个测试文件分进程逐文件通过；最后补充边界用例后重跑登录
  两个文件，共 16 passed，累计当前门禁 1244 passed / 2 默认跳过。真实自有 Tk
  宿主下登录窗可见/聚焦；取消、再次登录、最小化宿主和映射超时均已验证。
- 未验证：发布 EXE、全部游戏 UI 可达性、完整可选扩展、真实音频长期稳定性。

## Risks and follow-ups

- `optional.has_lottie` 探测 rlottie、renderer 导入 rlottie_python；涉及该扩展先核对。
- VmemoRecorder 后台 on_done/on_error 当前直接进入 GUI 预览/Toast 接线；相关
  开发需主线程移交，尚未真机复现，本次技能整理不修改业务代码。
- 部分游戏 painter 与 _CLICKS/_GAME_ACTIONS 路由未齐；新增/启用时验证动作可达，
  不把纯规则测试等同完整玩法交付。
- 昵称安全目录替换/截断可能碰撞，下载目录全局；迁移/多账号任务需针对验证。
- `.spec` 含旧机器绝对 icon 路径且缺 build.py 的 Vosk 模型逻辑；打包入口不等价。
- docs/优化清单.md 属于另一个 Ollama IDE 项目；旧 UI 文档可能只记录早期状态。
- 链接预览目前拒绝 3xx，部分跳转网页没有卡片；正文与链接正常可用。

## Evidence index

- `COLLABORATION.md`, `README.md`, `docs/开发环境.md` — 当前约定与启动方式。
- `protocol.py`, `crypto.py`, `crypto_e2ee.py` — 帧、握手、消息 E2EE。
- `client.py`, `client_core.py`, `prefs.py` — 主线程 UI、网络事件、本地状态。
- `server.py`, `web.py`, `server_store.py`, `audit.py` — Hub、网页、权威快照与审计。
- `games_pkg/base.py`, `games_pkg/rooms.py`, `games_pkg/__init__.py`, `client_gameui.py` — 游戏各层。
- `file_client.py`, `voice_call.py`, `voice_room.py`, `voice_api.py`, `vmemo_api.py` — 文件/媒体链。
- `widgets/excel_chrome.py`, `widgets/excel_sheet.py` — 可编辑工作簿与发送接入。
- `build.py`, `client.spec`, `server.spec`, `optional.py` — 打包入口和能力降级。
- `docs/项目审核_2026-09-30.md`, `tests/test_audit_*.py`, `tests/test_excel*` — 审核/工作表证据。
