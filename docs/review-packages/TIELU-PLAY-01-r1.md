# TIELU-PLAY-01 v1 · 本地试玩审查

**IMPLEMENTED / AI_ACCEPTED_LOCAL_PLAY_ONLY / STOPPED**。2026-11-06（Asia/Shanghai），
任务见 [Task](../task-packages/TIELU-PLAY-01.md)。base/HEAD `de4031e1937665b34d8d5f724c0956d68eb8528d`，
`feature/tielu-tickets-20261106`，独立开发目录 `D:/Project/321_FISH/_tmp_gui/tielu-play-20261106`，入场 clean，交付 dirty。
未提交、推送、合并、构建或发布；父目录旧工作只读保留，后续 Git 由父聊天评审处理。

## 结果

- 本人起手/新抽目标票显示城市、分值与实时连通状态；抽票公共事件仅显示抽票动作。
- 达标后补回合不受线路耗尽影响，最后一位确实行动后才结算；摸牌依牌库而非剩余线路校验。
- 两端结束表按玩家显示线路分、票证加/扣分、最终总分；同分仍按座次首人胜。
  铁路结束画面保留30秒，其它游戏3秒规则不变。桌面迟到私有帧触发重绘；地图底色确保城市名可读。
- 写入边界：games_pkg/tielu.py、client_gameui.py、web.py、client.py的铁路私有帧重绘、server.py的铁路停留时间、
  两个聚焦测试与本批资料。没有通用框架或其它游戏修复。

## 验证与原件

全部命令在上述开发目录、pwsh 7 下执行，解释器 `D:/Project/321_FISH/.venv/Scripts/python.exe`（3.14.5）。
原件仅合成数据，存 ignored `_tmp_gui/tielu-play/`；本报告保存可接续结论，不依赖日志猜状态。

1. `run.py test-all tests/test_tielu_play.py tests/test_tielu_click.py tests/test_batch4b_rules.py tests/test_games_euro.py tests/test_rule_gaps_b.py tests/test_round_flow.py tests/test_rooms.py tests/test_server_games.py --label tielu-play --run-dir _tmp_gui/tielu-play/gate`
   → 8文件 **95 passed / 0 failed / 0 skipped / exit0**。之后仅补绘制/私有帧回归与地图可读性。
2. 最终 `run.py test-all tests/test_tielu_play.py tests/test_tielu_click.py tests/test_server_games.py tests/test_client_core.py --label tielu-final --run-dir _tmp_gui/tielu-play/final-gate`
   → 4文件 **54 passed / 0 failed / 0 skipped / exit0**。其余未变规则领域引用首轮结果，不重复计算测试数。
   最终门禁 source_content_id `dcdc8560855cb46527e8d82ed8d07ad6c9a1ef7337a86e10c7819d858ef73564`。
3. 四人案例：只读利用父目录 UPSTREAM-REVIEW-20261030 的初始发牌/摸牌计划/79步完整合法序列，
   聚焦回归每步核每色总量12。玩家2拿最后线路后 turn=3；玩家3行动后 turn=4、仍未结束；
   玩家4分别用摸牌/抽目标/跳过三分支完成最终一手，才结束。本用例仅合成合法夹具，不声称自然随机发牌。
4. 真实桌面 GameWindow/BoardFocusWindow + Hub/TCP/ClientCore 与实际 Web PAGE/HTTP/SSE，两名合成玩家、固定自然 seed79。
   桌面实际点河城→雾谷，目标即显示已连通；网页抽目标得到山城→沙堡2分，公共事件没有泄漏；
   最终版另实际点击Web SVG港口→河城，认领成功。中间普通回合由后台合法动作推进，未改分或跳 turn。
   最后一轮Web玩家真实摸2张结束：两端同为甲 **10+2−3=9**，乙 **2+0−7=−5**，甲冠军。
   `ui/observations.json` 最后一项 ended 且桌面实际Canvas文本匹配；`web-result-final.jpg` 保存实际结束画面。
   第一局还实际看过480×400最小专注窗：起手目标、已连通和逐人结束表均可读（该局乙未认领，为−7分）。
5. 用户告知在使用电脑后立即停止CUA/前台操作；从后台关闭自有两个测试Core/窗口/监听，session55802自然exit0。
   之后仅后台14步合法两人局验证：结束3.51秒后仍ENDED，30.06秒自动回CREATED、gs清空，exit0。
   见 `background/result.json`。无前台输入，也未关闭其它应用。一次原生Raise超时仅为界面工具限制，
   最终网页结算图已保存；最终桌面版本以Canvas输出和前一局真实结束窗共同佐证，不伪称超时后的截屏成功。

最终七个源码/测试文件内容ID `d0f9074f1f90de091b73ba3f305a4fa997eff29cb59988e9b572e62dc8867f63`，
清单见 `candidate.json`；门禁、首局与最终局原件分别保留，所有测试自然结束。
独立只读 `tielu_review` 从Task/实际diff/原件复核，代码与试玩范围0 MUST；指出资料未更新的收尾项已在本次补齐。
主控依此记录有限本地 AI_ACCEPTED，不代表用户/Pro验收、应用全量、EXE、物理LAN或发布验证。
本项不是合并/发布候选，未跑全量门禁；下一阶段如合并须按协作规范补全量。

## 从哪里试玩

这是源码分支，已有EXE不含本次修改。以下操作留给用户启动，本批结束不再打开前台窗口。
在上述开发目录的 pwsh 7 终端，使用同一解释器，先初始化一个全新合成服务目录（只做一次），再起服务：

```powershell
$env:MOYU_BIND_HOST='127.0.0.1'
$env:MOYU_TCP_PORT='19527'
$env:MOYU_WEB_PORT='19529'
$env:MOYU_WEB_HTTPS='0'
& D:/Project/321_FISH/.venv/Scripts/python.exe run.py server initialize-new --store-dir _tmp_gui/tielu-play/manual-server
& D:/Project/321_FISH/.venv/Scripts/python.exe run.py server open --store-dir _tmp_gui/tielu-play/manual-server
```

另开两个相同工作目录的 pwsh 7 终端，分别运行：

```powershell
& D:/Project/321_FISH/.venv/Scripts/python.exe run.py client --host 127.0.0.1 --port 19527 --nick 试玩甲
& D:/Project/321_FISH/.venv/Scripts/python.exe run.py client --host 127.0.0.1 --port 19527 --nick 试玩乙
```

桌游→铁路→创建/加入→房主开始。网页端 `http://127.0.0.1:19529` 登录合成昵称后进入同房间。
需要重启服务时只运行 open，不重复 initialize-new；端口占用则为本次手工试玩另选空闲端口。
