# -*- coding: utf-8 -*-
"""R36/R42 E2EE 密聊引擎（payload 级端到端加密，叠加在 crypto.py 通道加密之上）。

安全模型（诚实边界）：
- 服务器是「不可信中继」：1v1 握手公钥、密聊正文、群 sender key 信封
  全部只透传，服务器只见密文；
- 1v1：双方 X25519 身份密钥 DH → HKDF(salt=双方 uid 排序串[+rs]) → 根密钥；
  R42 起 1v1 消息走 **对称链 ratchet**：每消息独立密钥（HKDF(链, 随机盐)），
  链单向步进、旧消息密钥即弃——链态泄露不泄历史；
- R42 **DH 轮转**：每 ROTATE_EVERY 条或手动触发，双方临时 X25519 交换
  （rt1/rt2 控制帧骑现有链传输，TCP 有序免信封），新根 =
  HKDF(旧根‖DH(eph,eph))，**临时私钥即弃** → 身份私钥泄露也无法解旧纪元
  （前向保密）；
- 群：每成员随机 32B sender_key，经各自 1v1 会话密钥（无则临时 X25519 信封）
  分发；R42 起群消息用 sender_key 种子的每消息链加密，接收方按
  (gid, from_uid, epoch) 取链解密；成员变动 → epoch+1 触发 re-key；
  R44 **群 DFSS 棘轮**：种子分发即擦（收发两端只留前向链态，种子泄露
  不解历史）+ 每发 GROUP_ROTATE_EVERY 条自动 re-key（泄露自愈）；
- 指纹：根密钥前 8 字节 → 8 枚 emoji（人工比对防 MITM；轮转不换身份，
  指纹稳定）；
- 兼容：v2 头 [ver][epoch][counter][8B盐][nonce][ct]；解密端对旧版对端的
  v1 裸封装自动回退（legacy 根 = 无 rs 派生）。

密钥落盘：身份私钥存 history 旁 e2ee_identity.json（随 R35 多账号子目录隔离）。
本地密聊历史为明文 JSONL（保搜索/重开可用性；README 写明"本机明文"边界）。
"""
import hashlib
import json
import os
import struct
import threading
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_NONCE_LEN = 12
_INFO = b"moeyu-e2ee/v1"
_FINGER_EMOJI = ["🐟", "🎮", "☕", "🔥", "🌙", "🎲", "💬", "🗂", "🎯",
                 "🧊", "🍃", "📎", "🪙", "🍋", "🫧", "🛡"]   # 4bit → 16 枚

KEY_LEN = 32
NONCE_LEN = 12

# ---------- R42 链式 ratchet 常量 ----------
_V2_VER = 2
_SALT_LEN = 8
_HDR_LEN = 1 + 4 + 4 + _SALT_LEN          # ver + epoch + counter + salt
ROTATE_EVERY = 64                         # 每发送 64 条触发一次 DH 轮转
GROUP_ROTATE_EVERY = 64                   # R44 群 DFSS：每发送 64 条自动 re-key
_OLD_EPOCH_KEEP = 2                       # 过渡期保留的旧纪元接收链数量
_ROT_TIMEOUT = 15.0                       # 轮转握手超时（秒）
MAX_RATCHET_SKIP = 1024                   # 未认证计数最多补链 1024 步，防超大计数耗尽 CPU
_INFO_MSG = b"moeyu-e2ee/msg"
_INFO_STEP = b"moeyu-e2ee/step"
_INFO_DIR_LO = b"moeyu-e2ee/dir-lo>hi"    # 小 uid → 大 uid 方向链
_INFO_DIR_HI = b"moeyu-e2ee/dir-hi>lo"


def e2ee_channel_key(a: int, b: int) -> str:
    """1v1 密聊会话键（双方 uid 排序，与 private: 键形状区分）。"""
    lo, hi = sorted((int(a), int(b)))
    return f"e2ee:{lo}:{hi}"


def fingerprint_of(key_or_pub: bytes) -> str:
    """指纹：字节前 8 位 → 8 枚 emoji（每 nibble 一枚，稳定可复现）。"""
    head = bytes(key_or_pub[:8])
    return " ".join(_FINGER_EMOJI[b >> 4] + _FINGER_EMOJI[b & 0xF] for b in head)


def _rs_join(rs_local: str, rs_remote: str) -> str:
    """R42：双方握手随机盐按字典序拼接（与谁发起无关，双方可各自算出一致）。"""
    parts = sorted(str(x or "") for x in (rs_local, rs_remote) if x)
    return ":".join(parts)[:128]


def _hkdf_session(shared: bytes, uid_a: int, uid_b: int, rs: str = "") -> bytes:
    """DH 共享密钥 → 32B 根密钥（salt=双方 uid 排序串[+rs 组合串]；R42）。"""
    lo, hi = sorted((int(uid_a), int(uid_b)))
    salt = f"{lo}:{hi}".encode() if not rs else f"{lo}:{hi}:{str(rs)[:128]}".encode()
    return HKDF(algorithm=hashes.SHA256(), length=KEY_LEN, salt=salt,
                info=_INFO).derive(shared)


def _msg_key(chain: bytes, salt: bytes) -> bytes:
    """R42：链当前态 + 每消息随机盐 → 消息密钥。"""
    return HKDF(algorithm=hashes.SHA256(), length=KEY_LEN, salt=bytes(salt),
                info=_INFO_MSG).derive(bytes(chain))


def _step_chain(chain: bytes, epoch: int, n: int) -> bytes:
    """R42：链单向步进（one-way；旧消息密钥不可回推）。"""
    return HKDF(algorithm=hashes.SHA256(), length=KEY_LEN, salt=_INFO_STEP,
                info=f"{int(epoch)}:{int(n)}".encode()).derive(bytes(chain))


def _dir_chains(root: bytes) -> tuple:
    """R42：根 → 双方向链 (lo>hi, hi>lo)，双方各自取己方向，杜绝收发同链。"""
    lo = HKDF(algorithm=hashes.SHA256(), length=KEY_LEN, salt=b"dir",
              info=_INFO_DIR_LO).derive(bytes(root))
    hi = HKDF(algorithm=hashes.SHA256(), length=KEY_LEN, salt=b"dir",
              info=_INFO_DIR_HI).derive(bytes(root))
    return lo, hi


def _rot_root(old_root: bytes, shared: bytes, uid_a: int, uid_b: int,
              epoch: int) -> bytes:
    """R42：DH 轮转 → 新根 = HKDF(旧根‖新DH, salt=rot:uid:uid:epoch)。"""
    lo, hi = sorted((int(uid_a), int(uid_b)))
    salt = f"rot:{lo}:{hi}:{int(epoch)}".encode()
    return HKDF(algorithm=hashes.SHA256(), length=KEY_LEN, salt=salt,
                info=_INFO).derive(bytes(old_root) + bytes(shared))


class E2EEError(Exception):
    """E2EE 引擎错误（密钥缺失/解密失败/epoch 落后等）。

    code：no_key（缺 sender key/纪元）/ replay（重放）/ decrypt（解密失败/
    篡改）/ stale（旧纪元登记拒收）/ generic——核心层按 code 分流处置
    （R44：仅 no_key 触发 SK_REQ 补发，防重放/篡改引发 re-key 风暴）。"""

    def __init__(self, msg: str, code: str = "generic"):
        super().__init__(msg)
        self.code = str(code)


class E2EEEngine:
    """端到端加密引擎：身份密钥对 + 1v1 链式会话 + 群 sender key 链表。"""

    def __init__(self, data_dir: str) -> None:
        self._dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self._lock = threading.RLock()
        self._identity = self._load_or_create_identity()
        # 1v1 会话态：peer_uid -> {"root","legacy","epoch","send":[chain,n],
        #                         "recv":{epoch:{"chain","n"}},"rot":None|{...}}
        self._sessions: dict = {}
        # 群 sender key 表：gid -> {"epoch": int, "sk_map": {from_uid: (epoch, key)},
        #                           "recv": {from_uid: {epoch: {"chain","n"}}}}
        self._groups: dict = {}
        # 我在各群的发送链：gid -> {"epoch","chain","n"}
        self._my_sk: dict = {}
        self._my_send: dict = {}

    # ---------- 身份密钥 ----------
    def _load_or_create_identity(self) -> x25519.X25519PrivateKey:
        path = os.path.join(self._dir, "e2ee_identity.json")
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                raw = bytes.fromhex(str(data.get("priv") or ""))
                if len(raw) == KEY_LEN:
                    return x25519.X25519PrivateKey.from_private_bytes(raw)
            except (OSError, ValueError, TypeError):
                pass
        priv = x25519.X25519PrivateKey.generate()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"priv": priv.private_bytes_raw().hex()}, f)
        except OSError:
            pass                      # 落盘失败仍可用（本次会话内有效）
        return priv

    @property
    def identity_pub(self) -> bytes:
        """本机身份公钥（32B 原始字节）。"""
        return self._identity.public_key().public_bytes_raw()

    # ---------- 1v1 会话 ----------
    def derive_session_key(self, my_uid: int, peer_uid: int, peer_pub: bytes) -> bytes:
        """用双方身份公钥 DH+HKDF 派生根密钥（不落缓存；指纹/校验用）。"""
        shared = self._identity.exchange(
            x25519.X25519PublicKey.from_public_bytes(bytes(peer_pub)))
        return _hkdf_session(shared, my_uid, peer_uid)

    def fingerprint(self, my_uid: int, peer_uid: int, peer_pub: bytes) -> str:
        """与 peer 的会话指纹（双方各自算出一致；人工比对防 MITM）。"""
        return fingerprint_of(self.derive_session_key(my_uid, peer_uid, peer_pub))

    def establish_session(self, my_uid: int, peer_uid: int, peer_pub: bytes,
                          rs_local: str = "", rs_remote: str = "",
                          legacy_peer: bool = False) -> bytes:
        """建立并缓存与 peer 的会话（R42：双方握手随机盐混入根；链式状态初始化）。

        rs_local/rs_remote = 本端/对端本次握手的随机盐（按序无关拼接）——
        每次握手根全新，重启不复用旧链。双双缺省 = 与 R36 静态派生一致。
        legacy_peer=对端为旧版客户端（握手无 rs/ACK 无 rv）→ 收发走 v1
        静态封装、不触发轮转（混版本部署兼容）。返回根密钥。"""
        shared = self._identity.exchange(
            x25519.X25519PublicKey.from_public_bytes(bytes(peer_pub)))
        rs = _rs_join(rs_local, rs_remote)
        root = _hkdf_session(shared, my_uid, peer_uid, rs)
        legacy = _hkdf_session(shared, my_uid, peer_uid)   # 旧版对端静态钥
        lo_c, hi_c = _dir_chains(root)
        mine_first = int(my_uid) < int(peer_uid)
        with self._lock:
            self._sessions[int(peer_uid)] = {
                "root": root, "legacy": legacy, "epoch": 0,
                "send": [lo_c if mine_first else hi_c, 0],
                "recv": {0: {"chain": hi_c if mine_first else lo_c, "n": 0}},
                "rot": None, "t0": self._now(),
                "fp": fingerprint_of(legacy),   # 身份静态指纹（轮转不变）
                "old": bool(legacy_peer),
            }
        return root

    def session_key(self, peer_uid: int) -> bytes | None:
        """当前与 peer 的根密钥（信封分发等控制面用；未建立 None）。"""
        with self._lock:
            st = self._sessions.get(int(peer_uid))
            return st["root"] if st else None

    def drop_session(self, peer_uid: int) -> None:
        with self._lock:
            self._sessions.pop(int(peer_uid), None)

    def peer_fingerprint(self, peer_uid: int) -> str:
        """当前缓存的与 peer 的会话指纹（身份 DH 静态派生，轮转后不变；
        人工比对防 MITM；未建立返回空串）。"""
        with self._lock:
            st = self._sessions.get(int(peer_uid))
            return str(st.get("fp") or "") if st else ""

    def session_fresh(self, peer_uid: int, max_age: float = 10.0) -> bool:
        """R42：会话是否「刚建立且未使用」（并发握手去重用——刚握完手的
        会话不接受对方紧接着的重复握手覆盖）。"""
        with self._lock:
            st = self._sessions.get(int(peer_uid))
            return bool(st and st["epoch"] == 0 and st["send"][1] == 0
                        and all(r["n"] == 0 for r in st["recv"].values())
                        and self._now() - st.get("t0", 0.0) <= max_age)

    # ---------- R42 1v1 链式收发 ----------
    @staticmethod
    def _plain(obj) -> bytes:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def _seal_v2(self, chain: bytes, epoch: int, n: int, obj) -> bytes:
        """v2 载荷：[ver][epoch][counter][8B盐][12B nonce][AES-GCM(JSON)]。"""
        salt = os.urandom(_SALT_LEN)
        mk = _msg_key(chain, salt)
        nonce = os.urandom(_NONCE_LEN)
        ct = AESGCM(mk).encrypt(nonce, self._plain(obj), None)
        return (struct.pack(">BII", _V2_VER, int(epoch) & 0xFFFFFFFF,
                            int(n) & 0xFFFFFFFF) + salt + nonce + ct)

    def seal_ratchet(self, peer_uid: int, obj) -> bytes:
        """R42：1v1 发送——当前发送链密封，链步进（每消息独立密钥）。

        对端为旧版客户端（legacy_peer）→ v1 静态封装（无链；接收端新版本
        自动回退可解，旧版本原生可解）。"""
        with self._lock:
            st = self._sessions.get(int(peer_uid))
            if st is None:
                raise E2EEError("会话未建立")
            if st.get("old"):
                return self.seal(st["legacy"], obj)
            chain, n = st["send"]
            blob = self._seal_v2(chain, st["epoch"], n, obj)
            st["send"] = [_step_chain(chain, st["epoch"], n), n + 1]
            return blob

    def unseal_ratchet(self, peer_uid: int, blob: bytes):
        """R42：1v1 接收——v2 链解密（含旧纪元过渡）；v1 裸封装回退（旧对端）。

        链计数落后（重放）或未知纪元 → E2EEError。"""
        peer = int(peer_uid)
        with self._lock:
            st = self._sessions.get(peer)
        if st is None:
            raise E2EEError("会话未建立")
        if blob and blob[0] == _V2_VER and len(blob) >= _HDR_LEN + 16:
            epoch, n = struct.unpack(">II", blob[1:9])
            salt = blob[9:9 + _SALT_LEN]
            nonce = blob[9 + _SALT_LEN:9 + _SALT_LEN + _NONCE_LEN]
            ct = blob[9 + _SALT_LEN + _NONCE_LEN:]
            with self._lock:
                r = st["recv"].get(epoch)
                if r is None:
                    raise E2EEError(f"未知纪元 {epoch}（请重新握手密聊）")
                if n < r["n"]:
                    raise E2EEError("重放帧已拒收")
                if n - r["n"] > MAX_RATCHET_SKIP:
                    raise E2EEError("密聊计数跳跃超限，请重新握手", code="counter")
                c = r["chain"]
                for i in range(r["n"], n):       # 步进到目标计数（中间密钥即弃）
                    c = _step_chain(c, epoch, i)
                mk = _msg_key(c, salt)
                try:
                    plain = AESGCM(mk).decrypt(nonce, ct, None)
                except Exception as exc:
                    raise E2EEError("decrypt failed (篡改或密钥不一致)") from exc
                st["recv"][epoch] = {"chain": _step_chain(c, epoch, n), "n": n + 1}
                self._cap_recv(st)
            try:
                return json.loads(plain.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise E2EEError("bad plaintext json") from exc
        return self.unseal(st["legacy"], blob)   # 旧版对端 v1 回退

    @staticmethod
    def _cap_recv(st: dict) -> None:
        """只保留当前纪元 + 最近 _OLD_EPOCH_KEEP 个旧纪元的接收链。"""
        cur = st["epoch"]
        others = sorted(e for e in st["recv"] if e != cur)
        for e in others[:max(0, len(others) - _OLD_EPOCH_KEEP)]:
            st["recv"].pop(e, None)

    # ---------- R42 1v1 DH 轮转（rt1/rt2 控制帧骑现有链） ----------
    @staticmethod
    def _now() -> float:
        return time.monotonic()

    def rotate_begin(self, my_uid: int, peer_uid: int) -> dict | None:
        """发起轮转：生成临时 X25519 并挂 pending，返回 rt1 控制载荷。

        已有进行中的轮转（或刚发起未超时）→ None。"""
        with self._lock:
            st = self._sessions.get(int(peer_uid))
            if st is None:
                raise E2EEError("会话未建立")
            rot = st["rot"]
            if rot is not None:
                if self._now() - rot["t0"] <= _ROT_TIMEOUT:
                    return None
                st["rot"] = None                    # 超时放弃旧轮转
            eph = x25519.X25519PrivateKey.generate()
            st["rot"] = {"epoch": int(st["epoch"]) + 1, "priv": eph,
                         "pub": eph.public_key().public_bytes_raw(),
                         "t0": self._now()}
            return {"rt": 1, "epoch": st["rot"]["epoch"],
                    "eph": st["rot"]["pub"].hex()}

    def rotate_on_rt1(self, my_uid: int, peer_uid: int, eph_pub: bytes) -> bytes | None:
        """被动方收 rt1：rt2 用旧发送链封好 → 切新纪元 → 返回 rt2 blob。

        并发轮转收敛：双方同时发起时 uid 较大一方的轮转让位（返回 None）。"""
        if len(eph_pub) != 32:
            raise E2EEError("bad eph pub")
        peer = int(peer_uid)
        with self._lock:
            st = self._sessions.get(peer)
            if st is None:
                raise E2EEError("会话未建立")
            rot = st["rot"]
            if rot is not None:
                if self._now() - rot["t0"] <= _ROT_TIMEOUT:
                    if int(my_uid) > peer:
                        st["rot"] = None            # 让位：小 uid 一方优先
                    else:
                        return None                 # 我方优先，忽略对端 rt1
                else:
                    st["rot"] = None
            new_epoch = int(st["epoch"]) + 1
            eph = x25519.X25519PrivateKey.generate()
            # 1) rt2 先用旧发送链封（帧头仍是旧纪元；对端旧接收链可解）
            chain, n = st["send"]
            blob = self._seal_v2(chain, st["epoch"], n,
                                 {"rt": 2, "epoch": new_epoch,
                                  "eph": eph.public_key().public_bytes_raw().hex()})
            st["send"] = [_step_chain(chain, st["epoch"], n), n + 1]
            # 2) 计算新根并切换（eph 临时私钥用后即弃）
            shared = eph.exchange(x25519.X25519PublicKey.from_public_bytes(bytes(eph_pub)))
            self._commit_epoch(st, int(my_uid), peer, shared, new_epoch)
            return blob

    def rotate_on_rt2(self, my_uid: int, peer_uid: int, eph_pub: bytes) -> bool:
        """发起方收 rt2：DH 混入新根并切换（临时私钥随 pending 丢弃）。"""
        if len(eph_pub) != 32:
            return False
        peer = int(peer_uid)
        with self._lock:
            st = self._sessions.get(peer)
            rot = st["rot"] if st else None
            if st is None or rot is None:
                return False
            shared = rot["priv"].exchange(
                x25519.X25519PublicKey.from_public_bytes(bytes(eph_pub)))
            self._commit_epoch(st, int(my_uid), peer, shared, int(rot["epoch"]))
            st["rot"] = None
            return True

    def _commit_epoch(self, st: dict, my_uid: int, peer_uid: int,
                      shared: bytes, new_epoch: int) -> None:
        root = _rot_root(st["root"], shared, my_uid, peer_uid, new_epoch)
        lo_c, hi_c = _dir_chains(root)
        mine_first = int(my_uid) < int(peer_uid)
        st["root"] = root
        st["epoch"] = new_epoch
        st["send"] = [lo_c if mine_first else hi_c, 0]
        st["recv"][new_epoch] = {"chain": hi_c if mine_first else lo_c, "n": 0}
        self._cap_recv(st)

    def rotate_due(self, peer_uid: int) -> bool:
        """发送计数到达 ROTATE_EVERY 整数倍且无进行中轮转 → 应触发轮转。

        旧版对端（legacy_peer）不支持 rt 控制帧 → 永不自动轮转。"""
        with self._lock:
            st = self._sessions.get(int(peer_uid))
            return bool(st and not st.get("old") and st["rot"] is None
                        and st["send"][1] > 0
                        and st["send"][1] % ROTATE_EVERY == 0)

    def is_legacy_peer(self, peer_uid: int) -> bool:
        """对端是否旧版客户端（不支持链式/轮转；未建立会话返回 False）。"""
        with self._lock:
            st = self._sessions.get(int(peer_uid))
            return bool(st and st.get("old"))

    def rotate_pending(self, peer_uid: int) -> bool:
        with self._lock:
            st = self._sessions.get(int(peer_uid))
            return bool(st and st["rot"] is not None)

    def rotate_abort(self, peer_uid: int) -> None:
        """放弃进行中的轮转（超时兜底；临时私钥丢弃）。"""
        with self._lock:
            st = self._sessions.get(int(peer_uid))
            if st:
                st["rot"] = None

    # ---------- 信封加密（群 sender key 分发用）----------
    def seal_for_peer(self, peer_pub: bytes, plain: bytes) -> bytes:
        """临时 X25519 信封：[32B eph_pub][nonce][AES-GCM(ct)]（无需既有会话）。"""
        eph = x25519.X25519PrivateKey.generate()
        shared = eph.exchange(x25519.X25519PublicKey.from_public_bytes(bytes(peer_pub)))
        key = HKDF(algorithm=hashes.SHA256(), length=KEY_LEN,
                   salt=b"moeyu-envelope-v1", info=_INFO).derive(shared)
        nonce = os.urandom(_NONCE_LEN)
        ct = AESGCM(key).encrypt(nonce, bytes(plain), None)
        return eph.public_key().public_bytes_raw() + nonce + ct

    def open_envelope(self, blob: bytes) -> bytes:
        """解临时信封（对方用我身份公钥封的）。"""
        if len(blob) < 32 + _NONCE_LEN + 16:
            raise E2EEError("envelope too short")
        eph_pub, rest = blob[:32], blob[32:]
        nonce, ct = rest[:_NONCE_LEN], rest[_NONCE_LEN:]
        shared = self._identity.exchange(
            x25519.X25519PublicKey.from_public_bytes(eph_pub))
        key = HKDF(algorithm=hashes.SHA256(), length=KEY_LEN,
                   salt=b"moeyu-envelope-v1", info=_INFO).derive(shared)
        try:
            return AESGCM(key).decrypt(nonce, ct, None)
        except Exception as exc:
            raise E2EEError("envelope decrypt failed") from exc

    # ---------- 载荷密封（AES-256-GCM + 随机 nonce；v1 原语，信封/回退用）----------
    @staticmethod
    def seal(key: bytes, obj) -> bytes:
        """任意可 JSON 对象 → [12B nonce][AES-GCM(JSON)]。"""
        plain = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        nonce = os.urandom(_NONCE_LEN)
        return nonce + AESGCM(bytes(key)).encrypt(nonce, plain, None)

    @staticmethod
    def unseal(key: bytes, blob: bytes):
        """[12B nonce][AES-GCM] → 对象；tag 校验失败抛 E2EEError。"""
        if len(blob) < _NONCE_LEN + 16:
            raise E2EEError("payload too short")
        nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
        try:
            plain = AESGCM(bytes(key)).decrypt(nonce, ct, None)
        except Exception as exc:
            raise E2EEError("decrypt failed (篡改或密钥不一致)") from exc
        try:
            return json.loads(plain.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise E2EEError("bad plaintext json") from exc

    # ---------- 群 sender key（R42：epoch 内每消息链） ----------
    @staticmethod
    def _g_seed(key: bytes, gid: int, epoch: int) -> bytes:
        """sender_key → 该 (gid, epoch) 的消息链种子。"""
        return HKDF(algorithm=hashes.SHA256(), length=KEY_LEN,
                    salt=f"g:{int(gid)}:{int(epoch)}".encode(),
                    info=_INFO).derive(bytes(key))

    def new_group_epoch(self, gid: int, retain_seed: bool = True) -> tuple:
        """生成新 epoch + 我的新 sender_key（re-key 起点）。返回 (epoch, key)。

        R44 DFSS：retain_seed=False 时引擎随即只留发送链态、擦除原始种子
        （返回值仅供本次信封封装使用；种子暴露窗从整个纪元压缩到分发瞬间）。
        混合旧版组（v1 静态发送仍需种子）由核心层传 retain_seed=True。"""
        with self._lock:
            st = self._groups.setdefault(int(gid), {"epoch": 0, "sk_map": {},
                                                    "recv": {}})
            st["epoch"] = int(st["epoch"]) + 1
            sk = os.urandom(KEY_LEN)
            epoch = st["epoch"]
            self._my_sk[int(gid)] = (epoch, bytes(sk)) if retain_seed \
                else (epoch, None)
            self._my_send[int(gid)] = {"epoch": epoch,
                                       "chain": self._g_seed(sk, gid, epoch), "n": 0}
            return epoch, sk

    def group_epoch(self, gid: int) -> int:
        with self._lock:
            return int(self._groups.get(int(gid), {}).get("epoch") or 0)

    def my_group_epoch(self, gid: int) -> int:
        """我在该群当前发送纪元（未开启返回 0）。"""
        with self._lock:
            s = self._my_send.get(int(gid))
            return int(s["epoch"]) if s else 0

    def my_group_counter(self, gid: int) -> int:
        """我在该群当前发送链已用计数（未开启返回 0）。"""
        with self._lock:
            s = self._my_send.get(int(gid))
            return int(s["n"]) if s else 0

    def group_rotate_due(self, gid: int) -> bool:
        """R44 DFSS：群发送计数到达 GROUP_ROTATE_EVERY → 自动 re-key 到期。"""
        with self._lock:
            s = self._my_send.get(int(gid))
            return bool(s and int(s["n"]) >= GROUP_ROTATE_EVERY)

    def set_my_sender_key(self, gid: int, epoch: int, key: bytes) -> None:
        with self._lock:
            self._my_sk[int(gid)] = (int(epoch), bytes(key))
            cur = self._my_send.get(int(gid))
            if cur is None or int(cur["epoch"]) != int(epoch):
                self._my_send[int(gid)] = {"epoch": int(epoch),
                                           "chain": self._g_seed(key, gid, epoch),
                                           "n": 0}

    def my_sender_key(self, gid: int) -> tuple | None:
        with self._lock:
            return self._my_sk.get(int(gid))

    def seal_group(self, gid: int, obj) -> bytes:
        """R42：群发送——我的 sender 链密封（帧头 epoch 由 my_group_epoch 提供）。"""
        with self._lock:
            s = self._my_send.get(int(gid))
            if s is None:
                raise E2EEError("该群未开启密聊")
            blob = self._seal_v2(s["chain"], s["epoch"], s["n"], obj)
            s["chain"] = _step_chain(s["chain"], s["epoch"], s["n"])
            s["n"] += 1
            return blob

    def set_peer_sender_key(self, gid: int, from_uid: int, key: bytes,
                            epoch: int, retain_seed: bool = True) -> None:
        """记录成员 sender_key（按 (gid, from_uid) 维度，仅接受该发送者更新/同纪元）。

        同纪元重复登记（SK_REQ 补发）不重置已步进的接收链。
        R44 DFSS：retain_seed=False 只派生接收链、随即擦除原始种子——
        接收端仅存前向链态，登记态泄露不解历史。legacy 发送者须传 True
        （其 v1 裸封装回退解密依赖原始 key）。"""
        with self._lock:
            st = self._groups.setdefault(int(gid), {"epoch": 0, "sk_map": {},
                                                    "recv": {}})
            cur = st["sk_map"].get(int(from_uid))
            if cur is not None and int(epoch) < int(cur[0]):
                raise E2EEError(f"stale sk epoch {epoch} < {cur[0]}", code="stale")
            st["sk_map"][int(from_uid)] = (int(epoch),
                                           bytes(key) if retain_seed else None)
            st["epoch"] = max(int(st["epoch"]), int(epoch))
            recv = st["recv"].setdefault(int(from_uid), {})
            if int(epoch) not in recv:
                recv[int(epoch)] = {"chain": self._g_seed(key, gid, epoch), "n": 0}
            self._prune_group_epochs(st, int(from_uid))

    @staticmethod
    def _prune_group_epochs(st: dict, from_uid: int) -> None:
        """R44：每发送者只保留当前 + 最近 _OLD_EPOCH_KEEP 个旧纪元接收链
        （过期链态即弃，历史消息不再可解）。"""
        recv = st.get("recv", {}).get(int(from_uid))
        if not recv:
            return
        cur = st["sk_map"].get(int(from_uid), (0, None))[0]
        old = sorted(e for e in recv if e != cur)
        for e in old[:max(0, len(old) - _OLD_EPOCH_KEEP)]:
            recv.pop(e, None)

    def peer_sender_entry(self, gid: int, from_uid: int) -> tuple | None:
        """返回 (epoch, key)；未登记返回 None。"""
        with self._lock:
            cur = self._groups.get(int(gid), {}).get("sk_map", {}).get(int(from_uid))
            return (int(cur[0]), cur[1]) if cur else None

    def peer_sender_key(self, gid: int, from_uid: int) -> bytes | None:
        entry = self.peer_sender_entry(gid, from_uid)
        return entry[1] if entry else None

    def unseal_group(self, gid: int, from_uid: int, blob: bytes):
        """R42：群接收——按 (gid, from_uid, epoch) 取链解密；v1 裸封装回退。"""
        gid, src = int(gid), int(from_uid)
        with self._lock:
            g = self._groups.get(gid) or {}
            rmap = g.get("recv", {}).get(src) or {}
            entry = g.get("sk_map", {}).get(src)
        if blob and blob[0] == _V2_VER and len(blob) >= _HDR_LEN + 16:
            epoch, n = struct.unpack(">II", blob[1:9])
            salt = blob[9:9 + _SALT_LEN]
            nonce = blob[9 + _SALT_LEN:9 + _SALT_LEN + _NONCE_LEN]
            ct = blob[9 + _SALT_LEN + _NONCE_LEN:]
            with self._lock:
                r = rmap.get(epoch)
                if r is None:
                    raise E2EEError(f"缺纪元 {epoch} sender key", code="no_key")
                if n < r["n"]:
                    raise E2EEError("重放帧已拒收", code="replay")
                if n - r["n"] > MAX_RATCHET_SKIP:
                    raise E2EEError("群密聊计数跳跃超限", code="counter")
                c = r["chain"]
                for i in range(r["n"], n):
                    c = _step_chain(c, epoch, i)
                mk = _msg_key(c, salt)
                try:
                    plain = AESGCM(mk).decrypt(nonce, ct, None)
                except Exception as exc:
                    raise E2EEError("decrypt failed (篡改或密钥不一致)",
                                    code="decrypt") from exc
                rmap[epoch] = {"chain": _step_chain(c, epoch, n), "n": n + 1}
            try:
                return json.loads(plain.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise E2EEError("bad plaintext json", code="decrypt") from exc
        if entry is None or entry[1] is None:
            raise E2EEError("缺 sender key", code="no_key")
        return self.unseal(entry[1], blob)       # 旧版对端 v1 回退

    def drop_group(self, gid: int) -> None:
        """退群/被踢：销毁该群全部密钥材料。"""
        with self._lock:
            self._groups.pop(int(gid), None)
            self._my_sk.pop(int(gid), None)
            self._my_send.pop(int(gid), None)
