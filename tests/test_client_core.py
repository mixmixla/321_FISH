# -*- coding: utf-8 -*-
"""客户端核心 e2e：真 socket + 真 Hub 服务器（127.0.0.1 随机端口）

覆盖：登录/welcome（名单+表情+服务器历史合并）、公聊/私聊/群聊本地历史落盘与
频道隔离、本地历史磁盘持久化（重启恢复）、心跳 ping/pong、断线自动重连并重入群、
离线发送报错。
"""
import os
import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, serve as serve_tcp
from client_core import ClientCore, LocalHistory


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
    threading.Thread(target=serve_tcp, args=(h, port, stop, False), daemon=True).start()
    time.sleep(0.1)
    yield h, port, stop
    stop.set()
    time.sleep(0.2)


class Collector:
    """on_event 收集器：与 TestClient.wait 同语义（匹配即移除）"""
    __test__ = False

    def __init__(self, core: ClientCore) -> None:
        self.events = []
        self._lock = threading.Lock()
        core._on_event = self._on

    def _on(self, ev: dict) -> None:
        with self._lock:
            self.events.append(ev)

    def wait(self, t: str, timeout: float = 3.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, e in enumerate(self.events):
                    if e.get("t") == t and (pred is None or pred(e)):
                        del self.events[i]
                        return e
            time.sleep(0.01)
        return None

    def has(self, t: str, pred=None) -> bool:
        with self._lock:
            return any(e.get("t") == t and (pred is None or pred(e)) for e in self.events)


def _make_core(port: int, nick: str, tmp_path, **kw):
    kw.setdefault("heartbeat_interval", 0.1)
    kw.setdefault("heartbeat_timeout", 0.8)
    kw.setdefault("reconnect_base", 0.05)
    kw.setdefault("reconnect_max", 0.3)
    hist_dir = kw.pop("history_dir", str(tmp_path / f"hist_{nick}"))
    return ClientCore(host="127.0.0.1", port=port, nick=nick,
                      history_dir=hist_dir, **kw)


def _spawn(port: int, nick: str, tmp_path, **kw):
    core = _make_core(port, nick, tmp_path, **kw)
    col = Collector(core)
    core.start()
    return core, col


def _online(col, timeout: float = 3.0):
    return col.wait("state", timeout=timeout,
                    pred=lambda e: e.get("state") == "online")


# ---------- 登录 / welcome ----------
def test_login_welcome_state(hub, tmp_path):
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    try:
        assert _online(ac)
        w = ac.wait("welcome")
        assert w and w["uid"] == a.uid and a.uid is not None
        assert a.state == "online" and a.connected
        assert any(u["nick"] == "alice" for u in a.roster.values())
        assert a.stickers                       # welcome 自带表情包
    finally:
        a.stop()


def test_welcome_merges_server_history(hub, tmp_path):
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_chat("早会开场白")
        bc.wait("chat", pred=lambda e: e.get("text") == "早会开场白")
        # 新成员 c 上线，welcome 自带服务器公聊历史 → 本地历史里有
        c, cc = _spawn(port, "charlie", tmp_path)
        assert _online(cc)
        assert any(e.get("text") == "早会开场白" for e in c.history("public"))
    finally:
        a.stop(); b.stop(); c.stop()


# ---------- 公聊 + 本地历史 ----------
def test_public_chat_reach_and_local_history(hub, tmp_path):
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_chat("大家好 :smile:")
        m1 = ac.wait("chat", pred=lambda e: e.get("text") == "大家好 :smile:")
        m2 = bc.wait("chat", pred=lambda e: e.get("text") == "大家好 :smile:")
        assert m1 and m2
        assert m1["seq"] == m2["seq"] and m1["nick"] == "alice"
        assert m1["channel"] == "public"
        # 本地历史：双方都落盘
        assert any(e.get("text") == "大家好 :smile:" for e in a.history("public"))
        assert any(e.get("text") == "大家好 :smile:" for e in b.history("public"))
    finally:
        a.stop(); b.stop()


# ---------- 私聊 + 频道隔离 ----------
def test_private_chat_local_channel_isolation(hub, tmp_path):
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    c3, cc = _spawn(port, "charlie", tmp_path)
    try:
        assert _online(ac) and _online(bc) and _online(cc)
        bob_uid = b.uid
        assert a.send_private("悄悄话", bob_uid)
        got = bc.wait("chat", pred=lambda e: e.get("text") == "悄悄话")
        assert got and got["channel"] == "private" and got["to"] == bob_uid
        assert not cc.has("chat")               # 第三方收不到
        # 本地历史按配对隔离：alice/bob 有，charlie 与 bob 的配对为空
        assert any(e.get("text") == "悄悄话" for e in a.history("private", bob_uid))
        assert b.history("private", a.uid)
        assert c3.history("private", bob_uid) == []
    finally:
        a.stop(); b.stop(); c3.stop()


# ---------- 群聊生命周期 ----------
def test_group_chat_lifecycle(hub, tmp_path):
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.create_group("摸鱼群", public=True)   # R54：公开群才可被直接加入
        gs = ac.wait("group_state", pred=lambda e: e.get("name") == "摸鱼群")
        gid = gs["gid"]
        bc.wait("group_list", pred=lambda e: any(g["gid"] == gid for g in e["groups"]))
        assert b.join_group(gid)
        assert bc.wait("group_state", pred=lambda e: e.get("gid") == gid
                       and "加入" in (e.get("text") or ""))
        assert a.send_group("晚上开黑？", gid)
        got = bc.wait("chat", pred=lambda e: e.get("text") == "晚上开黑？")
        assert got and got["channel"] == "group" and got["to"] == gid
        # 群历史 key 正确落盘
        assert any(e.get("text") == "晚上开黑？" for e in a.history("group", gid))
        assert any(e.get("text") == "晚上开黑？" for e in b.history("group", gid))
        # 退群
        assert b.leave_group(gid)
        ac.wait("group_state", pred=lambda e: e.get("gid") == gid
                and "退群" in (e.get("text") or ""))
        assert gid not in b._joined_groups
    finally:
        a.stop(); b.stop()


def test_group_announce_sync_and_send(hub, tmp_path):
    """群公告：owner 发布后全员 group_announces 同步；非 owner 发送被服务器拒绝。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.create_group("摸鱼群", public=True)   # R54：公开群才可被直接加入
        gs = ac.wait("group_state", pred=lambda e: e.get("name") == "摸鱼群")
        gid = gs["gid"]
        assert b.join_group(gid)
        bc.wait("group_state", pred=lambda e: e.get("gid") == gid
                and "加入" in (e.get("text") or ""))
        # owner 发布公告 → 双端 group_announces 同步
        assert a.send_group_announce(gid, "今晚八点开黑")
        gs2 = ac.wait("group_state", pred=lambda e: e.get("gid") == gid
                      and (e.get("announce") or "") == "今晚八点开黑")
        assert gs2 is not None
        bc.wait("group_state", pred=lambda e: e.get("gid") == gid
                and (e.get("announce") or "") == "今晚八点开黑")
        assert a.group_announces.get(gid) == "今晚八点开黑"
        assert b.group_announces.get(gid) == "今晚八点开黑"
        # 普通成员 bob 发送 → 服务器拒绝
        assert b.send_group_announce(gid, "我篡位")
        assert bc.wait("error", pred=lambda e: e.get("code") == "perm")
        # 成员列表/群摘要里的 announce 也同步（判权用）
        assert a.groups.get(gid, {}).get("announce") == "今晚八点开黑"
        # 清除公告
        assert a.send_group_announce(gid, "")
        cleared = ac.wait("group_state", pred=lambda e: e.get("gid") == gid
                          and "已清除" in (e.get("text") or ""))
        assert cleared is not None
        bc.wait("group_state", pred=lambda e: e.get("gid") == gid
                and "已清除" in (e.get("text") or ""))
        assert not a.group_announces.get(gid)
        assert not b.group_announces.get(gid)
    finally:
        a.stop(); b.stop()


def test_voice_message_roundtrip_and_persist(hub, tmp_path):
    """语音：发送端二进制 WAV 经服务器透传，接收端落盘 voice_path 并在历史中保留。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_voice("public", None, b"RIFFWAV1", 2.5)
        got = bc.wait("chat", pred=lambda e: e.get("voice")
                      and e.get("channel") == "public")
        assert got is not None and got["duration"] == 2.5
        # 接收端落盘 voice_path 且文件内容一致；历史也包含该语音消息
        vp = got.get("voice_path")
        assert vp and os.path.exists(vp)
        assert open(vp, "rb").read() == b"RIFFWAV1"
        assert any(e.get("voice") for e in a.history("public"))
        # 私聊语音 → 对端收到
        assert b.send_voice("private", a.uid, b"RIFFWAV2", 1.0)
        priv = ac.wait("chat", pred=lambda e: e.get("voice")
                       and e.get("channel") == "private")
        assert priv is not None and os.path.exists(priv.get("voice_path", ""))
    finally:
        a.stop(); b.stop()


# ---------- 本地历史磁盘持久化（重启恢复） ----------
def test_local_history_disk_persist(tmp_path):
    d = str(tmp_path / "hist")
    lh = LocalHistory(d)
    lh.add("public", {"seq": 1, "text": "h1"})
    lh.add("private:1:2", {"seq": 2, "text": "h2"})
    lh.add("group:7", {"seq": 3, "text": "h3"})
    assert [m["text"] for m in lh.load("public")] == ["h1"]
    # 模拟重启：先冲刷句柄（正常退出路径），新实例内存为空，磁盘可恢复
    lh.close()
    lh2 = LocalHistory(d)
    assert lh2.load("public") == []
    assert [m["text"] for m in lh2.load_disk("public")] == ["h1"]
    assert [m["text"] for m in lh2.load_disk("private:1:2")] == ["h2"]
    assert [m["text"] for m in lh2.load_disk("group:7")] == ["h3"]


def test_client_restart_recovers_history(hub, tmp_path):
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    a2 = None
    try:
        assert _online(ac)
        assert a.send_chat("持久化一条")
        assert ac.wait("chat", pred=lambda e: e.get("text") == "持久化一条")
        hist_dir = a._history._dir
        a.stop()
        # 同目录新实例（模拟重启）→ 磁盘历史恢复
        a2 = _make_core(port, "alice", tmp_path, history_dir=hist_dir)
        col2 = Collector(a2)
        a2.start()
        assert _online(col2)
        assert any(e.get("text") == "持久化一条"
                   for e in a2.history("public"))
    finally:
        a.stop()
        if a2 is not None:
            a2.stop()


# ---------- 心跳 ----------
def test_heartbeat_ping_pong(hub, tmp_path):
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    try:
        assert _online(ac)
        time.sleep(0.6)                         # 0.1s 间隔 → 应有多次 pong
        assert a.pong_count >= 2
        assert a.state == "online"
    finally:
        a.stop()


# ---------- 断线自动重连 + 重入群 ----------
def test_reconnect_and_rejoin_group(hub, tmp_path):
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.create_group("测试群", public=True)   # R54：公开群才可被直接加入
        gs = ac.wait("group_state", pred=lambda e: e.get("name") == "测试群")
        gid = gs["gid"]
        bc.wait("group_list", pred=lambda e: any(g["gid"] == gid for g in e["groups"]))
        assert b.join_group(gid)
        bc.wait("group_state", pred=lambda e: e.get("gid") == gid
                and "加入" in (e.get("text") or ""))
        assert gid in a._joined_groups
        # 模拟网络中断：alice 掉线（服务器把 alice 移出群；bob 仍在 → 群存活）
        a.drop()
        assert ac.wait("state", timeout=5, pred=lambda e: e.get("state") == "offline")
        # 自动重连 → welcome → 自动重入群
        assert _online(ac, timeout=5)
        assert ac.wait("group_state", timeout=5, pred=lambda e:
                       e.get("gid") == gid
                       and any(m.get("uid") == a.uid for m in e.get("members", [])))
        # 服务器侧确认成员身份恢复
        with hub[0].lock:
            g = hub[0].groups.get(gid)
            assert g and any(u == a.uid for u in g["members"])
    finally:
        a.stop(); b.stop()


# ---------- 离线发送报错 ----------
def test_send_offline_reports_error(hub, tmp_path):
    a = _make_core(99999, "ghost", tmp_path)    # 未 start
    assert not a.send_chat("hi")
    ev = a.events.get(timeout=1)
    assert ev["t"] == "error" and ev["code"] == "offline"


# ---------- R13 表情回应 ----------
def test_reaction_flow_core(hub, tmp_path):
    """core 收发 reaction：事件推到双方，且本地历史消息写入 reactions 状态。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_chat("点个赞")
        m = ac.wait("chat", pred=lambda e: e.get("text") == "点个赞")
        seq = m["seq"]
        assert b.send_reaction(seq, "👍")
        r = ac.wait("reaction", pred=lambda e: e.get("seq") == seq)
        assert r and str(b.uid) in r["reactions"]["👍"]
        # 本地历史里那条消息已被写入 reactions（GUI 行共享该 dict）
        hist = [e for e in a.history("public") if e.get("seq") == seq][0]
        assert str(b.uid) in hist["reactions"]["👍"]
        # 摘下 → 历史里清空
        assert b.send_reaction(seq, "👍", on=False)
        ac.wait("reaction", pred=lambda e: e.get("seq") == seq and not e.get("reactions"))
        hist2 = [e for e in a.history("public") if e.get("seq") == seq][0]
        assert "reactions" not in hist2 or hist2["reactions"] == {}
    finally:
        a.stop(); b.stop()


# ---------- R13 已读回执 ----------
def test_read_receipt_core_state(hub, tmp_path):
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_chat("请已读")
        m = ac.wait("chat", pred=lambda e: e.get("text") == "请已读")
        assert b.send_read("public", None, m["seq"])
        rd = ac.wait("read", pred=lambda e: e.get("uid") == b.uid)
        assert rd and rd["key"] == "public" and rd["seq"] == m["seq"]
        # core 侧 reads 状态写入（GUI 用 ✓已读 标记）
        assert b.uid in a.reads.get("public", {})
        assert a.reads["public"][b.uid] == m["seq"]
    finally:
        a.stop(); b.stop()


# ---------- R13 消息置顶 ----------
def test_pin_flow_core_and_welcome(hub, tmp_path):
    """core 收发 pin：事件+self.pins 更新；welcome 携带可见置顶。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_chat("置顶内容")
        m = ac.wait("chat", pred=lambda e: e.get("text") == "置顶内容")
        assert a.send_pin("public", None, m["seq"], on=True)
        p = bc.wait("pin", pred=lambda e: e.get("seq") == m["seq"] and e.get("on"))
        assert p and b.pins.get("public", {}).get("seq") == m["seq"]
        # 取消置顶 → self.pins 移除
        assert a.send_pin("public", None, m["seq"], on=False)
        bc.wait("pin", pred=lambda e: e.get("seq") == m["seq"] and not e.get("on"))
        assert "public" not in b.pins
    finally:
        a.stop(); b.stop()


def test_pin_delivered_on_reconnect_core(hub, tmp_path):
    """重连后 welcome 的 pins 重新填充 core.pins。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_chat("导览")
        m = ac.wait("chat", pred=lambda e: e.get("text") == "导览")
        assert a.send_pin("public", None, m["seq"], on=True)
        bc.wait("pin", pred=lambda e: e.get("seq") == m["seq"] and e.get("on"))
        # 新实例（模拟重启）→ welcome 重建 pins
        c, cc = _spawn(port, "charlie", tmp_path)
        assert _online(cc)
        assert c.pins.get("public", {}).get("seq") == m["seq"]
    finally:
        a.stop(); b.stop()
        c.stop()


# ---------- R13 消息转发 ----------
def test_forward_snapshot_passthrough(hub, tmp_path):
    """发送方附原消息快照（forward），接收方事件原样携带，本地历史落盘。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_chat("原始机密")
        orig = ac.wait("chat", pred=lambda e: e.get("text") == "原始机密")
        # 把 orig 当转发快照发给 bob
        snapshot = {"nick": orig["nick"], "text": orig["text"],
                    "seq": orig["seq"], "ts": orig.get("ts", 0)}
        assert a.send_chat("转发给你", to=b.uid, channel="private", forward=snapshot)
        got = bc.wait("chat", pred=lambda e: e.get("forward") and e["forward"]["seq"] == orig["seq"])
        assert got and got["text"] == "转发给你" and got["channel"] == "private"
        assert got["forward"]["text"] == "原始机密"
        # 本地历史保留 forward 快照
        hist = [e for e in b.history("private", a.uid) if e.get("forward")]
        assert hist and hist[-1]["forward"]["seq"] == orig["seq"]
    finally:
        a.stop(); b.stop()


# ---------- R14 会话清理（本地历史） ----------
def test_purge_event_drops_local_history(hub, tmp_path):
    """send_purge 后本地历史按 until_seq 丢弃并落盘。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        for t in ("一", "二", "三"):
            assert a.send_chat(t)
        m3 = ac.wait("chat", pred=lambda e: e.get("text") == "三")
        assert a.send_purge("public", None, m3["seq"])
        ac.wait("purge", pred=lambda e: e.get("until_seq") == m3["seq"])
        bc.wait("purge", pred=lambda e: e.get("until_seq") == m3["seq"])
        texts = [m.get("text") for m in a.history("public")]
        assert not any(t in texts for t in ("一", "二"))     # 旧消息已清
    finally:
        a.stop(); b.stop()


def test_send_chat_burn_flag(hub, tmp_path):
    """send_chat(burn=True) 正常送达；对端读后收到 burn 广播的 del。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_chat("焚毁", burn=True)
        burn = bc.wait("chat", pred=lambda e: e.get("text") == "焚毁")
        assert b.send_read("public", None, burn["seq"])
        ac.wait("del", pred=lambda e: e.get("seq") == burn["seq"] and e.get("burn"))
    finally:
        a.stop(); b.stop()


# ---------- A3 后台线程化：MD5 计算不阻塞调用方（UI 主线程等价路径） ----------
def test_send_file_md5_async_not_blocking(hub, tmp_path, monkeypatch):
    """send_file 立即返回；MD5 在子线程计算期间聊天/收发照常；
    释放后 FILE_OFFER 才发出且 md5 正确。"""
    import hashlib
    import os

    import file_client
    from filexfer import compute_md5 as real_compute_md5

    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        data = os.urandom(1 << 20)                     # 1MB 载荷
        path = str(tmp_path / "payload.bin")
        with open(path, "wb") as f:
            f.write(data)
        expected_md5 = hashlib.md5(data).hexdigest()

        released = threading.Event()
        def slow_md5(p, cs):
            released.wait(5)                           # 模拟大文件长时间哈希
            return real_compute_md5(p, cs)
        monkeypatch.setattr(file_client, "compute_md5", slow_md5)

        t0 = time.time()
        fid = a.files.send_file(path, b.uid)
        assert fid is not None
        assert time.time() - t0 < 1.0                  # 哈希未释放却已返回 → 后台线程

        # 哈希进行中（未释放）：确认 hashing 进度事件已到，且聊天链路照常可用
        assert ac.wait("file_progress", timeout=2,
                       pred=lambda e: e.get("state") == "hashing")
        assert a.send_chat("哈希期间聊天照常")
        assert ac.wait("chat", timeout=2,
                       pred=lambda e: e.get("text") == "哈希期间聊天照常")

        released.set()                                 # 放行哈希
        offer = bc.wait("file_offer", timeout=5,
                        pred=lambda e: e.get("file_id") == fid)
        assert offer is not None
        assert a.files.xfers[fid].md5 == expected_md5   # 发送侧 xfer 记录
        assert b.files.xfers[fid].md5 == expected_md5   # 接收侧 xfer 记录（协议透传）
    finally:
        a.stop(); b.stop()


# ---------- 文件传输（搭桥直连 + 拒绝 + 断点续传） ----------
def _make_src(tmp_path, name="数据.xlsx", size=300_000):
    import random
    rnd = random.Random(7)
    data = bytes(rnd.randrange(256) for _ in range(size))
    p = tmp_path / name
    p.write_bytes(data)
    return str(p), data


def test_file_send_receive_full(hub, tmp_path):
    from filexfer import compute_md5
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    dl = tmp_path / "dl"
    dl.mkdir()
    try:
        assert _online(ac) and _online(bc)
        src, data = _make_src(tmp_path)
        fid = a.files.send_file(src, b.uid)
        assert fid
        offer = bc.wait("file_offer", timeout=8)
        assert offer and offer["file_id"] == fid
        assert b.files.accept(fid, str(dl))
        done = ac.wait("file_progress", timeout=15,
                       pred=lambda e: e.get("file_id") == fid and e.get("state") == "done")
        assert done, "发送方未收到完成事件"
        # 接收方最终文件内容与源一致
        saved = dl / "数据.xlsx"
        assert saved.read_bytes() == data
        assert compute_md5(str(saved)) == compute_md5(src)
    finally:
        a.stop(); b.stop()


def test_image_send_auto_receive(hub, tmp_path, monkeypatch):
    """A7 图片消息：接收端免确认自动接收，完成后推 image 事件（含落盘路径）。

    发送方把图当附件发出（复用 file 传输）；接收端识别为图片自动 accept（不弹
    保存确认），传输完成后在接收方产生一条 image 事件供 GUI 渲染缩略图。
    """
    from PIL import Image
    import os
    _, port, _ = hub
    dl = tmp_path / "dl"
    dl.mkdir()
    monkeypatch.setattr(CFG, "downloads_dir", str(dl))    # 落盘到测试目录，不污染真实下载
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        img = tmp_path / "photo.png"
        Image.new("RGB", (64, 48), (200, 30, 30)).save(str(img))
        fid = a.files.send_file(str(img), b.uid)
        assert fid
        # 图片免确认：接收方不应收到 file_offer 确认弹窗事件
        assert bc.wait("file_offer", timeout=1) is None
        ev = bc.wait("image", timeout=15, pred=lambda e: e.get("file_id") == fid)
        assert ev, "接收方未收到 image 事件"
        assert ev["image_path"] and os.path.isfile(ev["image_path"])
        # 发送方完成（文件身份/校验在 file 层已覆盖）
        done = ac.wait("file_progress", timeout=15,
                       pred=lambda e: e.get("file_id") == fid and e.get("state") == "done")
        assert done
    finally:
        a.stop(); b.stop()


def test_file_reject(hub, tmp_path):
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        src, _ = _make_src(tmp_path, name="拒绝文件.txt", size=10_000)
        fid = a.files.send_file(src, b.uid)
        offer = bc.wait("file_offer", timeout=8)
        assert offer and offer["file_id"] == fid
        assert b.files.reject(fid)
        ev = ac.wait("file_progress", timeout=8,
                     pred=lambda e: e.get("file_id") == fid and e.get("state") == "failed")
        assert ev and "拒绝" in (ev.get("text") or "")
    finally:
        a.stop(); b.stop()


def test_file_resume_from_disk(hub, tmp_path):
    """断点续传：接收端已有前 2 块（.part + .meta.json），接受时位图带回跳过"""
    from filexfer import PartFile, TransferMeta, chunk_count, compute_md5, save_meta
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    dl = tmp_path / "dl"
    dl.mkdir()
    try:
        assert _online(ac) and _online(bc)
        src, data = _make_src(tmp_path, name="续传.bin", size=200_000)
        md5 = compute_md5(src)
        fid = a.files.send_file(src, b.uid)
        offer = bc.wait("file_offer", timeout=8)
        assert offer and offer["file_id"] == fid
        # 模拟上次中断：接收端已落盘前 2 块 + 元数据
        name = offer["filename"]
        size = offer["size"]
        chunk = CFG.chunk_size
        total = chunk_count(size, chunk)
        part = dl / f"{name}.part"
        pf = PartFile(str(part), size)
        for i in range(2):
            pf.write_chunk(i, data[i * chunk:(i + 1) * chunk], chunk)
        pf.close()
        save_meta(str(dl / f"{name}.part.meta.json"), TransferMeta(
            file_id=fid, filename=name, size=size, chunk_size=chunk,
            md5=md5, acked=[0, 1]))
        assert b.files.accept(fid, str(dl))
        done = ac.wait("file_progress", timeout=15,
                       pred=lambda e: e.get("file_id") == fid and e.get("state") == "done")
        assert done, "续传未完成"
        assert (dl / name).read_bytes() == data
        assert total >= 3          # 至少还有后续块需要传，证明位图生效
    finally:
        a.stop(); b.stop()


# ---------- R67 拍一拍（客户端核心） ----------
def test_send_nudge_local_rate_limit(tmp_path):
    """send_nudge 本地 5s/人 限速：第二次立即调用被拒。"""
    core = ClientCore(host="127.0.0.1", port=1, nick="t",
                      history_dir=str(tmp_path / "h"))
    core._send_frame = lambda h, body=b"": True   # 免网络直判
    assert core.send_nudge("public") is True
    assert core.send_nudge("public") is False     # 5s 内第二帧被限速


def test_nudge_event_pushed_to_handlers(hub, tmp_path):
    """真链路：a 拍一拍 public → b 的 on_event 收到 nudge 事件（不落本地历史）。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_nudge("public")
        got = bc.wait("nudge", pred=lambda e: e.get("channel") == "public"
                      and e.get("uid") == a.uid)
        assert got and got["nick"] == "alice"
        assert not any(m.get("t") == "nudge" for m in b.history("public"))
    finally:
        a.stop(); b.stop()


# ---------- R68 窗口抖动 / 在线状态（客户端核心） ----------
def test_send_shake_local_rate_limit(tmp_path):
    """send_shake 本地 10s/人 限速：第二次立即调用被拒。"""
    core = ClientCore(host="127.0.0.1", port=1, nick="t",
                      history_dir=str(tmp_path / "h"))
    core._send_frame = lambda h, body=b"": True   # 免网络直判
    assert core.send_shake("public") is True
    assert core.send_shake("public") is False     # 10s 内第二帧被限速


def test_send_status_validates(tmp_path):
    """send_status 只接受 online/away/busy，非法值直接拒绝。"""
    core = ClientCore(host="127.0.0.1", port=1, nick="t",
                      history_dir=str(tmp_path / "h"))
    sent = []
    core._send_frame = lambda h, body=b"": sent.append(h) or True
    assert core.send_status("away") is True
    assert sent[-1]["status"] == "away"
    assert core.send_status("nope") is False      # 非法状态
    assert len(sent) == 1


def test_shake_event_pushed_to_handlers(hub, tmp_path):
    """真链路：a 抖一抖 public → b 的 on_event 收到 shake 事件（不落本地历史）。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_shake("public")
        got = bc.wait("shake", pred=lambda e: e.get("channel") == "public"
                      and e.get("uid") == a.uid)
        assert got and got["nick"] == "alice"
        assert not any(m.get("t") == "shake" for m in b.history("public"))
    finally:
        a.stop(); b.stop()


def test_status_ack_updates_me(hub, tmp_path):
    """真链路：设置状态 → status_ack 回帧后 core.me['status'] 同步。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    try:
        assert _online(ac)
        assert a.send_status("busy")
        got = ac.wait("status_ack", pred=lambda e: e.get("status") == "busy")
        assert got
        assert a.me.get("status") == "busy"
    finally:
        a.stop()


# ---------- R69C9 好友备注名（客户端核心） ----------
def test_display_name_prefers_remark(tmp_path):
    """display_name 备注优先；无备注回退昵称；未知 uid 回退 用户N。"""
    core = ClientCore(host="127.0.0.1", port=1, nick="t",
                      history_dir=str(tmp_path / "h"))
    core.roster = {7: {"uid": 7, "nick": "bob", "remark": "老王"}}
    core.known = {}
    assert core.display_name(7) == "老王"
    core.roster = {7: {"uid": 7, "nick": "bob", "remark": ""}}
    assert core.display_name(7) == "bob"
    assert core.display_name(99) == "用户99"


def test_send_remark_frame(tmp_path):
    """send_remark 发 REMARK_SET 帧，uid 已 int 化。"""
    core = ClientCore(host="127.0.0.1", port=1, nick="t",
                      history_dir=str(tmp_path / "h"))
    sent = []
    core._send_frame = lambda h, body=b"": sent.append(h) or True
    assert core.send_remark(7, "老王") is True
    assert sent[-1]["t"] == "remark_set" and sent[-1]["uid"] == 7
    assert sent[-1]["remark"] == "老王"


def test_remark_roundtrip_via_roster(hub, tmp_path):
    """真链路：a 设 b 的备注 → a 收 remark_ack，且本人视角 roster 带 remark。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_remark(b.uid, "老王")
        got = ac.wait("remark_ack", pred=lambda e: e.get("uid") == b.uid)
        assert got and got["remark"] == "老王"
        assert a.display_name(b.uid) == "老王"      # roster 广播已带 remark
    finally:
        a.stop(); b.stop()
