# -*- coding: utf-8 -*-
"""R38 媒体/AI 包回归：1v1 语音对讲 / 可选依赖门面 / Lottie 动画表情。

R38A 语音对讲：
- 单元（CallManager 状态机，假 core）：主叫 ringing/占线/拒绝/挂断/
  被叫 incoming/reject/占线回 END/握手失败 fail-fast/PTT 非通话期无效
- 集成（经服务器 + 真实 UDP 回环，音频设备打桩）：
  甲→乙全流程 incall；PTT 采集帧加密→对端解密还原；挂断双向清理；
  通话中第三方呼入被占线快速拒绝且不影响原通话
- 服务器：CALL_RING 对方不在线 → 回 END 快速失败（不占服务器状态）

R38B 可选依赖（optional.py）：
- has/find_spec 探测 + 缓存；has_stt/translator/lottie 组合
- transcribe_wav/translate_text 缺依赖抛 OptionalMissing（不崩 UI）
- find_model_dir：prefs > VOSK_MODEL 环境变量 > 项目 models/vosk

R38C Lottie 动画表情（lottie_label.py + msg_list 集成）：
- LottieFrames.ready 语义；load_async 后台解码失败回调一次（failed）
- load_async 缓存命中（同路径同尺寸返回同一实例）
- attach 轮播帧前进 / 重复 attach 忽略 / detach_canvas 停表清点
- LottieLabel 缺依赖回退静态 glyph
- msg_list._draw_lottie_sticker 三分支：缺依赖 glyph 行 /
  就绪画首帧+attach / 解码中占位块（行高稳定不跳版）
- 服务器贴纸白名单放行 json（上传/拉取回环）；非法 ext 拒绝
"""
import http.client
import json
import os
import queue
import socket
import threading
import time
import tkinter as tk
from dataclasses import replace
from types import SimpleNamespace

import pytest

import optional
import voice_api
import voice_call
from client_core import ClientCore
from config import CFG
from protocol import MsgType as M
from server import Hub, serve as serve_tcp
from widgets import lottie_label
from widgets.msg_list import MsgList, STICKER_MAX

FONT = ("Microsoft YaHei UI", 9)

_LOTTE_MINI = b'{"v":"5.7.4","fr":30,"ip":0,"op":2,"w":8,"h":8,"layers":[],"assets":[]}'


# ---------- 夹具 ----------

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    time.sleep(0.2)
    yield h, port, stop
    stop.set()
    time.sleep(0.2)


class _Cli:
    """裸协议客户端（保留 body，供贴纸字节断言）。"""
    __test__ = False

    def __init__(self, port, nick):
        from crypto import client_handshake
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.chan = client_handshake(self.sock)
        self.nick = nick
        self.uid = None
        self.events = []
        self._lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            while True:
                hdr, body = self.chan.recv_frame()
                with self._lock:
                    self.events.append((hdr, body))
        except Exception:
            pass

    def send(self, header, body=b""):
        self.chan.send_frame(header, body)

    def wait(self, t, timeout=3.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, (hdr, body) in enumerate(self.events):
                    if hdr.get("t") == t and (pred is None or pred(hdr)):
                        del self.events[i]
                        return hdr, body
            time.sleep(0.01)
        return None, None

    def hello(self):
        self.send({"t": "hello", "nick": self.nick})
        hdr, _ = self.wait("welcome")
        if hdr:
            self.uid = hdr["uid"]
        return hdr

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


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
                for i, ev in enumerate(self.events):
                    if ev.get("t") == t and (pred is None or pred(ev)):
                        del self.events[i]
                        return ev
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


@pytest.fixture()
def stub_audio(monkeypatch):
    """音频设备打桩：不碰真实 winmm 设备，PTT 采集/播放走内存。"""
    class StubMic:
        def __init__(self, on_error=None):
            self.frames = queue.Queue()
            self.stopped = False

        def start(self):
            return True

        def stop(self):
            self.stopped = True

    class StubSpk:
        def __init__(self, on_error=None):
            self.fed = []
            self._lock = threading.Lock()

        def start(self):
            pass

        def stop(self):
            pass

        def feed(self, pcm):
            with self._lock:
                self.fed.append(bytes(pcm))

    monkeypatch.setattr(voice_api, "MicRecorder", StubMic)
    monkeypatch.setattr(voice_api, "SpkPlayer", StubSpk)
    return SimpleNamespace(Mic=StubMic, Spk=StubSpk)


@pytest.fixture(scope="module")
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:          # 无显示环境（headless CI）跳过
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


@pytest.fixture()
def ml(root):
    ml = MsgList(root, FONT)
    ml.configure(width=400, height=400)
    ml.pack(fill="both", expand=True)
    root.update_idletasks()
    root.update()
    yield ml
    ml.destroy()


# ================= R38A 单元：CallManager 状态机（假 core） =================

class _FakeCore:
    def __init__(self):
        self.roster = {}
        self.known = {7: {"nick": "小七"}}
        self.sent = []
        self.events = []
        self.e2ee = SimpleNamespace(session_key=lambda uid: b"k" * 32)
        self.ready = True                 # e2ee_ready 返回值
        self.handshake_result = "fp:👍"   # start_e2ee 返回值（None=失败）

    def _send_frame(self, h, body=b""):
        self.sent.append(h)
        return True

    def _push(self, ev):
        self.events.append(ev)

    def e2ee_ready(self, uid):
        return self.ready

    def start_e2ee(self, uid, timeout=5.0):
        return self.handshake_result


def _call_events(core):
    return [e for e in core.events if e.get("t") == "call"]


def _last_state(core):
    evs = _call_events(core)
    return evs[-1]["state"] if evs else None


def test_call_start_and_wire():
    core = _FakeCore()
    cm = voice_call.CallManager(core)
    assert cm.start_call(7) is True
    assert cm.state == "ringing" and cm.role == "caller" and cm.peer == 7
    assert cm.peer_nick == "小七"
    assert core.sent[-1] == {"t": M.CALL_RING.value, "to": 7}
    assert _last_state(core) == "ringing"
    assert cm.duration() == 0.0           # 未连通不计时


def test_call_busy_and_third_party_busy_reply():
    core = _FakeCore()
    cm = voice_call.CallManager(core)
    assert cm.start_call(7) is True
    assert cm.start_call(8) is False      # 已在通话中
    assert _last_state(core) == "failed"
    # 占线时收到第三方来电：立即回 END，不改变自己的通话
    n = len(core.sent)
    cm.handle(M.CALL_RING.value, {"t": M.CALL_RING.value, "from": 9})
    assert core.sent[n] == {"t": M.CALL_END.value, "to": 9, "reason": "占线"}
    assert cm.state == "ringing" and cm.peer == 7


def test_call_reject_by_callee_reset():
    core = _FakeCore()
    cm = voice_call.CallManager(core)
    cm.start_call(7)
    cm.handle(M.CALL_REJECT.value,
              {"t": M.CALL_REJECT.value, "from": 7, "reason": "在忙"})
    assert cm.state == "idle" and cm.peer is None
    ev = _call_events(core)[-1]
    assert ev["state"] == "ended" and "在忙" in ev["text"]


def test_call_callee_incoming_and_reject():
    core = _FakeCore()
    cm = voice_call.CallManager(core)
    cm.handle(M.CALL_RING.value, {"t": M.CALL_RING.value, "from": 7,
                                  "nick": "小七"})
    assert cm.state == "incoming" and cm.role == "callee"
    ev = _call_events(core)[-1]
    assert ev["state"] == "incoming" and ev["nick"] == "小七"
    assert cm.reject_call("开会中") is True
    assert core.sent[-1] == {"t": M.CALL_REJECT.value, "to": 7,
                             "reason": "开会中"}
    assert cm.state == "idle"
    assert _last_state(core) == "ended"
    assert cm.reject_call() is False      # 已空闲，重复拒绝无效


def test_call_end_and_idle_semantics():
    core = _FakeCore()
    cm = voice_call.CallManager(core)
    assert cm.end_call() is False         # idle 挂断无效
    cm.start_call(7)
    assert cm.end_call("有事先走") is True
    assert core.sent[-1] == {"t": M.CALL_END.value, "to": 7,
                             "reason": "有事先走"}
    assert cm.state == "idle"
    assert _last_state(core) == "ended"


def test_call_handshake_fail_fast():
    core = _FakeCore()
    core.ready = False
    core.handshake_result = None          # 模拟握手失败
    cm = voice_call.CallManager(core)
    assert cm.start_call(7) is False
    assert cm.state == "idle"
    ev = _call_events(core)[-1]
    assert ev["state"] == "failed" and "握手" in ev["text"]
    assert all(h["t"] != M.CALL_RING.value for h in core.sent)


def test_call_ptt_ignored_when_not_incall():
    core = _FakeCore()
    cm = voice_call.CallManager(core)
    cm.set_ptt(True)                      # idle：静默忽略，不建麦
    assert cm._mic is None and cm._ptt is False


def test_call_handle_unknown_type_noop():
    core = _FakeCore()
    cm = voice_call.CallManager(core)
    cm.handle("call_bogus", {})           # 未知信令类型不崩
    assert cm.state == "idle" and not core.sent


# ============ R38A 集成：经服务器 + 真实 UDP 回环（音频打桩） ============

def _establish_call(a, ca, b, cb):
    """预热 E2EE 后甲呼乙，双方到 incall。"""
    assert a.start_e2ee(b.uid, timeout=5.0)
    assert a.calls.start_call(b.uid) is True
    ev = cb.wait("call", timeout=5.0, pred=lambda e: e.get("state") == "incoming")
    assert ev is not None, "乙未收到来电"
    assert b.calls.accept_call() is True
    ev = ca.wait("call", timeout=8.0, pred=lambda e: e.get("state") == "incall")
    assert ev is not None, "甲未连通（UDP 打洞失败）"
    ev = cb.wait("call", timeout=5.0, pred=lambda e: e.get("state") == "incall")
    assert ev is not None, "乙未进入通话"


def test_call_full_flow_ptt_audio(hub, stub_audio, tmp_path):
    """甲→乙全流程：信令经服务器、UDP 直连打洞、PTT 加密音频对端还原、挂断双向清理。

    R39A 起默认全双工；本测锁定 PTT 可选模式旧行为，先切回半双工。
    """
    _h, port, _stop = hub
    a, ca = _spawn(port, "甲", tmp_path)
    b, cb = _spawn(port, "乙", tmp_path)
    try:
        a.calls.set_duplex(False)
        b.calls.set_duplex(False)
        _establish_call(a, ca, b, cb)
        assert a.calls.state == "incall" and b.calls.state == "incall"
        assert a.calls._mic is None          # PTT 模式连通不开麦

        pcm = (bytes(range(256)) * 2)[:320]  # 320B 定长帧（R45 起 >320B 解密载荷按视频分片分流）
        a.calls.set_ptt(True)                # 开麦（打桩麦）
        assert a.calls._mic is not None
        a.calls._mic.frames.put(pcm)
        deadline = time.time() + 4.0
        while time.time() < deadline and not b.calls._spk.fed:
            time.sleep(0.05)
        assert b.calls._spk.fed, "乙未收到音频帧"
        assert b.calls._spk.fed[-1] == pcm   # AES-GCM 解密后与原文一致
        a.calls.set_ptt(False)

        a.calls.end_call("测试结束")
        ev = cb.wait("call", timeout=4.0,
                     pred=lambda e: e.get("state") == "ended")
        assert ev is not None and "测试结束" in ev["text"]
        assert a.calls.state == "idle" and b.calls.state == "idle"
    finally:
        a.calls.shutdown()
        b.calls.shutdown()
        a.stop()
        b.stop()


def test_call_busy_third_party(hub, stub_audio, tmp_path):
    """通话中第三方呼入：被占线快速拒绝，原通话不受影响。"""
    _h, port, _stop = hub
    a, ca = _spawn(port, "甲", tmp_path)
    b, cb = _spawn(port, "乙", tmp_path)
    c, cc = _spawn(port, "丙", tmp_path)
    try:
        _establish_call(a, ca, b, cb)
        assert c.calls.start_call(a.uid) is True   # 丙呼甲（含丙-甲握手）
        ev = cc.wait("call", timeout=8.0,
                     pred=lambda e: e.get("state") == "ended"
                     and "占线" in e.get("text", ""))
        assert ev is not None, "丙未收到占线"
        assert c.calls.state == "idle"
        assert a.calls.state == "incall"     # 甲乙通话不受打扰
    finally:
        a.calls.shutdown()
        b.calls.shutdown()
        c.calls.shutdown()
        a.stop()
        b.stop()
        c.stop()


def test_server_call_ring_offline_fast_fail(hub):
    """服务器层：CALL_RING 对方不在线 → 直接回 END（主叫快速失败）。"""
    _h, port, _stop = hub
    a = _Cli(port, "主叫")
    a.hello()
    a.send({"t": M.CALL_RING.value, "to": 424242})
    hdr, _ = a.wait(M.CALL_END.value, timeout=3.0)
    assert hdr is not None and "不在线" in (hdr.get("reason") or "")
    a.close()


# ==================== R38B 可选依赖门面（optional.py） ====================

def test_optional_has_and_cache():
    assert optional.has("json") is True
    assert optional.has("no_such_module_r38") is False
    assert optional._cache["no_such_module_r38"] is False   # 结果已缓存
    assert optional.has_stt() == optional.has("vosk")
    assert optional.has_translator() == optional.has("deep_translator")
    assert optional.has_lottie() == (optional.has("rlottie")
                                     and optional.has("PIL"))


def test_optional_missing_raises():
    # 未配置模型目录 → OptionalMissing（无论 vosk 是否安装）
    with pytest.raises(optional.OptionalMissing):
        optional.transcribe_wav("whatever.wav", model_dir="")
    if not optional.has_translator():
        with pytest.raises(optional.OptionalMissing):
            optional.translate_text("hello")


def test_optional_find_model_dir(tmp_path, monkeypatch):
    good = tmp_path / "vosk_model"
    (good / "am").mkdir(parents=True)
    (good / "am" / "final.mdl").write_bytes(b"x")
    assert optional.find_model_dir(str(good)) == str(good)   # prefs 优先
    monkeypatch.setenv("VOSK_MODEL", str(good))
    assert optional.find_model_dir("") == str(good)          # 环境变量次之
    monkeypatch.setenv("VOSK_MODEL", str(tmp_path / "nope"))
    assert optional.find_model_dir("") == ""                 # 无效配置忽略
    # 项目内 models/vosk 兜底（不存在则空串）
    local = os.path.join(os.path.dirname(os.path.abspath(optional.__file__)),
                         "models", "vosk")
    expected = local if (os.path.isdir(local) and os.path.isfile(
        os.path.join(local, "am", "final.mdl"))) else ""
    assert optional.find_model_dir() == expected


# ==================== R38C Lottie 动画表情（lottie_label.py） ====================

def _ready_frames(root, delay=30):
    """伪造一段已就绪的帧序列（真实 PhotoImage，绕过 rlottie 解码）。"""
    lf = lottie_label.LottieFrames("fake.json", 64)
    photo = tk.PhotoImage(width=8, height=8)
    lf.photos = [photo, photo]
    lf.state = "ready"
    lf.delay_ms = delay
    return lf


def test_lottie_frames_ready_semantics(root):
    lf = lottie_label.LottieFrames("fake.json", 64)
    assert lf.state == "loading" and lf.ready is False
    lf.state = "ready"
    assert lf.ready is False               # 无 photos 仍不算就绪
    lf.photos = [tk.PhotoImage(width=4, height=4)]
    assert lf.ready is True


def test_lottie_load_async_fails_callback_once(root, tmp_path):
    """坏文件后台解码必失败：回调恰好一次且 ready=False（走静态回退）。"""
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{not a lottie")
    got = []
    ret = lottie_label.load_async(str(bad), 32, root, lambda lf: got.append(lf))
    deadline = time.time() + 5.0
    while time.time() < deadline and not got:
        root.update()
        time.sleep(0.02)
    assert ret is None                     # 发起时后台解码中
    assert len(got) == 1 and got[0].state == "failed" and not got[0].ready
    # 同路径同尺寸再次请求：缓存命中，直接给失败实例（不再解码）
    again = lottie_label.load_async(str(bad), 32, root, lambda lf: None)
    assert again is got[0]


def test_lottie_attach_advance_and_detach(root):
    ml = MsgList(root, FONT)
    ml.configure(width=200, height=200)
    lf = _ready_frames(root)
    item = ml.create_image(10, 10, image=lf.photos[0])   # 与生产一致：attach 画 image item
    lottie_label.attach(ml, item, lf)
    assert lottie_label.active_count() == 1
    lottie_label.attach(ml, item, lf)      # 重复 attach 同一 item 忽略
    assert lottie_label.active_count() == 1
    key = (ml, item)
    deadline = time.time() + 2.0
    while time.time() < deadline and lottie_label._ITEMS[key]["i"] == 0:
        ml.update()
        time.sleep(0.02)
    assert lottie_label._ITEMS[key]["i"] >= 1     # 帧在前进
    lottie_label.detach_canvas(ml)
    assert lottie_label.active_count() == 0       # 停表并清点


def test_lottie_label_fallback_glyph(root, monkeypatch):
    monkeypatch.setattr(lottie_label, "available", lambda: False)
    lab = lottie_label.LottieLabel(root, "no_such.json", size=48)
    assert lab.cget("text") == lottie_label.GLYPH   # 缺依赖保持静态 glyph
    lab.destroy()


# ============= R38C msg_list 集成：_draw_lottie_sticker 三分支 =============

def test_msglist_lottie_unavailable_glyph_row(ml, monkeypatch):
    monkeypatch.setattr(lottie_label, "available", lambda: False)
    h = ml._draw_lottie_sticker("lk", "a.json", 10, 10)
    assert h == ml._linespace              # 静态行：同行高不跳版
    texts = [ml.itemcget(i, "text") for i in ml.find_all()
             if ml.type(i) == "text"]
    assert any("🎞" in t and "[:lk:]" in t for t in texts)


def test_msglist_lottie_ready_attaches_animation(ml, monkeypatch):
    lf = _ready_frames(ml)
    monkeypatch.setattr(lottie_label, "available", lambda: True)
    monkeypatch.setattr(lottie_label, "load_async",
                        lambda path, size, master, cb: lf)
    h = ml._draw_lottie_sticker("lk", "a.json", 10, 10)
    assert h == lf.photos[0].height() + ml.PAD_TOP
    assert lottie_label.active_count() == 1       # 已挂上轮播
    lottie_label.detach_canvas(ml)
    assert lottie_label.active_count() == 0


def test_msglist_lottie_loading_placeholder_stable_height(ml, monkeypatch):
    monkeypatch.setattr(lottie_label, "available", lambda: True)
    monkeypatch.setattr(lottie_label, "load_async",
                        lambda path, size, master, cb: None)   # 解码中
    h = ml._draw_lottie_sticker("lk", "a.json", 10, 10)
    assert h == STICKER_MAX + ml.PAD_TOP   # 占位块行高与就绪后一致（不跳版）
    texts = [ml.itemcget(i, "text") for i in ml.find_all()
             if ml.type(i) == "text"]
    assert any(t == lottie_label.GLYPH for t in texts)


# ================== R38C 服务器：贴纸 ext 白名单放行 json ==================

def test_server_sticker_json_whitelist(hub, tmp_path):
    """ext=json（Lottie）上传→清单→落盘→拉取回环；非法 ext 拒绝。"""
    h, port, _stop = hub
    a = _Cli(port, "动画师")
    a.hello()
    a.send({"t": M.STICKER_CUSTOM_ADD.value, "code": "lk1",
            "label": "动画", "ext": "json"}, _LOTTE_MINI)
    sl, _ = a.wait("sticker_list")
    assert sl and any(s["code"] == "lk1" for s in sl["custom_stickers"])
    assert h.custom_stickers["lk1"]["ext"] == "json"
    assert (tmp_path / "web" / "stickers" / "lk1.json").exists()

    a.send({"t": M.STICKER_CUSTOM_GET.value, "code": "lk1"})
    hdr, body = a.wait("sticker_custom_data")
    assert hdr and hdr["ext"] == "json" and body == _LOTTE_MINI

    # 不在白名单的 ext → error，不落盘
    a.send({"t": M.STICKER_CUSTOM_ADD.value, "code": "bad1",
            "ext": "exe"}, b"MZ...")
    err, _ = a.wait("error")
    assert err and err.get("code") == "sticker"
    assert "bad1" not in h.custom_stickers
    a.close()
