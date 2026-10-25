# KEY-INIT-RACE-REPRO-01 v1 — 同UID密钥首次初始化的有限复现

2026-10-25 已冻结READY并完成设计审；现PARTIAL_BLOCKED / NOT_AI_REPRO_CONFIRMED_TASK。用户本轮约90分钟有限本地开发授权，
剩余时间只补下一项故障的合成复现证据，不修改产品或已验收包。base为已Git/API核main
`18a4a5e4e90bc1669dda142c9f0db02dc14a2a7d`。本任务不是密钥并发修复或完整安全设计。

## 唯一范围

root从base新建独立key-init-race-repro-20261025工作树；server_scout唯一写一个本地候选诊断测试
及ignored证据辅助脚本，绝不修改产品/旧测试/依赖/门禁。root唯一Task/Review/evidence/中心/投影；
identity_scout独立设计、实际测试与原件审查，不参与实现。原集成树505源、已有EXE/新旧包保持不变。

一次新隔离门禁仅两个真实ClientCore、同ROOT/scope/UID案例，预建共享UID目录以排除已修父目录竞争。
仅合成账号/密钥，公钥只比相等、私钥不读或打印；受控hook必须继续真实open/json.dump/fsync/load，
不能用模拟异常代替故障。门只命中A线程和精确新合成key路径；观察wrapper仅记录异常类型并原样rethrow，B也有界线程。Event门及有界join/stop，超时/夹具错误不能当故障证据。

1. A在精确e2ee_identity.json的真实mode=x调用前暂停；B完整WELCOME并完成真实落盘，冻结B文件SHA，
   再放A。候选回归期望两端成功且同公钥，现版应实际FileExistsError导致A local_storage/manual；
   B成功、原件SHA不变、A失败来源与门全部正常必须有证据。
2. A实际open(x)已创建零字节文件后、真实json.dump前暂停；B真实WELCOME应读该空文件，
   捕获实际JSONDecodeError到E2EEError的链和Core拒绝；随后放A完整写入/fsync成功。候选回归仍期望
   双端成功而现版失败。不得把A尚未完成时的短暂空文件误称持久损坏，也不得声称已泄露密钥。
3. 单次两例RED保留真实exit/完整stdout/progress/sandbox/清理/source快照；预期失败与意外超时分类。
   独立技术确认两个真实窗口后最多AI_REPRO_CONFIRMED_ONLY（仅两个真实Core的同进程受控交错，不代表跨进程复现或发生概率），不写AI_ACCEPTED修复。
   不为变绿修改产品、重跑或弱化断言；如未命中，只记录未确认/具体阻塞，不补造证据。

## 时间、交付与后继

新长步骤须06:12 UTC前实际启动，06:27收尾；若无法及时完成独立测试预审或复现，停止并保存本地候选。
不开始修复、跨进程实验、源码full、构建或GUI；不读取真实用户资料或改个人记忆。
本地候选失败测试和原日志仅ignored/未提交诊断工作树；绝不合入main失败测试。
只可公开本Task、Review、脱敏计数/状态/hash的evidence、中心与生成投影五文件；独立公开与Git对象审后
沿用户许可正常main快进/push，不PR/强推/绕保护/发布/上传EXE/raw。

后继需独立选择跨进程初始化协调或不可覆盖的原子发布，保持已有合法/坏key与reparse拒绝、写入失败、
超时/关闭、跨进程双实例及不同UID不串锁合同；本任务不选择或批准实现。不把同进程复现当跨进程修复验收。
完整GUI、自然退出、物理LAN、异机/DPI、STT、暂停视频4759及其历史失败保持原结论。

## 本次结果与停止点

06:08:06 UTC启动唯一kir25-red，实际exit1/2F/1.221s；第一例完整命中FileExistsError到末正常行为断言，
成功方和赢家key保持/清理证据充分。第二例真实空文件读取链为E2EEError→JSONDecodeError→StopIteration，
夹具只预期前两类而提前失败；未完成最终双Core状态/写完后SHA证据，不算整例确认。
独立原件审查同样判PARTIAL_BLOCKED，任务未整体验收。候选测试保持本地原SHA，未改产品、未重跑。
只有准确披露此状态的项目文档和脱敏摘要可经独立公开审交付；不把资料审查通过等同诊断Task通过。
下一轮需明确修订夹具合同后，仅补第二窗口验证；完整修复设计与跨进程验证仍另Task。
