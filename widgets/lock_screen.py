# -*- coding: utf-8 -*-
"""widgets/lock_screen.py —— 运行时全屏锁屏遮罩（R10，对标 TG preview_passcode_lock）。

锁定后 `root.withdraw()` 隐藏主窗，本遮罩（topmost 全屏）独占画面：仅显示锁图标 +
解锁输入框，任务栏/预览再也看不到聊天内容。通过正确解锁码 `unlock_app()` 恢复。

判定逻辑复用 PasscodeBox 的 `_decide` 范式（FloodGuard 限频 + 错误内联提示）；
配色走 theme.get_skin 的 window_bg/fg/sub/accent token，随皮肤刷新。
"""
import tkinter as tk

from auth import FloodGuard

_ERR = "#e03e3e"


class LockOverlay(tk.Toplevel):
    """全屏锁屏遮罩。verifier(code)->bool；on_unlock() 解锁回调（可选 on_cancel）。

    Esc / 「取消」亦视为解锁（可随时离开锁屏）；回车 / 「解锁」提交判定。
    """

    def __init__(self, master, verifier=None, on_unlock=None, on_cancel=None,
                 skin: dict | None = None, title="摸鱼助手已锁定") -> None:
        super().__init__(master)
        self.verifier = verifier
        self.on_unlock = on_unlock
        self.on_cancel = on_cancel
        self.guard = FloodGuard()
        self._closed = False
        sk = skin or {}
        bg = sk.get("window_bg", "#f3f5f7")
        fg = sk.get("fg", "#333333")
        sub = sk.get("sub", "#8a8f98")
        accent = sk.get("accent", "#1a73e8")

        # 全屏 topmost 遮罩
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        w, h = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+0+0")
        self.configure(bg=bg)

        box = tk.Frame(self, bg=bg)
        box.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(box, text="🔒", bg=bg, font=("Segoe UI Emoji", 40)).pack()
        tk.Label(box, text=title, bg=bg, fg=fg,
                 font=("Microsoft YaHei UI", 14, "bold")).pack(pady=(8, 2))
        tk.Label(box, text="输入解锁码以继续使用", bg=bg, fg=sub,
                 font=("Microsoft YaHei UI", 9)).pack()
        self.entry = tk.Entry(box, show="*", font=("Microsoft YaHei UI", 12),
                              width=18, relief="solid", bd=1)
        self.entry.pack(fill="x", pady=(14, 0))
        self.entry.bind("<Return>", lambda e: self._submit())
        self.entry.bind("<KeyRelease>", self._clear_error)
        self.err = tk.Label(box, text="     ", fg=_ERR,
                            font=("Microsoft YaHei UI", 9), bg=bg)
        self.err.pack(anchor="center", pady=(2, 0))
        btns = tk.Frame(box, bg=bg)
        btns.pack(anchor="center", pady=(6, 0))
        tk.Button(btns, text="取消", font=("Microsoft YaHei UI", 10),
                  relief="flat", padx=12, command=self.cancel).pack(side="left", padx=6)
        tk.Button(btns, text="解锁", font=("Microsoft YaHei UI", 10),
                  relief="flat", padx=12, bg=accent, fg="#ffffff",
                  command=self._submit).pack(side="left", padx=6)

        self.bind("<Escape>", lambda e: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.deiconify()
        self.entry.focus_set()

    # ---------- 关闭 / 取消（视为解锁，KeyEsc 兜底） ----------
    def cancel(self) -> None:
        if self._closed:
            return
        self._closed = True
        cb = self.on_cancel
        self.destroy()
        if callable(cb):
            cb()

    # ---------- 判定（纯逻辑，供单测；范式同 PasscodeBox._decide） ----------
    def _decide(self, code: str, guard: FloodGuard, check):
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
            self._closed = True
            cb = self.on_unlock
            self.destroy()
            if callable(cb):
                cb()
            return
        self._err(msg)
        self.entry.selection_range(0, "end")
        self.entry.focus_set()

    def _err(self, msg: str) -> None:
        self.err.config(text=msg)
        self.entry.config(highlightbackground=_ERR, highlightcolor=_ERR,
                          highlightthickness=1)

    def _clear_error(self, _e=None) -> None:
        self.err.config(text="     ")
        self.entry.config(highlightthickness=1, highlightbackground="#ccc")