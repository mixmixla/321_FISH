# EXE-EXIT-01 v1.2 第二轮运行独立审查：FAIL / event0

2026-10-13，purchase_review（GPT-6.1 Sol）。只读核 runtime-recheck 原 summary、case、bind、sender-ready 及三 raw 日志；未调用 native API，未启动应用、测试、构建或 sender。

结论：**本轮 FAIL / exit1，不作服务自然退出接受。** 保留首轮与第二轮独立原证据；本次不是收到 Ctrl+C 后产品退出失败，owner 在发许可前拦截，仍为 event0。

## 原始事实

- fresh Store initialize-new 自然 exit0/Job0。server33472 实际 loopback10822/10823 LISTEN、HTTP200；root 目标为 onefile父36664，路径与已核当版 server.exe 相同。
- sender 实际PID16376，由已核基础3.14.5 python.exe直接执行，记录 `-E -S -B`，image/birth与owner创建身份相同。初始 console_count=0、last_error=6；随后正确 Attach 指定server，ready记录 attached=true/event_count=0。
- 完整 console members 为 `[16376,33472,36664]`，三个完整 image/creation_filetime/session_id均保存；后二者是当版 server父子，前者是唯一基础Python sender。该集合与服务 Job `[28976,33472,36664]` 的server成员相符。
- associated console HWND596844 的 window_pid36664，hidden=true（visible=false），desktop=`MoyuExit-35724-5bff8c5906`。旧 `host_identity` 字段实际保存的是 HWND owner identity，路径/创建时间正是已核 server父36664；不能按字段名推断它必是OS backend host。
- owner在 `Dedicated OS consolehost image` 断言拦截。sender-permit.json、sender-result.json均不存在，没有到发信号许可；ready的status FAIL是尚未发送时的初始记录，不应当作sender自然终态。
- 失败清理时 sender仍running/Job1，service仍running/Job3，二者仅 owned Job强停，之后各 poll124/Job0/PID列表空。initialize poll0/Job0；forced_cleanup_count=2。sender自然detach/exit0与service自然exit0没有取得；无 post-natural inspect。
- service Job第三PID28976未在拦截前保存完整image身份，不能在本轮报告把它写成已实核conhost。后继必须重新取得完整 Job每个PID的image/birth并拒绝未知路径。

| 原日志 | 字节数 | 实际 SHA256（与 summary 一致） |
| --- | ---: | --- |
| initialize.log | 431 | `54e4f7860eb17d05891f78cbfc8d1f7d9bce6a739b38bb25c5c906980dfeda10` |
| sender.log | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| server.log | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

三 raw 的实际 hash/size全部匹配，两个0字节输出原样保留；case与summary FAIL一致。bind为受审 recheck helper `8aef99527e4dd2c97821bc6762e3a8f054a61cf06d311cc0ad80fee4000487cc`，native/sender仍原SHA。summary绑定 source13514b5d…/410且source/binary保持、所有最终Job0；不存在运行通过的证据。

## v1.3 有限方案判断

方案可安全冻结，**方案层面0 MUST**，尚不能当新helper可执行结论；实际新Task/diff/hash还须独立预审。GetConsoleWindow只承诺返回关联console所用HWND，不承诺该HWND所属进程一定是conhost；不能仅据当前owner是server就宣称已确定pseudoconsole。[Microsoft GetConsoleWindow](https://learn.microsoft.com/en-us/windows/console/getconsolewindow)

必要条件：关联HWND的window_pid必须属于完整fresh服务Job；其完整身份必须与该Job当次记录一致，且路径只允许已核server父/子或精确SystemRoot/System32/conhost.exe。完整Job各成员路径仍只允许server/conhost；console成员仍只能是唯一sender加实际server父子。必须保留image/birth/session、nonce/TTL、hidden/private desktop及sender发前全集合复查，不把backend identity与HWND owner混写，不放行任何unknown console成员。

只允许新v1.3/fresh run/profile/nonce下最后一次确认（最多第三run）；不重建或改产品/测试/依赖，不FreeConsole已有console、不补GUI fallback。原两轮FAIL及清理124永久保留，任何再次前置不符仍event0/明确受阻。主会话GUI退出、完整游戏、外机/LAN/DPI/visual保持未验。
