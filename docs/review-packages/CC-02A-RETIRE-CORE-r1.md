# CC-02A-RETIRE-CORE — 实施与独立验证 r1

2026-10-02（Asia/Shanghai），对应[Task v1](../task-packages/CC-02A-RETIRE-CORE.md)。状态只见[指挥中心](../AI_COMMAND_CENTER.md)。
用户已直接批准按[Pro审查结论](../decisions/CC02-RETIRE_核心实施审查决定_v1.md)实施；不使用原完整RETIRE DRAFT一次覆盖119 handler。

## 决策与入场

来源链接网页只返回登录页；Codex只读“项目接管审查”的对应最新Pro回答已取得，选定回答本机原文SHA256 `0ad7e455d788350d853858e4d73f78c1f161f21d1ef2e2c9bfef43f3b06d6197`。
不入库私有聊天全文，仅保存决定摘要、批准来源及实现映射。审查要求收窄核心server.py/最少store/tests，UI、资源、整体loader/marker延期。
正文CORE-before-STORE与persist receipt存在依赖：本批只包含失败传播/写顺序两项必要前置，完整Store V2/持久revision/hash-proof/初始化系统不纳入。

HEAD fc9c991bed82dc969aefdbfc9a77a46e75bde5d5，tree ba45f96a9de7a55c91b8150eacd78aa6740fe95c，branch codex/cc02a-consistency，index为空。
371入场非ignored原字节已镜像到_tmp_gui/cc02-retire-core/entry-source，entry.json保存路径/hash/版本/index；305源与既验收1f94f8fc…逐项一致。
旧七设计Markdown dirty保留、旧主控idle、没有本项目应用/测试/门禁需恢复；新Goal在Task冻结后启动，不恢复321-fish PAUSED守护。

## 所有权与范围

backend唯一server.py/server_store.py及本批测试写入；主控只文档、边界/导出/测试调度；独立审查只读且不参与实现。
本批不改UI/web.py/资源处理/依赖/真实数据，不Git提交/推送/PR/合并/发布或外部/Pro/其它聊天消息。
原Pro材料及原RETIRE实现DRAFT保持历史正文IDc45e7f27…；新的收窄Task/审查决定是本次执行依据。

## 执行记录

只读方案核对正在进行；Task v1冻结核心C、最低持久确认与延期边界，当前不提前宣布实现/测试通过。
后续逐步记录原红/候选/专项/领域/真实JSON和HTTP/最终raw manifest/全量/独立审查及真实结束状态。

Task冻结后Goal工具已启动active；retire_core_backend唯一实现，retire_core_review独立只读范围/后续diff审查。
只读retire_core_plan确认具体核心入口与Hub→bus方向，但提出known-tombstone候选不符合Pro/冻结Task；主控明确采用独立retired顶层字段，known清活跃记录。
写顺序审查重点包含旧slot晚入队和force过早capture，而非只在取slot处加锁。backend已收到这两类时序与禁止Hub内writer等待/IO边界。
本机run_checks.py仅复制前批已验证逐文件helper并改变日志目录namespace，export.py保留原字节/排除真实数据；不新增正式VB-01入口或改项目run.py/dev.ps1。

retire_core_review独立Task预审：可继续执行，与最终Pro收窄结论一致，无范围/权限阻断。
它明确将旧快照迟到入槽、force/flush过早capture、Hub内writer等待/IO、READ-burn事件锁外发送、严格新retired恢复列为实现必须项；不以一把writer锁替代时序证据。
当前两份新增核心测试准备中，尚未取得原红/修绿；原红将冻结测试版本并在入场raw额外导出上执行，镜像entry-source不直接运行应用。

### 原红C1输入冻结

主控在已镜像的入场raw371文件上叠加当前两新测试，导出original-v1-source；入场应用/测试字节不使用正在变动的工作树后端。
导出命令为项目.venv python -X utf8 _tmp_gui/cc02-retire-core/export.py original-v1 original；完整路径/hash/content ID见original-v1-export.json。
将启动唯一隔离逐文件负例：run_checks.py --label original-v1 --source-dir original-v1-source tests/test_cc02_retire_core.py tests/test_cc02_store_min.py。
该C1只有当前初稿11项，不冒称未来新增Event/IO矩阵已有原红；任何测试更改另记版本并保存旧报告。

原红C1结束：2文件各真实exit1，核心6failed/store5failed，共11 failed/0passed/0skip，4.65秒；无collection error/夹具或环境错误。
core测试SHA062d36ad48795822f3c2868a756a4065adab974534ef07a1acfb0fdbe006088b，store测试SHA312e8cff199352e9b32724640670de747cb00e567c6f4be117a21ec27cfb7c78。
原应用/测试输入来自entry镜像，完整导出ID205edd5b1a83fb821cd7803c545581de7fa53eda0a2945465c7de0f5bf1498fb；正在实现的后端没有叠入负例。
失败覆盖M1/tombstone未实现、旧删号后私有草稿/blocks仍在、管理结果缺失、无Store仍清理、save/force返回None无确认及旧候选保存等；缺新增retired字段是功能缺失断言，不伪称所有IO子阶段已分别复现。
原set编码TypeError与同步save stderr保持在日志；这只是C1，尚无Event/Barrier完整矩阵或修绿，原文件/summary在original-v1目录。
后台已在取负例前准备部分候选代码；C1仍严格绑定入场raw+相同测试，不回写成先测试后修改的虚假时序。

### 候选阶段整改（未验收）

backend提交初步候选及14/28/11摘要，因尚未提供完整命令/source-root/env/原始日志绑定，不作为本批验收结果；主控将对新的冻结版本统一隔离验证。
必要普通整改：写入ack保留快照/FP/IO期间新请求，捕获代次不可在FP计算后误包含新变更；pwd/claim晚到t0不得反馈成功；管理员PROFILE目标写区不得重建known。
测试C2需Event/Barrier覆盖已过A的核心末点、实际encode/open/write/flush/fsync/replace故障、失败重试与严格新字段恢复，而非仅post-t0直接调用或总是最后force flush。
候选中的bot_say资源回写修改已要求撤回；bot用户输入属于CHAT子路径，回复迟到边界仍按Pro延期。Hub/barrier/bus锁拓扑正独立阶段核对，不以代码作者自称完成给ACCEPTED。

独立阶段审未放行，四必须项保留：READ重构后原burn TTL调用丢失、缺实际worker/force/迟到入槽Event时序、retired昵称不得被bot永久预留误拒、confirmed重试不可降级pending/failed。
均已交唯一backend普通整改；Task v1.1澄清CHAT用户bot输入辅助与回复延期、可选短barrier仅Hub后取得、TTL/confirmed幂等/实际UID保护。没有扩应用文件/数据/Git权限或开启资源批次。

### 初绿C2隔离输入

主控将当前工作树原字节导出为positive-v1-source，并逐路径核对导出后工作树相同；它是独立候选快照，不在变动主树运行测试。
将执行唯一两新文件初绿。输入包含新增Event/真实IO/严格retired补强，不把它们沿用为C1原红11项；精确hash/全部manifest保存positive-v1-export.json。
本次仍是专项，不是最终全量或实现验收；后端可继续候选整改，版本变动另冻结，不把旧候选结果用于新源。

positive-v1实际结果：两个文件各exit2、共2 collection error，server.py4760出现IndentationError，0业务passed/failed，2.74秒。
主控过早导出尚在TTL整改的WIP候选，即使export前后字节一致也不等于静态可执行；不把这轮收集错误说成业务红或绿。
固定export ID8a04a2edbfcd0ce3570516f38412c93863d9b57b8d1a443366455c89a6c058cc与原日志保留，后续须实现者稳定声明/静态语法后新label复核，不覆盖原结果。

### 稳定候选C3（positive-v2）

backend完成阶段整改后声明稳定，py_compile六个允许文件/diff-check已真实通过；已撤bot_say回复改动、移除多余barrier，核心直接Hub→bus，保留READ触发TTL与confirmed幂等。
主控原字节导出positive-v2-source与边界检查，精确六文件hash/307源ID见positive-v2-export.json/boundary.json；旧3正文IDc45e7f27…、head/branch/index保持。
即将启动唯一两新测试专项；不沿用旧14/28/11摘要，不把positive-v1收集错误覆盖为绿。前后版本均保存。

positive-v2唯一session9057已真实结束：CORE12 passed/1 failed，Store18 passed，总30 passed/1 failed，22.33秒；各exit1/0，总exit1。
失败为新增sched准备阶段Event未触发（等待5秒返回false），非存储失败；已交实现者按真实调用链/有效输入核对夹具，不允许弱化交错断言。
该轮export IDc96d70aa847d4207cfb7edc71a0d4d4fea2919842a1f29e04de73cc79115a594，307源ID2fdc299c4178a7b2377a400886e0b95993d1fb0be002b97f69fcff15ebface5e；原log/summary保持。
下一轮先仅复测受影响CORE测试，已通过Store18在源/测试不变时引用，不重跑同版领域或提前全量。

positive-v3仅受影响CORE13 passed/真实exit0，4.70秒，导出ID63600d48f6267dd56d3cc63237920c5e9ac902f9aa3a1f0f87d23a74fa45336f。
sched夹具改为当前时间+3600，保持完整Event晚到C断言；_on_block_set重复通知/audit/persist尾部已移除，其他profile重复副作用核对。
随后追加实际worker旧候选/晚队列/force-flush、已摘due及CHAT/burn同C强测，应用server4c523082…未再改变；两测试新版本须重测，不沿用旧Store18或CORE13代替新增分支。
新的稳定positive-v4原字节导出及307边界已捕获，将唯一执行两个最终专项文件，实际命令/exit/count按日志追加。

positive-v4/session30047实际33 passed/3 failed，23.27秒，总exit1；CORE15p/1f/1线程异常警告，Store18p/2f。
CHAT/burn新强测在已持Hub的publish暂停期间等待retire的锁后resolver，夹具形成互等超时；Store两参数场景误期望新schema完全没有retired字段而非目标tombstone尚未存在。
均保留原日志/警告并交唯一backend修正可控交错与目标数据断言，不能移除测试或计为绿；当前只是专项，full未开始。
独立C3审仍要求锁内采过期burn seq、防锁外可变字典遍历，以及旧普通snapshot晚于新force完成后入队的真实Event证据；backend后续源B3088be3…和新case已准备，夹具修后另版本复核。

### 冻结专项C4通过、准备领域/独立复核

positive-v5/session90990已权威exit0，CORE16 passed/Store21 passed，合37 passed/0failed/0skip/无警告，22.91秒。
原字节独立导出IDff7e7cd136b023162735fdee49bb7378eaf816fe843407bd02614d133bb9ce29；新IO/迟到队列/实际worker force-flush/due/CHAT-burn交错与夹具修复版本分别保留，不追溯覆盖前失败。
real-v1在positive-v3相同认证/退役业务源码（后续只TTL锁内copy）运行生产加密TCP与实际HTTP、有效JSON新Hub重启，14观察全true/exit0；两个Web端+TCP同UID失效/其他账号存活/同昵称拒绝/JSON占用与op保持。
本机real-v1/proof.json/command.json/stdout/stderr固定；配置提示的web URL是旧serve_tcp显示配置，实际HTTP使用helper随机端口，不冒称提示9529为验收端口。
将针对冻结positive-v5源唯一跑受影响19文件领域，随后独立阶段允许后才最终full；仍不把37专项当整批ACCEPTED。

domain-v1/session41583真实exit0，19文件276 passed/0failed/0skip，93.35秒；raw源均positive-v5，日志逐文件独立/无重试。
当前307源与positive-v5导出逐项完全相同，候选源ID`c647d65c7061ceb67e26bd571520230ed84730b0480968b5ea6c809abdae2f28`固定到candidate.json。
将对完全相同最终两tests在原入场raw额外导出original-v2取得同版对照，不沿用C1初稿11为37个最终断言的原红；随后real-v2按同候选源码重绑14通道/重启观察。

original-v2/session25650结束：同最终37 tests在入场raw导出为36 failed/1 passed/exit1，13.18秒；原READ TTL通过，两个旧路径hook线程warnings保持。
这一对照的若干失败是新增retired/API确认功能缺失，部分新hook在旧调用链不适用，不能把全部36失败描述成独立竞态复现；C1无夹具/环境错误的11负例与最终原始报告分别保留。
real-v2在最终positive-v5源重新验证encryptedTCP/实际HTTP/validJSON新Hub重启，14观察全部true、真实exit0，真实raw文件与op保持均读取合成Store；不复用旧source hash冒称本次同版。
remarks快照独立性与READ已过A后最终C采用源码`copy.deepcopy`、Hub同锁及既有snapshotIsolation/资料保持/本批retired READ无副作用证据，未伪称新增这两项单独并发测试；独立审查须判断证据是否充分。

独立full前门禁：retire_core_review明确无剩余阶段must，当前代码/307ID与positive-v5一致，37专项/276域/real-v2 14检查证据同版；remarks/READ组合源码及行为证据可接受。
原36f/1p负例与中间语法/夹具/线程警告原始保持，不阻塞当前候选final full，也不冒称为当前通过。

### 最终全量输入冻结（未提前报结果）

将以原字节final-full-source、原项目.venv解释器运行115测试文件，各文件单独pytest进程/UTF8/独立basetemp，默认opt-in跳过沿原规则。
命令：`& ./.venv/Scripts/python.exe -X utf8 _tmp_gui/cc02-retire-core/run_checks.py --label final-full --source-dir _tmp_gui/cc02-retire-core/final-full-source`。
完整源/测试/依赖307 IDc647d65c…，候选前/导出/后源hash须一致；全部应用/tests暂停写入，主控唯一全量，最终真实exit/计数/环境/耗时另录。
子进程cwd/PYTHONPATH/profile/Home/AppData均隔离导出，敏感/外部模型env只清子进程；不复制真实运行数据，不改依赖/run.py/dev.ps1或正式VB-01入口。

### 最终全量实际结果

唯一final-full/session74648权威结束exit0，115文件逐独立进程各一次，**1392 passed / 0 failed / 2 skipped**，391.32秒，无重试、无warning/xfail。
跳过仅既有test_r45硬件`--run-hardware`与test_visual_screenshot视觉`--run-visual`，没有新增skip或弱化断言。
Windows11 10.0.26200、项目.venv Python3.14.5/pytest9.1.1；真实115日志/summary独立重汇总一致，summary SHA256`c4fb12b2e69019852aab6299261c2d9528856159e02abc40903be8957e6ec3d9`。
candidate/current/final export curated307均0mismatch，源ID`c647d65c7061ceb67e26bd571520230ed84730b0480968b5ea6c809abdae2f28`；full-verification.json保存实际环境/退出/原skip与文件比对。
全量期间仅PROJECT_MEMORY/技能事实与CC/Review流转，未变应用/测试/依赖；final-full-source内的旧文档快照不是最终文档版本，最终资料另捕获。
HEAD/branch/tree/index保持，边界0越界、旧3设计正文IDc45e7f27…不变、101相对链接/投影/diff-check通过；无应用/pytest/full进程需恢复。
目前仅门禁结束，正式独立终审正在交接；不由实现者自验收、不等于完整RETIRE资源/UI闭合或R1通过，未Git提交/推送/PR/合并/发布。

### 独立正式终审与本批验收

retire_core_review正式结论：**CC-02A-RETIRE-CORE v1.1可ACCEPTED，无剩余必须修复项。**
独立核对Task/最新决定/真实diff/当前资料、307候选/导出/前后hash、115原始日志/summary/exit/skip与实际环境；37专项、276域、real-v2 14观察均同源。
最终1392/0/2、391.32秒一次full，无warning/xfail/重试；两个旧opt-in skip准确。remarks/READ组合源码与行为证据等级符合批准范围。
原负例/中间语法/夹具/线程警告全部保持；未把旧结果或代码作者摘要冒称最新验收。现有GUI/资源/loader等延期未悄然实现，权限无越界。
主控据独立结论将本批置ACCEPTED，仅更新CC/Review/投影/记忆事实流转；应用/tests307不变。CORE验收不等于完整RETIRE、Pro R1、Git合并或发布。
已请求open_in_codex显示本报告（queued），用户可直接从本工作区链接读取；本批目标满足，待工具结束Goal。

Goal工具已确认complete，6929秒（约1小时55分钟），未设预算；此后仅本Review/指挥中心/投影结束元数据流转。
307源码/tests/依赖仍与门禁candidate/export一致，旧设计正文c45e7f27…与head/branch/index保持，边界/101相对链接/投影/diff-check最终PASS。
本批本地未提交交付，未commit/push/新PR/merge/release、未真实数据操作或外部/Pro/其它聊天消息，旧321-fish heartbeat保持PAUSED。
范围到此停止，不自动推进STORE/RESOURCE/CC-05；有效JSON成功退役保证不扩为首失败跨重启、损坏loader、UI或所有资源边界已安全闭合。
