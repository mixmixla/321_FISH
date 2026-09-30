# -*- coding: utf-8 -*-
"""widgets/image_wall.py —— R69B5 会话图片墙（九宫格相册）。

聚合当前会话已加载的图片路径，按网格铺缩略图；点击某格 → 全屏灯箱（可左右翻页）。

设计要点：
- 缩略图由调用方提供 `thumb_of(path) -> PhotoImage|None`（复用 MsgList 的缩略图缓存与
  解码线程，不重复解码）；未就绪先画占位格，200ms 轮询补齐，全部就绪即停轮询。
- 缩略图可能大于格子（MsgList 上限 240x150），用 `PhotoImage.subsample(k)` 整数倍降采样
  适配格子（纯 Tk 实现，不引入额外 PIL 重采样）；降采样产物自持引用防 GC。
- 纯 Canvas 布局 + tag 命中（tag "iwc<i>"），无子控件，重排/刷新成本低。
"""
import math
import tkinter as tk
from tkinter import font as tkfont

POLL_MS = 200           # 缩略图轮询间隔


class ImageWall(tk.Toplevel):
    """图片墙。paths=图片路径列表；on_pick(index) 点击回调（通常开灯箱）。"""

    def __init__(self, master, paths, thumb_of=None, on_pick=None,
                 font=None, colors=None, title="🖼 图片墙",
                 cols=4, cell=130, gap=8) -> None:
        super().__init__(master)
        self._paths = list(paths)
        self._thumb_of = thumb_of
        self._on_pick = on_pick
        self._cols = max(1, int(cols))
        self._cell = max(40, int(cell))
        self._gap = max(0, int(gap))
        self._pad = 10
        self._font = tkfont.Font(root=master, font=font) if font else None
        cp = colors or {}
        self._c_win = cp.get("win", "#f4f4f6")
        self._c_bg = cp.get("bg", "#ffffff")
        self._c_fg = cp.get("fg", "#222222")
        self._c_sub = cp.get("sub", "#999999")
        self._c_ph = cp.get("tab_bg", "#e8e8ee")
        self._photos = {}                 # i -> 降采样 PhotoImage（自持引用防 GC）
        self._items = {}                  # i -> [canvas item id, ...]
        self._job = None

        self.title(title)
        self.transient(master)
        self.configure(bg=self._c_win)
        w = self._pad * 2 + self._cols * self._cell + (self._cols - 1) * self._gap
        h = min(640, self._pad * 2 + 3 * self._cell + 2 * self._gap + 34)
        self.geometry(f"{w}x{h}")
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        n = len(self._paths)
        tk.Label(self, text=f"共 {n} 张图片  ·  点击查看大图（灯箱内 ←/→ 翻页）",
                 fg=self._c_sub, bg=self._c_win,
                 font=(self._font.actual("family"), 9) if self._font else None,
                 anchor="w").pack(fill="x", padx=self._pad, pady=(6, 2))

        box = tk.Frame(self, bg=self._c_win)
        box.pack(fill="both", expand=True, padx=self._pad, pady=(0, self._pad))
        sb = tk.Scrollbar(box)
        sb.pack(side="right", fill="y")
        self.canvas = tk.Canvas(box, bg=self._c_bg, highlightthickness=0, bd=0,
                                yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.config(command=self.canvas.yview)

        self._redraw()
        self._kick()                              # 缩略图未就绪 → 轮询补齐
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Escape>", lambda _e: self.destroy())

    # ---------- 布局/绘制 ----------
    def _slot(self, i: int) -> tuple:
        """第 i 格的左上角画布坐标。"""
        col = i % self._cols
        row = i // self._cols
        x = self._pad + col * (self._cell + self._gap)
        y = self._pad + row * (self._cell + self._gap)
        return x, y

    def _fit(self, i: int):
        """按格子尺寸取缩略图（必要时整数倍降采样）；未就绪返回 None。"""
        if self._thumb_of is None:
            return None
        photo = self._thumb_of(self._paths[i])
        if photo is None:
            return None
        if i in self._photos:
            return self._photos[i]
        try:
            w, h = photo.width(), photo.height()
        except tk.TclError:
            return None
        if w <= 0 or h <= 0:
            return None
        span = max(w, h)
        limit = self._cell - 6                     # 留 3px 边距，避免贴格
        k = max(1, int(math.ceil(span / float(limit))))
        try:
            shrunk = photo if k == 1 else photo.subsample(k, k)
        except tk.TclError:
            shrunk = photo
        self._photos[i] = shrunk                   # 常驻引用防 GC
        return shrunk

    def _draw_cell(self, i: int) -> None:
        for it in self._items.pop(i, []):
            self.canvas.delete(it)
        x, y = self._slot(i)
        c = self._cell
        tags = ("iwc%d" % i,)
        items = [self.canvas.create_rectangle(
            x, y, x + c, y + c, fill=self._c_ph, outline="", tags=tags)]
        photo = self._fit(i)
        if photo is not None:
            items.append(self.canvas.create_image(
                x + c / 2, y + c / 2, image=photo, tags=tags))
        else:
            items.append(self.canvas.create_text(
                x + c / 2, y + c / 2, text="…", fill=self._c_sub,
                font=self._font, tags=tags))
        self._items[i] = items

    def _redraw(self) -> None:
        for items in self._items.values():
            for it in items:
                self.canvas.delete(it)
        self._items = {}
        for i in range(len(self._paths)):
            self._draw_cell(i)
        rows = max(1, int(math.ceil(len(self._paths) / float(self._cols))))
        h = self._pad * 2 + rows * self._cell + (rows - 1) * self._gap
        self.canvas.configure(scrollregion=(0, 0, self.winfo_reqwidth(), h))

    def _pending(self) -> list:
        """尚未取到缩略图的格下标。"""
        return [i for i in range(len(self._paths)) if i not in self._photos]

    def _tick(self) -> None:
        self._job = None
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:                        # 窗口已销毁 → 静默收摊
            return
        left = self._pending()
        for i in left:
            if self._fit(i) is not None:           # 缩略图到位 → 就地换格
                self._draw_cell(i)
        if self._pending():                        # 仍有缺 → 继续轮询
            self._job = self.after(POLL_MS, self._tick)

    def _kick(self) -> None:
        if self._job is None:
            self._job = self.after(POLL_MS, self._tick)

    def _on_wheel(self, ev) -> None:
        self.canvas.yview_scroll(-1 if ev.delta > 0 else 1, "units")

    # ---------- 交互 ----------
    def _hit(self, ev) -> int:
        """按点击坐标反解格下标；不在任何格内返回 -1。"""
        x = self.canvas.canvasx(ev.x)
        y = self.canvas.canvasy(ev.y)
        step = self._cell + self._gap
        col = int((x - self._pad) // step)
        row = int((y - self._pad) // step)
        if col < 0 or col >= self._cols or row < 0:
            return -1
        i = row * self._cols + col
        if i >= len(self._paths):
            return -1
        ox, oy = self._slot(i)
        if not (ox <= x <= ox + self._cell and oy <= y <= oy + self._cell):
            return -1                               # 落在间隙上
        return i

    def _on_click(self, ev) -> None:
        i = self._hit(ev)
        if i < 0 or self._on_pick is None:
            return
        self._on_pick(i)

    def destroy(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        super().destroy()
