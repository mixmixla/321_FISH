# CC-02B-STORE — 设计审查决定 v1

2026-10-02（Asia/Shanghai）。技术输入：[用户给出的Pro审查链接](https://chatgpt.com/s/t_6abf7206049481918946060d1260ad00)。
用户在当前聊天直接答复“我批准按此审查意见进行”，授权按以下补正冻结有限Task并实施；不再重复请求同一代码范围批准。
分享网页只返回登录页；已通过Codex只读“项目接管审查”取得最新对应审查正文，输入附件原字节SHA256与本工作区Pro材料一致：
`9120aa777c1fe1833a593718080fb42835d9b3f2817758e91c6efd2e081c2576`。
选定回答仅本机ignored归档，UTF8+末尾LF SHA256为`de107ad947a533a50eea9e3677537a4d51558127156ae06659c50bccfdd5330e`；不入库私有聊天全文/真实聊天标识。
回答所链接sandbox附件尚未通过本工具取得；以下决定与正式Task矩阵依据完整可读审查正文，不宣称逐字复制附件ST01–ST12。

## 方案与四项决定

Pro选定S1最小方案，S1严格bytes/阶段IO→S2有限候选证明/统一ack→S3 unknown对账/同op查询重试，在一个有限Task内按顺序完成。
设计结论为需要补正M01–M05，不是代码验收；CORE1392/0/2只作历史证据，STORE变化另验证。

| 决定 | 冻结结果 |
| --- | --- |
| Q1 | 保留已修writer/fresh capture/request_seq；request_seq仅保存请求截止，不是身份持久证明。无持久revision/schema/全119版本系统 |
| Q2 | 严格一次JSON UTF8 bytes、插入序、allow_nan=False、无default/repr/替换字符；检查键转换冲突与strict read重复键；同bytes计算运行态SHA256/长度和写入，无磁盘hash或永久ledger |
| Q3 | 专用严格读取有限对账；unknown约束所有writer和活动Hub兼容save。只有可证已知合法前序且无冲突才failed/retryable；其它冲突/不解释/missing/坏文件保持unknown，不覆盖 |
| Q4 | 确认来源必须返回written/reconciled_current_json/restored_valid_json；恢复仅证明合法退役记录，没有旧receipt则SHA/revision None，不重新编码内存伪造旧回执 |

## 五项必须补正及接口边界

| ID | 正式实施与验收要求 |
| --- | --- |
| M01 | 全部实际snapshot嵌套可变对象独立；捕获后live变化不影响候选。CORE退役条件先校验，失败不发布权威JSON、保留fence/dirty，不能先写后只拒confirmed |
| M02 | 未决提交保存在有限运行态，普通worker/force/flush/活动Hub兼容调用都必须在下一实际replace前统一对账。无结论暂停该Store替换，不忙循环、不持Hub等待；其它允许内存业务可继续 |
| M03 | 对账区分未决候选匹配、已知合法后继且同op清理有效、已知合法前序无op无冲突、同UID异op/昵称冲突/清理残留/无法解释、missing/读错/坏结构。无充分证据不允许自动覆盖；当前读bytes是新receipt SHA来源，后到dirty保持 |
| M04 | writer→短控制锁读cutoff→释放控制锁→Hub→bus capture→校验/编码/IO→仅ack cutoff。禁止capture旧状态后才取较大request_seq；统一ack覆盖后台补成功/迟到失败不降级 |
| M05 | 三种confirmed来源必填且保证不同；不升级为UI/资源完整、坏缺loader/备份恢复或首次失败跨重启保证 |

TCP及HTTP直调payload查询进入同一对账步骤，但纯payload与IO步骤分离，核对所有实际外层锁。不得持Hub/bus/persist控制锁等待writer/磁盘。
typed SaveResult显式比较effect，不能对象truthiness；短写/0进度/无效返回都处理，close在replace前、cleanup不遮首错。

## 文件与权限

实施限server_store.py、server.py存储/快照/退役结果/查询辅助、专用tests及必要旧hook；正式冻结见[CC-02B-STORE v1.1](../task-packages/CC-02B-STORE.md)。
用户当前批准含代码、合成隔离验证、独立审查与必要文档，沿已有Goal偏好持续到有限验收终点。
不改web.py/客户端/资源handler/协议/依赖；CLOUD/upload/bot/preview、UI、CREDENTIAL/LOCAL迁移、全119、物理GC延期。
marker/InitializeNew/整体loader/durable intent归CC-05。不commit/push/PR/merge/release，不真实数据、外部消息或恢复heartbeat。
STORE通过不等于完整RETIRE、Pro R1、合并或发布；首次持久提交从未成功的重启限制保持。
