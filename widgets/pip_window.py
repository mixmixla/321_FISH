# -*- coding: utf-8 -*-
"""D15 画中画悬浮窗：无边框置顶小窗，通话中把视频画面脱离通话窗常驻桌面角。

- 展示最新一帧（Tk 原生 PNG 解码，与通话窗同一份 png 数据，零额外传输）；
- 按住画面任意处拖动窗口；「返回」或双击画面回到通话窗（销毁本窗）；
- 自包含、不 `grab_set`（参考 image_viewer.py / global_search.py 的弹窗惯例）。
"""
import base64
import tkinter as tk

FONT_FAMILY = "Microsoft YaHei UI"

_W, _H = 260, 220          # 默认小窗尺寸（标题条 + 画面）


class PipWindow(tk.Toplevel):
    """画中画小窗：``set_frame(png)`` 刷画面，``close()`` 收窗（回调 on_close）。"""

    def __init__(self, master, on_close=None, title: str = "画中画"):
        super().__init__(master)
        self._on_close = on_close
        self._photo = None
        self._drag = None

        self.overrideredirect(True)                 # 无边框（去系统标题栏）
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.configure(bg="#111111")
        self._place_default()

        self.lbl = tk.Label(self, bg="#0d0d0d", fg="#777777",
                            font=(FONT_FAMILY, 9), text="等待画面…")
        self.lbl.pack(fill="both", expand=True)

        bar = tk.Frame(self, bg="#222222")
        bar.pack(fill="x", side="bottom")
        self.lbl_title = tk.Label(bar, text=f"🅿 {title}", bg="#222222",
                                  fg="#cccccc", font=(FONT_FAMILY, 8))
        self.lbl_title.pack(side="left", padx=6)
        tk.Button(bar, text="返回", command=self.close, relief="flat",
                  bg="#222222", fg="#8ab4f8", activebackground="#222222",
                  activeforeground="#c7dbff", cursor="hand2",
                  font=(FONT_FAMILY, 8)).pack(side="right", padx=4)

        for w in (self, self.lbl, self.lbl_title):   # 拖动抓手：画面/标题条
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
        self.lbl.bind("<Double-Button-1>", lambda _e: self.close())
        self.bind("<Escape>", lambda _e: self.close())

    # ---------- 对外 ----------

    def set_frame(self, png) -> None:
        """刷新画面（对端/本端最新帧）。异常静默（防御残留 PhotoImage 引用）。"""
        if not png:
            return
        try:
            self._photo = tk.PhotoImage(data=base64.b64encode(png))
            self.lbl.config(image=self._photo, text="")
        except Exception:
            pass

    def set_hint(self, text: str) -> None:
        self.lbl.config(text=str(text or ""))

    def close(self) -> None:
        cb, self._on_close = self._on_close, None
        try:
            self.destroy()
        except tk.TclError:
            pass
        if callable(cb):
            try:
                cb()
            except Exception:
                pass

    def alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    # ---------- 拖动 / 定位 ----------

    def _place_default(self) -> None:
        """默认贴右下角（离边缘留 24px），避免压住常见 IM 主窗内容区。"""
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            self.geometry(f"{_W}x{_H}+{sw - _W - 24}+{sh - _H - 64}")
        except tk.TclError:
            self.geometry(f"{_W}x{_H}+100+100")

    def _drag_start(self, e) -> None:
        self._drag = (e.x_root, e.y_root, self.winfo_x(), self.winfo_y())

    def _drag_move(self, e) -> None:
        if not self._drag:
            return
        x0, y0, wx, wy = self._drag
        self.geometry(f"+{wx + e.x_root - x0}+{wy + e.y_root - y0}")
