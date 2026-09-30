# -*- coding: utf-8 -*-
"""R34 群内话题 Threads：话题窗口（Toplevel 内嵌 MsgList）。

- 顶部固定根消息条（灰底），下方为话题回复流（复用 MsgList 全套渲染管线）
- 发送自动附 thread_root=根消息 seq（由 ChatWindow.send 回调实际发帧）；
  双击某条回复 → 引用快照随帧发送
- 数据由 ChatWindow 驱动：实时回复 _on_thread_reply → append_msg；
  打开窗口/跨端拉取 THREAD_HISTORY → load_msgs（按 seq 去重重建）
- 话题回复不进主列表（ChatWindow._append_msg 过滤）；本地历史同频道混存，
  重启后窗口重建靠 LocalHistory.thread_msgs + THREAD_HISTORY 兜底
"""
import tkinter as tk

FONT_FAMILY = "Microsoft YaHei UI"


class ThreadWindow(tk.Toplevel):
    def __init__(self, master, *, root_msg, key, me_uid, make_msglist, send,
                 on_close=None):
        super().__init__(master)
        self.root_seq = int(root_msg.get("seq"))
        self.key = key                       # 所属会话键（public / private:a:b / group:gid）
        self.me_uid = me_uid
        self._send = send                    # send(text, reply) → core.send_chat(thread_root=…)
        self._on_close = on_close
        self._rows_by_seq = {}               # seq → raw（THREAD_HISTORY 去重重建）
        self._reply = None                   # 引用回复快照（双击某条回复）

        root_text = (root_msg.get("text")
                     or ("[图片]" if root_msg.get("image_path")
                         else ("[表情]" if root_msg.get("sticker_custom") else "…")))
        self.title(f"话题：{root_text[:24]}")
        self.geometry("640x520")

        # 顶部根消息条
        top = tk.Frame(self, bg="#ececee")
        top.pack(fill="x")
        who = root_msg.get("nick") or "?"
        tk.Label(top, text=f"💬 话题 · {who}: {root_text[:80]}",
                 font=(FONT_FAMILY, 9), bg="#ececee", fg="#333",
                 anchor="w", justify="left", wraplength=600).pack(
            fill="x", padx=8, pady=6)

        # 回复流（复用 MsgList；on_row_double → 窗口内引用回复）
        self.msg_list = make_msglist(self)
        self.msg_list.pack(fill="both", expand=True)

        # 输入栏（引用条 + 输入框 + 发送）
        bar = tk.Frame(self, bg="#ececee")
        bar.pack(fill="x", side="bottom")
        self.reply_lbl = tk.Label(bar, text="", font=(FONT_FAMILY, 8),
                                  bg="#ececee", fg="#06c", anchor="w")
        self.reply_lbl.pack(fill="x", padx=8)
        row = tk.Frame(bar, bg="#ececee")
        row.pack(fill="x")
        self.entry = tk.Entry(row, font=(FONT_FAMILY, 10), relief="flat",
                              highlightthickness=1,
                              highlightbackground="#c8c8c8")
        self.entry.pack(side="left", fill="x", expand=True, padx=6, pady=5)
        self.entry.bind("<Return>", self._do_send)
        tk.Button(row, text="发送", width=6, relief="flat",
                  font=(FONT_FAMILY, 9), cursor="hand2",
                  command=self._do_send).pack(side="left", padx=(0, 6), pady=5)
        self.entry.focus_set()
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ---------- 数据注入 ----------
    def load_msgs(self, msgs: list, me_uid=None) -> None:
        """THREAD_HISTORY / 打开窗口：全量重建（仅本话题回复，按 seq 去重升序）。"""
        if me_uid is not None:
            self.me_uid = me_uid
        seen = {}
        for m in msgs:
            seq = m.get("seq")
            if seq is not None and m.get("thread_root") == self.root_seq:
                seen[seq] = m
        self._rows_by_seq = seen
        self.msg_list.load(sorted(seen.values(),
                                  key=lambda m: m.get("seq") or 0),
                           me_uid=me_uid)
        self.msg_list.scroll_to_end()

    def append_msg(self, m: dict) -> None:
        """实时回复（ChatWindow._on_thread_reply 路由进来；按 seq 去重）。"""
        seq = m.get("seq")
        if seq is None or seq in self._rows_by_seq:
            return
        self._rows_by_seq[seq] = m
        self.msg_list.append(m)
        self.msg_list.scroll_to_end()

    # ---------- 发送 / 引用 ----------
    def _do_send(self, *_a) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        reply, self._reply = self._reply, None
        self._set_reply_lbl()
        self._send(text, reply)
        self.entry.delete(0, "end")

    def set_reply(self, idx: int) -> None:
        """双击某条回复 → 引用快照（随帧 reply 字段发送）。"""
        rows = sorted(self._rows_by_seq.values(),
                      key=lambda m: m.get("seq") or 0)
        if 0 <= idx < len(rows):
            m = rows[idx]
            self._reply = {"seq": m.get("seq"), "nick": m.get("nick"),
                           "text": (m.get("text") or "")[:60]}
            self._set_reply_lbl()
            self.entry.focus_set()

    def _set_reply_lbl(self) -> None:
        if self._reply:
            self.reply_lbl.config(
                text=f"回复 {self._reply.get('nick')}: "
                     f"{self._reply.get('text')[:40]}  ✕")
            self.reply_lbl.bind("<Button-1>", lambda _e: self._clear_reply())
        else:
            self.reply_lbl.config(text="")

    def _clear_reply(self) -> None:
        self._reply = None
        self._set_reply_lbl()

    def _close(self) -> None:
        if self._on_close:
            try:
                self._on_close(self.root_seq)
            except Exception:
                pass
        self.destroy()
