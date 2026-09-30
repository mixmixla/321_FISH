# -*- coding: utf-8 -*-
"""R27 表情回应扩展回归：hover 快速回应条 / 药丸可点 / 弹入动画。

- 网页端：/api/reaction 端点（复用 REACTION 协议）加/摘回应、越权拦截；
- 桌面端 msg_list：_recent_emoji 弹入动画判定、_row_reactable 可回应性、
  hover 悬浮条绘制与隐藏、药丸点击回调（r27r 标签）绑定。
"""
import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, serve as serve_tcp
from web import serve as serve_web
from widgets.msg_list import MsgList

FONT = ("Microsoft YaHei UI", 9)


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

    def send(self, text, channel="public", to=None):
        body = {"token": self.token, "channel": channel, "text": text}
        if to is not None:
            body["to"] = to
        st, d = self._post("/api/send", body)
        assert st == 200 and d["ok"], d

    def react(self, seq, emoji, on=True):
        return self._post("/api/reaction", {"token": self.token, "seq": seq,
                                            "emoji": emoji, "on": on})

    def history(self, channel="public", to=None):
        q = f"token={self.token}&channel={channel}"
        if to is not None:
            q += f"&to={to}"
        st, d = self._get("/api/history?" + q)
        assert st == 200 and d["ok"], d
        return d["msgs"]


# ---------- 网页端 /api/reaction ----------
def test_web_reaction_add_and_remove(hub):
    h, port, wport, _ = hub
    u1 = _Web(wport, "红宝")
    u2 = _Web(wport, "蓝宝")

    u1.send("求赞")
    seq = next(m["seq"] for m in u1.history() if m.get("text") == "求赞")

    # u2 加 👍 → u1 视角历史里该消息带 reactions
    st, d = u2.react(seq, "👍")
    assert st == 200 and d["ok"], d
    m = next(m for m in u1.history() if m["seq"] == seq)
    assert str(u2.uid) in m["reactions"]["👍"]

    # u2 再点一次（摘）→ reactions 清空
    st, d = u2.react(seq, "👍", on=False)
    assert st == 200 and d["ok"], d
    m2 = next(m for m in u1.history() if m["seq"] == seq)
    assert not m2.get("reactions") or "👍" not in m2["reactions"]


def test_web_reaction_private_membership(hub):
    h, port, wport, _ = hub
    u1 = _Web(wport, "主")
    u2 = _Web(wport, "客")
    u3 = _Web(wport, "外人")

    u1.send("悄悄话", channel="private", to=u2.uid)
    seq = next(m["seq"] for m in u1.history(channel="private", to=u2.uid)
               if m.get("text") == "悄悄话")

    # 会话双方可回应
    st, d = u1.react(seq, "❤️")
    assert st == 200 and d["ok"], d
    m = next(m for m in u1.history(channel="private", to=u2.uid) if m["seq"] == seq)
    assert str(u1.uid) in m["reactions"]["❤️"]

    # 局外人回应 → HTTP 仍 200（错误走 SSE error 帧），reactions 不被写入
    st, d = u3.react(seq, "👍")
    assert st == 200 and d["ok"], d
    m2 = next(m for m in u1.history(channel="private", to=u2.uid) if m["seq"] == seq)
    assert "👍" not in m2.get("reactions", {})


def test_web_reaction_unauth(hub):
    h, port, wport, _ = hub
    import http.client
    import json
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn.request("POST", "/api/reaction", json.dumps({"seq": 1, "emoji": "👍"}).encode(),
                 {"Content-Type": "application/json"})
    r = conn.getresponse()
    data = json.loads(r.read().decode() or "{}")
    conn.close()
    assert r.status == 401 and not data["ok"]


# ---------- 桌面端 msg_list：弹入动画 / 可回应性 / hover 悬浮条 ----------
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
    ml = MsgList(root, FONT, on_react=lambda seq, emoji: None)
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


def test_recent_emoji_animation(ml):
    """弹入动画判定：2s 内最新变化的表情命中，陈旧/空桶不触发。"""
    now = time.time()
    assert MsgList._recent_emoji(None) is None
    assert MsgList._recent_emoji({}) is None
    # ❤ 最新（1s 前）→ 命中；👍 更早
    r = {"👍": {"1": now - 5}, "❤": {"2": now - 1}}
    assert MsgList._recent_emoji(r) == "❤"
    # 全部超过 2s → 不触发动画
    r2 = {"👍": {"1": now - 9}, "❤": {"2": now - 3}}
    assert MsgList._recent_emoji(r2) is None


def test_row_reactable_rules(ml):
    """可回应性：系统行/已撤回/无 seq 不可回应；普通消息可。"""
    ml.append({"uid": 1, "nick": "甲", "channel": "public",
               "ts": time.time(), "text": "系统", "tag": "sys"}, is_system=True)
    ml.append(_msg("普通", seq=101))
    ml.append(_msg("已撤回", seq=102, deleted=True))
    ml.append(_msg("无seq", seq=103))
    del ml._rows[3].raw["seq"]
    assert not ml._row_reactable(0)          # sys
    assert ml._row_reactable(1)              # 普通
    assert not ml._row_reactable(2)          # 撤回
    assert not ml._row_reactable(3)          # 无 seq
    assert not ml._row_reactable(99)         # 越界


def test_hover_shows_and_hides_quick_bar(ml):
    """hover 行渲染悬浮快速回应条（r27q 标签），清除 hover 即消失。"""
    ml.append(_msg("求赞"))
    ml._render()
    base_items = len(ml._item_ids)

    ml._set_hover(0)
    assert ml._hover_row == 0
    tags = {t for i in ml._item_ids for t in ml.gettags(i)}
    assert any(t.startswith("r27q") for t in tags)     # 悬浮条表情药丸已画
    assert len(ml._item_ids) > base_items

    ml._set_hover(None)
    assert ml._hover_row is None
    tags2 = {t for i in ml._item_ids for t in ml.gettags(i)}
    assert not any(t.startswith("r27q") for t in tags2)


def test_hover_skips_unreactable_row(ml):
    """hover 到系统行/撤回行 → 不显示悬浮条（_set_hover 自行校验可回应性）。"""
    ml.append(_msg("无seq", seq=201))          # 删除 seq → 不可回应
    del ml._rows[0].raw["seq"]
    ml.append(_msg("普通", seq=202))
    ml._set_hover(0)
    assert ml._hover_row is None           # 不可回应行不驻留
    ml._set_hover(1)
    assert ml._hover_row == 1


def test_reaction_pill_clickable(ml):
    """回应药丸带 r27r 标签 + 点击回调绑定（on_react 存在时）。"""
    calls = []
    ml._on_react = lambda seq, emoji: calls.append((seq, emoji))
    ml.set_me_uid(2)
    reactions = {"👍": {"1": 100.0, "2": 101.0}}
    ml.append(_msg("带回应", reactions=reactions))
    ml._render()
    tags = {t for i in ml._item_ids for t in ml.gettags(i)}
    assert any(t.startswith("r27r") for t in tags)
    # 点击绑定已注册：tag_bind 两参调用返回绑定脚本（非空）
    bound = False
    for i in ml._item_ids:
        for t in ml.gettags(i):
            if t.startswith("r27r") and ml.tag_bind(t, "<Button-1>"):
                bound = True
    assert bound
    # 无 on_react 时（on_react 为 None）药丸有标签但无点击绑定
    ml2 = MsgList(ml.winfo_toplevel(), FONT, on_react=None)
    ml2.configure(width=400, height=300)
    ml2.set_me_uid(2)
    ml2.append(_msg("带回应2", seq=301, reactions={"👍": {"1": 100.0}}))
    ml2._render()
    tags2 = {t for i in ml2._item_ids for t in ml2.gettags(i)}
    r27 = [t for t in tags2 if t.startswith("r27r")]
    assert r27 and not any(ml2.tag_bind(t, "<Button-1>") for t in r27)
    ml2.destroy()
