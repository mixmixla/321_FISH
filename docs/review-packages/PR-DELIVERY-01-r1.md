# PR-DELIVERY-01 — 提交与 PR 交付证据 r1

对应[Task v1](../task-packages/PR-DELIVERY-01.md)，2026-10-01。执行状态只见[指挥中心](../AI_COMMAND_CENTER.md)。

入场HEAD ec73118c86250e555ec455f789e27df67036b2e6，分支fix/cc-01a-admin-credentials、dirty，index空。
远端main仍fbdd915，任务分支尚未推送，无open PR；用户明确批准提交、推送和Draft PR，合并/发布另行。

已验收源集合：CC294项 b1350db334cf981f687fd167a939c4c2e0900e2e58121883fa1621c2a4c43e01；
FILE295项 df4563966335c964541410a35641ba6cf8aefcba88d7068f54432c6e172f4f80；
R1 300项 64b829d183370ebb019abf19d05aaa8abb870db49246cc011a5cb15296abd093。
三层当前文件/历史entry snapshot按SHA256全部可恢复、缺失0，独立方案审查可接受。
独立审查起初建议排除AGENTS，读COORD Task/Review直接证据后已纠正：它属于已验收仓库资料，随docs提交。

Git core.autocrlf=true，无.gitattributes；既有工作区含CRLF或混合换行，Git blob为LF。
原工作区字节保持，逐路径raw SHA→Git clean blob映射单独保存，Git tree不冒称验收raw内容ID。
最终应用候选108文件1335 passed/0 failed/2原有optin skipped，353.79秒；独立终审通过。
本次只整理提交和资料；源码/测试/依赖与合并基线不变时引用该全量及Tk/Node/IAB证据。

三层候选已在隔离index生成，当前任务分支仍ec73118，真实index与当前源码/测试字节未改；尚未推送/创建PR。

| 层 | 候选提交 | 已验收源集合 | 相对父层变化 |
| --- | --- | --- | --- |
| 已有R26 | ec73118c86250e555ec455f789e27df67036b2e6 | 原测试同步补正 | 已有提交保留，不重复cherry-pick |
| CC | 1babebe3714f7ab663987ee4d8446518e9714c34 | 294项，raw ID b1350db3… | 13个管理员相关源码/测试 |
| FILE | f6c2a68dde53b73829943a193fa645e51d3fbd4f | 295项，raw ID df456396… | server三个handler + 新FILE回归 |
| R1 | 30cc0b29898a06ee0b420c76dfe03fe3e8ec032d | 300项，raw ID 64b829… | 五核心文件 + 五新生命周期测试 |

每层raw输入都匹配完整验收manifest，Git tree逐路径只做CRLF→LF clean规范化，无其它字节差异。
规范化后源集合ID（与raw内容ID是不同算法输入，不相互替代）：
CC `71f7b12fe43860255dc37085126a3116e132ba158b1c0a6b2513bc7e4f3d97ed`；
FILE `1fe48938256ec1bd313f7cbbef64242c096ba807edda0ce0e02d040c9267a0cc`；
R1 `e5021eea3ad04f2b2207b95fffbf9015512ff779cf4ccb165a80059da3785d92`。
映射算法同R1 manifest的compact sort_keys JSON，每项以规范化bytes/SHA256计算；逐路径Git blob映射保留本机。
原应用/测试没有改写，原基线main未变，因此引用同冻结代码的全量/独立审查证据，不声称重新跑过测试。

后续：docs候选形成后独立核对树/文件范围/公开资料，原子更新当前分支和index、推送、创建Draft PR。
PR创建后追加URL与创建时head；后续纯交付记录提交由Git历史追踪，不递归声称文档能包含其自身commit SHA。
