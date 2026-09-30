# -*- coding: utf-8 -*-
"""R11 冒烟：@提及 / 链接 富文本渲染。
发送含 @提及 与 http 链接 的消息 → 校验气泡里出现
- mention 色（紫色）文本 run ms、- link 色（蓝）文本 run 且带 r11lnk tag 的 <Button-1> 绑定。
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
from widgets import runs


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

    core = ClientCore(host="127.0.0.1", port=port, nick="富文本甲")
    app = ChatWindow(core)
    peer = _peer(port, "小明")
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

    # 对端发一条含 @提及 + 链接 的公开消息
    peer.send_frame({"t": "chat", "to": "public", "text": "开会了 @小明，文档见 https://example.com/demo 请查收",
                     "ch": "public"})
    pump(0.8)

    ml = app.msg_list
    ml.scroll_to_end()
    ml._render()
    app.root.update()

    pal = ml._pal
    link_fill, mention_fill = pal["link"], pal["mention"]
    link_items, mention_items = 0, 0
    link_tags = []
    for it in ml.find_all():
        try:
            tags = ml.itemcget(it, "tags") or ""
        except Exception:
            continue
        fill = ml.itemcget(it, "fill") if ml.type(it) == "text" else ""
        if fill == link_fill:
            link_items += 1
            if "r11lnk" in tags:
                link_tags.append(tags.split()[0])
        if fill == mention_fill:
            mention_items += 1

    check("renders mention-colored runs", mention_items >= 1, f"mention={mention_items}")
    check("renders link-colored runs", link_items >= 1, f"link={link_items}")

    bound = any(ml.tag_bind(t, "<Button-1>") for t in link_tags)
    check("link has click binding", bool(link_tags) and bound, str(link_tags))

    # 纯函数辅助校验
    segs = runs.tag_entities("给@小明看 https://a.com/b")
    check("tag_entities finds @ + url",
          any(k == runs.MENTION for _, k in segs)
          and any(k == runs.LINK for _, k in segs))

    print("\n".join(results))
    peer.send_frame({"t": "bye"})
    app.quit_app()
    print("GUI R11 RICH SMOKE OK" if ok else "GUI R11 RICH SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())