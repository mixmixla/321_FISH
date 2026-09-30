# -*- coding: utf-8 -*-
"""R8 冒烟：Frameless 无边框窗（overrideredirect + 自绘标题栏 + DWM 圆角不抛异常）。"""
import os
import socket
import threading
import time
from dataclasses import replace

os.environ["MOYU_FRAMELESS"] = "1"      # 强制本冒烟走 frameless

from config import CFG
from client_core import ClientCore
from client import ChatWindow


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    hub = None
    from server import Hub, serve as serve_tcp
    cfg = replace(CFG, audit_dir="_tmp_gui/audit")
    hub = Hub(cfg=cfg, audit_dir="_tmp_gui/audit")
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)

    core = ClientCore(host="127.0.0.1", port=port, nick="无边框冒烟")
    app = ChatWindow(core)
    results = []
    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    try:
        app.root.update()
        check("overrideredirect enabled", bool(app.root.overrideredirect()))
        check("title_bar created", app.title_bar is not None)
        # 标题栏换色跟随皮肤
        app._on_skin_change("dark")
        app.root.update()
        expected = app._skin["titlebar_bg"]
        actual = app.title_bar["bg"]
        check("titlebar follows skin", actual == expected, f"{actual} vs {expected}")
        app._on_skin_change("office")

        # DWM 圆角不抛异常（win32 下调用过）
        try:
            app._apply_dwm_corner()
            check("dwm corner no exception", True)
        except Exception as e:   # noqa
            check("dwm corner no exception", False, repr(e))
    finally:
        stop.set()
        app.quit_app()

    print("\n".join(results))
    print("GUI FRAMELESS SMOKE OK" if ok else "GUI FRAMELESS SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())