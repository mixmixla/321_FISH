# -*- coding: utf-8 -*-
"""加密层单测：往返加解密 / 篡改必 fail / 双端密钥一致 / 握手 / 重放拒绝"""
import socket
import struct
import threading

import pytest

import crypto
from protocol import MsgType


def test_roundtrip_encrypt_decrypt():
    s1, s2 = socket.socketpair()
    try:
        ch = crypto.CryptoChannel(s1, b"k" * 32, b"j" * 32, role="client")
        ch.send_frame({"t": MsgType.CHAT.value, "text": "密文测试"}, b"\x01\x02")
        ch2 = crypto.CryptoChannel(s2, b"k" * 32, b"j" * 32, role="server")
        header, body = ch2.recv_frame()
        assert header["t"] == "chat" and body == b"\x01\x02"
    finally:
        s1.close(); s2.close()


def test_tampered_frame_rejected():
    """篡改密文后 GCM tag 校验必须失败"""
    s1, s2 = socket.socketpair()
    try:
        c2s, s2c = b"k" * 32, b"j" * 32
        client_ch = crypto.CryptoChannel(s1, c2s, s2c, role="client")
        server_ch = crypto.CryptoChannel(s2, c2s, s2c, role="server")
        client_ch.send_frame({"t": "ping"})
        raw = _read_packet(s2, server_ch)      # 从服务器侧读到原始密文包
        tampered = raw[:-1] + bytes([raw[-1] ^ 0xFF])
        s1.sendall(struct.pack(">I", len(tampered)) + tampered)  # 篡改后塞回链路
        with pytest.raises(Exception):
            server_ch.recv_frame()
    finally:
        s1.close(); s2.close()


def test_wire_has_no_plaintext():
    """握手后发送中文聊天帧，线上字节必须是随机密文（不含明文子串）"""
    s1, s2 = socket.socketpair()
    try:
        c = crypto.CryptoChannel(s1, b"k" * 32, b"j" * 32, role="client")
        plain = "上班摸鱼秘密暗号".encode()
        c.send_frame({"t": "chat", "text": "上班摸鱼秘密暗号"}, plain)
        raw = s2.recv(4096)
        assert b"chat" not in raw
        assert "上班摸鱼秘密暗号".encode() not in raw
    finally:
        s1.close(); s2.close()


def test_full_handshake_both_sides():
    """真实 socketpair 上跑完整握手，双端能互发互收"""
    s1, s2 = socket.socketpair()
    results = {}

    def server():
        ch = crypto.server_handshake(s2)
        results["server"] = ch
        ch.send_frame({"t": "welcome", "uid": 1})
        h, b = ch.recv_frame()
        results["server_h"] = h

    t = threading.Thread(target=server, daemon=True)
    t.start()
    ch_client = crypto.client_handshake(s1)
    h, b = ch_client.recv_frame()
    assert h["uid"] == 1
    ch_client.send_frame({"t": MsgType.HELLO.value, "nick": "测试员"})
    t.join(timeout=3)
    assert results["server_h"]["t"] == "hello"


def test_replay_nonce_rejected():
    """重放已用过的 nonce（同计数器帧）必须被拒绝"""
    s1, s2 = socket.socketpair()
    try:
        c2s, s2c = b"k" * 32, b"j" * 32
        client_ch = crypto.CryptoChannel(s1, c2s, s2c, role="client")
        server_ch = crypto.CryptoChannel(s2, c2s, s2c, role="server")
        client_ch.send_frame({"t": "ping"})
        packet = _read_packet(s2, server_ch)        # 取出原始密文包
        s1.sendall(struct.pack(">I", len(packet)) + packet)  # 原样回放一次（合法）
        server_ch.recv_frame()                      # 正常消费，recv_counter=0
        s1.sendall(struct.pack(">I", len(packet)) + packet)  # 再次回放同一帧
        with pytest.raises(Exception):
            server_ch.recv_frame()
    finally:
        s1.close(); s2.close()


def _read_packet(sock, ch):
    import struct
    ln = sock.recv(4)
    assert len(ln) == 4
    return sock.recv(struct.unpack(">I", ln)[0])
