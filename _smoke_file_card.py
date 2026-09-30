# -*- coding: utf-8 -*-
"""T1 文件卡片冒烟：驱动 app._on_file_progress 伪造事件，
验证卡片创建/进度更新/完成保留+打开目录/失败销毁。"""
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

    core = ClientCore(host="127.0.0.1", port=port, nick="冒烟丁")
    app = ChatWindow(core)
    peer = _peer(port, "文件对手")
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
        # 1) 发送方：进度事件 → 卡片创建并显示文件名/大小
        fid = "tc1"
        app._on_file_progress({"file_id": fid, "state": "sending",
                               "filename": "报表.xlsx", "total": 5 * 1048576,
                               "name": "报表.xlsx", "size": 5 * 1048576,
                               "pct": 20, "text": "报表.xlsx 20%"})
        pump(0.2)
        card = app._xfer_bars.get(fid)
        check("send card created", card is not None)
        name_label, size_label = card.row1.winfo_children()
        check("card shows filename", "报表.xlsx" in name_label.cget("text"))
        check("card shows size", "5.0MB" in size_label.cget("text") or "5MB" in size_label.cget("text"),
              size_label.cget("text"))
        check("card progress 20 fill",
              int(card._fill_f.cget("width")) == max(1, int(card._bar_w * 0.2)))

        # 2) 进度推进到 100
        app._on_file_progress({"file_id": fid, "state": "sending",
                               "filename": "报表.xlsx", "total": 5 * 1048576,
                               "pct": 100, "text": "全部块已发送，等待校验…"})
        pump(0.2)
        check("card progress 100",
              int(card._fill_f.cget("width")) == card._bar_w)

        # 3) 完成：发送方不提供打开目录（role=send 无 path），卡片保留
        app._on_file_progress({"file_id": fid, "state": "done",
                               "filename": "报表.xlsx", "name": "报表.xlsx",
                               "role": "send", "pct": 100,
                               "text": "文件已送达: 报表.xlsx"})
        pump(0.2)
        check("done keeps card", app._xfer_bars.get(fid) is card)
        check("done no open button for send", card._open is None)
        check("done appends sys msg",
              any(r.tag == "sys" and "文件已送达" in r.body for r in app.msg_list._rows))

        # 4) 接收方完成：提供 path → 出现「打开目录」按钮
        rid = "tc2"
        app._on_file_progress({"file_id": rid, "state": "done",
                               "filename": "资料.txt", "name": "资料.txt",
                               "role": "receive", "pct": 100,
                               "path": r"_tmp_gui/x/资料.txt",
                               "text": "文件已接收: 资料.txt"})
        pump(0.2)
        rcard = app._xfer_bars.get(rid)
        check("receive done card", rcard is not None)
        check("receive done open button", rcard._open is not None
              and rcard._open.cget("text") == "打开目录")

        # 5) 失败/拒绝：卡片销毁 + 系统消息
        ffid = "tc3"
        app._on_file_progress({"file_id": ffid, "state": "rejected",
                               "name": "a.txt", "text": "已拒绝文件"})
        pump(0.2)
        check("rejected destroys card", ffid not in app._xfer_bars)
        check("rejected sys msg",
              any(r.tag == "sys" and "已拒绝" in r.body for r in app.msg_list._rows))

        # 6) 无 fid 的全局失败：不建卡、仅系统消息
        app._on_file_progress({"state": "failed", "text": "文件不存在"})
        pump(0.2)
        check("no-fid failure sys msg",
              any(r.tag == "sys" and "文件不存在" in r.body for r in app.msg_list._rows))

    finally:
        peer.send_frame({"t": "bye"})
        app.quit_app()

    print("\n".join(results))
    print("GUI FILE CARD SMOKE OK" if ok else "GUI FILE CARD SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())