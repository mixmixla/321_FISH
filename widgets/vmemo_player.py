# -*- coding: utf-8 -*-
"""R72 圆形视频留言播放器：圆形裁剪 · 循环播放 · 含声音。

- 容器解析走 `vmemo_api.unpack`（VMA1：整帧 PNG + 8kHz/16bit 单声道 PCM）
- 圆形裁剪：**加粗圆环轮廓遮罩**——一条与窗体同色的圆环（内缘恰为内切圆）一次性
  盖住画面四角，等价于「四角扇形遮罩」但只需 1 个 canvas item；全程无逐像素 alpha，
  40 帧 @8fps 只有一次 itemconfig，性能稳（计划 §3.3 的实现手法）
- 播放：`after()` 按 fps 换帧，**默认循环**直到点击暂停；点击画面＝暂停/继续
- 声音：`voice_api.SpkPlayer`（同 1v1 通话播放器），按视频帧节拍分步喂帧，
  避免把 5s PCM 一次性灌满 jitter 队列（队列上限 100 帧＝2s）
"""
import base64
import tkinter as tk

import vmemo_api
import voice_api

FONT_FAMILY = "Microsoft YaHei UI"

_BG = "#ffffff"
_GREEN = "#2e9e5b"
_GREY = "#f2f3f5"
_DIM = "#9aa0a6"
_STAGE = "#111111"

_PAD = 10                       # 圆形画面与窗体边距
_MAX_D = 280                    # 圆形画面直径上限（不含边距）
_AUDIO_FRAME = voice_api.FRAME_BYTES


class VmemoPlayer(tk.Toplevel):
    """视频留言播放窗（一个客户端可开多个；关闭即释放播放器）。"""

    def __init__(self, master, *, blob: bytes, on_close=None,
                 title: str = "视频留言"):
        super().__init__(master)
        self._on_close = on_close
        self._closed = False
        self._playing = False
        self._loop = True
        self._job = None
        self._idx = 0
        self._acur = 0
        self._spk = None
        self._photos = []
        self._D = 120
        self._title = title

        data = vmemo_api.unpack(bytes(blob or b""))
        self._frames = list(data.get("frames") or [])
        self._pcm = bytes(data.get("pcm") or b"")
        self._fps = max(1, min(30, int(data.get("fps") or 8)))
        self._frame_ms = 1000.0 / self._fps
        self._dur_ms = int(data.get("dur_ms") or 0)
        if not self._dur_ms and self._frames:
            self._dur_ms = int(len(self._frames) * self._frame_ms)

        self.title(title)
        self.configure(bg=_BG)
        self.protocol("WM_DELETE_WINDOW", self._just_close)

        self.lbl_title = tk.Label(
            self, name="vmemo_title", bg=_BG, fg="#222",
            font=(FONT_FAMILY, 11, "bold"),
            text=f"⭕ {self._dur_ms / 1000.0:.1f}s"
                 f" · {self._fps}fps · "
                 f"{'🔊 有声' if self._pcm else '🔇 无声'}")
        self.lbl_title.pack(pady=(10, 2))

        self._decode_frames()
        side = self._D + 2 * _PAD
        self.canvas = tk.Canvas(self, name="vmemo_canvas", width=side,
                                height=side, bg=_BG, highlightthickness=0)
        self.canvas.pack(padx=8, pady=4)
        self.canvas.bind("<ButtonPress-1>", lambda _e: self._toggle_play())
        self._build_stage()

        bar = tk.Frame(self, bg=_BG, name="vmemo_bar")
        bar.pack(pady=(2, 10))
        self.btn_play = tk.Label(bar, text="⏸ 暂停", name="vmemo_play",
                                 font=(FONT_FAMILY, 10), bg=_GREY, fg="#333",
                                 padx=18, pady=6, cursor="hand2")
        self.btn_play.bind("<ButtonPress-1>", lambda _e: self._toggle_play())
        self.btn_play.pack(side="left", padx=6)
        self.btn_loop = tk.Label(bar, text="🔁 循环：开", name="vmemo_loop",
                                 font=(FONT_FAMILY, 10), bg=_GREY, fg=_GREEN,
                                 padx=14, pady=6, cursor="hand2")
        self.btn_loop.bind("<ButtonPress-1>", lambda _e: self._toggle_loop())
        self.btn_loop.pack(side="left", padx=6)

        self.lbl_hint = tk.Label(self, text="点击圆画面可暂停/继续",
                                 name="vmemo_hint", bg=_BG, fg=_DIM,
                                 font=(FONT_FAMILY, 8))
        self.lbl_hint.pack(pady=(0, 8))

        self._set_playing(True)
        self.lift()

    # ---------- 帧解码与舞台 ----------

    def _decode_frames(self) -> None:
        """全部帧一次性解成 PhotoImage（40 帧量级，开销可忽略），并按需放大。"""
        zoom = 1
        if self._frames:
            try:
                probe = tk.PhotoImage(data=base64.b64encode(self._frames[0]))
                ph = probe.height() or 120
                for z in (3, 2, 1):          # 取最大整数倍使直径 ≤ _MAX_D
                    if ph * z <= _MAX_D:
                        zoom = z
                        break
                self._D = min(_MAX_D, ph * zoom)
            except Exception:
                zoom = 1
        for png in self._frames:
            try:
                img = tk.PhotoImage(data=base64.b64encode(png))
            except Exception:
                continue
            if zoom > 1:
                try:
                    img = img.zoom(zoom)
                except Exception:
                    pass
            self._photos.append(img)

    def _build_stage(self) -> None:
        """搭圆形舞台：底圆 + 首帧 + 圆环遮罩（盖四角）+ 细描边。"""
        c = self.canvas
        d = self._D
        side = d + 2 * _PAD
        cx = cy = side / 2
        r = d / 2
        c.delete("all")
        c.create_oval(cx - r, cy - r, cx + r, cy + r,
                      fill=_STAGE, outline="")
        if not self._photos:
            c.create_text(cx, cy, text="无画面", fill="#ffffff",
                          font=(FONT_FAMILY, 10))
        # 画面（先画，遮罩盖在其上）
        self._img_id = c.create_image(
            cx, cy, image=(self._photos[0] if self._photos else None),
            anchor="center")
        # 圆环遮罩：内缘 = 内切圆（半径 r），外缘 0.74d ≥ 对角线 0.707d → 四角全盖
        R = 0.62 * d
        c.create_oval(cx - R, cy - R, cx + R, cy + R,
                      outline=_BG, width=int(0.24 * d) + 2)
        c.create_oval(cx - r, cy - r, cx + r, cy + r,
                      outline="#e2e2e2", width=1)

    def _show(self, idx: int) -> None:
        """换帧（只 itemconfig，不重建 item）。"""
        if not self._photos:
            return
        try:
            self.canvas.itemconfig(self._img_id,
                                   image=self._photos[idx % len(self._photos)])
        except Exception:
            pass

    # ---------- 播放控制 ----------

    def _toggle_play(self) -> None:
        self._set_playing(not self._playing)

    def _toggle_loop(self) -> None:
        self._loop = not self._loop
        self.btn_loop.config(text="🔁 循环：开" if self._loop else "➡ 循环：关",
                             fg=(_GREEN if self._loop else "#666"))

    def _set_playing(self, on: bool) -> None:
        """开始/暂停（暂停＝停定时器 + 停喂音频；播放器保留避免重开设备）。"""
        self._playing = bool(on)
        self.btn_play.config(text="⏸ 暂停" if on else "▶ 播放")
        if on:
            if self._spk is None:
                self._spk = voice_api.SpkPlayer()
                if not self._spk.start():
                    self._spk = None            # 无音频设备：静音播放
            self._feed_audio()
            self._tick_play()
        elif self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _tick_play(self) -> None:
        """按 fps 换帧；非循环模式播到末尾自动停。"""
        self._job = None
        if self._closed or not self._playing or not self._photos:
            return
        nxt = self._idx + 1
        if nxt >= len(self._photos):
            if not self._loop:
                self._set_playing(False)
                return
            nxt = 0
            self._acur = 0                       # 循环 → 音频回到开头
        self._idx = nxt
        self._show(self._idx)
        self._feed_audio()
        try:
            self._job = self.after(max(20, int(self._frame_ms)), self._tick_play)
        except Exception:
            self._job = None

    def _feed_audio(self) -> None:
        """按视频节拍分步喂 PCM（每帧 = 20ms 音频帧 × 每帧毫秒数）。"""
        spk = self._spk
        if spk is None or not self._pcm:
            return
        step = _AUDIO_FRAME * max(1, int(round(self._frame_ms / 20.0)))
        if self._acur >= len(self._pcm):
            self._acur = 0
        chunk = self._pcm[self._acur:self._acur + step]
        self._acur += step
        for i in range(0, len(chunk), _AUDIO_FRAME):
            spk.feed(chunk[i:i + _AUDIO_FRAME])

    # ---------- 收尾 ----------

    def _just_close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._set_playing(False)
        spk, self._spk = self._spk, None
        if spk is not None:
            try:
                spk.stop()
            except Exception:
                pass
        if self._on_close is not None:
            try:
                self._on_close()
            except Exception:
                pass
        self.destroy()