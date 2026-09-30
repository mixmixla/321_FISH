# -*- coding: utf-8 -*-
"""R38a UI 冒烟：CallWindow 各状态渲染（来电/连通/通话/警告/结束）。"""
import tkinter as tk

from widgets.call_window import CallWindow


class StubMgr:
    state = "idle"

    def set_ptt(self, on):
        self.state = "incall" if on else "idle"

    def accept_call(self):
        return True

    def reject_call(self):
        return True

    def end_call(self):
        return True

    def duration(self):
        return 65.0


root = tk.Tk()
root.withdraw()
w = CallWindow(root, manager=StubMgr(), peer_nick="甲")
for ev in ({"state": "incoming", "nick": "乙", "text": "乙 请求语音通话"},
           {"state": "connecting", "text": "已接听，建立直连…"},
           {"state": "incall"},
           {"state": "warn", "text": "无法打开麦克风"},
           {"state": "ended", "text": "已挂断"}):
    w.update_state(ev)
    root.update()
assert w.lbl_nick.cget("text") == "乙"
assert "已挂断" in str(w.lbl_status.cget("text"))
root.destroy()
print("CallWindow UI 冒烟通过")
