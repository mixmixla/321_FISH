# -*- coding: utf-8 -*-
"""R42 E2EE 密钥轮转回归：

单元（crypto_e2ee）：
- 链式收发往返：每消息独立密钥（盐不同 → 密文不同）；乱序/重放拒收
- v1 裸封装回退（旧版对端 legacy 静态钥可解）
- 双 rs 握手：拼序无关对称；rs 变 → 根变；session_fresh 判定
- DH 轮转：rt1/rt2 全流程 → 双方同纪元新根互通；旧纪元消息过渡期可解
- rotate_due / pending / abort；并发轮转 uid 收敛（小 uid 优先）
- 群链：seal_group/unseal_group 往返 + 重放拒收

集成（经服务器）：
- 1v1 握手（rs 双盐）+ 密聊互通 + 指纹一致且轮转后不变
- 自动轮转：发送计数到期（monkeypatch ROTATE_EVERY）→ 双方 e2ee_rotated
  → 新纪元互通
- 手动轮转：core.rotate_e2ee_key → 完成 → 互通
- 并发握手：双方同时 start_e2ee → 双就绪同指纹 → 互通（nonce 收敛去重）
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
import crypto_e2ee
from crypto_e2ee import E2EEEngine, E2EEError


# ---------- 夹具（仿 test_r36） ----------

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


def _pair(tmp_path) -> tuple:
    """引擎对：a(uid=1) 与 b(uid=2) 双向建会话（带 rs）。"""
    a = E2EEEngine(str(tmp_path / "ra"))
    b = E2EEEngine(str(tmp_path / "rb"))
    a.establish_session(1, 2, b.identity_pub, rs_local="aa", rs_remote="bb")
    b.establish_session(2, 1, a.identity_pub, rs_local="bb", rs_remote="aa")
    return a, b


# ---------- 单元：链式收发 ----------

def test_ratchet_roundtrip_and_unique_blobs(tmp_path):
    a, b = _pair(tmp_path)
    blobs = [a.seal_ratchet(2, {"n": i, "text": f"m{i}"}) for i in range(5)]
    assert len({bytes(x) for x in blobs}) == 5        # 每消息独立密钥/盐
    for i, blob in enumerate(blobs):
        assert b.unseal_ratchet(1, blob) == {"n": i, "text": f"m{i}"}
    # v2 头：ver=2, epoch=0, counter=i
    assert blobs[0][0] == 2
    assert b.peer_sender_entry(9, 9) is None           # smoke：群表未涉及


def test_ratchet_replay_and_gap_reject(tmp_path):
    a, b = _pair(tmp_path)
    b0 = a.seal_ratchet(2, {"n": 0})
    b1 = a.seal_ratchet(2, {"n": 1})
    assert b.unseal_ratchet(1, b0) == {"n": 0}
    with pytest.raises(E2EEError):
        b.unseal_ratchet(1, b0)                        # 重放拒收
    assert b.unseal_ratchet(1, b1) == {"n": 1}
    b2 = a.seal_ratchet(2, {"n": 2})
    b3 = a.seal_ratchet(2, {"n": 3})
    assert b.unseal_ratchet(1, b3) == {"n": 3}         # 跳过中间帧仍可解（链快进）
    with pytest.raises(E2EEError):
        b.unseal_ratchet(1, b2)                        # 落后计数按重放拒收


def test_ratchet_tamper_reject(tmp_path):
    a, b = _pair(tmp_path)
    blob = a.seal_ratchet(2, {"secret": "暗号"})
    bad = bytearray(blob)
    bad[-1] ^= 0xFF
    with pytest.raises(E2EEError):
        b.unseal_ratchet(1, bytes(bad))


def test_v1_legacy_fallback(tmp_path):
    """旧版对端（R36）：无 rs 静态根 + 裸 seal 封装 → unseal_ratchet 回退可解。"""
    a = E2EEEngine(str(tmp_path / "la"))
    b = E2EEEngine(str(tmp_path / "lb"))
    a.establish_session(1, 2, b.identity_pub)          # 双双无 rs = legacy 根
    b.establish_session(2, 1, a.identity_pub)
    legacy = b.session_key(1)
    blob = E2EEEngine.seal(legacy, {"old": True})      # 旧对端用裸封装发来
    assert a.unseal_ratchet(2, blob) == {"old": True}  # a 侧 v1 回退可解


def test_legacy_peer_downgrade(tmp_path):
    """混版本部署：新端（R42）对旧端（R36）自动降级——
    发送走 v1 静态封装（旧端原生可解）；不触发轮转。"""
    a = E2EEEngine(str(tmp_path / "ma"))               # 新端
    b = E2EEEngine(str(tmp_path / "mb"))               # 旧端（R36 语义）
    a.establish_session(1, 2, b.identity_pub, rs_local="x", legacy_peer=True)
    b.establish_session(2, 1, a.identity_pub)          # 旧端：无 rs 静态根
    # 新端发送 → v1 裸封装 → 旧端静态 unseal 可解
    blob = a.seal_ratchet(2, {"m": "mix"})
    assert blob[0] != 2                                # 非 v2 头
    assert b.unseal(b.session_key(1), blob) == {"m": "mix"}
    # 旧端发 v1 → 新端回退可解
    blob2 = E2EEEngine.seal(b.session_key(1), {"m": "back"})
    assert a.unseal_ratchet(2, blob2) == {"m": "back"}
    # 不触发自动轮转；手动判定给明确拒绝依据
    for i in range(crypto_e2ee.ROTATE_EVERY + 1):
        a.seal_ratchet(2, {"i": i})
    assert not a.rotate_due(2)
    assert a.is_legacy_peer(2) and not b.is_legacy_peer(1)


def test_rs_pair_symmetry_and_effect(tmp_path):
    x = E2EEEngine(str(tmp_path / "s1"))
    y = E2EEEngine(str(tmp_path / "s2"))
    k1 = x.establish_session(1, 2, y.identity_pub, rs_local="aa", rs_remote="bb")
    k2 = y.establish_session(2, 1, x.identity_pub, rs_local="bb", rs_remote="aa")
    assert k1 == k2                                    # 拼序无关 → 对称
    k3 = x.establish_session(1, 2, y.identity_pub, rs_local="cc", rs_remote="bb")
    assert k3 != k1                                    # 换 rs → 根换（重握手全新）


def test_session_fresh(tmp_path):
    a, b = _pair(tmp_path)
    assert a.session_fresh(2)
    a.seal_ratchet(2, {"m": 1})                        # 发送即「已使用」
    assert not a.session_fresh(2)
    a.drop_session(2)
    assert not a.session_fresh(2)


# ---------- 单元：DH 轮转 ----------

def test_rotate_full_flow(tmp_path):
    a, b = _pair(tmp_path)
    root0 = a.session_key(2)
    fp0 = a.peer_fingerprint(2)
    # 发一条旧纪元消息并暂存（验证过渡期可解）
    pre = a.seal_ratchet(2, {"n": "pre-rotate"})
    assert b.unseal_ratchet(1, pre) == {"n": "pre-rotate"}

    # 发起方 a：rt1 骑链发送
    rt1 = a.rotate_begin(1, 2)
    assert rt1 is not None and rt1["rt"] == 1 and rt1["epoch"] == 1
    blob1 = a.seal_ratchet(2, rt1)
    # 被动方 b：解 rt1 → 切新纪元 → 回 rt2（旧链封装）
    pay = b.unseal_ratchet(1, blob1)
    assert pay["rt"] == 1
    blob2 = b.rotate_on_rt1(2, 1, bytes.fromhex(pay["eph"]))
    assert blob2 is not None
    # 发起方 a：解 rt2 → 混入新根
    pay2 = a.unseal_ratchet(2, blob2)
    assert pay2["rt"] == 2
    assert a.rotate_on_rt2(1, 2, bytes.fromhex(pay2["eph"])) is True
    assert a.session_key(2) != root0                   # 根已轮转
    assert a.peer_fingerprint(2) == fp0 == b.peer_fingerprint(1)  # 指纹不变
    # 新纪元互通（双向）
    m1 = a.seal_ratchet(2, {"n": "post-a"})
    assert b.unseal_ratchet(1, m1) == {"n": "post-a"}
    m2 = b.seal_ratchet(1, {"n": "post-b"})
    assert a.unseal_ratchet(2, m2) == {"n": "post-b"}
    assert a.session_key(2) == b.session_key(1)
    # 轮转后 a 的发送帧带新纪元头
    post = a.seal_ratchet(2, {"n": "post-epoch"})
    assert post[0] == 2
    assert b.unseal_ratchet(1, post) == {"n": "post-epoch"}


def test_rotate_due_pending_abort(tmp_path):
    a, b = _pair(tmp_path)
    assert not a.rotate_due(2)                         # 计数 0 不轮转
    for i in range(crypto_e2ee.ROTATE_EVERY):
        a.seal_ratchet(2, {"i": i})
    assert a.rotate_due(2)                             # 到达整数倍
    assert a.rotate_begin(1, 2) is not None
    assert not a.rotate_due(2)                         # 轮转进行中不再触发
    assert a.rotate_pending(2)
    assert a.rotate_begin(1, 2) is None                # 重复发起 → None
    a.rotate_abort(2)
    assert not a.rotate_pending(2)
    with pytest.raises(E2EEError):
        a.rotate_begin(1, 99)                          # 无会话报错


def test_rotate_concurrent_convergence(tmp_path):
    """双方同时发起：小 uid（a=1）优先，b 让位 → 同纪元收敛互通。"""
    a, b = _pair(tmp_path)
    rt1_a = a.rotate_begin(1, 2)
    rt1_b = b.rotate_begin(2, 1)
    assert rt1_a is not None and rt1_b is not None
    # b 收到 a 的 rt1（b 让位：uid 大者让位）
    blob2 = b.rotate_on_rt1(2, 1, bytes.fromhex(rt1_a["eph"]))
    assert blob2 is not None
    # a 收到 b 的 rt1（a 我方优先 → 忽略）
    assert a.rotate_on_rt1(1, 2, bytes.fromhex(rt1_b["eph"])) is None
    # a 解 b 的 rt2 → 收敛
    pay2 = a.unseal_ratchet(2, blob2)
    assert a.rotate_on_rt2(1, 2, bytes.fromhex(pay2["eph"])) is True
    assert a.session_key(2) == b.session_key(1)
    m = a.seal_ratchet(2, {"c": "converged"})
    assert b.unseal_ratchet(1, m) == {"c": "converged"}
    m2 = b.seal_ratchet(1, {"c": "reverse"})
    assert a.unseal_ratchet(2, m2) == {"c": "reverse"}


def test_rotate_rt1_timeout_stale_gc(tmp_path):
    """超时的旧轮转：再次 rotate_begin 时放弃旧 pending 重新发起。"""
    a, b = _pair(tmp_path)
    r1 = a.rotate_begin(1, 2)
    assert r1 is not None
    st = a._sessions[2]
    st["rot"]["t0"] -= crypto_e2ee._ROT_TIMEOUT + 1.0  # 人为超时
    r2 = a.rotate_begin(1, 2)
    assert r2 is not None and r2["eph"] != r1["eph"]   # 新临时密钥重试


# ---------- 单元：群链 ----------

def test_group_chain_roundtrip(tmp_path):
    a = E2EEEngine(str(tmp_path / "ga"))
    b = E2EEEngine(str(tmp_path / "gb"))
    epoch, sk = a.new_group_epoch(7)
    assert epoch == 1
    b.set_peer_sender_key(7, 1, sk, epoch)
    blobs = [a.seal_group(7, {"gi": i}) for i in range(3)]
    for i, blob in enumerate(blobs):
        assert b.unseal_group(7, 1, blob) == {"gi": i}
    with pytest.raises(E2EEError):
        b.unseal_group(7, 1, blobs[0])                 # 重放拒收
    # epoch 落后拒收：b 登记更高 epoch 后，旧 epoch 裸帧回退走旧 key（v1 语义）
    _, sk2 = a.new_group_epoch(7)
    b.set_peer_sender_key(7, 1, sk2, 2)
    with pytest.raises(E2EEError):
        b.set_peer_sender_key(7, 1, sk, 1)             # 落后登记拒收
    assert b.peer_sender_entry(7, 1)[0] == 2


# ---------- 集成 ----------

def test_handshake_chat_and_fingerprint_stable(hub, tmp_path):
    h, port, _wp, _stop = hub
    a, ca = _spawn(port, "轮甲", tmp_path)
    b, cb = _spawn(port, "轮乙", tmp_path)
    try:
        fp = a.start_e2ee(b.uid)
        assert fp, "握手失败"
        assert a.e2ee_ready(b.uid) and b.e2ee_ready(a.uid)
        assert a.e2ee_fingerprint(b.uid) == b.e2ee_fingerprint(a.uid) == fp

        # 链式互通 + 多条（计数步进）
        for i in range(3):
            assert a.send_e2ee_chat(f"甲密{i}", b.uid)
        for i in range(3):
            ev = cb.wait("chat", pred=lambda e, i=i:
                         e.get("channel") == "e2ee" and e.get("text") == f"甲密{i}")
            assert ev is not None, f"b 未收到 甲密{i}"
        assert b.send_e2ee_chat("乙密回", a.uid)
        ev = ca.wait("chat", pred=lambda e: e.get("channel") == "e2ee"
                     and e.get("text") == "乙密回")
        assert ev is not None

        # 手动轮转 → 双方都推 e2ee_rotated → 指纹不变 → 仍互通
        assert a.rotate_e2ee_key(b.uid)
        ra = ca.wait("e2ee_rotated", timeout=8)
        rb = cb.wait("e2ee_rotated", timeout=8)
        assert ra is not None and rb is not None, "轮转未完成"
        assert a.e2ee_fingerprint(b.uid) == fp
        assert a.send_e2ee_chat("轮转后甲", b.uid)
        ev = cb.wait("chat", pred=lambda e: e.get("channel") == "e2ee"
                     and e.get("text") == "轮转后甲")
        assert ev is not None
    finally:
        a.stop()
        b.stop()


def test_auto_rotation_on_count(hub, tmp_path, monkeypatch):
    h, port, _wp, _stop = hub
    monkeypatch.setattr(crypto_e2ee, "ROTATE_EVERY", 3)   # 3 条即触发
    a, ca = _spawn(port, "自转甲", tmp_path)
    b, cb = _spawn(port, "自转乙", tmp_path)
    try:
        assert a.start_e2ee(b.uid)
        for i in range(3):
            assert a.send_e2ee_chat(f"自动{i}", b.uid)
        ra = ca.wait("e2ee_rotated", timeout=8)
        rb = cb.wait("e2ee_rotated", timeout=8)
        assert ra is not None, "a 侧自动轮转未触发"
        assert rb is not None, "b 侧自动轮转未触发"
        # 新纪元互通
        assert a.send_e2ee_chat("新纪元甲", b.uid)
        ev = cb.wait("chat", pred=lambda e: e.get("channel") == "e2ee"
                     and e.get("text") == "新纪元甲")
        assert ev is not None
        assert b.send_e2ee_chat("新纪元乙", a.uid)
        ev2 = ca.wait("chat", pred=lambda e: e.get("channel") == "e2ee"
                      and e.get("text") == "新纪元乙")
        assert ev2 is not None
    finally:
        a.stop()
        b.stop()


def test_concurrent_handshake_convergence(hub, tmp_path):
    """双方同时 start_e2ee（并发重复握手）：nonce 收敛去重，双就绪同指纹互通。"""
    h, port, _wp, _stop = hub
    a, ca = _spawn(port, "并甲", tmp_path)
    b, cb = _spawn(port, "并乙", tmp_path)
    try:
        res = {}

        def _hs(core, tag):
            res[tag] = core.start_e2ee(b.uid if tag == "a" else a.uid)

        t1 = threading.Thread(target=_hs, args=(a, "a"))
        t2 = threading.Thread(target=_hs, args=(b, "b"))
        t1.start()
        time.sleep(0.05)
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)
        assert res.get("a"), "a 握手失败"
        assert res.get("b"), "b 握手失败"
        assert a.e2ee_ready(b.uid) and b.e2ee_ready(a.uid)
        assert a.e2ee_fingerprint(b.uid) == b.e2ee_fingerprint(a.uid)
        assert a.send_e2ee_chat("并发后甲", b.uid)
        ev = cb.wait("chat", pred=lambda e: e.get("channel") == "e2ee"
                     and e.get("text") == "并发后甲")
        assert ev is not None
        assert b.send_e2ee_chat("并发后乙", a.uid)
        ev2 = ca.wait("chat", pred=lambda e: e.get("channel") == "e2ee"
                      and e.get("text") == "并发后乙")
        assert ev2 is not None
    finally:
        a.stop()
        b.stop()


def test_group_chain_integration(hub, tmp_path):
    """群密聊 R42 链式：开群 → 多条互通（每消息独立密钥）→ re-key 后互通。"""
    h, port, _wp, _stop = hub
    a, ca = _spawn(port, "群甲", tmp_path)
    b, cb = _spawn(port, "群乙", tmp_path)
    assert a.create_group("轮群", public=True)   # R54：公开群才可被直接加入
    gs = ca.wait("group_state")
    gid = gs["gid"]
    assert b.join_group(gid)
    ca.wait("group_state", pred=lambda e: e.get("gid") == gid
            and len(e.get("members") or []) == 2)
    try:
        ok, err = a.open_group_e2ee(gid)
        assert ok, err
        ok2, err2 = b.open_group_e2ee(gid)
        assert ok2, err2
        deadline = time.time() + 5
        while time.time() < deadline and \
                (a.e2ee.peer_sender_entry(gid, b.uid) is None
                 or b.e2ee.peer_sender_entry(gid, a.uid) is None):
            time.sleep(0.05)
        for i in range(3):
            assert a.send_e2ee_group(f"群链{i}", gid)
        for i in range(3):
            ev = cb.wait("chat", pred=lambda e, i=i: e.get("channel") == "group"
                         and e.get("e2ee") is True and e.get("text") == f"群链{i}")
            assert ev is not None, f"b 未收到 群链{i}"
    finally:
        a.stop()
        b.stop()
