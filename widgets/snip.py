# -*- coding: utf-8 -*-
"""widgets/snip.py —— Alt+A 区域截图选择层（纯 tkinter + Pillow）。

交互：全屏半透明遮罩 → 拖动框选 → 松手裁图回调 on_done(PIL.Image)。
取消：Esc / 右键 / 选区过小 → on_done(None)。
DPI：dpi.apply_early() 已声明 SYSTEM_DPI_AWARE，Tk 坐标≈物理像素，
与 ImageGrab 的 bbox 口径一致，无需再做缩放换算。
"""
import tkinter as tk


class SnipOverlay:
    """一次性的区域选框；构造即置顶显示，结束时自毁并回调。"""

    def __init__(self, root, on_done=None) -> None:
        self.root = root
        self.on_done = on_done or (lambda _img: None)
        self._x0 = 0
        self._y0 = 0
        self._rect = None
        self._closed = False
        self._sw = root.winfo_screenwidth()
        self._sh = root.winfo_screenheight()
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.attributes("-alpha", 0.28)          # 遮罩半透明，看清底下内容
        self.top.geometry(f"{self._sw}x{self._sh}+0+0")
        self.cv = tk.Canvas(self.top, bg="#101010", highlightthickness=0,
                            cursor="crosshair")
        self.cv.pack(fill="both", expand=True)
        self.cv.create_text(self._sw // 2, 30, fill="#ffffff",
                            font=("Microsoft YaHei UI", 11),
                            text="拖动框选截图区域 · Esc 取消")
        self.cv.bind("<Button-1>", self._press)
        self.cv.bind("<B1-Motion>", self._drag)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.top.bind("<Escape>", lambda _e: self._finish(None))
        self.top.bind("<Button-3>", lambda _e: self._finish(None))
        try:
            self.top.grab_set()                      # 独占输入，避免误触主窗
        except Exception:
            pass
        self.top.focus_force()

    def _press(self, ev) -> None:
        self._x0, self._y0 = ev.x, ev.y
        if self._rect is not None:
            self.cv.delete(self._rect)
        self._rect = self.cv.create_rectangle(
            ev.x, ev.y, ev.x, ev.y, outline="#ff8a5c", width=2)

    def _drag(self, ev) -> None:
        if self._rect is None:
            return
        self.cv.coords(self._rect, self._x0, self._y0, ev.x, ev.y)

    def _release(self, ev) -> None:
        x1, y1 = min(self._x0, ev.x), min(self._y0, ev.y)
        x2, y2 = max(self._x0, ev.x), max(self._y0, ev.y)
        if x2 - x1 < 4 or y2 - y1 < 4:               # 误点/极小选区视为取消
            self._finish(None)
            return
        self.top.withdraw()                          # 先让出画面，避免拍到遮罩
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        img = None
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        except Exception:
            img = None
        self._finish(img)

    def _finish(self, img) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.top.grab_release()
        except Exception:
            pass
        try:
            self.top.destroy()
        except Exception:
            pass
        self.on_done(img)