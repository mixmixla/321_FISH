# -*- coding: utf-8 -*-
"""R31B（消息多选）冒烟：
- MsgList 级：进入/勾选切换/退出、系统行不可选、回调计数
- 覆盖层点击切换（stipple 命中块）
- Client 级：选择栏显隐/计数、多选转发、多选删除（桩核心记录调用）
"""
import socket
import threading
import time
from dataclasses import replace

import tkinter as tk

from config import CFG
from server import Hub, serve as serve_tcp
from client_core import ClientCore
from client import ChatWindow


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    cfg = replace(CFG, audit_dir="_tmp_gui/audit")
    hub = Hub(cfg=cfg, audit_dir="_tmp_gui/audit")
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)

    core = ClientCore(host="127.0.0.1", port=port, nick="多选冒烟")
    app = ChatWindow(core)
    core.start()
    deadline = time.time() + 6
    while not core.connected and time.time() < deadline:
        app.root.update()
        time.sleep(0.03)

    def pump(secs: float):
        t = time.time() + secs
        while time.time() < t:
            app.root.update()
            time.sleep(0.02)

    ok = True
    results = []

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    try:
        pump(0.6)
        # 灌入 8 条历史消息
        for i in range(1, 9):
            app.msg_list.append({"seq": 100 + i, "uid": core.uid if i % 2 else 999,
                                 "nick": "我" if i % 2 else "他人",
                                 "text": f"消息 {i}", "ts": 1700000000 + i})
        pump(0.5)
        events = []

        # 1. 进入选择模式（包装原回调：既记录事件又保持选择栏联动）
        orig_cb = app.msg_list._on_sel_change
        app.msg_list.set_sel_cb(
            lambda m, c: (events.append((m, c)), orig_cb(m, c)))
        app.msg_list.enter_select_mode(2)
        pump(0.3)
        check("进入选择模式", app.msg_list.in_select_mode())
        check("首条已勾选", app.msg_list.selected_rows() == [2],
              str(app.msg_list.selected_rows()))
        check("回调通知计数", events and events[-1] == (True, 1), str(events))
        check("选择栏显示", app.sel_bar.winfo_manager() == "place")
        check("计数标签", app.sel_count_lbl.cget("text") == "已选 1 条")

        # 2. 系统行不可选
        app.msg_list.append_sys("系统提示行")
        pump(0.3)
        sys_idx = len(app.msg_list._rows) - 1
        app.msg_list._toggle_select(sys_idx)
        check("系统行不可勾选", sys_idx not in app.msg_list.selected_rows())

        # 3. 覆盖层点击切换（canvas 级点击命中 stipple 块）
        h = app.msg_list._heights[3] or 40
        cy = int(app.msg_list._cum[3] - app.msg_list.canvasy(0) + h / 2)
        app.msg_list.event_generate("<Button-1>", x=200, y=cy)
        pump(0.3)
        check("点击行3勾选", 3 in app.msg_list.selected_rows(),
              str(app.msg_list.selected_rows()))
        check("计数更新", app.sel_count_lbl.cget("text") == "已选 2 条",
              app.sel_count_lbl.cget("text"))
        cy2 = int(app.msg_list._cum[3] - app.msg_list.canvasy(0) + h / 2)
        app.msg_list.event_generate("<Button-1>", x=200, y=cy2)
        pump(0.3)
        check("再点取消勾选", 3 not in app.msg_list.selected_rows())

        # 4. 多选删除：桩 send_del 记录（行1=自己 seq101，行2=他人 seq102 跳过）
        app.msg_list.enter_select_mode(1)      # 行1=自己
        app.msg_list._toggle_select(2)         # 行2=他人
        dels = []
        core.send_del = lambda seq: dels.append(seq)
        app._multi_delete()
        pump(0.3)
        check("删除只撤自己消息", dels == [101], str(dels))
        check("删除后退出选择模式", not app.msg_list.in_select_mode())
        check("选择栏隐藏", app.sel_bar.winfo_manager() == "")
        check("跳过提示", any("跳过 1 条" in r.body
                              for r in app.msg_list._rows
                              if r.tag == "sys"))

        # 5. 多选转发：驱动真实转发对话框（选公共频道 → 点「转发」）
        app.msg_list.enter_select_mode(3)
        app.msg_list._toggle_select(5)
        sent = []
        core.send_chat = lambda text, **kw: sent.append((text, kw.get("forward")))
        app._multi_forward()
        pump(0.3)
        dlgs = [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel)]
        lb = next(w for w in dlgs[-1].winfo_children()
                  if isinstance(w, tk.Listbox))
        btn = next(w for w in dlgs[-1].winfo_children()
                   if isinstance(w, tk.Button) and w.cget("text") == "转发")
        lb.selection_set(0)
        btn.invoke()
        pump(0.3)
        check("多条转发逐条发送", len(sent) == 2, str(sent))
        check("转发快照带 nick/seq",
              all(f.get("nick") and f.get("seq") for _t, f in sent))
        check("转发后退出选择模式", not app.msg_list.in_select_mode())

        # 6. 无可转发内容提示（选中行清空后全部为图？此处用空模式验证按钮禁用）
        app.msg_list.enter_select_mode(1)
        app.msg_list._toggle_select(1)         # 取消唯一勾选
        pump(0.2)
        check("0 条时按钮禁用",
              str(app.sel_fwd_btn.cget("state")) == "disabled"
              and str(app.sel_del_btn.cget("state")) == "disabled")
        check("0 条时选择栏仍在", app.sel_bar.winfo_manager() == "place")
        # 7. Esc 退出
        app._esc_exit_select()
        pump(0.2)
        check("Esc 退出选择模式", not app.msg_list.in_select_mode()
              and app.sel_bar.winfo_manager() == "")
        # 8. 会话清空自动退模式
        app.msg_list.enter_select_mode(0)
        pump(0.2)
        app.msg_list.clear()
        pump(0.2)
        check("清空会话退选择模式", not app.msg_list.in_select_mode()
              and app.sel_bar.winfo_manager() == "")
    except Exception as e:
        ok = False
        results.append(f"[FAIL] 异常: {type(e).__name__}: {e}")
    finally:
        stop.set()
        time.sleep(0.2)

    print("\n".join(results))
    print("R31B 冒烟:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
