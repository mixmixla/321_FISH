# -*- coding: utf-8 -*-
"""discovery.py —— UDP 自动发现（阶段3）。

- 服务器侧：每 udp_broadcast_interval 秒向 255.255.255.255:udp_port 广播
  [magic(8B) + tcp_port(4B) + 服务器名]。
- 客户端侧：bind 同一端口监听，校验 magic 后维护候选表
  {ip -> (name, port, seen)}，TTL 过期自动淘汰。
- magic 用无意义常量（防行为管理关键词特征匹配）；被防火墙拦广播时
  客户端收不到 → 界面「设置」面板可手填/手选候选，或 CLI --host 兜底。
"""
import socket
import threading
import time

# 无意义常量：不与"摸鱼/聊天/moyu"等字样沾边，避免被特征扫描命中
MAGIC = b"\xa5\xf1\x9b\x3c\x5e\x2d\xc8\x77"
MAGIC_LEN = len(MAGIC)          # 8
PORT_BYTES = 4


def _packet(name: str, tcp_port: int) -> bytes:
    """封包：magic + tcp_port(4B big-endian) + 服务器名(utf-8)"""
    return (MAGIC + int(tcp_port).to_bytes(PORT_BYTES, "big")
            + name.encode("utf-8", "replace"))


def parse_packet(data: bytes) -> dict | None:
    """解包；非本 magic 或长度不足返回 None"""
    if not data or len(data) < MAGIC_LEN + PORT_BYTES:
        return None
    if not data.startswith(MAGIC):
        return None
    port = int.from_bytes(data[MAGIC_LEN:MAGIC_LEN + PORT_BYTES], "big")
    name = data[MAGIC_LEN + PORT_BYTES:].decode("utf-8", "replace") or "服务器"
    return {"port": port, "name": name}


class DiscoveryBroadcaster:
    """服务器侧周期广播（守护线程；stop 事件退出）"""

    def __init__(self, cfg, name: str = "", stop: threading.Event | None = None):
        self.cfg = cfg
        self.name = name or "服务器"
        self.stop = stop or threading.Event()
        self._thread = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="disco-bcast")
        self._thread.start()

    def _run(self) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.settimeout(0.5)
            packet = _packet(self.name, self.cfg.tcp_port)
            addr = ("255.255.255.255", self.cfg.udp_port)
            while not self.stop.wait(self.cfg.udp_broadcast_interval):
                try:
                    s.sendto(packet, addr)
                except OSError:
                    break          # 网络异常（无网卡等）→ 安静退出
        finally:
            try:
                s.close()
            except OSError:
                pass


class DiscoveryClient:
    """客户端侧监听广播；candidates() 返回未过期候选（最近者在前）"""

    def __init__(self, cfg, stop: threading.Event | None = None):
        self.cfg = cfg
        self.stop = stop or threading.Event()
        self._cands: dict = {}
        self._lock = threading.Lock()
        self._thread = None
        self._failed = False          # 端口被占/无网卡 → 监听失败标记

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="disco-listen")
        self._thread.start()

    def _run(self) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", self.cfg.udp_port))
        except OSError:
            # 端口被占（本机可能同时跑服务器广播）→ 不阻塞，标记后退出
            self._failed = True
            try:
                s.close()
            except OSError:
                pass
            return
        s.settimeout(0.5)
        try:
            while not self.stop.wait(0.1):
                try:
                    data, addr = s.recvfrom(1024)
                except socket.timeout:
                    continue
                except OSError:
                    break
                info = parse_packet(data)
                if info is None:
                    continue
                with self._lock:
                    self._cands[addr[0]] = {"name": info["name"],
                                            "port": info["port"],
                                            "seen": time.time()}
        finally:
            try:
                s.close()
            except OSError:
                pass

    def candidates(self) -> list:
        """未过期候选列表：[(ip, name, port), ...] 最近看到者在前"""
        now = time.time()
        with self._lock:
            keep = {k: v for k, v in self._cands.items()
                    if now - v["seen"] < self.cfg.udp_candidate_ttl}
            self._cands = keep
            items = [(ip, v["name"], v["port"]) for ip, v in keep.items()]
        items.sort(key=lambda x: -keep[x[0]]["seen"])
        return items
