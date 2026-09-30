# -*- coding: utf-8 -*-
"""widgets/title_bar.py —— 自绘标题栏（Frameless 主窗），Apple 风格红绿灯按钮。

Apple 风格（traffic_lights=True）：
- 左：红🔴 黄🟡 绿🟢 三个圆形按钮（hover 显示符号 ✕ — ⤢）
- 中：应用名+当前昵称（居中，可拖动窗口、双击最大化）
- 右：🔒锁定按钮

传统风格（traffic_lights=False / 旧皮肤）：
- 左：应用名+昵称；右：— ▢ 🔒 ✕（与原行为一致）

颜色走 theme token，可随 _apply_skin / set_colors 刷新。
"""
import tkinter as tk
from theme import BASE, get_skin


class TitleBar(tk.Frame):
    def __init__(self, master: tk.Misc, app, font=None) -> None:
        self.app = app
        self._maxed = False
        self._normal_geo = ""
        # Apple 红绿灯 vs 传统按钮模式
        sk = getattr(app, "_skin", None) or {}
        self._traffic = bool(sk.get("traffic_lights", False))
        h = int(sk.get("titlebar_h", BASE["titlebar_h"]))
        super().__init__(master, bg=sk.get("titlebar_bg", "#ececee"), height=h,
                         padx=8, pady=0)
        self.pack_propagate(False)
        f = font or ("TkDefaultFont", 10)
        self._f = f
        self._btns: list = []
        self._lights: list = []       # Apple 红绿灯按钮
        self._light_hovers = {}        # light_label -> hover_color

        if self._traffic:
            self._build_traffic_lights()
            # 居中标题（用 expand + center anchor）
            self.title = tk.Label(self, text=app.core.nick, font=f,
                                  bg=self["bg"], fg=sk.get("titlebar_fg", "#1d1d1f"),
                                  anchor="center")
            self.title.pack(side="left", fill="x", expand=True)
            # 右侧锁定按钮
            self.btn_lock = self._mkbt_right("🔒", 20, self.app.lock_app)
        else:
            # 传统风格：左标题 + 右按钮
            self.title = tk.Label(self, text=app.core.nick, font=f,
                                  bg=self["bg"], fg=sk.get("titlebar_fg", "#666"),
                                  anchor="w")
            self.title.pack(side="left", fill="x", expand=True)
            self.btn_close = self._mkbt("✕", 20, self.app.quit_app,
                                        hover="#e03e3e", fg_hover="#fff")
            self.btn_lock = self._mkbt("🔒", 20, self.app.lock_app)
            self.btn_max = self._mkbt("▢", 20, self._toggle_max)
            self.btn_min = self._mkbt("—", 20, self.app.hide_to_mini)

        # 拖动 + 双击最大化（标题区域和空白区域均可拖动）
        for w in (self, self.title):
            w.bind("<Button-1>", self._press)
            w.bind("<B1-Motion>", self._drag)
            w.bind("<Double-Button-1>", lambda _e: self._toggle_max())
            w.bind("<Button-3>", self._show_menu)
        self._menu = None

    # ---------- Apple 红绿灯按钮 ----------
    def _build_traffic_lights(self) -> None:
        """构建左侧三个圆形按钮：红(关闭) 黄(最小化) 绿(最大化)。"""
        lights_frame = tk.Frame(self, bg=self["bg"])
        lights_frame.pack(side="left", padx=(0, 8))
        self._lights_frame = lights_frame
        # 红：关闭
        self._mk_light(lights_frame, "✕", "#ff5f57", "#e4443e",
                       self.app.quit_app)
        # 黄：最小化（进迷你条）
        self._mk_light(lights_frame, "—", "#febc2e", "#e0a423",
                       self.app.hide_to_mini)
        # 绿：最大化/还原
        self._mk_light(lights_frame, "⤢", "#28c840", "#1aab2e",
                       self._toggle_max)

    def _mk_light(self, parent, symbol, color, hover_color, cmd):
        """创建单个圆形红绿灯按钮（hover 时显示符号）。"""
        dot = tk.Label(parent, text="●", font=("TkDefaultFont", 11),
                       bg=self["bg"], fg=color, cursor="hand2", width=2)
        dot.pack(side="left", padx=1)
        dot.bind("<Button-1>", lambda _e: cmd())
        dot.bind("<Enter>", lambda _e, d=dot, s=symbol, c=color:
                 d.config(text=s, fg=c))
        dot.bind("<Leave>", lambda _e, d=dot: d.config(text="●"))
        self._lights.append(dot)
        self._light_hovers[dot] = (symbol, color)
        self._btns.append(dot)
        return dot

    # ---------- 传统右侧按钮 ----------
    def _mkbt(self, text, w, cmd, hover=None, fg_hover=None):
        b = tk.Label(self, text=text, width=2, font=("TkDefaultFont", 10),
                     bg=self["bg"], fg="#666", cursor="hand2")
        b.pack(side="right", padx=1, fill="y")
        b.bind("<Button-1>", lambda _e: cmd())
        h = hover or "#999"
        fh = fg_hover or "#fff"
        b.bind("<Enter>", lambda _e: b.config(bg=h, fg=fh))
        b.bind("<Leave>", lambda _e: b.config(bg=self["bg"], fg="#666"))
        self._btns.append(b)
        return b

    def _mkbt_right(self, text, w, cmd):
        """Apple 风格右侧按钮（锁）。"""
        b = tk.Label(self, text=text, width=2, font=("TkDefaultFont", 10),
                     bg=self["bg"], fg=self._skin_or("titlebar_btn", "#86868b"),
                     cursor="hand2")
        b.pack(side="right", padx=(8, 0), fill="y")
        b.bind("<Button-1>", lambda _e: cmd())
        hover = self._skin_or("hover_bg", "#e3e3e5")
        b.bind("<Enter>", lambda _e: b.config(bg=hover))
        b.bind("<Leave>", lambda _e: b.config(bg=self["bg"]))
        self._btns.append(b)
        return b

    def _skin_or(self, key, default):
        sk = getattr(self.app, "_skin", None) or {}
        return sk.get(key, default)

    def _show_menu(self, _e) -> None:
        app = self.app
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="隐藏到迷你条",
                         command=lambda: app.hide_to_mini())
        if hasattr(app, "lock_app"):
            menu.add_command(label="🔒 锁定（防偷窥）",
                             command=lambda: app.lock_app())
        menu.add_separator()
        menu.add_command(label="退出", command=lambda: app.quit_app())
        menu.tk_popup(_e.x_root, _e.y_root)
        self._menu = menu

    # ---------- 拖动 ----------
    def _press(self, ev) -> None:
        self._drag_x, self._drag_y = ev.x_root, ev.y_root
        self._win_x, self._win_y = self.master.winfo_x(), self.master.winfo_y()

    def _drag(self, ev) -> None:
        dx, dy = ev.x_root - self._drag_x, ev.y_root - self._drag_y
        self.master.geometry(f"+{self._win_x + dx}+{self._win_y + dy}")

    def _toggle_max(self) -> None:
        win = self.master
        if not self._maxed:
            self._normal_geo = win.geometry()
            # R56：最大化扣底部任务栏预算（40px），不再盖住任务栏
            sw = win.winfo_screenwidth()
            sh = max(20, win.winfo_screenheight() - 40)
            win.geometry(f"{sw}x{sh}+0+0")
            self._maxed = True
        else:
            win.geometry(self._normal_geo)
            self._maxed = False

    def set_colors(self, sk: dict) -> None:
        bg = sk.get("titlebar_bg", "#ececee")
        fg = sk.get("titlebar_fg", "#1d1d1f")
        btn_fg = sk.get("titlebar_btn", "#86868b")
        self.config(bg=bg)
        self.title.config(bg=bg, fg=fg)
        for b in self._btns:
            b.config(bg=bg)
        # Apple 红绿灯保持各自颜色不变（仅背景跟随）
        if hasattr(self, "_lights_frame"):
            self._lights_frame.config(bg=bg)


class DialogTitleBar(tk.Frame):
    """轻量自绘弹窗标题栏：挂在 `overrideredirect(True)` 的 Toplevel 顶部。

    Apple 风统一（与主窗 TitleBar 同款红绿灯）：靠左红黄绿三个圆点，
    红=关闭（on_close）、黄/绿=装饰（悬停显示 − / ⤢），靠左标题文字；
    支持鼠标按下拖动整窗（geometry 位移）。颜色走主题 token：优先
    `theme.get_skin(None)` 的 titlebar_bg / titlebar_fg，缺省浅灰默认。

    用法（dialogbox/launcher/passcode 等所有 frameless 弹窗共用）：
        dlg.overrideredirect(True)
        DialogTitleBar(dlg, title="xxx", on_close=lambda: <取消/关闭>)

    构造即 `pack(side="top", fill="x")`；用 `pack_propagate(False)` 固定 26~28px 高。
    """

    _DANGER = "#e03e3e"      # 关闭按钮 hover 危险红（保留字段，Apple 红点已覆盖）
    _BTN_FG = "#666666"      # 关闭按钮默认灰（保留字段）

    def __init__(self, master: tk.Misc, title: str, on_close=None, *, height=None,
                 font=None) -> None:
        sk = get_skin(None)                 # 若调用方可感知皮肤可自行改 token，这里取默认
        bg = sk.get("titlebar_bg", "#ececee")
        fg = sk.get("titlebar_fg", "#1d1d1f")
        h = height or int(sk.get("titlebar_h", BASE["titlebar_h"]))
        super().__init__(master, bg=bg, height=h, padx=8, pady=0)
        self.pack_propagate(False)          # 固定标题栏高度
        self._win = master
        self._on_close = on_close

        # 左：Apple 红黄绿圆点（红=关闭，黄/绿=装饰，悬停显示符号）
        for sym, col, hover, cmd in (
                ("✕", "#ff5f57", "#e4443e", self._close),   # 红=关闭
                ("—", "#febc2e", "#e0a423", self._noop),    # 黄=装饰
                ("⤢", "#28c840", "#1aab2e", self._noop)):   # 绿=装饰
            dot = tk.Label(self, text="●", font=("TkDefaultFont", 11),
                           bg=bg, fg=col, cursor="hand2", width=2)
            dot.pack(side="left", padx=1)
            dot.bind("<Button-1>", lambda _e, c=cmd: c())
            dot.bind("<Enter>", lambda _e, d=dot, s=sym, c=col:
                     d.config(text=s, fg=c))
            dot.bind("<Leave>", lambda _e, d=dot: d.config(text="●"))

        # 靠左标题文字（紧跟红绿灯右侧，左对齐）
        data = font or ("TkDefaultFont", 10)
        title_lbl = tk.Label(self, text=title, bg=bg, fg=fg, font=data, anchor="w")
        title_lbl.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # 拖动整窗（标题文字与空白区均可拖）
        for w in (self, title_lbl):
            w.bind("<Button-1>", self._press)
            w.bind("<B1-Motion>", self._drag)

        # 挂到父窗口顶部
        self.pack(side="top", fill="x")

    def _close(self) -> None:
        # 走「取消/关闭」语义：回调异常静默，绝不因回调炸掉 frameless 弹窗
        try:
            cb = self._on_close
            if callable(cb):
                cb()
        except Exception:
            pass

    def _noop(self) -> None:
        """黄/绿圆点的装饰操作：弹窗为固定尺寸，最小化/最大化无意义，悬停给反馈。"""
        pass

    def _press(self, ev) -> None:
        # 记录按下点到窗口相对位置，拖动时保持相对偏移
        try:
            self._dx = ev.x_root - self._win.winfo_x()
            self._dy = ev.y_root - self._win.winfo_y()
        except Exception:
            self._dx, self._dy = 0, 0

    def _drag(self, ev) -> None:
        try:
            self._win.geometry(f"+{ev.x_root - self._dx}+{ev.y_root - self._dy}")
        except Exception:
            pass
