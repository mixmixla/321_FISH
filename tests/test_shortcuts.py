# -*- coding: utf-8 -*-
"""r5b 快捷键注册表辅助函数单测：模式标签 / 键盘捕获 → Tk 绑定模式。"""
import client  # noqa: F401   # 导入即校验注册表定义无语法/导入错误


class _Ev:
    """模拟 Tk KeyPress 事件的最小对象（仅需 state / keysym）。"""

    def __init__(self, state=0, keysym=""):
        self.state = state
        self.keysym = keysym


def test_pattern_label_readable():
    assert client._pattern_label("<Control-Prior>") == "Ctrl+PgUp"
    assert client._pattern_label("<Control-f>") == "Ctrl+F"
    assert client._pattern_label("<Control-9>") == "Ctrl+9"
    assert client._pattern_label("") == "（已禁用）"


def test_event_to_pattern():
    # Ctrl+F：Windows 修正位 state 含 0x4 + keysym 'f'
    assert client._event_to_pattern(_Ev(state=0x4, keysym="f")) == "<Control-f>"
    assert client._event_to_pattern(_Ev(state=0x4, keysym="9")) == "<Control-9>"
    # Ctrl+Alt+Shift+P（避开 boss 的 Ctrl+Alt+H 冲突组合）
    pat = client._event_to_pattern(_Ev(state=0x4 | 0x1 | 0x8, keysym="p"))
    assert pat == "<Control-Shift-Alt-p>"
    # 无修饰也无键 → 空串（不误捕获）
    assert client._event_to_pattern(_Ev(state=0, keysym="")) == ""


def test_registry_unique_ids_and_handlers():
    ids = [s["id"] for s in client.SHORTCUTS]
    assert len(ids) == len(set(ids))          # id 唯一（持久化键不冲突）
    for s in client.SHORTCUTS:
        assert s["default"] < "" or s["default"].startswith("<")
        assert "<Control-Alt-H" not in s["default"]   # 不与 boss 全局热键冲突
        assert callable(getattr(client.ChatWindow, s["handler"], None))  # 处理器存在


# ---------- R65：新增快捷键（未读跳转 / 会话静音 / Esc 逐层收起） ----------

def test_r65_pattern_label_for_new_keys():
    assert client._pattern_label("<Alt-Up>") == "Alt+Up"
    assert client._pattern_label("<Control-Shift-m>") == "Ctrl+Shift+M"
    assert client._pattern_label("<Control-Shift-f>") == "Ctrl+Shift+F"   # 多修饰键修复


class _PrefsStub:
    """只实现快捷键用到的 is_muted。"""

    def __init__(self):
        self.muted = False

    def is_muted(self, _key):
        return self.muted


class _NavStub(client.ChatWindow):
    """_jump_unread_* / _mute_current 的最小 self 替身（不建 Tk、不调 super().__init__）。
    继承 ChatWindow 以便 self 上直接解析到被测方法。"""

    def __init__(self, order, unread, view=("public", None)):
        self._order = list(order)
        self._unread = dict(unread)
        self.view = view
        self.switched = []
        self.toasts = []
        self.toggled = []
        self.refreshed = 0
        self._prefs = _PrefsStub()

    def _session_order(self):
        return list(self._order)

    def _switch_view(self, ch, to):
        self.switched.append((ch, to))

    def show_toast(self, text, warn=False):
        self.toasts.append(text)

    def _pin_key(self, ch, to):
        return f"{ch}:{to}"

    def _toggle_mute_conv(self, key):
        self.toggled.append(key)
        self._prefs.muted = not self._prefs.muted

    def _refresh_lists(self):
        self.refreshed += 1


def test_r65_jump_unread_next_and_prev():
    order = [("public", None), ("private", 2), ("private", 3), ("group", 9)]
    unread = {("public", None): 1, ("private", 3): 2, ("group", 9): 0}
    s = _NavStub(order, unread, view=("public", None))
    client.ChatWindow._jump_unread_next(s)          # 跳过无未读的 private:2
    assert s.switched == [("private", 3)]
    # 从 private:3 继续向下：环回到 public（group 无未读）
    s.view = ("private", 3)
    s.switched.clear()
    client.ChatWindow._jump_unread_next(s)
    assert s.switched == [("public", None)]
    # 向上：public 之前环回 private:3
    s.view = ("public", None)
    s.switched.clear()
    client.ChatWindow._jump_unread_prev(s)
    assert s.switched == [("private", 3)]


def test_r65_jump_unread_none_reports_toast():
    s = _NavStub([("public", None), ("private", 2)], {}, view=("public", None))
    client.ChatWindow._jump_unread_next(s)
    assert s.switched == []
    assert s.toasts == ["没有未读会话"]


def test_r65_jump_unread_unknown_view_starts_from_head():
    """当前会话不在顺序表（如 e2ee 频道）时，向下从表头开始找。"""
    order = [("public", None), ("private", 2)]
    s = _NavStub(order, {("private", 2): 1}, view=("e2ee", 5))
    client.ChatWindow._jump_unread_next(s)
    assert s.switched == [("private", 2)]


def test_r65_mute_current_toggles_and_refreshes():
    s = _NavStub([("public", None), ("private", 2)], {},
                 view=("private", 2))
    client.ChatWindow._mute_current(s)
    assert s.toggled == ["private:2"] and s.refreshed == 1
    assert "已静音" in s.toasts[-1]
    client.ChatWindow._mute_current(s)
    assert s.toggled == ["private:2", "private:2"]
    assert s.toasts[-1] == "已取消静音"


class _EscStub(client.ChatWindow):
    """_esc_layer 的最小 self 替身：按需打开各层，记录被收起的是哪一层。"""

    def __init__(self, **layers):
        self.handled = []

        class _GS:
            def __init__(self, alive):
                self._alive = alive

            def winfo_exists(self):
                return self._alive

            def destroy(self):
                self._alive = False

        self._global_search_box = (_GS(True) if layers.get("global_search")
                                   else None)
        outer = self

        class _Search:
            def winfo_ismapped(self):
                return outer._search_open

        self._search_open = bool(layers.get("search"))
        self.chat_search = _Search()

        class _ML:
            def __init__(self, on):
                self._on = on

            def in_select_mode(self):
                return self._on

            def exit_select_mode(self):
                outer.handled.append("select")

        self.msg_list = _ML(bool(layers.get("select")))
        self._pending_edit_seq = 7 if layers.get("edit") else None
        self._pending_reply = {"nick": "甲"} if layers.get("reply") else None
        self._archived_show = bool(layers.get("archived"))

    def _close_chat_search(self):
        self.handled.append("search")

    def _cancel_pending_input(self):
        self.handled.append("edit")

    def _toggle_archived_panel(self):
        self.handled.append("archived")
        return "break"


def test_r65_esc_layer_order_and_fallthrough():
    # 多层同时打开时，只收起最上层，其余保持
    s = _EscStub(global_search=True, search=True, select=True, edit=True)
    assert client.ChatWindow._esc_layer(s) == "break"
    assert s.handled == []
    assert s._global_search_box is None              # 只收起最上层搜索窗
    assert s._search_open and s.msg_list.in_select_mode()
    # 关掉全局搜索后 → 聊天内搜索条
    s2 = _EscStub(search=True, select=True)
    assert client.ChatWindow._esc_layer(s2) == "break"
    assert s2.handled == ["search"]
    assert s2.msg_list.in_select_mode() is True      # 下层未被动到
    # 仅多选打开 → 退出多选
    s3 = _EscStub(select=True)
    assert client.ChatWindow._esc_layer(s3) == "break"
    assert s3.handled == ["select"]
    # 仅编辑态 → 取消编辑/引用
    s4 = _EscStub(edit=True)
    assert client.ChatWindow._esc_layer(s4) == "break"
    assert s4.handled == ["edit"]
    # 仅归档区 → 收起归档
    s5 = _EscStub(archived=True)
    assert client.ChatWindow._esc_layer(s5) == "break"
    assert s5.handled == ["archived"]
    # 无任何层可收 → 不拦截（输入框 Esc 保持原义）
    assert client.ChatWindow._esc_layer(_EscStub()) is None


class _EntryStub:
    """输入框替身：只实现 _cancel_pending_input 用到的 get/delete/focus_set。"""

    def __init__(self, text=""):
        self.text = text
        self.focused = 0

    def get(self, _first, _last):
        return self.text.split("\n")[0]

    def delete(self, _first, last):
        if last == "end":
            self.text = ""
        else:                                        # "2.0"：删掉首行（引用标记行）
            self.text = "\n".join(self.text.split("\n")[1:])

    def focus_set(self):
        self.focused += 1


class _InputStub(client.ChatWindow):
    """_cancel_pending_input 的最小 self 替身。"""

    def __init__(self, text="", editing=None, replying=None):
        self.entry = _EntryStub(text)
        self._pending_edit_seq = editing
        self._pending_reply = replying
        self._dropped = 0
        self.sys = []

    def _drop_reply_state(self):
        self._dropped += 1
        self._pending_reply = None

    def _append_sys(self, text, *_a, **_k):
        self.sys.append(text)


def test_r65_cancel_pending_input_edit_and_reply():
    # 编辑态：清空编辑内容 + 丢弃引用快照
    s = _InputStub("改后的正文", editing=42, replying={"nick": "甲"})
    s._cancel_pending_input()
    assert s._pending_edit_seq is None and s.entry.text == ""
    assert s._dropped == 1 and s.sys == ["已取消编辑"] and s.entry.focused == 1
    # 引用态：只移除输入框首行引用标记，保留已输入的正文
    s2 = _InputStub("↩ 甲: 原文\n我的回复", replying={"nick": "甲"})
    s2._cancel_pending_input()
    assert s2._pending_reply is None and s2.entry.text == "我的回复"
    assert s2.sys == ["已取消引用"] and s2.entry.focused == 1