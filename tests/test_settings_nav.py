# -*- coding: utf-8 -*-
"""test_settings_nav.py —— 设置面板左侧分类导航渲染回归。

用户反馈：设置面板左侧导航区域空白，仅底部"摸鱼助手"可见。
若页面构造中途抛异常，_show 会在 _nav_redraw() 之前中断 →
导航 Canvas 全部空白且右侧页面保持半成品 → 与本用例断言目标一致。
"""
import socket
import threading
import time

import pytest

from config import CFG
from crypto import client_handshake
from server import Hub, serve as serve_tcp
from client_core import ClientCore
from client import ChatWindow


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def app():
    import tkinter as tk
    try:
        tk.Tk()
    except tk.TclError as exc:          # 无显示环境（headless CI）跳过
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    port = _free_port()
    hub = Hub(cfg=CFG)
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                     daemon=True).start()
    time.sleep(0.1)
    core = ClientCore(host="127.0.0.1", port=port, nick="导航测试")
    window = ChatWindow(core)
    core.start()
    deadline = time.time() + 8
    while not core.connected and time.time() < deadline:
        window.root.update()
        time.sleep(0.03)
    yield window
    try:
        window.quit_app()
    except Exception:
        pass
    stop.set()


def _pump(app, secs=0.3):
    t = time.time() + secs
    while time.time() < t:
        app.root.update()
        time.sleep(0.02)


def test_settings_nav_rows_render(app):
    """打开设置面板，左侧导航 5 个分类行各应有 1 个 text item。"""
    app._on_settings()
    _pump(app)

    sw = app._settings_win
    assert sw is not None and sw.winfo_exists()

    nav = None
    for ch in sw.winfo_children():
        for ch2 in ch.winfo_children():
            if ch2.winfo_class() == "Frame":
                try:
                    if ch2.pack_info().get("side") == "left":
                        nav = ch2
                        break
                except Exception:
                    pass
            if nav is not None:
                break
        if nav is not None:
            break
    assert nav is not None, "未找到左侧导航 Frame"

    canvases = [c for c in nav.winfo_children() if c.winfo_class() == "Canvas"]
    assert len(canvases) == 5, f"导航应渲染 5 个分类行，实际 {len(canvases)}"

    labels = []
    for cv in canvases:
        items = cv.find_all()
        texts = [cv.itemcget(it, "text") for it in items if cv.type(it) == "text"]
        labels.append(texts[0] if texts else None)
    assert labels == ["通用", "外观", "隐私", "账号", "服务器"], labels

    # 当前页（通用）应有高亮底色项
    active = canvases[0]
    filled = [i for i in active.find_all()
              if active.type(i) == "polygon"]
    assert filled, "当前分类行应有高亮底色"

    # 点击「外观」→ 右侧切换到外观页
    app._settings_page  # noqa: B018  (attr 存在即可)
    canvases[1].event_generate("<Button-1>")
    _pump(app)
    assert app._settings_page == "外观"
    # 切换后仍保持 5 行文字
    labels2 = []
    for cv in canvases:
        texts = [cv.itemcget(it, "text") for it in cv.find_all()
                 if cv.type(it) == "text"]
        labels2.append(texts[0] if texts else None)
    assert labels2 == ["通用", "外观", "隐私", "账号", "服务器"], labels2
