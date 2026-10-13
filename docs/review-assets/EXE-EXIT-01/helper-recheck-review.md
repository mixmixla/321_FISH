# EXE-EXIT-01 v1.2 recheck helper 独立预审

2026-10-13，purchase_review（GPT-6.1 Sol）。实读最新 Task v1.2、新 exit_runtime_recheck.py 相对原 exit_runtime.py 的全部实际 diff，以及未变的 exit_native.py/exit_sender.py。未启动任何应用、sender、Tk、测试、构建或 native API；旧 helper-review.md 保留。

结论：限定 recheck helper 安全 **0 MUST**，可由唯一 root 按 v1.2 执行一次新 run。实际自然退出仍须新原证据终核，不因预审通过或 observer 修正提前接受。

## 有限差异

- 输出改为新 `runtime-recheck`，由 exist_ok=False 防止复用；随新 run 生成 fresh profile/Store、随机 loopback/private desktop/nonce。新 bind 记录 recheck 文件名/hash，summary 标签改为 v1.2；原 run 不覆盖。
- owner 必须仍为项目原 `.venv/Scripts/python.exe`、原 `.venv` prefix 和 Python3.14.5。sender 只使用该 owner 的 sys._base_executable，要求与该 .venv 的 pyvenv.cfg executable、home、version 三者一致，并 hard-pin 基础解释器 SHA256 `3adbbf2af609e206e3ca18cd55fc7c4b52f5c8bb8218dd99fd5a9e50d7a193cd`。
- 此 pin 已由前一轮独立实际文件哈希核验：同项目 pyvenv.cfg 指向的基础3.14.5 python.exe 为106208字节；项目 .venv python.exe 是255200字节的 venvlauncher，二者不能混同。没有切换 owner 构建/测试环境、改依赖/项目源/三 EXE。
- sender 命令使用该固定基础解释器加 `-E -S -B`，stdlib-only 脚本；仅 sender_env 清除 __PYVENV_LAUNCHER__，其余原 OS-only/fresh profile 安全 flags 保持。记录 sender_interpreter、实际 sender_command 与 owner 创建得到的 sender_identity，供后续核对真实 image/birth/PID。
- 原 launcher、无初始console的 count0/error6 守卫、单 sender PID Job、完整动态 Job/console 集合、image/creation time/session 复查、nonce/10秒TTL、一次 Ctrl+C、sender-only detach，以及自然 exit0/Job0/端口关闭/inspect 必须先于 cleanup 的条件全部未改。未放行初始 console 或未知成员，也没有调用 FreeConsole 清除已有 console。

## 实际 hash

| 文件 | SHA256 |
| --- | --- |
| exit_runtime_recheck.py | `8aef99527e4dd2c97821bc6762e3a8f054a61cf06d311cc0ad80fee4000487cc` |
| exit_native.py（未变） | `33284e300c7ac237b8a9c6f89342e2dc970f8ad02822d329b108b898870b8554` |
| exit_sender.py（未变） | `ea992a918b7f50fba8a62a59cf0c1da760dcc975728cb3f691a78704d77676c4` |
| 原 exit_runtime.py（保留） | `701450c88a4036660bb5d87b1d419e52af19f8690ee3e803199710849e0af9a5` |

来源目录 `_tmp_gui/advance-20261013`。本次静态结论仅绑定上述文件字节及冻结 v1.2。

首轮 FAIL 必须继续与复核并列保存。若基础解释器仍有初始 console、完整身份或专用 console 验证不符，必须 event0 失败退出；不再扩大 interpreter/member 白名单、不用全局事件或强停称自然。主会话 GUI 退出仍 BLOCKED，完整游戏/外机/LAN/DPI/visual 不在此次范围。
