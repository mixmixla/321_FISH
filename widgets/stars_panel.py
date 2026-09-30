# -*- coding: utf-8 -*-
"""widgets/stars_panel.py —— R14 收藏/星标面板：跨会话聚合浏览与跳转。

`_stars` 结构（来自 prefs['stars']，本地快照，不做服务器协调）：
    { convo_key: { seq: {nick,text,ts,channel} } }

双击条目回调 on_pick(key) 由调用方（client）解析键并 `_switch_view` 跳转。
"""
import time
import tkinter as tk


class StarsPanel(tk.Toplevel):
    """收藏面板：只读列表 + 双击跳转（用户已收藏的本地聚合）。"""

    def __init__(self, master, stars: dict, on_pick) -> None:
        super().__init__(master)
        self.title("★ 收藏")
        self.transient(master)
        self.resizable(True, True)
        self._stars = stars
        self._on_pick = on_pick
        top = tk.Frame(self)
        top.pack(fill="x", padx=8, pady=(8, 4))
        self._label = tk.Label(top, text="")
        self._label.pack(side="left")
        tk.Label(top, text="双击跳转到原会话", fg="#999").pack(side="right")
        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.listbox = tk.Listbox(body, height=10, width=64,
                                  activestyle="none")
        sb = tk.Scrollbar(body, command=self.listbox.yview)
        self.listbox.config(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self._seqs = []
        self._reload()
        self.listbox.bind("<Double-Button-1>", self._on_double)
        self.listbox.bind("<Return>", self._on_double)

    def _reload(self) -> None:
        self.listbox.delete(0, "end")
        self._seqs = []
        for key, seqs in self._stars.items():
            for seq, snap in sorted(seqs.items(),
                                    key=lambda kv: kv[1].get("ts", 0)):
                self._seqs.append((key, seq))
                text = (snap.get("text") or "").replace("\n", " ")
                at = time.strftime("%m-%d %H:%M",
                                   time.localtime(snap.get("ts", 0)))
                who = snap.get("nick") or "?"
                self.listbox.insert("end",
                                    f"[{key}] {at}  {who}: {text[:40]}")
        self._label.config(text=f"共 {len(self._seqs)} 条收藏")

    def _on_double(self, _ev=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        key, seq = self._seqs[sel[0]]
        self._on_pick(key, seq)          # 回调传 (会话键, seq) → 切会话并定位该消息
        self.destroy()


class SnoozePanel(tk.Toplevel):
    """R69C11「稍后处理」清单：列出本地「标为未读」的会话。

    marks 结构：[{"key": str, "label": str, "preview": str}, ...]
    - 双击条目 → on_pick(key)（调用方切会话，打开即自动清标记）
    - 「✓ 已处理」按钮 → on_clear(key)（仅清除标记，不跳转）
    """

    def __init__(self, master, marks: list, on_pick, on_clear=None) -> None:
        super().__init__(master)
        self.title("⏳ 稍后处理")
        self.transient(master)
        self._marks = list(marks)
        self._on_pick = on_pick
        self._on_clear = on_clear
        top = tk.Frame(self)
        top.pack(fill="x", padx=8, pady=(8, 4))
        self._label = tk.Label(top, text="")
        self._label.pack(side="left")
        tk.Label(top, text="双击跳转 / 选中后可标为已处理", fg="#999").pack(side="right")
        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.listbox = tk.Listbox(body, height=10, width=60, activestyle="none")
        sb = tk.Scrollbar(body, command=self.listbox.yview)
        self.listbox.config(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        btns = tk.Frame(self)
        btns.pack(fill="x", padx=8, pady=(0, 8))
        tk.Button(btns, text="✓ 已处理", command=self._on_clear_sel).pack(side="left")
        tk.Button(btns, text="关闭", command=self.destroy).pack(side="right")
        self._reload()
        self.listbox.bind("<Double-Button-1>", self._on_double)
        self.listbox.bind("<Return>", self._on_double)

    def _reload(self) -> None:
        self.listbox.delete(0, "end")
        for m in self._marks:
            pv = (m.get("preview") or "").replace("\n", " ")
            self.listbox.insert("end", f"{m.get('label', '?')}  ·  {pv[:44]}")
        self._label.config(text=f"待处理 {len(self._marks)} 项")

    def _on_double(self, _ev=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        key = self._marks[sel[0]].get("key")
        self.destroy()
        if key and self._on_pick:
            self._on_pick(key)           # 跳转并打开会话（自动清标记）

    def _on_clear_sel(self) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        i = sel[0]
        key = self._marks[i].get("key")
        self._marks.pop(i)
        self._reload()
        if key and self._on_clear:
            self._on_clear(key)
        if not self._marks:
            self.destroy()