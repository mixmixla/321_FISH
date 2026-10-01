# GAME-LIFECYCLE-01 — 现有游戏公共结束与再开

版本v1，2026-10-01；范围来自 [BATCH-R1](BATCH-R1.md)，状态只见 [指挥中心](../AI_COMMAND_CENTER.md)。
会话多端/最后端边界已明确；实际server断线/结束整合依赖SESSION-02阶段审查。
允许先并行独立A阶段：仅RoomManager.start状态检查与纯房间回归，不改变API/断线/leave语义。
已由主控明确所有权并置READY，完成A阶段不代表整个游戏任务通过。

目标：现有游戏正常结束后，公共房间状态/现有结果展示准确，结束处理只发生一次，
玩家通过现有房主/准备/开局入口能再开；退出/重入不残留旧局状态或误伤其它同UID端。
以少量已有可终局游戏验证公共路径，不新增旗舰游戏/美术、不改各游戏规则或排行/奖励产品规则。

候选范围：`games_pkg/rooms.py`公共状态、server房间/游戏结束桥接、桌面/Web通用房间controls，
以及既有房间/服务器游戏回归。优先复用已有消息和动作；需要破坏兼容的协议或结算规则变化时记录具体决定。
不同时让两实现者改server.py/client.py/web.py，不把47款全面玩法/UI审查扩到本任务。

只读核验已确认待具体实现的问题：进行中手动leave不调用player_left，disconnect丢返回消息/终局检查，
start允许PLAYING/ENDED覆盖游戏，finish/timer无单轮幂等保护，结束/复位不刷新公共列表，桌面离开后本地房间状态残留。
冻结不变量：仅CREATED可start；手动leave与最后UID端disconnect使用一致善后，player_left最多一次；
action/tick/player_left终局一次finish/audit/reset；旧Timer不能影响新轮，reset同步state/list并保留玩家以房主开始下一轮。
现有协议没有GAME_READY，本批不新增准备协议，保留“满足人数由房主开始”。
公共确定性探针选现有TicTacToe，掉线致终局选已有Kalah；保持它们的规则/奖励语义，不改47款规则。
精确写入函数与UI交互矩阵在SESSION共享边界清晰后置READY，不允许调查阶段提前多写核心文件。
动态终局探针已证实Timer构造传daemon关键字会TypeError，导致自动复位无法安排；本Task须修正实际Timer生命周期。

## 写入阶段与所有权

- A阶段：主控唯一写`games_pkg/rooms.py:RoomManager.start`和新`tests/test_game_lifecycle.py`的状态守卫回归；
  与SESSION02的server.unregister可并行，接口/其他RoomManager方法不改。原红→最小guard→修绿，独立审查。
- B阶段：SESSION02阶段满足后主控再分配server公共结束/Timer/leave与RoomManager善后及客户端同步具体函数，
  不让多实现者写同核心；A阶段回归继续保留。此阶段与最终UI/领域/完整批次全量完成后才可给游戏任务最终结论。
- 已核验结束状态`_send_room_state`当前丢弃public snapshot，只有文字事件；须在本范围内保留实际终局公共结果以正确展示，
  不改私密分发/奖励/排名规则。实际消息字段沿用现有state/room/events。

B阶段在SESSION02阶段通过后冻结：

- `file_auth_impl`唯一写`games_pkg/rooms.py`公共leave/disconnect detail兼容桥接、
  `server.py`游戏state/finish/reset/leave/action/tick结束桥接及`_disconnect_rooms_of`整合，
  新`tests/test_server_game_lifecycle.py`及必要Room回归。保留A start守卫和S2 UID重登/通知保护。
- 主控唯一写`client_core.py`game_state离房确认/私密状态清理，必要`client.py`窗口关闭同步，
  `web.py`仅game_state ACK/公共房间controls及客户端生命周期回归。后端不写这些客户端文件。
- 复用已有game_state对离开者确认退出：当前room成员不含其UID，空房room=None；
  客户端仅对匹配当前room_id的退出确认清本地room/public/private/events，不清其它当前房间，不新MsgType。
- leave bool/on_disconnect room-id list接口保留，内部detail承接player_left消息与native ended，观战离开不调用player_left。
- 不添加TicTacToe离开判对手胜等新规则，不修改注册游戏规则类。Kalah既有player_left终局按原结果；
  无native结果而人数不足以继续的房间由公共生命周期中止，不指定winner、不计新奖励，保留公共棋盘与中止事件再回大厅。
- 同UID存活端接收该UID应有的公开/自己私密状态，保持权限和私密边界，Hub→Room锁序、锁外发送。
- 真实Timer构造、重复finish去重、当前room/round/gs身份守卫、结束/复位列表同步、终局公开snapshot、
  离开/重入UI需全链路验证，A纯Room测试不能代替。

验收：终局→结算可见→新局状态重建，多次tick/重复结束不重复处理；非法角色开局不改状态；
房主/准备/玩家数量检查保留，退出重入与多端断线隔离正确；公共UI入口能触发合法动作。
只有规则测试不能证明UI可达，改UI时另做隔离真实交互；未覆盖真实设备/全部游戏必须标明。
冻结精确缺口/边界后实现，专项/领域、独立审查和最终批次全量，证据见 [Review](../review-packages/GAME-LIFECYCLE-01-r1.md)。
