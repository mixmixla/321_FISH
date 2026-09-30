# -*- coding: utf-8 -*-
"""R37 加密云历史 —— 客户端侧打包/加密/解包/合并（纯逻辑，无 UI/网络依赖）。

安全模型（诚实边界）：
- 口令不落盘、不上传：仅在本机用于派生密钥；忘了口令 = 云端备份不可恢复；
- 派生：PBKDF2-HMAC-SHA256(口令, salt=16B 随机, ITERS=100k, 与 auth.py 同参) → 32B；
- 载荷：{"v":1,"uid":...,"nick":...,"exported":ts,"channels":{key:[msg...]},
  "conv_states":{key:{ts,read,unread,draft,pin,muted,archived}}}   ← R39B 会话状态段
  （可省略：旧客户端打包的 blob 无此段；新客户端读旧 blob 视为空）
  → JSON/UTF-8 → AES-256-GCM（blob = magic + salt(16) + nonce(12) + 密文）；
- 服务器只见密文 blob（按 uid 存一份，重启保留），解不出任何消息内容；
- 本地密聊历史亦明文存在于本机 JSONL → 打包加密后云端不可见，边界一致。

合并策略：按频道去重（指纹 = (ts, uid, text)），仅追加本地缺失的消息；
编辑/撤回等已有 seq 的消息以本地为准（不回滚）。
R39B 会话状态：per 会话键整段快照按 ts 新者胜（merge_conv_states）。
"""
import json
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"MHCL"          # moeyu-history-cloud v1
_SALT_LEN = 16
_NONCE_LEN = 12
_KEY_LEN = 32
_ITERS = 100_000         # 与 auth.py 对齐

CLOUD_BLOB_MAX = 2 * 1024 * 1024   # 云端单份备份配额（字节，防滥用）


class CloudHistoryError(Exception):
    """云历史打包/解包错误（口令错/数据损坏/版本不识别）。"""


def derive_key(password: str, salt: bytes) -> bytes:
    """口令 → 32B 会话密钥（PBKDF2-HMAC-SHA256）。"""
    import hashlib
    return hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"),
                               bytes(salt), _ITERS, dklen=_KEY_LEN)


def pack(channels: dict, uid: int, nick: str, password: str,
         conv_states: dict | None = None) -> bytes:
    """全量频道历史 → 加密 blob。channels: {key: [msg, ...]}。

    conv_states（R39B）：{key: state} 会话状态段，空/None 不写入（兼容旧结构）。
    """
    payload = {"v": 1, "uid": int(uid), "nick": str(nick),
               "exported": time.time(),
               "channels": {str(k): list(v or []) for k, v in channels.items()}}
    if conv_states:
        payload["conv_states"] = {str(k): dict(v or {})
                                  for k, v in conv_states.items()}
    plain = json.dumps(payload, ensure_ascii=False,
                       separators=(",", ":")).encode("utf-8")
    salt = _random(_SALT_LEN)
    nonce = _random(_NONCE_LEN)
    ct = AESGCM(derive_key(password, salt)).encrypt(nonce, plain, None)
    return MAGIC + salt + nonce + ct


def unpack(blob: bytes, password: str) -> dict:
    """加密 blob → 载荷 dict（口令错/损坏抛 CloudHistoryError）。"""
    head = len(MAGIC) + _SALT_LEN + _NONCE_LEN
    if not isinstance(blob, (bytes, bytearray)) or len(blob) <= head \
            or bytes(blob[:len(MAGIC)]) != MAGIC:
        raise CloudHistoryError("不是有效的云备份文件")
    salt = bytes(blob[len(MAGIC):len(MAGIC) + _SALT_LEN])
    nonce = bytes(blob[len(MAGIC) + _SALT_LEN:head])
    ct = bytes(blob[head:])
    try:
        plain = AESGCM(derive_key(password, salt)).decrypt(nonce, ct, None)
    except Exception as exc:
        raise CloudHistoryError("解密失败（口令错误或数据被篡改）") from exc
    try:
        data = json.loads(plain.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise CloudHistoryError("备份内容损坏") from exc
    if not isinstance(data, dict) or int(data.get("v") or 0) != 1 \
            or not isinstance(data.get("channels"), dict):
        raise CloudHistoryError("备份版本不识别")
    if not isinstance(data.get("conv_states"), dict):   # R39B：旧 blob 无此段
        data["conv_states"] = {}
    return data


def fingerprint(msg: dict):
    """合并去重指纹：(ts, uid, text)。ts 统一转 float（历史里可能是字符串）。"""
    ts = msg.get("ts", 0)
    if isinstance(ts, str):
        try:
            ts = float(ts)
        except (TypeError, ValueError):
            ts = 0.0
    return (ts, msg.get("uid"), msg.get("text"))


def merge(existing: list, incoming: list) -> list:
    """把 incoming 中本地缺失的消息追加到 existing 之后（就地修改并返回）。

    已存在的（按指纹判重）跳过；incoming 保持原时间顺序。
    """
    seen = {fingerprint(m) for m in existing}
    for m in incoming:
        if not isinstance(m, dict):
            continue
        f = fingerprint(m)
        if f in seen:
            continue
        seen.add(f)
        existing.append(m)
    return existing


def merge_conv_states(local: dict, incoming: dict) -> dict:
    """R39B：会话状态合并（per 会话键，ts 新者胜；就地修改并返回）。

    ts 相等或 incoming 无 ts → 本地保留；某键只在一边 → 直接纳入。
    """
    for key, st in (incoming or {}).items():
        if not isinstance(st, dict):
            continue
        cur = local.get(key)
        if isinstance(cur, dict) and \
                float(st.get("ts") or 0) <= float(cur.get("ts") or 0):
            continue
        local[key] = st
    return local


def _random(n: int) -> bytes:
    import os
    return os.urandom(n)
