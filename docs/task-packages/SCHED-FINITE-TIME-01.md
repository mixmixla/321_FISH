# SCHED-FINITE-TIME-01 v1 — 非有限定时时间不得进入持久快照

2026-10-25 READY / INDEPENDENT_DESIGN_REVIEW_0_MUST（identity_scout）。用户本轮本地可靠性开发授权，base/远端main
`41a01148f8d87464270993484c8a78f9fd9c1794`，与PREFS-INVALID-ROOT-01合并为一个有限验收批次。

## 冻结合同

`Hub._on_sched_set` 当前将合法JSON字符串 `NaN` 转为非有限float，两个时间窗口比较均不能拒绝，
因而写入scheds并回报成功。durable路径 `_persist → recovery.validate_snapshot` 拒绝该值并
触发 `_fail_store`，服务进入FAILED并置stop；无durable协调器时后果不同，不混称同一传播。

仅在输入转换阶段捕获转换溢出并拒绝非有限 `fire_at`，沿用现有 `fire_at` 错误回执。
不得加入队列、成功审计或触发该请求的持久化；原已有定时任务不变。正常有限未来时间、
现有合法数字字符串、已过期/过远校验和定时发送行为保持。不得修正坏值为当前时间或静默丢既有任务。

server_scout独立工作树唯一写入server.py该校验段和新增tests/test_sched_finite_time.py，
不改Store/recovery/Web/协议/依赖/门禁/既有测试。root持有Task/Review/中心/投影及组合验收，
identity_scout独立只读设计/代码/原始证据审查，不参与实现。root另写prefs，文件归属无交叉。

## 验证与交付

- 合成RED覆盖NaN/正负Infinity/转换溢出的巨大整数，检查错误回执及原scheds不变；保留原退出与字节。
- GREEN覆盖上述输入和有限合法值；至少一条真实新建durable Store/Hub/Session路径，拒绝后强制持久化成功、
  service_ready/stop与正常定时恢复保持。不得用mock持久化冒充durable不失效证明，测试监听仅loopback或无需监听。
- 相关定时/Store/恢复/多会话领域验证；root组合两个最终字节后唯一全量并审查，不并发两个全量。
- 独立原件/代码审查0 MUST、完整全量及公开边界检查后有限AI_ACCEPTED；正常提交快进main并非强制push。

仅新建合成数据，不读真实资料；视频4759保持暂停失败，不继承/诊断。06:12 UTC后不开大任务，06:27收尾。
不PR/强推/绕保护/发布或上传EXE/raw；完整GUI、自然退出、LAN、STT仍未验收。
