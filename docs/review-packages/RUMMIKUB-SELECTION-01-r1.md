# RUMMIKUB-SELECTION-01 r1 — 最近棋盘空选择

IMPLEMENTED / INDEPENDENT_CODE_DOMAIN_PASSED / INTEGRATION_FULL_RUNNING；[Task v1](../task-packages/RUMMIKUB-SELECTION-01.md)。
root只改client.py _submit_sel取首个最近/默认候选，即使空选也不扫描另一份旧牌。
原成功提交清当前候选、默认候选顺序、接续弹窗上下文检查保持；inactive非候选不扩展清理。
Kalah控制器由同一作者按独立Task修同文件，不混改规则/协议或UI窗模块。

- RED1共29F14P，其中一新测试误要求inactive focus也清空；按冻结候选范围纠正测试，
  保存原失败并明确夹具原因，不扩大生产清理。
- 正式[RED2](../review-assets/FOLLOWUP-20261013/controller/controller-red-r2/summary.json)
  共28F15P，拉密两向真实Tk select→deselect仍2F5P，真实规则误接受旧三牌；修复后7P。
- UI整合前[controller-green](../review-assets/FOLLOWUP-20261013/controller/controller-green/summary.json)
  三文件104P，是旧候选；当前[整合领域](../review-assets/FOLLOWUP-20261013/controller/controller-ui-domain/summary.json)
  12文件220P0F0S/exit0/37.638秒，source b81b266a532dcaedc1e86786e57f4ead1f31e10e4e73567dbad90924d89a378b。
  新7例包含真实大厅/专注Tk事件、真实Rummikub完整状态/RNG拒绝、副作用与合法33点首任、默认来源；
  既有旗舰43例保留接续弹窗变化/成功回归。原raw hash/单attempt/cleanup/379输入身份已核。

领域后仅GATE-FIXTURE-01两个测试整合形成新候选，产品输入未变；原full2323P/3F/2S
永久保留。独立Sol实际diff/Task/原RED、220P/source/cleanup和四新增Kalah整合Tk链
终核0 MUST；[独立结论](../review-assets/FOLLOWUP-20261013/controller/independent-review.md)。
最终同版full新run integration-full/session90958运行，尚无整体验收；不据领域记整体AI_ACCEPTED。
未merge/release/EXE/LAN/用户验收；PR403未重试。
