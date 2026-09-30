# -*- coding: utf-8 -*-
"""C1 聊天内搜索冒烟（含跨端命中 + 高亮 + 上下条导航两种协议）：
- 注入实况消息后 search_all 命中计数正确
- 上下条导航循环切换活动命中
- 命中行渲染高亮、当前命中用深色
- Ctrl+F 开关搜索条
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

    def send_many(n: int, text: str, fill: str = "无关内容"):
        for i in range(n):
            peer.send_frame({"t": "chat", "channel": "public",
                             "text": f"{fill} #{i} {text}", "ts": time.time()})

    ok = True
    results = []

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    # 1) Ctrl+F 默认隐藏 → 呼出搜索条（用 winfo_manager 判定，映射时机无关紧要）
    check("search bar hidden by default", app.chat_search.winfo_manager() == "")
    app._focus_search()
    pump(0.2)
    check("ctrl+f shows search bar", app.chat_search.winfo_manager() == "grid")

    # 2) 无匹配词 → 计数 0/0 且无命中高亮
    app.chat_search_entry.delete(0, "end")
    app.chat_search_entry.insert(0, "zzz不存在词")
    app._do_chat_search()
    pump(0.2)
    check("no-match count 0", app.msg_list.search_count() == 0)
    check("no-match no highlight", len(app.msg_list._hit_idx) == 0)

    # 3) 注入含命中词的消息，检索命中数正确 + 高亮命中行
    send_many(3, "目标词汇")
    pump(1.0)
    app.chat_search_entry.delete(0, "end")
    app.chat_search_entry.insert(0, "目标词汇")
    n = app._do_chat_search()
    pump(0.2)
    hit_count = app.msg_list.search_count()
    check("search finds 3 hits", hit_count == 3 and n == 3)
    hit_rows = [i for i, r in enumerate(app.msg_list._rows)
                if "目标词汇" in r.body]
    check("hit rows highlighted",
          app.msg_list._hit_idx == set(hit_rows) and len(hit_rows) == 3)

    # 4) 上下导航循环切换活动命中
    app._chat_search_goto(1)
    pump(0.2)
    check("next sets active 0->first", app.msg_list.search_active_index() == 0)
    before = app.msg_list.search_active_index()
    app._chat_search_goto(1)
    app._chat_search_goto(1)
    app._chat_search_goto(1)          # 第4次回绕到0
    pump(0.2)
    check("next loops back", app.msg_list.search_active_index() == 0)
    app._chat_search_goto(-1)
    pump(0.2)
    check("prev wraps to last", app.msg_list.search_active_index() == 2)

    # 5) 计数显示 idx/n
    app._update_search_count()
    check("count label 3/3", app.chat_search_count.cget("text") == "3/3")

    # 6) 关闭搜索条 → 高亮清除
    app._close_chat_search()
    pump(0.2)
    check("close hides bar", app.chat_search.winfo_manager() == "")
    check("close clears highlight", len(app.msg_list._hit_idx) == 0
          and app.msg_list.search_count() == 0)

    print("\n".join(results))
    peer.send_frame({"t": "bye"})
    app.quit_app()
    print("GUI SEARCH SMOKE OK" if ok else "GUI SEARCH SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())