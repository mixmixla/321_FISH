# -*- coding: utf-8 -*-
"""R39A 冒烟：1v1 语音全双工（音频打桩，UDP 直连走真实本机回环）。

与 R38A 差异：连通后**无需任何按键**双方麦克风常开、音频双向对流；
PTT 在全双工下被忽略；通话中 set_duplex 热切换麦克风立刻停/复。
真设备听感（延迟/回声/爆音）属人工验证项，不在本脚本范围。
"""
import queue
import socket
import sys
import threading
import time
from dataclasses import replace

from config import CFG
from server import Hub, serve as serve_tcp
from client_core import ClientCore
import voice_call
import voice_api


class FakeMic:
    def __init__(self, on_error=None):
        self.frames = queue.Queue(maxsize=200)
        self.started = False
        self.stopped = False
        self._gen = None

    def start(self):
        self.started = True
        self.stopped = False
        self._gen = threading.Thread(target=self._produce, daemon=True)
        self._gen.start()
        return True

    def _produce(self):
        """连续采集（贴近真实麦克风）：20ms 一帧，直到 stop。"""
        while not self.stopped:
            try:
                self.frames.put(b"\x01\x02" * 160, timeout=0.1)
            except queue.Full:
                pass
            time.sleep(0.02)

    def stop(self):
        self.stopped = True


class FakeSpk:
    feeds = []                                    # 类级：断言用

    def __init__(self, on_error=None):
        self.started = False

    def start(self):
        self.started = True
        return True

    def feed(self, pcm):
        FakeSpk.feeds.append(bytes(pcm))

    def stop(self):
        pass


voice_api.MicRecorder = FakeMic
voice_api.SpkPlayer = FakeSpk
voice_call.voice_api = voice_api               # CallManager 内引用同一模块


class Collector:
    def __init__(self, core):
        self.events = []
        self._lock = threading.Lock()
        core._on_event = self._on

    def _on(self, ev):
        with self._lock:
            self.events.append(ev)

    def wait(self, t, state=None, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, e in enumerate(self.events):
                    if e.get("t") == t and (state is None
                                            or e.get("state") == state):
                        del self.events[i]
                        return e
            time.sleep(0.01)
        return None


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _spawn(port, nick, tmp):
    core = ClientCore(host="127.0.0.1", port=port, nick=nick,
                      history_dir=tmp,
                      heartbeat_interval=0.1, heartbeat_timeout=0.8,
                      reconnect_base=0.05, reconnect_max=0.3)
    col = Collector(core)
    core.start()
    assert col.wait("welcome"), f"{nick} 未收到 welcome"
    return core, col


def _rx_frames():
    return [p for p in list(FakeSpk.feeds) if len(p) == 320]


def main():
    import tempfile
    audit_dir = tempfile.mkdtemp(prefix="smoke39a_audit_")
    h = Hub(cfg=replace(CFG, audit_dir=audit_dir), audit_dir=audit_dir)
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    time.sleep(0.2)

    a, ca = _spawn(port, "甲", ".smoke39a_a")
    b, cb = _spawn(port, "乙", ".smoke39a_b")
    try:
        # 1. 呼叫接通（信令回归）
        assert a.calls.start_call(b.uid), "start_call 失败"
        assert cb.wait("call", "incoming"), "被叫未收到来电"
        assert b.calls.accept_call(), "accept_call 失败"
        assert ca.wait("call", "incall"), "主叫未进入 incall（UDP 打洞失败）"
        assert cb.wait("call", "incall"), "被叫未进入 incall"
        print("连通：双方 incall ✓")

        # 2. 全双工：无按键双方麦克风常开
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if a.calls._mic_up and b.calls._mic_up and a.calls._mic.started \
                    and b.calls._mic.started:
                break
            time.sleep(0.05)
        assert a.calls._mic_up and a.calls._mic.started, "甲麦克风未常开"
        assert b.calls._mic_up and b.calls._mic.started, "乙麦克风未常开"
        print("全双工：双方麦克风常开 ✓")

        # 3. 不按任何键，A 的语音自动流到 B（对端解密还原）
        n0 = len(_rx_frames())
        deadline = time.time() + 3.0
        while time.time() < deadline and len(_rx_frames()) - n0 < 5:
            time.sleep(0.05)
        assert len(_rx_frames()) - n0 >= 5, \
            f"B 未自动收到音频（新增 {len(_rx_frames()) - n0} 帧）"
        print(f"音频：B 无操作自动收到 {len(_rx_frames()) - n0} 帧 PCM ✓")

        # 4. 全双工下 PTT 被忽略（不干扰常开麦）
        a.calls.set_ptt(True)
        assert a.calls._ptt is False and a.calls._mic_up, "PTT 泄漏进全双工"
        a.calls.set_ptt(False)
        print("PTT：全双工下忽略 ✓")

        # 5. 热切换 全双工→PTT：甲麦克风立刻停；乙不受影响
        a.calls.set_duplex(False)
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if not a.calls._mic_up and a.calls._mic.stopped:
                break
            time.sleep(0.05)
        assert not a.calls._mic_up and a.calls._mic.stopped, "甲麦克风未停"
        assert b.calls._mic_up and b.calls._mic.started, "乙麦克风被误停"
        # 6. 热切换回全双工：甲麦克风恢复常开、链路仍通
        a.calls.set_duplex(True)
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if a.calls._mic_up and a.calls._mic.started:
                break
            time.sleep(0.05)
        assert a.calls._mic_up and a.calls._mic.started, "甲麦克风未恢复"
        n0 = len(_rx_frames())
        deadline = time.time() + 3.0
        while time.time() < deadline and len(_rx_frames()) - n0 < 3:
            time.sleep(0.05)
        assert len(_rx_frames()) - n0 >= 3, "热切换后音频断流"
        print("热切换：全双工↔PTT 麦克风停/复即时，链路保持 ✓")

        # 7. 挂断清理
        b.calls.end_call("再见")
        assert ca.wait("call", "ended"), "主叫未收到挂断"
        assert cb.wait("call", "ended"), "被叫未收到 ended"
        assert a.calls.state == "idle" and b.calls.state == "idle"
        assert a.calls._udp is None and b.calls._udp is None
        print("收尾：双方 ended，资源已清理 ✓")
        print("R39A 冒烟: 全部通过")
        return 0
    finally:
        a.stop()
        b.stop()
        stop.set()
        time.sleep(0.2)


if __name__ == "__main__":
    sys.exit(main())
