# -*- coding: utf-8 -*-
"""R39A 1v1 全双工语音回归。

- 模式语义：默认全双工；连通即双方常开麦（无按键双向收流）；PTT 保留为可选
  模式（回归旧行为：连通不开麦、按住才开、松开即停）
- 热切换：通话中 set_duplex 开/关麦克风即时生效；全双工下 set_ptt 被忽略
- jitter buffer：预缓冲帧数在计划区间；足量即返/欠载提前开播；溢出丢旧帧
- 信令回归：占线第三方回 END；挂断后资源清理（麦克风停、_mic_up 复位）
- 通话窗：模式钮/PTT 钮/提示行随模式与状态显隐
"""
import queue
import threading
import time
import tkinter as tk
from types import SimpleNamespace

import pytest

import voice_api
from protocol import MsgType as M
from voice_call import CallManager
from widgets.call_window import CallWindow

_PCM = b"\x01\x02" * 160          # 一帧 320B 假 PCM


# ---------- 夹具 ----------

@pytest.fixture()
def stub_audio(monkeypatch):
    """音频设备打桩：不碰真实 winmm 设备，采集/播放走内存。"""
    class StubMic:
        def __init__(self, on_error=None):
            self.frames = queue.Queue()
            self.stopped = False
            self.started = False

        def start(self):
            self.started = True
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

        def last(self):
            with self._lock:
                return self.fed[-1] if self.fed else None

    monkeypatch.setattr(voice_api, "MicRecorder", StubMic)
    monkeypatch.setattr(voice_api, "SpkPlayer", StubSpk)
    return SimpleNamespace(Mic=StubMic, Spk=StubSpk)


class _FakeCore:
    def __init__(self, uid, nick):
        self.uid = uid
        self.nick = nick
        self.roster = {}
        self.known = {}
        self.sent = []
        self.events = []
        self.e2ee = SimpleNamespace(session_key=lambda uid: b"k" * 32)
        self._route = None                      # 模拟服务器转发目标

    def _send_frame(self, h, body=b""):
        self.sent.append(h)
        if self._route is not None:
            self._route(h)
        return True

    def _push(self, ev):
        self.events.append(ev)

    def e2ee_ready(self, uid):
        return True

    def start_e2ee(self, uid, timeout=5.0):
        return "fp:👍"


def _wait(cond, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


def _pair(stub_audio):
    """甲乙两台 CallManager，经假服务器路由互通（CALL_READY 回填 127.0.0.1）。"""
    core_a = _FakeCore(1, "甲")
    core_b = _FakeCore(2, "乙")
    cm_a = CallManager(core_a)
    cm_b = CallManager(core_b)

    def route(src, dst):
        def send(h, body=b""):
            h2 = dict(h)
            h2["from"] = src.uid
            if h.get("t") == M.CALL_READY.value:
                h2["ip"] = "127.0.0.1"
            dst.handle(h["t"], h2)
        return send

    core_a._route = route(core_a, cm_b)
    core_b._route = route(core_b, cm_a)
    core_a.known[2] = {"nick": "乙"}
    core_b.known[1] = {"nick": "甲"}
    return core_a, cm_a, core_b, cm_b


def _connect(stub_audio, cm_a, cm_b):
    """甲呼叫乙并等双方进 incall（真实 UDP 回环 + 探活打洞）。"""
    assert cm_a.start_call(2) is True
    assert cm_b.accept_call() is True
    assert _wait(lambda: cm_a.state == "incall" and cm_b.state == "incall"), \
        "双方未连通"
    return time.time()


# ================= 模式语义 =================

def test_default_duplex_and_toggle(stub_audio):
    cm = CallManager(_FakeCore(1, "甲"))
    assert cm.is_duplex() is True          # R39A：默认全双工
    cm.set_duplex(False)
    assert cm.is_duplex() is False
    cm.set_duplex(False)                   # 幂等
    assert cm.is_duplex() is False
    cm.set_duplex(True)
    assert cm.is_duplex() is True


def test_duplex_connected_auto_mic_both_directions(stub_audio):
    core_a, cm_a, core_b, cm_b = _pair(stub_audio)
    _connect(stub_audio, cm_a, cm_b)
    # 全双工：连通即双方常开麦，无需任何按键
    assert cm_a._mic_up and cm_a._mic.started and not cm_a._mic.stopped
    assert cm_b._mic_up and cm_b._mic.started and not cm_b._mic.stopped
    # 甲→乙：甲麦克风帧被采集加密发送，乙扬声器解密还原
    cm_a._mic.frames.put(_PCM)
    assert _wait(lambda: cm_b._spk.last() == _PCM), "甲→乙 音频未到达"
    # 乙→甲 反向同样成立
    cm_b._mic.frames.put(_PCM)
    assert _wait(lambda: cm_a._spk.last() == _PCM), "乙→甲 音频未到达"
    # 连通提示带全双工/戴耳机语义
    evs = [e for e in core_a.events if e.get("t") == "call"
           and e.get("state") == "incall"]
    assert evs and "全双工" in evs[-1]["text"]


def test_ptt_mode_regress_old_behavior(stub_audio):
    core_a, cm_a, core_b, cm_b = _pair(stub_audio)
    cm_a.set_duplex(False)
    cm_b.set_duplex(False)
    _connect(stub_audio, cm_a, cm_b)
    # PTT 模式：连通不开麦
    assert not cm_a._mic_up and cm_a._mic is None
    # 按住才开麦，帧可送达
    cm_a.set_ptt(True)
    assert cm_a._mic_up and cm_a._mic.started
    cm_a._mic.frames.put(_PCM)
    assert _wait(lambda: cm_b._spk.last() == _PCM), "PTT 音频未到达"
    # 松开即停
    cm_a.set_ptt(False)
    assert _wait(lambda: not cm_a._mic_up and cm_a._mic.stopped)
    # 对端 PTT 不受影响：乙仍可按住发话
    cm_b.set_ptt(True)
    cm_b._mic.frames.put(_PCM)
    assert _wait(lambda: cm_a._spk.last() == _PCM), "对端 PTT 音频未到达"


def test_ptt_ignored_outside_call_and_in_duplex(stub_audio):
    core = _FakeCore(1, "甲")
    cm = CallManager(core)
    cm.set_ptt(True)                       # 非通话期：安全空操作
    assert cm._ptt is False and cm._mic is None
    core_a, cm_a, core_b, cm_b = _pair(stub_audio)
    _connect(stub_audio, cm_a, cm_b)
    cm_a.set_ptt(True)                     # 全双工下 PTT 被忽略
    assert cm_a._ptt is False
    assert cm_a._mic_up                    # 麦克风不受影响保持常开


def test_mode_hot_switch_midcall(stub_audio):
    core_a, cm_a, core_b, cm_b = _pair(stub_audio)
    _connect(stub_audio, cm_a, cm_b)
    # 全双工 → PTT：麦克风停（_mic 创建在后台 call-wait 线程，竞态下可为 None，None 亦视为已停）
    cm_a.set_duplex(False)
    assert _wait(lambda: not cm_a._mic_up
                 and (cm_a._mic is None or cm_a._mic.stopped))
    # PTT → 全双工：麦克风恢复常开
    cm_a.set_duplex(True)
    assert _wait(lambda: cm_a._mic_up and cm_a._mic.started)
    # 热切换后链路仍通
    cm_a._mic.frames.put(_PCM)
    assert _wait(lambda: cm_b._spk.last() == _PCM), "切换后音频断流"


def test_end_call_cleans_mic_and_state(stub_audio):
    core_a, cm_a, core_b, cm_b = _pair(stub_audio)
    _connect(stub_audio, cm_a, cm_b)
    assert cm_a.end_call("好了") is True
    assert _wait(lambda: cm_a.state == "idle")
    assert cm_a._mic_up is False and (cm_a._mic is None or cm_a._mic.stopped)
    assert cm_a._udp is None
    assert _wait(lambda: cm_b.state == "idle")     # 对端收 END 同步清理
    assert cm_b._mic_up is False


def test_busy_third_party_regress(stub_audio):
    core_a, cm_a, core_b, cm_b = _pair(stub_audio)
    _connect(stub_audio, cm_a, cm_b)
    core_b._route = None                   # 断开乙→甲转发，隔离观察占线回执
    core_c = _FakeCore(3, "丙")
    cm_c = CallManager(core_c)
    core_c._route = lambda h: cm_b.handle(h["t"], {**h, "from": 3})
    assert cm_c.start_call(2) is True
    end = next(h for h in core_b.sent
               if h.get("t") == M.CALL_END.value and h.get("reason") == "占线")
    cm_c.handle(M.CALL_END.value, {**end, "from": 2})
    assert cm_c.state == "idle"            # 丙被占线快速结束
    assert cm_b.state == "incall" and cm_b.peer == 1   # 原通话（与甲）不受影响


# ================= jitter buffer =================

def test_spk_jitter_prime_full_and_starved():
    assert 3 <= voice_api.JITTER_MIN <= 5          # 计划区间（60~100ms）
    if not voice_api.available():
        pytest.skip("非 Windows/无音频设备：SpkPlayer 为占位实现")
    spk = voice_api.SpkPlayer()
    # 足量：_pump 先取走首帧，_prime 攒满 JITTER_MIN（含首帧共 4 帧）
    for _ in range(voice_api.JITTER_MIN):
        spk._jitter.put(_PCM)
    assert spk._jitter.get_nowait() is not None    # 模拟 _pump 取首帧
    assert spk._prime() == voice_api.JITTER_MIN
    assert spk._jitter.qsize() == 0
    # 欠载：无后续帧也提前开播（短超时后返回 1）
    t0 = time.time()
    assert spk._prime() == 1
    assert time.time() - t0 < 1.0


def test_spk_feed_overflow_drops_old():
    if not voice_api.available():
        pytest.skip("非 Windows/无音频设备：SpkPlayer 为占位实现")
    spk = voice_api.SpkPlayer()
    for _ in range(105):
        spk.feed(_PCM)
    assert spk._jitter.qsize() == 100              # maxsize=100
    oldest = spk._jitter.get_nowait()
    assert oldest is not None and oldest != b""    # 丢旧帧保实时，不崩


# ================= 通话窗 =================

@pytest.fixture(scope="module")
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def _packed(w):
    try:
        w.pack_info()
        return True
    except tk.TclError:
        return False


def test_call_window_mode_widgets(stub_audio, root):
    core_a, cm_a, core_b, cm_b = _pair(stub_audio)
    _connect(stub_audio, cm_a, cm_b)
    win = CallWindow(root, manager=cm_a, peer_nick="乙")
    try:
        win.update_state({"t": "call", "state": "incall",
                          "peer": 2, "nick": "乙",
                          "text": cm_a._incall_text()})
        root.update()
        # 全双工：模式钮显示切 PTT 动作，PTT 钮隐藏，戴耳机提示可见
        assert "按住说话" in win.btn_mode.cget("text")
        assert not _packed(win.btn_ptt)
        assert _packed(win.lbl_hint)
        # 切到 PTT：热生效 + 模式钮文案反转 + PTT 钮出现
        win._toggle_mode()
        root.update()
        assert cm_a.is_duplex() is False
        assert "全双工" in win.btn_mode.cget("text")
        assert _packed(win.btn_ptt) and not _packed(win.lbl_hint)
        # PTT 下按住/松开联动窗口文案
        win._ptt_on()
        assert cm_a._mic_up
        assert win.btn_ptt.cget("text") == "讲话中…"
        win._ptt_off()
        assert not cm_a._mic_up
        assert win.btn_ptt.cget("text") == "按住 讲话"
        # 结束态：模式相关控件全部收起
        win.update_state({"t": "call", "state": "ended", "peer": 2,
                          "text": "已挂断"})
        root.update()
        assert not _packed(win.btn_mode) and not _packed(win.btn_ptt)
    finally:
        cm_a.end_call()
        try:
            win.destroy()
        except tk.TclError:
            pass


def test_call_window_duplex_persist_callback(stub_audio, root):
    core_a, cm_a, core_b, cm_b = _pair(stub_audio)
    _connect(stub_audio, cm_a, cm_b)
    saved = []
    win = CallWindow(root, manager=cm_a, peer_nick="乙",
                     persist_mode=saved.append)
    try:
        win.update_state({"t": "call", "state": "incall", "peer": 2,
                          "nick": "乙", "text": ""})
        root.update()
        win._toggle_mode()
        assert saved == [False]                    # 切换值回传 client 持久化
        win._toggle_mode()
        assert saved == [False, True]
    finally:
        cm_a.end_call()
        try:
            win.destroy()
        except tk.TclError:
            pass
