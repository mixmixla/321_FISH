# 开发、验证与打包

## 环境与入口

源码要求 Windows 10/11、PowerShell 7、pyenv-win Python 3.14.5。
以当前 `.python-version`、`requirements.txt`、`requirements-dev.txt` 为准；
不能使用历史文档的“纯标准库、只装 pytest”说法。

运行依赖有 cryptography（握手、E2EE、媒体/备份加密）、Pillow（图片/截图）、
pystray（托盘）；开发还需 pytest、PyInstaller。可选语音转写、翻译、Lottie
见 `optional.py`，语音转写另需模型目录。

优先用 `dev.ps1`，避免系统 Python 3.10 或其他 PATH 项抢先：

```powershell
.\dev.ps1                      # 全量门禁
.\dev.ps1 test -k excel_sheet  # 专项示例
.\dev.ps1 test -o faulthandler_timeout=60
.\dev.ps1 server               # 独立终端先起服务
.\dev.ps1 client --host 127.0.0.1
.\dev.ps1 build
```

`run.py` 也支持同样子命令，必须由项目 `.venv\Scripts\python.exe` 调用。
默认 `run.py` 是测试，不是 GUI。`dev.ps1` 透传余下参数，避免 PowerShell
高级函数的 `-OutVariable/-OutBuffer` 与 pytest `-o` 冲突。

`run.py` 的测试分支在子进程运行 pytest；每次在 `_tmp_gui` 内创建独立目录，
避免不同 Windows 执行身份共享 `pytest-of-*` 的 ACL/锁冲突，父进程清理并
返回子进程退出码。`tests/conftest.py` 因 Tcl 清理问题调用 `os._exit`，
通过 `pytest_sessionfinish` 保存真实状态；不要再读不存在的 `Config.exitcode`。

## 选测试

| 改动域 | 首先检查的用例 |
| --- | --- |
| 帧/握手 | `test_protocol.py`, `test_crypto.py` |
| Hub、会话与权限 | `test_server.py`, `test_multisession.py`, `test_admin_groups*.py`, `test_audit_server_security.py` |
| 昵称密码与网页登录 | `test_auth.py`, `test_r47.py`, `test_p0_web_security.py` |
| 群与频道 | `test_r28_group_mgmt.py`, `test_r53.py`, `test_r54.py`, `test_r73.py` |
| 消息列表、主题与设置 | `test_msg_list.py`, `test_msglist_group.py`, `test_session_list.py`, `test_theme.py`, `test_settings_nav.py` |
| 登录窗显示、焦点与原生句柄 | `test_login_visibility.py`, `test_login_foreground.py` |
| Excel 工作表 | `test_excel_sheet.py`, `test_excel_skin.py`, `tests/_smoke_excel_skin.py` |
| 文件/网页附件/转发 | `test_filexfer.py`, `test_fwd_media.py`, `test_r46b_web_fix.py` 及对应 R 系列 |
| E2EE | `test_r36.py`, `test_r42.py`, `test_r44.py`, `test_audit_e2ee_limits.py` |
| 音视频 | `test_r38.py`, `test_r39a.py`, `test_r41.py`, `test_r45.py`, `test_audit_audio_callbacks.py` |
| 游戏 | `test_games*.py`, `test_rooms.py`, `test_server_games.py`，按游戏 key 搜索对应文件 |
| 审核修复 | `test_audit_*.py`, `test_test_runner_exitcodes.py` |

用 `rg` 在测试中找实际函数/消息类型，不因 R 编号接近就猜覆盖范围。
目标代码改变后按 `COLLABORATION.md` 跑全量；当前 `docs/任务清单.md` 要求按文件
分进程跑门禁，避免长生命周期中的 Tk/网络状态串扰，不把多文件合并成一次 pytest。
完整验证应遍历当前所有 `tests/test_*.py`，汇总各进程真实退出码和计数。
`dev.ps1 test` 目前仍使用单个 pytest 进程，T1 的 `test-all` 入口尚未实现；
逐文件验收可分别用 `.venv\Scripts\python.exe -m pytest -q tests/单个文件.py`
并为每个进程指定独立 `--basetemp`，不要假定未来命令已经存在。
文档/技能更新一般只需核对引用，
不重复运行整个 GUI/网络门禁。

## GUI 与设备检查

普通单元/网络测试应使用临时 Prefs、历史目录、合成媒体、FakeMic/FakeSpk/FakeCam。
剪贴板测试使用内存替身，不覆盖真实剪贴板。需要真机采集时使用明确选项：

```powershell
.\dev.ps1 test --run-visual -k three_modes_render_different
.\dev.ps1 test --run-hardware -k real_camera_capture
```

新 Entry 必须在 `root.update_idletasks()/update()` 完成映射并获得焦点后再生成
按键事件；程序化直接调用 handler 不能证明 Tab、Ctrl+Enter 或中文输入可用。
GUI 改动检验真实窗口、正常/最小尺寸、皮肤/表页切换、关闭与偏好保存。
新 worksheet 已有隔离冒烟，支持 `--screenshot`；只截本应用合成数据窗口。

旧根目录 `_smoke_*.py` 有些会改共享 prefs 或含旧色值断言，先读代码再执行，
必要时移入隔离数据目录；不能因脚本名字像当前功能就直接运行。

卡住时查当前用例与目标测试进程调用栈；`faulthandler_timeout` 可帮助定位。
别仅加 timeout 后释放仍被 WinMM 驱动引用的缓冲，也不把全部 GUI skip 当作通过。

## 打包

`build.py:build()` 使用 PyInstaller 构建 console `server.exe` 和 windowed
`client.exe`；`COMMON_HIDDEN` 是动态导入清单。函数内导入的 web/discovery、
托盘/媒体/UI 模块和 cryptography 二进制子模块要核对收集。新增静态导入的
ExcelSheet/ExcelChrome 通常自动收集，仍需实际打包验证后才能声称 EXE 可用。

语音转写打包还依赖 `vosk_args()`、`stt_data_args()` 和 `models/vosk/am/final.mdl`；
依赖/模型缺失会警告并继续，成功打包不代表具备转写能力。`.spec` 与 build.py
可能存在不同资源清单，按实际执行入口核查。当前会话只验证了源码和测试，
未验证成品 EXE、全部可选扩展或真实设备长期通话。

## Git 与文档

仓库约定 `feature/` / `fix/`，`类型: 一句话说明`，稳定 main 只经 PR 合并。
协议/架构不兼容更改需同步 `config.py:PROTOCOL_VERSION` 和两端；日常提交不改
发布版本，tag 时按 `COLLABORATION.md` 决定。已有本地改动先保留，再决定同步方式。

`PROJECT_MEMORY.md` 记录当前事实；`docs/项目审核_2026-09-30.md` 是历史审核证据。
`docs/优化清单.md` 属于另一个 Ollama IDE 项目；旧 UI 设计笔记不能当成当前状态。

用户明确要求“成品 EXE 语音转写可用”时，缺 Vosk 或模型不是可接受的最终交付：
先验证包与 `am/final.mdl`，再走 build.py 收集，并用隔离数据目录/合成 WAV
验证成品定位模型与识别调用。`MsgList.on_transcribe → ChatWindow._voice_stt →
optional.find_model_dir/transcribe_wav` 是识别链；voice_api 是采集/播放，不能混同。
`test_r71.py` 覆盖模型路径，`test_r38.py` 覆盖软依赖降级；源码单元测试不能
证明成品可转写。目前没有成品 EXE 的正向 STT 验收测试，应单独完成并报告。
