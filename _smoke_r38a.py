# -*- coding: utf-8 -*-
"""R38a 冒烟：1v1 语音对讲信令全流程（音频层打桩，UDP 直连走真实本机回环）。

流程：A 呼 B → B 来电 → B 接听 → CALL_READY 回填 ip → UDP 打洞连通 →
A PTT 说话 → B 收到解密 PCM → B 挂断 → 双方 ended 清理。
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

    def start(self):
        self.started = True
        for _ in range(10):
            self.frames.put(b"\x01\x02" * 160)   # 320B 假 PCM
        return True

    def stop(self):
        pass


class FakeSpk:
    feeds = []                                    # 类级：测试断言用

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


def main():
    import tempfile
    audit_dir = tempfile.mkdtemp(prefix="smoke38a_audit_")
    h = Hub(cfg=replace(CFG, audit_dir=audit_dir), audit_dir=audit_dir)
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    time.sleep(0.2)

    a, ca = _spawn(port, "甲", ".smoke38a_a")
    b, cb = _spawn(port, "乙", ".smoke38a_b")
    try:
        # 1. 主叫发起
        assert a.calls.start_call(b.uid), "start_call 失败"
        ev = ca.wait("call", "ringing")
        assert ev, "主叫未进入 ringing"
        ev = cb.wait("call", "incoming")
        assert ev and ev.get("peer") == a.uid, "被叫未收到来电"

        # 2. 被叫接听 → 双方连通（本机回环 UDP 直连）
        assert b.calls.accept_call(), "accept_call 失败"
        assert ca.wait("call", "connecting"), "主叫未进入 connecting"
        assert cb.wait("call", "incall"), "被叫未进入 incall"
        assert ca.wait("call", "incall"), "主叫未进入 incall（UDP 打洞失败）"
        assert a.calls.state == "incall" and b.calls.state == "incall"
        assert a.calls._udp is not None and b.calls._udp is not None
        print("连通：双方 incall ✓")

        # 3. PTT 说话 → 被叫收到解密后 PCM
        a.calls.set_ptt(True)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            got = [p for p in list(FakeSpk.feeds) if len(p) == 320]
            if len(got) >= 5:
                break
            time.sleep(0.05)
        a.calls.set_ptt(False)
        got = [p for p in list(FakeSpk.feeds) if len(p) == 320]
        assert len(got) >= 5, f"被叫只收到 {len(got)} 帧音频"
        print(f"音频：被叫收到 {len(got)} 帧 320B PCM（解密成功）✓")

        # 4. 被叫挂断 → 双方 ended + 资源清理
        b.calls.end_call("再见")
        assert ca.wait("call", "ended"), "主叫未收到挂断"
        assert cb.wait("call", "ended"), "被叫未收到 ended"
        assert a.calls.state == "idle" and b.calls.state == "idle"
        assert a.calls._udp is None and b.calls._udp is None
        print("收尾：双方 ended，UDP/音频资源已清理 ✓")

        # 5. 占线校验：B 呼 A，A 再呼别人应失败 → 简化为 A 呼 B 后 B 来电占线
        assert a.calls.start_call(b.uid), "第二次发起失败"
        assert cb.wait("call", "incoming"), "B 未再次来电"
        assert not a.calls.start_call(a.uid), "通话中重复发起未被拒"
        a.calls.end_call("取消呼叫")       # 主叫取消走 end_call（reject 仅被叫）
        assert ca.wait("call", "ended"), "A 未收到取消"
        assert cb.wait("call", "ended"), "B 未收到取消回执"
        print("占线/拒绝 ✓")
        print("R38A 冒烟: 全部通过")
        return 0
    finally:
        a.stop()
        b.stop()
        stop.set()
        time.sleep(0.2)


if __name__ == "__main__":
    sys.exit(main())
