"""UX-TRIAL regressions; synthetic state and real Tk layout, no user data."""
import queue
import time
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("upload", [False, True])
def test_fresh_fish_state_and_lifecycle_keep_polling(upload, monkeypatch):
    import client
    monkeypatch.setattr(client, "CFG", SimpleNamespace(global_hotkeys_enabled=False, discovery_enabled=False))
    app = object.__new__(client.ChatWindow)
    after, handled, scores = [], [], []
    app.root = SimpleNamespace(after=lambda delay, cb: after.append((delay, cb)))
    app.core = SimpleNamespace(events=queue.Queue(), game_state=None, game_room=None,
                               send_fish_score=lambda *args: scores.append(args))
    app._closed = app._list_dirty = app._draft_dirty = False
    app._disco_ticks = app._typing_ticks = app._draft_ticks = 0
    app._fish_upload = upload
    app._fish_add = lambda **_: None
    app._handle = handled.append
    app._pump_scheduled = app._rec_tick = app._refresh_chan_label = lambda: None
    # New profile, active round, ended round, reset, rejoin/reconnect, leave.
    for phase in (None, "playing", "ended", "created", "playing", None):
        app.core.game_room = {"game": "connect4"} if phase else None
        app.core.game_state = {"phase": phase} if phase else None
        app.core.events.put({"t": "chat", "text": str(phase)})
        app._poll()
    assert len(handled) == 6 and len(after) == 6
    assert scores == ([("connect4", 1)] if upload else [])


def test_poll_exception_remains_visible_and_does_not_cancel_next_tick():
    from client import ChatWindow
    app = object.__new__(ChatWindow)
    after = []
    app.root = SimpleNamespace(after=lambda delay, cb: after.append(cb))
    app._closed = False
    app.core = SimpleNamespace(events=queue.Queue())
    app.core.events.put({"t": "synthetic-broken-event"})
    def broken(_):
        raise ValueError("synthetic callback failure")
    app._handle = broken
    with pytest.raises(ValueError, match="synthetic callback failure"):
        app._poll()
    assert after == [app._poll]
    app._closed = True
    after[0]()
    assert len(after) == 1


def test_lobby_rebuild_same_columns_and_resize_preserves_selection():
    import tkinter as tk
    import client
    from test_flagship_gui import _fake_game_core
    root = tk.Tk()
    gw = None
    try:
        core = _fake_game_core()
        core.game_room = core.game_state = None
        core.game_meta = {f"synthetic{i}": {"label": f"游戏{i}", "min": 2, "max": 2,
                                          "desc": "synthetic", "rules": "rules"} for i in range(24)}
        app = SimpleNamespace(root=root, core=core, _dp=client._DEFAULT_PAL,
                              _frameless=False, _skin={}, _camo_title=lambda: "UX synthetic")
        gw = client.GameWindow(app, pal=client._DEFAULT_PAL)
        root.update_idletasks()
        for width in (960, 960, 1280, 640, 960):
            gw.win.geometry(f"{width}x760")
            root.update_idletasks()
            gw._on_pick_game("synthetic12")
            canvas = gw._scroll_regions[0][0]
            canvas.yview_moveto(0.4)
            before = canvas.yview()[0]
            gw._refresh_games()
            root.update_idletasks()
            assert len(gw.game_cards) == 24
            assert gw._sel_game == "synthetic12"
            assert all(card.winfo_manager() == "grid" for card in gw.game_cards.values())
            assert abs(canvas.yview()[0] - before) < 0.05
        saved_meta = core.game_meta
        core.game_meta = {}
        gw._refresh_games()
        root.update_idletasks()
        assert gw._sel_game is None and not gw.game_cards
        assert canvas.yview()[0] == 0
        assert any("正在获取" in w.cget("text") for w in gw.game_inner.winfo_children())
        core.game_meta = saved_meta
        gw._refresh_games()
        root.update_idletasks()
        assert all(card.winfo_manager() == "grid" for card in gw.game_cards.values())
        gw.close()
        gw = client.GameWindow(app, pal=client._DEFAULT_PAL)
        deadline = time.monotonic() + 3
        while not gw.game_cards and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        root.update_idletasks()
        assert len(gw.game_cards) == 24
        assert all(card.winfo_manager() == "grid" for card in gw.game_cards.values())
    finally:
        if gw is not None:
            gw.close()
        root.destroy()


def _lobby_app(root):
    """构造真实 GameWindow 所需的最小 app 替身（与上面同一套 synthetic core）。"""
    import client
    from test_flagship_gui import _fake_game_core
    core = _fake_game_core()
    core.game_room = core.game_state = None
    core.game_meta = {}
    return SimpleNamespace(root=root, core=core, _dp=client._DEFAULT_PAL,
                           _frameless=False, _skin={},
                           _camo_title=lambda: "UX synthetic")


def test_lobby_leaves_room_list_the_leftover_height():
    """大厅左栏：桌游区锁定 2 行高，剩余纵向空间全部归房间列表。

    回归点：原来桌游区与房间列表都 expand，默认窗下房间列表被挤成一条缝，
    新刷出的房间要手动放大窗口才点得到。
    """
    import tkinter as tk
    import client
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    gw = None
    try:
        app = _lobby_app(root)
        gw = client.GameWindow(app, pal=client._DEFAULT_PAL)
        gw.win.geometry("1000x720")
        gw.win.deiconify()                          # 未映射的控件 winfo_height 恒为 1
        root.update()
        root.update_idletasks()
        game_canvas = gw._scroll_regions[0][0]      # 桌游卡网格
        room_canvas = gw._scroll_regions[1][0]      # 房间列表
        gh, rh = game_canvas.winfo_height(), room_canvas.winfo_height()
        assert gh <= gw._game_zone_h + 6, f"桌游区不应再被拉高：{gh}"
        assert rh >= 150, f"房间列表应吃掉剩余空间：{rh}"
    finally:
        if gw is not None:
            gw.close()
        root.destroy()


def test_tile_drag_does_not_move_the_window():
    """画布拖拽不应带走整窗：窗口拖动只绑在标题栏，Toplevel 本身不绑。

    回归点：_make_draggable(Toplevel) 会经 bindtags 传播，画布上的花砖拖拽
    被当成窗口拖动，拖砖时整窗跟着指针跑。
    """
    import tkinter as tk
    import client
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    gw = None
    try:
        app = _lobby_app(root)
        gw = client.GameWindow(app, pal=client._DEFAULT_PAL)
        root.update_idletasks()
        assert "<Button-1>" not in gw.win.bind(), "Toplevel 不应绑窗口拖动"
        assert "<Button-1>" in gw._plain_bar.bind(), "标题栏应保留拖动整窗"
        assert "<B1-Motion>" in gw.game_cv.bind(), "画布应保留游戏拖拽交互"
    finally:
        if gw is not None:
            gw.close()
        root.destroy()


def test_title_bar_double_click_toggles_maximize():
    """双击标题栏任意处（含居中的标题文字）→ 最大化/还原。
    """
    import tkinter as tk
    import client
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    gw = None
    try:
        app = _lobby_app(root)
        gw = client.GameWindow(app, pal=client._DEFAULT_PAL)
        gw._build_apple_bar(gw.win)                 # frameless 路径：自绘红绿灯标题栏
        root.update_idletasks()
        bar = gw._apple_bar
        assert "<Double-Button-1>" in bar.bind()
        titles = [w for w in bar.winfo_children()
                  if isinstance(w, tk.Label) and "桌游" in str(w.cget("text"))]
        assert titles, "标题栏缺少居中标题"
        assert all("<Double-Button-1>" in w.bind() for w in titles), \
            "居中标题未绑双击 → 双击标题文字无反应"
        gw._bar_max()
        assert gw._bar_maxed is True
        gw._bar_max()
        assert gw._bar_maxed is False
    finally:
        if gw is not None:
            gw.close()
        root.destroy()
