# -*- coding: utf-8 -*-
"""R72 回归：多人语音房 · 论坛频道 · 位置共享 · 圆形视频留言。

覆盖：
- 语音房：入房上限（voice_room_max=6）、ROOM_PEERS 全量下发、ROOM_ADDR 广播、
  退房名册更新、空房删除、非群成员 group:<gid> 被拒
- 论坛频道：kind="forum" 可自由发言（不被频道只读拦）；thread_root 回复在历史中
  带标记，THREAD_FETCH 可按根 seq 过滤
- 位置共享：_san_geo 非法坐标丢弃 / name 截断 / live+expire 归一；
  GEO_LIVE 广播不入历史；GEO_STOP 广播
- 视频留言：VMA1 pack/unpack 往返一致；服务器存储 + 透传；
  TTL 淘汰；超限拒收
- 纯逻辑：mix_frames 饱和相加、rms_level、geo_api.parse 各格式
"""
import array
import os
import socket
import struct
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from protocol import MsgType
from server import Hub, serve as serve_tcp

import optional


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    time.sleep(0.2)
    yield h, port, stop
    stop.set()
    time.sleep(0.2)


class _Cli:
    """原始帧客户端：直发 JSON 头，便于构造非标准负载。"""
    __test__ = False

    def __init__(self, port, nick):
        from crypto import client_handshake
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.chan = client_handshake(self.sock)
        self.nick = nick
        self.uid = None
        self.events = []
        self._lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            while True:
                h, b = self.chan.recv_frame()
                with self._lock:
                    self.events.append((h, b))
        except Exception:
            pass

    def send(self, header, body=b""):
        self.chan.send_frame(header, body)

    def wait(self, t, timeout=3.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, (h, b) in enumerate(self.events):
                    if h.get("t") == t and (pred is None or pred(h)):
                        del self.events[i]
                        return h, b
            time.sleep(0.01)
        return None, None

    def hello(self):
        self.send({"t": "hello", "nick": self.nick})
        h, _ = self.wait("welcome")
        if h:
            self.uid = h["uid"]
        return h

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def _mk_group(owner, name="测试群", forum=False, channel=False):
    """owner 建群并返回 (gid, group_state)。forum=True → 论坛频道；channel=True → 频道。"""
    hdr = {"t": "group_create", "name": name, "public": True}
    if forum:
        hdr["forum"] = True
    if channel:
        hdr["broadcast"] = True
    owner.send(hdr)
    gs, _ = owner.wait("group_state", pred=lambda x: x.get("name") == name)
    assert gs, "群未创建"
    return gs["gid"], gs


def _join_group(cli, gid):
    cli.send({"t": "group_join", "gid": gid})
    assert cli.wait("group_state", pred=lambda x: x.get("gid") == gid)


# ================ 纯逻辑：voice_room.mix_frames / rms_level ================

def test_mix_frames_saturation():
    """两路全幅正值相加应饱和到 32767，不溢出。"""
    from voice_room import mix_frames, _AUDIO_FRAME
    a = array.array("h", [32767] * (_AUDIO_FRAME // 2)).tobytes()
    b = array.array("h", [32767] * (_AUDIO_FRAME // 2)).tobytes()
    out = mix_frames([a, b])
    assert len(out) == _AUDIO_FRAME
    arr = array.array("h")
    arr.frombytes(out)
    assert all(v == 32767 for v in arr)


def test_mix_frames_empty_returns_silence():
    from voice_room import mix_frames, _AUDIO_FRAME
    out = mix_frames([])
    assert out == b"\x00" * _AUDIO_FRAME


def test_mix_frames_none_entries_skipped():
    from voice_room import mix_frames, _AUDIO_FRAME
    a = array.array("h", [100] * (_AUDIO_FRAME // 2)).tobytes()
    out = mix_frames([None, a, b""])
    arr = array.array("h")
    arr.frombytes(out)
    assert all(v == 100 for v in arr)


def test_rms_level_silence():
    from voice_room import rms_level
    assert rms_level(b"\x00" * 320) == 0.0


def test_rms_level_signal():
    from voice_room import rms_level
    pcm = array.array("h", [6000] * 160).tobytes()
    level = rms_level(pcm)
    assert 0.0 < level <= 1.0


# ================ 纯逻辑：geo_api.parse / osm_url ================

def test_geo_parse_standard_pair():
    from geo_api import parse
    r = parse("39.9042,116.4074")
    assert r is not None
    assert r["lat"] == 39.9042
    assert r["lon"] == 116.4074
    assert not r["ambiguous"]


def test_geo_parse_swapped_order():
    """116 > 90 → 自动判定为经度在前，交换。"""
    from geo_api import parse
    r = parse("116.4074,39.9042")
    assert r is not None
    assert r["lat"] == 39.9042
    assert r["lon"] == 116.4074
    assert not r["ambiguous"]


def test_geo_parse_ambiguous():
    """两个数都 ≤ 90 → ambiguous=True。"""
    from geo_api import parse
    r = parse("20,30")
    assert r is not None
    assert r["ambiguous"]


def test_geo_parse_geo_scheme():
    from geo_api import parse
    r = parse("geo:39.9042,116.4074")
    assert r is not None
    assert r["lat"] == 39.9042
    assert r["lon"] == 116.4074


def test_geo_parse_url_with_lat_lng():
    from geo_api import parse
    r = parse("https://maps.example.com/?lat=39.9042&lng=116.4074")
    assert r is not None
    assert r["lat"] == 39.9042
    assert r["lon"] == 116.4074


def test_geo_parse_invalid_text():
    from geo_api import parse
    assert parse("你好世界") is None
    assert parse("") is None
    assert parse(None) is None


def test_geo_valid():
    from geo_api import valid
    assert valid(39.9, 116.4)
    assert not valid(91.0, 116.4)
    assert not valid(39.9, 181.0)
    assert not valid("abc", "def")


def test_geo_format_pair():
    from geo_api import format_pair
    s = format_pair(39.9042, 116.4074)
    assert "39.904200" in s
    assert "116.407400" in s


def test_geo_osm_url():
    from geo_api import osm_url
    url = osm_url(39.9042, 116.4074)
    assert "openstreetmap.org" in url
    assert "39.904200" in url
    assert "116.407400" in url
    assert "map=16" in url


def test_geo_osm_url_zoom_clamp():
    from geo_api import osm_url
    url = osm_url(39.9, 116.4, zoom=99)
    assert "map=19" in url
    url = osm_url(39.9, 116.4, zoom=0)
    assert "map=1" in url


# ================ 纯逻辑：vmemo_api pack/unpack ================

def _fake_png(w=160, h=120):
    """构造一个最小合法 PNG（8×8 纯色也行，unpack 不验证内容）。"""
    import struct as st
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = st.pack(">I", 13) + b"IHDR" + st.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    ihdr_crc = st.pack(">I", 0xDEADBEEF)
    idat_len = st.pack(">I", 10)
    idat = b"IDAT" + b"\x00" * 10
    idat_crc = st.pack(">I", 0xCAFEBABE)
    iend = st.pack(">I", 0) + b"IEND" + st.pack(">I", 0xAE426082)
    return sig + ihdr + ihdr_crc + idat_len + idat + idat_crc + iend


def test_vmemo_pack_unpack_roundtrip():
    from vmemo_api import pack, unpack, MAGIC, VER
    f1 = _fake_png()
    f2 = _fake_png()
    pcm = b"\x00\x01" * 8000
    blob = pack([f1, f2], pcm, fps=8, w=160, h=120, dur_ms=250)
    d = unpack(blob)
    assert d["ver"] == VER
    assert d["has_audio"]
    assert d["n_frames"] == 2
    assert d["dur_ms"] == 250
    assert d["fps"] == 8.0
    assert d["w"] == 160
    assert d["h"] == 120
    assert d["frames"][0] == f1
    assert d["frames"][1] == f2
    assert d["pcm"] == pcm


def test_vmemo_pack_no_audio():
    from vmemo_api import pack, unpack
    f = _fake_png()
    blob = pack([f], fps=5, w=160, h=120, dur_ms=200)
    d = unpack(blob)
    assert not d["has_audio"]
    assert d["pcm"] == b""


def test_vmemo_unpack_bad_magic():
    from vmemo_api import unpack
    with pytest.raises(ValueError, match="magic"):
        unpack(b"XXXX" + b"\x00" * 40)


def test_vmemo_unpack_too_short():
    from vmemo_api import unpack
    with pytest.raises(ValueError, match="过短"):
        unpack(b"\x00" * 10)


def test_vmemo_first_frame_png():
    from vmemo_api import pack, first_frame_png
    f = _fake_png()
    blob = pack([f, f], fps=8, dur_ms=250)
    ff = first_frame_png(blob)
    assert ff == f


def test_vmemo_first_frame_bad_blob():
    from vmemo_api import first_frame_png
    assert first_frame_png(b"garbage") is None


def test_vmemo_describe():
    from vmemo_api import pack, describe
    f = _fake_png()
    blob = pack([f, f, f], b"\x00" * 100, fps=8, dur_ms=375)
    meta = describe(blob)
    assert meta is not None
    assert meta["n_frames"] == 3
    assert meta["has_audio"]
    assert meta["dur_ms"] == 375


# ================ 服务器：语音房 ================

def test_room_join_and_state(hub):
    """入房后收到 ROOM_STATE，名册含自己。"""
    h, port, _ = hub
    a = _Cli(port, "阿龙")
    a.hello()
    a.send({"t": MsgType.ROOM_JOIN.value, "room": "public"})
    st, _ = a.wait(MsgType.ROOM_STATE.value)
    assert st is not None
    assert st["room"] == "public"
    assert st["count"] == 1
    assert any(m["uid"] == a.uid for m in st["members"])
    a.close()


def test_room_join_limit(hub):
    """第 7 人入房被拒（voice_room_max=6）。"""
    h, port, _ = hub
    clis = []
    for i in range(6):
        c = _Cli(port, f"u{i}")
        c.hello()
        c.send({"t": MsgType.ROOM_JOIN.value, "room": "public"})
        assert c.wait(MsgType.ROOM_STATE.value)
        clis.append(c)
    g = _Cli(port, "老七")
    g.hello()
    g.send({"t": MsgType.ROOM_JOIN.value, "room": "public"})
    err, _ = g.wait("error", timeout=3.0,
                   pred=lambda x: x.get("code") == "room_full")
    assert err is not None
    assert "6" in err.get("text", "")
    for c in clis + [g]:
        c.close()


def test_room_peers_sent_to_newcomer(hub):
    """新入房者收到 ROOM_PEERS（含已在房者地址）。"""
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    a.send({"t": MsgType.ROOM_JOIN.value, "room": "public"})
    assert a.wait(MsgType.ROOM_STATE.value)
    a.send({"t": MsgType.ROOM_ADDR.value, "room": "public", "port": 50001})
    b = _Cli(port, "乙")
    b.hello()
    b.send({"t": MsgType.ROOM_JOIN.value, "room": "public"})
    # b 应收到 ROOM_STATE + ROOM_PEERS
    assert b.wait(MsgType.ROOM_STATE.value)
    peers, _ = b.wait(MsgType.ROOM_PEERS.value)
    assert peers is not None
    assert any(p["uid"] == a.uid for p in peers.get("peers", []))
    a.close()
    b.close()


def test_room_addr_broadcast(hub):
    """上报端口后，房内其他人收到 ROOM_ADDR。"""
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    a.send({"t": MsgType.ROOM_JOIN.value, "room": "public"})
    assert a.wait(MsgType.ROOM_STATE.value)
    b = _Cli(port, "乙")
    b.hello()
    b.send({"t": MsgType.ROOM_JOIN.value, "room": "public"})
    assert b.wait(MsgType.ROOM_STATE.value)
    # b 上报端口 → a 应收到 ROOM_ADDR
    b.send({"t": MsgType.ROOM_ADDR.value, "room": "public", "port": 50002})
    addr, _ = a.wait(MsgType.ROOM_ADDR.value, timeout=3.0)
    assert addr is not None
    assert addr["uid"] == b.uid
    assert addr["port"] == 50002
    a.close()
    b.close()


def test_room_leave_broadcast(hub):
    """退房后其他人收到 ROOM_STATE 人数 -1；全员退房后空房键被删。"""
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    a.send({"t": MsgType.ROOM_JOIN.value, "room": "public"})
    assert a.wait(MsgType.ROOM_STATE.value)
    b = _Cli(port, "乙")
    b.hello()
    b.send({"t": MsgType.ROOM_JOIN.value, "room": "public"})
    assert b.wait(MsgType.ROOM_STATE.value)
    # a 退房 → b 收到 count=1 的 ROOM_STATE
    a.send({"t": MsgType.ROOM_LEAVE.value, "room": "public"})
    st, _ = b.wait(MsgType.ROOM_STATE.value, timeout=3.0,
                  pred=lambda x: x.get("count") == 1)
    assert st is not None
    assert st["count"] == 1
    # b 也退房 → 空房键应被删
    b.send({"t": MsgType.ROOM_LEAVE.value, "room": "public"})
    time.sleep(0.2)
    assert "public" not in h.voice_rooms
    a.close()
    b.close()


def test_room_requires_group_member(hub):
    """非群成员用 group:<gid> 入房被拒。"""
    h, port, _ = hub
    owner = _Cli(port, "群主")
    owner.hello()
    gid, _ = _mk_group(owner, "私群")
    outsider = _Cli(port, "外人")
    outsider.hello()
    outsider.send({"t": MsgType.ROOM_JOIN.value, "room": f"group:{gid}"})
    err, _ = outsider.wait("error", timeout=3.0,
                           pred=lambda x: x.get("code") == "room")
    assert err is not None
    owner.close()
    outsider.close()


def test_room_group_member_can_join(hub):
    """群成员可用 group:<gid> 入房。"""
    h, port, _ = hub
    owner = _Cli(port, "群主")
    owner.hello()
    gid, _ = _mk_group(owner, "语音群")
    member = _Cli(port, "成员")
    member.hello()
    _join_group(member, gid)
    member.send({"t": MsgType.ROOM_JOIN.value, "room": f"group:{gid}"})
    st, _ = member.wait(MsgType.ROOM_STATE.value)
    assert st is not None
    assert st["room"] == f"group:{gid}"
    owner.close()
    member.close()


# ================ 服务器：论坛频道 ================

def test_group_state_carries_kind(hub):
    """频道/论坛/普通群的 kind 正确下发。"""
    h, port, _ = hub
    owner = _Cli(port, "群主")
    owner.hello()
    # 论坛
    gid_f, gs_f = _mk_group(owner, "论坛A", forum=True)
    assert gs_f["kind"] == "forum"
    # 频道
    gid_c, gs_c = _mk_group(owner, "频道B", channel=True)
    assert gs_c["kind"] == "channel"
    # 普通群
    gid_n, gs_n = _mk_group(owner, "普通群C")
    assert gs_n["kind"] == ""
    owner.close()


def test_forum_not_readonly(hub):
    """kind=="forum" 可自由发言（不被频道只读拦）。"""
    h, port, _ = hub
    owner = _Cli(port, "坛主")
    owner.hello()
    gid, _ = _mk_group(owner, "技术论坛", forum=True)
    member = _Cli(port, "坛友")
    member.hello()
    _join_group(member, gid)
    # 非创建者发贴 → 应成功（无 readonly 拒绝）
    member.send({"t": "chat", "channel": "group", "to": gid,
                "text": "论坛第一贴"})
    msg, _ = member.wait("chat", pred=lambda x: x.get("text") == "论坛第一贴")
    assert msg is not None
    assert msg.get("vmemo") is None  # 普通文本消息
    owner.close()
    member.close()


def test_forum_threads_tagged_in_history(hub):
    """带 thread_root 的回复在历史中带标记，THREAD_FETCH 可按根 seq 过滤。"""
    h, port, _ = hub
    owner = _Cli(port, "坛主")
    owner.hello()
    gid, _ = _mk_group(owner, "话题论坛", forum=True)
    member = _Cli(port, "坛友")
    member.hello()
    _join_group(member, gid)
    # 发主贴
    member.send({"t": "chat", "channel": "group", "to": gid,
                "text": "主贴标题"})
    root_msg, _ = member.wait("chat",
                              pred=lambda x: x.get("text") == "主贴标题")
    assert root_msg is not None
    root_seq = root_msg["seq"]
    # 发回复（带 thread_root）
    member.send({"t": "chat", "channel": "group", "to": gid,
                "text": "这是回复", "thread_root": root_seq})
    reply_msg, _ = member.wait("chat",
                               pred=lambda x: x.get("text") == "这是回复")
    assert reply_msg is not None
    assert reply_msg.get("thread_root") == root_seq
    # THREAD_FETCH 应返回该回复
    member.send({"t": MsgType.THREAD_FETCH.value, "channel": "group",
                "to": gid, "root_seq": root_seq})
    th, _ = member.wait(MsgType.THREAD_HISTORY.value)
    assert th is not None
    assert len(th["msgs"]) == 1
    assert th["msgs"][0]["text"] == "这是回复"
    owner.close()
    member.close()


# ================ 服务器：位置共享 ================

def test_geo_whitelist_and_sanitize(hub):
    """非法 lat/lon 整体丢弃；name 截断；live+expire 归一。"""
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    b = _Cli(port, "乙")
    b.hello()
    # 合法位置卡片
    a.send({"t": "chat", "channel": "private", "to": b.uid,
            "text": "我在这里", "geo": {"lat": 39.9042, "lon": 116.4074,
                                        "name": "天安门广场"}})
    msg, _ = b.wait("chat", pred=lambda x: x.get("geo"))
    assert msg is not None
    assert msg["geo"]["lat"] == 39.9042
    assert msg["geo"]["lon"] == 116.4074
    assert msg["geo"]["name"] == "天安门广场"
    assert "live" not in msg["geo"]  # 非 live 不带 live/expire/session

    # 非法经纬度 → geo 丢弃，但消息本身仍送达（如果有 text）
    a.send({"t": "chat", "channel": "private", "to": b.uid,
            "text": "坏坐标", "geo": {"lat": 999, "lon": 116.4}})
    msg2, _ = b.wait("chat", pred=lambda x: x.get("text") == "坏坐标")
    assert msg2 is not None
    assert "geo" not in msg2

    # name 超长截断
    long_name = "X" * 200
    a.send({"t": "chat", "channel": "private", "to": b.uid,
            "text": "长名", "geo": {"lat": 30.0, "lon": 120.0,
                                    "name": long_name}})
    msg3, _ = b.wait("chat", pred=lambda x: x.get("text") == "长名")
    assert msg3 is not None
    assert len(msg3["geo"]["name"]) <= 64
    a.close()
    b.close()


def test_geo_live_not_in_history(hub):
    """GEO_LIVE 广播但不入历史（与 typing 同待遇）。"""
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    b = _Cli(port, "乙")
    b.hello()
    a.send({"t": MsgType.GEO_LIVE.value, "channel": "private", "to": b.uid,
            "geo": {"lat": 39.9, "lon": 116.4, "live": 1,
                    "expire": time.time() + 300, "session": "s1"}})
    gl, _ = b.wait(MsgType.GEO_LIVE.value)
    assert gl is not None
    assert gl["geo"]["lat"] == 39.9
    assert gl["geo"]["live"] == 1
    # 拉历史 → 不含 GEO_LIVE
    a.send({"t": MsgType.HISTORY.value, "channel": "private", "to": b.uid})
    hist, _ = a.wait("history")
    assert hist is not None
    assert all(m.get("t") != "geo_live" for m in hist["msgs"])
    a.close()
    b.close()


def test_geo_stop_broadcast(hub):
    """GEO_STOP 广播给对端。"""
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    b = _Cli(port, "乙")
    b.hello()
    a.send({"t": MsgType.GEO_STOP.value, "channel": "private", "to": b.uid,
            "session": "s1"})
    gs, _ = b.wait(MsgType.GEO_STOP.value)
    assert gs is not None
    assert gs.get("session") == "s1"
    a.close()
    b.close()


# ================ 服务器：视频留言 ================

def test_vmemo_stored_and_forwarded(hub):
    """VMEMO 存入 _vmemo 表并透传给收件人。"""
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    b = _Cli(port, "乙")
    b.hello()
    blob = _fake_png()
    from vmemo_api import pack
    vma1 = pack([blob, blob], b"\x00" * 100, fps=8, dur_ms=250)
    a.send({"t": MsgType.VMEMO.value, "channel": "private", "to": b.uid,
            "duration": 2.5}, vma1)
    msg, body = b.wait("chat",
                       pred=lambda x: x.get("vmemo") is True)
    assert msg is not None
    assert msg["duration"] == 2.5
    assert body == vma1  # body 透传
    seq = msg["seq"]
    assert seq in h._vmemo
    assert h._vmemo[seq] == vma1
    a.close()
    b.close()


def test_vmemo_ttl_sweep(hub):
    """过期后 _vmemo 被 _sweep_stale_voice 清空。"""
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    b = _Cli(port, "乙")
    b.hello()
    blob = _fake_png()
    from vmemo_api import pack
    vma1 = pack([blob], b"", fps=8, dur_ms=100)
    a.send({"t": MsgType.VMEMO.value, "channel": "private", "to": b.uid,
            "duration": 0.1}, vma1)
    msg, _ = b.wait("chat", pred=lambda x: x.get("vmemo") is True)
    assert msg is not None
    seq = msg["seq"]
    assert seq in h._vmemo
    # 把时间戳改到很久以前
    with h.lock:
        h._vmemo_ts[seq] = 0.0
    h._sweep_stale_voice()
    assert seq not in h._vmemo
    assert seq not in h._vmemo_ts
    a.close()
    b.close()


def test_vmemo_max_bytes_rejected(hub):
    """超过 vmemo_max_bytes 的 blob 被拒。"""
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    b = _Cli(port, "乙")
    b.hello()
    oversized = b"\x00" * (CFG.vmemo_max_bytes + 1)
    a.send({"t": MsgType.VMEMO.value, "channel": "private", "to": b.uid,
            "duration": 1.0}, oversized)
    err, _ = a.wait("error", timeout=3.0,
                    pred=lambda x: x.get("code") == "big")
    assert err is not None
    a.close()
    b.close()


def test_vmemo_empty_rejected(hub):
    """空 body 被拒。"""
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    b = _Cli(port, "乙")
    b.hello()
    a.send({"t": MsgType.VMEMO.value, "channel": "private", "to": b.uid,
            "duration": 1.0}, b"")
    err, _ = a.wait("error", timeout=3.0,
                    pred=lambda x: x.get("code") == "empty")
    assert err is not None
    a.close()
    b.close()


def test_vmemo_channel_readonly_blocked(hub):
    """频道（kind=channel）非创建者发视频留言被拒。"""
    h, port, _ = hub
    owner = _Cli(port, "频道主")
    owner.hello()
    gid, _ = _mk_group(owner, "频道", channel=True)
    member = _Cli(port, "观众")
    member.hello()
    _join_group(member, gid)
    blob = _fake_png()
    from vmemo_api import pack
    vma1 = pack([blob], b"", fps=8, dur_ms=100)
    member.send({"t": MsgType.VMEMO.value, "channel": "group", "to": gid,
                 "duration": 0.1}, vma1)
    err, _ = member.wait("error", timeout=3.0,
                         pred=lambda x: x.get("code") == "readonly")
    assert err is not None
    owner.close()
    member.close()


# ================ 客户端：实时位置接收侧标记（会话隔离/过期/停止） ================

class _MarkerApp:
    """轻量 stub：仅承载 client.App 的位置标记方法，免 tkinter。"""
    __test__ = False

    def __init__(self, view, uid=7, ttl=300.0):
        self.view = view
        self.uid = uid
        self._geo_live_markers = {}
        self.refreshed = 0
        self.core = _FakeCore(ttl=ttl)

    def _refresh_chan_label(self):
        self.refreshed += 1

    def _marker_name(self, u):
        return f"U{u}"

    # 直接复用 client.py 的类方法
    _set_geo_marker = __import__("client", fromlist=["ChatWindow"]).ChatWindow._set_geo_marker
    _drop_geo_marker = __import__("client", fromlist=["ChatWindow"]).ChatWindow._drop_geo_marker
    _current_geo_markers = __import__("client", fromlist=["ChatWindow"]).ChatWindow._current_geo_markers
    _on_geo_live_evt = __import__("client", fromlist=["ChatWindow"]).ChatWindow._on_geo_live_evt


class _FakeCore:
    """提供 cfg.geo_live_ttl 的最小 core stub。"""

    class _Cfg:
        geo_live_ttl = 300.0

    def __init__(self, ttl=300.0):
        self.cfg = self._Cfg()
        self.cfg.geo_live_ttl = ttl

    def display_name(self, uid):
        return f"用户{uid}"


def test_marker_session_isolation():
    """标记按会话隔离：群1 的共享不污染群2 的标题。"""
    app = _MarkerApp(("group", 1))
    app._set_geo_marker("group", 1, 7, 31.0, 121.0, "工位")
    app._set_geo_marker("group", 2, 9, 30.0, 120.0, "会议室")
    assert set(app._current_geo_markers()) == {7}
    app.view = ("group", 2)
    assert set(app._current_geo_markers()) == {9}


def test_marker_geo_stop_removes():
    """GEO_STOP 摘掉标记；空会话整个移除。"""
    app = _MarkerApp(("group", 1))
    app._on_geo_live_evt({"t": "geo_live", "channel": "group", "to": 1,
                          "uid": 9, "geo": {"lat": 30.0, "lon": 120.0,
                                             "expire": time.time() + 300}})
    assert set(app._current_geo_markers()) == {9}
    app._on_geo_live_evt({"t": "geo_stop", "channel": "group", "to": 1,
                          "uid": 9})
    assert not app._current_geo_markers()


def test_marker_live_wo_expire_dropped():
    """GEO_LIVE 无 expire（异常帧）→ 视为过期摘除，不残留。"""
    app = _MarkerApp(("group", 1))
    app._on_geo_live_evt({"t": "geo_live", "channel": "group", "to": 1,
                          "uid": 9, "geo": {"lat": 30.0, "lon": 120.0}})
    assert not app._current_geo_markers()


def test_marker_expired_swept():
    """过期标记在读取时被清理。"""
    app = _MarkerApp(("group", 1), ttl=-1.0)   # ttl 为负 → 立即过期
    app._set_geo_marker("group", 1, 9, 30.0, 120.0)
    assert not app._current_geo_markers()
    assert app._geo_live_markers == {}


def test_marker_wrong_session_ignored():
    """非当前会话的事件不写标记。"""
    app = _MarkerApp(("group", 1))
    app._on_geo_live_evt({"t": "geo_live", "channel": "group", "to": 2,
                          "uid": 9, "geo": {"lat": 30.0, "lon": 120.0}})
    assert not app._current_geo_markers()
