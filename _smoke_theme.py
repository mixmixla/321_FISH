# -*- coding: utf-8 -*-
"""T3 主题冒烟：设置页打开皮肤下拉、切到深色/畅聊即时应用并持久化、
再切回 office 恢复浅色，末尾回归默认避免污染共享 prefs.json。"""
import socket
import threading
import time
from dataclasses import replace

from config import CFG
from crypto import client_handshake
from server import Hub, serve as serve_tcp
from client_core import ClientCore
from client import ChatWindow


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _peer(port: int, nick: str):
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    chan = client_handshake(sock)
    sock.settimeout(None)
    chan.send_frame({"t": "hello", "nick": nick})
    while True:
        h, _b = chan.recv_frame()
        if h.get("t") == "welcome":
            break
    return chan


def main() -> int:
    cfg = replace(CFG, audit_dir="_tmp_gui/audit")
    hub = Hub(cfg=cfg, audit_dir="_tmp_gui/audit")
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)

    core = ClientCore(host="127.0.0.1", port=port, nick="冒烟戊")
    app = ChatWindow(core)
    peer = _peer(port, "主题对端")
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
        # 0) 启动皮肤自洽：msg_list 颜色表必须等于当前皮肤 token（不硬编码皮肤名）
        from theme import get_skin
        sk0 = get_skin(app._skin_name)
        check("launch skin tokens applied",
              app.msg_list._pal["bubble_out"] == sk0["bubble_out"]
              and app.msg_list._pal["bg"] == sk0["msg_bg"],
              f"{app._skin_name}: {app.msg_list._pal['bubble_out']}/{app.msg_list._pal['bg']}")

        # 1) 设置页为内嵌全屏面板（不再是独立 Toplevel 弹窗）
        top_before = app.root.winfo_toplevel()
        app._on_settings()
        pump(0.2)
        check("settings panel opens (embedded frame)",
              hasattr(app, "_settings_win") and app._settings_win.winfo_exists()
              and app._settings_win.winfo_ismapped())
        check("not a separate toplevel dialog",
              app._settings_win.winfo_toplevel() is top_before)
        app._close_settings()
        pump(0.1)
        check("settings panel closes (hidden)",
              not app._settings_win.winfo_ismapped())

        # 2) 切深色：即时应用 + msg_list 颜色表跟随 + 持久化
        app._on_skin_change("dark")
        pump(0.2)
        check("dark skin applied", app._skin_name == "dark")
        check("dark msg background", app.msg_list._pal["bg"] == "#282e33",
              app.msg_list._pal["bg"])
        check("dark bubble out", app.msg_list._pal["bubble_out"] == "#2a2f33",
              app.msg_list._pal["bubble_out"])
        check("dark roster listbox bg",
              app.roster_list.cget("bg") == "#282e33",
              app.roster_list.cget("bg"))
        check("skin persisted in prefs",
              app._prefs.get("skin", "") == "dark")

        # 3) 切畅聊：自己气泡变绿
        app._on_skin_change("chat")
        pump(0.2)
        check("chat skin applied", app._skin_name == "chat")
        check("chat bubble out green",
              app.msg_list._pal["bubble_out"] == "#c9f1d7",
              app.msg_list._pal["bubble_out"])

        # 4) 切回 office 恢复浅色（避免污染共享 prefs.json 留 office）
        app._on_skin_change("office")
        pump(0.2)
        check("office restored", app.msg_list._pal["bubble_out"] == "#def1fd")
        check("skin reset persisted", app._prefs.get("skin", "") == "office")
    finally:
        app._on_skin_change("office")
        peer.send_frame({"t": "bye"})
        app.quit_app()

    print("\n".join(results))
    print("GUI THEME SMOKE OK" if ok else "GUI THEME SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())