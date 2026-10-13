# EXE-EXIT-01 首轮运行独立审查：FAIL / event0

2026-10-13，purchase_review（GPT-6.1 Sol）。只读核原 runtime/summary.json、service-ctrl-c.json、sender-result.json、bind-before、preflight、生成 launcher 与三份 raw 日志；没有启动应用、测试或 native API。

**首轮运行 FAIL / exit1，不作服务自然 Ctrl+C 接受。** 实际执行依据为 v1.1；原 helper 的 summary 内部旧 v1 标签与 preflight 的 v1.1 冻结记录区分保留。辅助安全拦截生效，不能描述成产品已经收到 Ctrl+C 后失败。

- synthetic Store initialize-new 自然 exit0/Job0；service 在 private desktop `MoyuExit-33524-a08fa92a2e` 实际 loopback TCP1892、HTTP1893 LISTEN，HTTP200。此时仅证明服务就绪。
- sender-result 实际 sender_pid30324，初始 console_count=1、last_error=0，status FAIL，attached=false、event_count=0、detached=false。原 sender-ready.json 与 sender-permit.json 均不存在。sender 未到 AttachConsole/GenerateConsoleCtrlEvent/FreeConsole 路径，root 也未 attach/detach。
- service 原 cleanup 前 poll=null、Job active3（PID432/5516/14112），只在失败清理时 owned Job 强停，之后 poll124/Job0/PID列表空。sender 最终 poll1/Job0，initialize poll0/Job0；所有最终清理记录 Job0。强停124不能变为服务自然退出通过，未取得 post-natural inspect。
- 三原 raw 日志的实际 SHA256/长度与 summary 完全一致；server.log 为0字节的原空输出，完整保留，不能补写服务正常关闭文本。

| 原日志 | 字节数 | SHA256 |
| --- | ---: | --- |
| initialize.log | 431 | `2c60840b08545d37e6b5a3ff26f1a2b8c302d4d8a9daf7c726f348f3caabbb54` |
| sender.log | 279 | `3ac6e2cce5f829cf2ef216132ee9788e990816742ddb1ed30a740c165fb1bfa2` |
| server.log | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

生成 detached launcher 实际 flags 为 SUSPENDED|DETACHED|UNICODE|EXTENDED，service 为 SUSPENDED|NEW_CONSOLE|UNICODE|EXTENDED；原 Assign-before-Resume 与继承句柄白名单保留。bind 三 helper SHA 与已审 v1.1 相同。另独立逐份核当前410源输入及三构建EXE实际SHA全部保持，source_content_id仍 `13514b5d70d6e92a39f9eadd8f20ae39562d3e80570437b26f6e4ea0a2164345`。

执行原快照 `exit_native.py.executed.txt`、`exit_sender.py.executed.txt`、`exit_runtime.py.executed.txt` 均已逐份重新计算实际SHA，与首轮 bind 对应的三个 hash 完全相同；原执行身份具备可公开接续的字节证据。

静态原因旁证：本机项目 .venv/Scripts/python.exe 与同基础版本 Lib/venv/scripts/nt/venvlauncher.exe 的SHA相同（`896ccf899b9d45c1c119ba35d6cce6e16cc10dd6a7f502f88fb50429a6e5cf4c`），pyvenv.cfg 指向基础3.14.5解释器。CPython3.14.5 venvlauncher 源码在419-420以 creationFlags=0创建真正解释器子进程，不传外层 DETACHED。这一机制与 sender 初始 console1 观测一致，属有来源的静态技术推断；首轮未完整保存 redirector 父子 image/PID链，不能假称已作该链的运行实证。[CPython 官方源码](https://raw.githubusercontent.com/python/cpython/v3.14.5/PC/venvlauncher.c)

首轮 FAIL/exit1/event0 及 owned 清理124 必须永久保存。后续只在冻结 v1.2 并通过新 helper 独立预审后，以 fresh run/profile/nonce作有限复核，不覆盖本轮原证据。主会话 GUI 退出、完整 EXE 游戏、外机/LAN/DPI/visual 均仍未验。
