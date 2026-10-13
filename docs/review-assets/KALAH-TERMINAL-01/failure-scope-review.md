# KALAH-TERMINAL-01：唯一完整门禁失败归属复核

独立审查者：purchase_review / GPT-6.1 Sol。2026-10-13。仅只读检查 Task v1.1、实际差异、原日志及相关源码；未启动测试、服务、UI、构建或 native 调用，未修改源、测试或治理。按本项结束即停的指示，不启动对照或重试。

## 结论

完整门禁 **FULL_FAILED / NOT_AI_ACCEPTED**：169 文件、2457 PASS / 2 FAIL / 20 SKIP，exit 1，836.497 秒。两项 FAIL 必须真实保留，并阻断本项 AI_ACCEPTED。18 项新规则测试在同一 full 中 PASS，不能替代完整门禁。

本项生产差异限于 `games_pkg/kalah.py::_sow`：播子/捕获后先判终局，finished 优先、取消额外回合、胜/平局返回，不再切换 turn。两项失败的具体路径没有发现该改动的直接调用联系，相关服务、聊天 UI 和旧测试文件相对 base 未改。**这只是静态路径与差异事实，不是候选版本免责、baseline 失败、环境根因或 flaky 的证明。** 未提供同环境基线对照，失败归属仍未完全隔离。

## 版本与原证据绑定

- 工作树：`_tmp_gui/gate-collection-20261013`；base/HEAD `2fa1c9eb5fc499c1bd424b36e2093f1f5bc84b69` 加本项未提交改动。
- 原 full：`_tmp_gui/kalah-terminal-20261013/full`。
- source：`1b5fa41cf53ab7146a000a37d9116b520c1c1c92e5421b9d7f7f6df29911d561`，manifest 411 输入；未启 run_visual/run_hardware。
- 本复核对 `games_pkg/kalah.py`、新规则测试、两失败测试、`server.py`、`test_sandbox.py`、`widgets/msg_list.py`、`client.py` 共 8 文件逐 SHA256 核对：current、full/source 和三个实际 case/source_cwd 都等于 full manifest 记录。未将此有限核对表述为全 411 输入重新独立核验。
- 三个相关文件均只有 attempt 1；原 raw SHA256 与 summary 记录一致，cleanup_ok=true、artifact_error=false、unexpected_skips=[]。summary cleanup_failures=[]。

| 原 raw | SHA256 | 结果 |
|---|---|---|
| logs/test_server.attempt1.log | 044a091eb121c2b8f2efddc2184d5f341afbc8fbcb34663597153fae2b1b7682 | 1 FAIL / 60 PASS，exit 1 |
| logs/test_ux_visual_chat_regressions.attempt1.log | ee88b1e55f106b9882e9f203909f62252399b6efb3cf87f73176f10589e3fdd5 | 1 FAIL / 12 PASS，exit 1 |
| logs/test_kalah_terminal.attempt1.log | 5a4dfac28275186b0d007d43647cd764e0e66c8ef55427f045ede471e458eb82 | 18 PASS，exit 0 |

## 服务失败：实际监听启动失败，尚未登录

失败名 `test_status_default_online_in_welcome`。原 raw 明确服务 Thread-156 在 `server.py:10525` 的 `srv.bind((bind_host, port))` 抛出 PermissionError / WinError 10013。客户端随后在 `tests/test_server.py:47` 的 socket.create_connection 到 127.0.0.1:2414 抛出 ConnectionRefusedError / WinError 10061；welcome/status 断言尚未执行。

**2414 是本次动态取得的端口，并非测试固定端口常量。** `tests/test_server.py:24-40` 的 `_free_port()` 先 bind 到 127.0.0.1:0，取 getsockname 后关闭临时 socket；fixture 再启动后台 serve，固定睡眠 0.1 秒后 yield。端口释放到实际监听 bind 之间有窗口，且该 fixture 没有等待 listener 就绪或把后台启动异常传给前台。此为静态观察到的 fixture 风险，不能据此确定本次 10013 的系统原因。

`test_sandbox.py` 对 loopback 原样放行，wildcard bind 只改 host 为 loopback、保留 port；raw 的 GuardedSocket.bind 最终调用系统 bind。没有证据显示 sandbox 把端口固定为 2414。10013 不足以直接证明端口占用、保留范围、安全策略或其他具体原因，本复核未探查系统配置。

服务 `serve()` 的 bind 位于 listen、worker/game ticker 启动之前；客户端连接也位于 crypto 握手与登录发送之前。该失败路径没有 Kalah 合法动作或 `_sow` 调用。`tests/test_server.py`、`server.py`、`test_sandbox.py` 相对 base 的 git diff 为空。因此可记录“监听启动失败导致该欢迎测试未进入待测行为”，不能记录“候选无关已证明”或“历史基线失败”。

## 聊天失败：内部首行索引断言，像素结论未到达

失败名 `test_short_history_is_not_clipped_after_window_grows`。原 raw 明确 4 条合成聊天消息 load 后，窗口 geometry('1000x700')，5 次 root.update 与每次 sleep(.02)，`_cum[-1] < winfo_height()` 已通过；随后 `tests/test_ux_visual_chat_regressions.py:127` 的 `_first_visible == 0` 失败，实际为 1。之后的 `canvasy(0) <= 1` 断言未执行，raw 没有该值或截图，不能宣称已直接证明可见像素裁剪或顶部偏移。

fixture 构造合成 ClientCore/ChatWindow，history/prefs 均在 tmp_path，并禁用硬件、发现、全局热键和托盘；该 case 仅加载文本和调整聊天窗口，没有创建、启动或操作 Kalah。

`widgets/msg_list.py::_render` 根据 canvasy(0) 与累积高度计算并写 `_first_visible`，随后才可能更新 scrollregion、执行 stick-bottom 的 yview 调整；`_on_configure` 在 4112 行通过 after(120, _on_resize_flush) 延迟处理 resize。测试显式 sleep 合计约 100 ms，没有等待 resize flush 或视口状态稳定的谓词。这提供“观察时机/内部索引语义可能有关”的静态风险；实际 update 耗时未记录，不能推定 120 ms 回调必未运行，更不能据此判定 flaky 或根因。

`tests/test_ux_visual_chat_regressions.py`、`widgets/msg_list.py`、`client.py` 相对 base 的 git diff 为空。没有发现聊天断言到新 `_sow` 的直接调用路径；没有同环境基线/候选对照或足够的原始视口状态来进一步隔离。

## 停止及交付边界

可交付本项实现、18 项新测试、领域和唯一 full 的真实证据，以及以上未隔离失败说明；不能将专项 PASS 或旧版 full PASS 抵消当前 full FAIL，不能接受本项、整体源码/发布或当前产物。

旧三 EXE/ZIP 仍绑定旧 source13514b5d…/410 输入，不含本项 Kalah 改动。主 GUI 真实退出、编译桌面完整游戏流程、外机/LAN/DPI/视觉仍未验。client.py 无条件 Kalah 摘要“轮到”的已知包外边界不在本项修复中。

本次没有追加修复、重试、对照或新 Task。两项完整门禁失败及根因未隔离状态按用户当前停止要求保留。
