# CC-02C-RESOURCE — 设计审查决定 v1

2026-10-02（Asia/Shanghai）。技术来源：[用户提供的Pro审查链接](https://chatgpt.com/s/t_6abfc634ea9c8191a98906dccb60e049)。
网页工具只取得登录页；已通过Codex只读“项目接管审查”取得最新对应完整正文，未发送消息。选定回答仅本机ignored保存，UTF8+末尾LF SHA256 `fb24bf4843d16e6bc477eaaa955a5a7ffbcdb793cf5f7c30b214a7845912f1d7`。
回答对应《RESOURCE Pro材料v1.1》；下载的sandbox决定附件未取得，不冒称逐字复制附件或验证上传附件原字节。以下归档可读正文的决定，不保存私有聊天全文。

用户在当前聊天直接要求“请按审核意见进行”，主控据此落实同一有限范围：先M01–M04正式Task冻结/独立预审，再四文件实现及合成隔离验证/独立验收；不重复请求批次内普通整改批准。
实施授权来自这条直接用户请求，Pro正文仅提供技术决定，其当时“待用户批准”是本次用户请求前的状态，不授予额外Git、数据或外部消息权限。

## 选定方案及Q1–Q4

| 问题 | 冻结决定 |
| --- | --- |
| R1/Q1 | C为短Hub最终发布许可，D_resource为独立IO结果。C<t0的在途尝试可完成锁外IO，t0不排空资源、不保证零晚物理写；t0<C不能新发布，CLOUD私有可见性撤销 |
| Q2 | 完成Web文件保留有效认证+fid共享访问；新owner/op/hash/length与明确manifest版本、body→manifest最后发布。坏新格式不可降级legacy，不加频道ACL、不猜旧owner、不扫描迁移 |
| Q3 | 有限运行态四态/同op查询重试、独立资源字段及有限查询入口；不改客户端/协议enum、不永久ledger、不首无op全响应丢失找回/跨重启exactly-once。查询权与共享下载权分开 |
| Q4 | bot owner/target最终bus检查、提醒队列同步、Agent成功/异常同门禁、preview及edit/del窄bus桥接；不撤销外部工具副作用、不重做SCHED、不加全handler退役gate |

## M01–M04必须补正

| ID | 实施与验收要求 |
| --- | --- |
| M01 | 逻辑op与attempt分开；pending重复合并/查询不新fid/执行者，unknown只对账，failed重试R→Hub新许可复查fence/目标/前序；t0后不新attempt，旧CLOUD op被后续不同op C取代不能重试覆盖；confirmed只查。begin owner/kind/op/key/payload及影响结果metadata原子绑定、staging前原子quota预留 |
| M02 | resource_manifest_version=1；出现标记或任一新专属字段必须strict新格式，无缺字段legacy降级。拒未知版本/重复键/fid/op/owner/hash/length不匹配。整体not_committed不等于磁盘未变，body孤儿/manifest未知精确分类；同op可靠残留可原fid恢复，但须M01许可与冲突检查。上传/下载/CHAT统一实际资格；C_read交已验证不可变bytes或同一对象句柄，不能重开路径 |
| M03 | 同op confirmed单调，send/audit失败不降级；有限attempt身份/R顺序防旧callback覆盖新索引。旧op可历史confirmed但visibility=superseded，退役cloud withdrawn。opaque相同bytes对账是目标内容证明，允许confirmed+uncertain+reconciled_current_resource，不假written；已知替换前失败仍failed，即使内容本来相同。管理员只结果对账不正文/不重开私有索引 |
| M04 | preview仅最终seq/author/channel/to/当前首URL/deleted/fence/无已有preview匹配；同URL文字编辑及U→V→U最终匹配允许，deleted/当前不匹配拒。callback先C后续编辑沿旧产品行为，不增generation/客户端撤图。窄bus桥接无bus→Hub辅助反向等待，cache hit先释放preview锁，原SSRF与首seqinflight保持 |

保留原19矩阵，在F01/F02/F03/F04/W02/W03/J03/NO01/P02加入上述子案例，不重新大范围资料准备。
执行顺序：文件/查询→bot/提醒/Agent→preview/窄桥接→同候选领域/最终全量/独立验收。
仅server.py/web.py/bots.py/agent_bot.py与冻结tests/必要资料。server_store.py/protocol.py/客户端/依赖/外部324/群文件分块/其它媒体/通用UIDgate/119/物理GC及CC-05 loader/marker/intent均不纳入。
CORE/STORE与1483/0/2只历史，RESOURCE新候选另验收；不得提前称RESOURCE/完整RETIRE/Pro R1完成。正式范围见[Task v1](../task-packages/CC-02C-RESOURCE.md)。
