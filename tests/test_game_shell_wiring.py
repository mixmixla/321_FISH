# -*- coding: utf-8 -*-
"""Task 5 回归：桌游窗标题栏必须读注入的 pal（game_shell_pal），
不得直读全局/app 皮肤。

断言（不变式）：
- 苹果风标题栏底色取注入 pal 的 ``win``（而非 fake skin 的 ``#123456``）；
- 高度取 ``theme.BASE["titlebar_h"]``（=28，而非 fake skin 的 99）。
"""

from types import SimpleNamespace

import pytest

import client as client_module
import theme


class _FakeCore:
    """GameWindow.__init__ 只需 ``game_list()``；其余属性留给占位。"""

    uid = 7
    connected = False
    roster = {}
    game_rooms = []
    game_meta = {}
    game_private = None
    game_events = []

    def game_list(self):
        return True


def _fake_app(root):
    """最小可构造 GameWindow 的 app 替身；皮肤 token 故意与注入 pal 不同，
    以便复用真实构建路径并暴露「直读皮肤」的回归。"""
    return SimpleNamespace(
        root=root, core=_FakeCore(),
        _dp=client_module._DEFAULT_PAL,
        _frameless=False,
        _skin={"titlebar_bg": "#123456", "titlebar_h": 99,
               "panel_bg": "#ffffff", "fg": "#000000", "sub": "#666666"},
        _camo_title=lambda: "synthetic",
    )


def test_apple_bar_uses_injected_pal():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        root.withdraw()
        app = _fake_app(root)
        pal = theme.game_shell_pal(theme.get_skin("mist"))
        win = client_module.GameWindow(app, pal=pal)
        # 显式触发苹果风标题栏构建（frameless 路径），再读回真实控件。
        win._build_apple_bar(win.win)
        bar = win._apple_bar
        assert bar["bg"].upper() == pal["win"].upper()
        assert int(bar["height"]) == int(theme.BASE["titlebar_h"])
    finally:
        try:
            root.destroy()
        except Exception:
            pass
