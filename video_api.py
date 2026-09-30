# -*- coding: utf-8 -*-
"""R45 视频采集与帧传输层（Media Foundation ctypes 纯标准库，桌面端 only）。

规格：320×240 彩色 ~10fps；MF 原生 YUY2/NV12 直通采集（不做任何 MFT 格式
转换——本机 MFT 注册表为空，ENABLE_VIDEO_PROCESSING 反而令全部协商失败，
spike 实证），Python 查表软解 YUV→RGB，PNG(zlib L6) 编码后应用层分片。
无 320×240 原生格式的摄像头取最小面积格式并 2 倍抽稀回 320 级（decim）。

spike（Temp/mf_probe2.py）关键结论，勿回退：
- 类型协商必须把 GetNativeMediaType 返回的原生类型对象直接喂给
  SetCurrentMediaType；手工拼的类型缺 MF_MT_FRAME_RATE 等字段会被 reader
  判为"需转换"→ 走拓扑 → 0xC00D5212（本机无 MFT 必死）。
- vtable 扁平序号（vfn 内 +3 得槽位）：IMFSourceReader 仅接 IUnknown
  （GetNativeMediaType=2 SetCurrentMediaType=4 ReadSample=6）；
  IMFSample 直接继承 IMFAttributes(30)，不继承 IMFMediaBuffer
  （ConvertToContiguousBuffer=38）；IMFActivate 接 IMFAttributes(30)
  （ActivateObject=30 ShutdownObject=31）；IMFMediaSource 接
  IMFEventGenerator(6)（Shutdown=11）。
- 首帧 ReadSample 可能因硬件 MFT 起流失败报 0xC00D3704 或无限阻塞；
  OS 层解法 = 重启 FrameServer 服务 + USB 父设备。应用层对策 = 采集线程
  看门狗 + 重新枚举设备重建 reader 自愈一次，仍失败回调 on_error 提示。
- 每帧 IMFMediaBuffer 必须 Release（抽干 MF 分配池会让流停滞）。

线上格式（与 voice_call 共用 UDP 加密通道）：
- 音频保持 R44 裸 PCM 320B（无 kind 头）不变；
- 视频分片载荷 = [0x02][fid:u16][idx:u16][total:u16][framelen:u32][data]，
  满片 data=1165B（载荷 1176B + 12B nonce + 16B tag = 1204B < MTU）；
  尾片不足 310B 垫零到载荷 ≥321B，与 320B 音频帧严格区分。

D15 屏幕共享（可选采集源，接口与 CamRecorder 对齐）：`ScreenRecorder` 用
Pillow `ImageGrab` 抓全屏 → 等比缩到 320 宽 → 同一 PNG/分片管线，故对端无需改动。
"""
import array
import os
import struct
import threading
import time
import zlib

VID_W, VID_H = 320, 240
TARGET_FPS = 10
PNG_LEVEL = 6                 # 实测 ~31KB/帧 @3.4ms；L1 体积翻倍不值
STALE_SECS = 6.0              # 超过该时长无帧判定摄像头失联

CHUNK_HDR = struct.Struct(">BHHHI")     # kind, fid, idx, total, framelen
KIND_VIDEO = 2
CHUNK_DATA = 1165             # 单片净荷上限（11B 头后）
MIN_PAYLOAD = 321             # 视频载荷下限（>320B 音频帧）

_AVAILABLE = None             # 惰性探测缓存


# ================= PNG 编解码（仅支持本模块产出的 filter0/RGB8） =================

def png_encode(rows, w, h, level: int = PNG_LEVEL) -> bytes:
    """顶行起步 RGB24 行列表 → PNG（filter 0，color type 2）。"""
    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    scan = b"".join(b"\x00" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(scan, level)) + chunk(b"IEND", b""))


def png_decode(png: bytes):
    """PNG → (w, h, rows)；仅接受 filter 0（本模块只发这个）。"""
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("非 PNG 数据")
    pos, w, h, idat = 8, None, None, bytearray()
    while pos + 8 <= len(png):
        (ln,) = struct.unpack(">I", png[pos:pos + 4])
        tag = png[pos + 4:pos + 8]
        body = png[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if tag == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
    if not w or not h:
        raise ValueError("PNG 缺 IHDR")
    raw = zlib.decompress(bytes(idat))
    stride = w * 3
    rows = []
    for y in range(h):
        off = y * (stride + 1)
        if raw[off] != 0:
            raise ValueError("不支持的 PNG filter")
        rows.append(raw[off + 1:off + 1 + stride])
    return w, h, rows


# ================= YUV→RGB 查表软解（R/Y/B 预裁剪，G 两段合成） =================

_YUV_TABS = None


def _yuv_tables():
    """惰性建表（~0.1s 一次）：R=R_YV[y][v]，B=B_YU[y][u]，
    G=(G_YU[y][u] + G_V[v])>>8（两段查表避开 16M 三维表）。"""
    global _YUV_TABS
    if _YUV_TABS is None:
        r_yv = bytearray(65536)
        b_yu = bytearray(65536)
        g_yu = array.array("i", bytes(262144))
        g_v = array.array("i", bytes(1024))
        for y in range(256):
            base = y << 8
            cc = 298 * (y - 16) + 128
            for v in range(256):
                val = (cc + 409 * (v - 128)) >> 8
                r_yv[base | v] = 0 if val < 0 else (255 if val > 255 else val)
            for u in range(256):
                val = (cc + 516 * (u - 128)) >> 8
                b_yu[base | u] = 0 if val < 0 else (255 if val > 255 else val)
                g_yu[base | u] = cc - 100 * (u - 128)
        for v in range(256):
            g_v[v] = -208 * (v - 128)
        _YUV_TABS = (r_yv, b_yu, g_yu, g_v)
    return _YUV_TABS


def _g_clamp(g):
    return 0 if g < 0 else (255 if g > 255 else g)


def yuy2_to_rows(data: bytes, w: int, h: int, decim: int = 1):
    """YUY2（packed，2B/像素，UV 每 2 像素共享）→ RGB24 顶行起步行列表。
    decim=2 时横竖各隔行抽稀，输出 (w//2)×(h//2)。"""
    r_yv, b_yu, g_yu, g_v = _yuv_tables()
    st = len(data) // h
    rows = []
    if decim == 2:
        wout = w // 2
        for oy in range(0, h, 2):
            ln = data[oy * st: oy * st + w * 2]
            row = bytearray(wout * 3)
            j = 0
            for ox in range(wout // 2):
                bA = 8 * ox                      # 源像素 4ox（对 2ox 首像素）
                bB = bA + 4                      # 源像素 4ox+2（对 2ox+1 首像素）
                k1, u1, v1 = ln[bA] << 8, ln[bA + 1], ln[bA + 3]
                k2, u2, v2 = ln[bB] << 8, ln[bB + 1], ln[bB + 3]
                row[j] = r_yv[k1 | v1]
                row[j + 1] = _g_clamp((g_yu[k1 | u1] + g_v[v1]) >> 8)
                row[j + 2] = b_yu[k1 | u1]
                row[j + 3] = r_yv[k2 | v2]
                row[j + 4] = _g_clamp((g_yu[k2 | u2] + g_v[v2]) >> 8)
                row[j + 5] = b_yu[k2 | u2]
                j += 6
            rows.append(bytes(row))
        return rows
    w2 = w & ~1
    for y in range(h):
        ln = data[y * st: y * st + w * 2]
        row = bytearray(w * 3)
        j = 0
        for i in range(0, w2, 2):
            o = i + i
            y1, u, y2, v = ln[o], ln[o + 1], ln[o + 2], ln[o + 3]
            k1, k2 = y1 << 8, y2 << 8
            row[j] = r_yv[k1 | v]
            row[j + 1] = _g_clamp((g_yu[k1 | u] + g_v[v]) >> 8)
            row[j + 2] = b_yu[k1 | u]
            row[j + 3] = r_yv[k2 | v]
            row[j + 4] = _g_clamp((g_yu[k2 | u] + g_v[v]) >> 8)
            row[j + 5] = b_yu[k2 | u]
            j += 6
        rows.append(bytes(row))
    return rows


def nv12_to_rows(data: bytes, w: int, h: int, decim: int = 1):
    """NV12（Y 平面 + UV 交错平面，UV 每 2×2 块共享）→ RGB24 行列表。
    decim=2 时横竖各隔行抽稀（UV 块粒度天然对齐），输出 (w//2)×(h//2)。"""
    r_yv, b_yu, g_yu, g_v = _yuv_tables()
    ys = w * h                                  # UV 平面起始
    rows = []
    if decim == 2:
        wout = w // 2
        for oy in range(0, h, 2):           # oy = 源行（偶数）
            yrow = data[oy * w: oy * w + w]
            uvoff = ys + (oy >> 1) * w      # UV 块行 = 源行 >> 1
            row = bytearray(wout * 3)
            j = 0
            for ox in range(wout):
                k = yrow[2 * ox] << 8
                u, v = data[uvoff + 2 * ox], data[uvoff + 2 * ox + 1]
                row[j] = r_yv[k | v]
                row[j + 1] = _g_clamp((g_yu[k | u] + g_v[v]) >> 8)
                row[j + 2] = b_yu[k | u]
                j += 3
            rows.append(bytes(row))
        return rows
    for y in range(h):
        yrow = data[y * w: y * w + w]
        uvoff = ys + (y >> 1) * w
        row = bytearray(w * 3)
        j = 0
        for i in range(0, w & ~1, 2):
            u, v = data[uvoff + i], data[uvoff + i + 1]
            k1, k2 = yrow[i] << 8, yrow[i + 1] << 8
            row[j] = r_yv[k1 | v]
            row[j + 1] = _g_clamp((g_yu[k1 | u] + g_v[v]) >> 8)
            row[j + 2] = b_yu[k1 | u]
            row[j + 3] = r_yv[k2 | v]
            row[j + 4] = _g_clamp((g_yu[k2 | u] + g_v[v]) >> 8)
            row[j + 5] = b_yu[k2 | u]
            j += 6
        rows.append(bytes(row))
    return rows


# ================= 应用层分片 / 重组 =================

class Chunker:
    """PNG 帧 → 视频分片载荷列表（加密由 voice_call._send_packet 统一做）。"""

    def chunk(self, frame: bytes, fid: int) -> list:
        n = max(1, -(-len(frame) // CHUNK_DATA))
        out = []
        for i in range(n):
            part = frame[i * CHUNK_DATA:(i + 1) * CHUNK_DATA]
            if i == n - 1 and CHUNK_HDR.size + len(part) < MIN_PAYLOAD:
                part += b"\x00" * (MIN_PAYLOAD - CHUNK_HDR.size - len(part))
            out.append(CHUNK_HDR.pack(KIND_VIDEO, fid & 0xFFFF, i, n,
                                      len(frame)) + part)
        return out


class Reassembler:
    """分片重组：出序容忍、TTL 淘汰、在途帧数上限（防对端疯灌）。"""

    def __init__(self, ttl: float = 1.5, max_pending: int = 4):
        self._ttl = ttl
        self._max = max_pending
        self._frames = {}          # fid → {"n","len","parts","ts"}

    def feed(self, payload: bytes):
        """喂一片；集齐返回完整 PNG bytes，否则 None。"""
        if len(payload) < CHUNK_HDR.size or payload[0] != KIND_VIDEO:
            return None
        _, fid, idx, total, framelen = CHUNK_HDR.unpack(
            payload[:CHUNK_HDR.size])
        now = time.time()
        for k in [k for k, f in self._frames.items()
                  if now - f["ts"] > self._ttl]:
            del self._frames[k]
        fr = self._frames.get(fid)
        if fr is None:
            if len(self._frames) >= self._max:
                oldest = min(self._frames, key=lambda k: self._frames[k]["ts"])
                del self._frames[oldest]
            fr = self._frames[fid] = {"n": total, "len": framelen,
                                      "parts": {}, "ts": now}
        fr["parts"][idx] = payload[CHUNK_HDR.size:]
        fr["ts"] = now
        if len(fr["parts"]) < fr["n"]:
            return None
        raw = b"".join(fr["parts"][i] for i in range(fr["n"]))[:fr["len"]]
        del self._frames[fid]
        return raw


# ================= Media Foundation 采集（ctypes，nt only） =================

if os.name == "nt":
    import ctypes
    from ctypes import (HRESULT, POINTER, byref, c_int32, c_int64, c_uint8,
                        c_uint16, c_uint32, c_uint64, c_void_p, string_at)

    ole32 = ctypes.WinDLL("ole32")
    mfplat = ctypes.WinDLL("mfplat")
    mfdll = ctypes.WinDLL("mf")             # MFEnumDeviceSources 在 mf.dll
    mfreadwrite = ctypes.WinDLL("mfreadwrite")

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", c_uint32), ("Data2", c_uint16),
                    ("Data3", c_uint16), ("Data4", c_uint8 * 8)]

    def G(s):
        s = s.strip("{}")
        a, b, c, d, e = s.split("-")
        return GUID(int(a, 16), int(b, 16), int(c, 16),
                    (c_uint8 * 8).from_buffer_copy(
                        bytes.fromhex(d) + bytes.fromhex(e)))

    def vfn(obj, idx, restype, *argtypes):
        """COM vtable：idx 为扁平自有序（+3 = 槽位），首参 this。"""
        tbl = ctypes.cast(obj, ctypes.POINTER(c_void_p))[0]
        fp = ctypes.cast(tbl, ctypes.POINTER(c_void_p))[idx + 3]
        return ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(fp)

    GUID_SRC_TYPE = G("C60AC5FE-252A-478F-A0EF-BC8FA5F7CAD3")  # MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE
    GUID_VIDCAP = G("8AC3587A-4AE7-42D8-99E0-0A6013EEF90F")    # …_SOURCE_TYPE_VIDCAP_GUID
    IID_MEDIASOURCE = G("279A808D-AEC7-40C8-9C6B-A6B492C78A66")
    MT_VIDEO = G("73646976-0000-0010-8000-00AA00389B71")       # MFMediaType_Video
    FMT_YUY2 = G("32595559-0000-0010-8000-00AA00389B71")
    FMT_NV12 = G("3231564E-0000-0010-8000-00AA00389B71")
    GUID_MAJOR = G("48EBA18E-F8C9-4687-BF11-0A74C9F96A8F")     # MF_MT_MAJOR_TYPE
    GUID_SUBTYPE = G("F7E34C9A-42E8-4714-B74B-CB29D72C35E5")   # MF_MT_SUBTYPE
    GUID_FRAMESZ = G("1652C33D-D6B2-4012-B834-72030849A37D")   # MF_MT_FRAME_SIZE
    FIRST_VIDEO = 0xFFFFFFFC                                    # MF_SOURCE_READER_FIRST_VIDEO_STREAM

    _SETGUID, _SETUINT32, _GETUINT64, _GETGUID = 21, 18, 5, 7   # IMFAttributes
    _ACT_ACTIVATE, _ACT_SHUTDOWN = 30, 31                       # IMFActivate
    _SRC_SHUTDOWN = 11                                          # IMFMediaSource
    _RD_GETNATIVE, _RD_GETCUR, _RD_SETCUR, _RD_READ = 2, 3, 4, 6
    _SMP_C2CB = 38                                              # IMFSample

    def _mf_startup():
        hr = ole32.CoInitializeEx(None, 0x0)                    # MTA
        mfplat.MFStartup(0x20070, 0)
        return hr in (0, 1)

    def _mf_cleanup(com):
        try:
            mfplat.MFShutdown()
        except OSError:
            pass
        if com:
            try:
                ole32.CoUninitialize()
            except OSError:
                pass

    def _enum_activates():
        """枚举摄像头 IMFActivate 列表；失败返回 []。"""
        attrs = c_void_p()
        if mfplat.MFCreateAttributes(byref(attrs), 1) != 0:
            return []
        if vfn(attrs, _SETGUID, HRESULT, POINTER(GUID), POINTER(GUID))(
                attrs, byref(GUID_SRC_TYPE), byref(GUID_VIDCAP)) != 0:
            return []
        acts = POINTER(c_void_p)()
        cnt = c_uint32()
        if mfdll.MFEnumDeviceSources(attrs, byref(acts), byref(cnt)) != 0:
            return []
        return [acts[i] for i in range(cnt.value)]


def available() -> bool:
    """本机是否有摄像头（真实 MF 枚举一次并缓存；非 Windows → False）。"""
    global _AVAILABLE
    if _AVAILABLE is None:
        if os.name != "nt":
            _AVAILABLE = False
        else:
            box = []
            t = threading.Thread(target=_probe_available, args=(box,),
                                 daemon=True)
            t.start()
            t.join(2.0)
            _AVAILABLE = bool(box and box[0])
    return _AVAILABLE


def _probe_available(box: list) -> None:
    try:
        com = _mf_startup()
        try:
            box.append(len(_enum_activates()) > 0)
        finally:
            _mf_cleanup(com)
    except Exception:
        pass


class CamRecorder:
    """MF 摄像头采集器（对齐 voice_api.MicRecorder 的用法）。

    on_frame 在采集线程回调（png bytes）；调用方应快速返回或自行入队。
    自愈：读帧异常/空帧时释放旧 source → 重新枚举设备重建 reader（仅一次），
    再失败回调 on_error 并停止。is_healthy() 供外部看门狗
    （>STALE_SECS 无帧=失联，外部可 stop 后重开）。
    """

    def __init__(self, on_frame, on_error=None, fps: int = TARGET_FPS):
        self.on_frame = on_frame
        self.on_error = on_error
        self.fps = max(1, int(fps))
        self.last_frame_ts = 0.0
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._open_ok = False
        self._thread = None
        self._act = self._src = self._reader = None
        self._decoder = None
        self._W = self._H = self._decim = 0

    # ---------- 对外 ----------

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        if not available():
            self._fail("本机没有可用摄像头（可能被占用或系统设置关闭）")
            return False
        self._stop.clear()
        self._ready.clear()
        self._open_ok = False
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="cam-recorder")
        self._thread.start()
        if not self._ready.wait(5.0) or not self._open_ok:
            self.stop()
            self._fail("摄像头打开失败（可能被其它程序占用）")
            return False
        return True

    def stop(self) -> None:
        self._stop.set()
        t, self._thread = self._thread, None
        if t and t.is_alive():
            t.join(1.5)                    # 卡在 ReadSample 时放弃等待（daemon）

    def is_healthy(self) -> bool:
        return (self._thread is not None and self.last_frame_ts > 0.0
                and time.time() - self.last_frame_ts < STALE_SECS)

    def _fail(self, text: str) -> None:
        if self.on_error:
            try:
                self.on_error(text)
            except Exception:
                pass

    # ---------- COM 对象释放 ----------

    def _release_reader(self) -> None:
        r, s = self._reader, self._src
        self._reader = self._src = None
        for obj in (r, s):
            if obj is not None:
                try:
                    vfn(obj, -1, c_uint32)(obj)          # IUnknown::Release
                except OSError:
                    pass

    def _release_act(self) -> None:
        a, self._act = self._act, None
        if a is not None:
            try:
                vfn(a, _ACT_SHUTDOWN, HRESULT)(a)
            except OSError:
                pass
            try:
                vfn(a, -1, c_uint32)(a)
            except OSError:
                pass

    # ---------- 采集线程 ----------

    def _run(self) -> None:
        com = False
        try:
            com = _mf_startup()
            acts = _enum_activates()
            if not acts:
                self._fail("未找到摄像头设备")
                self._ready.set()
                return
            self._act = acts[0]
            if not self._open_reader():
                self._ready.set()
                return                      # _open_reader 已回调 _fail
            self._open_ok = True
            self._ready.set()
            self._capture_loop()
        except Exception as e:              # 采集线程任何意外：报错收场
            self._open_ok = self._open_ok and self._stop.is_set()
            self._ready.set()
            self._fail(f"摄像头异常：{e}")
        finally:
            self._release_reader()
            self._release_act()
            _mf_cleanup(com)

    def _open_reader(self) -> bool:
        """激活 self._act → 空属性 SourceReader → 原生类型直通协商。
        成功后 self._src/_reader/_decoder/_W/_H/_decim 就绪。"""
        src = c_void_p()
        hr = vfn(self._act, _ACT_ACTIVATE, HRESULT, POINTER(GUID),
                 POINTER(c_void_p))(self._act, byref(IID_MEDIASOURCE),
                                    byref(src))
        if hr != 0 or not src.value:
            self._fail("摄像头激活失败")
            return False
        mfreadwrite.MFCreateSourceReaderFromMediaSource.argtypes = (
            c_void_p, c_void_p, POINTER(c_void_p))
        mfreadwrite.MFCreateSourceReaderFromMediaSource.restype = HRESULT
        rattr = c_void_p()
        mfplat.MFCreateAttributes(byref(rattr), 0)          # 空属性（勿开 VP）
        reader = c_void_p()
        if mfreadwrite.MFCreateSourceReaderFromMediaSource(
                src, rattr, byref(reader)) != 0 or not reader.value:
            self._fail("无法创建采集器（SourceReader）")
            return False
        # 枚举原生类型
        native = []
        for i in range(64):
            mt_i = c_void_p()
            if vfn(reader, _RD_GETNATIVE, c_int32, c_uint32, c_uint32,
                   POINTER(c_void_p))(reader, c_uint32(FIRST_VIDEO),
                                      c_uint32(i), byref(mt_i)) != 0:
                break
            sub, sz = GUID(), c_uint64()
            vfn(mt_i, _GETGUID, HRESULT, POINTER(GUID), POINTER(GUID))(
                mt_i, byref(GUID_SUBTYPE), byref(sub))
            vfn(mt_i, _GETUINT64, HRESULT, POINTER(GUID), POINTER(c_uint64))(
                mt_i, byref(GUID_FRAMESZ), byref(sz))
            vfn(mt_i, -1, c_uint32)(mt_i)
            native.append((sub, int(sz.value >> 32), int(sz.value & 0xFFFFFFFF)))

        def match(fmt, wh=None):
            for i, (g, w, h) in enumerate(native):
                if bytes(memoryview(g)) == bytes(memoryview(fmt)) and (
                        wh is None or (w, h) == wh):
                    return i
            return None

        idx, decim = None, 1
        for fmt in (FMT_YUY2, FMT_NV12):            # 首选：原生 320x240
            idx = match(fmt, (VID_W, VID_H))
            if idx is not None:
                break
        if idx is None:                             # 兜底：最小面积原生格式，
            cands = []                              # 面积过大则 2 倍抽稀回 320 级
            for fmt in (FMT_YUY2, FMT_NV12):
                cands += [(w * h, i) for i, (g, w, h) in enumerate(native)
                          if bytes(memoryview(g)) == bytes(memoryview(fmt))]
            if cands:
                _, idx = min(cands)
                _, W0, H0 = native[idx]
                decim = 2 if W0 * H0 > VID_W * VID_H * 1.5 else 1
        if idx is None:
            self._fail("摄像头不支持 YUY2/NV12 输出")
            return False
        sub, W, H = native[idx]
        fmt_name = "YUY2" if bytes(memoryview(sub)) == \
            bytes(memoryview(FMT_YUY2)) else "NV12"
        # 原生类型对象直通 SetCurrentMediaType（字段完整 → 零转换）
        mt_i = c_void_p()
        if vfn(reader, _RD_GETNATIVE, c_int32, c_uint32, c_uint32,
               POINTER(c_void_p))(reader, c_uint32(FIRST_VIDEO),
                                  c_uint32(idx), byref(mt_i)) != 0:
            self._fail("读取摄像头原生格式失败")
            return False
        hr = vfn(reader, _RD_SETCUR, c_int32, c_uint32, c_void_p, c_void_p)(
            reader, c_uint32(FIRST_VIDEO), None, mt_i)
        vfn(mt_i, -1, c_uint32)(mt_i)
        if hr != 0:
            self._fail(f"摄像头格式协商失败 0x{hr & 0xFFFFFFFF:08X}")
            return False
        self._src, self._reader = src, reader
        self._decoder = yuy2_to_rows if fmt_name == "YUY2" else nv12_to_rows
        self._W, self._H, self._decim = W, H, decim
        return True

    def _read_frame(self) -> bytes | None:
        """同步读一帧原始数据；失败抛 OSError，空样本连续过多返回 None。"""
        nulls = 0
        while True:
            smp = c_void_p()
            idx, flg, ts = c_uint32(), c_uint32(), c_int64()
            hr = vfn(self._reader, _RD_READ, HRESULT, c_uint32, c_uint32,
                     POINTER(c_uint32), POINTER(c_uint32), POINTER(c_int64),
                     POINTER(c_void_p))(self._reader, c_uint32(FIRST_VIDEO),
                                        0, byref(idx), byref(flg), byref(ts),
                                        byref(smp))
            if hr != 0:
                raise OSError(f"ReadSample 0x{hr & 0xFFFFFFFF:08X}")
            if smp.value:
                break
            nulls += 1
            if nulls > 50:
                return None
            if self._stop.wait(0.02):
                return None
        buf = c_void_p()
        hr = vfn(smp, _SMP_C2CB, HRESULT, POINTER(c_void_p))(smp, byref(buf))
        if hr != 0 or not buf.value:
            vfn(smp, -1, c_uint32)(smp)
            raise OSError(f"ContiguousBuffer 0x{hr & 0xFFFFFFFF:08X}")
        try:
            ptr, mx, cl = c_void_p(), c_uint32(), c_uint32()
            hr = vfn(buf, 0, HRESULT, POINTER(c_void_p), POINTER(c_uint32),
                     POINTER(c_uint32))(buf, byref(ptr), byref(mx), byref(cl))
            if hr != 0:
                raise OSError(f"Buffer Lock 0x{hr & 0xFFFFFFFF:08X}")
            data = string_at(ptr, cl.value)
        finally:
            vfn(buf, 1, HRESULT)(buf)                       # Unlock（未锁无害）
            vfn(buf, -1, c_uint32)(buf)                     # Release（防抽干池）
            vfn(smp, -1, c_uint32)(smp)
        return data

    def _capture_loop(self) -> None:
        interval = 1.0 / self.fps
        next_t = time.perf_counter()
        rebuilt = False
        while not self._stop.is_set():
            try:
                data = self._read_frame()
            except OSError as e:
                if rebuilt or not self._rebuild():
                    self._fail(f"摄像头流中断：{e}")
                    return
                rebuilt = True
                continue
            if data is None:
                if rebuilt or not self._rebuild():
                    self._fail("摄像头无帧输出")
                    return
                rebuilt = True
                continue
            rows = self._decoder(data, self._W, self._H, self._decim)
            png = png_encode(rows, self._W // self._decim,
                             self._H // self._decim)
            self.last_frame_ts = time.time()
            try:
                self.on_frame(png)
            except Exception:
                pass
            next_t += interval
            delay = next_t - time.perf_counter()
            if delay > 0:
                if self._stop.wait(delay):
                    return
            else:
                next_t = time.perf_counter()        # 落后则重置基准，防突发追赶

    def _rebuild(self) -> bool:
        """起流自愈：释放旧 reader/src → 重新枚举设备激活 → 重建 reader。
        （IMFActivate::ShutdownObject 后不可复用，必须重新枚举。）"""
        self._release_reader()
        self._release_act()
        try:
            acts = _enum_activates()
        except Exception:
            return False
        if not acts:
            return False
        self._act = acts[0]
        return self._open_reader()


# ================= D15 屏幕共享采集（Pillow ImageGrab，接口对齐 CamRecorder） =================

def screen_available() -> bool:
    """本机能否抓屏共享（Windows + Pillow；不缓存，Pillow 缺失是启动期常量）。"""
    if os.name != "nt":
        return False
    try:
        from PIL import ImageGrab                 # noqa: F401
        return True
    except Exception:
        return False


class ScreenRecorder:
    """D15 屏幕采集器：全屏（或 bbox 区域）→ 等比缩到 VID_W 宽 → png_encode。

    公开接口与 :class:`CamRecorder` 完全对齐（``start/stop/is_healthy/on_frame``），
    故 ``voice_call`` 可无差别替换采集源。区别：
    - 无 MF 那套设备自愈——抓屏是一次 GDI 拷贝，失败即 ``on_error`` 收场；
    - 不做 MF 初始化，抓屏与摄像头可同时进行（互不占用设备）。
    """

    def __init__(self, on_frame, on_error=None, fps: int = TARGET_FPS, bbox=None):
        self.on_frame = on_frame
        self.on_error = on_error
        self.fps = max(1, int(fps))
        self.bbox = bbox                          # (l,t,r,b) | None（全屏）
        self.last_frame_ts = 0.0
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._open_ok = False
        self._thread = None

    # ---------- 对外（与 CamRecorder 同名同义） ----------

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        if not screen_available():
            self._fail("无法共享屏幕（需要 Windows + Pillow 抓屏支持）")
            return False
        self._stop.clear()
        self._ready.clear()
        self._open_ok = False
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="screen-recorder")
        self._thread.start()
        if not self._ready.wait(5.0) or not self._open_ok:
            self.stop()
            self._fail("屏幕采集启动失败（抓屏被系统拒绝？）")
            return False
        return True

    def stop(self) -> None:
        self._stop.set()
        t, self._thread = self._thread, None
        if t and t.is_alive():
            t.join(1.5)

    def is_healthy(self) -> bool:
        return (self._thread is not None and self.last_frame_ts > 0.0
                and time.time() - self.last_frame_ts < STALE_SECS)

    def _fail(self, text: str) -> None:
        if self.on_error:
            try:
                self.on_error(text)
            except Exception:
                pass

    # ---------- 采集线程 ----------

    def _run(self) -> None:
        try:
            from PIL import ImageGrab
        except Exception:
            self._ready.set()
            self._fail("未安装 Pillow，无法共享屏幕")
            return
        try:
            self._grab_once(ImageGrab)            # 首帧探活：抓不到就直接失败
        except Exception as e:
            self._ready.set()
            self._fail(f"屏幕采集失败：{e}")
            return
        self._open_ok = True
        self._ready.set()
        interval = 1.0 / self.fps
        while not self._stop.is_set():
            t0 = time.perf_counter()
            try:
                self._grab_once(ImageGrab)
            except Exception as e:
                self._fail(f"屏幕采集中断：{e}")
                return
            delay = interval - (time.perf_counter() - t0)
            if delay > 0 and self._stop.wait(delay):
                return

    def _grab_once(self, ImageGrab) -> None:
        """抓一帧 → 等比缩到 VID_W 宽（偶数高）→ RGB24 行 → png_encode → 回调。"""
        img = ImageGrab.grab(bbox=self.bbox).convert("RGB")
        w, h = img.size
        if w <= 0 or h <= 0:
            raise ValueError("抓屏尺寸为 0")
        out_w = VID_W
        out_h = max(2, int(round(h * out_w / float(w))))
        if out_h & 1:
            out_h += 1
        if (w, h) != (out_w, out_h):
            img = img.resize((out_w, out_h))
        data = img.tobytes()
        stride = out_w * 3
        rows = [data[y * stride:(y + 1) * stride] for y in range(out_h)]
        png = png_encode(rows, out_w, out_h)
        self.last_frame_ts = time.time()
        try:
            self.on_frame(png)
        except Exception:
            pass
