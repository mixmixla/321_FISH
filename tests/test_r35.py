# -*- coding: utf-8 -*-
"""R35 生态包测试（贴纸商店 / Bots / 多档案）。

覆盖：
- 服务器贴纸商店：STICKER_SHOP 回目录+默认订阅、STICKER_SUB 订阅/退订回全量、
  非法包报错、welcome 带回订阅、重连后订阅保持
- 服务器 Bots：welcome known 含 type=bot、私聊发骰子/回声 bot 得回复、
  发送方收到自己消息回显、提醒到期 sweeper 推送、群聊发 bot 不拦截
- prefs 多档案：首账号认领顶层状态、切换换出/换入 pinned/muted/archived/drafts
- client_core：按昵称历史子目录+旧文件迁移、sticker_shop_list/sticker_sub
  帧处理进状态+事件流、subscribed_stickers 过滤与回退
- UI：StickerShop 渲染与订阅回调
"""
import os
import socket
import threading
import time
import tkinter as tk
from dataclasses import replace

import pytest

import bots as _bots
from client_core import ClientCore, _nick_history_dir, _nick_safe
from config import CFG
from prefs import Prefs
from protocol import MsgType
from server import Hub, serve as serve_tcp
from widgets.sticker_shop import StickerShop

FONT = ("Microsoft YaHei UI", 9)


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


# ================= 贴纸商店（服务器） =================

def test_sticker_shop_catalog_and_default_subs(hub):
    h, port, _ = hub
    a = _Cli(port, "甲")
    w = a.hello()
    assert w and "sticker_subs" in w              # welcome 带回订阅
    assert w["sticker_subs"] == ["basic"]         # 未自选 → 默认订阅
    a.send({"t": MsgType.STICKER_SHOP.value})
    hl, _ = a.wait(MsgType.STICKER_SHOP_LIST.value)
    assert hl and hl.get("packs")
    ids = [p["pack_id"] for p in hl["packs"]]
    assert "basic" in ids and "mood" in ids
    for p in hl["packs"]:
        assert p.get("items") and p["items"][0].get("emoji")
    a.close()


def test_sticker_sub_toggle_and_persist(hub):
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    a.send({"t": MsgType.STICKER_SUB.value, "pack_id": "mood", "on": True})
    hs, _ = a.wait(MsgType.STICKER_SUB.value)
    assert hs and hs["subs"] == ["basic", "mood"]     # 回帧带全量
    a.send({"t": MsgType.STICKER_SUB.value, "pack_id": "basic", "on": False})
    hs2, _ = a.wait(MsgType.STICKER_SUB.value)
    assert hs2 and hs2["subs"] == ["mood"]            # 退订
    # 重连后订阅保持（welcome 带回）
    a.close()
    b = _Cli(port, "甲")
    w = b.hello()
    assert w["sticker_subs"] == ["mood"]
    b.close()


def test_sticker_sub_invalid_pack(hub):
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    a.send({"t": MsgType.STICKER_SUB.value, "pack_id": "nope", "on": True})
    he, _ = a.wait("error", pred=lambda x: x.get("code") == "pack")
    assert he
    a.close()


# ================= Bots（服务器） =================

def test_bots_in_known_and_welcome(hub):
    h, port, _ = hub
    a = _Cli(port, "甲")
    w = a.hello()
    bots_known = [u for u in (w.get("known") or []) if u.get("type") == "bot"]
    assert len(bots_known) == len(_bots.BOTS)
    assert {u["uid"] for u in bots_known} == set(_bots.BOT_BY_UID)
    a.close()


def test_bot_dice_and_echo_reply(hub):
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    # 回声 bot：原样复读
    a.send({"t": "chat", "channel": "private", "to": _bots.BOT_ECHO.uid,
            "text": "hello123"})
    hr, _ = a.wait("chat", pred=lambda x: x.get("uid") == _bots.BOT_ECHO.uid)
    assert hr and "🔁 hello123" in (hr.get("text") or "")
    assert hr["channel"] == "private" and hr["to"] == a.uid
    # 骰子 bot：掷骰回复
    a.send({"t": "chat", "channel": "private", "to": _bots.BOT_DICE.uid,
            "text": "骰子"})
    hd, _ = a.wait("chat", pred=lambda x: x.get("uid") == _bots.BOT_DICE.uid)
    assert hd and "掷出了" in (hd.get("text") or "")
    # 发送方收到自己发往 bot 的消息回显
    ho, _ = a.wait("chat", pred=lambda x: x.get("uid") == a.uid
                   and x.get("to") == _bots.BOT_DICE.uid)
    assert ho and ho.get("text") == "骰子"
    a.close()


def test_bot_reminder_due_push(hub):
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    # 直接注入一条到期提醒（避免真实等待）
    h.bot_reminders.append({"uid": a.uid, "due": time.time() - 1,
                            "text": "开会", "bot_uid": _bots.BOT_REMIND.uid})
    _bots.sweep_reminders(h)
    hr, _ = a.wait("chat", pred=lambda x: x.get("uid") == _bots.BOT_REMIND.uid)
    assert hr and "提醒" in (hr.get("text") or "") and "开会" in hr.get("text")
    assert not h.bot_reminders                   # 队列已清
    a.close()


def test_bot_remind_parse_and_queue(hub):
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    a.send({"t": "chat", "channel": "private", "to": _bots.BOT_REMIND.uid,
            "text": "23:59 收衣服"})
    hr, _ = a.wait("chat", pred=lambda x: x.get("uid") == _bots.BOT_REMIND.uid)
    assert hr and "已设置提醒" in (hr.get("text") or "")
    assert len(h.bot_reminders) == 1 and h.bot_reminders[0]["uid"] == a.uid
    a.close()


def test_group_chat_not_bot_intercepted(hub):
    """群聊里即使文本像命令也不触发 bot（仅私聊拦截）"""
    h, port, _ = hub
    a = _Cli(port, "甲")
    a.hello()
    a.send({"t": "chat", "channel": "public", "text": "骰子"})
    hp, _ = a.wait("chat", pred=lambda x: x.get("uid") == a.uid
                   and x.get("channel") == "public")
    assert hp and hp.get("text") == "骰子"        # 原样广播，无 bot 回复
    a.close()


# ================= prefs 多档案 =================

def test_prefs_profile_claim_and_switch(tmp_path):
    p = Prefs(str(tmp_path / "prefs.json"))
    p.toggle_pin("private:2")                    # 老用户：顶层已有会话状态
    p.set("drafts", {"public": "草稿A"})
    p.remember_account("甲")                     # 首账号认领顶层状态
    assert p.known_accounts() == ["甲"]
    assert p.is_pinned("private:2")
    # 切到新账号：状态清空，甲的状态快照保留
    p.remember_account("乙")
    p.switch_profile("乙")
    assert p.active_account() == "乙"
    assert not p.is_pinned("private:2")
    assert p.get("drafts") == {}
    # 切回甲：状态完整恢复
    p.switch_profile("甲")
    assert p.is_pinned("private:2")
    assert p.get("drafts") == {"public": "草稿A"}
    assert p.known_accounts() == sorted(["甲", "乙"])


def test_prefs_switch_saves_dirty_state(tmp_path):
    p = Prefs(str(tmp_path / "prefs.json"))
    p.remember_account("甲")
    p.toggle_mute("group:7")                     # 会话中改动（仅顶层+落盘）
    p.switch_profile("乙")
    p.switch_profile("甲")
    assert p.is_muted("group:7")                 # 换出时快照进档案


# ================= client_core：多档案目录 / 商店帧 =================

def test_nick_history_dir_migration(tmp_path, monkeypatch):
    base = tmp_path / "history"
    base.mkdir()
    (base / "public.jsonl").write_text('{"seq":1}\n', encoding="utf-8")
    (base / "voice").mkdir()
    monkeypatch.setattr("client_core._default_history_dir", lambda: str(base))
    d = _nick_history_dir("小明")
    assert os.path.basename(d) == _nick_safe("小明")
    assert (base / _nick_safe("小明") / "public.jsonl").exists()   # 旧文件已迁入
    assert not (base / "public.jsonl").exists()
    # 二次调用同账号：目录已存在，不再迁移
    assert _nick_history_dir("小明") == d


def test_core_sticker_shop_frames(tmp_path):
    core = ClientCore(nick="测试", history_dir=str(tmp_path / "d"))
    core._dispatch({"t": MsgType.STICKER_SHOP_LIST.value,
                    "packs": [{"pack_id": "mood", "name": "心情",
                               "items": [{"code": "cool", "emoji": "😎"}]}],
                    "subs": ["mood"]})
    ev = core.events.get_nowait()
    assert ev["t"] == MsgType.STICKER_SHOP_LIST.value
    assert core.sticker_subs == ["mood"]
    assert core.subscribed_stickers() == [{"code": "cool", "emoji": "😎"}]
    core._dispatch({"t": MsgType.STICKER_SUB.value, "pack_id": "mood",
                    "on": False, "subs": []})
    ev = core.events.get_nowait()
    assert ev["t"] == MsgType.STICKER_SUB.value
    assert core.sticker_subs == []
    assert core.subscribed_stickers() == []       # 空订阅 → 不回退（商店已拉到）
    # 未拉商店目录时回退服务器内置平铺
    core2 = ClientCore(nick="测试", history_dir=str(tmp_path / "d2"))
    core2.stickers = [{"code": "smile", "emoji": "😀"}]
    assert core2.subscribed_stickers() == [{"code": "smile", "emoji": "😀"}]


def test_core_send_sticker_shop_and_sub(tmp_path):
    core = ClientCore(nick="测试", history_dir=str(tmp_path / "d"))
    calls = []

    def fake_send(header, body=b""):
        calls.append(header)
        return True

    core._send_frame = fake_send
    assert core.request_sticker_shop()
    assert calls[-1]["t"] == MsgType.STICKER_SHOP.value
    assert core.send_sticker_sub("mood", True)
    assert calls[-1] == {"t": MsgType.STICKER_SUB.value, "pack_id": "mood",
                         "on": True}


def test_core_nick_history_scoping(tmp_path):
    """显式 history_dir 优先；不指定时按昵称子目录隔离"""
    import client_core as cc
    d = tmp_path / "d"
    core = ClientCore(nick="测试", history_dir=str(d))
    assert core._history._dir == os.path.abspath(str(d))
    monkey_base = tmp_path / "base"
    monkey_base.mkdir()
    orig = cc._default_history_dir
    cc._default_history_dir = lambda: str(monkey_base)
    try:
        core2 = ClientCore(nick="阿明")
        assert os.path.basename(core2._history._dir) == _nick_safe("阿明")
    finally:
        cc._default_history_dir = orig


# ================= UI：商店窗口 =================

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


def test_sticker_shop_render_and_toggle(root):
    class _Core:
        sticker_shop = [
            {"pack_id": "basic", "name": "常用",
             "items": [{"code": "smile", "emoji": "😀"},
                       {"code": "laugh", "emoji": "😂"}]},
            {"pack_id": "mood", "name": "心情",
             "items": [{"code": "cool", "emoji": "😎"}]},
        ]
        sticker_subs = ["basic"]

        def request_sticker_shop(self):
            pass

    toggles = []
    core = _Core()
    dlg = StickerShop(root, core=core,
                      on_toggle=lambda pid, on: toggles.append((pid, on)))
    try:
        cards = dlg.body.winfo_children()
        assert len(cards) == 2                     # 两个包各一节
        # 未订阅的"心情"包 → 按钮文本 ＋ 订阅；点击回调
        btn = None
        for c in cards:
            for w in c.winfo_children():
                if isinstance(w, tk.Frame):
                    for x in w.winfo_children():
                        if isinstance(x, tk.Button) and "订阅" in x.cget("text"):
                            btn = x
        assert btn is not None and "＋" in btn.cget("text")
        btn.invoke()
        assert toggles == [("mood", True)]
        # 订阅态变化 → refresh 重绘为已订阅
        core.sticker_subs = ["basic", "mood"]
        dlg.refresh()
        texts = []
        for c in dlg.body.winfo_children():
            for w in c.winfo_children():
                if isinstance(w, tk.Frame):
                    for x in w.winfo_children():
                        if isinstance(x, tk.Button):
                            texts.append(x.cget("text"))
        assert any("已订阅" in t for t in texts)
    finally:
        dlg.destroy()
