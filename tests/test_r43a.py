# -*- coding: utf-8 -*-
"""R43A 动效与手感回归：弹窗淡入 / 按钮按压反馈。

- fade_in：alpha 0→1 插值收尾、目标窗口中途销毁不抛错、
  非 Toplevel/Tk 容错（无 alpha 支持的 WM 上原样显示）；
- press_feedback：raised 按钮按下凹陷/松开恢复；flat 按钮
  pressed_bg 变色还原（R43A2 带插值过渡，断言用 _pump 等动画收尾）；
  disabled 不响应；Leave 触发恢复。
"""
import time

import pytest

tk = pytest.importorskip("tkinter")

from widgets import ui_fx                                   # noqa: E402


@pytest.fixture()
def root():
    # py3.14/pyenv-win 下 Tcl 初始化偶发读库失败（auto.tcl/tk.tcl 报错漂移，
    # 同 conftest 兜底的环境问题）：有限重试，两次间隔让 notifier 线程收尾
    r = None
    for i in range(3):
        try:
            r = tk.Tk()
            break
        except tk.TclError:
            if i == 2:
                raise
            time.sleep(0.1)
    r.geometry("+0+0")                       # 需映射：event_generate 只送达已视图化窗口
    r.update()
    yield r
    r.destroy()


def _pump(r, seconds=2.0, until=None):
    """跑事件循环直至 until() 为真或超时（驱动 after 回调）。"""
    deadline = time.time() + seconds
    while time.time() < deadline:
        r.update()
        if until and until():
            return True
        time.sleep(0.01)
    return False


# ---------------- fade_in ----------------

def test_fade_in_completes(root):
    dlg = tk.Toplevel(root)
    ui_fx.fade_in(dlg, ms=60)
    assert float(dlg.attributes("-alpha")) < 1.0    # 起点已隐身
    assert _pump(root, until=lambda: float(dlg.attributes("-alpha")) >= 1.0)
    assert float(dlg.attributes("-alpha")) == 1.0
    dlg.destroy()


def test_fade_in_destroyed_window_no_raise(root):
    dlg = tk.Toplevel(root)
    dlg.destroy()
    ui_fx.fade_in(dlg, ms=30)                       # 不应抛 TclError


def test_fade_in_updates_during(root):
    """动画是渐进而非一步到位：中途 alpha 严格单调逼近 1。"""
    dlg = tk.Toplevel(root)
    ui_fx.fade_in(dlg, ms=90)
    seen_mid = False
    deadline = time.time() + 2.0
    while time.time() < deadline:
        root.update()
        a = float(dlg.attributes("-alpha"))
        if 0.0 < a < 1.0:
            seen_mid = True
            break
        time.sleep(0.005)
    assert seen_mid
    _pump(root, until=lambda: float(dlg.attributes("-alpha")) >= 1.0)
    dlg.destroy()


# ---------------- press_feedback ----------------

def test_press_feedback_raised_sunken_cycle(root):
    btn = tk.Button(root, text="B", relief="raised")
    btn.pack()
    root.update()                            # 映射后才接受合成事件
    ui_fx.press_feedback(btn)
    btn.event_generate("<ButtonPress-1>")
    root.update()
    assert str(btn["relief"]) == "sunken"
    btn.event_generate("<ButtonRelease-1>")
    root.update()
    assert str(btn["relief"]) == "raised"


def test_press_feedback_flat_bg_swap(root):
    btn = tk.Button(root, text="T", relief="flat", bd=0, bg="#101010")
    btn.pack()
    root.update()                            # 映射后才接受合成事件
    ui_fx.press_feedback(btn, pressed_bg="#ff0000")
    btn.event_generate("<ButtonPress-1>")
    root.update()
    assert str(btn["bg"]) != "#101010"       # R43A2 插值过渡：按下即开始变色
    # anim_ms=90（3 帧 × 30ms）走完 → 落到完整按下色
    assert _pump(root, until=lambda: str(btn["bg"]) == "#ff0000")
    btn.event_generate("<ButtonRelease-1>")
    root.update()
    assert _pump(root, until=lambda: str(btn["bg"]) == "#101010")


def test_press_feedback_leave_restores(root):
    btn = tk.Button(root, text="T", relief="flat", bd=0, bg="#101010")
    btn.pack()
    root.update()                            # 映射后才接受合成事件
    ui_fx.press_feedback(btn, pressed_bg="#ff0000")
    btn.event_generate("<ButtonPress-1>")
    assert _pump(root, until=lambda: str(btn["bg"]) == "#ff0000")   # 先按到位
    btn.event_generate("<Leave>")
    root.update()
    # 拖出即渐回原色，不粘住按压态
    assert _pump(root, until=lambda: str(btn["bg"]) == "#101010")


def test_press_feedback_disabled_noop(root):
    btn = tk.Button(root, text="D", relief="raised", state="disabled")
    btn.pack()
    root.update()                            # 映射后才接受合成事件
    ui_fx.press_feedback(btn, pressed_bg="#ff0000")
    btn.event_generate("<ButtonPress-1>")
    root.update()
    assert str(btn["relief"]) == "raised"           # 禁用态无任何视觉响应
    assert not hasattr(btn, "_pf_bg")
