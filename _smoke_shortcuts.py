# -*- coding: utf-8 -*-
"""B1 快捷键冒烟：真实 Hub + ClientCore + ChatWindow，
验证快捷键注册无冲突（避开 Ctrl+Alt+H）且行为正确：
会话循环切换（Ctrl+PgUp/Dn）、Ctrl+E 编辑上一条、Shift+Enter 换行、Enter 发送。"""
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
    """第二个客户端：连上并排空回显，收集收到的 chat 事件供断言"""
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    chan = client_handshake(sock)
    sock.settimeout(None)
    chan.send_frame({"t": "hello", "nick": nick})
    while True:
        h, _b = chan.recv_frame()
        if h.get("t") == "welcome":
            break
    got = []

    def _loop():
        try:
            while True:
                h, _b = chan.recv_frame()
                if h.get("t") == "chat":
                    got.append(h)
        except Exception:
            pass

    threading.Thread(target=_loop, daemon=True).start()
    return chan, got


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
    peer, got = _peer(port, "对端乙")
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

    # 0) 绑定注册且不占用 boss 热键（Ctrl+Alt+H 是全局热键，root 不应有绑定）
    for seq in ("<Control-w>", "<Control-Prior>", "<Control-Next>",
                "<Control-j>", "<Control-e>"):
        check(f"bound {seq}", bool(app.root.bind(seq)))
    check("boss hotkey free on root", app.root.bind("<Control-Alt-h>") == "")

    # 1) 己方发一条（供 Ctrl+E），对端回一条（供会话列表有对象）
    app.entry.insert("1.0", "己方首条消息")
    app._on_entry_return()
    peer.send_frame({"t": "chat", "channel": "public", "text": "对端消息"})
    pump(1.5)
    own_msgs = [r.raw for r in app.msg_list._rows
                if r.raw.get("uid") == core.uid and r.raw.get("text")]
    check("own msg rendered", len(own_msgs) >= 1)

    # 2) Ctrl+E：编辑自己最后一条 → 输入框带原文
    app._edit_last_own()
    check("Ctrl+E loads last own text",
          "己方首条消息" in app._entry_text())
    check("Ctrl+E appends edit hint",
          any("正在编辑该条" in (r.raw.get("text") or "")
              for r in app.msg_list._rows if r.tag == "sys"))

    # 3) Shift+Enter 换行
    app.entry.delete("1.0", "end")
    app.entry.insert("1.0", "第一行")
    app._on_entry_newline()
    app.entry.insert("end", "第二行")
    check("Shift+Enter newline", app._entry_text() == "第一行\n第二行")

    # 4) Enter 发送（多行内容仍整段发送）；空输入不发送
    app._on_entry_return()
    check("entry cleared after send", app._entry_text().strip() == "")
    pump(1.0)                       # 等上一条自己消息抵达对端
    own_before = len([h for h in got if h["uid"] == core.uid])
    app._on_entry_return()          # 空输入不发送
    pump(0.5)
    own_after = len([h for h in got if h["uid"] == core.uid])
    check("empty send no-op", own_after == own_before)

    # 5) Ctrl+PgDn / PgUp 会话循环：public → 私聊(对端) → public
    peer_uid = next(u["uid"] for u in core.roster.values()
                    if u["nick"] == "对端乙")
    app.view = ("public", None)
    app._load_view_history()
    app._next_chat()
    check("Ctrl+PgDn → private",
          app.view == ("private", peer_uid), f"view={app.view}")
    app._next_chat()
    check("Ctrl+PgDn → public", app.view == ("public", None),
          f"view={app.view}")
    app._prev_chat()
    check("Ctrl+PgUp → private", app.view == ("private", peer_uid),
          f"view={app.view}")

    # 6) Ctrl+J 聚焦名单
    app._focus_contacts()
    check("Ctrl+J focus roster",
          app.root.focus_get() is app.roster_list)

    print("\n".join(results))
    peer.send_frame({"t": "bye"})
    app.quit_app()
    print("GUI SHORTCUTS SMOKE OK" if ok else "GUI SHORTCUTS SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
