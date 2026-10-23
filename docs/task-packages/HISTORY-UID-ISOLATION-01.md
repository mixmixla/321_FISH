# HISTORY-UID-ISOLATION-01 v2.1 — 已确认账号的本地聊天隔离

2026-10-23 READY / INDEPENDENT_DESIGN_REVIEW_0_MUST。用户已批准：聊天历史按账号UID隔离，改昵称记录连续，旧昵称历史保留、不自动归给新账号。沿用Sol+FAST与普通main集成授权，实际服务回执不可见不冒称核实。base已Git/API双核main `293cc526ea2c49a4c5ca4520a09ca73aa5733a01`；独立集成工作树history-uid-integration-20261023/feature/history-uid-integration-20261023，旧试用树checkpoint/r3-delivered-20261023同base无文件改变。原工程视频4759保持clean/暂停/非祖先，不继承、诊断或合并。

## 冻结语义与命名空间

- 新持久历史键仅用当前已接受WELCOME的 `auth.store_mode=durable`、严格32位小写hex `store_scope_id` 与正整数UID（拒bool/路径串）。目录为history-root/v2/<store_scope_id>/uid-<uid>，昵称、host/port别名和每次启动变化的server_epoch不入持久键。现协议的durable Store ID跨正常重启稳定，新Store换ID；复制整个Store会复制ID，现协议无法区分克隆，本批不新增服务器身份/信任固定机制或承诺克隆独立性。
- UID只在该Store内唯一。不同scope同UID、同scope不同UID即使昵称相同也隔离；同scope同UID即使显示昵称改变或换服务端点别名仍连续。服务器当前没有实际改名入口，本批不新增改名功能，只保证相同已确认身份对应同历史。
- Core构造仅使用每Core独占fresh临时bundle，维持LocalHistory/E2EE/媒体接口；不计算、枚举、读取、搬移或覆盖默认旧昵称/顶层历史。只有当前connection/epoch的WELCOME经现认证接受后，才完整prepare并一次性切新bundle，且须早于history/saved、贴纸缓存、云合并及UI welcome。认证前临时内容不自动迁入持久目录。
- 缺失/volatile/畸形scope只用fresh会话临时bundle，不按nick、endpoint或裸UID降级持久保存；给调用方明确本地存储身份/模式。无有效UID不接受身份。显式history_dir统一是调用方给定ROOT，也必须按相同身份分层，不是绕过身份的直达目录seam。
- 同目标普通断线保留已确认身份的离线历史；显式切号/目标变化、认证拒绝立即使旧bundle/generation失效，关闭旧句柄并清旧UI内容。新WELCOME身份不同必须在处理新数据前隔离；旧异步cloud_restore、密钥/媒体/缓存worker持捕获bundle/generation，提交前重核，不能经可变self._history等写进新身份。只清理自己创建的临时目录，等自有句柄/worker收尾，不覆盖原错误；不删旧持久目录。
- 创建/准备持久bundle、身份key读取或保存失败，须明确失败并停止本次本地上线/写入，不退回旧账号、昵称目录或共享root。已有损坏/不可读身份文件不自动生成覆盖；如需crypto_e2ee仅增用于此绑定的窄strict存储选项，旧默认/加密算法/协议不改。新目录片段严格验证，拒绝越界和reparse/symlink别名进入其他账号或旧目录。

## 最小关联UI和聊天prefs

ChatWindow在身份确认前聊天六字段pinned/muted/archived/drafts/stars/unread_marks为空/临时态，不能从legacy nick profiles或顶层恢复旧正文。现launcher预认证remember/switch_profile的旧内容认领必须退出新主流程，仅保留登录选择/默认昵称等元数据。已确认身份使用新的UID聊天视图/明确v2 schema，历史、消息收藏及草稿按同scope+UID绑定；不得把稳定key传旧switch_profile假装迁移，不污染known_accounts为内部scope键。

旧prefs顶层六字段、profiles[nick]和opaque-stars原值保留，不自动迁入任何新身份；既有旧Prefs StarsPreservation保护不削弱。设备主题/热键/登录偏好行为保持，六字段相关写入不能改写旧账号数据。UI在主线程绑定/切换后再加载历史与服务器草稿，清除旧_drafts/_stars、列表/预览/旧输入和全局搜索结果；后台旧事件须按身份代次拒绝。GlobalSearch/Ghost在临时/未绑定态不得以空路径扫描cwd或旧目录。quick/reminders等其他个人文本、云格式/同步功能及整个prefs体系不在本批，不能宣称所有个人内容隔离。

## 文件所有权与边界

root唯一Task/Review/evidence/中心/投影/必要稳定记忆/最终验证与Git集成。A session_scout独立工作树history-uid-20261023，唯一产品写入者：client_core.py、client.py、prefs.py、launcher.py；必要的新纯身份辅助local_identity.py；crypto_e2ee.py仅上述strict本地身份存储窄选项。新测试tests/test_history_uid_isolation.py与tests/test_uid_chat_profile.py；已有相关测试仅更新本次history_dir/旧迁移/认证fixture契约（先列清具体文件与原因），不删行为断言/加skip/弱化保护。不得改服务器/协议/Store、视频、门禁、依赖/系统设置/真实数据。

B flagship_scout独立只读设计、代码、原始证据、资料与新增对象审查，不参与补丁实现。总活动主控+两Sol工作者，不并行全量。只有本包经独立设计0 MUST并在中心置READY后才编码。

## 证据与验收硬门

1. 先用合成旧昵称/顶层jsonl、媒体/身份和prefs标记保存全清单/hash；原产品执行确定性RED，须触达真实旧读取/认领/跨账号问题，不能把新helper不存在或fixture前置错冒充产品失败；首次失败/退出码/测试字节均保留。
2. GREEN覆盖认证前不读取旧目录/不迁移、登录失败/拒绝、登录登出切号、同昵称不同UID、同UID显示名变更、两个durable服务同UID、新Store、同Store真实重启、端点别名同Store、missing/volatile/非法scope/UID、显式ROOT、绑定失败后恢复、路径逃逸/重解析拒绝与旧字节不变。历史唯一标记使用私聊/本地合成内容，不能把服务端合法公共历史共享误判为泄露。
3. 必须有旧worker受控门：启动于身份A，切B或失败后再放行，确认不写/合并B、不恢复A UI；不靠sleep概率或无界压力。六字段UID视图重载/切换、legacy opaque-stars保持、失败写入无旧内容覆盖、实际launcher接线与必要真实Tk组件路径回归；不把组件/协议算可视GUI或自然退出。
4. 代码/原件独立0 MUST后冻结组合输入并按文件隔离full。首组合hui23-final-01已自然失败，完整原件永久保留；七个已定位旧测试文件按下列v2/v2.1契约修订，先单次七文件选测/独立原件复核。测试输入变化不得resume旧指纹或改终态失败，新冻结501组合候选用短原工程_tmp_gui/hui23-final-02完成必要最终full。任一时刻仅一全量/选测；若出现不同问题先分类，不盲重全量或retry-to-green。source-dir是当前Git集成树，保留旧skip/历史失败。
5. root绑定当前/冻结/快照/解释器依赖/原log/sandbox/完整集合/单attempt清理与实际shell exit，B从原件独立终审后才有限AI_ACCEPTED本Task。新增全部中间提交/可达对象及metadata脱敏审计；原日志/私聊/用户名/密钥/prefs/历史/二进制只本地，不上传。普通非强制main集成与推送后Git/API核完整SHA，CI无记录不称通过；不PR/发布/强推/绕保护或改权限凭据。

原件主控本树_tmp_gui/history-uid-isolation-20261023；worker与正式门禁各独立ignored目录，长动作开始/结束更新中心与实际exec。基线498输入/raw source f3b5e013dc2008d10b198ccdac9273bd5fbd5c0b144c9b2134b1abbaf7b8eaae，与既有221文件3022P0F20skip/exit0完整门禁逐字节一致。原v1冻结时尚未编码或运行测试，不沿用旧门禁作为新实现验收。真实GUI/自然退出/LAN/异机/新EXE与视频仍未验。

## 设计审查结论

flagship_scout从冻结v1独立审查0 MUST；窄strict身份存储、legacy保护和原子WELCOME/异步代次为必验项，root据此将本Task置READY。尚未实施或测试，不等验收。

## v2 有限验证修订（产品范围不变）

决定来源：root依现有本地自治/用户UID隔离授权，B独立原日志和差异审查0 MUST；不增加产品功能，不改变真实数据边界。v1首组合full01已实见夹具失配，不能以专项或原run续跑改称全量通过。v1设计/首RED/首次领域及选测失败仍逐版本保留。

A仅增加五个既有测试文件所有权：tests/test_admin_group_dissolve_scope.py、tests/test_admin_group_remove_scope.py、tests/test_group_kick_scope.py、tests/test_group_leave_scope.py的Core私有WELCOME wrapper每处仅接收并透传captured connection关键字；tests/test_game_client_lifecycle.py的唯一__new__合成factory仅补threading导入及transition RLock/threadlocal/local generation三前置。真实Core、所有用例/行为断言/屏障和生产代码不变；不为裸__new__在产品添加fallback，不删/skip/弱化测试。

同一kick文件的旧send mock另仅显式接收expected_local_generation可选关键字，函数体/门/断言不变；原日志两参数例直接显示门超时和cleanup AssertionError，关键字绑定拒绝为确定性源码推导，不冒称原日志直接打印TypeError。

v2冻结时五文件差异已B独立静态0 MUST，worker501/source06652735e0d86ad1c3e31e932110ced5e12b91c33f4b5f097420cf2e0ce4fef6；未执行选测/提交。等待full01完整终态，若其他失败须另审具体原因，不能批量把未知问题列为夹具。02仅因已定位测试输入修正而必要，不承诺通过。

## v2.1 已批准产品合同的旧断言更新

full01完整失败恰七文件；前五项为上述夹具/前置兼容，另外两项由B独立原件及Task v1确认是旧断言与已批准UID隔离合同冲突，不能统称夹具或改产品迎合旧期待。

A另仅获tests/test_retirement_status_wire.py及tests/test_stars_preserve.py所有权：前者保留失败发送不pop旧成员、恰两GET且零DEL/ever_del断言；显式set_host后改断旧uid/known/roster已撤销，迟到回执仍不能复活。后者仅三个launcher参数例按metadata-only登录选择更新期望，旧top stars/profiles/active_profile逐值保留，不迁移/认领，不创建uid_profiles；验证新UID视图为空。其余34个Stars保护用例及直接旧API保护不变。

决定来源仍为用户已批准稳定UID隔离及launcher不认领legacy正文的既定产品合同；root授权技术验收修订，B独立判合同及差异。生产文件零改动，所有失败原件保留。七文件最终候选501/source9388d7f96ab69a83f3ef46960430ff3b3bc4728cfb90f6df7bf6fe10c0164c66，先独立审查后唯一hui23-contracts-final-01七文件选测，再按新指纹最终full02；不将full01改称通过。
