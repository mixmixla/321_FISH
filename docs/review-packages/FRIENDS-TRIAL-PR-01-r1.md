# FRIENDS-TRIAL-PR-01 r1

状态：组合完整门禁与Sol独立终核通过（0 MUST），候选分支已push，draft PR创建被连接器HTTP403阻塞；仅允许新分支draft PR，不merge/release。本文件只保存公开源hash和结果摘要，不提交本机资料、路径身份、诊断或运行原始日志。

来源：core raw ID `bde3743b1674054025aea5789c78e32bce78a61e26ae2866e4390e819f988f75`，358输入/152测试；baseline356/source `f30d38ff51f1d75dbe41ae74ffb67b7dbaecd9087ed61ef2af2e979fd8d02cc7` 中353输入保持、3生产stars保护/launcher拒绝流程替换、2对应测试新增。原全部150测试保持。入口6输入source `eab6cadc4ce0ccdecd320fc00b2e508389a2a326f2f1676d878e859521f264e0`；共享run/test_gate/test_sandbox与核心逐字节相同，PR只新增两入口模块及测试，所以组合361输入/153测试。

| 项目 | 实际结果 | 边界 |
|---|---|---|
| core默认完整门禁 | 2211 PASS / 0 FAIL / 2原opt-in SKIP；152文件、exit0、707.892s、单次attempt | raw source bde3743；原始152测试日志hash/cleanup已本机+Sol核，不上传日志 |
| 入口最终专项 | 36 PASS / 0 FAIL / 0 SKIP，exit0 | host故障、部分启动、private desktop真实归属、父死亡子孙清理且另Job存活 |
| 双EXE build/private desktop | PASS、build exit0、新Store、真实双TCP login/HTTP200、image/cleanup | 冻结358源未变，build副本仅2 spec生成差异 |
| 第三EXE/compiled入口 | PASS | 内嵌入口模块/Job/test_sandbox/python314.dll；OS-only PATH、中文空格目录双登录；中断精确新owner PID，13所属PID全exited，bootloader125，无fallback树强停，非自然GUI退出 |
| 本地包 | ZIP逐字节/CRC/hash与8文件范围PASS；无runtime资料 | SHA256 `4b63cda13821a78724dbc8877e90fdfad8c9f92012e1e1299b0f7e2a4ba49035`，61098441bytes；不入Git/不外传 |
| 组合153文件默认门禁 | **2247 PASS / 0 FAIL / 2原opt-in SKIP**；exit0、718.093s、一次 | source `cda76204c1e24f6236eb93e4af74058944a21e6a228d2da51f072e65a69b4ad1`；361输入、153日志/attempt/cleanup已核；无filter/retry/resume |
| manual EXE对局/自然退出/重复操作、console X、其他Windows/物理LAN | 未运行 | 不冒充发布或朋友验收通过 |

所有RED保持：host旧实现27P/3F、private desktop旧API35P/1F（没有用错误API启动GUI），最终36P；第三EXE包装脚本最后path下标错误wrapper1后只修finalization；包初组装找不到代码清单外LICENSE在ZIP前失败后从精确HEAD读取公开LICENSE。旧开发整合2571P/1F/2SKIP及单文件引用数修正30P仍保持，不由核心2211P替代。

CP4 `local_owner._atomic` 历史自然 WinError5/errno13仍BLOCKED/ROOT_CAUSE_UNDETERMINED；六独立实验模块及13测试保留原开发区，未混入PR。正常core的server_store等别的replace路径仍存在，不据本候选通过推断免疫相同OS问题。没有ProcMon捕获、真实资料读取或权限/防火墙修改。

此PR必需前置并非从其它dirty随意选取：核心source358包含credential_ops/server恢复/退役状态及相应wire/IO/生命周期/UX回归，是已测core2211版本；原开发新增owner模型未接ClientCore，完全排除。规范化Git blob与raw tested文件逐项关联，[安全来源摘要](../review-assets/FRIENDS-TRIAL-PR-01/candidate-evidence.json)公开hash可核；本机原始证据仍保留。

Task见[FRIENDS-TRIAL-PR-01 v1](../task-packages/FRIENDS-TRIAL-PR-01.md)，使用说明见[朋友试用候选](../朋友试用候选_2026-10-06.md)。

Git规范化source ID `721644cf6b20a3a7a27585392420001e78715cfcc5d70d3cabc4d17159e15507`；raw→staged/HEAD仅CRLF→LF，297输入规范化，其余内容一致。全部原始门禁日志在本机保留，公开仅源/日志hash与合成结果。新组合PASS不替代开发版历史FAIL或CP4缺陷。

Sol最终只读独审：0 MUST，限定接受本分支commit/push/main draft PR；核过78路径、361源输入、153原始日志hash/cleanup、CRLF→LF唯一Git变换、资料边界和人工待验/CP4限制。原独立报告只留本机，公开保存本结论。

远端交付核对：源码commit `e9ab94aaa34945194ed08799c41c9d001c9b0952` 与remote候选branch一致；main仍 `0c90fd0ecb1d7d38cad1a3082e26fcbe20e23e8d`。创建draft PR返回HTTP403 `Resource not accessible by integration`，再次只读查询该branch的开放PR为0；未创建成功，不虚填PR号。该head CI status context为0、PR触发workflow run为0，本仓没有workflow，CI未运行。修改本段等交付元数据不改变361源输入，复用唯一2247P/0F/2原SKIP门禁。
