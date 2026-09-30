# -*- coding: utf-8 -*-
"""auth.py —— 本机解锁码（Passcode）哈希与本地限频（对标 TG passcode/受限尝试）。

- make/verify：PBKDF2-HMAC-SHA256 派生，存盘为 "hexsalt:hexhash"，不存明文。
- FloodGuard：本地记忆内限频，步进式递进冷却，对齐 TG settings.h `passcodeCanTry`：
  从第 max_attempts 次失败起，等待时间随失败次数逐级拉长（第 3 次 5s、每多一次 +5s，
  封顶 window/30s），连续试错期间连正确码也暂拒。纯逻辑、无 UI/tk 依赖，可单测。
"""
import hashlib
import os
import time

SALT_LEN = 16
ITERS = 100_000
MAX_ATTEMPTS = 3          # 从此次数失败起进入递进冷却（TG 从第 3 次起）
LOCK_WINDOW = 30          # 秒；递进冷却的封顶等待
_GRADE_SEC = 5            # 每次失败递增的等待（6 档到封顶，对应 TG 5…30s）


def salt() -> bytes:
    return os.urandom(SALT_LEN)


def _h(plain: str, s: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), s, ITERS)


def make(scode: str) -> str:
    """生成可存盘的密码串 "hexsalt:hexhash"。"""
    s = os.urandom(SALT_LEN)
    return s.hex() + ":" + _h(scode, s).hex()


def verify(scode: str, stored: str) -> bool:
    """校验明文 scode 是否匹配 stored。空码/坏格式一律 False。"""
    if not scode or not stored:
        return False
    try:
        salt_hex, hash_hex = stored.split(":", 1)
        s = bytes.fromhex(salt_hex)
        want = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    if not s or not want:
        return False
    got = _h(scode, s)
    return got == want   # 长度固定，直接比对即可


class FloodGuard:
    """本地解锁限频：失败次数达到阈值后进入逐级递进冷却（对齐 TG passcodeCanTry）。

    第 N 次失败起（N=max_attempts，默认 3），等待 = (N-阈值+1)*grade，封顶 window。
    连续失败期连正确码也拒；解码成功后清零（ok）。
    """

    def __init__(self, max_attempts: int = MAX_ATTEMPTS,
                 window: float = LOCK_WINDOW) -> None:
        self._threshold = max(int(max_attempts), 1)
        self._cap = max(float(window), 1.0)
        self._bad_tries = 0
        self._last_try = 0.0

    def _wait_sec(self) -> float:
        """当前失败次数对应的需等待秒数；未达阈值返回 0。"""
        if self._bad_tries < self._threshold:
            return 0.0
        grade = max(self._cap / 6.0, _GRADE_SEC / 6.0)
        steps = self._bad_tries - self._threshold + 1
        return min(self._cap, grade * steps)

    def remaining(self) -> float:
        """还需等待秒数；>0 表示正在锁定中，0 表示可试。"""
        wait = self._wait_sec()
        dt = time.time() - self._last_try
        return max(0.0, wait - dt)

    def allowed(self) -> bool:
        return self.remaining() <= 0

    def fail(self) -> None:
        """记录一次失败（并启动/拉长本次冷却）。"""
        self._bad_tries += 1
        self._last_try = time.time()

    def ok(self) -> None:
        """解锁成功后清零。"""
        self._bad_tries = 0
        self._last_try = 0.0