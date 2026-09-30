# -*- coding: utf-8 -*-
"""R12 冒烟：文本选择复制——右键菜单含「选择文本」→ 打开只读 Text 窗，
可拖选（tag_add sel）+ 复制进剪贴板；Esc 关闭。"""
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
    out = []
    for i in range(menu.index("end") + 1):
        try:
            out.append(menu.entrycget(i, "label"))
        except Exception:
            pass
    return out


def main() -> int:
    cfg = replace(CFG, audit_dir="_tmp_gui/audit")
    hub = Hub(cfg=cfg, audit_dir="_tmp_gui/audit")
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)

    core = ClientCore(host="127.0.0.1", port=port, nick="选择甲")
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

    peer.send_frame({"t": "chat", "channel": "public",
                     "text": "这是一段用于选择复制的完整正文内容。"})
    pump(0.8)

    idx = next(i for i, r in enumerate(app.msg_list._rows)
               if r.raw.get("nick") == "对端乙" and r.raw.get("text"))
    body = app.msg_list.body_text(idx)
    check("menu has 选择文本", _labels(app._build_msg_menu(idx)) ==
          ["复制", "选择文本", "引用回复"])

    # 打开文本窗 → 内容一致；拖选部分 → 复制
    app._select_text(idx)
    pump(0.3)
    viewers = [w for w in app.root.winfo_children()
               if w.__class__.__name__ == "TextViewer"]
    check("viewer opened", len(viewers) == 1, f"n={len(viewers)}")
    if viewers:
        v = viewers[0]
        content = v.text.get("1.0", "end-1c")
        check("viewer carries body", content == body, f"got={content!r}")
        # 选中"用于选择"五个字 → 复制
        v.text.configure(state="normal")
        s = content.index("用于选择")
        e = s + len("用于选择")
        v.text.tag_add("sel", f"1.0+{s}c", f"1.0+{e}c")
        v.text.configure(state="disabled")
        v._copy()
        check("copy selection to clipboard",
              app.root.clipboard_get() == "用于选择",
              f"got={app.root.clipboard_get()!r}")
        v.destroy()

    # 系统行无菜单
    pump(0.2)
    sys_idx = next((i for i, r in enumerate(app.msg_list._rows)
                    if r.tag == "sys"), None)
    check("sys row no menu", sys_idx is None or
          app._build_msg_menu(sys_idx) is None)

    print("\n".join(results))
    peer.send_frame({"t": "bye"})
    app.quit_app()
    print("GUI R12 SELECT SMOKE OK" if ok else "GUI R12 SELECT SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
