# -*- coding: utf-8 -*-
"""R70 批次回归：TG 残余补齐 + 摸鱼差异化。

A 剧透文字（rich/markdown 原语）、B 编辑历史、D 群慢速模式、C 投票增强
（匿名 / 多选 / 测验）。e2e 用真 socket + 真 Hub（127.0.0.1 随机端口），
与 test_r26.py 同款夹具；纯解析类断言不依赖网络。
"""
import json
import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, serve as serve_tcp
from client_core import ClientCore
from widgets import rich, runs


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
    """on_event 收集器：wait 匹配即移除（与 test_r26 同语义）+ drain 全量取。"""
    __test__ = False

    def __init__(self, core: ClientCore) -> None:
        self.events = []
        self._lock = threading.Lock()
        core._on_event = self._on

    def _on(self, ev: dict) -> None:
        with self._lock:
            self.events.append(ev)

    def _match(self, t, pred):
        return [e for e in self.events
                if e.get("t") == t and (pred is None or pred(e))]

    def wait(self, t: str, timeout: float = 3.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                hits = self._match(t, pred)
                if hits:
                    self.events.remove(hits[0])
                    return hits[0]
            time.sleep(0.01)
        return None

    def drain(self, t: str, timeout: float = 1.0, pred=None) -> list:
        """收集 timeout 内所有匹配事件（用于同时广播 + 单播的场景）。"""
        deadline = time.time() + timeout
        out = []
        while time.time() < deadline:
            with self._lock:
                hits = self._match(t, pred)
                for e in hits:
                    self.events.remove(e)
            out.extend(hits)
            if out:
                return out
            time.sleep(0.01)
        return out

    def has(self, t: str, pred=None) -> bool:
        with self._lock:
            return bool(self._match(t, pred))


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


# ---------- R70A 剧透文字 ----------
def test_spoiler_parse_basic():
    """`||x||` 解析成 spoiler run，前后保留普通文本。"""
    segs = rich.parse("前 ||秘密|| 后")
    assert segs == [("前 ", "plain", None), ("秘密", rich.SPOILER, None),
                    (" 后", "plain", None)]
    assert rich.SPOILER in rich.ALLOWED_KINDS


def test_spoiler_unclosed_stays_plain():
    """未闭合的 `||` 保持原文，不产生遮盖段。"""
    segs = rich.parse("||没闭合")
    assert all(k != rich.SPOILER for _t, k, _h in segs)
    assert "||没闭合" in "".join(t for t, _k, _h in segs)


def test_spoiler_not_inside_code():
    """代码段内 `||x||` 不误判为剧透（代码优先）。"""
    segs = rich.parse("`||x||`")
    assert segs == [("||x||", "code", None)]


def test_spoiler_wrap_keeps_href_slot():
    """换行拆分保留 seg 第 3 槽（渲染层用它塞 run 索引）。"""
    segs = [(("秘密" * 2), rich.SPOILER, "7")]
    lines = runs.wrap_segments(segs, 20, lambda s, k: len(s) * 8)
    assert sum(len(ln) for ln in lines) >= 1
    assert all(len(seg) == 3 for ln in lines for seg in ln)


# ---------- R70B 编辑历史 ----------
def test_edit_history_accumulates_and_truncates(hub, tmp_path):
    """编辑把旧版本入 edits；超上限丢最旧（单条截断由 edit_history_len 控制）。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    try:
        assert _online(ac)
        assert a.send_chat("第一版")
        chat = ac.wait("chat", pred=lambda e: e.get("text") == "第一版")
        seq = chat["seq"]
        assert a.send_edit(seq, "第二版")
        ev = ac.wait("edit", pred=lambda e: e.get("seq") == seq)
        assert ev and ev["text"] == "第二版"
        assert [x["text"] for x in ev["edits"]] == ["第一版"]
        assert a.send_edit(seq, "第三版")
        ev2 = ac.wait("edit", pred=lambda e: e.get("seq") == seq)
        assert [x["text"] for x in ev2["edits"]] == ["第一版", "第二版"]
    finally:
        a.stop()


def test_edit_history_max_truncates(tmp_path):
    """edit_history_max=2：连续编辑 3 次只保留最近 2 个历史版本。"""
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"), edit_history_max=2)
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False), daemon=True).start()
    time.sleep(0.1)
    a, ac = _spawn(port, "alice", tmp_path)
    try:
        assert _online(ac)
        assert a.send_chat("v1")
        seq = ac.wait("chat", pred=lambda e: e.get("text") == "v1")["seq"]
        for txt in ("v2", "v3", "v4"):
            assert a.send_edit(seq, txt)
            ac.wait("edit", pred=lambda e: e.get("seq") == seq)
        with h.bus._lock:
            _k, msg = h.bus.find(seq)
        assert [x["text"] for x in msg["edits"]] == ["v2", "v3"]   # 最旧的 v1 被丢弃
    finally:
        a.stop()
        stop.set()
        time.sleep(0.2)


# ---------- R70D 群慢速模式 ----------
def test_group_slow_gate_and_exempt(hub, tmp_path):
    """慢速档内二次发言被拒（slow）；群主/管理员豁免。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.create_group("慢速群", public=True)
        gid = ac.wait("group_state", pred=lambda e: e.get("name") == "慢速群")["gid"]
        assert b.join_group(gid)
        bc.wait("group_state", pred=lambda e: e.get("gid") == gid)
        assert a.send_group_slow(gid, 5)             # 开 5 秒慢速
        bc.wait("group_state", pred=lambda e: e.get("gid") == gid
                and e.get("slow") == 5)
        assert b.send_chat("第一条", channel="group", to=gid)
        assert bc.wait("chat", pred=lambda e: e.get("text") == "第一条") is not None
        assert b.send_chat("第二条", channel="group", to=gid)   # 档内第二条
        assert _err(bc, "slow") is not None
        # owner 豁免：连发两条都不被拦
        assert a.send_chat("管理一", channel="group", to=gid)
        assert a.send_chat("管理二", channel="group", to=gid)
        assert ac.wait("chat", pred=lambda e: e.get("text") == "管理二") is not None
    finally:
        a.stop(); b.stop()


def test_group_slow_beaten_by_mute(hub, tmp_path):
    """优先级：禁言 > 慢速（被禁言时报 muted 而不是 slow）。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.create_group("优先级群", public=True)
        gid = ac.wait("group_state", pred=lambda e: e.get("name") == "优先级群")["gid"]
        assert b.join_group(gid)
        bc.wait("group_state", pred=lambda e: e.get("gid") == gid)
        assert a.send_group_slow(gid, 30)
        assert a.mute_member(gid, b.uid, 60)         # 直接禁言 bob
        bc.wait("group_state", pred=lambda e: e.get("gid") == gid and e.get("mutes"))
        assert b.send_chat("我还能说话吗", channel="group", to=gid)
        assert _err(bc, "muted") is not None
    finally:
        a.stop(); b.stop()


# ---------- R70C 投票增强 ----------
def test_poll_anonymous_never_leaks_uid(hub, tmp_path):
    """匿名投票：广播不含 votes，投票人只收到本人 mine（无 uid→选项映射）。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_poll(channel="public", question="匿名测试",
                           options=["甲", "乙"], anonymous=True)
        seq = ac.wait("poll", pred=lambda e: e.get("channel") == "public")["seq"]
        assert b.send_poll_vote(seq, 1)
        bcast = ac.drain("poll_state", timeout=2.0,
                         pred=lambda e: e.get("seq") == seq)
        assert bcast, "发起人未收到匿名广播"
        assert "votes" not in bcast[0]               # 匿名不广播 uid→idx
        assert bcast[0].get("counts") == [0, 1] and bcast[0].get("total") == 1
        mine_ev = bc.drain("poll_state", timeout=2.0,
                           pred=lambda e: e.get("seq") == seq and "mine" in e)
        assert mine_ev and mine_ev[0]["mine"] == [1]  # 本人只拿到自己的选择
        assert "votes" not in mine_ev[0]
    finally:
        a.stop(); b.stop()


def test_poll_multi_toggle(hub, tmp_path):
    """多选：可叠加选择，再点同项取消。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_poll(channel="public", question="多选测试",
                           options=["一", "二", "三"], multi=True)
        seq = ac.wait("poll", pred=lambda e: e.get("channel") == "public")["seq"]
        assert b.send_poll_vote(seq, 0)
        st = bc.wait("poll_state", pred=lambda e: e.get("seq") == seq)
        assert st["counts"] == [1, 0, 0]
        assert b.send_poll_vote(seq, 2)              # 再选一项
        st2 = bc.wait("poll_state", pred=lambda e: e.get("seq") == seq)
        assert st2["counts"] == [1, 0, 1]
        assert b.send_poll_vote(seq, 0)              # 再点第一项 = 取消
        st3 = bc.wait("poll_state", pred=lambda e: e.get("seq") == seq)
        assert st3["counts"] == [0, 0, 1]
    finally:
        a.stop(); b.stop()


def test_poll_quiz_hides_correct_until_end(hub, tmp_path):
    """测验：结束前不下发 correct；到点 sweep 后广播正确项。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    h = hub[0]
    try:
        assert _online(ac) and _online(bc)
        assert a.send_poll(channel="public", question="1+1=?",
                           options=["2", "3"], quiz=True, correct=0)
        ev = ac.wait("poll", pred=lambda e: e.get("channel") == "public")
        seq = ev["seq"]
        assert "correct" not in ev["poll"]           # 消息本身不带答案
        assert b.send_poll_vote(seq, 1)
        st = bc.wait("poll_state", pred=lambda e: e.get("seq") == seq)
        assert "correct" not in st                   # 结束前不下发
        with h.lock:
            h._polls[seq]["end"] = time.time() - 1   # 模拟到点
        h._sweep_polls(time.time())
        st2 = bc.wait("poll_state", timeout=3.0,
                      pred=lambda e: e.get("seq") == seq and "correct" in e)
        assert st2 and st2["correct"] == 0
    finally:
        a.stop(); b.stop()


def test_poll_quiz_requires_correct(hub, tmp_path):
    """测验必须给出合法正确项，否则拒绝。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    try:
        assert _online(ac)
        # 绕过客户端封装（send_poll 会把 correct=None 兜底成 0），直接发缺 correct 的原始帧
        assert a._send_frame({"t": "poll", "channel": "public", "question": "问题",
                              "options": ["a", "b"], "quiz": True})
        assert _err(ac, "poll") is not None
        assert a.send_poll(channel="public", question="问题",
                           options=["a", "b"], quiz=True, correct=5)
        assert _err(ac, "poll") is not None
    finally:
        a.stop()


def test_poll_old_shape_still_accepted(tmp_path):
    """旧形状兼容：poll_state_local 收到 {votes:...} 仍写 poll["votes"]。"""
    from client_core import LocalHistory
    hist = LocalHistory(str(tmp_path / "h_old"))
    key = "public"
    hist.add(key, {"t": "poll", "seq": 5, "channel": "public", "uid": 1,
                   "poll": {"question": "旧", "options": ["a", "b"],
                            "votes": {}, "end": time.time() + 3600}})
    assert hist.poll_state_local(key, 5, {"votes": {"2": 0}})
    m = next(x for x in hist.load(key) if x.get("seq") == 5)
    assert m["poll"]["votes"] == {"2": 0}
    # 新形状落 poll["state"]
    assert hist.poll_state_local(key, 5, {"counts": [1, 0], "total": 1,
                                          "mine": [0], "end": time.time() + 3600})
    m2 = next(x for x in hist.load(key) if x.get("seq") == 5)
    assert m2["poll"]["state"]["counts"] == [1, 0]
    assert m2["poll"]["state"]["mine"] == [0]
    hist.close()


def test_poll_snapshot_keeps_new_fields(tmp_path):
    """快照保留 anonymous/multi/quiz/correct；votes 还原为 int 键 + list 值。"""
    store_dir = tmp_path / "r70_poll"
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"))
    h1 = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"), store_dir=str(store_dir))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h1, port, stop, False), daemon=True).start()
    time.sleep(0.1)
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    bob_uid = b.uid
    seq = None
    try:
        assert _online(ac) and _online(bc)
        assert a.send_poll(channel="public", question="快照测验",
                           options=["对", "错"], anonymous=True, multi=True,
                           quiz=True, correct=0)
        seq = ac.wait("poll", pred=lambda e: e.get("channel") == "public")["seq"]
        assert b.send_poll_vote(seq, 0)
        bc.wait("poll_state", pred=lambda e: e.get("seq") == seq)
        h1._persist_flush()
    finally:
        a.stop(); b.stop()
        stop.set()
        time.sleep(0.2)

    h2 = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"), store_dir=str(store_dir))
    p = h2._polls[seq]
    assert p["anonymous"] is True and p["multi"] is True and p["quiz"] is True
    assert p["correct"] == 0
    assert p["votes"].get(bob_uid) == [0]            # int 键 + list 值


# ---------- R70E 消息伪装 ----------
def test_disguise_transit_and_persist(hub, tmp_path):
    """disguise 透传且落盘；未知风格被拒；不带 disguise 照常发送。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_chat("假装是代码", disguise="code")
        ev = bc.wait("chat", pred=lambda e: e.get("text") == "假装是代码")
        assert ev and ev.get("disguise") == "code"
        m = next(x for x in b.history("public") if x.get("seq") == ev["seq"])
        assert m.get("disguise") == "code"          # 本地历史原样落盘
        assert b.send_chat("非法风格", disguise="nope")
        assert _err(bc, "disguise") is not None     # 白名单外被拒
        assert b.send_chat("无伪装")                 # 不带 disguise 正常
        assert bc.wait("chat", pred=lambda e: e.get("text") == "无伪装") is not None
    finally:
        a.stop(); b.stop()


def test_disguise_row_whitelist_and_headers():
    """_Row 只接受白名单风格；三风格表头文案非空，未知回落普通气泡。"""
    from widgets.msg_list import MsgList, _Row
    for style in CFG.disguise_styles:
        r = _Row({"t": "chat", "seq": 1, "uid": 1, "nick": "a",
                  "ts": 1.0, "text": "正文", "disguise": style})
        assert r.disguise == style
        assert MsgList._disguise_header(style) != ""
    bad = _Row({"t": "chat", "seq": 2, "uid": 1, "nick": "a",
                "ts": 1.0, "text": "正文", "disguise": "nope"})
    assert bad.disguise == ""                       # 未识别 → 普通气泡
    assert _Row({"t": "chat", "seq": 3, "uid": 1, "nick": "a",
                 "ts": 1.0, "text": "正文"}).disguise == ""


# ---------- R70F 敏感词打码 ----------
def test_guard_mask_segs_namespace():
    """命中 PLAIN 段 → SPOILER 遮盖段；run 索引用 1000+ 命名空间，不丢字符。"""
    import re as _re
    from widgets.msg_list import MsgList
    stub = object.__new__(MsgList)                 # 不建 Tk，仅测纯函数
    stub._guard_on = True
    stub._guard_words = ("密码", "secret")
    stub._guard_rx = _re.compile("(" + "|".join(
        _re.escape(w) for w in stub._guard_words) + ")", _re.IGNORECASE)
    segs = [("我的密码是secret吗", runs.PLAIN, None)]
    out = MsgList._guard_mask_segs(stub, segs)
    sp = [s for s in out if s[1] == rich.SPOILER]
    assert [s[0] for s in sp] == ["密码", "secret"]       # 中文命中 + 大小写不敏感
    assert all(int(s[2]) >= 1000 for s in sp)             # 1000+ 命名空间，避开富文本剧透
    assert "".join(s[0] for s in out) == "我的密码是secret吗"
    assert MsgList._guard_mask_segs(
        stub, segs + [("链接", runs.LINK, "u")])[-1][1] == runs.LINK   # 非 PLAIN 段不动
    stub._guard_on = False
    assert MsgList._guard_mask_segs(stub, segs) == segs    # 关闭态原样返回


def test_guard_hours_window(monkeypatch):
    """时段留空=全天；区间命中/不命中/跨天分支正确。"""
    import client as client_mod
    from client import ChatWindow
    c = object.__new__(ChatWindow)                 # 不建 Tk，仅测时段判定
    c._guard_on = True
    monkeypatch.setattr(client_mod.time, "localtime",
                        lambda *a: type("T", (), {"tm_hour": 10, "tm_min": 30})())
    c._guard_hours = ""
    assert c._guard_enabled_now() is True
    c._guard_hours = "9-18"
    assert c._guard_enabled_now() is True
    c._guard_hours = "9:30-12,14-18"
    assert c._guard_enabled_now() is True
    c._guard_hours = "20-22"
    assert c._guard_enabled_now() is False
    c._guard_hours = "22-6"                        # 跨天：白天不在段内
    assert c._guard_enabled_now() is False
    monkeypatch.setattr(client_mod.time, "localtime",
                        lambda *a: type("T", (), {"tm_hour": 3, "tm_min": 0})())
    assert c._guard_enabled_now() is True          # 凌晨落在跨天段内
    c._guard_on = False
    assert c._guard_enabled_now() is False


# ---------- R70G 忙碌自动回复 ----------
def test_auto_flag_transit_and_persist(hub, tmp_path):
    """header.auto → 事件透传 auto 标记，并随消息落盘（防环路依据）。"""
    _, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_chat("自动回复内容", channel="private", to=b.uid, auto=True)
        ev = bc.wait("chat", pred=lambda e: e.get("text") == "自动回复内容")
        assert ev is not None and ev.get("auto") is True
        hist = b.history("private", a.uid)
        assert any(h.get("text") == "自动回复内容" and h.get("auto")
                   for h in hist), "auto 标记未随本地历史落盘"
    finally:
        a.stop(); b.stop()


def test_auto_reply_gating():
    """门控：老板键关/群聊/本人/auto 标记/冷却内 均不回复。"""
    from client import ChatWindow
    sent = []
    c = object.__new__(ChatWindow)                 # 不建 Tk，仅测门控逻辑
    c._auto_reply_on = True
    c._auto_reply_text = "我在忙"
    c._auto_reply_cd = 600.0
    c._auto_reply_at = {}
    c._boss_active = True
    c._append_sys = lambda *a, **k: None

    class _Core:
        uid = 1
        def send_chat(self, *a, **k):
            sent.append(k)
            return True
    c.core = _Core()
    c._maybe_auto_reply({"channel": "private", "uid": 2, "text": "在吗"})
    assert len(sent) == 1 and sent[0].get("auto") is True and sent[0].get("to") == 2
    c._maybe_auto_reply({"channel": "private", "uid": 2, "text": "还在吗"})   # 冷却内
    assert len(sent) == 1
    c._maybe_auto_reply({"channel": "private", "uid": 3, "text": "x",
                         "auto": True})              # 防环路：带 auto 不再触发
    assert len(sent) == 1
    c._maybe_auto_reply({"channel": "group", "uid": 4, "to": 9, "text": "x"})
    c._maybe_auto_reply({"channel": "public", "uid": 4, "text": "x"})
    assert len(sent) == 1                          # 群/公共频道不回复
    c._maybe_auto_reply({"channel": "private", "uid": 1, "text": "x"})       # 本人消息
    assert len(sent) == 1
    c._boss_active = False                         # 老板键关闭
    c._maybe_auto_reply({"channel": "private", "uid": 5, "text": "x"})
    assert len(sent) == 1


# ---------- R70H 摸鱼排行榜（opt-in 默认关闭） ----------
def test_fish_board_disabled_ignores_and_empty(hub, tmp_path):
    """默认 opt-in 关闭：上报被静默忽略；拉取回空榜（不泄露任何数据）。"""
    h, port, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    try:
        assert _online(ac)
        assert a.send_fish_score("gomoku", 5)
        assert a.request_fish_board("gomoku")
        ev = ac.wait("fish_board", pred=lambda e: e.get("game") == "gomoku")
        assert ev is not None and ev["entries"] == []
        with h.lock:
            assert h._fish == {}                   # 关闭态不落任何积分
    finally:
        a.stop()


def test_fish_board_accumulate_cap_order_and_snapshot(tmp_path):
    """开启后：累加、单次夹取上限、降序（同分 uid 升序）、仅昵称+分数、快照往返。"""
    from protocol import MsgType
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  fish_board_enabled=True, fish_board_score_max=100,
                  fish_board_top=2)
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False), daemon=True).start()
    time.sleep(0.1)
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        assert a.send_fish_score("gomoku", 3)
        assert bc.wait("fish_board", pred=lambda e: e.get("game") == "gomoku") is not None
        assert a.send_fish_score("gomoku", 4)      # 累加 → 7
        assert b.send_fish_score("gomoku", 999)    # 夹取上限 → 100
        ev = bc.wait("fish_board", pred=lambda e: len(e.get("entries") or []) == 2)
        assert ev is not None
        assert [(e["nick"], e["score"]) for e in ev["entries"]] == \
            [("bob", 100), ("alice", 7)]
        assert all(set(e) == {"uid", "nick", "score"} for e in ev["entries"])
        assert a.send_fish_score("gomoku", 0)      # 非正分：静默忽略
        assert a.send_fish_score("", 5) is False   # 空游戏名：客户端本地拒绝
        assert a._send_frame({"t": MsgType.FISH_SCORE.value, "score": 5})
        assert _err(ac, "fish") is not None        # 缺游戏名 → error 帧
        with h.lock:
            assert h._fish["gomoku"] == {a.uid: 7, b.uid: 100}
        h2 = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit2"))
        h2._restore(h._snapshot_state())           # 快照 → 恢复
        assert h2._fish["gomoku"] == {a.uid: 7, b.uid: 100}
        assert [(e["nick"], e["score"])
                for e in h2._fish_board_payload("gomoku")["entries"]] == \
            [("bob", 100), ("alice", 7)]
    finally:
        a.stop(); b.stop()
        stop.set()
        time.sleep(0.2)


def test_report_fish_score_optin_gate():
    """客户端上报门控：默认关不上报；开启后按当前房间游戏名上报 1 分。"""
    from client import ChatWindow
    sent = []
    c = object.__new__(ChatWindow)                 # 不建 Tk，仅测门控
    c._fish_upload = False

    class _Core:
        game_room = {"game": "gomoku"}
        def send_fish_score(self, *args):
            sent.append(args)
            return True
    c.core = _Core()
    c._report_fish_score()
    assert sent == []                              # opt-in 关闭 → 不上报
    c._fish_upload = True
    c._report_fish_score()
    assert sent == [("gomoku", 1)]
    c.core.game_room = None                        # 不在房间 → 不上报
    c._report_fish_score()
    assert sent == [("gomoku", 1)]


@pytest.fixture()
def web_env(tmp_path):
    """R70H：TCP + 网页双通道 Hub（排行榜开启，供 /api/fish_board 只读验证）。"""
    from web import serve as serve_web
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"), fish_board_enabled=True)
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    tp, wp = _free_port(), _free_port()
    sc, sw = threading.Event(), threading.Event()
    threading.Thread(target=serve_tcp, args=(h, tp, sc, False), daemon=True).start()
    threading.Thread(target=serve_web, args=(h, wp, sw, False), daemon=True).start()
    time.sleep(0.2)
    yield h, tp, wp
    sw.set(); sc.set()
    time.sleep(0.2)


def _web_login(port: int, nick: str) -> str:
    import http.client as hc
    conn = hc.HTTPConnection("127.0.0.1", port, timeout=8)
    conn.request("POST", "/api/login", json.dumps({"nick": nick}).encode(),
                 {"Content-Type": "application/json"})
    r = conn.getresponse(); r.read(); sc = r.getheader("Set-Cookie") or ""
    conn.close()
    return sc.split(";")[0]


def _web_get(port: int, path: str, cookie: str = ""):
    import http.client as hc
    conn = hc.HTTPConnection("127.0.0.1", port, timeout=8)
    conn.request("GET", path, headers={"Cookie": cookie} if cookie else {})
    r = conn.getresponse(); raw = r.read(); conn.close()
    return r.status, json.loads(raw.decode() or "{}")


def test_fish_board_web_readonly(web_env, tmp_path):
    """网页端只读：登录后回只读载荷；未登录 401（不上报积分，仅展示）。"""
    _h, tcp_port, web_port = web_env
    a, ac = _spawn(tcp_port, "alice", tmp_path)
    try:
        assert _online(ac)
        assert a.send_fish_score("gomoku", 4)
        assert ac.wait("fish_board",
                       pred=lambda e: e.get("game") == "gomoku") is not None
        cookie = _web_login(web_port, "webuser")
        st, d = _web_get(web_port, "/api/fish_board?game=gomoku", cookie)
        assert st == 200 and d["ok"] and d["game"] == "gomoku"
        assert [(e["nick"], e["score"]) for e in d["entries"]] == [("alice", 4)]
        st2, d2 = _web_get(web_port, "/api/fish_board?game=gomoku")   # 未登录
        assert st2 == 401 and d2["ok"] is False
    finally:
        a.stop()


# ---------- R70 GUI 冒烟（剧透遮盖/揭示 + 编辑历史点击） ----------
def test_gui_smoke_r70(hub, tmp_path):
    import tkinter as tk
    try:
        r0 = tk.Tk()
        r0.destroy()
    except tk.TclError as exc:
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    from widgets.msg_list import MsgList
    root = tk.Tk()
    try:
        edits = []
        ml = MsgList(root, ("Microsoft YaHei UI", 9),
                     on_edit_history=lambda row: edits.append(row))
        ml.configure(width=420, height=420)
        ml.pack(fill="both", expand=True)
        root.update_idletasks()
        root.update()
        now = time.time()
        ml.append({"t": "chat", "seq": 1, "uid": 1, "nick": "alice",
                   "channel": "public", "ts": now, "text": "答案 ||42|| 是",
                   "rich": [list(seg) for seg in rich.parse("答案 ||42|| 是")]})
        root.update_idletasks()
        root.update()
        assert ml.count == 1
        row0 = ml._rows[0]
        assert any(seg[1] == rich.SPOILER and "42" in seg[0] for seg in row0.rich)
        ml._toggle_spoiler(row0, 0)                  # 揭示
        root.update()
        assert (id(row0), 0) in ml._spoiler_open
        ml._toggle_spoiler(row0, 0)                  # 再遮盖
        assert (id(row0), 0) not in ml._spoiler_open
        # 编辑历史：行内 ✎已编辑 热区可点并回调
        ml.append({"t": "chat", "seq": 2, "uid": 1, "nick": "alice",
                   "channel": "public", "ts": now, "text": "改过的消息",
                   "edited": True, "edits": [{"ts": now, "text": "原消息"}]})
        ml.update_text(2, "改过的消息", edits=[{"ts": now, "text": "原消息"}])
        root.update_idletasks()
        root.update()
        assert ml.count == 2
        hits = [it for it in ml.find_all()
                if any(str(t).startswith("r70ed") for t in ml.gettags(it))]
        assert hits, "编辑历史热区未创建"
        x0, y0, x1, y1 = ml.bbox(hits[0])
        ml.event_generate("<Button-1>", x=(x0 + x1) // 2, y=(y0 + y1) // 2)
        ml.event_generate("<ButtonRelease-1>", x=(x0 + x1) // 2, y=(y0 + y1) // 2)
        root.update()
        assert edits and edits[0].raw.get("edits")
        # R70E 三风格伪装：表头段 + 正文遮盖段齐备，渲染不异常
        for si, style in enumerate(CFG.disguise_styles):
            ml.append({"t": "chat", "seq": 10 + si, "uid": 1, "nick": "alice",
                       "channel": "public", "ts": now, "text": "假装内容 " * 6,
                       "disguise": style})
        root.update_idletasks()
        root.update()
        assert ml.count == 2 + len(CFG.disguise_styles)
        drow = ml._rows[-1]
        dsegs = ml._bubble_segs(drow, False, False)
        assert any(s[1] == runs.DISGUISE for s in dsegs), "伪装表头段缺失"
        assert any(s[1] == rich.SPOILER for s in dsegs), "伪装正文遮盖段缺失"
        # R70F 敏感词打码：开启 → 命中词成遮盖段（1000+ 命名空间可点击揭示）；关闭 → 还原
        ml.set_guard(("机密", "secret"), True)
        ml.append({"t": "chat", "seq": 30, "uid": 1, "nick": "alice",
                   "channel": "public", "ts": now, "text": "这是机密文件 secret"})
        root.update_idletasks()
        root.update()
        grow = ml._rows[-1]
        gsp = [s for s in ml._bubble_segs(grow, False, False)
               if s[1] == rich.SPOILER]
        assert [s[0] for s in gsp] == ["机密", "secret"], "打码遮盖段缺失"
        assert all(int(s[2]) >= 1000 for s in gsp)
        ml._toggle_spoiler(grow, int(gsp[0][2]))     # 点击揭示该遮盖段
        assert (id(grow), int(gsp[0][2])) in ml._spoiler_open
        ml.set_guard((), False)                      # 关闭 → 遮盖段消失
        root.update()
        assert not any(s[1] == rich.SPOILER
                       for s in ml._bubble_segs(grow, False, False))
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass