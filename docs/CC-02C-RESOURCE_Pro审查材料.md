# CC-02C-RESOURCE — Pro 资源边界审查材料

版本 v1.1，2026-10-02（Asia/Shanghai）。**这是只读资料与未批准实施建议，尚无 RESOURCE 代码或测试结果。**
本文自包含审查目标、现状、候选、待决定项及未来验收；执行状态只见[指挥中心](AI_COMMAND_CENTER.md)。
资料授权见[RESOURCE-SCOPE Task](task-packages/CC-02C-RESOURCE-SCOPE.md)，有限实施建议见[RESOURCE-DRAFT](task-packages/CC-02C-RESOURCE-DRAFT.md)。

## 1. 基线、已经完成与本次问题

实际 HEAD `0bf1d2684d0b975603fb3ce7505459a9f282fc3a`，tree `51da8e1943428deda3c333a741a0d19cf1a76fdc`，branch codex/cc02a-consistency；接续 clean/index 空。
旧主控 idle，CORE、STORE及交付 Goal 已结束；成果已追加 Draft PR #5，未由本资料批次操作远端。
CORE v1.1 独立 ACCEPTED，115文件1392/0/2；STORE v1.1 独立 ACCEPTED，116文件1483/0/2。以上是历史同版证据，本次不复跑。
依据：[CORE决定](decisions/CC02-RETIRE_核心实施审查决定_v1.md)/[Task](task-packages/CC-02A-RETIRE-CORE.md)/[Review](review-packages/CC-02A-RETIRE-CORE-r1.md)，[STORE决定](decisions/CC-02B-STORE_设计审查决定_v1.md)/[Task](task-packages/CC-02B-STORE.md)/[Review](review-packages/CC-02B-STORE-r1.md)，[交付Review](review-packages/PR-DELIVERY-04-r1.md)。

已完成 M1 身份退役/UID昵称保留、认证、核心 CHAT/burn/DRAFT/SCHED/PROFILE、bot 用户 CHAT 输入与服务端 sched due 的最终 C。
STORE 已完成唯一 writer 后 fresh capture、严格一次 JSON bytes、typed IO、统一单调 ack、有限 unknown 对账及三种 confirmed 来源。
资源仍有自己的文件、元数据、队列和异步回写；**Store receipt 只证明 state.json，不证明 cloud blob、Web 二进制/sidecar 或后台任务结果完成。**
核心退役 confirmed 不可被改称资源擦除完成。首次退役 D 从未成功时旧有效 JSON 重启可能复活；marker/整体 loader/InitializeNew/durable intent 的补强仍归 CC-05。

本次只讨论 CLOUD 扫描/PUT/GET、Web upload/file、bot_say/提醒、Agent 后台结果、preview 回写。
不纳入 UI/客户端四态、CREDENTIAL、LOCAL/CLOUD 格式迁移、其它媒体/群文件分块传输/全部119、通用 UID gate、Store V2、物理 GC；P2P 文件参与者鉴权及既有核心实现保持。

## 2. 术语与审查不变量

- owner：资源或异步工作的来源用户；actor：实际执行写入/发布者（可以是系统 bot）；target：私聊 UID、群频道或尚未绑定频道的上传文件。
- A：入口认证/参数检查或后台工作启动；A 通过不等于最终许可。
- t0：现有 Hub 锁内记录 retired、撤会话/token、核心逻辑清理的屏障；即使 STORE failed/unknown，当前进程 fence 仍在。
- C：最后一次有权接受该资源发布/消息变更的短内存提交点，必须与 t0 使用同一 Hub 内存边界排序；异步消息 C 含 bus 的实际变更。
- D_resource：实际独立文件 IO 的确定结果。文件 C 与 D_resource 分开；已登记 permit、state.json receipt、HTTP 回包均不能代替文件成功。
- 访问 C_read：最后授权取得不可变响应内容或传输句柄的边界。此前下载可继续送达，不承诺追回已交付字节。

必须区分 `t0<C`（拒绝新发布/结果，无有效 fid/历史变更）与 `C<t0`（已接受工作可完成 IO/锁外通知；私有访问仍撤权）。
若要求 t0 后绝无物理落盘，现有 t0 不能独自提供此保证，必须增加排空/持久意图等另一批设计；本建议不隐藏这一差别。
不在 Hub/bus 锁内等资源锁、Store writer、网络或磁盘；资源锁不成为包住全部 handler 的 UID gate。

## 3. 静态事实与缺口

以下行号绑定本 HEAD，不表示资源行为已经验证。[server.py](../server.py)、[web.py](../web.py)、[bots.py](../bots.py)、[agent_bot.py](../agent_bot.py)是实际源码依据。

| 链路 | owner / actor / target | A、当前实际写点与锁/IO | 退役与保留边界 |
| --- | --- | --- | --- |
| CLOUD 启动 | owner=文件名 UID；actor=服务器；target=本人备份 | Hub 初始化 server.py:504–508 先扫描；`_cloud_load_disk`:5578–5594 读独立非空 `.bin`；623–641才恢复 Store 身份 | 只按数字文件名/非空/IO成功读入，不验证密文内容；扫描不查 retired，应在已有身份恢复完成后过滤，保留文件不等于允许读取 |
| CLOUD PUT | owner=actor=认证 sess.uid；target=本人 UID | `_on_cloud_put`:5596–5615 只校验 blob 大小，先改 self.cloud，再直接覆盖 uid.bin；OSError 被吞仍回 CLOUD_DONE | A后/t0后晚到可新建内存备份或落盘；当前“成功”不能证明磁盘，不应以资源 IO 失败回开身份 |
| CLOUD GET | owner=target=sess.uid；actor=认证请求者 | `_on_cloud_get`:5617–5627 从 self.cloud 取 blob 后发送，无独立最终 retired 检查 | 正常 dispatch 会筛会话，不能覆盖已过 A 的旧请求；需要 C_read，不把已捕获字节的锁外发送当可撤销 |
| Web upload | owner=认证 sess.uid；actor=HTTP服务器；target=尚无频道绑定的 fid | web.py:7177–7210 先读完整请求体/JSON，之后一次 token检查并解码；server.py:2178–2191 直接写 body/sidecar，sidecar不含 owner/target/op | 无最终 C、两文件非事务；owner身份应由 Session 给出，不信请求头；不把已存在共享文件全部按上传者清除 |
| Web file | owner=旧 metadata无法判定；actor=请求者；target=fid | web.py:7212–7243 仅 token+fid/meta/path 检查后读/写HTTP；server.py:2193–2210 验hex/readmeta/path | 当前有效认证用户持 fid 即可读，没有会话/群ACL。该既有共享语义及 legacy 无owner策略需要明确决定；fid不是身份凭证 |
| Web文件CHAT引用 | actor=发送用户；target=消息public/private/group；不以owner授权 | web.py:6683–6760透传file；server.py:3646–3663在核心C前读取sidecar并canonicalize，未查本体；3880–3907已有核心CHAT C | 当前缺本体仍能发布消息；本建议仅加完整发布资格桥接，不重写核心CHAT/频道授权或群文件库 |
| bot 回复 | owner=发起用户；actor=BOT UID；target=同用户私聊 | `_bot_dispatch`用户输入已CORE提交；`bot_say`:3946–3958 单独 bus.publish→route→persist，未拿Hub最终检查 | clear_uid仅清作者旧UID，BOT作者回复可在t0后新增并被STORE保存；已C的bot回复属于他人作者消息，沿保留表保留 |
| bot 提醒 | owner=msg.uid；actor=提醒BOT；target=owner私聊 | bots.py:76–93 append内存list；126–136 sweep摘due/替换list后逐条bot_say，当前无Hub序列化 | 与已修服务端 SCHED/due 不同；退役清owner未入C提醒及已摘due晚结果，普通离线仍可提醒，不按KICK取消 |
| Agent | owner=发起用户；actor=Agent BOT；target=owner私聊 | agent_bot.py:48–77 启动daemon后调用外部adapter，成功和异常都bot_say；只携to_uid | 不修改外部324项目/工具执行；最终拒绝回写不能保证取消已经执行的外部副作用；任务线程不跨重启恢复 |
| preview | owner=原消息作者；actor=预览worker；target=原消息频道/私聊接收者 | server.py:4302–4345 cache/inflight独立锁，网络锁外；回调只bus锁定位seq并写preview，然后route/persist | 作者消息可能已被t0清除，seq存在检查有部分保护，但没有与Hub fence完整排序；cache命中当前在preview锁内回调，未来引入Hub检查前须移出此锁 |
| preview依赖的edit/del | actor=现有编辑/撤回请求者；owner/target沿原消息 | `_on_edit`:4590–4640、`_on_del`:4651–4684只在find时取bus锁，text/edits/deleted赋值在锁外 | preview自己的bus锁不能与这些写原子排序；需要仅原消息查验/赋值/事件副本捕获的窄bus锁桥接，或收窄并发保证，不能以callback锁冒称已解决 |

ChatBus.publish/find/clear_uid 在 server.py:343–442；核心 t0/clear_uid 在5034–5227，snapshot bus/group_files 在702–778。
完成附件、其它用户消息、共享引用/副本、审计/备份保留；cloud与Web文件不属于该snapshot的原子事务。
Web群文件库的其它目录/handler及各媒体本体仅作为范围对照，不纳本Task修复。

## 4. 候选与建议

| 候选 | 行为/代价 | 判断 |
| --- | --- | --- |
| R0 仅入口 retired if | 不能覆盖A后迟到、吞IO成功、分离文件/索引；改动小但缺口仍在 | 不建议 |
| R1 有限资源串行与最终提交 | 只对cloud UID/Web fid建立资源操作，独立stage/typedIO/有限receipt；bot/preview短Hub→bus C；不变retired/Store JSON | **建议**，Q1–Q4决定后再冻结实施 |
| R2 通用UID gate/跨资源事务/持久ledger/物理擦除 | 要重构119/loader/格式与恢复，超出资料批准目标 | 延期，不能借资料验收开工 |

### 4.1 文件：staging、permit、发布、index与结果

采用 R1 的建议顺序：A认证→在不可服务的同目录随机 staging 中准备不可变 bytes→取得该资源串行锁 R→短Hub最终C检查/登记有限permit→释放Hub→实际发布IO→短Hub完成index/receipt→锁外响应。
R只锁 cloud UID 或新Web fid，不锁所有UID业务；同资源未知结果阻止该资源下一覆盖，不阻止其它UID/资源或STORE。
staging写全/flush/fsync/close成功后才进入C；短写/0进度/无效write返回失败。网络、哈希、文件读写和cleanup均Hub外。
按 `R→Hub→bus（仅需要时）`；t0不取R、不等R，只内存fence及私有可见index/待提醒清理。禁止反向 `Hub→R`。

**C是最终授权排序点，D_resource是IO完成点。** C<t0允许已接受文件发布完成；t0<C则不能发布最终可服务manifest/index，staging仅作临时残留，cleanup失败不得假成功。
Cloud uid.bin用一次os.replace发布，替换成功才更新self.cloud；t0后完成的旧permit可有IO receipt，但不重建retired owner的cloud可见index，visibility=withdrawn。
GET在短Hub C_read取得已确认不可变blob后锁外发帧；retired/身份损坏拒绝，其他UID不受影响。未知覆盖期间保留最后已证实可见版本，不把未知候选先装入cloud。

Web body/metadata先stage，最终body发布后**metadata manifest最后发布**；只有完整manifest和实际body匹配才能报上传成功/有效fid。
两个replace并非跨文件事务，manifest最后也不等于断电原子；body孤儿不通过file接口服务。新metadata可增加owner_uid/resource_operation_id及length/hash证明（不含私密正文），是否采用由Q2决定；不改云blob格式、不扫描迁移旧metadata。
在C后身份退役，已接受共享Web文件可完成并保留；未C上传无有效fid。新fid需唯一，不能覆盖已有已完成文件。
metadata发布成功但ack/响应失败记未知或已有confirmed，不能谎称磁盘未变或生成第二fid。读meta/文件和HTTP发包都在Hub外；最终C_read重查Session/fence及发布资格。
Web CHAT 引用的文件读取/校验仍在Hub外；已有核心CHAT C只检查准备好的完整发布资格，不等R/读盘。不得仅凭孤立sidecar发出有效文件消息。

资源结果是运行态 `{operation_id,kind,owner_uid,resource_key,status,io_effect,visibility,stage,error_code,length,sha256,origin}`。
`status=pending/failed/unknown/confirmed`只表示资源操作；`io_effect=not_committed/uncertain/committed`只表示本体/manifest效果；visibility另外取pending/available/withdrawn。
confirmed须文件实际确定成功，origin只能written/reconciled_current_resource；已合法加载文件仅可给恢复访问事实，不能伪造历史op回执。
retirement.origin沿STORE保持，资源字段不得塞入retired三字段或让resource confirmed伪装core D。

替换前确定失败→failed/可重试；替换尝试或成功后回执不明→unknown，先串行读实际bytes/manifest对账。
Cloud候选hash匹配才承认此次文件成功；只有已观察的合法前序且无冲突才failed；missing/读错/不解释/冲突保持unknown。Web需body与manifest同fid/op/hash/length匹配；仅body、仅manifest或tmp不算confirmed。
未知时不自动盲写/回滚/初始化/复用旧fid，查询纯结果不得顺手产生新操作；重试须同op同payload且不重复C或共享发布。多进程writer/人工文件修改不支持。
资源receipt不写永久ledger，进程重启op查询可返回result_unavailable，不能把NotFound当未提交或允许自动重放；已完成文件按有限访问证据继续可用。
**CLOUD unknown与同key覆盖屏障只在当前进程有效。** replace后/finalize前崩溃，重启会按非空opaque `.bin`恢复访问（owner未退役时），无法识别该文件是原unknown候选还是旧confirmed；不能伪造op receipt。unknown fence随运行态丢失，重启后显式新PUT可能覆盖它。本批不增加持久unknown ledger/durable intent，若要跨重启保留fence须CC-05另批。合法retired JSON后的私有拒绝保证仍独立成立；“GET只返回已证版本”指当前运行态，新Hub扫描仅恢复文件访问事实，不证明历史操作成功。
运行态只保留有界最近终态及必要未决记录；pending/unknown不得被普通淘汰而解除同key约束，达到owner配额在新操作A前拒绝，不读写盘。query不返回内容bytes/路径；owner失效后仅认证管理员可按明确owner/op查有限结果，仍不重新开放私有cloud。
精确同op恢复以调用方已知operation_id为前提。首请求省略op且所有响应丢失时，旧客户端可能不知道op/Web fid；本批不猜owner+kind最新操作、不以相同payload自动去重两个有意上传，也不承诺该请求可精确找回。无op重发是新请求，仍受同key unknown阻断；Web新fid可能形成两个独立已接受文件，这不叫同op重试或exactly-once。重启/淘汰更不能由文件存在伪造原请求回执，此限制须Q3认可。

### 4.2 bot/提醒/Agent 与 preview 的最终 bus C

bot_say新增有限上下文：owner_uid、target_uid、来源kind/请求seq（可用时）。actor固定BOT_BY_UID，不能以BOT保护绕过owner/target退役。
短Hub检查身份可用/owner与私聊target未retired→bus.publish整体C→释放锁route/persist；离线正常用户不因没Session被拒，KICK不变为永久fence。
提醒入队和sweep摘due在Hub短内存边界；t0逻辑取消owner未提交提醒，已经摘出的due仍走同一个bot结果C。
Agent只向本仓库hub.bot_say传有限来源上下文；外部adapter/network/子进程都Hub外，无需bot任务持锁等结果，也不承诺撤销外部执行。
已C的bot结果保持，t0后的新结果拒绝且不入bus/不route/不persist新消息；worker错误文本也要同门禁，不能异常分支绕过。
提醒t0清理是候选目标，当前CORE未清bot_reminders；bus C只说明本进程历史变更，不等于Store确认/重启结果持久成功。结果查询沿既有private history/seq；本批不为Agent/提醒创建永久作业ledger或跨重启job query。

preview cache读写/网络完成后释放_preview_lock再调用最终回写；共享URL cache可保留，不按退役用户清cache。
短Hub→bus重新定位seq、比对原author/channel/to和当前首URL，检查作者及私聊target fence、消息仍存在且未deleted/未已有preview，才整体修改并产生事件副本。
不新增持久消息revision：seq单调且worker不跨重启；消息删除/编辑URL/目标变化或t0胜出则丢弃关联结果，不误写其他同URL消息。
锁外route/persist；preview C<t0后通知可晚到，不声称网络撤回；原SSRF/public-address/DNS固定连接/拒3xx/TTL/失败静默降级保持。
必要窄依赖建议：`_on_edit/_on_del`仅将find/原权限与消息状态复查/纯内存赋值及事件副本捕获置于同一bus短锁，error/route/audit/persist仍锁外；不新增这两handler的retired门禁、不改编辑/撤回产品或授权，不扩119。preview以Hub→bus与此bus赋值排序，不允许bus内回取Hub。P02需Event同时验证edit/del先及callback先，而非仅顺序调用。此依赖须纳Q4与下一有限Task批准，未写任何代码。

## 5. 需 Pro 决定的最小问题

| ID | 需要明确选择 | 建议与未选后果 |
| --- | --- | --- |
| Q1 C/t0与物理IO | 是否接受C为短Hub最终授权，C<t0允许IO完成、C>t0无发布，私有cloud撤可见；core confirmed与resource结果分开？ | 建议接受有限排序。若要求t0后零物理写或退役响应必须排空所有资源，另批持久/排空设计，不能在Hub里等R |
| Q2 Web完成/legacy访问 | 完成共享文件维持有效认证+fid，还是要求会话/群ACL？新owner/op/hash metadata及body→manifest发布，legacy无owner/op怎样读？ | 建议本批维持完成文件既有auth+fid语义，legacy仅有效认证读取，不猜owner/不迁移；新未完整manifest拒绝。若需收紧附件ACL须另冻结来源引用/转发规则，不追认已修FILE-AUTH等于WebACL |
| Q3 资源回执/查询外表面 | 是否批准仅运行态资源四态、同op有限查询/重试及首无op全响应丢失限制，不修改客户端？ | 建议资源输入/输出统一独立resource_operation_id/resource_owner_uid；CLOUD_GET可选resource_query，仅confirmed用CLOUD_DONE，其它ERROR；Web新增GET resource_result，owner或明确owner/op的认证管理员查询；原INFO.resources仅runtime概要，不等IO，不与retirement.operation_id冲突，不伪造跨重启receipt。未批准前草案不得READY |
| Q4 异步owner/target、保留及窄锁依赖 | bot/提醒/Agent绑定来源owner=私聊target；preview绑定原作者/私聊target；t0后丢弃、已C共享保留、外部任务只禁本仓库回写，并允许edit/del纯内存bus锁桥接，是否认可？ | 建议认可四应用有限范围及两函数窄桥接；无取消外部324副作用、无重做SCHED/普通bot输入、无新增edit/del退役gate或全消息purge。若需删完成结果/传播撤回，另批决定 |

上述Q是待决定问题，尚无新Pro批准；独立资料ACCEPTED不代表建议被选定。用户下一有限Task批准是独立权限前置。

## 6. 建议文件、接口与未执行验收

有限应用建议仅server.py资源函数/初始化过滤/t0私有资源辅助/两个现有CHAT与管理查询接口的最小桥接、web.py upload/file/可选query路由、bots.py提醒、agent_bot.py上下文。
server.py另含仅为preview并发成立的_on_edit/_on_del纯内存bus锁桥接；不改这些handler的业务授权或退役门禁。
server_store.py、protocol.py、客户端、依赖、正式门禁、外部324、群文件分块与其它媒体不动。
建议测试仅三新增资源专项及tests/test_r37.py/test_r35.py/test_r46.py/test_r46b_web_fix.py/test_audit_preview.py/test_r26.py的必要夹具；test_r26仅preview相关hook，原投票等业务保持；原断言不弱化、不新增skip。
接口建议：`_resource_begin/session→ResourceContext`、`_resource_file_commit(ctx,bytes,meta)→ResourceResult`、`_resource_query(session,op)→ResourceResult`、`_resource_read(session,key)→immutable result`；只有限kind，不做通用handler封装。
内部operation_id只在ResourceContext/Result内使用；外部CLOUD/Web资源请求及resource对象统一resource_operation_id/resource_owner_uid，与现有退役顶层operation_id和retirement.operation_id完全分开。ADMIN_USER_INFO新增独立`resources={resource_owner_uid:目标UID,scope:runtime,operations:[资源摘要]}`，仅有限状态/IO/visibility/stage/error/length/hash/origin，纯内存不等R/IO，不返回正文/路径。明确管理员资源query可对账，但不重新开放retired本人blob。
异步桥接`bot_say(...,owner_uid/source_kind/request_seq)`、`_bot_reminder_enqueue/_take_due`及`_preview_ready(...,expected context)`；命名可微调，语义/锁序/失败/外表面须冻结。

**以下矩阵全部未执行，属于下一实施候选。** 每项需Event/Barrier固定源码点、超时释放/join及线程异常检查；不以sleep证明排序。真实IO用合成隔离目录/实际文件；不会打开真实用户资源或执行外部Agent工具。

| ID | 顺序/故障/访问 | 必须判据 |
| --- | --- | --- |
| F01 | CLOUD A或stage暂停→t0→C；反向C→t0→replace/ack | t0胜出无新index/成功；C胜出IO可完成但私有visibility撤销；receipt不冒充STORE |
| F02 | 同owner两个PUT，旧stage晚取R；不同UID并行；GET读边界交错 | 接受顺序由R下C确定，无旧完成覆盖新已完成；GET只有已证版本，不持Hub等R |
| F03 | CLOUD open/write短写/0/flush/fsync/close/replace逐点失败；replace实际完成后异常 | failed/unknown真实分类，旧index不先变；实际bytes匹配方补receipt，不能吞错CLOUD_DONE |
| F04 | unknown候选/已证前序/缺失/坏manifest/冲突/读错及同op查询/重试 | 同key未知不盲覆盖、其它key继续；错op/错owner无IO/无泄漏，query不创建新op |
| W01 | upload token检查/读body/stage→t0；C<t0完成两个文件 | 未C无有效fid；已C按完成共享策略保留，body孤儿不可读，不以JSON退役receipt替代资源成功 |
| W02 | body发布成功/meta失败、meta已replace但ack/HTTP发送失败、cleanup失败，调用方已知op | 两者同op/hash完整才成功；首错保持/有限unknown，已知同op重试不新fid，不服务不完整body |
| W03 | 无登录/失效token/新有效其它UID，合法/非法fid，legacy与新metadata | 按Q2冻结访问；路径穿越拒绝、retired session C_read拒绝，其他有效UID完成文件兼容 |
| W04 | file认证后读bytes前/读后C_read前→t0；C_read胜出后t0 | t0胜出不开始新授权交付，C_read胜出可锁外发送；不宣称追回已交付字节 |
| A01 | 同步bot响应准备后→t0；正常offline/KICK；错误分支 | 旧owner/target不新增BOT作者历史，BOT及其它UID可用，普通离线不误拒 |
| A02 | 提醒append前/摘due后→t0；并发enqueue/sweep | 无list覆盖丢他人提醒，无本人未C队列或迟到结果；服务端SCHED原实现不重做 |
| A03 | 合成adapter成功/异常结果→最终bot C前t0；C反向 | 两分支同门禁；外部执行只stub，不声称外部副作用已取消；已C结果保持 |
| P01 | 网络/TTL cache hit完成→preview C前t0，反向C先 | Hub→bus原子排序；t0先不patch/event，C先事件可晚到，cache保持 |
| P02 | Event使edit/del赋值先与callback先两向排序；原seq淘汰/编辑URL/deleted/不同目标/他人同URL | 窄bus桥接后只改匹配消息，edit/del已C则旧preview不patch；callback已C则保持其提交顺序，不清cache、不改原编辑权限/SSRF边界 |
| L01 | 持R暂停IO同时t0/CHAT/STORE快照；cache命中并发callback | Hub能独立前进，无Hub→R/preview锁→Hub或bus→Hub反向等待；IO及send/audit锁外 |
| J01 | 合成资源+有效retired JSON，新Hub启动扫cloud与完成Web文件 | restore后cloud retired不可见，不物理删除；合法完成共享文件按Q2可读，meta/本体非state事务 |
| J02 | C与资源IO中途结束，cloud已replace未finalize崩溃、缺Webmanifest/首STORE失败旧JSON重启 | cloud非retired owner可能读到扫描文件且unknown fence丢失，新显式PUT可覆盖；仅恢复访问事实无旧op receipt。记录孤儿/身份可能复活限制，不自动init/重放，不扩loader |
| J03 | 资源op进程重启后查询、旧uid/op/无权限查询、管理员明确owner/op查询及独立概要 | result_unavailable与未提交区分；core confirmed不表示资源完成，权限错配0IO，管理员对账也不重开私有访问，查询不泄漏路径/正文 |
| NO01 | 首无op且全部响应丢失，随后带已知op/无op重发、同keyunknown/并发/终态淘汰/重启 | 已知op精确查；未知op不猜latest/不自动合并相同payload，不声称恢复旧fid；无op是新请求且不能覆盖该keyunknown，不承诺exactly-once或旧请求可找回 |
| V01 | 新测试入场raw负例、稳定修绿、受影响领域、同raw最终逐文件全量 | 旧1483只是历史；新候选另绑定raw/命令/exit/skip/真实资源TCP HTTP JSON，独立实施验收再ACCEPTED |

未来实施测试、raw冻结/领域/最终门禁仅在下一用户批准范围中执行。本资料只做文档、源码版本边界与独立资料审查。

现有同URL inflight只绑定首个seq，后续同URL消息不订阅该次结果；本批保持此行为，不借修复退役回写扩大预览分发功能。deleted墓碑保留seq（server.py:4683），必须显式拒绝，不能只用find(seq)非空判断。

v1.1是独立资料初审必须项补正：preview窄锁依赖、CLOUD unknown运行态/重启边界、资源字段独立命名空间和19项矩阵同步。技术建议仍待Q1–Q4与用户下一有限实施批准，资料修订不扩大本批只读权限。
