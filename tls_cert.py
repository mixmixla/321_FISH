# -*- coding: utf-8 -*-
"""网页端 HTTPS 自签证书（纯标准库，零第三方依赖）。

P0 安全加固（竞品审计 §2.4）：网页端原为明文 HTTP，本模块提供无依赖的
自签 TLS 证书生成——RSA-2048 密钥对（Miller-Rabin 素性检测）+ 最小
X.509 v3 DER 编码（SHA256withRSAEncryption 自签），PEM 落盘缓存，
证书 SAN 含本机全部 IPv4 + localhost/主机名，有效期 10 年。

ensure_cert(cert_dir) → (cert_path, key_path)：目录下已有一对可用证书
（能被 ssl.load_cert_chain 配对加载）则直接复用，否则生成新的一对。
生成约需 1~3 秒（纯 Python 素数搜索），仅首次启动发生。
"""
import base64
import datetime
import hashlib
import ipaddress
import math
import os
import secrets
import socket
import ssl
import threading

_LOCK = threading.Lock()

# OID（DER 内容字节由 _oid() 编码）
OID_RSA_ENCRYPTION = (1, 2, 840, 113549, 1, 1, 1)
OID_SHA256_RSA = (1, 2, 840, 113549, 1, 1, 11)
OID_CN = (2, 5, 4, 3)
OID_SHA256 = (2, 16, 840, 1, 101, 3, 4, 2, 1)
OID_BASIC_CONSTRAINTS = (2, 5, 29, 19)
OID_SUBJECT_ALT_NAME = (2, 5, 29, 17)

# ---------------------------------------------------------------- DER 基元

def _der(tag: int, payload: bytes) -> bytes:
    n = len(payload)
    if n < 0x80:
        length = bytes([n])
    elif n < 0x100:
        length = b"\x81" + bytes([n])
    else:
        length = b"\x82" + n.to_bytes(2, "big")
    return bytes([tag]) + length + payload


def _seq(*parts: bytes) -> bytes:
    return _der(0x30, b"".join(parts))


def _int(n: int) -> bytes:
    """正整数（自动补前导 0 保证非负）"""
    return _der(0x02, n.to_bytes(max(1, n.bit_length() // 8 + 1), "big"))


def _bitstr(b: bytes) -> bytes:
    return _der(0x03, b"\x00" + b)


def _octet(b: bytes) -> bytes:
    return _der(0x04, b)


def _null() -> bytes:
    return _der(0x05, b"")


def _oid(*arcs: int) -> bytes:
    out = bytearray([40 * arcs[0] + arcs[1]])
    for a in arcs[2:]:
        tmp = bytearray([a & 0x7F])
        a >>= 7
        while a:
            tmp.append(0x80 | (a & 0x7F))
            a >>= 7
        out += bytes(reversed(tmp))
    return _der(0x06, bytes(out))


def _utf8(s: str) -> bytes:
    return _der(0x0C, s.encode("utf-8"))


def _utctime(s: str) -> bytes:
    return _der(0x17, s.encode("ascii"))


def _boolean(v: bool) -> bytes:
    return _der(0x01, b"\xff" if v else b"\x00")


# ---------------------------------------------------------------- RSA

def _small_primes(limit: int = 2048) -> list:
    sieve = bytearray([1]) * limit
    sieve[0:2] = b"\x00\x00"
    for i in range(2, int(limit ** 0.5) + 1):
        if sieve[i]:
            sieve[i * i::i] = b"\x00" * len(sieve[i * i::i])
    return [i for i in range(limit) if sieve[i]]


_SMALL = _small_primes()


def _is_probable_prime(n: int, rounds: int = 24) -> bool:
    if n < 2:
        return False
    for p in _SMALL:
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        x = pow(2 + secrets.randbelow(n - 3), d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _gen_prime(bits: int, e: int) -> int:
    while True:
        p = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if p % e == 1:                      # 保证 gcd(e, p-1) 可能性，排除后重试
            continue
        if _is_probable_prime(p):
            return p


def _rsa_keygen(bits: int = 2048) -> tuple:
    """返回 (n, e, d, p, q)"""
    e = 65537
    while True:
        p, q = _gen_prime(bits // 2, e), _gen_prime(bits // 2, e)
        if p == q:
            continue
        n = p * q
        if n.bit_length() != bits:
            continue
        lam = (p - 1) * (q - 1) // math.gcd(p - 1, q - 1)
        if math.gcd(e, lam) != 1:
            continue
        d = pow(e, -1, lam)
        return n, e, d, p, q


def _pkcs1_private_der(n: int, e: int, d: int, p: int, q: int) -> bytes:
    """RSAPrivateKey ::= SEQUENCE {version,n,e,d,p,q,dp,dq,qinv}"""
    dp, dq = d % (p - 1), d % (q - 1)
    qinv = pow(q, -1, p)
    return _seq(_int(0), _int(n), _int(e), _int(d), _int(p), _int(q),
                _int(dp), _int(dq), _int(qinv))


# ---------------------------------------------------------------- X.509

def _pem(kind: str, der: bytes) -> str:
    b64 = base64.b64encode(der).decode("ascii")
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return (f"-----BEGIN {kind}-----\n" + "\n".join(lines)
            + f"\n-----END {kind}-----\n")


def _name(cn: str) -> bytes:
    return _seq(_der(0x31, _seq(_oid(*OID_CN), _utf8(cn))))


def _local_names() -> list:
    """SAN 条目：localhost + 主机名（DNS）+ 本机全部 IPv4（IP）"""
    names = [("DNS", "localhost")]
    try:
        host = socket.gethostname()
        if host:
            names.append(("DNS", host))
    except OSError:
        pass
    ips = {"127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    names += [("IP", ip) for ip in sorted(ips)]
    return names


def _san_der(names: list) -> bytes:
    parts = b""
    for kind, value in names:
        if kind == "DNS":
            parts += _der(0x82, value.encode("ascii"))
        else:                                # IP: OCTET STRING 4 字节
            parts += _der(0x87, ipaddress.ip_address(value).packed)
    return _seq(parts)


def _ext(oid: tuple, value: bytes, critical: bool = False) -> bytes:
    """Extension ::= SEQUENCE {extnID, critical DEFAULT FALSE, extnValue}"""
    parts = _oid(*oid)
    if critical:
        parts += _boolean(True)
    parts += _octet(value)
    return _seq(parts)


def _cert_der(key: tuple, cn: str, names: list,
              not_before: datetime.datetime,
              not_after: datetime.datetime) -> bytes:
    n, e, d = key[0], key[1], key[2]
    serial = 1 + secrets.randbelow(2 ** 62)
    sig_alg = _seq(_oid(*OID_SHA256_RSA))
    issuer = subject = _name(cn)
    validity = _seq(_utctime(not_before.strftime("%y%m%d%H%M%SZ")),
                    _utctime(not_after.strftime("%y%m%d%H%M%SZ")))
    spki = _seq(_seq(_oid(*OID_RSA_ENCRYPTION), _null()),
                _bitstr(_seq(_int(n), _int(e))))
    bc = _ext(OID_BASIC_CONSTRAINTS, _seq(_boolean(True)), critical=True)  # CA:TRUE
    san = _ext(OID_SUBJECT_ALT_NAME, _san_der(names))
    extensions = _der(0xA3, _seq(bc, san))               # [3] EXPLICIT
    tbs = _seq(_der(0xA0, _int(2)), _int(serial), sig_alg,
               issuer, validity, subject, spki, extensions)
    # EMSA-PKCS1-v1_5 签名
    digest_info = _seq(_seq(_oid(*OID_SHA256), _null()), _octet(
        hashlib.sha256(tbs).digest()))
    k = (n.bit_length() + 7) // 8
    padded = b"\x00\x01" + b"\xff" * (k - len(digest_info) - 3) + b"\x00" + digest_info
    sig = pow(int.from_bytes(padded, "big"), d, n).to_bytes(k, "big")
    return _seq(tbs, sig_alg, _bitstr(sig))


def _pair_loadable(cert_path: str, key_path: str) -> bool:
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert_path, key_path)
        return True
    except (OSError, ssl.SSLError, ValueError):
        return False


def ensure_cert(cert_dir: str, cn: str = "moeyu-helper",
                days: int = 3650) -> tuple:
    """返回 (cert_pem, key_pem)；已有可用证书对则复用，否则生成并落盘。"""
    os.makedirs(cert_dir, exist_ok=True)
    cert_path = os.path.join(cert_dir, "web_cert.pem")
    key_path = os.path.join(cert_dir, "web_key.pem")
    if os.path.exists(cert_path) and os.path.exists(key_path) \
            and _pair_loadable(cert_path, key_path):
        return cert_path, key_path
    with _LOCK:
        # 双检：并发调用时第二个进锁的直接复用
        if os.path.exists(cert_path) and os.path.exists(key_path) \
                and _pair_loadable(cert_path, key_path):
            return cert_path, key_path
        key = _rsa_keygen(2048)
        now = datetime.datetime.now(datetime.timezone.utc)
        cert_der = _cert_der(key, cn, _local_names(),
                             now - datetime.timedelta(days=1),
                             now + datetime.timedelta(days=days))
        cert_pem = _pem("CERTIFICATE", cert_der).encode("ascii")
        key_pem = _pem("RSA PRIVATE KEY",
                       _pkcs1_private_der(*key)).encode("ascii")
        with open(cert_path, "wb") as f:
            f.write(cert_pem)
        with open(key_path, "wb") as f:
            f.write(key_pem)
        try:                                 # 尽量收紧权限（Windows 忽略）
            os.chmod(key_path, 0o600)
            os.chmod(cert_path, 0o644)
        except OSError:
            pass
    if not _pair_loadable(cert_path, key_path):   # 自检：生成结果必须可用
        raise RuntimeError("自签证书生成失败：生成的证书无法被 ssl 加载")
    return cert_path, key_path
