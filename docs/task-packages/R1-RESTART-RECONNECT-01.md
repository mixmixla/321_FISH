# R1-RESTART-RECONNECT-01 v1 — 持久服务重启后的原客户端续连

2026-10-21 READY。base/main ddf1c79b0143890a4c98941b6b5b500b6909e761；独立分支 feature/r1-restart-reconnect-20261021。本批只覆盖既有 R1/M1 客户端与服务重启一致性的一个正常停止/重开场景。不是完整异常崩溃恢复、整个 M1 退役或 R1 验收。

## 现有证据与缺口

既有 tests/test_client_core.py::test_reconnect_and_rejoin_group 用真实 socket/Hub 证明同一 Hub 断线重连；tests/test_retire_recovery_hub.py::test_completed_retirement_reopens_with_same_identity_and_truthful_origin 用真实 Store/Hub 证明重开后退役身份状态。两者尚未联结为“原 ClientCore 保持运行，服务端以同一个隔离 Store 重开并让它自动回连”的真实路径。先跑必要既有对照，不重复无关构建/EXE 或已通过全量。

## 冻结正确性条件

只在 tmp_path 合成 Store、审计和 loopback 临时端口上执行，禁用发现、硬件及外部网络，不读用户真实资料。真实 Hub+serve、真实 ClientCore/加密通道、真实 ServerStore JSON；正常关闭第一 Hub 并等到 owned 服务线程结束、持久状态确认后，在同一端口以同一 Store 新开 Hub，旧 ClientCore 自动回连。以连接 epoch、新 welcome、两 Hub 实际 UID/昵称映射判断新会话，不能用前一代缓存事件冒充。要求重连 UID 不变、不产生重复账号或 UID 计数倒退，重连后真实双端聊天可达，最终各服务线程/客户端可靠收口。使用有界事件等待，不靠任意固定 sleep 追绿。

如果真实红测揭示产品缺陷，再最小修复和受影响回归；如路径已正确，只加覆盖上述独立要求的有意义回归，不制造代码变化。检查测试数据隔离和进程所有权。领域回归后独立只读代码/证据审查，再按仓库门禁要求执行适用全量；仅通过后有限 AI 接受，不把这条测试扩大为 GUI/EXE/LAN/自然退出验收。

公开只允许代码/测试/项目文档/脱敏摘要；原始测试日志、用户名、私密数据、密钥、二进制留本地。审全部新增历史、远端保护和新改动，按本周授权正常推送、依仓库约定经 PR 合并 main；不直接 push main、不强推、不发布。2026-10-22 集成渠道澄清不改变上述正确性条件。恢复入口：AI_COMMAND_CENTER 当前段、此 Task、Review、Git refs、原始 run/summary 与实际活动进程。

## 休眠前检查点（2026-10-21）

目标/领域分别 1P/75P、独立代码复审 0 MUST；全量原 run r1-restart-reconnect-full-20261021-20261021-224241-6202d94027 人工中断，最后原进度 189/213 passed、tests/test_server.py running、无 summary，不能验收。已确认无本轮自有 test_gate/pytest/Python 进程。代码与本 Task 保持未提交；无 push/merge。明日恢复先看 AI_COMMAND_CENTER、git status、该 run 原进度和进程，再完成适用门禁与独立终审。
