# CC-02B-STORE — 有限实施 Task

版本 v1.1，2026-10-02（Asia/Shanghai）。用户当前聊天直接批准按最新Pro审查意见实施；状态/放行只见[指挥中心](../AI_COMMAND_CENTER.md)。
历史资料依据[STORE-SCOPE v1](CC-02B-STORE-SCOPE.md)/[Pro材料 v1](../CC-02B-STORE_Pro审查材料.md)；本实施以[最新决定v1](../decisions/CC-02B-STORE_设计审查决定_v1.md)及下述M01–M05补正为准。
Q1–Q4已有Pro决定，用户本聊天实施批准已取得；先独立Task预审，满足后在本有限批次连续实现，不覆盖CORE历史Task或重问子任务批准。

## 1. 基线、目标和权限

事实基线HEAD `df487cf18a0829fc0428a4ab640bcb0e24cc8866`，tree `0db5ddaa77de8d9a4cb3889a0f5a446e8c0893cd`，branch codex/cc02a-consistency。
CORE已修save真实True/False、actual writer后fresh capture、request_seq保护后到dirty；保持这些行为，禁止重复实施或回退。
目标只为严格一次bytes、真实阶段结果、captured-op receipt、统一单调确认、有限unknown对账/同op查询重试。
单state.json与现有retired `{nick,retired_at,operation_id}`不变；不新增持久revision/store_schema/cleanup_version、marker/初始化/loader状态机/durable intent。
运行态SHA只识别实际bytes，不宣称永久proof。当前首次失败重启限制、旧有效JSON恢复语义、数据保留表保持。

本批允许代码/测试、项目.venv隔离合成验证与必要资料；不得真实用户数据/设备。未授权commit/push/PR/merge/release、Pro或其它聊天消息、UI/资源或heartbeat。
下表为本批唯一允许的应用/测试写入边界；矩阵入场尚未执行，结果将绑定实际候选记录Review，不沿用CORE历史全量。

## 2. 冻结文件与符号边界

| 文件 | 有限改动及所有权 |
| --- | --- |
| server_store.py | 唯一backend：严格encode_state辅助/typed SaveResult与ReadResult、save_bytes、read_bytes_result；save(state)->bool兼容wrapper。load保持原接口/启动语义，允许仅记录已加载合法bytes的运行态前序标识，以及活动Hub绑定同一writer的兼容路径；不改整体loader/路径选择/初始化/恢复策略 |
| server.py | 同一backend：persist初始化运行态receipt；snapshot必要嵌套深复制及捕获的op来源，不改变业务字段；fingerprint/persist/sync/worker/flush共同提交与ack；retirement_payload/admin GET/DEL有限同op及单调状态辅助；restore只标已有合法retired来源和无旧receipt，不改整体恢复器 |
| tests/test_cc02_store_receipt.py（新） | 同backend专项：严格bytes/阶段错误/短写/unknown/receipt与Event矩阵；独立审查不参与编写 |
| tests/test_cc02_store_min.py | 最少旧save/fingerprint hook迁至唯一新seam并补强；旧fresh/dirty/顺序/坏retired/JSON断言全部保留 |
| tests/test_cc02_retire_core.py | 最少旧save失败hook兼容与同op结果补强；认证/t0/C/清理/保护/重启断言不弱化 |
| tests/test_server.py | 仅现有save计数/hook必要适配；快照隔离/节流/后台等业务断言保持，load坏JSON返回{}的旧契约不改 |
| 本Task/Review/必要决定/指挥中心/生成清单/PROJECT_MEMORY | 主控唯一文档；不与backend并写server.py。独立代理只读，范围有新文件需求先版本化记录，不泛泛授权任意tests |

禁止protocol.py、web.py、客户端、bots.py、资源handler、run.py/dev.ps1、依赖、游戏与技能代码变更。无需新worktree并行写核心，原分支/交付保留。

## 3. 内部接口与结果契约

以下冻结接口语义；最少私有辅助命名可普通调整并在Review说明，不能以重构扩大应用文件、行为或数据格式。

- `encode_state(state)->EncodedState`：严格UTF8不可变payload、length、sha256；一次dumps，无default/repr/替换字符，allow_nan=False、不排序、拒绝JSON键转换碰撞。只纯CPU、Hub外。
- `save_bytes(payload: bytes)->SaveResult`：effect committed/not_committed/uncertain，stage/error_code/retryable/length；Store只IO，不再编码，不靠truthiness。
  短write循环或失败；open→write→flush→fsync→close→replace；cleanup保留首错。replace尝试后无法证明效果记uncertain，receipt/网络错误不改已成功效果。
- `read_bytes_result()->ReadResult`：严格读取权威state.json原bytes，区分missing/read_error/bytes；不返回{}掩盖异常，不调用load，不读取tmp/备份。
  Hub有限校验器解析拒绝NaN/重复键，检查既有identity字段与本批核心清理；read/parse/verify失败均不覆盖权威文件。
- `ServerStore.save(state)->bool`保持wrapper；仅committed True。`Hub._persist(force)`, `_persist_sync`, `_persist_flush`现有外部形状保持；内部 `_commit_snapshot`（建议名）返回typed receipt/result供退役查询，永不把False等同必然旧文件。
- `CommitReceipt` runtime仅length/sha256/capture_request_seq/有限op集合与origin；不存第二份全量state，不入JSON、不记正文。未知对账只在必要窗口保留候选digest/有限校验信息。
- 统一 `_ack_commit`：actual成功候选的UID/op/nick/清理校验通过且与当前runtime匹配才confirmed；worker/sync/flush相同；后到request_seq不清dirty。
  失败只更新未confirmed同op；重复/迟到状态不可降级confirmed。编码/候选校验失败不得产生成功receipt。
- `ADMIN_USER_GET/DEL`沿既有MsgType支持可选expected `operation_id`；首次无op由服务器生成，已有无op兼容UID查询。带错op或错目标在副作用前拒绝。
  pending同op合并；failed同op显式重试；unknown查询先对账，重试也先查询。query不隐式写、不创建op。仅confirmed后使用现有持久成功通知。
  expected-op新增仅TCP管理帧；web.py:6929的HTTP user_groups只传UID，继续兼容返回服务器op。本Task不改Web接口转传或UI。
  Hub的_admin_user_payload锁外共用query辅助，覆盖HTTP直调与TCP查询的unknown对账；不能只在_on_admin_user_get做新逻辑。
- `retirement`返回已有字段，stage/error有限稳定类别；revision保持None，SHA仅有真实bytes证据时非空；重启来源已有合法retired可confirmed/SHA None，不伪造旧receipt。
  retryable专指重试退役写入：确定failed可True，其它三态False；unknown可重复只读查询，必须对账变为failed后才允许新提交。
  confirmed.origin必须且仅为written/reconciled_current_json/restored_valid_json；pending/failed/unknown的origin明确None。同op重复查询或迟到失败不得改写既有确认来源，origin不落入retired三字段JSON。

候选op校验至少：retired正确UID/op/nick、nick_to_uid占用；known、本人draft/sched/blocks/reads缺席；群members/admins/mutes/owner无旧权限；bus旧作者与其burn清除。
不清他人blocks旧UID引用、pins/共享副本/附件/moments/审计/备份；不把资源文件纳入receipt。校验据captured state，不以live检查代替。

## 4. 锁序、失败与重启限制

1. handler核心C/t0沿原Hub→bus纯内存。释放Hub后标请求/调用persist，不能Hub内等writer或进行网络/磁盘。
2. writer串行取得后，persist控制锁短读capture_seq并释放，再Hub→bus capture，释放后校验/编码/Store IO。
3. Store文件锁不回调Hub；save/read返回释放Store后，writer仍持有，短Hub匹配op补ack；persist控制锁短更新fp/dirty，不能持它等Hub。
4. 发帧、广播、audit在Hub/Store锁外；receipt与确认不因通知失败降级。维护已修旧槽/旧snapshot仅触发与fresh capture规则。

失败分类：encode/capture/verify及replace前确定失败→failed保留fence/dirty；replace尝试后不确定或ack无法证实→unknown；
unknown在writer内strict read，且须符合第8节M03；仅已知合法候选/后继同op及有限清理符合补ack，已知合法前序无op无冲突才failed；missing/read错误/坏JSON/有效但不解释或冲突继续unknown，不盲写、回滚或初始化。
后续普通writer若要覆盖unknown，先完成该op对账；损坏/缺失权威文件不能被普通自动重试覆盖。其它仍脏数据保留等待受控处理，不自建恢复策略。
恢复合法retired沿现有M1确认，不要求新schema；首次从未成功的t0仍可能在旧JSON重启后消失，无durable intent不补该保证。
外部第二进程writer、人工改JSON、降级旧版本、旧备份恢复、全系统断电保证均不支持；不借本批承诺资源/UI完整。

## 5. 未来验收矩阵（全部未执行，不是本资料结果）

使用有效合成输入和Event/Barrier停在具体源码点，禁止sleep代替排序。每个并发测试需限定超时、释放屏障/join、检查线程异常与无残留；
IO测试使用真实ServerStore及独立临时目录，替换真实IO点，不只stub总save返回False。保持当前CORE历史证据，本批新代码另绑定版本。

| ID | 场景/可控顺序 | 通过判据 |
| --- | --- | --- |
| B01 | 中文/嵌套remarks/正常int键/retired/burn列表真实编码 | 实际state.json bytes与唯一EncodedState完全相等，length/SHA独立计算一致；新Hub恢复正常，合法旧schema保持 |
| B02 | object/set/循环/NaN/±Infinity/非法UTF8字符串/JSON键碰撞 | encode阶段明确失败，旧权威bytes不变，fp/receipt不前进，退役fence保留；无default/repr偷偷成功 |
| B03 | 普通/force/flush/worker实际候选编码计数 | 每次实际候选只编码一次，hash和写入用同bytes；普通跳写只引用已有成功内容，force不冒充未确认D |
| I01 | open/write/flush/fsync/close各点真实失败 | 阶段准确、stable error/重试类别；旧文件原bytes保持、cleanup不遮首错、不报confirmed |
| I02 | short write / write返回0或异常 | 循环完整才成功，无法完整即write失败；不以flush/fsync成功掩盖截断 |
| I03 | replace前失败，或replace拒绝但旧JSON有效 | 不成功；uncertain经strict read得failed；旧bytes保持，tmp不当成D |
| I04 | 真实replace先完成→注入异常 | unknown→strict read核对实际bytes/op/清理→confirmed；不谎称旧file、不回开身份、不盲重试 |
| I05 | 成功replace→ack点异常/返回丢失 | 查询按已有receipt或strict read补confirmed；IO期间新request仍dirty；通知失败不改D |
| I06 | tmp清理/audit/网络send再失败 | 原IO阶段保持，实际成功receipt不降级，不暴露正文/路径/凭据 |
| E01 | worker取旧触发器→force新退役完成→旧继续 | 旧writer后fresh capture，不能覆盖新JSON；保留CORE已有Event回归并按新seam验证 |
| E02 | 旧普通snapshot/fingerprint晚入队、force与flush交错 | 只有触发器、不提交旧对象；最终bytes含最新op，request_seq不被错误覆盖 |
| E03 | snapshot后/encode中/IO中/ack前新request | 真成功只ack捕获内容，后来变更dirty保留并最终flush；不借递增capture_seq假称状态包含后到变更 |
| E04 | capture暂停→t0/核心CHAT-burn/private资料竞争 | Hub→bus没有半个核心提交，已修remarks深复制保持；IO注入回调可非阻塞取得Hub证明无锁内IO |
| E05 | force失败→普通后台成功含同op | worker统一ack使查询confirmed；不长期残留failed，返回真实bytes标识 |
| E06 | 同UID并发两请求，一成功一晚失败/响应交错 | 一个op/timestamp/t0，confirmed单调；不重复清理/新op、晚失败不降级 |
| O01 | 保存的候选op正确/错误/缺失或清理残留 | 仅captured-op+必要清理符合才确认；不得以live retired、hash相等或capture_seq大小代替 |
| O02 | 同UID expected错op、正确op、无op兼容 | 错op副作用/磁盘写0；正确返回同op；旧客户端无op路径保持，权限仍仅管理员 |
| O03 | 首次pending/failed/unknown/confirmed查询，TCP帧/HTTP user_groups双路径 | 字段准确；Hub共用辅助使HTTP直调同样对账，expected-op只测TCP；unknown先读不隐式重试，failed显式同op重试；普通非管理员不能获取管理结果 |
| O04 | 已ack成功但响应丢失、重复DEL后注入新save失败 | 服务器仍confirmed；查询返回原op，confirmed重试不降级，不因HTTP200认定D |
| O05 | unknown读错误/missing/NaN/重复键/坏JSON | 继续unknown，fence/dirty保持，无写/初始化/备份回滚；结果为read/parse/verify有限类别 |
| O06 | unknown实际文件已知合法前序无op/有效但不解释/异op或清理冲突/已知合法后继含同op | 只已知前序无冲突可failed/retryable；其它继续unknown不覆盖；已知后继含op可确认，SHA来自实际读取bytes，后到dirty保持 |
| R01 | 成功真实bytes→全新Hub→TCP/两个HTTP端/查询 | 退役UID/昵称/token仍拒绝，其它账号可用；same op，恢复confirmed来源明确且无伪造旧SHA |
| R02 | 首次失败→仍旧有效JSON→新Hub | 记录可能恢复旧身份的负例限制，不宣称解决；不自动marker/intent/降级回开当前进程 |
| R03 | 故障重试成功→重启→再次查询/DEL | 当前JSON含正确op与清理，UID/昵称不复用；返回一致confirmed，无新op/新数据迁移 |

应用阶段节奏：严格bytes/IO专项→统一receipt/并发专项→unknown/query/真实通道→受影响领域→冻结同raw源码/tests/依赖的最终逐文件全量→独立正式验收。
选测至少覆盖以上三个STORE测试文件、test_server、管理员凭据/安全、CC-02A PROFILE/RESTORE/KICK、SESSION与核心CHAT/DRAFT/SCHED领域；按实际diff调整并记录理由。
最终全量使用现有项目环境/隔离逐文件流程，UTF8、真实exit、独立basetemp、原opt-in skips与历史失败保留；新代码不能沿用1392/0/2冒称新结果。
核心存储变化必须新最终全量，静态/专项不能替代。独立审查从正式Task、actual diff、raw manifest/命令/日志检查，不由实现者自验。

## 6. 后续RESOURCE候选（本Task禁止实施）

| 类别 | 当前与后续最小核对/验收 |
| --- | --- |
| CLOUD | server.py:459–464扫描早于569的restore；4719–4738 PUT先改内存/直写文件且吞OSError仍CLOUD_DONE；4740–4750 GET无最终退役复查。后续owner最终C/隔离staging/真实独立IO结果；暂停PUT临时写→t0→不发布，重启按retired过滤索引；物理密文保留政策另决定。正常旧覆盖test_r37/test_r39b不替代迟到验收 |
| Web upload | web.py:7177–7210一次session检查后，server.py:1440–1451分别直写本体/meta；退役晚到及孤儿窗口存在。后续permit绑定UID、staging→最终C整体发布fid/meta，Event认证或暂存→t0→拒绝有效fid；完成共享文件保持。/api/file web.py:7212–7243读取另核；test_r46b_web_fix仅正常内容类型覆盖 |
| bot/Agent | server.py:2996–2999/3154–3169用户bot输入已受CHAT核心C；3187–3198 bot_say回复无target退役复查，agent_bot.py:69–77异步回写，bots.py:76–92/126–136提醒入队/已摘due。后续以目标最终C拒绝迟到私聊、本人提醒逻辑取消；三种Event分别覆盖提醒入队/摘due/Agent返回，不停用BOT或永久保留昵称。test_r35/test_r46只正常覆盖 |
| preview | server.py:3543–3572锁外抓取，3574–3584回调仅bus锁/seq存在检查，无作者退役复查。后续Hub→bus短内存最终C重查seq/作者/fence，外网完成可保留URL缓存；Event覆盖t0先/回调先及他人同URL。test_r26:368–394既有SSRF/缓存保持，不全局清共享cache |

以上是df487cf的静态只读事实与未来候选，未运行资源测试。RESOURCE的gate/IO排序方案须另冻结，不在本批增UID/resource gates。
RESOURCE必须另Pro必要决定/用户有限批准；UI、其它媒体/119均不由该候选表一次放行。

## 7. 执行和验收检查点

Q1–Q4/M01–M05按最新决定冻结，用户批准已取得。HEAD df487cf/index空、七旧资料dirty原字节均保存于_tmp_gui/cc02b-store-implementation/entry.json与entry-source；不自动pull/切分支。
主控唯一资料/测试调度；唯一backend仅允许表内应用/tests，独立Task/diff/证据审查不参与实现；已有资料代理都已结束，无项目应用/pytest进程，旧heartbeat PAUSED。先独立预审再放行实施，Goal持续至正式独立ACCEPTED、版本/资料边界及交付满足后结束；本批完成不开始RESOURCE或Git交付。

## 8. Pro补正 M01–M05（优先于历史草案措辞）

- M01：整份实际snapshot所有嵌套可变值与live独立；capture后修改live不能改变verify/encode输入。对当前进程需本批清理证明的op先validate捕获候选，失败不得调用save_bytes/replace，保留fence/dirty。历史restored_valid_json不借本批重证所有旧清理。
- M02：同一Store有未决提交时，统一writer的所有worker/普通/force/flush/活动Hub兼容save，在下一实际替换前必须先reconcile。失败不忙循环，保留dirty且暂停实际替换；其它被允许的内存业务可继续。兼容Store.save不能绕过Hub writer后fresh capture或未决约束，不新增第二writer/UID gate。
- M03：runtime只需最后真实成功/合法加载文件标识及未决候选证据，无永久ledger。actual bytes匹配未决候选且op/清理正确可confirmed；不同bytes必须可由已有真实提交证据解释为合法后继且含同op/清理才confirmed。可证明是已知合法前序、无本op且无身份/操作/清理冲突才failed/retryable；异op/昵称占用冲突/清理残留/有效但不解释/missing/读错/重复键/坏结构均unknown不可写。对账SHA/length来自实际读bytes，不复用失败候选；对账不能清后到请求。
- M04：取得writer→短控制锁读cutoff→释放控制锁→Hub→bus capture→verify/encode/IO→只ack cutoff；内存提交后再发保存请求。宁可冗余写，不在capture后取较大request_seq误清未保存变更；全路径统一单调ack、后台补成功、同op不重复t0/清理、旧失败不降级confirmed。
- M05：retirement.origin必填written/reconciled_current_json/restored_valid_json；前两者有真实本次写/读bytes证据和有限CORE清理，恢复仅保证既有合法退役记录。无旧receipt SHA/revision None，不serialize live假冒历史回执。不能扩UI/资源/坏缺loader/首次失败跨重启保证。

v1.1为独立预审的普通契约补正，没有扩大用户范围/应用文件/外部权限：

1. 活动Hub绑定的ServerStore.save(state)不得裸写。允许最少私有绑定到已有Hub writer/fresh capture/reconcile，传入旧候选不能直接提交；独立ServerStore保持bool wrapper。同一绑定Hub不出现第二writer/gate，低层save_bytes是唯一受协调IO seam，外部兼容调用不得绕未决状态。
2. known predecessor限定为当前进程真实成功bytes或strict合法加载bytes的运行态标识，且无目标UID/op/昵称/清理冲突；known successor必须有同进程真实提交证据，并含同op及完整清理。只有有效JSON/同op字段不是前后序证明；没有证据保持unknown，不从重启内存重新编码伪造。
3. 普通_persist只request/dirty/queue trigger，不在writer外snapshot/预编码；实际writer读取cutoff后做唯一capture/verify/strict encode/IO/ack。旧fingerprint若保留只复用严格编码语义且不参加两次实际编码流水。
4. ST02覆盖_snapshot_state的全部实际可变字段，除原示例还明确blocks、retired、fish_board/_fish、custom_stickers、sticker_pack_meta、moment_covers与group member任意嵌套值；uid/gid等标量不需伪造并发案例，候选独立断言不可只列少数字段。

纯payload组装与可能IO的query/reconcile分离，核对所有TCP/HTTP/内部调用栈的外层锁，任何Hub/bus/persist控制锁内等待writer/IO都是验收失败。
SaveResult显式effect，bool兼容wrapper只committed为True；短写允许正进度循环，0/负数/None/非整数等无效返回立即失败，不能无限循环；close在replace前、cleanup不遮首错。

## 9. ST01–ST12 补正验收组

以下12组由主控将完整可读Pro正文转为Task验收，不声称逐字复制未取得的sandbox附件；与第5节24项矩阵共同必测，均入场未执行。

| ID | 必须证据 |
| --- | --- |
| ST01 | 严格JSON键字符串化冲突/重复键/非有限值/非法UTF8/对象/cycle拒绝；成功actual bytes=EncodedState，独立SHA/length一致，只编码一次 |
| ST02 | capture后修改groups成员嵌套、reads/pins/burn/known.remarks/polls/drafts/scheds/stickers/group_files/tasks/moments/covers等实际可变字段，候选保持；verify中Event暂停后修改live也不污染 |
| ST03 | 捕获候选tombstone与known/draft/sched/blocks/reads/群权/作者bus/burn任一不清理，verify失败且实际save/replace调用0，旧权威bytes保持 |
| ST04 | open/write/flush/fsync/close逐实际IO故障，短写继续成功与0/None/负数/非整数失败；首错/稳定公开字段/旧权威/temp清理准确 |
| ST05 | replace拒绝和真实replace后包装异常、成功后ack故障/回执丢失；typed effect与unknown/confirmed来源诚实，不由truthiness假成功 |
| ST06 | unknown→未管理员重试→普通worker/force/flush/活动Hub兼容save；missing/坏JSON/read失败时均实际replace0、不忙循环/不清dirty、不持Hub等盘 |
| ST07 | 有效JSON同UID异op、昵称映射冲突、清理残留、合法但非已知前后序均unknown/不可重试/实际replace0；known合法前序才failed retryable |
| ST08 | 对账已知合法后继含同op且清理正确，origin=reconciled_current_json，SHA/length实际读取；失败候选digest不能冒用，后到未保存request仍dirty |
| ST09 | Event证明cutoff在capture前，snapshot/encode/IO/ack各窗口新request保留；旧worker/旧普通迟到触发/force-flush不提交旧对象，最后flush完整 |
| ST10 | 后台成功补confirmed、同UID并发一个op/t0、旧失败晚到不降级、confirmed重试不再清理；错expected-op副作用及IO0 |
| ST11 | TCP ADMIN_USER_GET/DEL及HTTP user_groups同状态查询/对账、权限/无码op兼容、origin字段；所有实际调用栈无外层锁等待writer/盘，网络audit在锁外 |
| ST12 | 真实合成JSON及加密TCP/双HTTP/新Hub重启，成功同op拒旧UID昵称token、他人可用；restored_valid_json/SHA None；首次失败旧JSON重启负例限制作实录；同版本领域/最终逐文件全量/独立正式验收 |

验收以实现不变量而非数量为准。新增测试先在入场raw+同版测试额外导出取得有效原红；原旧接口缺失可作功能缺失证据，不把所有错误冒称生产竞态复现。
稳定候选声明/静态语法/边界后才导出修绿，不在后台仍写应用时取WIP候选；失败/警告/环境与collection错误分开保留，普通修复先受影响项再领域，最后唯一同版full。
