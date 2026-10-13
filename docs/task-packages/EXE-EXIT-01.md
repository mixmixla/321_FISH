# EXE-EXIT-01 v1.3：当版服务自然 Ctrl+C 与主会话退出边界

状态：AI_ACCEPTED_SERVICE_EXIT_ONLY / MAIN_GUI_BLOCKED（2026-10-13 冻结与有限交付）。来源：父线程授权复用 source9803303 三 EXE，先真实主会话退出/服务 Ctrl+C，再一个修改游戏；本有限自然阶段只完成退出可安全执行部分，不重复构建/入口用例。

## 固定版本与归属

文档基线 f71438aedb229a509f741a4823bfc84ab552e5a0；受测代码 6c8bdf715cbbd544610d2edb5a97e1daed9d19d4，产物绑定 9803303f916b93be10a9e27239cd99583d007661，source_content_id 13514b5d70d6e92a39f9eadd8f20ae39562d3e80570437b26f6e4ea0a2164345 / 410 输入。原 .venv/Python3.14.5，三产物只核 hash 不重建：server 4578d79266e3df0fef0c77142c138c1442569f00ed008631987306afbd61c463；client dcd25aa52963f9e87723eefc49c53cc08fb8ec2fed67425b9c85126f9d1ce5f4；StartTrial 6fcf35bb164eee9f76a5725623e27b77c447bb261e4b9f8026e32f1fb39473cf。

root 是唯一启动进程/测试/治理写入者。代理只读 Task、实际辅助程序和原证据，不启动应用或正式门禁。本任务只修改新 Task/Review/evidence、指挥中心与路线投影，以及仅独立工作树 .gitattributes 的本 Task 原日志出版规则；生产/测试/依赖/PROJECT_MEMORY 不改。原 c864234 dirty/index/1143 保护文件保持，独立工作树 fix/gemcity-purchase-20261013。v1.1 执行前冻结合成原日志窄 -text/-whitespace 出版，其余源/测试/文档检查保持。v1.2 保留首轮 FAIL/exit1/event0/owned清理124/Job0，只修 stdlib-only sender 选择该 .venv 已核 sys._base_executable（pyvenv.cfg home/executable/version对应同一3.14.5；pin SHA256 3adbbf2af609e206e3ca18cd55fc7c4b52f5c8bb8218dd99fd5a9e50d7a193cd，-E -S -B且sender-only清除__PYVENV_LAUNCHER__），避免 venv redirector flags0 再创子console；root和所有项目构建/测试仍 .venv，产品/EXE完全不改，不切其它项目环境。新复核runtime-recheck/newprofile/nonce，仅一次额外执行，经新helper独立预审后才启动；仍坚持初始无console，不FreeConsole已有console，不降格归属/自然验收。首轮三helper执行原快照/hash与三raw永久保留。

## 冻结范围与验收

v1.3 决定来源仍为父线程已授权本机自然退出与本轮主控有限自治。v1.2那一次复核已终止FAIL/event0/无permit、服务与sender仅124清理/最终Job0，原资料不覆盖；原初始无console问题已按same-base闭合。仅纠正 HWND 元数据合同：GetConsoleWindow保证associated HWND，不保证其owner是conhost；实际owner为已核server父。新native字段名 window_owner_identity，必须为当前fresh服务Job成员、逐image/birth/session与owner的完整Job核对一致，仅exactserver或System32/conhost，hidden/exact private不变；全console信号成员仍严格sender+actualserver父子，完整列表/nonce/发送前复查不放宽。实际backend身份分账记UNDETERMINED，known owned conhost仅console helper候选，不声称已证明pseudoconsole。READY仅准备/独立预审这一元数据修订，然后允许一个 runtime-final/newprofile/nonce 的最终有限确认（本阶段最多3 runs，不再递归复核）。无源/依赖/EXE改动，前两FAIL/六raw/各自执行快照永久保留。

1. 主会话真正“退出”：WM_CLOSE 是 hide，不算通过。当前 native Computer Use 不可用；没有安全可识别真实退出控件时 BLOCKED，不猜坐标、不通过应用注入调用 quit_app、不替换自然退出为强停。本 Task 不使用自制截图/鼠标 fallback，不抓默认 desktop 或操作其他窗口。
2. 服务态 Ctrl+C：fresh 合成 profile/Store、随机 loopback、专用隐藏 console/private desktop、先挂入 owned KILL_ON_JOB_CLOSE Job 再恢复。Task-only launcher 创建标志 NEW_CONSOLE+SUSPENDED+UNICODE+EXTENDED，不含 NO_WINDOW/NEW_GROUP。DETACHED sender 自己附着该 owned server PID；root 不 detach 控制台，不附着父控制台。只继承 NUL/日志句柄，不继承 Job 句柄。
3. sender/owner nonce 许可协议：sender 完整动态扩容 GetConsoleProcessList，owner 完整动态扩容 Job PID 清单，并核 image/creation time/当前运行归属。发送前再次核控制台成员集合必须一致、包含服务器父子且除 sender 外全部在 fresh server Job 中；任何未知成员、错误、可见/归属不明 console 或超时立即失败。sender 附着后仅忽略自己 Ctrl+C；只发一次 GenerateConsoleCtrlEvent(CTRL_C_EVENT,0)，最终自行 detach。
4. 自然通过必须服务就绪且实际 TCP/HTTP 可访问，真实 server 退出0、owned Job0、sender自然退出0且detach、loopback两端口关闭、合成 Store 后续 inspect 正常；全部自然证据在任何 terminate/close 前取得。API 返回成功本身不代表验收。失败原样保留；owned 强停仅清理，绝不变为 PASS。OS consolehost 只记录，不直接关闭窗口或按其 PID 杀进程；失败时该 consolehost 若为本次 owned Job 成员，Job 整体清理可覆盖它，仍只记清理。
5. 后续 inspect 仅本次合成 Store，本次没有客户端游戏或真实资料。来源未变引用 SYNC 唯一 full 2441P/0F/20原opt-in，不重跑门禁或启用 --run-visual。独立实际 helper/原运行证据审查后，主控只接受完成的服务退出范围。

## 边界与停止

不构建/改产物、不发送真实消息、不外机/LAN/公司/休眠电脑/CP4/安全设置操作，不 main push/merge/Release。完整 EXE 游戏/邀请/结束/再开、主会话退出若受阻、DPI/视觉仍未验。普通任务分支资料 commit/push 已授权；PR403不重试。自然阶段结束交父线程续跑；14:30北京不新大任务、15:00前收尾。

## 官方 API 合同

[创建标志](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags)、[AttachConsole](https://learn.microsoft.com/en-us/windows/console/attachconsole)、[完整控制台成员](https://learn.microsoft.com/en-us/windows/console/getconsoleprocesslist)、[Ctrl+C 广播范围](https://learn.microsoft.com/en-us/windows/console/generateconsolectrlevent)。Ctrl+C 的 group0仅广播 sender 当前专用 console；非零 group 不能定向 Ctrl+C，故归属核验不可省略。[CPython3.14.5 venv redirector](https://raw.githubusercontent.com/python/cpython/v3.14.5/PC/venvlauncher.c) 419-420子进程flags0，与本轮sender初始console1/error0吻合；只读技术推断，不把首轮服务状态叫产品Ctrl+C失败（实际event0）。[GetConsoleWindow](https://learn.microsoft.com/en-us/windows/console/getconsolewindow)只给associated HWND，不保证owner为backend；本Task不据其hidden推断pseudoconsole。
