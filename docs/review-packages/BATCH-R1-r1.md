# BATCH-R1 — 连续运行与里程碑证据 r1

2026-10-01；对应 [批次Task](../task-packages/BATCH-R1.md)。状态只见 [指挥中心](../AI_COMMAND_CENTER.md)。
本包保留入场与阶段记录；最终候选全量与独立证据/资料终审均已通过，三任务及批次可接受。

- 入场HEAD `ec73118`、dirty20M+14??，已验收FILE候选295项源/依赖0 mismatch。
- 完整入场patch/hash/文件保护清单在`_tmp_gui/r1-lifecycle/entry.json`、`entry.patch`。
- active Goal已创建在当前主控聊天；heartbeat `321-fish`已创建并从本机automation.toml确认kind=heartbeat、
  target为当前聊天、每小时0/30分唤醒。前一项暂停的周工作回顾未改动，没有重复新建。
- 并行额度：主控+2子代理，先一个只读调查Web退出、一个只读调查游戏公共生命周期，
  冻结文件边界后再编码。独立审查不能由实现者验收。
- 初始操作只读和资料快照；当前未修改应用源码/运行应用测试。SESSION/GAME实现与证据将追加到各子Review。

官方能力核对：[Goals](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)、
[本地定时任务](https://learn.chatgpt.com/docs/automations?surface=app)。具体权限/范围由用户本次授权和Task约定，
不是官方页面批准代码任务。Goal承担活跃推进，守护不重复执行，遇暂停/预算限制不规避。

最终里程碑包待三个子任务实现/审查与最终全量后形成；当前无commit/push/合并/发布。

阶段进展：SESSION01原同2294最终测试在entry源11/2预期红，六域82绿，Node行为12/12与mutation、真实IAB清理/重登证据闭合；
SESSION02资源清理与通知/群GC竞态经两轮受控证据整改，3790/C12阶段审查可衔接GameB；
GameA仅RoomManager.start的CREATED守卫，原红2/3、修绿及Room域20项，独立阶段审查可接受。
所有阶段仍按批次最终全量统一确认；后续GameB、客户端与最终真实UI整改证据见下文。

## 冻结交付与边界

- HEAD/base仍为`ec73118c86250e555ec455f789e27df67036b2e6`，分支`fix/cc-01a-admin-credentials`，dirty，未新增提交。
- 最终300项源/测试/依赖内容ID：`64b829d183370ebb019abf19d05aaa8abb870db49246cc011a5cb15296abd093`。
  算法为UTF8 compact sort_keys JSON `{relative_path:{bytes,sha256}}`的SHA256；完整manifest见`final-candidate.json`。
- 相对入场295项只改`server.py`、`web.py`、`client_core.py`、`client.py`、`games_pkg/rooms.py`；
  只新增5个生命周期回归文件。28份原入场保护资料/代码无变化，管理员/文件鉴权既有测试和行为保护保持。
- server `3b992ed5a10bca846a371e826691e9229b6644fd00224bfce9aaadd0c38b174e`；
  rooms `dbe22e05a7e8e0c633091f0a5aeb0af24cb233174d2e9d2ce8fd3caf06f352db`；
  Web `9880d127e941cae447aeb568902a6aeb41d66a78dfa28a2a3dd732c783af303c`；
  Core `aa2c724798d9ae6256783299e0655ea138d69b3162d850802843ad640888f116`；
  client `2dc4790134dea7b29b53a0e3dfdbbf7083e768dd7c8403948e72fe553a481409`。
- 最终新测试SHA256（均随完整门禁验证）：
  Web logout `2294d495a3593c9bbba0dddc01f585af61ffa598e3f4c1e599f66e690c2182d2`；
  Session cleanup `ac003457d59676aeae91331d35fc2ae015f38f36bd53c5552f089f555a888151`；
  GameA `fab76f989147a09ae4009dbaa6947abcbe7be15d6d58d07cb4f27f6f6a27a1b6`；
  GameB `305e5fdc48fd2ff0f64763d902380a1e8103b852c4cb9afccfb384507ef34c4d`；
  Core `5b77a708e9e461977d9a865088554f3d0fffd13e15a8e1e26bcac76e13438836`。
- 实际交付：当前Web会话明确退出与旧SSE隔离；真正最后UID端才清传输/游戏/语音和发下线通知；
  游戏公开终局、3秒复位、房主再开、退出确认和干净重入，多端状态fanout及旧轮身份防护。
  不新增MsgType/账号模型/游戏规则/胜负奖励；没有动注册规则类，不从少量UI探针推出47款全部可玩。

## 测试与独立审查

| 层次 | 实际证据 | 边界 |
| --- | --- | --- |
| SESSION01 | 最终13项原红11/2、修绿；六域82；生产JS12与mutation；真实IAB | 阶段Web f178，最终Web9880另有12项JS/HTTP及统一full |
| SESSION02 | 4/6项多轮失败与整改保留，最终7项绿及5/15/45/24/16领域 | 各测试版本/私有屏障变化明确，不把不同字节红/绿冒称同版 |
| GameA | 同5项原红2/3、修绿，三个Room文件20绿 | 纯Room不代替服务器/UI |
| GameB | 初始5项4/1红；8项4/4红后绿；9项绿；最终同12项3/9红后12绿 | 两轮独立必须项与payload P1均关闭，最终A5/r49 15/multi5绿 |
| Core | 初8项7/1红后绿；最终同12项2/10红后12绿 + client33 | 发送返回前回帧与失败fence有真实屏障回归 |
| 最终UI | Tk真实双窗/Canvas13，生产Web函数Node20，SESSION01 Node12全true；IAB真实TTT全链 | 合成账号/loopback，未读取真实prefs/历史或启用设备 |
| 补充领域 | 正名P0 Web9/admin_groups_web8/r47 16/r49 15/rooms8/server_games4，共60绿 | 错名test_p0_web.py exit4/no tests保留，不计通过/应用断言失败 |
| 最终full | 唯一进程83335，108文件，1335 passed / 0 failed / 2 skipped，353.79秒，所有真实exit0 | 每文件新进程/新basetemp，UTF8、单文件240秒、无重试，前后300项完全一致 |

浏览器最终TTT在12880隔离页（server3b99）保存终局inert公开棋盘/胜者、自动reset、9空格再开、leave清面板、卡片重入；
其来源由`ui/final-overlay-close/server.json`加载源码hash绑定。退出独立在13200同源码验证login可见/main隐藏/无panel，
`ui/game-after-logout-server.json`证明同UID TCP仍活/UID在线、Web sessions/token均0。
顶层旧`game-created.json`仍是609315阶段证据，不作为最终版本证明；旧全链另保留`ui/game-stage609315/`。
模态背景点击只关面板的首次观察保留，未冒称退出通过。最终所有临时tab/UI服务均已关、真实exit0。

独立阶段审查已从实际diff/任务包/原始证据出发，关闭旧Timer/tick身份、同UID ACK、payload混轮与Core重入时序问题。
独立边界审计复算300项0 mismatch、HEAD/28保护与5核心+5新测试范围一致；不由实现者自行验收。
完整门禁结果与最终资料已独立终审可接受，执行状态以指挥中心为准。

## 最终门禁结果

命令：`& ./.venv/Scripts/python.exe _tmp_gui/r1-lifecycle/run_gate.py --label final-full`。
运行环境：Windows11 10.0.26200、pwsh7.6.5、项目.venv Python3.14.5/pytest9.1.1；108文件各一次，
所有真实退出码0；runner明确按tests/test_*.py枚举，不改run.py/dev.ps1的既有入口。
2项跳过只为`test_r45.py:425`显式`--run-hardware`与`test_visual_screenshot.py`显式`--run-visual`，
与入场全量相同，未启用真实设备，不以skip掩盖失败。
门禁前`final-candidate.json`与后`post-full.json`均300项、ID64b829…相同；
HEAD仍ec73118，28入场保护无变化。`final-verification.json`22项全部true，原始108日志与summary计数逐项一致，
21资料/95相对链接有效、git diff --check真实exit0。原红/错名/遮罩观察不改写为绿。
最终summary SHA256 `295d8011f633c2f9fb43f113cf0fee111717add4f30ae9e56edfc519f5456d2c`。
独立终审已重算manifest/门禁/资料：可接受，无未关闭必须修复项。三目标实现/回归/真实UI/最终全量均有证据，
源边界/版本无越界；主控依结论将批次与三项置ACCEPTED。这是独立开发验收，不表示Pro里程碑、合并或发布已完成。
持续运行已自动走到批准终点；heartbeat `321-fish`已PAUSED并核验，Goal已complete，持续推进约3小时3分钟。
没有下一READY，不续跑其它候选；后续产品批次决定不要求用户每小时检查或逐项催促。

实际限制：EXE/真实局域网设备、真实音视频、全部47款UI与长期负载未纳入；账号删除/踢所有端、
FILE_ACCEPT离线可用性等仍是候选，未自动扩入本批。没有commit/push/PR/merge/发布或外部消息。
原始证据都在`_tmp_gui/r1-lifecycle/`，本包保存可交接的范围、版本、结论与限制，ignored日志不是唯一状态来源。
