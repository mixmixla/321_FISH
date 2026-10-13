# TRIAL-EVIDENCE-REFRESH-01 — Review r1

2026-10-13。[冻结Task v1](../task-packages/TRIAL-EVIDENCE-REFRESH-01.md)。仅资料实施，技术接受/整合由主窗口决定；本记录不宣称应用、当版47款、EXE、视觉、外机、R1或发布通过。

## 版本与所有权

base `08d263b2a78b7a6df0b888616e2fbf44793182b8`，分支 `docs/trial-evidence-refresh-20261013`，独立worktree。原开发HEAD c864234/继承dirty以及主窗口GemCity分支保留；本窗口不写两处工作树或治理资料。范围仅本Task/Review、完成度地图、现代化规划视图、新试用分类与本任务静态JSON，共6文件。

## 改动与静态依据

- 撤下当前地图的旧14桌面禁入、缺COC begin/拉密提交/clear/trade/pass/buy_res、围棋错误路由及Nimmt旧outerHTML结论；统一基线和分类边界。当前桌面47项未验证，Web46项未验证/1项第二方操作不支持；两旗舰实验单列旧版本。
- 现代化清单校正为源码覆盖/上游实现提交/当版待验三层，保留A–F规划编号，不批量放行范围；去除另一机器file URI及把旧源码审计当现状的总括。
- 新分类表补上朋友候选2247及三EXE/便携包的版本，区分合并、门禁、构建、异常清理、实际键鼠、自然退出和外部环境。旧FAIL、CP4、Tk fatal及未验边界保留；未更改旧Review。

[static-audit.json](../review-assets/TRIAL-EVIDENCE-REFRESH-01/static-audit.json)从当前公开源码读取：Python使用stdlib AST，Web按GRENDER方法定义文本扫描；不import项目、不调用玩法、UI、测试或构建。47标签/动作/画师/Web key精确相同；点击key20，附加通用按钮13，禁入set0。7个公开源文件逐项记录原始SHA及Git LF SHA，working字节仅允许CRLF→LF后与08d263b blob相同。输出只含公开源码元数据/标签/分类，无真实资料或凭据。

旧动作变化的来源：`client.py` _GAME_ACTIONS/_parse_action、`client_gameui.py` _CLICKS/_click_go/_click_blokus、Web GRENDER与各act/private；逐游戏入口行号保存在JSON和地图。独立只读事实补核确认：

| 项目 | 08d263b定位 | 本文采用的限定结论 |
| --- | --- | --- |
| Nimmt | web.py:5136–5140直接mkCard/append，3937–3941包含键盘；nimmt.py:59–67读取card | 旧outerHTML原因已不成立；完整玩法未验 |
| 开拓trade | client.py:11624/13611–13618，web.py:4776–4789，kaituo.py:195–207 | 两端入口与give/want/n字段已存在；交互未验 |
| 城主pass | client.py:11607，web.py:4906，chengzhu.py:62–65 | 入口已存在；交互未验 |
| 宝石buy_res/take2 | client.py:11611/11614，web.py:4941–4943/4952–4960 | 入口旧缺口覆盖；购买原子性另由主窗口修订 |
| 中心自选 | client.py:11539/13636–13640，web.py:4313–4323，onewolf.py:111–117 | 两个中心序号可选择；交互未验 |
| 领地米宝 | client.py:11628/13619–13635，web.py:4810–4818，lingdi.py:108–123 | 空/self/坐标入口存在；交互未验 |
| 四季文案 | client_gameui.py:4758/4775/4784，web.py:4971–4972/4992 | 引擎映射已加，资源crystal→施法仍不一致；视觉未验 |
| Kalah | web.py:5201/5207，kalah.py:39–55；桌面client_gameui.py:2163–2177/1274–1280 | Web第二方按钮不符合法穴/上排为空；桌面第二方鼠标/提示有缺口，整数可手填全局穴号不等实操已验 |
| Balatro私有文本 | client.py:13260–13261及balatro.py的private返回hand结构 | join(list[dict])路径保留；不扩推整个游戏无入口 |

Kalah当前静态缺口已通知主窗口作后继有限任务候选，本Task只记资料，不整改产品。

## 文档检查与独立审查

纯文档/边界核对PASS：6文件允许范围；47行游戏key与静态JSON精确一致；桌面47未验证，Web46未验证/1项Kalah第二方操作不支持；149个相对链接、其中120个源码行号有效；7公开源hash与冻结Git LF blob匹配；`git diff --check`通过。未改变生产、测试、依赖、治理文档或旧Review。不运行应用门禁，主窗口当前full真实结果保持其原记录。

独立只读终审已完成，限定结论 **0 MUST**。审查者从本Task、实际diff、静态JSON、当前源码和旧证据复算，确认47 key/覆盖计数及分类、Kalah/Balatro缺口、GemCity边界与历史2247/三EXE/旗舰证据归属一致；149链接/120源码行锚/7源码hash通过，6文件范围准确，另核9份旧Review/治理资料保持基线。审查者未参与文档写入，未改文件或执行应用/测试/构建；未自行登记AI_ACCEPTED。技术接受及整合仍由主窗口决定。

临时校对输出只作辅助，本段保存可接续的检查方法、范围和结果。本次分支提交仅交付资料，不推导应用候选可合并或发布。

首次静态计数输出遇GBK不能打印emoji而失败，随后仅将该临时文档工具stdout设UTF-8，同版AST核对成功。环境已有pyenv路径提示，但项目.venv实际完成该静态命令；未修改环境/依赖或项目解释器。

本窗口本地分支提交后交主窗口可整合SHA；不push/PR/merge/release，不操作设备/网络或真实数据，不恢复旧Goal/ProcMon。
