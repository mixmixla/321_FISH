# R1-OFFLINE-RETIRE-DIAG-01 v1.1

2026-10-22 READY；本轮R1/M1重启一致性优先级及允许不依赖main合并的隔离诊断。base `4a94762d767a1f25e5886d20fc36731d09c04e7d`，独立分支feature/r1-offline-retire-diagnostic-20261022。原feature/r1-restart-reconnect-20261021待PR合并状态保持；PR连接器403不重试、不直接push main。root唯一执行/资料写入，r1_review独立只读设计与证据审查。

仅验收诊断，不改产品或正式tests，不重建/重跑已验全量。以最终已验490输入的逐SHA副本加一个本地探针，通过既有逐文件隔离门禁执行一次。探针只用fresh合成Store/profile/随机loopback端口，禁用发现、Web、托盘、硬件，随机合成管理员密码不输出。原件和探针留ignored本地，公开仅脱敏结论/输入与结果哈希。

目标：两个原ClientCore在Hub1正常停止后保持运行；无TCP监听的Hub2从同Store重开，管理员通过既有认证/退役接口确认目标身份持久退役，再正常shutdown释放owner；Hub3同端口同Store重开。目标原core在新epoch收到retired/manual_login_required，停止reconnector且无新welcome/会话；旁观原core保持UID并新epoch welcome、实际聊天可达。核retired UID/昵称占用及operation_id一致，不复活账号。按实际证据区分管理员控制接口调用与真实客户端加密TCP链，不称完整管理UI操作。

所有自有core/worker/listener/Store owner有界清理；先登记资源，finally逐项清理，原失败加cleanup note而不覆盖。只运行此新增场景，不重跑既有路径追绿。失败保留，先独立诊断，不自动扩产品修复；通过仅有限AI接受该场景，不升级R1/M1/GUI/LAN/EXE或自然应用退出。正式回归是否纳入后续批次另定，本次不制造代码堆叠。

开始前设计及探针独立审查；完成后原结果/来源绑定/清理/脱敏文档独立终审。当前代码已通过2984P0F20S的既有完整门禁仅作基线，不冒充新增探针的全量；本批纯诊断资料无新产品/正式测试输入。

版本v1.1：实际非Git门禁仅捕获487输入（原486+探针），准备副本仍491。排除.python-version/app.ico/tests/_run_all.py/tests/_smoke_excel_skin.py；另核真实解释器、依赖及原490未改。此为执行后证据绑定澄清，不变更正确性条件，不据此重复诊断。
