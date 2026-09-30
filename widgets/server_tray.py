# -*- coding: utf-8 -*-
"""widgets/server_tray.py —— 服务器托盘（防误关）。

服务端是 console（server.exe），进程被 Windows 的控制台窗口独占，
用户点窗口的 ✕ 或误按关闭就会把服务器整个干掉。托盘让服务器
缩进后台常驻：菜单可「打开网页端」「隐藏/显示控制台」「退出」，
退出必须从托盘显式操作，避免误关。

要点：
- 无 Tk：pystray 用 run_detached() 在独立线程跑消息循环；
- 回调在托盘线程执行，这里不碰 Tk，直接落地即可（与 client 的 Tray 不同）；
- pystray / PIL 缺失或初始化失败 → 返回 None，服务器照常运行（静默降级）。
"""
import ctypes
import threading
import webbrowser

_ICON_TIP = "内部办公助手"


def exists():
    try:
        import pystray  # noqa
        import PIL  # noqa
        return True
    except Exception:
        return False


def _make_image():
    """素色「文档」图标（与 build.make_icon / client 托盘同款配色）。"""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((5, 5, 59, 59), 10, fill=(37, 88, 150))
    d.rounded_rectangle((16, 15, 48, 23), 2, fill=(255, 255, 255))
    d.rounded_rectangle((16, 28, 48, 36), 2, fill=(214, 228, 242))
    d.rounded_rectangle((16, 41, 37, 49), 2, fill=(150, 195, 235))
    return img


def _console_hwnd():
    try:
        return ctypes.windll.kernel32.GetConsoleWindow()
    except Exception:
        return 0


def _set_console_visible(show: bool) -> None:
    hwnd = _console_hwnd()
    if not hwnd:
        return
    try:
        ctypes.windll.user32.ShowWindow(hwnd, 5 if show else 0)
    except Exception:
        pass


class ServerTray:
    """服务器常驻托盘。pystray 缺失时 __init__ 抛异常，由调用方捕获降级。"""

    def __init__(self, *, home_url: str = "", on_quit=None, tip: str = "内部办公助手"):
        import pystray
        self._home_url = home_url
        self._on_quit = on_quit
        self._hidden = False
        self._lock = threading.Lock()

        def _open_home():
            if self._home_url:
                try:
                    webbrowser.open(self._home_url)
                except Exception:
                    pass

        def _toggle_console():
            with self._lock:
                self._hidden = not self._hidden
                _set_console_visible(not self._hidden)

        def _quit():
            _set_console_visible(True)          # 退出前先还原控制台，避免残留隐藏窗进程
            cb = self._on_quit
            try:
                self._icon.stop()
            except Exception:
                pass
            if cb:
                try:
                    cb()
                except Exception:
                    pass

        menu = pystray.Menu(
            pystray.MenuItem("打开网页端", _open_home, default=True),
            pystray.MenuItem("隐藏/显示控制台", _toggle_console),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出服务器", _quit),
        )
        self._icon = pystray.Icon("moyu_server", _make_image(), tip or _ICON_TIP, menu)
        self._icon.run_detached()

    def set_home(self, url: str) -> None:
        self._home_url = url

    def visible(self) -> bool:
        icon = getattr(self, "_icon", None)
        return icon is not None

    def stop(self) -> None:
        icon = getattr(self, "_icon", None)
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
            self._icon = None


def start_server_tray(stop: "threading.Event", home_url: str = "") -> ServerTray | None:
    """创建服务器托盘并常驻；pystray 缺失/失败返回 None（不阻断起服）。"""
    if not exists():
        return None
    try:
        return ServerTray(home_url=home_url, on_quit=stop.set)
    except Exception:
        return None