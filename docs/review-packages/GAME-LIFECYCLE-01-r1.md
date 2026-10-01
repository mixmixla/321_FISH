# GAME-LIFECYCLE-01 Review r1

对应 [Task](../task-packages/GAME-LIFECYCLE-01.md)，状态只见 [指挥中心](../AI_COMMAND_CENTER.md)。
最终当前交付统一绑定[BATCH-R1门禁包](BATCH-R1-r1.md)：300项内容ID64b829…，108文件1335/0/2；
新GameA5/后端12/Core12均通过，最终版本Tk13/Web Node20/IAB实测完成，最终独立终审可接受，无必须项。
本包保留调查、原红、整改与阶段证据；最终批次全量与独立验收均完成。
已核验公共CREATED/PLAYING/ENDED状态与3秒复位，现有TicTacToe桌面/Web入口存在，无GAME_READY协议。
缺口：leave未调用player_left、断线返回/终局丢失、start未检查房间状态、finish/reset无幂等/旧Timer保护、
结束/复位未广播房间列表、桌面离开后本地状态未清；同UID每端触发rooms.disconnect归SESSION-02先修。
调查代理只读，没有源码/测试写入，不能将这些静态线索冒称动态复现或验收结论。

主控真实Hub.dispatch井字棋五步胜局探针触发 `_finish_game` 后TypeError：
`threading.Timer(..., daemon=True)`不是当前Python3.14.5 Timer构造支持的参数，房间已ENDED但无法安排复位。
真实签名 `(interval, function, args=None, kwargs=None)`，证据 `baseline-probes/result.json` / `game-end-traceback.txt`。
这属于已有公共结束/复位范围的必要修复，不改变游戏规则或协议。

## 独立A阶段

主控仅在RoomManager.start添加CREATED状态守卫，Owner/人数/规则/接口保持，
未改leave/on_disconnect，与SESSION02 server写入边界独立。Room代码hash
`dc392ca9a5296e3d74d0db6218d34d7cb5431b566f2a15b66c94eb2c227cffdc`；
新test_game_lifecycle hash `fab76f989147a09ae4009dbaa6947abcbe7be15d6d58d07cb4f27f6f6a27a1b6`。
原代码真实2 failed/3 passed（playing/ended重复start未拒绝），修复5 passed；
rooms8、w3_rooms7，总20 passed、0失败、逐文件真实exit0，原始 `game-start-original/` / `game-start-green/`。
独立只读审查接受A阶段；这些纯Room测试不证明Hub Timer/终局/公开结果或桌面/Web交互已完成，B阶段仍需实施。
保持已有规则、结算/奖励语义；当前缺口、精确所有权、原红/修绿、真实UI与独立审查按证据记录。

## GameB与客户端阶段

后端复用leave/on_disconnect兼容API，以detail承接既有player_left结果；观战离开不调用player_left，
Kalah保持native胜者，无native结果且人数不足时公共层中止，不指定winner/奖励。
ENDED保留公开snapshot，仅PLAYING分发本人private；finish/3秒reset去重并刷新state/list；
同UID状态及退出ACK发给全部存活Session，发送在锁外。

初始GameB原红4 failed/1 passed，修后5 passed；独立审查发现旧Timer/tick缺gs/round守卫、
ACK只到发起Session，必须整改。追加8项矩阵在旧7f28/adc源为4 failed/4 passed，修后8 passed；
再补旧tick成为9项，609315/DBE22/32CD候选9 passed。第9项没有同版原红，不把8项红冒称9项。
第二轮审查还发现身份检查到payload snapshot之间可能混合新轮state与旧事件，正在关闭此窗口；
原始各轮`game/original*`、`after*`、`domain*`保留，当前不能提前给后端最终结论。

客户端新Core测试同版2bfadbe3原红7 failed/1 passed，修后8 passed；连带client_core33通过。
匹配房间的非成员/空房ACK清room/public/private/events，无关房间不清；离房旧帧fence，显式join/spectate解除。
ENDED保留public并清private，新round/CREATED清本轮记录；桌面非playing操作按钮移除，Canvas发送也校验状态。
Web在发join/spectate前解除fence，允许SSE先于HTTP，失败恢复；终局面板保留公开棋盘并inert/禁操作。

最新阶段客户端版本：client `2dc4790134dea7b29b53a0e3dfdbbf7083e768dd7c8403948e72fe553a481409`、
Core `cec4120b3589fd95454839180e13576c8c175908933ebfd1ab202499df2af731`、
Web `9880d127e941cae447aeb568902a6aeb41d66a78dfa28a2a3dd732c783af303c`。
真实Tk GameWindow/BoardFocusWindow与Canvas事件13项全true：公开终局/按钮移除/不发动作、
复位可开始、新轮同长度日志更新、ACK清模型并隐藏双窗、显式重入恢复。只用合成core，不读写prefs/真实历史。
Node执行实际生产SSE/API/panel函数20项全true：匹配/无关ACK、迟到私密帧、player/spectator、
join/spectate消息先于HTTP、网络/业务失败fence恢复、终局公开/禁操作、复位及新轮日志/private。
最新Web的SESSION01 Node12项仍全true。证据`game-tk/result.json`、`game-js/result.json`、`session01/js-runtime-result.json`。

真实IAB与隔离合成Hub（Web9880/server609315/roomsDBE22）走通：大厅建井字棋、第二玩家加入、
房主开局、网页三次落子/合成对手两次落子、真实胜局、公开最终棋盘及winner可见，main inert，
3秒自动复位、同房再开9格全空且无旧胜局日志、离房ACK移除面板、等待房间卡片显式重入无旧私密状态。
随后Web logout返回登录并移除面板；服务器证明同UID TCP仍活/在线、Web sessions与token均0。
截图`ui/game-ended.png`；各步DOM/AX与加载源码hash保存`ui/game-*-dom.json`/`game-after-logout-server.json`。
这是609315后端版本的阶段UI证据，后续snapshot守卫候选需复核，不冒称最终代码已完整UI通过。
临时IAB tab已关闭，UI进程98251权威exit0，未启用设备或真实用户数据。

领域补测：client-session-extra四个实际文件61 passed；第五个误写test_p0_web.py导致exit4/no tests，
该命令失败保留、不得计为通过/应用断言失败。正确test_p0_web_security9/admin_groups_web8/r47 16/r49 15/rooms8/server_games4，
六文件60 passed、全部exit0；证据`web-security-corrected/`，进程54581已结束。

## 最终候选补正

payload身份窗口已关闭：在Room锁内验证expected gs/round/status再构造snapshot，
action/tick/finish/reset/leave/disconnect传对应身份；同UID ACK单端发送异常不阻断其它端。
同最终12项回归原红3 failed/9 passed，修后12 passed；A5/r49 15/multisession5绿。
最终server `3b992ed5a10bca846a371e826691e9229b6644fd00224bfce9aaadd0c38b174e`，
rooms `dbe22e05a7e8e0c633091f0a5aeb0af24cb233174d2e9d2ce8fd3caf06f352db`，
server新测试 `305e5fdc48fd2ff0f64763d902380a1e8103b852c4cb9afccfb384507ef34c4d`。

主控追加Core发送返回前收帧与发送失败回归：同最终12项在CEC旧候选2 failed/10 passed，
修后12 passed + client_core33，总45passed，真实exit0，进程67432已结束。
`_game_reentry`在发帧前解除fence，发送失败恢复，避免接收线程抢先回帧而丢掉重入状态。
独立审查修正前次误读“Core已发送前清fence”的结论，不沿用错误判断；最新Core
`aa2c724798d9ae6256783299e0655ea138d69b3162d850802843ad640888f116`、
客户端新测试 `5b77a708e9e461977d9a865088554f3d0fffd13e15a8e1e26bcac76e13438836`，Tk13重新验证全true。
原始`game-client-send-original/`、`game-client-send-green/`及旧Core副本保持。
最新后端/Core独立阶段审查无未关闭功能性必须项；真实browser版本绑定与full仍作为批次最后验证。

最终server3b99/Web9880/roomsDBE真实浏览器已复核同完整TTT链路：终局public与inert、
真实3秒reset、再开9格空、leave ACK移除面板、同房重入无旧private，最终截图与DOM已覆盖为当前版。
第一次最终退出观察实际只点击到模态背景关闭面板，未触发头部logout；其main仍flex/活token证据
保存在`ui/final-overlay-close/`，不计为退出通过。随后同源码另起隔离页，确认真实logout登录画面后再关页，
服务器证据TCP active/UID online均true、web_sessions/token_count均0；两次验证加载源码hash相同。
原609315全链证据单独保留`ui/game-stage609315/`。最终隔离服务83543/34774均exit0、临时tab全部关闭。
