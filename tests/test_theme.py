# -*- coding: utf-8 -*-
"""T3 主题 Token 单元测试：皮肤存在性/键完整性/msg_colors 映射/回落。"""
import theme
from theme import get_skin, msg_colors, names, DEFAULT_SKIN


def test_all_skins_have_all_tokens():
    """全部皮肤键集合一致且含 msg_list 需要的键。"""
    ref = set(get_skin(DEFAULT_SKIN))
    assert len(names()) >= 3                # office/apple/apple_dark + chat/dark(R30+)
    for n in names():
        assert set(get_skin(n)) == ref          # 键表完全对齐
    assert {"msg_bg", "bubble_out", "bubble_in", "normal",
            "self", "priv", "sys"} <= ref
    # R8 新增标题栏/hover/边框 token 齐全
    assert {"titlebar_bg", "titlebar_fg", "titlebar_close",
            "hover_bg", "glass_border"} <= ref


def test_msg_colors_maps_all_canvas_keys():
    s = get_skin("office")
    m = msg_colors(s)
    # MsgList.COLORS 用到的键都应在映射里
    need = {"bg", "sys", "self", "priv", "normal", "hit", "hit_active",
            "bubble_in", "bubble_out", "bubble_inline", "bubble_outline"}
    assert need <= set(m)                    # 核心键必须齐（扩展键 R11+ 合法注入）
    assert m["bubble_out"] == s["bubble_out"]
    assert m["bg"] == s["msg_bg"]


def test_unknown_falls_back_office():
    assert get_skin("不存在") == get_skin(None) == get_skin(DEFAULT_SKIN)
    assert get_skin("") == get_skin(DEFAULT_SKIN)


def test_dark_skin_values_differ_from_light():
    """深色套窗/气泡应明显比浅色暗。"""
    from theme import SKINS
    assert SKINS["dark"]["window_bg"] != SKINS["office"]["window_bg"]
    assert SKINS["dark"]["bubble_out"] != SKINS["office"]["bubble_out"]


def test_surface_returns_base_plus_skin_values():
    su = theme.surface("office")
    assert su["titlebar_h"] == theme.BASE["titlebar_h"]
    assert su["scrim_alpha"] == theme.BASE["scrim_alpha"]
    assert su["radius_window"] == theme.BASE["radius_window"]


def test_get_skin_returns_copy_not_mutating_source():
    a = get_skin("office")
    a["window_bg"] = "#000000"
    assert get_skin("office")["window_bg"] != "#000000"


def test_chat_theme_overlay_names_roundtrip():
    """聊天主题叠层：名列表含空串，取主题字典带 msg_list 关键键，未知回落空。"""
    from theme import chat_theme_names, chat_theme_display, get_chat_theme
    assert chat_theme_names()[0] == ""
    assert "mint" in chat_theme_names() and len(chat_theme_names()) >= 5
    assert chat_theme_display("") == "跟随皮肤"
    assert chat_theme_display("mint") == "薄荷"
    t = get_chat_theme("mint")
    assert t["name"] == "薄荷"
    for k in ("bg", "self", "normal", "bubble_in", "bubble_out",
              "bubble_inline", "bubble_outline"):
        assert k in t            # 主题每套须覆盖核心气泡/文本键
    assert get_chat_theme("") == {} and get_chat_theme("不存在") == {}


# ---------- 主题包二：扁平极简冷灰（flat 家族）单元测试 ----------
def _rel_lum(hexc):
    """WCAG 相对亮度：输入 #rrggbb 返回 0~1。"""
    c = [int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    def lin(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = [lin(x) for x in c]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    """WCAG 对比度 (a,b)。"""
    la, lb = _rel_lum(a), _rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def test_flat_skins_present_covered_family():
    """flat/flat_dark 存在、family=flat、核心键齐全（遍历缺键必抛 KeyError）。"""
    from theme import SKINS, skin_family, FAMILY_FLAT
    assert "flat" in SKINS and "flat_dark" in SKINS
    for n in ("flat", "flat_dark"):
        s = SKINS[n]
        assert skin_family(n) == FAMILY_FLAT
        for k in ("window_bg", "panel_bg", "fg", "sub", "list_bg", "icon_bg",
                  "accent", "input_bg", "titlebar_bg", "glass_border",
                  "msg_bg", "sys", "self", "priv", "normal", "hit", "hit_active",
                  "bubble_in", "bubble_out", "bubble_inline", "bubble_outline",
                  "mention", "link", "date", "read", "unread",
                  "react_bg", "react_fg", "react_own", "sel_band", "sel_ring"):
            _ = s[k]
        # 提示条三连（pin/ann/voice）也须齐
        for k in ("pin_bg", "pin_fg", "ann_bg", "ann_fg", "voice_bg", "voice_fg"):
            _ = s[k]


def test_flat_contrast_ok():
    """冷灰浅 + 墨蓝深：主文字 vs 窗底，自气泡白字 vs 自气泡，对比度均须≥4.5。"""
    from theme import SKINS
    f = SKINS["flat"]
    assert _contrast(f["fg"], f["window_bg"]) >= 4.5        # 浅灰底读深炭字
    assert _contrast(f["self"], f["bubble_out"]) >= 4.5     # 白字 on 钢蓝自气泡
    fd = SKINS["flat_dark"]
    assert _contrast(fd["fg"], fd["window_bg"]) >= 4.5      # 墨蓝底读白字
    assert _contrast(fd["self"], fd["bubble_out"]) >= 4.5   # 白字 on 墨蓝自气泡


def test_flat_family_distinct():
    """family 标注：flat 属 flat 家族，旧皮肤与未知名回落 retro。"""
    from theme import skin_family, FAMILY_FLAT, FAMILY_RETRO
    assert skin_family("flat") == FAMILY_FLAT
    assert skin_family("apple") == FAMILY_RETRO
    assert skin_family("qq") == FAMILY_RETRO
    assert skin_family("不存在") == FAMILY_RETRO


def test_web_flat_theme_vars_and_js():
    """web 冷灰两套 CSS 变量齐全（覆写主变量），家族切换 JS 与下拉均在。"""
    import os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(_root, "web.py"), encoding="utf-8") as f:
        src = f.read()
    def seg(name):
        return src.split(':root[data-theme="%s"]{' % name)[1].split("}")[0]
    for var in ("--bg", "--card", "--line", "--txt", "--accent",
                "--bub-self", "--chat-bg", "--side"):
        assert var in seg("flat") and var in seg("flat-dark")
    for js in ("applyWebTheme", "setThemeFamily", "webThemeMode",
               "selThemeFamily", "localStorage.getItem(\"web_theme\")"):
        assert js in src
    # 默认仍是暖粉（light=无 data-theme 保留暖粉浅）
    assert ":root[data-theme=\"flat\"]{" in src