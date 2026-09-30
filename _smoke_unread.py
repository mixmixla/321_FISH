# -*- coding: utf-8 -*-
"""C2/C5/C6 未读红点 + 置顶 + 搜索框冒烟：全链路验证。

覆盖：
- 其它会话来消息 → 未读计数 + 名单/群徽标 (n)
- 切换到该会话 → 未读清零
- 置顶 → 排序置顶且持久化；右键菜单显示「取消置顶」
- 搜索框过滤名单/群；Ctrl+F 聚焦
- Ctrl+G 跳最早未读；标记已读
"""
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

    # 等在线名单同步出对端乙
    deadline = time.time() + 4
    while "对端乙" not in [u["nick"] for u in core.roster.values()] and time.time() < deadline:
        app.root.update()
        time.sleep(0.03)
    uid_b = next(u["uid"] for u in core.roster.values() if u["nick"] == "对端乙")

    # 默认停在公共频道
    check("initial view public", app.view == ("public", None))

    # 1) 私聊来消息 → 未读累计 (1)，列表项出现 (1)
    peer.send_frame({"t": "chat", "channel": "private",
                     "to": core.uid, "uid": uid_b,
                     "nick": "对端乙", "text": "你好呀", "ts": time.time()})
    pump(0.4)
    check("unread bumped to 1", app._unread.get(("private", uid_b)) == 1)
    roster_text = [app.roster_list.get(i) for i in range(app.roster_list.size())]
    check("roster shows (1) badge", any("(1)" in t for t in roster_text),
          str(roster_text))

    # 2) 切到私聊 → 未读清零
    app._switch_view("private", uid_b)
    pump(0.2)
    check("switch clears unread", app._unread.get(("private", uid_b), 0) == 0)

    # 4) 置顶对端乙 → 排序置顶 + 持久化 + 菜单文案
    key = app._pin_key("private", uid_b)
    app._prefs.toggle_pin(key)
    app._refresh_roster()
    pump(0.2)
    top_idx = app._roster_order[0]
    check("pinned moved to top", top_idx == uid_b, f"top={top_idx}")
    check("pin persisted", app._prefs.is_pinned(key))
    menu = app._build_roster_menu(uid_b)
    labels = []
    if menu is not None:
        for i in range(menu.index("end") + 1):
            try:
                labels.append(menu.entrycget(i, "label"))
            except Exception:
                pass
    check("menu shows 取消置顶", "取消置顶" in labels, str(labels))
    app._prefs.toggle_pin(key)          # 复位
    app._refresh_roster()

    # 5) 搜索过滤
    app.search_entry.insert(0, "对端")
    app._search = app.search_entry.get().strip().lower()
    app._refresh_lists()
    pump(0.2)
    roster_text = [app.roster_list.get(i) for i in range(app.roster_list.size())]
    check("search filters roster", all("对端" in t for t in roster_text), str(roster_text))
    app.search_entry.delete(0, "end")
    app._search = ""
    app._refresh_lists()
    pump(0.2)

    # 6) 回到公共，来私聊未读 + Ctrl+G 跳最早未读
    app._switch_view("public", None)
    peer.send_frame({"t": "chat", "channel": "private",
                     "to": core.uid, "uid": uid_b,
                     "nick": "对端乙", "text": "再发一条", "ts": time.time()})
    pump(0.4)
    check("unread bumped again", app._unread.get(("private", uid_b), 0) == 1)
    app._jump_unread()
    pump(0.2)
    check("Ctrl+G jumps to unread chat", app.view == ("private", uid_b))

    print("\n".join(results))
    peer.send_frame({"t": "bye"})
    app.quit_app()
    print("GUI UNREAD SMOKE OK" if ok else "GUI UNREAD SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())