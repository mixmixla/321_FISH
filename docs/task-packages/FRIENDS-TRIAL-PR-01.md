# FRIENDS-TRIAL-PR-01 v1

状态：LOCAL_ACCEPTED_DRAFT_DELIVERY_PENDING。目标：把已经本地冻结的少量朋友试用候选必要源码、测试、说明提交新隔离分支，并向 main 创建 draft PR；保持草稿，不合并、不 release、不联系朋友。

基线：已核远端 main `0c90fd0ecb1d7d38cad1a3082e26fcbe20e23e8d`，PR #6 已合并，入场无开放 PR。分支 `feature/friends-trial-candidate-20261006`；原开发 checkout/全部 dirty 保留，不 pull、不切换。

范围：冻结核心358输入/152测试文件（已验2211P/0F/2原opt-in SKIP），及独立便携入口2模块+36案例测试。包括核心候选所必需的credential_ops、retirement_status、server_recovery及对应应用/协议/UX回归；这些已经在核心门禁中执行。不得附带原checkout的其它dirty或六实验模块 client_auth/client_session/client_work/local_owner/local_prefs/owner_history及其13测试。

验收：逐项绑定候选raw hash及Git行尾规范化blob；完整diff及secret/运行资料/大binary边界检查；Sol独立审查；新组合361输入/153测试只跑一次默认完整门禁，0失败、仅2原opt-in SKIP，不过滤/恢复/弱化。失败原样保留并只修相关问题。

交付：源/test/doc提交到指定repo的新分支，创建base main的draft PR，核head SHA、差异及CI状态。新入口已有真实private desktop身份、合成父死亡子孙清理/其他Job存活、compiled双登录后精确owner中断清理证据。不得把强制中断写成自然GUI退出。

禁止：真实prefs/聊天/账号/凭据/运行Store或TLS私钥、诊断/原始运行日志、EXE/ZIP大包、ProcMon、改变防火墙/安全设置、恢复Goal。CP4历史WinError5/errno13继续BLOCKED/root cause未定且留在开发范围；本候选不包含该实验链，也不宣称根因修复。

未运行保留：完整EXE窗口对局/自然退出/重复操作、实际console X、非开发机Windows、物理跨机LAN。朋友试用包不等于生产发布。本次交付范围止于remote新branch/push/draft PR，不延伸到merge/release。
