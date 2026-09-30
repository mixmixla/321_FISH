# -*- coding: utf-8 -*-
"""R31D（托盘 + 隐身友好 Toast）冒烟：
- StealthToast：显示右下角浮窗、自动消失、重复显示覆盖不报错
- stealth_text：返回假办公文案（不含真实昵称/正文）
- Client：非前台收消息 → Toast 弹出（默认假文案）；前台 → 不弹
- Tray：托盘创建成功（pystray 可用则 True），stop 后释放
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
from widgets.stealth_toast import StealthToast, stealth_text


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

    core = ClientCore(host="127.0.0.1", port=port, nick="托盘冒烟")
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
        # 1. stealth_text 假文案
        t1 = stealth_text()
        check("假文案生成", bool(t1) and "冒烟" not in t1, t1)
        check("假文案多样", any(stealth_text() != t1 for _ in range(20)))

        # 2. StealthToast 独立显示
        toast = StealthToast(app.root)
        toast.show("文档 Q3_报表_v3.docx 已同步", dur=1.0)
        pump(0.3)
        check("Toast 显示", toast._win is not None
              and toast._win.winfo_ismapped())
        geo = toast._win.geometry()
        check("右下角定位", "+" in geo and
              int(geo.split("+")[1]) > 300, geo)
        toast.show("第二条覆盖", dur=0.6)
        pump(0.2)
        check("重复显示覆盖", toast._body.cget("text") == "第二条覆盖")
        pump(1.0)
        check("超时自动隐藏", not toast._win.winfo_ismapped())

        # 3. Client：非前台收消息 → Toast 弹出（默认假文案，不透出昵称/正文）
        app.root.withdraw()
        pump(0.3)
        app._toast_notify({"nick": "老板", "text": "今晚加班"})
        pump(0.3)
        shown = app._toast._body.cget("text")
        check("Toast 弹出", app._toast._win.winfo_ismapped())
        check("默认假文案脱敏",
              "老板" not in shown and "加班" not in shown, shown)
        app._toast.hide()
        pump(0.2)

        # 4. 真实摘要模式（prefs toast_stealth=False）
        app._prefs.set("toast_stealth", False)
        app._toast_notify({"nick": "老板", "text": "今晚加班"})
        pump(0.2)
        check("真实摘要模式",
              app._toast._body.cget("text") == "老板：今晚加班",
              app._toast._body.cget("text"))
        app._prefs.set("toast_stealth", True)
        app._toast.hide()
        pump(0.2)

        # 5. 前台时不弹（恢复窗口后走 _flash_taskbar → return）
        app.show_main()
        pump(0.3)
        app._flash_taskbar({"nick": "x", "text": "y"})
        pump(0.2)
        check("前台不弹 Toast", not app._toast._win.winfo_ismapped())

        # 6. 托盘创建（pystray 可用）
        check("托盘已创建", app._tray is not None and app._tray.visible())
    except Exception as e:
        ok = False
        results.append(f"[FAIL] 异常: {type(e).__name__}: {e}")
    finally:
        try:
            if getattr(app, "_tray", None) is not None:
                app._tray.stop()
            app.root.destroy()
        except Exception:
            pass
        stop.set()
        time.sleep(0.2)

    print("\n".join(results))
    print("R31D 冒烟:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
