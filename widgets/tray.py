# -*- coding: utf-8 -*-
"""tray.py —— 系统托盘（R31D B1，pystray 可选依赖）。

隐身定位要点：
- 托盘 tooltip / 菜单全部用「办公助手」等中性文案，不出现聊天特征；
- 图标复用 build.make_icon 同款素色「文档」图（无文字/无摸鱼特征）；
- pystray 回调在托盘线程执行，统一 root.after 转回 Tk 主线程；
- pystray/PIL 缺失或初始化失败 → 返回 None，client 静默降级走任务栏闪烁旧路。
"""
import queue
import threading

_ICON_TIP = "办公助手"


def _make_image():
    """素色「文档」图标（与 build.make_icon 同款配色）。"""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((5, 5, 59, 59), 10, fill=(37, 88, 150))
    d.rounded_rectangle((16, 15, 48, 23), 2, fill=(255, 255, 255))
    d.rounded_rectangle((16, 28, 48, 36), 2, fill=(214, 228, 242))
    d.rounded_rectangle((16, 41, 37, 49), 2, fill=(150, 195, 235))
    return img


class Tray:
    """系统托盘：左键/菜单「打开」恢复主窗；隐身入口 + 退出。
    R46：tip=初始 tooltip；set_tip 即时改托盘悬停文字（伪装包联动）。"""

    def __init__(self, root, on_show, on_boss, on_ghost, on_quit, tip=None):
        import pystray
        self._root = root
        # R56：托盘线程只把回调入队，主线程 pump 执行（from 托盘线程 root.after
        #   在 threaded Tcl 下抛 RuntimeError，被吞后菜单点击失效）
        self._q = queue.Queue()
        self._pump()

        def _post(fn):
            def _run():
                self._q.put(fn)
            return _run

        menu = pystray.Menu(
            pystray.MenuItem("打开 办公助手", _post(on_show), default=True),
            pystray.MenuItem("隐身模式", pystray.Menu(
                pystray.MenuItem("切换到表格视图", _post(on_boss)),
                pystray.MenuItem("悬浮字幕", _post(on_ghost)),
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", _post(on_quit)),
        )
        self._icon = pystray.Icon("assistant", _make_image(), tip or _ICON_TIP,
                                  menu)
        self._icon.run_detached()          # Windows 后端：独立线程跑消息循环

    def _pump(self) -> None:
        """主线程执行入队的托盘回调（托盘线程只负责 put，不碰 Tk）。"""
        try:
            while True:
                fn = self._q.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except queue.Empty:
            pass
        try:
            self._root.after(50, self._pump)
        except Exception:
            pass                      # 主窗已销毁：停止 pump

    def set_tip(self, tip: str) -> None:
        """R46：更新托盘悬停文字（伪装标题；空串回退默认「办公助手」）。"""
        icon = getattr(self, "_icon", None)
        if icon is None:
            return
        try:
            icon.title = tip or _ICON_TIP
        except Exception:
            pass

    def visible(self) -> bool:
        return getattr(self, "_icon", None) is not None

    def stop(self) -> None:
        icon = getattr(self, "_icon", None)
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
            self._icon = None
