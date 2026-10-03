# -*- coding: utf-8 -*-
"""R38 1v1 语音对讲编排（挂 ClientCore.calls，由 core 转发 CALL_* 信令帧）。

流程（服务器只搭桥，音频 UDP 直连不经服务器）：
1. 主叫 start_call → CALL_RING → 服务器转发 → 被叫弹来电窗
2. 被叫 accept_call（先确保 1v1 E2EE 会话，密钥复用）→ CALL_ACCEPT{vcap}
3. 主叫收 ACCEPT{vcap=对端视频能力} → 绑随机 UDP 端口 → CALL_READY{port,vcap}
4. 被叫收 READY → 双方各起 UDP 收发循环；探活包同期互发完成打洞
5. 音频载荷 [12B nonce][AES-GCM(PCM 320B)]；R39A 默认全双工（连通即双方常开麦，
   建议戴耳机防回声），PTT 按住说话保留为可选模式（set_duplex 切换，热生效）
6. end_call → CALL_END 双向清理；UDP 打洞失败明确报错（本期不做服务器音频中转）

R45 视频（共用同一 UDP 加密通道，桌面端 only）：
- 能力协商：ACCEPT/READY 各带 vcap（本机有摄像头=1）；对端不支持则 UI 不出
  摄像头开关（老客户端无该字段=0，自动降级纯语音）
- 复用切换：解密后载荷 >320B 判为视频分片（视频载荷下限 321B）→ 重组回调
  video_frame 事件；=320B 为音频。探活包在解密前已按包长剔除
- 发送：set_video(True) 起 CamRecorder，采集线程回调 PNG → Chunker 分片逐片
  _send_packet（AES-GCM 同音频）；丢片由重组端 TTL 淘汰，不做重传
- D15：set_video(True, source="screen") 改起 ScreenRecorder（Pillow 抓屏 → 同一
  PNG 分片管线，对端零改动）；video 事件带 source 供 UI 区分开关文案

边界：密聊会话未建立时自动握手；握手失败/无音频设备 → 通话失败并提示。
"""
import os
import socket
import threading
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from protocol import MsgType as M
from config import CFG
import video_api
import voice_api

_NONCE_LEN = 12
_AUDIO_FRAME = 320       # 音频帧定长（>320B 的解密载荷一律按视频分片处理）
_PROBE_INTERVAL = 0.3    # 探活包间隔（打洞 + connected 判定）
_PROBE_COUNT = 33        # ~10s 连不上判失败


class CallManager:
    """1v1 通话状态机 + UDP 音频链路。同一时刻至多一路通话。"""

    def __init__(self, core) -> None:
        self.core = core
        self._lock = threading.RLock()
        self.state = "idle"        # idle/ringing/incoming/connecting/incall
        self.peer = None           # 对端 uid
        self.peer_nick = ""
        self.role = None           # "caller" | "callee"
        self._key = None
        self._aead = None
        self._udp = None
        self._peer_addr = None
        self._connected = threading.Event()
        self._stop = threading.Event()
        self._mic = None
        self._spk = None
        self._threads = []
        self._duplex = True             # R39A：默认全双工（客户端按 prefs 初始化）
        self._ptt = False               # PTT 按住态（仅半双工模式有意义）
        self._mic_up = False            # 麦克风期望开启态（_apply_mic 同步）
        self._started_at = 0.0
        # R45 视频：能力探测后台预热（避免接听时现场枚举卡顿）。
        # REL-01 hardware=0 forbids even this Media Foundation preheat.
        if CFG.hardware_enabled:
            threading.Thread(target=video_api.available, daemon=True,
                             name="cam-probe").start()
        self._has_cam = False           # 本机摄像头可用（惰性探测缓存）
        self._peer_vcap = False         # 对端声明支持视频（ACCEPT/READY 协商）
        self._video_on = False          # 本端视频开关
        self._video_source = "cam"      # D15：当前采集源 "cam"（摄像头）| "screen"（屏幕）
        self._cam = None                # CamRecorder | ScreenRecorder | None
        self._chunker = video_api.Chunker()
        self._reasm = video_api.Reassembler()
        self._fid = 0                   # 发送帧序号（u16 回绕）

    # ---------- 对外 API ----------

    def start_call(self, to_uid: int) -> bool:
        """主叫发起。要求在线；未建立 E2EE 时自动握手（阻塞至多 5s）。"""
        with self._lock:
            if self.state != "idle":
                self._push("failed", text="已在通话中")
                return False
        nick = (self.core.roster.get(to_uid) or
                self.core.known.get(to_uid) or {}).get("nick") or f"用户{to_uid}"
        key = self._ensure_key(to_uid)
        if key is None:
            self._push("failed", peer=to_uid, nick=nick,
                       text="密聊握手失败，无法建立加密通话")
            return False
        with self._lock:
            self.state = "ringing"
            self.peer = int(to_uid)
            self.peer_nick = nick
            self.role = "caller"
            self._key = key
            self._aead = AESGCM(bytes(key))
        self.core._send_frame({"t": M.CALL_RING.value, "to": int(to_uid)})
        self._push("ringing", peer=to_uid, nick=nick, text=f"正在呼叫 {nick}…")
        return True

    def accept_call(self) -> bool:
        """被叫接受：确保密钥 → CALL_ACCEPT。"""
        with self._lock:
            if self.state != "incoming":
                return False
            peer, nick = self.peer, self.peer_nick
            self.state = "connecting"
        key = self._ensure_key(peer)
        if key is None:
            self._fail(f"与 {nick} 的密聊握手失败，无法接听")
            return False
        with self._lock:
            self._key = key
            self._aead = AESGCM(bytes(key))
            self._has_cam = (video_api.available() if CFG.hardware_enabled
                             else False)            # 惰性探测（已预热则瞬时）
        self.core._send_frame({"t": M.CALL_ACCEPT.value, "to": int(peer),
                               "vcap": 1 if self._has_cam else 0})
        self._push("connecting", peer=peer, nick=nick, text="已接听，建立直连…")
        return True

    def reject_call(self, reason: str = "") -> bool:
        with self._lock:
            if self.state != "incoming":
                return False
            peer = self.peer
            self._reset()
        self.core._send_frame({"t": M.CALL_REJECT.value, "to": int(peer),
                               "reason": str(reason or "已拒绝")[:100]})
        self._push("ended", peer=peer, text="已拒绝")
        return True

    def end_call(self, reason: str = "已挂断") -> bool:
        """主动挂断（双向清理）。"""
        with self._lock:
            if self.state == "idle":
                return False
            peer = self.peer
            self._reset()
        if peer is not None:
            self.core._send_frame({"t": M.CALL_END.value, "to": int(peer),
                                   "reason": str(reason)[:100]})
        self._push("ended", peer=peer, text=str(reason))
        return True

    def is_duplex(self) -> bool:
        """当前是否全双工模式（客户端持久化 prefs['call_duplex']）。"""
        return self._duplex

    def set_duplex(self, on: bool) -> None:
        """R39A 全双工开关（热生效）：开=连通后麦克风常开；关=回到 PTT。"""
        with self._lock:
            if self._duplex == bool(on):
                return
            self._duplex = bool(on)
        self._apply_mic()

    def set_ptt(self, on: bool) -> None:
        """PTT：按住开麦、松开停（半双工防回声）。全双工模式下忽略。"""
        with self._lock:
            if self.state != "incall" or self._duplex:
                return
            if on == self._ptt:
                return
            self._ptt = on
        self._apply_mic()

    # ---------- R45 视频 ----------

    def video_supported(self) -> bool:
        """双方都具备视频条件（对端声明 vcap 且本机有摄像头）才出摄像头开关。"""
        return self._peer_vcap and video_api.available()

    def screen_supported(self) -> bool:
        """D15：对端能显示视频 + 本机能抓屏 → 出「共享屏幕」开关。"""
        return self._peer_vcap and video_api.screen_available()

    def video_source(self) -> str:
        """D15：当前采集源（"cam" | "screen"）。"""
        return self._video_source

    def is_video_on(self) -> bool:
        return self._video_on

    def set_video(self, on: bool, source: str = "cam") -> None:
        """本端视频开关（热生效）。``source``：摄像头 "cam"（默认）/ 屏幕 "screen"。

        开启在后台线程起采集（避免卡 UI）；关闭不区分来源，一律停当前采集器。
        """
        src = "screen" if source == "screen" else "cam"
        with self._lock:
            if self._video_on == bool(on):
                return
            if on and self.state != "incall":
                return
            self._video_on = bool(on)
            if on:
                self._video_source = src
        if on:
            threading.Thread(target=self._cam_start, args=(src,), daemon=True,
                             name="cam-start").start()
        else:
            cam, self._cam = self._cam, None
            if cam is not None:
                cam.stop()
            self._push("video", on=False, source=src)

    def _cam_start(self, source: str = "cam") -> None:
        """按来源起采集器（D15：摄像头 / 屏幕共享，两者接口一致）。"""
        if source == "screen":
            rec = video_api.ScreenRecorder(on_frame=self._send_video_frame,
                                           on_error=self._video_fail)
        else:
            rec = video_api.CamRecorder(on_frame=self._send_video_frame,
                                        on_error=self._video_fail)
        if not rec.start():
            return                          # on_error 已提示并复位
        with self._lock:
            if not self._video_on:          # 期间已被关闭：立即丢弃
                rec.stop()
                return
            self._cam = rec
        self._push("video", on=True, source=source)

    def _send_video_frame(self, png: bytes) -> None:
        """采集线程回调：PNG → 分片 → 逐片加密外发（不重传，丢片 TTL 淘汰）。"""
        with self._lock:
            if self.state != "incall" or not self._video_on:
                return
            fid = self._fid
            self._fid = (self._fid + 1) & 0xFFFF
        for chunk in self._chunker.chunk(png, fid):
            self._send_packet(chunk)
        # 任务4：本端镜像预览——同一帧回显到通话窗（与对端 video_frame 并行，
        # 采集线程回调，_push 已线程安全）
        self._push("video_local", png=png)

    def _video_fail(self, text: str) -> None:
        """摄像头异常：停发 + UI 复位开关（通话继续，仅视频下线）。"""
        with self._lock:
            self._video_on = False
            self._cam = None
        self._push("video", on=False, text=str(text))

    def _apply_mic(self) -> None:
        """按（模式 + PTT 按住态）同步麦克风与发送线程（幂等）。"""
        with self._lock:
            if self.state != "incall":
                return
            desired = self._duplex or self._ptt
            if desired == self._mic_up:
                return
            self._mic_up = desired
        if desired:
            if self._mic is None:
                self._mic = voice_api.MicRecorder(
                    on_error=lambda m: self._fail(m))
            if not self._mic.start():
                with self._lock:
                    self._mic_up = False
                self._push("warn", text="无法打开麦克风")
                return
            threading.Thread(target=self._send_loop, daemon=True,
                             name="call-send").start()
        else:
            if self._mic is not None:
                self._mic.stop()

    def duration(self) -> float:
        return max(0.0, time.time() - self._started_at) if self._started_at else 0.0

    def shutdown(self) -> None:
        """断线/关停清理（不发声令帧）。"""
        with self._lock:
            self._reset()

    # ---------- 信令路由（core.dispatch 调用） ----------

    def handle(self, t: str, h: dict) -> None:
        if t == M.CALL_RING.value:
            self._on_ring(h)
        elif t == M.CALL_ACCEPT.value:
            self._on_accept(h)
        elif t == M.CALL_REJECT.value:
            self._on_reject(h)
        elif t == M.CALL_READY.value:
            self._on_ready(h)
        elif t == M.CALL_END.value:
            self._on_end(h)

    def _on_ring(self, h: dict) -> None:
        src = int(h.get("from") or 0)
        with self._lock:
            if self.state != "idle":
                # 占线：立即回 END 让对方快速失败
                self.core._send_frame({"t": M.CALL_END.value, "to": src,
                                       "reason": "占线"})
                return
            self.state = "incoming"
            self.peer = src
            self.peer_nick = str(h.get("nick") or f"用户{src}")
            self.role = "callee"
        self._push("incoming", peer=src, nick=self.peer_nick,
                   text=f"{self.peer_nick} 请求语音通话")

    def _on_accept(self, h: dict) -> None:
        with self._lock:
            if self.state != "ringing" or self.role != "caller":
                return
            self.state = "connecting"
            peer = self.peer
            self._peer_vcap = bool(h.get("vcap"))   # 对端视频能力（R45）
            self._has_cam = (video_api.available() if CFG.hardware_enabled
                             else False)
        # 绑随机 UDP 端口并上报（服务器回填 ip 转给被叫）
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(("0.0.0.0", 0))
        port = udp.getsockname()[1]
        with self._lock:
            self._udp = udp
        self.core._send_frame({"t": M.CALL_READY.value, "to": int(peer),
                               "port": port,
                               "vcap": 1 if self._has_cam else 0})
        self._push("connecting", peer=peer, nick=self.peer_nick,
                   text="对方已接听，建立直连…")
        # 连通等待放后台线程（读线程阻塞会拖住心跳/其它信令）
        threading.Thread(target=self._start_audio, args=(udp,), daemon=True,
                         name="call-wait").start()

    def _on_reject(self, h: dict) -> None:
        with self._lock:
            if self.state not in ("ringing", "connecting") or self.role != "caller":
                return
            peer = self.peer
            self._reset()
        self._push("ended", peer=peer, text=h.get("reason") or "对方已拒绝")

    def _on_ready(self, h: dict) -> None:
        """被叫：拿主叫 ip/port → 起 UDP 打洞收发（连通确认放后台线程）。"""
        with self._lock:
            if self.state != "connecting" or self.role != "callee":
                return
            ip = str(h.get("ip") or "")
            port = int(h.get("port") or 0)
            peer = self.peer
            self._peer_vcap = bool(h.get("vcap"))   # 对端视频能力（R45）
        if not ip or not port:
            self._fail("信令缺少对端地址")
            return
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(("0.0.0.0", 0))
        with self._lock:
            self._udp = udp
            self._peer_addr = (ip, port)
        self._push("connecting", peer=peer, nick=self.peer_nick,
                   text="对方已就绪，建立直连…")
        # 连通等待放后台线程（与主叫同路径：超时明确报错，不留"假连通"）
        threading.Thread(target=self._start_audio, args=(udp,), daemon=True,
                         name="call-wait").start()

    def _on_end(self, h: dict) -> None:
        with self._lock:
            if self.state == "idle":
                return
            peer = self.peer
            self._reset()
        self._push("ended", peer=peer, text=h.get("reason") or "通话已结束")

    # ---------- 音频链路 ----------

    def _start_audio(self, udp: socket.socket) -> None:
        """主叫/被叫共用：起接收线程 + 探活线程；连通后进 incall（双方同路径）。"""
        self._stop.clear()
        self._connected.clear()
        if self._spk is None:
            self._spk = voice_api.SpkPlayer(on_error=lambda m: self._fail(m))
            if self._spk.start() is False:
                self._fail("无法打开扬声器（无可用输出设备）")
                return
        t1 = threading.Thread(target=self._recv_loop, args=(udp,), daemon=True,
                              name="call-recv")
        t2 = threading.Thread(target=self._probe_loop, daemon=True,
                              name="call-probe")
        self._threads = [t1, t2]
        t1.start()
        t2.start()
        deadline = time.time() + _PROBE_INTERVAL * _PROBE_COUNT
        if self._connected.wait(max(0.0, deadline - time.time())):
            with self._lock:
                self.state = "incall"
                self._started_at = time.time()
            self._apply_mic()             # R39A：全双工常开麦
            self._push("incall", peer=self.peer, nick=self.peer_nick,
                       text=self._incall_text())
        else:
            self._fail("UDP 直连失败（对方不可达），本期不支持服务器中转")
            self.end_call("直连失败")

    def _incall_text(self) -> str:
        """连通提示按模式区分（全双工提示戴耳机防回声）。"""
        return ("已连通，全双工通话（建议戴耳机）" if self._duplex
                else "已连通，按住说话")

    def _probe_loop(self) -> None:
        """探活：空载荷加密包定期外发（打洞 + 对端 connected 判定）。"""
        while not self._stop.is_set() and self.state in ("connecting", "incall"):
            self._send_packet(b"")
            if self._stop.wait(_PROBE_INTERVAL):
                return

    def _recv_loop(self, udp: socket.socket) -> None:
        udp.settimeout(0.2)
        while not self._stop.is_set():
            try:
                data, addr = udp.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                if not self._stop.is_set():
                    self._fail("语音链路中断（网络异常）")
                return
            with self._lock:
                first = not self._connected.is_set()
                self._peer_addr = addr          # 学习对端真实地址（打洞）
            if first:
                self._connected.set()
            if len(data) <= _NONCE_LEN + 16:
                continue                        # 探活包
            try:
                pcm = self._aead.decrypt(bytes(data[:_NONCE_LEN]),
                                         bytes(data[_NONCE_LEN:]), None)
            except Exception:
                continue
            if len(pcm) > _AUDIO_FRAME:
                # R45 视频分片（视频载荷下限 321B）：重组完整 PNG 后上抛
                png = self._reasm.feed(pcm)
                if png is not None:
                    self._push("video_frame", png=png)
                continue
            if self._spk is not None:
                self._spk.feed(pcm)

    def _send_loop(self) -> None:
        """开麦期间（全双工常开 / PTT 按住）：采集帧 → 加密 → sendto。"""
        mic = self._mic
        while not self._stop.is_set():
            with self._lock:
                if self.state != "incall" or not self._mic_up:
                    return
            try:
                pcm = mic.frames.get(timeout=0.2)
            except Exception:
                continue
            self._send_packet(pcm)

    def _send_packet(self, payload: bytes) -> None:
        with self._lock:
            udp, addr, aead = self._udp, self._peer_addr, self._aead
        if udp is None or addr is None or aead is None:
            return
        try:
            from os import urandom
            nonce = urandom(_NONCE_LEN)
            ct = aead.encrypt(nonce, bytes(payload), None)
            udp.sendto(nonce + ct, addr)
        except OSError:
            pass

    # ---------- 工具 ----------

    def _ensure_key(self, peer: int):
        """通话密钥 = 1v1 E2EE 会话密钥；未建立则自动握手。"""
        core = self.core
        if core.e2ee_ready(peer):
            return core.e2ee.session_key(peer)
        fp = core.start_e2ee(peer, timeout=6.0)
        if not fp:
            return None
        return core.e2ee.session_key(peer)

    def _reset(self) -> None:
        """清空全部通话资源（持锁调用或自持锁）。"""
        self.state = "idle"
        self.peer = None
        self.peer_nick = ""
        self.role = None
        self._key = None
        self._aead = None
        self._peer_addr = None
        self._connected.clear()
        self._stop.set()
        self._ptt = False
        self._mic_up = False
        self._started_at = 0.0
        udp, self._udp = self._udp, None
        if udp is not None:
            try:
                udp.close()
            except OSError:
                pass
        mic, self._mic = self._mic, None
        if mic is not None:
            mic.stop()
        spk, self._spk = self._spk, None
        if spk is not None:
            spk.stop()
        cam, self._cam = self._cam, None
        if cam is not None:
            cam.stop()
        self._video_on = False
        self._peer_vcap = False
        self._fid = 0
        self._reasm = video_api.Reassembler()   # 丢弃在途分片（fid 可能复用）
        self._threads = []

    def _fail(self, text: str) -> None:
        """链路级失败：清理 + 通知 + 挂断信令。"""
        with self._lock:
            if self.state == "idle":
                self._push("failed", text=text)
                return
            peer = self.peer
            self._reset()
        if peer is not None:
            self.core._send_frame({"t": M.CALL_END.value, "to": int(peer),
                                   "reason": text[:100]})
        self._push("failed", peer=peer, text=text)

    def _push(self, state: str, **kw) -> None:
        ev = {"t": "call", "state": state, "peer": self.peer,
              "nick": self.peer_nick}
        ev.update({k: v for k, v in kw.items() if v is not None})
        self.core._push(ev)
