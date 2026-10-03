# -*- coding: utf-8 -*-
"""R41 P0 体验补全回归：语音录制去 ffmpeg / 深色模式跟随系统。

- R41A 语音：client 录音链路改用 voice_api.MicRecorder（winmm waveIn 直录
  8kHz/16bit/单声道），无设备/启动失败明确提示；_stop_record 收尾发 WAV
  （RIFF 头 + 8000Hz 采样率字段）；取消不发。
- R41D 深色跟随：theme.system_prefers_dark 读注册表 AppsUseLightTheme
  （1=浅色/0=深色/缺失=None/非 nt=None）；client _resolve_system_skin 映射
  apple/apple_dark；_poll_sys_theme 在开关开启且系统深浅变化时自动换肤。
"""
import queue
import threading
import time
from types import SimpleNamespace

import pytest

import client as client_mod
import theme
from client import ChatWindow
from prefs import Prefs


# ---------- 打桩工具（不建 Tk） ----------

def _stub_app(tmp_path):
    app = ChatWindow.__new__(ChatWindow)
    app._prefs = Prefs(str(tmp_path / "prefs.json"))
    app._recorder = None
    app._rec_th = None
    app._rec_lock = threading.Lock()
    app._rec_data = bytearray()
    app._rec_start = 0.0
    app._rec_ticks = 0
    app._vrec_default_bg = "#ffffff"
    app._vrec_btn = SimpleNamespace(config=lambda **kw: None)
    app._voice_bar = SimpleNamespace(pack=lambda **kw: None,
                                     pack_forget=lambda: None)
    app._rec_lbl = SimpleNamespace(config=lambda **kw: None)
    app.root = SimpleNamespace(after=lambda ms, fn: 1)
    app.core = SimpleNamespace(send_voice=lambda ch, to, wav, dur: True)
    return app


class _FakeRecorder:
    """替身采集器：start() 预置 6 帧（每帧 1600B ≈ 0.1s @8k/16bit 单声道）。"""

    def __init__(self):
        self.frames = queue.Queue()
        self.started = False
        self.stopped = False

    def start(self) -> bool:
        self.started = True
        for _ in range(6):
            self.frames.put(b"\x01\x02" * 800)
        return True

    def stop(self) -> None:
        self.stopped = True


@pytest.fixture()
def fake_voice(monkeypatch):
    import voice_api
    recs = []
    monkeypatch.setattr(voice_api, "available", lambda: True)

    def _make():
        r = _FakeRecorder()
        recs.append(r)
        return r
    monkeypatch.setattr(voice_api, "MicRecorder", _make)
    return recs


@pytest.fixture()
def root():
    """Required Tk root: initialization/package errors must fail the gate."""
    r = __import__("tkinter").Tk()
    r.withdraw()
    yield r
    try:
        r.destroy()
    except Exception:
        pass


# ================= R41A 语音录制去 ffmpeg =================

def test_toggle_record_uses_mic_recorder(fake_voice, tmp_path):
    """🎙 开始：MicRecorder.start() 被调、drain 线程搬帧入 _rec_data。"""
    app = _stub_app(tmp_path)
    app._toggle_record()
    assert app._recorder is fake_voice[0] and fake_voice[0].started
    deadline = time.time() + 2
    while len(app._rec_data) < 6 * 1600 and time.time() < deadline:
        time.sleep(0.02)
    assert len(app._rec_data) == 6 * 1600          # 6 帧全部搬入
    app._stop_record(False)                        # 取消：收尾不发
    assert fake_voice[0].stopped


def test_stop_record_sends_wav_8000hz(fake_voice, tmp_path):
    """完成并发送：8kHz WAV 合法（RIFF 头 + 采样率字段 8000），时长≈0.6s。"""
    app = _stub_app(tmp_path)
    sent = []

    def _send(ch, to, wav, dur):
        sent.append((ch, to, wav, dur))
        return True
    app.core = SimpleNamespace(send_voice=_send)
    app.view = ("private", 7)
    app._toggle_record()
    deadline = time.time() + 2
    while len(app._rec_data) < 6 * 1600 and time.time() < deadline:
        time.sleep(0.02)
    app._stop_record(True)
    assert len(sent) == 1
    ch, to, wav, dur = sent[0]
    assert (ch, to) == ("private", 7)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    rate = int.from_bytes(wav[24:28], "little")
    assert rate == 8000                            # R41A：与 voice_api 对齐
    assert dur >= 0.5


def test_toggle_record_no_device(monkeypatch, tmp_path):
    """无输入设备：toast 提示且不建录音器。"""
    import voice_api
    app = _stub_app(tmp_path)
    tips = []
    monkeypatch.setattr(voice_api, "available", lambda: False)
    # R55：信息提示走轻量 toast（不再弹 messagebox.showinfo）
    app.show_toast = lambda msg, duration=2600, warn=False: tips.append(msg)
    app._toggle_record()
    assert app._recorder is None and len(tips) == 1


def test_toggle_record_start_failure(monkeypatch, tmp_path):
    """start() 失败（设备被占用）：toast 提示且不进入录音态。"""
    import voice_api
    app = _stub_app(tmp_path)

    class _Bad:
        def __init__(self):
            self.frames = queue.Queue()

        def start(self):
            return False
    monkeypatch.setattr(voice_api, "available", lambda: True)
    monkeypatch.setattr(voice_api, "MicRecorder", _Bad)
    tips = []
    app.show_toast = lambda msg, duration=2600, warn=False: tips.append(msg)
    app._toggle_record()
    assert app._recorder is None and len(tips) == 1


def test_stop_record_too_short_silent(monkeypatch, tmp_path):
    """录音过短（<0.5s）：不发、走 toast 提示路径（无竞态：直接注入短数据）。"""
    app = _stub_app(tmp_path)
    tips = []
    sent = []
    app.core = SimpleNamespace(send_voice=lambda *a: sent.append(a) or True)
    app.show_toast = lambda msg, duration=2600, warn=False: tips.append(msg)
    app._rec_data = bytearray(b"\x00\x00" * 100)   # 200B ≈ 0.0s
    app._stop_record(True)
    assert not sent and len(tips) == 1


# ================= R41D 深色模式跟随系统 =================

def test_system_prefers_dark_registry(monkeypatch):
    """注册表 AppsUseLightTheme：1→False，0→True，缺失→None。"""
    import winreg

    class _K:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(winreg, "OpenKey", lambda *a, **k: _K())
    monkeypatch.setattr(winreg, "QueryValueEx",
                        lambda k, n: (1, winreg.REG_DWORD))
    assert theme.system_prefers_dark() is False
    monkeypatch.setattr(winreg, "QueryValueEx",
                        lambda k, n: (0, winreg.REG_DWORD))
    assert theme.system_prefers_dark() is True

    def _raise(k, n):
        raise FileNotFoundError(n)
    monkeypatch.setattr(winreg, "QueryValueEx", _raise)
    assert theme.system_prefers_dark() is None


def test_system_prefers_dark_non_windows(monkeypatch):
    """非 Windows → None（os.name 打桩，结束后自动还原）。"""
    monkeypatch.setattr(theme.os, "name", "posix")
    assert theme.system_prefers_dark() is None


def test_resolve_system_skin_mapping(tmp_path, monkeypatch):
    """系统深浅 → apple_dark / apple 映射；None 视为浅色。"""
    app = _stub_app(tmp_path)
    monkeypatch.setattr(theme, "system_prefers_dark", lambda: True)
    assert app._resolve_system_skin() == "apple_dark"
    monkeypatch.setattr(theme, "system_prefers_dark", lambda: False)
    assert app._resolve_system_skin() == "apple"
    monkeypatch.setattr(theme, "system_prefers_dark", lambda: None)
    assert app._resolve_system_skin() == "apple"


def test_poll_sys_theme_switches_on_change(tmp_path, monkeypatch):
    """开关开启：系统由浅转深 → 自动 _on_skin_change(apple_dark)。"""
    app = _stub_app(tmp_path)
    app._prefs.set("skin_follow_system", True)
    app._skin_name = "apple"
    switched = []
    app._on_skin_change = lambda name: switched.append(name)
    monkeypatch.setattr(theme, "system_prefers_dark", lambda: True)
    app._poll_sys_theme()
    assert switched == ["apple_dark"]


def test_poll_sys_theme_noop_when_off_or_same(tmp_path, monkeypatch):
    """开关关闭或深浅未变：不换肤。"""
    app = _stub_app(tmp_path)
    app._skin_name = "apple"
    switched = []
    app._on_skin_change = lambda name: switched.append(name)
    monkeypatch.setattr(theme, "system_prefers_dark", lambda: True)
    app._poll_sys_theme()                          # 开关关 → 不动
    assert switched == []
    app._prefs.set("skin_follow_system", True)
    monkeypatch.setattr(theme, "system_prefers_dark", lambda: False)
    app._poll_sys_theme()                          # 已是浅色 → 不动
    assert switched == []


def test_startup_resolves_skin_when_follow_on(tmp_path, monkeypatch):
    """启动装载：prefs['skin_follow_system']=True 时按系统态解析皮肤。"""
    from theme import SYSTEM_DARK_SKIN
    app = ChatWindow.__new__(ChatWindow)
    app._prefs = Prefs(str(tmp_path / "prefs.json"))
    app._prefs.set("skin_follow_system", True)
    monkeypatch.setattr(theme, "system_prefers_dark", lambda: True)
    # 模拟 __init__ 中的解析段（不建 GUI）
    app._skin_name = app._prefs.get("skin", theme.DEFAULT_SKIN)
    if app._prefs.get("skin_follow_system"):
        app._skin_name = app._resolve_system_skin()
    assert app._skin_name == SYSTEM_DARK_SKIN


# ================= R41E 引用/空消息拦截状态机 =================

class _StubEntry:
    """替身输入框：行级 get/insert/delete 模型，够 _quote/_send/_begin_edit 用。"""

    def __init__(self, text=""):
        self.lines = text.split("\n") if text else [""]
        self.cleared = 0

    def get(self, a, b=None):
        if a == "1.0" and b == "1.end":
            return self.lines[0] if self.lines else ""
        return "\n".join(self.lines)

    def delete(self, a, b=None):
        if a == "1.0" and b == "2.0":          # R41F 连续引用：删旧引用标记行
            self.lines = self.lines[1:] or [""]
        else:                                   # ("1.0", "end") 全清
            self.lines = [""]
            self.cleared += 1

    def insert(self, index, text_):
        pieces = text_.split("\n")
        head = self.lines[0] if self.lines else ""
        self.lines = pieces[:-1] + [pieces[-1] + head] + self.lines[1:]

    def mark_set(self, *a):                     # Tk Text 接口占位
        pass

    def focus_set(self):
        pass


def _stub_sender(tmp_path, entry_text=""):
    """打桩 _send 依赖：entry/view/core/草稿与历史钩子。"""
    from types import SimpleNamespace as NS
    app = ChatWindow.__new__(ChatWindow)
    app._prefs = Prefs(str(tmp_path / "prefs.json"))
    app.entry = _StubEntry(entry_text)
    app._entry_text = lambda: app.entry.get("1.0", "end-1c")  # 与 stub 行模型联动
    app.view = ("public", None)
    app._pending_reply = None
    app._pending_edit_seq = None
    app._burn_mode = False
    app._silent_mode = False
    app._disguise_mode = ""                     # R70E：消息伪装风格（桩需初始化）
    app._last_send = 0.0
    app._sys = []
    sent = []
    app.core = NS(uid=2,
                  send_chat=lambda text, **kw: (sent.append((text, kw)) or True),
                  send_edit=lambda seq, text, **kw: (sent.append(("edit", seq, text)) or True))
    app.msg_list = NS(append=lambda raw: None,            # P0 三态：发送成功 → 本地「发送中」行
                      drop_local_row=lambda raw: False,
                      redraw_all=lambda: None)
    app.root = NS(after=lambda ms, cb: None)
    app._pending_rows = []                                # P0 三态：发送中行队列
    app._record_send = lambda text: None
    app._clear_draft = lambda key: None
    app._pin_key = lambda ch, to: f"{ch}:{to}"
    app._append_sys = lambda msg: app._sys.append(msg)
    return app, sent


def test_send_empty_with_reply_cancels_quote(tmp_path):
    """空文本 + 挂起引用：本地取消引用、清输入框、不发送（R41E 提前拦截）。"""
    app, sent = _stub_sender(tmp_path, entry_text="↩ 甲: 原文\n")
    app._pending_reply = {"nick": "甲", "text": "原文", "seq": 12}
    app._send()
    assert sent == [] and app._pending_reply is None
    assert app.entry.cleared == 1
    assert any("已取消引用" in m for m in app._sys)


def test_send_swallows_reply_after_one_use(tmp_path):
    """带正文发送：reply 快照只随本条走，发送后复位（不泄漏到下一发）。"""
    app, sent = _stub_sender(tmp_path, entry_text="↩ 甲: 原文\n正文")
    app._pending_reply = {"nick": "甲", "text": "原文", "seq": 12}
    app._send()                                  # 第 1 条：带引用
    assert len(sent) == 1
    text, kw = sent[0]
    assert text == "正文" and kw.get("reply", {}).get("seq") == 12
    assert app._pending_reply is None
    app._entry_text = lambda: "正文二"            # 第 2 条：无引用
    app._send()
    text2, kw2 = sent[1]
    assert text2 == "正文二" and kw2.get("reply") is None


def test_begin_edit_drops_pending_reply(tmp_path):
    """引用挂起时进入编辑：引用态被丢弃（不会漏到编辑后的新消息）。"""
    app, _ = _stub_sender(tmp_path)
    app._pending_reply = {"nick": "甲", "text": "x", "seq": 1}
    app.entry.delete = lambda *a: None           # _begin_edit 会 delete+insert
    app.entry.insert = lambda *a: None
    app.entry.focus_set = lambda: None
    ChatWindow._begin_edit(app, {"seq": 7, "text": "原文"})
    assert app._pending_edit_seq == 7
    assert app._pending_reply is None


def test_edit_send_does_not_leak_reply(tmp_path):
    """编辑中误引用另一条 → Enter 发编辑：编辑内容正确、引用态清空。"""
    app, sent = _stub_sender(tmp_path, entry_text="↩ 乙: hi\n改后内容")
    app._pending_edit_seq = 5
    app._pending_reply = {"nick": "乙", "text": "hi", "seq": 2}
    app._send()
    assert sent == [("edit", 5, "改后内容")]      # ↩ 行被剥离，编辑正文正确
    assert app._pending_reply is None            # 引用态不泄漏到下一发


# ================= R41F 引用跳转 + 标记行卫生 =================

def test_send_strips_only_first_line(tmp_path):
    """正文里以「↩ 」开头的行不再被误删（只剥首行引用标记）。"""
    app, sent = _stub_sender(
        tmp_path, entry_text="↩ 甲: hi\n↩ 正文首行\n尾行")
    app._send()
    text, kw = sent[0]
    assert text == "↩ 正文首行\n尾行"             # 正文 ↩ 行保留
    assert kw.get("reply") is None               # 无引用挂起 → 纯文本消息


def test_quote_blocked_while_editing(tmp_path):
    """编辑中引用：拦截 + 提示，不进引用态、不污染编辑框。"""
    from types import SimpleNamespace as NS
    app, _ = _stub_sender(tmp_path)
    app._pending_edit_seq = 9
    app.msg_list = NS(get_row=lambda i: {"seq": 3, "nick": "甲", "text": "x"},
                      body_text=lambda i: "x")
    app._quote(0)
    assert app._pending_reply is None            # 不进入引用态
    assert app.entry.lines == [""]               # 编辑框未被插入 ↩ 行
    assert any("编辑中" in m for m in app._sys)


def test_quote_replaces_old_marker_line(tmp_path):
    """连续引用：旧 ↩ 标记行被移除，只保留最新一条（不再叠两行）。"""
    from types import SimpleNamespace as NS
    app, _ = _stub_sender(tmp_path)
    app.msg_list = NS(
        get_row=lambda i: ({"seq": 1, "nick": "甲", "text": "first"}
                           if i == 0 else {"seq": 2, "nick": "乙", "text": "second"}),
        body_text=lambda i: "first" if i == 0 else "second")
    app._quote(0)
    assert app.entry.lines[0] == "↩ 甲: first"
    assert app._pending_reply["seq"] == 1
    app._quote(1)                                # 第二次引用
    assert app.entry.lines[0] == "↩ 乙: second"  # 旧行被替换
    assert len([ln for ln in app.entry.lines if ln.startswith("↩ ")]) == 1
    assert app._pending_reply["seq"] == 2


def test_row_reply_prefix_fields():
    """_Row：引用前缀/被引用 seq 字段生成，body 前缀可剥离还原。"""
    from widgets.msg_list import _Row
    r = _Row({"seq": 20, "nick": "乙", "text": "回复内容",
              "reply": {"nick": "甲", "text": "原文文本", "seq": 5}})
    assert r.reply_seq == 5
    assert r.reply_prefix == "↩ 甲: 原文文本 | "
    assert r.body.startswith(r.reply_prefix)
    assert r.body[len(r.reply_prefix):] == "回复内容"
    r2 = _Row({"seq": 21, "nick": "乙", "text": "",           # 无正文纯引用
               "reply": {"nick": "甲", "text": "原文", "seq": 6}})
    assert r2.reply_prefix == "↩ 甲: 原文"
    assert r2.body == r2.reply_prefix


def test_jump_to_seq_highlight(root):
    """jump_to_seq：命中返回 True 并置高亮行；未命中返回 False；到期消退。"""
    from widgets.msg_list import MsgList
    ml = MsgList(root, ("Microsoft YaHei UI", 9))
    for i in range(30):
        ml.append({"seq": i + 1, "nick": f"u{i}", "text": f"msg {i}"})
    assert ml.jump_to_seq(5) is True
    assert ml._jump_hi == 4                      # 第 5 条 → 下标 4
    assert ml.jump_to_seq(9999) is False         # 不存在的 seq
    ml._clear_jump_hi()
    assert ml._jump_hi == -1
    assert ml.jump_to_seq(None) is False         # 无 seq（旧消息）安全


def test_reply_row_renders_and_jumps(root):
    """带引用气泡渲染 smoke：REPLY 段不炸、reply_seq 取自 reply 快照。"""
    from widgets.msg_list import MsgList
    ml = MsgList(root, ("Microsoft YaHei UI", 9), on_jump_reply=lambda seq: None)
    for i in range(6):
        ml.append({"seq": i + 1, "nick": f"u{i}", "text": f"msg {i}"})
    ml.append({"seq": 7, "nick": "乙", "text": "回复内容",
               "reply": {"nick": "u4", "text": "msg 4", "seq": 5}})
    ml._render()                                 # 强制同步渲染（含 REPLY 分支）
    assert ml._rows[-1].reply_seq == 5
    assert ml.jump_to_seq(5) is True             # 点前缀 → 命中原消息
    root.update()                                # 跑一遍事件循环清 after

