# -*- coding: utf-8 -*-
"""R38 语音对讲音频层（winmm ctypes 纯标准库，无第三方依赖）。

规格：8kHz / 16bit / 单声道 / 20ms 帧（8000*0.02*2 = 320 字节 PCM）。
- MicRecorder：waveInOpen(CALLBACK_FUNCTION) + 4 缓冲轮转；回调内仅
  「拷贝入队 + 重新挂缓冲」，异常一律吞掉（winmm 回调里抛错会崩进程）；
- SpkPlayer：waveOutOpen + 8 header 池；播放线程从 jitter 队列取帧，
  不足 3 帧先垫静音（underrun 防爆音），WOM_DONE 回调 unprepare 并归还池；
- 探测：waveInGetNumDevs()==0 或非 Windows → AVAILABLE=False（UI 降级）。
"""
import collections
import ctypes
import os
import queue
import threading

SAMPLE_RATE = 8000
CHANNELS = 1
BITS = 16
FRAME_MS = 20
FRAME_BYTES = SAMPLE_RATE * FRAME_MS // 1000 * CHANNELS * BITS // 8   # 320

JITTER_MIN = 4          # 播放前至少缓冲帧数（R39A 全双工 80ms 预缓冲防爆音）
_POOL = 8               # 播放 header 池

_AVAILABLE = None       # 惰性探测结果缓存


def available() -> bool:
    """本机是否具备音频采集能力（非 Windows / 无输入设备 → False）。"""
    global _AVAILABLE
    if _AVAILABLE is None:
        if os.name != "nt":
            _AVAILABLE = False
        else:
            try:
                _AVAILABLE = _winmm().waveInGetNumDevs() > 0
            except Exception:
                _AVAILABLE = False
    return _AVAILABLE


def _winmm():
    winmm = ctypes.windll.winmm
    return winmm


# ---------- 功能③ 语音倍速（播放前对 WAV 做 PCM 变速重采样） ----------
# winsound 只按文件自带采样率播放、不支持 rate/speed 参数。为支持 0.5x/1.5x/2x，
# 我们在播放前把 PCM 按 factor 重采样：保持采样率不动、增减样本数 → 播放时长随之
# 缩短/拉长，实现变速（经典磁带变速，音调随速变化；纯标准库、无新增依赖）。
_RIFF_SPEEDS = (0.5, 1.0, 1.5, 2.0)          # 合法倍速档（msg_list 循环切换用）


def parse_speed(v):
    """功能③：把任意字符串/数字解析为合法倍速浮点；非法/越界回落 1.0。"""
    try:
        r = float(v)
    except (TypeError, ValueError):
        return 1.0
    if r <= 0.0 or r > 4.0:
        return 1.0
    return r


def resample_wav(wav: bytes, rate: float) -> bytes:
    """功能③：把 G 16-bit PCM 的 WAV 按 factor 变速重采样，返回新 WAV 字节。

    rate>1 变快、rate<1 变慢、rate==1 原样返回。解析最小 RIFF/WAVE 头
    （"fmt "/"data" 块），仅处理 16-bit PCM；不支持时原样返回（降级正常速）。
    """
    if not wav or wav[8:12] != b"WAVE":
        return wav
    rate = parse_speed(rate)
    if abs(rate - 1.0) < 1e-9:
        return wav
    # 扫描块：取 fmt 的 channels/sampleRate/bits 与 data 偏移/长度
    channels = sample_rate = bits = None
    data_off = data_len = None
    pos = 12
    total = len(wav)
    while pos + 8 <= total:
        cid = wav[pos:pos + 4]
        csz = int.from_bytes(wav[pos + 4:pos + 8], "little")
        body = pos + 8
        if cid == b"fmt " and csz >= 16:
            import struct as _s
            _avail = _s.unpack_from("<H", wav, body)[0]
            channels = _s.unpack_from("<H", wav, body + 2)[0]
            sample_rate = _s.unpack_from("<I", wav, body + 4)[0]
            bits = _s.unpack_from("<H", wav, body + 14)[0]
        elif cid == b"data":
            data_off = body
            data_len = csz
            break
        pos = body + csz + (csz & 1)          # 块按双字节对齐
    if not (data_off is not None and channels == 1 and bits == 16 and sample_rate):
        return wav                            # 非 16-bit 单声道 → 不重采样
    orig = wav[data_off:data_off + data_len]
    n = len(orig) // 2
    if n <= 0:
        return wav
    new_n = max(1, int(round(n / rate)))
    import struct as _s
    out = bytearray(new_n * 2)
    for i in range(new_n):
        p = i * rate
        i0 = int(p)
        i1 = n - 1 if i0 + 1 > n - 1 else i0 + 1
        x0 = _s.unpack_from("<h", orig, i0 * 2)[0]
        x1 = _s.unpack_from("<h", orig, i1 * 2)[0]
        v = x0 + (x1 - x0) * (p - i0)
        _s.pack_into("<h", out, i * 2, int(round(v)))
    new_data = bytes(out)
    byte_rate = sample_rate * 2
    header = (b"RIFF" + (36 + len(new_data)).to_bytes(4, "little") + b"WAVE"
              + b"fmt " + (16).to_bytes(4, "little")
              + (1).to_bytes(2, "little")          # PCM 格式标签
              + (1).to_bytes(2, "little")          # 单声道
              + sample_rate.to_bytes(4, "little")
              + byte_rate.to_bytes(4, "little")
              + (2).to_bytes(2, "little")          # 块对齐
              + (16).to_bytes(2, "little")         # 位深
              + b"data" + len(new_data).to_bytes(4, "little"))
    return header + new_data


if os.name == "nt":
    import ctypes.wintypes as wt

    class WAVEFORMATEX(ctypes.Structure):
        _fields_ = [("wFormatTag", wt.WORD),
                    ("nChannels", wt.WORD),
                    ("nSamplesPerSec", wt.DWORD),
                    ("nAvgBytesPerSec", wt.DWORD),
                    ("nBlockAlign", wt.WORD),
                    ("wBitsPerSample", wt.WORD),
                    ("cbSize", wt.WORD)]

    class WAVEHDR(ctypes.Structure):
        _fields_ = [("lpData", ctypes.c_char_p),
                    ("dwBufferLength", wt.DWORD),
                    ("dwBytesRecorded", wt.DWORD),
                    ("dwUser", ctypes.c_size_t),
                    ("dwFlags", wt.DWORD),
                    ("dwLoops", wt.DWORD),
                    ("lpNext", ctypes.c_void_p),
                    ("reserved", ctypes.c_size_t)]

    _WAVE_MAPPER = 0xFFFFFFFF          # (UINT)-1
    _WAVE_FORMAT_PCM = 1
    _CALLBACK_FUNCTION = 0x30000
    _WIM_DATA = 0x3C0
    _WOM_DONE = 0x3BD
    _WHDR_DONE = 0x1

    _PROC = ctypes.WINFUNCTYPE(
        None, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p)


    class MicRecorder:
        """麦克风采集：start() 后后台持续填帧到 frames 队列；stop() 释放设备。"""

        def __init__(self, on_error=None) -> None:
            self.frames: "queue.Queue[bytes]" = queue.Queue(maxsize=200)
            self._on_error = on_error          # 设备级异常回调（UI 提示/挂断）
            self._h = None
            self._hdrs = []
            self._bufs = []
            self._proc = None
            self._running = False
            self._lock = threading.Lock()

        def start(self) -> bool:
            if not available():
                return False
            with self._lock:
                if self._running:
                    return True
                winmm = _winmm()
                fmt = WAVEFORMATEX(_WAVE_FORMAT_PCM, CHANNELS, SAMPLE_RATE,
                                   SAMPLE_RATE * CHANNELS * BITS // 8,
                                   CHANNELS * BITS // 8, BITS, 0)
                h = ctypes.c_void_p()
                # 回调持引用防 GC
                self._proc = _PROC(self._callback)
                rc = winmm.waveInOpen(ctypes.byref(h), _WAVE_MAPPER,
                                      ctypes.byref(fmt), self._proc, 0,
                                      _CALLBACK_FUNCTION)
                if rc != 0:
                    self._proc = None
                    return False
                self._h = h
                self._hdrs = []
                self._bufs = []
                for _ in range(4):
                    buf = ctypes.create_string_buffer(FRAME_BYTES)
                    hdr = WAVEHDR()
                    hdr.lpData = ctypes.cast(buf, ctypes.c_char_p)
                    hdr.dwBufferLength = FRAME_BYTES
                    rc = winmm.waveInPrepareHeader(h, ctypes.byref(hdr),
                                                   ctypes.sizeof(hdr))
                    if rc != 0:
                        continue
                    rc = winmm.waveInAddBuffer(h, ctypes.byref(hdr),
                                               ctypes.sizeof(hdr))
                    if rc != 0:
                        winmm.waveInUnprepareHeader(h, ctypes.byref(hdr),
                                                    ctypes.sizeof(hdr))
                        continue
                    self._hdrs.append(hdr)
                    self._bufs.append(buf)
                if not self._hdrs:
                    self.stop()
                    return False
                self._running = True
                winmm.waveInStart(h)
                return True

        def stop(self) -> None:
            with self._lock:
                h, self._h = self._h, None
                hdrs, self._hdrs = self._hdrs, []
                bufs, self._bufs = self._bufs, []
                self._running = False
            if h is None:
                self._proc = None
                return
            winmm = _winmm()
            try:
                winmm.waveInReset(h)
                for hdr in hdrs:
                    winmm.waveInUnprepareHeader(h, ctypes.byref(hdr),
                                                ctypes.sizeof(hdr))
                winmm.waveInClose(h)
            except Exception:
                pass
            self._proc = None
            # 清空残留帧，避免下次通话误播旧音频
            try:
                while True:
                    self.frames.get_nowait()
            except queue.Empty:
                pass

        def _callback(self, _h, msg, _inst, param1, _param2) -> None:
            """winmm 回调：仅拷贝入队 + 重新挂缓冲；任何异常吞掉（回调里抛错崩进程）。"""
            try:
                if msg != _WIM_DATA or not self._running:
                    return
                hdr = ctypes.cast(param1, ctypes.POINTER(WAVEHDR)).contents
                got = int(hdr.dwBytesRecorded)
                if got > 0:
                    buf = ctypes.string_at(hdr.lpData, got)
                    try:
                        self.frames.put_nowait(buf)
                    except queue.Full:
                        pass                      # 丢帧优于阻塞音频回调
                if self._h is not None:
                    _winmm().waveInAddBuffer(self._h, ctypes.byref(hdr),
                                             ctypes.sizeof(hdr))
            except Exception as exc:
                try:
                    if self._on_error is not None:
                        self._on_error(f"采集异常: {exc}")
                except Exception:
                    pass


    class SpkPlayer:
        """扬声器播放：feed() 进 jitter 队列；内部线程出帧 waveOutWrite。

        underrun（缓冲不足 JITTER_MIN 帧）垫静音，避免爆音；stop() 释放设备。
        """

        def __init__(self, on_error=None) -> None:
            self._jitter: "queue.Queue[bytes]" = queue.Queue(maxsize=100)
            self._on_error = on_error
            self._h = None
            self._proc = None
            self._free: collections.deque = collections.deque()
            self._pool = []                    # (hdr, buffer) 池
            self._running = False
            self._thread = None
            self._cond = threading.Condition()

        def start(self) -> bool:
            if not available():
                return False
            with self._cond:
                if self._running:
                    return True
                winmm = _winmm()
                fmt = WAVEFORMATEX(_WAVE_FORMAT_PCM, CHANNELS, SAMPLE_RATE,
                                   SAMPLE_RATE * CHANNELS * BITS // 8,
                                   CHANNELS * BITS // 8, BITS, 0)
                h = ctypes.c_void_p()
                self._proc = _PROC(self._callback)
                rc = winmm.waveOutOpen(ctypes.byref(h), _WAVE_MAPPER,
                                       ctypes.byref(fmt), self._proc, 0,
                                       _CALLBACK_FUNCTION)
                if rc != 0:
                    self._proc = None
                    return False
                self._h = h
                self._pool = []
                for _ in range(_POOL):
                    buf = ctypes.create_string_buffer(FRAME_BYTES)
                    hdr = WAVEHDR()
                    hdr.lpData = ctypes.cast(buf, ctypes.c_char_p)
                    self._pool.append((hdr, buf))
                    self._free.append((hdr, buf))
                self._running = True
                self._thread = threading.Thread(target=self._pump, daemon=True,
                                                name="spk-pump")
                self._thread.start()
                return True

        def feed(self, pcm: bytes) -> None:
            """喂入一帧解码后的 PCM（长度不足帧补齐，超长截断）。"""
            try:
                self._jitter.put_nowait(pcm)
            except queue.Full:
                try:
                    self._jitter.get_nowait()  # 丢旧帧保实时
                    self._jitter.put_nowait(pcm)
                except (queue.Empty, queue.Full):
                    pass

        def stop(self) -> None:
            self._running = False
            with self._cond:
                self._cond.notify_all()
            t, self._thread = self._thread, None
            if t is not None:
                t.join(timeout=1.0)
            h, self._h = self._h, None
            if h is not None:
                winmm = _winmm()
                try:
                    winmm.waveOutReset(h)
                    for hdr, _buf in self._pool:
                        winmm.waveOutUnprepareHeader(h, ctypes.byref(hdr),
                                                     ctypes.sizeof(hdr))
                    winmm.waveOutClose(h)
                except Exception:
                    pass
            self._pool = []
            self._free.clear()
            self._proc = None
            try:
                while True:
                    self._jitter.get_nowait()
            except queue.Empty:
                pass

        def _prime(self) -> int:
            """开播预缓冲：等 jitter 队列攒到 JITTER_MIN 帧（或短超时即播）。

            独立方法便于测试（欠载提前开播 / 足量即返回）。
            """
            buffered = 1
            while buffered < JITTER_MIN:
                try:
                    self._jitter.get(timeout=0.05)
                    buffered += 1
                except queue.Empty:
                    break
            return buffered

        def _callback(self, _h, msg, _inst, param1, _param2) -> None:
            """WOM_DONE：unprepare 后把 header 归还空闲池；异常吞掉。"""
            try:
                if msg != _WOM_DONE:
                    return
                winmm = _winmm()
                hdr = ctypes.cast(param1, ctypes.POINTER(WAVEHDR)).contents
                winmm.waveOutUnprepareHeader(self._h, ctypes.byref(hdr),
                                             ctypes.sizeof(hdr))
                for pair in self._pool:
                    if pair[0] is hdr:
                        with self._cond:
                            self._free.append(pair)
                            self._cond.notify_all()
                        break
            except Exception as exc:
                try:
                    if self._on_error is not None:
                        self._on_error(f"播放异常: {exc}")
                except Exception:
                    pass

        def _pump(self) -> None:
            # 先攒 jitter buffer 再开播（防开头 underrun）
            primed = False
            while self._running:
                try:
                    pcm = self._jitter.get(timeout=0.1)
                except queue.Empty:
                    continue
                if not primed:
                    self._prime()
                    primed = True
                with self._cond:
                    while self._running and not self._free:
                        self._cond.wait(timeout=0.2)
                    if not self._running:
                        return
                    hdr, buf = self._free.popleft()
                data = (pcm or b"")[:FRAME_BYTES].ljust(FRAME_BYTES, b"\x00")
                ctypes.memmove(buf, data, FRAME_BYTES)
                hdr.dwBufferLength = FRAME_BYTES
                hdr.dwFlags = 0
                winmm = _winmm()
                if winmm.waveOutPrepareHeader(self._h, ctypes.byref(hdr),
                                              ctypes.sizeof(hdr)) == 0:
                    winmm.waveOutWrite(self._h, ctypes.byref(hdr),
                                       ctypes.sizeof(hdr))
else:
    class MicRecorder:                     # 非 Windows：占位（available()=False）
        def __init__(self, on_error=None) -> None:
            self.frames = queue.Queue()

        def start(self) -> bool:
            return False

        def stop(self) -> None:
            pass

    class SpkPlayer:
        def __init__(self, on_error=None) -> None:
            pass

        def start(self) -> bool:
            return False

        def feed(self, pcm: bytes) -> None:
            pass

        def stop(self) -> None:
            pass
