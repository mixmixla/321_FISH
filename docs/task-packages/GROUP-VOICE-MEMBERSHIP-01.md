# GROUP-VOICE-MEMBERSHIP-01 v1

2026-10-23 READY。沿用户持续Sol+FAST、既定R1资源/成员一致性及正常main交付授权。base为fresh fetch/API已核main `ed287336d689360aec7090bfd4cc75c1c8099da7`，root唯一主控；不声称获工具未暴露的实际FAST回执。视频4759继续暂停，不继承/诊断/合并或启硬件。

## 缺陷与最小产出

`Hub._on_room_join`在锁外_room_key_ok验证群存在/成员，随后锁内直接voice_rooms.setdefault并写UID。若主动退群、群踢出、管理员移除/解散在两者间完成清理，迟到join可把已离群UID重新写入group:{gid}，或为已解散群创建孤儿语音名册。现有test_r72只顺序权限测试，未覆盖校验与写入之间的成员撤销。

只修改server.py此join handler必要范围和新增tests/test_group_voice_membership_race.py。在同一Hub锁内权威检查当前群存在/成员资格与写入群语音名册，可把既有键校验移入锁内，或保留预检但锁内再查；不能以锁外结果作最终授权。拒绝不得创建空/孤儿群房、更新UID地址、发送成功ROOM_STATE/ROOM_PEERS或成功审计。新增拒绝IO必须锁外；如为明确单一成功/拒绝出口需局部整理现有room_full判断，保持原错误码/文字、容量与成功数据语义，不扩展其它handler/架构。

保持public房正常加入、同UID合法重入更新ip/保持port、既有voice_room_max、Web只读拒绝、规范化房键/ROOM_STATE/ROOM_PEERS/audit等协议与权限；其他群/房/账号/token/密钥保持。只以写入时当前成员资格决定，合法重新加入者仍可入房，不引入永久封禁、跨成员代次协议或新语音功能。不改_on_room_addr/leave/drop、群移除handler、客户端/GUI/媒体、依赖/存储/游戏/视频。不启麦克风/摄像头或真实音频UDP，不安装工具/改系统网络安全设置。

## 证据与验收

独立设计0 MUST后，先完成有限newtest在原server一次确定性RED。真实Hub与合成Session，目标线程在旧锁外校验成功后、实际首次Hub写锁acquire前被受控门暂停；主线程调用真实leave/kick/admin remove/admin dissolve使成员撤销或删群并完成清理，再释放join。证明两阶段确实发生、旧版重新插入/创建名册，失败线程异常原样传播且全部owned线程有界join；不sleep竞争或无界压力追绿。

至少覆盖群仍存在的成员移出与整群解散两类，四个既有撤销入口可参数化；断迟到join返回原room错误、无目标名册和成功peers/audit、public/另一群已有名册保留。正常合法成员/同UID重入port保留/public容量等用有限控制及既有R72真实加密TCP域对照，不用全stub替代Hub。可用另一线程取Hub锁证明新增拒绝IO锁外；成功IO由独立代码结构审查，不冒称全路径动态探针。仅验证服务器名册/控制协议，不当真实音频设备验收。

修后首GREEN及一次必要旧域（R72、leave/kick、admin remove/dissolve、会话清理按影响选择），不重复同字节已绿newtest、不并行full。RED/GREEN test保持字节一致，必要纠正需保留首次失败与版本。B独立代码/原件后worker仅提交server.py/newtest；root等blob集成、冻结逐输入hash、唯一最终full用现有短--run-dir原工程_tmp_gui/gvm23-final-01，source-dir为当前Git工作树。基线gla23-final-01为220文件3017P0F20既有skip、497输入，不预写新计数。必测失败保留具体问题，不retry-to-green或以专项替代全量。

独立最终技术/公开资料终审后root据证据有限AI_ACCEPTED此Task；审全部新可达对象/中间提交/metadata，fresh远端及可见规则核实，正常非强制main合并推送并核完整SHA，无CI记录不称通过。不强推/改权限凭据保护/重写历史/发布，原日志/本机身份/私密/二进制只ignored本地，公开仅脱敏摘要；不声称可视GUI/自然退出/物理LAN/新EXE/完整R1通过。

## 文件与恢复边界

root唯一资料/指挥中心/任务投影/必要稳定记忆、组合验证与集成，主控independent-r1工作树/分支fix/group-voice-membership-integration-20261023。session_scout独立group-voice-membership-20261023工作树/分支fix/group-voice-membership-20261023，仅server.py/newtest写入；flagship_scout只读独立设计/代码/原件/资料/对象审查，总活动最多3含root。冻结时同base clean，无在途调用/活动测试；长测试/变更/交接及时记指挥中心。原件本工作树_tmp_gui/group-voice-membership-20261023及正式短run目录；原工程视频4759保持不动。

## 本批实施结论

2026-10-23有限AI_ACCEPTED_GROUP_VOICE_MEMBERSHIP_ONLY；需求v1范围不变。worker94685dbd9d03130159279b833ac2a2e0bedaaf48、组合ceae77c497e08742db1fa0acc1a72e757d12905d，唯一full221文件3022P0F20既有skip/exit0，独立最终技术0 MUST。公开资料独立0 MUST；普通main集成仍待，版本/原件/后验见Review；不等用户/Pro或完整R1验收。
