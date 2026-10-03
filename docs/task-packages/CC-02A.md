# CC-02A — 基础一致性首批实施

版本 v1，2026-10-01（Asia/Shanghai）。执行状态及子切片放行只见[指挥中心](../AI_COMMAND_CENTER.md)。
用户在本聊天明确答复“我是批准首批实施”，批准范围为架构决定第4节的 **PROFILE → RESTORE → KICK**。
既有Goal偏好适用：本批自主衔接实现、专项、独立审查、整改、最终全量及交付，到终点停止。

## 决定、基线与权限

- 方案来源：[CC-02 架构决定 v1](../decisions/CC-02_架构审查决定_v1.md)，原文件逐字节归档，SHA256
  `62e5a02ac131115780590aec36aa3b8c3486757954e44708dd37f76de6e46089`。它是技术决定输入，实施授权来自上述用户答复。
- HEAD/base `d07b29577a48367f887cc0c2dbf1671ed13bb326`，branch `fix/cc-01a-admin-credentials`，index空；
  入场356个非ignored文件，包含上一轮13份未提交文档。source300 raw ID
  `64b829d183370ebb019abf19d05aaa8abb870db49246cc011a5cb15296abd093`，已逐项核对无变化。
- 决定文件引用的四份资料hash均与入场版本匹配；旧主控idle，原Goal已完成/heartbeat PAUSED，无应用/测试进程。
- 允许本批应用/测试/资料改动与合成数据隔离验证；不改真实prefs/history/server_state/audit/web_files/downloads/TLS，
  不commit/push/PR/merge/release、发送外部或Pro消息、启动heartbeat、启用真实设备。
- 排除RETIRE/STORE-COMMIT、UID/昵称再注册改造、普通密码并发/改密撤权策略、LOCAL/CLOUD格式与迁移、协议、
  广泛物理清除、游戏入口筛查、EXE、新功能。M1已选定为后续技术方案，尚未在本批实施。

## 写入所有权与精确入口

- `cc02a_backend`唯一写`server.py`及新增`tests/test_cc02a_profile.py`、`test_cc02a_restore.py`、`test_cc02a_kick.py`；
  如旧恢复断言与正确新类型冲突，可必要修改`tests/test_server.py`对应恢复期望，必须保留并加强行为断言。
- 主控在独立checkout唯一写`client_core.py`、`client.py`、`web.py`与新增`tests/test_cc02a_client_kick.py`、`test_cc02a_web_kick.py`；
  仅强制失效接线/当前登录停止重连及回手动登录，不改其它UI/业务/游戏逻辑。必要launcher接线先核对再记录包修订，
  优先复用既有`request_switch_account`/`_exit_reason=\"switch\"`流程。
- 主控拥有本Task/Review、方案决定归档、修订实现草案、PROJECT_MEMORY、指挥中心及生成任务清单；
  旧架构材料/旧TaskReview保持历史证据，不把新源码行号或新结果反写旧结论。
- 独立审查`cc02_docs_review`只读，不参与代码写入。实现与独立审查不能由同一写入者自验；
  同server.py串行PROFILE→RESTORE→KICK，已有变动不回滚，所有权变更先保存检查点。
- 本机原文件/manifest/版本、命令、日志和进度保存于`_tmp_gui/cc02a/`，不是唯一状态来源。

## PROFILE：正常注销资料保留

入口`Hub.unregister`与`_attach`的既有资料带回；以既有known记录为基础，只更新nick/last_online等明确运行摘要，
保留pwd/sign/avatar/invisible/status/remarks（字段存在即保留，包括False/空字符串/空dict），不得落盘Session/token等运行对象。
公开online/offline继续由存活会话决定，保留busy等偏好不能让离线用户显示在线。
中间端注销、最后端注销、代表切换、重复注销、重登、新端资源、退群/转群主/空群解散沿用已验收语义。

验收：合成资料的单端/中间端/最后端、重登、真实JSON持久化重启后逐字段保持；他人资料不变，
最后端在线名单正确；管理员部署凭据仍不进入snapshot/audit，普通pwd摘要按原规则保留。
先以新增回归验证原候选实际资料丢失，再实现；没有复现的观察记录限制，不假造原红。

## RESTORE：实际UID/GID字段恢复规范化

入口`Hub._restore`及仅用于字段白名单转换的必要私有辅助。冻结白名单前核对完整snapshot/消费者：
至少groups外层GID、members/mutes内层UID、reads内层UID；其它实际身份map如果已有正确转换保留，
有新增确证同类缺口先在Review写出字段、消费者和回归，再纳入本范围。昵称/频道/资源ID不递归int化。
排除账号退役、云格式、目录迁移、全面存储重写及IO提交可靠性改造。

字段策略必须确定性且fail closed：拒绝bool/非整数身份键、非法结构；归一化冲突不能任意覆盖后授予权限。
成员/管理员/群主等授权字段异常时不创建宽松权限；禁言不能因坏记录静默消失后允许原本受限发送。
已读冲突不能取更大游标触发误读/误焚；非法条目处理及诊断写入Review，不记录真实正文或凭据。
本片实际变更白名单冻结为groups外层GID、owner UID、admins集合值UID、members/mutes内层UID键，以及reads内层UID键。
组的身份键/值、结构或归一化冲突拒绝该群记录，保留其它独立有效群；reads非法或冲突拒绝该会话reads映射，
不取更大游标。bool不是整数身份；字符串仅严格整数表示可转换，具体有效ID范围按现有正整数UID/GID验证。
昵称/会话/资源字符串及其余已正确转换字段保持；管理员和owner必须符合正常成员/角色关系，不从坏记录授予额外权限。
完整字段审计见Review，其中已有正确转换和字符串类型契约不重复改写；不纳入burn pend持久化序列化修复。

验收：真实`ServerStore` JSON往返/独立临时目录重启后继续群发送、成员/管理员/群主权限、禁言/解禁、已读单调行为；
合法与非法主体均覆盖，结果与重启前一致。旧字符串身份键与当前整数键兼容，混合/非法/冲突拒绝或安全降级。
测试验证业务操作，不只把字符串期望改成整数；频道/昵称/资源字符串保留，已有快照其他字段往返不回归。

## KICK：全端撤权与手动重登

入口`Hub._on_admin_kick`、Session活性/注销的必要私有辅助；Web Session/SSE关闭与前端失效处理，
Core ERROR/kicked、连接/发送/重连生命周期及ChatWindow错误处理/退出接线。保持既有MsgType/ERROR code与认证入口。

1. 在同一个锁内撤权提交点确定目标UID现有端集合，使这些Session/token授权失效；通知/底层关闭在锁外。
2. 提交点之后正常认证完成的新端允许存在；迟到旧注销不得清新资源/known/群成员或误下线新端。
3. 提交点前已通过现有业务接受边界的操作不追溯取消；提交点后新请求在dispatch/token解析/直接Web认证入口拒绝。
   各异步队列/文件IO的接受与提交边界在Review明列；不把此目标扩大为RETIRE身份的全部写入屏障。
4. 可达TCP/Web端接到kicked后停止旧登录自动重连，清当前认证/游戏/面板与网络回调，回可手动登录入口。
   网络断开端在失效事件或后续认证失败后收口，不承诺断网UI瞬变；旧SSE回调不能复活，新手动登录可用。
5. 单端logout只撤当前端、普通网络暂断自动重连、SESSION-02最后端清理和其它UID资源保持；不封禁、无冷却期。

客户端精确函数：Core初始化/显式start、`_dispatch/_send_frame/_run/_read_loop`必要闸门；
ChatWindow `_on_error`复用switch登录、`_poll`销毁后立即返回；`quit_app`销毁本root前仅取消此Tk解释器的定时队列，
保留各控件Python命令注册簿，由正常Widget.destroy按所有者释放；不改轮询业务、tkguard或launcher已有回路。
Web `leaveLogin/openStream`及最小认证fetch包装：当前同源受保护API的401在请求token仍属当前登录时收口，
旧401响应不能清新手动登录；首页/meta/login/公开贴纸静态资源与其它HTTP错误不触发退出。
SSE断流先探whoami确认失效或保留普通暂断重连，旧对象和探针回调均有代际保护。

验收：TCP+两个Web全端失效（包含代表/非代表）、旧token/Session拒绝发消息、他人/管理员继续收发，
提交时全部端集合与随后新登录由Event/Barrier交错验证；新端传输/房间/语音名册/群关系不能被旧清理误伤。
Core收到强制失效不再HELLO/发送，普通断线仍重连；真实Tk回登录/新手动会话、生产Web JS及实际HTTP/SSE/浏览器回登录，
刷新/旧回调、已有logout和手动重登均验证。通知时连接失败不得影响撤权集合或他人。

## 验证节奏、版本与终点

- 先冻结切片范围/READY，新增合成回归在原源集合取原红（可用本机隔离导出），再修复和专项/领域。
- 每片实现+必要专项/领域+独立阶段审查满足后自主衔接下一片；普通整改不等用户推动。
- GUI改动另做隔离真实Tk/Web交互；不读取真实用户配置，不启动真实麦克风/摄像头。
- 最终冻结source/test/dependency manifest，按本项目逐文件独立进程全量；真实退出码、UTF8、独立basetemp、
  原失败和skip保留；历史1335/0/2不能冒充本批结果。最终全量失败不得被专项或重试覆盖。
- HEAD/index和入场其它文件保护，实际函数增量、内容ID、原始命令/结果、活动进程与下一动作写入Review/指挥中心。
- 目标/必测/独立审查无未关闭必须项、版本与交付检查点齐备才ACCEPTED；结束Goal。本批未获merge/release，R1里程碑另审。

证据与白名单补充见[CC-02A Review](../review-packages/CC-02A-r1.md)；后续技术决定见[修订草案](CC-02-IMPLEMENTATION-DRAFT.md)。
