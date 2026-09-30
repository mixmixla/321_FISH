# -*- coding: utf-8 -*-
"""C3/C4 编辑·撤回·引用回复冒烟（双端端到端）。

- 乙发消息 → 甲收到
- 乙 edit → 甲原地更新并标注"已编辑"
- 乙 del  → 甲渲染「消息已撤回」（墓碑）
- 甲引用回复乙 → 乙收到的消息带 reply 快照；引用块在列表渲染为 ↩ 前缀
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

    def find_row(nick, text=None):
        for i, r in enumerate(app.msg_list._rows):
            if r.raw.get("nick") == nick and (text is None or r.raw.get("text") == text):
                return i, r
        return None, None

    # 1) 乙发公聊 → 甲显示
    peer.send_frame({"t": "chat", "channel": "public", "text": "原始文字", "ts": time.time()})
    pump(0.5)
    idx, row = find_row("对端乙", "原始文字")
    check("peer msg received", idx is not None)
    seq = row.raw.get("seq")
    check("peer msg has seq", seq is not None)

    # 2) 乙编辑 → 甲原地更新 + 已编辑标记（C3）
    peer.send_frame({"t": "edit", "seq": seq, "text": "已修改文字"})
    pump(0.5)
    idx2, row2 = find_row("对端乙", None)
    check("edit updates text", idx2 is not None and "已修改文字" in row2.body)
    check("edit marks edited", row2.raw.get("edited") is True and "已编辑" in row2.body)

    # 3) 乙撤回 → 甲渲染「消息已撤回」墓碑（C3）
    peer.send_frame({"t": "del", "seq": seq})
    pump(0.5)
    idx3, row3 = find_row("对端乙", None)
    check("del marks deleted", idx3 is not None and row3.body == "（消息已撤回）")
    check("del keeps seq tombstone", row3.raw.get("seq") == seq)

    # 4) 乙再发一条，甲引用它发送 → 乙收到 reply 快照（C4）
    peer.send_frame({"t": "chat", "channel": "public", "text": "需要被引用", "ts": time.time()})
    pump(0.5)
    ridx, rrow = find_row("对端乙", "需要被引用")
    check("new peer msg received", ridx is not None)
    app._quote(ridx)
    app.entry.insert("end", "这是我的回复")
    app._send()
    pump(0.5)
    # 轮询乙收到的帧里是否出现带 reply 的 chat
    got_reply = None
    chan = peer
    timeout = time.time() + 3
    while time.time() < timeout:
        try:
            h, _b = chan.recv_frame()
        except Exception:
            break
        if h.get("t") == "chat" and h.get("reply"):
            got_reply = h["reply"]
            break
        if h.get("t") == "chat" and h.get("text") == "这是我的回复":
            got_reply = h.get("reply")
            break
    check("sent msg carries reply snapshot",
          got_reply is not None and got_reply.get("nick") == "对端乙"
          and got_reply.get("text") == "需要被引用")

    # 5) 引用块在列表渲染（甲自己那条带 ↩ 前缀 + 待发快照已清空）
    mine_idx, mine_row = find_row("冒烟甲")
    check("own reply row rendered w/ ↩ prefix",
          mine_idx is not None and mine_row.body.startswith("↩ 对端乙: 需要被引用"))
    check("pending reply cleared after send", app._pending_reply is None)

    print("\n".join(results))
    peer.send_frame({"t": "bye"})
    app.quit_app()
    print("GUI EDIT/DEL/REPLY SMOKE OK" if ok else "GUI EDIT/DEL/REPLY SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())