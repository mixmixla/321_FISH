# SYNC-LATEST-MAIN-01 v1.2 独立最终审查

审查者：purchase_review（GPT-6.1 Sol）。2026-10-13。仅执行源码、原始证据与归档的独立核查；本次未启动测试、Tk、构建、素材生成器，也未修改源码、治理文件或公共证据。此文件是主控明确授权的 ignored 审查报告。

## 结论

限定 SOURCE_SYNC 合同内 **0 MUST**。证据支持 root 对本次源码整合作有限技术接受；本报告不代替 root 记录 AI_ACCEPTED，也不构成 EXE、发布、共享 main 合并、视觉或 LAN 整体验收。

候选：`6c8bdf715cbbd544610d2edb5a97e1daed9d19d4`，实际 Git parents 为本批 `2e0ae8d67cf2f31e3564226aeba0495118b9cf83` 与上游 `52d5ff00c53c2e104811048a2db55d6b53e432cc`。本次检查时源码未变化，仅后继治理/公共归档文件处于 dirty。

## 实际证据核验

- 沿用同源已完成的静态 merge 审查：本侧独有 469 路径与上游独有 61 路径保留，3 个共同核心模块完成普通 merge；本批 13 个关键函数 AST 与本侧 parent 一致，网页 Kalah 实际 GRENDER 区块保留。未把普通源码保留说成新增视觉修复。
- domain：24 文件，337 PASS / 0 FAIL / 18 上游显式 visual opt-in SKIP，exit 0，100.879 秒；此前已逐项核原始日志、公开副本、single attempt 和 cleanup。
- full：原 `full/summary.json` 与 `progress.json` 的 168 个结果一致，逐项单 attempt（attempt=1），每项 exit 0、cleanup_ok=true、artifact_error=false，sandbox report 存在，unexpected_skips 为空。顶层 failures 与 cleanup_failures 均空；逐项累加 **2441 PASS / 0 FAIL / 20 SKIP**，exit 0，820.93 秒。
- 168 份原 raw 日志实际 SHA256 等于各 result 与 attempt 的 log_sha256，均包含记录的 pytest summary。公开 `docs/review-assets/SYNC-LATEST-MAIN-01/full/logs/*.log.txt` 的 SHA256、长度及字节与原 raw 一致；公开每项 single_attempt、cleanup、exit、status、counts 同原记录，168 份全部核完。
- full/domain manifest、summary 及 full 公开 summary 均绑定 source_content_id `13514b5d70d6e92a39f9eadd8f20ae39562d3e80570437b26f6e4ea0a2164345`。410 个输入逐份核 full source snapshot、当前 worktree、domain source snapshot 的实际 SHA256 与长度（共 1230 次文件核验），另核 domain manifest 和公开 source-inputs 的 410 项路径/hash 一致。不同选测集合使 domain/full content_fingerprint 不同，source_content_id 相同，属正确边界。
- full content_fingerprint：`c4a30f6989eba0f041eca205aef4d4a9888ab00b9cf483e2018039d8c25d8d9e`。公开 tested_code_commit 为上述 merge HEAD；merge-proof 的两 parents 与 Git 实际值一致。
- skip 精确只涉及三文件：`test_r45.py` 1 项需 `--run-hardware`；`test_visual_screenshot.py` 1 项需 `--run-visual`；上游新 `test_ux_visual_chat_shots.py` 18 项需 `--run-visual`（原 raw 分组 12+3+3）。run_visual=false、run_hardware=false；无其它环境 skip。
- `test_boardgame_assets.py` 3 PASS / 0 SKIP；`test_boardgame_asset_img.py` 3 PASS / 0 SKIP。后者实际 gui=true，私有 desktop `MoyuGate-20444-0596374cbe`，不是因 Pillow/Tk 缺失跳过。
- 历史原失败文件在本 full 为 `test_cc02a_web_kick.py` 1 PASS、`test_r32.py` 26 PASS；历史 3 FAIL 原始证据仍保留。本次未使用重试覆盖历史失败。

## 保留的后继边界

- 上游新截图测试 18 项只作默认显式 SKIP；不构成视觉 PASS。门禁 `_gui_hint` 漏掉模块级 visual marker，实际该文件 gui=false / desktop=null；其截图与 Escape keybd_event 不能安全启用，仍禁止 `--run-visual`，需另冻结隔离整改任务。
- 上游已有 `_RoomCard` 图标 PhotoImage 强引用缺口经静态确认：工厂创建新 ImageTk.PhotoImage 无缓存，Label 只存 Tcl image name，房间卡片未持图片 Python 强引用；Pillow 析构删除 Tcl image，tkguard 未提供图片保活。这在上游 52 已存在，本 SYNC 原样保留，未修复且未运行现场 Tk 复现，应保留后继 UI-ROOM-ICON 任务。
- `test_flagship_gui.py` 原 raw 的 Tcl `after` invalid command name 诊断保留，虽文件测试 PASS，不能描述为无任何 GUI 诊断。
- EXE 完整游戏及自然退出、打包 Vosk 作者绝对路径的可移植性、非开发 Windows、真实 LAN、最终视觉和 DPI 均未验；本任务未构建或启动 EXE。共享 main、发布、真实用户资料均不在本结论范围。

原证据目录：`D:/Project/321_FISH/_tmp_gui/sync-main-evidence-20261013/{domain,full}`。公共归档：候选 worktree 的 `docs/review-assets/SYNC-LATEST-MAIN-01/{domain,full}`。
