# CC-02 后续实现 Task Package 草案

版本 draft-v1，2026-10-01（Asia/Shanghai）。**DRAFT，未获实现授权，不是 READY 任务。**
这是[架构材料](../CC-02_用户会话与数据边界审查.md)的可审查范围模板，
准备工作由[CC-02-DESIGN v1](CC-02-DESIGN.md)批准，准备批准不延伸到本草案代码。
执行状态只见[指挥中心](../AI_COMMAND_CENTER.md)。

## 问题、基线与冻结前置

基线 `d07b29577a48367f887cc0c2dbf1671ed13bb326`，源集合历史raw ID `64b829d183370ebb019abf19d05aaa8abb870db49246cc011a5cb15296abd093`。
已有Web本端退出/Session token绑定/最后端资源清理/文件鉴权/公共游戏生命周期必须保留。
当前删号后同昵称可复用旧UID，私有数据未统一清，踢人只踢代表；本地以昵称为范围，真实JSON恢复有UID键类型风险。

实现开工前必须取得：

1. Pro对架构材料D1–D11的决定；用户批准有限实现批次、范围和权限。延期项明确记录“本批不处理”，不能默认为全选。
2. 从下面候选切片选择目标并分别生成冻结Task版本；写明具体退役/重注册/保留/删除/失败/UI语义。
   不能仅凭本草案给所有切片同时置READY；没有方案决定时保留WAITING_FOR_DECISION/PROPOSED。
3. 重新核对源码/合并base、实际diff、旧主控/Goal/活动进程与原始证据，保存入场保护。
   当前材料未提交，另一checkout必须取得同一资料；PR远端状态需另核验。
4. 冻结每个模块唯一写入者、独立审查者和合成数据路径。并行改代码须独立worktree；真实迁移/删除权限独立批准。

## 候选切片（不是已批准清单）

| 草案ID | 最小目标与可能文件 | 必须先决定 / 范围限制 |
| --- | --- | --- |
| CC02-KICK | `Hub._on_admin_kick`及必要Session撤权辅助；Web/桌面收到强制失效后的UI收口；专项测试 | D2明确踢现有全部端还是单端、是否允许重登、并发attach线性化时刻。若承诺全端UI回登录，必须纳入web.py/client_core.py/client.py必要接线 |
| CC02-RETIRE | Hub登录/attach/dispatch提交、管理员删号、SCHED/DRAFT/CLOUD必要边界、snapshot/restore退役记录；必要ServerStore成功反馈及专项测试 | D1/D3/D4/D7冻结M1或M2、私有/共享/物理策略。M2不能在无本地新身份方案时按“最小包”放行；网络/磁盘IO不持Hub锁 |
| CC02-PROFILE | `unregister`对known资料的更新与回归；如改离线退群另有精确范围 | D9明确保留字段；不把保留资料自动扩大为永久群成员产品变化 |
| CC02-RESTORE | `_restore`中UID map规范化与真实JSON往返后继续鉴权的测试 | D10批准完整字段与旧格式兼容；不得只改单个测试让字符串/整数都通过 |
| CC02-CREDENTIAL | 首次密码认领/改密的原子提交与失败Session处理，保持部署管理员凭据规则 | D6/D8明确权限和已有端撤销语义，不能用last-write-wins注释代替规则 |
| CC02-LOCAL/CLOUD | 服务域/身份范围、本地目录/profile/下载断点、云restore/import与旧数据迁移方案 | D5/D11另审；涉及协议server_id/代际或真实迁移先冻结版本/备份/回滚。不默认归入首批RETIRE |

建议送审先限定KICK与M1逻辑退役，PROFILE/RESTORE可作为独立兼容切片；具体组合由Pro/用户决定。
所有切片都是本次观察衍生的候选，普通实现不得顺手纳入延期切片或FILE_ACCEPT/游戏47入口/EXE。

## 行为不变量模板

- 身份取服务器认证Session.uid，header、fid、昵称/路径不能授权；sessions代表端不等于全部端。
- 本端logout只撤本端，SSE暂断可恢复；最后端的已有清理不重复，也不误清新端资源。
- 退役提交后旧UID不能登录/认领密码/发消息/建资源/读写私有数据/触发定时消息；无论请求此前是否通过入口检查。
- 若采用M1，旧昵称保留且登录拒绝，旧UID不重新分配；若采用M2，同昵称新UID且本地/云数据不得自动继承。
  二者只选明确决定的分支；不把“清消息”称为彻底擦除账号。
- 私有和共享数据按D3/D4逐项冻结；对方消息、群共享资源、审计与下载副本不在没有决定时删除。
- 快照缺新增字段可按旧格式读取；新增退役状态重启不复活。磁盘失败不得报告成功，不能由旧worker/晚到cloud写回旧态。
- 决定回滚策略前，不允许降级旧服务读取新退役快照后重新放行；JSON可解析不等于语义安全兼容。
- 云历史加密口令与登录密码是不同职责；本地旧目录/旧blob没有归属证据时不自动merge/迁移。

## 验收矩阵模板

以下用合成用户、内存/loopback Session、独立临时store与目录执行；只验证最终获批切片，但必须保留既有领域回归。

| 场景 | 必须观察的结果 | 对应切片/决定 |
| --- | --- | --- |
| TCP+2Web、本端退出、SSE刷新 | 原Session token失败；其它端继续正常；最后端清理一次；旧回调不恢复已退出状态 | KICK/RETIRE均保留SESSION-01/02历史保护 |
| 踢全部现有端及他人隔离 | 目标全部端/token撤销、UI按承诺回登录；管理员/他人存活；重登按D2；并发新attach按冻结提交时刻处理 | KICK |
| 删号后同昵称重登及真实JSON重启 | M1拒绝；M2新UID/新本地身份；旧token不恢复，旧私有数据不继承 | RETIRE，D1/D3/D5/D7 |
| 删除与attach/dispatch/CLOUD IO交错 | 用事件屏障强制覆盖端集合抓取后、新端加入、活性检查后写入等窗口，旧身份不能迟到提交 | RETIRE，不使用固定sleep证明竞态 |
| 定时任务已排队/已取出due后退役 | 不发旧身份消息，不复建队列；他人定时消息正常，正常离线任务策略保持 | RETIRE，D3 |
| 草稿/云密文/所有者引用 | 每项按保留表检查内存、快照、独立文件；非法访问无状态副作用；清物理文件需IO失败重试证据 | RETIRE，D3/D4 |
| 最后端资料与群语义 | nick/pwd/sign/avatar/status/invisible/remarks逐项保留或按规则改变；不意外改变退群/转群主行为 | PROFILE，D9 |
| JSON恢复后群发送/管理/禁言/已读 | members/mutes/reads所有UID key统一；真实磁盘往返后继续合法/非法权限操作，结果与重启前一致 | RESTORE，D10 |
| 同昵称并发首次认领/多端改密 | 冻结胜者/失败权限正确，失败不覆盖密码、不留下不该授权的Session；部署管理员不变 | CREDENTIAL，D6/D8 |
| 写盘/replace失败、后台旧快照和重启 | 管理动作不误报已持久；旧状态不会覆盖退役提交；恢复/重试结果和回滚限制可核验 | RETIRE，D7 |
| 同昵称跨服务器/大小写/截断碰撞、旧顶层数据 | 不混账号/服务器；未归属目录保留并按批准流程迁移；E2EE身份不丢失/误共用 | LOCAL，D5 |
| 云包错UID/scope/代际、旧blob及跨身份导入 | restore拒错归属，旧格式按明确策略处理；显式import经规则映射，不直接透明merge | CLOUD，D11 |
| 同名下载/旧.part跨账号/服务器 | 断点身份与完整性检查一致；共享收件箱按决定显式共享，不能冒称账号隔离 | LOCAL，D5 |

现有源码测试索引（本次未运行）：`test_admin_credentials.py`、`test_multisession.py`、`test_web_logout.py`、
`test_session_cleanup.py`、`test_server.py`、`test_r51.py`、`test_drafts.py/test_r29.py`、
`test_r37.py/test_r39b.py`、`test_prefs.py/test_r35.py`、`test_client_core.py`、`test_r53.py`。
新增用例必须验证数据边界/竞态/真实JSON行为，不以复制实现或删/skip/弱化断言达成通过。

## 验证、审查与结束条件

按COLLABORATION三层选测：每个切片专项和受影响域，行为/UI变动做真实Tk/Web交互；最终认证/共享逻辑合并候选全量。
绑定源/测试/依赖、命令/环境/真实退出码、前后manifest和原失败证据；输入不变可引用历史报告，重大新改动不能只引用旧1335/0/2。
独立审查从冻结Task、实际diff和原始证据开始；必须项修复后重审，实施者不自行验收。

完成=所选冻结目标、相关验证、必要最终门禁、独立审查和可恢复检查点齐备；
ACCEPTED、MERGED、Pro里程碑和release分别记录。具体commit/push/PR/merge/release、真实数据迁移与外部消息权限逐项确定。
获得有限范围批准后默认Goal持续完成该批，不自动启动其它候选或恢复旧heartbeat。
