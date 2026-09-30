# -*- coding: utf-8 -*-
"""widgets/scrim.py —— 半透明遮罩层（对标 TG window_history_hider 的 layerBg+setOpacity）。

模态对话框下方的暗化背景：全屏 Toplevel 覆盖 root，alpha 淡入到 target，
关闭时淡出后 destroy。不参与 grab（模态拦截交给对话框自身 grab_set）。
"""
import tkinter as tk
from theme import surface


class Scrim(tk.Toplevel):
    """全屏半透明遮罩：show() 淡入，hide() 淡出并销毁。"""

    def __init__(self, root: tk.Misc, opaque: float | None = None,
                 fullscreen: bool = False) -> None:
        super().__init__(root)
        self._root = root
        self._fullscreen = fullscreen
        self.target = opaque if opaque is not None else surface()["scrim_alpha"]
        self._step = 0.06            # 每帧 alpha 变化量
        self._interval = 16          # ms
        self._fading = 0             # 1=淡入中  -1=淡出中  0=静止
        self.overrideredirect(True)
        self.configure(bg="#000000", highlightthickness=0)
        self.attributes("-topmost", True)
        self._sync_geometry()
        self.withdraw()

    # ---------- 几何跟随 root（全屏模式则覆盖整屏，不依赖 root 尺寸） ----------
    def _sync_geometry(self) -> None:
        # R56：窗口未显示（withdraw 后）/已销毁 → 停止 60ms 空转，省 CPU
        if not self.winfo_exists() or not self.winfo_ismapped():
            return
        if self._fullscreen:
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
        else:
            x = self._root.winfo_rootx()
            y = self._root.winfo_rooty()
            w = self._root.winfo_width()
            h = self._root.winfo_height()
            if w > 1 and h > 1:
                self.geometry(f"{w}x{h}+{x}+{y}")
        self.after(60, self._sync_geometry)

    # ---------- 进出场 ----------
    def show(self) -> None:
        self.deiconify()
        self.lift()
        self._fading = 1
        self._sync_geometry()      # 重新启动几何跟随（withdraw 时链已断）
        self._tick()

    def hide(self, cb=None) -> None:
        self._done_cb = cb
        self._fading = -1
        self._tick()

    def _tick(self) -> None:
        if self._fading == 1:
            a = min(1.0, float(self.alpha_value() or 0) + self._step)
            self.alpha_value(a)
            if a >= self.target:
                self.alpha_value(self.target)
                self._fading = 0
                return
            self.after(self._interval, self._tick)
        elif self._fading == -1:
            a = max(0.0, float(self.alpha_value() or self.target) - self._step)
            self.alpha_value(a)
            if a <= 0.01:
                self.destroy()
                cb = getattr(self, "_done_cb", None)
                if callable(cb):
                    cb()
                return
            self.after(self._interval, self._tick)

    def alpha_value(self, value=None):
        try:
            if value is None:
                return self.attributes("-alpha")
            self.attributes("-alpha", value)
            return value
        except tk.TclError:
            return None