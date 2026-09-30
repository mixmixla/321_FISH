# -*- coding: utf-8 -*-
"""widgets/task_panel.py —— R69B6/B7 群待办 / 接龙 / 签到面板。

服务端权威：面板只做输入与呈现——所有改动经回调发给 core（TASK_ADD/TASK_DO/TASK_DEL），
服务器广播回来的 TASK_STATE 由调用方 `set_tasks()` 回填刷新。

tasks 结构（TASK_STATE 原样透传）：
    [{"tid": int, "text": str, "mode": "todo|relay|checkin", "uid": int,
      "ts": float, "done": {"<uid>": ts}, "assignee": int, "closed": 0}]
"""
import time
import tkinter as tk
from tkinter import font as tkfont

MODE_LABEL = {"todo": "待办", "relay": "接龙", "checkin": "签到"}
MODE_ORDER = ("todo", "relay", "checkin")
MODE_DO = {"todo": "✓ 完成", "relay": "＋ 接龙", "checkin": "📍 打卡"}


class TaskPanel(tk.Toplevel):
    """群任务面板：发起（待办/接龙/签到）、参与/撤销、关闭、刷新。"""

    def __init__(self, master, gid: int, gname: str, uid: int,
                 name_of=None, on_add=None, on_do=None, on_del=None,
                 on_refresh=None, font=None, colors=None) -> None:
        super().__init__(master)
        self.gid = gid
        self._uid = uid
        self._name_of = name_of or (lambda u: f"用户{u}")
        self._on_add = on_add
        self._on_do = on_do
        self._on_del = on_del
        self._on_refresh = on_refresh
        self._font = tkfont.Font(root=master, font=font) if font else None
        cp = colors or {}
        self._c_win = cp.get("win", "#f4f4f6")
        self._c_bg = cp.get("bg", "#ffffff")
        self._c_fg = cp.get("fg", "#222222")
        self._c_sub = cp.get("sub", "#999999")
        self._c_btn = cp.get("tab_bg", "#e8e8ee")
        self._tasks = []
        self._mode = tk.StringVar(value="todo")

        self.title(f"🧾 群任务 · {gname}")
        self.transient(master)
        self.configure(bg=self._c_win)
        self.geometry("520x400")
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        tk.Label(self, text=f"🧾 群待办 / 接龙 / 签到 · {gname}", fg=self._c_fg,
                 bg=self._c_win, font=self._font, anchor="w").pack(
            fill="x", padx=10, pady=(8, 2))

        bar = tk.Frame(self, bg=self._c_win)
        bar.pack(fill="x", padx=10)
        for m in MODE_ORDER:
            tk.Radiobutton(bar, text=MODE_LABEL[m], value=m,
                           variable=self._mode, bg=self._c_win, fg=self._c_fg,
                           selectcolor=self._c_bg, activebackground=self._c_win,
                           font=self._font).pack(side="left")
        self._entry = tk.Entry(bar, font=self._font)
        self._entry.pack(side="left", fill="x", expand=True, padx=4)
        self._entry.bind("<Return>", lambda _e: self._add())
        tk.Button(bar, text="发起", relief="flat", bg=self._c_btn, fg=self._c_fg,
                  font=self._font, padx=8, command=self._add).pack(side="left")

        box = tk.Frame(self, bg=self._c_win)
        box.pack(fill="both", expand=True, padx=10, pady=6)
        sb = tk.Scrollbar(box)
        sb.pack(side="right", fill="y")
        self.listbox = tk.Listbox(box, yscrollcommand=sb.set, activestyle="none",
                                  bg=self._c_bg, fg=self._c_fg,
                                  font=self._font, highlightthickness=0)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._sync_btn())
        self.listbox.bind("<Double-Button-1>", lambda _e: self._do_toggle())

        foot = tk.Frame(self, bg=self._c_win)
        foot.pack(fill="x", padx=10, pady=(0, 8))
        self._do_btn = tk.Button(foot, text="＋ 参与/打卡", relief="flat",
                                 bg=self._c_btn, fg=self._c_fg, font=self._font,
                                 padx=8, command=self._do_toggle)
        self._do_btn.pack(side="left", padx=3)
        tk.Button(foot, text="关闭任务", relief="flat", bg=self._c_btn,
                  fg=self._c_fg, font=self._font, padx=8,
                  command=self._del_sel).pack(side="left", padx=3)
        tk.Button(foot, text="刷新", relief="flat", bg=self._c_btn,
                  fg=self._c_fg, font=self._font, padx=8,
                  command=self._refresh).pack(side="left", padx=3)
        self._hint = tk.Label(foot, text="", fg=self._c_sub, bg=self._c_win,
                              font=self._font)
        self._hint.pack(side="right")
        self._refresh()

    # ---------- 数据 ----------
    def set_tasks(self, tasks: list) -> None:
        """服务器权威清单回填（保留选中项）。"""
        sel = self._sel_tid()
        self._tasks = list(tasks or [])
        self._reload()
        if sel is not None:
            for i, t in enumerate(self._tasks):
                if t.get("tid") == sel:
                    self.listbox.selection_clear(0, "end")
                    self.listbox.selection_set(i)
                    break
        self._sync_btn()

    def _sel_tid(self):
        i = self.listbox.curselection()
        if not i or i[0] >= len(self._tasks):
            return None
        return self._tasks[i[0]].get("tid")

    def _sel_task(self) -> dict | None:
        i = self.listbox.curselection()
        if not i or i[0] >= len(self._tasks):
            return None
        return self._tasks[i[0]]

    def _reload(self) -> None:
        self.listbox.delete(0, "end")
        for t in self._tasks:
            mode = t.get("mode")
            done = t.get("done") or {}
            mine = self._uid in [int(k) for k in done.keys()]
            closed = bool(t.get("closed"))
            mark = "✅" if closed else ("☑" if mine else "☐")
            assignee = t.get("assignee") or 0
            who = self._name_of(t.get("uid"))
            when = time.strftime("%m-%d %H:%M",
                                 time.localtime(t.get("ts") or 0))
            tail = f"  → 指派 {self._name_of(assignee)}" if assignee and \
                assignee != t.get("uid") else ""
            self.listbox.insert(
                "end", f"{mark} [{MODE_LABEL.get(mode, mode)}] "
                       f"{len(done)} 人 · {str(t.get('text') or '')[:36]}"
                       f"  ·  {who} {when}{tail}")
        n_open = sum(1 for t in self._tasks if not t.get("closed"))
        self._hint.config(text=f"进行中 {n_open} / 共 {len(self._tasks)}")

    def _sync_btn(self) -> None:
        t = self._sel_task()
        if t is None:
            self._do_btn.config(text="＋ 参与/打卡")
            return
        done = [int(k) for k in (t.get("done") or {}).keys()]
        label = MODE_DO.get(t.get("mode"), "＋ 参与")
        self._do_btn.config(text=("↩ 撤销" if self._uid in done else label))

    # ---------- 交互 ----------
    def _add(self) -> None:
        text = self._entry.get().strip()
        if not text:
            self._hint.config(text="内容不能为空")
            return
        self._entry.delete(0, "end")
        if self._on_add:
            self._on_add(text, self._mode.get())

    def _do_toggle(self) -> None:
        t = self._sel_task()
        if t is None or not self._on_do:
            return
        done = [int(k) for k in (t.get("done") or {}).keys()]
        self._on_do(t.get("tid"), self._uid not in done)

    def _del_sel(self) -> None:
        t = self._sel_task()
        if t is None or not self._on_del:
            return
        self._on_del(t.get("tid"))

    def _refresh(self) -> None:
        if self._on_refresh:
            self._on_refresh()
