# -*- coding: utf-8 -*-
"""test_r64_paste_snip.py —— R64「Ctrl+V 粘贴图片/文件 + Alt+A 区域截图即发」。

覆盖：
- _clipboard_paths_and_image：位图 → 临时 PNG / 文件列表 → 真实路径过滤 /
  纯文本 → ([], None)（放行默认粘贴）
- _save_image_temp：落盘可读回
- _on_paste_clipboard：命中图片才拦截（return "break"），文本放行（None）；
  非私聊给出系统提示且不发送；粘贴走 confirm=False 免二次确认
- _start_snip：非私聊拒绝；重复触发防重入
- SnipOverlay：框选回调出图、Esc/极小选区 → on_done(None)
- 接线断言：entry 绑 <<Paste>>、Alt+A 热键注册参数
"""
import os
from types import MethodType, SimpleNamespace

import pytest

from client import (_clipboard_paths_and_image, _save_image_temp,
                    ChatWindow)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def root():
    import tkinter as tk
    try:
        r = tk.Tk()
    except tk.TclError as exc:          # 无显示环境（headless CI）跳过
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


# ---------- 剪贴板读取 ----------

def test_save_image_temp_roundtrip(tmp_path):
    from PIL import Image
    img = Image.new("RGB", (12, 8), (200, 30, 40))
    p = _save_image_temp(img)
    assert p and os.path.isfile(p)
    with Image.open(p) as back:
        assert back.size == (12, 8)


def test_clipboard_bitmap_to_png(monkeypatch):
    from PIL import Image
    monkeypatch.setattr("PIL.ImageGrab.grabclipboard",
                        lambda: Image.new("RGB", (6, 6), (1, 2, 3)))
    paths, img = _clipboard_paths_and_image()
    assert img is not None
    assert len(paths) == 1 and os.path.isfile(paths[0])
    assert paths[0].lower().endswith(".png")


def test_clipboard_filelist_filters_missing(monkeypatch, tmp_path):
    real = tmp_path / "a.txt"
    real.write_text("x", encoding="utf-8")
    monkeypatch.setattr("PIL.ImageGrab.grabclipboard",
                        lambda: [str(real), str(tmp_path / "nope.txt"), 42])
    paths, img = _clipboard_paths_and_image()
    assert paths == [str(real)]
    assert img is None


def test_clipboard_text_returns_empty(monkeypatch):
    monkeypatch.setattr("PIL.ImageGrab.grabclipboard", lambda: None)
    assert _clipboard_paths_and_image() == ([], None)


def test_clipboard_error_silent(monkeypatch):
    def _boom():
        raise RuntimeError("clipboard busy")
    monkeypatch.setattr("PIL.ImageGrab.grabclipboard", _boom)
    assert _clipboard_paths_and_image() == ([], None)


# ---------- 粘贴入口 ----------

def _paste_host(view):
    sent = []
    sys_lines = []
    host = SimpleNamespace(
        view=view,
        _append_sys=lambda t: sys_lines.append(t),
        _on_drop_files=lambda ps, **kw: sent.append((list(ps), kw)),
    )
    return host, sent, sys_lines


def _call_paste(host, monkeypatch, paths, img=None):
    from client import ChatWindow
    monkeypatch.setattr("client._clipboard_paths_and_image",
                        lambda: (list(paths), img))
    fn = MethodType(ChatWindow._on_paste_clipboard, host)
    return fn()


def test_paste_text_passes_through(monkeypatch):
    host, sent, sys_lines = _paste_host(("private", 2))
    r = _call_paste(host, monkeypatch, [])
    assert r is None                       # 放行 Tk 默认文本粘贴
    assert sent == [] and sys_lines == []


def test_paste_files_sends_without_confirm(monkeypatch, tmp_path):
    f = tmp_path / "pic.png"
    f.write_bytes(b"\x89PNG")
    host, sent, _ = _paste_host(("private", 2))
    r = _call_paste(host, monkeypatch, [str(f)])
    assert r == "break"
    assert len(sent) == 1
    assert sent[0][0] == [str(f)]
    assert sent[0][1] == {"confirm": False}


def test_paste_non_private_refused(monkeypatch, tmp_path):
    f = tmp_path / "pic.png"
    f.write_bytes(b"\x89PNG")
    host, sent, sys_lines = _paste_host(("public", None))
    r = _call_paste(host, monkeypatch, [str(f)])
    assert r == "break"                    # 仍拦截，避免把二进制塞进输入框
    assert sent == []
    assert any("仅限私聊" in t for t in sys_lines)


# ---------- 截图入口 ----------

def test_snip_non_private_refused():
    sys_lines = []
    host = SimpleNamespace(view=("group", 9), _snip=None,
                           _append_sys=lambda t: sys_lines.append(t))
    ChatWindow._start_snip(host)
    assert host._snip is None
    assert any("仅限私聊" in t for t in sys_lines)


def test_snip_reentrant_guard():
    sentinel = object()
    nostr = SimpleNamespace(view=("private", 2), _snip=sentinel,
                            _append_sys=lambda t: None)
    ChatWindow._start_snip(nostr)          # 已有选框 → 直接返回，不抛错
    assert nostr._snip is sentinel


# ---------- SnipOverlay ----------

def _ev(x, y):
    return SimpleNamespace(x=x, y=y)


def test_snip_overlay_returns_image(root, monkeypatch):
    from PIL import Image
    from widgets.snip import SnipOverlay
    got = []
    ov = SnipOverlay(root, on_done=got.append)
    monkeypatch.setattr("PIL.ImageGrab.grab",
                        lambda bbox=None, **kw: Image.new("RGB", (10, 10)))
    ov._press(_ev(20, 20))
    ov._drag(_ev(60, 50))
    ov._release(_ev(60, 50))
    assert len(got) == 1 and got[0] is not None


def test_snip_overlay_tiny_selection_cancels(root):
    from widgets.snip import SnipOverlay
    got = []
    ov = SnipOverlay(root, on_done=got.append)
    ov._press(_ev(5, 5))
    ov._release(_ev(6, 6))                 # < 4px 视为误点
    assert got == [None]


def test_snip_overlay_escape_cancels(root):
    from widgets.snip import SnipOverlay
    got = []
    ov = SnipOverlay(root, on_done=got.append)
    ov._finish(None)
    ov._finish(None)                       # 幂等：只回调一次
    assert got == [None]


# ---------- 接线 ----------

def test_wiring_bindings_and_hotkey():
    with open(os.path.join(ROOT_DIR, "client.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert 'self.entry.bind("<<Paste>>", self._on_paste_clipboard)' in src
    assert "HotkeyManager(mods=MOD_ALT, vk=0x41" in src
    assert "self._shot_hotkey.q.get_nowait()" in src
    assert "self._shot_hotkey.stop()" in src


def test_hotkey_desc_customizable():
    from hotkey import HotkeyManager, MOD_ALT
    assert HotkeyManager().desc == "Ctrl+Alt+H"
    assert HotkeyManager(mods=MOD_ALT, vk=0x41,
                         desc_text="Alt+A").desc == "Alt+A"