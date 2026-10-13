# KALAH-TERMINAL-01 r1：当版有限领域终局修复

状态：IMPLEMENTED / CODE_DOMAIN_REVIEWED / FULL_FAILED / NOT_AI_ACCEPTED / NOT_MERGE_READY。[Task v1.1](../task-packages/KALAH-TERMINAL-01.md)，base2fa1c9eb5fc499c1bd424b36e2093f1f5bc84b69 / fix/gemcity-purchase-20261013。用户13:34北京明确仅本项完成必要测试/独立审查/提交推送/清理后直接收尾；不启新Task/构建/UI/美化，旧连续推进上限已替代。main未改，原c864234/dirty/index/1143保护，root唯一规则/新tests/治理写入者。

## 问题与最小改变

原规则模块合同“任一玩家穴空即终局”，但末子落己库go_again会跳过_check_win，留下playing/current actor空穴/无法合法操作。平局finished=True且winner=None后，原分支仍换turn和输出领域“轮到”。生产仅_sow实际9+/4-：播子/捕获后沿原_check_win先判终局；finished取消有效go_again并保留last五元组其它信息，返回胜者/平局，结束不再换turn。原播子环路/跳对手库/捕获/清穴计库算法、A/B wire、非terminal额外和正常回合、其它生产/测试/依赖不改。

新tests/test_kalah_terminal.py冻结18case：6个A/B末洞入仓胜/负/平局；2捕获终局平局；4非terminal兼容；2真实RoomManager公开act；4初始48子固定随机合法动作序列（无状态注入、各最多400步）。近终局fixture明确合成48子，RoomManager测试只证明真实规则结果可给Hub，不伪称Manager自动切ENDED或发game_end/3秒再开。领域msgs无继续提示；client.py:13201无条件摘要“轮到”是包外已知静态边界，本Task不顺带改UI。

## 版本与真实门禁

生产未改时原RED唯一run：**11 FAIL / 7 PASS / 0 SKIP**，exit1/1.95秒/sourcec037425541d17e14eacfe10a1be3efa14ec542acf9a4ddc6cec9c256305d3ab3/411。10个近终局/RoomManager失败精准命中两缺口；自然seed1第49步真实公开合法act序列后A空仍playing为第11FAIL。7PASS兼容保留，不把近终局失败当工具问题。原RED raw和当时411输入完整保存，RED后test字节未改。

修复领域10文件 **150 PASS / 0 FAIL / 0 SKIP**，exit0/19.158秒/source1b5fa41cf53ab7146a000a37d9116b520c1c1c92e5421b9d7f7f6df29911d561/411。独立实际代码/Task/RED/领域0 MUST，原11raw/source/所有actualcase/singleattempt/cleanup已核。唯一完整169文件自然结束：{'passed': 2457, 'skipped': 20, 'failed': 2}，exit1/836.497秒/source1b5fa41cf53ab7146a000a37d9116b520c1c1c92e5421b9d7f7f6df29911d561/411。原20 opt-in file/count保持，未启--run-visual、未改timeout/skip，没有重试覆盖失败。

[RED原证据](../review-assets/KALAH-TERMINAL-01/red/summary.json)/[领域原证据](../review-assets/KALAH-TERMINAL-01/domain/summary.json)/[新同版full](../review-assets/KALAH-TERMINAL-01/full/summary.json)。日志为byte-exact .log.txt窄-text/-whitespace，其他源/测试/文档diff-check保持。source-inputs为公开源码路径/hash清单，无profile/prefs/history/Store/TLSkey或实际token；不把私有运行状态复制进仓库。原FAIL与旧阶段FAIL不抹掉。

[独立设计](../review-assets/KALAH-TERMINAL-01/design-review.md)/[实际代码领域审查](../review-assets/KALAH-TERMINAL-01/code-domain-review.md)/[领域证明](../review-assets/KALAH-TERMINAL-01/domain-proof.json)/[完整终核](../review-assets/KALAH-TERMINAL-01/full-final-review.md)。独立代码/领域审查范围0 MUST；完整门禁存在两个失败，不能据此作AI_ACCEPTED，当前不可合并。主控只记录本项实现和领域证据已审查，不是Pro/用户或整个R1/发布接受。

## 旧产物与最终停止

旧server/client/StartTrial三EXE、ZIP只绑定9803303f916b93be10a9e27239cd99583d007661/source13514b5d70d6e92a39f9eadd8f20ae39562d3e80570437b26f6e4ea0a2164345/410，**不包含本修复、不是最终源码测试包**。旧2441 full、EXE-LOCAL与EXE-EXIT服务自然退出有限通过仅历史。没有新构建、覆盖旧EXE/ZIP、上传或发布。

主会话真实退出工具BLOCKED不再重试；实际编译桌面完整游戏/邀请/结束/再开、外机Windows/真实LAN/125%-150%DPI/最终视觉未验。源规则测试通过不替代这些。已知client摘要仍可能“轮到”的静态包外问题保留。PR创建既有API403不重试，无新PR；普通任务branch commit/push已授权，不main push/merge/Release。

本次full旗舰GUI原log仍有Tcl after invalid-command-name诊断，该GUI源码未改，旧阶段同类别诊断保持。即便该文件pytest PASS，也不是干净窗口自然退出/最终视觉证明；原raw原样留存，不在当前停止批次扩修GUI。

本项终核/提交推送/清理后立即最终停止，不因额度重置继续新Task，不恢复旧Goal、不公司MES/PDA/真实资料/休眠设备/CP4/安全配置。最终实际commit/远端同SHA/clean与原dirty保护看Git及最终检查点。

## 完整门禁失败与有限收口

唯一完整门禁 **2457 PASS / 2 FAIL / 20 SKIP，exit1**，原失败永久保留，未重试覆盖、未改skip/timeout/断言。`test_server.py::test_status_default_online_in_welcome` 的线程在动态分配的loopback端口2414 bind发生WinError10013，随后连接WinError10061；`test_ux_visual_chat_regressions.py::test_short_history_is_not_clipped_after_window_grows` 放大窗口后 `_first_visible=1`，预期0。没有同环境干净基线对照，原因及基线归属仍未确定；不因相关源码未改而宣称历史失败。

[失败范围只读复核](../review-assets/KALAH-TERMINAL-01/failure-scope-review.md)/[收口决定](../review-assets/KALAH-TERMINAL-01/closure.json) 明确 FULL_FAILED、NOT_AI_ACCEPTED、NOT_MERGE_READY。用户已要求当前Kalah结束即停，两个失败在冻结规则差异之外需要另行获准处理，本次不扩大修复，不启动下一Task、重跑全量或构建。原180 raw、411输入和独立原证据终核后仅提交任务分支普通推送，随后清理与最终停止。
