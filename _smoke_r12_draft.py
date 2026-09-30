# -*- coding: utf-8 -*-
"""R12 冒烟：草稿自动保存（会话级 + 持久化）。

流程：
1. 公共频道输入草稿 → 切私聊 → 切回公共 → 草稿回填（会话级）
2. 私聊输入草稿 → 退出持久化 → 新实例**同名重连**（R12fix：昵称→uid 复用）
   → 公共/私聊草稿跨重启均恢复
3. 发送成功后草稿清除（切走再切回为空）
用独立 _tmp_gui/r12_prefs.json，避免污染共享 prefs.json（R4 教训）。
"""
import os
import socket
import threading
import time
from dataclasses import replace

from config import CFG
from crypto import client_handshake
from server import Hub, serve as serve_tcp
from client_core import ClientCore
from client import ChatWindow

PREFS = "_tmp_gui/r12_prefs.json"


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


def _launch(hub, port, nick: str, peer):
    core = ClientCore(host="127.0.0.1", port=port, nick=nick)
    app = ChatWindow(core, prefs_path=PREFS)
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

    return app, pump


def main() -> int:
    if os.path.exists(PREFS):
        os.remove(PREFS)
    cfg = replace(CFG, audit_dir="_tmp_gui/audit")
    hub = Hub(cfg=cfg, audit_dir="_tmp_gui/audit")
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)

    app, pump = _launch(hub, port, "草稿甲", None)
    peer = _peer(port, "对端乙")
    peer_uid = None
    deadline = time.time() + 6
    while time.time() < deadline:
        app.root.update()
        peer_uid = next((u["uid"] for u in app.core.roster.values()
                         if u["nick"] == "对端乙"), None)
        if peer_uid is not None:
            break
        time.sleep(0.03)

    ok = True
    results = []

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    # 1) 会话级：公共输入 → 切私聊 → 切回公共，草稿回填
    app.entry.insert("1.0", "公共草稿R12")
    app._switch_view("private", peer_uid)
    pump(0.2)
    check("switch away saves draft",
          app._drafts.get("public") == "公共草稿R12",
          f"drafts={app._drafts!r}")
    check("private entry empty on switch",
          app._entry_text() == "", f"got={app._entry_text()!r}")
    app.entry.insert("1.0", "私聊草稿X")
    app._switch_view("public", None)
    pump(0.2)
    check("switch back restores public draft",
          app._entry_text() == "公共草稿R12",
          f"got={app._entry_text()!r}")
    check("private draft saved",
          app._drafts.get("private:%d:%d" % (min(int(app.core.uid), peer_uid),
                                             max(int(app.core.uid), peer_uid)))
          == "私聊草稿X")

    # 2) 持久化：退出（_persist_drafts 写盘）→ 新实例**同名重连**（R12fix：
    #    昵称→uid 复用）→ 公共/私聊草稿跨重启均恢复
    app._persist_drafts()
    d = app._prefs.get("drafts", {})
    check("persisted to prefs", d.get("public") == "公共草稿R12"
          and "私聊草稿X" in list(d.values()),
          f"prefs_drafts={d!r}")
    app.quit_app()
    app2, pump2 = _launch(hub, port, "草稿甲", peer)   # 同名重连 → 复用原 uid
    pump2(0.3)
    check("restart restores public draft",
          app2._entry_text() == "公共草稿R12",
          f"got={app2._entry_text()!r}")
    app2._switch_view("private", peer_uid)
    pump2(0.2)
    check("restart restores private draft (uid reuse)",
          app2._entry_text() == "私聊草稿X",
          f"got={app2._entry_text()!r} app_uid={app2.core.uid}")
    app2._switch_view("public", None)
    pump2(0.2)

    # 3) 发送成功清草稿 + 私聊会话级往返
    app2.entry.delete("1.0", "end")
    app2.entry.insert("1.0", "这条会发出去")
    app2._send()
    pump2(0.3)
    check("send clears draft in mem",
          "public" not in app2._drafts, f"drafts={app2._drafts!r}")
    check("send clears draft on disk",
          "public" not in (app2._prefs.get("drafts", {}) or {}))
    app2._switch_view("private", peer_uid)
    pump2(0.2)
    # 先清掉跨重启恢复的私聊草稿「私聊草稿X」（R12fix 恢复验证已完成）
    app2.entry.delete("1.0", "end")
    app2.entry.insert("1.0", "清草稿私聊消息")
    app2._send()
    pump2(0.2)
    check("restored private draft cleared by send",
          "private:%d:%d" % (min(int(app2.core.uid), peer_uid),
                             max(int(app2.core.uid), peer_uid))
          not in app2._drafts,
          f"drafts={app2._drafts!r}")
    check("private entry empty after clear-send", app2._entry_text() == "",
          f"got={app2._entry_text()!r}")
    app2.entry.insert("1.0", "私聊草稿B")
    app2._switch_view("public", None)
    pump2(0.2)
    app2._switch_view("private", peer_uid)
    pump2(0.2)
    check("private draft roundtrip",
          app2._entry_text() == "私聊草稿B", f"got={app2._entry_text()!r}")
    app2._send()                       # 私聊发送 → 草稿清除
    pump2(0.3)
    app2._switch_view("public", None)
    pump2(0.2)
    app2._switch_view("private", peer_uid)
    pump2(0.2)
    check("private draft cleared after send",
          app2._entry_text() == "", f"got={app2._entry_text()!r}")

    print("\n".join(results))
    try:
        peer.send_frame({"t": "bye"})
    except Exception:
        pass
    app2.quit_app()
    print("GUI R12 DRAFT SMOKE OK" if ok else "GUI R12 DRAFT SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
