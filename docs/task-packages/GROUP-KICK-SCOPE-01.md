# GROUP-KICK-SCOPE-01 v1.1

2026-10-22 READY，既定R1会话/群权限一致性优先。base `3a995e90996fe8d6bd7bac9248ffcf32a64b8347`，分支fix/group-kick-session-scope-20261022；依赖前批已审门禁修复，原待合并分支保持。root唯一产品/测试/资料写入，r1_review独立设计、代码、原证据审查。最多本批一个活动产品修改，不直接push main、不重试PR403、不发布。

已查明协议碰撞：server._on_group_kick与管理员强制下线均发error/kicked；ClientCore、ChatWindow、Web生产处理器据kicked执行全账号下线。群目标只通知代表Session，且其未收到新group_state，可能保留自动重入集合。不能让群主操作成为账号强制下线。

本批产出：server.py发独立error/group_removed并带gid，只向踢出时已存在的该UID全部Session通知，不撤账号/token；client_core.py仅清理该gid的自动重入、旧成员/邀请码及已开启群密聊材料，保留其它群、账号、会话与消息。客户端/UI/Web已有通用错误显示继续使用，真正管理员kicked、deleted、retired终止语义保持。无需改协议版本、认证或群授权规则，不增加禁入群承诺；显式正常再加入仍按原服务规则。旧服务仍用歧义kicked时不猜测文本降级，混版本限制如实说明。

先新增真实合成Hub+双目标ClientCore+群主的加密loopback回归，受控红测证明被移群导致错误下线；修复后两目标端保持同UID/epoch在线、公聊可达，移除群不自动重入（实际断线续连后核服务端成员），其它群仍正常。群通知不触发桌面切号或Web leaveLogin；服务器所有目标端（含Web Session/token）保持认证、非目标不误伤；原群权限/管理员踢下线回归保留。更新旧测试两个通知码断言并加强gid，不能删除权限断言/新增skip。

允许产品仅server.py/client_core.py；测试限新增tests/test_group_kick_scope.py及test_server.py、test_cc02a_client_kick.py、test_cc02a_web_kick.py必要回归。先红测，再最小修复/领域/独立复核；最终冻结唯一新产品候选完成适用全量、独立终审和新增对象审计后正常推功能分支。保留旧全量及所有新失败，不retry-to-green。源码变更前不把静态问题当作已运行复现。

全部数据fresh合成、loopback、默认隔离门禁；不动真实用户群/账号/口令/配置。自有服务/核心线程有界清理、异常不覆盖原失败。公开只代码/测试/项目文档/脱敏摘要，不原日志/本机用户名/私密/二进制。真实协议与生产处理器测试不等于可视GUI、自然退出、物理LAN或新EXE验收。

v1.1设计审查补足两条必要竞态：Hub运行态单调group_revision在同一Hub锁内与group_state捕获/群移除取得，Core修改缓存前过滤旧或相等版本；WELCOME仅清服务端revision。Core本地每gid generation与removed标记在已有_send_lock下更新，密钥worker开始capture/最终校验与生成发送登记分短锁段，握手等待锁外；移除使旧worker失效，WELCOME不重置generation，较新且含自身的group_state才解除removed；迟到密钥信封不得恢复已移除群。受控Event证明旧state晚到/新加入后旧remove、握手跨移除（含重连）和重启后较小revision正常接收；不持Hub锁IO、不改持久格式、不建立永久ban。独立设计0 MUST后进入红测，代码和原证据仍须复审。
