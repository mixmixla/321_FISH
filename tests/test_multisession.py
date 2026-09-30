# -*- coding: utf-8 -*-
"""R批次③ 单元测试：
1) 同 uid 多 session 并存（桌面+网页不顶号）；
2) _chan_recipients/_route 按 uid 广播到该 uid 全部端；
3) 已读回执(read)事件广播到该 uid 多端；
4) 仅当最后一个端离线才真正下线（广播「已下线」、移出在线集）；
5) vosk 转录降级：vosk/模型缺失时不崩溃，抛受控 OptionalMissing。
纯内存 Hub（不起网络服务器），无 Tk 依赖，可独立运行。
"""
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, Session
import optional
from optional import OptionalMissing


class _Rec:
    """记录本会话收到的所有帧（供断言）。"""

    def __init__(self) -> None:
        self.frames = []

    def send(self, payload: dict, body: bytes = b"") -> None:
        self.frames.append(payload)


def _mk_hub(tmp_path) -> Hub:
    return Hub(cfg=replace(CFG, audit_dir=str(tmp_path / "audit")))


def _two_sessions(tmp_path):
    """构造同 uid 的两端会话并 attach，返回 (hub, a1rec, a2rec, a1, a2, brec, b)。"""
    h = _mk_hub(tmp_path)
    r1, r2, rb = _Rec(), _Rec(), _Rec()
    a1 = Session(0, "multi", "tcp", "127.0.0.1", r1.send)
    a2 = Session(0, "multi", "web", "127.0.0.1", r2.send)
    b = Session(0, "bob", "tcp", "127.0.0.1", rb.send)
    assert h._attach(a1)
    assert h._attach(a2)
    assert h._attach(b)
    return h, r1, r2, a1, a2, rb, b


def test_same_uid_multisession_coexist(tmp_path):
    """同一昵称登录第二端不再顶号；同一 uid；在线集按 uid 唯一但两端都在。
    顺序：bob 在线 → multi 第一端上线 → multi 第二端上线（不应重复广播「已上线」）。"""
    h = _mk_hub(tmp_path)
    rb, r1, r2 = _Rec(), _Rec(), _Rec()
    b = Session(0, "bob", "tcp", "127.0.0.1", rb.send)
    a1 = Session(0, "multi", "tcp", "127.0.0.1", r1.send)
    a2 = Session(0, "multi", "web", "127.0.0.1", r2.send)
    assert h._attach(b)
    assert h._attach(a1)
    assert h._attach(a2)                                 # 第二端不顶号
    assert a1.uid == a2.uid
    assert len(h._uid_clients[a1.uid]) == 2              # 两端并存
    assert a1.uid in h.sessions                          # uid 仍在在线集
    # 两端各自拿到 welcome
    assert any(f.get("t") == "welcome" for f in r1.frames)
    assert any(f.get("t") == "welcome" for f in r2.frames)
    # 第二端上线不重复广播「已上线」：旁观者 bob 仅见一次 multi 上线
    sys_bob = [f.get("text") for f in rb.frames if f.get("t") == "system"]
    assert sys_bob.count("multi 已上线") == 1


def test_route_fans_out_to_all_uid_sessions(tmp_path):
    """新消息按 uid 投递到该 uid 的全部会话（web+桌面都收到）。"""
    h, r1, r2, a1, a2, _rb, b = _two_sessions(tmp_path)
    h._route({"t": "chat", "channel": "private", "uid": b.uid,
              "to": a1.uid, "text": "x"})
    assert any(f.get("text") == "x" for f in r1.frames)
    assert any(f.get("text") == "x" for f in r2.frames)


def test_read_broadcast_to_uid_multisession(tmp_path):
    """A 端已读 → 本 uid 两端都收到 read 事件（一端已读另一端不再显示未读）。"""
    h, r1, r2, a1, a2, _rb, _b = _two_sessions(tmp_path)
    h._on_read(a2, {"t": "read", "channel": "public", "seq": 42})
    got1 = [f for f in r1.frames if f.get("t") == "read" and f.get("seq") == 42]
    got2 = [f for f in r2.frames if f.get("t") == "read" and f.get("seq") == 42]
    assert got1 and got2


def test_offline_only_when_last_session(tmp_path):
    """关闭一端（仍有另一端在线）不真正下线；最后一个端离线才移出在线集。"""
    h, _r1, _r2, a1, a2, _rb, _b = _two_sessions(tmp_path)
    h.unregister(a1, "test")
    assert a1.uid in h.sessions          # a2 还在 → 该 uid 仍在线
    h.unregister(a2, "test")
    assert a2.uid not in h.sessions      # 全离线 → 移出在线集
    assert a2.uid not in h._uid_clients


def test_transcribe_degrade_when_vosk_missing(monkeypatch):
    """vosk/模型缺失：transcribe_wav 抛受控 OptionalMissing，不崩进程。"""
    monkeypatch.setattr(optional, "has_stt", lambda: False)
    with pytest.raises(OptionalMissing):
        optional.transcribe_wav("noop.wav", "")
    # 模型目录缺失（即使 vosk 假定存在）也为受控异常
    monkeypatch.setattr(optional, "has_stt", lambda: True)
    with pytest.raises(OptionalMissing):
        optional.transcribe_wav("noop.wav", "")