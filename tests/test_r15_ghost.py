# -*- coding: utf-8 -*-
"""R15：跨会话全局最近消息（LocalHistory.recent_global）+ GHOST 透明 token 表。"""
import tempfile
import time

from theme import (GHOST, GHOST_PUNCH, GHOST_BLACK, SKINS, ghost_palette,
                   _hex_mix)
from client_core import LocalHistory


def _mk(ts, text, nick="x"):
    return {"channel": "public", "text": text, "ts": ts, "nick": nick}


def test_recent_global_cross_channel_sorted():
    lh = LocalHistory(tempfile.mkdtemp())
    t = time.time()
    lh.add("public", _mk(t + 0, "a"))
    lh.add("private:1:2", _mk(t + 1, "b"))
    lh.add("group:7", _mk(t + 2, "c"))
    r = lh.recent_global(3)
    assert [m["text"] for m in r] == ["c", "b", "a"]   # 跨会话按 ts 降序


def test_recent_global_max_caps():
    lh = LocalHistory(tempfile.mkdtemp())
    t = time.time()
    for i in range(5):
        lh.add("public", _mk(t + i, f"m{i}"))
    r = lh.recent_global(2)
    assert [m["text"] for m in r] == ["m4", "m3"]


def test_recent_global_str_ts_tolerated():
    lh = LocalHistory(tempfile.mkdtemp())
    t = time.time()
    lh.add("public", {"channel": "public", "text": "str", "ts": str(t), "nick": "x"})
    lh.add("public", {"channel": "public", "text": "bad", "ts": "oops", "nick": "x"})
    lh.add("public", {"channel": "public", "text": "num", "ts": t + 1, "nick": "x"})
    r = lh.recent_global(3)
    assert [m["text"] for m in r] == ["num", "str", "bad"]


def test_recent_global_empty():
    lh = LocalHistory(tempfile.mkdtemp())
    assert lh.recent_global(5) == []


def test_ghost_table_covers_all_skin_keys():
    # GHOST 必须覆盖 SKINS 的所有配色键（除 name），否则 _apply_skin(palette=GHOST) 会 KeyError
    for k in SKINS["office"]:
        assert k in GHOST, f"GHOST 缺 token: {k}"


def test_ghost_punch_black_values():
    bg_keys = ("window_bg", "panel_bg", "list_bg", "input_bg", "titlebar_bg",
               "msg_bg", "hover_bg", "glass_border", "bubble_in", "bubble_out",
               "bubble_inline", "bubble_outline", "hit", "hit_active", "react_bg")
    fg_keys = ("fg", "sub", "normal", "sys", "self", "priv", "accent",
               "titlebar_fg", "titlebar_btn", "titlebar_close", "selected_fg",
               "mention", "link", "date", "read", "react_fg", "react_own")
    for k in bg_keys:
        assert GHOST[k] == GHOST_PUNCH, k
    for k in fg_keys:
        assert GHOST[k] == GHOST_BLACK, k


def test_ghost_palette_zero_is_punch():
    # 衬底 0 → 气泡仍为挖空色（只有黑字悬浮）
    pal = ghost_palette(0.0)
    assert pal["bubble_in"] == GHOST_PUNCH
    assert pal["bubble_out"] == GHOST_PUNCH


def test_ghost_palette_higher_back_towards_white():
    pal0 = ghost_palette(0.0)
    pal1 = ghost_palette(0.5)
    pal2 = ghost_palette(1.0)
    # 气泡色从近黑(挖空) 单调趋向纯白，文字键不受影响
    assert int(pal0["bubble_in"][1:3], 16) <= int(pal1["bubble_in"][1:3], 16) <= 255
    assert int(pal1["bubble_out"][1:3], 16) < int(pal2["bubble_out"][1:3], 16)
    assert pal2["bubble_in"] == "#ffffff"
    assert pal1["normal"] == GHOST_BLACK      # 文字恒黑
    # 覆盖 SKINS 全部键
    for k in SKINS["office"]:
        assert k in pal1


def test_ghost_palette_clamped():
    assert ghost_palette(-3)["bubble_in"] == GHOST_PUNCH
    assert ghost_palette(9)["bubble_in"] == "#ffffff"
    mid = ghost_palette(1.0)["bubble_in"]
    assert mid == "#ffffff"


def test_hex_mix_endpoints():
    assert _hex_mix("#000000", "#ffffff", 0.0) == "#000000"
    assert _hex_mix("#000000", "#ffffff", 1.0) == "#ffffff"
    assert _hex_mix("#000000", "#ffffff", 0.5) == "#808080"