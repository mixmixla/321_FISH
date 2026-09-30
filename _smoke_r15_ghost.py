# -*- coding: utf-8 -*-
"""R15 冒烟：全透明黑字模式（F1 切换）+ 跨会话全局字幕。

- 按 F1 → 进入 ghost：根窗 transparentcolor 置为挖空色、topmost=True、
  消息区换成全局最近跨会话消息（含不同频道）
- ghost 中实时收到新消息 → 直接滚入字幕
- 再按 F1 → 退出：透明色还原、topmost 关闭、当前会话历史还原
"""
import socket
import threading
import time
import tkinter as tk
from dataclasses import replace

from config import CFG
from crypto import client_handshake
from server import Hub, serve as serve_tcp
from client_core import ClientCore
from client import ChatWindow
from theme import GHOST, GHOST_PUNCH, GHOST_BLACK


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

    # 先在公聊/私聊各造一条消息，让跨会话历史有内容
    app.entry.insert("1.0", "公聊字幕一")
    app._on_entry_return()
    peer.send_frame({"t": "chat", "channel": "public", "text": "公聊字幕二"})
    peer.send_frame({"t": "chat", "channel": "private", "to": core.uid,
                     "text": "私聊字幕三"})
    pump(1.0)

    def tc():
        try:
            return str(app.root.attributes("-transparentcolor") or "")
        except tk.TclError:
            return "unknown"

    # 0) 默认：非 ghost
    check("初始不在 ghost", not app._ghost)
    check("初始无挖空色", tc() == "")

    # 1) F1 进入 ghost
    app.toggle_ghost(None)
    pump(0.6)
    check("进入 ghost 置标志", app._ghost)
    check("进入 ghost 挖空色", tc() == GHOST_PUNCH, f"(tc={tc()!r} GHOST_PUNCH={GHOST_PUNCH!r})")
    try:
        check("进入 ghost topmost", bool(app.root.attributes("-topmost")))
    except Exception:
        pass    # 部分平台不支持查询，跳过
    ghost_msgs = app.msg_list._rows
    bodies = [r.raw.get("text") for r in ghost_msgs]
    check("ghost 跨会话字幕含私聊",
          any("私聊字幕三" in (b or "") for b in bodies))
    check("ghost 消息区仅全局字幕(无频道切换)",
          len(ghost_msgs) >= 3 and all(r.raw.get("channel") for r in ghost_msgs))

    # 2) ghost 中实时收到新消息 → 直接滚入字幕
    before = app.msg_list.count
    peer.send_frame({"t": "chat", "channel": "public", "text": "实时字幕四"})
    pump(1.0)
    check("ghost 实时追加字幕", app.msg_list.count == before + 1)
    check("ghost 新消息在字幕中",
          any("实时字幕四" in (r.raw.get("text") or "")
              for r in app.msg_list._rows))

    # 3) 字幕衬底(Ctrl+→/←)：衬底档升高 → 气泡色变浅向白
    app.ghost_back_inc(None)
    pump(0.4)
    check("衬底增大 气泡变白", int(app._ghost_back * 10) > 0)
    app.ghost_back_dec(None)
    app.ghost_back_dec(None)
    app.ghost_back_dec(None)
    pump(0.4)
    check("衬底回0 气泡回挖空", app._skin["bubble_out"] == GHOST_PUNCH,
          f"(back={app._ghost_back})")
    check("衬底0 文字仍黑", app._skin["normal"] == GHOST_BLACK)

    # 4) 频道过滤(F2)：循环到仅公聊 → 私聊字幕被滤掉
    app.ghost_cycle_filter(None)   # all->public
    pump(0.4)
    check("过滤=public", app._ghost_filter == "public")
    pub_bodies = [r.raw.get("text") for r in app.msg_list._rows]
    check("过滤后私聊字幕剔除",
          all("私聊字幕三" not in (b or "") for b in pub_bodies))
    app.ghost_cycle_filter(None)   # public->atme
    app.ghost_cycle_filter(None)   # atme->all
    pump(0.4)
    check("过滤循环回 all", app._ghost_filter == "all")

    # 5) R17 黑字描边(F3)开关：进入 ghost 默认开、可关可开、幂等
    check("进入 ghost 默认开描边", app._ghost_halo_on)
    app.msg_list.set_halo("#ffffff")
    app.msg_list._delete_items()
    y = 0
    for i, row in enumerate(app.msg_list._rows):
        y += app.msg_list._draw_row(i, row, y, 400)
    halo_white = any(app.msg_list.itemcget(i, "fill") == "#ffffff"
                     and app.msg_list.type(i) == "text"
                     for i in app.msg_list._item_ids)
    check("描边开启 文字有白光晕副本", halo_white)
    app.ghost_toggle_halo(None)    # 关描边
    pump(0.4)
    check("描边可关闭", not app._ghost_halo_on and app.msg_list._halo is None)
    app.ghost_toggle_halo(None)    # 再开
    pump(0.4)
    check("描边可重开", app._ghost_halo_on and app.msg_list._halo == "#ffffff")

    # 6) F1 退出 ghost
    app.toggle_ghost(None)
    pump(0.6)
    check("退出 ghost 清标志", not app._ghost)
    check("退出 ghost 还原挖空色", tc() == "")
    try:
        check("退出 ghost 关 topmost", not app.root.attributes("-topmost"))
    except Exception:
        pass
    # 退出后当前会话历史恢复（处于公聊，应含公聊消息）
    cur_bodies = [r.raw.get("text") for r in app.msg_list._rows]
    check("退出后恢复当前会话历史",
          any("公聊字幕一" in (b or "") for b in cur_bodies))

    print("\n".join(results))
    peer.send_frame({"t": "bye"})
    app.quit_app()
    print("GUI R15 SMOKE OK" if ok else "GUI R15 SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())