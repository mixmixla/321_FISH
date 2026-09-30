# -*- coding: utf-8 -*-
"""R13 冒烟：表情回应 / 消息转发 / 已读回执 / 消息置顶 四条 UI 链路。

- 消息右键菜单裁剪出 R13 三项（表情回应…/转发…/置顶）
- 置顶/取消置顶 → 服务器 pins 状态 + 顶部横幅显示/隐藏 + 菜单标签翻转
- 表情回应加/摘 → 本地历史写入 + 自己参与的回应主题色高亮
- 转发：图片行构造真实转发快照（image_path+占位文本）；文本消息构造 forward 快照
- 多选转发：图片+文本快照一并收集
- 图片真实转发到私聊：走文件传输（send_file 落点校验）
"""
import os
import socket
import sys
import threading
import time
import tkinter as tk
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


def _menu_labels(menu):
    if menu is None:
        return None
    n = menu.index("end") + 1
    out = []
    for i in range(n):
        try:
            out.append(menu.entrycget(i, "label"))
        except Exception:                       # separator 无 label
            out.append("---")
    return out


def main() -> int:
    def mark(tag: str) -> None:
        print(f"[smoke] {tag} t={time.time():.1f}", flush=True)

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
    mark("peer connected")
    core.start()
    deadline = time.time() + 6
    while not core.connected and time.time() < deadline:
        app.root.update()
        time.sleep(0.03)
    mark("core started")

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

    app.entry.insert("1.0", "R13 冒烟消息")
    app._on_entry_return()
    peer.send_frame({"t": "chat", "channel": "public", "text": "对方消息"})
    pump(1.0)
    mark("msgs loaded")

    rows = app.msg_list._rows
    own_idx = next(i for i, r in enumerate(rows)
                   if r.raw.get("uid") == core.uid and r.raw.get("text"))
    other_idx = next(i for i, r in enumerate(rows)
                     if r.raw.get("nick") == "对端乙" and r.raw.get("text"))

    # 1) 菜单裁剪出 R13 项：own 含 复制/选择文本/编辑/撤回/引用回复 + R13 三件套
    own_lbl = _menu_labels(app._build_msg_menu(own_idx))
    check("own menu 含 R13 三件套",
          own_lbl is not None and "表情回应…" in own_lbl and "转发…" in own_lbl
          and "置顶" in own_lbl and "---" in own_lbl)
    other_lbl = _menu_labels(app._build_msg_menu(other_idx))
    check("other menu 含 R13 三件套",
          other_lbl is not None and "表情回应…" in other_lbl and "转发…" in other_lbl
          and "置顶" in other_lbl)

    # 2) 置顶 → 服务器 pins 状态 + 横幅显示 + 菜单标签翻转为取消置顶
    app._toggle_pin_msg(other_idx)
    pump(1.2)
    mark("pin on")
    check("pin 上服务器状态", hub.pins.get("public", {}).get("seq") == rows[other_idx].raw.get("seq"))
    check("pin 横幅显示", app.pin_bar.winfo_ismapped())
    check("pin 后菜单变取消置顶",
          "取消置顶" in _menu_labels(app._build_msg_menu(other_idx)))
    # 取消置顶 → 横幅隐藏、服务器状态清空
    app._toggle_pin_msg(other_idx)
    pump(1.2)
    mark("pin off")
    check("unpin 服务器状态清空", not hub.pins.get("public"))
    check("unpin 横幅隐藏", not app.pin_bar.winfo_ismapped())

    # 3) 加/摘表情回应 → 本地历史写入 + 高亮
    app._react(own_idx, "👍")
    pump(1.2)
    mark("react on")
    own_raw = app.msg_list.get_row(own_idx)
    check("加回应 历史写入", "👍" in (own_raw.get("reactions") or {}))
    check("加回应 自己高亮", str(core.uid) in own_raw["reactions"]["👍"])
    app._react(own_idx, "👍")                 # 再点 → 摘下
    pump(1.2)
    mark("react off")
    own_raw2 = app.msg_list.get_row(own_idx)
    check("摘回应 历史清空", "👍" not in (own_raw2.get("reactions") or {}))

    # 4) 转发：图片行（无 seq）构造真实转发快照；文本行构造 forward 快照
    import os
    import tempfile
    tdir = tempfile.mkdtemp(prefix="fwdimg_")
    img_path = os.path.join(tdir, "photo.jpg")
    with open(img_path, "wb") as fh:
        fh.write(b"\xff\xd8\xff\xe0" + b"\x00" * 256)
    img_idx = app.msg_list.count
    app.msg_list.append({"uid": 3, "nick": "图片人", "channel": "public",
                         "ts": time.time(), "text": "海边日落",
                         "image_path": img_path})          # 无 seq：本地图片行
    captured = {}
    orig_pick = app._forward_pick
    app._forward_pick = lambda fwd: captured.update(fwd)
    app._forward(img_idx)
    app._forward_pick = orig_pick
    mark("snap image")
    check("转发图片行 构造快照",
          captured.get("image_path") == img_path
          and captured.get("text") == "[图片] photo.jpg"
          and captured.get("caption") == "海边日落")

    # 5) 多选：图片 + 文本 快照一并收集
    app.msg_list.enter_select_mode(img_idx)
    app.msg_list._sel_rows.add(other_idx)
    snaps = app._sel_forward_snaps()
    mark("multi snaps")
    check("多选快照 图片+文本齐收",
          len(snaps) == 2
          and any(s.get("image_path") == img_path for s in snaps)
          and any(s.get("text") == "对方消息" for s in snaps))
    app.msg_list.exit_select_mode()

    # 6) 图片真实转发到私聊目标 → send_file 落点 + 本地图片行
    app._forward_pick(captured)
    dlg = None
    for w in app.root.winfo_children():
        if isinstance(w, tk.Toplevel):
            dlg = w
            break
    check("转发选择器弹出", dlg is not None)
    if dlg is not None:
        lb = next(w for w in dlg.winfo_children() if isinstance(w, tk.Listbox))
        priv_idx = next((i for i in range(lb.size())
                         if lb.get(i) == "对端乙"), None)
        sent_files = []
        orig_send_file = core.files.send_file
        core.files.send_file = lambda p, to, caption="": (
            sent_files.append((p, to, caption)) or "fid-x")
        try:
            if priv_idx is None:
                check("私聊目标存在", False)
            else:
                lb.selection_set(priv_idx)
                fwd_btn = next(w for w in dlg.winfo_children()
                               if isinstance(w, tk.Button)
                               and str(w.cget("text")) == "转发")
                fwd_btn.invoke()
                app.root.update()
                mark("real fwd done")
                check("图片真实转发 send_file",
                      sent_files and sent_files[0][0] == img_path
                      and sent_files[0][2] == "海边日落")
                priv_uid = next((uid for uid, u in core.roster.items()
                                 if u.get("nick") == "对端乙"), None)
                check("转发图片 会话预览更新",
                      priv_uid is not None
                      and "[图片]" in (app._preview.get(("private", priv_uid)) or ("",))[0])
        finally:
            core.files.send_file = orig_send_file

    # 7) 文本消息转发 → 快照含 nick/text/seq
    app._forward_pick = lambda fwd: captured.update(fwd)
    app._forward(other_idx)
    app._forward_pick = orig_pick
    check("转发文本 构造快照",
          captured.get("text") == "对方消息"
          and captured.get("nick") == "对端乙"
          and captured.get("seq") == rows[other_idx].raw.get("seq"))

    # 5) 把文本快照真正发到公共频道 → 本端应收到的转发事件落成一条转发行
    if captured.get("seq"):
        core.send_chat(captured.get("text", ""), channel="public", forward=captured)
        pump(1.2)
        check("转发落成本端转发行",
              any((r.raw.get("forward") or {}).get("seq") == captured["seq"]
                  for r in app.msg_list._rows))

    print("\n".join(results))
    mark("results printed")
    peer.send_frame({"t": "bye"})
    app.quit_app()
    mark("quitted")
    print("GUI R13 SMOKE OK" if ok else "GUI R13 SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())