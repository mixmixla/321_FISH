# LOCAL-RELIABILITY-20261025 r1

2026-10-25 IMPLEMENTED / INDEPENDENT_CODE_REVIEW_0_MUST / FINAL_FULL_PASSED / FINAL_TECH_REVIEW_0_MUST / PUBLIC_REVIEW_0_MUST / AI_ACCEPTED_TWO_FIXES_ONLY。范围为
[PREFS-INVALID-ROOT-01 v1](../task-packages/PREFS-INVALID-ROOT-01.md) 与
[SCHED-FINITE-TIME-01 v1](../task-packages/SCHED-FINITE-TIME-01.md)。
base已Git/API双核 `41a01148f8d87464270993484c8a78f9fd9c1794`。

## 分工与边界

root唯一prefs实现、集成资料和最终组合全量；server_scout在独立工作树实现server时间输入门；
identity_scout独立设计、代码与原始证据审查，不参与实现。两个实现树各自单写者，原main树与
暂停视频分支未改变。Astra配置用于两个代理；FAST为用户选择，工具未提供实际服务回执。
本轮不恢复旧Goal/heartbeat，不读取真实资料或安装工具，不改变系统/保护/权限。

## PREFS-INVALID-ROOT-01

server_scout正式设计审查0 MUST。仅 `Prefs._load` 在JSON解析后拒绝非object根，
复用现有 `_load_error` 与拒写路径。新27例覆盖8类非object输入的登录选择、普通设置和UID绑定，
加缺文件/空object/带未知键object三正对照；没有修改旧断言或skip。

原产品单次RED `pir25-red`：24F/3P，actual exit1，1.690s，source
`556ddc1e22f10c24a0f68be55e7c3910ac955c189110a8a075189fd492474ca7`，
summary SHA `88c512f5b64475092d2c9d3de3891527c8f51376f05a4f1aaf2522a2bc46eae6`。
首次修复及相关领域 `pir25-green-domain`：7文件131P/0F/0S，actual exit0，20.313s，source
`6be2a2ab620beb8e595f09767a51eeb24d147f2589b4c9d56e9f8fc48c5292ad`，
summary SHA `cfe65747014be6362cdf187c6b05fbb33aae02780484021b557dadeb0846b57d`。
新测试27P，RED/GREEN测试字节相同；原summary、原log计数/哈希、sandbox、单attempt清理、
manifest指纹和源码快照已由root复核。identity_scout独立代码/全部原件审查0 MUST。
24个RED均未抛预期异常；其中8个UID例止于绑定断言，没有执行后续写入，不能称全部已发生覆盖。

## SCHED-FINITE-TIME-01

identity_scout正式设计审查0 MUST。精确原故障链为NaN入scheds后，durable
`_persist → recovery.validate_snapshot` 的verify阶段失败，继而 `_fail_store` 置FAILED/停止事件。
正负Infinity原来已有past/far拒绝，不能称其污染；巨大整数是转换溢出。
实现仅+4/-1行：float转换捕获OverflowError，入队前math.isfinite拒绝。
`sft25-red` 原版9F5P/exit1/2.555s，source
`62f1e55bbe67e6baaea8e311ad35a4a1cbad8fb0e30c0eef689a8ca4b59fb919`；
独立durable用例先实际force persist再断言，明确观察persisted=False/ready=False/stopped=True/FAILED。
`sft25-green` 14P/exit0/1.724s，`sft25-domain` 六文件194P/exit0/28.222s，
后二者source均 `f8434a887c972512e8ee8623910e81b6e2e401b7357c4c5da8644cd85453f8ee`。
原summary SHA分别为 `e248ea1ca4b78f2db4b1128d8f91f265238c52d84bb9310e331978fe2b90b237`、
`13e0d1d08e3e623e2446652c6c99d034f7c66c7a0f87efd642bbdab810918304`、
`7b207763da12b9ccbd04388274ef7c2dcc229ff8617fb7c1f17d839cf7b770f5`。
测试字节RED/GREEN保持；真实Store恢复后两条合法定时到期发送并再次持久化成功。
identity_scout独立代码/三run原件0 MUST。实际shell退出来自实现者工具回执，独立磁盘核验的是
summary/progress/每个child exit，不虚构磁盘shell记录；root拷贝两文件与已审候选逐SHA相同。

## 组合冻结

503输入/source `702ccc0c4147cac8db36830124f75009da1160b58db44b78d3f059b4f72502d5`。
相对旧501/source81c36be8，仅prefs.py、server.py及两个新测试四路径变化。
首次本地freeze核验脚本从另一cwd调用Git枚举原main树，受safe.directory限制而退到非Git枚举、
漏四个非mandatory输入；该断言失败与诊断在工具记录保留。实际四文件原字节相同；仅改本地核验脚本，
以原完整full manifest枚举501并逐SHA核原main，未改Git/system配置、产品或测试，也未因此重复测试。
唯一组合full `lr25-full` / exec64067已自然结束：225文件3111P/0F/20既有skip，actual exit0，813.691s。
summary SHA `1f48d637772b901315cfdfd408d5903056ce4308f399bb4983ec060d9c108ae7`。
root24项后验全true：当前/冻结/快照503输入完全相同，225集合与全部原log哈希/计数、sandbox、
单attempt/清理与真实shell退出一致；旧223每文件计数及skip保持，仅新增27+14个通过。
解释器/依赖/门禁身份相同，五阶段原件、旧UID失败和暂停视频失败SHA保持。没有活动Python测试。
脱敏索引见[结构化证据](../review-assets/LOCAL-RELIABILITY-20261025/evidence.json)。

## 验收与交付待办

identity_scout已独立重算225原log计数/哈希/退出/清理与503当前/冻结/快照，旧223计数与20个skip原因不变，
完整501原main清单、五专项及两个历史失败均核，最终技术0 MUST。server_scout仅审公开资料准确性，
精确12路径、六run结构化摘要、425相对链接与中心投影/隐私边界全部通过，不作为其server实现自验。
root据此记录有限AI_ACCEPTED，仅本批两个Task，不是用户/Pro验收或完整里程碑通过。
当前不重复已完成全量。
原始证据仅ignored本地：集成树 `_tmp_gui/local-reliability-20261025` 与原工程短run目录。
当前未提交/推送/合并；新增Git对象审计尚待完成。按用户本轮授权正常提交、快进main并非强制push，
只公开代码、测试、项目文档和脱敏摘要；不PR、绕保护、发布或上传EXE/raw。

暂停视频4759及其0xC0000005失败、历史UID第一full失败永久保持，不被本次通过覆盖。
完整GUI、自然退出、物理LAN、STT和现有EXE包含本修复均未验证。
首次创建UID共享父目录的竞态仅候选，本批不实施。
