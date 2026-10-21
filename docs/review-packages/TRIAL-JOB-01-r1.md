# TRIAL-JOB-01 r1 — 标准自主 EXE 预检的 Job 所有权

2026-10-21：**AI_ACCEPTED_JOB_ONLY / FULL_PASSED / STANDARD_EXE_PREFLIGHT_PASSED / PUSH_APPROVAL_BLOCKED / R3_GUI_NOT_RUN**。
[Task v1](../task-packages/TRIAL-JOB-01.md)。当前用户要求自主验收并继续一个不依赖GUI放行的小增量；本轮只此项，不扩产品功能或发布。

## 选择与改动

基底main ade446e639713297774fea3e7898f8dbb523a4ac，分支fix/trial-owned-job-20261021，root唯一实现/治理，gate_review独立只读。当前工具重新核无node_repl/cua/sky/native GUI入口；先前ComputerUse技能路径也不存在，不自制替代输入/截图。
R3完整大厅/邀请接受/一局结束再开/返回聊天/红退出仍未测；不能因此阻塞独立可推进部分。当前无其它独立READY产品任务，优先解决R3标准预检仍需临时adapter的已证实清理风险。

代码提交 `975c09b7903b7c80b908b41b746a52cb3b38ae18`：local_trial.py仅34+/16-，默认launch_process改为既有friend_trial_process.launch_owned；进程suspended→赋私有unnamed Job→resume，终止只按持有Job句柄，不按可能重用PID。角色仍在新增记录/查询前登记。
新增_cleanup_trial_process记录active_before/active_after/close_ok，查询/terminate/close任一失败均ok=false并传递到run_candidate的非0结果；不再吞close异常。state只作信息，所有权/成功由Job归零与关闭决定。
未改client/server/协议/GUI/规则、共享friend_trial_process/test_sandbox或依赖。新增真实Windows进程测试6case：自然初始化exit0/7、真实子孙树与无关sentinel Job、围绕真实Job的query/terminate/close故障注入。故障注入只证明错误分账，不冒充完整EXE或GUI验证。

## 复现与夹具时序

原生产先6F；测试收尾改同版本base解释器直起，避免RED的venv redirector子进程，再6F。旧默认seam返回DesktopProcess而非OwnedJob，且无正式清理接口。
首修4P2F原样保留：根wait自然0/7后Job accounting瞬时仍1，原before==after==0断言失败。独立短Job只观察不强停，均在10.8ms自然到0；据此只给initializer夹具加2秒有界自然归零等待，保留全部原退出码/前后0断言，超时仍FAIL。故障setup也纳finally保护。
冻结最终测试SHA `f10d0fbd9cde35f1c0dbd9cd452946150d608dfeabbfce653a3f511dfc636d09`，独立白名单副本只恢复ade446e旧local_trial，最终同字节RED6F/exit1；修后领域3文件57P/0F/0S、exit0。中间RED/4P2F、诊断与最终RED原件全部保留在[证据目录](../review-assets/TRIAL-JOB-01/)，不以重试抹失败。
最终RED原目录 `_tmp_gui/trial-job-20261021/final-red-source/_tmp_gui/test-gate/trial-job-frozen-red-20261021-142537-e37300e7c6`；领域 `_tmp_gui/test-gate/trial-job-domain-20261021-142606-8f174eea89`。

## 最终全量

唯一完整run `_tmp_gui/test-gate/trial-job-full-20261021-142858-9910a7a8ba`：**207文件、2916 PASS / 0 FAIL / 20原opt-in SKIP、exit0、720.711秒**。
484输入/source `0fb990f761b1230c3bfa1c1b859a7f0b893409affd9a3e94ad86cb673e8645e5` 与领域/当前/完整snapshot逐hash相同；对旧完整源只改local_trial并增新test，旧206文件各计数保持，新6case全绿，之前三项修复输入原样保持。
207原raw SHA、单attempt、cleanup/退出码、无unexpected skip均核；默认visual/hardware未启用。20 skip精确r45硬件1、ux_visual_chat_shots18、visual_screenshot1，不改任何旧skip/断言/timeout。
[完整原summary](../review-assets/TRIAL-JOB-01/full-summary.json) SHA `2c2e610dc179cb585042b3a8dd8c13ccb2b1086004641fc43a9a1ef361a568bb`；[后验](../review-assets/TRIAL-JOB-01/full-verification.json)记录11项检查与全部207日志hash。

## 正式无 adapter 实际 EXE 预检

实际命令：项目.venv Python执行 `local_trial.py run --source-dir <R3 build/source> --run-root _tmp_gui/trial-job-20261021/exe-preflight`；无monkeypatch/临时adapter/pytest guard。
run `run-20261021-062805-8f25534c0c` 真exit0：fresh三profile、private desktop、127.0.0.1 TCP7984/Web7985，发现/托盘/热键/设备/HTTPS关闭；server.exe显式initialize-new自然0再open，HTTP200，实际双client.exe以uid1/2经TCP登录并同时存活，映像一致。
4个Job active_before为client2/beta2/server3/init0，active_after全0、close_ok全true。服务与客户端由Job强停只算清理，**不证明自然GUI或server退出**；只有initializer自然0已取证。
runtime副本479项前后同9d8d9625ad67db943be4a54659fad8ec24b4fc969e426d4c42ba771b50c52c00；它是旧构建副本子集，不能混同本轮484输入。crash.log均boot行。
三EXE hash与R3原件相同，实际CArchive/PYZ均无local_trial，所以受测组合明确是新外部harness+旧未变产品，不重建、不声称旧EXE含新harness。见[组合绑定](../review-assets/TRIAL-JOB-01/exe-combination-identity.json)。
[标准预检摘录](../review-assets/TRIAL-JOB-01/standard-exe-preflight.json)只省略生成profile逐文件大清单，保留原summary路径/size/SHA `2365e46d5a76d87899a61e98f87982a23d9031c995be6271fb89e838fc3c7fa7`。未复制真实profile或二进制入库。

## 自主验收分层与剩余事项

[覆盖映射](../review-assets/TRIAL-JOB-01/autonomous-coverage.json)逐层列清：

| 层级 | 本轮真实证据 | 不能外推 |
| --- | --- | --- |
| Windows进程/Job | 新6case，真实子孙/无关Job/错误与关闭 | GUI流程或产品自然退出 |
| 源码加密loopback TCP | 五子棋/四子棋终局→房间复位→再开；游戏列表/建房加入/观战/非法动作/离开；公聊/私聊广播 | 编译客户端完整对局或LAN |
| Tk组件 | 房间图片GC/刷新/重建、DPI布局等原回归通过 | OS鼠标键盘完整大厅或其它真实DPI |
| 实际EXE | 正式CLI显式建库/启动、HTTP200、双TCP登录、映像存活与4Job清理 | 完整大厅/邀请接受/对局/返回聊天/红退出 |

完整原生GUI、客户端/服务自然退出、物理LAN/多机/其它Windows/DPI、硬件/完整STT模型能力仍NOT_RUN；Vosk/模型未随原包，不假放行R3/M1/R1/发布。用户不便人工验收，不要求用户代为操作，工具缺口只影响这些明确步骤。
当前旗舰Tk组件raw仍有 `11` 处invalid command name/after诊断，旧full原raw亦有；测试6P不当干净销毁/自然退出证据，本任务不改UI。下一自主候选是同环境对照诊断该销毁回调并仅修明确小缺陷，可在真实组件层推进；只建议，不在本轮新增执行Task。

## 审查、交付与恢复

gate_review独立预审/最终测试绑定/领域/正式EXE及完整207原件/公开历史/输入/资料终审均0 MUST。主控据此记录AI_ACCEPTED_JOB_ONLY，仅默认owned Job预检/清理和本批资料；不是用户/Pro、完整R3或发布接受。冻结源保持，不再重测。
用户已授权质量达标正常push/merge，集成前fetch检查新改动与保护/required checks，不强推/绕过、不删开发分支、不发布；无可见CI不能记CI PASS。最终资料leaf/远端SHA在Git与本轮回执记录。
恢复：指挥中心本Task→Task/本Review→Git/实际进程→上述原summary及公开SHA；full/EXE运行结束后不重复启动。达到本Task有限终点停止，不恢复旧Goal、不扩大功能，R3GUI未测单独保留。

## 远端交付阻碍（最终检查点）

源码975c09b和资料1e42b7d已本地提交。普通push到origin refs/heads/fix/trial-owned-job-20261021在进程创建前被自动审批拒绝：认为本批40个新资料文件及本地构建/运行日志、绝对路径元数据的GitHub披露授权不够明确。
补充对最终42个Git blob逐项审计：549处绝对路径全部在用户已授权D:/project/321_FISH内，无越界/遍历、个人Users路径/姓名/私钥/token或二进制/实际runtime文件；标准预检只公开新合成profile根和数量，不含prefs/audit正文。
据新证据仅重试同一普通push一次，自动审批再次拒绝，并明确即使无秘密/个人路径/二进制，仍要求对这42个源码/测试/治理证据与日志的具体外部披露明确授权。停止该动作，不换工具或PR/API绕过；尚未push/设置upstream/合并。
拒绝后ls-remote确认main仍ade446e639713297774fea3e7898f8dbb523a4ac，目标分支不存在；本地源/测试/门禁/独立接受不受影响。需要用户明确同意把此42文件（含合成测试日志和项目绝对路径元数据）公开推送至https://github.com/mixmixla/321_FISH.git，然后再依既有质量条件集成。最终阻碍记录leaf见本地Git。

## 后续集成回执（2026-10-21）

用户随后具体批准该42文件公开推送和合并。此前被拒动作确认未执行，据新授权仅重试同一普通push一次并成功；未扩大8f1595d提交树。fetch核main未变、无保护/required checks/rulesets后正常FF集成，ls-remote核main与fix/trial-owned-job-20261021均为8f1595d77da3b2bfd531a1c535930de7b6bbf39f。GitHub后续读取亦确认main同SHA，statuses/check-runs空，不称CI PASS。上节PUSH_APPROVAL_BLOCKED为当时历史，现已解除；未强推/删分支/发布。后续Tk任务在新分支单独进行，不混入原42文件许可。
