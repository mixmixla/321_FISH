# -*- coding: utf-8 -*-
"""服务器 e2e：真 socket（127.0.0.1）crypto 握手 → 登录/名单/公聊/私聊/群聊/
历史/心跳踢人/审计/表情包/网页端（HTTP+SSE）全链路"""
import http.client
import json
import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from crypto import client_handshake
from server import Hub, serve as serve_tcp, ChatBus
from web import serve as serve_web


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def hub(tmp_path):
    """每测一个独立 Hub + TCP 服务器（随机端口，审计落 tmp）"""
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)
    yield h, port, stop
    stop.set()
    time.sleep(0.2)


class TestClient:
    """加密握手 + 后台读帧线程的测试客户端"""
    __test__ = False                 # 不是测试类，避免 pytest 收集

    def __init__(self, port: int, nick: str) -> None:
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.chan = client_handshake(self.sock)
        self.nick = nick
        self.uid = None
        self.events = []
        self.alive = True
        self._lock = threading.Lock()
        self._th = threading.Thread(target=self._read, daemon=True)
        self._th.start()

    def _read(self):
        try:
            while True:
                h, _b = self.chan.recv_frame()
                with self._lock:
                    self.events.append(h)
        except Exception:
            with self._lock:
                self.alive = False

    def send(self, header: dict) -> None:
        self.chan.send_frame(header)

    def sendb(self, header: dict, body: bytes = b"") -> None:
        self.chan.send_frame(header, body)

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

    def hello(self):
        self.send({"t": "hello", "nick": self.nick})
        w = self.wait("welcome")
        if w:
            self.uid = w["uid"]
        return w

    def has(self, t: str, pred=None) -> bool:
        with self._lock:
            return any(e.get("t") == t and (pred is None or pred(e))
                       for e in self.events)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ---------- 握手 / 名单 ----------
def test_welcome_and_roster(hub):
    _, port, _ = hub
    a = TestClient(port, "alice")
    w = a.hello()
    assert w and a.uid is not None
    assert any(u["nick"] == "alice" for u in w["roster"])
    assert w["stickers"] and w["history"] == []
    b = TestClient(port, "bob")
    wb = b.hello()
    assert {u["nick"] for u in wb["roster"]} == {"alice", "bob"}
    ra = a.wait("roster", pred=lambda e: len(e["online"]) == 2)
    assert {u["nick"] for u in ra["online"]} == {"alice", "bob"}
    a.close(); b.close()


def test_same_uid_multisession_coexist_and_sync(hub):
    """R批次③：同一昵称（同一 uid）桌面+网页可并存，不再顶号。
    新消息 / 已读回执按 uid 广播到该 uid 的全部端——一端已读另一端同步。"""
    _, port, _ = hub
    a = TestClient(port, "multi")
    wa = a.hello()
    assert wa and a.uid is not None
    a2 = TestClient(port, "multi")          # 第二端同昵称 → 不再被拒
    wa2 = a2.hello()
    assert wa2 and a2.uid == a.uid          # 复用同一 uid
    b = TestClient(port, "bob")
    b.hello()
    # 公聊：b 发消息，a 与 a2 两端都要收到（按 uid 广播）
    b.send({"t": "chat", "channel": "public", "text": "hello multi"})
    got_a = a.wait("chat", pred=lambda e: e.get("text") == "hello multi")
    got_a2 = a2.wait("chat", pred=lambda e: e.get("text") == "hello multi")
    assert got_a and got_a2
    # 已读回执：a 报告读到 seq，a、a2 两端的已读事件都要广播到本 uid
    a.send({"t": "read", "channel": "public", "seq": 100})
    ra = a.wait("read", pred=lambda e: e.get("uid") == a.uid)
    ra2 = a2.wait("read", pred=lambda e: e.get("uid") == a.uid)
    assert ra and ra2 and ra["seq"] == ra2["seq"] == 100
    a.close(); a2.close(); b.close()


def test_nick_uid_reused_after_reconnect(hub):
    """R12fix：昵称→uid 映射断线后保留，同名重连复用原 uid——
    私聊/群/历史/草稿等 uid 对 key 跨客户端重启稳定对齐。"""
    _, port, _ = hub
    a = TestClient(port, "reuser")
    wa = a.hello()
    assert wa and a.uid is not None
    uid_a = a.uid
    a.close()
    time.sleep(0.3)                       # 等服务端 unregister（断线检测）
    b = TestClient(port, "reuser")
    wb = b.hello()
    assert wb is not None
    assert b.uid == uid_a                 # 复用同一 uid，而非递增新号
    b.close()


def test_nick_uid_not_reused_by_other(hub):
    """不同昵称不蹭旧 uid：断线后新昵称仍走 _uid_seq 递增。"""
    _, port, _ = hub
    a = TestClient(port, "uiduser-a")
    assert a.hello()
    uid_a = a.uid
    a.close()
    time.sleep(0.3)
    c = TestClient(port, "uiduser-c")
    wc = c.hello()
    assert wc is not None
    assert c.uid != uid_a
    c.close()


def test_ping_pong(hub):
    _, port, _ = hub
    a = TestClient(port, "pinguser")
    a.hello()
    a.send({"t": "ping"})
    assert a.wait("pong")
    a.close()


# ---------- 公聊 ----------
def test_public_chat_broadcast_and_seq(hub):
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "chat", "text": "大家好 :smile:"})
    m1 = a.wait("chat", pred=lambda e: e.get("text") == "大家好 :smile:")
    m2 = b.wait("chat", pred=lambda e: e.get("text") == "大家好 :smile:")
    assert m1 and m2
    assert m1["seq"] == m2["seq"] and m1["nick"] == "alice" and m1["channel"] == "public"
    # seq 单调递增
    a.send({"t": "chat", "text": "第二条"})
    m3 = b.wait("chat", pred=lambda e: e.get("text") == "第二条")
    assert m3["seq"] > m1["seq"]
    a.close(); b.close()


def test_chat_validation(hub):
    _, port, _ = hub
    a = TestClient(port, "alice")
    a.hello()
    a.send({"t": "chat", "text": ""})
    assert a.wait("error", pred=lambda e: e.get("code") == "empty")
    a.send({"t": "chat", "text": "x" * 5000})
    assert a.wait("error", pred=lambda e: e.get("code") == "long")
    a.send({"t": "chat", "text": "hi", "sticker": "not_exist"})
    assert a.wait("error", pred=lambda e: e.get("code") == "sticker")
    a.send({"t": "chat", "text": "哦", "sticker": "fish"})
    m = a.wait("chat", pred=lambda e: e.get("sticker") == "fish")
    assert m and m["text"] == "哦"
    a.close()


# ---------- 私聊 ----------
def test_private_chat_isolated(hub):
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    c = TestClient(port, "charlie")
    a.hello(); b.hello(); c.hello()
    a.send({"t": "chat", "channel": "private", "to": b.uid, "text": "悄悄话"})
    got = b.wait("chat", pred=lambda e: e.get("text") == "悄悄话")
    assert got and got["to"] == b.uid
    assert not c.has("chat")     # 第三方收不到
    a.send({"t": "chat", "channel": "private", "to": 99999, "text": "x"})
    assert a.wait("error", pred=lambda e: e.get("code") == "offline")
    a.close(); b.close(); c.close()


def test_private_offline_message(hub):
    """R63 离线留言：好友离线也能发送，消息进 bus 历史（私聊历史 key 双向），
    对方上线拉该会话历史能看到；未登记的未知 uid 仍按既有语义拒收。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()                # bob 登记为已知用户后才下线
    bob_uid = b.uid
    b.close()                          # bob 下线（known 仍保留，视为离线好友）
    a.send({"t": "chat", "channel": "private", "to": bob_uid, "text": "离线留言1"})
    got = a.wait("chat", pred=lambda e: e.get("text") == "离线留言1")
    assert got and got.get("to") == bob_uid      # 发送方收回显，入历史而非被拒
    key = ChatBus.key("private", a.uid, bob_uid)   # 双向归一化 key：双方拉历史同 key
    assert any(m.get("text") == "离线留言1"
               for m in hub[0].bus.history(key))
    # 未登记未知 uid 仍拒收
    a.send({"t": "chat", "channel": "private", "to": 99999, "text": "x"})
    assert a.wait("error", pred=lambda e: e.get("code") == "offline")
    a.close()


# ---------- 群聊 ----------
def test_group_lifecycle(hub):
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    c = TestClient(port, "charlie")
    a.hello(); b.hello(); c.hello()
    a.send({"t": "group_create", "name": "摸鱼群", "public": 1})   # R54：公开群才可被直接加入
    gs = a.wait("group_state", pred=lambda e: e.get("name") == "摸鱼群")
    assert gs and gs["owner"] == a.uid
    gl = b.wait("group_list", pred=lambda e: any(g["name"] == "摸鱼群" for g in e["groups"]))
    gid = next(g["gid"] for g in gl["groups"] if g["name"] == "摸鱼群")
    b.send({"t": "group_join", "gid": gid})
    assert b.wait("group_state", pred=lambda e: e.get("gid") == gid and "加入" in (e.get("text") or ""))
    # 群聊只发给成员
    a.send({"t": "chat", "channel": "group", "to": gid, "text": "晚上开黑？"})
    got = b.wait("chat", pred=lambda e: e.get("text") == "晚上开黑？")
    assert got and got["channel"] == "group"
    assert not c.has("chat")
    # 退群后收不到
    b.send({"t": "group_leave", "gid": gid})
    a.wait("group_state", pred=lambda e: e.get("gid") == gid and "退群" in (e.get("text") or ""))
    a.send({"t": "chat", "channel": "group", "to": gid, "text": "还有人吗"})
    assert not b.wait("chat", pred=lambda e: e.get("text") == "还有人吗", timeout=0.5)
    # 最后一人退群 → 解散
    a.send({"t": "group_leave", "gid": gid})
    gl2 = b.wait("group_list", pred=lambda e: not any(g["gid"] == gid for g in e["groups"]))
    assert gl2 is not None
    a.close(); b.close(); c.close()


def _group_mk(hub, owner_nick, *members):
    """owner 建群 -> 其余成员入群；返回 (gid, {nick: TestClient})，成员均已确认在群。"""
    _, port, _ = hub
    clients = [TestClient(port, owner_nick)]
    for m in members:
        clients.append(TestClient(port, m))
    for c in clients:
        c.hello()
    o = clients[0]
    o.send({"t": "group_create", "name": "测试群", "public": 1})   # R54：公开群才可被直接加入
    gs = o.wait("group_state", pred=lambda e: e.get("name") == "测试群")
    assert gs is not None and gs["owner"] == o.uid
    assert gs["admins"] == [] and gs["mutes"] == {}
    gid = gs["gid"]
    by = {owner_nick: o}
    for c, m in zip(clients[1:], members):
        c.send({"t": "group_join", "gid": gid})
        c.wait("group_state", pred=lambda e: e.get("gid") == gid
               and any(u["uid"] == c.uid for u in e.get("members", [])))
        by[m] = c
    return gid, by


def test_group_manage_permissions(hub):
    """普通成员无权治理；群主/管理员才能操作，且管理员不能动群主。"""
    gid, by = _group_mk(hub, "alice", "bob", "charlie")
    a, b, c = by["alice"], by["bob"], by["charlie"]
    # 普通成员设管理员 → 拒绝
    b.send({"t": "group_set_admin", "gid": gid, "target": c.uid, "enable": True})
    assert b.wait("error", pred=lambda e: e["code"] == "perm")
    # 普通成员禁言 → 拒绝
    b.send({"t": "group_mute", "gid": gid, "target": c.uid, "duration": 600})
    assert b.wait("error", pred=lambda e: e["code"] == "perm")
    # 普通成员踢人 → 拒绝
    b.send({"t": "group_kick", "gid": gid, "target": c.uid})
    assert b.wait("error", pred=lambda e: e["code"] == "perm")
    # 群主设 bob 为管理员
    a.send({"t": "group_set_admin", "gid": gid, "target": b.uid, "enable": True})
    gs = b.wait("group_state", pred=lambda e: e.get("gid") == gid
                and e.get("admins") and b.uid in e.get("admins"))
    assert gs is not None
    # 管理员踢成员 ok
    b.send({"t": "group_kick", "gid": gid, "target": c.uid})
    b.wait("group_state", pred=lambda e: e.get("gid") == gid
           and "移出" in (e.get("text") or ""))
    kicked = c.wait("error", pred=lambda e: e["code"] == "kicked")
    assert kicked is not None
    # 管理员不能踢群主
    b.send({"t": "group_kick", "gid": gid, "target": a.uid})
    assert b.wait("error", pred=lambda e: e["code"] == "perm")
    # 管理员不能设管理员（仅群主）
    b.send({"t": "group_set_admin", "gid": gid, "target": b.uid, "enable": False})
    assert b.wait("error", pred=lambda e: e["code"] == "perm")
    a.close(); b.close(); c.close()


def test_group_mute_blocks_and_unmute(hub):
    """禁言拦截群内发言；到期/解禁后可发言。"""
    gid, by = _group_mk(hub, "alice", "bob")
    a, b = by["alice"], by["bob"]
    a.send({"t": "group_mute", "gid": gid, "target": b.uid, "duration": 600})
    b.wait("error", pred=lambda e: e["code"] == "muted")
    # 禁言中被拦
    b.send({"t": "chat", "channel": "group", "to": gid, "text": "禁言中的发言"})
    err = b.wait("error", pred=lambda e: e["code"] == "muted")
    assert err is not None
    # 解除禁言后可正常发言
    a.send({"t": "group_mute", "gid": gid, "target": b.uid, "duration": 0})
    a.wait("group_state", pred=lambda e: e.get("gid") == gid
           and "解除" in (e.get("text") or "") and b.uid not in e.get("mutes", {}))
    b.send({"t": "chat", "channel": "group", "to": gid, "text": "恢复正常"})
    assert b.wait("chat", pred=lambda e: e.get("text") == "恢复正常")
    a.close(); b.close()


def test_group_owner_transfer_and_cleanup(hub):
    """群主退群转交管理员；被踢者在重连后不再自动重入。"""
    gid, by = _group_mk(hub, "alice", "bob", "charlie")
    a, b, c = by["alice"], by["bob"], by["charlie"]
    a.send({"t": "group_set_admin", "gid": gid, "target": b.uid, "enable": True})
    b.wait("group_state", pred=lambda e: e.get("gid") == gid
           and b.uid in e.get("admins"))
    # 群主退群 -> 群主转交给管理员 bob
    a.send({"t": "group_leave", "gid": gid})
    gs = b.wait("group_state", pred=lambda e: e.get("gid") == gid
                and e.get("owner") == b.uid)
    assert gs is not None
    # 新群主 bob 踢 charlie
    b.send({"t": "group_kick", "gid": gid, "target": c.uid})
    assert c.wait("error", pred=lambda e: e["code"] == "kicked")
    a.close(); b.close(); c.close()


def test_group_announce_permission_and_broadcast(hub):
    """群公告：普通成员被拒；owner/admin 可发布/清除；广播 group_state 带 announce。"""
    gid, by = _group_mk(hub, "alice", "bob", "charlie")
    a, b, c = by["alice"], by["bob"], by["charlie"]
    # 普通成员设置 → 拒绝
    c.send({"t": "group_announce", "gid": gid, "text": "我发的公告"})
    assert c.wait("error", pred=lambda e: e["code"] == "perm")
    # 群主发布公告 → 全员收到带 announce 的 group_state
    a.send({"t": "group_announce", "gid": gid, "text": "今晚开黑八点"})
    for cli in (a, b, c):
        gs = cli.wait("group_state", pred=lambda e: e.get("gid") == gid
                      and (e.get("announce") or "") == "今晚开黑八点")
        assert gs is not None
    # 管理员发布 → 生效
    a.send({"t": "group_set_admin", "gid": gid, "target": b.uid, "enable": True})
    b.wait("group_state", pred=lambda e: e.get("gid") == gid
           and b.uid in e.get("admins"))
    b.send({"t": "group_announce", "gid": gid, "text": "管理员新公告"})
    gs2 = a.wait("group_state", pred=lambda e: e.get("gid") == gid
                 and (e.get("announce") or "") == "管理员新公告")
    assert gs2 is not None
    # 群主清除公告（空文本）→ announce 变空
    a.send({"t": "group_announce", "gid": gid, "text": ""})
    cleared = c.wait("group_state", pred=lambda e: e.get("gid") == gid
                     and "已清除" in (e.get("text") or ""))
    assert cleared is not None
    # 非成员设置 → 拒绝
    d = TestClient(hub[1], "dave")
    d.hello()
    d.send({"t": "group_announce", "gid": gid, "text": "外人公告"})
    assert d.wait("error", pred=lambda e: e["code"] == "perm" or e["code"] == "group")
    a.close(); b.close(); c.close(); d.close()


def test_voice_broadcast_and_permission(hub):
    """语音：公聊/私聊透传 voice/duration 字段；群内非成员/被禁言发语音被拒。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    # 公聊语音 → b 收到 chat voice 事件
    a.sendb({"t": "voice", "channel": "public", "duration": 2.5}, b"WAVDATA")
    vb = b.wait("chat", pred=lambda e: e.get("voice") and e.get("channel") == "public")
    assert vb is not None and vb["duration"] == 2.5
    # 私聊语音 → 送达对端
    a.sendb({"t": "voice", "channel": "private", "to": b.uid, "duration": 1.2}, b"WAVPRIV")
    vp = b.wait("chat", pred=lambda e: e.get("voice") and e.get("channel") == "private")
    assert vp is not None and vp["to"] == b.uid
    # 群：用独立昵称建群；非成员与成员均需正确收/拒
    gid, by = _group_mk(hub, "vowner", "vowel")
    o = by["vowner"]
    v = by["vowel"]
    d = TestClient(port, "dave")
    d.hello()
    d.sendb({"t": "voice", "channel": "group", "to": gid, "duration": 1}, b"X")
    assert d.wait("error", pred=lambda e: e["code"] in ("group", "perm"))
    # 成员语音 → 群主收到
    v.sendb({"t": "voice", "channel": "group", "to": gid, "duration": 0.8}, b"WAVGRP")
    gv = o.wait("chat", pred=lambda e: e.get("voice") and e.get("channel") == "group")
    assert gv is not None and gv["to"] == gid
    # 被禁言成员发语音 → muted
    o.send({"t": "group_mute", "gid": gid, "target": v.uid, "duration": 600})
    v.wait("error", pred=lambda e: e["code"] == "muted")
    v.sendb({"t": "voice", "channel": "group", "to": gid, "duration": 1}, b"X")
    assert v.wait("error", pred=lambda e: e["code"] == "muted")
    a.close(); b.close(); o.close(); v.close(); d.close()


# ---------- 历史 ----------
def test_history_sync_and_permission(hub):
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "chat", "text": "历史1"})
    a.send({"t": "chat", "channel": "private", "to": b.uid, "text": "私密历史"})
    b.wait("chat", pred=lambda e: e.get("text") == "历史1")
    b.wait("chat", pred=lambda e: e.get("text") == "私密历史")
    # 新成员欢迎自带公聊历史
    c = TestClient(port, "charlie")
    w = c.hello()
    assert any(e.get("text") == "历史1" for e in w["history"])
    # 私聊历史按配对隔离
    b.send({"t": "history", "channel": "private", "to": a.uid})
    hb = b.wait("history", pred=lambda e: e.get("channel") == "private")
    assert any(e.get("text") == "私密历史" for e in hb["msgs"])
    c.send({"t": "history", "channel": "private", "to": a.uid})
    hc = c.wait("history", pred=lambda e: e.get("channel") == "private")
    assert hc["msgs"] == [] or all(e.get("uid") == c.uid for e in hc["msgs"])
    # 无权限：群历史非成员
    c.send({"t": "history", "channel": "group", "to": 12345})
    assert c.wait("error", pred=lambda e: e.get("code") == "deny")
    a.close(); b.close(); c.close()


# ---------- 心跳踢人 ----------
def test_heartbeat_kick(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  sweep_interval=0.2, heartbeat_timeout=0.8)
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)
    a = TestClient(port, "sleepy")
    assert a.hello()
    deadline = time.time() + 4
    while a.alive and time.time() < deadline:
        time.sleep(0.1)
    assert not a.alive            # 45s 心跳超时（测试缩到 0.8s）被踢
    a.close()
    stop.set()
    time.sleep(0.2)


# ---------- 审计 ----------
def test_audit_log_written(hub, tmp_path):
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "chat", "text": "审计测试"})
    b.wait("chat", pred=lambda e: e.get("text") == "审计测试")
    a.close(); b.close()
    time.sleep(0.2)
    log_path = tmp_path / "audit" / (time.strftime("audit-%Y%m%d.jsonl"))
    assert log_path.exists()
    lines = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    types = {l["type"] for l in lines}
    assert {"login", "chat", "logout"} <= types
    assert all("text" not in l for l in lines)   # 正文不落盘
    a.close(); b.close()


# ---------- R13 表情回应 ----------
def test_reaction_add_remove_broadcast(hub):
    """对公聊消息加表情 → 两边收 REACTION（含 reactions 状态）；摘下 → 清空。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "chat", "text": "开会呢"})
    m = a.wait("chat", pred=lambda e: e.get("text") == "开会呢")
    seq = m["seq"]
    # bob 加 ❤
    b.send({"t": "reaction", "seq": seq, "emoji": "❤"})
    r = a.wait("reaction", pred=lambda e: e.get("seq") == seq)
    assert r and r["reactions"]["❤"] == {str(b.uid): r["reactions"]["❤"][str(b.uid)]}
    # 我自己（bob）也收到广播
    rb = b.wait("reaction", pred=lambda e: e.get("seq") == seq)
    assert rb and str(b.uid) in rb["reactions"]["❤"]
    # 摘下 → reactions 空桶被清掉
    b.send({"t": "reaction", "seq": seq, "emoji": "❤", "on": False})
    ra = a.wait("reaction", pred=lambda e: e.get("seq") == seq and "❤" not in e.get("reactions", {}))
    assert ra is not None and ra["reactions"] == {}
    a.close(); b.close()


def test_reaction_validation(hub):
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "chat", "text": "校验用"})
    m = a.wait("chat", pred=lambda e: e.get("text") == "校验用")
    seq = m["seq"]
    # 缺 seq / 缺 emoji
    a.send({"t": "reaction", "emoji": "❤"})
    assert a.wait("error", pred=lambda e: e["code"] == "seq")
    a.send({"t": "reaction", "seq": seq, "emoji": ""})
    assert a.wait("error", pred=lambda e: e["code"] == "emoji")
    # 不存在的 seq
    a.send({"t": "reaction", "seq": 999999, "emoji": "❤"})
    assert a.wait("error", pred=lambda e: e["code"] == "expired")
    # 已撤回的消息不可回应
    a.send({"t": "chat", "text": "将撤回"})
    m2 = a.wait("chat", pred=lambda e: e.get("text") == "将撤回")
    a.send({"t": "del", "seq": m2["seq"]})
    b.wait("del", pred=lambda e: e.get("seq") == m2["seq"])
    b.send({"t": "reaction", "seq": m2["seq"], "emoji": "❤"})
    assert b.wait("error", pred=lambda e: e["code"] == "dead")
    a.close(); b.close()


def test_reaction_private_permission(hub):
    """非私聊对方不可回应；群外人不可回应。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    c = TestClient(port, "charlie")
    a.hello(); b.hello(); c.hello()
    a.send({"t": "chat", "channel": "private", "to": b.uid, "text": "私聊回应"})
    m = b.wait("chat", pred=lambda e: e.get("text") == "私聊回应")
    # charlie（局外人）回应 → 拒绝
    c.send({"t": "reaction", "seq": m["seq"], "emoji": "👍"})
    assert c.wait("error", pred=lambda e: e["code"] == "forbid")
    a.close(); b.close(); c.close()


# ---------- R13 已读回执 ----------
def test_read_receipt_broadcast_and_monotonic(hub):
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "chat", "text": "已读我"})
    m1 = a.wait("chat", pred=lambda e: e.get("text") == "已读我")
    a.send({"t": "chat", "text": "已读我2"})
    m2 = a.wait("chat", pred=lambda e: e.get("text") == "已读我2")
    # bob 读到 m2 的 seq
    b.send({"t": "read", "channel": "public", "to": None, "seq": m2["seq"]})
    rd = a.wait("read", pred=lambda e: e.get("uid") == b.uid)
    assert rd and rd["key"] == "public" and rd["seq"] == m2["seq"]
    # 幂等：回退 seq 不广播（只前进不回退）
    b.send({"t": "read", "channel": "public", "to": None, "seq": m2["seq"] - 1})
    assert a.wait("read", timeout=0.5, pred=lambda e: e.get("uid") == b.uid) is None
    a.close(); b.close()


# ---------- R13 消息置顶 ----------
def test_pin_broadcast_and_snapshot(hub):
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "chat", "text": "重要公告"})
    m = a.wait("chat", pred=lambda e: e.get("text") == "重要公告")
    # alice 置顶
    a.send({"t": "pin", "seq": m["seq"], "on": True})
    p = b.wait("pin", pred=lambda e: e.get("seq") == m["seq"] and e.get("on"))
    assert p and p["key"] == "public" and p["msg"]["text"] == "重要公告"
    # 服务器侧状态可见
    with hub[0].lock:
        assert hub[0].pins.get("public", {}).get("seq") == m["seq"]
    # 取消置顶
    a.send({"t": "pin", "seq": m["seq"], "on": False})
    p2 = b.wait("pin", pred=lambda e: e.get("seq") == m["seq"] and not e.get("on"))
    assert p2 and p2["msg"] == {}
    a.close(); b.close()


def test_pin_delivered_in_welcome(hub):
    """新成员 hello 的 welcome 应携带可见的置顶快照。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "chat", "text": "置顶导览"})
    m = a.wait("chat", pred=lambda e: e.get("text") == "置顶导览")
    a.send({"t": "pin", "seq": m["seq"], "on": True})
    b.wait("pin", pred=lambda e: e.get("seq") == m["seq"] and e.get("on"))
    # charlie 上线 → welcome 自带 public 置顶
    c = TestClient(port, "charlie")
    w = c.hello()
    assert w, "charlie 未登录"
    assert any(p.get("key") == "public" and p.get("seq") == m["seq"] for p in w["pins"])
    a.close(); b.close(); c.close()


def test_pin_private_permission(hub):
    """局外人不能置顶/取消私聊消息；群外人不能置顶群消息。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    c = TestClient(port, "charlie")
    a.hello(); b.hello(); c.hello()
    a.send({"t": "chat", "channel": "private", "to": b.uid, "text": "私聊置顶"})
    m = b.wait("chat", pred=lambda e: e.get("text") == "私聊置顶")
    c.send({"t": "pin", "seq": m["seq"], "on": True})
    assert c.wait("error", pred=lambda e: e["code"] == "forbid")
    a.close(); b.close(); c.close()


# ---------- R14 会话清理（purge） ----------
def test_purge_deletes_up_to_seq(hub):
    """purge 只清服务器历史，广播给全体参与者。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    for txt in ("一", "二", "三"):
        a.send({"t": "chat", "text": txt})
    m3 = a.wait("chat", pred=lambda e: e.get("text") == "三")
    until = m3["seq"]
    a.send({"t": "purge", "channel": "public", "until_seq": until})
    ev = b.wait("purge", pred=lambda e: e.get("until_seq") == until)
    assert ev and ev["key"] == "public" and ev["removed"] >= 3
    # 服务器历史已清空该会话
    assert hub[0].bus.history("all") == []
    a.close(); b.close()


def test_purge_group_forbidden(hub):
    """群外人 / 私聊局外人不能清理对应频道。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    c = TestClient(port, "charlie")
    a.hello(); c.hello()
    a.send({"t": "chat", "channel": "private", "to": 999, "text": "x"})
    a.wait("error", pred=lambda e: e["code"] == "offline")
    # 私聊局外人发起 purge（目标不在线也拒绝）
    c.send({"t": "purge", "channel": "private", "to": a.uid, "until_seq": 1})
    assert c.wait("error", pred=lambda e: e["code"] == "forbid")
    a.close(); c.close()


# ---------- R14 阅后即焚（burn） ----------
def test_burn_deletes_after_all_read(hub):
    """burn 消息被全体读后，服务器广播 del 并从历史删除。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "chat", "text": "阅后即焚", "burn": True})
    m = a.wait("chat", pred=lambda e: e.get("text") == "阅后即焚")
    burn_seq = m["seq"]
    assert burn_seq in hub[0]._burn
    # 发送方视为已读，对端 bob 回一个非 burn 消息触发其已读帧
    b.send({"t": "read", "channel": "public", "to": None, "seq": burn_seq})
    # bob 读到 burn_seq → pend 全满足 → del 广播 + 历史删除
    a.wait("del", pred=lambda e: e.get("seq") == burn_seq and e.get("burn"))
    b.wait("del", pred=lambda e: e.get("seq") == burn_seq)
    assert burn_seq not in hub[0]._burn
    assert hub[0].bus.history("all") == []
    # 同会话更早消息不受影响：再发一条后仍是空→验证 discard 只删一条
    a.close(); b.close()


def test_burn_keeps_earlier_messages(hub):
    """burn 只删自己这一条，同会话更早消息保留。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "chat", "text": "保留我"})
    keep = a.wait("chat", pred=lambda e: e.get("text") == "保留我")
    a.send({"t": "chat", "text": "焚毁", "burn": True})
    burn = a.wait("chat", pred=lambda e: e.get("text") == "焚毁")
    b.send({"t": "read", "channel": "public", "to": None, "seq": burn["seq"]})
    a.wait("del", pred=lambda e: e.get("seq") == burn["seq"] and e.get("burn"))
    # 保留消息仍在服务器历史
    hist = hub[0].bus.history("all")
    assert any(m.get("seq") == keep["seq"] for m in hist)
    assert not any(m.get("seq") == burn["seq"] for m in hist)
    a.close(); b.close()


# ---------- R14 群 @提及 & @全员 ----------
def test_group_mention_everyone(hub):
    """群消息文本含 @全员/@所有人 → 广播事件带 everyone=True。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    c = TestClient(port, "charlie")
    a.hello(); b.hello(); c.hello()
    a.send({"t": "group_create", "name": "测试群", "public": 1})   # R54：公开群才可被直接加入
    st = a.wait("group_state", pred=lambda e: e.get("name") == "测试群")
    gid = st["gid"]
    b.send({"t": "group_join", "gid": gid})
    a.wait("group_state", pred=lambda e: e.get("gid") == gid)
    a.send({"t": "chat", "channel": "group", "to": gid, "text": "麻烦 @全员 看下"})
    ev = b.wait("chat", pred=lambda e: e.get("text", "").startswith("麻烦"))
    assert ev.get("everyone") is True
    a.close(); b.close(); c.close()


def test_group_mention_by_nick(hub):
    """@昵称 → 广播事件带 mentions 命中该成员 uid。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "group_create", "name": "M群", "public": 1})   # R54：公开群才可被直接加入
    st = a.wait("group_state", pred=lambda e: e.get("name") == "M群")
    gid = st["gid"]
    b.send({"t": "group_join", "gid": gid})
    a.wait("group_state", pred=lambda e: e.get("gid") == gid)
    a.send({"t": "chat", "channel": "group", "to": gid, "text": "hi @bob"})
    ev = b.wait("chat", pred=lambda e: e.get("text", "").startswith("hi"))
    assert b.uid in ev.get("mentions", [])
    # @未提及他人则不附带 mentions
    a.send({"t": "chat", "channel": "group", "to": gid, "text": "hello 大家"})
    ev2 = b.wait("chat", pred=lambda e: e.get("text") == "hello 大家")
    assert not ev2.get("mentions") and not ev2.get("everyone")
    a.close(); b.close()


# ---------- 网页端 ----------
def test_web_login_send_stream(hub):
    _, port, _ = hub
    wport = _free_port()
    httpd = serve_web(hub[0], port=wport)
    time.sleep(0.2)
    # 1) TCP 端就位
    tcp = TestClient(port, "tcpuser")
    tcp.hello()
    # 2) 网页端登录
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=10)
    conn.request("POST", "/api/login",
                 json.dumps({"nick": "webuser"}).encode(),
                 {"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = json.loads(resp.read().decode())
    assert data["ok"] and data["token"]
    token = data["token"]
    # 3) 网页端发公聊 → TCP 端收到
    conn.request("POST", "/api/send",
                 json.dumps({"token": token, "channel": "public",
                             "text": "来自网页端"}).encode(),
                 {"Content-Type": "application/json"})
    resp = conn.getresponse(); assert resp.read().decode()
    got = tcp.wait("chat", pred=lambda e: e.get("text") == "来自网页端")
    assert got and got["nick"] == "webuser"
    # 4) 网页端 SSE 收到 TCP 端消息
    sse_lines = []
    sse_done = threading.Event()

    def read_sse():
        c2 = http.client.HTTPConnection("127.0.0.1", wport, timeout=10)
        c2.request("GET", "/api/events?token=" + token)
        r = c2.getresponse()
        while True:
            line = r.readline()
            if not line:
                break
            sse_lines.append(line.decode("utf-8", "replace"))
            if "TCP入群" in line.decode("utf-8", "replace"):
                break
        c2.close()
        sse_done.set()

    th = threading.Thread(target=read_sse, daemon=True)
    th.start()
    time.sleep(0.5)
    tcp.send({"t": "chat", "text": "TCP入群了"})
    sse_done.wait(5)
    assert any("TCP入群了" in ln for ln in sse_lines)
    # 5) 网页端未登录直接取历史 → 401
    conn2 = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn2.request("GET", "/api/history?token=bad&channel=public")
    r2 = conn2.getresponse()
    assert r2.status == 401
    conn2.close()
    httpd.shutdown()
    tcp.close()


# ---------- R16 服务器全状态持久化 ----------
def test_serverstore_atomic_roundtrip(tmp_path):
    """ServerStore：正常保存可读回；缺文件/损坏文件回落空 dict。"""
    from server_store import ServerStore
    p = tmp_path / "state.json"
    store = ServerStore(str(p))
    payload = {"a": 1, "channels": [[1, 2], [3]], "nested": {"x": "汉"}}
    store.save(payload)
    assert store.load() == payload
    # 缺失文件 → 空 dict
    assert ServerStore(str(tmp_path / "nope.json")).load() == {}
    # 损坏内容 → 空 dict 不抛
    p.write_text("{{{bad json", encoding="utf-8")
    assert ServerStore(str(p)).load() == {}


def _hub_with_store(tmp_path, store_dir):
    """构造启用持久化的独立 Hub（每测孤立目录），只托底审计，不起 TCP。"""
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"))
    return Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"), store_dir=str(store_dir))


def test_persist_messages_and_restore(tmp_path):
    """消息/seq 落盘后重启同 store_dir 的新 Hub 应恢复频道历史并延续 seq。"""
    store_dir = tmp_path / "r16_msg"
    h1 = _hub_with_store(tmp_path, str(store_dir))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h1, port, stop, False), daemon=True).start()
    time.sleep(0.1)
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "chat", "text": "持久化一枝"})
    a.wait("chat", pred=lambda e: e.get("text") == "持久化一枝")
    h1._persist_flush()          # 强制落盘
    a.close(); b.close()
    stop.set(); time.sleep(0.2)

    h2 = _hub_with_store(tmp_path, str(store_dir))   # 模拟重启
    with h2.bus._lock:
        pub = [x for x in h2.bus._channels.get("all", [])]
    assert any(x.get("text") == "持久化一枝" for x in pub)
    assert h2.bus._seq > 0


def test_persist_uid_and_nick_reuse_after_restart(tmp_path):
    """nick_to_uid / uid_seq 落盘后重启仍保持——重启后同名重连复用同 uid。"""
    store_dir = tmp_path / "r16_uid"
    h1 = _hub_with_store(tmp_path, str(store_dir))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h1, port, stop, False), daemon=True).start()
    time.sleep(0.1)
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    uid_a, uid_b = a.uid, b.uid
    h1._persist_flush()
    a.close(); b.close()
    stop.set(); time.sleep(0.2)

    h2 = _hub_with_store(tmp_path, str(store_dir))
    assert h2.nick_to_uid["alice"] == uid_a
    assert h2.nick_to_uid["bob"] == uid_b
    # uid_seq 已推进到两 uid 之上 → 新加入者不复用已分配 uid
    assert h2._uid_seq > uid_a and h2._uid_seq > uid_b

    # 重启后新 Hub 上同名重连 → 仍复用同 uid（会话未在线时复用现存映射）
    port2 = _free_port()
    stop2 = threading.Event()
    threading.Thread(target=serve_tcp, args=(h2, port2, stop2, False), daemon=True).start()
    time.sleep(0.1)
    a2 = TestClient(port2, "alice")
    a2.hello()
    assert a2.uid == uid_a
    # R17 跨重启键稳定：bob 也重连后，私聊会话键仍用同一有序 uid 对
    # （草稿/已读/置顶的 key 含 uid 对，uid 复用 ⇒ 跨重启 key 不变）
    bs = TestClient(port2, "bob")
    bs.hello()
    assert bs.uid == uid_b
    k1 = tuple(sorted((int(uid_a), int(uid_b))))
    k2 = tuple(sorted((int(a2.uid), int(bs.uid))))
    assert k2 == k1, f"会话键跨重启漂移: {k1} vs {k2}"
    a2.close(); bs.close()
    stop2.set(); time.sleep(0.2)


def test_persist_group_reads_pins_restore(tmp_path):
    """群、已读回执、置顶、阅后即焚恢复。"""
    store_dir = tmp_path / "r16_state"
    h1 = _hub_with_store(tmp_path, str(store_dir))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h1, port, stop, False), daemon=True).start()
    time.sleep(0.1)
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    # 建群
    a.send({"t": "group_create", "name": "持久群", "public": 1})   # R54：公开群才可被直接加入
    ast = a.wait("group_state", pred=lambda e: e.get("name") == "持久群")
    gid = ast["gid"]
    b.send({"t": "group_join", "gid": gid})
    b.wait("group_state", pred=lambda e: e.get("gid") == gid)
    # 公聊消息 + 已读回执 + 置顶
    a.send({"t": "chat", "text": "公告正文"})
    m = a.wait("chat", pred=lambda e: e.get("text") == "公告正文")
    b.send({"t": "read", "channel": "public", "to": None, "seq": m["seq"]})
    a.send({"t": "pin", "seq": m["seq"], "on": True})
    a.wait("pin", pred=lambda e: e.get("seq") == m["seq"] and e.get("on"))
    h1._persist_flush()
    a.close(); b.close()
    stop.set(); time.sleep(0.2)

    h2 = _hub_with_store(tmp_path, str(store_dir))
    assert gid in h2.groups and h2.groups[gid]["name"] == "持久群"
    assert h2.groups[gid]["members"].get(str(a.uid)) is not None
    assert h2.pins.get("public", {}).get("seq") == m["seq"]
    key = "public"
    assert h2.reads.get(key, {}).get(str(b.uid)) == m["seq"]


# ---------- R16 阶段一：落盘优化（无变更跳过重建 / 单次写 / 快照独立性） ----------
def _wrap_persist(hub):
    """包一层 save / _snapshot_state，返回 (writes, builds) 两个计数器。"""
    writes, builds = [], []
    os_ = hub._snapshot_state
    ow = hub.store.save
    hub._snapshot_state = lambda: builds.append(1) or os_()
    hub.store.save = lambda *a: writes.append(1) or ow(*a)
    return writes, builds


def test_persist_skips_when_unchanged(tmp_path):
    """连续多次 _persist() 间无状态变更 → 只构建一次快照、不重复写盘。"""
    store_dir = tmp_path / "r16_skip"
    h = _hub_with_store(tmp_path, str(store_dir))
    writes, builds = _wrap_persist(h)
    # 空态首次落盘：构建+写各一次
    h._persist_flush()
    assert len(writes) == 1 and len(builds) == 1
    builds.clear(); writes.clear()
    # 无任何变更：连续多次 _persist（窗口内被节流折叠）→ 不重建、不写盘
    h._persist(); h._persist(); h._persist()
    assert len(builds) == 0, "无变更不应反复重建快照"
    assert len(writes) == 0, "无变更不应反复写盘"
    # 走出窗口后再次 _persist：构建后经内容对比判定无变更 → 仍不写盘
    h._persist_last -= h._persist_interval + 1
    h._persist()
    assert len(writes) == 0, "无变更走出窗口也不应写盘"


def test_persist_writes_latest_change(tmp_path):
    """状态变更后再次 _persist / flush 能落盘最新状态。"""
    store_dir = tmp_path / "r16_latest"
    h = _hub_with_store(tmp_path, str(store_dir))
    h._persist_flush()                       # 初始落盘
    # 造一个真实变更（走 handler 语义：改 live 后调 _persist）
    h.nick_to_uid["newbie"] = 1000
    h.pins["public"] = {"seq": 9, "nick": "alice"}
    h._persist()
    h._persist_flush()                       # 兜底写最新
    data = h.store.load()
    assert data["nick_to_uid"].get("newbie") == 1000
    assert data["pins"].get("public") == {"seq": 9, "nick": "alice"}
    # 再次读出与内存一致
    with h.lock:
        h2_snap = h._snapshot_state()
    assert h2_snap["pins"]["public"] == data["pins"]["public"]


def test_persist_flush_single_write_and_no_loss(tmp_path):
    """flush 只写最后一次（不再双写）、内容正确、空闲关停不丢。"""
    store_dir = tmp_path / "r16_flush"
    h = _hub_with_store(tmp_path, str(store_dir))
    writes, _ = _wrap_persist(h)
    h.reads["all"] = {"1": 5}
    h._persist_flush()                       # 一次 flush → 恰好一次写
    assert len(writes) == 1, f"flush 应只写一次: {len(writes)}"
    assert h.store.load()["reads"].get("all") == {"1": 5}
    # 空闲关停兜底：不再有变更，盘上仍是最新、不覆盖为旧
    h.store.save = (lambda *a: writes.append(1))  # 停止真正落盘，仅计数
    h._persist_flush()
    assert h.store.load()["reads"].get("all") == {"1": 5}, "关停兜底不丢最后状态"


def test_snapshot_isolation(tmp_path):
    """快照逐层独立：handler 原地改 live 状态不污染已构建快照（含消息子结构）。"""
    store_dir = tmp_path / "r16_iso"
    h = _hub_with_store(tmp_path, str(store_dir))
    with h.bus._lock:
        dq = h.bus._channels["all"]
        dq.append({"seq": 1, "uid": 100, "channel": "public", "to": None,
                   "nick": "alice", "text": "hi", "reactions": {}})
    snap = h._snapshot_state()
    snap_msg = snap["bus"]["channels"]["all"][0]
    live_msg = dq[0]
    assert snap_msg is not live_msg, "消息本体应为独立对象"
    assert snap_msg["reactions"] is not live_msg["reactions"], "reactions 应为独立 dict"
    # 原地修改 live（别动在 _snapshot_state 之外）：编辑文本 + 加回应 + 加子结构
    with h.bus._lock:
        live_msg["text"] = "EDITED"
        live_msg["reactions"]["heart"] = {}
        live_msg["rich"] = {"blocks": []}
    snap2 = snap["bus"]["channels"]["all"][0]
    assert snap2["text"] == "hi", "快照内容不被 handler 原地改动污染"
    assert "heart" not in snap2["reactions"], "快照 reactions 不被污染"
    assert "rich" not in snap2, "快照不出现 live 后续新增字段"


# ---------- R65：内容指纹替代常驻第二份快照 ----------
def test_persist_unchanged_skip_by_fingerprint(tmp_path):
    """R65：无变更判定改用内容指纹（md5(json)），不再常驻第二份全量快照。
    走出窗口后重建快照做指纹比对 → 无变更仍不写盘。"""
    store_dir = tmp_path / "r65_fp"
    h = _hub_with_store(tmp_path, str(store_dir))
    assert not hasattr(h, "_last_saved_state"), "不应再常驻第二份全量快照"
    writes, builds = _wrap_persist(h)
    h._persist_flush()
    builds.clear(); writes.clear()
    h._persist_last -= h._persist_interval + 1
    h._persist()                     # 建一次快照 → 指纹一致 → 不写
    assert len(builds) == 1 and len(writes) == 0
    # 真实变更 → 指纹变化 → 落盘
    h.reads["public"] = {"1": 3}
    h._persist_last -= h._persist_interval + 1
    h._persist()
    deadline = time.time() + 3
    while not writes and time.time() < deadline:
        time.sleep(0.01)
    assert len(writes) == 1, "状态变更后应落盘"


def test_persist_force_writes_synchronously(tmp_path):
    """R65：force=True 同步落盘——返回即已持久，不依赖后台 worker 窗口
    （关键变更：清空/解散/删号/定时队列快照）。"""
    store_dir = tmp_path / "r65_force"
    h = _hub_with_store(tmp_path, str(store_dir))
    h._persist_last -= h._persist_interval + 1
    h.reads["public"] = {"1": 7}
    h._persist(force=True)
    assert h.store.load()["reads"].get("public") == {"1": 7}
    # 同步写后，后台旧槽被丢弃：空槽不残留（不会稍后覆盖本次写）
    assert h._persist_slot is None and h._persist_pending is False


# ---------- R66：无变更也推进节流时钟 + ChatBus seq 索引 ----------
def test_persist_no_change_advances_throttle_clock(tmp_path):
    """R66：无变更走出窗口后只重建一次快照，并推进节流时钟——
    否则下一次 _persist()（如 _on_group_invite_get 等无变更调用）会再重建一次。"""
    store_dir = tmp_path / "r66_clock"
    h = _hub_with_store(tmp_path, str(store_dir))
    writes, builds = _wrap_persist(h)
    h._persist_flush()
    builds.clear(); writes.clear()
    h._persist_last -= h._persist_interval + 1
    h._persist()                     # 建快照 → 指纹一致 → 不写盘，但推进时钟
    assert len(builds) == 1 and len(writes) == 0
    h._persist(); h._persist()       # 时钟已推进 → 窗口内直接返回，不再重建
    assert len(builds) == 1, "无变更已推进节流时钟，不应反复重建快照"
    assert len(writes) == 0


def test_bus_seq_index_find_discard_sync(tmp_path):
    """R66：seq 索引与频道内容同源——publish/find/discard/clear 后一致。"""
    bus = ChatBus(10)
    m1 = bus.publish({"channel": "public", "uid": 1, "text": "a"})
    m2 = bus.publish({"channel": "private", "uid": 1, "to": 2, "text": "b"})
    k1, g1 = bus.find(m1["seq"])
    assert k1 == "all" and g1 is m1 or g1["seq"] == m1["seq"]
    k2, g2 = bus.find(m2["seq"])
    assert k2 == ChatBus.key("private", 1, 2) and g2["seq"] == m2["seq"]
    assert bus.find(99999) == (None, None)

    assert bus.discard(m2["seq"]) is True
    assert bus.find(m2["seq"]) == (None, None)
    assert bus.discard(m2["seq"]) is False          # 幂等：已丢弃
    assert bus.history(ChatBus.key("private", 1, 2)) == []

    assert bus.clear_all() == 1
    assert bus.find(m1["seq"]) == (None, None)
    assert bus.history("all") == []


def test_bus_seq_index_no_leak_past_maxlen(tmp_path):
    """R66：环形 maxlen 淘汰后索引同步摘除，不残留旧 seq（不泄漏、不再命中）。"""
    bus = ChatBus(3)
    seqs = [bus.publish({"channel": "public", "uid": 1,
                         "text": f"m{i}"})["seq"] for i in range(6)]
    assert len(bus._by_seq) == 3, "索引条数应与环形缓冲一致"
    for old in seqs[:3]:
        assert bus.find(old) == (None, None), "已淘汰消息不应再被 find 命中"
    for new in seqs[3:]:
        assert bus.find(new)[1]["seq"] == new


def test_bus_seq_index_clear_uid_and_purge():
    """R66：clear_uid / purge 后索引同步；未涉及的消息仍可命中。"""
    bus = ChatBus(50)
    keep = bus.publish({"channel": "public", "uid": 1, "text": "keep"})
    drop = bus.publish({"channel": "public", "uid": 2, "text": "drop"})
    assert bus.clear_uid(2) == 1
    assert bus.find(drop["seq"]) == (None, None)
    assert bus.find(keep["seq"])[1]["seq"] == keep["seq"]
    # purge：丢弃该频道 seq<=until 的消息
    m3 = bus.publish({"channel": "public", "uid": 1, "text": "c"})
    removed = bus.purge("public", 1, None, m3["seq"])
    assert removed == 2
    assert bus.find(keep["seq"]) == (None, None)
    assert bus.find(m3["seq"]) == (None, None)
    assert bus._by_seq == {}


def test_bus_seq_index_rebuilt_on_restore(tmp_path):
    """R66：从快照恢复后索引按频道内容重建（find 可用）。"""
    store_dir = tmp_path / "r66_reindex"
    h = _hub_with_store(tmp_path, str(store_dir))
    msg = h.bus.publish({"channel": "public", "uid": 1, "text": "hi"})
    h._persist_flush()
    h2 = _hub_with_store(tmp_path, str(store_dir))
    assert h2.bus.find(msg["seq"])[1]["text"] == "hi"


# ---------- R67 拍一拍 ----------
def test_nudge_public_broadcast_not_sender(hub):
    """R67：公聊拍一拍广播给在线应收方（不含拍者）；不入服务器历史。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "nudge", "channel": "public"})
    got = b.wait("nudge", pred=lambda e: e.get("channel") == "public"
                 and e.get("uid") == a.uid)
    assert got and got["nick"] == "alice"
    assert not a.has("nudge")                       # 服务器不回拍者（本地乐观渲染）
    assert hub[0].bus.history("public") == []       # 不入历史
    a.close(); b.close()


def test_nudge_private_only_peer(hub):
    """R67：私聊拍一拍仅双方可见，第三方收不到。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    c = TestClient(port, "charlie")
    a.hello(); b.hello(); c.hello()
    a.send({"t": "nudge", "channel": "private", "to": b.uid})
    got = b.wait("nudge", pred=lambda e: e.get("channel") == "private"
                 and e.get("to") == b.uid and e.get("uid") == a.uid)
    assert got
    assert not c.has("nudge")
    a.close(); b.close(); c.close()


def test_nudge_private_offline_target_ignored(hub):
    """R67：私聊拍一拍对方不在线 → 服务器静默忽略（同 typing 语义）。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "nudge", "channel": "private", "to": 999})
    assert not b.has("nudge")
    a.close(); b.close()


def test_nudge_group_target_nick(hub):
    """R67：群内拍指定成员 → 全员收 target/target_nick；非成员收不到。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    c = TestClient(port, "charlie")
    d = TestClient(port, "dave")
    for t in (a, b, c, d):
        t.hello()
    a.send({"t": "group_create", "name": "N群", "public": 1})
    st = a.wait("group_state", pred=lambda e: e.get("name") == "N群")
    gid = st["gid"]
    for t in (b, c):                             # d 在线但非群成员
        t.send({"t": "group_join", "gid": gid})
        a.wait("group_state", pred=lambda e: e.get("gid") == gid)
    a.send({"t": "nudge", "channel": "group", "to": gid, "target": c.uid})
    got = b.wait("nudge", pred=lambda e: e.get("channel") == "group"
                 and e.get("uid") == a.uid)
    assert got and got["to"] == gid and got["target"] == c.uid
    assert got["target_nick"] == "charlie"
    assert not d.has("nudge")                       # 非成员收不到
    a.close(); b.close(); c.close(); d.close()


def test_nudge_server_rate_limit(hub):
    """R67：服务器 5s/人 限速——同 uid 连发两帧只转发第一帧。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "nudge", "channel": "public"})
    a.send({"t": "nudge", "channel": "public"})
    time.sleep(0.3)
    with b._lock:
        n = sum(1 for e in b.events if e.get("t") == "nudge")
    assert n <= 1
    a.close(); b.close()


def test_nudge_illegal_channel_ignored(hub):
    """R67：未知频道拍一拍静默忽略。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "nudge", "channel": "unknown"})
    time.sleep(0.3)
    assert not b.has("nudge")
    a.close(); b.close()


def test_web_nudge_ok_forward_and_unauth(hub):
    """R67 网页端：POST /api/nudge → 服务器转 nudge 帧给 TCP 端；未登录 401。"""
    _, port, _ = hub
    wport = _free_port()
    httpd = serve_web(hub[0], port=wport)
    time.sleep(0.2)
    tcp = TestClient(port, "tcpuser")
    tcp.hello()
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=10)
    conn.request("POST", "/api/login",
                 json.dumps({"nick": "webuser"}).encode(),
                 {"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = json.loads(resp.read().decode())
    assert data["ok"] and data["token"]
    token = data["token"]
    # 未登录 → 401
    conn.request("POST", "/api/nudge",
                 json.dumps({"channel": "public"}).encode(),
                 {"Content-Type": "application/json"})
    r = conn.getresponse(); r.read()
    assert r.status == 401
    # 登录 → 广播给 TCP 端
    conn.request("POST", "/api/nudge",
                 json.dumps({"token": token, "channel": "public"}).encode(),
                 {"Content-Type": "application/json"})
    r = conn.getresponse()
    body = json.loads(r.read().decode())
    assert body.get("ok") is True
    got = tcp.wait("nudge", pred=lambda e: e.get("channel") == "public"
                   and e.get("nick") == "webuser")
    assert got
    conn.close(); httpd.shutdown(); tcp.close()


# ---------------- R68 窗口抖动 / 在线状态 ----------------

def test_shake_public_broadcast_not_sender(hub):
    """R68：公聊窗口抖动 → 其余在线者收到，拍者自己收不到。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "shake", "channel": "public"})
    got = b.wait("shake", pred=lambda e: e.get("channel") == "public")
    assert got and got.get("nick") == "alice"
    assert not a.has("shake")                       # 服务器不回发送者
    a.close(); b.close()


def test_shake_private_offline_target_ignored(hub):
    """R68：私聊窗口抖动目标离线 → 不转发。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "shake", "channel": "private", "to": 999999})
    time.sleep(0.3)
    assert not b.has("shake")
    a.close(); b.close()


def test_shake_server_rate_limit(hub):
    """R68：服务器 10s/人 限速——同 uid 连发两帧只转发第一帧。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "shake", "channel": "public"})
    a.send({"t": "shake", "channel": "public"})
    time.sleep(0.3)
    with b._lock:
        n = sum(1 for e in b.events if e.get("t") == "shake")
    assert n <= 1
    a.close(); b.close()


def test_status_set_persist_and_roster(hub):
    """R68：设置在线状态 → 广播 roster 携带 status；非法值报错不生效。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "status_set", "status": "busy"})
    ack = a.wait("status_ack", pred=lambda e: e.get("status") == "busy")
    assert ack
    got = b.wait("roster", pred=lambda e: any(
        u.get("uid") == a.uid and u.get("status") == "busy"
        for u in (e.get("online") or [])))
    assert got                                        # 他人 roster 同步
    a.send({"t": "status_set", "status": "nope"})
    err = a.wait("error", pred=lambda e: e.get("code") == "status")
    assert err                                        # 非法状态被拒
    a.close(); b.close()


def test_status_default_online_in_welcome(hub):
    """R68：未设置过状态的用户，welcome 里 status 默认 online。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    w = a.hello()
    assert w and w.get("status") == "online"
    a.close()


def test_group_detail_member_status_online(hub):
    """R68：群详情成员带 online/status（在线者非 offline）。"""
    _, port, _ = hub
    a = TestClient(port, "alice")
    b = TestClient(port, "bob")
    a.hello(); b.hello()
    a.send({"t": "group_create", "name": "S群", "public": 1})
    st = a.wait("group_state", pred=lambda e: e.get("name") == "S群")
    gid = st["gid"]
    b.send({"t": "group_join", "gid": gid})
    a.wait("group_state", pred=lambda e: e.get("gid") == gid and len(
        e.get("members") or []) >= 2)
    detail = hub[0].group_detail(gid, a.uid)
    m = {x["uid"]: x for x in detail["members"]}
    assert m[b.uid]["online"] is True
    assert m[b.uid]["status"] in ("online", "away", "busy")
    a.close(); b.close()
