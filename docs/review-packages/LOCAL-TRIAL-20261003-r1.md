# LOCAL-TRIAL-20261003 — 接管与本地试用验证记录

授权：[自治决定](../decisions/LOCAL-AUTONOMY-20261003.md)。此文件保存证据；当前状态只见
[指挥中心](../AI_COMMAND_CENTER.md)。尚未达到本轮试用终点，不是用户/Pro验收或发布。

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
