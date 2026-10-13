# GEMCITY-PURCHASE-01 v1.1 — 璀璨宝石购买原子性

2026-10-13。用户本轮授权同步、选最高优先级明确未完任务、实现/测试/审查、commit、
任务分支普通push及draft PR；不merge或正式发布。基线origin/main
`08d263b2a78b7a6df0b888616e2fbf44793182b8`。状态以[指挥中心](../AI_COMMAND_CENTER.md)为准。

v1.1仅补原始证据发布边界：暂存实查pytest原日志自带尾随空格，Git默认换行过滤可能
改变公开原日志字节。允许`.gitattributes`仅对本任务`**/*.log.txt`设`-text -whitespace`，
保留原始字节/诊断空白并逐份核Git blob SHA256；源码/手写资料检查不变，门禁不变。
来源为本轮主控证据终核，不扩大购买规则/测试行为范围，无新运行输入。

## 已复现问题

`games_pkg/base.py`明确非法动作抛GameRuleError后状态不变。当前GemCity两条购买入口
违背该合同：

1. 保留卡先pop再验资金；不足被拒后卡永久丢失。
2. 每种颜色重复使用同一份万能金做资金校验；两色各缺1而只有1金时买成功，金变-1。

两项在实时基线的合成规则探针已复现。桌面和Web均已有buy/buy_res入口，不新增UI。
先核的历史gate失败在当前干净基线8 PASS/exit0，但原FAIL和未定因保持；不能据此
修正或放宽门禁。优先选择确定的对局状态损坏；只实施本购买任务。

## 冻结范围

- `games_pkg/gemcity.py`：支付前计算折扣后每色实际支付量和总万能金需求；资金不足
  不改变任何状态。保留卡资金验证/支付成功后才移除。
- 新 `tests/test_gemcity_purchase.py`，必要既有规则测试核对；Task/Review/公开合成
  证据/指挥中心与阅读投影、稳定项目记忆。
- root唯一写入，代理只读分流和独立审查。在独立fix任务分支，不整合原dirty。

不修改其它游戏、货币获取/贵宾/胜负规则、参数协议或UI；不接CP4、账号Goal或ProcMon。
不访问真实数据、设备、公司项目、休眠电脑，不改共享main，不merge/Release/部署。

## 验收

- RED证明市场/保留卡两路径拒绝合同和总金缺口缺陷；保存原始FAIL。
- 不足拒绝完整state/RNG/轮次/卡牌/金库不变；足够时按原彩色优先规则支付一次，
  总金需求不得超余额，各资源守恒且不负数。
- 折扣/分数/贵宾/终局补回合原行为、市场补牌和保留相邻卡保持；回合只前进一次。
- 真实RoomManager入口拒绝不变、补足后成功；非轮到/观战者拒绝。
- 项目.venv/Python3.14.5，正式隔离逐文件规则/房间/Hub领域，随后同候选完整门禁。
  每文件单attempt、真实退出、日志hash、cleanup及source ID保存；不skip或重试覆盖。
- 独立审查从Task/diff/原证据开始；无MUST且必测通过后有限AI_ACCEPTED，保持
  IMPLEMENTED/AI_ACCEPTED/PR交付/实际MERGED/产品发布分别记录。

最终交付任务分支commit与draft PR。EXE全对局/退出、其它干净Windows、真实LAN和
视觉/DPI等原发布阻碍单列；本规则修复不证明这些已验收。
