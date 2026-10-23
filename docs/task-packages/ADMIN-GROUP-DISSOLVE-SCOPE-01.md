# ADMIN-GROUP-DISSOLVE-SCOPE-01 v1

2026-10-23 READY，按用户持续Sol+FAST与正常直接main集成授权。base为fresh fetch/API双核main `7dbbd28cd9b608657c04e6444a75230cd6bdcd0a`；唯一主控root，复用已读项目开发技能，实际模型/服务回执不可见则不冒称核实。不继承视频4759，视频批暂停、不诊断/合并或开真实设备。

## 问题与最小范围

`Hub._on_admin_group_set(op="dissolve")`只删除group并发persist/system/list/audit，没有群移除revision、原群全部成员各会话group_removed、群语音名册删除。Core目录刷新不会清已加入意图/成员/邀请/E2EE材料；群已删除不等于必然重新入群，不能夸称仍会成功入群。用户价值是显式解散后每个原成员立即退出该群本地状态与语音名册，其他群与账号可继续使用。

现场不存在普通群主独立dissolve协议/handler。普通群主离开有剩余成员会转让群主，最后成员leave才解散；以现有_on_group_leave最后成员路径为对照，不新增普通群主解散入口，不改变其权限/行为。上一已验收管理员remove是不同入口，不拿其通过代替本批验收。

只修改server.py显式dissolve分支必要小段，新增tests/test_admin_group_dissolve_scope.py。保留系统管理员override与现有对象身份复核；在同一Hub锁内取得原群成员集合/所有现有_uid_clients目标Session快照、递增_group_state_revision形成带gid的group_removed、删除该群及group:{gid}语音名册。锁外逐目标send容错、既有force持久化/system/group_list/audit；外部IO不得持Hub锁。非成员不收group_removed，离线成员无Session不报错；每个实际目标Session只通知一次。重复/并发解散不得双删除、重复成功通知/审计或KeyError；现有错误或同对象已消失的无操作语义保持，不扩展为新协议。

保留账号在线、Web token、其它群与密钥/成员/语音房、私聊/通话及媒体资源。不要调用整号注销/踢下线/退役、删历史或清全量voice_rooms；不改变add/remove、普通leave/kick、client/client_core/UI、协议、环境依赖、游戏、持久化架构或视频，不安装原生调试工具或更改系统安全设置。

## 验证与证据

独立设计复核0 MUST后实施。先完成有限newtest（合成群名不超过实际配置上限），在原server运行一次确定性RED，保留原字节/源ID/实际退出码与失败；新测试应覆盖真实Hub全部原成员多Session（含合成Web与token）、仅目标群语音名册删除和其他账号/群资源保留。双UID/至少同UID双真实ClientCore经loopback协议证明群加入/成员/邀请/E2EE材料清理、另一群密钥和连接epoch保持，普通重连不再发送已解散gid的自动GROUP_JOIN（记录实际handler/发送入口并用同连接后续chat响应作有序屏障，不能只看服务器group已不存在），另一群消息仍可用。无真实管理员凭据，仅合成admin Session调用实际handler；不启用麦克风/摄像头。

必要控制：一个目标send失败不阻塞其他目标、非admin/不存在群无副作用、并发重复仅一次成功、revision新于原群快照且通知全部原成员、既有普通最后成员leave行为保持。dissolve在_known_names之前，竞态门应放目标线程首次Hub锁acquire前（不可沿用remove第二锁门），同时触门并有界join/异常传播；不能sleep竞态或循环追绿。成功外部IO锁外可用独立代码结构审查证明；动态跨线程探针若仅拒绝路径，要准确声明范围，不为镜像with结构造重复测试。

修复后首GREEN及一次必要旧领域（admin_groups/web、admin_remove、leave/kick、capacity、R72按实际影响选择），不重复同字节已绿newtest或并行full。独立代码/原件审查通过，worker只提交server.py/newtest；root无冲突等blob集成、冻结组合每输入hash，再唯一最终全量。使用现有--run-dir原工程ignored全新短目录（计划agd23-final-01），source-dir为当前Git工作树，不能切非Git快照冒充同集合。基线agr23-final-01为218文件3009P/0F/20既有skip、495输入；不预写新计数。

全量或必测失败保存具体问题/原件，不retry-to-green，不把初失败或测试前置错误隐去；修复/纠正须版本绑定。独立最终技术及资料审查后root据证据有限AI_ACCEPTED此Task；全部新Git可达对象/中间提交/metadata脱敏，fresh远端与可见规则核实后正常非强制main集成/推送/完整SHA核实。无CI记录不称通过，不发布/强推/改权限凭据保护/重写历史。公开仅脱敏摘要，原日志/用户身份/二进制只ignored本地；不声称可视GUI、自然退出、物理LAN、新EXE或完整R1通过。

## 文件与恢复边界

root唯一写Task/Review/指挥中心/任务投影/必要稳定记忆与原始证据绑定，主控工作树independent-r1-20261023/分支fix/admin-group-dissolve-integration-20261023。session_scout独立admin-group-dissolve-20261023工作树/分支fix/admin-group-dissolve-scope-20261023，唯一写server.py与newtest；flagship_scout只读独立设计/代码/原件/公开审查，最多3活动worker含root。冻结前两个新分支同base、无在途调用/活动测试，旧批次与视频分支不动。长测试开始/结束/变更与审查交接均更新指挥中心，原件本工作树_tmp_gui/admin-group-dissolve-20261023及正式短run目录。
