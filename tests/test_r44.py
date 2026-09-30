# -*- coding: utf-8 -*-
"""R44 群聊 DFSS 棘轮回归（Double Forward Secrecy Scheme，双向前向保密）：

单元（crypto_e2ee）：
- 种子分发即擦：发/收两端只留前向链态（my_sender_key/peer_sender_entry 的
  key 位为 None），链上消息往返不受影响
- re-key 新纪元互通 + 旧纪元在途消息过渡期可解 + 落后登记拒收
- 错误码分流：replay / no_key / decrypt / stale（核心层仅 no_key 触发 SK_REQ）
- 接收链修剪：每发送者只保留当前 + 2 个旧纪元
- legacy 发送者保留种子 → v1 裸封装回退可解；种子已擦 → v1 回退 no_key
- 发送计数 / group_rotate_due 到期判定

集成（经服务器）：
- 纯 v2 群 DFSS 往返：双方互不可取对方原始种子，消息互通
- SK_REQ 触发 re-key：种子已擦时以全新纪元信封代替补发 → 自愈互通
- 自动轮转：monkeypatch GROUP_ROTATE_EVERY → 计数到期自动 re-key → 新纪元互通
- 混合 legacy 组：种子保留、v1 静态封装往返（R36 兼容不回归）
"""
import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, serve as serve_tcp
from web import serve as serve_web
from client_core import ClientCore
from protocol import MsgType
import crypto_e2ee
from crypto_e2ee import E2EEEngine, E2EEError


# ---------- 夹具（仿 test_r42） ----------

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
    wport = _free_port()
    httpd = serve_web(h, port=wport)
    time.sleep(0.2)
    yield h, port, wport, stop
    stop.set()
    time.sleep(0.2)


class Collector:
    __test__ = False

    def __init__(self, core: ClientCore) -> None:
        self.events = []
        self._lock = threading.Lock()
        core._on_event = self._on

    def _on(self, ev: dict) -> None:
        with self._lock:
            self.events.append(ev)

    def wait(self, t: str, timeout: float = 5.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, e in enumerate(self.events):
                    if e.get("t") == t and (pred is None or pred(e)):
                        del self.events[i]
                        return e
            time.sleep(0.01)
        return None


def _spawn(port: int, nick: str, tmp_path):
    core = ClientCore(host="127.0.0.1", port=port, nick=nick,
                      history_dir=str(tmp_path / f"hist_{nick}"),
                      heartbeat_interval=0.1, heartbeat_timeout=0.8,
                      reconnect_base=0.05, reconnect_max=0.3)
    col = Collector(core)
    core.start()
    w = col.wait("welcome")
    assert w is not None, f"{nick} 未收到 welcome"
    return core, col


def _engine_pair(tmp_path) -> tuple:
    """v2 会话引擎对：a(uid=1) 与 b(uid=2)。"""
    a = E2EEEngine(str(tmp_path / "da"))
    b = E2EEEngine(str(tmp_path / "db"))
    a.establish_session(1, 2, b.identity_pub, rs_local="aa", rs_remote="bb")
    b.establish_session(2, 1, a.identity_pub, rs_local="bb", rs_remote="aa")
    return a, b


# ---------- 单元：种子擦除与链态 ----------

def test_dfss_seed_erased_chain_roundtrip(tmp_path):
    """发/收两端种子即擦（key 位 None），前向链态照常往返多条消息。"""
    a, b = _engine_pair(tmp_path)
    epoch, sk = a.new_group_epoch(7, retain_seed=False)
    assert epoch == 1
    assert a.my_sender_key(7) == (1, None)            # 发送端种子已擦
    b.set_peer_sender_key(7, 1, sk, epoch, retain_seed=False)
    assert b.peer_sender_entry(7, 1) == (1, None)     # 接收端只留链态标记
    assert b.peer_sender_key(7, 1) is None            # 原始种子不可取
    blobs = [a.seal_group(7, {"i": i, "t": f"m{i}"}) for i in range(3)]
    for i, blob in enumerate(blobs):
        assert b.unseal_group(7, 1, blob) == {"i": i, "t": f"m{i}"}


def test_dfss_rekey_new_epoch_and_inflight(tmp_path):
    """re-key 后新纪元互通；旧纪元在途消息过渡期仍可解；落后登记拒收。"""
    a, b = _engine_pair(tmp_path)
    e1, sk1 = a.new_group_epoch(7, retain_seed=False)
    b.set_peer_sender_key(7, 1, sk1, e1, retain_seed=False)
    inflight = a.seal_group(7, {"n": "在途"})          # 旧纪元尾部消息（re-key 前密封）
    e2, sk2 = a.new_group_epoch(7, retain_seed=False)
    assert e2 == 2 and a.my_sender_key(7) == (2, None)
    b.set_peer_sender_key(7, 1, sk2, e2, retain_seed=False)
    assert b.unseal_group(7, 1, inflight) == {"n": "在途"}
    assert b.unseal_group(7, 1, a.seal_group(7, {"n": "新纪元"})) == {"n": "新纪元"}
    with pytest.raises(E2EEError) as ei:
        b.set_peer_sender_key(7, 1, sk1, 1)           # 落后登记拒收
    assert ei.value.code == "stale"


def test_dfss_error_codes(tmp_path):
    """错误码分流：重放=replay / 缺纪元=no_key / 篡改=decrypt。"""
    a, b = _engine_pair(tmp_path)
    epoch, sk = a.new_group_epoch(7, retain_seed=False)
    b.set_peer_sender_key(7, 1, sk, epoch, retain_seed=False)
    blob = a.seal_group(7, {"m": 1})
    assert b.unseal_group(7, 1, blob) == {"m": 1}
    with pytest.raises(E2EEError) as er:
        b.unseal_group(7, 1, blob)                    # 重放
    assert er.value.code == "replay"
    bad_epoch = bytearray(blob)
    bad_epoch[1:5] = (99).to_bytes(4, "big")          # 未知纪元
    with pytest.raises(E2EEError) as en:
        b.unseal_group(7, 1, bytes(bad_epoch))
    assert en.value.code == "no_key"
    bad = bytearray(a.seal_group(7, {"m": 2}))        # 未消费消息（同计数已用会先判 replay）
    bad[-1] ^= 0xFF                                   # 篡改密文
    with pytest.raises(E2EEError) as ed:
        b.unseal_group(7, 1, bytes(bad))
    assert ed.value.code == "decrypt"


def test_dfss_prune_old_epochs(tmp_path):
    """接收链修剪：每发送者只保留当前 + 最近 2 个旧纪元。"""
    a, b = _engine_pair(tmp_path)
    for e in range(1, 5):
        _, sk = a.new_group_epoch(7, retain_seed=False)
        b.set_peer_sender_key(7, 1, sk, e, retain_seed=False)
    recv = b._groups[7]["recv"][1]
    assert set(recv) == {2, 3, 4}                     # cur=4 + 2 旧
    assert b.unseal_group(7, 1, a.seal_group(7, {"ok": 1})) == {"ok": 1}
    with pytest.raises(E2EEError) as e1:
        b.unseal_group(7, 1, bytearray(b"\x02" + (1).to_bytes(4, "big")
                                       + (0).to_bytes(4, "big") + b"\x00" * 8
                                       + b"\x00" * 12 + b"\x00" * 16))
    assert e1.value.code == "no_key"                  # 纪元 1 接收链已被修剪


def test_dfss_counter_and_rotate_due(tmp_path, monkeypatch):
    """发送计数步进；GROUP_ROTATE_EVERY 到期判定（new_group_epoch 计数清零）。"""
    a, b = _engine_pair(tmp_path)
    a.new_group_epoch(7, retain_seed=False)
    assert not a.group_rotate_due(7)
    for i in range(3):
        a.seal_group(7, {"i": i})
    assert a.my_group_counter(7) == 3
    monkeypatch.setattr(crypto_e2ee, "GROUP_ROTATE_EVERY", 3)
    assert a.group_rotate_due(7)
    a.new_group_epoch(7, retain_seed=False)           # re-key 后计数清零
    assert a.my_group_counter(7) == 0 and not a.group_rotate_due(7)


def test_dfss_legacy_retain_and_v1_fallback(tmp_path):
    """legacy 发送者保留种子 → v1 裸封装回退可解；种子已擦 → v1 回退 no_key。"""
    a, b = _engine_pair(tmp_path)
    e1, sk1 = a.new_group_epoch(9, retain_seed=True)  # legacy 组：种子保留
    b.set_peer_sender_key(9, 1, sk1, e1, retain_seed=True)
    assert b.peer_sender_key(9, 1) == sk1
    v1 = E2EEEngine.seal(sk1, {"m": "旧封装"})
    assert b.unseal_group(9, 1, v1) == {"m": "旧封装"}
    e2, sk2 = a.new_group_epoch(9, retain_seed=False)  # 纯 v2 组：种子擦
    b.set_peer_sender_key(9, 1, sk2, e2, retain_seed=False)
    v1b = E2EEEngine.seal(sk2, {"m": "不可解"})
    while v1b[0] == 2:                                 # nonce 首字节撞 v2 头（1/256）→ 重造
        v1b = E2EEEngine.seal(sk2, {"m": "不可解"})
    with pytest.raises(E2EEError) as ex:
        b.unseal_group(9, 1, v1b)
    assert ex.value.code == "no_key"                   # 走 SK_REQ → 对端 re-key


# ---------- 集成 ----------

def _mk_group(hub, tmp_path, names):
    """建群 + 全员入群；返回 (cores, cols, gid)。"""
    h, port, _wp, _stop = hub
    cores, cols = [], []
    for nick in names:
        c, col = _spawn(port, nick, tmp_path)
        cores.append(c)
        cols.append(col)
    assert cores[0].create_group("DFSS群", public=True)   # R54：公开群才可被直接加入
    gs = cols[0].wait("group_state")
    gid = gs["gid"]
    for core, col in zip(cores[1:], cols[1:]):
        assert core.join_group(gid)
        col.wait("group_state", pred=lambda e, gid=gid: e.get("gid") == gid)
    cols[0].wait("group_state", pred=lambda e: e.get("gid") == gid
                 and len(e.get("members") or []) == len(names))
    return cores, cols, gid


def _wait_chat(col: Collector, text: str, timeout: float = 5.0):
    """等待指定文本的群密聊消息事件。"""
    return col.wait("chat", timeout=timeout,
                    pred=lambda e: e.get("channel") == "group"
                    and e.get("e2ee") is True and e.get("text") == text)


def test_dfss_group_roundtrip_no_seed(hub, tmp_path):
    """纯 v2 群：开群双方种子即擦、互不可取对方原始种子，消息照常互通。"""
    cores, cols, gid = _mk_group(hub, tmp_path, ["DFSS甲", "DFSS乙"])
    a, b = cores
    try:
        ok, err = a.open_group_e2ee(gid)
        assert ok, err
        assert a.e2ee.my_sender_key(gid)[1] is None        # a 自己种子已擦
        deadline = time.time() + 5
        while time.time() < deadline and \
                b.e2ee.peer_sender_entry(gid, a.uid) is None:
            time.sleep(0.05)
        assert b.e2ee.peer_sender_key(gid, a.uid) is None  # b 取不到 a 种子
        for i in range(3):
            assert a.send_e2ee_group(f"擦种子{i}", gid)
        for i in range(3):
            assert _wait_chat(cols[1], f"擦种子{i}") is not None, \
                f"b 未收到 擦种子{i}"
    finally:
        a.stop()
        b.stop()


def test_dfss_skreq_triggers_rekey(hub, tmp_path):
    """种子已擦时 SK_REQ → 对端以全新纪元 re-key 代替补发 → 自愈互通。"""
    cores, cols, gid = _mk_group(hub, tmp_path, ["补钥甲", "补钥乙"])
    a, b = cores
    try:
        ok, err = a.open_group_e2ee(gid)
        assert ok, err
        deadline = time.time() + 5
        while time.time() < deadline and \
                b.e2ee.peer_sender_entry(gid, a.uid) is None:
            time.sleep(0.05)
        e1 = b.e2ee.peer_sender_entry(gid, a.uid)[0]
        # b 显式请求补发（模拟漏收信封）；a 种子已擦 → 触发 re-key
        assert b._send_frame({"t": MsgType.E2EE_SK_REQ.value, "gid": gid})
        deadline = time.time() + 8
        while time.time() < deadline and \
                (b.e2ee.peer_sender_entry(gid, a.uid) or (e1, None))[0] <= e1:
            time.sleep(0.05)
        e2 = b.e2ee.peer_sender_entry(gid, a.uid)[0]
        assert e2 > e1, f"SK_REQ 未触发 re-key（epoch 仍 {e2}）"
        assert a.e2ee.my_group_epoch(gid) == e2
        # re-key 后新纪元互通
        assert a.send_e2ee_group("补钥后消息", gid)
        assert _wait_chat(cols[1], "补钥后消息") is not None
    finally:
        a.stop()
        b.stop()


def test_dfss_auto_rotation_on_count(hub, tmp_path, monkeypatch):
    """monkeypatch GROUP_ROTATE_EVERY=2：计数到期自动 re-key，新纪元互通。"""
    monkeypatch.setattr(crypto_e2ee, "GROUP_ROTATE_EVERY", 2)
    cores, cols, gid = _mk_group(hub, tmp_path, ["自转甲", "自转乙"])
    a, b = cores
    try:
        ok, err = a.open_group_e2ee(gid)
        assert ok, err
        e1 = a.e2ee.my_group_epoch(gid)
        for i in range(3):
            assert a.send_e2ee_group(f"自转{i}", gid)
        deadline = time.time() + 8
        while time.time() < deadline and a.e2ee.my_group_epoch(gid) <= e1:
            time.sleep(0.05)
        assert a.e2ee.my_group_epoch(gid) > e1, "自动轮转未触发"
        deadline = time.time() + 5
        while time.time() < deadline and \
                (b.e2ee.peer_sender_entry(gid, a.uid) or (0, None))[0] \
                < a.e2ee.my_group_epoch(gid):
            time.sleep(0.05)
        assert a.send_e2ee_group("自转后消息", gid)
        assert _wait_chat(cols[1], "自转后消息") is not None
    finally:
        a.stop()
        b.stop()


def test_dfss_mixed_legacy_group_static(hub, tmp_path):
    """混合 legacy 组：双方种子保留、v1 静态封装往返（R36 兼容不回归）。"""
    cores, cols, gid = _mk_group(hub, tmp_path, ["混版甲", "混版乙"])
    a, b = cores
    try:
        # 双向 1v1 会话标记 legacy（模拟 R36 对端）
        a.e2ee.establish_session(a.uid, b.uid, b.e2ee.identity_pub,
                                 legacy_peer=True)
        b.e2ee.establish_session(b.uid, a.uid, a.e2ee.identity_pub,
                                 legacy_peer=True)
        ok, err = a.open_group_e2ee(gid)
        assert ok, err
        assert a.e2ee.my_sender_key(gid)[1] is not None    # 混版组：种子保留
        deadline = time.time() + 5
        while time.time() < deadline and \
                b.e2ee.peer_sender_entry(gid, a.uid) is None:
            time.sleep(0.05)
        assert b.e2ee.peer_sender_key(gid, a.uid) is not None  # b 也保留 a 种子
        assert a.send_e2ee_group("混版静态消息", gid)       # v1 静态封装
        assert _wait_chat(cols[1], "混版静态消息") is not None
    finally:
        a.stop()
        b.stop()
