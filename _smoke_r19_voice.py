# -*- coding: utf-8 -*-
"""R19（语音消息）冒烟：
- 收到语音帧 → 历史含 voice 事件、voice_path 落盘存在、msg_list 渲染不崩
- _pcm_to_wav 输出合法 RIFF/WAVE
- 录音条"完成并发送" → 复用录音数据发语音，对端收到 voice/binary WAV 体
- 语音气泡点击播放回调已接入 app.msg_list._on_voice
"""
import os
import socket
import threading
import time
from dataclasses import replace

from config import CFG
from crypto import client_handshake
from server import Hub, serve as serve_tcp
from client_core import ClientCore
from client import ChatWindow


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _peer(port: int, nick: str):
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    chan = client_handshake(sock)
    sock.settimeout(None)
    chan.send_frame({"t": "hello", "nick": nick})
    while True:
        h, _b = chan.recv_frame()
        if h.get("t") == "welcome":
            return chan, h["uid"]


def main() -> int:
    cfg = replace(CFG, audit_dir="_tmp_gui/audit")
    hub = Hub(cfg=cfg, audit_dir="_tmp_gui/audit")
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)

    core = ClientCore(host="127.0.0.1", port=port, nick="冒烟主")
    app = ChatWindow(core)
    bob, _ = _peer(port, "乙方")
    core.start()
    deadline = time.time() + 6
    while not core.connected and time.time() < deadline:
        app.root.update()
        time.sleep(0.03)

    def pump(secs: float):
        t = time.time() + secs
        while time.time() < t:
            app.root.update()
            time.sleep(0.02)

    ok = True
    results = []

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    # 1) 对端发语音 → 本端历史含 voice 事件 + voice_path 落盘可读
    bob.send_frame({"t": "voice", "channel": "public", "duration": 2.5}, b"RIFFWAV1")
    pump(0.8)
    vmsg = next((m for m in core.history("public") if m.get("voice")), None)
    check("voice msg in history", vmsg is not None)
    if vmsg:
        check("voice duration kept", vmsg.get("duration") == 2.5)
        vp = vmsg.get("voice_path", "")
        check("voice_path persisted", bool(vp) and os.path.exists(vp), f"{vp}")
        if vp and os.path.exists(vp):
            check("voice file content", open(vp, "rb").read() == b"RIFFWAV1")

    # 2) msg_list 渲染 speaker 气泡不崩，且播放入口已接线
    app._switch_view("public", None)
    pump(0.4)
    check("on_voice wired", app.msg_list._on_voice == app._on_voice)
    vrow = next((r for r in app.msg_list._rows if r.voice), None)
    check("voice row seen in msg_list", vrow is not None)

    # 3) _pcm_to_wav 产出合法 RIFF/WAVE（R41A：8kHz 直录）
    pcm = bytes(bytearray((i & 0xFF) for i in range(16000)))   # 约 1 秒 8k/16bit
    wav = app._pcm_to_wav(pcm, 8000, 1, 2)
    check("wav has RIFF header", wav[:4] == b"RIFF" and wav[8:12] == b"WAVE")
    wav_len = int.from_bytes(wav[4:8], "little")
    check("wav length consistent", wav_len + 8 == len(wav))

    # 4) 录音条"完成并发送"：注入充足录音数据 → 对端收到 voice + WAV 体
    app._recorder = None
    app._rec_th = None
    app._rec_data = bytearray(pcm)                     # 约 1.0 秒
    app._stop_record(True)
    pump(0.8)
    got = False
    t_end = time.time() + 2
    while time.time() < t_end:
        try:
            h, body = bob.recv_frame()
            # 发送者同为公聊接收者，先忽略之前那条 2.5s 旧语音，直到匹配本次录音体
            if (h.get("t") == "chat" and h.get("voice")
                    and bytes(body) == wav and h.get("duration", -1) == 1.0):
                got = True
                break
        except Exception:
            pass
        time.sleep(0.02)
    check("peer received recorded voice", got)

    print("\n".join(results))
    bob.send_frame({"t": "bye"})
    app.quit_app()
    print("GUI VOICE SMOKE OK" if ok else "GUI VOICE SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())