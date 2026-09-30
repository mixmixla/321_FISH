# -*- coding: utf-8 -*-
"""widgets/text_viewer.py —— 消息文本选择复制窗（R12，对标 TG 拖选复制）。

Canvas 逐 run 渲染的消息正文无法在 tkinter 里做字符级拖选；改用只读 Text
弹窗承载正文，原生支持拖选 + Ctrl+C / 右键复制。行为与 T7 图片查看器一致：
非阻塞、topmost、Esc 关闭。
"""
import tkinter as tk

_CHROME = 8


class TextViewer(tk.Toplevel):
    """只读文本查看/选择窗。text=正文；font/colors 走主题；Esc/关闭即销毁。"""

    def __init__(self, master, text: str, font=None, title: str = "选择文本",
                 colors: dict | None = None):
        super().__init__(master)
        self.transient(master)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.title(title)

        palette = {"bg": "#fafafa", "fg": "#333333", "sub": "#666666"} | (colors or {})
        self.configure(bg=palette["bg"])

        frm = tk.Frame(self, bg=palette["bg"])
        frm.pack(fill="both", expand=True, padx=10, pady=(10, 6))

        self.text = tk.Text(frm, wrap="word", undo=False,
                            font=font, bg=palette["bg"], fg=palette["fg"],
                            insertbackground=palette["fg"], relief="flat",
                            highlightthickness=0, padx=4, pady=4,
                            height=min(18, max(6, 2 + text.count("\n"))),
                            width=60)
        vbar = tk.Scrollbar(frm, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=vbar.set)
        self.text.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")
        self.text.insert("1.0", text)
        self.text.configure(state="disabled")     # 只读但可选可复制

        # 底部按钮：全选 / 复制 / 关闭（复制经 Text 选区原生 API）
        btns = tk.Frame(self, bg=palette["bg"])
        btns.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(btns, text="全选", command=self._select_all,
                  bg=palette["bg"], fg=palette["sub"],
                  relief="flat", activebackground=palette["sub"],
                  activeforeground="#ffffff").pack(side="left")
        tk.Button(btns, text="复制", command=self._copy,
                  bg=palette["bg"], fg=palette["sub"],
                  relief="flat", activebackground=palette["sub"],
                  activeforeground="#ffffff").pack(side="left", padx=8)
        tk.Button(btns, text="关闭", command=self.destroy,
                  bg=palette["bg"], fg=palette["sub"],
                  relief="flat", activebackground=palette["sub"],
                  activeforeground="#ffffff").pack(side="right")

        self.bind("<Escape>", lambda e: self.destroy())
        self.geometry(f"+{master.winfo_rootx() + 120}+{master.winfo_rooty() + 90}")

    def _select_all(self):
        self.text.focus_set()
        self.text.tag_add("sel", "1.0", "end-1c")

    def _copy(self):
        try:
            sel = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            sel = self.text.get("1.0", "end-1c")     # 无选区 → 全量
        if sel:
            self.clipboard_clear()
            self.clipboard_append(sel)
