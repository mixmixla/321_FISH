# -*- coding: utf-8 -*-
"""R31C（发送失败红感叹号 + 点击重发）冒烟：
- MsgList 级：failed 行渲染、❗ 点击回调、drop_local_row 移除
- Client 级：发送失败 → 本地失败气泡；点击重发成功 → 行移除 + 系统提示
"""
import socket
import threading
import time
from dataclasses import replace

import tkinter as tk

from config import CFG
from server import Hub, serve as serve_tcp
from client_core import ClientCore
from client import ChatWindow


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    cfg = replace(CFG, audit_dir="_tmp_gui/audit")
    hub = Hub(cfg=cfg, audit_dir="_tmp_gui/audit")
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)

    core = ClientCore(host="127.0.0.1", port=port, nick="重发冒烟")
    app = ChatWindow(core)
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
        pump(0.6)
        # 1. MsgList 级：failed 行 + ❗ 点击回调
        clicked = []
        app.msg_list.set_sel_cb(app.msg_list._on_sel_change)  # 保持原回调
        app.msg_list._on_failed = lambda idx: clicked.append(idx)
        app.msg_list.append({"seq": None, "uid": core.uid,
                             "nick": "我", "text": "失败消息",
                             "ts": 1700000000, "failed": True})
        pump(0.4)
        fidx = len(app.msg_list._rows) - 1
        check("failed 行已追加",
              app.msg_list.get_row(fidx).get("failed") is True)
        app.msg_list._on_failed(fidx)
        check("❗ 回调携带行号", clicked == [fidx], str(clicked))

        # 2. drop_local_row 按身份移除
        raw = app.msg_list.get_row(fidx)
        check("移除失败行", app.msg_list.drop_local_row(raw))
        check("行数回落", app.msg_list.get_row(fidx) is None)
        check("重复移除返回 False", not app.msg_list.drop_local_row(raw))

        # 3. Client 级：发送失败 → 本地失败气泡
        before = len(app.msg_list._rows)
        core.send_chat = lambda *a, **k: False
        app.entry.delete("1.0", "end")
        app.entry.insert("1.0", "这条会失败")
        app._send()
        pump(0.4)
        frow = app.msg_list.get_row(len(app.msg_list._rows) - 1)
        check("发送失败出现失败气泡",
              frow and frow.get("failed") and frow.get("text") == "这条会失败",
              str(frow))
        check("失败气泡带重发参数",
              frow.get("resend", {}).get("channel") == "public")

        # 4. 点击重发成功 → 行移除 + 系统提示
        calls = []
        core.send_chat = lambda text, **k: calls.append((text, k)) or True
        app._resend_failed(len(app.msg_list._rows) - 1)
        pump(0.4)
        check("重发调用 send_chat", len(calls) == 1 and
              calls[0][0] == "这条会失败", str(calls))
        check("重发成功移除失败行",
              not (app.msg_list.get_row(len(app.msg_list._rows) - 1) or {})
              .get("failed"))
        check("系统提示已重新发送",
              any("已重新发送" in r.body for r in app.msg_list._rows
                  if r.tag == "sys"))

        # 5. 重发仍失败 → 行保留
        core.send_chat = lambda *a, **k: False
        app.entry.delete("1.0", "end")
        app.entry.insert("1.0", "再次失败")
        app._send()
        pump(0.3)
        n_fail_before = sum(1 for r in app.msg_list._rows
                            if r.raw.get("failed"))
        app._resend_failed(len(app.msg_list._rows) - 1)
        pump(0.3)
        n_fail_after = sum(1 for r in app.msg_list._rows
                           if r.raw.get("failed"))
        check("重发失败行保留", n_fail_after == n_fail_before,
              f"{n_fail_before}->{n_fail_after}")
        check("失败提示", any("重发仍失败" in r.body
                              for r in app.msg_list._rows if r.tag == "sys"))
    except Exception as e:
        ok = False
        results.append(f"[FAIL] 异常: {type(e).__name__}: {e}")
    finally:
        stop.set()
        time.sleep(0.2)

    print("\n".join(results))
    print("R31C 冒烟:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
