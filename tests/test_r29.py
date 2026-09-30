# -*- coding: utf-8 -*-
"""R29 四件套回归：定时发送 / 草稿同步 / @提及增强 / 表情回应扩展。

- R29A/R51 定时发送：_schedule_send 改走服务器权威（sched_set 交给服务器队列，
  本地不再落盘/泵出）；_pump_scheduled 仅剪枝展示；_on_sched_sync 回帧覆盖。
- R29B 草稿同步：服务器按 (uid,key) 内存存、welcome/登录响应带回、空文清除、
  非法频道忽略、跨用户隔离、TTL 清扫；网页端 /api/draft。
- R29C @提及：msg_list 内 @昵称 run 带 r29m 可点绑定；client _ac_candidates
  群成员优先+去重+排除自己；_on_mention_click 跳该成员私聊。
- R29D 表情扩展：REACT_GROUPS 多分类常量；悬浮条"＋"(r29p) 回调；
  _touch_recent_react 去重前置/上限 5/落盘/刷悬浮条；_on_quick_more 弹选择器。
"""
import os
import socket
import threading
import time
from dataclasses import replace

import pytest

from client import ChatWindow, REACT_GROUPS, REACT_RECENT_MAX
from config import CFG
from prefs import Prefs
from server import Hub, serve as serve_tcp
from web import serve as serve_web
from widgets.msg_list import MsgList
from theme import dialog_pal, get_skin

FONT = ("Microsoft YaHei UI", 9)

_palette = dialog_pal(get_skin("apple"))     # R57 对话框配色：供「更多表情」stub 使用


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


class _Web:
    """轻量 web HTTP 客户端：登录拿 token + 通用 POST/GET。"""
    __test__ = False

    def __init__(self, port, nick):
        self.port = port
        self.token = None
        self.uid = None
        self.last_login = {}
        self.login(nick)

    def _post(self, path, body):
        import http.client
        import json
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", path, json.dumps(body).encode(),
                     {"Content-Type": "application/json"})
        r = conn.getresponse()
        data = json.loads(r.read().decode() or "{}")
        conn.close()
        return r.status, data

    def _get(self, path):
        import http.client
        import json
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        r = conn.getresponse()
        data = json.loads(r.read().decode() or "{}")
        conn.close()
        return r.status, data

    def login(self, nick):
        st, d = self._post("/api/login", {"nick": nick})
        assert st == 200 and d["ok"], d
        self.token = d["token"]
        self.uid = d["uid"]
        self.last_login = d

    def post_draft(self, body):
        body = dict(body)
        body["token"] = self.token
        return self._post("/api/draft", body)


def _relogin(hub, wport, nick, token):
    """模拟换端：先把旧端下线（同名不可并发在线），再同昵称重新登录。"""
    h, _port, _wport, _ = hub
    sess = h.session_by_token(token)
    if sess is not None:
        h.unregister(sess, "test")
    return _Web(wport, nick)


# ================= R29B 草稿同步（服务器/网页端） =================

def test_web_draft_set_and_login_carries(hub):
    """设草稿 → 下线后同昵称换端登录 → 登录响应 drafts 带回。"""
    h, port, wport, _ = hub
    u1 = _Web(wport, "红宝")
    st, d = u1.post_draft({"channel": "public", "text": "草稿A"})
    assert st == 200 and d["ok"], d
    u1b = _relogin(hub, wport, "红宝", u1.token)        # 换端重登
    drafts = {x["key"]: x["text"] for x in u1b.last_login["drafts"]}
    assert drafts.get("public") == "草稿A"
    assert u1b.uid == u1.uid                             # 昵称→uid 持久映射


def test_web_draft_empty_clears(hub):
    h, port, wport, _ = hub
    u1 = _Web(wport, "红宝")
    u1.post_draft({"channel": "public", "text": "草稿B"})
    u1.post_draft({"channel": "public", "text": ""})
    u2 = _relogin(hub, wport, "红宝", u1.token)
    drafts = {x["key"]: x["text"] for x in u2.last_login["drafts"]}
    assert "public" not in drafts


def test_web_draft_scoped_per_user(hub):
    h, port, wport, _ = hub
    u1 = _Web(wport, "甲")
    u1.post_draft({"channel": "public", "text": "甲草稿"})
    u2 = _Web(wport, "乙")
    assert not u2.last_login["drafts"]                   # 乙看不到甲的草稿
    u1b = _relogin(hub, wport, "甲", u1.token)
    drafts = {x["key"]: x["text"] for x in u1b.last_login["drafts"]}
    assert drafts.get("public") == "甲草稿"              # 甲的草稿仍在


def test_web_draft_private_key(hub):
    h, port, wport, _ = hub
    u1 = _Web(wport, "甲")
    u2 = _Web(wport, "乙")
    u1.post_draft({"channel": "private", "to": u2.uid, "text": "私草稿"})
    u1b = _relogin(hub, wport, "甲", u1.token)
    drafts = {x["key"]: x["text"] for x in u1b.last_login["drafts"]}
    key = f"private:{min(u1.uid, u2.uid)}:{max(u1.uid, u2.uid)}"
    assert drafts.get(key) == "私草稿"


def test_web_draft_invalid_channel_ignored(hub):
    h, port, wport, _ = hub
    u1 = _Web(wport, "甲")
    st, d = u1.post_draft({"channel": "weird", "text": "x"})
    assert st == 200 and d["ok"]
    u1b = _relogin(hub, wport, "甲", u1.token)
    assert not u1b.last_login["drafts"]


def test_draft_ttl_cleanup(hub):
    """草稿超 DRAFT_TTL（24h）→ _drafts_for 清扫。"""
    h, port, wport, _ = hub
    u1 = _Web(wport, "红宝")
    u1.post_draft({"channel": "public", "text": "旧草稿"})
    with h.lock:
        h._drafts[(u1.uid, "public")]["ts"] = time.time() - 100000
    assert h._drafts_for(u1.uid) == []


# ================= R51 定时发送（服务器权威，替代原 R29A 本地泵出） =================

class _CoreSend:
    __test__ = False

    def __init__(self):
        self.sent = []
        self.sched = []

    def send_chat(self, text, channel="public", to=None, burn=False):
        self.sent.append((text, channel, to, burn))

    def sched_set(self, text, channel="public", to=None, fire_at=0.0):
        self.sched.append((text, channel, to, fire_at))
        return True

    def sched_cancel(self, rid):
        self.sched.append(("cancel", rid))
        return True


def _sched_stub(tmp_path, core):
    s = type("S", (), {})()
    s._prefs = Prefs(str(tmp_path / "p.json"))
    s._scheduled = []
    s._sched_dlg = None
    s._sched_reload = None
    s.view = ("public", None)
    s._burn_mode = False
    s._append_sys = lambda *a: None
    s.core = core
    return s


def test_schedule_send_pushes_to_server(tmp_path):
    """R51：_schedule_send 把定时任务交给服务器（sched_set），本地不再落盘/泵出。"""
    core = _CoreSend()
    s = _sched_stub(tmp_path, core)
    sc = ChatWindow._schedule_send.__get__(s)
    sc("你好", "public", None, 1)
    assert len(core.sched) == 1
    text, ch, to, fire_at = core.sched[0]
    assert text == "你好" and ch == "public" and to is None
    assert fire_at > time.time()
    assert s._scheduled == []                      # 本地不保存（服务器权威）
    assert core.sent == []                         # 不到点不发


def test_sched_sync_replaces_list(tmp_path):
    """R51：SCHED_LIST 回帧覆盖本地展示队列，已到点项剪掉。"""
    core = _CoreSend()
    s = _sched_stub(tmp_path, core)
    now = time.time()
    ev = {"items": [
        {"rid": "a", "channel": "public", "to": None, "text": "x",
         "fire_at": now + 100, "created": now},
        {"rid": "b", "channel": "public", "to": None, "text": "y",
         "fire_at": now - 5, "created": now},
    ]}
    ChatWindow._on_sched_sync.__get__(s)(ev)
    assert [r["rid"] for r in s._scheduled] == ["a"]


def test_pump_scheduled_prunes_display_only(tmp_path):
    """R51：_pump_scheduled 仅剪枝展示（到点由服务器发出），不再本地发送。"""
    core = _CoreSend()
    s = _sched_stub(tmp_path, core)
    now = time.time()
    s._scheduled = [
        {"rid": "a", "channel": "public", "to": None, "text": "x",
         "fire_at": now + 100, "created": now},
        {"rid": "b", "channel": "public", "to": None, "text": "y",
         "fire_at": now - 10, "created": now},
    ]
    ChatWindow._pump_scheduled.__get__(s)()
    assert [r["rid"] for r in s._scheduled] == ["a"]
    assert core.sent == []                         # 服务器托管，本地不泵出


# ================= R29C @提及增强（补全候选 + 点击跳转） =================

def _ac_stub(view=("group", 7)):
    core = type("C", (), {"uid": 1, "nick": "自己"})()
    core.group_members = {7: [{"nick": "小明", "uid": 5},
                              {"nick": "组长", "uid": 6},
                              {"nick": "自己", "uid": 1}]}
    core.roster = {5: {"uid": 5, "nick": "小明"},
                   9: {"uid": 9, "nick": "小刚"},
                   1: {"uid": 1, "nick": "自己"}}
    s = type("S", (), {"view": view, "core": core})()
    return s


def test_ac_candidates_group_priority_dedupe_exclude_self():
    s = _ac_stub()
    ac = ChatWindow._ac_candidates.__get__(s)
    assert ac("at", "小") == ["小明", "小刚"]    # 群成员优先 + 去重(小明) + 排除自己
    assert ac("at", "组") == ["组长"]           # 离线群成员也可 @
    assert ac("at", "X") == []                  # 无匹配
    s2 = _ac_stub(view=("public", None))
    ac2 = ChatWindow._ac_candidates.__get__(s2)
    assert ac2("at", "小") == ["小明", "小刚"]  # 公聊只看在线好友


def test_on_mention_click_switches_to_private():
    switches = []
    core = type("C", (), {})()
    core.group_members = {7: [{"nick": "小明", "uid": 5}]}
    s = type("S", (), {"view": ("group", 7), "core": core, "_prefs": {}})()
    s._switch_view = lambda ch, to: switches.append((ch, to))
    clk = ChatWindow._on_mention_click.__get__(s)
    clk("@小明")
    assert switches == [("private", 5)]
    clk("@不存在")                               # 未找到 → 不跳
    assert switches == [("private", 5)]
    s.view = ("public", None)
    clk("@小明")                                 # 非群会话 → 不跳
    assert switches == [("private", 5)]


# ================= R29D 表情回应扩展 =================

def test_react_groups_constant():
    """多分类表情集：5 类 × 16 个，每类非空字符串。"""
    assert len(REACT_GROUPS) == 5
    total = sum(len(em) for _n, em in REACT_GROUPS)
    assert total >= 40
    for name, em in REACT_GROUPS:
        assert name and len(em) == 16
        assert all(isinstance(x, str) and x for x in em)
    assert REACT_RECENT_MAX == 5


class _MLStub:
    __test__ = False

    def __init__(self):
        self.calls = []

    def set_quick_emojis(self, emojis):
        self.calls.append(list(emojis))


def test_touch_recent_react_dedupe_cap_persist(tmp_path):
    p = Prefs(str(tmp_path / "p.json"))
    ml = _MLStub()
    s = type("S", (), {"_prefs": p, "_recent_reacts": ["👍"], "msg_list": ml})()
    touch = ChatWindow._touch_recent_react.__get__(s)
    touch("❤️")
    assert s._recent_reacts == ["❤️", "👍"]
    touch("👍")                                    # 已在 → 前置去重
    assert s._recent_reacts == ["👍", "❤️"]
    for e in ("😀", "😂", "😮", "🔥"):              # 超上限 → 截断到 5
        touch(e)
    assert s._recent_reacts == ["🔥", "😮", "😂", "😀", "👍"]
    assert p.get("react_recent") == s._recent_reacts
    assert ml.calls[-1] == s._recent_reacts
    touch("")                                     # 空不入
    touch(None)
    assert len(s._recent_reacts) == 5


def test_react_records_recent_only_when_on(tmp_path):
    """加回应(on)记最近；摘回应(off)不记。"""
    p = Prefs(str(tmp_path / "p.json"))
    sent = []
    core = type("C", (), {"uid": 1})()
    core.send_reaction = lambda seq, emoji, on: sent.append((seq, emoji, on))

    class _ML:
        __test__ = False

        def __init__(self, raw):
            self._raw = raw
            self.quick_calls = []

        def get_row(self, i):
            return self._raw

        def set_quick_emojis(self, emojis):
            self.quick_calls.append(list(emojis))

    ml = _ML({"seq": 900, "reactions": {"👍": {"2": 1.0}}})
    s = type("S", (), {"_prefs": p, "_recent_reacts": [], "msg_list": ml,
                       "core": core})()
    s._touch_recent_react = ChatWindow._touch_recent_react.__get__(s)
    react = ChatWindow._react.__get__(s)
    react(0, "👍")                                  # 我(1)不在 → on=True → 记入
    assert s._recent_reacts == ["👍"]
    assert ml.quick_calls[-1] == ["👍"]
    ml._raw = {"seq": 901, "reactions": {"👍": {"1": 1.0}}}
    react(0, "👍")                                  # 我已回 → on=False → 不记新
    assert s._recent_reacts == ["👍"]


# ---------- msg_list 绘制层（GUI） ----------

@pytest.fixture(scope="module")
def root():
    try:
        r = __import__("tkinter").Tk()
    except Exception as exc:
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except Exception:
        pass


@pytest.fixture()
def ml(root):
    ml = MsgList(root, FONT, on_react=lambda seq, emoji: None,
                 on_mention=lambda nick: None,
                 on_quick_more=lambda seq: None)
    ml.configure(width=400, height=400)
    ml.pack(fill="both", expand=True)
    root.update_idletasks()
    root.update()
    yield ml
    ml.destroy()


def _msg(text="hi", seq=100, **kw):
    d = {"uid": 1, "nick": "甲", "channel": "public",
         "ts": time.time(), "seq": seq, "text": text}
    d.update(kw)
    return d


def test_quick_bar_plus_button_clickable(ml):
    """悬浮条含"＋"(r29p) 且绑定 Button-1（on_quick_more）。"""
    ml.append(_msg("求赞", seq=600))
    ml._set_hover(0)
    ml._render()
    tags = {t for i in ml._item_ids for t in ml.gettags(i)}
    plus = [t for t in tags if t.startswith("r29p")]
    assert plus
    assert ml.tag_bind(plus[0], "<Button-1>")
    ml._set_hover(None)


def test_mention_run_clickable(ml):
    """消息内 @昵称 run 带 r29m 标签且可点。"""
    calls = []
    ml._on_mention = lambda nick: calls.append(nick)
    ml.append(_msg("@小明 你好", seq=601))
    ml._render()
    tags = {t for i in ml._item_ids for t in ml.gettags(i)}
    m = [t for t in tags if t.startswith("r29m")]
    assert m
    assert ml.tag_bind(m[0], "<Button-1>")


def test_quick_emojis_limits(ml):
    ml.set_quick_emojis(["a", "b", "c", "d", "e", "f"])
    assert ml._quick_emojis == ["a", "b", "c", "d", "e"]
    ml.set_quick_emojis([])
    assert ml._quick_emojis == []
    ml.set_quick_emojis(None)
    assert ml._quick_emojis == []


def test_on_quick_more_opens_selector(root, ml):
    """悬浮条"＋"→ 打开「更多表情回应」多分类选择器。"""
    import tkinter as tk
    ml.append(_msg("可回应", seq=700))
    ml._render()
    stub = type("S", (), {"root": ml.winfo_toplevel(), "msg_list": ml,
                          "_recent_reacts": [], "_dp": _palette,
                          # 弹窗套壳钩子（实现侧 `_on_quick_more` 会调用；stub 空实现）
                          "_apply_apple_dialog": lambda *a, **k: None})()
    stub._react = lambda idx, em: None
    ChatWindow._on_quick_more.__get__(stub)(ml.get_row(0)["seq"])
    root.update()
    wins = [w for w in root.winfo_children()
            if isinstance(w, tk.Toplevel) and w.title() == "更多表情回应"]
    assert wins
    wins[0].destroy()
    root.update()
