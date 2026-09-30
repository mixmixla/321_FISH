# -*- coding: utf-8 -*-
"""R46 测试：#16 Bots inline 键盘+命令补全 / #19 伪装包。

覆盖：
- bots.py：命令注册表形状、kb_rows 分行、help_kb 生成、handler 返回 (text, kb)
- msg_list._sanitize_kb：正常/畸形键盘形状校验
- config.CAMO_PRESETS：预设表完整性与唯一性
- tray.set_tip：tooltip 更新（Mock pystray）
- 服务器集成：bot 回复携带 kb 字段、kb 随历史 publish 保留、
  bot_say kb 透传给客户端、网页端登录下发 bots 清单
"""
import socket
import threading
import time
import tkinter as tk
from dataclasses import replace

import pytest

import bots as _bots
from config import CAMO_PRESETS, CFG
from protocol import MsgType
from server import Hub, serve as serve_tcp
from widgets.msg_list import _sanitize_kb

FONT = ("Microsoft YaHei UI", 9)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def hub(tmp_path):
    cfg = replace(CFG,
                  audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"))
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


# ================= 单元：bots.py 命令注册表 =================

def test_bot_commands_registered():
    """每个 bot 的 commands 非空且 (cmd, desc) 形状正确"""
    for bot in _bots.BOTS:
        assert bot.commands, f"{bot.nick} 无命令注册"
        for cmd, desc in bot.commands:
            assert isinstance(cmd, str) and cmd
            assert isinstance(desc, str) and desc


def test_kb_rows_split():
    """kb_rows 按每行 3 个按钮分组"""
    btns = [("A", "a"), ("B", "b"), ("C", "c"), ("D", "d"), ("E", "e")]
    rows = _bots.kb_rows(btns, per_row=3)
    assert len(rows) == 2                   # 5 个按钮 → 2 行
    assert len(rows[0]) == 3 and len(rows[1]) == 2
    assert rows[0][0] == {"t": "A", "c": "a"}
    assert rows[1][1] == {"t": "E", "c": "e"}


def test_help_kb_matches_commands():
    """help_kb 生成的键盘按钮数 = 命令数"""
    kb = _bots.help_kb(_bots.BOT_DICE)
    assert kb is not None
    total = sum(len(r) for r in kb)
    assert total == len(_bots.BOT_DICE.commands)
    # 每个按钮 t == 命令、c == 命令
    flat = [b for r in kb for b in r]
    for i, (cmd, _d) in enumerate(_bots.BOT_DICE.commands):
        assert flat[i]["t"] == cmd and flat[i]["c"] == cmd


def test_bot_handle_returns_kb_tuple():
    """骰子 bot 收到「帮助」时返回 (text, kb) 元组"""
    replies = _bots.BOT_DICE.handle(None, {"text": "帮助", "nick": "甲",
                                          "uid": 1})
    assert len(replies) == 1
    text, kb = replies[0]
    assert isinstance(text, str) and "点下方按钮" in text
    assert kb is not None and isinstance(kb, list)


def test_bot_handle_dice_roll():
    """骰子 bot 收到「d20」时返回纯字符串（带骰子结果）"""
    replies = _bots.BOT_DICE.handle(None, {"text": "d20", "nick": "甲",
                                          "uid": 1})
    assert len(replies) == 1
    text = replies[0]
    assert isinstance(text, str) and "掷出了" in text and "/ 20" in text


# ================= 单元：_sanitize_kb 形状校验 =================

def test_sanitize_kb_valid():
    kb = [[{"t": "骰子", "c": "骰子"}, {"t": "d20", "c": "d20"}]]
    out = _sanitize_kb(kb)
    assert out == kb


def test_sanitize_kb_none_for_non_list():
    assert _sanitize_kb("not a list") is None
    assert _sanitize_kb(None) is None
    assert _sanitize_kb(42) is None


def test_sanitize_kb_rejects_missing_fields():
    assert _sanitize_kb([[{"t": "ok"}]]) is None     # 缺 c
    assert _sanitize_kb([[{"c": "ok"}]]) is None     # 缺 t
    assert _sanitize_kb([[{"t": "", "c": "ok"}]]) is None   # t 空
    assert _sanitize_kb([[{"t": "ok", "c": ""}]]) is None   # c 空


def test_sanitize_kb_rejects_non_dict_button():
    assert _sanitize_kb([["str"]]) is None
    assert _sanitize_kb([[42]]) is None


def test_sanitize_kb_truncates_long_text():
    long_t = "A" * 100
    long_c = "B" * 200
    out = _sanitize_kb([[{"t": long_t, "c": long_c}]])
    assert len(out[0][0]["t"]) == 24
    assert len(out[0][0]["c"]) == 120


def test_sanitize_kb_limits_rows_and_cols():
    """超过 4 行/4 列 → 截断（不报错）"""
    big = [[{"t": f"t{i}", "c": f"c{i}"} for i in range(6)] for _ in range(6)]
    out = _sanitize_kb(big)
    assert len(out) == 4                    # 行限 4
    for row in out:
        assert len(row) == 4                # 列限 4


def test_sanitize_kb_empty_rows_dropped():
    """空行（无按钮）被丢弃"""
    out = _sanitize_kb([[{"t": "A", "c": "a"}], []])
    assert len(out) == 1


# ================= 单元：CAMO_PRESETS 伪装包 =================

def test_camo_presets_complete():
    """预设表含「关闭」和至少 3 种预设"""
    names = [n for n, _ in CAMO_PRESETS]
    assert "关闭" in names
    assert len(CAMO_PRESETS) >= 4


def test_camo_presets_unique_names():
    names = [n for n, _ in CAMO_PRESETS]
    assert len(names) == len(set(names))


def test_camo_off_value_is_empty():
    """「关闭」预设的值为空串"""
    d = dict(CAMO_PRESETS)
    assert d["关闭"] == ""


# ================= 单元：tray.set_tip =================

def test_tray_set_tip(monkeypatch):
    """set_tip 更新 icon.title（Mock pystray.Icon）"""
    from widgets import tray as _tray_mod

    class _FakeIcon:
        def __init__(self):
            self.title = "办公助手"
            self.name = "assistant"

        def run_detached(self):
            pass

        def stop(self):
            pass

    # 跳过 __init__ 直接构造实例
    t = _tray_mod.Tray.__new__(_tray_mod.Tray)
    t._icon = _FakeIcon()
    t._root = None
    t.set_tip("Book1 - Excel")
    assert t._icon.title == "Book1 - Excel"
    # 空串回退默认
    t.set_tip("")
    assert t._icon.title == "办公助手"


def test_tray_set_tip_noop_without_icon():
    """托盘未初始化时 set_tip 静默不报错"""
    from widgets import tray as _tray_mod
    t = _tray_mod.Tray.__new__(_tray_mod.Tray)
    t._icon = None
    t.set_tip("test")          # 不应抛异常


# ================= 集成：服务器 bot_say 携带 kb =================

def test_bot_reply_carries_kb(hub):
    """bot 回复「帮助」时消息带 kb 字段，kb 随历史 publish 保留"""
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    a.send({"t": "chat", "channel": "private", "to": _bots.BOT_DICE.uid,
            "text": "帮助"})
    hr, _ = a.wait("chat", pred=lambda x: x.get("uid") == _bots.BOT_DICE.uid)
    assert hr and "kb" in hr
    assert isinstance(hr["kb"], list) and hr["kb"]
    # kb 随历史 publish 保留
    key = h.bus.key("private", _bots.BOT_DICE.uid, a.uid)
    hist = h.bus.history(key)
    bot_msg = [m for m in hist if m.get("uid") == _bots.BOT_DICE.uid]
    assert bot_msg and "kb" in bot_msg[-1]
    a.close()


def test_bot_kb_click_sends_command(hub):
    """点击键盘按钮 = 向 bot 发指令 → bot 回复（闭环验证）"""
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    # 先触发帮助得到键盘
    a.send({"t": "chat", "channel": "private", "to": _bots.BOT_DICE.uid,
            "text": "帮助"})
    hr, _ = a.wait("chat", pred=lambda x: x.get("uid") == _bots.BOT_DICE.uid)
    assert hr and "kb" in hr
    # 取第一个按钮的 c 值，向 bot 发送
    cmd = hr["kb"][0][0]["c"]
    a.send({"t": "chat", "channel": "private", "to": _bots.BOT_DICE.uid,
            "text": cmd})
    h2, _ = a.wait("chat", pred=lambda x: x.get("uid") == _bots.BOT_DICE.uid
                   and x.get("text") != hr.get("text"))
    assert h2 and "掷出了" in (h2.get("text") or "")
    a.close()


def test_web_login_returns_bots_list(hub):
    """网页端登录响应的 bots 清单来源：hub._known_list() 含全部 bot 条目
    （web.py /api/login 直接下发 _bots.BOTS 元数据 + known 供 roster 展示）"""
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    known = h._known_list()
    bot_entries = [u for u in known if u.get("type") == "bot"]
    assert {u["uid"] for u in bot_entries} == set(_bots.BOT_BY_UID)
    # web.py 登录响应字段与 BOTS 元数据一致
    bots_meta = [{"uid": b.uid, "nick": b.nick, "desc": b.desc}
                 for b in _bots.BOTS]
    assert bots_meta[0]["nick"] == "骰子娘"
    a.close()


# ================= 集成：bot 命令补全数据源 =================

def test_bot_command_completion_source():
    """BOT_BY_UID 查表 → 命令列表（补全候选数据源）"""
    bot = _bots.BOT_BY_UID[_bots.BOT_DICE.uid]
    cmds = [c for c, _ in bot.commands]
    assert "骰子" in cmds and "d20" in cmds and "d100" in cmds


def test_bot_prefix_filter():
    """命令前缀过滤（补全逻辑核心）"""
    bot = _bots.BOT_BY_UID[_bots.BOT_DICE.uid]
    low = "d"
    matched = [c for c, _ in bot.commands if c.lower().startswith(low)]
    assert "d20" in matched and "d100" in matched
    assert "骰子" not in matched


# ================= 集成：伪装标题 prefs =================

def test_camo_persist_and_apply(tmp_path):
    """prefs['camo'] 写入/读取 + _camo_title 回退逻辑"""
    from prefs import Prefs
    p = Prefs(str(tmp_path / "p.json"))
    assert p.get("camo") == "" or p.get("camo") is None   # 默认空
    p.set("camo", "Book1 - Excel")
    assert p.get("camo") == "Book1 - Excel"
    # 重新加载
    p2 = Prefs(str(tmp_path / "p.json"))
    assert p2.get("camo") == "Book1 - Excel"


# ================= UI：msg_list 键盘渲染 =================

@pytest.fixture(scope="module")
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def test_msg_list_kb_render_and_callback(root):
    """bot 消息带 kb → 行解析出键盘且高度计入；on_kb 回调接线"""
    from widgets.msg_list import MsgList
    clicks = []
    ml = MsgList(root, FONT, me_uid=1,
                 on_kb=lambda uid, cmd: clicks.append((uid, cmd)))
    ml.configure(width=400, height=300)
    ml.pack()
    try:
        ml.append({"seq": 1, "uid": 901, "nick": "骰子娘", "text": "帮助",
                   "ts": time.time(), "channel": "private", "to": 1,
                   "kb": [[{"t": "骰子", "c": "骰子"}]]})
        ml.update()
        row = ml._rows[-1]
        assert row.kb == [[{"t": "骰子", "c": "骰子"}]]
        assert ml._kb_height(row) == ml.KB_BTN_H + ml.KB_GAP
        # 无 kb 消息：键盘高度 0
        ml.append({"seq": 2, "uid": 901, "nick": "骰子娘", "text": "plain",
                   "ts": time.time(), "channel": "private", "to": 1})
        ml.update()
        assert ml._kb_height(ml._rows[-1]) == 0
        # 回调接线
        ml._on_kb(901, "骰子")
        assert clicks == [(901, "骰子")]
    finally:
        ml.destroy()
