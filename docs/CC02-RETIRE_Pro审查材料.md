# CC02-RETIRE — Pro 审查材料 v1

2026-10-02（Asia/Shanghai）。本文件可整体交给 Pro；不要求审阅者访问本机源码或 ignored 日志。
它是 **M1 + STORE-COMMIT 的待审设计**，不是已实现行为或实施授权。执行状态只见[指挥中心](AI_COMMAND_CENTER.md)。
资料批次需求见[CC02-RETIRE-DESIGN](task-packages/CC02-RETIRE-DESIGN.md)，后续[实施 Task 草案](task-packages/CC02-RETIRE-DRAFT.md)仍为 DRAFT。

## 1. 请审什么、依据是什么

请判断本方案能否在保持现有 KICK/单端 logout/最后端清理语义的前提下，可靠退役旧 UID，关闭认证和全部迟到写入，并只在当前 JSON 提交成功后报告成功。
请逐项回答第 8 节 P1–P7，确认第 6 节数据表和第 9 节验收矩阵，列出必须整改项；审查不直接批准真实账号操作或下一代码批次。

- 代码依据：CC-02A 代码提交 `e065591d32936115f7b36550ba0b1d9f7bb57f60`；读取工作树 raw 源/测试/依赖 305 项内容集合
  `1f94f8fca3da7746c5db293b05e5729e76b37935e1a05d0314658bde9de39830`，与已验收候选逐项一致。
- 本批文档接管 HEAD：`fc9c991bed82dc969aefdbfc9a77a46e75bde5d5`，branch `codex/cc02a-consistency`；准确 tree/index/dirty 和接管过程见[本批 Review](review-packages/CC02-RETIRE-DESIGN-r1.md)。
  代码源码行号对应上述 raw 版本；后续版本变化须重新核对，不能仅沿用代码审查通过结论。
- 历史已验收：PROFILE 保留资料；RESTORE 严格恢复 groups/reads 身份 map；KICK 锁内撤销当时全部端，锁外通知，允许随后重新认证。
  113 文件、1355 passed / 0 failed / 2 原有 opt-in skipped 仅属于 CC-02A 的已冻结版本，**不是 RETIRE 验收结果**。
- [架构决定 v1](decisions/CC-02_架构审查决定_v1.md)已选 M1（D1），明确逻辑清理/共享保留（D3/D4）、可靠提交（D7）、不扩大普通凭据改造（D8）、不改 LOCAL/CLOUD 格式（D5/D11）。
  本文把这些决定细化为可审提交方案；新增技术取舍仍待 Pro。
- 本批只读源码、整理文档；未运行应用或测试，未读取真实运行数据。本文件所列竞态是源码时序推断，未伪称已做动态复现。

## 2. 当前源码事实与缺口

| 事实 | 源码锚点及含义 |
| --- | --- |
| 昵称仍复用旧 UID | `server.py:_attach` 1664–1724：有 nick_to_uid 就复用，否则分配 uid_seq 后递增；旧删号最后只移除 known，不移除昵称映射 |
| 旧删号只保护当前执行者自己 | `_on_admin_user_del` 3830–3882：退群、清目标作者消息、撤旧端/token、移除 known、force 写盘；无显式 retired、due/草稿/CLOUD 屏障 |
| KICK 接受点 | `dispatch` 2196–2201、`session_by_token` 2084–2092；`_kick_targets` 3557–3577 锁内 closed/token 撤权；已接受操作不笼统追溯取消 |
| 认证检查与认领分离 | `_pwd_check_for_login` 1752–1773、`_pwd_claim/_pwd_store` 1775–1794；PBKDF2 在锁外，attach 后才认领；普通并发认领/改密风险仍归 CREDENTIAL |
| due 摘取不等于发布 | `_sweep_scheds` 1588–1626：Hub 锁内摘除，锁外校验和 publish；`_sched_still_valid` 1628–1642 只检查屏蔽/群成员 |
| bot 与预览绕 dispatch | `_bot_dispatch/bot_say` 2787–2822；`bots.sweep_reminders` 126–136；`agent_bot._run_async` 69–77；`_preview_ready` 3198–3208 修改已有消息 |
| CLOUD 是独立文件 | `_cloud_load_disk` 4209–4225 在 restore 前扫描；PUT 4227–4246 先改内存、直接覆盖文件、吞 OSError 后仍 CLOUD_DONE；GET 4248–4258 无退役检查 |
| 快照复制不等于同一时点 | `_snapshot_state` 570–638 先复制 bus，释放后再复制 Hub；known.remarks 等仍共享内层对象；CLOUD/物理文件不在 snapshot |
| 后台与 force 可倒序 | `_persist` 1071–1104 先捕获快照再入槽；worker 1137–1162 已取旧槽时，force 清槽不能取消该对象；Store 文件锁只序列化调用，未保证版本顺序 |
| 失败可能被误作成功 | `server_store.py:save` 36–53 吞写入/replace 的 OSError；Hub 可能推进 fingerprint；fingerprint 使用 default=str，实际 dump 不使用，burn.pend 的 set 可使真实序列化失败 |
| load 会掩盖不可读状态 | `server_store.py:load` 26–34 把缺失/坏 JSON/非 dict/IO 错误均变为 {}；不能让这种降级绕过已退役身份约束 |
| 现有 IO 锁范围需拆分 | 群文件 chunk 6181–6220 在 Hub 锁内写文件，done 6239–6264 在锁内 getsize；READ→_burn_finish 3941–3959/4273–4289 可在外层 Hub 锁内通知/持久调用 |

当前快照顶层字段完整集合为：`bus, uid_seq, gid_seq, nick_to_uid, groups, reads, pins, burn, known, blocks, polls, drafts, scheds, custom_stickers, sticker_pack_meta, group_files, gf_seq, tasks, task_seq, fish_board, moments, moment_covers, pid_seq`。
`sessions/_uid_clients/web_tokens`、CLOUD、bot_reminders、sticker_subs、传输/游戏/语音房和媒体本体不是这个 JSON 的事务对象。
现有快照未保存群 `avatar/about/slow_last`；本方案不借机修全部存储格式，但任何候选序列化错误必须失败反馈，不能默认为提交成功。

## 3. M1 身份模型与保护集合

### 身份关系和恢复

建议新增严格解析的 `retire_schema=1`、`store_revision` 与 `retired[uid] = {nick, operation_id, retired_at, cleanup_version:1}`。
revision 是快照提交顺序，cleanup_version 是本文数据表的清理版本；这些字段名称为设计建议，不是现有 schema。
只保留必要 UID/原登录名/操作关联与时间，不保留可认证密码、Session、token、私有正文。`nick_to_uid[原昵称] = 原 UID` 保持占用。
运行态另有 `pending[uid]`（操作 ID、目标 revision、阶段、失败类别）；它不作为“已落盘成功”的证据。

- 任一 retired 或 pending 身份都不能登录、免密认领、改密、产生 token、再次 attach 或拥有新私有记录；昵称判断须早于密码检查，并在实际授权提交处复查。
- `_uid_seq` 是**下一个** UID；恢复后不小于原值并高于普通昵称映射/普通known/retired的UID上界，分配时跳过所有已占用及实际 bot UID，不能重用旧 UID。
  固定 bot 的高位号不单独强迫普通序号跳跃；昵称清洗保持现有规则。
- 恢复时先验证普通昵称映射是否已占用注册 bot UID，再注入 bot；发现既有碰撞必须拒绝可写启动/转受控处理，不继续用 bot known 覆盖普通用户。未来注册表变化同样先查碰撞。
- 老快照字段缺失视为未包含退役信息，不从 known 缺失推断退役。新增字段出现但格式非法、UID/nick 冲突、身份映射冲突或包含受保护身份时，拒绝以可写服务启动；不能静默丢坏退役项。
- 无应用恢复/同昵称再注册入口。管理员重复请求或重试通过 tombstone 专用查询定位原 operation_id，不能为重试重建 known。
- tombstone 只用于约束身份/显示旧引用；普通已知账号名单不能因共享作者引用或启动扫描重新创建活跃账号。

### 不可退役的实际身份

| 集合 | 当前证据 | 建议保护边界 |
| --- | --- | --- |
| 管理员保留登录名 | Hub 430–440：默认 `ADMIN_NICK` 与配置有效管理员名加入 `_reserved_admin_nicks`；管理员 UID 随 attach 分配 | 拒绝退役这两个登录名所绑定的 UID，以及当前真正认证的 is_admin Session UID；未配置密码时保留名仍受保护 |
| 实际 bot | `bots.BOT_BY_UID`；基础 901/902/903，可选 Agent 为 909；Hub 在 restore 后注入 known[type=bot] | 以实际注册 UID 集合保护，分配器跳过该集合；不把所有 UID≥900 的普通用户当作 bot |
| 系统消息 | `_broadcast_system` 是消息来源，没有另一个可登录系统账号 UID | 不发明额外系统账号；未来注册新增身份须纳入同一保护注册表 |
| 历史管理员/同名普通用户 | known 没有管理员角色；配置变更后不能单凭历史昵称证明身份。bot 昵称目前可被普通 UID 使用 | 不猜测迁移或覆盖现有映射；P5 决定是否加入“曾认证管理员 UID”的持久保护集、bot 昵称预留及碰撞兼容策略 |

## 4. 完整入口、接受点与最终效果提交

定义：A 为现有 dispatch/API 接受点；C 为本方案需要加的最终效果提交点；t0 为 UID 退役屏障提交；D 为持久成功确认。
**A 在 t0 前不自动授权任意迟到 C。** 已完成 C 的操作不回溯抹除网络交付/下载副本；只通过 A、尚未获准 C 的工作在 t0 后拒绝身份写入。
KICK 继续沿现有 A 语义；RETIRE 的新增 UID fence 不应无说明变成所有 KICK 操作的追溯取消。

| 写入面/路径 | 当前 A / 副作用 | RETIRE 的 C 与约束 |
| --- | --- | --- |
| TCP HELLO→_on_hello；Web login→login_web | 密码检查、_attach、_pwd_claim、token 发布分散 | 登录名早拒绝；UID 分配/在线集合/known 重建、认领摘要写回、token 插入分别在 UID gate 和 Hub 内存提交区复查 fence；哈希/welcome/audit 在锁外 |
| _pwd_store/set_password；Web /api/passwd | Web _session 后直调用，不走 dispatch；可迟到重建 known | 摘要写入前检查 retirement epoch，拒绝复活 known；只做 RETIRE 屏障，不实现普通凭据版本 CAS/轮换策略 |
| dispatch 身份/profile/私有状态 | 头像、签名、状态、隐身、备注、BLOCK_SET、DRAFT_SET、SCHED_SET/CANCEL、sticker_subs | 每个内存最终写入区以认证 UID 检查 fence；target 私有记录的管理员变更也检查目标，不仅检查执行者 |
| dispatch 消息/共享记录 | CHAT、POLL/VOTE、VOICE/VMEMO 元数据、EDIT/DEL/REACTION、READ/BURN、PIN、PURGE | bus.publish/原地 edit/discard、reads/pins/burn/polls 等状态修改时检查 UID fence；不得仅包 dispatch 开头；广播/audit/媒体 IO 放锁外 |
| dispatch 群及共享库 | 建群/加入/退出/踢人/管理/公告/邀请码/头像/群文件/任务/动态/贴纸/排行榜 | 群、任务、动态、共享索引内存修改在最终提交区；不凭保留旧 UID 引用给退役人新权限；持久字段变更均标 dirty（不能只依赖已有 _persist 调用） |
| dispatch 短生命周期状态 | typing/nudge/shake、E2EE/位置/语音、房间/game、P2P/中转 xfers | 最终注册/入队/资源变更复查 fence，t0 后不再登记旧 UID；已有共享游戏继续按已验收离房规则，不改游戏玩法或做筛查 |
| Web 直接 /api/upload | _session→_save_web_file；文件/元数据无 owner UID，后续 send 才走 dispatch | 将认证 permit 带到最终文件发布；独立 staging，UID gate 内最后复查再发布 fid/meta；失败/退役不返回有效上传成功；不猜归属清旧文件 |
| Web logout→unregister、内部注销 | 直接改在线/known/群/token，旧回调可能重建资料 | 已退役 UID 的注销只清旧 Session/资源，不能重建 known；迟到旧回调不能清其它 UID 或后来合法会话 |
| Web whoami/events 及其它 GET | touch；SSE attach/detach/q；下载/媒体读盘。whoami 不生成 token | SSE 真正 attach 前复查；closed/fenced 端不再靠 touch 延寿或重挂队列。私有读在取得数据访问权前查 UID；锁外传输已取得字节不承诺远程收回 |
| Web dispatch wrappers | _session 再 dispatch，许多忽略 False 仍返回 200 | 底层 C 一律拒绝迟到写。RETIRE 管理结果必须传递持久状态，HTTP200/“已提交”不能作永久成功；不全面改其它 wrapper 响应契约 |
| sweeper 已摘取 sched due | 锁内从 scheds 摘出，锁外 _sched_still_valid 后 publish | 摘取/校验不算 C；UID gate 内最终退役+原群/屏蔽检查与 bus.publish 原子排序；t0 后丢弃，不回灌被取消任务 |
| bot_reminders、普通 bot、Agent后台结果 | bots 直接追加/摘出；bot_say 直接 publish；Agent 可长时运行 | 提醒入队按所属 UID 过 C；t0 清目标提醒。最终 bot_say 检查**接收目标 UID**，不是只检查受保护 bot；不可取消的外部工作可结束但结果不再形成私有记录 |
| 链接预览 worker→_preview_ready | 网络在外，按 seq 找消息后原地补 preview | 原 CHAT 已 C 不代表可以补已删除消息；最终检查消息仍存在/作者未 fenced，丢弃目标作者的迟到补写；他人消息继续。已有投递不追回 |
| CLOUD PUT/GET、启动扫描 | 独立内存+文件，当前写错仍 CLOUD_DONE；启动先扫描再 restore | PUT 用独立 tmp，最终 UID gate→复查→锁外 fsync/replace→索引提交→成功回执；退役与 replace 按同 gate 排序。GET 最终访问检查；启动先恢复退役约束或隔离扫描后过滤再开放 |
| 普通 persist、force、flush、后台已取快照 | 非身份入口，当前旧对象可倒序 save | 全部进入同一 writer；取得 writer 后才采集当前一致状态，不接受独立旧 snapshot。D 绑定被写候选的 retirement operation_id，不能用一次函数返回替代确认 |
| sweeper 内部过期/GC/tick/离线通知 | 没有普通 Session；会改持久或运行记录 | 内部路径也走内存提交规约和 dirty 标记；只做既有过期/清理，不重建退役私有记录。系统共享状态可继续，禁止借 system actor 绕过私有 owner fence |

上表覆盖 `server.py:dispatch` 2204–2459 的整张路由表及其之外的实际入口；分类不等于每个 handler 已改造。
未来实现必须交付逐 handler 的 C/锁/IO 对照，含直接函数调用；同一 UID 的主体与目标私有状态需区别，保留共享引用不触发“清除他人数据”。
新群成员/管理员授权及任何 target 私有 owner 的新建，也须在最终 C 检查目标 fence；别的合法管理员不能通过旧UID参数把退役身份加回权限集合。
`/api/sticker/<code>` 是当前公开共享资源，不因 RETIRE 改成 UID 私有；Web 当前无 user_del 管理入口，不顺手新增新管理产品面。

### 4A 逐handler提交矩阵（119个实际dispatch目标）

本表经AST枚举与人工语义分类逐函数对照，119/119无漏项；行号属于冻结raw源码。A统一为dispatch已接受的服务器permit，HELLO为待认证入口；它们之外另见4B。
表中C是**建议的完整效果边界**，不宣称当前代码已原子化。每个写C检查actor及明确的private owner/新授权target；共享作者/备注/投票UID仅引用时不新增该身份权限。
t0对每个写C按相同UID gates排序，C尚未取得时拒绝，已取得C则t0在Hub外等待完整效果完成。所有JSON字段变更按5.2A递增revision。
锁/IO码：M=UID gates→必要资源锁→Hub→bus纯内存；F=同序检查、释放Hub后文件IO、UID/资源锁保持、回Hub完整内存提交；G=UID gate排序RoomManager纯内存动作，内部子锁/事件不反向等待Hub，网络在外；S=许可发送集合捕获后锁外网络；R=访问核准后锁外读。
D码：J=JSON字段变更标dirty走统一writer，普通操作不冒称同步持久；J-force仍须明确receipt；J-RETIRE-D必须等本op_id确认；CLOUD-D是独立文件成功，不能替代JSON退役D；N=不在JSON；N*=当前schema未保存该字段，不借本批静默扩展。
F跨文件/内存效果只保证相对于该UID的t0顺序及完整内存提交，不宣称整个媒体目录与JSON是原子事务；暂存文件未公开索引前不得取得共享访问。

| handler@server.py行 | actor/target | 建议完整C | 锁/IO/D |
| --- | --- | --- | --- |
| `_on_block_set@1457` | 本人owner；被屏蔽UID仅引用 | blocks[A]开关完整变更 | M/J |
| `_on_block_list@1484` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_sched_set@1512` | 本人owner；私聊接收UID/群GID | scheds[A][rid]完整任务；私聊接收UID fence及原群/屏蔽条件 | M/J |
| `_on_sched_cancel@1570` | 本人owner/rid | 移除本人任务整条 | M/J |
| `_on_sched_list@1584` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_set_pwd@1824` | 本人private owner | known[A].pwd最终写回；哈希在外，仅退役epoch屏障 | M/J |
| `_on_avatar_set@1859` | 本人private owner/头像资源 | 文件发布/删除与known.avatar变更按UID gate排序；内存字段一次提交 | F/J |
| `_on_avatar_del@1891` | 本人private owner/头像资源 | 文件发布/删除与known.avatar变更按UID gate排序；内存字段一次提交 | F/J |
| `_on_avatar_get@1906` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_sign_set@1925` | 本人private owner | known[A]对应sign/status/invisible整值更新 | M/J |
| `_on_status_set@1933` | 本人private owner | known[A]对应sign/status/invisible整值更新 | M/J |
| `_on_remark_set@1949` | 本人owner；备注UID为引用 | known[A].remarks对应项完整更新；不删他人备注 | M/J |
| `_on_invis_set@1980` | 本人private owner | known[A]对应sign/status/invisible整值更新 | M/J |
| `_on_admin_invis_set@1993` | 管理员actor+目标private owner | known[T].invisible更新；目标gate/fence与actor一起检查 | M/J |
| `_on_hello@2461` | 待认证昵称→实际UID | attach的昵称占用/UID/online/known完整建立；另逐点claim/token；zombie之前查fence | M/J |
| `_on_chat@2538` | 发送者；新私聊接收UID/群GID | bus消息/seq索引+实际burn注册+群slow_last关联状态同一内存C；bot分支另见内部表 | M/J |
| `_on_typing@2824` | 发送者/接收范围 | 本人限速运行字段+受许可接收集合；网络发送在外 | M/N |
| `_on_nudge@2860` | 发送者/接收范围 | 本人限速运行字段+受许可接收集合；网络发送在外 | M/N |
| `_on_shake@2913` | 发送者/接收范围 | 本人限速运行字段+受许可接收集合；网络发送在外 | M/N |
| `_on_poll_create@2959` | 发起者；新私聊接收UID/群GID | bus消息/seq与_polls[seq]完整权威投票一起建立 | M/J |
| `_on_poll_vote@3045` | 投票者；已有共享poll seq | votes与非匿名bus投票聚合一起更新；作者UID仅共享引用 | M/J |
| `_on_voice@3210` | 发送者；新私聊接收UID/群GID | bus元数据/seq与_voice或_vmemo及对应ts缓存/实际关联状态一起登记 | M/J |
| `_on_vmemo@3273` | 发送者；新私聊接收UID/群GID | bus元数据/seq与_voice或_vmemo及对应ts缓存/实际关联状态一起登记 | M/J |
| `_on_geo_live@3370` | 发送者/许可私聊或群范围 | 仅信令授权与接收集合捕获，无JSON状态 | S/N |
| `_on_geo_stop@3386` | 发送者/许可私聊或群范围 | 仅信令授权与接收集合捕获，无JSON状态 | S/N |
| `_on_edit@3455` | 原作者/自己的seq | bus消息text/edited/edits等全部修改字段原子更新 | M/J |
| `_on_del@3516` | 作者/合法私聊对端或管理员/seq | bus消息全部删除字段与索引一致；保持既有权限 | M/J |
| `_on_admin_kick@3579` | 管理员/目标UID | 当时端集合closed/token撤权提交；锁外旧注销清理；不改KICK的A语义 | M/N |
| `_on_admin_groups@3640` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_admin_group_set@3660` | 管理员/GID；新增授权target UID | 群成员/管理员/owner/空群结果整体变更；新授权查target fence | M/J |
| `_on_admin_user_get@3756` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_admin_clear_all@3779` | 管理员/全部频道或作者UID | bus清理及seq索引同一内存提交，force仍经统一writer | M/J-force |
| `_on_admin_clear_uid@3792` | 管理员/全部频道或作者UID | bus清理及seq索引同一内存提交，force仍经统一writer | M/J-force |
| `_on_admin_user_del@3830` | 管理员+目标UID | 完整t0：tombstone/全部旧授权/作者历史/本人私有字段/群授权及清理计划 | M/J-RETIRE-D |
| `_on_reaction@3884` | 回应者/已有seq | bus.reactions完整变更 | M/J |
| `_on_read@3930` | 本人读游标owner/会话key | reads游标与实际burn pend/完成/对应bus变化一起提交；通知/持久IO移出Hub | M/J |
| `_on_read_detail@3994` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_msg_readers@4007` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_e2ee_pub@4071` | actor/许可私聊UID或群范围 | 仅密文/信令授权与收件集合捕获；不把新信令登记到退役人 | S/N |
| `_on_e2ee_pub_ack@4086` | actor/许可私聊UID或群范围 | 仅密文/信令授权与收件集合捕获；不把新信令登记到退役人 | S/N |
| `_on_e2ee_chat@4106` | actor/许可私聊UID或群范围 | 仅密文/信令授权与收件集合捕获；不把新信令登记到退役人 | S/N |
| `_on_e2ee_group@4117` | actor/许可私聊UID或群范围 | 仅密文/信令授权与收件集合捕获；不把新信令登记到退役人 | S/N |
| `_on_e2ee_sk_dist@4142` | actor/许可私聊UID或群范围 | 仅密文/信令授权与收件集合捕获；不把新信令登记到退役人 | S/N |
| `_on_e2ee_sk_req@4184` | actor/许可私聊UID或群范围 | 仅密文/信令授权与收件集合捕获；不把新信令登记到退役人 | S/N |
| `_on_cloud_put@4227` | 本人private owner/CLOUD文件 | 独立tmp→最终核准replace→cloud索引；同UID gate持至完整效果完成 | F/CLOUD-D |
| `_on_cloud_get@4248` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_purge@4298` | 操作者/许可会话和截止seq | bus频道和_by_seq索引按原purge规则完整更新 | M/J |
| `_on_draft_set@4336` | 本人private owner/key | _drafts[(A,key)]完整更新或删除 | M/J |
| `_on_sticker_pack_rename@4401` | actor/共享旧新pack资源 | 包名/关联贴纸元数据/封面路径整体效果；资源锁按名称固定次序 | F/J |
| `_on_sticker_pack_del@4442` | actor/共享pack资源 | 贴纸清单/包元数据与文件删除按资源锁排序；非RETIRE的既有正常删除操作 | F/J |
| `_on_sticker_pack_cover@4468` | actor/共享pack资源 | 封面文件效果与pack_meta完整变更 | F/J |
| `_on_sticker_pack_cover_get@4519` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_sticker_reorder@4536` | actor/共享code或pack | 相关order值一次提交 | M/J |
| `_on_sticker_custom_add@4574` | actor/共享code资源 | 贴纸文件效果与custom_stickers完整变更 | F/J |
| `_on_moment_publish@4634` | 作者/新pid与共享图片资源 | 图片发布后moments记录与pid_seq完整内存提交；未发布staging不变成共享索引 | F/J |
| `_on_moment_like@4681` | 操作者/共享pid | likes或comments完整变更；旧作者UID不代表活跃权限 | M/J |
| `_on_moment_comment@4700` | 操作者/共享pid | likes或comments完整变更；旧作者UID不代表活跃权限 | M/J |
| `_on_moment_del@4730` | 作者/共享pid及图片引用 | post移除与可靠关联图片正常删除按资源锁排序 | F/J |
| `_on_moment_feed@4764` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_moment_img_get@4793` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_moment_cover_set@4826` | actor/自己的已发布封面资源 | 封面文件效果与moment_covers完整变更；RETIRE保留分类待P6 | F/J |
| `_on_moment_cover_get@4878` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_moment_cover_del@4895` | actor/自己的已发布封面资源 | 封面文件效果与moment_covers完整变更；RETIRE保留分类待P6 | F/J |
| `_on_sticker_custom_del@4909` | actor/共享code资源 | 贴纸文件效果与custom_stickers完整变更 | F/J |
| `_on_sticker_custom_get@4928` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_sticker_shop@4951` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_sticker_sub@4956` | 本人private运行owner/pack引用 | sticker_subs[A]完整开关，非JSON | M/N |
| `_on_pin@4976` | 操作者/共享会话seq | pins完整置顶副本变化；当前未主动persist也必须标dirty | M/J |
| `_on_history@5054` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_thread_fetch@5091` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_call_ring@5109` | actor/通话对端UID | 许可对端/地址信令捕获，传输及审计在外 | S/N |
| `_on_call_ready@5120` | actor/通话对端UID | 许可对端/地址信令捕获，传输及审计在外 | S/N |
| `_on_call_simple@5135` | actor/通话对端UID | 许可对端/地址信令捕获，传输及审计在外 | S/N |
| `_on_room_join@5278` | actor/语音房名册 | voice_rooms成员/地址/空房结果完整提交；广播在外 | M/N |
| `_on_room_addr@5310` | actor/语音房名册 | voice_rooms成员/地址/空房结果完整提交；广播在外 | M/N |
| `_on_room_leave@5331` | actor/语音房名册 | voice_rooms成员/地址/空房结果完整提交；广播在外 | M/N |
| `_on_file_offer@5350` | sender+receiver UID/fid | xfers完整建立；新对端授权查fence | M/N |
| `_on_file_accept@5387` | 认证参与者/xfers fid | 对应状态/端口/direct/活动时间完整变更并捕获合法转发目标；body网络在外 | M/N |
| `_on_file_reject@5409` | 合法参与者/xfers fid | 参与者授权及xfers移除同一内存提交，通知在外 | M/N |
| `_on_file_listen@5421` | 认证参与者/xfers fid | 对应状态/端口/direct/活动时间完整变更并捕获合法转发目标；body网络在外 | M/N |
| `_on_file_direct_ok@5437` | 认证参与者/xfers fid | 对应状态/端口/direct/活动时间完整变更并捕获合法转发目标；body网络在外 | M/N |
| `_on_file_data@5444` | 认证参与者/xfers fid | 对应状态/端口/direct/活动时间完整变更并捕获合法转发目标；body网络在外 | M/N |
| `_on_file_chunk_ack@5457` | 合法接收者/xfers fid | 许可参与者与ACK收件捕获；无新JSON状态 | S/N |
| `_on_file_verify@5468` | 合法参与者/xfers fid | 参与者授权及xfers移除同一内存提交，通知在外 | M/N |
| `_on_file_cancel@5480` | 合法参与者/xfers fid | 参与者授权及xfers移除同一内存提交，通知在外 | M/N |
| `_on_group_create@5569` | actor/GID；新的member owner | 群创建或成员加入完整提交；邀请码校验关联计数保持，群快照字段必须标dirty | M/J |
| `_on_group_join@5596` | actor/GID；新的member owner | 群创建或成员加入完整提交；邀请码校验关联计数保持，群快照字段必须标dirty | M/J |
| `_on_group_leave@5619` | actor/GID及被移除成员 | 成员/admin/mute/owner/空群结果与语音成员撤除；撤权清理可处理已fenced目标 | M/J |
| `_on_group_kick@5657` | actor/GID及被移除成员 | 成员/admin/mute/owner/空群结果与语音成员撤除；撤权清理可处理已fenced目标 | M/J |
| `_on_group_mute@5698` | actor/GID及被授权成员UID | mutes或admins完整变更；新增目标权限查target gate/fence | M/J |
| `_on_group_slow@5752` | actor/GID | slow及slow_last相关运行状态整体变更，slow进入JSON | M/J |
| `_on_group_set_admin@5780` | actor/GID及被授权成员UID | mutes或admins完整变更；新增目标权限查target gate/fence | M/J |
| `_on_group_announce@5811` | actor/GID | 对应公告/模式/invite/name整字段变更；生成invite也属写 | M/J |
| `_on_group_ann_mode@5835` | actor/GID | 对应公告/模式/invite/name整字段变更；生成invite也属写 | M/J |
| `_on_group_invite_get@5861` | actor/GID | 对应公告/模式/invite/name整字段变更；生成invite也属写 | M/J |
| `_on_group_join_invite@5886` | actor/GID；新的member owner | 群创建或成员加入完整提交；邀请码校验关联计数保持，群快照字段必须标dirty | M/J |
| `_on_group_rename@5934` | actor/GID | 对应公告/模式/invite/name整字段变更；生成invite也属写 | M/J |
| `_on_group_about@5963` | actor/GID | groups.about完整内存更新；当前快照未含about，不虚称已持久 | M/N* |
| `_on_group_avatar_set@5986` | actor/GID共享头像资源 | 群头像文件与groups.avatar整字段效果；当前快照未含avatar | F/N* |
| `_on_group_avatar_del@6031` | actor/GID共享头像资源 | 群头像文件与groups.avatar整字段效果；当前快照未含avatar | F/N* |
| `_on_group_avatar_get@6063` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_group_file_list@6120` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_group_file_upload_start@6133` | 上传者/GID与新fid | group_files未完成记录、gf_seq和_gf_uploading一起登记 | M/J |
| `_on_group_file_upload@6167` | 上传者/GID/fid上传资源 | 偏移/大小核准→资源锁内锁外write→内存offset/完成状态，UID gate持到结束 | F/J |
| `_on_group_file_upload_done@6228` | 上传者/GID/fid上传资源 | 锁外实际大小核对后完整完成记录与上传标记移除；资源锁排序 | F/J |
| `_on_group_file_del@6293` | 合法上传者/群管理员/GID/fid | 共享元数据移除与文件删除效果按资源锁排序 | F/J |
| `_on_group_file_get@6328` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_task_add@6431` | 创建者/GID及assignee引用 | task_seq与完整task记录一起提交；合法成员/指派条件最终核对 | M/J |
| `_on_task_do@6470` | 参与者/已有task | done[A]完整更新，旧作者引用保留 | M/J |
| `_on_task_list@6501` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_task_del@6510` | 合法创建者/群管理员/已有task | 任务完整移除 | M/J |
| `_on_game_create@6679` | actor/共享RoomManager room | RoomManager的完整既有内存操作与事件结果；UID gate排序t0，事件发送在外，不改玩法 | G/N |
| `_on_game_join@6691` | actor/共享RoomManager room | RoomManager的完整既有内存操作与事件结果；UID gate排序t0，事件发送在外，不改玩法 | G/N |
| `_on_game_leave@6705` | actor/共享RoomManager room | RoomManager的完整既有内存操作与事件结果；UID gate排序t0，事件发送在外，不改玩法 | G/N |
| `_on_game_start@6725` | actor/共享RoomManager room | RoomManager的完整既有内存操作与事件结果；UID gate排序t0，事件发送在外，不改玩法 | G/N |
| `_on_game_sync@6737` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |
| `_on_game_action@6746` | actor/共享RoomManager room | RoomManager的完整既有内存操作与事件结果；UID gate排序t0，事件发送在外，不改玩法 | G/N |
| `_on_fish_score@6804` | actor/共享game积分 | _fish[game][A]完整更新；当前无即时persist也必须标dirty | M/J |
| `_on_fish_board_get@6826` | 请求者/原权限允许的数据或资源 | 只读访问最终核准；private owner fence/原资源权限保持，读盘/发送/审计在外 | R/N |

### 4B dispatch之外及直接分支的C矩阵

| 函数/路径（当前源码） | A/owner与完整候选C | 锁/IO/D |
| --- | --- | --- |
| _attach@1664、_release_zombie@1645 | 登录前fence；占用昵称解析后gate复查；新UID原子分配/映射/known/online。zombie清理只是旧端撤权，不能在退役后先注销再重建 | UID→Hub；旧端通知/关闭在外；JSON字段J |
| _pwd_claim/_pwd_store@1775–1794、set_password@1796 | 登录/改密服务器permit，派生完成后的known摘要最终C查fence；不允许put重建retired known | UID→Hub；PBKDF2在外；J；一般凭据CAS仍排除 |
| login_web@1726、_on_hello@2461 | attach、claim、Web token插入每个C都复查；实际token授权发布在Hub内。已attach未发token的端被t0撤销 | UID→Hub；welcome/audit/网络在外；token N |
| unregister@2094、_drop_xfers_of/_disconnect_rooms_of/语音名册清理 | 旧端身份已撤销时只执行可靠旧Session资源撤除；活跃UID正常注销保留PROFILE，pending/retired不得重建known | C/t0同UID排序；资源锁/Hub纯内存，网络/审计在外；相关字段J/运行N |
| _sweep_scheds/_sched_still_valid@1588 | 摘取非A/C授权；publish前creator gate，私聊还取receiver gate，完整检查fence+原屏蔽/群条件+bus历史及关联状态 | UID升序→Hub→bus；审计/route/persist请求在外；J |
| _bot_dispatch/bot_say@2787、bots提醒入队/摘取、agent_bot后台结果 | 用户输入消息按CHAT C；提醒owner入队C；bot_say以接收UID gate防迟到私有记录，受保护bot不是绕过目标屏障的理由 | UID→Hub→bus；bot/外部执行在外，最终J |
| _preview_ready@3198、_fetch_preview_worker | 网络/URL缓存不是作者身份写C；取得作者gate后Hub/bus查消息仍在和作者epoch，再整体写preview | 缓存锁释放后取UID→Hub→bus；网络在外；J |
| Web /api/login、/api/passwd、/api/logout | Web _session为原A，底层按上述attach/claim/token/pwd/unregister各C执行，不由HTTP返回代替效果授权 | 同底层规约；锁外HTTP写；J/N |
| Web /api/upload→_save_web_file@1307 | 服务器认证permit带owner到helper；独立tmp，FID body/meta最终发布及有效索引整体C；中央helper不能被无owner直接调用绕过 | UID→fid资源锁→Hub检查，Hub外IO；F/文件成功 |
| Web /api/events→_sse_loop@7557；whoami及GET touch | A后队列真正attach复查，旧closed/fenced端不续挂；detach只操作其旧队列。GET touch是运行写，不产生token/known | UID→Hub纯内存；SSE/读盘在外；N |
| Web直接history/export/file/avatar/group_avatar/moments/cover/vmemo/room及其它鉴权GET | 现有Session为A，取得数据访问权前检查fence和原资源权限。t0后无新访问授权，已经输出字节不声称追回 | R/N；磁盘/HTTP在外；公开/api/sticker保持原共享公开规则 |
| Web其它POST wrapper→dispatch | _session/dispatch为A，效果仍落到4A的每个C；200 ok不表示RETIRE D | 同4A；不全面改REST响应 |
| PING/STICKER_LIST/GAME_LIST/PADDING/重复HELLO/未知类型 | 前三为许可只读/应答，padding空操作，错误不获得业务权限；TTL touch不重建身份 | N；网络发送在外 |
| sweeper过期、burn完成、离线通知、房间tick与GC | 系统permit不是私有owner豁免；现有过期/撤权状态变更在Hub纯内存提交并标J/N，通知按可靠旧记录复查；不新建retired私有状态 | 内存锁规约；既有物理清理/网络在外；不新增广泛GC |
| _persist/_persist_sync/_persist_worker/_persist_flush；ServerStore.load/save | 无普通actor；唯一writer取得后capture，一份严格bytes与包含op_id清理证明，明确文件结果与acked/dirty | writer→Hub→bus采集；释放内存锁做磁盘；D见5.2A |

## 5. STORE-COMMIT 最小候选

### 5.1 运行态屏障与 UID gate

建议每 UID 一把 final-commit gate（多 UID 时按数值固定次序）。计算/网络 fetch/哈希/staging 可在 gate 外；实际效果提交必须获取 gate。
它不是覆盖整个 dispatch 的大锁。磁盘不可取消的最后阶段可持有 UID gate，但必须释放 Hub 锁；这允许 t0 在 Hub 外等待该 UID 已获准的 C 完成。
全局锁序为 **UID gates（数值升序）→必要资源锁→Hub.lock→bus._lock**；不需要资源锁的路径跳过该层。
writer 走 **writer→Hub→bus**，永不获取 UID/资源 gate；不得持 Hub/bus/preview 缓存锁后等待 UID gate、writer 或 IO。
资源锁仅限 fid/共享包/房间等并发效果的现有或必要保护；Hub释放后做IO，资源锁/UID gate仍保留以排序同一效果。
_attach 在 `_release_zombie` 及旧注销前检查 fence；preview 先识别消息作者，取作者gate后再在Hub/bus复查该seq；私聊due还要检查接收目标UID。
完整C包含关联状态，例如CHAT的bus消息与burn注册、投票消息与poll状态、语音消息与缓存登记在同一内存事务中提交，不能只把publish当作全部完成。
permit 必须由服务器 A 产生并绑定认证主体/私有 owner/退役 epoch，不能信任请求头声称的已接受状态。
已占用昵称先在 Hub 内解析 UID，锁外获取对应 gate，再在 Hub 内复查映射；变化时释放重试。尚无 UID 的首次分配和昵称占用在 Hub 内原子完成，
后续 claim/token 按实际 UID 取得 gate；不在持 Hub 时等待 gate，也不依赖预先猜测的下一个 UID。

1. 验证管理员和目标保护集；未配置必要 Store 时在 t0 **之前**拒绝本操作，不报永久退役，也不先做不可确认的逻辑清理。
2. 在 Hub 锁外取得目标 UID gate。已取得 C 的短提交/文件发布先完成；只通过 A 的慢工作尚无 C，之后被 fence 拒绝。
3. Hub 内纯内存 t0：记录 tombstone 和 runtime pending，撤销全部旧端/token，取消 sched/草稿/本人私有状态，清作者消息、移群并形成清理计划，递增 revision。
   与 bus 变更共同使用 `Hub.lock → bus._lock` 的固定顺序；不能在这块调用含发送/磁盘/审计的原 unregister/_burn_finish。
4. 释放 Hub。锁外关闭/通知旧端并处理既有运行资源；任何后续 unregister 均不得恢复 known。释放 UID gate 后，该 UID 的 fence 仍持续拒绝新 C。
5. 发起含 operation_id 的强制持久请求，等待 D；此时 pending/失败均不是成功。成功后发最终管理回执及成功清理广播；撤权通知可以在 D 前发送，明确只是运行态失效。

已经 C 的 CHAT 在 t0 后可能继续网络送达；兼容清目标作者历史，但不能收回字节和副本。
已经 C 的 CLOUD 文件替换可先完成，然后 t0 隔离其文件访问；只有 A/写好了 staging 的上传不得在 t0 后 replace 或发布元数据。
这是一组具体边界，不是“所有已接受操作都取消/都放行”的笼统承诺。受保护身份的正常功能及其它 UID 的业务继续。

### 5.2 一致快照、后台/force/flush 的顺序

建议沿用 ServerStore 全量 JSON + 同目录 tmp/replace，不引入数据库、WAL、全新云包或跨文件事务。

- 所有影响快照的纯内存变更在 Hub 提交区修改并标记 `state_revision`；bus 的 publish/edit/discard/clear 与 Hub 侧字段统一锁顺序。
  其它线程不能持 bus/传输子锁再等待 Hub。实现需给锁序核对；涉及群文件/READ-burn 的旧锁内 IO 必须拆到锁外，不把问题复制进新路径。
- 使用一把 writer 序列锁覆盖普通、后台、force、flush。取 writer **不得持 Hub 锁**；writer 不获取 UID gate，也不调用业务 handler。
  顺序为 writer→Hub→bus，仅采集深复制的内存状态；释放 Hub/bus 后序列化、磁盘 IO。没有反向 Hub→writer 等待。
- 普通队列只放 dirty revision/唤醒需求，不常驻可迟到 save 的旧 snapshot。writer 获得所有权后才捕获当前状态。
  在场旧 writer 可以先写旧状态；RETIRE 强制请求等待其结束，再捕获含 t0 的新状态，所以旧对象不能随后覆盖。
- 快照在同一内存边界复制 bus/Hub/retired；known.remarks、pins、burn、polls、tasks 等所有嵌套可变项须完全独立。
  runtime pending/Session/锁/线程/token 不序列化。候选按真正 `json.dump` 编码规则校验；fingerprint 不能以 default=str 掩盖实际编码失败。
- `ServerStore.save` 只在 temp dump、flush、fsync、replace 成功后返回成功 receipt；OSError/编码/其它必要阶段错误传播为结构化失败。
  receipt 记录 revision/内容标识/包含的退役 operation_id；只有确实成功候选推进 fingerprint、acked revision，标记对应 pending 为 durable。
- revision 只是顺序证据，**不能单凭 acked_revision≥目标值报告成功**；还须成功候选包含正确 tombstone/昵称占用及本次清理。
  捕获之后发生的新变更继续 dirty，成功写 r 不能把 r+1 的 dirty 清掉；无变化跳写只引用已确认相同内容的 receipt，RETIRE force 不以未确认指纹跳写。
- 失败保留内存 tombstone、pending、dirty，记错误类别而不记录正文/凭据；replace之前失败保留旧磁盘文件，replace之后未知结果按下面规则核对，不能假定旧文件仍在。
  不能自动解除屏障或把重试当首次新退役。
  无忙循环；管理员按同 op_id 重试/查询。后续普通成功快照若确实包含该 op_id，也可确认完成；异常关闭/flush 返回未确认结果。
- 不存在“仅单个 writer 就自动解决全部 handler”的捷径：其前提是第 4 节完整 C 和内存锁规约落实。多服务进程写同一目录不在本方案能力内，部署限制为单实例 writer。

### 5.2A revision、字节回执与未知结果状态机

以下为P2/P4/P7待审的可执行候选规约，替代仅列字段名的模糊回执：

| 阶段 | 精确规则 |
| --- | --- |
| 内存提交 | 每次**完整**快照相关C在Hub内事务结束时递增state_revision一次；关联bus/私有字段不能分开递增或先放行半个事务。无变化/纯touch/纯信令不递增。新增retire t0与全部JSON清理共一个revision；同op_id无新变更重试不新建身份/时间 |
| 捕获 | writer取得后在Hub→bus内捕获r及所有深副本，候选store_revision=r。旧JSON无revision时用0，恢复后递增；单进程恢复与分配检查不得靠时间戳排序 |
| 字节 | 在锁外使用严格JSON编码（UTF8、ensure_ascii=False、sort_keys=True、紧凑分隔符、allow_nan=False、不用default=str），生成唯一不可变bytes。编码失败是失败；实际写入的就是这份bytes，content_sha256=SHA256(bytes)，不能用另一种编码的MD5假冒 |
| 清理证明 | 候选校验retired[uid]的op_id/nick/cleanup_version、nick_to_uid占用、known/draft/sched/本人blocks/reads/群授权清理。receipt携带这份候选的retirement_proof（UID/op_id/tombstone摘要/清理版本与校验结果）；运行资源及CLOUD索引的清理计划另在t0状态中完成，不声称文件本体进入JSON |
| 文件阶段 | save报告stage：encode/open/write/flush/fsync/replace。只有所有必要阶段成功且候选清理证明有效才形成confirmed receipt；其字段为r、实际bytes哈希、含op_id的证明。Store文件锁之外不能再有另一个绕过writer的save调用 |
| ack | writer成功后短持Hub更新acked_revision/fp及对应op_id confirmed；如live_revision>r，仍保持dirty。后台更新和force请求共用这条ack路径；仅r≥目标不能证明该op完成 |
| replace前失败 | failed、failed_stage/error_code，旧权威JSON保持；不推进ack/fp、不清dirty或fence。同op_id重试获取**当前**完整候选，不能复用半写tmp或旧snapshot |
| replace后不确定 | receipt建立/进程退出等使结果不能确认时记unknown，fence保持。在writer所有权下严格重读权威JSON并验证实际字节hash/当前包含op_id与清理证明；确认后补ack，否则继续unknown/受控处理。不得回开身份或自动拿旧备份覆盖 |
| 回执丢失 | 若服务器已ack但网络响应丢失，服务器状态仍confirmed；客户端显示unknown并按UID/op_id查询。audit/通知失败另记元数据告警，不把已成功JSON反写成“持久失败”或恢复账号 |

### 5.2B 结构化load与部署初始化标记

为使“新目录/权威文件丢失”可执行，P7候选增加不含用户数据的 `<data_dir>/store.initialized` 标记，**不是退役意图/WAL**：

- load结果固定为 VALID_LEGACY/VALID_CURRENT、UNINITIALIZED、MISSING_DEPLOYED、CORRUPT、IO_ERROR、INVALID_MARKER；非valid不返回空dict给Hub继续认证。
- state存在且有效、marker不存在的旧部署：先严格恢复/校验全部身份约束，在Hub锁外原子写入+fsync初始化marker；marker建立失败则不开放TCP/HTTP认证。
- state和marker均无：默认为UNINITIALIZED，只有部署者明确执行 InitializeNew（正式Task须确认入口）且确认新存储目录时才初始化。先原子写有效空state，再写marker，全部成功后开放服务；不自动把已有数据目录认成新目录。
- marker存在而state缺失：MISSING_DEPLOYED，拒绝可写启动；state坏JSON/非对象/不可读或marker异常同样拒绝，错误诊断不含正文/凭据。
- 存在`.tmp`不改变判断，不自动提升其为权威快照。残留tmp隔离/报元数据诊断，由单writer或停服受控恢复清理，不能据此放行已丢失的state。
- 顺序必须为load→strict restore（retired/保护/映射/序号）→marker确认→CLOUD扫描过滤→开放认证。当前先CLOUD扫描的初始化顺序须调整。
- marker只防“已部署文件缺失被当新库”，不记录未成功退役意图；不能解决首次D失败后读取仍有效旧JSON的R05负例，也不抵抗marker与state都被人为删除/旧备份替换/旧二进制。这些仍按P3及受控恢复限制处理。

### 5.3 重启、失败与回滚的实际限制

| 状态 | 用户/运维可依赖的结论 |
| --- | --- |
| D 已成功 | 当前权威 JSON 含 tombstone/昵称占用和逻辑清理；真实读取该文件的新版本重启继续拒绝认领/访问；不等于擦除独立物理文件 |
| t0 已提交、D 失败且从未成功 | 本进程仍拒绝该 UID；磁盘可能还是活跃旧快照。没有 durable intent/WAL，崩溃/重启后**不能保证**阻断仍存在；必须先成功重试或停服受控处置，不能宣称永久成功 |
| 没有 Store | t0 前拒绝永久退役，提供明确未执行/无持久能力结果 |
| JSON 损坏/非对象/读取 IO 失败 | 按5.2B结构化load/marker fail closed；新目录须明确InitializeNew，已部署state缺失拒绝可写启动，不自动用tmp/旧备份补位 |
| 新版读取旧快照 | 严格兼容旧字段；没有 retired 字段不证明历史删号已成功退役 |
| 旧版读取新快照 | 旧程序忽略未知 retired 字段仍可能复活 UID；仅加 schema 不提供降级保护。退役实例禁止未审降级，修复版须保留约束；旧备份覆盖属于重新审查的数据恢复 |
| power loss/设备损坏/人工改盘 | file fsync+replace 的回执不宣称所有 Windows 存储层的断电持久保证，也不抵抗人工删除/旧二进制改盘；本批承诺和验收限成功提交后的进程重启，P3 确认是否需要更强要求 |

## 6. 冻结数据处理表（v1 待 Pro 确认）

“清除”指当前权威逻辑记录的清理及拒绝再读写；本表不批准真实操作或广泛物理擦除。

| 字段/对象 | t0 处理及成功 JSON | 保留/隔离边界 |
| --- | --- | --- |
| nick_to_uid、UID序号、新 retired | 保留旧名→旧 UID；新增最小 tombstone；序号不回退/不复用 | 无恢复/同名注册；不保留可认证密码 |
| Session、Web token、SSE绑定、运行资源 | 全部旧端撤权；按既有最后端规则移出房间/语音/传输/通知 | 不写 JSON；其它 UID/正常 KICK 新登录隔离保持 |
| known[uid] | 移除整个活跃记录（含 pwd/sign/avatar/invisible/status/remarks/last_online）；新旧注销不能重建 | tombstone 保留原 nick；头像本体可仍存在，不能说已擦除 |
| drafts uid|key | 清目标 UID 的全部草稿；读写拒绝 | 不删他人的草稿或客户端本地草稿 |
| scheds[uid]；已摘 due | 取消全部排队任务；迟到 publish 前拒绝 | 不回灌 due；他人 sched 保持 |
| blocks[uid]、reads[key][uid]、sticker_subs[uid] | 清本人屏蔽偏好/读游标/订阅运行偏好 | 保留他人 blocks 中旧 UID 引用、其它读游标；sticker_subs 原本不持久 |
| bot_reminders[owner uid]、Agent迟到结果 | 清本人提醒，最终 bot_say 拒绝向 retired UID 写私有记录 | 外部执行是否已完成不影响 fence；不宣称取消第三方已发生效果 |
| bus 消息 | 沿 ChatBus.clear_uid 清目标作者 UID 记录，seq 单调/索引一致 | 不删除对方私聊消息或整个会话；回复/转发/置顶中已有复制文本/旧引用可保留，不声称清尽所有出现内容 |
| groups.members/admins/mutes/owner | 沿现有删号规则移成员/转群主/空群解散 | 不借机改变正常离线退群语义；保留其它群/成员和独立共享库，不新增物理 GC |
| polls、tasks、group_files、fish_board | 保留共享主体、作者/投票/完成/分数的旧 UID 引用 | 保留共享内容不会重新授权退役人；群解散后已有独立索引/本体不猜归属擦除 |
| moments、moment_covers、评论/点赞 | 视为已发布共享数据保留旧 UID 引用与封面索引 | 禁止退役人再写；保留公共图片不等于私有账号仍有效 |
| pins、burn、共享贴纸/pack_meta | 按现有共享及TTL机制保留；作者消息清理不扩为所有共享副本删除 | 不顺手修全量 burn 格式；无法编码须返回提交失败（P7） |
| cloud[uid] / cloud/{uid}.bin | 清活跃内存访问索引，GET/PUT/final replace拒绝，启动恢复过滤 | 首批可留物理密文；不能表述数据已删除；格式/restore-import归属另审 |
| Web fid/meta、群文件/头像/媒体/贴纸本体 | 无可靠私有所有者索引的对象不批量猜删 | 合法共享用户的访问按原权限保留；停用退役端认证，孤立文件 GC另审 |
| audit、旧备份、用户下载/history/prefs/E2EE/.part | 不改写、不迁移、不远程删除 | 保留既有留底/副本，JSON逻辑清理不承诺其同步擦除 |

建议 UI：**“退役该账号：原登录名和 UID 将保留并禁止再次登录。取消服务器定时消息，清理本人草稿和活跃私有记录，移出群并清理本人作者消息。共享引用、审计、备份、云密文及下载副本可能保留；不提供应用内恢复。”**
请求发出只显示“已提交”；D 前显示“已阻断，等待持久提交/失败待重试”；D 后显示“退役已持久提交”。
沿既有 ERROR/deleted 扩展受支持客户端的手动登录收口，与 KICK 同样有旧回调代际保护；Web不自动新增退役按钮。

### 6A 运行资源与物理目录逐项规则

以下路径均为配置相对目录模板，未读取真实文件；它们不在当前JSON的全文件事务中。

| 实际字段/路径 | 候选处理 |
| --- | --- |
| _offline_notice_records[uid]；_typing_ts/_nudge_ts/_shake_ts | 取消目标UID待发通知/移除本人限速运行项；旧回调复查fence/记录身份，不恢复known或误发新身份下线 |
| _voice/_voice_ts、_vmemo/_vmemo_ts（按seq的共享媒体） | 不做按文件名猜UID的物理删除，按现有TTL清理；t0清作者消息元数据，退役端不能GET。其他合法共享访问按原权限；不把孤立seq缓存视为新身份依据，P6确认是否进一步回收可靠关联的缓存 |
| _burn[seq] | 可靠关联到本次被clear_uid移除的作者seq时，清其对应burn跟踪；其它作者消息的pend不把退役等同已读，不提前焚毁，按原TTL/机制处理，编码表示由P7确认 |
| rooms；voice_rooms | 按现有最后UID端离房/玩家离开/语音名册移除，空语音房回收；共享游戏/其他成员不改玩法或强制删整房 |
| xfers | 沿现有UID参与者传输取消/失效清理；body中转、直连客户端副本不声称擦除，保留FILE-AUTH权限与其它UID传输 |
| _preview_cache/_preview_inflight/_preview_lock | URL全局共享缓存保留TTL；不按作者删整缓存。seq回写先取作者gate，重查消息/作者fence；出网任务可结束但不再补目标作者记录 |
| web_files/{fid}与{fid}.json | 完成的共享文件保留；新upload独立staging在C前退役则不发布fid/meta。未发布临时文件隔离并记录可GC元数据，本批不猜旧fid归属批量删除 |
| web_files/cloud/{uid}.bin | 密文物理保留；独立tmp发布按UID gate，退役后无访问索引，启动过滤；不改blob格式 |
| web_files/avatars/{uid}.{ext}、g{gid}.{ext} | 用户/群头像本体保留，不作广泛GC；目标活跃known头像引用清理，共享群头像按既有群规则，写入必须经过C |
| web_files/moments/{filename}、moments/covers/ | 动态图片及封面是候选共享发布资料，保留索引/旧UID引用；P6明确moment_covers共享分类，不从作者UID推断物理擦除 |
| web_files/stickers/、stickers/_covers/ | 全局贴纸/包封面及引用保留；只清本人sticker_subs运行偏好 |
| web_files/group_files/{gid}/{fid}、_gf_uploading[fid] | 已完成共享元数据/文件保留；目标未完成上传停止C、撤掉未完成记录/上传标记并隔离已写staging字节；不得通过无归属GC删其它人完成附件 |
| state.json及store.initialized；独立audit/备份 | 当前JSON权威逻辑清理/部署标记，审计留底与旧备份不改写；受控备份/恢复必须保护退役约束，不能以marker声称强抗回滚 |

### 6B 管理结果协议与客户端乐观缓存

P4推荐具体候选（不新增MsgType/协议身份字段，仍待Pro确认）：

- `ADMIN_USER_DEL {uid}` 首次发起或对同UID重试；服务器生成唯一op_id，重复请求返回该身份的同op_id，不建立新身份。
- `ADMIN_USER_GET {uid}` 查询，管理员目标查找扩展到pending/tombstone；响应用既有`ADMIN_USER_INFO`附可选`retirement`对象：
  `{status:pending|failed|confirmed|unknown, operation_id, target_uid, target_nick, target_revision, committed_revision?, content_sha256?, failed_stage?, error_code?, retryable}`。
  不含密码/Session/token/私有正文；普通用户资料回帧契约保持。unknown只表示未确认结果，不能表述为已退役或已回滚。
- t0后先发pending/运行失效，D后confirmed。失败保留目标行的failed/重试入口；超时/响应丢失为unknown，先查询再按同op_id重试，不能靠HTTP200或请求发送成功判定D。
- 当前`ClientCore.send_admin_user_del`（2534–2555）会**在_send_frame前就pop本地known/roster**。候选必须取消这一步：发送失败不改缓存；pending只标状态，服务器真实roster撤权变化与永久结果分开；confirmed后才从活跃账号缓存收口并保留最小退役显示。
- Tk管理面两处旧删除确认/操作台（10112–10210）改准确范围及阶段；目标Core/Tk/Web识别ERROR/deleted停止旧自动登录，与KICK旧回调代际保护保持。Web只做既有失效/直接写入口改动，不新增退役按钮。
- 对外成功CLEARED/群目录及“退役成功”广播在confirmed后；撤权/实时状态变化可以先通知但不使用永久成功措辞。审计/通知失败不改变已确认JSON，另记录投递告警。

## 7. 实现切分、保留项与排除项

后续建议有限批次为 STORE-COMMIT → M1/FENCE → 私有清理/全写入面 → 客户端准确结果与真实重启验收。
这是同一 RETIRE 批次的候选内部分解，不能先宣布只有内存撤权的 RETIRE 已完成。
server.py 唯一写入者；必要 server_store.py/bots.py（仅提醒入口）与 Core/Tk/Web 狭窄接线；并行代码必须独立 checkout，合并后以确切候选验证。
沿用 CC-02A 的 PROFILE/RESTORE/KICK、SESSION-01/02、FILE-AUTH-01 和公共游戏生命周期保护；不重做已修功能。

排除普通认领/改密 CAS 与改密退出所有端、LOCAL/CLOUD 格式/跨服务器迁移、协议身份字段、游戏筛查/玩法、数据库/WAL全面改造、EXE/发布、真实数据、物理 GC。
如 P3/P5/P7 决定需要额外能力，先明确任务版本/必要文件和用户有限范围批准，不能从本资料验收自动扩权。

## 8. 需 Pro 决定的问题

| ID | 建议与必须回答的问题 |
| --- | --- |
| P1 提交边界 | 采用 UID final-commit gate + Hub纯内存最终检查，t0 等已取得 C 的效果完成；仅通过 A/哈希/staging的迟到任务拒绝。确认4A的119个handler和4B入口的完整C，特别是CHAT/burn关联、due私聊target、CLOUD、bot、preview；是否有必须保留的异步补写例外？建议不允许目标作者已被清理后补写 |
| P2 快照/锁序 | 采用UID升序→资源→Hub→bus，单writer→Hub→bus且从不拿UID/资源gate；force等待旧writer而非只清槽。确认完整C与5.2A的revision/strict bytes SHA256/receipt/dirty/未知结果，以及群文件和READ-burn锁内IO拆分的必要范围；替代方案须同样证明无旧覆盖/混合快照 |
| P3 耐久与首失败 | 承诺 fsync+replace 成功后进程重启保持，不承诺断电/介质损坏；首次D失败无 durable intent 时必须阻断本进程并限制重启/旧备份/降级。是否接受？若要求首失败后的自动重启仍保退役，应另批准 durable intent，而不能口头保证 |
| P4 结果与重试接口 | 确认6B：ADMIN_USER_DEL发起/同UID重试，ADMIN_USER_GET查询，ADMIN_USER_INFO.retirement四状态与op_id/实际字节hash；取消Core发送前乐观pop。旧客户端无回执不能显示永久成功，超时先查询，Web不新增管理产品面 |
| P5 保护集合 | 当前可证：默认/有效管理员保留名映射、活跃已认证管理员 UID、BOT_BY_UID。是否增加持久“曾认证管理员 UID”保护集、bot昵称预留？建议另明确历史管理员无角色证据、既有同名普通UID、未来bot注册/UID碰撞的拒绝/迁移规则；不得自动改真实映射 |
| P6 数据表 | 确认第6/6A节逐字段/目录：known整行/本人blocks/reads/sticker_subs清除，moment_covers作为共享发布资料保留，作者seq的burn跟踪清理、其它burn不把退役当已读，缓存TTL/未完成staging隔离；pins/转发副本/审计/备份/云密文物理保留。是否有必须调整字段？ |
| P7 loader/编码 | 确认5.2B结构化load、store.initialized与显式InitializeNew、tmp不自动提升、先restore再CLOUD。marker不是durable intent，不掩盖P3限制。burn.pend=set等编码不一致至少真实失败/待重试；如修可序列化表示先冻结精确兼容字段，不全面迁移 |

Pro 回答应逐项选择/补正，注明可进入实施的范围与剩余必须项；再由用户批准下一有限实施批次。
资料独立 ACCEPTED 不替代这次设计批准，也不表示 R1 里程碑通过。

## 9. 后续验收矩阵（未执行）

所有对象为合成数据/独立临时目录。竞态用 Event/Barrier 或可控回调暂停；固定 sleep 不是竞态证明。
每项记录 raw候选ID、屏障顺序、真实命令/退出/断言，模拟 IO 失败不能替代真实 JSON 重启。

| ID | 可控交错或场景 | 必须结果 |
| --- | --- | --- |
| E01 | TCP/Web免密/密码校验完成前暂停→t0→继续 | 拒绝登录，UID/token/known/密码不能重新建立 |
| E02 | attach前、attach后claim前、token插入前分别暂停→t0 | 每个最终提交点拒绝；已经建立的端在t0集合中撤销 |
| E03 | /api/passwd解析token后、PBKDF2完成后暂停→t0 | pwd写回不能复活known；非退役普通改密原语义不扩权 |
| E04 | dispatch A后暂停CHAT/DRAFT/SCHED/PROFILE/READ/REMARK各C→t0 | 各迟到状态无副作用；他人资料不变；只有A的permit不能绕过fence |
| E05 | C已完成CHAT，暂停网络发送→t0 | 不重发/恢复作者历史；已接受字节交付可能到达，界面不承诺远程擦除 |
| E06 | Web upload token检查后/staging完成后暂停→t0 | 不发布有效fid/meta，不返回上传成功；残留临时文件按隔离策略记录，不猜删旧共享文件 |
| E07 | sched due已摘出，暂停publish→t0→继续 | 无新seq/历史/路由；排队和已取任务都取消；他人due正常 |
| E08 | bot提醒入队前/due已取出/Agent返回前→t0 | 提醒不得新入队；bot_say不形成目标私聊记录；bot保护身份自身仍可用 |
| E09 | preview网络结束前→t0清目标作者消息→回调 | 原消息不复活/不广播新preview；他人消息可正常补写 |
| E10 | CLOUD临时写完、final gate前→t0 | 无replace、无访问索引、无CLOUD_DONE成功；旧密文访问隔离 |
| E11 | CLOUD已获得C，暂停文件replace→并发RETIRE | t0在Hub外等待；C先完成，再t0隔离；其他UID请求可通过Hub锁 |
| E12 | SSE认证后attach前→t0；旧ping/touch/重连 | 不重挂旧队列/不续授权；Core/Tk/Web收失效进入手动登录，旧回调不影响新账号 |
| E13 | 群文件chunk/done、头像/动态/贴纸各staging与最终索引间→t0 | 迟到提交拒绝；内存偏移/元数据不复活；Hub锁可供他人，既有合法文件权限保护保持 |
| E14 | 他人管理员/后台试图写retired目标known/私有记录，或加群/设管理员 | target fence生效；共享旧作者引用保留，无活跃身份授权 |
| E15 | 多端TCP+Web×2、快速旧注销、其它UID、受保护身份 | 全旧端/token失效；无known再建；正常单端logout/KICK允许重登/PROFILE/RESTORE保护不回归 |
| E16 | runtime关闭/传输/房间tick与t0交错 | 旧UID资源清理，不误伤他人/合法新端；系统共享tick不重新产生私有owner记录 |
| E17 | Web file/头像/群文件/动态图片/封面/vmemo/room等鉴权读取在A后暂停→t0 | t0后无新访问授权；他人原共享权限保持；已输出副本不承诺收回，公开sticker行为不变 |
| S01 | writer持旧快照已开始IO→排RETIRE强制→释放旧写 | 旧写先结束，新写后含tombstone；D后无旧snapshot覆盖 |
| S02 | 普通唤醒在force前/后，两个force和flush交错 | 同一序列所有结果可定位；无丢tombstone/倒序，shutdown等待与失败有结果 |
| S03 | capture时暂停bus/Hub变更与t0 | 一份候选的作者清理、groups、private、retired属于同一提交边界；不存在混合前后版本 |
| S04 | capture后原地改remarks/poll/task/burn等嵌套对象 | 已捕获候选保持独立，指纹/文件内容不被修改；新状态保持dirty |
| S05 | save(r)执行时发生新revision r+1 | r成功不清r+1 dirty；ack与含op_id内容绑定，不只比较整数 |
| S06 | 没有必要Store | t0前拒绝，未清状态，不报永久成功 |
| S07 | CHAT的publish与burn、POLL的消息与_poll、媒体元数据与cache登记各中间点暂停 | 不能暴露半个内存C给t0或snapshot；revision每个完整变更一次，writer不等待UID/resource锁 |
| I01 | 注入temp open/write错误、磁盘满 | 错误传播，旧JSON可读，UID仍pending/fenced，fp/acked不前进，无最终成功事件 |
| I02 | 注入flush/fsync错误 | 与I01同；不能以tmp有字节作为成功 |
| I03 | 注入replace失败/共享占用 | 当前旧文件保持，失败待重试；清理tmp失败不影响阻断或掩盖主错误 |
| I04 | 注入真实dump不可编码/异常快照 | 不用default=str假成功；明确失败/dirty/fence，无静默吞错 |
| I05 | 同op_id重试/并发重试；成功后响应丢失 | 幂等：同UID/昵称占用，不重复副作用；查询返回confirmed而非再执行/恢复 |
| I06 | 失败后普通writer提交含同op_id；或仍不含 | 只有确实包含清理/tombstone的成功receipt确认，未包含不得报成功 |
| I07 | replace已完成但receipt/响应/通知故障；先重读或重启查询 | 不能假称旧文件仍在或重开身份；unknown先查实际bytes/op证明，confirmed不被投递失败改写，no默认旧备份回滚 |
| R01 | 成功D后结束实例，真实state.json独立新实例启动 | 旧名/旧UID的所有认证拒绝；private清理保持，uid_seq安全、有效共享记录保持 |
| R02 | 重启扫描仍有cloud/{uid}.bin/头像/共享附件 | retired无CLOUD索引/GET/PUT，合法他人共享访问仍可用，物理保留如实说明 |
| R03 | 旧JSON无新字段，known缺失，UID字符串/计数边界 | 不虚构退役；不重复UID/碰撞bot；保留CC-02A恢复权限/禁言/已读行为 |
| R04 | 真实坏JSON/非对象/权限读取错误/非法retired映射 | 不以{}启动可写认证；明确启动失败/受控恢复，诊断不含真实正文/凭据 |
| R05 | 首次D失败后用旧JSON启动隔离实例 | 负例证明不能宣称屏障跨重启存在；记录运维限制，不把该风险写成已解决 |
| R06 | tombstone与active known/昵称冲突、管理员/bot记录被标退役 | 严格fail-closed；不静默丢tombstone、不重建受保护身份冲突 |
| R07 | 干净新目录、权威文件被外部删除、旧备份/旧程序降级 | 分别记录初始化/受控恢复/禁止降级边界；不把兼容旧JSON等同安全回滚 |
| R08 | legacy有效state无marker、两者均无、marker有而state缺失、marker创建失败及残留tmp | 按5.2B各结构化结果；无明确InitNew不空启动，marker建立失败不开认证，tmp不提升，restore在CLOUD之前 |
| U01 | 真Tk确认/提交中/IO失败重试/确认成功；Web失效 | 用词区分已提交、运行阻断、持久成功；ERROR/deleted也停止旧自动登录；不展示未授权物理擦除承诺 |
| U02 | admin发送False、pending、failed、超时unknown、响应丢失后查询confirmed | known/roster不在发送前pop；四阶段可辨，缓存按服务器事实更新，查询/同op_id重试幂等，不拿“已提交”代替D |
| G01 | 冻结合并后代码/测试/依赖的最终候选 | 领域集成、真实UI及项目逐文件全量；保留历史失败/原opt-in skip与真实exit，独立终审无必须项后才代码ACCEPTED |

本资料批次只做文档/边界检查。上述 E/S/I/R/U/G 全部是下一实施批次的验收要求，当前均未执行。
