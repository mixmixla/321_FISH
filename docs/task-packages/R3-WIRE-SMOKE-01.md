# R3-WIRE-SMOKE-01 v1.1 — 正式预检的有限真实协议门禁

2026-10-21 READY。用户明确批准推进此DRAFT；base/main13e7d21b753bbcd99de1ba81eca69eb40abf1971，fresh fetch同SHA/clean，新分支feature/r3-wire-smoke-20261021；root唯一实现/执行/资料写入，gate_review独立只读，普通模型/Standard。本周有界公开/合并许可仍适用，原件仅本地，未授权发布/强推/绕保护/公开私密数据。

## 最小冻结范围

- 仅扩既有local_trial.py，不新建并行框架/启动器：默认run在TCP/HTTP/双实际EXE登录成功后，使用同一127.0.0.1 server.exe的两个新合成加密TCP peer，执行唯一双向公聊与gomoku/connect4 create/join/start/逐手终局/CREATED复位/round+1空棋盘/双方leave/列表缺房。复用已有crypto和已验证wire状态断言语义；不改业务协议/游戏/GUI/构建/依赖、旧测试/skip/门禁。
- _wire_probe总预算默认45s，单阶段最多5s且不超过总截止；同步peer读写，不新增reader线程。所有socket recv/send及握手共享绝对deadline，防止分块数据持续到来重置超时。待匹配帧队列有上限。严格room/round/stone/turn/winner、真实welcome UID、唯一文本及递增seq，不用旧帧冒充确认。
- peer先登记后connect，任何握手/读写/EOF/断言/超时均finally逐socket尝试关闭；关闭失败可见并使probe失败，不能阻止其它peer收尾。只用自己的socket；所有应用进程继续沿用现正式owned Job启动/清理，不用数值PID kill。
- wire结果进入原run summary/probes，记录阶段/已完成步骤/timeout/error_type/cleanup及耗时；wire失败或异常使正式CLI非0，仍按既有finally清全部Job。startup失败不执行wire；不增加绕过默认wire的开关。结果明确不是GUI/自然退出/LAN验收。

## 验收与边界

先运行既有受影响基线；最终测试同字节原代码RED，最小实现后领域回归/独立审查，再一次适用默认全量，不重复旧全量或为工具扩展重建业务EXE。真实loopback Hub测试只证明协议实现；故障peer验证静默/分块握手绝对超时、途中EOF、错welcome/旧轮次队列/关闭失败及边界预算，正式run失败传播用明确故障注入及真实owned Job收尾测试，不当实际EXE接受。
另复用已验收r3-rebuild三EXE，先核产品源码/产物SHA无业务差异，根正式CLI一次真实双client.exe+server.exe默认wire成功；再一个有明确标记的wire超时故障注入，核实际EXE启动后正式run非0/4Job归零close/源与EXE不变。它是故障路径证据，不当真实服务器自然超时或自然应用退出。隔离新profile/private desktop/loopback、禁发现/托盘/热键/设备/HTTPS，不改系统网络/防火墙或真实资料。
全部raw/完整summary/profile/EXE留新ignored _tmp_gui/r3-wire-smoke-20261021。公开仅local_trial代码、新专项测试、Task/Review/结构化脱敏hash索引、现中心/投影及必要稳定记忆/技能说明，审全部新增文件和新commit history；不公开原日志/用户名/私密/密钥，不发布/删分支/强推。独立0 MUST后有限AI接受、fresh fetch/保护/required checks后正常push/安全集成并核远端完整SHA；无可见CI不当PASS。
完整native GUI/自然客户端或open-server退出/物理LAN/其它DPI/硬件/STT仍未测，旧7文件包的应用产物hash保持原样；本批只工具增量，不升级R3。终点为此一增量交付与恢复入口，不顺手扩产品功能；下一优先级依据真实结果另定。

## v1.1 执行前约束精化（独立设计审查）

welcome两peer共用同一个阶段截止；每个chat/整棋终局重开/离房阶段仅开始时取min(总截止,now+5)，各recv/sendall及分块不重置。raw socket先登记再connect，单帧上限128KiB、待匹配128帧，超限明确失败。初版17case RED17F原件保留；据此补聊天超时/超长帧并强化无效budget不开raw socket，最终19case同字节RED后才实现。未缩短业务定时器或弱化旧断言。

## 预full复审记录（范围不变）

负路径控制器必须核injection_invoked和全部startup成功、wire.exception/timed_out/TimeoutError，不能仅凭exit1；trickle测试夹具收到EOF即退出，避免测试自身忙循环。最终19case原生产同字节RED wire-red-verified-20261021-184134-0f786f60b8为19F，候选原raw备份/finally精确恢复且其它487输入同byte；最终领域wire-domain-verified-20261021-184139-317b7f6eab为84P，source dcf9dfb850acd8530274165b6984655ef457ccc077d438978ffe1cdacbd18757。前序证据保留，不当最终source结果；尚未启动full。

## 最终执行检查点（范围不变）

代码93bc7cbf68027e0a9fbfa101ac5d9e3ef3d056f5，最终RED19F/领域84P，实际EXE正0/明确超时注入负1及两次各4Job清理通过。唯一full wire-full-20261021-185108-b66afa85c5：211文件2958P0F20原skip/exit0，488输入dcf9dfb850acd8530274165b6984655ef457ccc077d438978ffe1cdacbd18757。见[Review r1](../review-packages/R3-WIRE-SMOKE-01-r1.md)/结构化索引；最终独立终审与披露审计待完成，不是R3接受。

独立最终原件/资料审查0 MUST，主控仅AI_ACCEPTED_WIRE_PREFLIGHT_ONLY；最终门禁已完成，普通push/安全集成尚待执行，GUI/自然退出/LAN仍未验。

## 正常集成回执

再次fresh fetch核main仍13e7d21b753bbcd99de1ba81eca69eb40abf1971，protected=false/required checks off/rulesets=[]；按用户本周明确有界合并授权正常push分支/本地FF/普通push main，ls-remote核main与保留开发分支同 `39b6f1038d16abd9c10995e7794992a955d4f2b0`。无强推/绕保护/删分支/发布。该提交check-runs/statuses/Actions均0，无可见CI不等于CI PASS。准确9路径及全部新history已审，原件/用户名/私密/密钥/profile/EXE未公开；488源码逐hash保持（checkout行尾变化仅在当前/原snapshot归一化均严格同Git blob后恢复已验证raw字节），不重跑full。后续仅同范围五份文档/摘要补此回执，最终leaf完整SHA以Gitrefs/本地delivery-receipt为准，无循环修改自指SHA。完整GUI/自然应用退出/LAN/其它DPI等边界不变。
