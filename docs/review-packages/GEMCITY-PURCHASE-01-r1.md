# GEMCITY-PURCHASE-01 r1 — 璀璨宝石购买原子性

2026-10-13。依据[Task v1.1](../task-packages/GEMCITY-PURCHASE-01.md)。
**IMPLEMENTED / INDEPENDENT_CODE_REVIEWED / FULL_FAILED / NOT_AI_ACCEPTED**。
完整158文件门禁已自然结束；不是AI_ACCEPTED或合并/发布验收。

## 问题与修复

保留卡在检查资金之前被移除，拒绝动作也丢卡。各色校验重复计算同一份万能金，
两色各缺1、仅1金仍可以买成功并使金余额变-1。两项均违反GameRuleError状态不变合同。

修复仅在 `games_pkg/gemcity.py`：先算折扣后实际彩色支付量和总金需求，整体足额
才统一扣款；保留卡在 `_buy_card` 成功后移除。彩色优先、市场补牌、贵宾、得分和
补回合逻辑保持。没有UI、协议、门禁策略或其它游戏行为改动。

`tests/test_gemcity_purchase.py` 新增21项行为回归：两条购买路径不足拒绝完整状态和
RNG不变；足额成功的支付/供应守恒、不负数、卡牌归属、补牌/相邻保留卡、一次推进；
折扣/贵宾/胜负补回合及RoomManager入口。没有修改RED中的断言。

## 当前验证与独立审查

[完整合成证据与每份原日志](../review-assets/GEMCITY-PURCHASE-01/evidence.json)：

| 运行 | 结果 | 含义 |
| --- | --- | --- |
| 干净main门禁诊断 | 1文件8 PASS，exit0，24.878秒 | 历史3秒collection超时本轮未复现，不改该合同或抹历史FAIL |
| 原规则RED | 1文件9 FAIL/12 PASS，exit1，2.113秒 | 9项失败均对应上述购买缺陷 |
| 修复领域 | 7文件86 PASS/0 FAIL/0 SKIP，exit0，14.859秒 | 规则/房间/服务端生命周期通过 |
| 完整门禁 | 158文件2323 PASS/3 FAIL/2原opt-in SKIP，exit1，809.201秒 | 两个无关测试文件失败，原样保存，不当全量PASS |

候选 source ID `c56eefa861bd569c11cea74cac8c202506845867a8bba061a829efce6d6bea60`。
独立Sol代码/领域审查0 MUST，[原始审查结论](../review-assets/GEMCITY-PURCHASE-01/independent-code-review.md)。
371受测输入和当前源码hash一致，RED→领域仅生产GemCity改变；领域7份日志均单attempt、
真实exit0、hash匹配、cleanup_ok。完整158日志同样逐份单attempt、hash匹配、
cleanup_ok，无意外skip；全量与领域source ID一致，工具session54447已自然结束。
独立终核再次核167公开原日志/4个summary SHA、158单attempt/cleanup/原skip及371输入。
其中flagship GUI原文仍打印Tcl `invalid command name` after回调诊断，尽管pytest 6 PASS；
保留该观察，不据全量/该文件通过声称自然退出、完整GUI或EXE已验。

本任务原日志通过窄`.gitattributes`保留字节和pytest诊断尾随空格；仅这些原输出不做
空白格式改写，源代码与手写资料仍正常检查。公开日志Git blob SHA逐份匹配记录的raw SHA。

完整门禁的3条失败：Web踢出夹具抽取closeLobby但漏其真实uxSelectNavigation；R32两条
高度断言仍要求1行，实际视觉默认3行。没有在本任务修改这些无关测试或产品。
干净基线正式对照未完成，不宣称本环境“已有失败”。后续最小夹具/合同整改另冻Task。

## 版本、边界与待完成

base `08d263b2a78b7a6df0b888616e2fbf44793182b8`；独立分支
`fix/gemcity-purchase-20261013`，工作目录 `_tmp_gui/gate-collection-20261013`
沿用初始诊断名称。代码commit `1153e068dd06ec8af6f65f1df89c2b9184a6b12e`
已普通push并核远端一致；Draft PR创建因连接器403和浏览器控制启动错误受阻，尚无PR号。
[交付回执](../review-assets/GEMCITY-PURCHASE-01/delivery.json)保存入口与原因，不沿用旧审查为本候选通过。

[原工作区边界](../review-assets/GEMCITY-PURCHASE-01/boundary.json)：原开发HEAD c864234、
原分支/index与入场1145公开文件保护；原目录只更新本Task/Review、指挥中心与投影。
没有pull/stash/reset/clean/强推或真实数据操作。PR7/8已由实时GitHub确认merged；
本轮没有merge/release权限，没有主分支push。

完整门禁和证据归档/独立原证据终核、任务分支commit/push已完成，draft PR创建仍受阻。
已审阅的TRIAL-EVIDENCE-REFRESH-01纯文档提交另在任务分支整合，371运行输入不变；
该资料接受不改变full FAIL。CP4历史WinError5、完整EXE对局与
退出、外机Windows、真实LAN、视觉/DPI等原验收缺口保持；本规则修复不关闭它们。
