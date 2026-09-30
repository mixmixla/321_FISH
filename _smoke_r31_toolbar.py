# -*- coding: utf-8 -*-
"""R31（TG 风格收纳工具栏）冒烟：
- 工具行平铺 5 按钮（😊 📎 🎙 🗳 ＋），发送在右
- 「＋」更多菜单 9 项（开关项带 ✓）
- 🔥/🔕 徽标随开关显隐（点徽标即取消）
- 频道只读递归禁用嵌套按钮
"""
import socket
import threading
import time
from dataclasses import replace

import tkinter as tk  # noqa: F401  （只读断言用）

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

    core = ClientCore(host="127.0.0.1", port=port, nick="工具栏冒烟")
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
        # 1. 平铺按钮
        texts = [b.cget("text") for b in app._bottom_btns]
        check("平铺 5 按钮", len(app._bottom_btns) == 5, str(texts))
        check("按钮文案正确",
              texts == ["😊", "📎", "🎙", "🗳", "＋"], str(texts))
        check("发送按钮在右", app._send_btn.cget("text") == "发送")
        # 2. 更多菜单 9 项
        m = app._build_more_menu()
        items = [m.entrycget(i, "label") for i in range(m.index("end") + 1)
                 if m.type(i) != "separator"]
        check("更多菜单 9 项", len(items) == 9, str(items))
        check("开关项默认无勾选",
              all(not it.startswith("✓") for it in items[-2:]), str(items[-2:]))
        # 3. 徽标显隐
        check("徽标默认隐藏",
              app._burn_btn.winfo_manager() == ""
              and app._silent_btn.winfo_manager() == "")
        if app._burn_mode:                    # prefs 里开着则先关
            app._toggle_burn_mode()
        if app._silent_mode:
            app._toggle_silent_mode()
        pump(0.2)
        check("徽标默认隐藏（确认）",
              app._burn_btn.winfo_manager() == ""
              and app._silent_btn.winfo_manager() == "")
        app._toggle_burn_mode()
        app._toggle_silent_mode()
        pump(0.2)
        check("开关后徽标显示",
              app._burn_btn.winfo_manager() == "pack"
              and app._silent_btn.winfo_manager() == "pack")
        m2 = app._build_more_menu()
        items2 = [m2.entrycget(i, "label") for i in range(m2.index("end") + 1)
                  if m2.type(i) != "separator"]
        check("菜单开关项出现 ✓",
              items2[-2].startswith("✓") and items2[-1].startswith("✓"),
              str(items2[-2:]))
        app._toggle_burn_mode()               # 点徽标即取消
        app._toggle_silent_mode()
        pump(0.2)
        check("再点徽标取消",
              app._burn_btn.winfo_manager() == ""
              and app._silent_btn.winfo_manager() == "")
        # 4. 频道只读递归禁用
        app.view = ("group", "g1")
        app.core.groups = {"g1": {"kind": "channel", "owner": 999}}
        app._ro_mode = False
        app._apply_channel_ro()
        pump(0.2)
        ro_ok = all(b.cget("state") == "disabled" for b in app._bottom_btns)
        check("只读时平铺按钮禁用", ro_ok)
        check("只读时输入框禁用",
              str(app.entry.cget("state")) == "disabled")
        # 恢复
        app.core.groups = {"g1": {"kind": "channel", "owner": core.uid}}
        app._apply_channel_ro()
        pump(0.2)
        check("恢复后可发言",
              all(b.cget("state") == "normal" for b in app._bottom_btns)
              and str(app.entry.cget("state")) == "normal")
    except Exception as e:
        ok = False
        results.append(f"[FAIL] 异常: {type(e).__name__}: {e}")
    finally:
        stop.set()
        time.sleep(0.2)

    print("\n".join(results))
    print("R31 冒烟:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
