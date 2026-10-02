# CC-02B-STORE — 最小剩余提交设计供 Pro 审查

资料版本 v1，2026-10-02（Asia/Shanghai）。**这是自包含的技术审查材料，未批准代码实施。**
事实基线：D:/Project/321_FISH，HEAD `df487cf18a0829fc0428a4ab640bcb0e24cc8866`，tree `0db5ddaa77de8d9a4cb3889a0f5a446e8c0893cd`，branch codex/cc02a-consistency。
本次入场 clean/index 空；远端 PR #5 同 head，open/draft/未 merge，main base `cc7e2951695041face3ea2451ef98a02d469d15b`。
以下给当前事实、推荐最小方案和需要 Pro 决定的边界；旧完整 RETIRE 设计没有自动转为当前需求。

## 1. 已有交付与本次问题

M1保留退役 UID/昵称占用，不开放同名重新注册。CORE v1.1 已独立 ACCEPTED：服务端 t0 撤权、核心最终C、本人私有逻辑清理、有效JSON重启拒绝旧身份。
同版最终115文件1392 passed / 0 failed / 2原有 opt-in skipped；37专项、276领域、14真实通道观察及失败历史见[CORE Review](review-packages/CC-02A-RETIRE-CORE-r1.md)。
这些是已完成的历史应用证据，本次未运行应用/pytest，资料验收不扩大其保证。

[Pro最新决定](decisions/CC02-RETIRE_核心实施审查决定_v1.md)已将完整 RETIRE 拆为 CORE、必要 STORE 剩余、RESOURCE、CC-05 存储加固。
本批只准备 STORE 最小草案；UI、CREDENTIAL、LOCAL/CLOUD格式迁移、整体119、游戏筛查、资源代码、物理GC不纳入。
marker/InitializeNew/整体loader/durable intent归CC-05。有效成功JSON不等于首次失败后崩溃仍可靠退役，不能因加receipt改变这一限制。

## 2. 当前源码事实（可直接定位到本基线）

| 事实锚点 | 已完成或剩余 |
| --- | --- |
| server_store.py:35–62 `save(state)->bool` | dump→flush→fsync→close→replace真成功才True；其它异常False并尝试清tmp。CORE已修真假成功；错误阶段/类别未返回。不能把“False总是旧文件”扩为replace已生效后异常的保证 |
| server.py:579–656 `_snapshot_state` | Hub→bus捕获核心内存，channels深复制、known深复制、burn.pend转既有恢复列表、retired独立字段。docstring仍称不嵌套是旧文字，实际代码嵌套；不新增另一锁体系 |
| server.py:1136–1144 `_state_fingerprint` | MD5另一次JSON，sort_keys/default=str，异常repr兜底；与save的严格程度/分隔符/顺序/实际bytes不同；NaN当前也可进入dump。该指纹是跳写提示，不能当实际字节回执 |
| server.py:1159–1239 `_persist/_persist_sync` | force与worker共享writer；sync取得writer后fresh capture，忽略旧state/fp参数，真成功后更新fp。request_seq保留捕获/IO期间新请求；不重做已修前置 |
| server.py:1250–1305 worker/flush | 槽只是触发器，writer后重新capture；失败dirty，flush同步重建。成功只推进fp/dirty，没有统一确认对应 `_retire_ops` |
| server.py:1844–1869 `_retirement_payload` | 已有pending/failed/confirmed及unknown默认文字、operation_id；revision/SHA占位None，failed_stage通常store.save。不是完整unknown对账实现 |
| server.py:4139–4152 ADMIN_USER_GET / web.py:6929 | TCP管理员按UID/昵称查询；HTTP user_groups直接调用_admin_user_payload且只传UID，两者返回已有retirement；没有expected operation_id核验 |
| server.py:4214–4360 ADMIN_USER_DEL | 同UID复用retired.operation_id，已confirmed普通重试直接返回；handler以 `_persist(force=True)` bool更新状态。后台之后成功可已含该op，而runtime仍failed；并发handler迟到失败仍需防止覆盖confirmed |
| server.py:901–907 `_restore` | 合法既有retired生成runtime confirmed；这证明恢复到有效已保存退役记录，无法伪造上轮bytes回执；坏/缺整体load仍是CC-05问题 |

必要剩余是**bytes与结果归属**，不应再写一套writer顺序/持久revision或逐119字段版本系统。
现有CORE已测encode/open/write/flush/fsync/replace旧文件保护；未来STORE必须补阶段结果、短写、close、replace后异常与ack丢失，不能拿原用例数量冒称这些都已测。

## 3. 推荐最小方案 S1

采用一份严格不可变bytes、一条writer提交/ack路径、少量运行态操作证据；保持单state.json、当前retired schema、现有writer/fresh capture/request_seq。
没有新增持久revision、store_schema、cleanup_version、初始化marker、WAL或durable intent；不要求全部JSON写入口新增版本CAS。

### 3.1 编码和内容标识

实际writer取得 `_persist_writer_lock` 后，沿当前Hub→bus捕获私有state及capture_seq；释放内存锁后生成有限退役候选校验，再严格编码一次：
`json.dumps(..., ensure_ascii=False, separators=(",", ":"), allow_nan=False)` → UTF-8（strict）→ immutable bytes。
不用default=str、repr或encode(errors=replace)；保持插入顺序，不启用sort_keys，以免混合int/string键排序形成无必要格式迁移。
只接受当前snapshot预期的JSON值和string/int非bool键；在编码前检查JSON键字符串化冲突，非法对象/set/NaN/Infinity/循环/非法UTF8编码均报告encode失败。
这是拒绝不可准确表示候选，不能静默递归改格式或改loader。legacy非法值会阻止本次保存；原有效文件和当前退役fence保持，问题需明确报告。

同一份bytes用于长度、运行态SHA256、实际二进制写入；不再由另一套default=str/MD5表示“已落盘内容”。SHA256只用于有限内容识别与对账，不是签名/防篡改或永久审计证明。
每次实际候选只编码一次；普通触发器可直接标dirty/唤醒，让writer编码后比较上次真成功字节标识。force/flush仍实际提交，不能用未确认fingerprint冒充D。
若保留 `_state_fingerprint` 兼容测试接口，它必须调用同一严格编码器，不成为第二种宽松内容语义；真实writer不再先fingerprint再重新dump。

SHA最小替代是保留上次成功bytes并做精确字节比较，语义等价但多保留一份全量bytes。推荐只留digest/length和有限op证据；不增加磁盘hash文件。
digest只是无变化优化；退役confirmed必须绑定成功候选包含的正确op与清理，不由hash相等或序号大小单独推出。

### 3.2 阶段结果与兼容接口

拟由server_store.py提供同一编码器、`save_bytes(bytes)->SaveResult` 和 `read_bytes_result()->ReadResult`（名称随最终Task冻结）。
SaveResult为显式结构：effect=`committed|not_committed|uncertain`，stage、error_code、retryable、byte_length；不能靠对象truthiness推断成功。
save_bytes只写这份bytes，检查完整写入（短写需循环至完整或失败），依序open/write/flush/fsync/close/replace。close也是replace前必要步骤。
每阶段单独归类；失败cleanup不能覆盖首个错误；错误只用稳定类别/errno，公开结果不包含路径、正文、密码或异常repr。
replace一旦尝试而结果无法证明，保守uncertain；例如真实replace后包装器抛错。普通OS替换前拒绝可经读取确认not_committed。
不增加目录fsync/平台发布耐久承诺；当前保证是这些调用成功后的有效JSON恢复，断电/文件系统/外部改写/旧备份回滚仍无额外保证。

保留 `ServerStore.save(state)->bool` 兼容wrapper：严格编码一次后调用save_bytes，仅committed返回True；False不再被注释解释为一定旧bytes。
Hub内部需要typed结果；现有 `_persist(force)`, `_persist_sync`, `_persist_flush` 兼容bool/None外形保留，退役改用统一receipt结果判断。
主程序退出日志或整体loader策略不纳入；现有save测试hook迁至新的唯一提交 seam时须保持原业务/时序断言，不删除测试或加skip。

### 3.3 receipt及operation确认

runtime CommitReceipt仅包含实际写bytes的digest/length、捕获request_seq（不是状态revision）、验证通过的UID/op_id/nick与有限清理结论。
没有永久receipt ledger；捕获state的校验在锁外纯CPU完成，针对CORE必要条件：retired匹配op、昵称占用、known/本人draft/sched/blocks/reads缺席，群权限与作者消息/burn已逻辑清除。
保留他人blocks中的旧UID、共享引用/附件/其它消息/动态/审计/备份；不查CLOUD或物理资源，不证明119写入面。
这组谓词使用captured state，不能用当前live retired重新检查替代实际候选证据，也不能仅凭capture_seq≥某数确认。

sync/worker/flush全部在writer所有权内用同一commit+ack：仅committed且候选校验有效，短持Hub匹配当前UID/op更新confirmed，再更新真成功fp与dirty。
IO和网络都在Hub外；随后返回/发帧。确认与网络通知、audit、广播投递分别处理：投递失败不能把confirmed改failed。
后台成功含先前failed op时必须同样补confirmed；普通跳写只有先前真成功receipt可复用，并明确其覆盖的op。
失败保留dirty与fence，不解除退役。confirmed对同一op单调，晚到失败/重复请求不能降级；本方案只保证单进程writer顺序。
同UID并发请求在t0短锁内合并成同operation，不重复清理或生成新时间；失败后显式重试也复用op。

### 3.4 unknown、查询、重试与重启

| 状态/情形 | 推荐处理 |
| --- | --- |
| pending | t0已运行阻断，尚无D。重复同op只查询/合并，不并发重做逻辑清理 |
| failed | encode/replace前确定未提交，或读取权威文件证明候选未生效。保留fence；允许同op显式重试 |
| unknown | replace/ack边界无法判断。先持writer读取权威bytes，对账后再决定；不自动回开或直接盲写 |
| confirmed | actual committed候选校验通过或unknown对账证明；网络响应丢失后服务器仍confirmed，只查询 |
| 首次提交失败→崩溃 | 无durable intent，旧有效JSON可没有retired；本批仍不保证重启阻断 |
| 成功JSON→正常重启 | 沿现有严格retired恢复确认；旧runtime digest/阶段丢失不伪造。revision/SHA继续None，可标明origin=restored_valid_json |

unknown专用读取不能调用吞错返回{}的load。读取结果区分read失败、missing、无效JSON、匹配、有效不匹配；parse拒绝NaN/重复键，验证有限核心op/清理。
同writer下读取，Store锁保护文件IO；不持Hub。先比捕获的实际bytes digest/length，并校验含op/清理；若另一次本进程写已经推进且含同op，可凭当前有效bytes校验确认，不要求旧digest相等。
读失败/无效/missing保持unknown并返回有限错误；不覆盖损坏文件、不回退旧备份、不创建新状态。有效JSON明确无该op才failed/retryable。
这里retryable专指再次提交该退役写入：确定failed可True，pending/confirmed/未对账unknown为False；unknown仍允许重复只读查询，不能用retryable绕过对账。
成功后ack前异常时可保留最后成功receipt让查询补ack；若不能证明则unknown严格读。捕获/IO期间后来请求保持dirty，读取/补ack不得清掉后到请求。

沿既有ADMIN_USER_GET/ADMIN_USER_DEL（MsgType不变）增加可选`operation_id`作为expected值：首次无op创建服务器op；已存在无op沿既有UID查询兼容。
带op必须与目标UID当前op相等；错op/目标不匹配在t0/持久化前拒绝，无副作用。query只读runtime confirmed/failed/pending；unknown可对账，但不隐式重试或创建op。
结果沿已有retirement字段：status、operation_id、target_uid/nick、failed_stage、error_code、retryable；content_sha256只在存在真实bytes证据时填写，revision占位保持None。
服务器known confirmed后响应丢失是调用端unknown；本批不改UI或新增客户端状态机，不宣称现有GUI会正确查询/停止乐观删除。
恢复合法retired仅确认恢复后的M1身份事实；无原bytes receipt时hash保持None。缺/坏整体loader问题不因增加查询接口得到关闭。
HTTP现有user_groups不转传operation_id；本批不改web.py，expected-op契约仅新增于TCP管理帧，HTTP继续UID查询兼容并返回服务器op。
unknown对账须由Hub查询辅助覆盖TCP与HTTP直接payload两条路径，放在_admin_user_payload锁外；不能仅修改_on_admin_user_get使HTTP永远陈旧。

## 4. 文件、锁序与实施切片

允许下一草案应用文件只为server_store.py、server.py的存储/退役结果辅助；新增专用STORE测试及最少旧hook补正。
不改protocol.py/web.py/client_core.py/client.py/bots.py或资源handler；不加依赖。详细符号与未来验证见[CC-02B-STORE-DRAFT](task-packages/CC-02B-STORE-DRAFT.md)。

固定锁序：writer→短Hub→bus捕获；释放Hub/bus后编码/文件IO；Store文件锁不反取Hub；ack在Store锁已释放后短持Hub。
persist控制锁只短持读取capture_seq/slot/dirty，释放后才等writer/Hub；不形成persist_lock→Hub与Hub→persist_lock的互等。
业务t0/最终C保持Hub→bus，释放Hub后调用persist；任何Hub内等待writer/网络/磁盘都是验收失败。
本次不引入UID/resource gates，不用Store作为所有handler包装器。

建议下一单批：S1严格bytes/阶段IO → S2统一receipt/单调ack → S3有限unknown对账及同op查询重试。切片属于同一个有限Task，先完成前片专项/独立阶段审再推进。
最终应用候选仍须相关领域、真实合成JSON/TCP/HTTP、冻结逐文件全量与独立验收；本资料批次没有执行这些未来门禁。

## 5. 需要 Pro 的有限决定

| 问题 | 推荐及替代/影响 |
| --- | --- |
| Q1 是否接受S1、不增持久revision/schema？ | 推荐已有writer+request_seq+实际候选op校验，覆盖本批必要确认。若要求跨进程/全119统一版本，须另冻结范围，不能直接扩本Task |
| Q2 严格bytes及runtime SHA范围？ | 推荐allow_nan=False/无宽松兜底、插入序、binary一次编码；runtime SHA只识别真实bytes。替代精确bytes比较；不增排序/永久proof/格式迁移。历史非法值保留失败，不静默修数据 |
| Q3 unknown的最小对账边界？ | 推荐仅replace/ack不确定结果专用strict read，错op拒绝，同op显式重试；missing/无效保持unknown，不覆盖。无需整体loader重构；是否接受此边界和首失败重启限制？ |
| Q4 confirmed证据与旧JSON恢复？ | 推荐当前写入有有限captured-op校验/runtime receipt；现有合法retired重启仍confirmed且SHA None/来源明确。无UI/资源完整承诺；如要求历史JSON全清理重新证明，须另Task |

Q1–Q4是推荐而非Pro已决定；普通措辞/文档整改自主完成。Pro必要决定落档后仍须用户批准下一有限实施Task，才可改应用。
本材料/草案自包含，用户可直接提供给Pro；Codex不发送Pro或其它聊天消息。本资料结束即结束Goal，不自动实施。
附带静态风险：_ensure_persist_worker首次启动检查没有单独互斥，可能创建多个daemon，但已存在writer确保文件顺序。
本最小资料方案不为此新增worker启动修复；若实施时出现独立故障证据，再另冻结必要改动，不能自行扩大当前草案。

## 6. 后续 CC-02C-RESOURCE（只列候选）

CLOUD独立文件、Web upload、bot回复/Agent、preview均不在本次JSON receipt覆盖内；CORE中的用户bot输入CHAT已在核心C检查，sched已摘due也已修，不重复列为未修。
后续须逐资源明确owner/接收方、prepare与最终发布C、退役排序、拒绝后的staging/索引处理及真正独立IO结果；不能把state.json成功当资源提交成功。
精确资源锚点与候选验收见[实施草案的延期表](task-packages/CC-02B-STORE-DRAFT.md)；不扩为全119、迁移或物理擦除任务。
