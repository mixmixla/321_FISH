# EXE-EXIT-01 v1.1 独立 helper 预审

2026-10-13，purchase_review（GPT-6.1 Sol）。实读冻结 Task、exit_native.py、exit_sender.py、exit_runtime.py 与此前已核的 friend_trial_process.py。只读代码及官方 API 合同；未启动应用、sender、Tk、测试、构建、服务或任何 native API。本报告是明确授权的 ignored 文档。

执行前追加核验 Task v1.1：退出执行及验收范围与 v1 相同。仅增加独立工作树原日志出版规则 `docs/review-assets/EXE-EXIT-01/logs/*.txt -text -whitespace`，以及澄清“不直接按 consolehost PID 杀进程或关闭其窗口；失败时本次 owned Job 整体清理可覆盖其中的 consolehost，仅记清理”。实际 .gitattributes diff 只有该本 Task 窄规则；其他源码/测试/文档规则未变。三个 helper 实际 SHA256 与下表完全相同，因此既有静态预审结论继续适用 v1.1。helper 内部固定 v1 标签不代表不同退出实现，后续 Review 应注明运行依据的冻结合同为 v1.1。

## 结论

限定 helper 执行安全 **0 MUST**，支持唯一 root 按本 Task 执行一次。此结论不保证实际服务会自然退出，也不构成运行验收；首次原始日志及结果后须另作独立终核。主会话真实 GUI 退出保持 `BLOCKED_NATIVE_UI_UNAVAILABLE`，没有截图/鼠标/注入/WM_CLOSE 替代路径。

## 核验边界

- server task-only launcher 仅改函数名、STARTF_USESHOWWINDOW/SW_HIDE 与创建标志，使用 SUSPENDED|NEW_CONSOLE|UNICODE|EXTENDED，去掉 NO_WINDOW 与 NEW_PROCESS_GROUP；sender 用 SUSPENDED|DETACHED|UNICODE|EXTENDED。原 unnamed KILL_ON_JOB_CLOSE Job、不允许 breakaway、NUL/日志继承句柄白名单、AssignProcessToJobObject 后 ResumeThread 均保留；Job 句柄不继承。
- 原三 binary hash 与 410 source inputs 在任何应用启动前核验；fresh profile/Store、随机 loopback 端口和唯一 private desktop，关闭 discovery/tray/global hotkeys/hardware/HTTPS。没有旧资料、GUI fallback 或系统配置动作。
- sender 先证明 GetConsoleProcessList 返回无 console / ERROR_INVALID_HANDLE，不通过 FreeConsole 脱离已有 console；然后按 target PID/path/creation_filetime/session_id 精确相等核验，拒绝 PID 0 与 ATTACH_PARENT_PROCESS。Attach 后只在 sender 设置忽略 Ctrl+C；root 只有观察功能，未调用 AttachConsole/FreeConsole。
- Console PID 列表和 Job PID 列表均动态扩容，错误或超出上限失败，不以截断数组作完整证明。owner 要求 sender Job 只有 sender，console 除 sender 外含指定 server 父子且全部属于 fresh service Job，二者路径均为该受核 server；完整 service Job 的其余 image 只允许精确 SystemRoot/System32/conhost.exe，不接受未知 image。
- console HWND 的 desktop 必须为唯一预定 private desktop且不可见；OS consolehost 路径、创建时间及会话身份被记录。没有按 consolehost PID 单独 terminate、关闭窗口或输入动作；所有必要失败清理仍限定 owned Job。
- permit 使用新 UUID nonce、sender 完整身份和 10 秒 TTL，经原子 replace 发布。sender 发事件前重新取得 console 完整集合，要求与 ready/permit 相同，target/sender 均在其中，除 sender 外集合与 owner 的 owned_console_pids 相同；逐 PID 的 image/creation_filetime/session_id 必须再次完全一致，console HWND/host/desktop/visibility 也必须不变。未知成员、身份变化、超时或任何失败不发送。
- GenerateConsoleCtrlEvent(0,0) 只有一条路径、无重试；sender 在 finally 仅脱离自己附着的 console。这里的 group0确实广播同一 console 的所有进程，不能用非零 group定向 Ctrl+C，因此完整归属验证不可省略。[Microsoft GenerateConsoleCtrlEvent](https://learn.microsoft.com/en-us/windows/console/generateconsolectrlevent)
- console 列表扩容正确遵循“返回所需容量后重新取得完整列表”的合同；DETACHED 与 NEW_CONSOLE 分开，NEW_CONSOLE 不继承 root console。[GetConsoleProcessList](https://learn.microsoft.com/en-us/windows/console/getconsoleprocesslist)、[创建标志](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags)、[AttachConsole](https://learn.microsoft.com/en-us/windows/console/attachconsole)
- 服务实际 TCP/HTTP 就绪之后才启动 handshake；事件成功不直接视为自然接受。代码必须先记录 sender exit0/detach/Job0、server exit0/Job0、两端口不可连接、同新 Store inspect exit0/Job0，全部在 finally 的 terminate/close 清理前。失败只保存 FAIL 和 scoped cleanup；源/产物变化、Job 残留也使 summary exit1。

## 受审脚本身份

| 文件 | SHA256 |
| --- | --- |
| exit_native.py | `33284e300c7ac237b8a9c6f89342e2dc970f8ad02822d329b108b898870b8554` |
| exit_sender.py | `ea992a918b7f50fba8a62a59cf0c1da760dcc975728cb3f691a78704d77676c4` |
| exit_runtime.py | `701450c88a4036660bb5d87b1d419e52af19f8690ee3e803199710849e0af9a5` |

来源均为 `D:/Project/321_FISH/_tmp_gui/advance-20261013/`。实际脚本变化须重新核对，不能沿用此 hash 的通过结论。

## 后续终核要求

保留 bind/launcher-proof、sender-config/ready/permit/result、完整 console/Job 身份列表、所有 raw 日志/hash、自然状态与 cleanup 的前后记录、端口关闭及 inspect 原文，并核原源与三产物仍未变。任何受阻不得用全局 console 广播、GUI fallback、第二次事件或强停替代自然接受。完整游戏、外机/LAN/DPI/视觉与真正主会话退出均仍未验。
