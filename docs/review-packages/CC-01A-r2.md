# CC-01A 最终验收补正 Review Package r2

日期：2026-10-01（Asia/Shanghai）。批准依据是用户新下达的
[CC-01A-FIX-01 v1](../task-packages/CC-01A-FIX-01.md)；本记录补充
[历史 r1](CC-01A-r1.md)，不抹掉其中的失败和证据缺口。
执行状态及下一动作只见 [指挥中心](../AI_COMMAND_CENTER.md)。

## CC-01A 修改范围与本次增量

原 CC-01A 是公开仓库管理员认证整改：部署侧凭据、缺失配置 fail closed、
保留管理员登录标识、TCP/Web 管理员认证与权限消费、对应测试和公开仓库安全文档。
原交付 22 文件的不可变入场记录见 [基线表](CC-01A-baseline.md)。
范围依据是本聊天用户提供的原正式 CC-01A 包：明确列出管理员认证、凭据配置、
相关测试与公开仓库安全文档，并要求检查 TCP/Web/session/token 认证路径。
r1 在 COORD-01 迁移时记录的工作区内原包缺失仍是历史事实，不将重建文档假装为原文。

| 原范围 | 实际变更 | 排除的扩展 |
| --- | --- | --- |
| `config.py`、`server.py` | 环境配置与密码回退移除、管理员标识校验、部署凭据改密边界、Web token 的认证会话绑定/失效、非 secret 启动提示与操作者日志 | 不重写账号系统，不改 UID 分配、跨端数据模型、群/游戏业务 |
| `web.py`、`client.py` | 管理员面板固定昵称文案纠偏 | 不重设计 UI，不改游戏界面或 Web 协议 |
| `client_core.py`、`protocol.py` | 管理员权限来源注释纠偏 | 不改收包业务、消息字段或线格式；`PROTOCOL_VERSION=1` |
| 原 7 个认证/管理员测试文件 | 显式随机测试凭据、认证/权限/token/secret 回归 | 不删、skip 或弱化既有行为断言 |
| 原 9 个文档/技能文件 | 公开仓库安全前提、部署与升级说明及技术索引 | 不批准 Roadmap 或发布动作；COORD-01 后续资料改动单列 |

本次唯一代码增量是 `tests/test_r26.py`：显式等待目标 `gid/kind` 的 `group_list`，
保留频道只读拒绝、创建者正常发送、普通群正常发送等断言。频道和普通群两条同类
测试均修复创建者/成员等待条件，没有固定 sleep、skip、自动重试或放宽断言。
**没有修改 R26 业务，也没有修改 R43A 测试/动画业务。**

独立本地提交：`ec73118c86250e555ec455f789e27df67036b2e6`，
`test: 修复 R26 群列表事件等待竞态`；只含 `tests/test_r26.py`，24 插入/2 删除。
未提交的 CC-01A、COORD-01 与本次补正资料没有混入该提交；未 push/PR/merge/发布。

## 为什么 Web token 生命周期属于 CC-01A

原批准目标明确要求检查 TCP/Web/session/token 的管理员认证路径，并验证普通用户
不能越权、正确管理员能消费权限。token 是 `/api/admin`、`whoami`、SSE 和 REST
取得服务器认证会话的凭据，登录校验不能脱离这个权限消费入口来单独验收。

旧路径为 `token -> uid -> sessions[uid]`。`sessions` 是最近登录的代表会话，
同账号再登录 TCP 后，原 Web token 会解析到 TCP 会话；服务器注销原 Web 会话而
其它端仍在线时，旧 token 仍可能借代表会话继续使用。这既破坏原 Web 队列/SSE
对象语义，也使被注销认证会话的凭据没有随该会话撤销。

整改限定为已有认证路径：`token -> 原已认证 Web Session`；解析验证活性，注销
该 Session 撤销其 token，删号撤销该 uid 的全部端/token。管理员权限仍由原有
服务器 `Session.is_admin` 判断，没有增加角色、重写注册/账户模型或改变协议。
共享鉴权入口对普通 Web 用户同样适用，是修复同一个认证机制；不能仅为管理员
另建一套相互矛盾的 token 语义。

本次没有实现显式 Web logout、持久 token、热轮换、云账号或完整多端生命周期。
浏览器关闭/SSE 断开仍只 detach，Session 沿用闲置清理。也没有声称已证明普通用户
能通过旧 token 直接升级为管理员：修复的是认证对象绑定及撤销边界，不夸大漏洞。

## R26 归因与最小修复

失败点是原测试等待 `group_state` 后立即读取 `a.groups[gid]`。
`Hub._on_group_create` 先发送 `group_state`，再广播 `group_list`；客户端
`_on_group_state` 对尚不存在的摘要不创建 `self.groups[gid]`，随后处理
`group_list` 才创建该摘要，且更新完成后才通知 Collector。
因此测试必须等待列表事件，而不能把收到成员状态等同于列表已更新。

AST 比较确认 `_on_group_create`、`_on_group_join`、`_send_group_state`、
`_broadcast_group_list`、`ClientCore._on_group_state` 在干净 `fbdd915`、
CC-01A 修复前导出与当前候选三侧完全相同。原 R26 测试本身在 CC-01A 中也未变。
R26 使用 TCP `ClientCore`，不经过 Web token 解析。静态证据只是范围说明，归因还
由下面同环境动态对照补足。

环境：同一 `.venv/Scripts/python.exe`，Python 3.14.5、pytest 9.1.1，
Windows 11 `10.0.26200`。基线为 `git archive` 导出的完整 tracked 源码
`fbdd915e8fd5947e01b6f4d371b3cd1e37020729`；没有用户运行状态或部署配置复制。
修复前 CC 导出在相同基线覆盖原候选变更，R26 原文件保持与基线完全相同。

| 对照 | 结果 | 退出码 |
| --- | --- | ---: |
| 干净基线、原测试、自然完整 R26 | 14 passed | 0 |
| CC-01A 原候选、原测试、自然完整 R26 | 14 passed | 0 |
| 干净基线、原测试、受控事件间隙 | 1 failed，原位置 `KeyError: 1` | 1（预期负例） |
| CC-01A 原候选、原测试、同一受控间隙 | 1 failed，原位置 `KeyError: 1` | 1（预期负例） |
| 干净基线、仅覆盖修复测试、同一间隙 | 1 passed | 0 |
| CC-01A 候选、修复测试、同一间隙 | 1 passed | 0 |

受控探针只在测试进程 monkeypatch：状态已发送后用 Event 暂缓第一次频道
`group_list`，测试明确等待列表时释放。payload、群状态、权限及协议均不变，
不使用时间性 sleep/重试。它代表允许发生的网络/线程交错，不声称自然运行必然失败。
两边原测试同样失败、修复测试同样成功，结合未变的业务路径，确认是既有测试等待
竞态，**不是 CC-01A 引入的 R26 业务回归**。

## 命令、版本与证据

自然对照命令（不同源码 cwd，使用同一解释器，每次独立 basetemp）：

```text
D:/Project/321_FISH/.venv/Scripts/python.exe -m pytest -q -rs tests/test_r26.py --basetemp <独立目录> -o faulthandler_timeout=60
```

受控对照将目标收窄为
`tests/test_r26.py::test_channel_create_kind_and_readonly`，增加 `-p race_gate`，
两边均使用同一 `PYTHONPATH=<证据目录>`；探针只用于归因，不加载到最终门禁。
完整对照的命令、cwd、真实退出码、测试 hash 和输出摘要固定在
`_tmp_gui/cc01a-fix01/r26-comparison.json`；探针与运行程序位于同目录，
静态方法 hash 记录为 `r26-business-ast.json`。六份原始日志保留，不把预期负例写成通过。

最终候选标识：测试独立提交 `ec73118` + 未提交 CC-01A 业务；源/测试/依赖内容 ID
`b1350db334cf981f687fd167a939c4c2e0900e2e58121883fa1621c2a4c43e01`。
完整 manifest、解释器/OS/pytest、门禁脚本 hash 与启动命令保存于
`_tmp_gui/cc01a-fix01/final-candidate.json`。

最终门禁命令：

```text
pwsh: & ./.venv/Scripts/python.exe _tmp_gui/cc01a-fix01/run_full_gate.py --label final-full
```

每文件子进程固定为 `python -m pytest -q -rs <文件> --basetemp <独立目录>
-o faulthandler_timeout=60`；102 个文件逐个执行，UTF-8 输出、真实退出码及逐文件
进度保存。没有自动重试，没有受控探针或新增 skip。活动门禁开始后的代码内容
必须与上述 ID 保持相同，否则结果不能沿用。

## 最终全量状态

本次最终逐文件门禁：**102 文件，1268 passed / 0 failed / 2 skipped，退出码 0**，
耗时 388.64 秒。102 个文件进程的真实退出码均为 0；两个 skip 是原有显式启用项：
`test_r45.py` 的真实摄像头测试需要 `--run-hardware`，
`test_visual_screenshot.py` 需要 `--run-visual`。没有新增 skip 或自动重试。

R26 完整文件 14 passed；R43A 7 passed；R41 21 passed，未出现新的 Tk 初始化 skip。
从本次完整门禁中提取的原 7 文件管理员/安全集共 74 passed（含新增凭据文件 24），
此处明确是全量中的子集，不伪称另跑了一次专项命令。

门禁结束后复算完整源/测试/依赖 manifest，与开始时的内容 ID 完全相同；
`final-verification.json` 固定这一复核、102 个真实退出码及 summary 的 SHA-256。
原始完整结果位于 `_tmp_gui/cc01a-fix01/final-full/summary.json`。
`py_compile tests/test_r26.py` 与 `git diff --check` 退出 0。

历史 r1 的两轮退出 1 保留，**本次新候选全量通过不追溯改写旧候选结果**。
真实摄像头/截图、发布 EXE 和实际部署未在本任务执行；应用代码仍为未提交候选，
因此验收须结合测试独立提交、CC-01A 差异和上述内容 ID，不能只看 `ec73118`。

## 独立审查

`auth_path_review` 已核对六组原始对照、相同方法/文件 hash、探针的测试侧边界和
实际测试 diff，可接受既有竞态归因及仅测试修复。最终终审另行复核全部 102 文件
真实退出码、两个原有 opt-in skip、候选内容不变、测试独立提交和本报告，结论为：
**CC-01A-FIX-01 满足用户三项补正要求，无未关闭必须修复项，可接受。**
CC-01A 父任务仍保留待最终审核安排，本记录不冒认 Pro 已完成 CC-01A/R0 里程碑验收。
