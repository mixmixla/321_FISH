# HISTORY-UID-ISOLATION-01 r1 · v2.1

**IMPLEMENTED / FINAL_FULL_02_PASSED / FINAL_INDEPENDENT_REVIEW_0_MUST / AI_ACCEPTED_HISTORY_UID_ISOLATION_ONLY / PUBLIC_REVIEW_0_MUST / NEW_OBJECT_AUDIT_0_MUST / MERGED_MAIN / REMOTE_VERIFIED**。用户已批准稳定UID隔离、更名连续、旧昵称历史保留且不自动归属。[冻结Task](../task-packages/HISTORY-UID-ISOLATION-01.md) / [完整脱敏指纹与阶段后验](../review-assets/HISTORY-UID-ISOLATION-20261023/evidence.json)。基线main293cc526ea2c49a4c5ca4520a09ca73aa5733a01，root唯一集成/组合验证；A独立树实现，B独立只读设计、代码与原件审。实际Sol/FAST运行回执不可见，不冒称已核。

## 结果与边界

新历史/voice/vmemo/贴纸/E2EE身份仅在当前captured connection的WELCOME接受后按durable store_scope_id+正整数UID绑定，默认与显式history_dir都为`ROOT/v2/<scope>/uid-<uid>`。未认证、volatile或缺有效服务scope使用独占fresh临时bundle；旧昵称/顶层原件不读/不认领/不删除。相同Store+UID不因显示名/端点别名分裂，不新增实际改名API；不同Store同UID和同名不同UID隔离。复制整个Store复制scope，现协议不能区分克隆。

六字段pinned/muted/archived/drafts/stars/unread_marks使用新UID视图；launcher只记登录元数据，旧top/profiles/opaque stars保值，坏prefs拒写、新UID保存原子替换。Excel/quick/reminders等其他设备偏好及全局下载目录不在本批隔离范围。云恢复仅新增本地代次提交保护，不增加备份包UID/服务签名或同步功能。

显式stop/切目标/认证拒绝撤旧UID/UI状态；正常同目标断线保留已确认离线历史。完整WELCOME及captured帧提交与身份迁移串行，目标切换先关闭捕获旧socket解除同步发送阻塞；阻塞events投递及_on_event出迁移锁，主线程退休快照最多一个额外合并项，关键chat原背压保留。旧cloud/E2EE/媒体/贴纸/排队事件和Tk回调携origin代次，拒绝写入或发送到新身份。durable路径/已有媒体leaf拒reparse别名，坏key不覆盖。

## 阶段证据（首失败全部保留）

每个阶段使用独立短run-dir、单attempt；root逐原件核manifest/source snapshot、progress、测试集合、原log SHA与计数、sandbox、清理及指纹。下表摘要SHA前12位用于阅读，完整SHA/source ID/actual session/exit在脱敏JSON；原日志与合成profile仅本地。

| Run | 文件 | 结果 | 实际退出 | Summary SHA前12 |
| --- | ---: | --- | ---: | --- |
| hui23-red-01 | 1 | 3F | 1 | f3998d1bbff6 |
| hui23-green-01 | 2 | 8P | 0 | 474583a0d137 |
| hui23-green-02 | 2 | 9P | 0 | 064382e1e0ec |
| hui23-domain-01 | 2 | 48P/1F | 1 | 7ea3a1d95ca5 |
| hui23-green-03 | 3 | 44P/1F | 1 | df7a92714042 |
| hui23-green-04 | 2 | 42P | 0 | 39ec956935c2 |
| hui23-green-05 | 2 | 18P | 0 | 241cd646ed4d |
| hui23-domain-02 | 12 | 168P/3F | 1 | a27839ffb0cd |
| hui23-green-06 | 5 | 74P/1F | 1 | fba7a0fe5080 |
| hui23-green-07 | 1 | 9P | 0 | fc3f17b0126b |
| hui23-affected-final-01 | 6 | 103P/1F | 1 | f08e76077d8e |
| hui23-ui-fixture-final-01 | 1 | 11P | 0 | c75a8d348d33 |
| hui23-final-01 | 223 | 3048P/22F/20S | 1 | 6de2fab0a29b |
| hui23-contracts-final-01 | 7 | 107P | 0 | 8b53cf6eeed5 |
| hui23-final-02 | 223 | 3070P/20S | 0 | 2cea79203a4a |

原RED仅新增测试，旧498输入逐SHA同base，3F确触预认证读legacy/同名跨UID共用/同UID改显示名目录分裂，无fixture/import误差；直接dispatch seam不冒称真实认证。后续真实durable loopback接受/拒绝、服务Store关闭重开local-only marker（服务器bus无marker）、第二端localhost别名、不同Store/volatile、重启/切目标、路径/准备失败、受控旧worker及实际Tk组件已覆盖。

domain01的1F是真实本批volatile新bundle误清群重入意图，保原断言修为accepted runtime epoch+UID+原目标仅保重入意图，历史/keys仍fresh；不称baseline旧错。domain02三F对应stop后旧UID期待和旧volatile fixture密钥留存，独立确认后捕获stop前UID、单例改真实durable保持原行为断言。green03错误等待仅其他流程设置的manual_login_required，green06误用MsgList.rows，affected-final mock误拦正常STICKER_SHOP，各首原件保留，测试修正分别另记，不混用源版本或称旧失败通过。

## 首组合full失败与v2.1修订

hui23-final-01/exec76517自然actual exit1，223文件3048P22F20既有skip/841.176s，summary6de2fab0a29bc4020512ac428d21de4e4a1aad1d33054efce3236b2e01dfc10c。root13后验全true，B独立223原件一致，原full永久FAILED。

五个旧测试文件需新增接口前置兼容：四个Core私有WELCOME wrapper透传captured connection；game_client_lifecycle唯一__new__合成factory补RLock/threadlocal/localgen；kick的send mock接expected_local_generation关键字。kick两参数例原日志直接显示entered超时/cleanup assert，关键字拒绝发生于mock体前是确定性源码推导，不冒称日志直接打印TypeError。

另两文件是已批准产品语义更新，不能统称fixture：retirement_wire在set_host后应撤旧UID/名册，保先前失败发送不pop、恰两GET与零DEL/ever_del、迟到回执零复活；Stars三个launcher例改为仅元数据登录，旧top/profiles/active_profile原值保留、不生成UID归属，启用新UID视图为空，其余34 Stars保护例不动。生产源码未因这七文件再变更，全部用例/安全门或对应新批准语义保留，B独立差异0 MUST。

唯一hui23-contracts-final-01/exec25125自然exit0，七文件107P（5+6+12+6+4+37+37）/25.841s，summary8b53cf6eeed5d878fc6f4ccba04581bd80add6eb603021327ff48baa1a5c7d4e；root九后验/B七原件及501源独立0 MUST。测试输入变更不能resume旧指纹或重置终态F，必要新组合full02不属于相同输入盲重。

## 版本绑定与当前门禁

A产品c3280ec999871b9d5977a1eaf6c8edc00b23e20b接root ae63aeea5de5131f6c4f828aabd42b304774c849；七test合同68d326c2c39727e532a00c47c990cdcb6c389b99无冲突接root2c58d90ea3798cc01dd7ffc5be0d38766f91443b。A末source501/9388d7f96ab69a83f3ef46960430ff3b3bc4728cfb90f6df7bf6fe10c0164c66，与root501规范化逐字节相同，raw仅Core/local_identity/两新test四文件Git换行差。root新冻结source81c36be82a54f5663f0ea2b473884a6499040741c171a4c0115500539aa965e5，223文件。

hui23-final-02/exec28091已自然actual exit0，223文件3070P0F20既有skip/811.651s，summary SHA2cea79203a4a284cc90db0e3435bd243dd161adb0a43bc0e81f20f303a3b0dc1。root首次28后验全true：当前/冻结/快照501、223全原log/sandbox/单attempt/清理、旧221逐文件P/S计数和20既有skip不变、解释器/依赖/门禁身份、worker19规范化字节及全部首失败保存。只新增37+11通过，不增skip。

B独立复算223原件/501当前源、身份/逐文件计数、原full01/RED/选测失败保留，最终技术0 MUST。root据此仅AI_ACCEPTED本Task v2.1，不等于用户/Pro验收、整里程碑或发布。未见活动Python，无源码/依赖变化不再测试。第一full冻结/stdout/exit与所有原件保留，第二输出单列full-02-*。

公开四终稿及Task/稳定事实/技能参考已独立资料0 MUST；全部8个新可达commit/40tree/48blob共96对象及中间版本/metadata已root扫描和B独立敏感审0 MUST。fresh fetch/API确认原main仍base、protected=false/可见rulesets为空后，正常快进合并并非强制push成功。Git ls-remote与API双核main完整提交21e2ef0cf1fb19afca9655e4cb46c0ad60eb1bdb，501输入仍逐字节等full02、代码交付核验时工作树clean，原视频4759仍独立暂停。

该交付提交的check-runs/status contexts/Actions均0（aggregate pending/total0），不称CI通过。本段为纯资料交付回执，回执新增对象另审后正常推送，最终leaf以Git refs为准；无源码变化不再全量或构建。

当前及先前原件分别本工作树_tmp_gui/history-uid-isolation-20261023、原工程_tmp_gui/hui23-*；只用合成数据与临时目录。旧paused video4759保持非祖先/不继承/不诊断；原视频/路径首次失败原位保留。不上传原日志、私有prefs/聊天/凭据、用户名或二进制，不强推/改保护权限凭据/发布。不公开旧历史敏感细节、不重写共享历史或轮换部署凭据；本纯资料回执新增对象另审，保留可恢复检查点。

本批不证明可视GUI、自然退出、物理跨机器LAN、硬件、新EXE或完整R1/R3；Tk组件/协议与此前旧源码EXE包分别记录，不相互替代。
