# EXE-LOCAL-01 v1 三产物独立归档审查

审查者 purchase_review（GPT-6.1 Sol），2026-10-13。限定构建/归档收集审查 **0 MUST**；运行、自然退出、EXE 游戏对局及发布尚不在本结论内。本审查未启动应用、Tk、测试、构建、服务或下载，未修改源码、治理或公共证据。

## 来源与方法

交付 HEAD `9803303f916b93be10a9e27239cd99583d007661`；受测代码 merge `6c8bdf715cbbd544610d2edb5a97e1daed9d19d4`。410 输入清单的实际重新计算 source_content_id 为 `13514b5d70d6e92a39f9eadd8f20ae39562d3e80570437b26f6e4ea0a2164345`，与 bind、SYNC full 清单一致；410 个当前 worktree 文件仍与原 hash/size 一致。

使用本项目已安装 PyInstaller 的 CArchiveReader/PYZ reader读取三份 EXE，unmarshal 为代码对象后核目录和常量。只 compile 原源码作比较、AST literal_eval 读取素材字典并用 Pillow 解码 PNG，**没有 exec/import 包内或项目模块**。代码结构比较包含嵌套代码、字节码、全部常量、名称及行表等，仅排除构建改写的 filename。完整逐项记录见同目录 `artifact-proof.json`；其 errors 为空。

独立副本：`builds/build-20261013-035610-53ac3e03a4/source`。410 原输入中仅生成的 `client.spec`、`server.spec` 字节变化；其余 408 项保持，`app.ico`虽重新生成但字节与原输入相同。StartTrial 新 spec 在副本 `_tmp_gui/entry-spec/StartTrial.spec`，单列生成资料，未改原 worktree。

## 实际产物

| 产物 | 字节数 | SHA256 | 实际项目模块代码对象核验 |
| --- | ---: | --- | ---: |
| server.exe | 25363867 | `4578d79266e3df0fef0c77142c138c1442569f00ed008631987306afbd61c463` | 76/76 相同 |
| client.exe | 27003706 | `dcd25aa52963f9e87723eefc49c53cc08fb8ec2fed67425b9c85126f9d1ce5f4` | 123/123 相同 |
| StartTrial.exe | 9737941 | `6fcf35bb164eee9f76a5725623e27b77c447bb261e4b9f8026e32f1fb39473cf` | 2/2 相同 |

三份实际文件 hash/size 均等于 build-summary 原记录；此外 `server`、`client`、`friend_trial_start` 三个主入口脚本代码对象各自与副本源码相同。

- client 实际 PYZ 含 `_art_boardgame`、`ui_design`、`widgets.design_controls`、`widgets.msg_list`、`client_gameui`、`PIL.Image`、`PIL.ImageTk`；其 Tcl/Tk、_tkinter、PIL _imagingtk、python314.dll 二进制依赖实际在归档中。
- server 实际含 `web`、`ui_design`、`games_pkg.gemcity` 等所核源模块。
- StartTrial 实际含 `friend_trial_process`、`test_sandbox`、`ctypes`、`ctypes.wintypes`，并有 `_ctypes.pyd`、python314.dll；两项目 helper 的全部代码结构与原源码一致，包括 Job/继承句柄及 Assign-before-Resume 实现。
- 请求中 `widgets.boardgame_assets`、`widgets.boardgame_asset_img` 不是此候选源码模块，两文件均不存在；实际运行素材模块是 `_art_boardgame`，实际解码/缓存 helper 在 `client_gameui`。此名称差异不能写成缺失已存在的依赖，也不能宣称这些模块已收集。

client 归档 `_art_boardgame` 的完整代码对象与源码一致，包含 **26** 个 PNG data URL 常量，逐个与源码内嵌 URL 完全相同。26 个内嵌 PNG 与副本对应原 PNG **尺寸及 RGBA 像素全部相同**；PNG 压缩文件字节 0/26 相同，不能写成 PNG 原文件 hash 相同。三 EXE 均未收集外部 `assets/boardgame/*.png` 数据条目；client 采用上述内嵌常量，不依赖外部 PNG 查找。原 PNG 的 26 项输入 hash 仍保持。

## 构建原证据与边界

双 EXE build 与 StartTrial 原 command/summary exit 均为 0。实际 `build.log` SHA 为 `651ad17b747a78e2c46ebc56f6d8c6b8b3ad0612e111bc4fe510b14589e7066e`，`entry-build.log` 为 `b4573f99e08130672c883fac041149cbdb76007e975c39c5f9c8a8594ccc1111`，均与记录一致。外层 `build-console.log` SHA `5eecac63f56b5a585725c899d5f4903c2773c9d18d845280da82007ef26c4508` 也匹配 command 记录。

生成的 server/client spec 以副本 app.ico 为图标，无上游作者绝对 Vosk 路径/collect_all('vosk')；client console=false，server/StartTrial console=true，均 onefile 构建合同。Vosk 和模型的缺失警告及 client warn 中 `missing module named vosk` 原文保留；实际归档无 vosk 模块或 models/vosk 数据。其缺失符合冻结可选合同，转写仍未验，不能声称随包可用。

本机构建/归档一致性不能证明非开发 Windows、真实 LAN、最终视觉/DPI、完整 EXE 游戏、主会话自然退出或服务态自然退出。上游房间图标强引用缺口、危险 visual 模式禁用及历史 Tcl after 诊断保持后继边界。

## root 运行 helper 的有限安全预审

另实读 `_tmp_gui/advance-20261013/runtime_exe_local.py`：有限执行安全 **0 MUST**。任务自有 launcher 仅替换函数名及原 NUL stdin 为 `0\n\n` 输入文件，保留原 Job flags、继承句柄白名单、Assign-before-Resume；无产品退出钩子。WM_CLOSE 从自有 desktop 枚举、当前 Job 成员及 expected client image 识别唯一可见 TkTopLevel/title，发送前重新枚举逐字段重核；没有全局输入、截图或控制台广播。

自然 case 先观察 poll 0 与 Job active=0 再清理；compiled demo 之后仅 owned Job 强停，明确 exit 124/不自然。主会话 quit_app 和服务 Ctrl+C 未验。helper 的 cleanup 断言失败会中止并须保存原异常，不可将已完成子项记为全部接受。本报告只审 helper 代码，未执行它；运行原证据到达后另作终核。
