# CC-02C-RESOURCE-SCOPE — 资料与版本边界 r1

2026-10-02（Asia/Shanghai），对应[资料 Task v1.1](../task-packages/CC-02C-RESOURCE-SCOPE.md)。状态唯一见[指挥中心](../AI_COMMAND_CENTER.md)。

## 接续和证据边界

用户直接批准只读资源资料/有限草案/独立资料审查与 Goal；不批准代码实现或 Git 交付。
启动顺序已读 AGENTS/COLLABORATION/中心/生成清单/接续指南/PROJECT_MEMORY、CORE 与 STORE 最新决定/Task/Review及 PR-DELIVERY-04 Review。
实际 HEAD `0bf1d2684d0b975603fb3ce7505459a9f282fc3a`，tree `51da8e1943428deda3c333a741a0d19cf1a76fdc`，branch codex/cc02a-consistency，入场 clean/index 空。
旧主控“准备 CC-02B-STORE-SCOPE”idle、最后交付轮 completed；只读最后答复确认交付 Goal 已完成/HEAD0bf1d26。当前 get_goal 原为 null，随后新资料 Goal active。
Get-CimInstance 未见 Python/pytest/项目应用/Git交付进程；现存 Codex 服务不视为同队列实现主控，不终止无关进程。
未 fetch/pull/切分支/改 index；PR open/draft/未 merge 只引用原交付证据，本批不另宣称实时远端核验。
本机入场证据 `C:/Users/liang/.codex/resource-scope-20261002/entry.json` 为 tracked 文件 hash/bytes、index 条目及版本，不含真实数据。

## 文件所有权与执行记录

主控唯一七 Markdown；resource_files_facts/resource_async_facts 两代理只读源码；独立资料审查另用新上下文且不参与文档编写。
所有 shell 通过 pwsh；未运行应用/pytest，不读取真实运行目录。本批只做文档/边界检查，不复跑116文件1483/0/2，原 CORE/STORE/PR 证据原字节保持。
Goal 只覆盖本批准资料终点，不恢复 heartbeat、不发 Pro/其它聊天消息、不做 Git 交付或 RESOURCE 实现。

后续记录实际事实梳理、材料版本、独立必须项/整改、hash/相对链接/投影/HEAD-index 边界与 Goal 工具结束结果。当前未提前宣布资料验收或未来资源测试通过。

## 静态调查与资料候选 v1

resource_files_facts/resource_async_facts独立只读返回源码锚点：CLOUD先内存后IO吞错、扫描在identity restore前；Web先读完整body后认证，两文件直写、legacy无owner/target、GET任意有效认证+fid；Web CHAT只查sidecar不查本体；bot_say/提醒队列/Agent结果绕过最终Hub屏障；preview仅bus检查且deleted墓碑保留seq、cache hit在preview锁内回调。
主控初稿形成自包含Pro材料/R1候选、Q1–Q4待决定、四应用/三新增专项有限草案及F01–V01全部未执行矩阵；v1.1加NO01，最终19项映射RC01–10。文件C定义为最终授权permit、D_resource为IO成功，Q1显式供Pro决定；不声称跨文件事务/t0后零物理写/重启op可恢复。
legacy/完成Web访问保持现行auth+fid作为建议，ACL收紧待Q2；未根据bus是否还留消息猜owner，不擅自执行新ACL。Agent只限制本仓库结果回写，不宣称外部副作用取消；preview同URL首seq分发保持。
独立resource_docs_review已从新上下文开始Task/实际源码/文档差异审查，未参与编写。

首轮文档边界helper只使用stdlib与Git只读命令，无应用/pytest导入：`& ./.venv/Scripts/python.exe -X utf8 C:/Users/liang/.codex/resource-scope-20261002/check_docs.py --generate`，真实exit0。
入场388 tracked路径；改变仅中心/生成视图，新四Markdown；源码308 raw ID `96e62366ff150364bf9cf77ecd8d19ab4369a84e9973b3c8987086192c8eb628` 与原STORE完全一致。
HEAD/tree/branch/index原字节一致、0越界、166相对链接无断链、投影/源SHA与diff-check通过。随后必要PROJECT_MEMORY事实索引及接口精确化在允许七文档内，最终检查计数/正文ID另捕获，不复用首轮计数冒称最终。

额外窄只读复核明确：服务端首次生成op且所有响应丢失，旧客户端可能同时不知op与Web fid；精确同op查询有“已知op”前提。材料新增NO01/RC10负例及明确限制，不新增latest定位/payload去重/客户端行为。无op重发作为新请求，不能覆盖同key unknown；Web不同fid的新请求可能重复，不能假称旧资源精确恢复。19项未来矩阵仍全部未执行。

## 独立初审与 v1.1 必须项整改

resource_docs_review新上下文独立只读初审：C/D_resource及t0排序、Hub不等R/IO、confirmed才CLOUD_DONE、已知op前提、legacy待Q2与Web非事务已基本自洽，提出四资料must，未先ACCEPTED。

| must | v1.1整改与待独立关闭 |
| --- | --- |
| Preview/edit/del锁依赖 | 源4590–4640/4651–4684赋值原在bus外；草案明确两函数find/状态检查/赋值/事件副本窄bus锁桥接并纳符号/P02 Event/test_r26必要hook，错误/route/persist锁外。不增其它handler retired gate，Q4及用户下一Task需涵盖，当前只文档 |
| CLOUD unknown重启 | 明确仅当前进程unknown/同key fence；replace后finalize前崩溃，新Hub非retired owner可扫入非空blob，仅恢复访问无旧op receipt，fence丢失且新显式PUT可覆盖；跨重启fence/intent延期CC-05，合法retired JSON私有访问保证另成立，J02补负例 |
| 管理resource与retirement op冲突 | 外部资源统一resource_operation_id/resource_owner_uid，ADMIN_USER_INFO.resources独立runtime摘要，原顶层/retirement.operation_id及Storeorigin不变；无路径/正文、无概要IO等待、adminquery不重开retired cloud |
| 版本/投影计数 | Scope/Pro/Draft v1.1，19项未执行矩阵/RC01–10，当前中心与生成视图同步；历史首轮166/后续173链接仅保留当时证据，最终重算 |

主控同时注明当前CORE未清bot_reminders，提醒清理是候选；bus C不是Store/重启持久证明，异步结果沿现有history/seq查询，不扩永久job ledger。
修订只原七Markdown；四must须独立复核关闭后资料ACCEPTED，未运行资源/应用测试，Pro Q1–Q4及下一有限实施批准仍缺。

## 独立终核与资料交付

resource_docs_review独立最终复核：v1.1四must全部关闭，无剩余资料级必须修复项，**可ACCEPTED（仅资料）**。
它未参与编写/实现，从Scope/Pro/Draft/实际源码与文档差异核对，确认preview窄bus依赖及双向矩阵、CLOUD运行态/重启限制、独立资源字段/管理员runtime摘要、19矩阵/NO01和历史计数边界；CORE未清提醒/bus C非持久成功/legacy待Q2均明确。

最终三正文绑定（Scope/Pro/DRAFT，不含Review与中心流转）：规范JSON路径→SHA256映射的body ID `9418113e96423ed3be29dc3dc211a825224400f8fe0c300ac1cee3f0f182d3fa`，原字节逐文件SHA在本机boundary.json；后续只Review/中心/投影结束元数据，不变此正文。
最新静态helper真实exit0：388入场tracked旧文件中仅PROJECT_MEMORY/中心/生成清单变更，新增四批准Markdown，共七文档；0越界/无新非文档。
308源码/tests/依赖raw ID `96e62366ff150364bf9cf77ecd8d19ab4369a84e9973b3c8987086192c8eb628` 完全保持原STORE；原CORE/STORE/决定/交付资料及其它入场路径原字节一致。
HEAD/tree/branch/index原字节一致（index SHA f88d8372…且无staged），173相对链接无断链、投影/源SHA和git diff --check通过；19未来矩阵仍未执行。
主控据独立结论置资料ACCEPTED，唯一中心/生成视图已同步；Pro材料open_in_codex返回queued，仅表示请求显示，文件可由工作区链接读取。

下一审批点：用户将Pro材料及v1.1草案交Pro决定Q1 C/t0、Q2 Web legacy/共享及metadata、Q3独立资源查询与首次无op丢响应限制、Q4异步保留及edit/del窄桥接；归档后正式有限Task独立预审，用户批准下一实施才READY。
没有未完成资料must，不要求为待决技术选择继续本资料Goal。未运行应用/pytest、未真实数据/Git交付/外部消息/heartbeat，原交付仍保留。本资料不等于RESOURCE代码验收、完整RETIRE/R1、merge/release。

Goal工具已确认complete，1750秒（约29分钟），未设预算。结束后只本Review/中心/生成视图补录工具终态，三正文9418113e…不变；最终173相对链接/投影/308源/HEAD-tree-branch-index/388旧文件边界仍PASS。完整最终七文档hash与检查结果在本机boundary.json，不用自身文档构造自引用SHA。
本资料批次交付完成并停止；七Markdown本地未提交，资源实施候选仍PROPOSED，Pro决定/下一用户批准另取得，无应用或pytest过程/未完成资料验收需要接续。
