# -*- coding: utf-8 -*-
"""test_session_list.py —— 两行会话列表控件（R7/T5+T6+T8）专项测试。

核心验收：
- Listbox 兼容外层 API：set_items/size/get/curselection/selection_set/
  selection_clear/nearest/see
- 未读角标文案（fmt_unread，>99→99+）与行文本携带未读/置顶信息
- 键盘导航：Up/Down/Home/End 移选择 + 边界钳制；Enter 触发 on_pick
- 静音/置顶在渲染与兼容文本中正确体现
"""
import time
import tkinter as tk

import pytest

from widgets.session_list import SessionList, fmt_unread

FONT = ("Microsoft YaHei UI", 9)


@pytest.fixture(scope="module")
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:          # 无显示环境（headless CI）跳过
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


@pytest.fixture()
def sl(root):
    picks = []
    s = SessionList(root, FONT, height=150,
                    on_pick=lambda i: picks.append(i))
    s.configure(width=200)
    s.pack(fill="both", expand=True)
    root.update_idletasks()
    root.update()
    yield s, picks
    s.destroy()


def _items(n=3, names=("甲", "乙", "丙"), muted=(), pinned=(), unreads=()):
    def _name(i):
        return names[i] if i < len(names) else f"用户{i}"
    items = []
    for i in range(n):
        u = (i + 1) % (unreads or [0]) if unreads else 0
        items.append({
            "key": f"k{i}",
            "name": _name(i),
            "preview": f"预览{i}",
            "ts": time.time() - i,
            "unread": u,
            "pinned": i in pinned,
            "muted": i in muted,
        })
    return items


def test_fmt_unread():
    assert fmt_unread(0) == ""
    assert fmt_unread(3) == "3"
    assert fmt_unread(99) == "99"
    assert fmt_unread(100) == "99+"
    assert fmt_unread(233) == "99+"
    assert fmt_unread(-5) == ""


def test_compat_size_and_get(sl):
    s, _ = sl
    assert s.size() == 0
    s.set_items(_items())
    assert s.size() == 3
    assert s.get(0)  # 单下标返回字符串（含名称/预览/时间/未读）
    row0 = s.get(0, "end")
    assert isinstance(row0, tuple) and len(row0) == 3
    assert "甲" in row0[0]


def test_curselection_roundtrip(sl):
    s, picks = sl
    s.set_items(_items())
    assert s.curselection() == ()
    s.selection_set(1)
    assert s.curselection() == (1,)
    s.selection_clear(0, "end")
    assert s.curselection() == ()


def test_selection_set_clamps(sl):
    s, _ = sl
    s.set_items(_items())
    s.selection_set(99)                      # 越界 → 忽略
    assert s.curselection() == ()
    s.selection_set(0)
    assert s.curselection() == (0,)


def test_keyboard_up_down_home_end(sl):
    s, picks = sl
    s.set_items(_items())
    s._sel = 0
    s._on_down()                             # 0→1
    assert s._sel == 1
    s._on_end()                              # → last
    assert s._sel == 2
    s._on_down()                             # 超界钳制在末位
    assert s._sel == 2
    s._on_up()                               # →1
    assert s._sel == 1
    s._on_home()                             # →0
    assert s._sel == 0
    s._on_up()                               # 超界钳制在 0
    assert s._sel == 0


def test_enter_triggers_on_pick(sl):
    s, picks = sl
    s.set_items(_items())
    s._sel = 1
    s._on_return()
    assert picks == [1]


def test_click_triggers_on_pick(sl):
    s, picks = sl
    s.set_items(_items())
    ev = _uml_fake_event(56 + 10)            # 第二行中点
    s._on_click(ev)
    assert s._sel == 1
    assert picks == [1]


def test_unread_in_text(sl):
    s, _ = sl
    items = _items(n=1, names=("甲",))
    items[0]["unread"] = 7
    s.set_items(items)
    assert "(7)" in s.get(0)
    items[0]["unread"] = 150                 # 兼容文本带原值；视觉角标经 fmt_unread 压 99+
    s.set_items(items)
    assert "(150)" in s.get(0)


def test_pinned_prefix_in_text(sl):
    s, _ = sl
    items = _items(n=1, names=("甲",), pinned=(0,))
    s.set_items(items)
    assert "📌" in s.get(0)


def test_muted_does_not_break_draw(sl):
    s, _ = sl
    items = _items(n=2, names=("甲", "乙"), muted=(1,))
    s.set_items(items)                       # 静音行渲染不抛异常
    assert s.size() == 2


def test_set_items_preserves_selection_by_key(sl):
    s, _ = sl
    items = _items()
    s.set_items(items)
    s.selection_set(1)
    s.set_items(_items())                    # 全量刷新（key 命中恢复选中）
    assert s.curselection() == (1,)


def test_nearest_accounts_for_scroll(sl):
    s, _ = sl
    s.set_items(_items(n=10))                 # 10 行 * 56 = 560，超出可视高
    s.yview_moveto(0.5)                       # 滚到中部：画布 y = 视口 y + 偏移
    s._redraw()
    # 视口 y=10 处，忽略滚动会误判为第 0 行；correct 实现应右移到滚动行
    assert s.nearest(10) >= 1, f"滚动后 nearest 未右移: {s.nearest(10)}"


def _uml_fake_event(y):
    return type("_Ev", (), {"y": y, "x": 10})()