# -*- coding: utf-8 -*-
"""widgets/dialogbox.py —— 全站统一卡片风弹窗（对标 Telegram 对话框风格）。

单一风格来源：白底卡片 + 主色蓝操作按钮 + 强调标题 + 灰色副标题/说明。
提供四类常用模态框：
  - ask_string(prompt)：单行输入（文本/密码 show），替代 simpledialog.askstring
  - ask_yesno(问题)：确认框，替代 messagebox.askyesno
  - show_message(信息)：提示/警告/错误，替代 messagebox.showinfo/warning/error
  - ask_fields(多字段)：昵称改密等旧/新/确认密码组合输入

parent 传 None 时自建临时 Tk root（launcher 门禁阶段用，自管销毁）；
传既有窗口（self.root）则作为 transient 弹在其上。
返回 None 表示取消；typing.ineged 时静默失败，绝不崩溃（与现有 ui_fx 同思路）。
"""
import typing
import tkinter as tk

from widgets import ui_fx
from widgets.title_bar import DialogTitleBar
from config import FONT_FAMILY

# ---------- 主题 token（原创手绘暖粉家族，与全站暖色统一） ----------
_BG = "#fffdf7"          # 弹窗底（暖白）
_CARD = "#f5ead9"        # 内容卡片底（暖奶油）
_BORDER = "#efdcc4"      # 卡片描边
_ACCENT = "#ff8a5c"      # 主按钮（珊瑚）
_ACCENT_HOVER = "#ed7a4e"
_DANGER = "#e8635a"
_TX = "#5b4636"          # 主文本（可可）
_SUB = "#b7a48e"         # 副文本/提示
_FAM = FONT_FAMILY                  # 与主界面同款字体，保持全站统一皮肤

# ---------- 字号 token（点制；fix_scaling 后随 DPI 自动放大） ----------
# 统一层级：标题 > 输入框 > 按钮 > 正文/标签/提示。避免各处 8~13 混用。
_F_TITLE = (_FAM, 14, "bold")          # 弹窗标题
_F_BODY = (_FAM, 10)                   # 正文/说明/主提示
_F_HINT = (_FAM, 9)                    # 辅助说明/字段标签/错误/复选框
_F_INPUT = (_FAM, 12)                  # 输入框内容
_F_BTN = (_FAM, 11)                    # 底部按钮


def _hide_owner(root: tk.Tk) -> None:
    """self-owned 的临时根窗口：屏外 + 无边框，隐藏其任务栏按钮且不入屏。

    关键：不能用 root.withdraw()——Tk 会同步隐藏所有 transient 子窗口，
    导致弹窗（本应是唯一可见的面）根本不映射，程序卡在 wait_window 无任何
    画面（双击 exe「没反应」的根因）。overrideredirect 只在装饰/任务栏层面
    隐藏宿主，transient 弹窗仍正常显示。ref: R50-ish dialog 宿主可见性。
    """
    try:
        root.overrideredirect(True)
    except Exception:
        pass
    try:
        root.geometry("-30000+0")
    except Exception:
        pass


def _center_on_screen(dlg: tk.Toplevel) -> None:
    dlg.update_idletasks()
    w = dlg.winfo_reqwidth() + 30
    h = dlg.winfo_reqheight() + 20
    try:
        x = dlg.winfo_pointerx() - w // 2
        y = dlg.winfo_pointery() - h // 2
    except Exception:
        x, y = 120, 120
    dlg.geometry("+%d+%d" % (max(8, x), max(8, y)))


class _CardDialog(tk.Toplevel):
    """卡片风模态基类：创建标题、说明、内容区、底部按钮。ref:wait_window。"""

    def __init__(self, parent, title: str, text: str) -> None:
        tk.Toplevel.__init__(self, parent)
        self._result: typing.Any = None
        # Frameless：去掉系统原生标题栏/边框/图标，换用自绘 DialogTitleBar（全站统一）
        try:
            self.overrideredirect(True)
        except Exception:
            pass
        self.title(title)
        self.configure(bg=_BG)
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass
        try:
            self.transient(parent)
            self.grab_set()
        except Exception:
            pass
        self.resizable(False, False)

        # 顶部自绘标题栏；✕ 走「取消」语义，保证 wait_window 正常返回、result 为取消值
        DialogTitleBar(self, title, on_close=lambda: _terminate(self, None))
        # 玻璃感：顶沿 1px 高光带 + 细描边（仿毛玻璃入射高光/卡片描边）
        try:
            tk.Frame(self, bg="#ffffff", height=1).pack(side="top", fill="x")
        except Exception:
            pass
        try:
            self.configure(highlightthickness=1, highlightbackground=_BORDER)
        except Exception:
            pass
        # overrideredirect 的窗口默认不给焦点，lift + focus_force 保证 Esc/Return 绑定仍可用
        try:
            self.lift()
        except Exception:
            pass
        try:
            self.focus_force()
        except Exception:
            pass

        head = tk.Frame(self, bg=_BG)
        head.pack(padx=24, pady=(16, 8), fill="x")
        tk.Label(head, text=title, bg=_BG, fg=_TX,
                 font=_F_TITLE).pack(anchor="w")
        if text:
            tk.Label(head, text=text, bg=_BG, fg=_SUB, justify="left",
                     font=_F_BODY, wraplength=340).pack(anchor="w", pady=(4, 0))
        self._body = tk.Frame(self, bg=_BG)
        self._body.pack(padx=24, fill="x")
        self._btns = tk.Frame(self, bg=_BG)
        self._btns.pack(padx=24, pady=(8, 16), fill="x")

    # ---------- 底部按钮 ----------
    def _add_btn(self, text: str, command, *, side="left", primary=True,
                 width: int = 10) -> tk.Button:
        if primary:
            b = tk.Button(self._btns, text=text, width=width, relief="flat",
                          bg=_ACCENT, fg="#ffffff", activebackground=_ACCENT_HOVER,
                          activeforeground="#ffffff", command=command,
                          font=_F_BTN)
            _cmd = command
            b.configure(command=lambda: (ui_fx.click(), _cmd()))
            ui_fx.btn3(b, base=_ACCENT, hover=_ACCENT_HOVER)
            b.pack(side=side, padx=(0, 8))
            return b
        b = tk.Button(self._btns, text=text, width=width, relief="flat",
                      bg=_BG, fg=_TX, activebackground="#f5ead9",
                      command=command, font=_F_BTN)
        ui_fx.btn3(b, base=_BG, hover="#f0e2c6", pressed="#e8d6b2")
        b.pack(side=side, padx=(0, 8))
        return b

    def _finish(self, value):  # 子类 close 时统一触发
        self._result = value
        self.destroy()


def _terminate(dlg, value):
    try:
        dlg._finish(value)
    except Exception:
        pass


# ----------------- 单行输入 / 密码 -----------------
def ask_string(title: str, prompt: str, *, parent=None, initialvalue: str = "",
               show: str | None = None, hint: str = "") -> str | None:
    """卡片风单行输入框。返回字符串或 None（取消）。show="*" 即密码框。"""
    own = parent is None
    if own:
        root = tk.Tk()
        try:
            from dpi import fix_scaling
            fix_scaling(root)
        except Exception:
            pass
        parent = root
        _hide_owner(parent)
    dlg = _CardDialog(parent, title, prompt)
    if hint:
        tk.Label(dlg._body, text=hint, bg=_CARD, fg=_SUB, padx=10, pady=6,
                 font=_F_HINT, anchor="w", relief="flat").pack(fill="x", pady=(0, 6))
    e = tk.Entry(dlg._body, show=show or "", relief="solid", bd=1,
                 font=_F_INPUT)
    e.insert(0, initialvalue)
    e.pack(fill="x")
    dlg._add_btn("取消", lambda: _terminate(dlg, None), primary=False, side="right")
    dlg._add_btn("确定", lambda: _terminate(dlg, e.get()), side="right")
    e.bind("<Return>", lambda _e: _terminate(dlg, e.get()))
    e.focus_set()
    _center_on_screen(dlg)
    ui_fx.fade_in(dlg)
    parent.wait_window(dlg)
    if own:
        try:
            root.destroy()
        except Exception:
            pass
    return dlg._result


# ----------------- 确认 -----------------
def ask_yesno(title: str, message: str, *, parent=None) -> bool:
    """卡片风确认框，返回是否确认。"""
    own = parent is None
    if own:
        root = tk.Tk()
        try:
            from dpi import fix_scaling
            fix_scaling(root)
        except Exception:
            pass
        parent = root
        _hide_owner(parent)
    dlg = _CardDialog(parent, title, message)
    # 增强说明展示：多行包装
    dlg._submit = False
    dlg._add_btn("取消", lambda: _terminate(dlg, False), primary=False, side="left")
    dlg._add_btn("确定", lambda: _terminate(dlg, True), side="right")
    dlg.bind("<Return>", lambda _e: _terminate(dlg, True))
    dlg.bind("<Escape>", lambda _e: _terminate(dlg, False))
    _center_on_screen(dlg)
    ui_fx.fade_in(dlg)
    parent.wait_window(dlg)
    if own:
        try:
            root.destroy()
        except Exception:
            pass
    return bool(dlg._result)


def ask_check(title: str, message: str, check_label: str, *,
              parent=None, default: bool = False) -> tuple[bool, bool]:
    """卡片风确认框 + 勾选框。返回 (是否确认, 勾选状态)。"""
    own = parent is None
    if own:
        root = tk.Tk()
        try:
            from dpi import fix_scaling
            fix_scaling(root)
        except Exception:
            pass
        parent = root
        _hide_owner(parent)
    dlg = _CardDialog(parent, title, message)
    var = tk.BooleanVar(value=default)
    tk.Checkbutton(dlg._body, text=check_label, bg=_BG, fg=_SUB,
                   font=_F_BODY, variable=var, activebackground=_BG,
                   anchor="w").pack(fill="x", pady=(4, 0))
    dlg._add_btn("取消", lambda: _terminate(dlg, (False, var.get())),
                 primary=False, side="left")
    dlg._add_btn("确定", lambda: _terminate(dlg, (True, var.get())),
                 side="right")
    dlg.bind("<Return>", lambda _e: _terminate(dlg, (True, var.get())))
    dlg.bind("<Escape>", lambda _e: _terminate(dlg, (False, var.get())))
    _center_on_screen(dlg)
    ui_fx.fade_in(dlg)
    parent.wait_window(dlg)
    if own:
        try:
            root.destroy()
        except Exception:
            pass
    return tuple(dlg._result) if isinstance(dlg._result, tuple) else (False, False)


# ----------------- 信息提示 -----------------
def show_message(title: str, message: str, *, kind: str = "info", parent=None):
    """卡片风信息提示。kind: info/warning/error。show 后自动返回。"""
    own = parent is None
    if own:
        root = tk.Tk()
        try:
            from dpi import fix_scaling
            fix_scaling(root)
        except Exception:
            pass
        parent = root
        _hide_owner(parent)
    dlg = _CardDialog(parent, title, message)
    icon = {"info": "ℹ️ ", "warning": "⚠️ ", "error": "❌ "}.get(kind, "")
    if icon:
        tk.Label(dlg._body, text=icon, bg=_BG, fg=_TX,
                 font=(_FAM, 24)).pack(anchor="w", pady=(0, 6))
    dlg._add_btn("知道了", lambda: _terminate(dlg, True), side="right")
    dlg.bind("<Return>", lambda _e: _terminate(dlg, True))
    dlg.bind("<Escape>", lambda _e: _terminate(dlg, True))
    _center_on_screen(dlg)
    ui_fx.fade_in(dlg)
    parent.wait_window(dlg)
    if own:
        try:
            root.destroy()
        except Exception:
            pass


# ----------------- 多字段（改密等） -----------------
def ask_fields(title: str, prompt: str, fields: list[tuple[str, str]],
               *, parent=None, validator=None) -> dict | None:
    """卡片风多字段输入框。fields: [(label, show字符), ...]。
    返回 {index: 输入串} 或 None（取消）。validator(dict)->error字符串，非空则红字拦截。"""
    own = parent is None
    if own:
        root = tk.Tk()
        try:
            from dpi import fix_scaling
            fix_scaling(root)
        except Exception:
            pass
        parent = root
        _hide_owner(parent)
    dlg = _CardDialog(parent, title, prompt)
    entries = []
    # 卡片容器
    card = tk.Frame(dlg._body, bg=_CARD, highlightbackground=_BORDER,
                    highlightthickness=1)
    card.pack(fill="x")
    for i, (label, showch) in enumerate(fields):
        if i:
            tk.Frame(card, bg=_BORDER, height=1).pack(fill="x")
        tk.Label(card, text=label, bg=_CARD, fg=_SUB, padx=12, pady=8,
                 anchor="w", font=_F_HINT).pack(fill="x")
        e = tk.Entry(card, show=showch or "", relief="solid", bd=1,
                     font=_F_INPUT)
        e.pack(fill="x", padx=12, pady=(2, 8))
        entries.append(e)
    err = tk.Label(dlg._body, text="", fg=_DANGER, font=_F_HINT, bg=_BG)
    err.pack(anchor="w", pady=(4, 0))

    def _ok():
        vals = {i: en.get() for i, en in enumerate(entries)}
        if validator:
            emsg = validator(vals)
            if emsg:
                err.config(text=emsg)
                return
        _terminate(dlg, vals)

    dlg._add_btn("取消", lambda: _terminate(dlg, None), primary=False, side="left")
    dlg._add_btn("确定", _ok, side="right")
    entries[0].focus_set()
    entries[0].bind("<Return>", lambda _e: _ok())
    if len(entries) > 1:
        entries[-1].bind("<Return>", lambda _e: _ok())
    _center_on_screen(dlg)
    ui_fx.fade_in(dlg)
    parent.wait_window(dlg)
    if own:
        try:
            root.destroy()
        except Exception:
            pass
    return dlg._result