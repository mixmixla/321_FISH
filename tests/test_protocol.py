# -*- coding: utf-8 -*-
"""protocol 封帧编解码单测"""
import pytest

from protocol import FrameReader, ProtocolError, MsgType, encode_frame


def test_roundtrip_simple():
    raw = encode_frame({"t": MsgType.CHAT.value, "from": 1, "text": "你好"}, b"")
    header, body = FrameReader().feed(raw)[0]
    assert header["t"] == "chat" and header["text"] == "你好"
    assert body == b""


def test_roundtrip_with_body():
    body = bytes(range(256))
    raw = encode_frame({"t": MsgType.FILE_DATA.value, "index": 7}, body)
    header, got = FrameReader().feed(raw)[0]
    assert header["index"] == 7 and header["body_len"] == 256
    assert got == body


def test_streaming_half_packets():
    raw = encode_frame({"t": "ping"}) + encode_frame({"t": "pong"}, b"xx")
    reader = FrameReader()
    frames = []
    for i in range(1, len(raw) + 1):
        frames += reader.feed(raw[i - 1:i])
    assert [(h["t"], b) for h, b in frames] == [("ping", b""), ("pong", b"xx")]


def test_multiple_frames_one_packet():
    raw = encode_frame({"t": "a"}) + encode_frame({"t": "b"})
    frames = FrameReader().feed(raw)
    assert [h["t"] for h, _ in frames] == ["a", "b"]


def test_oversize_header_rejected():
    raw = encode_frame({"t": "x", "big": "y" * 70000}, b"")
    # 构造一个伪造的超长 header_len
    import struct
    raw = struct.pack(">I", 70000) + b"x" * 70000
    with pytest.raises(ProtocolError):
        FrameReader().feed(raw)


def test_bad_json_rejected():
    import struct
    raw = struct.pack(">I", 5) + b"hello"
    with pytest.raises(ProtocolError):
        FrameReader().feed(raw)


def test_missing_t_rejected():
    import json, struct
    body = json.dumps({"a": 1}).encode()
    raw = struct.pack(">I", len(body)) + body
    with pytest.raises(ProtocolError):
        FrameReader().feed(raw)


def test_oversize_body_rejected():
    import struct
    # header_len 正常，但 body_len 超限
    import json
    h = json.dumps({"t": "x", "body_len": 10 * 1024 * 1024}).encode()
    raw = struct.pack(">I", len(h)) + h + b"\x00" * 10
    with pytest.raises(ProtocolError):
        FrameReader().feed(raw)
