# -*- coding: utf-8 -*-
"""R72 多人语音房（全互联 mesh：服务器只发名册/地址，音频 UDP 直连不经服务器）。

与 R38 1v1 通话的关系
---------------------
- **互斥**：麦克风/扬声器硬件独占，进入语音房前若在 1v1 通话中直接拒绝。
- **同款加密**：载荷 ``[12B nonce][AES-GCM(PCM 320B)]``，密钥复用 1v1 E2EE 会话密钥
  （``core.e2ee.session_key``），因此「房友」之间必须先各自握过手（``_ensure_key``）。
- **只发音频**：mesh 下视频带宽是 N×(N-1) 倍，会打爆内网；视频继续走 1v1。

拓扑与端口（**与实施计划的一处必要偏差**，理由见下）
----------------------------------------------------
计划写的是「每对端一条 UDP socket」，但服务器侧的 ROOM_ADDR/ROOM_PEERS 协议每个
客户端只上报**一个** port（``[{uid,ip,port}]``）——若每人开 N-1 条 socket，就必须
上报 N-1 个端口，协议自相矛盾。因此这里用**每房一条共享 socket**：
- 本端只绑 1 个随机端口并上报一次；所有对端都发往该端口；
- 收端按来源 ``addr`` 反查 uid（LAN 内来源端口 == 对端上报端口，一一对应）；
- NAT 导致来源地址与上报不符时，回退「用各对端密钥逐个试解」，解出即学习新地址。
行为与计划完全一致，只是 socket 数量从 N-1 降为 1。

资源模型
--------
| 资源 | 数量 | 说明 |
|---|---|---|
| MicRecorder | 1 | 全房共用一份采集（硬件独占） |
| 发送线程 | 1 | 取 320B 帧 → 对每个对端各自加密外发 |
| UDP socket | 1 | 共享，见上 |
| 收线程 | 1 | 解密后按对端入队 |
| 探活线程 | 1 | 每 0.3s 给所有对端发空载荷（打洞 + connected 判定） |
| 混音线程 | 1 | 每 20ms 每对端取一帧 → 饱和相加 → 交 SpkPlayer |
| SpkPlayer | 1 | 硬件独占（自带抖动缓冲） |
"""
import array
import collections
import socket
import threading
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from protocol import MsgType as M
import voice_api

_NONCE_LEN = 12
_AUDIO_FRAME = 320       # 8kHz/16bit/单声道 20ms
_AUDIO_MS = 0.02
_PROBE_INTERVAL = 0.3
_MIX_Q = 6               # 每对端最多缓存的待混音帧数（约 120ms，防积压）
_LEVEL_REF = 6000.0      # RMS 归一化参考值（UI 说话高亮）
_LEVEL_DECAY = 0.72      # 电平衰减系数（每 20ms）


def rms_level(pcm: bytes) -> float:
    """20ms 帧的响度（0..1），供 UI 说话者高亮。"""
    a = array.array("h")
    a.frombytes(bytes(pcm)[:_AUDIO_FRAME].ljust(_AUDIO_FRAME, b"\x00"))
    s = 0
    for v in a:
        s += v * v
    if not len(a):
        return 0.0
    return min(1.0, (s / len(a)) ** 0.5 / _LEVEL_REF)


def mix_frames(frames, frame_bytes: int = _AUDIO_FRAME) -> bytes:
    """把多路 16bit PCM 饱和相加成一路（同一时刻每路至多一帧）。

    无输入 → 输出静音（保证播放器始终有帧可播，不欠载）。纯函数，便于单测。
    """
    n = frame_bytes // 2
    acc = [0] * n                    # 用 Python list 累加（array('h') 赋值会溢出）
    got = False
    for f in frames:
        if not f:
            continue
        a = array.array("h")
        a.frombytes(bytes(f)[:frame_bytes].ljust(frame_bytes, b"\x00"))
        got = True
        for i in range(n):
            acc[i] += a[i]
    if not got:
        return b"\x00" * frame_bytes
    out = array.array("h", bytes(frame_bytes))
    for i in range(n):
        v = acc[i]
        if v > 32767:
            v = 32767
        elif v < -32768:
            v = -32768
        out[i] = v
    return out.tobytes()


class _PeerLink:
    """房内单个对端：地址 + 会话密钥 + 待混音帧队列 + 说话电平。"""

    def __init__(self, uid: int, addr, aead, nick: str = "") -> None:
        self.uid = uid
        self.addr = tuple(addr)
        self.aead = aead
        self.nick = nick
        self.q = collections.deque(maxlen=_MIX_Q)
        self.connected = False
        self.level = 0.0
        self._lock = threading.Lock()

    def feed(self, pcm: bytes) -> None:
        with self._lock:
            self.q.append(pcm)

    def pop(self):
        with self._lock:
            return self.q.popleft() if self.q else None

    def clear(self) -> None:
        with self._lock:
            self.q.clear()


class VoiceRoom:
    """N 人 mesh 音频房编排器（挂 ClientCore.voice_room）。同一时刻至多一个房。"""

    def __init__(self, core) -> None:
        self.core = core
        self._lock = threading.RLock()
        self.room = None                 # 房间键："public" | "group:<gid>"
        self.state = "idle"              # idle / joining / joined
        self.members = []                # [{uid, nick}]（服务器名册快照）
        self.room_max = 0
        self._links = {}                 # uid -> _PeerLink
        self._addr_uid = {}              # (ip, port) -> uid
        self._pending_peers = []         # 音频未起时先缓存 ROOM_PEERS
        self._udp = None
        self._port = 0
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._mic = None
        self._spk = None
        self._mic_on = True
        self._threads = []
        self._local_level = 0.0
        self._started_at = 0.0

    # ---------- 对外 API ----------

    def in_room(self) -> bool:
        return self.state == "joined"

    def join(self, room: str) -> bool:
        """入房（服务器校验房间键与人数上限）。1v1 通话中 / 无音频设备 → 拒绝。"""
        with self._lock:
            if self.state != "idle":
                self._push("failed", text="已在语音房中")
                return False
        if not voice_api.available():
            self._push("failed", text="本机没有可用音频设备，无法进入语音房")
            return False
        calls = getattr(self.core, "calls", None)
        if calls is not None and getattr(calls, "state", "idle") != "idle":
            self._push("failed", text="正在通话中，请先结束 1v1 通话再进语音房")
            return False
        with self._lock:
            self.room = str(room)
            self.state = "joining"
            self.members = []
            self._pending_peers = []
        self._push("joining", text="正在进入语音房…")
        self.core._send_frame({"t": M.ROOM_JOIN.value, "room": self.room})
        return True

    def leave(self) -> None:
        """退房：发 ROOM_LEAVE 并释放全部音频/UDP 资源。"""
        with self._lock:
            if self.state == "idle":
                return
            room = self.room
            self._reset()
        self.core._send_frame({"t": M.ROOM_LEAVE.value, "room": room})
        self._push("left", text="已离开语音房")

    def set_mic(self, on: bool) -> None:
        """闭麦/开麦（热生效；只影响本端发送，不影响收听）。"""
        with self._lock:
            if self._mic_on == bool(on):
                return
            self._mic_on = bool(on)
            mic = self._mic
        if mic is not None:
            if on:
                if not mic.start():
                    with self._lock:
                        self._mic_on = False
                    self._push("warn", text="无法打开麦克风")
            else:
                mic.stop()
        self._push("mic", mic=bool(on))

    def is_mic_on(self) -> bool:
        return self._mic_on

    def member_list(self) -> list:
        with self._lock:
            return [dict(m) for m in self.members]

    def link_count(self) -> int:
        with self._lock:
            return len(self._links)

    def connected_count(self) -> int:
        with self._lock:
            return sum(1 for lk in self._links.values() if lk.connected)

    def speaker_levels(self) -> dict:
        """{uid: 0..1} 说话电平；uid=0 为本端（UI 高亮用）。"""
        out = {0: self._local_level}
        with self._lock:
            for uid, lk in self._links.items():
                out[uid] = lk.level
        return out

    def duration(self) -> float:
        return max(0.0, time.time() - self._started_at) if self._started_at else 0.0

    def shutdown(self) -> None:
        """断线/关停清理（不发声令帧）。"""
        with self._lock:
            self._reset()

    # ---------- 信令路由（core.dispatch 调用） ----------

    def handle(self, t: str, h: dict) -> None:
        if t == M.ROOM_STATE.value:
            self._on_state(h)
        elif t == M.ROOM_PEERS.value:
            self._on_peers(h)
        elif t == M.ROOM_ADDR.value:
            self._on_addr(h)

    def _on_state(self, h: dict) -> None:
        room = str(h.get("room") or "")
        with self._lock:
            if self.state == "idle" or room != self.room:
                return
            self.members = [{"uid": int(m.get("uid") or 0),
                             "nick": str(m.get("nick") or "")}
                            for m in (h.get("members") or [])
                            if isinstance(m, dict)]
            try:
                self.room_max = int(h.get("max") or 0)
            except (TypeError, ValueError):
                self.room_max = 0
            first = self.state == "joining"
            self.state = "joined"
        self._prune_links()
        if first:
            self._start_audio()
        self._push("roster")

    def _on_peers(self, h: dict) -> None:
        peers = h.get("peers")
        peers = peers if isinstance(peers, list) else []
        with self._lock:
            if self.state == "idle" or self._audio_up():
                pending = None
            else:
                self._pending_peers = list(peers)
                pending = True
        if pending is None:
            for p in peers:
                self._open_link_from(p)

    def _on_addr(self, h: dict) -> None:
        if not self.in_room() and self.state != "joined":
            return
        self._open_link_from(h)

    def _open_link_from(self, p) -> None:
        """按 {uid,ip,port} 建/更新一条对端链路（后台线程做 E2EE 握手）。"""
        if not isinstance(p, dict):
            return
        try:
            uid = int(p.get("uid") or 0)
            port = int(p.get("port") or 0)
        except (TypeError, ValueError):
            return
        ip = str(p.get("ip") or "")
        if uid <= 0 or uid == int(getattr(self.core, "uid", 0)):
            return
        if not ip or port <= 0:
            return
        with self._lock:
            if self.state != "joined":
                return
            nick = next((m["nick"] for m in self.members if m["uid"] == uid), "")
            lk = self._links.get(uid)
            if lk is not None:
                lk.addr = (ip, port)                 # 地址刷新（重连/换端口）
                lk.nick = nick or lk.nick
                self._addr_uid[(ip, port)] = uid
                return
        threading.Thread(target=self._build_link, args=(uid, ip, port, nick),
                         daemon=True, name=f"room-link-{uid}").start()

    def _build_link(self, uid: int, ip: str, port: int, nick: str) -> None:
        key = self._ensure_key(uid)
        with self._lock:
            if self.state != "joined" or uid in self._links:
                return
            if key is None:
                # 握手失败：跳过该对端（其余房友不受影响），名册仍显示此人
                self._push("peer_failed",
                           text=f"与 {nick or ('用户%d' % uid)} 的密钥协商失败，听不到对方")
                return
            lk = _PeerLink(uid, (ip, port), AESGCM(bytes(key)), nick)
            self._links[uid] = lk
            self._addr_uid[(ip, port)] = uid
        self._push("peers")

    def _prune_links(self) -> None:
        """名册里已消失的房友：拆掉其链路与地址映射。"""
        with self._lock:
            alive = {m["uid"] for m in self.members}
            gone = [u for u in self._links if u not in alive]
            for u in gone:
                lk = self._links.pop(u)
                self._addr_uid.pop(lk.addr, None)
            if gone:
                self._push("peers")

    # ---------- 音频链路 ----------

    def _audio_up(self) -> bool:
        return self._udp is not None

    def _start_audio(self) -> None:
        """绑共享 UDP 端口 → 起收/探活/混音线程 → 上报端口 → 拉起缓存的对端。"""
        if not voice_api.available():
            self._fail("本机没有可用音频设备")
            return
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(("0.0.0.0", 0))
        port = udp.getsockname()[1]
        with self._lock:
            if self.state != "joined":
                udp.close()
                return
            self._udp = udp
            self._port = port
            self._stop.clear()
            self._connected.clear()
            self._started_at = time.time()
            self._local_level = 0.0
        if self._spk is None:
            self._spk = voice_api.SpkPlayer(on_error=lambda m: self._fail(m))
            if self._spk.start() is False:
                self._fail("无法打开扬声器（无可用输出设备）")
                return
        if self._mic is None:
            self._mic = voice_api.MicRecorder(on_error=lambda m: self._fail(m))
        if self._mic_on and not self._mic.start():
            with self._lock:
                self._mic_on = False
            self._push("warn", text="无法打开麦克风（可正常收听）")
        t_recv = threading.Thread(target=self._recv_loop, args=(udp,), daemon=True,
                                  name="room-recv")
        t_probe = threading.Thread(target=self._probe_loop, daemon=True,
                                   name="room-probe")
        t_mix = threading.Thread(target=self._mix_loop, daemon=True,
                                 name="room-mix")
        t_send = threading.Thread(target=self._send_loop, daemon=True,
                                  name="room-send")
        with self._lock:
            self._threads = [t_recv, t_probe, t_mix, t_send]
        for t in (t_recv, t_probe, t_mix, t_send):
            t.start()
        # 上报本机端口：房内其他人据此向本端打洞
        self.core._send_frame({"t": M.ROOM_ADDR.value, "room": self.room,
                               "port": port})
        with self._lock:
            pending = list(self._pending_peers)
            self._pending_peers = []
        for p in pending:
            self._open_link_from(p)
        self._push("joined", text="已进入语音房（建议戴耳机防回声）")

    def _recv_loop(self, udp: socket.socket) -> None:
        udp.settimeout(0.2)
        while not self._stop.is_set():
            try:
                data, addr = udp.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                if not self._stop.is_set():
                    self._fail("语音房链路中断（网络异常）")
                return
            link = self._link_for_addr(addr, bytes(data), learn=True)
            if link is None:
                continue
            if len(data) <= _NONCE_LEN + 16:
                link.connected = True
                self._connected.set()
                continue
            try:
                pcm = link.aead.decrypt(bytes(data[:_NONCE_LEN]),
                                        bytes(data[_NONCE_LEN:]), None)
            except Exception:
                continue
            link.connected = True
            self._connected.set()
            if not pcm or len(pcm) > _AUDIO_FRAME:
                continue                      # 本房不发视频：非音频帧一律忽略
            link.feed(pcm)

    def _link_for_addr(self, addr, data: bytes, learn: bool = False):
        """按来源地址找对端链路；未知地址时用各对端密钥试解并学习新地址。"""
        with self._lock:
            uid = self._addr_uid.get(addr)
            if uid is not None:
                return self._links.get(uid)
            links = list(self._links.values())
        if not learn or len(data) <= _NONCE_LEN + 16:
            return None
        for lk in links:
            try:
                lk.aead.decrypt(bytes(data[:_NONCE_LEN]),
                                bytes(data[_NONCE_LEN:]), None)
            except Exception:
                continue
            with self._lock:
                self._addr_uid.pop(lk.addr, None)
                lk.addr = tuple(addr)
                self._addr_uid[tuple(addr)] = lk.uid
            return lk
        return None

    def _probe_loop(self) -> None:
        """探活/打洞：定时给每个对端发空载荷加密包。"""
        while not self._stop.is_set():
            with self._lock:
                links = list(self._links.values())
            for lk in links:
                self._send_packet(lk, b"")
            if self._stop.wait(_PROBE_INTERVAL):
                return

    def _send_loop(self) -> None:
        """麦克风 20ms 帧 → 对每个对端各自加密外发（本端电平用于高亮）。"""
        while not self._stop.is_set():
            with self._lock:
                mic = self._mic
                on = self._mic_on and self._udp is not None
            if not on or mic is None:
                if self._stop.wait(_AUDIO_MS):
                    return
                continue
            try:
                pcm = mic.frames.get(timeout=0.2)
            except Exception:
                continue
            self._local_level = rms_level(pcm)
            with self._lock:
                links = list(self._links.values())
            for lk in links:
                self._send_packet(lk, pcm)

    def _send_packet(self, link: _PeerLink, payload: bytes) -> None:
        with self._lock:
            udp = self._udp
        if udp is None:
            return
        try:
            from os import urandom
            nonce = urandom(_NONCE_LEN)
            ct = link.aead.encrypt(nonce, bytes(payload), None)
            udp.sendto(nonce + ct, link.addr)
        except OSError:
            pass

    def _mix_loop(self) -> None:
        """每 20ms 每对端取一帧 → 饱和相加 → 交 SpkPlayer（缺帧即静音）。"""
        interval = _AUDIO_MS
        next_t = time.perf_counter()
        while not self._stop.is_set():
            with self._lock:
                links = list(self._links.values())
                spk = self._spk
            frames = []
            for lk in links:
                f = lk.pop()
                if f:
                    lk.level = rms_level(f)
                else:
                    lk.level *= _LEVEL_DECAY
                    if lk.level < 0.02:
                        lk.level = 0.0
                frames.append(f)
            self._local_level *= _LEVEL_DECAY
            if self._local_level < 0.02:
                self._local_level = 0.0
            if spk is not None:
                spk.feed(mix_frames(frames))
            next_t += interval
            delay = next_t - time.perf_counter()
            if delay > 0:
                if self._stop.wait(delay):
                    return
            else:
                next_t = time.perf_counter()      # 落后则重置基准，防突发追赶

    # ---------- 工具 ----------

    def _ensure_key(self, peer: int):
        """房友间密钥 = 1v1 E2EE 会话密钥（与 R38 通话同源）；未建立则自动握手。"""
        core = self.core
        try:
            if core.e2ee_ready(peer):
                return core.e2ee.session_key(peer)
            fp = core.start_e2ee(peer, timeout=6.0)
            if not fp:
                return None
            return core.e2ee.session_key(peer)
        except Exception:
            return None

    def _reset(self) -> None:
        """清空全部房间资源（持锁调用）。"""
        self.state = "idle"
        self.room = None
        self.members = []
        self.room_max = 0
        self._pending_peers = []
        self._started_at = 0.0
        self._stop.set()
        self._connected.clear()
        udp, self._udp = self._udp, None
        self._port = 0
        if udp is not None:
            try:
                udp.close()
            except OSError:
                pass
        for lk in self._links.values():
            lk.clear()
        self._links = {}
        self._addr_uid = {}
        mic, self._mic = self._mic, None
        if mic is not None:
            mic.stop()
        spk, self._spk = self._spk, None
        if spk is not None:
            spk.stop()
        self._threads = []
        self._mic_on = True
        self._local_level = 0.0

    def _fail(self, text: str) -> None:
        """链路级失败：清理 + 通知（房员各自独立，不影响服务器名册）。"""
        with self._lock:
            self._reset()
        self._push("failed", text=text)

    def _push(self, state: str, **kw) -> None:
        ev = {"t": "room", "state": state, "room": self.room}
        ev.update({k: v for k, v in kw.items() if v is not None})
        try:
            self.core._push(ev)
        except Exception:
            pass