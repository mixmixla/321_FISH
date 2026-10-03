# RESOURCE-FIX-01 v1.1 — 损坏 manifest 的数值资格拒绝

授权：[本地自治](../decisions/LOCAL-AUTONOMY-20261003.md)。主控根据 resource_review 独立窄核查
冻结此项；v1.1允许在独立worktree以已审读的无GUI/无外部工具/显式loopback窄测试先复现与修复，
不等待通用runner全部完工。安全边界不变，集成/最终门禁仍依赖VB-01；不重开RESOURCE主体设计。

目标/原因：`server._read_web_resource` 在 legacy/new manifest 的 `ts=10**1000` 时，
`math.isfinite(float(ts))` 抛 OverflowError，坏 manifest 不能按预期无资格拒绝。
同时明确新 manifest 版本必须 JSON 整数 1，不接受浮点 1.0/bool；沿原严格格式设计，不做迁移。

基线：入场452417e（RESOURCE代码2087af8）；实施时重新绑定集成HEAD。唯一范围为
server.py::_read_web_resource 的类型/数值检查和 tests/test_cc02c_resource_files.py 或新增窄测试。
共享相同入口的 CHAT/GET 必须拒绝坏资格，合法 legacy/new文件继续可读。
不改变body→manifest发布顺序、同op/结果状态、ACL、数据保留、历史文件格式、Store或preview。

验证：相同最终测试先在入场源码导出上得到真实失败，后在修复候选成功。
合成 legacy/new manifest 极大整数 ts、有限 int/float正常值、bool/NaN/inf/错类型；
新version int1通过、float1.0/bool/未知版本拒；_web_file_meta返回None、HTTP GET 404、CHAT拒绝且无落库副作用。
全部数据在隔离临时目录，loopback，不读实际web_files/用户数据。资源专项及相关领域，
最终集成全量绑定修复候选；独立代码/证据审查后 AI_ACCEPTED，不将局部补正等同完整RETIRE。

回退：本任务明确本地提交 revert；不删除实际文件或修改真实manifest。

实施身份：`codex/resource-fix-01` worktree，从本地资料提交ba748cb分出，仅server.py目标函数与
新增tests/test_resource_manifest_numbers.py；主控在此实现，gate_impl仍独占主树门禁源码。
本文件/Review/中心在主树由主控维护，不在两个checkout同时修改同一代码交付；整合后重新验证。
