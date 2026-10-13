# UI-ROOM-ICON-01 v1 — 房间图标引用保持（DRAFT）

2026-10-13。仅保存后继候选，不是READY实施。用户当前优先SYNC后当版三EXE验证，
按指挥中心顺序决定是否冻结本项；不得因为发现问题自行扩大已批SYNC。

已由root与独立Sol只读确定：main52/同步6c8bdf7的_RoomCard把临时game_icon_image
直接传入tk.Label，只保持Label/_texts，没有PhotoImage强引用。factory每次返回新
ImageTk.PhotoImage且无缓存；Pillow析构会删除Tcl图像，tkguard未保留它。SYNC原样
保留该上游缺口，没有修复或实测房间图标可见。

建议冻结范围：client.py仅_RoomCard保存对应图片强引用，必要真实Tk卡片回归证明
gc后image仍在、重复卡片/销毁不误共享；必要领域含大厅卡片/新图标层。不改其它
美术/规则/网络，不启用危险截图模式，不用空断言或程序化图替代真实widget证据。
独立审查并绑定新source；后续应用候选完整门禁按协作规范，旧SYNC结果保持。
正式Task应补具体测试和来源版本后才READY；目前未修改产品、运行Tk/测试或EXE。
