# -*- coding: utf-8 -*-
"""R72 冒烟：多人语音房 · 论坛频道 · 位置共享 · 圆形视频留言。

进程内起真实 Hub + TCP 服务 + web 服务（HTTPS 关），用两个真 ClientCore
做双端联调；语音房用原始帧客户端（VoiceRoom 需音频硬件，smoke 环境无设备）；
纯逻辑的混音算法用注入 PCM 直接验证。跑完即删。
"""
import http.client
import json
import os
import socket
import sys
import tempfile
import threading
import time
from dataclasses import replace

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["MOYU_TCP_PORT"] = "19657"
os.environ["MOYU_UDP_PORT"] = "19658"
os.environ["MOYU_WEB_PORT"] = "19659"
os.environ["MOYU_WEB_HTTPS"] = "0"

import server
from config import CFG
from protocol import MsgType
from client_core import ClientCore
import optional

WEB_PORT = 19659
TCP_PORT = 19657
_FAIL = []


def pump(core, bucket):
    while True:
        try:
            ev = core.events.get(timeout=1.0)
        except Exception:
            if getattr(core, "_smoke_stop", False):
                return
            continue
        bucket.append(ev)


def wait_for(bucket, pred, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        for ev in bucket:
            try:
                if pred(ev):
                    return ev
            except Exception:
                pass
        time.sleep(0.05)
    return None


def wait_uid(core, bucket):
    ev = wait_for(bucket, lambda e: e.get("t") == "welcome")
    return ev["uid"] if ev else None


def need(cond, msg):
    if cond:
        print(f"[OK] {msg}")
    else:
        _FAIL.append(msg)
        print(f"[FAIL] {msg}")


def _http(method, path, body=None, cookie=""):
    conn = http.client.HTTPConnection("127.0.0.1", WEB_PORT, timeout=8)
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    data = json.dumps(body).encode() if body is not None else None
    if data:
        headers["Content-Type"] = "application/json"
    conn.request(method, path, data, headers)
    r = conn.getresponse()
    raw = r.read().decode() or "{}"
    conn.close()
    return r.status, raw


# ================ 语音房（原始帧客户端，不依赖音频硬件） ================

class _Cli:
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
                h, b = self.chan.recv_frame()
                with self._lock:
                    self.events.append((h, b))
        except Exception:
            pass

    def send(self, header, body=b""):
        self.chan.send_frame(header, body)

    def wait(self, t, timeout=3.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, (h, b) in enumerate(self.events):
                    if h.get("t") == t and (pred is None or pred(h)):
                        del self.events[i]
                        return h, b
            time.sleep(0.01)
        return None, None

    def hello(self):
        self.send({"t": "hello", "nick": self.nick})
        h, _ = self.wait("welcome")
        if h:
            self.uid = h["uid"]
        return h

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def _room_flow():
    """3 人入房 / 地址互换 / 退房（纯服务器协议，不涉音频）。"""
    clis = []
    for nick in ("房主", "房客甲", "房客乙"):
        c = _Cli(TCP_PORT, nick)
        c.hello()
        clis.append(c)

    a, b, c = clis
    # a 入房
    a.send({"t": MsgType.ROOM_JOIN.value, "room": "public"})
    st, _ = a.wait(MsgType.ROOM_STATE.value)
    need(st is not None and st["count"] == 1, "R72 语音房：a 入房名册 count=1")

    # a 上报端口
    a.send({"t": MsgType.ROOM_ADDR.value, "room": "public", "port": 40001})

    # b 入房 → 收到 ROOM_STATE + ROOM_PEERS（含 a 的地址）
    b.send({"t": MsgType.ROOM_JOIN.value, "room": "public"})
    st_b, _ = b.wait(MsgType.ROOM_STATE.value)
    need(st_b is not None and st_b["count"] == 2, "R72 语音房：b 入房 count=2")
    peers, _ = b.wait(MsgType.ROOM_PEERS.value)
    need(peers is not None
         and any(p["uid"] == a.uid for p in peers.get("peers", [])),
         "R72 语音房：b 收到 ROOM_PEERS 含 a 的地址")

    # b 上报端口 → a 收到 ROOM_ADDR
    b.send({"t": MsgType.ROOM_ADDR.value, "room": "public", "port": 40002})
    addr, _ = a.wait(MsgType.ROOM_ADDR.value)
    need(addr is not None and addr["uid"] == b.uid and addr["port"] == 40002,
         "R72 语音房：a 收到 b 的 ROOM_ADDR")

    # c 入房 → 3 人
    c.send({"t": MsgType.ROOM_JOIN.value, "room": "public"})
    st_c, _ = c.wait(MsgType.ROOM_STATE.value)
    need(st_c is not None and st_c["count"] == 3, "R72 语音房：c 入房 count=3")

    # a 退房 → b 收到 count=2
    a.send({"t": MsgType.ROOM_LEAVE.value, "room": "public"})
    st_l, _ = b.wait(MsgType.ROOM_STATE.value,
                    pred=lambda x: x.get("count") == 2)
    need(st_l is not None and st_l["count"] == 2,
         "R72 语音房：a 退房后 count=2")

    for c in clis:
        c.close()


# ================ 论坛频道 ================

def _forum_flow(cores):
    A, bA = cores["甲"]
    B, bB = cores["乙"]
    need(A.create_group("R72论坛", public=True, forum=True), "R72 建论坛频道")
    gs = wait_for(bA, lambda e: e.get("t") == "group_state"
                  and e.get("name") == "R72论坛")
    gid = (gs or {}).get("gid")
    if not gid:
        _FAIL.append("R72 跳过：未取到论坛 gid")
        return
    need(gs.get("kind") == "forum", "R72 论坛 kind=forum 下发")

    B.join_group(gid)
    wait_for(bB, lambda e: e.get("t") == "group_state" and e.get("gid") == gid)

    # 非创建者发贴 → 放行（论坛不拦）
    B.send_chat("论坛主贴", channel="group", to=gid)
    root = wait_for(bB, lambda e: e.get("t") == "chat"
                    and e.get("text") == "论坛主贴")
    rseq = (root or {}).get("seq")
    need(rseq is not None, "R72 论坛非创建者可发贴")

    # 回复带 thread_root
    A.send_chat("沙发评论", channel="group", to=gid, thread_root=rseq)
    reply = wait_for(bA, lambda e: e.get("t") == "chat"
                     and e.get("text") == "沙发评论")
    need(reply is not None and reply.get("thread_root") == rseq,
         "R72 论坛 thread_root 回复透传")

    # THREAD_FETCH
    B.send_thread_fetch("group", gid, rseq)
    th = wait_for(bB, lambda e: e.get("t") == MsgType.THREAD_HISTORY.value)
    msgs = (th or {}).get("msgs") or []
    need(th is not None and len(msgs) == 1 and msgs[0].get("text") == "沙发评论",
         f"R72 论坛 THREAD_FETCH 取到评论 -> {[m.get('text') for m in msgs]}")


# ================ 位置共享 ================

def _geo_flow(cores):
    A, bA = cores["甲"]
    B, bB = cores["乙"]

    # 位置卡片消息
    A.send_chat("我在这里", channel="public",
                geo={"lat": 39.9042, "lon": 116.4074, "name": "天安门"})
    ev = wait_for(bB, lambda e: e.get("t") == "chat" and e.get("geo"))
    need(ev is not None and ev["geo"]["lat"] == 39.9042
         and ev["geo"]["name"] == "天安门",
         f"R72 位置卡片透传 -> {(ev or {}).get('geo')}")

    # 非法坐标 → geo 丢弃，消息仍送达
    A.send_chat("坏坐标", channel="public",
                geo={"lat": 999, "lon": 116.4})
    ev2 = wait_for(bB, lambda e: e.get("t") == "chat"
                   and e.get("text") == "坏坐标")
    need(ev2 is not None and "geo" not in ev2,
         "R72 非法坐标丢弃但消息送达")

    # GEO_LIVE 广播不入历史
    A.send_geo_live("public", None, {"lat": 40.0, "lon": 116.0,
                                    "live": 1,
                                    "expire": time.time() + 300,
                                    "session": "s1"})
    gl = wait_for(bB, lambda e: e.get("t") == MsgType.GEO_LIVE.value)
    need(gl is not None and gl["geo"]["lat"] == 40.0
         and gl["geo"]["live"] == 1, "R72 GEO_LIVE 广播")

    # GEO_STOP
    A.send_geo_stop("public", None, session="s1")
    gs = wait_for(bB, lambda e: e.get("t") == MsgType.GEO_STOP.value)
    need(gs is not None and gs.get("session") == "s1", "R72 GEO_STOP 广播")


# ================ 视频留言 ================

def _vmemo_flow(cores):
    A, bA = cores["甲"]
    B, bB = cores["乙"]

    # 构造一个最小 VMA1
    from vmemo_api import pack
    fake_png = (b"\x89PNG\r\n\x1a\n"
                + b"\x00\x00\x00\x0dIHDR" + b"\x00" * 13
                + b"\x00\x00\x00\x00IEND\xae\x42\x60\x82")
    pcm = b"\x00\x01" * 100
    blob = pack([fake_png, fake_png], pcm, fps=8, dur_ms=250)

    A.send_vmemo("public", None, blob, duration=2.5)
    ev = wait_for(bB, lambda e: e.get("t") == "chat"
                  and e.get("vmemo") is True)
    need(ev is not None and ev.get("duration") == 2.5,
         "R72 视频留言透传 + duration 正确")
    seq = (ev or {}).get("seq")
    need(seq is not None, "R72 视频留言有 seq")


# ================ 网页端只读 ================

def _web_sanity(cores):
    A, bA = cores["甲"]

    # /api/room 只读查看语音房名册
    st, raw = _http("GET", "/api/room?room=public")
    need(st in (200, 401), f"R72 /api/room 端点可访问（{st}）")

    # /api/vmemo 取首帧
    ev = wait_for(bA, lambda e: e.get("t") == "chat"
                  and e.get("vmemo") is True)
    seq = (ev or {}).get("seq")
    if seq:
        st2, raw2 = _http("GET", f"/api/vmemo?seq={seq}")
        need(st2 in (200, 401, 404),
             f"R72 /api/vmemo 端点可访问（{st2}）")


# ================ 纯逻辑：混音算法 ================

def _mix_logic():
    """用注入 PCM 验证 mix_frames 饱和相加。"""
    import array
    from voice_room import mix_frames, rms_level, _AUDIO_FRAME

    # 两路全幅正值 → 饱和到 32767
    a = array.array("h", [32767] * (_AUDIO_FRAME // 2)).tobytes()
    b = array.array("h", [32767] * (_AUDIO_FRAME // 2)).tobytes()
    out = mix_frames([a, b])
    arr = array.array("h")
    arr.frombytes(out)
    need(all(v == 32767 for v in arr), "R72 mix_frames 饱和到 32767")

    # 空输入 → 静音
    out0 = mix_frames([])
    need(out0 == b"\x00" * _AUDIO_FRAME, "R72 mix_frames 空输入返回静音")

    # rms_level 静音 → 0
    need(rms_level(b"\x00" * 320) == 0.0, "R72 rms_level 静音=0")


def main() -> int:
    store = tempfile.mkdtemp(prefix="r72srv_")
    hub = server.Hub(cfg=CFG, store_dir=store)
    stop = threading.Event()
    threading.Thread(target=server.serve, args=(hub, None, stop, True),
                     daemon=True).start()

    ready = False
    end = time.time() + 10
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", TCP_PORT), timeout=1), \
                 socket.create_connection(("127.0.0.1", WEB_PORT), timeout=1):
                ready = True
                break
        except OSError:
            time.sleep(0.3)
    if not ready:
        print("服务未就绪")
        return 1

    cores = {}
    try:
        for nick in ("甲", "乙"):
            c = ClientCore(host="127.0.0.1", port=TCP_PORT, nick=nick,
                           history_dir=os.path.join(
                               tempfile.mkdtemp(prefix="r72h_"), "h"))
            b = []
            c._smoke_stop = False
            threading.Thread(target=pump, args=(c, b), daemon=True).start()
            cores[nick] = (c, b)
            c.start()
        for nick in ("甲", "乙"):
            uid = wait_uid(*cores[nick])
            if uid is None:
                _FAIL.append(f"桌面端 {nick} 未上线")
            else:
                print(f"[..] {nick} uid={uid}")
        if _FAIL:
            return 1

        _room_flow()
        _forum_flow(cores)
        _geo_flow(cores)
        _vmemo_flow(cores)
        _web_sanity(cores)
        _mix_logic()
    finally:
        for _nick, (c, _b) in cores.items():
            c._smoke_stop = True
            try:
                c.stop()
            except Exception:
                pass
        stop.set()

    if _FAIL:
        for f in _FAIL:
            print(f"[FAIL] {f}")
        print("R72 SMOKE FAIL")
        return 1
    print("R72 SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
