# 关键约束与条件排错

本页只在相关模块修改、排错或审核时使用。以下基于 2026-09-30 本地源码；
后续代码变化先查证锚点，不能把已修问题重新当成当前漏洞，也不由本页自动
扩大任务为安全重构。

## 聊天与账号状态

- `Hub.sessions[uid]` 是代表，不是 uid 的全部客户端；`_uid_clients` 才是多端集。
  删除账号/撤销会话要覆盖所有端和 `web_tokens`，`dispatch` 不接受失效连接。
  相关锚点：`_attach/unregister/_session_is_active/_on_admin_user_del`。
- 管理员密码来自 `MOYU_ADMIN_PASSWORD`，未配置/空白时关闭登录，保留管理员昵称。
  TCP/Web 共用 `_pwd_check_for_login`；普通 SET_PWD 不可修改部署凭据。
  `web_tokens` 绑定已认证 Web Session，注销一端只撤销该端 token，删号撤销全部端。
- `ChatBus.seq` 是消息主标识；编辑、撤回、反应和已读是在既有消息上更新。
  UI 等服务器事件确认，不直接改 raw 来假定远端成功。保持 pending/failed
  本地乐观行与回显去重；纯 core.history 会漏掉尚未回显的行。
- 服务器定时消息 `SCHED_*` 是权威持久化；客户端提醒、本地草稿、bot 内存提醒
  是不同对象，不因名字相似合并生命周期。
- CC-02A-RETIRE-CORE以独立retired字段保留UID/昵称占用，核心t0与CHAT/burn/draft/sched/profile最终C在Hub→bus内存锁内排序。
  异步prepare不是提交许可；有效JSON持久确认后才报confirmed，失败阻断不自动回开。首次失败无durable intent不保证重启屏障。
  save显式成功、actual writer fresh capture及运行态请求代次是最小前置；GUI、CLOUD/upload/bot回复/preview资源、整体loader/marker仍延期，
  不把CORE等同完整RETIRE/R1通过。执行版本与验证只读当前Task/Review，不从本页自动授权真实退役或其它候选。
- 频道只读、群成员/管理员、消息编辑/撤回权限最终由 Hub 校验。新输入方式
  还需同步 UI 禁用状态。私聊撤回双方范围、论坛 thread_root 等沿用现有语义。

## Tk 与可编辑 Excel

`ChatWindow` 是组合式对象，不是 Tk 子类；调度用 `self.root.after`。
`ClientCore.events → ChatWindow._poll/_handle` 把后台事件带回主线程。
`tkguard` 处理 Font/Image/Variable 析构及 Tkapp 生命周期，不能删除守卫后
用“测试退出为 0”掩盖 Tcl 错误。

登录入口：`launcher.launch → show_login → LoginDialog`。独立登录用 withdrawn
root 作 Tcl 宿主，`owner_hidden=True` 时不能把它设置为 transient owner；
已有可见 master 保留 transient 关系。完整布局、映射后再取得本地 grab 和
输入焦点；退出时取消发现轮询/前台重试并释放自己的 grab。Win32 置顶须用
`GetAncestor(winfo_id(), GA_ROOT)` 的实际顶层 HWND 和指针宽度安全的原型，
不能直接操作 Tk client HWND；延迟唤起不能把密码框焦点移回账号框。
最小化宿主不作为 transient owner；映射等待有 2 秒上限，超时按取消清理，
外部关闭窗口也要停止发现线程，不能只依靠 Tk 销毁定时命令。
只修改登录自己的宿主策略，不全局改 `dialogbox._hide_owner` 或口令锁宿主。
回归见 `tests/test_login_visibility.py` 和 `tests/test_login_foreground.py`。

Excel 接线：`client.py` → `widgets.excel_chrome.ExcelChrome` →
`widgets.excel_sheet.ExcelSheet`；`theme.py` 提供配色 token，通过
`ChatWindow._sync_excel_layout/_send_excel_text` 接入。

- Excel 模式用独立 sheet_area，原聊天 body 仍保留；其它皮肤/ghost/原聊天视图
  必须恢复原控件。关窗取消轮询并保存未提交的本地格子输入。
- worksheet 坐标 API 为 0-based，名称框显示 A1。只有视口 Canvas item 和一个
  活跃编辑 Entry，不为 1000×26 格创建 Entry。列标/行号与双向滚动同步。
- Enter 提交本地值并下移，Tab 右移，Esc 取消；Ctrl+Enter 才显式发送。发送后
  格子保留，不能把普通提交/TSV 粘贴当成聊天发送。
- `work_sheet` 是本地可编辑表，`excel_cells` 在 Prefs；`message_sheet` 展示
  `_Row.raw` 的当前会话消息，其 A:D 为只读。它不是 Excel 公式计算引擎。
- 公式栏与当前格同步，保存/关闭需提交编辑；字体为显示级设置。发送仍进入
  原 `_send`，不绕过密聊、状态、草稿或只读规则；原聊天草稿要保留。
- GUI 复现用 `test_excel_sheet.py/test_excel_skin.py/tests/_smoke_excel_skin.py`，
  包含中文、Tab/Ctrl+Enter、切表/换肤、本地保存、原聊天回退和 680×480 检查。

## 权限、路径与预览

- 群文件分块/完成须验证成员、上传者 uid、偏移和实际字节数，并把检查、写入、
  状态推进放入同一序列化边界。fid 可猜测，不能当成授权。
- 动态图片 HTTP 入口需登录，图片须仍被现存动态引用；删除动态清理安全目录
  内的独占文件。检查 filename 与 realpath，不能只过滤 `../`。
- 链接预览必须在连接前拒绝非公网及混合 DNS 结果，固定已校验 sockaddr，
  HTTPS 保留原 hostname 的 SNI/证书校验；不使用代理绕过检查。当前实现拒绝
  3xx，因此部分跳转链接没有预览，正文/链接仍可用。若增加跳转，逐跳检查。
- E2EE 接收 ratchet 对未认证 counter 有有限跳跃窗口；不能先执行不受限补链
  再检查 AES-GCM。改变窗口要测试正常跳步、重放、篡改与链态不被失败修改。

锚点：`Hub._on_group_file_upload*`、`_moment_image_path/_moment_image_active`、
`web._Handler._moment_img`、`fetch_preview/_preview_public_addr`、
`crypto_e2ee.MAX_RATCHET_SKIP/unseal_ratchet/unseal_group`；回归在 `test_audit_*.py`。

## WinMM 音频生命周期

回调不得调用其它 wave native API；当前 `voice_api.py` 只在 callback 复制数据、
排队/通知，由普通 worker/pump 重挂、unprepare、reset、close。异步错误通知避免
回调等 CallManager 锁、挂断等 driver callback 的锁反转。

`WAVEHDR.lpData` 是原始指针；不能用 c_char_p 字段的自动 bytes 转换处理含 NUL
的 PCM。按 header 地址匹配回收池，而非 `.contents` 包装的 Python identity。
保留 proc/header/buffer 引用直到设备关闭，启动失败也不能重入持有的普通 Lock。

依据：[Microsoft waveInProc](https://learn.microsoft.com/en-us/previous-versions/dd743849(v=vs.85))。
离线回归：`test_audit_audio_callbacks.py`；网络 R45 用 FakeMic/FakeSpk/FakeCam。
真实驱动稳定性需要单独、明确授权的真机验证，不由“Windows DLL 存在”推出。

## 已知需要按功能核对的边界

- `optional.has_lottie()` 当前探测 `rlottie`，渲染器导入 `rlottie_python`；两者
  名称不一致。涉及 Lottie 时先核对包/API与降级，当前基础环境未验证此扩展。
- 本地聊天历史、E2EE 本地历史、prefs 与服务器快照含实际内容；传输加密
  不等于本地文件加密，审计元数据与快照正文不能混淆。
- 当前网页仍用独立 HTML/CSS/JS 主题；桌面 Excel 皮肤不会自动改变网页外观。
- 视频留言录制器声明后台线程回调，但 `ChatWindow._on_vmemo_done/_on_vmemo_error`
  目前直接触发 Tk 预览/Toast；涉及视频留言时核对主线程移交，当前未做真机复现。
- 游戏 painter、`_CLICKS` 和 `_GAME_ACTIONS` 对部分 key 的路由覆盖不一致；
  修改/启用这些游戏先验证具体动作能从客户端到达 Hub，不能只跑规则测试。
- 昵称安全目录会替换字符并截断，可能碰撞；下载目录不按昵称隔离。涉及账号
  与迁移时验证这两类路径的行为，不擅自迁移/合并现有用户目录。
- 现有 `.spec` 的图标含旧机器绝对路径，且没有当前 build.py 的 Vosk collect/data
  逻辑；直接调用 spec 打包前要核对，不把两个入口视为等价。
