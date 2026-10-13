# EXE-EXIT-01 v1.3 最后一次确认 helper 独立预审

2026-10-13，purchase_review（GPT-6.1 Sol）。实读冻结 Task v1.3，以及三个新文件对原已审文件的全部实际 diff。未启动应用、sender、测试、构建或 native API；旧预审与两轮 FAIL 审查全部保留。

结论：限定最终 helper 安全 **0 MUST**，可由唯一 root 在 fresh runtime-final/profile/nonce 下执行一次最后确认。本阶段最大3 runs；本次无论 PASS/FAIL均收口，不递归复核。本结论只允许执行，不提前作服务自然退出接受。

## 实际有限差异

- exit_native_metadata.py 仅把 console info 的旧字段 host_identity 改为准确的 window_owner_identity；完整动态 console/Job 列表、process image/creation time/session、hidden/exact private desktop观察逻辑不变。
- exit_sender_metadata.py 仅改为 import 新 native；初始无console（0/error6）、精确 target身份后 Attach、单独忽略sender Ctrl+C、完整ready与permit集合/nonce/10秒TTL/fresh身份比较、发前重新核console HWND owner与private/hidden、单次 GenerateConsoleCtrlEvent(0,0)及sender-only detach完全不变。
- exit_runtime_final.py 改为新runtime-final与新helper bind/命令/summary标签；固定同项目3.14.5基础解释器、hard-pin、-E/-S/-B及sender-only去__PYVENV_LAUNCHER__不变。
- owner 先取得完整fresh服务Job逐PID identity，全部image只能为已核server或精确SystemRoot/System32/conhost.exe。associated HWND owner必须当前服务Job成员、与该Job当次逐PID image/birth/session身份完全相同，且image在同一两类精确路径集合内；不是允许任意console成员。
- 真正接收信号的console集合仍严格为唯一sender加actual server父子，服务PID必须在其中且server两PID均属于fresh服务Job、路径与当前产物相同。nonce/发送前完整集合与身份重核不变。关联HWND的metadata修正不会扩大Ctrl+C的接收范围。
- 新console_metadata将associated_window_owner_identity、job_conhost_processes分账，actual_backend_identity=UNDETERMINED，pseudoconsole_claimed=false及window_owner_is_backend_claimed=false。仅记录自有Job里的conhost，不直接操作其窗口或PID。
- 原 SUSPENDED+专用hidden NEW_CONSOLE、DETACHED sender、Job句柄不继承、Assign-before-Resume、OS-only fresh profile/loopback条件保持。root没有Attach/FreeConsole或GUI fallback路径。
- 自然验收仍要求实际TCP/HTTP就绪、sender exit0/detach/Job0、服务exit0/Job0、两端口关闭、post-natural同Store inspect exit0/Job0，全部在terminate/close清理前取得。事件API成功本身不算通过；失败强停仅记清理124。

## 实际新文件身份

| 文件 | SHA256 |
| --- | --- |
| exit_native_metadata.py | `ef8ed05bf7ba1160e1b820f5625557ae806cd35b49eb2d9f50dd068203720795` |
| exit_sender_metadata.py | `b6df5c6731d0148983b207db33775dbe7b038d87be20a83790f981bbb630e312` |
| exit_runtime_final.py | `c7b4342c1623e378ac98127665186b82e00b10fa02150a3d9a6beec8920259a8` |

来源均为 `_tmp_gui/advance-20261013`。以上 hash 与根提供前缀一致；必须由执行前bind/执行快照及原日志绑定同字节，版本变化不能沿用预审。

后续只核此次原证据与公共归档，不重建、不更改产品/测试/依赖、不启用危险visual，不通过改变未知成员白名单、第四run或强停替代自然通过。前两轮FAIL/event0必须保留并列。主会话真实GUI退出BLOCKED、完整游戏、外机/LAN/DPI/视觉均仍未验。
