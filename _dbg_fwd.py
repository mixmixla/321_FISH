# -*- coding: utf-8 -*-
"""最小复现：_forward_pick 群目标为何不调 send_chat。"""
import os
import sys
import tempfile
import time
import tkinter as tk

from client import ChatWindow

root = tk.Tk()
root.withdraw()


class _Files:
    def __init__(self):
        self.sent = []

    def send_file(self, path, to, caption=""):
        self.sent.append((path, to, caption))
        return "fid-x"


class _Core:
    def __init__(self):
        self.uid = 1
        self.roster = {2: {"nick": "乙"}}
        self.groups = {10: {"name": "测试群"}}
        self.files = _Files()
        self.chats = []

    def send_chat(self, text="", sticker="", channel="public", to=None,
                  forward=None, fwd_seqs=None, fwd_from=None):
        self.chats.append((text, sticker, channel, to, forward))
        print(f"[dbg] send_chat text={text!r} ch={channel} to={to} "
              f"fwd={forward}", flush=True)


class _MsgList:
    def exit_select_mode(self, notify=True):
        print("[dbg] exit_select_mode", flush=True)


app = ChatWindow.__new__(ChatWindow)
app.root = root
app._dp = {"win": "#f0f0f0"}
app._skin = {}
app._apply_apple_dialog = lambda dlg, title=None: None
app.view = ("public", None)
app.core = _Core()
app._append_sys = lambda *a, **k: print("[dbg] sys:", a, flush=True)
app.msg_list = _MsgList()

tdir = tempfile.mkdtemp(prefix="dbg_")
img = os.path.join(tdir, "p.png")
with open(img, "wb") as f:
    f.write(b"x")

snap = app._fwd_snapshot({"uid": 2, "nick": "乙", "channel": "private",
                          "to": 1, "ts": time.time(), "image_path": img,
                          "text": "cap"})
print("[dbg] snap:", snap, flush=True)
app._forward_pick([snap])
root.update()

dlg = None
for w in root.winfo_children():
    if isinstance(w, tk.Toplevel):
        dlg = w
        break
print("[dbg] dlg:", dlg, flush=True)
if dlg is not None:
    lb = next(w for w in dlg.winfo_children() if isinstance(w, tk.Listbox))
    print("[dbg] items:", [lb.get(i) for i in range(lb.size())], flush=True)
    idx = next(i for i in range(lb.size()) if lb.get(i) == "测试群")
    print("[dbg] group idx:", idx, flush=True)
    lb.selection_set(idx)
    print("[dbg] curselection:", lb.curselection(), flush=True)
    btn = next(w for w in dlg.winfo_children()
               if isinstance(w, tk.Button) and str(w.cget("text")) == "转发")
    print("[dbg] btn:", btn.cget("text"), flush=True)
    btn.invoke()
    root.update()
print("[dbg] files.sent:", app.core.files.sent, flush=True)
print("[dbg] chats:", app.core.chats, flush=True)
root.destroy()
