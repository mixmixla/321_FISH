# TRIAL-JOB-01 v1 — 标准 EXE 预检的 Job 所有权

2026-10-21 冻结READY。用户要求自主验收并继续一个不依赖GUI放行的小开发增量；沿用普通模型/Standard。base/main ade446e639713297774fea3e7898f8dbb523a4ac，独立分支fix/trial-owned-job-20261021；root唯一实现/治理，gate_review独立只读。

## 选择依据与边界

R3-LOCAL-01已接受三EXE构建/实际双TCP登录/CLI，不是完整R3；完整大厅/邀请接受/一局结束再开/聊天/客户端红退出仍NOT_RUN。当前重新发现工具：无node_repl/cua/sky/native GUI入口，先前ComputerUse技能文件也不在原路径。不得自造输入/截图fallback或把组件/协议探针算GUI/LAN。
没有新的独立READY产品任务；历史DRAFT/失败任务不能按旧计划直接复活。选择现R3可测性依赖中已证实的风险：标准local_trial.py run仍导入test_sandbox.DesktopProcess，按数值PID taskkill且吞close异常；上轮只能任务局部adapter使用Job。将安全默认能力纳入正式入口，后续无人值守启动预检无需临时monkeypatch，不依赖未完成GUI验收，也不扩产品功能。

## 最小改动

只改local_trial.py默认launch_process为既有friend_trial_process.launch_owned，保留测试seam；清理正式记录Job active_before/after和close_ok，查询/terminate/close任一失败必须cleanup false、退出非0，不得吞失败。初始化已自然退出也只按其持有Job句柄处理，不按旧PID杀树。新记录/查询前先登记进程以保证finally覆盖。
不改friend_trial_process/test_sandbox共享实现、产品client/server/协议/GUI/规则、依赖、系统设置或已有原始R3证据。

## 验收与次序

1. 新回归在原代码先真实RED；真实Windows进程/private desktop/owned Job覆盖已退出初始化（自然0与非0）、存活子孙树、无关sentinel Job保持存活；清理故障注入只验证错误报告，明确不同于完整EXE/GUI验收。测试自己的RED清理只能持有句柄/Job，不能用潜在重用PID taskkill，不得泄漏子孙。
2. 修后同回归与现rel01/friend入口/相关sandbox真实回归，保留旧断言和skip规则。独立审查Task/diff/原raw和所有权/故障边界后冻结一次最终run.py test-all完整逐文件门禁；不得mock冒充真实路径，不启用visual/hardware。
3. 用正式local_trial.py run（无临时adapter）对R3上一批实际构建server/client执行一次fresh合成profile、loopback/private desktop启动预检，核init/open、双真实TCP登录/HTTP200/映像存活、Job0/close/source不变。二进制client/server代码未变，逐源码/hash映射确认后复用三EXE，不为harness变更重建未变产品；不称旧包包含新harness。
4. 绑定新源码内容标识、原/新测试/最终full/实际EXE运行证据。记录原R3GUI未测清单、无工具原因和分层覆盖；任务到此停止，不再自动扩任务或宣称完整R3/LAN/自然退出通过。
5. 独立终审后按用户授权正常commit/push并集成main，先fetch核新改动/保护/required checks，不强推/绕过检查、不删除分支、不发布；公开仅合成摘要/复现步骤/hash与必要日志，无私有profile/凭据/二进制。自动审批拒绝时按实际阻塞处理，不换工具绕过。

恢复先读指挥中心本任务首段、Task/Review、Git status/log、实际进程及原run summary；只一个实现主控与一次最终full。原R3历史接受范围不回溯升级。
