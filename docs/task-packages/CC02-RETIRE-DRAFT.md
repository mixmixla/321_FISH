# CC02-RETIRE — M1 + STORE-COMMIT 实现 Task 草案

版本 draft-v1，2026-10-02（Asia/Shanghai）。**DRAFT / 未获实现授权 / 不能置 READY。** 状态只见[指挥中心](../AI_COMMAND_CENTER.md)。
本草案是[资料批次](CC02-RETIRE-DESIGN.md)输出，按[自包含 Pro 材料 v1](../CC02-RETIRE_Pro审查材料.md)冻结候选边界。
它不替代[架构决定 v1](../decisions/CC-02_架构审查决定_v1.md)，不修改 CC-02A 已验收范围。

## READY 前置

- Pro逐项回答材料P1–P7，确认提交/锁序/数据表/回执/保护/失败与重启边界，关闭必须设计整改项。
- 用户批准下一有限实施批次和准确文件、数据、Git/发布权限；技术意见不自动授予实施或真实操作权限。
- 开工重新核对旧主控/Goal/进程、HEAD/branch/index/dirty与当前Review；不以本草案中的一次HEAD冒充未来开工版本。
- 资料读取版本 HEAD `fc9c991bed82dc969aefdbfc9a77a46e75bde5d5`，代码依据e065591，raw305 ID `1f94f8fca3da7746c5db293b05e5729e76b37935e1a05d0314658bde9de39830`。
  未来代码基线有变，先做实际diff与原不变量核对，重新冻结实现Task v1，不能沿用旧审查结论。

## 目标、不变量与候选文件

M1：原昵称→原UID关系保留、UID不再分配、同昵称不得认领；运行态pending阻断新认证/迟到写入；成功JSON才确认永久退役。
保护当前可证管理员保留名/已认证UID及BOT_BY_UID；P5新增范围必须写入正式Task，不能猜旧历史角色或覆盖同名用户。
JSON旧字段兼容不等于允许旧程序降级。未启用必要Store在t0前拒绝；首D失败保持本进程fence，不虚假保证重启阻断。

候选应用文件：server.py（唯一后端写入者），server_store.py（同后端归属），bots.py（仅提醒入队/摘取接统一Hub提交，不改bot功能），
client_core.py/client.py/web.py（现有退役请求/失效/管理员结果接线、准确文案与Web直接写入口屏障）。
若采用ADMIN_USER_INFO可选业务结果字段，protocol.py仅补既有帧说明；不新增server_id/身份代际/协议身份字段。
agent_bot.py、games_pkg、run.py/dev.ps1、依赖、LOCAL/CLOUD包格式和目录迁移默认不写；中央bot_say fence应承接Agent迟到结果。
需要额外模块时先记录必须理由/Task版本并核对批准范围，不把草案候选自动扩大成允许清单。
候选测试文件：test_cc02_retire、test_store_commit、必要客户端/Web专项；保留既有行为断言，不按数量删用例。

主控与后端实现者不并写server.py；UI并行采用独立checkout/worktree，不覆盖已有用户文件；独立审查者只读实际最终树与原始证据。
未来实施可以合成数据验证；真实prefs/history/server_state/audit/web_files/TLS/downloads不读写，不自动执行部署退役。

## 分步实施候选

1. STORE-COMMIT：统一普通/后台/force/flush writer，writer获得后才采集一致深快照；完整内存C一次递增revision，严格实际UTF8 bytes/SHA256+fsync+replace回执与清理证明。
   确认成功才推进fp/acked，捕获后新revision继续dirty。快照字段变更与bus遵循Hub纯内存提交规约，锁外IO。
   replace后receipt异常不假称旧文件仍在，保留unknown/fence，在writer下严格读盘查询；投递/audit失败不反写已确认JSON结果。
   P7确认结构化load、非退役意图store.initialized与InitializeNew入口，先restore再CLOUD/开放认证；已有state缺失不空启动，tmp不自动提升。
2. M1：严格retired字段、运行pending/操作ID、uid_seq单调/跳过实际保留UID、保护集；前置昵称拒绝与attach/claim/token最终复查。
   不采用known缺失为身份删除；严禁旧unregister/管理员目标资料写回重建活跃known。
3. 全C覆盖：Pro材料4A的119/119 handler表与4B旁路表是附件；逐项actor/私有owner/A/完整C/t0/D/锁/IO必须落实，dispatch只是入口检查。
   UID升序→资源锁→Hub→bus，writer→Hub→bus且不取UID/resource锁；CHAT/burn等关联状态同一次C，preview作者gate、due私聊接收target也查fence，zombie在登录fence之后。
   实现直接passwd/upload/logout/SSE、due、bot/Agent结果、preview、CLOUD最终提交及启动索引过滤。
   UID final-commit gate与t0排序；哈希/网络/staging锁外，群文件和READ-burn旧锁内IO做必要拆分；不顺手修游戏玩法。
4. 数据表：材料第6/6A节逐字段/物理目录作为正式Task附件原样或经Pro版本化修订。清本人known/draft/sched/blocks/reads/sticker_subs/提醒、可靠作者seq对应burn跟踪，沿原作者消息/移群规则；共享/缓存TTL/未完成上传隔离/物理保留与访问隔离按表落实。
5. 管理结果/UI：使用Pro确认的6B回执：ADMIN_USER_DEL发起/同UID重试、ADMIN_USER_GET查询、ADMIN_USER_INFO.retirement含pending/failed/confirmed/unknown和op_id等。
   “已提交/已阻断待提交/失败待重试/持久成功”分别呈现；取消Core发送前乐观pop，发送False不改缓存，超时先查询，不以HTTP200/已提交代替D。
   受支持客户端识别ERROR/deleted并停止旧自动登录；手动登录旧名被拒绝，其它账号/KICK正常重登保持；不新增Web退役产品入口。
6. 领域/真实UI/真实JSON重启/最终同版全量/独立终审；全部满足才应用ACCEPTED，merge/release/R1里程碑分别记录。

## 验收要求与版本证据

材料第9节完整矩阵 E01–E17、S01–S07、I01–I07、R01–R08、U01–U02、G01 共42项是候选验收附件（全部未执行）。
必须覆盖各实际入口最终C；竞态用Event/Barrier控制，不靠固定sleep证明无竞态。
IO失败含真实dump、open/write/flush/fsync/replace/残留tmp清理失败；旧JSON保持可读，不推进ack/fp、不误报成功、fence/dirty保留。
真实独立目录ServerStore/JSON重启验证成功后退役、私有清理、共享保留与CLOUD扫描过滤；失败首次提交的负例如实记录未解决的重启限制。
ADMIN默认/有效名、动态bot注册、UID序号/冲突、非法新增字段/坏JSON/读取错误均须fail-closed或明确受控恢复。
模拟Store回执不能代替真实写盘；源内编码失败不通过default=str掩盖。P7可能的兼容修复只按正式Task精确字段进行。

受影响领域至少包括CC-02A三片、SESSION-01/02、FILE-AUTH-01、持久恢复/定时/草稿/CLOUD/群文件/bot/媒体/消息操作和公共房间生命周期。
最终认证/核心共享状态/持久化改动必须按项目同版逐文件全量，UTF8、真实exit、独立basetemp/环境/原opt-in skip及失败历史完整。
历史113文件1355/0/2不冒充新版本结果；先专项、领域和真实UI，冻结完整manifest后唯一全量，版本不变不盲目重复。
每片保存Task版本、base/head/dirty、候选raw内容ID、精确命令/日志/exit/屏障顺序、活动进程和下一动作；最终review与实际diff绑定。

## 明确排除、权限与终点

CREDENTIAL普通认领/改密比较提交、改密撤全端语义、LOCAL/CLOUD格式与跨服务器restore/import/迁移、广泛物理擦除/GC、数据库/WAL大重写、游戏筛查/美术、EXE/发布均排除。
P3如不接受无durable intent的首失败重启限制，必须另冻结必要持久意图方案，不用运维一句话假装实现了抗重启保证。
commit/push/PR/merge/release、真实数据/设备、外部或Pro消息、heartbeat各自需要下一批明确授权；本草案不授予。
应用ACCEPTED需独立审查与完整原始验证，不能由实现者自验；Goal至获准有限批次终点停止，不自动衔接CREDENTIAL/LOCAL/CLOUD/游戏筛查。
