# -*- coding: utf-8 -*-
"""widgets/dropfiles.py —— Tk toplevel 的 Windows 窗口子类化钩子。

纯标准库实现（不引 tkdnd / 第三方），规避 PyInstaller 打包冲突。
提供两个能力：
1. enable_dropfiles(root, on_files)  文件拖放发送（WM_DROPFILES）
2. enable_edge_resize(root)          无边框窗的边缘拖动缩放（WM_NCHITTEST）

共享同一份窗口子类：多个钩子链在同一个 WNDPROC 上按消息分发，互不覆盖。
任一功能失败/非 Windows 时静默返回 False，调用方自行降级。
"""
import os

GWLP_WNDPROC = -4
WM_DROPFILES = 0x0233
WM_NCHITTEST = 0x0084

EDGE = 6                 # 边缘缩放热区像素宽
HTCLIENT = 1
_HT = {"left": 10, "right": 11, "top": 12,
       "topleft": 13, "topright": 14,
       "bottom": 15, "bottomleft": 16, "bottomright": 17}

WNDPROC = None           # 惰性创建（依赖 64/32 位指针宽度）
_SESSIONS = {}           # hwnd -> {old, proc_ref, handlers: {msg: [fn]}}


def enable_dropfiles(root, on_files) -> bool:
    """对 Tk toplevel 启用文件拖放。on_files(paths[, x, y]) 主线程回调。
    x/y 为拖放落点相对 toplevel 客户区坐标（WM_DROPFILES DragQueryPoint），
    供上层把文件定向投递到命中会话行；落点在客户区外时为 None。"""
    on_files = on_files or (lambda _p, _x=None, _y=None: None)

    def _handle(h, wp, lp):
        pt = _drop_point(wp)
        px = py = None
        if pt is not None:
            px, py = pt
        paths = _query_paths(wp)
        if paths:
            root.after(0, lambda: on_files(paths, px, py))
        return 0

    return _add_hook(root, WM_DROPFILES, _handle)


def enable_edge_resize(root) -> bool:
    """对 Tk toplevel 启用边缘拖动缩放（无边框窗用）。

    三态判定：内部区域返回 HTCLIENT 交给 Tk；四边 6px 热区返回对应
    HT* 常量让系统进入原生缩放；全屏锁定时返回 None 交回默认处理。
    """
    def _handle(h, wp, lp):
        if getattr(root, "_fullscreen_lock", False):
            return None                       # 全屏时不接管
        x = wp & 0xFFFF
        y = (wp >> 16) & 0xFFFF
        try:
            w = root.winfo_width()
            ht = root.winfo_height()
        except Exception:
            return None
        if w <= 1 or ht <= 1:
            return None
        left = x < EDGE
        right = x >= w - EDGE
        top = y < EDGE
        bottom = y >= ht - EDGE
        if top and left:
            return _HT["topleft"]
        if top and right:
            return _HT["topright"]
        if bottom and left:
            return _HT["bottomleft"]
        if bottom and right:
            return _HT["bottomright"]
        if left:
            return _HT["left"]
        if right:
            return _HT["right"]
        if top:
            return _HT["top"]
        if bottom:
            return _HT["bottom"]
        return HTCLIENT

    return _add_hook(root, WM_NCHITTEST, _handle)


def _add_hook(root, msg, handler) -> bool:
    """把 handler 挂到 root 的共享子类上；首次挂载时安装 WNDPROC。"""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes as wt
        global WNDPROC

        user32 = ctypes.windll.user32
        is64 = ctypes.sizeof(ctypes.c_void_p) == 8
        GetWindowLongPtr = (user32.GetWindowLongPtrW if is64
                            else user32.GetWindowLongW)
        SetWindowLongPtr = (user32.SetWindowLongPtrW if is64
                            else user32.SetWindowLongW)
        CallWindowProc = user32.CallWindowProcW
        Proto = ctypes.c_longlong if is64 else ctypes.c_long

        if is64:
            GetWindowLongPtr.restype = ctypes.c_longlong
            GetWindowLongPtr.argtypes = [wt.HWND, ctypes.c_int]
            SetWindowLongPtr.restype = ctypes.c_longlong
            SetWindowLongPtr.argtypes = [ctypes.c_longlong, ctypes.c_int,
                                         ctypes.c_longlong]
            CallWindowProc.restype = ctypes.c_longlong
            CallWindowProc.argtypes = [ctypes.c_longlong, wt.HWND, wt.UINT,
                                       ctypes.c_size_t, ctypes.c_longlong]
        if WNDPROC is None:
            WNDPROC = ctypes.WINFUNCTYPE(Proto, wt.HWND, wt.UINT,
                                         ctypes.c_size_t, Proto)

        root.update_idletasks()
        hwnd = user32.GetParent(root.winfo_id())   # Tk 子窗 → 真 toplevel HWND
        if not hwnd:
            return False

        sess = _SESSIONS.get(hwnd)
        if sess is None:
            old_proc = GetWindowLongPtr(hwnd, GWLP_WNDPROC)

            def _proc(h, msg_, wp, lp):
                sess_ = _SESSIONS.get(h)
                if sess_ is None:
                    return CallWindowProc(old_proc, h, msg_, wp, lp)
                for fn in tuple(sess_["handlers"].get(msg_, ())):
                    r = fn(h, wp, lp)
                    if r is not None:
                        return r
                return CallWindowProc(old_proc, h, msg_, wp, lp)

            proc_ref = WNDPROC(_proc)
            SetWindowLongPtr(hwnd, GWLP_WNDPROC,
                             ctypes.cast(proc_ref, ctypes.c_void_p).value)
            sess = {"old": old_proc, "proc": proc_ref, "handlers": {}}
            _SESSIONS[hwnd] = sess
            root._dropfiles_proc = sess        # 与窗口同生命周期，防 GC

        sess["handlers"].setdefault(msg, []).append(handler)
        return True
    except Exception:
        return False


def _query_paths(hdrop):
    """WM_DROPFILES 长路径：先查所需 WCHAR 数再一次性分配，避免截断。"""
    try:
        import ctypes
        from ctypes import wintypes as wt
        shell32 = ctypes.windll.shell32
        DragQueryFileW = shell32.DragQueryFileW
        DragQueryFileW.restype = wt.UINT
        DragQueryFileW.argtypes = [wt.HANDLE, wt.UINT, wt.LPWSTR, wt.UINT]
        DragFinish = shell32.DragFinish
    except Exception:
        return []
    n = DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
    out = []
    for i in range(n):
        cch = DragQueryFileW(hdrop, i, None, 0)   # 含结尾 NUL
        buf = ctypes.create_unicode_buffer(max(cch, 1))
        DragQueryFileW(hdrop, i, buf, cch)
        out.append(buf.value)
    DragFinish(hdrop)
    return out


def _drop_point(hdrop):
    """WM_DROPFILES 落点（toplevel 客户区坐标）；在客户区外 / 失败返回 None。"""
    try:
        import ctypes
        from ctypes import wintypes as wt
        user32 = ctypes.windll.user32
        pt = (wt.LONG * 2)()
        ok = user32.DragQueryPoint(hdrop, pt)
    except Exception:
        return None
    if not ok:
        return None
    return int(pt[0]), int(pt[1])