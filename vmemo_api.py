# -*- coding: utf-8 -*-
"""R72 圆形视频留言：VMA1 自研容器（打包/解包）+ 录制器。

为什么不复用一个通用容器：本项目不做逐帧视频流（R45 视频是实时分片，无文件
形态），而「圆形视频留言」需要**一段可整存整取、带音轨、能一次发完**的短片。
整帧 PNG + 裸 PCM 的小容器最省事，且完全无第三方依赖。

VMA1 布局（全部大端）::

    off  size  field
    0    4     magic "VMA1"
    4    1     ver = 1
    5    1     flags（bit0 = 含音频）
    6    2     dur_ms                时长（毫秒）
    8    2     fps × 100             帧率（×100 保留两位）
    10   2     n_frames              帧数
    12   2     w                     画面宽（像素，正方形边长）
    14   2     h                     画面高
    16   2     ar                    音频采样率（8000）
    18   2     ch                    声道数（1）
    20   2     bits                  位深（16）
    22   4     audio_off             PCM 起始绝对偏移（无音频=0）
    26   4     audio_len             PCM 字节数（无音频=0）
    30   2     pad = 0
    32   4     tbl_off = 32          帧表起始绝对偏移
    36   4*n   frame_off[]          各帧起始绝对偏移
    36+4n 4*n  frame_len[]          各帧字节数
    ...        frame data           整帧 PNG（不差分、不关键帧）
    ...        PCM                  ar/ch/bits，紧邻帧数据之后

体积控制：160×120 整帧 PNG 约 8~10KB；3~5s @ ≤8fps ≤ 480KB；硬保底
``config.VMEMO_MAX_BYTES``（900KB），超限立即截断收尾（不留半截容器）。
"""
import struct
import threading
import time

import video_api
import voice_api

MAGIC = b"VMA1"
VER = 1
_HDR = struct.Struct(">4sBBHHHHHHHHIIHI")   # 固定 36B 头（见上方布局表）
_HDR_LEN = _HDR.size
_TBL_OFF = _HDR_LEN                          # 帧表紧随头部

FLAG_AUDIO = 0x01
_OUT_W, _OUT_H = 160, 120                    # 留言画幅（正方形裁切前的源尺寸）
_AUDIO_BPS = voice_api.SAMPLE_RATE * 2       # 8000Hz × 16bit × 1ch = 16000 B/s


# ================= 纯函数：打包 / 解包 =================

def pack(frames, pcm: bytes = b"", fps: int = 8, w: int = 0, h: int = 0,
         dur_ms: int = 0) -> bytes:
    """把整帧 PNG 列表 + PCM 打成 VMA1。``w``/``h`` 缺省时从首帧 PNG 头取。"""
    frames = [bytes(f) for f in frames if f]
    if not frames:
        raise ValueError("没有可用帧")
    pcm = bytes(pcm or b"")
    if not w or not h:
        try:
            w, h, _ = video_api.png_decode(frames[0])
        except Exception:
            w, h = _OUT_W, _OUT_H
    if dur_ms <= 0:
        dur_ms = int(round(1000.0 * len(frames) / max(1, int(fps))))
    n = len(frames)
    flags = FLAG_AUDIO if pcm else 0
    tbl_len = _TBL_OFF + 8 * n
    offs, lens = [], []
    cur = tbl_len
    for f in frames:
        offs.append(cur)
        lens.append(len(f))
        cur += len(f)
    audio_off = cur if pcm else 0
    audio_len = len(pcm)
    body = bytearray()
    body += _HDR.pack(MAGIC, VER, flags, max(0, min(65535, int(dur_ms))),
                      max(0, min(65535, int(round(float(fps) * 100)))),
                      n, max(0, min(65535, int(w))), max(0, min(65535, int(h))),
                      voice_api.SAMPLE_RATE, voice_api.CHANNELS, voice_api.BITS,
                      audio_off, audio_len, 0, _TBL_OFF)
    for off in offs:
        body += struct.pack(">I", off)
    for ln in lens:
        body += struct.pack(">I", ln)
    for f in frames:
        body += f
    body += pcm
    return bytes(body)


def unpack(blob: bytes) -> dict:
    """VMA1 → {ver, flags, has_audio, dur_ms, fps, w, h, ar, ch, bits,
    frames:[bytes...], pcm:bytes}。非法数据抛 ValueError。"""
    blob = bytes(blob or b"")
    if len(blob) < _HDR_LEN:
        raise ValueError("容器过短")
    (magic, ver, flags, dur_ms, fps100, n, w, h, ar, ch, bits,
     audio_off, audio_len, _pad, tbl_off) = _HDR.unpack(blob[:_HDR_LEN])
    if magic != MAGIC:
        raise ValueError("magic 不匹配")
    if ver != VER:
        raise ValueError(f"不支持的版本 {ver}")
    if n <= 0 or n > 4096:
        raise ValueError("帧数非法")
    tbl_end = tbl_off + 8 * n
    if tbl_off < _HDR_LEN or tbl_end > len(blob):
        raise ValueError("帧表越界")
    offs = [struct.unpack_from(">I", blob, tbl_off + 4 * i)[0]
            for i in range(n)]
    lens = [struct.unpack_from(">I", blob, tbl_off + 4 * n + 4 * i)[0]
            for i in range(n)]
    frames = []
    for off, ln in zip(offs, lens):
        if ln <= 0 or off < tbl_end or off + ln > len(blob):
            raise ValueError("帧数据越界")
        frames.append(blob[off:off + ln])
    pcm = b""
    if (flags & FLAG_AUDIO) and audio_len > 0:
        if audio_off < tbl_end or audio_off + audio_len > len(blob):
            raise ValueError("音轨越界")
        pcm = blob[audio_off:audio_off + audio_len]
    return {"ver": ver, "flags": flags, "has_audio": bool(flags & FLAG_AUDIO),
            "dur_ms": dur_ms, "fps": fps100 / 100.0, "n_frames": n,
            "w": w, "h": h, "ar": ar, "ch": ch, "bits": bits,
            "frames": frames, "pcm": pcm}


def first_frame_png(blob: bytes):
    """取首帧 PNG（网页端静态缩略图用）；失败返回 None，绝不抛。"""
    try:
        d = unpack(blob)
        return d["frames"][0] if d["frames"] else None
    except Exception:
        return None


def describe(blob: bytes) -> dict | None:
    """轻量元信息（不解 PCM/帧内容之外的拷贝）；失败返回 None。"""
    try:
        d = unpack(blob)
    except Exception:
        return None
    return {"dur_ms": d["dur_ms"], "fps": d["fps"], "n_frames": d["n_frames"],
            "has_audio": d["has_audio"]}


def _subsample(rows, w: int, h: int):
    """RGB24 行列表 2× 抽稀（横竖各隔一）→ (w//2, h//2, 新行列表)。"""
    tw, th = max(1, w // 2), max(1, h // 2)
    out = []
    for y in range(0, h - 1, 2):
        src = rows[y]
        row = bytearray(tw * 3)
        j = 0
        for x in range(0, tw):
            o = x * 6
            row[j:j + 3] = src[o:o + 3]
            j += 3
        out.append(bytes(row))
    while len(out) < th:                    # 奇数高时补一行（防尺寸不符）
        out.append(out[-1] if out else bytes(tw * 3))
    return tw, out[:th]


# ================= 录制器 =================

class VmemoRecorder:
    """按住录制 → 松手 finish()；采集摄像头（2× 抽稀）+ 麦克风，产出 VMA1。

    on_done(blob) 在录制结束线程回调；on_error(text) 设备异常回调。两者都只调
    一次。达到 ``max_dur`` 或 ``max_bytes`` 自动收尾（不需要调用方干预）。
    """

    def __init__(self, on_done, on_error=None, fps: int = 8,
                 max_dur: float = 5.0, max_bytes: int = 900 * 1024):
        self.on_done = on_done
        self.on_error = on_error
        self.fps = max(1, min(int(fps), video_api.TARGET_FPS))
        self.max_dur = max(0.5, float(max_dur))
        self.max_bytes = max(64 * 1024, int(max_bytes))
        self._lock = threading.RLock()
        self._frames = []
        self._pcm = bytearray()
        self._bytes = 0
        self._active = False
        self._done = False
        self._cam = None
        self._mic = None
        self._drain = None
        self._timer = None
        self._t0 = 0.0

    # ---------- 对外 ----------

    def start(self) -> bool:
        """起摄像头 + 麦克风。无摄像头/无音频设备 → on_error 并返回 False。"""
        with self._lock:
            if self._active:
                return True
            if not video_api.available():
                self._fail("本机没有可用摄像头，无法录制视频留言")
                return False
            if not voice_api.available():
                self._fail("本机没有可用麦克风，无法录制视频留言")
                return False
            self._frames, self._pcm = [], bytearray()
            self._bytes, self._done = 0, False
            self._t0 = time.time()
            self._active = True
        self._cam = video_api.CamRecorder(on_frame=self._on_frame,
                                         on_error=self._cam_fail, fps=self.fps)
        if not self._cam.start():
            with self._lock:
                self._active = False
            return False
        self._mic = voice_api.MicRecorder(on_error=self._mic_fail)
        if not self._mic.start():
            self.stop()
            self._fail("麦克风打开失败（可能被其它程序占用）")
            return False
        self._drain = threading.Thread(target=self._drain_loop, daemon=True,
                                       name="vmemo-mic")
        self._drain.start()
        self._timer = threading.Thread(target=self._timer_loop, daemon=True,
                                       name="vmemo-timer")
        self._timer.start()
        return True

    def elapsed(self) -> float:
        return time.time() - self._t0 if self._t0 else 0.0

    def is_active(self) -> bool:
        return self._active and not self._done

    def finish(self) -> None:
        """正常收尾：停设备 → 打包 → on_done(blob)。幂等。"""
        with self._lock:
            if self._done:
                return
            self._done = True
            self._active = False
            frames = list(self._frames)
            pcm = bytes(self._pcm)
            dur_ms = int(round(self.elapsed() * 1000))
        self._shutdown_devices()
        if not frames:
            self._fail("没有采集到画面")
            return
        pcm = pcm[:max(0, int(_AUDIO_BPS * dur_ms / 1000.0))]
        try:
            blob = pack(frames, pcm, fps=self.fps, dur_ms=dur_ms)
        except Exception as e:
            self._fail(f"视频留言打包失败：{e}")
            return
        cb, self.on_done = self.on_done, None
        if cb:
            try:
                cb(blob)
            except Exception:
                pass

    def cancel(self) -> None:
        """放弃录制（不发 on_done）。"""
        with self._lock:
            if self._done:
                return
            self._done = True
            self._active = False
            self._frames, self._pcm = [], bytearray()
        self._shutdown_devices()

    def stop(self) -> None:
        """停采集设备（不改 _done；供失败路径复用）。"""
        self._shutdown_devices()

    # ---------- 内部 ----------

    def _shutdown_devices(self) -> None:
        with self._lock:
            self._active = False
            cam, self._cam = self._cam, None
            mic, self._mic = self._mic, None
        if cam is not None:
            try:
                cam.stop()
            except Exception:
                pass
        if mic is not None:
            try:
                mic.stop()
            except Exception:
                pass

    def _on_frame(self, png: bytes) -> None:
        """采集线程回调：抽稀到 160×120 再重编码，按体积/时长闸门收尾。"""
        with self._lock:
            if not self._active or self._done:
                return
            if self.elapsed() >= self.max_dur:
                over = True
            else:
                over = False
        if over:
            self.finish()
            return
        try:
            w, h, rows = video_api.png_decode(png)
            tw, small = _subsample(rows, w, h)
            out = video_api.png_encode(small, tw, len(small))
        except Exception:
            return
        with self._lock:
            if not self._active or self._done:
                return
            if self._bytes + len(out) > self.max_bytes:
                hit_cap = True
            else:
                hit_cap = False
                self._frames.append(out)
                self._bytes += len(out)
        if hit_cap:
            self.finish()

    def _drain_loop(self) -> None:
        """把麦克风 20ms 帧队列搬进 _pcm；超时长即退出。"""
        while True:
            with self._lock:
                if not self._active:
                    return
                mic = self._mic
            if mic is None:
                return
            if self.elapsed() >= self.max_dur:
                return
            try:
                fr = mic.frames.get(timeout=0.05)
            except Exception:
                continue
            with self._lock:
                if self._active and not self._done:
                    self._pcm.extend(fr)

    def _timer_loop(self) -> None:
        """到达 max_dur 自动收尾（避免调用方一直按住不松手）。"""
        while True:
            time.sleep(0.05)
            with self._lock:
                if not self._active or self._done:
                    return
            if self.elapsed() >= self.max_dur:
                self.finish()
                return

    def _cam_fail(self, text: str) -> None:
        with self._lock:
            if self._done:
                return
        self._fail(str(text))

    def _mic_fail(self, text: str) -> None:
        with self._lock:
            if self._done:
                return
        self._fail(str(text))

    def _fail(self, text: str) -> None:
        with self._lock:
            if self._done:
                return
            self._done = True
            self._active = False
        self._shutdown_devices()
        cb, self.on_error = self.on_error, None
        if cb:
            try:
                cb(str(text))
            except Exception:
                pass