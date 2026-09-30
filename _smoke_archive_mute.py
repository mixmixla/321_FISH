# -*- coding: utf-8 -*-
"""R4 C6 冒烟：会话归档 + 会话静音。
- 私聊收到离线消息 → 未读累计；右键菜单出现 静音/归档
- 静音后 _channel_muted 命中、菜单变为 取消静音
- 归档后主名单剔除、归档区收录；Ctrl+9/按钮展开折叠区；双击打开并取消归档
- 归档区的静音行灰化沿用同一 muted 判定
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
            return chan, h["uid"]


def _labels(menu):
    if menu is None:
        return None
    n = menu.index("end") + 1
    return [menu.entrycget(i, "label") for i in range(n)]


def main() -> int:
    cfg = replace(CFG, audit_dir="_tmp_gui/audit")
    hub = Hub(cfg=cfg, audit_dir="_tmp_gui/audit")
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)

    core = ClientCore(host="127.0.0.1", port=port, nick="冒烟主")
    app = ChatWindow(core)
    peer, peer_uid = _peer(port, "对端乙")
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

    # 1) 对端发私聊 → GUI 未读累计
    peer.send_frame({"t": "chat", "channel": "private", "to": core.uid,
                     "text": "归档前一句"})
    pump(0.6)
    key = app._pin_key("private", peer_uid)
    # 清掉历史遗留的偏好，保证断言从干净状态开始
    if app._prefs.is_pinned(key):
        app._prefs.toggle_pin(key)
    if app._prefs.is_muted(key):
        app._prefs.toggle_mute(key)
    if app._prefs.is_archived(key):
        app._prefs.toggle_archive(key)
    app._refresh_lists()
    check("private unread bumped",
          app._unread.get(("private", peer_uid), 0) >= 1)

    # 2) 右键菜单含 静音/归档
    lbls = _labels(app._build_roster_menu(peer_uid))
    check("menu has mute+archive", lbls and "静音" in lbls and "归档" in lbls,
          str(lbls))

    # 3) 静音：判定命中 + 菜单变 取消静音
    app._prefs.toggle_mute(key)
    app._refresh_roster()
    check("channel muted", app._channel_muted("private", peer_uid))
    lbls2 = _labels(app._build_roster_menu(peer_uid))
    check("menu now unmute", lbls2 and "取消静音" in lbls2, str(lbls2))

    # 4) 归档：主名单剔除 + 归档区收录
    app._prefs.toggle_archive(key)
    app._refresh_lists()
    check("excluded from main roster", peer_uid not in app._roster_order)
    check("archived keys collected", key in app._archived_keys)

    # 5) 展开归档区：按钮/Ctrl+9 切换 + 灰化沿用 muted
    r = app._toggle_archived_panel()
    pump(0.3)
    check("ctrl+9 returns break", r == "break")
    check("panel shown", app._archived_show is True
          and app._archived_list.winfo_ismapped())
    check("archived line present", app._archived_list.size() >= 1)

    # 6) 双击打开归档会话 → 取消归档并收起
    app._archived_list.select_set(0)
    app._on_archived_select()
    app._archived_list.select_clear(0, "end")
    app._open_archived()
    check("open unarchives", app._prefs.is_archived(key) is False)
    check("view switched", app.view == ("private", peer_uid))
    check("panel collapsed", app._archived_show is False)

    print("\n".join(results))
    peer.send_frame({"t": "bye"})
    app.quit_app()
    print("GUI ARCHIVE/MUTE SMOKE OK" if ok else "GUI ARCHIVE/MUTE SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())