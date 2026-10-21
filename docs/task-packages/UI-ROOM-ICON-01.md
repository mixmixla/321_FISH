# UI-ROOM-ICON-01 v1.1 — 房间图标生命周期窄修

2026-10-21冻结READY；执行状态以[指挥中心](../AI_COMMAND_CENTER.md)为准。
来源：用户明确批准继续本项，先真实Tk复现，再最小修复/独立审查/最终门禁，本轮结束后停止。
以已验证f693653为base，分支fix/room-icon-lifetime-20261021；保留前两项提交链：
84444b5 → 10caf9f门禁补包 → 25998f5资料 → ee487cb聊天DPI测试 → f693653资料。
本聊天唯一实现/治理，独立只读审查另安排；只本地提交，不push/PR/merge/发布。

## 已核对的范围

原v1（2026-10-13）DRAFT仅静态记录；本次授权取代旧SYNC优先顺序，冻结为有限正式任务。
当前client._RoomCard仍把临时game_icon_image直接传Label；factory返回新ImageTk.PhotoImage、
无缓存，Label只持有Tcl名字，tkguard不保留图片对象。GameWindow._refresh_rooms销毁并重建卡片。
先保留同测试RED原日志，确认Label名字尚在而实际Tcl图片已删；不能仅以静态推断当复现。

生产改动仅client.py的_RoomCard保存每个图标强引用；若回收证据要求，必要时在该类局部释放。
不改图标几何/颜色/全局缓存、共享Tk守卫、其它美术/规则/网络/依赖、前两项实现。
新增tests/test_room_icon_lifecycle.py：真实Tk与原图标factory，无fake图片/patch factory/环境skip。
覆盖已知与fallback图标对象GC/实际非透明像素/点击；重复同游戏卡片独立寿命；生产_refresh_rooms
多次刷新/状态变化/清空、容器销毁重建；root解释器重建。销毁并释放卡片后弱引用消失、Tcl图像数
返回基线，不引入无界引用缓存或泄漏。合成room/core仅是组件输入，不称完整游戏窗口流程验收。

## 验收

1. 原生产代码配最终回归先RED，原失败/输入/hash保留；修后同用例全部真实PASS、无skip。
2. 必要领域含房间卡片/设计控件/大厅外壳/前两个回归，原合法约束与点击行为保持。
3. 独立只读审查Task/diff/原raw/生命周期和释放边界；实现者不自验。
4. 冻结候选按现有run.py test-all逐文件/合成profile/loopback/私有桌面跑唯一最终全量；
   不启用visual/hardware、不弱化断言/skip，不以mock或旧full替代当前验证。
5. 更新现有Task/Review/指挥中心/投影，保存源/分支/命令/计数/活动进程/恢复入口与下一阶段建议。
6. 本轮达到终点停止，不无限新增任务；完整EXE/物理LAN/其它真实DPI/GUI自然退出未验保持未验。
