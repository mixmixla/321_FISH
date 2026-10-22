# R1-RESTART-RECONNECT-01 r1

2026-10-22 当前组合 **AI_ACCEPTED_NORMAL_RESTART_RECONNECT_ONLY / FINAL_REVIEW_0_MUST / INTEGRATION_PENDING**；原运行仍为 **FULL_FAILED**，以下保留原失败检查点。

Task v1；base/HEAD `ddf1c79b0143890a4c98941b6b5b500b6909e761`，分支 `feature/r1-restart-reconnect-20261021`。仅 `tests/test_client_core.py` 增加真实持久 Hub 正常重开、原 ClientCore 自动续连、UID/epoch/双端消息及自有线程清理回归，业务源码未改。root 唯一写入/执行，r1_review 独立只读代码审查 0 MUST。

原全量于用户停工后中断，189/213 passed、test_server running、无summary。恢复核当前与snapshot的490输入逐SHA一致、不可变身份/依赖/解释器/命令/环境指纹一致、原189日志完整、原PID已退出，使用原生 `run.py test-all --resume`，只补剩余24文件，保留test_server首次interrupted attempt和原日志。恢复前manifest/progress/日志哈希另存本地 `recovery-20261022`。

完整结果213文件 **2971 passed / 1 failed / 20既有skipped，actual exit1**；107.921秒为恢复执行阶段，不是整个全量耗时。唯一失败 `tests/test_test_gate.py::test_gate_preserves_timeout_and_collection_empty_statuses`：内层timeout清理记cleanup_ok=false，runner fail-closed退出2，原用例预期1；原nested summary、超时日志、外层1F7P全部保留。test_server恢复attempt2为61P，最终字节test_client_core为34P。历史75P领域日志早于最后清理修订且缺独立版本绑定，因此不作为最终字节领域证据。

[脱敏结果与逐文件哈希](../review-assets/R1-RESTART-RECONNECT-01/evidence.json)。原件仅ignored本地 `_tmp_gui/test-gate/` 对应run及 `_tmp_gui/r1-restart-reconnect-20261021/`。没有重复失败项、改skip或弱化断言；当前无活动测试。当时门禁清理失败阻止本批验收与集成；后续独立任务及组合验收见下节，不改变原失败结论。GUI、自然应用退出、LAN、新EXE、R1/M1整体验收均未取得。


## 后续组合有限验收（2026-10-22）

独立GATE-CLEANUP-WAIT-01修复终止后有界等待，保留上述failed记录。新组合full为213文件2984P0F20既有skip/exit0；最终test_client_core仍34P，源码与原R1候选仅门禁修复及其回归不同。原R1正常续连覆盖与新门禁候选的独立终审/有限验收见[GATE Review](GATE-CLEANUP-WAIT-01-r1.md)，独立原件/拟公开资料终审0 MUST后，主控有限AI接受正常重启续连回归；不能将原失败run改为通过，也不升级整体里程碑。
