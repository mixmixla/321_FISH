# TK-BOSS-AFTER-01 v1.1 — Boss 单进程生命周期诊断

2026-10-21 READY。base/main7ff225763caa2360f571b6de3beec654f32fa77d/clean，分支fix/boss-timer-lifetime-20261021；root唯一写入/执行，gate_review独立只读。普通模型/Standard。沿用用户本周有界公开/合并许可：只验收代码/测试/项目文档/脱敏摘要，排除原raw/本机用户名/私密数据/密钥/profile/EXE，不发布；审所有新文件及新提交历史，安全拒绝即停、不旁路。

## 证据门槛

先独立测试进程/单Tk root，仅Boss，真实mainloop跨1500ms show与3000ms tick，不缩短生产延迟。记录周期heartbeat、截止哨兵、实际耗时，close前后winfo_exists、每after ID/script及Tcl command是否存在、自然bgerror/Python异常。上批Mini之后的第二root在1700ms未捕获Boss bgerror，属于未确认，不凭pending或旧stderr声称应用退出坏。
若确认真实组件销毁缺陷，只冻结一个最小修复；不要顺手改skin重建多循环、重复show置顶策略或其它类。正式ChatWindow.quit_app已有全局cancel，不用本组件证据升级应用自然退出/完整GUI。
若诊断没有实际缺陷，只记录，不制造产品改动；转新源码构建及受支持有限R3，新的构建范围另在中心冻结，不无限追日志。

## 条件实现与验证

确认后只允许boss.py相应最小生命周期修复及一个真实Tk回归文件、现有管理与必要结构化证据；不改MiniBar/GameWindow/quit_app/tkguard/conftest、协议/规则/依赖，不扫root队列、不weak断言/skip或改产品延迟。
最终同字节真实RED→最小修复→相关领域→独立代码/原件审查→一次适用默认run.py test-all；源/测试/环境冻结，若执行环境中断先核PID和原件，仅按既有同run resume恢复，不重复已完成文件或覆盖partial。完整raw/exit/cleanup/skip、当前/领域/full源绑定均独立终审。
技术接受、MERGED、R3/用户里程碑、发布分开。公开精确路径/类别及历史全审后正常push/安全集成，fresh fetch/保护/checks、远端完整SHA与可见CI核实；无CI不记PASS。不发布，不删除分支。
完整native GUI/新EXE/红退出/LAN/其它DPI仍未测，不冒充组件或协议验证。本批终点形成准确恢复入口和下一项，不以消耗额度制造任务。

## v1.1 已证实缺陷与最小实现范围

独立原代码probe boss-single-diagnosis-20261021-171433-c2097c9160只验证观察器：heartbeat37/maxgap113.04ms，elapsed4190.81ms，两sentinel1882.33/3384.04ms。真实close276.19ms后窗口不存在且两个Tcl command已删除，但两个after脚本仍pending；自然1543.83ms lambda、3042.11ms _tick各报invalid command，Python异常无。原raw/probe源本地保留；1P不当Boss已通过。
冻结一个Boss owner timer生命周期修复：init自有after集合，_build/_tick/show既有排程经本类局部wrapper（执行前移除ID、_alive双guard），close和owner真实Destroy取消并清空自身任务；event.widget严格identity，忽略换肤子树Destroy。保留1500/3000ms、原hide/show及换肤排程语义，不顺手修多tick/repeated-show策略。不得扫root队列，不改其它类。
最终回归第一case把真实close放进root.mainloop的root.after回调，heartbeat和截止哨兵跨完整deadline；其它case核自然tick前后close、其它Boss/sentinel、隐藏仍tick/one-shot释放、子树换肤保持alive、6轮GC、父root/直接owner销毁、tick内重入close。原生产先同字节RED，再修；不缩短延迟。

## 验证检查点（范围不变）

最终同字节RED8F1P，代码46e25087b588cbc10e38b6550ce7e468e178d347，领域7文件101P0F0S；唯一full boss-timer-full-20261021-172649-12db730620：210文件2939P0F20原skip/exit0，487输入0a1d29967852b737d3aafa4ea8800d94da3e0747713bc616939e8ea7076052b7。只Boss生命周期，完整GUI/新EXE/自然退出/LAN/其它DPI/硬件未测，独立最终审查与公开审计待完成。详见[Review r1](../review-packages/TK-BOSS-AFTER-01-r1.md)。
