# -*- coding: utf-8 -*-
"""B2/B3 右键菜单 + B4 双击回复冒烟：
消息菜单按类型裁剪（自己/他人/系统）、复制/编辑/引用行为、
会话菜单删除本地记录、双击填充引用前缀。"""
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

    # 三条消息：自己 / 他人 / 系统
    app.entry.insert("1.0", "自己的消息文本")
    app._on_entry_return()
    peer.send_frame({"t": "chat", "channel": "public", "text": "他人的消息文本"})
    app.append_sys_hint = None
    app._append_sys("系统提示行")
    pump(1.2)

    rows = app.msg_list._rows
    own_idx = next(i for i, r in enumerate(rows)
                   if r.raw.get("uid") == core.uid and r.raw.get("text"))
    other_idx = next(i for i, r in enumerate(rows)
                     if r.raw.get("nick") == "对端乙" and r.raw.get("text"))
    sys_idx = next(i for i, r in enumerate(rows) if r.tag == "sys")
    other_body = app.msg_list.body_text(other_idx)

    # 1) 菜单裁剪（C3：自己消息增加"撤回"；R12：新增"选择文本"）
    check("own menu: 复制/选择文本/编辑/撤回/引用回复",
          _labels(app._build_msg_menu(own_idx)) == ["复制", "选择文本", "编辑", "撤回", "引用回复"])
    check("other menu: 复制/选择文本/引用回复",
          _labels(app._build_msg_menu(other_idx)) == ["复制", "选择文本", "引用回复"])
    check("sys menu: None", _labels(app._build_msg_menu(sys_idx)) is None)

    # 2) 双击回复 → 输入框出现引用标记行 + 待发快照（C4）
    app.entry.delete("1.0", "end")
    app._on_msg_double(other_idx)
    check("double-click quote prefix",
          app._entry_text().startswith("↩ 对端乙: 他人的消息文本\n"))
    check("quote sets pending reply",
          app._pending_reply is not None and app._pending_reply["nick"] == "对端乙")

    # 3) 编辑自己的消息 → 原文回填
    app._edit_msg(own_idx)
    check("edit fills own text", "自己的消息文本" in app._entry_text())

    # 4) 复制 → 剪贴板
    app._copy_text("复制目标串")
    check("copy to clipboard", app.root.clipboard_get() == "复制目标串")

    # 5) 会话右键菜单
    peer_uid = next(u["uid"] for u in core.roster.values() if u["nick"] == "对端乙")
    mk = app._pin_key("private", peer_uid)            # 清掉历史遗留偏好保证断言
    if app._prefs.is_pinned(mk):
        app._prefs.toggle_pin(mk)
    if app._prefs.is_muted(mk):
        app._prefs.toggle_mute(mk)
    if app._prefs.is_archived(mk):
        app._prefs.toggle_archive(mk)
    check("roster menu for peer",
          _labels(app._build_roster_menu(peer_uid)) ==
          ["置顶", "静音", "归档", "删除会话记录"])
    check("no roster menu for self",
          _labels(app._build_roster_menu(core.uid)) is None)
    check("no group menu for missing gid", _labels(app._build_group_menu(999)) is None)

    # 6) 删除私聊本地记录
    core.send_private("私聊一条", peer_uid)
    pump(1.0)
    assert any(m["text"] == "私聊一条" for m in core.history("private", peer_uid))
    app._drop_session("private", peer_uid)
    check("drop private history",
          core.history("private", peer_uid) == []
          and core._history.load_disk(f"private:{sorted((core.uid, peer_uid))[0]}:"
                                      f"{sorted((core.uid, peer_uid))[1]}") == [])

    print("\n".join(results))
    peer.send_frame({"t": "bye"})
    app.quit_app()
    print("GUI MENUS SMOKE OK" if ok else "GUI MENUS SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
