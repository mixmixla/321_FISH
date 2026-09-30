# -*- coding: utf-8 -*-
"""私密加密层：X25519 握手 + HKDF-SHA256 + AES-256-GCM 逐帧加密。

线上形态（TCP 连接建立后）：
    [64B 随机混淆前缀]
    [32B client X25519 pub] [32B server X25519 pub]
    -> 之后所有字节为加密帧：
    [4B uint32 密文长度][12B nonce][AES-256-GCM 密文 + 16B tag]

安全属性：
- 全程线上无明文（含文件块二进制）
- 双向独立密钥 + 单调递增 nonce（防重放/防计数器复用）
- 随机混淆前缀模仿 MTProto obfuscated2，DPI 只见随机字节
- JSON 头按 256B 对齐补随机填充，消去帧长指纹

诚实边界：hub 服务器（用户自己的机器）可解密中转 —— 相当于 Telegram
「云聊天」安全级；Secret Chat 级 E2EE 不在本期（见 README「加密与防识别」）。
"""
import hashlib
import os
import struct
import threading

from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from config import CFG, OBFUSCATE_PREFIX_LEN, PAD_TO

_C2S = b"cs01"   # client->server nonce 方向标识
_S2C = b"sc01"   # server->client nonce 方向标识
_NONCE_LEN = 12
_TAG_LEN = 16
_INFO = b"moeyu-helper/v1"


class HandshakeError(Exception):
    """握手失败"""


def _recv_exact(sock, n: int) -> bytes:
    chunks = []
    remain = n
    while remain > 0:
        data = sock.recv(remain)
        if not data:
            raise HandshakeError("connection closed during handshake")
        chunks.append(data)
        remain -= len(data)
    return b"".join(chunks)


def _hkdf(shared: bytes) -> tuple:
    """共享密钥 -> 双向 AES-256-GCM key"""
    material = HKDF(algorithm=hashes.SHA256(), length=64, salt=b"moeyu-hkdf-v1",
                    info=_INFO).derive(shared)
    return material[:32], material[32:]  # (c2s_key, s2c_key)


def client_handshake(sock) -> "CryptoChannel":
    """客户端侧握手：发混淆前缀 + 公钥，收服务器公钥。"""
    prefix = os.urandom(OBFUSCATE_PREFIX_LEN)
    priv = x25519.X25519PrivateKey.generate()
    sock.sendall(prefix)
    sock.sendall(priv.public_key().public_bytes_raw())
    server_pub = x25519.X25519PublicKey.from_public_bytes(_recv_exact(sock, 32))
    shared = priv.exchange(server_pub)
    c2s, s2c = _hkdf(shared)
    return CryptoChannel(sock, c2s, s2c, role="client")


def server_handshake(sock) -> "CryptoChannel":
    """服务器侧握手：读混淆前缀 + 公钥，回公钥。"""
    _recv_exact(sock, OBFUSCATE_PREFIX_LEN)  # 混淆前缀只读不用
    client_pub = x25519.X25519PublicKey.from_public_bytes(_recv_exact(sock, 32))
    priv = x25519.X25519PrivateKey.generate()
    sock.sendall(priv.public_key().public_bytes_raw())
    shared = priv.exchange(client_pub)
    c2s, s2c = _hkdf(shared)
    return CryptoChannel(sock, c2s, s2c, role="server")


def _pad_header(header: dict, body_len: int) -> dict:
    """随机填充 JSON 头，使最终帧长（4+hlen+body_len）为 PAD_TO 整数倍（消帧长指纹）。

    填充字段 "p" 用 hex（纯 [0-9a-f]，JSON 无转义，长度恒为偶数），键值对附加开销
    为 7+2x 字节（奇数）。当基础帧长为偶数时无解，额外挂一个空字段 "q"（开销 7）
    凑成偶数开销，从而总能精确对齐到 PAD_TO 的整数倍。
    """
    import json as _json
    base = dict(header)
    base.pop("p", None)
    base.pop("q", None)
    base["body_len"] = body_len        # encode_frame 会注入该字段，必须计入
    base_len = len(_json.dumps(base, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    total = 4 + base_len + body_len
    if total % 2 == 1:                       # 7+2x（奇数）→ 总和为偶，可直接对齐
        need = (PAD_TO - (total + 7) % PAD_TO) % PAD_TO
        base["p"] = os.urandom(need // 2).hex()
    else:                                    # 基础帧长为偶 → 再挂空 "q"（开销 7）
        need = (PAD_TO - (total + 14) % PAD_TO) % PAD_TO
        base["p"] = os.urandom(need // 2).hex()
        base["q"] = ""
    return base


class CryptoChannel:
    """加密通道：封装 socket 的加密收发。frame 为 protocol.encode_frame 产物。

    role='client'：发用 c2s key，收用 s2c key
    role='server'：发用 s2c key，收用 c2s key
    """

    def __init__(self, sock, c2s_key: bytes, s2c_key: bytes, role: str) -> None:
        self.sock = sock
        self.role = role
        self._c2s = AESGCM(c2s_key)
        self._s2c = AESGCM(s2c_key)
        self._send_counter = 0
        self._recv_counter = -1   # 重放防护：收到的 nonce 计数必须严格递增
        self._send_lock = threading.Lock()   # 并发 send（本连接读线程 + 其他连接的上线/广播推送线程）锁发送

    # ---- 加密/解密（按角色取方向）----
    def _tx_key(self):
        return self._s2c if self.role == "server" else self._c2s

    def _rx_key(self):
        return self._c2s if self.role == "server" else self._s2c

    def _encrypt(self, plain: bytes) -> bytes:
        nonce = self._tx_dir() + struct.pack(">Q", self._send_counter)
        self._send_counter += 1
        return nonce + self._tx_key().encrypt(nonce, plain, None)  # nonce 前置

    def _decrypt(self, nonce: bytes, ciphertext: bytes) -> bytes:
        counter = struct.unpack(">Q", nonce[4:])[0]
        if nonce[:4] != self._rx_dir():
            raise ValueError("wrong direction nonce")
        if counter <= self._recv_counter:
            raise ValueError("nonce reuse / replay rejected")
        self._recv_counter = counter
        return self._rx_key().decrypt(nonce, ciphertext, None)  # 篡改 -> InvalidTag

    def _tx_dir(self) -> bytes:
        return _S2C if self.role == "server" else _C2S

    def _rx_dir(self) -> bytes:
        return _C2S if self.role == "server" else _S2C

    def send_frame(self, header: dict, body: bytes = b"") -> None:
        """发送一帧（自动补填充并加密）。header 来自 protocol 语义。

        发送全程加锁：服务器可能从多条线程（本连接读循环、其他连接触发的
        上线/广播推送）并发向同一 channel 写帧，若不锁会造成 nonce 乱序，
        接收端按「严格递增」校验会误判为重放而断连。
        """
        with self._send_lock:
            from protocol import encode_frame
            h = _pad_header(header, len(body))
            plain = encode_frame(h, body)
            ct = self._encrypt(plain)      # 计数递增与加密在锁内，保证帧序=nonce序
            self.sock.sendall(struct.pack(">I", len(ct)) + ct)

    def recv_frame(self, max_len: int = CFG.max_body_bytes + 64 * 1024):
        """接收并解密一帧，返回 (header, body)。socket 关闭/坏 tag 抛异常。"""
        from protocol import FrameReader, ProtocolError
        length = _recv_exact(self.sock, 4)
        ct_len = struct.unpack(">I", length)[0]
        if ct_len <= 0 or ct_len > max_len + _TAG_LEN + 12:
            raise ProtocolError(f"bad encrypted frame length: {ct_len}")
        packet = _recv_exact(self.sock, ct_len)
        nonce, ct = packet[:12], packet[12:]
        plain = self._decrypt(nonce, ct)
        reader = FrameReader()
        frames = reader.feed(plain)
        if not frames:
            raise ProtocolError("empty frame after decrypt")
        return frames[0]

    def send_padding(self) -> None:
        """伪装流量：发送空填充帧（维持空闲流量形态）。"""
        from protocol import MsgType
        self.send_frame({"t": MsgType.PADDING.value})

    # ---- 校验辅助 ----
    def authenticate(self, key: bytes, msg: bytes, tag: bytes) -> bool:
        """HMAC 验签（供扩展：握手完整性校验）"""
        h = hmac.HMAC(key, hashes.SHA256())
        h.update(msg)
        try:
            h.verify(tag)
            return True
        except Exception:
            return False
