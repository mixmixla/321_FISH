# -*- coding: utf-8 -*-
"""客户端文件传输编排（搭桥直连，失败自动回退服务器中转）：

流程（服务器只做"搭桥"）：
1. 发送方 send_file → FILE_OFFER（含 md5/size）→ 服务器转给接收方
2. 接收方 accept → 带断点位图 acked 回 FILE_ACCEPT → 服务器双向告知 IP
3. 发送方起临时监听 → FILE_LISTEN 上报端口 → 服务器 FILE_DIRECT 通知接收方
4. 接收方主动直连（client_handshake，发送方 server_handshake）→ direct_ready 确认
   - 直连建立：块数据与 ACK 全走直连套接字（同样 AES-GCM 加密，线上无明文）
   - 直连超时：回退服务器中转（块走 FILE_DATA 转发，ACK 走 FILE_CHUNK_ACK）
5. 全部块收齐 → 接收方校验 md5 → FILE_VERIFY → 双方收尾

断点续传：接收方按 (md5,size) 找旧 .meta.json/.part，acked 位图随 FILE_ACCEPT
带回，发送方跳过已确认块。.part 随机写支持乱序，每块落盘 + 周期性保存位图。
"""
import os
import socket
import threading
import time
import uuid

from config import CFG
from crypto import HandshakeError, client_handshake, server_handshake
from protocol import MsgType as M
from filexfer import (PartFile, TransferMeta, chunk_count, compute_md5,
                      load_meta, save_meta)

_TCP = socket.IPPROTO_TCP
_NODELAY = socket.TCP_NODELAY

# A7：图片消息——按扩展名识别，接收端自动收且完成后推 image 事件渲染缩略图
_IMG_EXT = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"})


def _is_image_filename(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in _IMG_EXT


def _hsize(n: int) -> str:
    if n >= 1 << 30:
        return f"{n / (1 << 30):.2f}GB"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f}MB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.0f}KB"
    return f"{n}B"


def _safe_name(name: str) -> str:
    return "".join(c for c in name if c not in '\\/:*?"<>|').strip() or "file"


def _unique_path(dir_path: str, name: str) -> str:
    """同目录同名自动加序号，避免覆盖"""
    base, ext = os.path.splitext(name)
    p = os.path.join(dir_path, name)
    i = 1
    while os.path.exists(p):
        p = os.path.join(dir_path, f"{base}({i}){ext}")
        i += 1
    return p


class _Xfer:
    """一次传输的本地状态（send/receive 通用）"""

    def __init__(self, fid: str, role: str, filename: str, size: int,
                 md5: str, chunk_size: int, to_uid: int | None) -> None:
        self.fid = fid
        self.role = role              # "send" | "receive"
        self.filename = filename
        self.size = size
        self.md5 = md5
        self.chunk_size = chunk_size
        self.to_uid = to_uid
        self.total = chunk_count(size, chunk_size)
        self.status = "offering"
        self.acked: set = set()
        self.direct_chan = None
        self.sender_ip = None
        self.port_event = threading.Event()
        self.direct_port = None
        self.result: bool | None = None
        self.done = threading.Event()
        self.stopped = threading.Event()
        self.cond = threading.Condition()
        self.part = None              # 接收端 PartFile
        self.part_path = None
        self.meta_path = None
        self.final_path = None
        self.path = None              # 发送端源文件
        self.from_nick = ""
        self.from_uid = None          # 接收端：发送方 uid（A7 图片消息定位用）
        self.caption = ""             # R32B3 图片说明文字（随 FILE_OFFER 透传）

    def ack(self, index: int) -> None:
        with self.cond:
            self.acked.add(index)
            self.cond.notify_all()

    def wait_ack(self, index: int, timeout: float) -> bool:
        with self.cond:
            self.cond.wait_for(lambda: index in self.acked or self.stopped.is_set(),
                               timeout=timeout)
            return index in self.acked

    def progress(self) -> float:
        return len(self.acked) / self.total if self.total else 1.0


class FileManager:
    """文件传输编排器（挂在 ClientCore.files 上，由 core 转发 FILE_* 帧）"""

    def __init__(self, core) -> None:
        self.core = core
        self._lock = threading.RLock()
        self.xfers: dict = {}

    # ---------- 对外 API ----------
    def send_file(self, path: str, to_uid: int, caption: str = "") -> str | None:
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            self._push({"t": "file_progress", "state": "failed",
                        "text": f"文件不存在: {path}"})
            return None
        fid = uuid.uuid4().hex[:16]
        threading.Thread(target=self._send_prepare,
                         args=(fid, path, to_uid, str(caption or "")[:2000]),
                         daemon=True).start()
        return fid

    def accept(self, fid: str, dest_dir: str | None = None) -> bool:
        with self._lock:
            x = self.xfers.get(fid)
            if not x or x.role != "receive" or x.status != "offering":
                return False
            x.status = "accepted"
        dest_dir = dest_dir or CFG.downloads_dir
        os.makedirs(dest_dir, exist_ok=True)
        x.filename = _safe_name(x.filename)     # 防御：拼路径前再净化一次（防其它入口污染）
        part_path = os.path.join(dest_dir, x.filename + ".part")
        meta_path = os.path.join(dest_dir, x.filename + ".part.meta.json")
        final_path = _unique_path(dest_dir, x.filename)
        acked = []
        old = load_meta(meta_path)
        if old and old.md5 == x.md5 and old.size == x.size:
            acked = old.acked          # 断点续传：位图带回发送方
        x.meta_path, x.part_path, x.final_path = meta_path, part_path, final_path
        x.part = PartFile(part_path, x.size, resume=bool(acked))
        x.acked = set(int(i) for i in acked)
        self._save_meta(x)
        self.core._send_frame({"t": M.FILE_ACCEPT.value, "file_id": fid,
                               "acked": sorted(x.acked)})
        # 若断点位图已满（上次已收齐但未确认）→ 直接校验收尾
        if x.acked == set(range(x.total)):
            threading.Thread(target=self._recv_finish, args=(x,), daemon=True).start()
        else:
            self._push({"t": "file_progress", "file_id": fid, "state": "accepted",
                        "text": f"已接受，等待发送方传输（续传 {len(x.acked)} 块）…"})
        return True

    def reject(self, fid: str) -> bool:
        with self._lock:
            self.xfers.pop(fid, None)
        self.core._send_frame({"t": M.FILE_REJECT.value, "file_id": fid})
        self._push({"t": "file_progress", "file_id": fid, "state": "rejected",
                    "text": "已拒绝文件"})
        return True

    def cancel(self, fid: str) -> None:
        with self._lock:
            x = self.xfers.get(fid)
            if not x:
                return
            x.stopped.set()
        self.core._send_frame({"t": M.FILE_CANCEL.value, "file_id": fid})

    def shutdown(self) -> None:
        """连接关闭时终止所有传输"""
        with self._lock:
            xs = list(self.xfers.values())
        for x in xs:
            x.stopped.set()
            self._close_direct(x)

    # ---------- 收帧路由（core.dispatch 调用） ----------
    def handle(self, t: str, h: dict, body: bytes = b"") -> None:
        fid = h.get("file_id", "")
        if t == M.FILE_OFFER.value:
            self._recv_on_offer(h)
        elif t == M.FILE_ACCEPT.value:
            with self._lock:
                x = self.xfers.get(fid)
            if x is None:
                return
            if x.role == "send":
                self._sender_on_accept(x, h)
            else:
                self._recv_on_accept(x, h)
        elif t == M.FILE_REJECT.value:
            with self._lock:
                x = self.xfers.get(fid)
            if x:
                self._fail(x, "对方拒绝了文件")
        elif t == M.FILE_DIRECT.value:
            with self._lock:
                x = self.xfers.get(fid)
                if x:
                    x.direct_port = int(h.get("port", 0))
                    x.port_event.set()
        elif t == M.FILE_CHUNK_ACK.value:
            with self._lock:
                x = self.xfers.get(fid)
            if x and x.role == "send":
                idx = int(h.get("index", -1))
                if idx >= 0:
                    x.ack(idx)
        elif t == M.FILE_VERIFY.value:
            with self._lock:
                x = self.xfers.get(fid)
            if x and x.role == "send":
                x.result = bool(h.get("ok"))
                x.done.set()
        elif t == M.FILE_DATA.value:
            self._recv_on_data(fid, int(h.get("index", -1)), body)
        elif t == M.FILE_CANCEL.value:
            with self._lock:
                x = self.xfers.get(fid)
                if x:
                    x.stopped.set()
                    self._close_direct(x)
            if x:
                self._fail(x, h.get("text") or "传输已取消")
        elif t == M.FILE_PROGRESS.value:
            self._push(h)                     # 服务器中转的"等待接受"提示

    # ---------- 发送侧 ----------
    def _send_prepare(self, fid: str, path: str, to_uid: int,
                      caption: str = "") -> None:
        try:
            size = os.path.getsize(path)
            self._push({"t": "file_progress", "file_id": fid, "state": "hashing",
                        "text": f"正在计算校验… {os.path.basename(path)}"})
            md5 = compute_md5(path, CFG.chunk_size)
        except OSError as exc:
            self._push({"t": "file_progress", "file_id": fid, "state": "failed",
                        "text": f"读取文件失败: {exc}"})
            return
        x = _Xfer(fid, "send", os.path.basename(path), size, md5,
                  CFG.chunk_size, to_uid)
        x.path = path
        x.caption = caption
        with self._lock:
            self.xfers[fid] = x
        self.core._send_frame({"t": M.FILE_OFFER.value, "file_id": fid,
                               "filename": x.filename, "size": x.size,
                               "md5": x.md5, "to": to_uid,
                               "caption": x.caption})
        self._push({"t": "file_progress", "file_id": fid, "state": "waiting",
                    "text": f"等待对方接受 {x.filename}（{_hsize(x.size)}）…"})

    def _sender_on_accept(self, x: _Xfer, h: dict) -> None:
        x.acked = set(int(i) for i in h.get("acked") or [])
        x.sender_ip = h.get("receiver_ip")
        if x.total == 0 or x.acked == set(range(x.total)):
            # 空文件 / 全量已确认 → 直接等 verify
            threading.Thread(target=self._sender_wait_verify, args=(x,),
                             daemon=True).start()
            return
        threading.Thread(target=self._sender_bridge, args=(x,), daemon=True).start()

    def _sender_bridge(self, x: _Xfer) -> None:
        """搭桥：先尝试直连，失败回退服务器中转"""
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("0.0.0.0", 0))
        listener.listen(1)                  # 只接一个直连（搭桥）
        port = listener.getsockname()[1]
        timeout = CFG.file_direct_timeout
        listener.settimeout(timeout)
        direct = None
        try:
            self.core._send_frame({"t": M.FILE_LISTEN.value,
                                   "file_id": x.fid, "port": port})
            print(f"[DBG][snd] listening fid={x.fid} port={port} t={time.time():.3f}",
                  flush=True)
            deadline = time.time() + timeout
            while time.time() < deadline and not x.stopped.is_set():
                listener.settimeout(max(0.05, deadline - time.time()))
                try:
                    conn, _ = listener.accept()
                except socket.timeout:
                    continue
                except OSError as exc:
                    print(f"[DBG][snd] listener error {exc}", flush=True)
                    break
                print(f"[DBG][snd] accepted conn from {conn.getpeername()} "
                      f"t={time.time():.3f}", flush=True)
                try:
                    conn.setsockopt(_TCP, _NODELAY, 1)
                    chan = server_handshake(conn)       # 发送方扮演服务器
                    h, _b = chan.recv_frame()
                    if h.get("t") == "direct_ready":
                        direct = chan
                        break
                    conn.close()
                except (HandshakeError, OSError, ValueError) as exc:
                    print(f"[DBG][snd] handshake fail {exc}", flush=True)
                    try:
                        conn.close()
                    except OSError:
                        pass
        finally:
            print(f"[DBG][snd] listener closed fid={x.fid} "
                  f"t={time.time():.3f}", flush=True)
            listener.close()
        if direct is not None and not x.stopped.is_set():
            x.direct_chan = direct
            self.core._send_frame({"t": M.FILE_DIRECT_OK.value, "file_id": x.fid})
            self._push({"t": "file_progress", "file_id": x.fid, "state": "direct",
                        "text": f"已与对方直连，高速传输中"})
            threading.Thread(target=self._direct_reader, args=(x,), daemon=True).start()
            self._send_pump(x, direct=True)
        else:
            self._push({"t": "file_progress", "file_id": x.fid, "state": "relay",
                        "text": "直连不可达，回退服务器中转"})
            self._send_pump(x, direct=False)

    def _send_pump(self, x: _Xfer, direct: bool) -> None:
        chan = x.direct_chan if direct else None
        try:
            with open(x.path, "rb") as f:
                for i in range(x.total):
                    if x.stopped.is_set():
                        self.core._send_frame({"t": M.FILE_CANCEL.value,
                                               "file_id": x.fid})
                        return
                    if i in x.acked:
                        continue
                    f.seek(i * x.chunk_size)
                    data = f.read(x.chunk_size)
                    sent = False
                    for _ in range(CFG.file_max_retry + 1):
                        if x.stopped.is_set():
                            return
                        if direct:
                            if chan is None:
                                direct, chan = self._fallback_to_relay(x)
                            else:
                                try:
                                    chan.send_frame({"t": M.FILE_DATA.value,
                                                     "file_id": x.fid, "index": i},
                                                    data)
                                except OSError:
                                    # 直连中断 → 回退服务器中转续传剩余块
                                    direct, chan = self._fallback_to_relay(x)
                        if not direct:
                            self.core._send_frame({"t": M.FILE_DATA.value,
                                                   "file_id": x.fid, "index": i},
                                                  data)
                        if x.wait_ack(i, CFG.file_ack_timeout):
                            sent = True
                            break
                    if not sent:
                        self._fail(x, "发送超时，块未确认")
                        return
                    self._progress(x, "sending")
            self._push({"t": "file_progress", "file_id": x.fid, "state": "sending",
                        "text": f"全部块已发送，等待校验…"})
            self._sender_wait_verify(x)
        except OSError as exc:
            self._fail(x, f"传输中断: {exc}")
        finally:
            self._close_direct(x)

    def _fallback_to_relay(self, x: _Xfer) -> tuple:
        """直连中断：关直连通道转服务器中转续传；返回 (direct=False, chan=None)"""
        self._close_direct(x)
        self._push({"t": "file_progress", "file_id": x.fid, "state": "relay",
                    "text": "直连中断，回退服务器中转续传"})
        return False, None

    def _sender_wait_verify(self, x: _Xfer) -> None:
        while not x.done.wait(CFG.file_ack_timeout * 2):
            if x.stopped.is_set() or self.core._chan is None:
                return
        if x.result:
            self._finish(x, "done", f"文件已送达: {x.filename}")
        else:
            self._finish(x, "failed", f"对方校验失败: {x.filename}")

    def _direct_reader(self, x: _Xfer) -> None:
        """直连通道上的 ACK / VERIFY 读取（发送方视角）"""
        try:
            while not x.stopped.is_set():
                h, _b = x.direct_chan.recv_frame()
                t = h.get("t")
                if t == M.FILE_CHUNK_ACK.value and h.get("file_id") == x.fid:
                    x.ack(int(h.get("index")))
                elif t == M.FILE_VERIFY.value and h.get("file_id") == x.fid:
                    x.result = bool(h.get("ok"))
                    x.done.set()
                    return
                elif t == M.FILE_CANCEL.value:
                    x.result = False
                    x.done.set()
                    return
        except Exception:
            # 直连意外断开：不直接判失败（可能回退中转续传，最终结果以中转 VERIFY 为准），
            # 仅关闭通道让 _send_pump 的 send 尽快感知并回退中转
            if not x.stopped.is_set() and x.direct_chan is not None:
                try:
                    x.direct_chan.sock.close()
                except OSError:
                    pass
                x.direct_chan = None

    # ---------- 接收侧 ----------
    def _recv_on_offer(self, h: dict) -> None:
        fid = h["file_id"]
        # 防路径穿越：对端发来的文件名不可信，先净化（去掉 / \ : * ? " < > | 及盘符）
        name = _safe_name(str(h.get("filename") or ""))
        size = int(h["size"])
        if size <= 0 or size > CFG.file_max_size:
            # 超大/非法 offer 直接拒绝，不落盘（防磁盘撑爆）
            self.core._send_frame({"t": M.FILE_REJECT.value, "file_id": fid})
            self._push({"t": M.FILE_OFFER.value, "file_id": fid,
                        "filename": name, "size": size,
                        "from_uid": h.get("from_uid"), "from_nick": h.get("from_nick", ""),
                        "state": "rejected",
                        "text": f"文件过大（{_hsize(size)}），已自动拒绝"})
            return
        x = _Xfer(fid, "receive", name, size, h["md5"],
                  CFG.chunk_size, None)
        x.from_nick = h.get("from_nick", "")
        x.from_uid = h.get("from_uid")
        x.caption = str(h.get("caption") or "")[:2000]   # R32B3 图片说明文字
        with self._lock:
            self.xfers[fid] = x
        if _is_image_filename(x.filename):
            # A7 图片：免确认自动接收（缩略图消息渲染，不留保存弹窗）
            if not self.accept(fid):
                with self._lock:
                    self.xfers.pop(fid, None)
            return
        self._push({"t": M.FILE_OFFER.value, "file_id": fid,
                    "filename": x.filename, "size": x.size,
                    "from_uid": h.get("from_uid"), "from_nick": x.from_nick,
                    "text": f"{x.from_nick} 发来文件 {x.filename}（{_hsize(x.size)}）"})

    def _recv_on_accept(self, x: _Xfer, h: dict) -> None:
        x.sender_ip = h.get("sender_ip")
        x.port_event.clear()
        threading.Thread(target=self._recv_bridge, args=(x,), daemon=True).start()

    def _recv_bridge(self, x: _Xfer) -> None:
        """接收方搭桥：等 FILE_DIRECT 端口 → 直连；超时回退中转"""
        timeout = CFG.file_direct_timeout + 1.0
        if not x.port_event.wait(timeout) or x.stopped.is_set():
            print(f"[DBG][rcv] port_event timeout fid={x.fid} direct_port={x.direct_port}",
                  flush=True)
            self._push({"t": "file_progress", "file_id": x.fid, "state": "relay",
                        "text": "直连不可达，走服务器中转"})
            return
        if x.direct_port is None or x.stopped.is_set():
            return
        print(f"[DBG][rcv] port_event set fid={x.fid} port={x.direct_port} "
              f"t={time.time():.3f}", flush=True)
        try:
            sock = socket.create_connection((x.sender_ip, x.direct_port),
                                            timeout=CFG.file_direct_timeout)
            sock.setsockopt(_TCP, _NODELAY, 1)
            chan = client_handshake(sock)           # 接收方扮演客户端
            chan.send_frame({"t": "direct_ready"})
        except (OSError, HandshakeError) as exc:
            print(f"[DBG][rcv] direct connect fail fid={x.fid} "
                  f"ip={x.sender_ip} port={x.direct_port} err={exc}", flush=True)
            self._push({"t": "file_progress", "file_id": x.fid, "state": "relay",
                        "text": "直连不可达，走服务器中转"})
            return
        x.direct_chan = chan
        self._push({"t": "file_progress", "file_id": x.fid, "state": "direct",
                    "text": "已与对方直连"})
        try:
            while not x.stopped.is_set():
                h, body = chan.recv_frame()
                t = h.get("t")
                if t == M.FILE_DATA.value and h.get("file_id") == x.fid:
                    self._recv_chunk(x, int(h.get("index")), body, via_direct=True)
                elif t == M.FILE_CANCEL.value:
                    break
        except Exception:
            pass
        finally:
            self._close_direct(x)
            self._maybe_relay_after_direct_drop(x)

    def _maybe_relay_after_direct_drop(self, x: _Xfer) -> None:
        """直连中断且未收齐 → 允许服务器中转块继续补全"""
        if x.status not in ("done", "failed", "cancelled"):
            x.direct_chan = None
            self._push({"t": "file_progress", "file_id": x.fid, "state": "relay",
                        "text": "直连中断，回退服务器中转续传"})

    def _recv_on_data(self, fid: str, index: int, body: bytes) -> None:
        with self._lock:
            x = self.xfers.get(fid)
            if not x or x.role != "receive":
                return
            via_direct = x.direct_chan is not None
        self._recv_chunk(x, index, body, via_direct=via_direct)

    def _recv_chunk(self, x: _Xfer, index: int, body: bytes, via_direct: bool) -> None:
        # 越界块 / 超长块一律拒绝：防止恶意发送方把 .part 撑爆磁盘
        if index < 0 or index >= x.total or x.stopped.is_set() or index in x.acked:
            return
        if len(body) > x.chunk_size:
            self._fail(x, "收到超长数据块，传输已终止")
            return
        try:
            x.part.write_chunk(index, body, x.chunk_size)
        except ValueError as exc:
            self._fail(x, f"数据块校验失败: {exc}")
            return
        x.ack(index)
        if via_direct and x.direct_chan is not None:
            try:
                x.direct_chan.send_frame({"t": M.FILE_CHUNK_ACK.value,
                                          "file_id": x.fid, "index": index})
            except OSError:
                pass
        else:
            self.core._send_frame({"t": M.FILE_CHUNK_ACK.value,
                                   "file_id": x.fid, "index": index})
        if len(x.acked) % 25 == 0:
            self._save_meta(x)
        self._progress(x, "receiving")
        if x.acked == set(range(x.total)):
            threading.Thread(target=self._recv_finish, args=(x,), daemon=True).start()

    def _recv_finish(self, x: _Xfer) -> None:
        if x.status in ("done", "failed", "cancelled"):
            return
        try:
            ok = x.part.verify(x.md5, x.chunk_size)
            if ok:
                x.part.close()
                os.replace(x.part_path, x.final_path)
                if os.path.exists(x.meta_path):
                    os.remove(x.meta_path)
                x.status = "done"
                self._send_verify(x, True)
                self._finish(x, "done",
                             f"文件已保存: {os.path.basename(x.final_path)}")
            else:
                self._fail(x, "文件校验失败，请重发")
        except OSError as exc:
            self._fail(x, f"保存失败: {exc}")

    def _send_verify(self, x: _Xfer, ok: bool) -> None:
        """发校验结果：优先直连，失败/已断则走服务器中转（保证发送方一定收到）"""
        if x.direct_chan is not None:
            try:
                x.direct_chan.send_frame({"t": M.FILE_VERIFY.value,
                                          "file_id": x.fid, "ok": ok})
                return
            except OSError:
                self._close_direct(x)
        self.core._send_frame({"t": M.FILE_VERIFY.value, "file_id": x.fid, "ok": ok})

    # ---------- 统一收尾 ----------
    def _finish(self, x: _Xfer, state: str, text: str) -> None:
        if state == "done" and x.role == "receive" and _is_image_filename(x.filename):
            # A7 图片收齐落盘：推 image 事件让 GUI 在当前私聊会话渲染缩略图
            self.core._push({
                "t": "image", "channel": "private",
                "uid": x.from_uid, "to": self.core.uid,
                "nick": x.from_nick or "?", "file_id": x.fid,
                "image_path": x.final_path, "ts": time.time(),
                "text": x.caption,             # R32B3 图片说明文字
            })
        with self._lock:
            self.xfers.pop(x.fid, None)
        self._progress(x, state, text)

    def _fail(self, x: _Xfer, text: str) -> None:
        x.status = "failed"
        self._push({"t": "file_progress", "file_id": x.fid, "state": "failed",
                    "text": text})
        self._finish(x, "failed", text)

    def _progress(self, x: _Xfer, state: str, text: str | None = None) -> None:
        done = len(x.acked) * x.chunk_size
        if done > x.size:
            done = x.size
        self._push({"t": "file_progress", "file_id": x.fid, "state": state,
                    "filename": x.filename, "done": done, "total": x.size,
                    "role": x.role,
                    "path": (x.final_path or x.path) if state == "done" else None,
                    "pct": int(x.progress() * 100),
                    "text": text or f"{x.filename} {x.progress() * 100:.0f}%"})

    def _save_meta(self, x: _Xfer) -> None:
        try:
            save_meta(x.meta_path, TransferMeta(
                file_id=x.fid, filename=x.filename, size=x.size,
                chunk_size=x.chunk_size, md5=x.md5,
                sender_uid=0, receiver_uid=0, acked=sorted(x.acked)))
        except OSError:
            pass

    def _close_direct(self, x: _Xfer) -> None:
        chan = x.direct_chan
        if chan is not None:
            try:
                chan.sock.close()
            except OSError:
                pass
            x.direct_chan = None

    def _push(self, ev: dict) -> None:
        # 只要事件带 file_id 且该传输尚存活，就注入机器可读的名/大小，
        # 供 GUI 文件卡片（T1）统一使用，无需逐个调用点手工带字段。
        if ev.get("file_id"):
            with self._lock:
                x = self.xfers.get(ev["file_id"])
                if x:
                    ev.setdefault("name", x.filename)
                    ev.setdefault("size", x.size)
        self.core._push(ev)
