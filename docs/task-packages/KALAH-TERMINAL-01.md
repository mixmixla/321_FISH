# KALAH-TERMINAL-01 v1.1：终局优先于额外回合

状态：IMPLEMENTED / CODE_DOMAIN_REVIEWED / FULL_FAILED / NOT_AI_ACCEPTED / NOT_MERGE_READY（2026-10-13 有限收口；冻结合同保持）。父线程明确授权继续候选Kalah终局，先最小冻结/真实RED，确认领域bug再修。v1.1仅更新用户13:34北京最新停止决定：当前Kalah完成必要测试/独立审查/提交推送/清理后直接最终收尾，不启任何新任务/构建/美化；旧15:00连续推进上限已被替代，用量重置不增加任务范围。规则/18cases/门禁合同与v1相同。主GUI工具已BLOCKED，不再重试。主控本轮有限自治，不是Pro审批。

## 基线与唯一写入者

主worktree `_tmp_gui/gate-collection-20261013` / fix/gemcity-purchase-20261013，base2fa1c9eb5fc499c1bd424b36e2093f1f5bc84b69 clean；只读fresh远端main仍52d5ff00c53c2e104811048a2db55d6b53e432cc，不自动pull/reset/clean/强推。原目录c864234/dirty/index/1143保护保持。root独占 games_pkg/kalah.py、全新 tests/test_kalah_terminal.py、本Task/Review/evidence/指挥中心/投影与窄raw属性；不改其它生产/测试/依赖/PROJECT_MEMORY/旧Review或六文档资料。kalah_domain_review独立只读设计、实际差异和证据，未写领域代码；其他窗闲置，无重叠测试/构建。

旧源码source13514b5d70d6e92a39f9eadd8f20ae39562d3e80570437b26f6e4ea0a2164345/410，全量2441P0F20原opt-in；现有三EXE/ZIP仅绑定9803303/此旧source，旧EXE-LOCAL/EXE-EXIT接受均历史范围。规则修复后必须新source/domain/full；不以旧full或旧EXE冒充新规则结果。本Task仅源码交付，最新停止决定禁止新构建；最终严格声明旧EXE不是当前最终源码测试包。

## 冻结领域合同

1. 模块原合同“某玩家穴全空即终局”保持：合法act播子/捕获之后，沿原_check_win处理终局，不因最后落己方库而跳过。
2. finished优先于额外回合和换人：A/B胜/负/平局均按原规则清穴/收余子/比库，48子守恒；snapshot.status=ended、ended()非None（平局winner_uid=None），终局不改变turn到下一玩家。
3. 终局的领域act msgs不得再提示“再走一次”/“轮到”；胜者提示或明确平局，捕获事实消息可保留。仅act返回的领域消息，client.py无条件摘要另为已知包外静态边界，不在本Task顺带修UI。
4. last五元组形状(pid,hole,last,go_again,captured)不变，洞/最后落点/捕获信息保留；终局有效go_again=False。输入hole为global index+1、A1..6/B9..14、播子环路/跳对方库/捕获、非终局额外回合和正常换turn均保持，不重排cells或改权重。
5. 终局后双方act均GameRuleError且snapshot完全不变。真实RoomManager公开handle_action必须得到规则ended结果，Hub既有接收契约不改；不宣称纯RoomManager自己切ENDED、发送game_end或3秒再开。

## 实现前RED与必要门禁

新文件最多18个有限case：A/B末洞入仓各胜/负/平局6；非额外回合捕获终局平局A/B2；非terminal额外/普通A/B4；真实RoomManager A/B公开动作2；从初始48子出发4个固定随机选择种子合法act序列，最多各400步、无状态注入，检查每步守恒/进行中合法动作/最终ended。近终局fixture为明确合成合法48子，不叫实际GUI完整对局。

仅新增测试先通过原 .venv/Python3.14.5 run.py test-all 单文件隔离RED，保留原FAIL/原日志；生产尚无diff时先确认失败对应冻结缺口。再最小改规则，专项domain选新文件+现有Kalah四文件+games_w2_logic/rooms/game_lifecycle等实际相关文件，无全局截图/Escape/硬件或--run-visual。生产候选最终必须新同版完整门禁一次，默认原20 opt-in skip不放宽、singleattempt/cleanup/exit/rawhash/source一致，旧full不代替；失败原样保存，不重试覆盖。

测试开始/结束及审查交接同步中心/投影，run目录 `_tmp_gui/kalah-terminal-20261013/{red,domain,full}`，每阶段唯一run，无原运行时资料。只fresh profile/source-copy/private desktop/loopback，相关测试由root唯一执行；代理不启动测试/native/服务/构建。

## 接受与交付边界

独立实际diff/RED/domain/full原证据审查后，root仅作有限源码AI_ACCEPTED，不冒用户/Pro验收，不说主GUI退出、EXE游戏/外机Windows/LAN/DPI/视觉/R1或发布通过。新源码与旧三binary分账，当前Task不重建/覆盖旧包。只普通任务branch commit/push/draft可用权限；既有PR403不重试，不main push/merge/Release，不公司MES/PDA/真实资料/休眠机/CP4/安全配置/旧Goal。

原日志出版仅独立工作树 .gitattributes 新增 docs/review-assets/KALAH-TERMINAL-01/**/*.log.txt -text -whitespace，保留合成raw字节；其它源/测试/文档whitespace检查保持。原dirty不参与暂存。
