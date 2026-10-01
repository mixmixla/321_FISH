# CC-02A — 实施、验证与独立审查 r1

2026-10-01（Asia/Shanghai），对应[Task v1](../task-packages/CC-02A.md)。状态只见[指挥中心](../AI_COMMAND_CENTER.md)。

本批最终交付为正常注销资料保持、JSON身份映射恢复、全部现有端KICK与手动重登；独立终审可接受。
最终113文件1355 passed/0 failed/2原有opt-in skipped，源305前后/导出一致，当前仅本地未提交。
下文原红、候选与待验证措辞保留当时过程；最新门禁/终审/权限终点见最后章节，不能把历史句子当成当前队列。

## 批准与入场

用户答复“我是批准首批实施”，当前范围PROFILE→RESTORE→KICK，Goal已启动；
架构决定技术输入与用户实施授权分开，RETIRE/STORE-COMMIT及其它切片未放行。
决定文件逐字节归档至docs/decisions，SHA256 `62e5a02ac131115780590aec36aa3b8c3486757954e44708dd37f76de6e46089`；
其四份输入资料SHA均与工作区完全一致，未把文档自身的指令当成额外授权。

HEAD/base `d07b29577a48367f887cc0c2dbf1671ed13bb326`，branch fix/cc-01a-admin-credentials，index空/树0bdde556…。
356项入场非ignored文件/300项源码原字节已保护，source ID64b829…与历史验收集合一致；
原文件副本和完整manifest在`_tmp_gui/cc02a/entry.json`及entry-*，上轮13份dirty Markdown保留。
没有本项目应用/测试进程；旧主控“按协作方案持续开发”idle，旧R1守护PAUSED保持。
当前本聊天唯一主控；backend唯一server.py写入，主控负责必要Core/Tk/Web与文档，独立审查只读。

## 事实核对与切片冻结

PROFILE/RESTORE后端与KICK客户端路径已分配只读调查，Task准确函数/字段和接受边界在核对后补充。
历史108文件1335/0/2只作入场背景，不标成本批门禁。

### PROFILE 实现候选

仅server.py私有`_KNOWN_PROFILE_FIELDS`及`_attach/unregister`资料复制，字段按存在性保留pwd/sign/avatar/invisible/status/remarks，
包括空值/False；嵌套remarks深拷贝。nick/last_online按原场景更新，未变群/资源/代表/通知逻辑。
新增两项多断言回归覆盖中间/最后端、他人资料、offline roster、同UID重登、真实state.json重启与welcome资料。

原测试旧名`tests/test_cc02_profile.py`，已依Task归属重命名为`test_cc02a_profile.py`；字节不变，
SHA256 `fc78df6c86e73785b71435cc44f78e0cb572e11ea7e33f7c5de4100f6f66ee2e`，旧名→新名映射保留本机证据。
默认pytest临时目录ACL拒绝是环境错误，独立保存在profile-original-env-error.log，不计作业务原红。
使用隔离basetemp的有效原源回归2 failed、修复2 passed；领域SESSION02/多端/R52/logout/管理员/auth共68 passed，
R56/R68/R69适当选测8 passed/103 deselected；新路径复核2 passed/真实exit0，未运行全量。
命令/元数据与日志在`_tmp_gui/cc02a/profile-*.log`、profile-renamed-meta.txt、profile-rename-map.txt。
独立PROFILE阶段审查：可衔接，无必须修复项；主控按阶段结论放行RESTORE，未把阶段通过当批次验收。
审查者核对356入场仅3份资料+server.py变化，source300仅server.py，三处增量与原始失败/领域一致。
深拷贝主要由相等性测试与源码证明；既有未改群/资源边界另由SESSION02领域证据覆盖。

### RESTORE 白名单冻结

完整审计：groups(GID/owner/admins/members/mutes)、known UID、reads会话/UID、blocks UID、polls seq/votes UID、
drafts uid|key、scheds UID/rid/目标标量、group_files GID/作者标量、tasks GID/done/作者或指派标量、
fish_board game/UID、moments pid/作者/评论标量、moment_covers UID。须服从实际消费者的类型契约，不能仅因“引用UID”就int化。
其余已正确转换字段与资源字符串只保留回归，本片不做递归schema重写；昵称、频道/资源、rid/fid、remarks字符串键保持。
本次确定要改：groups外层GID及owner/admins集合值/members/mutes键的严格身份结构，reads内部UID键。
正常JSON的admins为数字集合值，并非JSON对象键；成员/禁言与reads对象键在JSON往返后变字符串是明确复现目标。
bool/非整数/非法结构或归一化碰撞时拒绝受影响群，保留其它合法群；reads拒绝受影响会话的整份映射，绝不取更大游标。
授权字段owner/admins需符合原成员角色关系，不能因坏mute落空而放宽发送。已有正确转换不重复实现；burn pend格式另记录排除。
这些异常策略在合成数据原红/修绿及真实重启后操作矩阵验证，不以减少旧断言或只改期望获得通过。

RESTORE候选：原源同测试2 failed、修绿2 passed，PROFILE+RESTORE最终4 passed，相关域88 passed。
旧test_server.py两处字符串键期望已改为运行时整数，真实业务断言保留。
初始多-k组合命令实际只1 passed/176 deselected；r70错误选词25 deselected/exit5、旧类型期望1 failed/2 passed均原样保留，
不能计为恢复域绿。后续按正确单-k逐文件分别记录test_server3项及R26/R28/R51/R52/R54/R64/R69/R70恢复验证，精确结果由meta/log绑定。
独立审查认为源码/白名单可接受，唯一必须项是补异常群分支测试：admin或mute非成员、members/mutes非法结构及UID冲突；
实现者正在补强回归，未改变代码范围。补强是测试覆盖，不能冒称出现新的业务原红。

覆盖补强已关闭：六类参数化异常群均确认坏组拒绝/正常独立组关系保留；文件8 passed、相关域94 passed。
最终测试SHA256 `d2ffcd7cb8a980fa45288aa7c976f9dc55afb81ff3dff4acc35ff5d778d1f829`；server未因补测改动。
独立复核可衔接KICK，无剩余必须项，原2项原红与补强后的测试版本分别记录，不冒称同版本新增原红。

### 最终门禁环境冻结计划

完整非ignored源码/测试/依赖/静态资源/必要文档原字节导出至本批独立验证目录，前/后/导出manifest完全一致；
不复制真实prefs/history/web_files/audit/server_state/downloads/TLS/.venv。
逐文件入口仍为本机ignored辅助，原项目.venv解释器，以导出目录为cwd/PYTHONPATH；CFG/prefs默认数据因__file__指向导出而隔离。
仅子进程环境清除管理员/站点口令及外部模型路径，子进程USERPROFILE/HOME/APPDATA指向专用隔离目录，用户shell与真实配置不变。
该方案已独立静态审查可行；最终执行时绑定确切source_root/环境/hash/真实exit。不会改run.py/dev.ps1/conftest或声称完成VB-01产品入口。

### KICK 后端候选

新增`_kick_targets`在锁内抓取全目标/代表兜底、closed与token撤销；锁外原unregister/通知/关闭，新端正常认证与旧清理复查保持。
原3项同测试全部失败→修3通过，随后通知异常补强第4项，最终4通过，相关域65、三后端新文件14通过。
最终测试hash `de06bcabf64df4dc51a39a8b7d280f042da766d9a923b9c8631a0cc69b9e64b0`，原3项与补强版本分开记。
独立后端审查可接受、无后端必须项；不证明RETIRE的异步/持久提交屏障，也尚不代表UI/批次完成。

### KICK 客户端/Web与集成候选

独立UI worktree `C:/Users/liang/.codex/worktrees/cc02a-client-kick/321_FISH`从同HEAD建立，主控仅三UI模块与两新增测试。
入口三UI文件先用主树原字节叠加，避免Git换行规范化混称原字节；入场副本/初始试验留在worktree `_tmp_gui/cc02a-ui/`。
Core/Tk最终4回归在旧UI4失败、修4通过；初稿第4项fixture缺少_hotkey导致AttributeError，单独保留fixture-v1，不计有效原红。
最终第四项改为明确“毁窗后继续消费事件”行为断言，原源同最终测试4失败；Core闸门阻旧发送/重连/迟到welcome，Tk复用既有switch。
Web生产函数在Node执行11个行为：kicked、旧SSE、同源401、500、公用/外域401、新认证迟到401、迟到logout401、
SSE401、普通暂断和旧探针；最终测试在原Web有5行为失败/6通过，修复后全true。旧10项试验另保留，未混记成最终11项。

集成围栏：主树三UI文件必须与入场hash相同、新测试不得碰撞；原字节复制已通过，`ui-integration.json`保存最终5文件hash。
有效同最终两测试负例在`ui-original-final-source`（入场Core/Tk/Web+当前已批准后端），4 failed +1 failed/真实exit1，
`ui-original-final-input.json`明确故意负例overlay及源ID，不能把前置export匹配记录冒称负例全树与主树一致。
正例隔离导出`kick-domain-v1-source`，305项source ID`d764a538adf4ca44b88e944c1d156498886835e55bd91dd83d3bab216d649fb3`，
前/后/导出raw完全一致；8文件领域正在唯一session42873运行，当前未宣布完成/全量。
独立客户端/Web审查已交接，真实Tk与双host浏览器验证仍待完成，不把Node VM当真实UI。

领域v1实际结束：82 passed/2 failed，exit1。失败是旧logout网络catch源码片段不再命中、P0 token-URL静态子串命中新的局部变量。
没有改/弱化这两旧测试；保留原网络失败catch语义并将局部快照变量改名后，受影响4文件域v2为27 passed/0失败，exit0。
独立UI审查另发现packcover实际需认证；已修公共排除策略，仅login/meta及sticker静态路径排除，增加两生产JS行为。
最终Web测试13行为（原Web6失败/7通过），最终同两文件负例Core4失败+Web1失败，测试版本/hash与11行为旧版本分别保留。
Web最终hash`bc8bfb4dbb2232884dae420aca8c7b6e756c7ed2fadaf032429840cbb9efbca0`、测试hash`37af2a5a6b76061510cc46170eb5d052809078eda1fd86218dd51678d6e91ec4`。

真实Tk首次12行为全true，但stderr有主题/last-online残留Tcl回调，不算最终通过。中间Python after_cancel枚举方案因删除子控件command
但未更新其owner命令簿，退出未完成并被核对PID终止；stack/debug/真实退出保留。窄句柄尝试完成12行为仍有_tick警告，也未冒称清洁通过。
最终只取消当前解释器Tcl定时队列，保留各控件命令簿，由正常destroy按所有者删除；不改tkguard/轮询/launcher业务。
最终Tk v5 source ID`1f94f8fca3da7746c5db293b05e5729e76b37935e1a05d0314658bde9de39830`，真实launcher/ChatWindow/LoginDialog/Entry Return/TCP
12行为全true，旧Core停止、trusted快路径不重复、手动新Core/同UID重登、正常退出，真实exit0；stderr无invalid command/TclError/Traceback/Timeout。
client最终hash`745b868b375828c2d90d402f82363ff100b71922ed961a6bca4e1931aa93f6ff`；新增Core/Tk5项+Web1项绿，最后相关GUI域5文件41 passed/exit0。

真实浏览器：IAB两个host Cookie隔离，生产登录/发送互见、TCP1+Web2三端被踢，后台3 closed/0活端，双DOM登录可见/main隐藏；
刷新不恢复旧Cookie认证，同昵称手动重登可用，B显式logout仍保留A，最终A浏览器error日志为空。12观察见browser-proof.json及browser-*.json。
控制POST返回嵌套status，首轮报告脚本KeyError独立保留；没有重复kick，GET status验证了真实撤权结果。
浏览器实际加载server6f251c…/Webbc8bfb…，与最终候选相同；启动附带旧client hash没有用作桌面证据，最终Tk另绑定全部实际Desktop源码。
截图由浏览器工具原生显示，临时两Tab已关，harness69870已真实exit0；没有待恢复UI/领域进程。

最终独立实现阶段审查：PROFILE/RESTORE/KICK后端与客户端/Web无未关闭必须项，可进入同版本全量。
backend只读AST边界核验其它函数不变；Core仅初始化/start/dispatch/send，client仅poll/on_error/quit，Web Python AST未改，5新测试/两旧期望准确。
HEAD/index/入场其它保护保持。最终完整门禁仍待运行，不能由上述领域/真实UI结果宣布批次ACCEPTED。

### KICK 接受边界（计划冻结）

撤权提交点采用Hub锁内目标Session集合closed=True及全部旧token删除；unregister早退依据membership而非closed，
因此锁外仍可承接已验收的注销/UID清理，不新增永久身份状态。后续正常attach允许，新token不在旧集合中。
Hub.dispatch的活性检查与直接Web `_session/session_by_token`是本批接受点；检查前撤权拒绝请求且无业务副作用，
检查后已被接受的操作可完成，不追溯取消。某些REST wrapper吞dispatch False返回200的竞态沿既有响应契约，
验收按无状态副作用；常规无效token仍401。未重写所有HTTP响应/直接业务模块。
已经接受的读、上传、排队SSE事件/异步工作沿原语义；due/CLOUD文件/全写入面持久屏障归RETIRE，不在KICK冒称解决。
Web SSE收到kicked复用leaveLogin，断流探whoami确认401后收口；旧对象/回调不得影响新手动登录。
Core需先停止旧认证的自动重连与发送，再Tk通过已有switch登录回路收口；poll销毁窗口后须立即返回。
Web当前受保护API401统一收口需请求token/当前token一致且同源；公共meta/login/静态资源不变。
迟到401/探针/旧SSE不能清新认证。正常请求错误、网络暂断保留原登录；不重写后端HTTP业务契约。
KICK并行遵守独立checkout：backend唯一主工作区server.py，主控独立UI worktree三应用文件/两前端测试；
从同一HEAD起，叠加当前PROFILE/RESTORE源码与冻结Task仅为上下文，集成前核对主树客户端原字节，防止覆盖新改动。

## 最终全量与交付候选

最终305项源/测试/依赖ID：`1f94f8fca3da7746c5db293b05e5729e76b37935e1a05d0314658bde9de39830`。
HEAD仍d07b295，branch fix/cc-01a-admin-credentials，未提交；这是本工作区未提交增量，不冒称PR已更新/合并或发布。
最终UI集成v5记录各原字节hash；server6f251c…/Corecf9dfe…/client745b86…/Webbc8bfb…；五新文件共20回归，test_server仅两处类型期望补正。

命令：`& ./.venv/Scripts/python.exe -X utf8 _tmp_gui/cc02a/run_gate.py --label final-full --source-dir _tmp_gui/cc02a/final-source`。
Windows11 10.0.26200、项目.venv Python3.14.5、pytest9.1.1；同原字节导出源及静态资源，子进程cwd/PYTHONPATH均导出根，
测试profile/Home与默认数据路径隔离，敏感/外部模型环境清除；没有复制真实运行数据或替换项目依赖环境。
独立113文件各一次，唯一session2946真实exit0，**1355 passed / 0 failed / 2 skipped**，373.21秒，无全量重试。
跳过仅原test_r45硬件opt-in与test_visual_screenshot视觉opt-in；没有新增skip/xfail或弱化旧断言。

门禁summary SHA256 `081b25db2fe0ca5971e91284302c3e2341fd72042fb29aee290abad9c1aaea7d`。
`final-candidate.json`/`post-full.json`/`final-export.json`的305项前后与导出完全一致，静态资产未变；HEAD/branch/index不变。
`verify_final.py`真实exit0、20项全true，8资料75相对链接有效、投影/源区块hash一致，diff-check exit0。
356入场仅9个批准文件变化，另4资料+5新测试，347其它入场文件保持；原draft-v1逐字节保留，同决定的审阅SHA72b59a…一致。
原始113日志真实计数与退出全部独立汇总一致，不把中间域失败/错误命令/Tk警告/终止或早期测试版本改写为绿。

所有测试、Tk和浏览器harness均权威结束，临时Tab已关闭，当前无需恢复的应用/测试。最终门禁/资料独立终审正在进行。
批次是否ACCEPTED只由指挥中心按独立终审结果记录；RETIRE/CREDENTIAL/LOCAL/CLOUD仍未实施，R1里程碑/merge/release另审。

## 独立终审与批次终点

`cc02_docs_review`最终独立结论：**可接受，无必须修复项**。独立复算HEAD/branch/index、305源与导出/前后manifest、静态资源0mismatch，
113原始日志/summary数量、真实exit全0、1355/0/2及仅原opt-in skip；环境与373.21秒一次full口径正确。
Node13、Tk最终12且stderr无错误、双hostIAB的实际server/Web版本与行为均有证据，中间失败/警告/挂起/版本差异保持。
20机械检查全true、75相对链接/投影/hash/diff-check通过，无应用/测试需恢复。

门禁后仅PROJECT_MEMORY、指挥中心、Review与实现草案等资料流转更新，应用/测试/依赖/静态资源未变；
不能把导出目录的旧资料快照误称最终资料版本，最终资料另捕获hash，不影响已冻结门禁结论。
原draft-v1逐字节公开保留；临时UI worktree已在list_artifacts确认为archived_worktree且路径不存在，所需ignored证据已保存在主树。
这是工具的可恢复归档快照，主工作区HEAD/index未变，没有将本批源码提交/推送到用户分支或PR。
已请求在Codex打开本报告（返回queued），文件可从本工作区链接读取。
主控依据独立结论将本批/三片置ACCEPTED；Goal工具已确认complete，9741秒（约2小时42分钟），未设预算。
范围至此停止，不继续RETIRE或发Pro消息；指挥中心/投影与最终8资料hash已保存，源码/门禁输入不变。

后续Git交付：用户于2026-10-02明确授权提交/推送/新Draft PR，范围见[PR-DELIVERY-02](../task-packages/PR-DELIVERY-02.md)。
本包“未提交”是实施验收终点状态；新交付已产生代码commit e065591，原source305/门禁证据保持，实际PR结果另记交付Review。
