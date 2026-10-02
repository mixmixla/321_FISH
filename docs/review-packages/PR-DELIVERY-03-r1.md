# PR-DELIVERY-03 — 已验收CORE提交树与 Draft PR #5 追加交付

2026-10-02（Asia/Shanghai），对应[Task v1](../task-packages/PR-DELIVERY-03.md)。状态只见[指挥中心](../AI_COMMAND_CENTER.md)。
用户直接授权可交付时提交PR；当前已独立验收CORE满足，Git补充授权不扩大下一产品/真实数据/合并发布权限。

## 入场与实际PR

GitHub get_pr_info与ls-remote均核对PR5open/draft/未merge，head fc9c991、base main cc7e295；当前分支正是其head。
本次追加已验收CORE及必要退役设计资料到现有PR5，更新PR标题/说明覆盖最终范围，保持Draft，不新建重复前置PR。
376入场非ignored raw文件/原index/明确6code+13docs边界已保存_tmp_gui/pr03/entry.json与entry-files；307source c647d65c…与门禁逐项一致。
CORE115文件1392/0/2、391.32秒、原skip/失败/实际通道与独立终审保持，本次不改源码/测试/依赖，不重新运行应用门禁。

## 执行与独立审查记录

主控唯一Git/资料写入，独立代理只读核对实际提交树和原115日志/manifest，不参与code修改。
源提交/资料提交/推送/PR元数据结果在真实完成后追加，不提前宣称成功；原代码与设计正文不覆盖。
下一阶段提示词将先核对CC-02B-STORE已实现前置与剩余范围，不自动把候选或本交付授权变成产品实现。

## 代码层实际提交

精确6路径提交`e91c1be5a666d692ce152f1f8ec89fa22771661c`，parent fc9c991，tree edfa04b316bf32c03a4ff5fdb483aec0ad1ecc96；未改应用/tests原字节。
307raw输入与门禁仍c647d65c…；Git clean/blob规范化及独立实际树校验另记录，不把换行变化混为代码行为改变。
当前仅本地code层完成，docs/push/PR更新尚未宣称完成；旧main/PR状态保持，不启动下一产品。

## 资料层、独立树与实际Git交付

资料层精确13路径提交`13ad59231a762112c88b934d50ba827db4a134f1`，parent e91c1be、tree f3983f656ca9fecfc4645a76de8c443b7c2a0543。
上述“当前仅本地”是代码层时检查点；现在两个逻辑层均已推送，后续仅指挥中心/本Review/生成清单补录实际结果。
本机flow提交记录保存精确SHA/parent/tree/路径，最终HEAD以Git和远端PR实际读取为准，不构造文档自引用SHA循环。

307raw source仍`c647d65c7061ceb67e26bd571520230ed84730b0480968b5ea6c809abdae2f28`，Git clean规范化ID
`49e5a054144788ff98c2fbba5dd7109888600cfd4b9a6dc0ecbbae983083394d`，raw/hash-object/blob零不一致。
code6/docs13/父子树/入场delta19路径精确，无runtime/凭据/真实data/依赖新改；132相对链接、投影、index空/diff-check及未授权文件原字节检查通过。
三旧设计正文IDc45e7f27…保持，CORE原始证据保留。独立pr03_tree_review从实际树及原115日志复算1392/0/2/exit0、summary SHA c4fb12b2…，可接受，无必须项。

`git push origin HEAD:refs/heads/codex/cc02a-consistency`真实成功fc9c991→13ad592。
紧随其后的ls-remote TLS unexpected EOF失败保留；只读重查成功确认head13ad592/maincc7e295，没有把推送成功改记失败或重复创建PR。
GitHub connector更新PR元数据403（Resource not accessible by integration）；随后按用户Git交付授权使用现有Git认证，仅在内存调用PATCH现有PR5成功，未打印/保存凭据。
实际[PR #5](https://github.com/mixmixla/321_FISH/pull/5)标题为“fix: 保留资料、多端撤权并实现 M1 身份退役核心”；body SHA256
`21039910bb882811d9df24cd64e7c080958452db28bcd8d3fe110bb960682680`。
更新后head13ad592/base maincc7e295，open/draft/merged=false；本聊天attach成功。后续三文档flow正常push只改变交付状态，不扩大PR实现范围。

本有限交付已ACCEPTED，三文档终核与实际远端HEAD复核后结束Goal；不宣布完整RETIRE/STORE/Pro R1通过，不merge/release，不重跑同版应用测试。
下一阶段仍在R1：先冻结CC-02B-STORE剩余最小范围，再处理CC-02C-RESOURCE。下方提示词供新批准批次使用，本轮未启动其资料或代码。

## 下一有限阶段的可复制提示词

```text
继续 321_FISH，工作区 D:/Project/321_FISH。

先读 AGENTS.md、COLLABORATION.md、docs/AI_COMMAND_CENTER.md、docs/任务清单.md、
docs/连续开发与换窗口接续.md、docs/decisions/CC02-RETIRE_核心实施审查决定_v1.md、
docs/task-packages/CC-02A-RETIRE-CORE.md、docs/review-packages/CC-02A-RETIRE-CORE-r1.md、
docs/review-packages/PR-DELIVERY-03-r1.md 和 PROJECT_MEMORY.md 必要段落。

接续背景：CORE v1.1 已独立 ACCEPTED，115文件1392 passed / 0 failed / 2原有opt-in skipped，
实施Goal complete；已追加至Draft PR #5。实际最新HEAD以Git/PR/指挥中心为准。
核对旧主控、Goal、HEAD/分支/index/diff、PR和活动进程；旧主控活动时先只读，避免第二写入者。
保留交付，不自动pull/切分支/覆盖，不重复同版门禁，全部shell使用pwsh。

本次批准CC-02B-STORE-SCOPE资料准备与有限Task冻结，请用Goal持续完成：
1. 只读核对save、snapshot/fingerprint、persist/sync/worker/flush与退役结果的已完成和剩余。
   save真实True/False、writer取顺序锁后fresh capture、request_seq保留后到dirty已完成，不重复实现。
2. 判断必要的剩余：严格一次JSON bytes、阶段IO错误、实际bytes回执/op确认、unknown查询与重试。
   revision/SHA/proof仅在必要且有限时采用，给最小等价方案，不直接扩成Store V2。
3. 交付自包含Pro审查材料、待决定问题和版本化实施Task草案，冻结文件/接口/锁序/失败/重启限制，
   包含Event/Barrier、IO失败、真实JSON与结果查询验收矩阵；重大取舍留给Pro审查。
4. 独立资料审查、文档/版本边界检查，先更新唯一指挥中心再生成任务清单；交付后结束Goal。

只读源码、写文档；不改应用/测试/依赖，不运行应用/pytest，不commit/push/PR/merge/release，
不读写真实数据，不发送Pro或其它聊天消息，不恢复heartbeat。
marker/InitializeNew/整体loader/durable intent归CC-05；CREDENTIAL CAS、UI、LOCAL/CLOUD格式迁移、
完整119、资源代码和物理GC不纳入。列出CC-02C的CLOUD/upload/bot/preview剩余，但不实现。
普通资料整改自主完成。Pro必要决定落实、用户批准下一有限实施Task后才进入代码。
```
