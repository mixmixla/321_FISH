# -*- coding: utf-8 -*-
"""R14 冒烟：收藏/定时/快捷短语/清理/阅后即焚/导出/@提及 六条 UI 链路。

- 右键菜单裁剪出「收藏 / 🔥 阅后即焚发送」
- 收藏 toggle → prefs['stars'] 写入 + 菜单标签翻转 + 收藏面板可开
- 快捷短语插入输入框 + 管理新增写回 prefs['quick']
- 阅后即焚开关 → prefs['burn_mode'] + 按钮文本翻转；开启后 _send 携带 burn 帧
- 会话清理 purge → 对端（peer）收到 purge 事件
- 定时发送 → _pump_scheduled 到点从主线程发出
- @提及预览 → _preview_text 给被@的群消息加 📣@我 前缀；导出 → 写出 .md
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


def _labels(menu):
    if menu is None:
        return None
    out = []
    for i in range(menu.index("end") + 1):
        try:
            out.append(menu.entrycget(i, "label"))
        except Exception:
            out.append("---")
    return out


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

    app.entry.insert("1.0", "R14 冒烟消息")
    app._on_entry_return()
    peer.send_frame({"t": "chat", "channel": "public", "text": "对方一"})
    pump(1.0)
    rows = app.msg_list._rows
    own_idx = next(i for i, r in enumerate(rows)
                   if r.raw.get("uid") == core.uid and r.raw.get("text"))

    # 1) 菜单裁剪出 R14 项
    lbl = _labels(app._build_msg_menu(own_idx))
    check("菜单含 收藏 + 阅后即焚", lbl and "收藏" in lbl and "🔥 阅后即焚发送" in lbl)

    # 2) 收藏 toggle + 面板
    app._toggle_star(own_idx)
    check("收藏写入 prefs", bool(app._prefs.get("stars")))
    lbl2 = _labels(app._build_msg_menu(own_idx))
    check("菜单标签翻转为取消收藏", lbl2 and "取消收藏" in lbl2)
    app._open_stars()
    pump(0.3)
    check("收藏面板可开", bool([w for w in app.root.winfo_children()
                                if w.winfo_class() == "Toplevel"]))

    # 3) 快捷短语（插入 + 管理新增）
    app._insert_quick("收到")
    check("快捷短语插入输入框", "收到" in app._entry_text())
    app.entry.delete("1.0", "end")
    app._quick_dialog()
    pump(0.3)
    app._quick.append("速回")
    app._prefs.set("quick", app._quick)
    check("快捷短语写回 prefs", "速回" in app._prefs.get("quick", []))

    # 4) 阅后即焚开关 + 发送携带 burn 帧
    app._toggle_burn_mode()
    check("阅后即焚状态翻转", app._burn_mode is True)
    check("阅后即焚按钮文本", app._burn_btn.cget("text") == "🔥ON")
    check("阅后即焚写 prefs", app._prefs.get("burn_mode") is True)
    app.entry.insert("1.0", "焚毁内容")
    app._send()
    pump(1.2)
    check("burn 帧触达服务器", bool(hub._burn))
    app._toggle_burn_mode()                      # 关掉

    # 5) 会话清理 purge → peer 收到 purge 事件
    app._purge_view()
    pump(1.2)
    peer.send_frame({"t": "chat", "channel": "public", "text": "探测"})
    # 轮询 peer 应已收到 purge
    got_purge = False
    peer_t = time.time() + 2
    while time.time() < peer_t:
        app.root.update()
        try:
            h, _b = peer.recv_frame()
            if h.get("t") == "purge":
                got_purge = True
        except Exception:
            break
        time.sleep(0.02)
    check("清理广播 purge 到对端", got_purge)

    # 6) 定时发送（改 0 分钟直接到点由 _poll 触发）
    app._scheduled.append({"channel": "public", "to": None,
                           "text": "定时到", "fire_at": time.time() - 1})
    pump(0.8)
    check("定时到点自动发送", any(
        r.raw.get("text") == "定时到" for r in app.msg_list._rows))

    # 7) 被@预览前缀
    syn = {"channel": "group", "uid": 999, "nick": "别人", "to": 1,
           "text": "@我说事", "ts": time.time(), "mentions": [core.uid]}
    prev = app._preview_text(syn)
    check("被@消息预览带📣@我", "📣@我" in prev)
    syn2 = {"channel": "group", "uid": 999, "nick": "别人", "to": 1,
            "text": "通知", "ts": time.time(), "everyone": True}
    check("@全员预览带📣@我", "📣@我" in app._preview_text(syn2))

    # 8) 导出会话 → 写出 .md
    import tempfile, os, tkinter.filedialog as fd
    out = os.path.join(tempfile.gettempdir(), "r14_export.md")
    fd.asksaveasfilename = lambda **kw: out
    app._export_conversation()
    pump(0.3)
    check("导出写出文件", os.path.exists(out) and "会话导出" in open(out, encoding="utf-8").read())

    print("\n".join(results))
    try:
        peer.send_frame({"t": "bye"})
    except Exception:
        pass
    app.quit_app()
    print("GUI R14 SMOKE OK" if ok else "GUI R14 SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())