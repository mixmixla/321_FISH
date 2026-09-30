# -*- coding: utf-8 -*-
"""theme.py —— Token 主题系统（T3，对照 UI_改造设计.md §4 双皮肤 + R3 深色）。

五套预置皮肤，每套是同一组 Token 的不同值：
- apple     「Apple 浅色」：iMessage 风格（蓝气泡/灰气泡），macOS Sonoma 配色
- apple_dark「Apple 深色」：iMessage 深色模式，macOS 深色配色
- office    「办公灰蓝」：摸鱼安全（像内网 OA，低识别度）
- chat      「畅聊模式」：像聊天软件（微信式绿意，自己气泡偏绿）
- dark      「深色」      ：对应 Telegram night-green 调色板

接入方式：`get_skin(name)` 拿整张 token 表；key 命名与 msg_list.COLORS、
client 顶层控件一一对应。皮肤名通过 prefs['skin'] 持久化。无第三方依赖。

R41D：`system_prefers_dark()` 读 Windows 个性化注册表（AppsUseLightTheme），
配合 client 的「跟随系统深浅」开关自动切 apple/apple_dark 皮肤。
"""
import os

# Token → (浅色) 值；深色皮肤按 TG night 调色板取值（§7.4）。
# 数值化密度常量（对标 TG st:: 间距/圆角/时长，避免散落硬编码）。
BASE = {
    "titlebar_h": 28,          # 自绘标题栏高（Apple 风格更紧凑）
    "radius_window": 10,       # 主窗圆角（Apple 标准 10px）
    "radius_small": 6,         # 小圆角
    "scrim_alpha": 0.40,       # 模态遮罩不透明度
    "anim": {"fast": 160, "normal": 250, "slow": 360},   # 过渡时长(ms)
    "pad_x": 8,
    "pad_y": 6,
}

# ── 主题包家族常量（必须定义于 SKINS 之前，供 SKINS 内 family 字段引用）──
FAMILY_RETRO = "retro"   # 暖粉手绘风（原家族，默认主家族）
FAMILY_FLAT = "flat"     # 扁平极简冷灰风（浅灰/白卡/冷描边/单强调色；深色=墨蓝黑）

SKINS = {
    # 全系改版：原创手绘暖粉家族（焦糖/珊瑚/浅紫蓝/薄荷，与网页/游戏画布一致）。
    # 所有界面（主窗三栏/标题栏/设置/弹窗/后台面板/游戏面板）都从这些 Token 派生，
    # 因此一套暖调即可让整个软件统一成「原创美术·高级交互」观感。
    "apple": {
        "name": "苹果暖粉",
        "family": FAMILY_RETRO,
        "window_bg": "#fff8f0",   # 奶油窗底（更明净）
        "panel_bg": "#fffefb",    # 会话面板/底栏（暖白更亮）
        "fg": "#544438",          # 里料可可主文字（对比更强）
        "sub": "#b09c84",         # 暖奶灰次要文字
        "list_bg": "#fff3e6",     # 侧边列表（焦糖浅）
        "icon_bg": "#ffe9d8",     # R52 最左图标栏（杏橙浅）
        "accent": "#ff8555",      # 珊瑚强调（更鲜艳显示精细）
        "input_bg": "#fffdf8",
        "titlebar_bg": "#ffe9d8",
        "titlebar_fg": "#8a6f55",
        "titlebar_close": "#ff7e67",   # 珊瑚红绿灯-红
        "titlebar_btn": "#c4a88c",
        "hover_bg": "#ffe9d6",
        "glass_border": "#efe0cc",     # 奶油描边
        # —— msg_list COLORS 对应键 ——
        "msg_bg": "#fff8f0",           # 聊天区奶油
        "sys": "#bca88f",
        "self": "#0e4a32",             # 自己气泡内文字=深薄荷（配薄荷气泡）
        "priv": "#5f4b38",
        "normal": "#544438",
        "hit": "#ffefd2",
        "hit_active": "#ffd180",
        "bubble_in": "#fffbf3",        # 他人气泡=更柔暖白（与描边区分）
        "bubble_out": "#54cd9b",       # 自己气泡=清亮薄荷（更饱和现代）
        "bubble_inline": "#e9d7c0",    # 他人气泡描边（奶油加深）
        "bubble_outline": "#a5e6c8",
        # R11 富文本：@提及（浅紫蓝）与 链接触发（珊瑚）
        "mention": "#9b6bd8",
        "link": "#ff7e67",
        "mention_self": "#ffd9cd",     # 薄荷底自适应浅紫
        "link_self": "#ffd4c8",
        # R12 日期分隔 / R13 回应 / 已读
        "date": "#a98e72",
        "react_bg": "#ffe8d4",
        "react_fg": "#5b4636",
        "react_own": "#ff8a5c",
        "read": "#a98e72",
        "unread": "#e8635a",
        "sel_band": "#ffe3d0",         # 多选整行高亮带（杏橙浅）
        "sel_ring": "#cfb49a",
        # R56 提示条 浅色变体
        "pin_bg": "#fff3d6", "pin_fg": "#b2772e",
        "ann_bg": "#fce4ee", "ann_fg": "#b25e85",
        "voice_bg": "#fff0e0", "voice_fg": "#e05a3a",
        # 手绘风气泡几何（更圆）
        "bubble_r": 18,
        "bubble_pad_h": 11,
        "bubble_pad_v": 8,
        "titlebar_h": 28,
        "traffic_lights": True,
    },
    "apple_dark": {
        "name": "暖粉深色",
        "family": FAMILY_RETRO,
        "window_bg": "#2a211b",   # 焦糖深底
        "panel_bg": "#352a22",    # 深面板
        "fg": "#f5e9dd",          # 暖白主文字
        "sub": "#b49b82",
        "list_bg": "#352a22",
        "icon_bg": "#2e241d",
        "accent": "#ff8a5c",      # 珊瑚强调（深底依旧醒目）
        "input_bg": "#3a2f26",
        "titlebar_bg": "#2e241d",
        "titlebar_fg": "#c0a58a",
        "titlebar_close": "#ff7e67",
        "titlebar_btn": "#9c8268",
        "hover_bg": "#42362c",
        "glass_border": "#4a3c30",
        "msg_bg": "#2a211b",
        "sys": "#a98e75",
        "self": "#ffefdf",        # 自己气泡内文字=暖白（配珊瑚泡泡）
        "priv": "#e7c9a8",
        "normal": "#efe2d2",
        "hit": "#54472f",
        "hit_active": "#7a6235",
        "bubble_in": "#3f332a",
        "bubble_out": "#c25e3e",  # 自己气泡=珊瑚
        "bubble_inline": "#4a3c30",
        "bubble_outline": "#4a3c30",
        "mention": "#c69ae0",
        "link": "#ff8a5c",
        "mention_self": "#ffd3c8",
        "link_self": "#ffd4c8",
        "date": "#a98e75",
        "react_bg": "#42362c",
        "react_fg": "#f5e9dd",
        "react_own": "#ff8a5c",
        "read": "#a98e75",
        "unread": "#e8635a",
        "sel_band": "#4a3320",
        "sel_ring": "#9c8268",
        "pin_bg": "#40361f", "pin_fg": "#e3be7a",
        "ann_bg": "#3e2733", "ann_fg": "#e5aeb3",
        "voice_bg": "#3e2c1e", "voice_fg": "#e0a060",
        "bubble_r": 16,
        "bubble_pad_h": 10,
        "bubble_pad_v": 7,
        "titlebar_h": 28,
        "traffic_lights": True,
    },
    "office": {
        "name": "奶油办公",
        "family": FAMILY_RETRO,
        "window_bg": "#fbf2e4",   # 奶油底（沿用办公低识别度定位，低调暖调）
        "panel_bg": "#fffdf6",    # 会话面板/底栏
        "fg": "#4f4233",
        "sub": "#9d8f7d",
        "list_bg": "#fbf1e0",
        "icon_bg": "#f2e4cc",
        "accent": "#c2703d",      # 焦糖强调（比珊瑚更沉稳，办公不招摇）
        "input_bg": "#fffdf6",
        "titlebar_bg": "#f2e4cc",
        "titlebar_fg": "#8a6f55",
        "titlebar_close": "#e05a3a",
        "titlebar_btn": "#b5a088",
        "hover_bg": "#efe0c6",
        "glass_border": "#e5d3b7",
        "msg_bg": "#fbf3e6",
        "sys": "#b0a08b",
        "self": "#0e4a32",
        "priv": "#6b5239",
        "normal": "#4f4233",
        "hit": "#ffedca",
        "hit_active": "#ffce7a",
        "bubble_in": "#fef3e3",
        "bubble_out": "#6fd3a4",  # 自己气泡=薄荷
        "bubble_inline": "#ecd8ba",
        "bubble_outline": "#bfe8d3",
        "mention": "#9b6bd8",
        "link": "#c2703d",
        "mention_self": "#ffd9cd",
        "link_self": "#ffd4c8",
        "date": "#a98e72",
        "read": "#a98e72",
        "unread": "#e0574f",
        "sel_band": "#f6e3c8",
        "sel_ring": "#c2ab8d",
        "react_bg": "#efe0c6",
        "react_fg": "#4f4233",
        "react_own": "#c2703d",
        "pin_bg": "#fdf0d6", "pin_fg": "#a86f2e",
        "ann_bg": "#fae6ee", "ann_fg": "#a25c7d",
        "voice_bg": "#fdede0", "voice_fg": "#d85a3a",
        "bubble_r": 14,
        "bubble_pad_h": 9,
        "bubble_pad_v": 6,
        "titlebar_h": 28,
        "traffic_lights": False,
    },
    "chat": {
        "name": "畅聊薄荷",
        "family": FAMILY_RETRO,
        "window_bg": "#f6f4e6",
        "panel_bg": "#fffef6",
        "fg": "#46513d",
        "sub": "#98a48a",
        "list_bg": "#f0f0e0",
        "icon_bg": "#e2ebda",
        "accent": "#3ba676",      # 薄荷绿强调
        "input_bg": "#fffef6",
        "titlebar_bg": "#eef2e4",
        "titlebar_fg": "#6b7a5f",
        "titlebar_close": "#e05a3a",
        "titlebar_btn": "#9fb093",
        "hover_bg": "#e6ecdd",
        "glass_border": "#dce4cd",
        "msg_bg": "#faf7ea",
        "sys": "#adb99d",
        "self": "#0e4a32",
        "priv": "#6b5239",
        "normal": "#46513d",
        "hit": "#fff3cd",
        "hit_active": "#ffd47c",
        "bubble_in": "#f5f2e2",
        "bubble_out": "#5ccb8e",  # 自己气泡=薄荷
        "bubble_inline": "#e3e5cf",
        "bubble_outline": "#a8dfbc",
        "mention": "#9b6bd8",
        "link": "#3ba676",
        "mention_self": "#c9efd2",
        "link_self": "#bfe8d0",
        "date": "#a9b39b",
        "read": "#a9b39b",
        "unread": "#e0574f",
        "sel_band": "#dfeccf",
        "sel_ring": "#b9c6a6",
        "react_bg": "#e6ecdd",
        "react_fg": "#46513d",
        "react_own": "#3ba676",
        "pin_bg": "#fdf0d6", "pin_fg": "#a86f2e",
        "ann_bg": "#fae6ee", "ann_fg": "#a25c7d",
        "voice_bg": "#fdede0", "voice_fg": "#d85a3a",
        "bubble_r": 14,
        "bubble_pad_h": 9,
        "bubble_pad_v": 6,
        "titlebar_h": 28,
        "traffic_lights": False,
    },
    "dark": {
        "name": "暖黑",
        "family": FAMILY_RETRO,
        "window_bg": "#241d19",
        "panel_bg": "#2e251f",
        "fg": "#efe0d0",
        "sub": "#a58d74",
        "list_bg": "#2e251f",
        "icon_bg": "#291f19",
        "accent": "#ff8a5c",
        "input_bg": "#2b211b",
        "titlebar_bg": "#241d19",
        "titlebar_fg": "#b49b82",
        "titlebar_close": "#e8635a",
        "titlebar_btn": "#8a745d",
        "hover_bg": "#3a2d24",
        "glass_border": "#443528",
        "msg_bg": "#2e251f",
        "sys": "#a58d74",
        "self": "#ffefdf",
        "priv": "#e7c9a8",
        "normal": "#efe0d0",
        "hit": "#4d4129",
        "hit_active": "#6d5a30",
        "bubble_in": "#3a2f26",
        "bubble_out": "#d9753f",  # 自己气泡=暖珊瑚
        "bubble_inline": "#443528",
        "bubble_outline": "#443528",
        "mention": "#c69ae0",
        "link": "#ff8a5c",
        "mention_self": "#ffd3c8",
        "link_self": "#ffd4c8",
        "date": "#a58d74",
        "read": "#a58d74",
        "unread": "#ff6b5e",
        "sel_band": "#48341f",
        "sel_ring": "#8a745d",
        "react_bg": "#3a2d24",
        "react_fg": "#efe0d0",
        "react_own": "#ff8a5c",
        "pin_bg": "#3e361f", "pin_fg": "#dfbb78",
        "ann_bg": "#3c2833", "ann_fg": "#e0a8b2",
        "voice_bg": "#3c2a1e", "voice_fg": "#de9c5a",
        "bubble_r": 14,
        "bubble_pad_h": 9,
        "bubble_pad_v": 6,
        "titlebar_h": 28,
        "traffic_lights": False,
    },
    # R交互：微信绿专属配色（随 interaction_mode=wechat 自动应用；暖粉家族里的薄荷绿）
    "wechat": {
        "name": "薄荷微信",
        "family": FAMILY_RETRO,
        "window_bg": "#f3f6ea",
        "panel_bg": "#fffef6",
        "fg": "#46513d",
        "sub": "#98a48a",
        "list_bg": "#fffef6",
        "icon_bg": "#e4eddd",
        "accent": "#3ba676",
        "input_bg": "#fffef6",
        "titlebar_bg": "#e4eddd",
        "titlebar_fg": "#6b7a5f",
        "titlebar_close": "#e05a3a",
        "titlebar_btn": "#9fb093",
        "hover_bg": "#e2edde",
        "glass_border": "#d7e2cf",
        "msg_bg": "#f8f5ea",
        "sys": "#adb99d",
        "self": "#0e4a32",
        "priv": "#46513d",
        "normal": "#46513d",
        "hit": "#fff3cd",
        "hit_active": "#ffd47c",
        "bubble_in": "#f5f2e2",
        "bubble_out": "#5ccb8e",
        "bubble_inline": "#e3e5cf",
        "bubble_outline": "#a8dfbc",
        "mention": "#2f9d63",
        "link": "#3ba676",
        "mention_self": "#c9efd2",
        "link_self": "#bfe8d0",
        "date": "#a9b39b",
        "read": "#a9b39b",
        "unread": "#e05a3a",
        "sel_band": "#dfeccf",
        "sel_ring": "#b9c6a6",
        "react_bg": "#e2edde",
        "react_fg": "#46513d",
        "react_own": "#3ba676",
        "pin_bg": "#eef7ef", "pin_fg": "#0a7a38",
        "ann_bg": "#f6eef8", "ann_fg": "#6d4fa8",
        "voice_bg": "#fdede0", "voice_fg": "#d85a3a",
        "bubble_r": 12,
        "bubble_pad_h": 9,
        "bubble_pad_v": 6,
        "titlebar_h": 28,
        "traffic_lights": False,
    },
    # R交互：QQ 蓝专属配色（随 interaction_mode=qq 自动应用；奶油底 + 灰蓝强调）
    "qq": {
        "name": "奶油QQ",
        "family": FAMILY_RETRO,
        "window_bg": "#f7f6f0",
        "panel_bg": "#fffef9",
        "fg": "#4f493d",
        "sub": "#a29b8b",
        "list_bg": "#fffef9",
        "icon_bg": "#ebe8dc",
        "accent": "#5a7bc0",       # 灰蓝强调（奶油底保留 QQ 辨识度）
        "input_bg": "#fffef9",
        "titlebar_bg": "#ebe8dc",
        "titlebar_fg": "#7a8770",
        "titlebar_close": "#e05a3a",
        "titlebar_btn": "#a89f8a",
        "hover_bg": "#efeadf",
        "glass_border": "#e0dbc9",
        "msg_bg": "#fdfbf2",
        "sys": "#b0a891",
        "self": "#1f2f4d",         # 自己气泡内文字=深蓝（配灰蓝泡泡）
        "priv": "#4f493d",
        "normal": "#4f493d",
        "hit": "#fff3cd",
        "hit_active": "#ffd47c",
        "bubble_in": "#f8f4e8",
        "bubble_out": "#7ea0d6",   # 自己气泡=灰蓝
        "bubble_inline": "#e6e0cc",
        "bubble_outline": "#b7c7e6",
        "mention": "#7c5f9e",
        "link": "#5a7bc0",
        "mention_self": "#cfe0f7",
        "link_self": "#cfe0f7",
        "date": "#a89f8a",
        "read": "#a89f8a",
        "unread": "#e05a3a",
        "sel_band": "#e6ecf6",
        "sel_ring": "#b8b2a0",
        "react_bg": "#efeaf0",
        "react_fg": "#4f493d",
        "react_own": "#5a7bc0",
        "pin_bg": "#eef3fb", "pin_fg": "#2d62a8",
        "ann_bg": "#f6eef8", "ann_fg": "#6d4fa8",
        "voice_bg": "#fdede0", "voice_fg": "#d85a3a",
        "bubble_r": 12,
        "bubble_pad_h": 8,
        "bubble_pad_v": 5,
        "titlebar_h": 28,
        "traffic_lights": False,
    },
    # ── 主题包二：扁平极简冷灰（flat 家族）────────────────────────────
    # 浅灰底/白卡/冷灰描边/单一强调色（钢蓝）；深色=墨蓝黑。冷酯无暖调，
    # 与暖粉手绘风形成两极。key 与 retro 家族逐一对齐，fallback 全兼容。
    "flat": {
        "name": "冷灰·浅色",
        "family": FAMILY_FLAT,
        "window_bg": "#f3f4f6",   # 浅灰窗底
        "panel_bg": "#ffffff",    # 白卡面板/底栏
        "fg": "#2b3036",          # 深炭主文字
        "sub": "#8b9199",         # 冷灰次要文字
        "list_bg": "#eceef1",     # 侧边列表浅灰
        "icon_bg": "#e4e7eb",     # 最左图标栏浅灰
        "accent": "#2e63e0",      # 单一强调色=钢蓝
        "input_bg": "#ffffff",
        "titlebar_bg": "#eceef1",
        "titlebar_fg": "#3a4048",
        "titlebar_close": "#e05a4d",
        "titlebar_btn": "#7a838c",
        "hover_bg": "#e5e8ec",
        "glass_border": "#dfe2e7",   # 冷灰细描边
        "msg_bg": "#f3f4f6",
        "sys": "#9aa0a8",
        "self": "#ffffff",           # 自己气泡内文字=白
        "priv": "#333a42",
        "normal": "#2b3036",
        "hit": "#e7eeff",
        "hit_active": "#c6d6ff",
        "bubble_in": "#ffffff",      # 他人气泡=白卡
        "bubble_out": "#2e63e0",     # 自己气泡=钢蓝
        "bubble_inline": "#dfe2e7",
        "bubble_outline": "#2e63e0",
        "mention": "#3b6df0",
        "link": "#2e63e0",
        "mention_self": "#dfe7ff",
        "link_self": "#dfe7ff",
        "date": "#8b9199",
        "react_bg": "#eceef1",
        "react_fg": "#2b3036",
        "react_own": "#2e63e0",
        "read": "#8b9199",
        "unread": "#e05540",
        "sel_band": "#e7eeff",
        "sel_ring": "#8f96a0",
        "pin_bg": "#eef1f7", "pin_fg": "#2f5fb8",
        "ann_bg": "#f0eff7", "ann_fg": "#6a5fa8",
        "voice_bg": "#f4f0ee", "voice_fg": "#d0503a",
        "bubble_r": 6,             # 扁平极简：小圆角
        "bubble_pad_h": 8,
        "bubble_pad_v": 5,
        "titlebar_h": 26,
        "traffic_lights": False,
    },
    "flat_dark": {
        "name": "冷灰·墨蓝",
        "family": FAMILY_FLAT,
        "window_bg": "#171a21",   # 墨蓝黑窗底
        "panel_bg": "#1f232c",    # 深面板
        "fg": "#e0e5ec",
        "sub": "#8b95a3",
        "list_bg": "#1c2028",
        "icon_bg": "#191d25",
        "accent": "#5b8def",      # 钢蓝强调（深底醒目）
        "input_bg": "#232834",
        "titlebar_bg": "#191d25",
        "titlebar_fg": "#aeb6c1",
        "titlebar_close": "#e0615d",
        "titlebar_btn": "#6b7481",
        "hover_bg": "#2a303c",
        "glass_border": "#303744",   # 冷灰深描边
        "msg_bg": "#171a21",
        "sys": "#7f8896",
        "self": "#ffffff",
        "priv": "#cfd6e0",
        "normal": "#e0e5ec",
        "hit": "#2a3550",
        "hit_active": "#3b4f7a",
        "bubble_in": "#232834",
        "bubble_out": "#3f6fd8",  # 自己气泡=墨蓝
        "bubble_inline": "#2f3644",
        "bubble_outline": "#3f6fd8",
        "mention": "#7d9cf0",
        "link": "#5b8def",
        "mention_self": "#2a3550",
        "link_self": "#2a3550",
        "date": "#7f8896",
        "react_bg": "#262c38",
        "react_fg": "#e0e5ec",
        "react_own": "#5b8def",
        "read": "#7f8896",
        "unread": "#e0615d",
        "sel_band": "#26324a",
        "sel_ring": "#5a6573",
        "pin_bg": "#232c3d", "pin_fg": "#8fb0ea",
        "ann_bg": "#2a2640", "ann_fg": "#a79de0",
        "voice_bg": "#332824", "voice_fg": "#e07a6a",
        "bubble_r": 6,
        "bubble_pad_h": 8,
        "bubble_pad_v": 5,
        "titlebar_h": 26,
        "traffic_lights": False,
    },
}

DEFAULT_SKIN = "apple"

# R15 全透明黑字模式：挖空色与纯黑。复用 -transparentcolor 把全窗背景挖空只剩黑字。
GHOST_PUNCH = "#010203"     # 挖空色（近黑、极罕见，避免与正常浅色主题误撞）
GHOST_BLACK = "#000000"     # 文字/强调统一纯黑

# 与 SKINS 同键；背景类→挖空色，文字/强调类→纯黑。
GHOST = {
    "name": "全透明",
    "family": FAMILY_RETRO,          # ghost 从默认 retro 家族抠出，保持 SKINS 键集全覆盖
    **{k: GHOST_PUNCH for k in (                 # —— 背景类：全挖空 ——
        "window_bg", "panel_bg", "list_bg", "icon_bg", "input_bg", "titlebar_bg",
        "msg_bg", "hover_bg", "glass_border",
        "bubble_in", "bubble_out", "bubble_inline", "bubble_outline",
        "hit", "hit_active", "react_bg", "sel_band",
        "pin_bg", "ann_bg", "voice_bg")},
    **{k: GHOST_BLACK for k in (                 # —— 文字/强调类：纯黑 ——
        "fg", "sub", "normal", "sys", "self", "priv", "accent",
        "titlebar_fg", "titlebar_btn", "titlebar_close", "selected_fg",
        "mention", "link", "mention_self", "link_self",
        "date", "read", "react_fg", "react_own", "unread", "sel_ring",
        "pin_fg", "ann_fg", "voice_fg")},
    # 几何 token：ghost 下保留原值（非颜色，不可挖空）
    "bubble_r": 10, "bubble_pad_h": 8, "bubble_pad_v": 5, "titlebar_h": 28,
    "traffic_lights": False,
}

# msg_list.COLORS 与主题 Token 的映射（get 时摘出传入 MsgList(colors=...)）
# 扩展键（mention/link/date/react_*/read/mention_self/link_self）仅在对应皮肤提供 token 时注入，
# 既有 SKINS 不含这些键 → msg_colors 过滤跳过，视觉零回归；GHOST 提供 → 全挖空。
MSG_TOKEN_MAP = {
    "bg": "msg_bg", "sys": "sys", "self": "self", "priv": "priv",
    "normal": "normal", "hit": "hit", "hit_active": "hit_active",
    "bubble_in": "bubble_in", "bubble_out": "bubble_out",
    "bubble_inline": "bubble_inline", "bubble_outline": "bubble_outline",
    "mention": "mention", "link": "link", "date": "date",
    "mention_self": "mention_self", "link_self": "link_self",
    "react_bg": "react_bg", "react_fg": "react_fg",
    "react_own": "react_own", "read": "read",
    "unread": "unread", "sel_band": "sel_band", "sel_ring": "sel_ring",
    # Apple 风格气泡几何（可选 token，msg_list set_colors 读取）
    "bubble_r": "bubble_r", "bubble_pad_h": "bubble_pad_h",
    "bubble_pad_v": "bubble_pad_v",
}


def names() -> list:
    return list(SKINS.keys())


# R41D 跟随系统深浅：浅色/深色分别落到这对 Apple 皮肤
SYSTEM_LIGHT_SKIN = "apple"
SYSTEM_DARK_SKIN = "apple_dark"

_SYS_THEME_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def system_prefers_dark() -> bool | None:
    """系统是否偏好深色应用（R41D）。

    读 HKCU…Themes\\Personalize 的 AppsUseLightTheme（0=深色）；
    非 Windows / 键值缺失 / 读失败 → None（调用方按浅色处理，但保留 None 区分）。
    """
    if os.name != "nt":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _SYS_THEME_KEY) as k:
            val, _t = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return int(val) == 0
    except OSError:
        return None


def display_name(name: str) -> str:
    s = SKINS.get(name)
    return s["name"] if s else (SKINS[DEFAULT_SKIN]["name"])


# ---------- 主题包抽象（family 家族字段） ----------
# 每套皮肤以 family 标注所属「整套主题包」视觉风格，仅作语义归组、供整站一键
# 切换时分主题包，不做结构化的多份 CSS。够用即止，不过度设计。
#   retro —— 暖粉手绘风（原五套 + 交互模式配色，默认主家族）
#   flat  —— 扁平极简冷灰风（浅灰/白卡/冷描边/单强调色，深色=墨蓝黑）
# 常量 FAMILY_RETRO / FAMILY_FLAT / FAMILY_KEY 已定义于文件顶部（SKINS 之前）。


def skin_family(name: str = "") -> str:
    """皮肤所属主题包家族；未知/空 → 默认 retro（兼容旧 prefs 无 family）。"""
    s = SKINS.get(name)
    if not s:
        return FAMILY_RETRO
    return str(s.get("family", FAMILY_RETRO))


FAMILY_KEY = "family"


def get_skin(name: str | None = None) -> dict:
    """按名字取皮肤 token 表；未知/空 → 回落到默认皮肤。"""
    s = SKINS.get(name)
    return dict(s) if s else dict(SKINS[DEFAULT_SKIN])


def surface(name: str | None = None) -> dict:
    """数值化密度/表面层：BASE 常量，皮肤若自定义则覆盖。"""
    sk = get_skin(name)
    val = dict(BASE)
    for k in ("scrim_alpha", "radius_window", "radius_small",
              "titlebar_h", "pad_x", "pad_y"):
        if k in sk:
            val[k] = sk[k]
    return val


def msg_colors(skin: dict) -> dict:
    """摘出 msg_list 需要的颜色子表（键名对齐 MsgList.COLORS）。"""
    return {k: skin[v] for k, v in MSG_TOKEN_MAP.items()
            if v in skin}


# ---------- 聊天主题（R??：气泡/聊天区配色叠层，独立于全局皮肤） ----------
# 键名对齐 msg_list.COLORS；"" = 不叠层（跟随皮肤默认）。只改聊天区与气泡，
# 不动全局窗口皮肤。每套覆盖：聊天区背景 bg、自己气泡 bubble_out、他人气泡
# bubble_in、描边 bubble_*/inline/outline、及相应文本 normal/self/priv/mention 等。
CHAT_THEMES = {
    # 薄荷：清爽薄荷气泡 + 浅奶绿聊天底
    "mint": {
        "name": "薄荷",
        "bg": "#eef7ef",
        "sys": "#7fa892",
        "self": "#ffffff",
        "priv": "#2f4a3c",
        "normal": "#2f4a3c",
        "bubble_in": "#ffffff",
        "bubble_out": "#4fc38d",
        "bubble_inline": "#dbeadd",
        "bubble_outline": "#bdebd3",
        "mention": "#1f9d63",
        "link": "#3ba676",
        "mention_self": "#d9f0e3",
        "link_self": "#d9f0e3",
        "date": "#7fa892",
        "react_bg": "#d9f0e3",
        "react_fg": "#2f4a3c",
        "react_own": "#4fc38d",
        "read": "#7fa892",
        "unread": "#e05a3a",
    },
    # 珊瑚：暖珊瑚气泡 + 米杏聊天底
    "coral": {
        "name": "珊瑚",
        "bg": "#fff3ed",
        "sys": "#c9957b",
        "self": "#ffffff",
        "priv": "#7a3d2a",
        "normal": "#6a3d2a",
        "bubble_in": "#ffffff",
        "bubble_out": "#ff8a5c",
        "bubble_inline": "#f2ddcf",
        "bubble_outline": "#ffc4a8",
        "mention": "#c06a3f",
        "link": "#ff8a5c",
        "mention_self": "#ffddc9",
        "link_self": "#ffddc9",
        "date": "#c9957b",
        "react_bg": "#ffe0ce",
        "react_fg": "#7a3d2a",
        "react_own": "#ff8a5c",
        "read": "#c9957b",
        "unread": "#e0555e",
    },
    # 暖粉：柔粉气泡 + 浅粉聊天底
    "peach": {
        "name": "暖粉",
        "bg": "#fff0f2",
        "sys": "#d496a6",
        "self": "#ffffff",
        "priv": "#7a2a3e",
        "normal": "#6b3140",
        "bubble_in": "#ffffff",
        "bubble_out": "#f7a8b8",
        "bubble_inline": "#f5dbe0",
        "bubble_outline": "#ffd6de",
        "mention": "#c0507a",
        "link": "#ec7ba0",
        "mention_self": "#ffdfe6",
        "link_self": "#ffdfe6",
        "date": "#d496a6",
        "react_bg": "#ffe4ea",
        "react_fg": "#7a2a3e",
        "react_own": "#f7a8b8",
        "read": "#d496a6",
        "unread": "#e0555e",
    },
    # 墨蓝：静谧深蓝气泡 + 淡雾蓝聊天底
    "ink": {
        "name": "墨蓝",
        "bg": "#eef1f8",
        "sys": "#95a4bc",
        "self": "#ffffff",
        "priv": "#2e3a52",
        "normal": "#2e3a52",
        "bubble_in": "#ffffff",
        "bubble_out": "#4a6fa5",
        "bubble_inline": "#dbe2ef",
        "bubble_outline": "#bdcbe0",
        "mention": "#3568b0",
        "link": "#4a6fa5",
        "mention_self": "#d9e2f5",
        "link_self": "#d9e2f5",
        "date": "#95a4bc",
        "react_bg": "#dfe7f6",
        "react_fg": "#2e3a52",
        "react_own": "#4a6fa5",
        "read": "#95a4bc",
        "unread": "#e0555e",
    },
}
DEFAULT_CHAT_THEME = ""


def chat_theme_names() -> list:
    """聊天主题键列表（含空字符串=跟随皮肤）。"""
    return [""] + list(CHAT_THEMES.keys())


def chat_theme_display(key: str) -> str:
    """聊天主题显示名；空/未知 → “跟随皮肤”。"""
    k = str(key or "")
    t = CHAT_THEMES.get(k)
    return t["name"] if t else "跟随皮肤"


def get_chat_theme(key: str) -> dict:
    """取聊天主题叠层字典；空/未知 → 空（不叠层，跟随皮肤默认）。"""
    t = CHAT_THEMES.get(str(key or ""))
    return dict(t) if t else {}


def _hex_mix(a: str, b: str, t: float) -> str:
    """按 t∈[0,1] 在 a（冷色）与 b（暖/白）之间线性混合，返回 #rrggbb。"""
    def ch(s):
        return (int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16))
    x, y = ch(a), ch(b)
    m = tuple(round(x[i] + (y[i] - x[i]) * t) for i in range(3))
    return f"#{m[0]:02x}{m[1]:02x}{m[2]:02x}"


def dialog_pal(skin: dict) -> dict:
    """R57：从皮肤 token 派生「对话框/独立面板」统一配色，供各类弹窗与
    独立窗口（桌游/协作/迷你条）使用。浅色主题观感与硬编码一致，深色
    主题自动换深色面，消除"除了聊天区都不换肤"。

    返回键：bg(面板主体) win(窗口) fg sub input accent border
            tab_bg tab_fg(条带/标签) doc_h(文档高亮) self priv。
    """
    bg = skin.get("panel_bg", "#ffffff")
    win = skin.get("window_bg", "#f5f5f7")
    input_bg = skin.get("input_bg", "#ffffff")
    border = skin.get("glass_border", "#d0d7de")
    dark = _is_dark(bg)
    if dark:
        # 深色面：条带/标签用略亮面板色，嵌套用略暗色
        return {
            "bg": bg, "win": win, "fg": skin.get("fg", "#ffffff"),
            "sub": skin.get("sub", "#8e8e93"),
            "input": input_bg, "accent": skin.get("accent", "#0a84ff"),
            "accent_fg": "#ffffff", "accent_hover": "#0056c2",
            "soft_bg": "#3a3a3c",
            "border": border,
            "tab_bg": "#3a3a3c", "tab_fg": "#ffffff",
            "tab_on_bg": "#4a4a4d", "card": "#38383a",
            "doc_h": "#48484a", "self": skin.get("sel_band", "#2a3950"),
            "priv": "#3ddbbb", "danger": "#e0555e",
            "warn_bg": "#3a3a30", "warn_fg": "#ffd95e",
        }
    return {
        "bg": bg, "win": win, "fg": skin.get("fg", "#333333"),
        "sub": skin.get("sub", "#8a8f98"),
        "input": input_bg, "accent": skin.get("accent", "#1a73e8"),
        "accent_fg": "#ffffff", "accent_hover": "#1259c7",
        "soft_bg": "#eef0f5",
        "border": border,
        "tab_bg": "#f0f0f0", "tab_fg": "#666666",
        "tab_on_bg": "#dfe6f0", "card": "#ffffff",
        "doc_h": "#c9cdd4", "self": skin.get("bubble_out", "#1a73e8"),
        "priv": "#0f766e", "danger": "#e03e3e",
        "warn_bg": "#fffbe6", "warn_fg": "#8d6e63",
    }


def _is_dark(hex_color: str) -> bool:
    """粗略亮度判定（用于派生对话框配色）。"""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
    except Exception:
        return False
    return (0.299 * r + 0.587 * g + 0.114 * b) < 128


def ghost_palette(back: float = 0.0) -> dict:
    """R15+：按字幕衬底深浅生成 ghost token 表。
    back=0 → 纯挖空（气泡色=挖空色，不可见，只剩黑字悬浮）；
    back 增大 → 气泡渐混向白底，黑字越清晰（配合 Ctrl+←/→ 调档）。"""
    pal = dict(GHOST)
    mix = _hex_mix(GHOST_PUNCH, "#ffffff", max(0.0, min(1.0, back)))
    for k in ("bubble_in", "bubble_out", "bubble_inline", "bubble_outline"):
        pal[k] = mix
    return pal
