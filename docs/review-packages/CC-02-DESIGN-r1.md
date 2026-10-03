# CC-02-DESIGN — 资料与边界审查证据 r1

2026-10-01（Asia/Shanghai），对应[Task v1](../task-packages/CC-02-DESIGN.md)。
执行状态、主控与下一动作只见[指挥中心](../AI_COMMAND_CENTER.md)。

## 入场核对

- HEAD/base `d07b29577a48367f887cc0c2dbf1671ed13bb326`，分支 `fix/cc-01a-admin-credentials`。
  4 个 tracked Markdown 已修改、5 个 untracked 文档文件，合计上轮 9 份路线资料；index 空。
- 已读 AGENTS、COLLABORATION、任务清单、指挥中心、接续指南、项目记忆和指定 Task/Review。
  实际 diff 与 DOC-ROADMAP-01 的资料边界一致；没有应用/测试增量，不 pull 或切分支。
- 从本机聊天工具确认旧主控“按协作方案持续开发” idle，最近两轮 completed，并留下用户当前使用的接续模板。
  旧 Goal 完成证据在 DOC-ROADMAP-01 Review；本聊天 get_goal 初始为空，随后新建本批准资料 Goal。
- 本机 automation.toml 中 `321-fish` 为 heartbeat、PAUSED、仍绑定旧主控；未修改它。
- Win32_Process 核对没有本项目 Python/pytest/run.py/server/client 进程；两个 Node 进程是旧 CUA runtime，
  不属于应用/测试，不终止无关进程。查询 shell 已结束，没有需恢复的门禁。
- 入场 352 个 Git 非 ignored 文件 hash 已保存，300 项原字节源码集合与上一轮验收 manifest 完全一致。
  index tree `0bdde55666b06103a46ecb02ba499ff4db93b0a5`，原始快照与可编辑三文件副本在 `_tmp_gui/cc02-design/entry.json`。

## 方法与事实来源

主控唯一文档写入；`identity_facts` / `persistence_facts` 只读源码与测试源码，各负责身份会话/持久数据事实。
本次不读取真实 prefs/history/server_state/audit/downloads，不实例化 Hub/Core/Prefs，不运行应用或测试。
既有 108 文件 1335/0/2 是 BATCH-R1 历史验证，未作为本次新测试结果。

## 候选材料与机械验证

已整合身份会话、17类数据归属/介质/保留表、已有修复/测试源覆盖与静态风险，给出M0/M1/M2及D1–D11。
建议送审M1逻辑退役和全端踢人；物理清理、本地/云迁移、密码并发、known资料和真实JSON恢复分别列边界。
所有选择仍需Pro/用户决定；实现Task仅draft-v1，没有READY授权。未更改应用或真实数据。

正文候选包括本Task、架构材料、实现草案和PROJECT_MEMORY四份；compact sort_keys、ensure_ascii=False UTF8 JSON
`{path:{bytes,sha256}}`的SHA256为`49fbcd01c28bb8bef3e9bbfcbd603276b26b093f488d7110ac1417502bf3e934`。
指挥中心/生成视图/本Review是流转记录，另捕获全七文件版本，避免自引用hash。

命令：`& ./.venv/Scripts/python.exe -X utf8 _tmp_gui/cc02-design/validate.py`，真实exit0。
13项检查全true，7份资料93相对链接有效，3份入场Markdown变化+4份新Markdown，HEAD/branch/index不变；
300项source不变，其余349入场文件不变，未删除入场文件；任务清单与指挥中心源区块/hash一致，git diff --check exit0。
保护清单与验证结果在`entry.json` / `verification.json`；应用测试未运行。

`cc02_docs_review`未参与材料编写，已独立核对入场版本/范围，候选冻结后从冻结Task、实际增量、源码和原始保护证据审查。
本节记录候选验证，独立终审结果见下文；资料验收与架构批准分开。

## 独立终审与交付

`cc02_docs_review`独立结论：**可接受，无必须修复项**。未写文件、未运行应用/测试。
独立重算HEAD/branch/index树与entry一致，300项source 0 mismatch，352入场仅3份Markdown变更/无删除、4份新增；
四正文ID仍`49fbcd01c28bb8bef3e9bbfcbd603276b26b093f488d7110ac1417502bf3e934`。
93相对链接有效、投影正文/hash一致、diff-check exit0；审查者直接核对源码而非只接受事实调查摘要。

已确认文档与源码相符：旧昵称/UID复用、按作者清消息、kick与全部端删号差异、最后端退群/known资料与运行资源边界、
JSON恢复的UID键、SCHED/CLOUD/ServerStore、本地目录迁移、Prefs与下载断点范围。
候选M1/M2及D1–D11仍待决定，草案明确DRAFT/未获授权；当前只通过资料审查，不表示Pro批准或R1里程碑通过。

实际限制：本批没有新应用测试；PR状态未重新查询。本地`clear_local_uid`只遍历内存缓冲，
不能证明磁盘历史、密钥或下载副本已物理擦除；资料已把逻辑清理与物理删除分开。
持久化失败、定时消息竞态、云包归属、本地迁移仍是待批准实现/验证输入，不宣称本批动态复现或修复。

`open_in_codex`已请求打开架构材料与实现草案，两次均返回queued；文件本体可通过工作区链接读取，不冒称屏幕已显示。
指挥中心与生成清单将资料批次记ACCEPTED，下一动作仅Pro方案决定/用户实现范围批准；本批无commit/push/外部消息/真实数据操作。
最终验收流转后重新生成任务清单并运行validate.py：真实exit0，13项全true、7资料99相对链接，
正文冻结ID不变、HEAD/index/source300及其它349入场文件保持。候选93链接与最终99链接分别对应审查/流转版本，不混记。
资料和检查点已交付，Goal工具已返回complete，实际1930秒（约32分钟），未设预算；本批不运行应用测试。
终点状态已回写指挥中心并同步任务清单，完整七文件版本另捕获`_tmp_gui/cc02-design/final-delivery.json`，
不把本机ignored证据当成唯一交接。后续仅等待Pro决定/用户批准实现范围，本批已结束。
