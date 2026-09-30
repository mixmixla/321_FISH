# -*- coding: utf-8 -*-
"""tkguard.py —— Tk 对象跨线程销毁守卫（修复 Tcl_AsyncDelete 抖动崩溃）。

根因（诊断阶段已在崩溃现场实证）：
CPython 的 GC 可在任意线程触发；当 Font/PhotoImage/Variable 等 Tk 对象
被引用环连带回收时，其 __del__ 会在触发 GC 的那个线程执行：
- tkinter.font.Font.__del__   → `font delete`
- tkinter.Image.__del__       → `image delete`（PhotoImage/BitmapImage 继承）
- tkinter.Variable.__del__    → `globalunsetvar`
后台线程（如 server 的 TCP 处理线程）碰 Tcl 解释器 → 跨线程调用 →
Tcl_AsyncDelete: async handler deleted by the wrong thread 崩溃。

修复（两道防线）：
1. `__del__` 线程守卫——Font/Image/Variable 仅在主线程执行真正的 Tcl 删除；
   非主线程只释放 Python 对象（Tcl 侧名字随解释器销毁一并释放，泄漏可忽略）。
2. Tkapp 常驻注册表——Tk 解释器（C 对象）一旦创建即永久持有，杜绝整棵
   widget 树被后台线程 GC 连带回收（否则 Tcl_DeleteInterp 在错误线程执行）。

client.py 与 tests/conftest.py 须在任何 Tk/Font 创建之前 import 本模块。
"""
import threading
import tkinter as _tk
import tkinter.font as _tkfont

_PATCHED = False

# Tkapp 常驻注册表：Tk 解释器（C 对象）一旦创建即由 Python 侧永久持有。
# 这样 Tkapp 与其内部 {Tcl名: widget} 表引用的整棵 widget 树永远可达，
# 不会被后台线程的 GC 连带回收——否则 `Tcl_DeleteInterp` 会在错误线程
# 执行（Tcl_AsyncDelete: async handler deleted by the wrong thread）。
# 生产进程只有一个 root，等于无泄漏；测试进程的解释器随进程退出释放。
_TKAPP_REGISTRY = []


def _thread_safe_del(orig):
    def safe(self):
        if threading.current_thread() is threading.main_thread():
            orig(self)
    return safe


def _keep_tkapp(self, *a, **k):
    _orig_tk_init(self, *a, **k)
    app = getattr(self, "tk", None)
    if app is not None and app not in _TKAPP_REGISTRY:
        _TKAPP_REGISTRY.append(app)


def _patch():
    global _PATCHED
    if _PATCHED:
        return
    for cls, attr in ((_tkfont.Font, "__del__"),
                      (_tk.Image, "__del__"),
                      (_tk.Variable, "__del__")):
        setattr(cls, attr, _thread_safe_del(getattr(cls, attr)))
    global _orig_tk_init
    _orig_tk_init = _tk.Tk.__init__
    _tk.Tk.__init__ = _keep_tkapp
    _PATCHED = True


_patch()
