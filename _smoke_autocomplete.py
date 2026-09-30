# -*- coding: utf-8 -*-
"""B5 @提及 + emoji 补全冒烟：触发/候选/选中替换/关闭 全链路。"""
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

    core = ClientCore(host="127.0.0.1", port=port, nick="冒烟甲")
    app = ChatWindow(core)
    peer = _peer(port, "对端乙")
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

    def type_text(s: str):
        """模拟逐字输入（触发 KeyRelease 刷新候选）"""
        app.entry.delete("1.0", "end")
        app.entry.focus_set()
        for ch in s:
            app.entry.insert("insert", ch)
            app._on_entry_key(type("E", (), {"keysym": ch})())

    # 1) @ 触发：候选列表出现"对端乙"
    type_text("@对")
    pump(0.2)
    check("@ trigger opens popup", app._ac_top is not None and app._ac_kind == "at")
    cands = [app._ac_list.get(i) for i in range(app._ac_list.size())]
    check("@ candidates contain 对端乙", "对端乙" in cands)

    # 2) Enter 选中 → 替换为 @对端乙 + 空格，弹窗关闭
    app._on_entry_return()
    check("choose @ inserts nick", app._entry_text() == "@对端乙 ")
    check("popup closed after choose", app._ac_top is None)

    # 3) : 触发 emoji 补全
    type_text(":sm")
    pump(0.2)
    check(": trigger opens popup", app._ac_top is not None and app._ac_kind == "emoji")
    ec = [app._ac_list.get(i) for i in range(app._ac_list.size())]
    check("emoji candidates match :sm", any(c.startswith("sm") for c in ec))

    # 4) Tab 选中 → :smile:
    app._ac_list.selection_set(0)
    app._ac_tab()
    check("choose emoji inserts :code:", ":smile:" in app._entry_text())

    # 5) 无触发器 → 弹窗关闭
    type_text("普通文本无触发")
    pump(0.2)
    check("no trigger closes popup", app._ac_top is None)

    # 6) @ 后跟空格（已提到名字继续输入）→ 不触发
    app.entry.delete("1.0", "end")
    app.entry.insert("1.0", "早上好 @对端乙 开会")
    app.entry.mark_set("insert", "end")
    app._refresh_ac()
    check("@ followed by space no trigger", app._ac_top is None)

    # 7) R10x：纯导航键（Left/Right/Home/End）不重建也不关闭补全（对齐 TG）
    app.entry.delete("1.0", "end")
    app.entry.insert("insert", "@对")
    app._refresh_ac()
    pump(0.2)
    check("popup open for nav test", app._ac_top is not None)
    app._on_entry_key(type("E", (), {"keysym": "Left"})())
    app._on_entry_key(type("E", (), {"keysym": "Right"})())
    app._on_entry_key(type("E", (), {"keysym": "Home"})())
    check("nav keys keep popup open", app._ac_top is not None)

    print("\n".join(results))
    peer.send_frame({"t": "bye"})
    app.quit_app()
    print("GUI AUTOCOMPLETE SMOKE OK" if ok else "GUI AUTOCOMPLETE SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
