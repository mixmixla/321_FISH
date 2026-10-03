# CC-02C-RESOURCE — 有限实施草案

版本 v1.1，2026-10-02（Asia/Shanghai）。**PROPOSED，未实施，不能调度代码。**
本草案为[资料Task](CC-02C-RESOURCE-SCOPE.md)的交付，技术选择待[Pro材料Q1–Q4](../CC-02C-RESOURCE_Pro审查材料.md)决定，用户下一有限实施Task批准尚未取得。
状态与放行唯一见[指挥中心](../AI_COMMAND_CENTER.md)，不把本资料ACCEPTED当实施READY。

## 1. 基线和有限目标

HEAD `0bf1d2684d0b975603fb3ce7505459a9f282fc3a` / tree `51da8e1943428deda3c333a741a0d19cf1a76fdc` / branch codex/cc02a-consistency，资料入场clean/index空。
CORE/STORE已独立ACCEPTED，STORE同版116文件1483/0/2只作历史；源码不变的资料批次不运行应用/pytest。
目标建议：只关闭CLOUD、Web upload/file、bot_say/提醒/Agent和preview的迟到最终C与独立IO错误确认；不重复身份/核心CHAT/DRAFT/SCHED/PROFILE、bot用户输入或sched due/STORE。
M1 retired与昵称保留、state.json字段、Store writer/receipt/unknown/三来源保持；资源回执单独证明资源，core confirmed不升级成全部资源完成。

## 2. 建议文件/符号冻结与所有权

下表是下一批待批准的完整边界，本资料批次不写这些应用或测试文件。建议只有一个backend写四应用文件，主控只资料和隔离验证调度，独立reviewer只读。
并行写核心须另checkout/worktree及明确归属；当前保留原交付，不自动pull/切分支。

| 文件 | 唯一允许的建议改动 |
| --- | --- |
| server.py | `Hub.__init__`/`_cloud_load_disk`已有身份恢复后cloud过滤；`_on_cloud_put/get`及仅CLOUD query的dispatch参数；`_save_web_file/_web_file_meta/_web_file_path`完整发布资格/资源IO；`_on_chat`仅Web file canonicalize及已有C处内存资格桥接；`_on_admin_user_del`仅t0 cloud可见index/owner提醒逻辑清理；`_admin_user_payload`仅独立runtime资源概要；`bot_say`/`_bot_dispatch`只回复上下文；`_maybe_fetch_preview/_fetch_preview_worker/_preview_ready`最终callback；有限资源辅助和初始化运行态 |
| server.py窄依赖 | `_on_edit/_on_del`只将原消息find/权限及状态复查/赋值/事件副本捕获置于同一bus短锁，使preview并发检查成立；原参数准备/错误通知/route/audit/persist锁外。不新增这两handler retired门禁、不改业务权限或其它handler |
| web.py | `_upload/_file`及`do_GET`下新resource_result路由/handler，`_session`与原Cookie/token语义复用；HTTP响应字段可附加资源结果，PAGE/UI不动 |
| bots.py | `_handle_remind/sweep_reminders`改为Hub短内存enqueue/take_due，传回复来源；不改骰子/回声产品规则、botUID/注册/外部能力 |
| agent_bot.py | `_dispatch/_run_async`仅捕获有限来源context与交最终bot结果；外部adapter调用/导入/功能和324项目不改，不实现外部取消 |
| tests/test_cc02c_resource_files.py（建议新） | CLOUD与Web staged IO、receipt/query/访问/合成文件JSON重启及Event锁序 |
| tests/test_cc02c_resource_async.py（建议新） | bot/提醒/合成Agent结果/preview最终bus C，Event与保留边界 |
| tests/test_cc02c_resource_integration.py（建议新） | 隔离真实TCP/HTTP资源/退役查询/JSON新Hub，不执行外部Agent工具 |
| tests/test_r37.py/test_r35.py/test_r46.py/test_r46b_web_fix.py/test_audit_preview.py/test_r26.py | 仅新接口必要fixture/hook兼容与原断言补强；test_r26仅preview，不改投票业务，不删用例/弱化/新skip |
| 本正式Task/Review/决定摘要/中心/生成视图/PROJECT_MEMORY | 下一实施主控唯一必要Markdown；旧CORE/STORE/资料正文保留原字节 |

不改server_store.py/protocol.py/client_core.py/client.py/依赖/run.py/dev.ps1/正式门禁/外部324/其它媒体、群文件分块handler及游戏。
不增通用UID gate、永久资源ledger、持久revision/Store V2、云格式迁移、物理GC。
marker/InitializeNew/整体loader/durable intent仍归CC-05。测试新增三文件数量不是验收依据，实施正式Task可经预审收窄但扩大须再批准。

## 3. 建议内部接口/外表面

以下是R1候选语义冻结，私有命名可普通调整；Q1–Q4落实后须把选定接口写进正式Task，不能含糊放行。

- `ResourceContext`：运行态不可变owner_uid/actor_uid/target(kind,key)、operation_id、来源Session或worker、有限expected输入摘要；只支持cloud/web_file，bot/preview各用专用上下文，不可通用包装119。
- `_resource_begin(sess,kind,key,payload_identity)`：A检查/生成pending；请求身份来自认证Session，不信owner header；资源锁的获取在Hub外。
- `_resource_file_commit(ctx,payload,meta)->ResourceResult`：同目录不可服务随机stage，write-all/flush/fsync/close；R下短Hub最终C授权，然后锁外发布，短Hub完成receipt/index。只有真实文件成功才能resource confirmed。
- `ResourceResult`：operation_id/kind/owner_uid/key/status/typed io_effect/visibility/stage/error_code/length/sha256/origin，不含正文/凭据/路径。status四态只属资源；retirement.origin原样保留。
- `_resource_query(sess,op,explicit_owner=None)->result`：先纯内存验owner/op；仅本人或认证管理员明确指定匹配owner/op可查，错误0IO；必要unknown对账在R下锁外strict读本资源实际bytes/manifest，再短Hub匹配补ack。不新op、不写盘、不重开retired私有cloud，不在ADMIN payload里同步等R对账。
- `_resource_read(sess,key)->immutable response`：R外/内按实际IO准备后短Hub C_read复查身份fence/完整资格，锁外发送；cloud已证不可变bytes可直接短Hub捕获。不承诺撤销C_read后已送字节。
- `bot_say(bot,to_uid,text,kb=None,*,owner_uid=None,source_kind=None,request_seq=None)`：默认owner=private target，仅实际BOT_BY_UID；短Hub→bus C检owner/target退役与schemafence；不因正常离线拒。现有调用可兼容，Agent/reminder显式context；route/persist锁外。
- `_bot_reminder_enqueue/_bot_reminder_take_due`：纯内存Hub边界，t0按owner逻辑清理；已摘due仍经bot_say最后C。提醒仍内存态、不改服务端SCHED。
- `_preview_ready(seq,url,meta,expected context)`：释放preview cache锁后Hub→bus，检查匹配seq/原作者/channel/to/当前首URL，非deleted/已有preview，作者/私聊target未fence，才整体patch并捕获事件副本。保留现有单URL首seq inflight语义。

外表面建议须Q3批准：CLOUD_PUT可选resource_operation_id（首次无op服务端生成）；CLOUD_GET可选resource_query/resource_operation_id及管理员显式resource_owner_uid，confirmed才CLOUD_DONE，其它状态ERROR附resource_pending/resource_failed/resource_unknown/result_unavailable及有限结果，普通GET的CLOUD_DATA不变。
POST /api/upload可选resource_operation_id，正常confirmed仍200 ok/file兼容并附resource；pending202/unknown409/IO failed500均ok=false且无file，参数400/无权限403。GET /api/resource_result?resource_operation_id=只允许owner Session，认证管理员可额外显式resource_owner_uid匹配owner查询；查询成功200仅代表查询有效，resource.status表示操作结果，unavailable404不等于未提交。
资源外部serializer只用resource_operation_id/resource_owner_uid，内部ResourceContext.operation_id不得直接覆盖管理退役字段。ADMIN_USER_INFO保持原顶层operation_id及retirement.operation_id/四态/Storeorigin不变，仅加独立resources对象：`{resource_owner_uid: targetUID, scope: runtime, operations: [有限资源结果摘要]}`，条目仅resource_operation_id/kind/resource_key/status/io_effect/visibility/stage/error_code/length/sha256/origin。不含正文/路径/凭据，概要纯内存不等R/IO；需对账走明确resource query，管理员也不重开retired cloud私有访问。
不得新增MsgType或改客户端，查询字段缺省保持旧请求；TCP失败/未决只ERROR，不发送成功CLOUD_DONE。旧客户端不会接到“CLOUD_DONE但实际上pending/unknown”的假成功；Q3仍需决定查询字段和HTTP外表面。
op由服务器生成，仅同owner/同kind/同key/同payload identity可复用；错误op/目标/输入拒绝无副作用。不同新op同资源以R下C接受顺序串行，未知阻止该key下一覆盖。
精确重试要求调用方持有原op；首无op且所有响应丢失，不承诺原op或Web fid可定位。无op重发是新请求，仍受同key unknown保护；Web不同fid可形成独立重复文件，本批不做payload自动去重/owner latest猜测，不宣称exactly-once。恢复未知首请求需要后续明确客户端/请求身份方案，不能借资料候选暗加协议或UI。

## 4. 最终C、锁序与权限范围

文件链：A→准备不可变stage→R→短Hub C登记publication permit→释放Hub→publish IO→短Hub finalize→释放R→响应。
stage本身无可服务fid/index。C是最终授权排序，IO完成D是资源确认，短Hub finalize只补当前op/visibility，不借“第二C”改变已确定的先后关系。
`t0<C`不允许最终资源发布；`C<t0`已接受IO可完成。Cloud私有index在t0撤销且旧permit D后不重建；Web已C完成共享文件按Q2保留，不按owner全擦除。
此契约不保证t0后零磁盘写、不保证跨资源与state.json事务；如Pro不接受C语义，必须重版本化方案后用户另批准，不能偷换C。

锁拓扑：R→短Hub（文件），Hub→bus（异步/t0/snapshot）；t0永不获取R。preview cache锁只取/写cache/inflight，释放后才Hub；不持bus回取Hub。
Store writer及persist控制锁沿已验收顺序独立；资源C内不得调用persist/query/network/audit或等writer，资源完成后锁外只mark/persist既有业务变化。
R registry短锁只查建锁条目，不能持registry等R/Hub/IO；同资源只一写入者，metadata读文件及hash计算都在Hub/bus外。
normal KICK/logout与离线不是永久退役；不修改原核心A语义。本批请求最终检查聚焦retired/schema fence，Session/token访问规则复用现有身份辅助；C_read对已失效认证的拒绝不得误伤其他UID/新端。

## 5. 文件、失败、查询与重启规则

### CLOUD

只本人blob，保持opaque bytes与`.bin`格式。新PUT不能先更新内存再吞IO错；stage与os.replace后确定成功才更新已证index。
每key保留有限最近已证前序与unknown候选摘要，不存第二份完整Store；query读真实该文件bytes，候选匹配补resource确认，已证前序无冲突才failed，其余unknown不覆盖。
GET不返回未知候选，t0后拒私有访问；restore后有限cloud过滤不让retired UID重新进入可见index。文件可保留，retired_schema_invalid时该入口fail closed，不重写整体loader。
以上“unknown不返回/阻止覆盖”仅指持有该运行态记录的当前进程。cloud在replace成功但finalize前崩溃，新Hub会按非空opaque `.bin`恢复非retired owner的访问，不能识别它是原unknown还是confirmed；只给恢复访问事实，原op/unknown fence丢失，不伪造receipt，新显式PUT可覆盖。合法retired JSON的访问fence仍独立有效；跨重启保留unknown须持久intent/ledger，明确延期CC-05。

### Web

新fid不覆盖旧文件。body/meta stage写全/flush/fsync/close后进入C；body先发布，metadata完整manifest最后发布，访问只能基于完整manifest与body证明。
可新增owner_uid/op/length/hash metadata供资源关联，不变旧字段。body孤儿/partial/meta坏JSON不能成为有效fid，CHAT引用也不能仅凭sidecar；同进程以完成registry作短内存C资格。
本建议Q2维持完成/legacy auth+fid语义，不从bus存在性猜旧owner、不按retired作者物理删完成文件；若选择新ACL需另写精确owner/转发/历史淘汰保留规则及矩阵，不把当前草案称统一ACL。
新manifest读取只作有限字段/本体匹配，临时文件不服务；不扫描迁移旧sidecar。发布两个replace并非事务/断电保证，C后崩溃只要有效manifest完整可按Q2作为完成资源，不重建旧op receipt。

### 统一资源结果

encode/参数/stage/发布前确定错误→failed，typed io_effect=not_committed。发布尝试/ack无法确定→unknown/uncertain，保留同key未决，不先谎称旧file。
已成功body+manifest/单cloud replace才可confirmed；response/audit失败不降级confirmed。仅实际读bytes/manifest同op匹配可origin=reconciled_current_resource；written来自本次实际IO。
Web仅body或manifest、冲突/missing/readerror不可报成功；已证未完整且无冲突是否failed按原操作阶段证据判，不能将未知一概可重试。
staging cleanup锁外，只清当前op自建临时文件；cleanup失败保留首错，记录有限残留，不删legacy/共享文件或扩大GC。
重试同op同payload，failed才可明确重试；unknown先只读对账，无法解释不写。不同op不能覆盖unknown，同key排队有界/无忙循环，其他key和Store独立。
resource结果有限运行态，无永久ledger；重启/eviction后result_unavailable明确不等于未提交，不自动重新执行。新op再次PUT是用户显式新写，不借旧op自动重放；不支持多进程writer/人工改资源/旧备份回滚。
正式Task须固定小型owner配额/终态保留上限；pending/unknown不淘汰，不解除同key覆盖约束，owner配额耗尽在A前拒新操作/0IO，不影响其它UID。terminal淘汰只能影响旧结果可查询性；不得因锁条目移除让同key出现两把锁。
合法retired JSON重启维持身份/私有cloud屏障；首次Store D未成功旧JSON重启可能无retired，即使resource D成功也不能代替身份durable intent。
Agent/reminder/inflight preview均内存/daemon，不跨重启恢复；不执行/取消外部324工具，不宣称外部副作用撤销；已C的bot消息依现有作者/共享保留策略。
bus最终C只证明本进程已publish/patch，持久化失败时不能称Store/重启完成；bot/提醒/Agent结果查询沿现有private history/seq，preview沿原消息seq，不增加永久job状态或四态UI。当前CORE尚未清bot_reminders，t0清owner提醒是本草案待实施目标。

## 6. 下一实施阶段与未来验收

建议顺序：R1a 文件typed IO/staging/有限结果→R1b CLOUD scan/读写与Web接口/完整资格→R1c bot/reminder/Agent/preview最终bus C；一次有限Task内先预审再顺序放行，同一server.py写入者。
具体阶段仅在Q1–Q4决定及用户正式Task批准后可READY；本资料只完成草案。
下表与[Pro材料F01–V01完整矩阵](../CC-02C-RESOURCE_Pro审查材料.md)共同冻结，**全部未执行**。

| 组 / 矩阵 | 下一批必须证据 |
| --- | --- |
| RC01 / F01–F02 | Event精确停A/stage/C/replace/ack，t0先与C先、同owner晚取R/不同owner/GET真实排序；不借sleep |
| RC02 / F03–F04 | 实际open/短写/0/flush/fsync/close/replace/写后异常；候选/已证前序/missing/readerror/冲突unknown，错op/owner零IO、同opquery/retry |
| RC03 / W01–W02 | 实际body/meta双文件中间故障与已replace后响应丢失；无成功fid/无孤儿访问/单调receipt、首错cleanup |
| RC04 / W03–W04 | 无登录/旧token/新端/其它UID、非法fid、legacy/newmeta、body缺失CHAT拒；Q2完成共享保留；t0/C_read两向授权与响应 |
| RC05 / A01–A03 | 同步bot、enqueue/sweep/已摘due、合成Agent成功/异常两分支；owner/targett0后不新增BOT作者历史，普通offline/KICK/其他UID及已C结果保持 |
| RC06 / P01–P02 | 网络完成/cache hit最终C两向，edit/del窄bus桥接Event两向；deleted墓碑/seq淘汰/编辑URL/target/同URL其他消息，原编辑授权/SSRF/DNS/TTL/拒3xx与首seqinflight不回归 |
| RC07 / L01 | 资源锁/IO停住时t0、其它CHAT/Store能够前进；cache hit无preview锁→Hub，Hub不等R/IO，bus不反向Hub；线程异常与join无遗留 |
| RC08 / J01–J03 | 真实合成bin/body/meta/state.json，新Hub/encryptedTCP/HTTP读取；restore过滤与完成共享、unknown/孤儿/首Store失败限制、重启op不可用与无越权查询 |
| RC10 / NO01 | 首无op响应全部丢失、原op未知与已知两支、并发/终态淘汰/重启；无latest猜测/payload自动合并/旧fid恢复或exactly-once假承诺；同keyunknown不可覆盖 |
| RC09 / V01 | 新tests在入场raw额外导出有效负例；稳定声明/语法/边界后修绿；受影响域；唯一新候选同raw逐文件最终全量/原opt-inskip不增/原失败保持；独立正式实施验收 |

并发测试均限定超时，finally释放Event/Barrier/join及断言无线程异常；真实IO只合成隔离目录，Agent外部工具仅stub最终结果。
不复制真实数据、不运行真实应用/pytest直到用户下一批授权；新候选代码变了不能拿1483/0/2冒称新资源验收。
普通实施整改可在正式批准范围内自主推进，应用文件/接口/资源类别扩大须重版本化及批准；Git交付/合并/发布/真实数据/外部消息/heartbeat分别另授权。

## 7. 进入正式Task的前置与资料终点

Pro至少回答Q1 C语义、Q2 legacy/共享访问及metadata、Q3兼容查询外表面、Q4异步保留；主控归档决定摘要，形成正式有限CC-02C Task并独立预审，用户批准下一有限实施后才开工。
本草案不将未决项算资料阻塞：材料和待决问题完整、独立资料审查无必须项、七文档版本边界/投影通过后结束资料Goal。
不自动发Pro消息、提交或开PR；资料ACCEPTED不等于实现通过、整个RETIRE/R1、merge或release。

v1.1来自独立资料初审；只补窄preview依赖/重启限制/独立资源字段和19矩阵，不授予当前资料批次应用/测试写入或Git权限。Q4需认可edit/del窄桥接，下一正式有限Task与用户批准须包含它，不能因本草案自行开工。
