# -*- coding: utf-8 -*-
"""文件分块/续传状态机单测"""
import hashlib
import os
import random

import pytest

from filexfer import (ChunkPlanner, PartFile, TransferMeta,
                      XferStatus, chunk_count, compute_md5, load_meta,
                      save_meta)


def _make_file(path, size):
    rnd = random.Random(42)
    data = bytes(rnd.randrange(256) for _ in range(size))
    with open(path, "wb") as f:
        f.write(data)
    return data


def test_chunk_count():
    assert chunk_count(0, 65536) == 0
    assert chunk_count(65536, 65536) == 1
    assert chunk_count(65537, 65536) == 2


def test_planner_skips_acked():
    p = ChunkPlanner(total=10, acked={0, 1, 2})
    assert p.next_chunk() == 3
    p.ack(3)
    assert p.next_chunk() == 4
    for i in range(4, 10):
        p.ack(i)
    assert p.next_chunk() is None


def test_compute_md5_streaming(tmp_path):
    src = tmp_path / "a.bin"
    data = _make_file(str(src), 200_000)
    md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()
    assert compute_md5(str(src), 65536) == md5


def test_partfile_random_write_matches_source(tmp_path):
    src = tmp_path / "src.bin"
    data = _make_file(str(src), 150_000)
    chunk = 65536
    total = chunk_count(len(data), chunk)
    part = tmp_path / "out.part"
    pf = PartFile(str(part), len(data))
    order = list(range(total))
    random.Random(7).shuffle(order)          # 乱序写入
    for i in order:
        block = data[i * chunk:(i + 1) * chunk]
        pf.write_chunk(i, block, chunk)
    pf.close()
    with open(part, "rb") as f:
        assert f.read() == data
    md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()
    assert compute_md5(str(part), chunk) == md5


def test_meta_roundtrip(tmp_path):
    meta = TransferMeta(file_id="f1", filename="报表.xlsx", size=1000,
                        chunk_size=512, md5="abc", sender_uid=1, receiver_uid=2)
    path = tmp_path / "m.json"
    save_meta(str(path), meta)
    loaded = load_meta(str(path))
    assert loaded.file_id == "f1"
    assert loaded.next_chunk() == 0


def test_resume_next_chunk_from_acked():
    meta = TransferMeta(file_id="f", filename="x", size=10, chunk_size=10,
                        md5="m", total=5, acked=[0, 1, 2])
    assert meta.next_chunk() == 3


def test_meta_status_and_ext_fields():
    """服务器撮合扩展态字段随 to_dict/from_dict 往返无损（M4 收敛后兼容旧 meta）"""
    meta = TransferMeta(file_id="f", filename="x", size=10, chunk_size=10,
                        md5="m", sender_uid=1, receiver_uid=2,
                        sender_nick="小明", sender_ip="127.0.0.1",
                        sender_port=40000, direct=True,
                        status=XferStatus.ACCEPTED.value)
    d = meta.to_dict()
    assert d["sender_nick"] == "小明" and d["direct"] is True
    assert d["status"] == "accepted"
    again = TransferMeta.from_dict(d)
    assert again.sender_ip == "127.0.0.1" and again.status == "accepted"
    # 旧版 meta（无扩展字段）加载仍兼容
    legacy = {k: v for k, v in d.items()
              if k not in ("sender_nick", "sender_ip", "sender_port", "direct")}
    old = TransferMeta.from_dict(legacy)
    assert old.sender_nick == "" and old.direct is False
