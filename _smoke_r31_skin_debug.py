# -*- coding: utf-8 -*-
"""R31 排查冒烟：切皮肤后工具栏是否还能点；更多菜单 grab 是否残留。"""
import socket
import threading
import time
from dataclasses import replace

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

    core = ClientCore(host="127.0.0.1", port=port, nick="皮肤排查")
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
        pump(0.5)
        from client import skin_names
        names = skin_names()
        results.append(f"可用皮肤: {names}")

        # 1. 切换每个皮肤 → 按钮仍可点、state 正常
        for name in names:
            app._on_skin_change(name)
            pump(0.2)
            states = [str(b.cget("state")) for b in app._bottom_btns]
            cur_grab = app.root.grab_current()
            check(f"皮肤 {name}: 按钮 state=normal 且无 grab 残留",
                  all(s == "normal" for s in states) and cur_grab is None,
                  f"states={states} grab={cur_grab}")

        # 2. 模拟点击：invoke 触发回调（表情条开合）
        app._on_skin_change(names[0])
        pump(0.1)
        before = app._sticker_on
        app._bottom_btns[0].invoke()          # 😊
        pump(0.2)
        check("点击 😊 表情条开合生效", app._sticker_on != before)

        # 3. 更多菜单弹出 → 关闭 → grab 是否残留
        m = app._build_more_menu()
        try:
            m.tk_popup(app._more_btn.winfo_rootx(),
                       app._more_btn.winfo_rooty() - 200)
            pump(0.3)
        finally:
            try:
                m.unpost()
                m.grab_release()
                m.destroy()
            except Exception:
                pass
        pump(0.3)
        grab = app.root.grab_current()
        check("更多菜单关闭后无 grab 残留", grab is None, f"grab={grab}")

        # 4. 点击 📎（文件对话框会弹——改点 🗳 投票对话框也会弹；
        #    只验证 state 与 command 绑定存在）
        cmds = [str(b.cget("command")) for b in app._bottom_btns]
        check("全部按钮 command 已绑定",
              all(c and c != "" for c in cmds), str(cmds))

        # 5. R31 ghost 修复闭环：进入 → 提示条显示 → 点击提示条 → 完整 UI 恢复
        app.toggle_ghost()
        pump(0.5)
        tip = getattr(app, "_ghost_exit_tip", None)
        check("ghost 进入后提示条显示",
              app._ghost and tip is not None
              and tip.winfo_manager() == "place"
              and str(tip.cget("bg")) == "#2b2b2b", f"tip={tip}")
        tip.invoke() if hasattr(tip, "invoke") else tip.event_generate("<Button-1>")
        pump(0.5)
        check("点击提示条恢复完整 UI",
              not app._ghost and tip.winfo_manager() == "")
        states = [str(b.cget("state")) for b in app._bottom_btns]
        check("恢复后按钮可点", all(s == "normal" for s in states),
              str(states))
        # 二次进入（验证挖空遍历后提示条颜色强制恢复）
        app.toggle_ghost()
        pump(0.4)
        check("二次进入提示条仍可见",
              app._ghost and str(app._ghost_exit_tip.cget("bg")) == "#2b2b2b")
        app.toggle_ghost()
        pump(0.4)
        check("二次退出收起提示条",
              not app._ghost
              and app._ghost_exit_tip.winfo_manager() == "")
    except Exception as e:
        import traceback
        ok = False
        results.append(f"[FAIL] 异常: {traceback.format_exc()}")
    finally:
        stop.set()
        time.sleep(0.2)

    print("\n".join(results))
    print("排查冒烟:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
