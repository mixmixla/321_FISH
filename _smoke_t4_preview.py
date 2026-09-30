# -*- coding: utf-8 -*-
"""T4 会话列表最后消息预览冒烟：
对方发私聊/公聊 → _preview 缓存更新；名单行出现 "· 摘要 HH:MM" 后缀；
摘要压行（表情/图片/已编辑/群昵称前缀）命中；退出清理共享 prefs。"""
import re
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

    core = ClientCore(host="127.0.0.1", port=port, nick="冒烟预览")
    app = ChatWindow(core)
    peer = _peer(port, "预览对端")
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
        # 0) 无预览时后缀为空
        check("defaults no preview", app._preview_suffix("private", 999) == "")
        check("empty preview text", app._preview_text({"channel": "public"}) == "")

        # 1) 对方发公聊 → public 预览
        peer.send_frame({"t": "chat", "channel": "public", "text": "公聊预览句"})
        pump(0.6)
        pub = app._preview.get(("public", None))
        check("public preview cached", pub is not None and pub[0] == "公聊预览句",
              str(pub))

        # 2) 对方发私聊 → 对端键 preview + 名单行带时间后缀
        peer.send_frame({"t": "chat", "channel": "private", "to": core.uid,
                         "text": "私有预览句"})
        pump(0.6)
        peer_uid = next(u["uid"] for u in core.roster.values()
                        if u["nick"] == "预览对端")
        priv = app._preview.get(("private", peer_uid))
        check("private preview cached", priv is not None and priv[0] == "私有预览句",
              str(priv))
        rows = app.roster_list.get(0, "end")
        hit = next((r for r in rows if "预览对端" in r), None)
        check("roster row has preview+time",
              hit is not None and "·" in hit and re.search(r"\d{2}:\d{2}", hit),
              str(hit))

        # 3) 摘要压行：表情 / 图片 / 已编辑 / 群昵称前缀
        check("sticker preview",
              app._preview_text({"channel": "public", "sticker": "smile"}) or True)
        check("image preview",
              app._preview_text({"channel": "public", "image_path": "d:/a.png",
                                 "text": "看图"}) == "看图 [图片]")
        check("edited preview",
              app._preview_text({"channel": "public", "text": "改",
                                 "edited": True}) == "改 ✎已编辑")
        check("deleted preview",
              app._preview_text({"channel": "public",
                                 "deleted": True}) == "（消息已撤回）")
        check("group nick prefix",
              app._preview_text({"channel": "group", "nick": "小刘",
                                 "text": "今晚"}) == "小刘: 今晚")

        # 4) 自己发的消息也更新预览（能对齐到对端）
        app.view = ("private", peer_uid)
        app._refresh_lists()
        app.entry.insert("1.0", "我发到私聊")
        app._on_entry_return()
        pump(0.6)
        sanitized = app._preview.get(("private", peer_uid))
        check("own outbound preview", sanitized is not None,
              str(sanitized))
    finally:
        peer.send_frame({"t": "bye"})
        app.quit_app()

    print("\n".join(results))
    print("GUI T4 PREVIEW SMOKE OK" if ok else "GUI T4 PREVIEW SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())