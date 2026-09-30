# -*- coding: utf-8 -*-
"""R43C 高分屏适配（Windows）：进程级 DPI 感知声明 + Tk 缩放校正。

问题：未声明 DPI 感知时，>96 DPI 的显示器上 Windows 对整个窗口做位图
拉伸——文字发虚。声明后 GDI/Tk 按真实 DPI 渲染，点制字体自动清晰。

- apply_early()：必须在首个 tk.Tk() 之前调用（进程级一次性，幂等安全）。
  三级降级：SetProcessDpiAwarenessContext(SYSTEM_AWARE)
          → Shcore.SetProcessDpiAwareness(1)
          → user32.SetProcessDPIAware()。
  选 SYSTEM_AWARE 而非 PER_MONITOR_V2：Tk 8.6 不会按显示器重算字体，
  跨不同 DPI 显示器拖动时 V2 会出现两屏字号不一致；System 级主屏清晰、
  副屏表现可预期（局域网工具的常见形态）。非 Windows/异常静默。
- fix_scaling(root)：用 GetDpiForSystem/GetDeviceCaps 取真实 DPI，显式
  把 tk scaling 钉到 dpi/72（防个别环境 Tk 探测滞后），返回缩放因子
  dpi/96 供像素几何放大；非 Windows 或未声明态恒为 1.0 零影响。
"""
import os


def _system_dpi() -> float:
    """真实系统 DPI：GetDpiForSystem（Win10 1607+）→ GetDeviceCaps 兜底。"""
    try:
        import ctypes
        if os.name != "nt":
            return 96.0
        user32 = ctypes.windll.user32
        try:
            if hasattr(user32, "GetDpiForSystem"):
                d = user32.GetDpiForSystem()
                if d:
                    return float(d)
        except Exception:
            pass
        try:
            dc = user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)   # LOGPIXELSY
            user32.ReleaseDC(0, dc)
            if dpi:
                return float(dpi)
        except Exception:
            pass
    except Exception:
        pass
    return 96.0


def apply_early(enabled: bool = True) -> bool:
    """进程级声明 DPI 感知；须在首个 tk.Tk() 前调用。返回是否已声明。"""
    if not enabled or os.name != "nt":
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        if hasattr(user32, "SetProcessDpiAwarenessContext"):
            try:
                # DPI_AWARENESS_CONTEXT_SYSTEM_AWARE = (HANDLE)-3
                if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-3)):
                    return True
            except Exception:
                pass
        try:
            if ctypes.windll.shcore.SetProcessDpiAwareness(1) == 0:
                return True                                   # SYSTEM_DPI_AWARE
        except Exception:
            pass
        return bool(user32.SetProcessDPIAware())              # Vista 兜底
    except Exception:
        return False


def fix_scaling(root) -> float:
    """root 建立后校正 tk scaling；返回缩放因子（dpi/96，非 Windows=1.0）。"""
    dpi = _system_dpi()
    if os.name == "nt" and dpi > 0:
        try:
            root.tk.call("tk", "scaling", dpi / 72.0)
        except Exception:
            pass
    return dpi / 96.0 if dpi > 0 else 1.0
