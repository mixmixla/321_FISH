# -*- coding: utf-8 -*-
"""test_r32.py —— R32「Telegram 细节补齐 + 群管理验证」专项测试。

覆盖：
- A3 fmt_list_time：今天 HH:MM / 昨天 / 周X / M月D日 / Y年M月D日（TG 风格）
- A1 拖拽发送：enable_dropfiles 在 Windows 真实注册成功（非 Windows 跳过）
- A2 输入框高度自适应：_adjust_entry_height 1→6 钳制（stub + MethodType）
- B1 会话草稿前缀：draft 非空预览变「草稿: xxx」，空则回退 preview
- B2 表情收藏：toggle 增删 + 收藏上限 + prefs 持久化（stub 挂方法）
- B3 图片 caption：_Row 提取 text → _cap_h 高度 > 0；锚点行高含 caption
- B4 聊天壁纸：set_wallpaper 换 bg / None 恢复主题 / set_colors 换肤后保留
- C1/C2 群改名与邀请码：R28 已实现，test_r28_group_mgmt.py 覆盖（不重复）
"""
import time
import tkinter as tk
from types import MethodType, SimpleNamespace

import pytest

from widgets.session_list import SessionList, fmt_list_time
from widgets.msg_list import MsgList
from widgets.dropfiles import enable_dropfiles

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


# ---------- A3：会话列表时间格式 ----------

def _ts_days_ago(days: int, hour=10, minute=30) -> float:
    """构造「days 天前 的 hour:minute」时间戳（按本地时区 mktime 回算，yday 对齐）。"""
    lt = time.localtime(time.time() - days * 86400)
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hour, minute, 0,
                        0, 0, -1))


def test_fmt_list_time_today():
    assert fmt_list_time(_ts_days_ago(0)) == "10:30"


def test_fmt_list_time_yesterday():
    assert fmt_list_time(_ts_days_ago(1)) == "昨天"


def test_fmt_list_time_weekday():
    s = fmt_list_time(_ts_days_ago(3))
    assert s.startswith("周") and len(s) == 2


def test_fmt_list_time_date():
    lt = time.localtime(_ts_days_ago(30))
    assert fmt_list_time(_ts_days_ago(30)) == f"{lt.tm_mon}月{lt.tm_mday}日"


def test_fmt_list_time_last_year():
    now = time.localtime()
    lt = time.localtime(_ts_days_ago(400))
    if lt.tm_year == now.tm_year:        # 闰年等极端偏移兜底：跳过
        pytest.skip("400 天前仍在同年")
    assert fmt_list_time(_ts_days_ago(400)) == \
        f"{lt.tm_year}年{lt.tm_mon}月{lt.tm_mday}日"


def test_fmt_list_time_empty():
    assert fmt_list_time(0) == ""


# ---------- A1：拖拽发送（Windows 真实注册） ----------

def test_dropfiles_enable(root):
    if __import__("os").name != "nt":
        pytest.skip("仅 Windows")
    calls = []
    ok = enable_dropfiles(root, lambda paths: calls.append(paths))
    assert ok is True
    assert getattr(root, "_dropfiles_proc", None) is not None   # 保引用防 GC


# ---------- A2：输入框高度自适应（stub + MethodType） ----------

def _mk_entry_stub(n_displaylines: int, height: int):
    entry = SimpleNamespace(
        count=lambda *a: (n_displaylines,),      # Tk count 返回 tuple
        cget=lambda k: height,
        config=lambda **kw: kw,
    )
    entry.configured = {}
    orig_cfg = entry.config

    def _cfg(**kw):
        entry.configured.update(kw)
        return orig_cfg(**kw)
    entry.config = _cfg
    return entry


def _attach_adjust(host):
    from client import ChatWindow
    host._adjust_entry_height = MethodType(ChatWindow._adjust_entry_height, host)


def test_entry_height_growth_clamped(root):
    host = SimpleNamespace(entry=_mk_entry_stub(99, 1))
    _attach_adjust(host)
    host._adjust_entry_height()          # 99 行 → 钳到 6
    assert host.entry.configured.get("height") == 6


def test_entry_height_one_line(root):
    host = SimpleNamespace(entry=_mk_entry_stub(1, 6))
    _attach_adjust(host)
    host._adjust_entry_height()          # 1 行 → 收回 1
    assert host.entry.configured.get("height") == 1


def test_entry_height_noop_same(root):
    host = SimpleNamespace(entry=_mk_entry_stub(3, 3))
    _attach_adjust(host)
    host._adjust_entry_height()          # 高度相同 → 不改
    assert host.entry.configured.get("height", None) is None


def test_entry_height_count_exception(root):
    entry = SimpleNamespace(count=lambda *a: (_ for _ in ()).throw(RuntimeError("x")),
                            cget=lambda k: 4, config=lambda **kw: kw)
    entry.configured = {}
    entry.config = lambda **kw: entry.configured.update(kw)
    host = SimpleNamespace(entry=entry)
    _attach_adjust(host)
    host._adjust_entry_height()          # count 异常 → 回退 1
    assert entry.configured.get("height") == 1


# ---------- B1：会话草稿前缀 ----------

@pytest.fixture()
def sl(root):
    s = SessionList(root, FONT, height=150)
    s.configure(width=220)
    s.pack(fill="both", expand=True)
    root.update_idletasks()
    root.update()
    yield s
    s.destroy()


def test_session_draft_prefix(sl):
    sl.set_items([{"key": "k1", "name": "甲", "preview": "最后一条",
                   "ts": time.time(), "unread": 0, "pinned": False,
                   "muted": False, "draft": "还没发的话"}])
    assert "草稿: 还没发的话" in sl.get(0)
    assert "最后一条" not in sl.get(0)     # 有草稿时预览被替换


def test_session_draft_empty_falls_back(sl):
    sl.set_items([{"key": "k1", "name": "甲", "preview": "最后一条",
                   "ts": time.time(), "unread": 0, "pinned": False,
                   "muted": False, "draft": ""}])
    assert "最后一条" in sl.get(0) and "草稿:" not in sl.get(0)


def test_session_draft_newline_flattened(sl):
    sl.set_items([{"key": "k1", "name": "甲", "preview": "p",
                   "ts": time.time(), "unread": 0, "pinned": False,
                   "muted": False, "draft": "一\n二"}])
    assert "草稿: 一 二" in sl.get(0)     # 换行压平（两行布局单行预览）


# ---------- B2：表情收藏（stub 挂方法） ----------

def _mk_fav_host(favs, existing=None):
    """stub ChatWindow 的 _toggle_fav_sticker 依赖面。"""
    from client import ChatWindow, FAV_STICKER_MAX
    saved = []
    sys_lines = []
    rebuilt = []
    host = SimpleNamespace(
        _fav_stickers=list(favs),
        FAV_STICKER_MAX=FAV_STICKER_MAX,
        _prefs=SimpleNamespace(set=lambda k, v: saved.append((k, list(v)))),
        _append_sys=lambda t: sys_lines.append(t),
        _build_stickers=lambda: rebuilt.append(1),
    )
    host._toggle_fav_sticker = MethodType(ChatWindow._toggle_fav_sticker, host)
    return host, saved, sys_lines, rebuilt


def test_fav_sticker_add_remove():
    host, saved, *_ = _mk_fav_host([])
    host._toggle_fav_sticker("smile")
    assert host._fav_stickers == ["smile"]
    host._toggle_fav_sticker("laugh")
    assert host._fav_stickers == ["laugh", "smile"]       # 新收藏置前
    host._toggle_fav_sticker("smile")
    assert host._fav_stickers == ["laugh"]
    assert saved and saved[-1] == ("fav_stickers", ["laugh"])


def test_fav_sticker_max():
    from client import FAV_STICKER_MAX
    favs = [f"c{i}" for i in range(FAV_STICKER_MAX)]
    host, saved, sys_lines, rebuilt = _mk_fav_host(favs)
    host._toggle_fav_sticker("extra")
    assert "extra" not in host._fav_stickers              # 满员拒绝
    assert any("收藏已满" in t for t in sys_lines)
    assert rebuilt == []                                  # 未重排贴纸条


# ---------- B3：图片 caption ----------

@pytest.fixture()
def ml(root):
    m = MsgList(root, FONT)
    m.configure(width=400, height=400)
    m.pack(fill="both", expand=True)
    root.update_idletasks()
    root.update()
    yield m
    m.destroy()


def _png(tmp_path, name="c.png"):
    from PIL import Image
    p = tmp_path / name
    Image.new("RGB", (60, 40), (10, 120, 220)).save(str(p))
    return str(p)


def test_caption_row_extracted(ml, tmp_path):
    p = _png(tmp_path)
    ml.append({"uid": 1, "nick": "甲", "channel": "private", "ts": time.time(),
               "image_path": p, "text": "这是说明文字"})
    assert ml._rows[0].caption == "这是说明文字"


def test_caption_no_text_empty(ml, tmp_path):
    p = _png(tmp_path)
    ml.append({"uid": 1, "nick": "甲", "channel": "private", "ts": time.time(),
               "image_path": p})
    assert ml._rows[0].caption == ""


def test_caption_increases_row_height(ml, tmp_path):
    p = _png(tmp_path)
    base = {"uid": 1, "nick": "甲", "channel": "private", "ts": time.time(),
            "image_path": p}
    ml.append(dict(base))
    h_plain = ml._heights[0]
    ml.clear()
    ml.append(dict(base, text="一行说明"))
    h_cap = ml._heights[0]
    assert h_cap >= h_plain + ml._cap_h("一行说明") - ml._linespace   # 至少多一行高
    assert ml._cap_h("一行说明") > 0


def test_caption_long_wraps(ml, tmp_path):
    p = _png(tmp_path)
    long_cap = "长说明" * 60
    ml.append({"uid": 1, "nick": "甲", "channel": "private", "ts": time.time(),
               "image_path": p, "text": long_cap})
    one = ml._cap_h("字")
    two_lines_cap = ml._cap_h(long_cap)
    assert two_lines_cap > one                            # 折行后高度增加
    ml._render()                                          # 渲染不崩（caption 画布项）
    assert ml._item_ids


# ---------- B4：聊天壁纸 ----------

def test_wallpaper_apply_and_reset(ml):
    default_bg = ml.cget("bg")
    ml.set_wallpaper("#e8dcc8")
    assert ml.cget("bg") == "#e8dcc8"
    assert ml._wallpaper == "#e8dcc8"
    ml.set_wallpaper(None)
    assert ml.cget("bg") == default_bg                    # 恢复主题默认
    assert ml._wallpaper is None
    ml.set_wallpaper("")                                  # 空串等价默认
    assert ml._wallpaper is None


def test_wallpaper_survives_theme_switch(ml):
    ml.set_wallpaper("#efd9e2")
    ml.set_colors({"bg": "#111111"})                      # 换肤（深色 bg）
    assert ml.cget("bg") == "#efd9e2"                     # 壁纸保留不随主题
    ml.set_wallpaper(None)
    assert ml.cget("bg") == "#111111"                     # 清壁纸后回到新主题
