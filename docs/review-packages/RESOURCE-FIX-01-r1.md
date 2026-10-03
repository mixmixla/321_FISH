# RESOURCE-FIX-01 v1.1 — manifest 数值资格补正

**最终结论（2026-10-03）：AI_ACCEPTED，限本轮本地技术范围。** resource_review独立终审无must，主控据最终1daea66/full1669-0-2与对应分层/产物证据裁决；非Pro/用户验收、整个R1/RETIRE通过或发布。以下阶段未完成/失败记录按历史保留。


Task：[RESOURCE-FIX-01](../task-packages/RESOURCE-FIX-01.md)。当前REVIEWING，未AI_ACCEPTED；
主控实现于独立worktree，resource_review独立审查。已以6543e00整合主树；以下阶段原始记录保留，最终全量见末尾。

## 候选与安全边界

- 基线ba748cb（应用同452417e/RESOURCE2087af8）；分支codex/resource-fix-01，独立checkout
  `_tmp_gui/resource-fix-01/`，不复制ignored数据。唯一修改server.py::_read_web_resource及新35项测试。
- 原server SHA256 `54743252235f94f5823f4a82c087ddda207634ca8040e25ef78d489838eb9b77`；
  修复server `d3fa8e38d62ee037c58ed5ed296c2f798ab2de4f6527eb9433a94ef8e87abe32`。
- 同一最终测试 SHA256 `ca96221060b2392b685fcbe88438fc3afbb4842c556568ea54b53155c36a2a57`。
  公共时间戳类型/finite检查捕获OverflowError；版本必须int1。未改IO次序、ACL、状态/保留语义或其它函数。
- 运行前逐读新测试和原资源文件专项入口：新Hub所有audit/web路径为tmp_path，原默认源码路径位于
  新独立checkout，无真实库；HTTP直接`_QuietServer(("127.0.0.1",0),...)`，不启动serve/discovery。
  无Tk窗口、设备、外部请求/Agent或测试内部subprocess。子环境只继承OS启动键，使用合成profile，
  清除部署环境，未修改父会话或系统配置。所有测试进程已结束；HTTP finally shutdown/server_close/join。

## 实际运行

环境为项目.venv / Python3.14.5 / Windows11 / pytest9.1.1；每次独立basetemp。
以下命令在独立checkout、上述合成子环境执行，`python`指项目.venv解释器，日志在
`_tmp_gui/resource-fix-evidence/`；可从Git基线和本测试重跑，不依赖原日志才能恢复结论。

| 命令（省略独立basetemp绝对路径） | 版本 | 实际结果 |
| --- | --- | --- |
| python -m pytest -q tests/test_resource_manifest_numbers.py --basetemp <negative-temp> | 原server + 最终新测试 | exit1，9 failed / 26 passed，8.47秒 |
| python -m pytest -q tests/test_resource_manifest_numbers.py --basetemp <positive-temp> | 修复server + 同测试 | exit0，35 passed，2.81秒 |
| python -m pytest -q tests/test_cc02c_resource_files.py --basetemp <files-domain-temp> | 同修复server | exit0，41 passed，1.56秒 |

原9失败明确为正负极大整数legacy/new资格异常4、float版本错误接受1、CHAT异常2、真实HTTP请求异常断开2。
26原通过保留有限int/float兼容、其它非法数值/类型拒绝。修复后HTTP404/CHAT无bus副作用均通过；
没有skip/重试/断言弱化，原HTTP OverflowError/RemoteDisconnected日志保留，不改写为环境失败。

## 未完成

resource_review已独立核对真实diff、代码/测试hash、negative/positive原日志：补丁范围无未关闭must，
可以本地提交。主控已提交为 `9baffbb`（仅上述两文件），独立worktree clean；未push/未整合主树。
原资源文件领域同候选41项亦通过。当前代码/专项阶段已独立通过，Task仍REVIEWING，
整合候选资源相关领域/最终全量仍待完成。
76项专项/领域通过不替代最终全量，不等于完整RETIRE/R1/真实设备/发布完成。

## 最终整合验证

修复已主树提交6543e00整合，后续REL只增加启动配置等其它函数，未改变本补正语义。
最终代码1daea66/source f224f73b20e72ee1494f7fff096d7751c20fb6757d8c5b41434964431b4867f6：
127文件1669passed/0failed/2原opt-in、exit0，包含本补正35项和原资源三个文件14+41+12项实际通过。
完整命令/run/fingerprint与原失败分别见[VB Review](VB-01-r1.md)，最终独立验收结论另记，非整个RETIRE验收。
