# -*- coding: utf-8 -*-
"""widgets/image_viewer.py —— 图片点击放大查看窗（T7，对标 TG media viewer）。

非阻塞 Toplevel：`transient(master)` + 不 `grab_set`（主窗仍可操作）。
- Canvas + 横/纵 Scrollbar，滚动区域 = 图像 bbox
- 大图用 daemon 线程 `PIL.Image.open+load`，主线程 `ImageTk.PhotoImage`
  （必须存 `self._photo` 防 GC 空白）
- 键：Esc→关闭；Left/Right→在传入的图片路径列表内循环切换
"""
import os
import queue
import threading
import tkinter as tk
from tkinter import font as tkfont

_SCREEN_PAD_RATIO = 0.8      # 图超屏 80% → 按屏 80% 收进滚动区
_CHROME = 60                  # 标题栏/滚动条等 chrome 高度预算


class ImageViewer(tk.Toplevel):
    """图片查看窗。paths=图片路径列表，index=初始展示的下标（循环切换）。"""

    def __init__(self, master, paths, index=0, font=None):
        super().__init__(master)
        self._photo = None                # 必须持有引用，防 GC 空白
        self._paths = list(paths)
        self._idx = max(0, min(index, len(self._paths) - 1))
        self._font = tkfont.Font(root=master, font=font) if font else None
        # R56：解码在 daemon 线程，结果经 Queue 投递，主线程 after 轮询（
        #   直接在线程里 self.after 会跨 appartment 崩，图片永不到位）
        self._q = queue.Queue()
        self.after(50, self._poll_img)

        self.transient(master)
        self.attributes("-topmost", True)
        self.configure(bg="#222222")
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        # Canvas + 双向滚动条（滚动区域随图片更新）
        self._canvas = tk.Canvas(self, bg="#1e1e1e", highlightthickness=0)
        vbar = tk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        hbar = tk.Scrollbar(self, orient="horizontal", command=self._canvas.xview)
        self._canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        hbar.pack(side="bottom", fill="x")
        vbar.pack(side="right", fill="y")
        self._canvas.pack(fill="both", expand=True)

        # 键位：Esc 关闭；Left/Right 循环切换
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Left>", lambda e: self._nav(-1))
        self.bind("<Right>", lambda e: self._nav(1))

        self._load(self._idx)

    # ---------- 图片加载（daemon 线程解码 → 主线程 PhotoImage） ----------
    def _load(self, idx: int) -> None:
        self._idx = idx
        path = self._paths[idx]
        self.title(os.path.basename(path))
        self._photo = None
        self._canvas.delete("all")
        self._status("加载中…")

        def work():
            try:
                from PIL import Image
                im = Image.open(path)
                im.load()
                res = im.convert("RGB")
            except Exception:
                res = None
            self._q.put(res)          # 跨线程只投递，不在子线程碰 Tk

        threading.Thread(target=work, daemon=True, name="img-view").start()

    def _poll_img(self) -> None:
        """主线程轮询解码结果（线程不直接调 Tk）。"""
        try:
            while True:
                res = self._q.get_nowait()
                if res is None:
                    self._status("无法解码该图片")
                    self._set_region(640, 360)
                else:
                    self._render(res)
        except queue.Empty:
            pass
        try:
            self.after(50, self._poll_img)
        except tk.TclError:
            pass                      # 窗口已销毁：停止轮询

    def _status(self, text: str) -> None:
        self._canvas.delete("all")
        self._canvas.create_text(10, 10, anchor="nw", text=text,
                                 fill="#cccccc",
                                 font=self._font or ("TkDefaultFont", 12))

    @staticmethod
    def _fit(w: int, h: int, sw: int, sh: int):
        """按屏高宽等比收进（不放大），返回 (目标宽, 目标高)。"""
        scale = min(sw / w, sh / h, 1.0)
        return max(1, int(w * scale)), max(1, int(h * scale))

    def _render(self, pil) -> None:
        from PIL import ImageTk
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        # 等比收进屏幕 80%，避免超屏
        vw = int(sw * _SCREEN_PAD_RATIO)
        vh = int(sh * _SCREEN_PAD_RATIO)
        disp_w, disp_h = self._fit(pil.width, pil.height, vw, vh - _CHROME)
        self._photo = ImageTk.PhotoImage(pil.resize((disp_w, disp_h),
                                                    ImageTk.Image.LANCZOS))
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, image=self._photo, anchor="nw")
        self._set_region(disp_w, disp_h)
        self._size_window(disp_w, disp_h)
        # 居中
        x = sw // 2 - (self.winfo_reqwidth() // 2)
        y = sh // 2 - (self.winfo_reqheight() // 2)
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _set_region(self, w: int, h: int) -> None:
        self._canvas.configure(scrollregion=(0, 0, w, h))

    def _size_window(self, img_w: int, img_h: int) -> None:
        cw = min(max(img_w, 200), int(self.winfo_screenwidth() * _SCREEN_PAD_RATIO))
        ch = min(max(img_h + 20, 120),
                 int(self.winfo_screenheight() * _SCREEN_PAD_RATIO))
        self.geometry(f"{cw + 14}x{ch + 14}")

    # ---------- 循环切换 ----------
    def _nav(self, step: int) -> None:
        n = len(self._paths)
        if n <= 1:
            return
        self._load((self._idx + step) % n)