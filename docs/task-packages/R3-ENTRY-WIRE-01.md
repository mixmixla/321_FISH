# R3-ENTRY-WIRE-01 v1 — compiled入口实际编排与owner死亡清理

2026-10-21 READY。用户明确批准本批。base/main60569347ed3cf93a787a9e6b54bab226c3f4d77e fresh fetch同SHA/clean；feature/r3-entry-wire-20261021。root唯一资料写入/执行，gate_review独立只读，普通模型/Standard。沿用本周代码/测试/项目文档/脱敏摘要公开和正常安全集成许可；不公开raw/用户名/私密/密钥/profile/EXE，不发布/强推/绕保护/删开发分支。

## 已核生命周期与最小范围

friend_trial_start正式支持--mode demo、--nick；demo先新profile，initialize-new/open自己的server，选两个空闲loopback随机端口，再启动alpha/beta actual client.exe并wait_clients。没有无GUI自然结束参数。只用真实compiled StartTrial.exe `--mode demo --nick REL_entry_alpha`，不使用help/dry-run代替、不传bundle-dir、不改entry/launch/protocol函数，不发送GUI/控制台输入或截图，不改等待分支。精确旧包仍base2e2115647940a4025e99f7fcdd112e1fdc9ae416、487/source0a1d29967852b737d3aafa4ea8800d94da3e0747713bc616939e8ea7076052b7三EXE；根当前488/source dcf9dfb850acd8530274165b6984655ef457ccc077d438978ffe1cdacbd18757只含后续外部wire工具变化，不能冒称旧二进制含新harness。

一次有限实际入口运行：保留原七文件包，复制同hash七文件到全新ignored `_tmp_gui/r3-entry-wire-20261021/入口编排 空格/便携包 321 FISH`，从独立空cwd启动。拒已存在目标和整条父链reparse、解析后仍在owned范围。B运行后允许且只允许新trial_runs树，原七文件SHA保持；旧原包不变。外部driver沿已有launch_owned创建私有containment Job/private desktop/OS-only PATH/新合成env，entry自行创建真实四个inner Job，不以外部harness直接启动server/client替代编排。

## 验收标准和观察边界

1. 在≤120s startup预算内，唯一新trial_runs/trial-*只含本次新server/alpha/beta profile与日志，实际audit核REL_entry_alpha及由该run生成的beta nick通过tcp/loopback登录；initializer日志/新store有效，entry root/worker、server和双client短时存活。影像均指新包，无旧数据导入/网络设置/设备动作。
2. 动态端口不猜测/不扫网：从持有outer Job的QueryInformationJobObject ProcessIdList取得成员，只枚举这些PID的TCP记录；将实际双client的已建立loopback连接remotePort与自己server监听端口交集识别唯一chat端口，剩余server唯一loopback监听口作HTTP。仅探测已证实本次server端点，HTTP200后复用根最新local_trial._wire_probe，45s/阶段≤5的既有7步双chat/两棋终局复位重开离房、2socket关闭必须成功。无第二套协议框架。
3. 协议后仍活：entry worker由Job成员、精确包StartTrial映像、父PID是本次直接持有bootloader根共同确定；OpenProcess取得稳定句柄并IsProcessInJob验证，所有观测成员保留QUERY/SYNCHRONIZE句柄（仅目标worker再有TERMINATE）。只对这个已验证worker句柄一次TerminateProcess(code125)注入owner死亡，不用数值PID kill/全局taskkill，不先TerminateJob/关闭outer Job。
4. 注入后≤15s，entry的kill-on-close inner Job应随worker死亡清所有子进程，持有的成员句柄全部signaled、outer Job active_count自然归零，bootloader记录实际非0退出。此观察完成前不得外部强停整个outer树冒充内层清理；若超时/失败，finally只对持有outer Job做containment兜底并记录为验收失败。另一个独立owned sentinel Job在这一期间必须仍运行，随后单独正常资源清理（可强停，不当自然退出）。句柄全部关闭。
5. 记录这是有意注入终止、不是客户端红色退出或完整demo通过。worker被终止时entry finally/session-summary可能未运行，缺失不当产品缺陷或cleanup成功凭证；用持有Job/进程句柄的外部证据验证。完整GUI/自然client与open-server退出/LAN/其它DPI/Windows/硬件/STT/完整compiled demo/无开发环境机器仍未测。
6. 根488及原七文件/副本七不可变输入前后hash保持，运行数据只本次fresh树；inventory使用strict os.walk(onerror=raise)验证完整枚举，不将受限rglob的部分视图当完整、不承诺持续磁盘不变或全系统IO追踪。原件仅本地新ignored根，含操作前后checkpoint/父关系与Job/API必要原件，绝不收集无关进程详情或端点到记录。

## 交付和门禁

先Task/控制器独立预审再运行，出现可复现实际缺陷才冻结最小修复/红绿和受影响检查；纯验收资料沿用同源既有211文件2958P0F20原skip/exit0 full，不重复构建/全量或已完成help/dryrun/正式run。
公开准确5路径：本Task、Review r1、review-assets/R3-ENTRY-WIRE-01/evidence.json脱敏结构化结果/hash、AI_COMMAND_CENTER及其生成任务清单。原日志/完整summary/控制器/用户名前缀/真实数据/密钥/二进制全部本地；审每个新增文件及全部新commit history。独立最终0 MUST后仅有限AI接受本入口编排/协议/owner死亡清理，不升级R3；fresh fetch/保护/required checks后普通push/安全FF，核远端完整SHA和可见CI，无CI不当PASS。
若无安全路线或证据失败，精确保存阻塞/未执行/不确定结果及恢复入口，不加无意义产品/测试工具；本批终点为此一个有限增量与下一项优先级，不顺手扩功能。

## 执行检查点（独立终审0 MUST）

控制器一次实际运行exit0；compiled入口自己编排双client登录/HTTP200，复用wire7步/6.17s/2socketclose。稳定worker句柄注入125后，outer尚未强停即10成员归零/全句柄signaled，bootloader125，sentinel仍活；outer释放0→0，sentinel单独3→0，fallback=False。四原checkpoint保留，session-summary缺失属强杀预期而非自然finally。根488/原七/副本七保持，无代码/full/build变更，见[Review r1](../review-packages/R3-ENTRY-WIRE-01-r1.md)。

实际原件和最终五docs经gate_review独立终审0 MUST，主控仅AI_ACCEPTED_ENTRY_WIRE_OWNER_DEATH_ONLY，未升级R3。终审时仅本地接受；随后审全部newhistory并核fresh远端/保护，已正常push/安全FF，详下节；原件保留，不重复full/build/EXE。

## 正常集成回执

fresh API/随后fetch核main仍60569347ed3cf93a787a9e6b54bab226c3f4d77e，protected=false/required checks off/rulesets=[]；准确五路径及全部新history审计通过，按用户本周有界许可普通push开发分支、本地FF、普通push main，ls-remote核两者同 `dce21358762c67259e27d0a28c8cf0a17303441b`。无强推/绕保护/删分支/发布。候选check-runs/statuses/Actions均0（status pending/total0），无可见CI不等于CI PASS，原API记录SHA已绑定索引。
后续仅同五路径追加此回执，最终leaf完整SHA以Gitrefs/本地delivery-receipt为准；原包/副本七文件及根488保持，不重跑full/build/EXE。GUI/自然退出/LAN/正常完整compiled demo/finally等未测范围不变。
