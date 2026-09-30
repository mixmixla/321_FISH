# -*- coding: utf-8 -*-
"""hotkey.py —— ctypes RegisterHotKey 全局热键（默认 Ctrl+Alt+H）→ queue（阶段5）。

约束（Windows 机制）：
- RegisterHotKey 必须在带 GetMessage 消息泵的同一线程注册并接收 WM_HOTKEY；
- 本模块用专用守护线程持 GetMessageW 消息泵，热键事件只入 queue.Queue，
  绝不在该线程碰 tkinter 控件（主线程 root.after 轮询消费）。
- 注册失败（热键被占/非 Windows）→ ok=False，GUI 降级为界面按钮。
- stop() 必须 PostThreadMessageW(WM_QUIT) 让 GetMessageW 返回 0 跳出循环，
  再 UnregisterHotKey 释放。
"""
import ctypes
import os
import queue
import threading
from ctypes import wintypes

MOD_ALT = 0x1
MOD_CONTROL = 0x2
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


class HotkeyManager:
    """全局热键管理器；q 收到 "toggle" 表示用户按了一次热键"""

    def __init__(self, mods: int = MOD_ALT | MOD_CONTROL, vk: int = 0x48,
                 hotkey_id: int = 0x1337,
                 desc_text: str = "Ctrl+Alt+H") -> None:
        self.mods = mods
        self.vk = vk
        self.hotkey_id = hotkey_id
        self._desc = desc_text
        self.q: queue.Queue = queue.Queue()
        self.ok = False
        self._thread = None
        self._stop = threading.Event()
        self._user32 = ctypes.windll.user32 if os.name == "nt" else None

    @property
    def desc(self) -> str:
        return self._desc

    def start(self) -> bool:
        """注册并启动消息泵线程；返回是否注册成功"""
        if self._user32 is None or self._thread is not None:
            return False
        reg = self._user32.RegisterHotKey(None, self.hotkey_id,
                                          self.mods | MOD_NOREPEAT, self.vk)
        if not reg:
            return False
        self.ok = True
        self._thread = threading.Thread(target=self._pump, daemon=True,
                                        name="hotkey-pump")
        self._thread.start()
        return True

    def _pump(self) -> None:
        msg = MSG()
        while not self._stop.is_set():
            r = self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r <= 0:                       # WM_QUIT 或出错
                break
            if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
                self.q.put("toggle")
            else:
                self._user32.TranslateMessage(ctypes.byref(msg))
                self._user32.DispatchMessageW(ctypes.byref(msg))

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            try:
                self._user32.PostThreadMessageW(self._thread.ident, WM_QUIT, 0, 0)
                self._thread.join(timeout=1.0)
            except Exception:
                pass
        if self.ok:
            try:
                self._user32.UnregisterHotKey(None, self.hotkey_id)
            except Exception:
                pass
            self.ok = False
        self._thread = None
