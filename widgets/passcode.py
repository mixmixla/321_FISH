# -*- coding: utf-8 -*-
"""widgets/passcode.py —— 本机解锁码框（对标 TG window_unlock_passcode_box）。

回车提交、空/错码内联提示、限频(FloodGuard)、焦点管理、Esc/关闭 = 取消。
纯展示；判定逻辑抽成 _decide 便于单测。
"""
import tkinter as tk
from auth import FloodGuard
from widgets.title_bar import DialogTitleBar

_ERR = "#e03e3e"


class PasscodeBox(tk.Toplevel):
    """模态解锁框。verifier(code)->bool；on_ok 成功回调；guard 限频（可为 None）。"""

    def __init__(self, master, title="解锁", about="请输入解锁码：",
                 verifier=None, on_ok=None, on_cancel=None,
                 guard: FloodGuard | None = None, font=None, colors=None) -> None:
        super().__init__(master)
        self.verifier = verifier
        self.on_ok = on_ok
        self.on_cancel = on_cancel
        self.guard = guard or FloodGuard()
        self._closed = False
        # R56：可传主题 token（colors={'bg','fg','sub'}），深色皮肤下解锁框不再是白块
        bg = (colors or {}).get("bg", "#ffffff")
        fg = (colors or {}).get("fg", "#222222")
        sub = (colors or {}).get("sub", "#666666")
        # Frameless：去掉系统原生标题栏，换自绘 DialogTitleBar（全站统一 Apple 风）。
        # ✕ == 取消（走 cancel，触发 on_cancel / finish(False)）。
        try:
            self.overrideredirect(True)
        except Exception:
            pass
        DialogTitleBar(self, title, on_close=self.cancel)
        self.withdraw()
        f = font or ("TkDefaultFont", 10)
        self.configure(bg=bg)
        self.title(title)
        body = tk.Frame(self, bg=bg, padx=20, pady=16)
        body.pack()
        tk.Label(body, text=title, font=(f[0], f[1] if isinstance(f[1], int) else 10, "bold"),
                 bg=bg, fg=fg).pack(anchor="w")
        tk.Label(body, text=about, font=(f[0], 9), fg=sub, bg=bg,
                 anchor="w").pack(fill="x", pady=(2, 8))
        self.entry = tk.Entry(body, show="*", font=(f[0], 11), width=18,
                              relief="solid", bd=1)
        self.entry.pack(fill="x")
        self.entry.bind("<Return>", lambda e: self._submit())
        self.err = tk.Label(body, text="", fg=_ERR, font=(f[0], 9), bg=bg)
        self.err.pack(anchor="w")
        self.entry.bind("<KeyRelease>", self._clear_error)
        btns = tk.Frame(body, bg=bg)
        btns.pack(anchor="e", pady=(10, 0))
        tk.Button(btns, text="取消", command=self.cancel, font=f,
                  relief="flat", padx=10, fg=fg, bg=bg).pack(side="left", padx=4)
        tk.Button(btns, text="确定", font=f, relief="flat", padx=10,
                  fg=fg, bg=bg, command=self._submit).pack(side="left")
        # 定位居中：master 已映射则相对它居中；否则相对屏幕（门禁阶段 root 未显示）
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        if master.winfo_ismapped():
            x = master.winfo_rootx() + (master.winfo_width() - w) // 2
            y = master.winfo_rooty() + (master.winfo_height() - h) // 3
        else:
            x = (self.winfo_screenwidth() - w) // 2
            y = (self.winfo_screenheight() - h) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.deiconify()
        self.entry.focus_set()
        self.bind("<Escape>", lambda e: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)

    # ---------- 关闭统一走 cancel（成功走 _submit 的 on_ok） ----------
    def cancel(self) -> None:
        if self._closed:
            return
        self._closed = True
        cb = self.on_cancel
        self.destroy()
        if callable(cb):
            cb()

    # ---------- 交互 ----------
    def _decide(self, code: str, guard: FloodGuard, check):
        """返回 ('err', msg) 或 ('ok', None)。纯逻辑，供单测（check(code)->bool）。"""
        if not guard.allowed():
            return ("err", f"尝试过于频繁，请稍候 {int(guard.remaining() + 1)} 秒再试")
        if not code.strip():
            return ("err", "请输入解锁码")
        if not check(code.strip()):
            guard.fail()
            return ("err", "解锁码错误")
        return ("ok", None)

    def _submit(self) -> None:
        code = self.entry.get()
        check = self.verifier if callable(self.verifier) else (lambda _c: False)
        status, msg = self._decide(code, self.guard, check)
        if status == "ok":
            self.guard.ok()
            if callable(self.on_ok):
                self.on_ok()
            self.destroy()
            return
        self._err(msg)
        self.entry.selection_range(0, "end")
        self.entry.focus_set()

    def _err(self, msg: str) -> None:
        self.err.config(text=msg)
        self.entry.config(highlightbackground=_ERR, highlightcolor=_ERR,
                          highlightthickness=1)

    def _clear_error(self, _e=None) -> None:
        self.err.config(text="")
        self.entry.config(highlightthickness=1, highlightbackground="#ccc")