# -*- coding: utf-8 -*-
"""stealth_toast.py —— 隐身友好 Toast 通知（R31D B1）。

不用系统 Toast（Win10 通知会暴露 exe 名/应用名），自制右下角无边框小浮窗：
- 深灰低调卡片，标题「办公助手」+ 一行正文（假办公文案）；
- overrideredirect + 不抢焦点，停留数秒自动淡出移除；
- 新通知覆盖上一条并重置计时（简单单槽队列，避免堆叠穿帮）。
"""
import time
import tkinter as tk


class StealthToast:
    """右下角假办公通知浮窗（Tk 自绘，跨主题用固定深色皮肤）。"""

    def __init__(self, root: tk.Misc):
        self._root = root
        self._win: tk.Toplevel | None = None
        self._job = None

    # ---------- 对外 ----------
    def show(self, body: str, title: str = "办公助手", dur: float = 3.5) -> None:
        """弹一条通知（右下角，dur 秒后自动消失）。"""
        try:
            self._build()
            self._title.config(text=title)
            self._body.config(text=body)
            self._place_bottom_right()
            self._win.deiconify()
            self._win.lift()
        except Exception:
            return
        if self._job is not None:
            try:
                self._root.after_cancel(self._job)
            except Exception:
                pass
        self._job = self._root.after(int(dur * 1000), self._hide)

    def hide(self) -> None:
        self._hide()

    # ---------- 内部 ----------
    def _build(self) -> None:
        if self._win is not None:
            return
        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.96)
        except Exception:
            pass
        card = tk.Frame(win, bg="#2b2f36", padx=12, pady=8,
                        highlightthickness=1, highlightbackground="#3c414b")
        card.pack(fill="both", expand=True)
        self._title = tk.Label(card, text="", font=("Microsoft YaHei UI", 9),
                               fg="#cfd6e0", bg="#2b2f36", anchor="w")
        self._title.pack(fill="x")
        self._body = tk.Label(card, text="", font=("Microsoft YaHei UI", 10),
                              fg="#f0f3f8", bg="#2b2f36", anchor="w",
                              wraplength=260, justify="left")
        self._body.pack(fill="x", pady=(2, 0))
        self._win = win
        self._card = card

    def _place_bottom_right(self) -> None:
        win = self._win
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        w = max(win.winfo_reqwidth(), 280)
        h = win.winfo_reqheight()
        win.geometry(f"{w}x{h}+{sw - w - 16}+{sh - h - 48}")

    def _hide(self) -> None:
        self._job = None
        if self._win is not None:
            try:
                self._win.withdraw()
            except Exception:
                pass


# ---------- R31D 假办公文案（脱敏映射，不含昵称/正文） ----------
_OFFICE_LINES = [
    "文档 Q3_报表_v3.docx 已同步至共享盘",
    "会议提醒：15:00 部门周会（腾讯会议）",
    "OA 审批：您有一张差旅单待处理",
    "邮件：新日程邀请已送达收件箱",
    "企业盘：合同扫描件已上传成功",
    "考勤：本月工时统计已生成",
    "共享盘：项目资料包更新完成",
    "日程：明天 09:30 晨会签到提醒",
]


def stealth_text() -> str:
    """随机挑一条假办公文案（time 种子足够，无需 random 模块也行——用 random）。"""
    import random
    return random.choice(_OFFICE_LINES)
