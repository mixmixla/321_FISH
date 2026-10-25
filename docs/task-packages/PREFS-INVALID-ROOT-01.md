# PREFS-INVALID-ROOT-01 v1 — 保留根类型错误的偏好原件

2026-10-25 READY / INDEPENDENT_DESIGN_REVIEW_0_MUST（server_scout）。来源：用户本轮约90分钟本地开发授权与既有坏prefs拒绝覆盖合同。
base/远端main已核 `41a01148f8d87464270993484c8a78f9fd9c1794`；独立工作树
`_tmp_gui/worktrees/local-reliability-20261025`，分支 `fix/local-reliability-20261025`。

## 冻结范围

现有 `Prefs._load` 对合法JSON但非object根（array/null/string/number/bool）静默使用默认值，
后续登录选择、普通设置或UID档案保存可覆盖原件。仅修复该已确认的数据保护缺口：
非object根必须进入现有 `_load_error` 拒写路径；保留原文件字节，拒绝绑定持久UID视图及保存。
缺文件、新建空object与正常object配置保持既有行为。临时UID视图仍可在内存使用。

root唯一写入 `prefs.py`、新增 `tests/test_prefs_invalid_root.py` 及Task/Review/中心/投影/必要稳定事实。
identity_scout只读定位和独立代码/证据审查，server_scout独立设计审查；不参与补丁实现。
不重构全部prefs、不改数据迁移/自动修复、UI、协议、依赖、门禁或原有测试断言。
只用新建合成资料，不读取真实prefs/聊天/密钥，不触碰暂停视频4759分支。

## 验收

1. 同一新回归在原产品上RED，覆盖非object根各JSON类型；明确测试到原件保护，而非只断私有错误字段。
2. 修复后GREEN：登录选择、普通保存和持久UID绑定拒绝且原字节不变；合法object与缺文件允许保存及重载。
3. 相关prefs/UID/launcher领域回归；所有旧断言和skip保持。最终应用候选仅一次新全量，失败先定位并保留原件。
4. 冻结source manifest；独立检查实际diff、原summary/log/退出码、当前与快照输入、失败保留后有限AI_ACCEPTED。
5. 已验收代码、测试、项目文档及脱敏摘要可正常提交并快进main/非强制push；不PR、不绕保护、不发布或上传EXE/raw。

06:12 UTC后不开大任务，06:27 UTC目标收尾。组件/源码门禁不代表完整GUI、自然退出、LAN、STT或现有EXE包含本修复。
