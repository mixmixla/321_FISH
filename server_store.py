# -*- coding: utf-8 -*-
"""服务器全状态持久化的严格 bytes/阶段 IO seam。

``ServerStore`` 只负责 state.json 的 bytes 读写。快照捕获、退役候选
校验、unknown 对账和状态确认仍由 ``server.Hub`` 负责；本模块不维护第二
份业务快照。活动 Hub 可通过私有绑定把兼容 save 调用接回同一 writer。
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import hashlib
import json
import math
import os
import secrets
import stat
import threading
import time
from typing import Any


@dataclass(frozen=True)
class EncodedState:
    """一次严格 JSON 编码产生的不可变 payload 及其真实 bytes 标识。"""

    payload: bytes
    length: int
    sha256: str

    @property
    def digest(self) -> str:
        """兼容调用方对摘要使用 ``digest`` 的命名。"""
        return self.sha256

    @property
    def data(self) -> bytes:
        return self.payload

    @property
    def content_sha256(self) -> str:
        return self.sha256


@dataclass(frozen=True)
class SaveResult:
    """一次 bytes IO 的真实阶段结果。

    ``effect`` 只有 ``committed`` 才代表 replace 已返回成功；replace 调用
    后无法证明效果时必须使用 ``uncertain``，不能用 bool 真值猜测。
    """

    effect: str
    stage: str | None = None
    error_code: str | None = None
    retryable: bool = False
    length: int = 0
    sha256: str | None = None

    @property
    def digest(self) -> str | None:
        return self.sha256

    @property
    def content_sha256(self) -> str | None:
        return self.sha256

    @property
    def committed(self) -> bool:
        return self.effect == "committed"

    def __bool__(self) -> bool:
        raise TypeError("compare SaveResult.effect explicitly")


@dataclass(frozen=True)
class ReadResult:
    """权威 state.json 的原始 bytes 读取结果。"""

    status: str
    payload: bytes | None = None
    length: int | None = None
    sha256: str | None = None
    error_code: str | None = None

    @property
    def effect(self) -> str:
        """与专项 seam 统一的状态别名；值仍为 bytes/missing/read_error。"""
        return self.status

    @property
    def digest(self) -> str | None:
        return self.sha256

    @property
    def data(self) -> bytes | None:
        return self.payload

    @property
    def content_sha256(self) -> str | None:
        return self.sha256


def _json_key_text(key: Any) -> str:
    """返回 json.dumps 对 object key 使用的文本形式，并拒绝隐式对象键。"""
    if isinstance(key, str):
        if any(0xD800 <= ord(ch) <= 0xDFFF for ch in key):
            raise UnicodeError("surrogate is not valid UTF-8 text")
        return key
    if isinstance(key, int) and not isinstance(key, bool):
        return str(key)
    raise TypeError(f"keys must be string/integer, got {type(key).__name__}")


def _validate_json_value(value: Any, active: set[int]) -> None:
    """预检 JSON 可编码值、有限数值、循环和 object-key 转换冲突。"""
    if isinstance(value, str):
        if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
            raise UnicodeError("surrogate is not valid UTF-8 text")
        return
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Out of range float values are not JSON compliant")
        return
    if isinstance(value, dict):
        marker = id(value)
        if marker in active:
            raise ValueError("circular JSON value")
        active.add(marker)
        try:
            converted: set[str] = set()
            for key, child in value.items():
                key_text = _json_key_text(key)
                if key_text in converted:
                    raise ValueError("JSON object key conversion collision")
                converted.add(key_text)
                _validate_json_value(child, active)
        finally:
            active.remove(marker)
        return
    if isinstance(value, (list, tuple)):
        marker = id(value)
        if marker in active:
            raise ValueError("circular JSON value")
        active.add(marker)
        try:
            for child in value:
                _validate_json_value(child, active)
        finally:
            active.remove(marker)
        return
    raise TypeError(f"value is not strict JSON data: {type(value).__name__}")


def encode_state(state: dict) -> EncodedState:
    """严格、单次编码快照并返回其真实 immutable bytes 标识。

    不排序键，保留快照插入顺序；不使用 ``default``、``repr`` 或字符替换。
    ``allow_nan=False`` 与显式预检共同保证 encode 阶段不会藏掉非法状态。
    """
    if not isinstance(state, dict):
        raise TypeError("state must be a dict")
    _validate_json_value(state, set())
    text = json.dumps(state, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False)
    payload = text.encode("utf-8")
    return EncodedState(payload=payload, length=len(payload),
                        sha256=hashlib.sha256(payload).hexdigest())


class _PublishDeadline(TimeoutError):
    """No new replace may start after the caller's publication deadline."""


class ServerStore:
    """线程安全的全量快照持久化；节流/捕获/对账由 Hub 管理。"""

    def __init__(self, path: str, *, create_parent: bool = True,
                 unique_temp: bool = False, replace_retry_budget: float = 0.0) -> None:
        self._path = os.path.abspath(path)
        self._lock = threading.Lock()
        self._hub_writer = None
        self._hub_permit = threading.local()
        self._last_save_result: SaveResult | None = None
        self._save_generation = 0
        self._unique_temp = unique_temp
        if (not math.isfinite(replace_retry_budget) or replace_retry_budget < 0
                or (replace_retry_budget and not unique_temp)):
            raise ValueError('replace retry requires an owned unique temporary file')
        self._replace_retry_budget = replace_retry_budget
        if create_parent:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)

    def _bind_hub_writer(self, callback) -> None:
        """绑定活动 Hub 的兼容入口；独立 ServerStore 不设置该回调。"""
        self._hub_writer = callback

    @contextmanager
    def _hub_write_permit(self, *, deadline=None):
        """仅供 Hub 现有 writer 进入真实 bytes IO 的私有 permit。"""
        old = getattr(self._hub_permit, "active", False)
        old_deadline = getattr(self._hub_permit, 'deadline', None)
        self._hub_permit.active = True
        self._hub_permit.deadline = deadline
        try:
            yield
        finally:
            self._hub_permit.active = old
            self._hub_permit.deadline = old_deadline

    def load(self) -> dict:
        """读 state.json；缺失/JSON 损坏/残留 .tmp → 返回 {}，绝不抛异常。"""
        with self._lock:
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                return data if isinstance(data, dict) else {}
            except (OSError, ValueError, TypeError):
                return {}

    @staticmethod
    def _payload_meta(payload: bytes) -> tuple[int, str]:
        return len(payload), hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _owns_temp(path, identity, payload=None):
        """Check the originally created file, never a replacement or link."""
        if identity is None:
            return False
        try:
            info = os.lstat(path)
            if (not stat.S_ISREG(info.st_mode)
                    or getattr(info, 'st_file_attributes', 0) & 0x400
                    or (info.st_dev, info.st_ino) != identity):
                return False
            if payload is None:
                return True
            with open(path, 'rb') as stream:
                opened = os.fstat(stream.fileno())
                return ((opened.st_dev, opened.st_ino) == identity
                        and opened.st_size == len(payload)
                        and stream.read(len(payload) + 1) == payload)
        except OSError:
            return False

    def save_bytes(self, payload: bytes) -> SaveResult:
        """原子写入一份已编码 payload，并报告真实阶段结果。

        ``save_bytes`` 不编码、不解析、不读取旧文件。replace 调用一旦开始
        却抛出异常，效果不可证时返回 ``uncertain``；cleanup 只清理临时文件，
        且不会覆盖最初阶段错误。
        """
        if (self._hub_writer is not None
                and not getattr(self._hub_permit, "active", False)):
            return self._hub_writer("bytes", payload)
        if not isinstance(payload, bytes):
            return SaveResult("not_committed", "encode", "payload_not_bytes",
                              False, 0, None)
        length, digest = self._payload_meta(payload)
        tmp = self._path + (".tmp-" + secrets.token_hex(12)
                            if self._unique_temp else ".tmp")
        fh = None
        replaced = False
        replace_attempted = False
        temp_created = False
        temp_identity = None
        stage = "open"
        first_error: BaseException | None = None
        with self._lock:
            try:
                fh = open(tmp, "xb" if self._unique_temp else "wb")
                temp_created = True
                if self._unique_temp:
                    created = os.fstat(fh.fileno())
                    temp_identity = (created.st_dev, created.st_ino)
                stage = "write"
                offset = 0
                while offset < length:
                    written = fh.write(payload[offset:])
                    if (isinstance(written, bool)
                            or not isinstance(written, int)
                            or written <= 0
                            or written > length - offset):
                        raise OSError("invalid short write result")
                    offset += written
                stage = "flush"
                fh.flush()
                stage = "fsync"
                os.fsync(fh.fileno())
                stage = "close"
                fh.close()
                fh = None
                stage = "replace"
                deadline = (time.monotonic() + self._replace_retry_budget
                            if self._replace_retry_budget else None)
                caller_deadline = getattr(self._hub_permit, 'deadline', None)
                if caller_deadline is not None:
                    deadline = (caller_deadline if deadline is None
                                else min(deadline, caller_deadline))
                last_refusal = None
                while True:
                    if deadline is not None and time.monotonic() >= deadline:
                        if last_refusal is not None:
                            raise last_refusal
                        raise _PublishDeadline('publication deadline expired')
                    replace_attempted = True
                    try:
                        os.replace(tmp, self._path)
                        break
                    except OSError as exc:
                        if (not self._replace_retry_budget
                                or getattr(exc, 'winerror', None) not in (5, 32, 33)
                                or not self._owns_temp(tmp, temp_identity, payload)):
                            raise
                        last_refusal = exc
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise
                        time.sleep(min(0.01, remaining))
                replaced = True
                return SaveResult("committed", "replace", None, False,
                                  length, digest)
            except BaseException as exc:
                first_error = exc
                # Any exception raised while invoking replace is deliberately
                # uncertain: an injected wrapper may have completed replace
                # before raising, and this layer cannot prove the final file.
                effect = "uncertain" if replace_attempted else "not_committed"
                retryable = effect == "not_committed"
                code = 'replace_deadline' if isinstance(exc, _PublishDeadline) else f"{stage}_failed"
                return SaveResult(effect, stage, code, retryable,
                                  length, digest)
            finally:
                if fh is not None:
                    try:
                        fh.close()
                    except BaseException:
                        # A prior write/flush/fsync error remains authoritative;
                        # close cleanup must never mask it.
                        if first_error is None:
                            first_error = OSError("close failed")
                if not replaced and (not self._unique_temp or
                        (temp_created and self._owns_temp(tmp, temp_identity))):
                    try:
                        os.remove(tmp)
                    except BaseException:
                        pass

    def read_bytes_result(self) -> ReadResult:
        """只读取权威 state.json 原始 bytes，不回落到 tmp/备份或 ``{}``。"""
        with self._lock:
            try:
                with open(self._path, "rb") as fh:
                    payload = fh.read()
            except FileNotFoundError:
                return ReadResult("missing")
            except Exception:
                return ReadResult("read_error", error_code="read_failed")
            if not isinstance(payload, bytes):
                return ReadResult("read_error", error_code="payload_not_bytes")
            length, digest = self._payload_meta(payload)
            return ReadResult("bytes", payload, length, digest)

    def _save_encoded(self, encoded: EncodedState) -> SaveResult:
        """Hub private seam：已编码快照只进入一次 bytes IO。"""
        result = self.save_bytes(encoded.payload)
        self._last_save_result = result
        self._save_generation += 1
        return result

    def save(self, state: dict | EncodedState) -> bool:
        """兼容旧调用形状；公共 wrapper 只返回 committed bool。"""
        if (self._hub_writer is not None
                and not getattr(self._hub_permit, "active", False)):
            return bool(self._hub_writer("state", state))
        if isinstance(state, EncodedState):
            before = self._save_generation
            result = self._save_encoded(state)
            if (isinstance(result, SaveResult)
                    and self._save_generation == before):
                self._last_save_result = result
                self._save_generation += 1
            return result.effect == "committed"
        try:
            encoded = encode_state(state)
        except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError):
            return False
        return self._save_encoded(encoded).effect == "committed"
