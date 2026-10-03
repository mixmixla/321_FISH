# CC-02C-RESOURCE-SCOPE — 资源资料与有限 Task 冻结

版本 v1.1，2026-10-02（Asia/Shanghai）。执行状态唯一见[指挥中心](../AI_COMMAND_CENTER.md)。
批准来源：用户在“冻结资源范围实施草案”聊天直接批准只读资料批次并要求以 Goal 持续完成。
本文只冻结资料工作；[实施草案](CC-02C-RESOURCE-DRAFT.md)须 Pro 必要决定及用户下一有限实施批准，不由资料验收转为 READY。

## 入场与所有权

- 工作区 D:/Project/321_FISH；实际 HEAD `0bf1d2684d0b975603fb3ce7505459a9f282fc3a`，tree `51da8e1943428deda3c333a741a0d19cf1a76fdc`，branch codex/cc02a-consistency。
- 入场 clean、index 空；index 原字节 SHA256 `f88d837230d5a8f0d1c7d76bdb7898c50f517a783dbaa697a934d90212904def`。入场 tracked 路径原字节 hash/index 条目保存于本机 `C:/Users/liang/.codex/resource-scope-20261002/entry.json`，不复制运行数据。
- 旧主控“准备 CC-02B-STORE-SCOPE”idle，最近交付轮 completed、交付 Goal complete；本聊天 get_goal 入场 null 后按本批启动新 Goal。未迁移或恢复旧 Goal。
- 未发现项目 Python/pytest/应用/Git 交付进程；只保留已有 Codex 服务及本次检查 pwsh。旧 heartbeat 保持原暂停边界，本批不操作其配置。
- CORE/STORE 独立 ACCEPTED，原 STORE 同版116文件1483 passed / 0 failed / 2原有 opt-in skipped仅引用历史证据，不复跑或改写。[CORE Review](../review-packages/CC-02A-RETIRE-CORE-r1.md)、[STORE Review](../review-packages/CC-02B-STORE-r1.md)、[原交付 Review](../review-packages/PR-DELIVERY-04-r1.md)保持原字节。
- 主控唯一写入七 Markdown：本文、RESOURCE Pro 材料、RESOURCE-DRAFT、本批 Review、PROJECT_MEMORY、指挥中心、生成任务清单。两个事实代理只读；另用未参与编写的代理独立资料审查，无应用/测试写入者。

## 资料目标

1. 核对 CLOUD 扫描/GET/PUT、Web upload/file、bot_say/提醒、Agent 后台结果及 preview 回写；区分 owner/actor/target、入口 A、最终 C、退役 t0、锁、独立 IO、访问及保留边界。
2. 给出必要最小 staging/发布/index/资源回执候选，异步结果最终 bus 提交与 IO failed/unknown/重启限制。Store receipt 只证明 state.json，不能充当独立资源回执；Hub 锁内不等资源锁或执行网络/磁盘 IO。
3. 自包含[Pro材料](../CC-02C-RESOURCE_Pro审查材料.md)和版本化有限实施草案，冻结建议文件、接口、锁序、失败及结果查询规则，列出待决定项。
4. 给出全部未执行的 Event/Barrier、真实 IO 故障、真实合成资源/JSON 重启、访问及查询矩阵；独立资料审查无剩余必须项、文档和版本边界通过后更新唯一中心/生成视图，交付并结束 Goal。

## 禁止与资料验收

只读源码、写必要文档，不改应用/测试/依赖，不运行应用或 pytest；不读写真实 prefs/history/server_state/audit/web_files/cloud/TLS/downloads。
不 commit/push/PR/merge/release，不发送 Pro 或其它聊天消息，不恢复 heartbeat；允许本机文档 hash/检查辅助，辅助不是唯一交接来源。
不重复身份/核心 CHAT/DRAFT/SCHED/PROFILE、bot 用户 CHAT 输入、sched due 或 STORE 已验收实现。
不扩通用 UID gate、Store V2、全119、UI/客户端四态、CREDENTIAL、LOCAL/CLOUD 格式迁移、其它媒体资源或广泛物理擦除/GC。
marker、InitializeNew、整体 loader、durable intent 仍归 CC-05。

资料事实绑定实际 HEAD/原字节；事实、建议、未决项清楚区分，草案可供 Pro 与用户评估但无代码授权。
独立审查从本文/实际源码/文档差异/原始检查结果开始，不能由编写者自验。
七 Markdown 相对链接、路线投影及 hash 一致；所有其它入场文件、源码/测试/依赖、HEAD/tree/branch/index 保持；没有新非文档文件入工作树。
交付后只结束本资料 Goal，不启动 RESOURCE 实现或下一候选；资料 ACCEPTED 不等于完整 RETIRE/R1、代码通过、合并或发布。

v1.1来自独立资料初审四必须项：草案只增加preview与原编辑/撤回纯内存赋值的窄bus锁桥接建议；明确CLOUD unknown及op记录不跨重启；冻结资源操作号的独立外部命名空间；同步19项未执行矩阵。仍只写原七Markdown，没有应用/测试实施授权或真实数据/Git权限扩大。
