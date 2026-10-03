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

from config import CFG

SAMPLE_RATE = 8000
CHANNELS = 1
BITS = 16
FRAME_MS = 20
FRAME_BYTES = SAMPLE_RATE * FRAME_MS // 1000 * CHANNELS * BITS // 8   # 320

JITTER_MIN = 4          # 播放前至少缓冲帧数（R39A 全双工 80ms 预缓冲防爆音）
_POOL = 8               # 播放 header 池

_AVAILABLE = None       # 惰性探测结果缓存


class _AsyncErrorReporter:
    """把设备错误交给独立线程，避免回调/生命周期锁同步互相等待。"""

    def __init__(self, callback) -> None:
        self._callback = callback
        self._queue = queue.Queue()
        self._thread = None
        if callback is not None:
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            name="audio-error")
            self._thread.start()

    def report(self, message: str) -> None:
        if self._callback is None:
            return
        try:
            self._queue.put_nowait(str(message))
        except Exception:
            pass

    def _run(self) -> None:
        while True:
            message = self._queue.get()
            try:
                self._callback(message)
            except Exception:
                # 设备错误回调属于降级通知，不能反过来杀掉音频线程。
                pass


def available() -> bool:
    """本机是否具备音频采集能力（非 Windows / 无输入设备 → False）。"""
    global _AVAILABLE
    # REL-01 hardware=0 is a hard gate: do not even load/query winmm device
    # counts.  Existing callers receive the same unavailable result used on a
    # machine without an input device.
    if not getattr(CFG, "hardware_enabled", True):
        return False
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
        # 原始指针必须保持为 c_void_p；c_char_p 读取字段会自动转成以
        # NUL 截断的 bytes，含 0x00 的 PCM 帧会因此读错长度/越界。
        _fields_ = [("lpData", ctypes.c_void_p),
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
        """麦克风采集；waveIn 回调只拷贝帧并通知普通线程重挂缓冲。"""

        def __init__(self, on_error=None) -> None:
            self.frames: "queue.Queue[bytes]" = queue.Queue(maxsize=200)
            self._on_error = on_error
            self._error_reporter = _AsyncErrorReporter(on_error)
            self._h = None
            self._hdrs = []                  # 直到 waveInClose 完成前保持引用
            self._bufs = []
            self._proc = None                # 直到 waveInClose 完成前保持引用
            self._running = False
            self._lock = threading.Lock()
            self._lifecycle = threading.Lock()
            self._native_lock = threading.Lock()
            self._events = queue.Queue()     # callback -> pump（无界，绝不丢重挂事件）
            self._stop_event = threading.Event()
            self._worker = None

        @staticmethod
        def _drain(q) -> None:
            try:
                while True:
                    q.get_nowait()
            except queue.Empty:
                pass

        def _finish_device(self, h, hdrs, worker) -> None:
            """等待重挂线程后 Reset/Unprepare/Close，最后才释放 ctypes 引用。"""
            self._stop_event.set()
            if worker is not None and worker is not threading.current_thread():
                worker.join()
            if h is not None:
                with self._native_lock:
                    try:
                        winmm = _winmm()
                    except Exception:
                        winmm = None
                    if winmm is not None:
                        try:
                            winmm.waveInReset(h)
                        except Exception:
                            pass
                        for hdr in hdrs:
                            try:
                                winmm.waveInUnprepareHeader(
                                    h, ctypes.byref(hdr), ctypes.sizeof(hdr))
                            except Exception:
                                pass
                        try:
                            winmm.waveInClose(h)
                        except Exception:
                            pass
            with self._lock:
                if self._h is h:
                    self._h = None
                    self._hdrs = []
                    self._bufs = []
                    self._proc = None
                    self._worker = None
            self._drain(self._events)

        def start(self) -> bool:
            if not available():
                return False
            cleanup = None
            with self._lifecycle:
                with self._lock:
                    if self._running:
                        return True
                    # 旧设备已完成 Close 后才允许新一轮事件进入 pump。
                    self._drain(self._events)
                    self._stop_event.clear()
                    winmm = _winmm()
                    fmt = WAVEFORMATEX(
                        _WAVE_FORMAT_PCM, CHANNELS, SAMPLE_RATE,
                        SAMPLE_RATE * CHANNELS * BITS // 8,
                        CHANNELS * BITS // 8, BITS, 0)
                    h = ctypes.c_void_p()
                    self._proc = _PROC(self._callback)
                    try:
                        rc = winmm.waveInOpen(
                            ctypes.byref(h), _WAVE_MAPPER, ctypes.byref(fmt),
                            self._proc, 0, _CALLBACK_FUNCTION)
                    except Exception:
                        rc = -1
                    if rc != 0:
                        self._proc = None
                        return False
                    self._h = h
                    self._hdrs = []
                    self._bufs = []
                    for _ in range(4):
                        buf = ctypes.create_string_buffer(FRAME_BYTES)
                        hdr = WAVEHDR()
                        hdr.lpData = ctypes.cast(buf, ctypes.c_void_p)
                        hdr.dwBufferLength = FRAME_BYTES
                        try:
                            rc = winmm.waveInPrepareHeader(
                                h, ctypes.byref(hdr), ctypes.sizeof(hdr))
                        except Exception:
                            rc = -1
                        if rc != 0:
                            continue
                        try:
                            rc = winmm.waveInAddBuffer(
                                h, ctypes.byref(hdr), ctypes.sizeof(hdr))
                        except Exception:
                            rc = -1
                        if rc != 0:
                            try:
                                winmm.waveInUnprepareHeader(
                                    h, ctypes.byref(hdr), ctypes.sizeof(hdr))
                            except Exception:
                                pass
                            continue
                        self._hdrs.append(hdr)
                        self._bufs.append(buf)
                    worker = None
                    if self._hdrs:
                        self._running = True
                        worker = threading.Thread(target=self._pump, daemon=True,
                                                   name="mic-pump")
                        self._worker = worker
                        worker.start()
                        try:
                            rc = winmm.waveInStart(h)
                        except Exception:
                            rc = -1
                        if rc in (0, None):
                            return True
                        self._running = False
                    # 不能在持有非重入 _lock 时调用 stop；由同一生命周期
                    # 流程在释放锁后完成完整 Reset/Close。
                    cleanup = (h, list(self._hdrs), worker)
                    self._stop_event.set()
            if cleanup is not None:
                self._finish_device(*cleanup)
            return False

        def stop(self) -> None:
            with self._lifecycle:
                with self._lock:
                    h = self._h
                    hdrs = list(self._hdrs)
                    worker = self._worker
                    self._running = False
                    self._stop_event.set()
                if h is not None:
                    self._finish_device(h, hdrs, worker)
                else:
                    self._drain(self._events)
            # 清空残留帧，避免下次通话误播旧音频。
            self._drain(self.frames)

        def _callback(self, _h, msg, _inst, param1, _param2) -> None:
            """waveInProc：只拷贝数据、入队并通知 pump，绝不调用 wave 函数。"""
            try:
                with self._lock:
                    if msg != _WIM_DATA or not self._running:
                        return
                hdr = ctypes.cast(param1, ctypes.POINTER(WAVEHDR)).contents
                got = max(0, min(int(hdr.dwBytesRecorded),
                                  int(hdr.dwBufferLength), FRAME_BYTES))
                if got:
                    try:
                        self.frames.put_nowait(ctypes.string_at(hdr.lpData, got))
                    except queue.Full:
                        pass                      # 丢帧优于阻塞音频回调
                self._events.put_nowait(("data", ctypes.addressof(hdr)))
            except Exception as exc:
                self._events.put_nowait(("error", f"采集异常: {exc}"))

        def _pump(self) -> None:
            while not self._stop_event.is_set():
                try:
                    kind, value = self._events.get(timeout=0.1)
                except queue.Empty:
                    continue
                if self._stop_event.is_set():
                    return
                if kind == "error":
                    self._error_reporter.report(value)
                    continue
                with self._lock:
                    h = self._h
                    hdr = next((item for item in self._hdrs
                                if ctypes.addressof(item) == value), None)
                    running = self._running
                if not running or h is None or hdr is None:
                    continue
                with self._native_lock:
                    with self._lock:
                        if (not self._running) or self._h is not h:
                            continue
                    try:
                        rc = _winmm().waveInAddBuffer(
                            h, ctypes.byref(hdr), ctypes.sizeof(hdr))
                    except Exception as exc:
                        self._error_reporter.report(f"采集异常: {exc}")
                        continue
                    if rc not in (0, None):
                        self._error_reporter.report(f"采集异常: waveInAddBuffer={rc}")


    class SpkPlayer:
        """扬声器播放；WOM_DONE 回调只入队，pump 线程负责回收 header。"""

        def __init__(self, on_error=None) -> None:
            self._jitter: "queue.Queue[bytes]" = queue.Queue(maxsize=100)
            self._on_error = on_error
            self._error_reporter = _AsyncErrorReporter(on_error)
            self._h = None
            self._proc = None
            self._free: collections.deque = collections.deque()
            self._pool = []                    # (hdr, buffer) 池
            self._prepared = set()              # ctypes.addressof(hdr)
            self._running = False
            self._thread = None
            self._cond = threading.Condition()
            self._lifecycle = threading.Lock()
            self._native_lock = threading.Lock()
            self._events = queue.Queue()        # callback -> pump
            self._stop_event = threading.Event()

        @staticmethod
        def _drain(q) -> None:
            try:
                while True:
                    q.get_nowait()
            except queue.Empty:
                pass

        def _finish_device(self, h, pool, thread) -> None:
            """等待 pump 后 Reset/Unprepare/Close，再释放 pool/proc 引用。"""
            self._stop_event.set()
            with self._cond:
                self._cond.notify_all()
            if thread is not None and thread is not threading.current_thread():
                thread.join()
            if h is not None:
                with self._cond:
                    prepared = set(self._prepared)
                with self._native_lock:
                    try:
                        winmm = _winmm()
                    except Exception:
                        winmm = None
                    if winmm is not None:
                        try:
                            winmm.waveOutReset(h)
                        except Exception:
                            pass
                        for hdr, _buf in pool:
                            if ctypes.addressof(hdr) in prepared:
                                try:
                                    winmm.waveOutUnprepareHeader(
                                        h, ctypes.byref(hdr), ctypes.sizeof(hdr))
                                except Exception:
                                    pass
                        try:
                            winmm.waveOutClose(h)
                        except Exception:
                            pass
            with self._cond:
                if self._h is h:
                    self._h = None
                    self._pool = []
                    self._free.clear()
                    self._prepared.clear()
                    self._proc = None
                    self._thread = None
                    self._cond.notify_all()
            self._drain(self._events)

        def start(self) -> bool:
            if not available():
                return False
            with self._lifecycle:
                with self._cond:
                    if self._running:
                        return True
                    self._drain(self._events)
                    self._stop_event.clear()
                    winmm = _winmm()
                    fmt = WAVEFORMATEX(
                        _WAVE_FORMAT_PCM, CHANNELS, SAMPLE_RATE,
                        SAMPLE_RATE * CHANNELS * BITS // 8,
                        CHANNELS * BITS // 8, BITS, 0)
                    h = ctypes.c_void_p()
                    self._proc = _PROC(self._callback)
                    try:
                        rc = winmm.waveOutOpen(
                            ctypes.byref(h), _WAVE_MAPPER, ctypes.byref(fmt),
                            self._proc, 0, _CALLBACK_FUNCTION)
                    except Exception:
                        rc = -1
                    if rc != 0:
                        self._proc = None
                        return False
                    self._h = h
                    self._pool = []
                    self._free.clear()
                    self._prepared.clear()
                    for _ in range(_POOL):
                        buf = ctypes.create_string_buffer(FRAME_BYTES)
                        hdr = WAVEHDR()
                        hdr.lpData = ctypes.cast(buf, ctypes.c_void_p)
                        self._pool.append((hdr, buf))
                        self._free.append((hdr, buf))
                    self._running = True
                    self._thread = threading.Thread(
                        target=self._pump, daemon=True, name="spk-pump")
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
            with self._lifecycle:
                with self._cond:
                    h = self._h
                    pool = list(self._pool)
                    thread = self._thread
                    self._running = False
                    self._stop_event.set()
                    self._cond.notify_all()
                if h is not None:
                    self._finish_device(h, pool, thread)
                else:
                    self._drain(self._events)
            self._drain(self._jitter)

        def _prime(self) -> int:
            """开播预缓冲：等 jitter 队列攒到 JITTER_MIN 帧（或短超时即播）。"""
            buffered = 1
            while buffered < JITTER_MIN and not self._stop_event.is_set():
                try:
                    self._jitter.get(timeout=0.05)
                    buffered += 1
                except queue.Empty:
                    break
            return buffered

        def _callback(self, _h, msg, _inst, param1, _param2) -> None:
            """waveOutProc：仅记录 header 地址并通知 pump，绝不调用 wave 函数。"""
            try:
                if msg != _WOM_DONE:
                    return
                hdr = ctypes.cast(param1, ctypes.POINTER(WAVEHDR)).contents
                self._events.put_nowait(("done", ctypes.addressof(hdr)))
                with self._cond:
                    self._cond.notify_all()
            except Exception as exc:
                self._events.put_nowait(("error", f"播放异常: {exc}"))
                with self._cond:
                    self._cond.notify_all()

        def _drain_callback_events(self) -> None:
            while not self._stop_event.is_set():
                try:
                    kind, value = self._events.get_nowait()
                except queue.Empty:
                    return
                if kind == "error":
                    self._error_reporter.report(value)
                    continue
                with self._cond:
                    h = self._h
                    running = self._running
                    pair = next((item for item in self._pool
                                 if ctypes.addressof(item[0]) == value), None)
                    prepared = value in self._prepared
                if not running or h is None or pair is None or not prepared:
                    continue
                hdr, _buf = pair
                with self._native_lock:
                    with self._cond:
                        if (not self._running) or self._h is not h \
                                or value not in self._prepared:
                            continue
                    try:
                        rc = _winmm().waveOutUnprepareHeader(
                            h, ctypes.byref(hdr), ctypes.sizeof(hdr))
                    except Exception as exc:
                        self._error_reporter.report(f"播放异常: {exc}")
                        continue
                    if rc not in (0, None):
                        self._error_reporter.report(
                            f"播放异常: waveOutUnprepareHeader={rc}")
                        continue
                with self._cond:
                    self._prepared.discard(value)
                    if not any(ctypes.addressof(item[0]) == value
                               for item in self._free):
                        self._free.append(pair)
                    self._cond.notify_all()

        def _pump(self) -> None:
            # 先攒 jitter buffer 再开播（防开头 underrun）
            primed = False
            while not self._stop_event.is_set():
                self._drain_callback_events()
                if self._stop_event.is_set():
                    return
                try:
                    pcm = self._jitter.get(timeout=0.1)
                except queue.Empty:
                    continue
                if not primed:
                    self._prime()
                    primed = True
                pair = None
                with self._cond:
                    while self._running and not self._stop_event.is_set():
                        self._drain_callback_events()
                        if self._free:
                            pair = self._free.popleft()
                            break
                        self._cond.wait(timeout=0.2)
                    if pair is None or not self._running:
                        return
                hdr, buf = pair
                data = (pcm or b"")[:FRAME_BYTES].ljust(FRAME_BYTES, b"\x00")
                ctypes.memmove(buf, data, FRAME_BYTES)
                hdr.dwBufferLength = FRAME_BYTES
                hdr.dwFlags = 0
                with self._native_lock:
                    with self._cond:
                        h = self._h
                        if not self._running or h is None:
                            self._free.appendleft(pair)
                            continue
                    try:
                        winmm = _winmm()
                        rc = winmm.waveOutPrepareHeader(
                            h, ctypes.byref(hdr), ctypes.sizeof(hdr))
                        if rc not in (0, None):
                            self._free.appendleft(pair)
                            self._error_reporter.report(
                                f"播放异常: waveOutPrepareHeader={rc}")
                            continue
                        with self._cond:
                            self._prepared.add(ctypes.addressof(hdr))
                        rc = winmm.waveOutWrite(
                            h, ctypes.byref(hdr), ctypes.sizeof(hdr))
                        if rc not in (0, None):
                            winmm.waveOutUnprepareHeader(
                                h, ctypes.byref(hdr), ctypes.sizeof(hdr))
                            with self._cond:
                                self._prepared.discard(ctypes.addressof(hdr))
                                self._free.appendleft(pair)
                            self._error_reporter.report(
                                f"播放异常: waveOutWrite={rc}")
                    except Exception as exc:
                        try:
                            winmm.waveOutUnprepareHeader(
                                h, ctypes.byref(hdr), ctypes.sizeof(hdr))
                        except Exception:
                            pass
                        with self._cond:
                            self._prepared.discard(ctypes.addressof(hdr))
                            self._free.appendleft(pair)
                        self._error_reporter.report(f"播放异常: {exc}")
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
