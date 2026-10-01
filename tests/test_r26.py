# -*- coding: utf-8 -*-
"""R26 第二梯队四件套回归：投票（A）、频道广播（B）、静默发送（C）、
链接预览（D，服务器出网抓取 + 缓存补发）。

e2e 用真 socket + 真 Hub（127.0.0.1 随机端口），与 test_r25.py 同款夹具；
预览元数据解析 / SSRF 拦截用纯单元断言；投票权威状态用 store 重启验证。
"""
import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, serve as serve_tcp, fetch_preview, _parse_meta
from client_core import ClientCore


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
    """on_event 收集器：wait 匹配即移除（与 TestClient.wait 同语义）。"""
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
            return any(e.get("t") == t and (pred is None or pred(e))
                       for e in self.events)


def _make_core(port: int, nick: str, tmp_path, **kw):
    kw.setdefault("heartbeat_interval", 0.1)
    kw.setdefault("heartbeat_timeout", 0.8)
    kw.setdefault("reconnect_base", 0.05)
    kw.setdefault("reconnect_max", 0.3)
    hist_dir = kw.pop("history_dir", str(tmp_path / f"hist_{nick}"))
    return ClientCore(host="127.0.0.1", port=port, nick=nick,
                      history_dir=hist_dir, **kw)


def _spawn(port: int, nick: str, tmp_path):
    core = _make_core(port, nick, tmp_path)
    col = Collector(core)
    core.start()
    w = col.wait("welcome", timeout=8.0)
    assert w is not None, f"{nick} 未收到 welcome"
    return core, col


def _online(col, timeout: float = 3.0):
    return col.wait("state", timeout=timeout,
                    pred=lambda e: e.get("state") == "online")


def _err(col, code: str, timeout: float = 3.0):
    return col.wait("error", timeout=timeout, pred=lambda e: e.get("code") == code)


# ---------- R26A 投票 ----------
def test_poll_public_create_and_vote(hub, tmp_path):
    """公聊发起投票：两端收 poll；投票后服务器广播 poll_state 权威票数。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_poll(channel="public", question="今晚吃什么？",
                           options=["火锅", "烧烤", "日料"])
        ev = ac.wait("poll", pred=lambda e: e.get("channel") == "public")
        assert ev and ev["poll"]["question"] == "今晚吃什么？"
        seq = ev["seq"]
        assert ev["poll"]["options"] == ["火锅", "烧烤", "日料"]
        assert ev["poll"]["votes"] == {} and ev["poll"]["end"] > time.time()
        evb = bc.wait("poll", pred=lambda e: e.get("seq") == seq)
        assert evb is not None                      # 双方都收到投票消息
        assert b.send_poll_vote(seq, 1)             # bob 投「烧烤」
        st = bc.wait("poll_state", pred=lambda e: e.get("seq") == seq)
        assert st and st["votes"].get(str(b.uid)) == 1
        sa = ac.wait("poll_state", pred=lambda e: e.get("seq") == seq)
        assert sa and sa["votes"].get(str(b.uid)) == 1   # 票数广播给所有人
        # 本地历史里的投票消息票数已更新（同一 dict 原地改；键为 JSON 字符串）
        msgs = a.history("public")
        m = next(x for x in msgs if x.get("seq") == seq)
        assert m["poll"]["votes"].get(str(b.uid)) == 1
    finally:
        a.stop(); b.stop()


def test_poll_private_only_peers_and_forbid(hub, tmp_path):
    """私聊投票只发给会话双方；第三方既收不到也不能投票。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    c3, cc = _spawn(port, "charlie", tmp_path)
    try:
        assert _online(ac) and _online(bc) and _online(cc)
        assert a.send_poll(channel="private", to=b.uid, question="去哪？",
                           options=["A", "B"])
        ev = ac.wait("poll", pred=lambda e: e.get("channel") == "private")
        seq = ev["seq"]
        assert bc.wait("poll", pred=lambda e: e.get("seq") == seq)
        assert not cc.has("poll")                   # 第三方收不到
        assert c3.send_poll_vote(seq, 0) is True    # 能发帧，但服务器拒绝
        assert _err(cc, "forbid") is not None       # 不在该频道，无法投票
    finally:
        a.stop(); b.stop(); c3.stop()


def test_poll_validation_errors(hub, tmp_path):
    """发起参数与投票参数校验：空问题/选项不足/无效选项/不存在 seq。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    try:
        assert _online(ac)
        a.send_poll(channel="public", question="  ", options=["a", "b"])
        assert _err(ac, "empty") is not None
        a.send_poll(channel="public", question="问题", options=["只有一个"])
        assert _err(ac, "poll") is not None
        assert a.send_poll(channel="public", question="合法问题", options=["x", "y"])
        ev = ac.wait("poll")
        seq = ev["seq"]
        a.send_poll_vote(seq, 99)                   # 越界选项
        assert _err(ac, "poll") is not None
        a.send_poll_vote(999999, 0)                 # 不存在的投票
        assert _err(ac, "expired") is not None
    finally:
        a.stop()


def test_poll_rewote_changes_vote(hub, tmp_path):
    """一人一票：重复投 = 改票，最终只保留最后一次。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_poll(channel="public", question="改票测试",
                           options=["一", "二"])
        ev = ac.wait("poll")
        seq = ev["seq"]
        assert b.send_poll_vote(seq, 0)
        bc.wait("poll_state", pred=lambda e: e.get("seq") == seq)
        assert b.send_poll_vote(seq, 1)             # 改票
        st = bc.wait("poll_state", pred=lambda e: e.get("seq") == seq)
        assert st["votes"] == {str(b.uid): 1}       # 仅一条记录且为最后选择
    finally:
        a.stop(); b.stop()


def test_poll_ended_rejected(hub, tmp_path):
    """截止后投票被拒（服务器按 end 判止）。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_poll(channel="public", question="限时投票",
                           options=["早", "晚"])
        ev = ac.wait("poll")
        seq = ev["seq"]
        hub_obj = hub[0]
        with hub_obj.lock:
            hub_obj._polls[seq]["end"] = time.time() - 1   # 模拟已截止
        b.send_poll_vote(seq, 0)
        assert _err(bc, "ended") is not None
    finally:
        a.stop(); b.stop()


def test_poll_edit_blocked(hub, tmp_path):
    """投票消息结构固定，服务器禁止编辑。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    try:
        assert _online(ac)
        assert a.send_poll(channel="public", question="不可篡改",
                           options=["是", "否"])
        ev = ac.wait("poll")
        assert a.send_edit(ev["seq"], "改个标题") is True
        assert _err(ac, "poll") is not None
    finally:
        a.stop()


def test_poll_persist_restore(tmp_path):
    """投票权威状态入 R16 快照：重启后 _polls 与历史票数仍保留。"""
    store_dir = tmp_path / "r26_poll"
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"))
    h1 = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"), store_dir=str(store_dir))
    port1 = _free_port()
    stop1 = threading.Event()
    threading.Thread(target=serve_tcp, args=(h1, port1, stop1, False), daemon=True).start()
    time.sleep(0.1)
    a, ac = _spawn(port1, "alice", tmp_path)
    b, bc = _spawn(port1, "bob", tmp_path)
    bob_uid = b.uid
    try:
        assert _online(ac) and _online(bc)
        assert a.send_poll(channel="public", question="重启后还在？",
                           options=["在", "不在"])
        ev = ac.wait("poll")
        seq = ev["seq"]
        assert b.send_poll_vote(seq, 0)
        bc.wait("poll_state", pred=lambda e: e.get("seq") == seq)
        h1._persist_flush()
    finally:
        a.stop(); b.stop()
    stop1.set(); time.sleep(0.2)

    h2 = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"), store_dir=str(store_dir))
    assert seq in h2._polls
    votes = h2._polls[seq]["votes"]
    assert votes.get(bob_uid) == [0]                # bob 投了选项 0（R70C：键 int、值 list）
    with h2.bus._lock:
        msgs = [x for x in h2.bus._channels.get("all", [])]
    m = next(x for x in msgs if x.get("seq") == seq)
    assert m["poll"]["votes"].get(str(bob_uid)) == 0


# ---------- R26B 频道广播 ----------
def test_channel_create_kind_and_readonly(hub, tmp_path):
    """频道 = 仅创建者可发言：成员发言被拒（readonly），创建者正常。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.create_group("📢 官方公告", broadcast=True, public=True)  # R54：公开群才可被直接加入
        ev = ac.wait("group_state", pred=lambda e: e.get("name") == "📢 官方公告")
        assert ev is not None
        gid = ev["gid"]
        assert ac.wait(
            "group_list",
            pred=lambda e: any(g.get("gid") == gid
                               and g.get("kind") == "channel"
                               for g in e.get("groups", []))) is not None
        assert a.groups[gid]["kind"] == "channel"   # group_list 带频道标记
        assert b.join_group(gid) is True
        assert bc.wait("group_state", pred=lambda e: e.get("gid") == gid) is not None
        assert bc.wait(
            "group_list",
            pred=lambda e: any(g.get("gid") == gid
                               and g.get("kind") == "channel"
                               for g in e.get("groups", []))) is not None
        assert b.groups[gid]["kind"] == "channel"   # 成员端同样可见只读标记
        # 成员发言 → 拒绝
        assert b.send_chat("我来发言", channel="group", to=gid) is True
        assert _err(bc, "readonly") is not None
        # 创建者发言 → 正常送达
        assert a.send_chat("官方消息", channel="group", to=gid) is True
        got = bc.wait("chat", pred=lambda e: e.get("group_name") == "📢 官方公告"
                       and e.get("text") == "官方消息")
        assert got and got["uid"] == a.uid
    finally:
        a.stop(); b.stop()


def test_normal_group_kind_empty(hub, tmp_path):
    """普通群无频道标记（kind=""）。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    try:
        assert _online(ac)
        assert a.create_group("普通讨论组", public=True) is True   # R54：公开群才可被直接加入
        ev = ac.wait("group_state", pred=lambda e: e.get("name") == "普通讨论组")
        assert ev is not None
        gid = ev["gid"]
        assert ac.wait(
            "group_list",
            pred=lambda e: any(g.get("gid") == gid
                               and g.get("kind", "") == ""
                               for g in e.get("groups", []))) is not None
        assert a.groups[gid]["kind"] == ""
        # 成员（bob 加入）可正常发言，不受只读限制
        b, bc = _spawn(port, "bob", tmp_path)
        try:
            assert _online(bc)
            assert b.join_group(gid) is True
            assert bc.wait("group_state", pred=lambda e: e.get("gid") == gid) is not None
            assert bc.wait(
                "group_list",
                pred=lambda e: any(g.get("gid") == gid
                                   and g.get("kind", "") == ""
                                   for g in e.get("groups", []))) is not None
            assert b.send_chat("随便聊聊", channel="group", to=gid) is True
            assert ac.wait("chat", pred=lambda e: e.get("text") == "随便聊聊")
        finally:
            b.stop()
    finally:
        a.stop()


# ---------- R26C 静默发送 ----------
def test_silent_flag_transit(hub, tmp_path):
    """静默消息透传 silent 标记；普通消息不带该字段。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_chat("悄悄话", silent=True)
        got = bc.wait("chat", pred=lambda e: e.get("text") == "悄悄话")
        assert got and got.get("silent") is True
        assert a.send_chat("普通消息")
        got2 = bc.wait("chat", pred=lambda e: e.get("text") == "普通消息")
        assert got2 and "silent" not in got2
    finally:
        a.stop(); b.stop()


# ---------- R26D 链接预览 ----------
def test_parse_meta_og():
    """HTML 元数据解析：og 优先于 title/description，取 domain。"""
    html = ("<html><head><title>页签标题</title>"
            "<meta property=\"og:title\" content=\"OG大标题\">"
            "<meta property=\"og:description\" content=\"OG简介\">"
            "<meta name=\"description\" content=\"普通简介\">"
            "</head><body></body></html>")
    meta = _parse_meta(html, "https://example.com/a/b", CFG)
    assert meta["title"] == "OG大标题"           # og:title 优先
    assert meta["desc"] == "OG简介"
    assert meta["domain"] == "example.com"
    assert meta["url"] == "https://example.com/a/b"
    # 无 og 时降级 title/description
    meta2 = _parse_meta("<html><head><title>只有标题</title></head></html>",
                        "https://ex.com/", CFG)
    assert meta2["title"] == "只有标题" and meta2["desc"] == ""


def test_fetch_preview_loopback_blocked():
    """SSRF 拦截：环回地址出网抓取一律返回 None。"""
    assert fetch_preview("http://127.0.0.1:9/x", CFG) is None
    assert fetch_preview("http://localhost/x", CFG) is None


def test_preview_cache_hit_dispatches(hub, tmp_path):
    """缓存命中（TTL 内）无需出网即补发 preview；chat → preview 有序收帧。"""
    h_obj, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        url = "https://example.com/art"
        meta = {"title": "缓存标题", "desc": "缓存描述",
                "domain": "example.com", "url": url, "image": ""}
        with h_obj._preview_lock:
            h_obj._preview_cache[url] = (time.time(), meta)
        assert a.send_chat(f"看这个 {url}") is True
        chat = bc.wait("chat", pred=lambda e: e.get("text", "").startswith("看这个"))
        assert chat is not None
        pv = bc.wait("preview", pred=lambda e: e.get("seq") == chat["seq"])
        assert pv and pv["preview"]["title"] == "缓存标题"
        # 本地历史里消息已附预览卡片（chat 先入历史，preview 再原地附上）
        msgs = b.history("public")
        m = next(x for x in msgs if x.get("seq") == chat["seq"])
        assert m["preview"]["title"] == "缓存标题"
    finally:
        a.stop(); b.stop()


# ---------- R26 GUI 冒烟（投票气泡渲染/点击 + 预览卡片） ----------
def test_gui_smoke_r26(hub, tmp_path):
    import tkinter as tk
    try:
        r0 = tk.Tk()
        r0.destroy()
    except tk.TclError as exc:
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    from widgets.msg_list import MsgList
    root = tk.Tk()                                    # 保持映射：canvas item 事件需要可视窗口
    try:
        clicked = []
        ml = MsgList(root, ("Microsoft YaHei UI", 9),
                     on_poll_vote=lambda i, oi: clicked.append((i, oi)))
        ml.configure(width=420, height=420)
        ml.pack(fill="both", expand=True)
        root.update_idletasks()
        root.update()
        now = time.time()
        # 投票气泡：渲染 + 选项热区可点（未截止）+ 点选回调触发
        poll = {"t": "poll", "seq": 11, "uid": 1, "nick": "alice",
                "channel": "public", "ts": now,
                "poll": {"question": "中午吃啥？", "options": ["面", "饭", "粉"],
                         "votes": {"2": 0}, "end": now + 3600}}
        ml.append(poll)
        ml.set_poll_state(11, {"2": 0, "3": 1})       # 票数更新重绘
        root.update_idletasks()
        root.update()
        assert ml.count == 1
        hits = ml.find_withtag("r26poll0_2")          # 第 0 行「粉」热区存在
        assert hits, "投票选项热区未创建"
        x0, y0, x1, y1 = ml.bbox(hits[0])
        ml.event_generate("<Button-1>", x=(x0 + x1) // 2, y=(y0 + y1) // 2)
        ml.event_generate("<ButtonRelease-1>", x=(x0 + x1) // 2, y=(y0 + y1) // 2)
        root.update()
        assert clicked == [(0, 2)]
        # 预览卡片：URL 消息补发 preview 后原地附卡片，渲染不崩
        chat = {"t": "chat", "seq": 12, "uid": 1, "nick": "alice",
                "channel": "public", "ts": now,
                "text": "看 https://example.com/x"}
        ml.append(chat)
        ml.set_preview(12, {"title": "标题", "desc": "描述",
                            "domain": "example.com", "url": "https://example.com/x",
                            "image": ""})
        root.update_idletasks()
        root.update()
        assert ml.count == 2
        assert ml._rows[1].preview and ml._rows[1].preview["domain"] == "example.com"
        # 已截止投票：不再生成可点热区
        poll2 = {"t": "poll", "seq": 13, "uid": 1, "nick": "alice",
                 "channel": "public", "ts": now,
                 "poll": {"question": "过期", "options": ["a", "b"],
                          "votes": {}, "end": now - 1}}
        ml.append(poll2)
        root.update_idletasks()
        root.update()
        assert not ml.find_withtag("r26poll2_0")
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
