# -*- coding: utf-8 -*-
"""R38C Lottie 动画表情播放（可选依赖 rlottie + Pillow；缺失一律静态 glyph 回退）。

- LottieFrames：rlottie 解码 → 最多 32 帧预渲染（PIL，后台线程）→
  主线程物化 ImageTk.PhotoImage；帧间隔按源 fps 折算，钳 16~200ms
- LottieLabel：tk.Label 版动画（贴纸面板等部件场景）；加载中/失败/缺依赖 → 🎞
- 画布集成：attach(canvas, item, frames) 把帧轮播到已有画布 item；
  detach_canvas(canvas) 停表（msg_list 重绘前调用，防句柄悬挂）
"""
import os
import queue
import threading
import tkinter as tk

import optional

_FRAME_MAX = 32                       # 预渲染帧数上限（防大动画吃内存）
_DELAY_MIN, _DELAY_MAX = 16, 200      # 帧间隔钳制（ms）
GLYPH = "🎞"                          # 静态回退 glyph

_lock = threading.Lock()
_cache: dict = {}                     # (abspath, size) -> LottieFrames
_ITEMS: dict = {}                     # (canvas, item_id) -> {"i":int,"after":id}
_pending: queue.Queue = queue.Queue() # (master, lf, on_ready) 待主线程派发
_pollers: set = set()                 # 已启动轮询的 master（id 集合）


def available() -> bool:
    return optional.has_lottie()


class LottieFrames:
    """一段 Lottie 的预渲染帧序列（decode 在后台，materialize 必须主线程）。"""

    def __init__(self, path: str, size: int):
        self.path = path
        self.size = size
        self.state = "loading"        # loading / ready / failed
        self.pils: list = []          # 后台线程填（PIL.Image）
        self.photos: list = []        # 主线程填（ImageTk.PhotoImage）
        self.delay_ms = 33

    @property
    def ready(self) -> bool:
        return self.state == "ready" and bool(self.photos)

    def _decode_pils(self) -> None:
        """后台线程：rlottie 解码出采样帧（PIL），不碰任何 Tk 对象。"""
        from rlottie_python import LottieAnimation
        with LottieAnimation.from_file(self.path) as anim:
            total = int(anim.lottie_animation_get_totalframe() or 1)
            fps = float(anim.lottie_animation_get_framerate() or 30) or 30.0
            step = max(1, total // _FRAME_MAX)
            for f in range(0, total, step):
                try:
                    img = anim.render(frame=f)     # PIL.Image（RGBA）
                except Exception:
                    continue
                img.thumbnail((self.size, self.size))
                self.pils.append(img)
            self.delay_ms = int(max(_DELAY_MIN,
                                    min(_DELAY_MAX, 1000.0 * step / fps)))

    def _materialize(self) -> None:
        """主线程：PIL → ImageTk.PhotoImage（必须在 Tk 线程创建）。"""
        try:
            from PIL import ImageTk
            self.photos = [ImageTk.PhotoImage(p) for p in self.pils]
            self.state = "ready" if self.photos else "failed"
        except Exception:
            self.state = "failed"


def _ensure_poller(master) -> None:
    """主线程启动一次 30ms 轮询：消费解码完成队列并派发回调。

    跨线程只经 Queue 中转（非线程化 Tcl 下工作线程直接调 after 会
    RuntimeError 且被吞，回调永久丢失）；master 销毁后轮询自停。"""
    if id(master) in _pollers:
        return
    _pollers.add(id(master))

    def _drain():
        try:
            while True:
                m, lf, cb = _pending.get_nowait()
                try:
                    if m.winfo_exists():
                        _finish(m, lf, cb)
                except Exception:
                    pass
        except queue.Empty:
            pass
        try:
            master.after(30, _drain)
        except Exception:
            _pollers.discard(id(master))

    master.after(30, _drain)


def load_async(path: str, size: int, master, on_ready):
    """取（或后台加载）帧序列；仅主线程调用。

    返回就绪实例 → 直接用 photos；
    返回 None → 正在后台解码（完成后主线程回调 on_ready(lf)，lf.ready=False
    表示解码失败，调用方走静态回退，且不再有后续回调）。
    """
    key = (os.path.abspath(path), int(size))
    with _lock:
        lf = _cache.get(key)
    if lf is not None:
        return lf if lf.state == "ready" else (
            None if lf.state == "loading" else lf)   # failed 直接给调用方判
    lf = LottieFrames(path, size)
    with _lock:
        _cache[key] = lf
    _ensure_poller(master)                # 主线程先起轮询，再放后台解码

    def _work():
        try:
            lf._decode_pils()
            lf.state = "decoded"
        except Exception:
            lf.state = "failed"
        _pending.put((master, lf, on_ready))

    threading.Thread(target=_work, daemon=True, name="lottie-decode").start()
    return None


def _finish(master, lf: LottieFrames, on_ready) -> None:
    """主线程：物化 PhotoImage 后回调（失败也回调一次，通知走回退）。"""
    if lf.state == "decoded":
        lf._materialize()
    try:
        on_ready(lf)
    except Exception:
        pass


class LottieLabel(tk.Label):
    """动画贴纸 Label：缺依赖/坏文件自动回退静态 glyph；销毁自清 after。"""

    def __init__(self, master, path: str, size: int = 96, **kw):
        self._path = path
        self._size = size
        self._lf = None
        self._i = 0
        self._after = None
        kw.setdefault("text", GLYPH)
        super().__init__(master, **kw)
        if available():
            lf = load_async(path, size, self, self._on_ready)
            if lf is not None and lf.ready:       # 缓存命中直接播
                self._use(lf)

    def _on_ready(self, lf) -> None:
        if lf is not None and lf.ready and self.winfo_exists():
            self._use(lf)
        # 失败：保持 glyph（构造时已设）

    def _use(self, lf: LottieFrames) -> None:
        self._lf = lf
        self._i = 0
        self.config(text="", image=lf.photos[0])
        self._tick()

    def _tick(self) -> None:
        if self._lf is None:
            return
        try:
            self._i = (self._i + 1) % len(self._lf.photos)
            self.config(image=self._lf.photos[self._i])
        except Exception:
            self._lf = None
            return
        self._after = self.after(self._lf.delay_ms, self._tick)

    def destroy(self) -> None:
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except Exception:
                pass
            self._after = None
        self._lf = None
        super().destroy()


# ---------- 画布集成（msg_list 贴纸行） ----------

def attach(canvas, item, lf: LottieFrames) -> None:
    """把帧序列轮播到画布 item（重复 attach 同一 item 忽略）。"""
    key = (canvas, item)
    if key in _ITEMS:
        return
    _ITEMS[key] = {"i": 0, "after": None}

    def _step():
        st = _ITEMS.get(key)
        if st is None:
            return
        try:
            if not canvas.winfo_exists():
                _ITEMS.pop(key, None)
                return
            st["i"] = (st["i"] + 1) % len(lf.photos)
            canvas.itemconfig(item, image=lf.photos[st["i"]])
        except Exception:
            _ITEMS.pop(key, None)
            return
        st["after"] = canvas.after(lf.delay_ms, _step)

    _ITEMS[key]["after"] = canvas.after(lf.delay_ms, _step)


def detach_canvas(canvas) -> None:
    """停掉该画布上的全部轮播（重绘前调用；item id 会失效）。"""
    for key in [k for k in _ITEMS if k[0] is canvas]:
        st = _ITEMS.pop(key)
        if st.get("after"):
            try:
                canvas.after_cancel(st["after"])
            except Exception:
                pass


def active_count() -> int:
    """画布轮播中的动画数（测试/调试用）。"""
    return len(_ITEMS)
