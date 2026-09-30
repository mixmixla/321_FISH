# -*- coding: utf-8 -*-
"""文件分段传输纯逻辑（零 socket / 零 GUI，可注入路径与数据）：

- chunk_count / compute_md5：分块规划与流式 MD5（不整读大文件）
- ChunkPlanner：顺序取第一个未确认块（断点续传的核心）
- TransferMeta：收发双方/服务器共用的元数据（.meta.json 持久化）
- PartFile：.part 随机写 + 校验（md5/size）

状态推进由调用方编排（server 用 TransferMeta 记录撮合状态、file_client 用 _Xfer
管理并发），本模块只提供无副作用的纯数据结构，不做状态机。
"""
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum


class XferStatus(str, Enum):
    OFFERING = "offering"
    ACCEPTED = "accepted"       # 服务器撮合阶段：对方已接受，等待直连/中转
    TRANSFERRING = "transferring"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def chunk_count(size: int, chunk_size: int) -> int:
    return (size + chunk_size - 1) // chunk_size


def compute_md5(path: str, chunk_size: int = 65536, progress=None) -> str:
    """流式 MD5（FIPS 模式下 usedforsecurity=False 避免阻塞）"""
    md5 = hashlib.md5(usedforsecurity=False)
    total = os.path.getsize(path)
    done = 0
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk_size)
            if not block:
                break
            md5.update(block)
            done += len(block)
            if progress:
                progress(done, total)
    return md5.hexdigest()


@dataclass
class TransferMeta:
    """传输元数据（发送端内存态 / 接收端 .meta.json / 服务器撮合记录共用）。

    后四个字段是服务器撮合阶段的扩展态（nick/ip/端口/是否已直连），
    对收发双方持久化 .meta.json 无影响（默认值即可）。
    """
    file_id: str
    filename: str
    size: int
    chunk_size: int
    md5: str
    sender_uid: int = 0
    receiver_uid: int = 0
    total: int = 0
    acked: list = field(default_factory=list)      # 已确认块索引
    status: str = XferStatus.OFFERING.value
    created_at: float = field(default_factory=time.time)
    # ---- 服务器撮合扩展态 ----
    sender_nick: str = ""
    sender_ip: str = ""
    sender_port: int = 0
    direct: bool = False

    def __post_init__(self):
        if not self.total:
            self.total = chunk_count(self.size, self.chunk_size)
        if isinstance(self.acked, list):
            self.acked = list(dict.fromkeys(int(i) for i in self.acked))

    def acked_set(self) -> set:
        return set(self.acked)

    def next_chunk(self) -> int | None:
        """顺序取第一个未确认块；全确认返回 None"""
        acked = self.acked_set()
        for i in range(self.total):
            if i not in acked:
                return i
        return None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TransferMeta":
        return cls(**d)


def save_meta(path: str, meta: TransferMeta) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta.to_dict(), f, ensure_ascii=False)


def load_meta(path: str) -> TransferMeta | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return TransferMeta.from_dict(json.load(f))
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        return None


class ChunkPlanner:
    """顺序规划未确认块；acked 变化后 next_chunk 自动前移"""

    def __init__(self, total: int, acked: set[int] | None = None) -> None:
        self.total = total
        self.acked = set(acked or [])

    def next_chunk(self) -> int | None:
        for i in range(self.total):
            if i not in self.acked:
                return i
        return None

    def ack(self, index: int) -> None:
        self.acked.add(index)


class PartFile:
    """.part 随机写：块按 index*chunk_size 偏移落盘，支持乱序"""

    def __init__(self, part_path: str, expected_size: int, resume: bool = False) -> None:
        self.part_path = part_path
        self.expected_size = expected_size
        os.makedirs(os.path.dirname(os.path.abspath(part_path)), exist_ok=True)
        if resume and os.path.exists(part_path) \
                and os.path.getsize(part_path) == expected_size:
            self._fh = open(part_path, "r+b")     # 续传：保留已落盘块
        else:
            self._fh = open(part_path, "wb")
            if expected_size > 0:                 # 空文件无需预分配（seek(-1) 非法）
                self._fh.seek(expected_size - 1)
                self._fh.write(b"\x00")
                self._fh.flush()

    def write_chunk(self, index: int, data: bytes, chunk_size: int) -> None:
        """随机写一块；越界（offset+len 超出预期大小）或块超长一律拒绝，防磁盘被恶意撑爆"""
        if index < 0 or len(data) > chunk_size:
            raise ValueError(f"bad chunk: index={index} len={len(data)} > {chunk_size}")
        offset = index * chunk_size
        if offset + len(data) > self.expected_size:
            raise ValueError(f"chunk overflow: offset={offset} len={len(data)} "
                             f"size={self.expected_size}")
        self._fh.seek(offset)
        self._fh.write(data)
        self._fh.flush()

    def verify(self, md5: str, chunk_size: int = 65536) -> bool:
        """校验 size 与 MD5"""
        self._fh.flush()
        if os.path.getsize(self.part_path) != self.expected_size:
            return False
        return compute_md5(self.part_path, chunk_size) == md5

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass
