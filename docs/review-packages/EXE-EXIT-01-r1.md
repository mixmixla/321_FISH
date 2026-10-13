# EXE-EXIT-01 r1：当版服务自然 Ctrl+C 有限验收

状态：AI_ACCEPTED_SERVICE_EXIT_ONLY / MAIN_GUI_BLOCKED / COMPLETE_GAME_UNVERIFIED。Task v1.3/base f71438aedb229a509f741a4823bfc84ab552e5a0；产物绑定9803303/受测代码6c8bdf7/source13514b5d…/410。生产/测试/依赖/三EXE未改，无重建，引用SYNC唯一2441P0F20原opt-in full。v1.1只冻合成原日志窄出版规则；v1.2只改变stdlib sender为该.venv核定base3.14.5/hardpin/-E -S -B，绕过flags0 redirector；v1.3纠正associated HWND身份与backend分账，window_owner_identity必须fresh Job/逐identity/exact server或conhost，backend UNDETERMINED。原初始无console/完整信号归属/自然退出断言不放宽；本阶段最多3runs，最终后不继续递归复核。

本 Task 原运行 service_status=PASS，exit=0；完整结果[summary](../review-assets/EXE-EXIT-01/summary.json)/[service](../review-assets/EXE-EXIT-01/service-ctrl-c.json)。所有本批Job已空，强停清理数=0。辅助程序、静态审查、原日志及固定源/三binary前后hash均分开记录，不把API调用返回成功当自然退出。初始化只本次合成Store前置，不重复计旧入口用例。

首轮[FAIL/exit1](../review-assets/EXE-EXIT-01/first/summary.json)与[原sender结果](../review-assets/EXE-EXIT-01/first/sender-result.json)永久保留：initial console1/error0、attached=false/event0、没有ready/permit，实际服务TCP/HTTP200但仅owned Job清理124/最终Job0。这不是产品Ctrl+C失败或自然通过。新run/profile/nonce唯一有限复核，不重跑旧CLI/compiled-demo，不覆盖首轮原始证据。

第二轮[FAIL/exit1](../review-assets/EXE-EXIT-01/recheck/summary.json)/[实际associated HWND](../review-assets/EXE-EXIT-01/recheck/sender-ready.json)保留：无初始console/正确Attach/完整sender+两server成员通过，但observer要求HWND owner为conhost而实际为已核server父，在许可前拒绝；无permit/result/event，sender与service仅owned清理124/最终Job0。旧host_identity字段只是窗口owner的实际image/birth，不是已证明backend；第三Job PID也无已核image，不补写为conhost。最后仅metadata修订、唯一fresh runtime-final，禁止把第二轮FAIL改成自然通过。

本次只 fresh profile/Store、随机loopback、专用隐藏private console；server先挂ownedJob再resume，sender独立DETACHED/ownJob，不继承Jobhandle。完整动态console/Job PID集合、image/出生时间、nonceTTL和发送前复查通过才一次CTRL_C_EVENT group0。root不attach/detach，consolehost只读记录；不关闭console窗、不操作用户控制台。sender自然返回0/detach/Job0，实际onefile父wait0+完整服务Job0且两端口关闭，再本次Store inspect自然0/Job0，以上都在强停/close之前记录。

最终实际采集是onefile父进程wait exit0与完整Job0，运行子退出码没有另独立wait日志；固定PyInstaller6.22.3的父传播子退出码合同另有此前源码审查支持。server raw只有监听/管理员未启用提示，没有shutdown日志行，不虚构。inspect raw实际ok=true/exclusive=true/pair=valid/control phase ready/intents0。退出前后只元数据，不把Store内容公开。

原日志.txt保持Git blob逐字节；JSON元数据仅CRLF→LF出版且结构完全相同，raw/public两个hash与[出版对照](../review-assets/EXE-EXIT-01/metadata-publication.json)分开，不声称JSON字节相同。

当前原生ComputerUse不可用，main自绘退出控件无法安全识别，**BLOCKED_NATIVE_UI_UNAVAILABLE**，没有自制截图/鼠标fallback、注入quit_app、强停伪装自然通过。旧EXE-LOCAL主WM_CLOSE只收起/最终124清理与首轮观察器FAIL永久保留，本Task不会覆盖。

独立[绑定只读核验](../review-assets/EXE-EXIT-01/binding-review.md)，[helper首轮预审](../review-assets/EXE-EXIT-01/helper-review.md)，[复核helper预审](../review-assets/EXE-EXIT-01/helper-recheck-review.md)，[metadata最终预审](../review-assets/EXE-EXIT-01/helper-final-review.md)，[首轮终核](../review-assets/EXE-EXIT-01/first-runtime-review.md)，[第二轮终核](../review-assets/EXE-EXIT-01/recheck-runtime-review.md)，[最终原运行终核](../review-assets/EXE-EXIT-01/runtime-review.md)。三轮原日志[byte/hash索引](../review-assets/EXE-EXIT-01/raw-log-index.json)，执行辅助程序公开快照仅去空行padding、含位置AST相同[出版证明](../review-assets/EXE-EXIT-01/helper-publication.json)。nonce是已结束测试辅助许可，不是实际账户凭据；没有profile/prefs/Store/TLSkey/真实数据入库。

技术接受只可覆盖实际服务自然Ctrl+C；不是用户/Pro验收或整个R1/发布完成。完整一个游戏/邀请/结束/再开、主GUI自然退出、外机Windows/真实LAN/最终视觉/DPI仍未验，危险--run-visual禁用。后继父线程冻结一个游戏，Kalah `_sow`仅非extra-turn路径check-win的静态风险供选题核查；未在本Task复现或改规则。

允许普通任务branch资料commit/push；PR403不重试，无新PR、不main push/merge/Release。原c864234/dirty/index/1143保护，后续以实际Git交付回执为准。自然阶段结束及时交父线程，14:30北京不新大任务、15:00前停止。

主控依独立实际helper/3轮原运行/公开出版终核0 MUST与固定产物证据作[有限技术接受](../review-assets/EXE-EXIT-01/adoption.json)，仅以上服务Ctrl+C退出；前两FAIL保留，非用户/Pro或完整游戏/发布接受。所有本批应用Job已空，无新测试/构建。普通Task资料提交/推送结果见Git与最终回执。
