# CC-01A — 历史交付 Review Package r1

本记录对应 [迁移重建的 CC-01A Task](../task-packages/CC-01A.md) 和 COORD-01 v1。
它保存实际入场 diff、历史测试摘要、时序解释和证据缺口；CC-01A 的状态、下一动作
和是否 ACCEPTED/MERGED 只见 [AI 指挥中心](../AI_COMMAND_CENTER.md)。本批资料迁移
没有运行应用测试，也没有把本记录当作验收结论。

## 资料来源与完整度

已核对的本机资料：

- `_tmp_gui/cc01a-root/CC-01A-Review-Package.txt`：旧 Review 的需求/实现/历史结果
  摘要；它声称原始需求来自用户 Task Package，但该 Task Package 和批准原文未在
  当前工作区找到。
- `_tmp_gui/cc01a-root/run_gate.py`：逐测试文件独立进程的门禁脚本及 UTF-8 输出处理。
- `_tmp_gui/cc01a-root/admin-special/summary.json`、`full/summary.json`、
  `full-final/summary.json`、`fade-recheck/summary.json` 及相应日志：本记录可直接
  绑定的摘要证据。
- `_tmp_gui/coord-01/incoming-manifest.json` 与 `incoming-22.patch`：入场 22 文件
  的内容快照和完整 patch，详见 [CC-01A 入场基线](CC-01A-baseline.md)。

原始 Task Package 缺失，所以需求部分是旧 Review 的重建摘要，不是对原批准文字的
伪造。下列缺口保持显式：110 passed 专项没有对应 summary/命令日志；py_compile 和
旧 `git diff --check` 只有 Review 文字声明；R26 独立 14 passed 没有可索引的原始
复测日志；历史门禁日志没有记录当时内容 hash，不能直接声称绑定本次入场 patch；
没有相同命令/环境的干净 main 对照；完整历史命令行和 Python/OS/pytest 版本没有保留。

## 实际 diff 范围

入场 base/head 均为 `fbdd915e8fd5947e01b6f4d371b3cd1e37020729`，分支为
`fix/cc-01a-admin-credentials`，dirty 入场为 20 个 tracked 修改和 2 个 untracked
文件。`diff-stat.txt` 记录完整差异为 **22 files changed, 904 insertions(+),
142 deletions(-)**；未提交、未 push、未创建 PR、未 merge、未发布。

按实际差异的功能范围归类如下，路径和入场字节/hash 见 [基线表](CC-01A-baseline.md)：

| 类别 | 文件 | 实际变化摘要 |
| --- | --- | --- |
| 配置/服务器 | `config.py`, `server.py` | 从部署环境读取管理员密码/昵称；缺失或空密码 fail closed；昵称配置校验与保留标识；认证成功后才授予 `is_admin`；拒绝普通密码接口修改部署凭据；Web token 绑定活跃 Web Session 并在注销/删号时撤销；日志使用已认证操作者昵称。 |
| Web/客户端/协议 | `web.py`, `client.py`, `client_core.py`, `protocol.py` | 去除固定管理员标识文案；客户端权限标识注明由服务器授予；协议注释改为部署侧凭据/服务器校验，`PROTOCOL_VERSION` 未变。 |
| 测试 | `tests/test_admin_credentials.py`, `tests/test_r53.py`, `tests/test_r54.py`, `tests/test_admin_groups.py`, `tests/test_admin_groups_web.py`, `tests/test_invis.py`, `tests/test_audit_server_security.py` | 新增凭据配置、TCP/HTTP、token、普通路径和 secret 脱敏覆盖；既有管理员、群、隐身和审计断言随认证方式更新。 |
| 文档/技能 | `docs/管理员凭据与公开仓库安全.md`, `README.md`, `COLLABORATION.md`, `INVITE_FRIEND.md`, `PROJECT_MEMORY.md`, `docs/任务清单.md`, `.agents/skills/fish-assistant-dev/SKILL.md`, `.agents/skills/fish-assistant-dev/references/invariants.md`, `.agents/skills/fish-assistant-dev/references/project-map.md` | 旧 Review 声称的配套文档/技能差异：补充部署侧凭据和公开仓库边界，纠正固定口令/管理员标识说明及历史索引；原批准文本缺失，不能证明这 9 个文件逐文件获批。 |

旧 Review 将这 22 个文件归入管理员交付，其中 9 个文档/技能文件只是其声称的配套
范围；原批准文本缺失，不能把它们逐文件视为已批准需求。`PROJECT_MEMORY.md` 同时
包含其它历史主题，不能仅凭它的文字把 Excel、登录窗或其它历史数字归入 CC-01A。
`COLLABORATION.md` 与 `PROJECT_MEMORY.md` 的 COORD-01 文档增量另行记录，不改写
本 CC-01A 入场快照。

## 历史验证命令、环境与结果

以下是原有交付的历史证据，不能当作本次文档迁移的新测试。`run_gate.py` 的脚本
明确了每个文件的实际子进程命令模板：

```text
<sys.executable> -m pytest -q -rs <tests/test_*.py> --basetemp <fresh-temp> -o faulthandler_timeout=60
```

每个文件在仓库根目录独立运行，环境复制自父进程并设置
`PYTHONIOENCODING=utf-8`；标准输出/错误以 UTF-8、`errors="replace"` 记录，单文件
超时为 240 秒，退出码写入 `progress.json`/`summary.json`。原始 shell 启动命令、
文件参数顺序和当时 `sys.executable` 路径没有保存，因此上面的模板不是对完整命令
行的伪造。指挥中心记录该工作区为 Windows、PowerShell 7、`.venv` Python 3.14.5；
历史 summary 没有记录完整 OS/Python/pytest 版本，项目依赖文档不能替代运行环境证明。

### 有 summary 可直接核对的结果

| 资料标签 | 文件数 | 结果 | 退出 | 用时 | 失败/说明 |
| --- | ---: | --- | ---: | ---: | --- |
| `admin-special/summary.json` | 7 | 74 passed / 0 failed / 0 skipped | 0 | 47.08 s | `test_admin_credentials.py` 24、`test_r53.py` 12、`test_r54.py` 8、`test_admin_groups.py` 14、`test_admin_groups_web.py` 8、`test_invis.py` 4、`test_audit_server_security.py` 4；对应日志存在。 |
| `full/summary.json` | 102 | 1266 passed / 1 failed / 3 skipped | 1 | 464.86 s | `test_r43a.py::test_fade_in_updates_during`：1 failed、6 passed。 |
| `full-final/summary.json` | 102 | 1267 passed / 1 failed / 2 skipped | 1 | 317.45 s | `test_r26.py::test_channel_create_kind_and_readonly`：1 failed、13 passed；该失败条目由恢复日志重建，条目 `seconds` 缺失。 |
| `fade-recheck/summary.json` | 1 | 7 passed / 0 failed / 0 skipped | 0 | 13.66 s | `test_r43a.py` 独立复测摘要可直接核对。 |

两轮全量均退出 1，不能标全绿。首轮摘要中 `test_r26.py` 为 14 passed，`test_r41.py`
为 20 passed / 1 skipped，`test_r43a.py` 为 1 failed / 6 passed；最终摘要中 `test_r26.py`
为 1 failed / 13 passed，`test_r41.py` 为 21 passed，`test_r43a.py` 为 7 passed。
首轮 `test_r41.py` 的 `full/test_r41.log` 只保留 `20 passed, 1 skipped`，没有保留
`SKIPPED` 原因，故该 skip 原因待确认，不能据源码推测。首轮另外两个 skip 对应
`test_r45.py` 和 `test_visual_screenshot.py`；最终日志明确分别需要显式启用
`--run-hardware` 与 `--run-visual`。这些历史 skip 没有被迁移资料改写成通过。

旧 Review 另外声明有“账号/聊天/Web 安全/多端/加密/协议专项 110 passed”。当前
目录没有该专项的独立 summary 或命令日志，所以这里只保留为未绑定的历史声明，不能
按本表的 74 passed 或全量结果重新推导。

旧 Review 还声明 6 个源码文件加 7 个测试文件 `py_compile` 通过，以及 `git diff
--check` 通过；当前仅找到 Review 文本和 `diff-check.stderr.log` 的换行告警，没有
完整命令、退出码或版本绑定，故不把它们列作可独立核验的新增结果。

## 两轮全量的时序与复测解释

复验过程中，临时门禁脚本在打印失败日志时遇到 Windows 默认 GBK 输出异常；脚本
随后采用 UTF-8 输出/子进程编码并以 `--resume` 继续。旧 Review 记录前 51 个文件
已有真实退出状态，恢复后完成剩余 51 个；`full-final/summary.json` 仍保留 R26
失败，未用恢复动作抹掉失败。原始 shell 命令和异常完整堆栈没有被保存，因此这段
时序是 Review + 脚本/summary 的交叉说明，不是可重放的完整日志证明。

R43A 的首轮失败仅发生在本次改动未触及的 `test_r43a.py`，旧 Review 报告可能是
首次窗口映射后错过 90ms 淡入中间帧；`fade-recheck` 随后 7 passed。R26 的最终失败
日志显示测试在收到 `group_state` 后立即读取由后续 `group_list` 创建的摘要，旧 Review
据此报告存在异步等待竞态；旧 Review 声称独立复测 14 passed，但没有对应原始日志
索引，不能把它当作本表的直接证据。两种解释都是时序假设，不是已完成的根因修复。

没有在同一命令、同一环境对干净 `main`/base 运行对照；因此不能把 R43A 或 R26 的
失败归因于 CC-01A patch，也不能宣称它们是基线既有失败。测试文件和相关实现未在
CC-01A diff 中修改这一事实只说明范围，不能替代对照运行。

## 敏感资料与证据绑定限制

本 Review 只记录环境变量名、非秘密的配置边界、路径、计数和哈希；不迁移历史固定
密码、实际 token、私有聊天全文、prefs、审计/运行状态、下载内容或 TLS 私钥。原始
patch、日志和测试 basetemp 仍留在 ignored 本机目录，不能作为公开仓库唯一状态来源。

入场 patch SHA-256、内容集合 ID 和 22 文件逐项 hash 见 [CC-01A-baseline](CC-01A-baseline.md)。
原有 22 文件的历史测试日志没有内嵌这个新内容 ID；历史日志没有当时内容 hash，故
patch/hash 只能证明保存的快照和 patch 字节，不能把任何历史测试自动绑定到它们。原始
CC-01A 批准文本、110 专项原始记录、py_compile/
diff-check 完整命令、R26 独立复测日志、完整历史环境和 clean-main 对照均待补；这些
缺口不扩大需求，也不产生 CC-01A 通过结论。
