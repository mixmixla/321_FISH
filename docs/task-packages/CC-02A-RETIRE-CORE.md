# CC-02A-RETIRE-CORE — 身份退役核心

版本 v1.1，2026-10-02（Asia/Shanghai）。状态与放行只见[指挥中心](../AI_COMMAND_CENTER.md)。
用户直接批准按[Pro最新结论](../decisions/CC02-RETIRE_核心实施审查决定_v1.md)实施；本Task冻结收窄后的第一有限批次，不执行原完整RETIRE DRAFT。
已完成CC-02A基础一致性历史包保持；原119 handler设计与42全范围矩阵仍是后续参考，不全部转为本批要求。

## 基线、权限和所有权

- HEAD/base `fc9c991bed82dc969aefdbfc9a77a46e75bde5d5`，tree `ba45f96a9de7a55c91b8150eacd78aa6740fe95c`，branch codex/cc02a-consistency；index无待提交。
- 入场371个非ignored路径原字节和原index已保存`_tmp_gui/cc02-retire-core/entry.json`/entry-source/entry-index；原七设计Markdown dirty保持。
  305项源码/测试/依赖仍匹配raw ID `1f94f8fca3da7746c5db293b05e5729e76b37935e1a05d0314658bde9de39830`；旧主控idle、无项目应用/pytest/旧验证进程。
- 允许应用文件只有server.py、server_store.py；backend唯一写入。新增tests/test_cc02_retire_core.py、tests/test_cc02_store_min.py及必要旧测试夹具/兼容断言补强。
  旧admin删除测试若无Store则改用隔离真实Store保留原撤权断言，加退役重启断言；不得删除/弱化断言或新增skip隐藏失败。
- 主控只写本Task/Review/审查决定/指挥中心/生成清单/PROJECT_MEMORY及必要技能事实索引，不与backend并写应用/测试。
  独立审查只读；不并行写server.py。无需UI写入者或新worktree；当前分支/dirty不pull/切分支/覆盖。
- 可以合成临时目录、隔离TCP/HTTP验证与项目.venv测试。不读写真实prefs/history/server_state/audit/web_files/TLS/downloads或设备。
  不commit/push/PR/merge/release、不发Pro/其它聊天消息、不恢复heartbeat。

## 冻结行为

1. 持久retired UID映射仅保存nick/retired_at/operation_id；原昵称映射占用不释放，原UID/昵称不得重新认领，无应用恢复。
   旧JSON无retired字段不推断删号成功；非法新字段/UID-nick冲突不能被宽松恢复后授权；计数是下一个UID，保持单调并跳过退役/注册botUID。
2. 保护默认/当前配置保留管理员昵称所绑定身份、当前已认证管理员UID及实际BOT_BY_UID；不永久保留bot昵称、不猜历史管理员角色。
3. 登录早于密码/zombie处理先查退役；真正attach、普通claim摘要最终写回、Web token发布处复查。PBKDF2在锁外，set_password/旧unregister不得重新建立退役known。
   这只是退役屏障，不实现普通并发认领/改密版本CAS/改密退出全端。
4. 核心写入最终C在Hub纯内存锁内检查retired/pending，再整体提交：CHAT publish与burn关联登记、DRAFT、SCHED_SET/CANCEL与已取due最终publish、PROFILE字段（sign/status/invisible/remarks与avatar元数据）及必要本人blocks/reads。
   不只增加dispatch入口if；A通过但尚未C的核心请求在t0后无副作用。KICK已有A语义、新登录保护和单端logout保持。
   私聊核心发布同时验证目标UID的退役；纯引用的共享作者/备注UID不自动触发他人数据删除。
5. ADMIN_USER_DEL改为幂等M1：锁内t0建立retired及runtime pending、撤全部当时端/token、清known/本人draft/sched/blocks/reads与可靠作者burn跟踪、沿既有clear_uid/移群/转群主/空群规则处理。
   网络通知、连接关闭、旧运行资源清理、审计与强制save在Hub锁外；旧注销不能恢复known。已完成共享任务/投票/附件/动态/他人消息/副本保留。
6. 没有必要Store时t0前拒绝永久退役，不清状态或报成功；IO/编码失败pending保持当前身份阻断并反馈failed/unknown，不能自动回开。
   成功必须确认当前被保存候选含正确op_id的retired与核心逻辑清理。首次D从未成功仍可能在旧有效JSON重启后复活，保留明确限制。
7. 最小store前置：ServerStore.save只在dump/flush/fsync/replace全部成功后给明确成功，失败向Hub传播；Hub只在真成功推进fp/确认。
   普通/后台/force/flush共享可验证顺序，已取旧候选也不能在更新成功后覆盖。可用运行态提交序号/锁，不增加持久revision/hash证明/marker/loader state machine。
   一致捕获至少将核心t0涉及bus/Hub置于同一内存边界并深复制known.remarks等；不在Hub锁内等待writer或磁盘/网络IO。
   若既有burn.pend=set使实际JSON不可编码，可仅按现有restore期望的UID列表做这一字段的序列化适配，不递归重写其它格式；记录精确增量和回归。
8. 服务端沿ADMIN_USER_INFO可选retirement字段返回pending/failed/unknown/confirmed/op_id/目标；同UID请求重试/查询不新建账号。仅confirmed后发持久退役成功广播。
   不改client_core.py/client.py/web.py/protocol.py；当前客户端发送前pop及deleted自动重连交互仍有后续工作，不宣传完整UI或资源闭合。

## 必须保持和明确延期

v1.1属于普通实现边界澄清，来源为Task独立预审/阶段审与主控实际调用链核对；用户批准目标、应用文件与外部权限未扩大。
`_on_chat`的私聊bot目标会通过`_bot_dispatch`直接发布**用户CHAT输入**，故这一输入的纯内存最终C纳入CHAT必要辅助。
不得由此修改`bot_say`回复、bots.py/Agent/提醒或资源访问；bot回复与异步迟到资源仍延期。候选的回复改动应恢复入场AST。
若使用额外短内存barrier，必须从Hub后取得，统一Hub→barrier→bus且从不持它进行IO；不得出现barrier→Hub反向等待。它不能作为119 handler全包装器。
READ/burn的锁外事件重构必须保留原`_burn_ttl_sweep`懒清理触发和业务语义，不能漏调用或擅自改为新周期策略。
confirmed退役操作幂等不可被重复请求的新save失败降级；新字段解析只保护实际bot UID，普通UID同bot昵称不得因新永久昵称预留而被拒。

PROFILE资料保留、CC-02A groups/reads严格恢复、KICK全旧端/新端隔离、SESSION-01/02、FILE-AUTH-01与既有群/公共游戏生命周期不能回归。
不改CLOUD文件/格式/扫描、Web upload、bot/Agent/preview、vmemo/sticker/moment、游戏/语音房规则或全部119 handler。
核心清理承接原注销的运行资源规则，不重写其产品语义；必要内存字段if或锁内IO移出辅助先记Review，不扩为资源任务。
延期完整CC-02B-STORE、CC-02C-RESOURCE、CC-05-STORE-HARDENING（marker/full loader/InitializeNew/durable intent）、CREDENTIAL/LOCAL/CLOUD迁移/游戏筛查/EXE。

## 验收矩阵与节奏

| 场景 | 本批必须证据 |
| --- | --- |
| 原缺口/正常身份 | 同一新增核心回归对入场raw源取得原红；修绿后其它UID/管理员/bot与普通KICK/logout可用 |
| 退役认证 | TCP HELLO、两个Web端、免密/已有pwd/attach→claim→token的Event/Barrier交错；旧名/UID/token不能再授权，保护集拒绝无副作用 |
| 核心迟到C | CHAT与burn关联、DRAFT、SCHED/已摘due、PROFILE/密码/必要blocks/reads暂停在最终C前→t0→继续，无旧UID写回；已C的网络送达不追溯擦除 |
| 数据表 | 本人私有记录/作者消息/群授权按表清理，其它用户、共享引用、完成附件、审计/备份等保持；UID计数/映射无复用 |
| 存储失败 | encode/open/write/flush/fsync/replace失败、无Store、重试与响应丢失；fp不假前进、pending不回开、不发confirmed，真实旧JSON状态可核验 |
| 写顺序/快照 | worker已取旧候选→强制新退役→旧继续、force/flush交错与嵌套remarks修改，Event/Barrier证明无旧覆盖/混合核心快照，无Hub锁内IO |
| 真实JSON重启 | 合成独立目录真实ServerStore/JSON成功后以新Hub继续认证与发送，旧名/UID失败、共享保持；首次失败用旧有效JSON的负例如实记录不保证重启阻断 |
| 领域与最终 | 影响领域逐文件、真实TCP/HTTP登录/旧token/管理结果；冻结实际raw源/测试/依赖后项目逐文件全量，真实exit/UTF8/独立basetemp/原opt-in skip/历史失败完整；不能引用1355/0/2冒充新候选 |

应用/认证/持久化变化必须最终全量；版本不变的选测/审查复核不重复整套。每轮先受影响专项再领域，最后唯一冻结全量。
原始命令/退出/hash/环境/屏障及进程记录见[Review](../review-packages/CC-02A-RETIRE-CORE-r1.md)与指挥中心；本机辅助不是状态来源。
backend实现者不能自验；独立Task/实际diff/原始证据终审无未关闭必须项并满足矩阵后才ACCEPTED。
按用户已批准Goal偏好连续完成本有限批次，到终点结束；不自动衔接STORE/RESOURCE或Git交付，完整RETIRE/R1里程碑另记。
