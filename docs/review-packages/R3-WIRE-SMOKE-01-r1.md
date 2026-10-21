# R3-WIRE-SMOKE-01 r1 — 正式协议预检

2026-10-21：**AI_ACCEPTED_WIRE_PREFLIGHT_ONLY / FULL_PASSED / NOT_MERGED / NOT_R3_ACCEPTED**。
[Task v1.1](../task-packages/R3-WIRE-SMOKE-01.md) / [脱敏结构化证据](../review-assets/R3-WIRE-SMOKE-01/evidence.json)。root唯一实现/执行/资料写入，gate_review独立只读，普通模型/Standard；本周有界公开/正常集成许可适用，未授权发布。

## 问题与有限实现

原正式local_trial.run只核TCP/HTTP/双EXE登录和短时存活，上一批真实server.exe的聊天/两棋探针还在本地控制器，协议失败不会成为默认预检失败。基于main `13e7d21b753bbcd99de1ba81eca69eb40abf1971`，分支feature/r3-wire-smoke-20261021；代码 `93bc7cbf68027e0a9fbfa101ac5d9e3ef3d056f5`，仅local_trial.py +245行和新375行/19case测试，不改业务协议、游戏、GUI、构建、依赖、旧断言/skip/门禁，也不新增平行框架。
run startup成功后默认执行同一loopback server上的两个同步加密peer：双向唯一聊天/同seq递增，gomoku9手和connect4 7手真实终局、CREATED stateNone复位、round+1空棋盘/无winner、双方leave和列表缺房。每阶段两peer共用min(总45s截止,阶段开始+5s)，每chunk重新计算剩余绝对预算，避免trickle重置；单帧128KiB/未匹配队列128，严格room/status/round/stones/turn/winner/真实UID。显式ValueError而非可被-O去除的assert。
raw socket先持有再connect，两个peer先登记、finally逐资源关闭，即使一项关闭异常仍尝试另一项；关闭失败可见且probe失败。同步无reader线程。false/异常使正式CLI非0，startup失败NOT_RUN；既有owned Job finally保持，清理失败/源码变化优先退出规则保持。Job强制清理只证明归属释放，不等于自然应用退出。

## 红绿与同版门禁

项目.venv Python3.14.5/Tk8.6，run.py test-all逐文件源码/合成profile/loopback/必要private desktop隔离。原件仅本地 `_tmp_gui/test-gate/<run_id>`。

| 阶段 | run_id | 结果 |
| --- | --- | --- |
| 原受影响基线 | wire-baseline-20261021-182405-1446917cdd | 2文件21P/exit0 |
| 最终同字节原生产RED | wire-red-verified-20261021-184134-0f786f60b8 | 19F/exit1 |
| 最终领域 | wire-domain-verified-20261021-184139-317b7f6eab | 6文件84P0F0S/exit0/34.33s |
| 唯一默认全量 | wire-full-20261021-185108-b66afa85c5 | 211文件2958P0F20原opt-in S/exit0/774.173s |

19case含真实Hub完成流程、静默/分块握手绝对超时、重复UID、聊天超时、超长帧、途中EOF/第二握手失败、旧轮次过滤/过期buffer不接受、帧洪泛、close失败仍清另一peer及无关socket保持、无效预算不开socket，以及正式run失败/异常/startup失败的真实owned Python Job故障seam。后者不冒充EXE。trickle夹具EOF保护在最终同字节RED前修正，不弱化断言；初17F/首19F/两次前序84P原件保留，不当最终source。RED时只临时替换主控自有local_trial旧生产bytes，候选先raw备份/finally同SHA精确恢复，其它487输入同字节。
488输入source `dcf9dfb850acd8530274165b6984655ef457ccc077d438978ffe1cdacbd18757`，当前/领域/full snapshot逐hash同一；最终RED同488仅local_trial.py不同，testSHA `49197d79e8b850f70218f53f9e24af8a3da3bac15104782c8fc9786dcbf92313`。相比上一Boss full只harness改变/新增test，旧210文件counts完全保持；仅增19P。全211均单attempt、原log SHA/exit0/cleanup/sandbox/artifact已核，20skip仍r45硬件1+ux_visual_chat_shots18+visual_screenshot1；无opt-in/额外pytest参数。summary SHA `4d27c337d5abfda46d37960404cf0232106459f49e2978675fdce8d191864a42`。这些结论不代替独立终审。

## 实际EXE正负路径

复用上一批base2e21156构建三EXE，不做无关重建。旧copy运行子集483/source dc151b377bed85914754d0eb36d4e6eae38eb589257adcd564dff50498eea133与根新harness488分别绑定；旧487完整源码相比当前只有local_trial变化/新增test，业务代码不变。实际根local_trial模块路径已核，新harness直接调正式main/run，不使用旧copy里的harness。三EXE原size/hash和两个source前后保持，详结构化索引。
- 正 `run-20261021-104824-b4a59527db`：actual CLI和process均0；HTTP200、实际client.exe uid1/2审计登录，wire peer uid3/4；双向chat seq1/2，精确7步、6.191s、两socketclose。客户端/server after_wait存活和映像检查通过。
- 负 `run-20261021-104908-c495f11a57`：actual CLI和process均1；五startup均成功，随后在_wire_probe调用点明确注入TimeoutError，injection_invoked=True、wire stage exception/timed_out/error_type及正式error一致。控制器不能以任意exit1冒充预期失败。该结果仅证明故障传播，不是自然server超时。
两次各4Job before2/2/3/0→after全0、ok/close_ok全true；client/open-server是强制Job清理，仅initialize root自然0，不称完整应用自然退出。运行已结束，无活动EXE。控制器执行前及原件独立复核0 MUST；本地控制器hash是事后provenance，不是执行密码学证明。

## 独立审查与披露

设计审查要求两peer共享阶段截止、raw先登记、bounded帧/队列已落实；代码/最终RED领域0 MUST。执行前控制器曾有MUST：负路径仅凭exit1会误收startup失败，已改成startup+真实注入+异常类型/阶段硬验后才执行。夹具EOF SHOULD已修并重新做最终同字节RED/领域。实际正/负原件独立复核0 MUST。唯一full及最终文档/公开范围终审待完成；未提前AI接受。
准确9路径，所有新增文件及全部新commit history都必须审计。公开只代码、测试、项目文档及脱敏结构化结果/hash；无原日志、完整summary、profile、EXE、本机用户名、私密数据、密钥。原证据不为公开修改。

| 仓库相对路径 | 内容类别 |
| --- | --- |
| `local_trial.py` | Formal preflight wire probe; 245 added lines |
| `tests/test_local_trial_wire_smoke.py` | 19 synthetic loopback/fault/owned Job regression cases |
| `docs/task-packages/R3-WIRE-SMOKE-01.md` | Frozen scope, execution boundaries and validation checkpoint |
| `docs/review-packages/R3-WIRE-SMOKE-01-r1.md` | Reproduction, source binding, review and acceptance evidence |
| `docs/review-assets/R3-WIRE-SMOKE-01/evidence.json` | Sanitized structured results and raw evidence SHA index |
| `docs/AI_COMMAND_CENTER.md` | Authoritative current checkpoint and next priority |
| `docs/任务清单.md` | Generated roadmap projection |
| `PROJECT_MEMORY.md` | Stable default wire preflight contract |
| `.agents/skills/fish-assistant-dev/references/development.md` | Stable preflight validation guidance |

按本周许可，最终独立0 MUST后仅有限AI接受本预检；fresh fetch核main/保护/required checks，正常push/安全FF，核远端完整SHA。安全拒绝停止、不强推/绕保护/删开发分支/发布。没有可见CI不当CI PASS。实际集成状态待回执，不把计划写成完成。
完整原生GUI、自然client/open-server退出、物理LAN、多机器/其它DPI/硬件/STT、搬移包完整demo及compiled StartTrial完整demo仍未测；原生GUI工具当前无可用入口，不以OS替代输入/截图绕过。R3不升级。下一候选R3-PACKAGE-WIRE-01 DRAFT：复用同hash七文件包搬移到隔离路径、用新默认正式wire预检验证路径独立性；无需人工GUI、不重建无关代码。恢复先AI_COMMAND_CENTER/Task/Review/Git/唯一full原summary和实际进程，勿重复运行已完成全量。

## 独立最终技术接受

gate_review从最终211文件原件、原sandbox JSON、source/hash、实际EXE正负与9公开路径/全部新history独立复核0 MUST，主控据证据仅AI_ACCEPTED_WIRE_PREFLIGHT_ONLY。原阶段“待终审”是当时检查点，现已闭合。源码/依赖/测试/命令/环境冻结，纯文档接受记录不重跑full；公开审计和正常集成前再次核所有新history与fresh远端，不把接受等同已合并或R3完成。
