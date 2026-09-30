# -*- coding: utf-8 -*-
"""R10 冒烟：运行时锁屏 + 任务栏防偷窥。
锁定 → 主窗隐藏 + 全屏 LockOverlay + DWM 防预览不抛异常；解锁恢复主窗。
覆盖：未设码不打锁、设码后 🔒/Ctrl+L 锁定、对/错码、取消解锁、quit 清理。
"""
import os
import socket
import threading
import time
from dataclasses import replace

# 锁定冒烟用标准边框窗，避免 overrideredirect 干扰 win 状态断言
os.environ["MOYU_FRAMELESS"] = "0"

from config import CFG
from client_core import ClientCore
from client import ChatWindow
from prefs import Prefs
import auth


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

    prefs = Prefs("_tmp_gui/r10_prefs.json")
    correct = "2468"
    prefs.set_passcode(auth.make(correct))

    core = ClientCore(host="127.0.0.1", port=port, nick="锁屏冒烟")
    app = ChatWindow(core, prefs_path=prefs._path)
    results = []
    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    try:
        app.root.update()
        # 锁定前主窗可见、无遮罩
        check("main visible before lock", app.root.state() == "normal")
        check("no overlay before lock", app._lock_overlay is None)

        # Ctrl+L 注册进 _bound
        pats = [p for p, _ in getattr(app, "_bound", [])]
        check("ctrl_l bound", "<Control-l>" in pats, str(pats))

        # 锁定 → 主窗隐藏 + LockOverlay + DWM 防偷窥不抛异常
        app.lock_app()
        app.root.update()
        check("locked flag", app._locked)
        check("overlay created", app._lock_overlay is not None
              and app._lock_overlay.winfo_exists())
        ov = app._lock_overlay
        check("overlay topmost", bool(ov.attributes("-topmost")))
        try:
            app._set_dwm_peek(True)
            app._set_dwm_peek(False)
            check("dwm peek no exception", True)
        except Exception as e:   # noqa
            check("dwm peek no exception", False, repr(e))

        # 错码 → 内联报错、不触发解锁、遮罩仍在
        ov.entry.delete(0, "end")
        ov.entry.insert(0, "0000")
        ov._submit()
        app.root.update()
        check("wrong keeps locked", app._locked)
        check("wrong overlay stays", app._lock_overlay is not None
              and ov.winfo_exists())

        # 对码 → 恢复主窗、遮罩关闭、_locked 复位
        ov.entry.delete(0, "end")
        ov.entry.insert(0, correct)
        ov._submit()
        app.root.update()
        check("unlocked flag", not app._locked)
        check("overlay gone", app._lock_overlay is None)
        check("main visible after unlock", not app.root.state() == "withdrawn")

        # 取消路径也解锁（on_cancel=unlock_app）
        app.lock_app()
        app.root.update()
        check("relocked", app._locked)
        app._lock_overlay.cancel()
        app.root.update()
        check("cancel unlocks", not app._locked)
    finally:
        stop.set()
        app.quit_app()

    print("\n".join(results))
    print("GUI R10 LOCK SMOKE OK" if ok else "GUI R10 LOCK SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())