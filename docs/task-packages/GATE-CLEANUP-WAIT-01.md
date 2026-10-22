# GATE-CLEANUP-WAIT-01 v1 — 终止自有测试进程后的有界退出确认

2026-10-22 READY。来源：本轮已授权自治及R1-RESTART-RECONNECT-01完整门禁实际失败；root唯一实现，r1_review独立设计审查0 MUST。base/HEAD ddf1c79b0143890a4c98941b6b5b500b6909e761，沿用现有feature/r1-restart-reconnect-20261021，不覆盖原R1未提交测试。

原full 2971P1F20S/exit1保留，失败为timeout cleanup无法确认。源码中Popen.kill/native TerminateProcess后立即poll可能先于异步退出；原日志没有分支trace，因此不能断言历史失败已精确定因或归因权限。

只允许test_sandbox.py的DesktopProcess.terminate_tree有界等待与tests/test_test_gate_safety.py必要回归。先在合成故障替身中确定性证明终止返回不等于退出；只等待已持有Popen/进程句柄，最长10秒，随后仍校验全部原observed descendants。wait超时/异常、退出状态未知、descendant存活/未知均false；不得扩大kill范围、重用旧PID杀进程、改变权限/ACL/环境、放宽skip或既有断言。不更换现有进程管理架构。

覆盖Popen/native两种路径的delayed exit、timeout、异常、退出未知、descendant不确定；另对两种真实合成自有进程禁用taskkill成功路径以验证持有句柄的回退清理。原始失败/红测保留，修复后选测/领域、独立代码复核，再唯一新组合全量；原R1 failed全量不得resume追绿。仅通过后组合有限AI接受。不是GUI/自然退出/LAN/新EXE/R1里程碑验收。

公开仅代码/测试/项目文档/脱敏摘要，原日志与合成profile留本地。完整新增历史审计与远端核验后按本周授权通过PR集成main，不直接push main、不强推、不发布。
