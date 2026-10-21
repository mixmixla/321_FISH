# TK-GAME-AFTER-01 v1.1 — 游戏窗口自有定时任务销毁

2026-10-21 READY。用户要求先独立定位旗舰 Tk 销毁后的失效回调，只做一个有真实证据的小增量；普通模型/Standard。base/main 8f1595d77da3b2bfd531a1c535930de7b6bbf39f，分支 fix/tk-destroy-callbacks-20261021。root 唯一写入/验证，gate_review 独立只读。

## 证据门槛与范围

先在单个存活 root 下，用真实 GameWindow.close、真实 Tcl after 队列和事件循环复现销毁后残留任务/失效命令；不能仅凭旧 full 的 stderr 断定正式应用退出失败。ChatWindow.quit_app 已全局取消解释器任务，该路径不据此认定有缺陷。只有单组件复现成立才修 GameWindow 自有 poll 与三次延迟 game_list 请求的生命周期。

允许 client.py 的 GameWindow 和一个真实 Tk 回归文件、既有管理/审查与必要合成证据。close 只取消自身任务，已执行 one-shot 不累计引用；hide/show 保持原轮询与补发，close 可重复调用，同步回调内关闭不能重排任务。不得清空整个解释器队列、修改 tkguard/conftest、延长产品时序、弱化断言/skip 或混修 MiniBar/BossWindow/BoardFocusWindow。其余诊断保留，不宣称全部 stderr 已消除。

## 验收

1. 原代码同一真实 Tk 回归先 RED，保存 pending ID/脚本、bgerror；区分正常隐藏与销毁。覆盖首次 poll 前后关闭、真实事件触发失效命令、无关 sentinel/另一个 GameWindow、反复创建/关闭与回收、hide/show、poll 同步期间重入关闭。测试数据 synthetic core，仅真实 Tk 组件，不当完整 GUI/网络证明。
2. 证实后最小实现，原断言不变，同回归 green，相关旗舰/大厅/房卡/布局/退出等逐文件领域回归；独立审查代码与原始 RED/green/领域结果。
3. 冻结候选后仅一次适用最终 run.py test-all，默认隔离 source/profile/private desktop/loopback，不启用 visual/hardware。独立终审核内容标识、退出码、逐文件原日志/cleanup/skip，失败不按重跑抹掉。
4. 更新现有指挥中心、任务投影、Review 和稳定事实。本轮至此停止，不新增产品任务。完整 native GUI、EXE 新代码、物理 LAN/其它 DPI/正常红退出仍未测；旧 EXE 不包含本修复，不能回溯升级其证据。
5. 本地提交允许。上一批 42 文件的具体公开许可只绑定 8f1595d；新批单独核内容和适用授权/安全检查。正常 push/安全合并须 fetch 核远端和保护；拒绝就报告，不换路线，不强推/发布。

## v1.1 真实引用链诊断后的验收精化（未扩大产品修改）

首RED5F1P；首修5P1F：队列断言已过，但原新增的“root仍活时整个GameWindow弱引用立即消失”不成立。独立真实probe tk-game-referrer-20261021-155308-1b3e942a24：唯一存活绑定方法是GameWindow._dispatch_wheel，对应root._tclCommands中的同名命令；四个本次新增run闭包均已释放，root.destroy后整个GameWindow释放。这是既有bind_all全局绑定的生命周期，不属于本修复。保留首修失败原件，不删断言掩盖。
冻结最终测试把内存边界明确为：每轮close后自有after队列回基线且新增调度闭包全部释放；完整GameWindow在root.destroy后全部释放。root存活时滚轮绑定保留仍是已知未修，不声称所有组件引用均已释放。最终同字节测试须在旧生产代码重新RED，再green/领域/独立审查/一次full。
