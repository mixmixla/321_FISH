# -*- coding: utf-8 -*-
"""R30 扩大六件套回归：未读分隔线 / 免打扰时段 / 自定义表情包 / 回应详情 /
hashtag 点击搜索 / 日期跳转。

- R30A 未读分隔线：msg_list set_unread_seq → 边界行画「未读消息」条（占行高），
  滚到底自动撤线；dates()/jump_to_date() 按日定位首条。
- R30B 免打扰时段：prefs.in_dnd_range 纯函数（跨天/全天/坏数据）+ 偏好存取。
- R30C 自定义表情包：stickers 短码校验；Hub add/del/get（落盘+广播+审计）；
  welcome 带清单；网页端 /api/sticker 直出图片；client_core 缓存路径/补拉/落盘。
- R30D 回应详情：msg_list 药丸 hover 500ms → on_react_detail(seq,emoji,ev)，
  移出即 hide（ev=None）。
- R30E hashtag：runs.tag_entities 切出 HASHTAG；msg_list 渲染带 r30h 可点绑定。
"""
import http.client
import json
import os
import socket
import threading
import time
from dataclasses import replace

import pytest

from client import ChatWindow
from client_core import ClientCore
from config import CFG
from prefs import Prefs, in_dnd_range
from server import Hub, serve as serve_tcp
from stickers import (custom_tokens, is_custom_sticker_text,
                      is_valid_custom_code)
from web import serve as serve_web
from widgets import runs
from widgets.msg_list import MsgList
from theme import dialog_pal, get_skin

_palette = dialog_pal(get_skin("apple"))     # R57 对话框配色：供 react 详情 stub 使用

UNREAD_H = MsgList.UNREAD_H          # R30A 分隔条高度（类常量）

FONT = ("Microsoft YaHei UI", 9)
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c626001000000ffff030000060005"
    "57bfabd40000000049454e44ae426082")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"))
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


class _Cli:
    """加密握手测试客户端（保留 body，供贴纸图片断言）。"""
    __test__ = False

    def __init__(self, port, nick):
        from crypto import client_handshake
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.chan = client_handshake(self.sock)
        self.nick = nick
        self.uid = None
        self.events = []                       # (header, body)
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


# ================= R30B 免打扰时段（纯函数 + 偏好） =================

def test_in_dnd_range_basic_and_bad_data():
    assert not in_dnd_range(None)                     # 未配置
    assert not in_dnd_range({})                       # 空
    assert not in_dnd_range({"on": False, "start": "01:00", "end": "02:00"})
    ts = time.mktime(time.strptime("2026-09-09 01:30:00", "%Y-%m-%d %H:%M:%S"))
    assert in_dnd_range({"on": True, "start": "01:00", "end": "02:00"}, now=ts)
    assert not in_dnd_range({"on": True, "start": "02:00", "end": "03:00"}, now=ts)
    assert not in_dnd_range({"on": True, "start": "bad", "end": "03:00"}, now=ts)
    assert not in_dnd_range({"on": True, "start": "25:00", "end": "03:00"}, now=ts)


def test_in_dnd_range_cross_midnight_and_all_day():
    night = time.mktime(time.strptime("2026-09-09 23:30:00", "%Y-%m-%d %H:%M:%S"))
    early = time.mktime(time.strptime("2026-09-09 07:59:00", "%Y-%m-%d %H:%M:%S"))
    noon = time.mktime(time.strptime("2026-09-09 12:00:00", "%Y-%m-%d %H:%M:%S"))
    rng = {"on": True, "start": "23:00", "end": "08:00"}   # 跨天
    assert in_dnd_range(rng, now=night)
    assert in_dnd_range(rng, now=early)
    assert not in_dnd_range(rng, now=noon)
    assert in_dnd_range({"on": True, "start": "08:00", "end": "08:00"}, now=noon)  # 全天


def test_prefs_dnd_range_roundtrip(tmp_path):
    p = Prefs(str(tmp_path / "p.json"))
    assert p.dnd_range() == {"on": False, "start": "23:00", "end": "08:00"}
    p.set_dnd_range(True, "22:30", "07:00")
    rng = p.dnd_range()
    assert rng["on"] and rng["start"] == "22:30" and rng["end"] == "07:00"
    p2 = Prefs(str(tmp_path / "p.json"))          # 重启恢复
    assert p2.dnd_range()["start"] == "22:30"


# ================= R30C 自定义表情包（短码 / Hub / 网页端 / core） =================

def test_custom_sticker_code_validation():
    assert is_valid_custom_code("cat_1")
    assert is_valid_custom_code("A" * 24)
    assert not is_valid_custom_code("")
    assert not is_valid_custom_code("A" * 25)
    assert not is_valid_custom_code("坏!码")
    assert not is_valid_custom_code(None)
    assert custom_tokens("看 [:a:] 和 [:b_c:]") == ["a", "b_c"]
    assert custom_tokens("无") == []
    assert is_custom_sticker_text("[:cat:]") == "cat"
    assert is_custom_sticker_text("  [:cat:]  ") == "cat"
    assert is_custom_sticker_text("前 [:cat:]") is None
    assert is_custom_sticker_text(":cat:") is None       # 内置单冒号不算


def test_hub_sticker_add_get_del(hub, tmp_path):
    """add 落盘+广播 → get 回图片 → del 清除+广播；非法短码被拒。"""
    h, port, _wport, _ = hub
    a = _Cli(port, "贴纸君")
    w = a.hello()
    assert w                                     # 登录就绪（welcome 无贴纸也应成功）
    a.send({"t": "sticker_custom_add", "code": "c1", "label": "猫猫",
            "ext": "png"}, PNG_1PX)
    sl, _ = a.wait("sticker_list")
    assert sl and any(s["code"] == "c1" for s in sl["custom_stickers"])
    assert h.custom_stickers["c1"]["label"] == "猫猫"
    assert (tmp_path / "web" / "stickers" / "c1.png").exists()

    a.send({"t": "sticker_custom_get", "code": "c1"})
    sd, body = a.wait("sticker_custom_data")
    assert sd and sd["ext"] == "png" and body[:4] == b"\x89PNG"

    a.send({"t": "sticker_custom_del", "code": "c1"})
    sl2, _ = a.wait("sticker_list")
    assert sl2 and all(s["code"] != "c1" for s in sl2["custom_stickers"])
    assert "c1" not in h.custom_stickers
    a.close()

    # 非法短码 → error 帧，不落盘
    b = _Cli(port, "恶意")
    b.hello()
    b.send({"t": "sticker_custom_add", "code": "坏!", "ext": "png"}, PNG_1PX)
    err, _ = b.wait("error")
    assert err and err.get("code") == "sticker"
    b.close()


def test_web_sticker_route_and_login_list(hub):
    h, _port, wport, _ = hub
    h.custom_stickers["w1"] = {"code": "w1", "label": "网页", "ext": "png"}
    with open(os.path.join(h.sticker_dir, "w1.png"), "wb") as f:
        f.write(PNG_1PX)
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn.request("GET", "/api/sticker/w1")
    r = conn.getresponse()
    data = r.read()
    conn.close()
    assert r.status == 200 and data[:4] == b"\x89PNG"
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn.request("GET", "/api/sticker/no_such")   # HTTP 请求行仅限 ASCII，用不存在的短码测 404
    r2 = conn.getresponse()
    r2.read()
    conn.close()
    assert r2.status == 404

    # 登录响应带清单（网页端渲染 [:code:] 用）
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn.request("POST", "/api/login", json.dumps({"nick": "网页君"}).encode(),
                 {"Content-Type": "application/json"})
    d = json.loads(conn.getresponse().read().decode())
    conn.close()
    assert any(s["code"] == "w1" for s in d.get("custom_stickers", []))


def test_client_core_sticker_cache(tmp_path):
    """core：_sync_custom_stickers 建清单并补拉；_on_sticker_data 落盘推事件；
    custom_sticker_path 按存在与否返回路径。"""
    core = ClientCore(host="127.0.0.1", port=1, nick="缓存君",
                      history_dir=str(tmp_path / "h"))
    sent = []
    core._send_frame = lambda header, body=b"": sent.append((header, body)) or True
    core._sync_custom_stickers([{"code": "k1", "label": "K", "ext": "png"}])
    assert core.custom_stickers["k1"]["label"] == "K"
    assert sent and sent[0][0]["t"] == "sticker_custom_get" and \
        sent[0][0]["code"] == "k1"
    assert core.custom_sticker_path("k1") is None      # 未落盘

    core._on_sticker_data({"code": "k1", "ext": "png"}, PNG_1PX)
    path = core.custom_sticker_path("k1")
    assert path and os.path.exists(path)
    ev = core.events.get_nowait()
    assert ev["t"] == "sticker_data" and ev["code"] == "k1"
    core._sync_custom_stickers([])                     # 清单清空
    assert "k1" not in core.custom_stickers


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
                 on_hashtag=lambda word: None,
                 on_react_detail=lambda seq, emoji, ev: None,
                 on_sticker_path=lambda code: None)
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


# ================= R30A 未读分隔线 + 日期跳转 =================

def test_unread_separator_drawn_and_height(ml):
    ml.append(_msg("旧消息", seq=10))
    ml.append(_msg("新消息A", seq=11))
    ml.append(_msg("新消息B", seq=12))
    ml.set_unread_seq(10)
    ml._render()
    texts = [ml.itemcget(i, "text") for i in ml.find_all()
             if ml.type(i) == "text"]
    assert "未读消息" in texts
    # 分隔条只画一次，且边界行高度含 UNREAD_H
    assert texts.count("未读消息") == 1
    h1 = ml._heights[1]
    ml.set_unread_seq(None)
    ml._render()
    assert ml._heights[1] == h1 - UNREAD_H


def test_unread_separator_no_seq_rows_skipped(ml):
    ml.append(_msg(seq=None))                 # 无 seq（历史本地行）不判边界
    ml.append(_msg(seq=5))
    ml.set_unread_seq(3)
    ml._render()
    texts = [ml.itemcget(i, "text") for i in ml.find_all()
             if ml.type(i) == "text"]
    assert "未读消息" in texts                 # 首条 seq>3 之上画线


def test_unread_clears_on_scroll_bottom(ml):
    for i in range(30):
        ml.append(_msg(f"m{i}", seq=100 + i))
    ml.set_unread_seq(105)
    ml._render()
    ml.yview_moveto(0.0)
    ml._set_stick_from_view()
    assert ml._unread_seq == 105              # 未到底：保留
    ml.scroll_to_end()
    ml._set_stick_from_view()
    assert ml._unread_seq is None             # 到底：已读，撤线


def test_dates_and_jump_to_date(ml):
    today = time.time()
    yesterday = today - 86400
    ml.append(_msg("昨天的", seq=1, ts=yesterday - 3600))
    ml.append(_msg("今天的", seq=2, ts=today))
    days = ml.dates()
    assert len(days) == 2
    assert days[-1] == time.strftime("%Y-%m-%d")
    ml.jump_to_date(days[0])
    assert ml._first_visible == 0             # 滚到昨天的第一条
    assert not ml.jump_to_date("1999-01-01")


def test_client_mark_read_key(tmp_path):
    """_mark_read_key：latest_seq 记入 _last_read；无消息不记。"""
    s = type("S", (), {})()
    s.core = type("C", (), {})()
    s.core.latest_seq = lambda ch, to: 42 if ch == "public" else None
    s._pin_key = lambda ch, to: "public"
    s._last_read = {}
    s._touch_conv_state = lambda key: None    # R39B：状态时刻钩子（stub 不采时序）
    ChatWindow._mark_read_key.__get__(s)("public", None)
    assert s._last_read == {"public": 42}
    ChatWindow._mark_read_key.__get__(s)("private", 5)
    assert s._last_read == {"public": 42}     # None 不覆盖


# ================= R30D 回应详情（药丸 hover） =================

def test_pill_hover_detail_callback(ml):
    got = []
    ml._on_react_detail = lambda seq, emoji, ev: got.append((seq, emoji, ev))
    raw = _msg("赞我", seq=300)
    raw["reactions"] = {"👍": {"2": 1.0}}
    ml.append(raw)
    ml._render()
    ml._pill_hover(300, "👍", "EV")
    assert ml._pill_job is not None
    deadline = time.time() + 2.0
    while time.time() < deadline and not got:
        ml.update()
        time.sleep(0.02)
    assert got and got[0][0] == 300 and got[0][1] == "👍"
    ml._pill_hover_end()
    assert got[-1] == (None, None, None)      # 移出 → 收起信号
    ml._pill_hover(300, "👍", "EV")
    ml._pill_hover(300, "❤️", "EV")            # 二次 hover 取消前一个定时器
    ml._pill_hover_end()


def test_client_react_detail_names(root):
    """_on_react_detail：uid → 昵称（roster/known），自己显「我」；hide 销毁。"""
    core = type("C", (), {})()
    core.uid = 1
    core.roster = {2: {"uid": 2, "nick": "小红"}}
    core.known = {}
    raw = {"seq": 1, "reactions": {"👍": {"2": 1.0, "1": 2.0, "9": 3.0}}}
    ml = type("ML", (), {})()
    ml.seq_index = lambda seq: 0
    ml.get_row = lambda i: raw

    class _S:
        pass

    s = _S()
    s.core = core
    s.msg_list = ml
    s._react_tip = None
    s.root = root                        # 复用 module 级 Tk（withdraw 态）
    s._dp = _palette
    det = ChatWindow._on_react_detail.__get__(s)
    det(1, "👍", "EV")
    assert s._react_tip is not None and s._react_tip.winfo_exists()
    det(None, None, None)                 # 收起
    assert s._react_tip is None


# ================= R30E hashtag（分词 + 可点） =================

def test_runs_hashtag_segments():
    segs = runs.tag_entities("看 #加班日常 和 https://a.b 加油")
    kinds = [k for _t, k in segs]
    assert runs.HASHTAG in kinds and runs.LINK in kinds
    tags = [t for t, k in segs if k == runs.HASHTAG]
    assert tags == ["#加班日常"]
    assert runs.tag_entities("") == []
    # 与 @提及共存（重叠跳过，不抛错）
    assert runs.tag_entities("@a #b") == runs.tag_entities("@a #b")


def test_hashtag_run_clickable(ml):
    calls = []
    ml._on_hashtag = lambda word: calls.append(word)
    ml.append(_msg("冲 #摸鱼文化 冲", seq=400))
    ml._render()
    tags = {t for i in ml._item_ids for t in ml.gettags(i)}
    h = [t for t in tags if t.startswith("r30h")]
    assert h
    assert ml.tag_bind(h[0], "<Button-1>")


# ================= R30C 贴纸渲染（msg_list 层） =================

def test_sticker_row_renders_placeholder_and_fetch(ml):
    fetched = []
    ml._sticker_fetch = lambda code: fetched.append(code)
    ml.append(_msg("[:mochi:]", seq=500))
    ml._render()
    row = ml._rows[0]
    assert row.sticker_custom == "mochi"      # 整条短码 → 贴纸行
    assert row.body == "[贴纸] :mochi:"       # 搜索/复制占位
    texts = [ml.itemcget(i, "text") for i in ml.find_all()
             if ml.type(i) == "text"]
    assert "[:mochi:]" in texts               # 未缓存 → 短码占位
    assert fetched == ["mochi"]               # 触发一次拉取（去重）
    ml._render()
    ml._render()
    assert fetched == ["mochi"]               # 重绘不重复拉取


def test_sticker_mixed_text_stays_plain(ml):
    ml.append(_msg("看 [:a:] 好笑", seq=501))
    ml._render()
    assert ml._rows[0].sticker_custom is None  # 混排 → 普通文本行
    assert "[:a:]" in ml._rows[0].body


def test_sticker_updated_and_clear_reset(ml):
    ml._stk_req.add("x")
    ml.stickers_updated()
    assert ml._stk_req == set()               # 事件到达清去重集
    ml._stk_req.add("x")
    ml.clear()
    assert ml._stk_req == set() and ml._unread_seq is None
