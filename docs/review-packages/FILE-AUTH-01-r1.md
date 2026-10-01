# FILE-AUTH-01 — 实现与独立审查 r1

2026-10-01（Asia/Shanghai）；对应 [Task v1](../task-packages/FILE-AUTH-01.md)。
执行状态与下一动作只见 [指挥中心](../AI_COMMAND_CENTER.md)。

一对一 REJECT、VERIFY 原来在检查接收者身份前删除传输，CANCEL 没有参与者检查。
知道 file_id 的第三方可以破坏传输并误通知发送者。现在三处都在现有锁内先取记录、
根据认证 Session.uid 检查角色，再删除；非法请求保持记录/字段/双方通知不变，合法流程保持原语义。

## 基线、实际增量与交付版本

- HEAD：`ec73118c86250e555ec455f789e27df67036b2e6`，分支 `fix/cc-01a-admin-credentials`，本机 dirty。
- 入场20M+11??共31文件，原CC-01A源/测试/依赖294项与验收ID
  `b1350db334cf981f687fd167a939c4c2e0900e2e58121883fa1621c2a4c43e01` 完全一致。
- 入场patch SHA-256：`8951cbd77cf6f8a9f79eb26fa279de0d1125f753684205ba55f5b7d5d97f0c4c`；
  入场内容集合：`655752fd62d64b384ea47db7b6fe91a1cbeb2cd205d947a09006ed62e0752cce`。
- 原31文件路径/hash与完整patch在 `_tmp_gui/file-auth01/entry.json`、`entry.patch`。
  `entry-server.py` 保存原管理员工作树；不回滚或混称其既有管理员修改为本批增量。

| 文件 | 本批变化 |
| --- | --- |
| `server.py` | 仅 `_on_file_reject`、`_on_file_verify`、`_on_file_cancel`，现有锁内 get/身份检查/pop；三函数外文本不变。 |
| `tests/test_audit_file_auth.py` | 新增18项，验证无副作用、真实参与者UID伪造header、合法继续、角色方向、同UID第二端、双方取消和未知ID。 |
| 本Task/Review、指挥中心、PROJECT_MEMORY | 冻结范围/版本/证据/唯一状态和稳定安全约束；不改其它原资料。 |

DIRECT_OK 原来已有正确sender检查；其它handlers只补回归，不修改逻辑。
REJECT/VERIFY/ACCEPT/CHUNK_ACK为receiver-only，LISTEN/DIRECT_OK/DATA为sender-only，CANCEL双方均可。
角色取记录UID与认证Session.uid，不信任header。沿用uid多端和代表端通知语义，不新增角色、字段或协议版本。
FILE_ACCEPT接收确认后发送者离线的状态阶段问题仅记录候选，未扩为整套状态机修复。

最终295项源/测试/依赖内容ID：
`df4563966335c964541410a35641ba6cf8aefcba88d7068f54432c6e172f4f80`。
算法为相对路径 → `{bytes,sha256}` 的 compact/sort_keys JSON UTF-8字节SHA-256。
完整前后manifest：`before-full-candidate.json`、`after-full-candidate.json`。
路径集合可从仓库重建：`git ls-files -- '*.py'` 加 `.python-version`、`requirements.txt`、
`requirements-dev.txt`、`tests/test_admin_credentials.py`、`tests/test_audit_file_auth.py`，共295项。

最终server+新测试相对入场的独立实现patch SHA-256：
`fd996e97a3a13e789489aa59b8edcab886a40f01175a537d76ab9f8a8166e0b8`。
新测试hash：`42688c653548f1eff17872868b77f0a714b7db7441ebae4a0fd7d61960cc1d2b`。
28个其它入场保护文件字节不变；HEAD未变、无未归类修改。本批未commit/push/PR/merge/发布。

## 验证矩阵与原始证据

环境：pwsh 7.6.5、项目`.venv` Python 3.14.5、pytest 9.1.1、Windows 11 `10.0.26200`。
只用合成账号/数据与独立basetemp，不启用真实设备或截图opt-in。
原始证据均在 `_tmp_gui/file-auth01/`；摘要和版本绑定留本报告。
本机runner不是新发布的dev.ps1入口。

| 验证 | 结果 / 真实退出码 | 原始证据 |
| --- | --- | --- |
| 最终18项测试、原入场server | 5 failed / 13 passed，exit1（预期负例） | `original-check-r3/command.json`, `result.json`, `pytest.log` |
| 同一最终18项测试、修复server | 18 passed，exit0 | `single-role-final/summary.json`及log |
| 五文件领域 | 57 passed / 0 failed / 0 skipped，五个exit0，17.15秒 | `domain/summary.json`及五log |
| 最终全量103文件 | **1286 passed / 0 failed / 2 skipped，所有exit0，350.01秒** | `final-full/summary.json`, `progress.json`及103log |

原入场负例在隔离导出运行：294项原源/依赖逐项hash匹配，server使用入场原字节，
复制同一最终新测试。完整raw证明REJECT/VERIFY/CANCEL五个非法参数项删除了记录；
当前工作树未被回滚。原红与修绿使用相同测试hash，不把原代码预期失败改写为通过。

```text
.venv/Scripts/python.exe _tmp_gui/file-auth01/run_original_probe.py original-check-r3
.venv/Scripts/python.exe _tmp_gui/file-auth01/run_gate.py --label single-role-final tests/test_audit_file_auth.py
.venv/Scripts/python.exe _tmp_gui/file-auth01/run_gate.py --label domain tests/test_client_core.py tests/test_filexfer.py tests/test_protocol.py tests/test_multisession.py tests/test_audit_server_security.py
.venv/Scripts/python.exe _tmp_gui/file-auth01/run_gate.py --label final-full
```

每文件子进程为同一解释器 `-m pytest -q -rs <test_file> --basetemp <独立目录>
-o faulthandler_timeout=60`，UTF-8日志、真实退出码/逐文件进度。原红cwd是隔离原源导出，
修绿/领域/全量cwd是项目根；原红完整command/env/hash在其command/result JSON。
完整门禁只运行一次，无resume、自动重试或受控探针。

两个skip只有`test_r45.py`需`--run-hardware`的真实摄像头、`test_visual_screenshot.py`需`--run-visual`。
R26为14 passed、R43A为7 passed、R41为21 passed；新增18项包含在全量中，不冒称另一次专项。
门禁前后295项完全一致，`final-verification.json`全部13项检查通过：文件集合/计数/真实退出码、
progress=summary、原有skip、写入边界及内容一致。
summary SHA-256：`27d9bb6ad1b32e7bd75fed04c864a99cf6a08a43d2c57fd3d1569ac6c0bc1e7e`。

领域文件分别33/7/8/5/4 passed；领域不导入新增审计文件。
领域294项输入ID `dd2ffe5b9a291f88698726cb1e6ca81dbddb2ababa8f0cdb90542e3f2765132f`，
`domain-input-verification.json`确认源/选中测试/依赖未变，可引用57项报告。

## 独立审查与修复轮次

实现代理`file_auth_impl`；只读调查/审查`file_auth_review`，未参与实现，也未继承主控实现历史。
初审接受三函数代码，提出两个必须测试项：真实合法角色UID的header防冒充、改动函数的第二端及双方取消。
第二轮补多端/双方取消，复核要求receiver-only负例具体伪造receiver UID，避免统一sender UID自然被拒绝。
最终角色化版本两项均已关闭；代码/测试候选与完整门禁证据均已完成只读独立审查。
最终独立终审（2026-10-01）：**满足Task v1，资料/实现/验证可接受，无未关闭必须修复项**。
审查代理核对103文件日志与真实退出码集合 `{0}`，独立汇总1286/0/2，确认两原有optin skip；
重算295项当前源码/测试/依赖字节/hash为0 mismatch，前后manifest/内容ID/独立patch一致，
域294项ID一致；r3原红/新绿使用同一测试版本，三handler外文本、28保护文件及HEAD不变。
本结论只绑定表列候选，不推导合并/发布、真实设备/部署或其它里程碑通过。

历史版本证据保留：

- 初17项版本hash `06d2878d115632141e7a359197d786f661697e72ca2a1c8a5a0ea6afa4df7bca`；原红5/12，修绿17。
  实现者首次`negative-before.output.txt`只是摘要，raw未落盘；主控以隔离`original-check-r1`补齐真正raw。
  修后首试与命令记录重跑均17通过，主控`single-confirm`也保存17项raw，没有失败重试取绿。
- 第二18项版本hash `c1357a5be0a5321f01cb9b2093fca27f62a88cd310eee64a6d8a381c6b957912`；
  `original-check-r2`原红5/13，`single-final`修绿18。最终r3因测试字段变化重新验证，r1/r2未覆盖。
- 初候选ID `09bb4b0d9c20309702efbe563a11ba0ed99561b484db183003d50455b356029e`及其patch/manifest保留，
  不能用其hash冒充最终版本。CC-01A原全量历史/验收结论保持原记录。

真实P2P降级环境、EXE、真实设备/部署和其它账号/群/游戏生命周期未在本批验收。
本任务终点为独立审查与必测通过，不自动启动下一候选、Goal、heartbeat或发布。
资料检查：13份启动/协作/Task/Review/记忆文档，61个相对链接有效、UTF-8可读，
`git diff --check`退出0；`doc-verification.json`另确认上述公开路径集合可重建完整295项manifest。
