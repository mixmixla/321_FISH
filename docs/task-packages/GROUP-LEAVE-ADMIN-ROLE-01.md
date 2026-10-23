# GROUP-LEAVE-ADMIN-ROLE-01 v1

2026-10-23 READY。沿用户持续Sol+FAST、既定R1本地试用方向及正常main交付授权；fresh fetch/API已核base `004d2bd545d31e7a2e2686a92b62c4c42e91c181`，root唯一主控。上一显式dissolve已完整交付，不继承暂停视频4759；不更改实际服务设置或声称已获工具未暴露的FAST回执。

## 已确认缺口与最小产品范围

普通 `_on_group_leave`只删成员而未清g.admins。非成员期间_group_role确实为空，不误称立即越权；但公共群合法重新加入只写members，旧UID仍在admins，旧群管理员会恢复管理能力而未由现任群主重新授予。与kick/admin remove/最终断线清理回收管理员资格的现有行为不一致。修复目的仅使主动离开的群管理员再加入后成为普通成员，仍可由当前群主合法重新授权。

只改server.py普通leave锁内成员删除后的必要管理员资格清理，新增tests/test_group_leave_admin_role.py。admins.discard与权威成员离开同锁完成；其他UID/其他群admins不动，群主转让、最后成员解散、revision/全目标Session移除通知/语音清理以及原网络IO/审计行为保持。不要把权限资格问题扩展成新群管理设计，不改加入许可、邀请制度或admin override，不改别的handler、客户端/协议/GUI/持久化格式/环境依赖/游戏/视频。

mutes语义单独处理：旧代码普通leave/rejoin保留禁言，文档未明确防逃禁言的长期策略。本Task保留现有mutes值/行为，明确不新增mutes.pop、不自行批准清禁言；仍在群内时管理员资格不被提前撤销。账号在线/Web token、另一群管理员能力、其它成员/群权限保持，不做整号注销/踢下线/撤部署凭据或真实用户数据迁移。

## 验收与证据

先独立设计审查，0 MUST后实施。完整有限newtest先在原server确定性RED：由真实Hub既有授权handler授予群管理员，正常主动leave→按原权限重新加入公共群，向真实受管理员权限保护的handler（如邀请获取/群设置）发请求，证实旧资格实际恢复；不能只读取admins集合或mock _group_role结论，也不能把测试前置失败当产品失败。修复后同test证明普通成员拒绝（现有perm语义）、现任群主重新授予后正常允许。

至少一个真实loopback ClientCore场景验证退群、同账号保持在线、合法重入与受保护动作拒绝/重授予后成功；其他群管理员能力保持。合成Session/Web token/第二成员可作有限控制，不使用真实管理员密码、用户资料或设备。保留现有mute记录作为不改政策控制，普通非管理员leave、群主转让/最后成员路径复用必要旧域，不为镜像一行discard制造无价值测试框架。owned资源有界清理、事件或协议顺序屏障，不sleep竞态/压力追绿，不改skip/断言隐藏失败。

首GREEN及一次必要旧域按影响选择普通leave/kick、admin remove/dissolve、群管理/R28等，不重复同版已绿newtest、不跑并行full。RED/GREEN保持newtest字节一致；若必要修正测试则保留首次错误和版本，不冒称同版。独立代码/原件复核后worker只提交server.py/newtest，root等blob集成/冻结每输入，唯一最终full使用现有短--run-dir原工程ignored全新gla23-final-01，source-dir为当前Git工作树。基线agd23-final-01为219文件3014P0F20既有skip、496输入；不预写新计数。任何必测失败保存具体问题，不retry-to-green或用专项替代full。

独立最终技术与公开资料终审后root据证据有限AI接受本Task；审计全部新增可达对象/中间提交/metadata，fresh远端与可见保护核实，按用户明确授权正常非强制main合并推送/完整SHA核实。无CI记录不称通过，不强推/绕规则/改权限凭据保护/重写共享历史或发布。原日志/用户身份/二进制只ignored本地，公开仅脱敏摘要，不声称GUI/自然退出/跨机LAN/新EXE或完整R1已验收。

## 责任与恢复

root独占Task/Review/指挥中心/任务投影/必要稳定记忆和组合验证/集成，主控independent-r1-20261023工作树/分支fix/group-leave-admin-role-integration-20261023。session_scout独立group-leave-admin-role-20261023工作树/分支fix/group-leave-admin-role-20261023，仅server.py/newtest写入；flagship_scout独立只读设计/代码/原件/资料/对象审查，总活动最多3含root。当前base一致clean，无活动测试或在途写入；长测试/变更/交接更新指挥中心，原件本工作树_tmp_gui/group-leave-admin-role-20261023及正式短run目录，视频原工程4759保持暂停不动。
