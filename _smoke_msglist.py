# -*- coding: utf-8 -*-
"""A1 GUI 冒烟：真实 Hub + 真实 ClientCore + ChatWindow，注入 5000 条公聊消息，
验证虚拟化消息列表端到端渲染（count 正确 / 可见元素有界 / 吸底 / 滚动不崩）。"""
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


def _inject(port: int, n: int) -> None:
    """第二个客户端：连上后向公共频道灌 n 条消息（后台读线程排空自己的回显，
    否则服务器广播给发送者时 sendall 会因发送者不读而阻塞，拖垮整条链路）。"""
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    chan = client_handshake(sock)
    sock.settimeout(None)                # 握手后转阻塞写，避免 sendall 超时
    chan.send_frame({"t": "hello", "nick": "灌水机"})
    deadline = time.time() + 5
    while time.time() < deadline:
        h, _b = chan.recv_frame()
        if h.get("t") == "welcome":
            break

    def _drain():
        try:
            while True:
                chan.recv_frame()
        except Exception:
            pass

    threading.Thread(target=_drain, daemon=True).start()   # 排空回显，模拟真实客户端
    for i in range(n):
        chan.send_frame({"t": "chat", "channel": "public",
                         "text": f"压力消息第 {i} 条，长度补足 30 字_" * 1})
    time.sleep(1.0)
    sock.close()


def main() -> int:
    cfg = replace(CFG, audit_dir="_tmp_gui/audit")
    hub = Hub(cfg=cfg, audit_dir="_tmp_gui/audit")
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)

    pushed = [0]
    evt_counts = {}
    core = ClientCore(host="127.0.0.1", port=port, nick="冒烟甲",
                      on_event=lambda ev: (
                          pushed.__setitem__(0, pushed[0] + 1)
                          if ev.get("t") == "chat" else
                          evt_counts.__setitem__(ev.get("t"),
                                                 evt_counts.get(ev.get("t"), 0) + 1)
                      ))
    app = ChatWindow(core)
    _orig_load_view = ChatWindow._load_view_history
    def _traced_load_view(self):
        before = self.msg_list.count
        _orig_load_view(self)
        print(f"  [load_view] {self.view} hist={len(self.core.history('public', None)) if self.view[0]=='public' else '?'} count {before} -> {self.msg_list.count}")
    ChatWindow._load_view_history = _traced_load_view
    core.start()

    deadline = time.time() + 6
    while not core.connected and time.time() < deadline:
        app.root.update()
        time.sleep(0.03)

    N = 5000
    t0 = time.time()
    inject = threading.Thread(target=_inject, args=(port, N), daemon=True)
    inject.start()
    # 泵事件直到消息收齐（GUI 主线程轮询路径 = _poll 的 after 链）
    last_log = 0.0
    while app.msg_list.count < N and time.time() - t0 < 30:
        app.root.update()
        time.sleep(0.02)
        now = time.time() - t0
        if now - last_log >= 5:
            last_log = now
            print(f"  …t={now:5.1f}s pushed={pushed[0]:5d} msgs={app.msg_list.count:5d}")
    app.root.update()
    app.root.update()
    print("DIAG state=", core.state, "connected=", core.connected,
          "uid=", core.uid, "events=", core.events.qsize(),
          "pushed=", pushed[0], "msgs=", app.msg_list.count,
          "reader_alive=", core._reader.is_alive(),
          "yview=", tuple(round(v, 4) for v in app.msg_list.yview()),
          "at_bottom=", app.msg_list.at_bottom,
          "evt_types=", evt_counts,
          "hist_public=", len(core.history("public")),
          "elapsed=", round(time.time() - t0, 2))

    count = app.msg_list.count
    items = len(app.msg_list._item_ids)
    at_bottom = app.msg_list.at_bottom
    cum_ok = app.msg_list._cum[-1] > 0 and app.msg_list._cum == sorted(app.msg_list._cum)
    # 唯一消息数：服务器全局 seq 去重后应恰好 = N（历史装载与实时事件不重复）
    uniq = len({r.raw.get("seq") for r in app.msg_list._rows
                if r.raw.get("seq") is not None})
    sys_n = sum(1 for r in app.msg_list._rows if r.tag == "sys")

    # 滚动到中部再验证有界
    app.msg_list.yview_moveto(0.5)
    app.msg_list._render()
    items_mid = len(app.msg_list._item_ids)
    ok = True
    for name, cond in [
        ("uniq msgs == 5000", uniq == N),
        ("no dup (count<=N+sys)", count <= N + sys_n),
        # R12：同 uid 连续消息分组 → 行高变矮，可见行数略增；上限放宽但仍远小于 N
        ("visible bounded", items <= 160 and items_mid <= 160),
        ("at bottom", at_bottom),
        ("cum monotonic", cum_ok),
    ]:
        print(f"[{'OK' if cond else 'FAIL'}] {name}  (count={count} uniq={uniq} "
              f"sys={sys_n} items={items} mid={items_mid} bottom={at_bottom})")
        ok = ok and cond

    app.quit_app()
    stop.set()
    time.sleep(0.3)
    print("GUI SMOKE", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
