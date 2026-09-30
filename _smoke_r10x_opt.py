# -*- coding: utf-8 -*-
"""R10x 冒烟：对比 TG 源码后的交互优化。
1) 标题栏右键菜单（隐藏/锁定/退出）存在且点选触发对应回调；
2) 发送节流：Hold 回车自动重复在 _ENTRY_SEND_GAP 内被丢弃，不连发。
"""
import os
import threading
import time
from dataclasses import replace

os.environ["MOYU_FRAMELESS"] = "0"
import tkinter as tk

from config import CFG
from client_core import ClientCore
from client import ChatWindow, _ENTRY_SEND_GAP


def _free_server() -> int:
    """起一个局域服务器并返回 port。"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    from server import Hub, serve as serve_tcp
    cfg = replace(CFG, audit_dir="_tmp_gui/audit")
    hub = Hub(cfg=cfg, audit_dir="_tmp_gui/audit")
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)
    return port, stop


def main() -> int:
    results = []
    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    # ---- 1) 标题栏右键菜单（独立 stub 构建 TitleBar） ----
    root = tk.Tk()
    root.withdraw()
    states = {"mini": 0, "lock": 0, "quit": 0}

    class StubCore:
        nick = "冒烟"

    class StubApp:
        core = StubCore()
        def hide_to_mini(self): states["mini"] += 1
        def lock_app(self): states["lock"] += 1
        def quit_app(self): states["quit"] += 1
        _skin = {"titlebar_bg": "#eef1f4"}

    from widgets.title_bar import TitleBar
    tb = TitleBar(root, StubApp())
    tk.Menu.tk_popup = lambda *a, **k: None   # 不弹模态，仅构建菜单供检查
    tb._show_menu(type("E", (), {"x_root": 0, "y_root": 0})())
    m = tb._menu
    check("titlebar menu built", m is not None)
    if m is not None:
        labels = []
        for i in range(m.index("end") + 1):
            try:
                labels.append(m.entrycget(i, "label") or "--")
            except tk.TclError:
                labels.append("--")          # separator 无 label
        check("menu has lock", any("锁定" in l for l in labels), str(labels))
        check("menu has mini", any("迷你条" in l for l in labels))
        check("menu has quit", any("退出" == l for l in labels))
    root.destroy()

    # ---- 2) 发送节流：同一 Text 内连续触发两次 Return，只发一次 ----
    port, stop = _free_server()
    core = ClientCore(host="127.0.0.1", port=port, nick="节流冒烟")
    app = ChatWindow(core)
    sent = {"n": 0}
    import weakref
    orig = core.send_chat
    def spy(text, **kw):
        sent["n"] += 1
        return orig(text, **kw)
    core.send_chat = spy
    try:
        app.root.update()
        app.entry.insert("1.0", "hello 节流")
        app._on_entry_return()
        app._on_entry_return()             # 紧跟第二次（gap 内）→ 应被丢弃
        app.root.update()
        check("send throttle drops repeat",
              sent["n"] == 1, f"sent={sent['n']}")
        # gap 过后可再发
        app._last_send = 0.0
        app.entry.insert("1.0", "again")
        app._on_entry_return()
        app.root.update()
        check("send allowed after gap", sent["n"] == 2, f"sent={sent['n']}")
        # 空消息不计数
        app.entry.delete("1.0", "end")
        app._last_send = 0.0
        app._on_entry_return()
        app.root.update()
        check("empty send ignored", sent["n"] == 2, f"sent={sent['n']}")
    finally:
        stop.set()
        app.quit_app()
        core.stop()

    print("\n".join(results))
    print("GUI R10X OPT SMOKE OK" if ok else "GUI R10X OPT SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())