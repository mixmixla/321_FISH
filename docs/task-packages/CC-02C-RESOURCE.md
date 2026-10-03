# CC-02C-RESOURCE — 有限实施 Task

版本 v1.1，2026-10-02（Asia/Shanghai）。用户直接要求按[最新审查决定](../decisions/CC-02C-RESOURCE_设计审查决定_v1.md)进行，有限实施权限已取得；执行状态/放行唯一见[指挥中心](../AI_COMMAND_CENTER.md)。
本Task优先于历史[Pro材料v1.1](../CC-02C-RESOURCE_Pro审查材料.md)/[草案v1.1](CC-02C-RESOURCE-DRAFT.md)的待决定、永久复用许可、IO真假与P02过强措辞。原资料正文不覆盖/改写。
先独立Task预审，M01–M04全部纳入后唯一backend按顺序实现；普通整改/选测/衔接持续到独立ACCEPTED，本有限Goal结束，不放行其它候选或Git交付。

## 1. 入场、目标与权限

工作区D:/Project/321_FISH，HEAD/base `0bf1d2684d0b975603fb3ce7505459a9f282fc3a`，tree `51da8e1943428deda3c333a741a0d19cf1a76fdc`，branch codex/cc02a-consistency；index空且原字节f88d8372…。
旧七Markdown未提交资料保持，资料Goalcomplete，本轮get_goal入场null、无项目应用/pytest/Git交付活动；不pull/切分支/覆盖。
392入场非ignored路径原字节已镜像`_tmp_gui/cc02c-resource-implementation/entry-source`，entry.json/index镜像绑定版本；原308源码/tests/依赖raw96e62366…保持。
CORE/STORE独立ACCEPTED及116文件1483/0/2是历史，不复做已修身份/CHAT/DRAFT/SCHED/PROFILE/bot用户CHAT输入/sched due/STORE。资源变化后另绑定新候选门禁。

允许四应用/冻结tests/必要文档、项目.venv合成隔离测试及真实合成TCP/HTTP/文件/JSON新Hub；不得真实prefs/history/audit/server_state/web_files/cloud/TLS/downloads或外部Agent工具/设备。
不commit/push/PR/merge/release、不外部/Pro/其它聊天消息、不恢复heartbeat；不改依赖/正式门禁/Store/协议/客户端/其它媒体/群文件分块/游戏。
不通用UIDgate/完整119handler/永久ledger/持久revision/云格式迁移/广泛物理GC。存储初始化marker/InitializeNew/整体loader/durable intent归CC-05；本批明确批准的resource_manifest_version仅识别Web新格式，不是初始化marker。首次Store未成功及资源unknown跨重启丢失限制保持。

## 2. 冻结文件和所有权

唯一backend拥有下表四应用与九测试路径；主控仅文档/原字节导出/边界与唯一验证调度。独立预审/代码审查只读，不参与编写。无需并行写同一核心或新worktree，当前分支交付保留。

| 文件 | 允许符号/最小变化 |
| --- | --- |
| server.py | Hub初始化有限资源runtime/已有restore后cloud过滤；_cloud_load_disk/_on_cloud_put/get及仅cloud dispatch参数；_save_web_file/_web_file_meta/_web_file_path及统一资格辅助；_on_chat仅Webfile canonicalize/已有C内存资格；_on_admin_user_del仅t0 cloudindex/提醒；_admin_user_payload仅runtime resources摘要；bot_say/_bot_dispatch仅结果context；preview三函数；_on_edit/_on_del仅find/原权限状态检查/赋值/事件副本窄bus桥接及必要资源辅助 |
| web.py | _upload/_file及GET resource_result路由/handler，原Session/Cookie/token复用，有限资源响应；PAGE/UI不动 |
| bots.py | _handle_remind/sweep_reminders只Hub enqueue/take_due与结果context，不改BOT UID/注册/骰子回声规则 |
| agent_bot.py | _dispatch/_run_async仅捕获来源context/成功异常统一bot_say；adapter/外部324不改/不实际执行 |
| tests/test_cc02c_resource_files.py（新） | stage/真实IO/manifest/atomic begin/attempt/receipt/query/CLOUD与Web Event |
| tests/test_cc02c_resource_async.py（新） | bot/提醒/合成Agent/preview与edit-del Event/最终上下文 |
| tests/test_cc02c_resource_integration.py（新） | 隔离真实TCP/HTTP/资源文件与state.json新Hub重启/访问/查询 |
| tests/test_r37.py/test_r35.py/test_r46.py/test_r46b_web_fix.py/test_audit_preview.py/test_r26.py | 仅新接口必要fixture/hook兼容及原断言补强；r26只preview，不改polls。无删除/弱化/新skip |
| 本Task/Review/新决定/中心/生成清单/PROJECT_MEMORY | 主控唯一资料，四旧RESOURCE正文/CORE/STORE/历史证据原字节保持 |

## 3. 文件操作、attempt与锁序（M01）

`_resource_begin`在短Hub内原子绑定认证owner/kind/op/key/输入身份，quota在任何stage前预留。Web初无op仅生成一次fid，后同op必须同fid/同R；输入身份包含payload bytes摘要及影响结果的name/kind等metadata，不能仅长度判断。
pending同op重复只返回已有结果/合并，不另执行/stage/fid；未知op或错误owner/kind/key/payload拒0资源IO；无op是新请求而非自动去重/旧请求恢复。
逻辑op可有多个明确attempt；failed显式重试R→Hub重新许可，复查owner/target/fence/原资源及前序。旧permit仅属那次仍在执行的attempt，结束后不可复用。
每key有限当前C身份/尝试序号足够；CLOUD op A失败后B不同op取得后续C，A retry返回superseded/conflict，不能写回A。确要再上传A须新op，不能借旧receipt覆盖B。
confirmed同op只查不写；unknown先对账不重写；pending唯一执行者。迟到attempt失败/完成须匹配当前attempt，不降级confirmed或覆盖后来index。
每owner最多16未终态、64最近终态（私有常量可预审收窄，语义不变）；pending/unknown不淘汰，容量满A前拒0IO，不影响其它owner；删除锁条目不能产生同key两R。

文件pipeline：A原子begin/quota→锁外不可服务随机stage/write-all/flush/fsync/close→R→短Hub最终发布许可C→释放Hub→body/manifest或cloud replace IO→短Hub结果/index→释放R→send/audit。
R→Hub，异步Hub→bus；t0不取/等R，只fence、私有cloud可见index及owner提醒纯内存清理。preview锁释放后才Hub，不bus→Hub；registry短锁不等R/Hub/IO。Store锁序沿旧实现，不在Hub/bus等Storewriter。
文件C为最终许可，不是IO完成：C<t0在途attempt可结束，cloud结果可confirmed/withdrawn，Web共享完成保留；t0后不开始新attempt，不承诺零晚物理写或退役排空。
哈希/编码/网络/磁盘/cleanup/send/audit/persist/query均Hub/bus外，C只纯内存检查/登记；正常KICK/logout/离线不变永久退役，访问Session规则复用已有辅助，不误伤新端。

## 4. 统一资源资格与部分效果（M02）

新Web sidecar固定`resource_manifest_version=1`，含fid/name/size/kind/ts及resource_owner_uid/resource_operation_id/content_length/content_sha256（精确命名可私有调整但外部op命名不变）。出现版本或任一新专属字段即按新规则，缺字段不得fallbacklegacy。
严格UTF8/JSON对象、拒重复键/非有限值/未知version/非法UID-op-fid/字段冲突；实际body长度/hash匹配声明和runtime操作identity才新资格，不能信请求published/confirmed/hash。
真legacy无新专属字段：仅既有合法fid/name/size/kind/ts、实际body存在与可验证长度，不补造owner/op/hash；有效认证+fid下载共享保持，不新增私聊/群ACL、不猜owner/扫描迁移。
上传/下载/CHAT共用同一实际资格语义。CHAT准备IO在Hub外，核心CHAT C仅查已验证内存资格；没有body/只有sidecar/partial/坏新manifest均不能成为有效CHAT附件。
新fid不覆盖旧文件。body先发布、manifest最后；body已发布而meta替换前确定失败=整体failed/not_committed，但disk有body孤儿，stage/error及部分效果须可解释，不能声称磁盘没变。
manifest replace尝试效果不明=unknown，先对账；完整body+manifest owner/op/fid/length/hash匹配才完整目标确认。可靠本op孤儿可沿原fid恢复，但须新attempt许可/原归属与冲突检查；只清本op自建temp，不扫描旧资源/广泛GC。
C_read交付已校验不可变bytes或同一已验证句柄，不能放下再按path重开；认证/retired/final资格短Hub检查，读/hash/HTTPsend锁外。t0先则不新授权交付，C_read先可锁外送达，不承诺追回已送bytes。
Cloud保持opaque `.bin`原格式，真实确定IO后才self.cloud；unknown候选不提前索引；恢复仅非空文件访问事实，已有有效retired JSON后过滤私有owner，schemafencefailclosed不扩loader。

## 5. 结果真值表、查询及重启（M03）

ResourceResult有限字段：resource_operation_id/resource_owner_uid/kind/resource_key/status/io_effect/visibility/stage/error_code/length/sha256/origin/retryable，资源op独立于retirement.operation_id。
visibility=pending/available/withdrawn/superseded/unavailable；最近许可C身份与当前已证可读index是不同运行态事实。后续不同op C即阻止旧failedop重试，但旧confirmed版本只有被后续已证可读版本替换才superseded；后续仅pending/unknown/failed时仍可保留旧已证GET版本。历史confirmed不是永远available，t0始终withdrawn，当前GET只对应当前可见已证index。

| 事实 | status / io_effect / origin | index / 重试 |
| --- | --- | --- |
| active attempt未结束 | pending / uncertain / None | 保留已证旧版本；重复合并 |
| replace前确定失败（即使旧bytes同候选） | failed / not_committed / None | 不把内容相同当本次成功；新attempt需许可/前序检查 |
| 完整实际写链成功 | confirmed / committed / written | 当前未retired且仍最新才available；回包失败不降级 |
| replace/本地ack效果不明，尚无目标证明 | unknown / uncertain / None | 当前key不盲覆盖，先query对账 |
| unknown读回满足获准目标（opaque前序与候选相同也可） | confirmed / uncertain / reconciled_current_resource | 仅确认目标内容，不证明某次replace唯一发生；解除内容未决但不伪written |
| unknown已证合法前序且目标未满足、无冲突 | failed / not_committed / None | 可重新许可同op；不自动写 |
| missing/read错/坏结构/无法解释/冲突 | unknown / uncertain / None | 不覆盖/回滚/初始化，query可继续 |
| 历史confirmed被后续已证可读版本替换/owner t0 | confirmed原io/origin不降级 | superseded或withdrawn；后续仅C尚未证实不冒称旧文件已不可读，admin不能重开私有index |

`not_committed`只指完整publication未完成，不宣称body无部分效果。reported serverunknown仅本地事实不明，不等调用端没收到响应；send/audit错误不改已证confirmed，旧callback必须attempt匹配。
query/retry先短Hub纯身份/op检查，错误owner/op 0资源IO；本人或认证管理员明确resource_owner_uid/op可查，不沿sharedfid给他人query权。query未知在R下锁外strict读实际资源、短Hub补结果，不隐式写/新op。
外表面：CLOUD_PUT可选resource_operation_id，CLOUD_GET可选resource_query/resource_operation_id/管理员explicitowner；仅confirmed CLOUD_DONE，pending/failed/unknown/unavailable ERROR有限资源字段，普通CLOUD_DATA兼容。
POST /api/upload可选resource_operation_id：confirmed200 ok/file，pending202/unknown409/IOfailed500均ok=false无file，参数400/身份403；GET /api/resource_result?resource_operation_id=&resource_owner_uid=仅owner/认证admin，查询有效200 resource状态，unavailable404不等未提交。
ADMIN_USER_INFO仅加resources={resource_owner_uid,scope:runtime,operations:[有界摘要]}，纯内存不等R/IO，无正文/路径/凭据，不改顶层/retirement op/四态/Storeorigin。admin对账只结果、不返回blob/不重开retiredcloud。
同op精确恢复需要已知op；首无op全响应丢失不保证op/fid找回，无latest猜测/payload自动去重/exactly-once。Web无op新请求可能另fid，不能冒称旧retry。
运行态op/unknown/fence不持久：cloud replace后finalize前崩溃，新Hub非retired owner可扫文件访问，无法区分旧unknown/confirmed，原op/fence丢失，新显式PUT可覆盖；不伪造历史receipt。Web完整manifest可恢复访问事实，不复建旧op ledger。有效retiredJSON私有fence独立；首次Store D未成功旧JSON仍可能复活，资源D不能代替durable intent。

## 6. 异步与preview（Q4/M04）

bot_say捕获owner=private来源用户、actor=实际BOT UID、target=用户；短Hub查schema/owner-targetretired→bus.publish C，释放锁route/persist。普通offline/KICK可用，bot输入既有CORE C不重写。错误回复同门禁，BOT保护不能绕ownerfence。
提醒enqueue/take_due/t0取消同Hub短内存边界，已摘due结果仍bot_say最终C，仍内存态重启丢失，不改服务端SCHED。
Agent成功/异常携同来源context交bot_say；外部adapterIO锁外，只用stub验证结果，不执行真实外部324工具/不承诺撤销副作用。bus C是本进程历史，不等Store/重启持久确认；结果查既有privatehistory/seq，不永久job查询。
preview cache/network完成先释放_preview_lock，再Hub→bus检查seq存在/非deleted/无preview、原author/channel/to/当前首URL匹配、author/private target未fence才patch/捕获事件，锁外route/persist。
del先deleted拒；URL当前变V拒；同URL周围文字编辑、U→V→U最终匹配允许；callback先C后编辑沿旧已有preview产品行为。本批无generation/客户端撤图，同URLinflight首seq/SSRF/DNS/TTL/拒3xx保持。
edit/del窄bus桥接只find/原状态与权限/赋值/事件副本；辅助若需Hub在bus外准备，不bus→Hub，错误/网络/audit/persist锁外。不扩两handler退休gate或原权限。

## 7. 冻结19矩阵及M子案例（本轮入场全部未执行）

Event/Barrier停明确源码点，超时/finally释放/join/线程异常断言；不用sleep证排序。实际IO故障注入open/write/flush/fsync/close/replace/ack，不仅stub总save；只合成目录/隔离Hub/TCP HTTP JSON。

| ID | 必测场景 / 判据 |
| --- | --- |
| F01 | A/stage/C→t0两向；在途许可可完且cloudwithdrawn；failed结束→t0→同opretry无新attempt/replace |
| F02 | 同owner两个PUT/旧stage晚首次C合法；Afailed→B新opC成功→Aretry superseded不能盖B；不同UID可用/GET只当前版本/旧callback不盖新index |
| F03 | cloud真实open/短write/0/flush/fsync/close/replace错误/实际replace后异常；前序=候选bytes时目标confirm+uncertain/reconciled，replace前确定failed仍failed |
| F04 | unknown候选/已证前序/missing/read错误/冲突；同opquery/retry/pending合并/错owner-op 0IO，新attemptfence/前序，confirmed不再写 |
| W01 | upload A/读body/stage→t0，C先允许共享完成；未C无有效fid |
| W02 | body/meta部分IO及meta后ack/send/cleanup失败；整体failed解释body孤儿；同op并发同fid/R/唯一executor/配额stage前一次预留；payload/name/kind不同0IO拒；可靠残留原fid重新许可恢复，confirmed回包失败不降级 |
| W03 | 无登录/失效token/其它有效UID共享fid/非法fid/legacy有限资格；新标记/新专属字段缺失、未知version/重复键/owner-op-fid-hash-length错不得降级；下载/CHAT统一拒缺body/不完整资格 |
| W04 | read bytes/验证后C_read与t0两向；C_read之后不可path重开，输出同一验证bytes；其他新Session不误伤 |
| A01 | 同步bot回复准备→t0/反向C先、错误分支，普通offline/KICK/bot其它UID保持，无旧BOT作者迟到历史 |
| A02 | enqueue/take_due/t0并发与已摘due，原他人提醒不丢，本人逻辑取消，SCHED不重做 |
| A03 | 合成Agent成功/异常callback→t0与C先，统一gate，不实际执行外部工具，已C结果保持 |
| P01 | 网络/cache hit两向C/t0，cache锁先释放，当前作者/target fence不patch/event，共享cache保持 |
| P02 | edit/del与callback窄bus Event两向；deleted/当前URL V拒，同URL文字edit/U→V→U允许，callback先C沿旧preview，不generation；淘汰/他人同URL正常 |
| L01 | R/IO暂停时Hub t0/其他CHAT/Store前进；无Hub→R/IO、bus→Hub、preview锁→Hub，所有send/audit锁外 |
| J01 | 合成bin/body/meta/stateJSON新Hub真实encryptedTCP/HTTP，restore过滤retiredcloud、完成/legacy共享按Q2保留 |
| J02 | cloud replace未finalize/不完整manifest崩溃、首Store失败旧JSON；如实扫文件访问/unknownfence丢失/可能身份复活，不伪旧op/不扩loader |
| J03 | op重启/淘汰unavailable，owner/明确adminquery/错op0IO，confirmed单调/历史superseded/cloudwithdrawn；admin概要无R等待/正文/私有访问复开 |
| NO01 | 首无op全响应丢失→已知op/未知op两支，无latest猜测/自动去重；同opfailed后t0不能retry，配额/并发/fid唯一，新请求不冒称exactly-once |
| V01 | 新tests入场raw有效负例→稳定修绿→受影响领域→真实资源TCP HTTP JSON→唯一新raw逐文件全量/原optinskip不增/原失败保留→独立正式验收 |

实现者不自行pytest/验收；主控唯一隔离export/选测/全量，稳定声明+语法+边界后取候选，源码正在变动不取WIP。每失败先受影响复测，原红功能缺失/夹具错误/真实竞态分别记录，原报告不覆盖。
应用/共享逻辑变化最终全量必须完成，不能引用1483/0/2当新RESOURCE通过；同版选测不重复，最终source/current/export逐hash一致/真实exit/原skip/env/原始log齐全。
独立Task/实际diff/原始证据审查无未关闭must、矩阵与边界交付全部满足才ACCEPTED；到有限Goal终点停止，无Git/数据/外部消息/heartbeat权限自动延伸。

v1.1为预审前实际规约核对补正：明确存储初始化marker与Web资源格式标记不同；分离latest许可（阻止旧failedop重试）与current已证可读index（GET/visibility）。没有改变Pro决定、四应用/测试范围或外部权限。
