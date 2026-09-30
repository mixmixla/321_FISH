# -*- coding: utf-8 -*-
"""R45 语音通话内视频回归（320×240 PNG @10fps，共用 UDP E2EE 通道）：

单元（video_api）：
- PNG 往返一致；坏数据（非 PNG / 缺 IHDR / 非 0 filter）拒绝
- Chunker/Reassembler 顺序与乱序重组；小帧垫零（载荷 ≥321B）截回原长
- 重组 TTL 淘汰 / 在途上限挤压 / 垃圾分片忽略
- YUY2 / NV12 合成数据解码正确（纯色→精确 RGB）；decim=2 输出减半
- 无摄像头环境 CamRecorder.start() 失败并回调 on_error

集成（经服务器）：
- vcap 能力协商：双方有摄像头时 ACCEPT/READY 均带 vcap=1
- 老客户端降级：对端无 vcap 字段 → video_supported()=False
- 视频帧端到端：FakeCam 注入真 PNG → 分片加密 → 对端重组 video_frame 事件
- 音频不受影响：320B 载荷不进重组器、无 video_frame 事件
- 挂断清理：video 状态复位、FakeCam 停止

真机（skipif 无摄像头）：CamRecorder 采集 ≥5 帧。
"""
import random
import socket
import struct
import threading
import time
import zlib
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, serve as serve_tcp
from web import serve as serve_web
from client_core import ClientCore
import video_api
import voice_call


# ---------- 夹具（仿 test_r44） ----------

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    wport = _free_port()
    httpd = serve_web(h, port=wport)
    time.sleep(0.2)
    yield h, port, wport, stop
    stop.set()
    time.sleep(0.2)
    httpd.shutdown()


class Collector:
    __test__ = False

    def __init__(self, core: ClientCore) -> None:
        self.events = []
        self._lock = threading.Lock()
        core._on_event = self._on

    def _on(self, ev: dict) -> None:
        with self._lock:
            self.events.append(ev)

    def wait(self, t: str, timeout: float = 5.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, e in enumerate(self.events):
                    if e.get("t") == t and (pred is None or pred(e)):
                        del self.events[i]
                        return e
            time.sleep(0.01)
        return None


def _spawn(port: int, nick: str, tmp_path):
    core = ClientCore(host="127.0.0.1", port=port, nick=nick,
                      history_dir=str(tmp_path / f"hist_{nick}"),
                      heartbeat_interval=0.1, heartbeat_timeout=0.8,
                      reconnect_base=0.05, reconnect_max=0.3)
    col = Collector(core)
    core.start()
    w = col.wait("welcome")
    assert w is not None, f"{nick} 未收到 welcome"
    return core, col


def _gradient_rows(w, h):
    """渐变 RGB 行（真实分布，PNG 几 KB 量级）。"""
    return [bytes((x * 7 + y * 13) % 256 for x in range(w * 3))
            for y in range(h)]


class FakeCam:
    """CamRecorder 替身：start 即成功，测试直呼 on_frame 注入帧。"""
    __test__ = False

    def __init__(self, on_frame, on_error=None, fps=10):
        self.on_frame = on_frame
        self.on_error = on_error
        self.stopped = False

    def start(self):
        return True

    def stop(self):
        self.stopped = True

    def is_healthy(self):
        return not self.stopped


def _setup_call(hub, tmp_path, monkeypatch, cam=True):
    """建 hub + 两端 → a 呼 b → 接通（incall）。返回 (a, cola, b, colb)。"""
    monkeypatch.setattr(video_api, "_AVAILABLE", True)
    monkeypatch.setattr(video_api, "CamRecorder", FakeCam)
    monkeypatch.setattr(video_api, "available", lambda: cam)
    a, cola = _spawn(hub[1], "甲", tmp_path)
    b, colb = _spawn(hub[1], "乙", tmp_path)
    assert a.calls.start_call(b.uid)
    ev = colb.wait("call", pred=lambda e: e.get("state") == "incoming")
    assert ev is not None, "被叫未收到来电"
    assert b.calls.accept_call()
    ev = cola.wait("call", pred=lambda e: e.get("state") == "incall")
    assert ev is not None, "主叫未连通"
    ev = colb.wait("call", pred=lambda e: e.get("state") == "incall")
    assert ev is not None, "被叫未连通"
    return a, cola, b, colb


# ---------- 单元：PNG 编解码 ----------

def test_png_roundtrip():
    rows = _gradient_rows(64, 48)
    w, h, back = video_api.png_decode(video_api.png_encode(rows, 64, 48))
    assert (w, h) == (64, 48)
    assert [bytes(r) for r in back] == [bytes(r) for r in rows]


def test_png_rejects_bad():
    rows = _gradient_rows(8, 4)
    good = video_api.png_encode(rows, 8, 4)
    with pytest.raises(ValueError):
        video_api.png_decode(b"not a png at all.......")
    # 缺 IHDR：剥掉整个 IHDR 块
    i0 = good.find(b"IHDR")
    ln0 = int.from_bytes(good[i0 - 4:i0], "big")
    no_ihdr = good[:i0 - 4] + good[i0 + 12 + ln0:]
    with pytest.raises(ValueError):
        video_api.png_decode(no_ihdr)
    # filter 非 0：每行前缀改 filter=1 重造 IDAT
    scan = b"".join(b"\x01" + r for r in rows)
    body = zlib.compress(scan)
    idat = (struct.pack(">I", len(body)) + b"IDAT" + body
            + struct.pack(">I", zlib.crc32(b"IDAT" + body) & 0xFFFFFFFF))
    i1 = good.find(b"IDAT")
    ln1 = int.from_bytes(good[i1 - 4:i1], "big")
    forged = good[:i1 - 4] + idat + good[i1 + 12 + ln1:]
    with pytest.raises(ValueError):
        video_api.png_decode(forged)


def test_chunker_reassembler_inorder():
    ch, re_ = video_api.Chunker(), video_api.Reassembler()
    frame = bytes(range(256)) * 137               # 35072B → 31 片
    chunks = ch.chunk(frame, 42)
    assert len(chunks) == 31
    out = None
    for c in chunks:
        r = re_.feed(c)
        if r:
            out = r
    assert out == frame


def test_reassembler_out_of_order():
    ch, re_ = video_api.Chunker(), video_api.Reassembler()
    frame = video_api.png_encode(_gradient_rows(320, 240), 320, 240)
    chunks = ch.chunk(frame, 1)
    sh = chunks[:]
    random.seed(7)
    random.shuffle(sh)
    out = None
    for c in sh:
        r = re_.feed(c)
        if r:
            out = r
    assert out == frame


def test_small_frame_tail_padding():
    """小帧单片垫零到载荷 ≥321B（与 320B 音频严格区分），重组截回原长。"""
    ch = video_api.Chunker()
    for size in (1, 10, 300, 309, 310, 311, 1165):
        cs = ch.chunk(b"Q" * size, 5)
        assert len(cs) >= 1
        for c in cs:
            assert len(c) >= video_api.MIN_PAYLOAD
        got = None
        re_ = video_api.Reassembler()
        for c in cs:
            r = re_.feed(c)
            if r:
                got = r
        assert got == b"Q" * size


def test_reassembler_ttl_eviction():
    ch = video_api.Chunker()
    re_ = video_api.Reassembler(ttl=0.05)
    cs1 = ch.chunk(b"A" * 3000, 1)                # 3 片：喂 2 留在途
    re_.feed(cs1[0])
    re_.feed(cs1[1])
    time.sleep(0.08)                              # 超 TTL：在途帧被清
    cs2 = ch.chunk(b"B" * 3000, 2)
    out = None
    for c in cs2:
        r = re_.feed(c)
        if r:
            out = r
    assert out == b"B" * 3000                     # 新帧不受旧帧残留影响
    out = None                                    # 旧帧补尾片也不复活
    for c in cs1[2:]:
        r = re_.feed(c)
        if r:
            out = r
    assert out is None


def test_reassembler_max_pending_eviction():
    re_ = video_api.Reassembler(max_pending=2)
    ch = video_api.Chunker()
    half1 = ch.chunk(b"1" * 3000, 1)[:1]          # 帧1 半程
    half2 = ch.chunk(b"2" * 3000, 2)[:1]          # 帧2 半程
    for c in half1 + half2:
        re_.feed(c)
    full3 = ch.chunk(b"3" * 3000, 3)              # 帧3 完整 → 挤掉最旧在途帧1
    out = None
    for c in full3:
        r = re_.feed(c)
        if r:
            out = r
    assert out == b"3" * 3000
    rest1 = ch.chunk(b"1" * 3000, 1)[1:]          # 帧1 剩余片不再能拼回
    assert all(re_.feed(c) is None for c in rest1)


def test_reassembler_ignores_garbage():
    re_ = video_api.Reassembler()
    assert re_.feed(b"") is None
    assert re_.feed(b"\x01") is None              # kind 非视频
    assert re_.feed(b"\x02\x00\x01") is None      # 超短
    assert re_.feed(b"\x00" * 400) is None


# ---------- 单元：YUV 软解 ----------

def test_yuy2_decode_synthetic():
    """YUY2 合成行：白/黑/红偏 → RGB 数值与通道序正确。"""
    w, h = 4, 3
    yuy = bytearray()
    for _ in range(w // 2):                       # 行0：白（Y=235 UV=128）
        yuy += bytes([235, 128, 235, 128])
    for _ in range(w // 2):                       # 行1：黑（Y=16）
        yuy += bytes([16, 128, 16, 128])
    for _ in range(w // 2):                       # 行2：V 高 U 低 → R>B
        yuy += bytes([180, 100, 180, 220])
    rows = video_api.yuy2_to_rows(bytes(yuy), w, h, 1)
    assert len(rows) == 3 and all(len(r) == w * 3 for r in rows)
    assert all(abs(rows[0][i] - 255) <= 6 for i in range(3))
    assert all(rows[1][i] <= 6 for i in range(3))
    assert rows[2][0] > rows[2][2] + 30           # R 显著大于 B


def test_nv12_decode_synthetic():
    w, h = 4, 4
    yplane = bytes([235] * 8 + [16] * 8)          # 上半白下半黑
    uvplane = bytes([128, 128] * 4)
    rows = video_api.nv12_to_rows(yplane + uvplane, w, h, 1)
    assert len(rows) == 4
    assert all(abs(rows[0][i] - 255) <= 6 for i in range(3))
    assert all(rows[2][i] <= 6 for i in range(3))


def test_decim2_halves_output():
    w, h = 8, 6
    yuy = bytes([100, 128, 150, 128] * (w * h // 2))
    r1 = video_api.yuy2_to_rows(yuy, w, h, 1)
    r2 = video_api.yuy2_to_rows(yuy, w, h, 2)
    assert len(r2) == h // 2 and all(len(r) == (w // 2) * 3 for r in r2)
    assert r2[0][0] == r1[0][0] and r2[0][1] == r1[0][1]   # 首像素同源
    nv = bytes([120] * (w * h)) + bytes([128, 128] * (w * h // 4))
    n2 = video_api.nv12_to_rows(nv, w, h, 2)
    assert len(n2) == h // 2 and all(len(r) == (w // 2) * 3 for r in n2)


def test_camrecorder_no_camera(monkeypatch):
    errs = []
    monkeypatch.setattr(video_api, "available", lambda: False)
    rec = video_api.CamRecorder(lambda p: None, on_error=errs.append)
    assert rec.start() is False
    assert errs and "摄像头" in errs[-1]


# ---------- 集成（经服务器） ----------

def test_vcap_negotiation(hub, tmp_path, monkeypatch):
    """双方有摄像头：主叫从 ACCEPT、被叫从 READY 得知对端 vcap=1。"""
    a, cola, b, colb = _setup_call(hub, tmp_path, monkeypatch, cam=True)
    try:
        assert a.calls.video_supported()
        assert b.calls.video_supported()
    finally:
        a.calls.end_call()
        b.calls.shutdown()


def test_vcap_legacy_peer_downgrades(hub, tmp_path, monkeypatch):
    """对端模拟老客户端（vcap 缺失）：video_supported()=False，纯语音照常。"""
    a, cola, b, colb = _setup_call(hub, tmp_path, monkeypatch, cam=False)
    try:
        assert not a.calls.video_supported()
        assert not b.calls.video_supported()
    finally:
        a.calls.end_call()
        b.calls.shutdown()


def test_video_frame_end_to_end(hub, tmp_path, monkeypatch):
    """FakeCam 注入真 PNG → 分片加密走 UDP → 对端重组 video_frame 事件。"""
    a, cola, b, colb = _setup_call(hub, tmp_path, monkeypatch, cam=True)
    try:
        b.calls.set_video(True)
        png = video_api.png_encode(_gradient_rows(320, 240), 320, 240)
        cam = None
        deadline = time.time() + 3
        while time.time() < deadline and cam is None:
            cam = b.calls._cam
            time.sleep(0.02)
        assert cam is not None, "FakeCam 未启动"
        cam.on_frame(png)                          # 模拟采集线程回调
        ev = cola.wait("call", timeout=5,
                       pred=lambda e: e.get("state") == "video_frame")
        assert ev is not None, "主叫未收到 video_frame"
        assert ev.get("png") == png
    finally:
        a.calls.end_call()
        b.calls.shutdown()


def test_audio_demux_unaffected(hub, tmp_path, monkeypatch):
    """320B 载荷不进重组器：通话中直发音频帧 → 对端无 video_frame 事件。"""
    a, cola, b, colb = _setup_call(hub, tmp_path, monkeypatch, cam=True)
    try:
        for _ in range(5):
            b.calls._send_packet(b"\xA7" * voice_call._AUDIO_FRAME)
            time.sleep(0.01)
        ev = cola.wait("call", timeout=1.0,
                       pred=lambda e: e.get("state") == "video_frame")
        assert ev is None, "320B 音频帧被误判为视频"
    finally:
        a.calls.end_call()
        b.calls.shutdown()


def test_end_call_cleans_video_state(hub, tmp_path, monkeypatch):
    """挂断后视频态复位：开关关、FakeCam 停、fid 归零。"""
    a, cola, b, colb = _setup_call(hub, tmp_path, monkeypatch, cam=True)
    b.calls.set_video(True)
    deadline = time.time() + 3
    while time.time() < deadline and b.calls._cam is None:
        time.sleep(0.02)
    assert b.calls.is_video_on()
    a.calls.end_call()
    time.sleep(0.3)
    assert not b.calls.is_video_on()
    assert b.calls._cam is None or b.calls._cam.stopped
    assert b.calls._fid == 0


# ---------- 真机（无摄像头自动跳过） ----------

def test_real_camera_capture():
    if not video_api.available():
        pytest.skip("本机无摄像头")
    frames, errs = [], []
    rec = video_api.CamRecorder(lambda p: frames.append(len(p)),
                                on_error=errs.append, fps=10)
    assert rec.start(), f"摄像头打开失败：{errs}"
    try:
        time.sleep(2.0)
        assert len(frames) >= 5, f"2s 采集帧数不足：{len(frames)}"
        assert rec.is_healthy()
        assert not errs, errs
    finally:
        rec.stop()

