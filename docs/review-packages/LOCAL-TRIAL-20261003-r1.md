# LOCAL-TRIAL-20261003 — 接管与本地试用验证记录

授权：[自治决定](../decisions/LOCAL-AUTONOMY-20261003.md)。此文件保存证据；当前状态只见
[指挥中心](../AI_COMMAND_CENTER.md)。本轮已AI_ACCEPTED（主控技术验收），不是用户/Pro验收或发布。
以下入场记录按时间保留，后续成果见末尾。

## 入场与治理

- 2026-10-03，HEAD `452417e20a8fe35c3ac641b1f2da488352dd6317`，原分支 codex/cc02a-consistency，
  `git status --short --branch` clean，`git diff --cached --stat` 空，唯一 worktree。
- `list_threads/read_thread`：旧主控“冻结资源范围实施草案”最后一轮 completed；无活动旧实现。
  PowerShell `Get-Process`/`Win32_Process` 未发现 Python 应用/pytest；未知宿主进程未终止。
- 新本地集成分支 codex/local-trial-20261003，基线不变；Goal 用 create_goal/get_goal 创建并确认 active，
  没有恢复 heartbeat、远端写入、真实数据或系统配置操作。
- 最小治理修改：AGENTS 审批/验收入口、COLLABORATION 相应分工、指挥中心当前权限/任务、
  接续指南优先级和生成任务清单。保留旧 Task/Review/决定历史正文与所有旧通过/未通过。
- `git diff --check` exit 0（仅 Git 换行提示）；8文档160相对链接有效、路线投影及hash一致。
  resource_review 独立治理窄审：无必须项，授权/历史边界保持；主控据此 AI_ACCEPTED 治理切片。

## 已有 RESOURCE 的复用核对

当前 Git 历史包含代码 `2087af8`、资料 `4d2a49b` 和实际交付补录至入场 HEAD。
已有 CC-02C-RESOURCE v1.1 独立 ACCEPTED、119 文件 1550 passed/0 failed/2 opt-in skipped，
详见[原 Review](CC-02C-RESOURCE-r1.md)。入场 clean，无代码变动，不以文档状态冒充新候选重测。
独立 resource_review 窄查同 op 重试、manifest 资格、资源结果与 preview 匹配条件：四项主体已落实。
发现确定边界缺陷：`_read_web_resource` 两处直接 `math.isfinite(float(meta["ts"]))`，极大JSON整数
`10**1000` 导致 OverflowError，而 `_file`/`_on_chat` 未捕获，应拒资格而非异常中断。
版本值 `1.0` 因数值相等被接受亦需沿严格格式明确；已内部冻结[RESOURCE-FIX-01](../task-packages/RESOURCE-FIX-01.md)。
尚未动态复现，不提前宣称已修复。unknown 与 newer permit 的疑虑未找到可达反例，不列必须项；
同URL并发preview只补首消息属于原产品行为观察，不据此重开冻结匹配方案。

## 门禁前的安全检查

实际读取 run.py/dev.ps1/tests/conftest.py/config.py/prefs.py/历史逐文件 runner：
config._log_dir 与 prefs 默认写源码旁；server.serve/web.serve 默认监听 0.0.0.0，server 同时启动 discovery。
仅设置 USERPROFILE 不足以隔离上述路径；直接在主工作区运行旧全量不满足本轮数据/网络边界。
已冻结 [VB-01 v1](../task-packages/VB-01.md)，采用源副本/合成 profile/loopback/独立 Windows desktop。
当前尚未跑应用或 pytest；新门禁事实和真实失败另见后续 VB-01 Review。

## 游戏入口初步静态事实（未作稳定验收）

使用 Python AST 读取 GAME 类名、client._GAME_ACTIONS、client_gameui 的注册 painter/_CLICKS，
并读取 web.GRENDER：共 47 个游戏、47 个桌面 painter、47 个 Web renderer。
桌面 11 项暂未发现按钮或统一点击分发：azul、bolan、chengzhu、gemcity、gongfang、kaituo、
lingdi、nimmt、siji、tielu、yahtzee。需进一步核对替代输入路径，不能仅凭静态数字声称不支持。
五子棋/四子棋已有逻辑及双端主操作；当前源码可见的体验候选包括玩家执色提示、棋盘点击坐标、
观战/非本人回合禁用、胜线和低打扰动画；均未以此文档宣称已修复或已通过真实 GUI。

本轮代码/测试/构建、最终完成度地图、独立验收、本地候选尚在进行。远端/真实设备/真实局域网
不由本记录推定完成。历史长期存储未知结果/首次失败重启等已明确限制，不伪称全部 RETIRE 闭合。

## 当前整合成果与证据索引

主树`codex/local-trial-20261003`从452417e接管，经本地治理、门禁、资源补正、旗舰/试用实现及整改，
最终代码提交`1daea66556c3fc6b5b7cbc8c8432378088cc3ed9`。没有push/远端PR修改/merge/tag/release。
330输入source `f224f73b20e72ee1494f7fff096d7751c20fb6757d8c5b41434964431b4867f6`；
独立resource_review贯穿有限设计/代码/反例复审，未参与实现，主控据真实证据作最终技术裁决。

| 切片 | 实际成果 | 可复核记录 |
| --- | --- | --- |
| 治理 | 本轮内部冻结/调度/独立技术验收可自治；远端/真实数据/系统边界保留 | 本文入场、自治决定与AGENTS |
| RESOURCE-FIX-01 | 极大JSON整数timestamp按无资格拒绝，manifest version严格整数1 | [原9失败→35通过、HTTP/CHAT证据](RESOURCE-FIX-01-r1.md) |
| VB-01 | 默认逐文件隔离、身份/日志/恢复/cleanup、意外skip拒绝、有效stdio与GUI sys捕获 | [门禁及全部历史失败](VB-01-r1.md) |
| CC-03-SCREEN | 47项双端真实分类；桌面14/Web2不支持；两旗舰实验、其余未验证 | [审查](CC-03-SCREEN-r1.md)、[地图](../游戏完成度地图.md) |
| GAME-UI-01 | 五子棋交点/四子棋列、最新态只读门禁/执色/胜线、有限动画、root/mini/游戏/专注窗恢复 | [原缺陷、真Tk、真实TCP、六布局截图](GAME-UI-01-r1.md) |
| REL-01 | 白名单源码构建、独立profile/loopback、禁设备/发现/托盘/热键、双实例隔离与手动试用入口 | [实际双EXE与哈希](REL-01-r1.md)、[使用说明/已知限制](../本地试用说明_2026-10-03.md) |

最终1daea66双EXE构建与实际双客户端登录/存活/进程树清理已通过；最终全量仍进行中，
不能先登记本轮AI_ACCEPTED。构建/source/driver与原始证据分开记录，不将Tk合成Core测试当EXE完整UI对局。

最终全量现已完成：127文件1669passed/0failed/2原opt-in、exit0，827.261秒；source仍为上述f224f73b…。
实际8文件试用ZIP已生成、CRC/hash/允许文件清单检查通过，精确产物hash见[REL Review](REL-01-r1.md)。
当前只余独立最终交付核对和资料提交；Goal仍active，尚不提前登记用户/Pro验收或远端发布。

## 最终独立验收与主控裁决

2026-10-03，resource_review独立完成全量报告、原skip/失败、最终build/run、8文件ZIP与范围终审，
无未关闭must。主控据此登记本轮及VB-01、RESOURCE-FIX-01、CC-03-SCREEN、GAME-UI-01、REL-01为
**AI_ACCEPTED（本地有限技术范围）**。全部127结果单次执行/exit0、无cleanup/artifact/policy failure。

本轮终点已具备：实际Windows本地试用包、47项双端真实地图、可复现代码/门禁/产物证据和明确未验证事项。
两旗舰仍列实验；EXE实际证明双客户端启动/登录/存活与harness清理，不声称完整EXE UI对局、真实设备/LAN、
非开发机器或完整RETIRE/R1验收。主树330输入到构建逐项绑定；run期source不变仅覆盖其326项子集，差别已明确。
没有push/PR修改/merge/tag/release/部署，没有真实数据或系统配置修改，没有启用heartbeat。

交付包：`_tmp_gui/321_FISH-local-trial-20261003-1daea66.zip`；SHA256
`74b543e8cc391e99671a326330155301f1b8fd105aa02252d6cc93f221968c89`，51,326,407 bytes。
同名目录可直接按README试用。原始故障、GUI布局截图与构建/运行日志保留在各Review记录的ignored证据目录，
必要断言/测试/harness与关键结论已在仓库，不依赖单一临时日志恢复。下一仅用户决定后续有限范围或外部权限，
不自动继续Roadmap候选；Goal工具收口与最终资料提交见指挥中心。

最终机械收口：18文档243相对链接有效、路线投影及330源码身份一致，资料本地提交c9f8ac7。Goal已由工具实际确认complete，11672秒（约3小时15分）；本轮无后续应用或验证工作，不恢复heartbeat或推进候选。
