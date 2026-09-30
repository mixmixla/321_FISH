# -*- coding: utf-8 -*-
"""P0：图片/文件消息支持转发（单条+多选）回归。

覆盖：
- _fwd_snapshot：文本/表情/桌面图片（image_path）/网页文件（file 字典）
  快照构造；语音/投票/已删除行 → None
- 桌面图片无 seq 也可单条转发（_forward 不再拒绝）
- _sel_forward_snaps：图片+文本多选齐收；被删行跳过
- _forward_pick 私聊目标 → 真实重发图片（send_file 落点 + caption 保留）
- 群/公共目标 / 本地文件缺失 → 转文本引用（send_chat + forward 快照）
- _merge_forward：无 seq 的图片行被过滤，不误报"缺少序号"
"""
import os
import time
import tkinter as tk

import pytest

from client import ChatWindow


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


@pytest.fixture(autouse=True)
def _no_leftover_dlg(root):
    """每测后清掉残留 Toplevel：Windows 上 Tk 快速建/毁 root 有 init.tcl
    竞态，故共用模块级 root；残留对话框销毁，避免跨测串扰。"""
    yield
    for w in list(root.winfo_children()):
        if isinstance(w, tk.Toplevel):
            try:
                w.destroy()
            except tk.TclError:
                pass


class _Files:
    def __init__(self):
        self.sent = []

    def send_file(self, path, to, caption=""):
        self.sent.append((path, to, caption))
        return "fid-x"


class _Core:
    def __init__(self):
        self.uid = 1
        self.nick = "甲"
        self.roster = {2: {"nick": "乙"}, 3: {"nick": "丙"}}
        self.groups = {10: {"name": "测试群"}}
        self.files = _Files()
        self.chats = []

    def send_chat(self, text="", sticker="", channel="public", to=None,
                  forward=None, fwd_seqs=None, fwd_from=None):
        self.chats.append((text, sticker, channel, to, forward))


class _MsgList:
    def __init__(self, rows):
        self._rows = rows
        self._sel = set()

    def get_row(self, idx):
        return self._rows[idx] if 0 <= idx < len(self._rows) else None

    def selected_rows(self):
        return sorted(self._sel)

    def exit_select_mode(self, notify=True):
        pass


@pytest.fixture()
def app(root):
    a = ChatWindow.__new__(ChatWindow)
    a.root = root
    a._dp = {"win": "#f0f0f0"}
    a._skin = {}
    a._apply_apple_dialog = lambda dlg, title=None: None
    a.view = ("public", None)
    a.core = _Core()
    a._append_sys = lambda *_, **__: None
    a._append_msg = lambda *_, **__: None
    a.msg_list = _MsgList([])
    return a


def _img_row(path, **kw):
    d = {"uid": 2, "nick": "乙", "channel": "private", "to": 1,
         "ts": time.time(), "image_path": str(path)}
    d.update(kw)
    return d


# ---------- _fwd_snapshot ----------

def test_fwd_snapshot_kinds(app):
    s = app._fwd_snapshot({"uid": 1, "nick": "甲", "seq": 5, "text": "hi"})
    assert s["text"] == "hi" and s["seq"] == 5 and s["nick"] == "甲"
    s = app._fwd_snapshot({"uid": 1, "nick": "甲", "seq": 6, "sticker": "s1"})
    assert s["sticker"] == "s1"
    s = app._fwd_snapshot({"uid": 1, "nick": "甲", "seq": 7,
                           "file": {"kind": "file", "name": "报表.xlsx",
                                    "size": 2048}})
    assert s["text"] == "[文件] 报表.xlsx（2KB）"
    s = app._fwd_snapshot({"uid": 1, "nick": "甲", "seq": 8,
                           "file": {"kind": "image", "name": "w.png",
                                    "size": 4096}})
    assert s["text"] == "[图片] w.png（4KB）"


def test_fwd_snapshot_unsupported_or_deleted(app):
    assert app._fwd_snapshot(None) is None
    assert app._fwd_snapshot({"uid": 1, "nick": "甲", "seq": 8,
                              "voice": True, "voice_path": "v.wav"}) is None
    assert app._fwd_snapshot({"uid": 1, "nick": "甲", "deleted": True,
                              "text": "x"}) is None


def test_fwd_snapshot_image_preserves_caption(app, tmp_path):
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    s = app._fwd_snapshot(_img_row(img, text="  海边日落  "))
    assert s["image_path"] == str(img)
    assert s["text"] == f"[图片] {img.name}"
    assert s["caption"] == "海边日落"


# ---------- 单条 / 多选 ----------

def test_forward_image_row_no_seq(app, tmp_path, monkeypatch):
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    app.msg_list._rows = [_img_row(img, text="cap")]
    captured = {}
    monkeypatch.setattr(app, "_forward_pick",
                        lambda fwd: captured.update(fwd))
    app._forward(0)
    assert captured.get("image_path") == str(img)
    assert captured.get("caption") == "cap"


def test_forward_unsupported_gives_notice(app):
    app.msg_list._rows = [{"uid": 1, "nick": "甲", "seq": 9,
                           "voice": True, "voice_path": "v.wav"}]
    sys_msgs = []
    app._append_sys = sys_msgs.append
    app._forward(0)
    assert sys_msgs and "不支持转发" in sys_msgs[0]


def test_sel_forward_snaps_collects(app, tmp_path):
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    app.msg_list._rows = [
        _img_row(img),
        {"uid": 1, "nick": "甲", "seq": 5, "text": "hello"},
        {"uid": 1, "nick": "甲", "seq": 6, "sticker": "s1"},
        {"uid": 3, "nick": "丙", "seq": 7, "text": "del", "deleted": True},
    ]
    app.msg_list._sel = {0, 1, 2, 3}
    snaps = app._sel_forward_snaps()
    assert len(snaps) == 3
    texts = {s.get("text") for s in snaps if s.get("text")}
    assert texts == {"hello", f"[图片] {img.name}"}
    assert any(s.get("sticker") == "s1" for s in snaps)


# ---------- _forward_pick 目标分发 ----------

def _open_dlg(app):
    for w in app.root.winfo_children():
        if isinstance(w, tk.Toplevel):
            return w
    return None


def _pick_and_invoke(dlg, label):
    lb = next(w for w in dlg.winfo_children() if isinstance(w, tk.Listbox))
    idx = next(i for i in range(lb.size()) if lb.get(i) == label)
    lb.selection_set(idx)
    btn = next(w for w in dlg.winfo_children()
               if isinstance(w, tk.Button)
               and str(w.cget("text")) == "转发")
    btn.invoke()


def test_forward_pick_private_image_real_send(app, tmp_path):
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    appended = []
    app._append_msg = lambda m: appended.append(m)
    snap = app._fwd_snapshot(_img_row(img, text="cap"))
    app._forward_pick([snap])
    app.root.update()
    dlg = _open_dlg(app)
    assert dlg is not None
    _pick_and_invoke(dlg, "乙")
    app.root.update()
    assert app.core.files.sent and app.core.files.sent[0][0] == str(img)
    assert app.core.files.sent[0][2] == "cap"
    assert not app.core.chats        # 图片真实转发不落 chat 文本引用
    assert appended and appended[0]["image_path"] == str(img)   # 本地立即可见


def test_forward_pick_group_image_text_ref(app, tmp_path):
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    snap = app._fwd_snapshot(_img_row(img))
    app._forward_pick([snap])
    app.root.update()
    dlg = _open_dlg(app)
    assert dlg is not None
    _pick_and_invoke(dlg, "测试群")
    app.root.update()
    assert not app.core.files.sent   # 群目标无文件传输 → 文本引用
    assert len(app.core.chats) == 1
    text, sticker, ch, to, fwd = app.core.chats[0]
    assert ch == "group" and to == 10 and not sticker
    assert text == f"[图片] {img.name}"
    assert fwd and fwd["nick"] == "乙" and fwd["text"] == text


def test_forward_pick_missing_file_falls_back_text(app, tmp_path):
    missing = tmp_path / "gone.png"   # 文件不存在
    snap = app._fwd_snapshot(_img_row(missing))
    assert snap["image_path"] == str(missing)
    app._forward_pick([snap])
    app.root.update()
    dlg = _open_dlg(app)
    assert dlg is not None
    _pick_and_invoke(dlg, "乙")
    app.root.update()
    assert not app.core.files.sent    # 源文件缺失 → 不发空文件
    assert app.core.chats and app.core.chats[0][3] == 2


def test_forward_pick_text_snapshot(app, tmp_path):
    snap = {"nick": "乙", "seq": 5, "text": "原文", "ts": time.time()}
    app._forward_pick([snap])
    app.root.update()
    dlg = _open_dlg(app)
    _pick_and_invoke(dlg, "公共频道")
    app.root.update()
    text, sticker, ch, to, fwd = app.core.chats[0]
    assert text == "原文" and ch == "public" and to is None
    assert fwd["seq"] == 5


# ---------- 合并转发 ----------

def test_merge_forward_filters_img_rows(app, tmp_path, monkeypatch):
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    app.msg_list._rows = [
        _img_row(img),
        {"uid": 1, "nick": "甲", "seq": 5, "text": "t"},
    ]
    app.msg_list._sel = {0, 1}
    captured = {}
    monkeypatch.setattr(app, "_forward_pick",
                        lambda fwd, merged=False: captured.update(
                            n=len(fwd), merged=merged))
    app._merge_forward()
    assert captured.get("n") == 1 and captured.get("merged") is True


def test_merge_forward_all_image_rejected(app, tmp_path, monkeypatch):
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    app.msg_list._rows = [_img_row(img)]
    app.msg_list._sel = {0}
    sys_msgs = []
    app._append_sys = sys_msgs.append
    captured = {}
    monkeypatch.setattr(app, "_forward_pick",
                        lambda fwd, merged=False: captured.update(fwd))
    app._merge_forward()
    assert not captured
    assert any("可合并转发" in m for m in sys_msgs)
