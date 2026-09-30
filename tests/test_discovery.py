# -*- coding: utf-8 -*-
"""阶段3 UDP 自动发现：封包/解包 + 真实 UDP 广播/监听（127.0.0.1）"""
import socket
import threading
import time
from dataclasses import replace

from config import CFG
import discovery


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_packet_roundtrip():
    pkt = discovery._packet("内部办公助手", 9527)
    info = discovery.parse_packet(pkt)
    assert info == {"name": "内部办公助手", "port": 9527}


def test_parse_rejects_foreign_magic():
    assert discovery.parse_packet(b"hello world this is a long packet!!") is None
    assert discovery.parse_packet(b"") is None
    assert discovery.parse_packet(b"\x00" * 5) is None


def test_client_receives_broadcast():
    """同进程：监听器 bind 回环端口，模拟服务器广播 sendto，验证
    解包/候选收集/TTL 过期淘汰全链路。"""
    udp_port = _free_port()
    tcp_port = _free_port()
    cfg = replace(CFG, udp_port=udp_port, tcp_port=tcp_port,
                  udp_candidate_ttl=2.0)
    cli = discovery.DiscoveryClient(cfg)
    cli.start()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        pkt = discovery._packet("内部办公助手", tcp_port)
        for _ in range(2):
            s.sendto(pkt, ("127.0.0.1", udp_port))
            time.sleep(0.15)
        s.close()
        deadline = time.time() + 3.0
        cands = []
        while time.time() < deadline:
            cands = cli.candidates()
            if cands:
                break
            time.sleep(0.05)
        assert cands, "应收到至少一个候选"
        ip, name, port = cands[0]
        assert ip == "127.0.0.1"
        assert name == "内部办公助手"
        assert port == tcp_port
        # TTL 过期后自动淘汰
        time.sleep(2.2)
        assert cli.candidates() == []
    finally:
        cli.stop.set()


def test_broadcaster_runs_and_stops():
    udp_port = _free_port()
    cfg = replace(CFG, udp_port=udp_port, udp_broadcast_interval=0.05)
    stop = threading.Event()
    b = discovery.DiscoveryBroadcaster(cfg, name="srv", stop=stop)
    b.start()
    time.sleep(0.3)
    assert b._thread is not None and b._thread.is_alive()
    stop.set()
    time.sleep(0.3)
    assert not b._thread.is_alive()
