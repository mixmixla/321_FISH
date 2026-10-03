# CC02-RETIRE-DESIGN — M1 与可靠提交设计准备

版本 v1，2026-10-02（Asia/Shanghai）。执行状态只见[指挥中心](../AI_COMMAND_CENTER.md)。
批准来源：用户在“整理身份退役设计审查材料”聊天明确批准本资料批次并要求以 Goal 持续完成。
本 Task 冻结的是资料交付；不批准 RETIRE 实现或真实账号退役。

## 入场与接管

- 入场发现旧主控“准备 CC-02 架构审查材料”仍在执行另获批准的 PR-DELIVERY-02，分支已改为 codex/cc02a-consistency、观察 HEAD e065591。
  本批先只读调查/独立 ignored 草稿，不与旧主控争用指挥中心、index、分支或交付文档；等待其结束后接管。
- 文档写入基线 HEAD `fc9c991bed82dc969aefdbfc9a77a46e75bde5d5`，tree/index/dirty、旧主控结束/Goal 完成与进程核对见[Review](../review-packages/CC02-RETIRE-DESIGN-r1.md)。
  本批不 pull/fetch、切分支、提交或推送；旧主控自己的 Git 动作按独立任务记录，不算本批动作。
- 已验收 CC-02A raw 源/测试/依赖305项 ID `1f94f8fca3da7746c5db293b05e5729e76b37935e1a05d0314658bde9de39830` 保持。
  历史113文件1355/0/2仅引用原报告，不重跑应用门禁，也不能替代 RETIRE 未来验收。
- 依据：[架构决定 v1](../decisions/CC-02_架构审查决定_v1.md)、[修订实现草案](CC-02-IMPLEMENTATION-DRAFT.md)、
  [CC-02A Task](CC-02A.md)/[Review](../review-packages/CC-02A-r1.md)、必要项目记忆；源码事实与未来设计分开。

## 冻结交付要求

1. 按已选 M1 保留旧昵称/UID关系，禁止重新认领；明确实际管理员/bot/系统保护集合及无法从旧数据推断的历史角色。
2. 完整写入面含登录/attach/密码认领/dispatch/直接 Web API、已取due、bot/预览内部回调、CLOUD 文件提交与后台快照；逐项注明 A接受点、C最终效果提交、t0退役屏障、D持久确认。
3. 最小 STORE-COMMIT 设计含 pending fence、一致深快照、普通/force/flush/worker顺序、成功receipt、失败待重试、首失败重启及旧服务/旧备份回滚限制；Hub全局锁内不做网络/磁盘IO。
4. 冻结数据表：本人草稿/定时/活跃私有记录清理、云密文访问隔离；共享引用/审计/备份/下载保留，作者消息沿现有兼容规则；不承诺广泛物理擦除。
5. 自包含 Pro 审查材料、逐项待决定问题、未授权的实现 Task 草案，以及可控 Event/Barrier、IO失败、真实JSON重启验收矩阵；不能把未来矩阵写成已通过。
6. 独立资料审查无未关闭必须项；文档链接/投影/版本与文件边界检查通过，更新唯一指挥中心再生成任务清单；打开交付材料，结束本Goal。

## 文件所有权与核对

主控唯一写入七份 Markdown：本 Task、[Pro材料](../CC02-RETIRE_Pro审查材料.md)、[RETIRE草案](CC02-RETIRE-DRAFT.md)、
[Review](../review-packages/CC02-RETIRE-DESIGN-r1.md)、`PROJECT_MEMORY.md`、`docs/AI_COMMAND_CENTER.md`、生成的`docs/任务清单.md`。
旧决定/CC-02A/PR交付包/历史draft保持，不反写历史证据。两个事实调查代理只读；新独立资料审查者不参与材料编写。
本机证据在 `_tmp_gui/cc02-retire-design/`；只含非ignored文件hash、文档草稿与检查结果，不是状态来源，不读/复制真实运行数据。
接管后保存全部非ignored文件manifest、HEAD/tree/branch/index内容标识；除上述七份文档其它入场文件保持，305源逐项保持。
正文内容ID仅覆盖本Task/Pro材料/实施草案三份，Review/指挥中心流转证据另捕获，避免自引用hash。

## 排除与终点

不修改应用/测试/依赖或真实数据，不启动/重复应用、测试或门禁，不实现 RETIRE。
CREDENTIAL、LOCAL/CLOUD格式与迁移、游戏筛查/玩法、物理GC不纳入。
不commit/push/创建PR/merge/release，不发Pro或其它聊天消息，不启用或恢复heartbeat。
旧321-fish守护保持PAUSED；本Goal是新的资料批次，不迁移或复活历史Goal。

普通资料整改自主完成；资料ACCEPTED后结束。本批验收不等于 Pro 批准提交方案或 R1 里程碑通过。
下一代码批次必须获得 Pro 设计答复、关闭必须设计项、冻结有限 Task 后由用户批准，才能 READY。
