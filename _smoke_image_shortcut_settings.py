# -*- coding: utf-8 -*-
"""R5 冒烟：A7 图片消息渲染 + r5b 快捷键设置/改绑。

- 上半场（私有会话）：
  - 发送方视角 append 一条 image 消息 → msg_list 出现图片行（[图片] 占位 + 渲染不崩）
  - 模拟收到 image 事件 → 也产生一条图片行
- 下半场（快捷键）：
  - _shortcut_settings() 打开设置页不报错
  - 改绑 ctrl_w → <Control-y> 并 _bind_shortcuts() 立即可见生效
  - _mark_current_read() 清除当前会话未读
  - 结束前清空 hotkeys 偏好，避免污染共享 prefs.json
"""
import os
import socket
import threading
import time
from dataclasses import replace

from PIL import Image

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

    core = ClientCore(host="127.0.0.1", port=port, nick="冒烟丙")
    app = ChatWindow(core)
    peer = _peer(port, "图片接收君")
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

    peer_uid = next((uid for uid, u in core.roster.items()
                     if u["nick"] == "图片接收君"), None)

    ok = True
    results = []

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    try:
        # 进入私有会话（否则图片行 out-of-view 走未读累积）
        app.view = ("private", peer_uid)
        app._load_view_history()
        pump(0.3)

        # ---- A7 发送方：直接追加一条本地图片消息 ----
        img = "_tmp_gui/smoke_img.png"
        os.makedirs("_tmp_gui", exist_ok=True)
        Image.new("RGB", (120, 80), (0, 0, 200)).save(img)
        fid = "imgf1"
        app._append_msg({"t": "image", "channel": "private", "uid": core.uid,
                         "to": peer_uid, "nick": core.nick, "file_id": fid,
                         "image_path": os.path.abspath(img), "ts": time.time()})
        pump(0.6)                                   # 子线程缩略图 + 渲染
        img_rows = [r for r in app.msg_list._rows
                    if r.image_path and r.image_path.endswith("smoke_img.png")]
        check("sender image row appended", len(img_rows) == 1)
        check("image body placeholder text",
              "[图片]" in app.msg_list.body_text(app.msg_list.count - 1) if img_rows else False)

        # ---- A7 接收方事件：_handle 收到 image → 也出图片行 ----
        img2 = "_tmp_gui/smoke_img2.png"
        Image.new("RGB", (60, 60), (0, 200, 0)).save(img2)
        app._handle({"t": "image", "channel": "private", "uid": peer_uid,
                     "to": core.uid, "nick": "图片接收君", "file_id": "imgf2",
                     "image_path": os.path.abspath(img2), "ts": time.time()})
        pump(0.6)
        rows2 = [r for r in app.msg_list._rows
                 if r.image_path and r.image_path.endswith("smoke_img2.png")]
        check("received image event row", len(rows2) == 1)

        # ---- r5b：设置页可打开 ----
        app._shortcut_settings()
        pump(0.2)
        check("shortcut settings dialog opens", True)

        # ---- r5b：改绑 ctrl_w → <Control-y> 立即生效 ----
        app._prefs.set("hotkeys", {"ctrl_w": "<Control-y>"})
        app._bind_shortcuts()
        bound = [p for p, _ in app._bound]
        check("rebind applied to registry",
              "<Control-y>" in bound and "<Control-w>" not in bound,
              f"bound={bound}")

        # ---- r5b：Ctrl+R 标记当前已读（未满即清零） ----
        app._unread[("private", peer_uid)] = 5
        app._refresh_lists()
        app._mark_current_read()
        check("mark-read clears unread", app._unread.get(("private", peer_uid), 0) == 0)

        # 面板里 restore 按钮命令可调用（不崩）
        app._prefs.set("hotkeys", {})
        app._bind_shortcuts()
    finally:
        app._prefs.set("hotkeys", {})           # 清空偏好，避免污染共享 prefs.json
        app._bind_shortcuts()

    print("\n".join(results))
    peer.send_frame({"t": "bye"})
    app.quit_app()
    print("GUI IMAGE+SHORTCUTSET SMOKE OK" if ok else "GUI IMAGE+SHORTCUTSET SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())