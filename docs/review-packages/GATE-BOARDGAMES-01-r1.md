# GATE-BOARDGAMES-01 r1 — 新机基线与展示包快照补正

2026-10-21。**IMPLEMENTED / CODE_DOMAIN_REVIEWED / FULL_FAILED / NOT_AI_ACCEPTED / NOT_MERGE_READY / STOP_AFTER_DELIVERY**。
[Task v1](../task-packages/GATE-BOARDGAMES-01.md)；base `84444b5aea305f1d179b2f07c9ace132fa78071b`；
分支 `fix/gate-boardgames-20261021`。只改runner源码收集和新回归，应用/依赖字节不变。
独立只读审查gate_review完成Task/实际diff/RED/领域/full原始证据终核，0 MUST；未参与实现或启动第二套测试。

## 环境与命令

DESKTOP-S0Q0M83 / Windows10 19045 / pwsh7.6.7 / Python3.14.5 / Tk8.6。
官方完整ZIP按发布manifest核对SHA256，在项目ignored目录解压；`.venv`使用仓库锁定依赖，
`pip check`无broken requirements。系统3.13.5/系统PATH/注册表保持；没有系统软件安装。

所有测试由 `D:\project\321_FISH\.venv\Scripts\python.exe run.py test-all ...` 执行，
每文件新进程、合成profile、loopback、Tk私有桌面；没有启用visual/hardware或运行旧smoke。
公开证据在 [本任务目录](../review-assets/GATE-BOARDGAMES-01/)，保留原失败，不重试覆盖。

| 阶段 | 文件/结果 | 命令末尾 | 原run目录（`_tmp_gui/test-gate/`下） |
| --- | --- | --- | --- |
| 干净主干基线 | 5文件26P/3F/0S，exit1 | test_boardgame_asset_img、game_shell_wiring、game_shell_pal、gameui_compact_gui、rooms，--label local-baseline-20261021 | local-baseline-20261021-20261021-103603-da0a1705dc |
| 新回归RED | 1文件4F，exit1 | tests/test_gate_boardgames.py --label gate-boardgames-red | gate-boardgames-red-20261021-103840-6ff2fee53d |
| 修复领域 | 10文件79P/0F/0S，exit0，34.467秒 | 上述5文件+test_gate_boardgames、test_test_gate、test_test_gate_safety、test_game_packages、test_azul_package_assets，--label gate-boardgames-domain | gate-boardgames-domain-20261021-103925-e788d08cd2 |

领域source_content_id：`1772c5a70fc8a8b8d1c3c050f046a1edd087da581813c3eeeea0f0a4f8e9acc8`。
基线真实缺包导致Azul通用绘制/ModuleNotFoundError；补包后原测试6项全部实际PASS，非skip。
新4case使用真实Git index和子门禁，覆盖tracked/untracked包导入、嵌套素材逐字节/sha256，
模块/素材变动时resume exit2并保持已完成summary/log原字节；敏感prefs/history/private-key/cache排除。
合成素材只验证资源读取，不声称图像解码；真实渲染由现有Tk测试验证。

## 实现与边界

`test_gate.py`只在原允许包加入boardgames、收集新Python与包内assets；所有项继续经过
原敏感排除、安全源路径与reparse校验，并沿原manifest/copy/fingerprint/resume路径。
既有安全8项/runner合同8项全绿；不更改默认skip、超时、网络/设备限制。
完整全量与独立终核结果见下。没有构建/EXE/物理LAN/外机/DPI/自然GUI退出证据。
旧CC/10月13日失败保持历史边界；本轮不推送、不PR、不发布、不扩房间图标草案。

## 唯一全量与终核

代码提交 `10caf9f`；完整命令：

```powershell
Set-Location D:\project\321_FISH
.\.venv\Scripts\python.exe run.py test-all --label gate-boardgames-full
```

205文件，2904 PASS / 1 FAIL / 20 SKIP，exit1，756.94秒。无重试、无resume覆盖，默认visual/hardware保持关闭。
run：`D:\project\321_FISH\_tmp_gui\test-gate\gate-boardgames-full-20261021-104115-300e65f5f5`。
source_content_id：`1772c5a70fc8a8b8d1c3c050f046a1edd087da581813c3eeeea0f0a4f8e9acc8`，482输入；与领域/当前工作树逐hash一致。
full-summary SHA256：`156fffc0934ae6cc527b3c22b7307e91513cac22a340f714b9ff5c5a5ef1b2f5`。
[完整原summary](../review-assets/GATE-BOARDGAMES-01/full-summary.json) / [后验检查](../review-assets/GATE-BOARDGAMES-01/verification.json)。
205项全部单attempt，原raw日志逐SHA256一致、owned cleanup全部true，snapshot逐hash匹配；
没有unexpected skip。跳过分布：

- `tests/test_r45.py`：17 passed, 1 skipped in 6.92s。
- `tests/test_ux_visual_chat_shots.py`：18 skipped in 0.13s。
- `tests/test_visual_screenshot.py`：1 skipped in 0.14s。

本次全量阻碍（原失败日志已随Review公开保存）：

- `tests/test_ux_visual_chat_regressions.py`：1 failed, 12 passed in 11.90s，exit1。

具体为 `test_short_history_is_not_clipped_after_window_grows`，原测试126行要求
`app.msg_list._cum[-1] < app.msg_list.winfo_height()`，实测 `490 < 325` 为假。
这是当前同版真实Tk布局失败，根因尚未归因；没有相同环境的干净base完整对照，
不能直接称历史/环境失败，也不冒称与10月13日另一断言失败相同。该阻碍没有被重试、
放宽断言或skip掩盖；下一任务须先做窄范围同环境对照和布局测量，再决定修复层。

独立审查验证了任务边界、当前source/领域/full一致、205条原log/hash/cleanup/退出码与公开证据；
本机代码差异只有runner与新4case，应用/规则/依赖保持base字节。资料与窄gitattributes另计；
`-text -whitespace`仅保护本任务原证据，不修改应用验证行为或伪造测试结论。

代码/领域审查不替代完整通过；因full失败，本任务不得AI_ACCEPTED或记为合并候选。

## 本地交付与接续

本轮仅本地相关提交，不push/PR/merge/发布，未运行构建或真实账号/设备/LAN。
最终资料提交SHA以本分支Git log为准；源码交付始终为 `10caf9f`，后继仅文档/证据。
所有本批应用/测试/构建均已结束；测试过程owned清理true，没有待恢复测试。
恢复顺序：`D:\project\321_FISH\AGENTS.md` → `docs/AI_COMMAND_CENTER.md` → 本Task/Review → Git/实际进程。
本机新开发基线已建立；当前目录为唯一checkout，原系统Python保持，`.venv`base目录须保留。
下一建议：先就本次全量具体失败另冻窄任务；本轮不扩大功能，也不将失败归为旧基线。
