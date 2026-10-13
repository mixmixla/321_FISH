# EXE-EXIT-01 v1.3 独立运行与公开证据终核

2026-10-13，purchase_review（GPT-6.1 Sol）。本次仅读取原始/公开资料与文件hash；未调用native API、启动应用、测试、构建或下载。旧first/recheck报告和helper预审均保留。

结论：限定当版服务自然 Ctrl+C 与其本次合成 Store 验证 **0 MUST**，支持root仅对该完成部分作技术接受；本报告不代替root登记AI_ACCEPTED，不是主GUI退出、完整游戏、发布或全项目验收。

三轮各一次：首轮FAIL/exit1/event0、第二轮FAIL/exit1/event0，原六raw及执行快照永久保留；第三runtime-final PASS/exit0。final-preflight记录的28个前轮冻结文件逐hash保持，三轮9helper执行绑定与各自预审/当前文件一致；三个unique run及fresh Store/nonce不同，没有第四run。公开11个helper快照另核，见下方。

最终sender实际PID5028，初始console0/error6，正确Attach当版server父14072；完整信号成员为5028/14072/14700，除sender外仅当版server父子且属于fresh服务Job。服务Job14072/14700/22232的完整image/birth/session均核记录，第三PID为精确SystemRoot/System32/conhost.exe；sender Job仅5028。ready/permit/result/owner observation完整成员及逐身份一致，nonce匹配，permit至唯一event约4.1695ms（TTL10秒），CTRL_C_EVENT/group0只发一次，API返回成功且sender随后detach。

associated HWND1056108的owner是14072，完整身份与fresh Job中的server父一致，hidden/exact private desktop MoyuExit-36452-2d6371ffa3；owner、Job conhost与backend分账。actual_backend_identity=UNDETERMINED，不声称确定pseudoconsole或owner等于backend。root未Attach/FreeConsole，没有全局输入/截图或GUI fallback。

自然证据均在清理前：initialize0/Job0、sender0/detach/Job0、实际onefile server父wait0/完整服务Job0、loopback2512/2513关闭，之后同合成Store inspect0/Job0。四角色before_cleanup/after_cleanup均0/Job0且无强停，forced_cleanup_count=0；未发现记录中的Job/PID残留，未另做系统进程扫描。运行子退出码未另单独wait，不能写成有独立子wait原日志；父wait0与Job0是本次直接观察证据。

实际HTTP200与owned loopback两LISTEN已核；inspect原文action=inspect/ok=true/exclusive=true/pair=valid/control phase ready/intent_count0。server raw183字节仅两监听与管理员未启用提示，**没有shutdown日志行**，不补写。最终四raw与全阶段10raw实际SHA/size均匹配。

410当前源输入与冻结manifest逐hash/size保持，source13514b5d70d6e92a39f9eadd8f20ae39562d3e80570437b26f6e4ea0a2164345；三EXE实际SHA/size保持，不重建/改源/测试/依赖，引用同源SYNC full而不重跑门禁。三preflight、各bind与新helper实际SHA链均核。

公共归档核验：10 raw全为byte-exact且索引hash/size匹配，实际empty日志为3；23 metadata只CRLF→LF、raw/public双hash及JSON结构相同；11helper快照全部含位置信息AST相同，仅空行padding规范化（9份字节同，2份launcher仅padding不同），不把其统一声称为字节相同。前两FAIL public JSON保持原状态；三preflight均已归档。

公开目录仅合成metadata、代码快照、审查文档与上述raw，没有profile/prefs/history/Store内容、binary、TLS私钥或实际账户凭据；nonce是已结束辅助许可，不是账号token。检查包含文件类型/路径边界、所有JSON敏感字段及私钥文本标志；这不是全系统I/O追踪。

主会话真实GUI退出仍BLOCKED_NATIVE_UI_UNAVAILABLE；完整一个EXE游戏/邀请/结束/再开、外机Windows、实际LAN、最终视觉/DPI未验，危险--run-visual继续禁用。仅服务自然退出部分可有限接受，第三轮后收口。

公开核验细项：

{
  "errors": [],
  "public_raw_logs": 10,
  "empty_raw_logs": 3,
  "public_metadata": 23,
  "public_helper_snapshots": 11,
  "byte_exact_helpers": 9,
  "ast_positions_equal_helpers": 11,
  "public_file_count": 53,
  "private_material_found": false
}
