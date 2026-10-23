# R3-UID-BUILD-01 v1 — UID隔离后的本地试用包刷新

2026-10-23 READY_BUILD。基线main `1e3c96af48552feeddba38b7071a31670c6f388a` 已Git/API核实，root唯一构建/运行/资料/集成，flagship_scout只读独立审查。沿用户持续开发与本次明确本地包刷新授权；Sol+FAST偏好沿用，实际服务回执不可见。工作树history-uid-integration-20261023，分支feature/r3-uid-build-20261023。

## 有限范围与验收

只将已验收UID隔离main刷新成本地三EXE、精确七文件包。沿用源码full hui23-final-02：223文件3070P0F20既有skip/actual exit0，summary SHA `2cea79203a4a284cc90db0e3435bd243dd161adb0a43bc0e81f20f303a3b0dc1`；当前501输入/source `81c36be82a54f5663f0ea2b473884a6499040741c171a4c0115500539aa965e5` 须与冻结/该full逐字节一致。不改产品/测试/工具/依赖/协议，不重复源码full。

1. 现有local_trial.py build --source-dir本Git工作树 --output-root原工程_tmp_gui/uib23，全新白名单副本。旧r3m23/bundle-main175777d-pending-gui七文件逐SHA保留不覆盖。沿现有OS-only控制器在同副本编译StartTrial；独立预审控制器只改新路径/标签，无pytest注入。记录实际命令、自然exit、原log与产物SHA，501输入除正常生成两spec外逐字节不变；核三入口嵌入code与角色必需PYZ模块，含client的local_identity。
2. 新bundle-main1e3c96a-pending-gui精确七文件：StartTrial.exe、dist/server.exe、dist/client.exe、LICENSE、README.md、VERIFICATION.json、SHA256SUMS.txt。校验单覆盖另六文件；执行前冻结整包七文件SHA，执行后再核。包内验证状态保持pending，结果另存包外，不修改已验候选。二进制及原始证据仅本地ignored，不上传/压缩/发布。
3. 入口仅实际--help与demo --dry-run，fresh合成profile/private desktop/owned Job，核实际exit0和Job after0/close成功；不是完整compiled demo。
4. 唯一现有local_trial.py run --source-dir必须指新七文件包，不能用build副本或exe override替代。默认strict三合成profile/loopback/private desktop；核initialize自然root0、HTTP200、双实际client.exe合成登录/映像/存活、默认wire双聊及gomoku/connect4终局→重开→离房/双peer清理。四Job active_after0/close成功、strict before/after清单无错误且同盘一致、包SHA不变。
5. 不改harness即利用本次已有合成profile原件确认UID目录：读取本次server Store元数据及仅本次账号映射，与双client profile中history/v2/<store_scope_id>/uid-N核对；uid_profiles不作为必有门（登录绑定本身可只在内存），若存在则只含该profile当前UID，不认领legacy。只核本次未生成旧昵称直达目录，不据此证明全部旧读路径。以strict完整inventory与本次合成login audit正整数UID核对双client各自UID目录，同一合法scope、两UID不同且彼此无对方账号目录；只核路径/存在，不读取正文或key，不公开scope值/完整清单。若run成功但UID目录门不成立，单列失败/不接受EXE-UID结论，保留首次证据，不扩harness或通过新GUI接口/猜测补造证明。UID更名/切账号/失败恢复完整合同已有源码full，本批不冒称EXE完整交互已覆盖。
6. 任一首次失败保留且停止相应验收，先分类不retry-to-green；长构建/运行前后更新中心/本地回执，只有实际启动回执后称运行中。构建/预检结束独立审原件与脱敏摘要，仅有限AI_ACCEPTED_UID_BUILD_PREFLIGHT_ONLY，不是用户/Pro或完整R1/R3/发布验收。
7. 公开只Task、Review、脱敏evidence、中心与其生成投影五文件。全部新可达Git对象/metadata审计及独立复核0后，沿用户明确正常main直接合并推送授权，不PR/强推/改保护凭据权限/历史重写；Git/API核远端，CI无记录不称通过。原视频4759暂停且非祖先，源码模块不继承、不诊断。无真实数据/摄像头麦克风/系统设置/网络安全改动；可视GUI、自然应用退出、物理LAN、异机/DPI、真实硬件/STT仍未验。

## 恢复

原件本工作树_tmp_gui/r3-uid-build-20261023，构建/包/正式运行原工程_tmp_gui/uib23。当前冻结前无活动Python，旧包保留，源码501精确等full。先独立设计/控制器预审，再构建；不并发运行或重建已成功操作。完成后报告真实依赖，不扩下一任务。
