# -*- coding: utf-8 -*-
"""R73 P0：消息三态标记（发送中 → 已送达 → 已读）。

覆盖：
- runs.PENDING 常量已注册（KINDS 含 pending）
- msg_list._heading_segs：pending 行渲染「⏳发送中」；私聊未读单勾 ✓；
  已读双勾 ✓✓；pending 优先于勾（互斥）
- client.ChatWindow._confirm_pending：服务器回显 → 移除发送中行（同会话+同文本+时间接近）；
  不同文本不匹配；历史装载（ts 差 >2s）不误删
- client.ChatWindow._pending_timeout：超时 → 转 failed + resend 参数可重发
"""
import time
import tkinter as tk
from types import SimpleNamespace

import pytest

from widgets import runs
from widgets.msg_list import MsgList

from client import ChatWindow

FONT = ("Microsoft YaHei UI", 9)


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


def test_pending_constant_registered():
    """runs.PENDING 已定义并纳入 KINDS。"""
    assert runs.PENDING == "pending"
    assert runs.PENDING in runs.KINDS


def _own_row(root, text="hi", seq=None, pending=False, channel="private",
             to=9):
    m = MsgList(root, FONT)
    m.set_me_uid(2)
    m.append({"uid": 2, "nick": "我", "channel": channel, "to": to,
              "ts": time.time(), "text": text, "seq": seq,
              "pending": pending})
    return m


def test_heading_pending_mark(root):
    """pending 行渲染「⏳发送中」段，且不画单勾。"""
    m = _own_row(root, pending=True)
    segs = m._heading_segs(m._rows[0], False, True)
    m.destroy()
    kinds = [k for _, k in segs]
    assert runs.PENDING in kinds
    assert runs.SENT_MARK not in kinds
    assert runs.READ_MARK not in kinds
    txt = "".join(t for t, _ in segs)
    assert "⏳发送中" in txt


def test_heading_sent_mark_after_confirm(root):
    """确认后（seq 有值、未读）：私聊渲染单勾 ✓（已送达）。"""
    m = _own_row(root, seq=12)
    segs = m._heading_segs(m._rows[0], False, True)
    m.destroy()
    kinds = [k for _, k in segs]
    assert runs.SENT_MARK in kinds
    assert runs.PENDING not in kinds


def test_heading_read_mark_after_read(root):
    """对端已读：双勾 ✓✓已读。"""
    m = _own_row(root, seq=12)
    m.set_reads({"9": 12})
    segs = m._heading_segs(m._rows[0], False, True)
    m.destroy()
    kinds = [k for _, k in segs]
    assert runs.READ_MARK in kinds
    assert runs.SENT_MARK not in kinds


def test_heading_pending_group(root):
    """群聊 pending 行同样渲染发送中标记。"""
    m = _own_row(root, pending=True, channel="group", to=5)
    segs = m._heading_segs(m._rows[0], True, True)
    m.destroy()
    assert runs.PENDING in [k for _, k in segs]


# ================= client 侧：确认 / 超时 =================

class _FakeML:
    """msg_list 最小替身：记录 append/drop/redraw。"""

    def __init__(self):
        self.rows = []
        self.redraws = 0

    def append(self, raw):
        self.rows.append(raw)

    def drop_local_row(self, raw):
        if raw in self.rows:
            self.rows.remove(raw)
            return True
        return False

    def redraw_all(self):
        self.redraws += 1


class _PendingApp:
    """ChatWindow 轻量实例：仅承载 P0 三态方法，免真实 UI。"""
    __test__ = False

    def __init__(self, uid=2):
        self.core = SimpleNamespace(uid=uid, nick="我")
        self.msg_list = _FakeML()
        self._pending_rows = []
        self.root = SimpleNamespace(after=lambda ms, cb: None)
        self._PENDING_TTL = 8.0

    _append_pending = ChatWindow._append_pending
    _confirm_pending = ChatWindow._confirm_pending
    _pending_timeout = ChatWindow._pending_timeout


def _mk_pending(app, text="hi", channel="private", to=9):
    app._append_pending(text, channel=channel, to=to)
    return app._pending_rows[0]


def test_confirm_pending_removes_on_echo():
    """服务器回显（同会话+同文本+时间接近）→ 发送中行移除。"""
    app = _PendingApp()
    raw = _mk_pending(app, "hi", "private", 9)
    assert raw in app.msg_list.rows
    echo = {"uid": 2, "channel": "private", "to": 9, "seq": 12,
            "text": "hi", "ts": time.time() + 0.05}
    app._confirm_pending(echo)
    assert app._pending_rows == []
    assert raw not in app.msg_list.rows


def test_confirm_pending_ignores_other_text():
    """不同正文的回显不误删。"""
    app = _PendingApp()
    raw = _mk_pending(app, "hi")
    echo = {"uid": 2, "channel": "private", "to": 9, "seq": 12,
            "text": "bye", "ts": time.time()}
    app._confirm_pending(echo)
    assert app._pending_rows == [raw]


def test_confirm_pending_ignores_old_history():
    """历史装载（ts 远离 now）不误删发送中行。"""
    app = _PendingApp()
    raw = _mk_pending(app, "hi")
    echo = {"uid": 2, "channel": "private", "to": 9, "seq": 12,
            "text": "hi", "ts": time.time() - 300}
    app._confirm_pending(echo)
    assert app._pending_rows == [raw]


def test_pending_timeout_converts_to_failed():
    """超时未确认 → 转失败行（带 resend 重发参数），可复用 ❗ 重发。"""
    app = _PendingApp()
    raw = _mk_pending(app, "hi", "group", 5)
    app._pending_timeout(raw)
    assert app._pending_rows == []
    assert raw.get("pending") is False
    assert raw.get("failed") is True
    rs = raw.get("resend") or {}
    assert rs.get("channel") == "group" and rs.get("to") == 5
    assert app.msg_list.redraws == 1


def test_pending_timeout_already_confirmed_noop():
    """已确认移除的行，超时回调不重复转换。"""
    app = _PendingApp()
    raw = _mk_pending(app, "hi")
    app._confirm_pending({"uid": 2, "channel": "private", "to": 9,
                          "seq": 1, "text": "hi", "ts": time.time()})
    app._pending_timeout(raw)
    assert app._pending_rows == []
