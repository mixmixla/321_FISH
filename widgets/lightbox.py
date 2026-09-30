# -*- coding: utf-8 -*-
"""widgets/lightbox.py —— R39D① 图片灯箱（对标 TG media viewer 沉浸态）。

非阻塞 fullscreen Toplevel（纯黑底 + Canvas 居中显示）：
- 滚轮缩放 20%~800%（指针为锚点），双击复位为「收进屏幕」适配档；
- ←/→ 或屏幕两侧按钮在多图间循环切换，右下角「i/N」计数；
- Esc 关闭；B1 拖拽平移；
- 原图懒加载：可选 thumb_of(path) 先显缩略图，daemon 线程解码原图后换真图；
- 解码/重采样均在子线程，主线程只做 PhotoImage 换帧（引用必须常驻防 GC）。

纯数学（clamp_zoom / fit_scale / zoom_anchor）为静态方法，可脱离 Tk 单测。
"""
import os
import queue
import threading
import tkinter as tk
from tkinter import font as tkfont

ZOOM_MIN = 0.2       # 缩放下限（相对原图）
ZOOM_MAX = 8.0       # 缩放上限
ZOOM_STEP = 1.2      # 每格滚轮缩放系数
_RESIZE_MAX = 8192   # 单次重采样边长上限（防 8x 放大大图撑爆内存）


class Lightbox(tk.Toplevel):
    """图片灯箱。paths=图片路径列表；index=初始下标；thumb_of(path)->PhotoImage|None。"""

    def __init__(self, master, paths, index=0, font=None, thumb_of=None):
        super().__init__(master)
        self._paths = list(paths)
        self._idx = max(0, min(index, len(self._paths) - 1))
        self._thumb_of = thumb_of
        self._font = tkfont.Font(root=master, font=font) if font else None
        self._pil = None                  # 当前原图（PIL）
        self._photo = None                # 常驻引用防 GC
        self._zoom = 1.0                  # 相对原图的缩放（1.0=原始像素）
        self._off = (0, 0)                # 图像左上角在 canvas 的偏移
        self._pil_size = (0, 0)
        self._render_job = None           # 重采样防抖定时器
        self._render_seq = 0              # 缩放会话序号（丢弃过期线程结果）
        self._drag = None
        # R56：解码/重采样在子线程，结果经 Queue 投递、主线程 after 轮询
        #   （子线程直接 self.after 会跨 appartment 抛 RuntimeError：图片永不到位）
        self._q = queue.Queue()
        self._decode_use_thumb = False
        self.after(50, self._poll)

        self.overrideredirect(False)
        try:
            self.attributes("-fullscreen", True)
        except tk.TclError:
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
        self.attributes("-topmost", True)
        self.configure(bg="#000000", cursor="fleur")
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._canvas = tk.Canvas(self, bg="#000000", highlightthickness=0,
                                 bd=0, cursor="fleur")
        self._canvas.pack(fill="both", expand=True)
        self._counter = tk.Label(self, text="", bg="#000000", fg="#dddddd",
                                 font=self._font or ("TkDefaultFont", 10))
        self._counter.place(relx=1.0, rely=1.0, x=-16, y=-14, anchor="se")
        self._prev_btn = tk.Label(self, text="‹", bg="#000000", fg="#cccccc",
                                  font=(self._font.actual("family"),
                                        max(18, self._font.actual("size") + 10))
                                  if self._font else ("TkDefaultFont", 22),
                                  cursor="hand2")
        self._next_btn = tk.Label(self, text="›", bg="#000000", fg="#cccccc",
                                  font=self._prev_btn.cget("font"), cursor="hand2")
        self._prev_btn.place(relx=0.0, rely=0.5, x=10, anchor="w")
        self._next_btn.place(relx=1.0, rely=0.5, x=-10, anchor="e")
        self._prev_btn.bind("<Button-1>", lambda e: self._nav(-1))
        self._next_btn.bind("<Button-1>", lambda e: self._nav(1))
        self._prev_btn.bind("<Enter>", lambda e: self._prev_btn.config(fg="#ffffff"))
        self._prev_btn.bind("<Leave>", lambda e: self._prev_btn.config(fg="#cccccc"))
        self._next_btn.bind("<Enter>", lambda e: self._next_btn.config(fg="#ffffff"))
        self._next_btn.bind("<Leave>", lambda e: self._next_btn.config(fg="#cccccc"))

        # 键/鼠：Esc 关；←/→ 切换；滚轮缩放（指针锚点）；双击复位；拖拽平移
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Left>", lambda e: self._nav(-1))
        self.bind("<Right>", lambda e: self._nav(1))
        self.bind("<MouseWheel>", lambda e: self._wheel(e.delta))
        self.bind("<Button-4>", lambda e: self._wheel(120))    # Linux 上滚
        self.bind("<Button-5>", lambda e: self._wheel(-120))   # Linux 下滚
        self._canvas.bind("<Double-Button-1>", self._reset)
        self._canvas.bind("<ButtonPress-1>", self._press)
        self._canvas.bind("<B1-Motion>", self._motion)
        self._canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        self.focus_force()
        self._load(self._idx)

    # ---------- 纯数学（单测覆盖） ----------
    @staticmethod
    def clamp_zoom(z: float) -> float:
        """缩放钳制在 [ZOOM_MIN, ZOOM_MAX]。"""
        return max(ZOOM_MIN, min(ZOOM_MAX, float(z)))

    @staticmethod
    def fit_scale(w: int, h: int, vw: int, vh: int) -> float:
        """「收进视口」适配缩放（只缩不放；视口非有效值时回退 1.0）。"""
        if w <= 0 or h <= 0 or vw <= 0 or vh <= 0:
            return 1.0
        return min(vw / w, vh / h, 1.0)

    @staticmethod
    def zoom_anchor(ox: float, oy: float, px: float, py: float, ratio: float):
        """指针 (px,py) 锚点缩放：ratio=new/old，返回新偏移 (ox,oy)。
        不变量：锚点所指的图像内容点在缩放前后保持屏幕位置不动。"""
        ratio = float(ratio)
        if ratio <= 0:
            ratio = 1.0
        return (px - (px - ox) * ratio, py - (py - oy) * ratio)

    # ---------- 加载（缩略图先行 → 子线程解码原图） ----------
    def _load(self, idx: int) -> None:
        self._idx = idx % len(self._paths) if self._paths else 0
        path = self._paths[self._idx]
        self._counter.config(text=f"{self._idx + 1}/{len(self._paths)}"
                             if len(self._paths) > 1 else "")
        self._canvas.delete("all")
        self._pil = None
        self._photo = None
        self._zoom = 1.0
        self._status("加载中…")
        thumb = None
        if self._thumb_of is not None:
            try:
                thumb = self._thumb_of(path)
            except Exception:
                thumb = None
        if thumb is not None:                  # 缩略图先行（占位即清晰小图）
            self._photo = thumb
            self._pil_size = (thumb.width(), thumb.height())
            self._canvas.delete("all")
            self._canvas.create_image(0, 0, image=thumb, anchor="nw",
                                      tags=("img",))
            self._center_view(thumb.width(), thumb.height())
        self._decode(path, use_thumb=thumb is not None)

    def _decode(self, path: str, use_thumb: bool) -> None:
        seq = self._render_seq                # 会话序号：切图/再缩放后丢弃过期结果
        self._decode_use_thumb = use_thumb

        def work():
            try:
                from PIL import Image
                im = Image.open(path)
                im.load()
                res = im.convert("RGB")
            except Exception:
                res = None
            self._q.put((seq, "decode", res))   # 跨线程只投递，不碰 Tk

        threading.Thread(target=work, daemon=True, name="lightbox-dec").start()

    def _apply(self, pil, keep_view: bool = False) -> None:
        """原图就绪：落位并按当前缩放渲染（keep_view=True 时保留缩略图视角）。"""
        self._pil = pil
        self._pil_size = (pil.width, pil.height)
        if not keep_view or self._zoom == 1.0:
            vw = max(1, self._canvas.winfo_width())
            vh = max(1, self._canvas.winfo_height())
            self._zoom = self.fit_scale(pil.width, pil.height, vw, vh)
            self._center_view(pil.width, pil.height)
        self._render()

    def _status(self, text: str) -> None:
        self._canvas.delete("all")
        self._canvas.create_text(16, 16, anchor="nw", text=text, fill="#bbbbbb",
                                 font=self._font or ("TkDefaultFont", 12))

    # ---------- 视口 ----------
    def _center_view(self, w: int, h: int) -> None:
        cw = max(1, self._canvas.winfo_width())
        ch = max(1, self._canvas.winfo_height())
        self._off = ((cw - w) // 2, (ch - h) // 2)

    def _place(self) -> None:
        item = self._find_img()
        if item:
            self._canvas.coords(item, self._off[0], self._off[1])

    def _find_img(self):
        ids = self._canvas.find_withtag("img")
        return ids[0] if ids else None

    # ---------- 渲染（先拉伸后清化） ----------
    def _render(self) -> None:
        """按当前 zoom 重采样出清晰帧（大图/深放大时降级：超限只拉伸不重采样）。"""
        if self._pil is None:
            return
        w = max(1, int(self._pil_size[0] * self._zoom))
        h = max(1, int(self._pil_size[1] * self._zoom))
        seq = self._render_seq

        def work():
            try:
                from PIL import Image
                rw = min(w, _RESIZE_MAX)
                rh = min(h, _RESIZE_MAX)
                res = self._pil.resize((rw, rh), Image.LANCZOS) if \
                    (rw, rh) != self._pil_size else self._pil
                photo = None
                try:
                    from PIL import ImageTk
                    photo = ImageTk.PhotoImage(res)
                except Exception:
                    photo = None
            except Exception:
                photo = None
            self._q.put((seq, "render", photo))   # 跨线程只投递，不碰 Tk

        threading.Thread(target=work, daemon=True, name="lightbox-rs").start()

    def _poll(self) -> None:
        """主线程轮询子线程结果（解码/重采样），过期序号丢弃。"""
        try:
            while True:
                seq, kind, payload = self._q.get_nowait()
                if seq != self._render_seq:
                    continue                  # 已切图/再缩放：丢弃过期结果
                if kind == "decode":
                    if payload is None:
                        self._canvas.delete("all")
                        self._status("无法解码该图片")
                    else:
                        self._apply(payload, keep_view=self._decode_use_thumb)
                elif payload is not None:     # render：换帧（None 时保留缩略图）
                    self._photo = payload
                    self._canvas.delete("all")
                    self._canvas.create_image(self._off[0], self._off[1],
                                              image=payload, anchor="nw",
                                              tags=("img",))
        except queue.Empty:
            pass
        try:
            self.after(50, self._poll)
        except tk.TclError:
            pass                              # 窗口已销毁：停止轮询

    def _schedule_render(self) -> None:
        """缩放连发防抖：先 canvas.scale 即时拉伸跟手，40ms 静默后重采样清晰化。"""
        if self._render_job is not None:
            try:
                self.after_cancel(self._render_job)
            except Exception:
                pass
        self._render_job = self.after(40, self._flush_render)

    def _flush_render(self) -> None:
        self._render_job = None
        self._render()

    # ---------- 交互 ----------
    def _wheel(self, delta: int) -> None:
        if self._pil is None:
            return
        px, py = self._canvas.winfo_pointerx() - self._canvas.winfo_rootx(), \
            self._canvas.winfo_pointery() - self._canvas.winfo_rooty()
        old = self._zoom
        new = self.clamp_zoom(old * (ZOOM_STEP if delta > 0 else 1 / ZOOM_STEP))
        if new == old:
            return
        ratio = new / old
        ox, oy = self._find_img_offset()
        self._zoom = new
        # 即时：canvas scale 拉伸现有 item（跟手），随后防抖重采样清晰化
        self._render_seq += 1                  # 使在途重采样作废（尺寸已变）
        item = self._find_img()
        if item:
            self._canvas.scale(item, px, py, ratio, ratio)
            bx0, by0 = self._canvas.coords(item)
            self._off = (bx0, by0)
        else:
            self._off = self.zoom_anchor(ox, oy, px, py, ratio)
        self._schedule_render()

    def _find_img_offset(self):
        item = self._find_img()
        if item:
            c = self._canvas.coords(item)
            return (c[0], c[1]) if len(c) >= 2 else self._off
        return self._off

    def _reset(self, _ev=None) -> None:
        """双击复位：收进视口 + 居中。"""
        if self._pil is None:
            return
        self._render_seq += 1
        self._zoom = self.fit_scale(self._pil_size[0], self._pil_size[1],
                                    max(1, self._canvas.winfo_width()),
                                    max(1, self._canvas.winfo_height()))
        self._center_view(int(self._pil_size[0] * self._zoom),
                          int(self._pil_size[1] * self._zoom))
        self._render()

    def _press(self, ev) -> None:
        self._drag = (ev.x, ev.y, *self._find_img_offset())

    def _motion(self, ev) -> None:
        if not self._drag:
            return
        dx, dy = ev.x - self._drag[0], ev.y - self._drag[1]
        self._off = (self._drag[2] + dx, self._drag[3] + dy)
        item = self._find_img()
        if item:
            self._canvas.coords(item, self._off[0], self._off[1])

    def _nav(self, step: int) -> None:
        n = len(self._paths)
        if n <= 1:
            return
        self._render_seq += 1                 # 在途解码/重采样全部作废
        self._load((self._idx + step) % n)

    def destroy(self) -> None:
        self._render_seq += 1
        if self._render_job is not None:
            try:
                self.after_cancel(self._render_job)
            except Exception:
                pass
            self._render_job = None
        super().destroy()
