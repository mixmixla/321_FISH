# ADMIN-GROUP-REMOVE-SCOPE-01 v1.1

2026-10-23 READY。沿用户持续Sol+FAST、小批次自主开发及正常main集成授权；root唯一集成/文档/最终验证，session_scout独立工作树实现，flagship_scout独立审查。
base为已核实main `087b6e92857093d69728c25f4aa1b97bff7d62bf`。不继承视频分支4759a01e，视频批继续暂停，不重复诊断或合并。

## 缺陷与有限产出

系统管理员 `_on_admin_group_set(op="remove")` 在锁外检查成员，锁内直接pop：同UID并发移除可KeyError。成功移除又未向目标会话发送已有group_removed协议，剩余成员群态与全局列表不能清除目标ClientCore的已加入群、成员/密钥缓存；其后重连可自动重加入公开群。这与普通退群/踢出已有的按gid清理不一致。

仅修改server.py该remove分支及必要共享只读变量位置、新增tests/test_admin_group_remove_scope.py。锁内权威复核同一群对象/目标成员、移除/管理员与禁言清理、必要群主转让、group_revision递增、目标全部会话快照；重复/群消失返回已有member/group语义，恰一次成功副作用。锁外发送group_removed（含gid/revision）到目标各现有TCP/Web会话，逐会话容错；通知、持久化、广播和审计不持Hub锁。清理仅group:{gid}语音成员；最后一成员移除时群本身及其群语音房解散。保持现有管理员override权限与持久化规则。

不得调用整号强制下线/注销/退役、撤销账号凭据、清理其他群/私聊/通话/媒体资源。不得改client_core、协议定义、GUI、视频、依赖/环境、游戏、add路径行为，或顺便修显式op=dissolve。正常成员移除、群主转让及remove导致空群解散属于本Task；显式dissolve的其他问题仍独立候选，不声称已修复。允许目标以后显式按原权限重新入群，不将移出变成永久封禁。

## 证明与验收

设计独立审查提出的确定性门位置已纳入v1.1：管理员handler先_known_names获取一次Hub读锁，再做旧cur预查；竞态屏障必须在每个owned目标线程第二次、即remove写锁acquire之前，不能误挂首次_known_names锁。原产品+新测试的RED应确定观察一成功/一KeyError，异常传播至测试主线程；修复后同测试证明一成功/一member拒绝，测试不得吞掉目标异常。设计独立复核通过再实施。实现者在原版用确定性受控锁屏障复现同UID并发移除异常，保留RED版本、实际退出码与异常；多会话目标真实ClientCore通过已有协议验证移除清缓存和重连不自动重入，保留另一群/另一群密钥及账号连接。以现有合成身份/Session接入实际Hub管理员handler，避免配置真实管理员凭据；TCP真实Hub/ClientCore证明核心行为，WebSession同UID通知可用合成传输观测。不能仅全stub或只断言服务器成员字典。

覆盖重复请求只一次成功审计/广播、不在Hub锁内网络IO/持久化/审计，非管理员/非成员拒绝、群主转让/最后成员、某目标send失败不妨碍其他会话通知、group语音清理与其他资源保留。测试owned线程有界join、异常向主线程传播，等待使用有界协议/事件屏障，不sleep竞态或无界压力追绿；清理不遗留自有Hub/会话。复用既有测试模式，不造新全局测试框架。必要领域含既有管理员群、group_removed/Core重连和退群/踢出、容量保护回归；worker不运行全量。

root冻结组合候选逐输入hash，独立代码/原始证据复核后唯一最终全量。使用既有--run-dir在原工程ignored目录下全新短路径，source-dir保持当前Git工作树，避免已证实嵌套测试Git路径超长。全量失败保留，不retry-to-green；与历史217文件3003P/0F/20既有skip基线对照，不能提前预写新计数。视频失败与上一批长路径失败原件保持，不因此新批通过改判。

通过后root据证据有限AI接受本Task，独立终审/资料检查、全部新增可达Git对象及metadata脱敏审计，fresh远端/可见保护检查，正常非强制合并推送main并核完整SHA；不重试PR、不改权限/凭据/保护、不改共享历史、不发布。CI无记录不称通过。原始日志/二进制/用户资料仅ignored本地，不公开；不声称可视GUI、自然退出、跨机LAN、新EXE或整个R1通过。

## 文件与进程所有权

主控工作树independent-r1-20261023，分支fix/admin-group-remove-integration-20261023；实现工作树admin-group-remove-20261023，分支fix/admin-group-remove-scope-20261023，base同上。session_scout唯一写server.py/newtest；root唯一写Task/Review/指挥中心/任务投影/稳定记忆与门禁证据，flagship_scout只读独立设计/代码/原件/公开对象审查。总活动工作者最多3含root，只有root启动最终full。冻结时无活动测试、无在途写操作；实际进程/命令/结果及时补指挥中心。
