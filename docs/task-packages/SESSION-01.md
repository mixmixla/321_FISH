# SESSION-01 — Web明确退出与单会话隔离

版本v1，2026-10-01。批准范围来自 [BATCH-R1](BATCH-R1.md) 的连续生命周期授权。
状态/下一动作只见 [指挥中心](../AI_COMMAND_CENTER.md)。

目标：网页用户有明确退出操作，注销当前已认证Web Session并立即撤销其token，
清理当前网页登录态/SSE并回到登录入口；同UID其它Web/TCP端保持在线和原权限。
刷新页面或SSE暂时断开仍按既有重连，不隐式注销整个账号。

精确范围：`web.py`既有工具栏、退出JS、本端EventSource重连保护、`do_POST`新增`/api/logout`分支及`_logout`；
新增`tests/test_web_logout.py`和相关既有领域。代码写入者`file_auth_impl`，不在本任务修改server.py。
优先复用现有`session_by_token`、`unregister`、认证/CSRF/Cookie规则，不新建平行账号或token模型。
消息协议、UID、管理员权限与文件鉴权保持；不改桌面账号UI或games_pkg规则。

验收：合成账号的真实HTTP退出流程、旧token失效、另一Web端和TCP端可继续收发，
注销通知/代表会话切换准确；伪造uid、未认证/失效token和跨源请求不影响其它会话。
网页退出入口可达、退出后SSE不自动重新恢复旧认证态；正常刷新/重连仍可用。
专项/领域与独立审查通过；最终候选全量按批次Task执行，不能把未跑全量写成子任务已全量。

已核验：现有token绑定具体Web Session并由unregister撤销；SSE detach不注销，当前无退出API/按钮。
成功退出200；失效/无凭证401且清除本端残留Cookie；GET退出无副作用。
当前没有全局Origin/CSRF模块，本任务只为新增退出POST在Origin存在时校验同源，
不匹配/非法/null Origin返回403且不注销/不清Cookie；无Origin的既有程序化请求继续兼容。
保持Cookie优先和body/query兼容入口，忽略body伪造uid作为注销目标；删除Cookie保留Path/HttpOnly/SameSite/HTTPS-Secure属性。
JS成功或401后关闭当前SSE、取消重连、清本端登录态、回登录；网络失败/其它错误保留状态并提示，
旧SSE回调不能恢复已退出认证。正常刷新/短暂断开仍可重连。

已知unregister的UID级 `_drop_xfers_of` 和 `rooms.on_disconnect` 目前会在非最后端执行；
归SESSION-02冻结修复，本子任务仅先形成认证/在线隔离候选，不能在本批其它端资源误伤尚未关闭前当成可发布版本。
其依赖可按“实现+领域+独立代码审查满足”继续SESSION-02，完整通过结论在批次最终候选全量后形成。

精确边界已由主控核验并置READY，开始实现后冻结。
普通整改在本范围内继续，不每轮等待用户；重大账号/协议决定才升级。原始证据在本批本机目录，
脱敏结果/版本/结论落 [Review](../review-packages/SESSION-01-r1.md)。
