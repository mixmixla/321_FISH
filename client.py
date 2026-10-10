# -*- coding: utf-8 -*-
"""client.py —— 唯一 GUI：隐秘聊天主窗 + 迷你条 + 表情条 + 频道/私聊/群聊。

设计原则（摸鱼场景）：
- 窗口标题/文案一律用无害办公词（内部办公助手），字体小、灰色调、布局紧凑
- 所有 UI 更新只在主线程（root.after 轮询 core.events，绝不在子线程碰 tk）
- 关窗 = 缩到迷你条（不退出）；迷你条右侧悬浮，鼠标右键退出
- 表情条：点表情 → 空输入框直接发"纯表情"，有输入则追加短代码 :code:
"""
import argparse
from copy import deepcopy
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog

import tkguard                      # 跨线程 Font/Image/Variable 销毁守卫（须在任何 Tk 创建前）

try:                                     # R19 语音播放：winsound 仅 Windows（可忽略）
    import winsound
except Exception:                        # pragma: no cover - 非 Windows
    winsound = None

from config import (APP_NAME, BOSS_SKIN_LABELS, BOSS_SKINS, CFG, CAMO_PRESETS,
                    FONT_FAMILY, FONT_SIZE,
                    MINI_H, MINI_W, STICKER_MAX_BYTES, WINDOW_H, WINDOW_W,
                    WEB_PORT,                     # R71：复制消息链接拼网页端地址
                    enable_crashlog, bootlog)

try:                                     # R48b：尽早开启动日志，覆盖后续重型导入崩溃留痕
    enable_crashlog()
except Exception:
    pass
from client_core import ClientCore
from bots import BOT_BY_UID              # R46：bot 命令注册表（补全/键盘判定）
from stickers import (STICKER_BY_CODE, expand_shortcodes,
                      is_valid_custom_code)
from discovery import DiscoveryClient
from hotkey import HotkeyManager, MOD_ALT
from boss import BossWindow
from prefs import (Prefs, StarsPreservationError, fish_add_day, fish_summary,
                   in_dnd_range, trim_stars)
from theme import (msg_colors, get_skin, names as skin_names,
                   display_name as skin_display, DEFAULT_SKIN,
                   GHOST, GHOST_PUNCH, GHOST_BLACK, ghost_palette,
                   dialog_pal,
                   chat_theme_names, chat_theme_display,
                   get_chat_theme as theme_chat_overlay)
from widgets.msg_list import MsgList, is_image_path
from widgets import rich                                      # R59：富文本解析
from widgets.thread_window import ThreadWindow   # R34 群内话题窗口
from widgets.call_window import CallWindow       # R38 语音通话窗口
from widgets.voice_room_window import VoiceRoomWindow  # R72 语音房窗口
from widgets.vmemo_player import VmemoPlayer    # R72 圆形视频留言播放器
from widgets.session_list import SessionList
from widgets.avatar import AvatarCache, set_default_frame   # R52：全局共享头像缓存；功能④ 全局默认相框
from widgets.excel_chrome import ExcelChrome         # Excel 工作簿风格主界面
from widgets.lightbox import Lightbox
from widgets.image_wall import ImageWall   # R69B5 会话图片墙（九宫格相册）
from widgets.task_panel import TaskPanel   # R69B6/B7 群待办/接龙/签到面板
from widgets.text_viewer import TextViewer
from widgets import ui_fx                         # R43A1 弹窗淡入/按压反馈
from widgets.design_controls import IconButton
from ui_design import body_font, color as design_color
from file_client import _hsize
import client_gameui                    # R: 桌游对局 Canvas 图形化渲染
import optional                          # R38B 可选依赖探测（vosk/翻译/rlottie）
import geo_api                           # R72 位置共享：坐标解析 + OSM 链接
import vmemo_api                        # R72 视频留言：VMA1 容器


# ---------- 交互模式（R交互：TG/微信/QQ 三选一，重启生效） ----------
# 标准三件套：发送键绑定 / 消息回执显示 / 会话列表布局密度。
READ_MARK_ALL = "✓已读  "        # tg/wechat 共用已读标记文案（现状）
# R-字号：聊天主体（消息区/会话列表/输入区）三档字体大小（中 = 系统默认 10pt）
_FONT_LABELS = ("小", "中", "大")
_FONT_SCALES = (9, 10, 12)
MODE_CONFIG = {
    "tg":     {"send": "enter",      "read_mark": READ_MARK_ALL,
               "layout": "tg",   "skin": "apple"},
    "wechat": {"send": "enter",      "read_mark": READ_MARK_ALL,
               "layout": "wechat", "skin": "wechat"},
    "qq":     {"send": "ctrl_enter", "read_mark": None,
               "layout": "qq",   "skin": "qq"},
}

# R69C12 群成员按在线状态分组：分组顺序与中文标题（点色复用 _status_color）
MEMBER_STATUS_ORDER = ("online", "away", "busy", "offline")
MEMBER_STATUS_LABEL = {"online": "在线", "away": "离开",
                       "busy": "忙碌", "offline": "离线"}

# R69B8 群文件库按类型过滤：扩展名 → 类别（image/doc/archive/other）
GF_KIND_EXTS = {
    "image": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".heic"),
    "doc": (".txt", ".md", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt",
            ".pptx", ".csv", ".json", ".log", ".py", ".js", ".html", ".xml"),
    "archive": (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"),
}
GF_KIND_LABELS = (("all", "全部"), ("image", "图片"),
                  ("doc", "文档"), ("archive", "压缩包"))


def gf_kind(name: str) -> str:
    """R69B8：群文件按扩展名归类（image/doc/archive/other）。"""
    ext = os.path.splitext(str(name or "").lower())[1]
    for k, exts in GF_KIND_EXTS.items():
        if ext in exts:
            return k
    return "other"


def _start_global_hotkey(manager) -> bool:
    """Start one global hotkey only when the process gate allows it."""
    if not CFG.global_hotkeys_enabled:
        return False
    return bool(manager.start())


# ---------- 剪贴板/截图 → 临时 PNG（Ctrl+V 粘贴、Alt+A 截图共用） ----------
def _save_image_temp(img) -> str:
    """把 PIL.Image 落到临时 PNG，返回路径；Pillow 缺失/写盘失败返回空串。"""
    try:
        import tempfile
        d = os.path.join(tempfile.gettempdir(), "moeyu_paste")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"paste_{int(time.time() * 1000)}.png")
        img.save(p, "PNG")
        return p
    except Exception:
        return ""


def _clipboard_paths_and_image():
    """读剪贴板 → (paths, img)。位图落临时 PNG；CF_HDROP 文件列表取真实路径。
    无可用内容 / PIL 缺失 → ([], None)，交由调用方放行默认文本粘贴。"""
    try:
        from PIL import ImageGrab
        data = ImageGrab.grabclipboard()
    except Exception:
        return [], None
    if isinstance(data, list):
        return [p for p in data if isinstance(p, str) and os.path.isfile(p)], None
    if data is not None and hasattr(data, "save"):
        p = _save_image_temp(data)
        return ([p], data) if p else ([], None)
    return [], None


# ---------- 快捷键注册表（r5b：可视化设置页可查看/改绑） ----------
# 每项：id（持久化键）/ desc（描述）/ default（Tk 事件模式）/ handler（self 上的方法名）。
# Ctrl+Alt+H 已被 boss 假 Excel 占用，注册时避开该组合。
SHORTCUTS = [
    {"id": "ctrl_w",  "desc": "隐藏到迷你条",         "default": "<Control-w>",  "handler": "hide_to_mini"},
    {"id": "ctrl_prev", "desc": "上一个会话",         "default": "<Control-Prior>", "handler": "_prev_chat"},
    {"id": "ctrl_next", "desc": "下一个会话",         "default": "<Control-Next>", "handler": "_next_chat"},
    {"id": "ctrl_j",  "desc": "打开在线名单",         "default": "<Control-j>",  "handler": "_focus_contacts"},
    {"id": "ctrl_e",  "desc": "编辑最后一条自己的消息", "default": "<Control-e>",  "handler": "_edit_last_own"},
    {"id": "ctrl_f",  "desc": "聊天内搜索",           "default": "<Control-f>",  "handler": "_focus_search"},
    {"id": "ctrl_shift_f", "desc": "全局搜索所有会话",   "default": "<Control-Shift-f>", "handler": "_focus_global_search"},
    {"id": "ctrl_g",  "desc": "跳到最早未读会话",     "default": "<Control-g>",  "handler": "_jump_unread"},
    {"id": "alt_prev_unread", "desc": "上一条未读会话", "default": "<Alt-Up>",   "handler": "_jump_unread_prev"},
    {"id": "alt_next_unread", "desc": "下一条未读会话", "default": "<Alt-Down>", "handler": "_jump_unread_next"},
    {"id": "ctrl_9",  "desc": "切换归档折叠区",       "default": "<Control-9>",  "handler": "_toggle_archived_panel"},
    {"id": "ctrl_r",  "desc": "标记当前会话已读",     "default": "<Control-r>",  "handler": "_mark_current_read"},
    {"id": "ctrl_shift_m", "desc": "静音/取消静音当前会话", "default": "<Control-Shift-m>", "handler": "_mute_current"},
    {"id": "ctrl_l",  "desc": "锁定（防偷窥）",       "default": "<Control-l>",  "handler": "lock_app"},
    {"id": "f1_ghost", "desc": "全透明黑字模式",      "default": "<F1>",         "handler": "toggle_ghost"},
    {"id": "ghost_back", "desc": "字幕衬底变浅(亮背景更清晰)", "default": "<Control-Left>", "handler": "ghost_back_inc"},
    {"id": "ghost_backd", "desc": "字幕衬底变深(回到纯透黑字)", "default": "<Control-Right>", "handler": "ghost_back_dec"},
    {"id": "ghost_filter", "desc": "字幕过滤循环(全部/公聊/@我)", "default": "<F2>",        "handler": "ghost_cycle_filter"},
    {"id": "ghost_halo",   "desc": "字幕黑字描边开关(亮暗背景可读)", "default": "<F3>",        "handler": "ghost_toggle_halo"},
]

GHOST_N = 12                     # R15：全透明黑字模式字幕显示的全局最近消息条数
GHOST_TTL = 10.0                 # R15+：字幕停留时长（秒），到期无新消息自动清空
GHOST_BACK_STEP = 0.12           # R15+：Ctrl+←/→ 每次调节的衬底深浅增量
GHOST_HALO = "#ffffff"           # R17：字幕黑字描边光晕色（白，亮/暗背景都清晰）
GHOST_FADE = 0.35                # R17：字幕 TTL 到期淡出时长（秒）
GHOST_FADE_STEPS = 12            # R17：淡出动画分帧数
GHOST_CLICK_THROUGH = True       # R17：字幕悬浮窗点击穿透（不抢后台焦点/点击）
GHOST_DEFAULT_HALO = True        # R17：进入 ghost 默认开启描边光晕

_MOD_LABELS = {"Control": "Ctrl", "Shift": "Shift", "Alt": "Alt"}
_KEYSYM_LABELS = {"Prior": "PgUp", "Next": "PgDn", "Return": "Enter"}

# R29D 表情回应扩展：多分类内置表情集（悬浮条"＋"选择器；"常用"分类动态取最近使用）
REACT_GROUPS = [
    ("表情", ["😀", "😄", "😁", "😆", "🤣", "😅", "😇", "😊",
              "😍", "🤩", "😘", "😜", "🤪", "😝", "🥰", "😎"]),
    ("手势", ["👏", "🙌", "👌", "✌️", "🤞", "👍", "👎", "✊",
              "👊", "🤝", "💪", "🫶", "🤙", "☝️", "🖐️", "🙏"]),
    ("动物", ["🐶", "🐱", "🐰", "🦊", "🐻", "🐼", "🐨", "🐯",
              "🦁", "🐮", "🐷", "🐸", "🐵", "🦄", "🐔", "🐧"]),
    ("食物", ["🍎", "🍕", "🍔", "🍟", "🍜", "🍰", "🍩", "🍪",
              "☕", "🍺", "🍉", "🍇", "🍒", "🥤", "🍦", "🍿"]),
    ("符号", ["⭐", "🌟", "✨", "💯", "💥", "🌈", "☀️", "🌙",
              "⚡", "🎯", "🏆", "🥇", "💎", "🔥", "🎈", "🎁"]),
]
REACT_RECENT_MAX = 5        # R29D 悬浮条最近使用最多展示数（含默认 QUICK_EMOJIS 兜底）
FAV_STICKER_MAX = 12        # R32B2 贴纸收藏上限（贴纸条单行，防止溢出）
STICKER_RECENT_MAX = 8      # 表情/贴纸「最近使用」最多展示数（去重前置，prefs 持久化）
STICKER_GIF_MS = 90         # R64 选择器内 GIF 贴纸缩略图帧切换间隔（ms）
STICKER_GIF_FRAMES = 12     # R64 缩略图抽帧上限（22px 小图，无需全帧）
STICKER_TRIAL_MAX = 8       # R64 未订阅包「试看」最多展示条目数


def _pattern_label(pattern: str) -> str:
    """`<Control-Prior>` -> `Ctrl+PgUp`；为「查看快捷键」提供人类可读文案。"""
    if not pattern:
        return "（已禁用）"
    p = pattern.strip("<>")
    mods, key = (p.split("-")[:-1], p.split("-")[-1]) if "-" in p else ([], p)
    parts = [_MOD_LABELS.get(m, m) for m in mods]
    ky = key if not key.islower() else key.upper()
    ky = _KEYSYM_LABELS.get(key, ky)
    return "+".join(parts + [ky])


def _event_to_pattern(ev) -> str:
    """键盘捕获事件 → Tk 绑定模式；仅打包修饰键 + 单键，避免覆盖输入框普通键入。"""
    mods = []
    if ev.state & 0x4:
        mods.append("Control")
    if ev.state & 0x1:
        mods.append("Shift")
    if ev.state & 0x8:
        mods.append("Alt")
    key = ev.keysym
    if len(key) == 1:
        key = key.lower()
    if not mods and not key:        # 无修饰也无键：忽略
        return ""
    return "<" + "-".join(mods + [key]) + ">"


def _now_str() -> str:
    return time.strftime("%H:%M:%S")


# Hold 回车自动重复的最小发送间隔（秒）：防误触连发相同消息（TG 同思路节流发送）。
_ENTRY_SEND_GAP = 0.6
_HIST_N = 20                 # R12：每个会话保留的输入历史条数（对齐 TG 上限）


def _flash_window(hwnd: int) -> None:
    """Windows 任务栏闪烁（FlashWindowEx / FLASHW_ALL）。非 Windows 环境静默跳过。"""
    import ctypes
    import platform
    if platform.system() != "Windows" or not hwnd:
        return
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        class FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint),
                        ("hwnd", ctypes.c_void_p),
                        ("dwFlags", ctypes.c_uint),
                        ("uCount", ctypes.c_uint),
                        ("dwTimeout", ctypes.c_uint)]

        FLASHW_ALL = 0x00000003
        fi = FLASHWINFO(ctypes.sizeof(FLASHWINFO), int(hwnd),
                        FLASHW_ALL, 0, 0)
        user32.FlashWindowEx(ctypes.byref(fi))
    except Exception:
        pass                      # 非交互/无桌面上层环境：闪烁失败可忽略


def _make_draggable(win, threshold=0):
    """让浮层窗口可被鼠标拖动移动。threshold>0 时按下超过 3px 才视为拖动
    （给带点击事件的浮层用，避免点击与拖动冲突）。失败静默降级。"""
    st = {"ax": None, "ay": None, "wx": None, "wy": None, "dx": 0, "dy": 0}
    def _nodes(w):
        yield w
        for c in w.winfo_children():
            yield from _nodes(c)
    def _curs(w, c):
        for top in (w, getattr(w, "master", None)):
            try:
                top.config(cursor=c)
            except Exception:
                pass
    def _press(e):
        # 只读一次初始坐标 + 初始鼠标位；后续移动纯累加鼠标位移（不重复读 winfo_x，
        # 否则拖动中系统返回旧坐标会被拉回 / 飘）。参考主窗 TitleBar 的稳健写法。
        st["ax"], st["ay"] = e.x_root, e.y_root
        try:
            st["wx"], st["wy"] = win.winfo_x(), win.winfo_y()
        except Exception:
            st["wx"] = st["wy"] = None
        st["dx"] = st["dy"] = 0
        _curs(e.widget, "fleur")          # 拖动时指针变移动图标，示意可拖
    def _mv(e):
        if st["ax"] is None or st["wx"] is None:
            return
        dx = e.x_root - st["ax"]; dy = e.y_root - st["ay"]
        if threshold and abs(dx) <= 3 and abs(dy) <= 3:
            return
        _curs(e.widget, "fleur")
        nwx = st["wx"] + dx; nwy = st["wy"] + dy
        try:
            win.geometry(f"+{nwx}+{nwy}")
        except Exception:
            pass
    def _rel(e):
        _curs(e.widget, "")               # 松开恢复默认指针
    try:
        for n in list(_nodes(win)):
            try:
                n.bind("<Button-1>", _press, add="+")
                n.bind("<B1-Motion>", _mv, add="+")
                n.bind("<ButtonRelease-1>", _rel, add="+")
            except Exception:
                pass
    except Exception:
        pass


class ChatWindow:
    """聊天主窗（含迷你条联动）"""

    def __init__(self, core: ClientCore, *, prefs_path: str | None = None) -> None:
        self.core = core
        self.view = ("public", None)       # (channel, target)  target=uid|gid
        self._closed = False
        self._exit_reason = "quit"          # R8 launcher 退出语义："quit"|"switch"
        self._mini = None
        # GAME-UI-01：收起/伪装事务的窗口身份快照。只在最外层进入时捕获，
        # 迷你条与老板键嵌套不能覆盖；恢复只还原仍存在且此前可见的对象。
        self._collapse_snapshot = None
        self._sticker_row = None
        self._sticker_on = False
        # C5/C6：未读计数 + 本地偏好（置顶）+ 搜索过滤
        self._prefs = Prefs(prefs_path)
        self._unread: dict = {}            # (ch, to) -> 未读数
        self._preview: dict = {}           # (ch, to) -> (末条摘要, ts)（T4 会话预览）
        self._list_dirty = False           # 名单/群需按未读/置顶重绘
        self._members_dlg = None           # C8 成员管理对话框（{gid,reload,dlg}）
        self._shop_dlg = None              # R35 贴纸商店窗口（StickerShop）
        # R64 贴纸包深化：包导航条 / 当前选中包（""=最近，"p:包名"=自定义，"s:pack_id"=内置）
        self._sticker_nav = None
        self._sticker_pack_sel = ""
        self._stk_gif_job = None           # 选择器 GIF 预览轮播定时器
        self._stk_gif_btns: dict = {}      # 按钮 -> [PhotoImage 列表, 当前帧下标]
        self._dnd = bool(self._prefs.get("dnd", False))    # C7 免打扰开关
        # R14：收藏/星标（key->{seq:快照}）；快捷短语；定时发送队列；阅后即焚模式
        self._stars = dict(self._prefs.get("stars", {}) or {})
        self._quick = list(self._prefs.get("quick", []) or [])
        self._scheduled: list = []
        self._sched_dlg = None               # R51：定时管理窗（打开时 SCHED_LIST 同步刷新）
        self._sched_reload = None
        # R51：定时消息改为服务器权威托管——本地不落盘，登录后由 SCHED_LIST 同步
        self._burn_mode = bool(self._prefs.get("burn_mode", False))
        # R30A 未读分隔线：各会话"读到哪条"（pin_key -> seq；切走/标记已读时记录）
        self._last_read: dict = {}
        # R30D 回应详情提示（药丸 hover 的小 Toplevel，None=未显示）
        self._react_tip = None
        # R26C 静默发送：🔕 开关（发送免通知，未读照常）；R26B 频道只读态
        self._silent_mode = bool(self._prefs.get("silent_mode", False))
        # R70E 消息伪装：当前风格（"" = 关闭；否则 ∈ CFG.disguise_styles）
        _dm = str(self._prefs.get("disguise_mode", "") or "")
        self._disguise_mode = _dm if _dm in CFG.disguise_styles else ""
        # R70F 敏感词打码：本地词表 / 开关 / 时段（纯显示层，默认关；不影响存储与搜索）
        self._guard_on = bool(self._prefs.get("guard_on", False))
        self._guard_words = [str(w) for w in (self._prefs.get("guard_words")
                                              or CFG.guard_words_default or [])
                             if str(w).strip()]
        self._guard_hours = str(self._prefs.get("guard_hours",
                                                CFG.guard_hours_default) or "")
        # R70G 忙碌自动回复：仅伪装态（老板键）下对 1v1 首条消息自动应答（纯本地，默认关）
        self._auto_reply_on = bool(self._prefs.get("auto_reply_on", False))
        self._auto_reply_text = str(self._prefs.get("auto_reply_text",
                                                    "我在忙，稍后回复你～") or "")
        try:
            self._auto_reply_cd = float(self._prefs.get(
                "auto_reply_cooldown", CFG.auto_reply_cooldown))
        except (TypeError, ValueError):
            self._auto_reply_cd = float(CFG.auto_reply_cooldown)
        self._auto_reply_at: dict = {}         # uid → 上次自动回复时间（冷却用，会话内内存）
        # R70H 摸鱼排行榜：opt-in 上报（默认关；开启后每结束一局向服务器累加 1 分）
        self._fish_upload = bool(self._prefs.get("fish_upload", False))
        self._fish_last_state = None
        self._fish_board_game = ""             # 排行榜面板当前选中的游戏名
        self._ro_mode = False
        # T3 主题：皮肤名持久化于 prefs['skin']，默认 office 办公灰蓝
        # R41D：开启「跟随系统深浅」时按注册表解析 apple / apple_dark
        self._skin_name = self._prefs.get("skin", DEFAULT_SKIN)
        if self._prefs.get("skin_follow_system"):
            self._skin_name = self._resolve_system_skin()
        # R交互：交互模式（TG/微信/QQ），重启生效；提前存 cfg 供各层消费
        self._mode = self._prefs.get("interaction_mode", "tg")
        self._mode_cfg = MODE_CONFIG.get(self._mode, MODE_CONFIG["tg"])
        self._settings_win = None              # R交互：内嵌全屏设置面板（懒建）
        # 主窗半透明（T7 扩展：chat/消息背景透出桌面玻璃感，0.6~1.0；R55F5 默认抬到 0.95，
        #   原 0.78 在浅色壁纸上会让桌面图标/纹理透过窗口与消息文字"叠"在一起难辨认）
        self._chat_alpha = float(self._prefs.get("chat_alpha", 1.0))
        self._skin = get_skin(self._skin_name)
        self._dp = dialog_pal(self._skin)   # R57：对话框/独立面板派生配色
        ui_fx.set_sound(CFG.hardware_enabled and
                        self._prefs.get("ui_sound", False))  # 界面反馈音（默认关，prefs 可开）
        # R29D 表情回应：最近使用（去重前置，最多 REACT_RECENT_MAX 个），驱动悬浮条快捷集
        self._recent_reacts = [str(e) for e in (self._prefs.get("react_recent") or [])
                               if str(e)][:REACT_RECENT_MAX]
        # R32B2 贴纸收藏：贴纸条最前展示（内置 code / 自定义 code 均可），prefs 持久化
        self._fav_stickers = [str(c) for c in (self._prefs.get("fav_stickers") or [])
                              if str(c)][:FAV_STICKER_MAX]
        # 表情/贴纸「最近使用」：用过的 emoji/贴纸置前，prefs 持久化
        self._recent_stickers = [str(c) for c in (self._prefs.get("sticker_recent") or [])
                                 if str(c)][:STICKER_RECENT_MAX]
        # 群文件库：窗口/上传/下载会话状态
        self._gf_dlg = None          # {"gid","dlg","lb","records"}
        self._gf_upload = {}         # {"gid","fid","path","size","off","fh"}
        self._gf_download = {}       # fid -> {"fh","size","written","path"}
        self._album_dlg = None       # R69B5：图片墙窗口（同一时间只维护一个）
        self._task_dlg = None        # R69B6/B7：群任务面板（同一时间只维护一个）
        self._ghost = False                    # R15：是否处于全透明黑字模式
        self._ghost_cache = {}                 # R15：透明模式下被强改色的 (widget->(bg,fg)) 缓存
        self._ghost_back = 0.0                 # R15+：字幕衬底深浅（0=纯透黑字，1=白底）
        self._ghost_after = None               # R15+：字幕停留 TTL 定时器 id
        self._ghost_filter = "all"             # R15+：字幕频道过滤（all/public/atme）
        self._FILTER_ORDER = ("all", "public", "atme")
        self._ghost_halo_on = bool(GHOST_DEFAULT_HALO)   # R17：字幕描边光晕开关
        self._ghost_fade_job = None            # R17：字幕淡出动画定时器
        self._ghost_click_thru = False         # R17：当前是否已置点击穿透
        self._archived_show = False        # 归档折叠区是否展开
        self._archived_keys: list = []     # 归档区当前 key（与列表行对齐）
        self._search = ""
        self._roster_order: list = []      # listbox idx -> uid
        self._group_order: list = []       # listbox idx -> gid
        # R25A/B：会话标题基础文案（无正在输入后缀）+ 轮询计数；R25D 当前文件夹
        self._chan_base = "公共频道"
        self._typing_ticks = 0
        self._active_folder: str | None = None   # 当前会话文件夹名（None=全部）
        # R34 群内话题：根 seq → 回复数徽标计数 + 当前打开的话题窗口
        self._thread_counts: dict = {}     # root_seq -> n
        self._thread_win = None            # ThreadWindow | None（同开一个）
        self._call_win = None              # CallWindow | None（R38 语音通话，同开一个）
        self._voice_room_win = None        # VoiceRoomWindow | None（R72 语音房，同开一个）
        self._vmemo_players = []           # R72 视频留言播放窗（可同时开多个）
        self._vmemo_rec = None             # R72 视频留言录制器
        self._geo_live_active = False       # R72 实时位置共享进行中
        self._geo_live_session = ""         # R72 实时位置共享会话标识
        self._geo_live_markers = {}         # R72 优化：(channel,to) -> {uid: {lat,lon,name,expire}}
        self._geo_live_self = False         # R72 优化：本端是否正在共享（标题打勾）
        # R39A 通话模式：prefs['call_duplex']（默认开全双工）应用到 CallManager
        self.core.calls.set_duplex(
            bool(self._prefs.get("call_duplex", True)))
        # R39B 云同步会话状态：本地变更时间戳 + 注入云备份采集/应用钩子
        # （cloud_upload/restore 在工作线程跑 → 应用侧 after 回主线程再动 UI）
        self._conv_state_ts: dict = {}     # pin_key -> 最近一次本地状态变更 ts
        self.core.set_conv_state_hooks(
            self._collect_conv_states,
            lambda states: self.root.after(
                0, lambda: self._apply_conv_states(states)))
        # C4/C3：待发引用快照 + 待编辑的自家消息 seq
        self._pending_reply = None         # {nick,text,seq}
        self._pending_edit_seq = None      # int|None
        self._pending_rows = []            # P0 三态：本地乐观行 raw dict（发送中 → 服务器确认后移除）
        self._last_send = 0.0              # D：发送节流（防 Hold 回车连发）
        # R12：输入历史回显 —— 按会话存已发送文本（每会话最近 _HIST_N 条）
        self._send_hist: dict = {}         # key -> [text,...]（新→旧序）
        self._hist_pos: dict = {}          # key -> 当前浏览下标（-1=未浏览）
        self._hist_draft: dict = {}        # key -> 进入浏览前的输入内容（↓ 回退恢复）
        self._hist_cur = None              # 当前浏览的会话 key
        # R12：草稿自动保存 —— 会话级（内存）+ 持久化（prefs['drafts'] dict）
        self._drafts: dict = dict(self._prefs.get("drafts", {}) or {})
        # R29B 草稿同步：本地最后保存时间 / 服务器已知时间（按会话键），按 ts 合并取新
        self._draft_ts: dict = {}
        self._remote_ts: dict = {}
        self._draft_dirty = False              # 输入变化待推送标记（_poll 节流 1.2s）
        self._draft_ticks = 0
        # R10 运行时锁屏状态（隐藏主窗 + 全屏 LockOverlay 防任务栏偷窥）
        self._locked = False
        self._lock_overlay = None
        self._build()
        self.root.title(APP_NAME)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_mini)
        self._bind_shortcuts()
        self._bind_autocomplete()            # B5 @提及/emoji 补全
        # 阶段3 自动发现 + 阶段5 快速隐藏（热键 + 假 Excel 窗）
        # REL-01：发现是可关闭的进程级能力。保留显式 host/port 的
        # ClientCore 配置，不在关闭时以任何候选覆盖它。
        self._disco = None
        if CFG.discovery_enabled:
            try:
                self._disco = DiscoveryClient(CFG)
                self._disco.start()
            except Exception:
                self._disco = None
        self._hotkey = HotkeyManager()
        self._hotkey_ok = _start_global_hotkey(self._hotkey)
        # Alt+A 区域截图即发（修饰键不同，与 Ctrl+Alt+H 不冲突；失败静默降级）
        self._shot_hotkey = HotkeyManager(mods=MOD_ALT, vk=0x41,
                                          hotkey_id=0x1338, desc_text="Alt+A")
        self._shot_hotkey_ok = _start_global_hotkey(self._shot_hotkey)
        self._snip = None                  # 进行中的截图选框（防重入）
        # R69A：多套伪装皮肤（记住上次所选；右键菜单/F2 轮换后持久化）
        self._boss = BossWindow(
            self.root,
            skin=str(self._prefs.get("boss_skin", "excel") or "excel"),
            on_cycle=lambda s: self._prefs.set("boss_skin", s))
        self._disco_target = None          # 已自动切换过的 (ip, port)，防抖动
        self._disco_ticks = 0
        # R31D B1：隐身友好 Toast + 系统托盘（pystray 缺失则降级为仅任务栏闪烁）
        from widgets.stealth_toast import StealthToast
        self._toast = StealthToast(self.root)
        self._tray = None
        if CFG.tray_enabled:
            try:
                from widgets.tray import Tray
                _stop_early_tray()             # 登录完毕：移除早期占位托盘，换正式托盘
                self._tray = Tray(self.root, on_show=self.show_main,
                                  on_boss=self._toggle_boss,
                                  on_ghost=self.toggle_ghost,
                                  on_quit=self.quit_app,
                                  tip=self._camo_title()) # R46：托盘跟随伪装
            except Exception:
                self._tray = None
        self._apply_camo()                   # R46：伪装标题启动即生效
        self._sys_theme_after = None         # R41D 系统深浅轮询定时器
        self.root.after(120, self._poll)
        self.root.after(2000, self._poll_sys_theme)   # R41D：2s 探测系统深浅
        self.root.after(1500, self._schedule_lastonline_refresh)  # R63：最后在线相对时间低频刷新

    # ---------- UI 搭建 ----------
    def _build(self) -> None:
        from dpi import apply_early
        dpi_enabled = bool(self._prefs.get('dpi_aware', True))
        apply_early(dpi_enabled)
        self.root = tk.Tk()
        self._set_default_colors()               # R57B：root 就绪后接入控件默认皮肤（须在 root 创建后）
        from dpi import fix_scaling           # R43C 高分屏：声明后按真实 DPI 校正
        self._dpi_scale = fix_scaling(self.root, enabled=dpi_enabled)
        _dpi_scale = self._dpi_scale
        self.root.geometry(f"{int(max(WINDOW_W, 960) * _dpi_scale)}x{int(max(WINDOW_H, 680) * _dpi_scale)}")
        self.root.minsize(int(680 * _dpi_scale), int(480 * _dpi_scale))
        # 半透明玻璃感（chat_alpha 0.6~1.0，受设置页滑杆调整并持久化；默认 0.95 保证可读）
        self.root.attributes("-alpha", self._chat_alpha)
        # R8 无边框玻璃窗（Frameless + DWM 圆角；MOYU_FRAMELESS=0 逃生关闭）
        self._frameless = False
        if (os.name == "nt"
                and os.environ.get("MOYU_FRAMELESS", "1") != "0"
                and self._prefs.get("frameless", True)):
            self._frameless = True
            self.root.overrideredirect(True)
        f = body_font()
        self._f = f
        self._design_buttons = []
        self._navigation_buttons = {}
        if self._frameless:
            from widgets.title_bar import TitleBar
            self.title_bar = TitleBar(self.root, self, f)
            self.title_bar.pack(fill="x")
            self._apply_dwm_corner()
        else:
            self.title_bar = None
        # Excel 皮肤的功能区/公式栏/工作表标签。先隐藏构造，待状态条创建后
        # 设置锚点，确保运行时从旧皮肤切回来时仍插在标题栏与状态条之间。
        self._excel_chrome = ExcelChrome(
            self.root, self, f, visible=False)
        self.root.title(APP_NAME)

        # 状态条
        sk = self._skin
        top = tk.Frame(self.root, bg=sk["window_bg"])
        self._status_bar_frame = top
        top.pack(fill="x", padx=12, pady=(6, 4))
        self._excel_chrome.set_anchor(top)
        self._excel_chrome.set_visible(self._skin_name == "excel")
        self.status_dot = tk.Label(top, text="○", fg=sk["sub"], font=f,
                                   bg=sk["window_bg"])
        self.status_dot.pack(side="left")
        self.status_text = tk.Label(top, text="正在连接…", fg=sk["sub"], font=f,
                                    bg=sk["window_bg"])
        self.status_text.pack(side="left", padx=(2, 0))
        self._top_btns = []
        for icon, txt, cmd in (("minimize", "收起", self.hide_to_mini),
                              ("game", "桌游", self.open_game),
                              ("settings", "设置", self._on_settings)):
            b = IconButton(top, icon=icon, text=txt, command=cmd,
                           palette=sk, scale=_dpi_scale, pady=3)
            b.pack(side="right", padx=(4, 0))
            self._top_btns.append(b)
            self._design_buttons.append(b)

        # 主体：左侧名单/群 + 右侧会话
        body = tk.Frame(self.root, bg=sk["window_bg"])
        self._body_frame = body
        if self._skin_name == "excel":
            body.configure(highlightthickness=1,
                           highlightbackground=sk.get("glass_border", "#d0d7de"))
        body.pack(fill="both", expand=True, padx=6, pady=2)
        self._build_left(body)
        self._build_right(body)
        self.root.bind('<FocusIn>', self._navigation_focus, add='+')
        self._apply_skin(persist=False)
        self.msg_list.set_grid(sk["glass_border"] if self._skin_name == "excel" else None)
        self._sync_excel_layout()
        # R-字号：会话/消息/输入三个控件已就绪，注入持久化的聊天主体字号
        # （只缩放聊天主体，顶栏/按钮等仍用 FONT_SIZE 默认字号）
        self._apply_font_scale()
        # R32A1 拖拽发送（失败静默降级为仅 📎 按钮）
        try:
            from widgets.dropfiles import enable_dropfiles
            enable_dropfiles(self.root, self._on_drop_files)
        except Exception:
            pass
        # R56 无边框主窗：边缘 6px 拖动缩放（消除 overrideredirect 无法缩放的死角）
        try:
            from widgets.dropfiles import enable_edge_resize
            enable_edge_resize(self.root)
        except Exception:
            pass

    def _build_left(self, body) -> None:
        sk = self._skin
        # R52：全局共享头像缓存（图标栏/会话列表/消息列表共用一份）
        self._avatars = AvatarCache()
        # 功能④ 头像相框：从 prefs 读取样式并注入全局默认（所有共享缓存统一生效）
        set_default_frame(self._prefs.get("avatar_frame") or "none")
        icon_bg = sk.get("icon_bg", sk["list_bg"])
        # ① 60px 图标栏（微信/Telegram 三栏最左列；R56 高 DPI 下列宽随窗缩放）
        self.icon_bar = tk.Frame(body, width=int(76 * self._dpi_scale), bg=icon_bg)
        self.icon_bar.pack(side="left", fill="y")
        self.icon_bar.pack_propagate(False)
        # 自己的圆形头像（点击 → 个人资料窗口；登录后画图/首字）
        self.icon_avatar = tk.Canvas(self.icon_bar, width=int(40 * self._dpi_scale),
                                     height=int(40 * self._dpi_scale),
                                     bg=icon_bg, highlightthickness=0)
        self.icon_avatar.pack(pady=(10, 4))
        self.icon_avatar.bind("<Button-1>", lambda e: self._on_profile())
        self.icon_avatar.bind("<Button-3>", lambda e: self._on_profile())
        # 导航图标（微信风格纵向排布）
        for icon, tip, cmd in (("chat", "消息", lambda: self._switch_view('public', None)),
                              ("people", "联系人", self._open_contacts_panel),
                              ("game", "桌游", self.open_game),
                              ("moments", "动态", self._open_moments)):
            b = IconButton(self.icon_bar, icon=icon, text=tip,
                           command=lambda key=icon, action=cmd:self._navigate(key, action),
                           palette=sk, role='navigation', scale=self._dpi_scale,
                           compound='top', padx=6, pady=8)
            b.pack(fill='x', padx=6, pady=3)
            self._design_buttons.append(b)
            self._navigation_buttons[icon] = b
            if icon == 'chat':
                b._nav_selected = True
                b.set_palette(sk)
            if icon == "moments":
                self._mom_btn = b                # R68：朋友圈入口（挂红点）
        # R68 朋友圈互动红点：未读数角标（红底白字，>0 时显示）
        self._mom_unread = 0
        self._mom_sig: dict = {}                 # pid -> (likes 集合, 评论条数)
        self._mom_badge = tk.Label(self.icon_bar, text="", bg="#e5484d",
                                   fg="#ffffff", font=(FONT_FAMILY, 7, "bold"),
                                   bd=0, padx=3, pady=0)
        self.icon_bar.bind("<Configure>", lambda e: self._update_mom_badge())
        # 底部菜单按钮（设置/资料入口）
        settings_button = IconButton(self.icon_bar, icon='settings', text='设置',
                                     command=lambda:self._navigate('settings',self._on_settings), palette=sk,
                                     role='navigation', scale=self._dpi_scale,
                                     compound='top', padx=6, pady=8)
        settings_button.pack(side='bottom', fill='x', padx=6, pady=8)
        self._design_buttons.append(settings_button)
        self._navigation_buttons['settings'] = settings_button
        # ② 中间列表列（原名单/群内容，宽 250；R56 随 DPI 缩放）
        left = tk.Frame(body, width=int(244 * self._dpi_scale), bg=sk["list_bg"])
        self._session_frame = left
        left.pack(side="left", fill="y", padx=(0, 4))
        left.pack_propagate(False)
        f = self._f
        tk.Label(left, text="消息", fg=sk["fg"], font=(body_font()[0], 14, 'bold'), anchor="w",
                 bg=sk["list_bg"]).pack(fill="x", padx=12, pady=(14, 10))
        # R25D 会话文件夹标签行（全部/各文件夹/＋新建）
        self._folder_bar = tk.Frame(left, bg=sk["list_bg"])
        self._folder_bar.pack(fill="x", padx=12, pady=(0, 8))
        self._rebuild_folder_bar()
        # C1/C6 搜索框：实时过滤名单/群（Ctrl+F 聚焦）
        self.search_entry = tk.Entry(left, font=f,
                                     bg=sk["input_bg"], fg=sk["fg"],
                                     insertbackground=sk["fg"],
                                     relief="flat",
                                     highlightthickness=1,
                                     highlightbackground=sk["glass_border"])
        self.search_entry.pack(fill="x", padx=12, pady=(0, 10), ipady=6)
        self.search_entry.bind("<KeyRelease>",
                               lambda e: (setattr(self, "_search",
                                                  self.search_entry.get().strip().lower()),
                                          self._refresh_lists()))
        # T5/T6 会话列表：两行 Canvas 布局（头像+名称/预览+时间/未读角标）
        # roster 是唯一的弹性控件（absorb 底部归档区推开/收起），最小自高度 2 行；
        # group 固定高、自带滚动。总请求高须远小于窗口高，否则归档区无空间可挤。
        self.roster_list = SessionList(
            left, font=self._f, height=2 * 56, on_pick=self._on_pick_roster,
            avatars=self._avatars, layout=self._mode_cfg["layout"],
            scale=self._dpi_scale,
            on_act=self._on_roster_hover_act,   # R-：hover 快捷操作
            on_avatar_dbl=self._shake_roster)   # R68：双击头像 → 窗口抖动
        self.roster_list.pack(fill="both", expand=True)
        self.roster_list.bind("<Button-3>", self._on_roster_menu)   # B3 会话右键
        tk.Label(left, text="群", fg=sk["sub"], font=f, anchor="w",
                 bg=sk["list_bg"]).pack(fill="x")
        self.group_list = SessionList(
            left, font=self._f, height=3 * 56, on_pick=self._on_pick_group,
            avatars=self._avatars, layout=self._mode_cfg["layout"],
            scale=self._dpi_scale,
            on_act=self._on_group_hover_act,   # R-：hover 快捷操作
            on_avatar_dbl=self._shake_group)   # R68：双击头像 → 窗口抖动
        self.group_list.pack(fill="x", pady=(0, 2))
        self.group_list.bind("<Button-3>", self._on_group_menu)     # B3 会话右键
        btns = tk.Frame(left, bg=sk["list_bg"])
        btns.pack(fill="x", pady=(2, 0))
        self._left_btns = []
        for txt, cmd in (("建群", self._on_create_group),
                         ("加群", self._on_join_group),
                         ("退群", self._on_leave_group)):
            b = tk.Button(btns, text=txt, command=cmd,
                          font=f, relief="flat", padx=2,
                          fg=sk["accent"], bg=sk["list_bg"])
            b.pack(side="left")
            self._left_btns.append(b)
        # C6 归档折叠区（"已归档" 开关按钮，Ctrl+9 也可切换）
        self._arch_btn = tk.Button(left, text="已归档 ▾", command=self._toggle_archived_panel,
                                   font=f, relief="flat", padx=2, anchor="w",
                                   fg=sk["sub"], bg=sk["list_bg"])
        self._arch_btn.pack(fill="x")
        self._archived_list = tk.Listbox(left, height=4, font=f,
                                         exportselection=False,
                                         bg=sk["list_bg"], fg=sk["fg"],
                                         selectbackground=sk["accent"],
                                         selectforeground="#ffffff",
                                         relief="flat",
                                         highlightthickness=0)
        self._archived_list.bind("<<ListboxSelect>>", self._on_archived_select)
        self._archived_list.bind("<Double-Button-1>", self._open_archived)
        self._archived_list.bind("<Button-3>", self._on_archived_menu)
        self._archived_list.pack_forget()

    def _select_navigation(self, key):
        for name, button in getattr(self, '_navigation_buttons', {}).items():
            button._nav_selected = name == key
            button.set_palette(self._skin)

    def _navigate(self, key, action):
        action()
        self._select_navigation(key)

    def _navigation_focus(self, event):
        if event.widget is self.root:
            settings = getattr(self, '_settings_win', None)
            active = settings is not None and settings.winfo_exists() and settings.winfo_ismapped()
            self._select_navigation('settings' if active else 'chat')

    def _navigation_dialog_closed(self, event, dialog):
        if event.widget is dialog and not self._closed:
            self._select_navigation('chat')

    def _sync_excel_layout(self, is_excel=None) -> None:
        """Excel 使用工作表中心区域；其它皮肤与原聊天视图复用原控件。"""
        chrome = getattr(self, "_excel_chrome", None)
        body = getattr(self, "_body_frame", None)
        status = getattr(self, "_status_bar_frame", None)
        if chrome is None or body is None:
            return
        if is_excel is None:
            is_excel = self._skin_name == "excel" and not getattr(self, "_ghost", False)
        sheet_mode = is_excel and not chrome._native
        if sheet_mode:
            body.pack_forget()
            if status is not None:
                status.pack_forget()
            chrome.sheet_area.pack(fill="both", expand=True)
        else:
            chrome.sheet_area.pack_forget()
            if status is not None:
                status.pack(fill="x", padx=6, pady=(4, 2))
            body.pack(fill="both", expand=True, padx=6, pady=2)
        title = getattr(getattr(self, "title_bar", None), "title", None)
        if title is not None and not self._prefs.get("camo"):
            title.configure(text="工作簿1 · 内部办公助手" if is_excel else self.core.nick)

    def _send_excel_text(self, text: str) -> bool:
        """从单元格发送新消息，仍使用聊天的统一发送和权限处理。"""
        if getattr(self, "_ro_mode", False) or not str(text).strip():
            return False
        draft = self._entry_text()
        reply, edit = self._pending_reply, self._pending_edit_seq
        try:
            # 单元格发送是一条新消息，不误用旧聊天编辑/引用状态；原草稿随后恢复。
            self._pending_reply = None
            self._pending_edit_seq = None
            self.entry.delete("1.0", "end")
            self.entry.insert("1.0", str(text))
            before = len(self.msg_list._rows)
            self._send()
            rows = self.msg_list._rows
            return not (len(rows) > before and rows[-1].raw.get("failed"))
        finally:
            self.entry.delete("1.0", "end")
            self.entry.insert("1.0", draft)
            self._pending_reply, self._pending_edit_seq = reply, edit
            self._save_draft()
            self._excel_chrome.refresh_messages()

    def _build_right(self, body) -> None:
        sk = self._skin
        right = tk.Frame(body, bg=sk["panel_bg"])
        self._chat_frame = right
        right.pack(side="left", fill="both", expand=True)
        f = self._f
        # 会话标题行 = 标题 + 免打扰灰标（平时隐藏）
        self.chan_label_row = tk.Frame(right, bg=sk["panel_bg"])
        self.chan_label_row.pack(fill="x", padx=16, pady=(12, 12))
        self.chan_label = tk.Label(self.chan_label_row, text="公共频道", fg=sk["fg"], font=(body_font()[0], 13, 'bold'),
                                   anchor="w", bg=sk["panel_bg"])
        self.chan_label.pack(side="left", fill="x", expand=True)
        # R72 优化：点会话标题的「📍 正在共享位置」→ 打开共享者地图
        self.chan_label.bind("<Button-1>", self._on_chan_label_click)
        self.chan_label.bind("<Enter>",
                             lambda _e: self.chan_label.configure(
                                 cursor="hand2" if self._geo_live_markers else ""))
        self.chan_label.bind("<Leave>", lambda _e: self.chan_label.configure(cursor=""))
        self._dnd_badge = tk.Label(self.chan_label_row, text=" 🔕勿扰中 ",
                                   fg=sk.get("muted", "#8a8a8a"),
                                   font=(FONT_FAMILY, 9), bg=sk["panel_bg"])
        self._dnd_badge.pack(side="right", padx=4)
        self._dnd_badge.pack_forget()              # 平时隐藏
        # R13 消息置顶横幅（会话级；默认隐藏）
        pin_bg = sk.get("pin_bg", "#fff8e1")
        pin_fg = sk.get("pin_fg", "#b26a00")
        self.pin_bar = tk.Frame(right, bg=pin_bg)
        self._pin_label = tk.Label(self.pin_bar, text="", fg=pin_fg,
                                   font=(FONT_FAMILY, 9), anchor="w",
                                   bg=pin_bg)
        self._pin_label.pack(side="left", fill="x", expand=True, padx=4)
        tk.Button(self.pin_bar, text="✕", font=(FONT_FAMILY, 9), relief="flat",
                  bd=0, bg=pin_bg, fg=pin_fg, command=self._unpin_current,
                  padx=4).pack(side="right")
        self.pin_bar.pack(fill="x")
        self.pin_bar.pack_forget()          # 默认隐藏
        wrap = tk.Frame(right, bg=sk["panel_bg"])
        self._wrap_frame = wrap
        wrap.pack(fill="both", expand=True)
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(1, weight=1)
        # R16 群公告横幅（群频道有公告时显示；默认隐藏；置于 wrap 之上）
        ann_bg = sk.get("ann_bg", "#fce8ee")
        ann_fg = sk.get("ann_fg", "#7b2d4e")
        self.announce_bar = tk.Frame(right, bg=ann_bg)
        self._announce_label = tk.Label(
            self.announce_bar, text="", fg=ann_fg, font=(FONT_FAMILY, 9),
            anchor="w", bg=ann_bg, wraplength=520)
        self._announce_label.pack(side="left", fill="x", expand=True, padx=4,
                                  pady=2)
        self.announce_bar.pack(fill="x", before=wrap)
        self.announce_bar.pack_forget()          # 默认隐藏
        # C1 聊天内搜索条（Ctrl+F 呼出，默认隐藏；grid_remove 保留 grid 位置）
        self.chat_search = tk.Frame(wrap, bg=sk["panel_bg"])
        self.chat_search.grid(row=0, column=0, sticky="ew")
        sf = (FONT_FAMILY, 9)
        tk.Label(self.chat_search, text="搜索", font=sf, fg=sk["sub"],
                 bg=sk["panel_bg"]).pack(side="left", padx=(0, 3))
        self.chat_search_entry = tk.Entry(self.chat_search, font=sf, width=18,
                                          highlightthickness=1,
                                          highlightbackground=sk["glass_border"],
                                          bg=sk["input_bg"], fg=sk["fg"],
                                          insertbackground=sk["fg"],
                                          relief="flat")
        self.chat_search_entry.pack(side="left")
        self.chat_search_count = tk.Label(self.chat_search, text="0/0",
                                          font=sf, fg=sk["sub"],
                                          bg=sk["panel_bg"])
        self.chat_search_count.pack(side="left", padx=(0, 3))
        for txt, d in (("◀", -1), ("▶", 1)):
            tk.Button(self.chat_search, text=txt, width=2, font=sf, relief="flat",
                      fg=sk["sub"], bg=sk["panel_bg"],
                      command=lambda dd=d: self._chat_search_goto(dd)).pack(
                side="left")
        tk.Button(self.chat_search, text="✕", width=2, font=sf, relief="flat",
                  fg=sk["sub"], bg=sk["panel_bg"],
                  command=self._close_chat_search).pack(side="left")
        self.chat_search_entry.bind("<Return>",
                                    lambda e: self._chat_search_goto(1))
        self.chat_search_entry.bind("<Escape>", lambda e: self._close_chat_search())
        self.chat_search_entry.bind("<KeyRelease>",
                                    lambda e: self._do_chat_search())
        self.chat_search.grid_remove()          # 默认隐藏

        self.msg_list = MsgList(wrap, self._f,
                                colors=msg_colors(self._skin),
                                avatars=self._avatars,
                                read_mark=self._mode_cfg["read_mark"],  # R交互：qq 模式隐藏回执
                                on_row_menu=self._on_msg_menu,      # B2
                                on_row_double=self._on_msg_double,  # B4 双击回复
                                on_row_image=self._on_row_image,    # T7 图片放大
                                on_link=self._on_msg_link,          # R11 链接打开
                                on_voice=self._on_voice,            # R19 语音播放
                                on_voice_end=self._on_voice_end,    # D14 语音连播
                                on_transcribe=(self._voice_stt
                                               if optional.has_stt() else None),  # R批次③ 转文字
                                on_poll_vote=self._on_poll_vote,    # R26A 点选项投票
                                on_react=self._on_react_seq,        # R27 快速回应/药丸
                                on_mention=self._on_mention_click,  # R29C：@昵称可点跳私聊
                                on_quick_more=self._on_quick_more,  # R29D：悬浮条"＋"全表情
                                on_hashtag=self._on_hashtag_click,  # R30E：#话题→全局搜索
                                on_react_detail=self._on_react_detail,  # R30D：药丸hover详情
                                on_sticker_path=self.core.custom_sticker_path,  # R30C
                                on_sticker_fetch=self._fetch_sticker_img,       # R30C
                                on_failed=self._resend_failed,                  # R31C 点❗重发
                                on_read_detail=self._on_read_hover,             # R33③ ✓已读hover详情
                                on_open_thread=self._open_thread,               # R34 点「N 条回复」开话题
                                on_fwd_open=self._open_fwd_pack,                # R39D③ 双击合并转发卡展开
                                on_jump_reply=self._on_jump_reply,              # R41F 点引用前缀跳转
                                on_kb=self._on_kb_click,                        # R46 点 bot 键盘按钮
                                on_bubble_act=self._on_bubble_act,                # R58C 悬停操作条
                                on_profile=self._open_user_card,                 # R69C10 点头像看资料
                                on_card=self._open_user_card,                    # R71 点名片卡看资料
                                on_vmemo=self._open_vmemo_player,                # R72 点视频留言播放
                                on_edit_history=self._show_edit_history)         # R70B 点✎已编辑看历史
        self.msg_list.set_history_loader(self._load_older_page)   # R39C 懒加载
        self.msg_list.set_fade_enabled(bool(self._prefs.get("bubble_fade")))  # R39D②
        self.msg_list.set_guard(self._guard_words, self._guard_enabled_now())  # R70F 敏感词打码
        self.msg_list.grid(row=1, column=0, sticky="nsew")
        if self._recent_reacts:                # R29D：重启后恢复悬浮条最近使用
            self.msg_list.set_quick_emojis(self._recent_reacts)

        # R31B 消息多选操作栏（浮在消息区顶部，进入选择模式才显示）
        self.sel_bar = tk.Frame(wrap, bg=sk["panel_bg"])
        tk.Button(self.sel_bar, text="✕", width=3, font=sf, relief="flat",
                  bd=0, fg=sk["sub"], bg=sk["panel_bg"], cursor="hand2",
                  command=self.msg_list.exit_select_mode).pack(side="left",
                                                               padx=(6, 2),
                                                               pady=3)
        self.sel_count_lbl = tk.Label(self.sel_bar, text="已选 0 条",
                                      font=sf, fg=sk["fg"],
                                      bg=sk["panel_bg"])
        self.sel_count_lbl.pack(side="left", padx=2)
        self.sel_del_btn = tk.Button(
            self.sel_bar, text="🗑 删除", font=sf, relief="flat", bd=0,
            fg="#e03e3e", bg=sk["panel_bg"], cursor="hand2",
            state="disabled", command=self._multi_delete)
        self.sel_del_btn.pack(side="right", padx=(2, 8))
        ui_fx.press_feedback(self.sel_del_btn, pressed_bg=sk["input_bg"])  # R43A2
        self.sel_fwd_btn = tk.Button(
            self.sel_bar, text="↪ 转发", font=sf, relief="flat", bd=0,
            fg=sk["accent"], bg=sk["panel_bg"], cursor="hand2",
            state="disabled", command=self._multi_forward)
        self.sel_fwd_btn.pack(side="right", padx=2)
        ui_fx.press_feedback(self.sel_fwd_btn, pressed_bg=sk["input_bg"])  # R43A2
        self.msg_list.set_sel_cb(self._on_sel_change)
        self.sel_bar.place_forget()

        # 传输状态条（文件收发进度，随事件更新，不刷屏）
        self.xfer_area = tk.Frame(right, bg=sk["panel_bg"])
        self.xfer_area.pack(fill="x", pady=(0, 2))
        self._xfer_bars: dict = {}          # fid -> _FileCard
        self._xfflow: dict = {}             # fid -> [prev_done, prev_ts, ema_speed] 速率滑动统计

        self._sticker_nav = tk.Frame(right, bg=sk["panel_bg"])
        self._sticker_nav.pack(fill="x")
        self._sticker_nav.pack_forget()          # R64：包导航条，默认随贴纸条隐藏
        self._sticker_row = tk.Frame(right, bg=sk["panel_bg"])
        self._sticker_row.pack(fill="x")
        self._sticker_row.pack_forget()          # 默认隐藏

        bottom = tk.Frame(right, bg=sk["panel_bg"])
        bottom.pack(fill="x", padx=14, pady=(8, 10))
        self._bottom_frame = bottom               # R26B：频道只读时整条禁用
        # 单行高 Text：Enter 发送、Shift+Enter 换行（对标 TG 多行输入）
        self.entry = tk.Text(bottom, height=3, font=f, wrap="word",
                             highlightthickness=1, bd=0, undo=False,
                             padx=10, pady=8,
                             bg=sk["input_bg"], fg=sk["fg"],
                             insertbackground=sk["fg"],
                             relief="flat",
                             highlightbackground=sk["glass_border"],
                             highlightcolor=sk["accent"])
        self.entry.pack(side="top", fill="x")
        # R63 输入框「自动+手动混合」拉伸：随内容自动增高，另加下方拖拽把手可手动调高
        self._entry_manual_lines = int(self._prefs.get("entry_manual_lines", 0) or 0)
        self._drag_y0 = 0
        self._drag_h0 = 0
        self._drag_bar = tk.Frame(bottom, height=3, bg=sk["glass_border"],
                                  cursor="sb_v_double_arrow")
        self._drag_bar.pack(side="top", fill="x")

        def _drag_line_px():
            """估算 Text 一个『显示行』的像素高，用于拖拽换算行数。"""
            d = self.entry.dlineinfo("1.0")
            return (int(d[3]) if d and d[3] else 16) or 16

        def _drag_start(ev):
            self._drag_y0 = ev.y_root
            self._drag_h0 = max(1, int(self.entry.cget("height") or 1))

        def _drag_move(ev):
            step = _drag_line_px()
            new_h = max(1, self._drag_h0 + round((ev.y_root - self._drag_y0) / step))
            self.entry.config(height=new_h)   # 拖拽不改内容、不触发 <<Modified>>，不会被打回

        def _drag_end(_ev):
            h = max(1, int(self.entry.cget("height") or 1))
            self._entry_manual_lines = h      # 固化手动高度（作为自动增高的下限）
            self._prefs.set("entry_manual_lines", h)

        def _drag_clear(_ev=None):
            """双击把手 → 清除手动高度，恢复纯自动 1-6 行自适应。"""
            self._entry_manual_lines = 0
            self._prefs.set("entry_manual_lines", 0)
            self._adjust_entry_height()
            return "break"

        self._drag_bar.bind("<Button-1>", _drag_start)
        self._drag_bar.bind("<B1-Motion>", _drag_move)
        self._drag_bar.bind("<ButtonRelease-1>", _drag_end)
        self._drag_bar.bind("<Double-Button-1>", _drag_clear)
        # R交互：发送键按交互模式绑定
        self._bind_send_key(self.entry)
        self.entry.bind("<<Modified>>", self._on_entry_modified)   # R32A2
        # Ctrl+V：剪贴板是图片/文件则直接发送，否则放行默认文本粘贴
        self.entry.bind("<<Paste>>", self._on_paste_clipboard)
        # R31 工具行（TG 风格收纳）：输入框整行在上，工具行在下；
        # 高频平铺（表情/文件/语音/投票/更多），低频收进「＋」更多菜单
        bar = tk.Frame(bottom, bg=sk["panel_bg"])
        bar.pack(side="top", fill="x", before=self.entry, pady=(0, 6))
        self._toolbar_bar = bar                   # R31：主题刷色需覆盖
        self._bottom_btns = []

        def _tool(txt, cmd):
            icons = {'表情':'emoji', '附件':'attach', '录音':'mic', '更多':'more', '@所有':'broadcast'}
            b = IconButton(bar, text=txt, icon=icons[txt], command=cmd,
                           palette=sk, scale=self._dpi_scale, padx=4, pady=4)
            b.pack(side="left")
            self._bottom_btns.append(b)
            self._design_buttons.append(b)
            return b

        _tool("表情", self._toggle_stickers)        # 表情/贴纸条
        _tool("附件", self._on_send_file)           # 发文件
        self._vrec_btn = _tool("录音", self._toggle_record)   # 语音录入
        self._vrec_default_bg = sk["panel_bg"]
        self._more_btn = _tool("更多", self._more_menu)       # 低频能力保持原菜单
        # @全体：群聊输入便捷入口，点击把 @全体 插入光标处（服务器据此全员广播）。
        # 非群聊时灰显并提示原因（见 _refresh_evbody），避免"点了没反应"的无效按键感。
        self._evbody_btn = _tool("@所有", self._insert_evbody)
        self._evbody_btn.pack_forget()                # 默认隐藏，仅群聊显示
        # 条件不可用提示：灰显时点击给出原因（disabled 态下 command 不触发，bind 仍生效）
        self._evbody_btn.bind(
            "<Button-1>",
            lambda e: self._append_sys("仅群聊可 @全体：请先进入一个群聊会话"))
        # 开关徽标（发送左侧，激活才出现；点一下即取消）
        self._burn_btn = tk.Button(bar, text="🔥", command=self._toggle_burn_mode,
                                   font=f, relief="flat", padx=4, bd=0,
                                   fg="#e03e3e", bg=sk["input_bg"],
                                   cursor="hand2")
        self._silent_btn = tk.Button(bar, text="🔕", command=self._toggle_silent_mode,
                                     font=f, relief="flat", padx=4, bd=0,
                                     fg=sk["sub"], bg=sk["input_bg"],
                                     cursor="hand2")
        # R70E 消息伪装：🎭 点一下循环切换风格（关 → code → log → excel → 关）
        self._disguise_btn = tk.Button(bar, text="🎭", command=self._cycle_disguise,
                                       font=f, relief="flat", padx=4, bd=0,
                                       fg=sk["sub"], bg=sk["input_bg"],
                                       cursor="hand2")
        if self._burn_mode:                       # 恢复 prefs 中的开关态
            self._burn_btn.pack(side="left")
        if self._silent_mode:
            self._silent_btn.pack(side="left")
        if self._disguise_mode:
            self._disguise_btn.pack(side="left")
        self._compose_footer = tk.Frame(bottom, bg=sk['panel_bg'])
        self._compose_footer.pack(fill='x', pady=(8, 0))
        self._compose_target = tk.Label(self._compose_footer, text='发送到：公共频道',
                                       bg=sk['panel_bg'], fg=sk['sub'],
                                       font=(body_font()[0], 9), anchor='w')
        self._compose_target.pack(side='left', fill='x', expand=True)
        self._send_btn = IconButton(self._compose_footer, icon='send', text='发送',
                                   command=self._send, palette=sk, role='primary',
                                   scale=self._dpi_scale, padx=14, pady=6)
        self._send_btn.pack(side="right")
        self._design_buttons.append(self._send_btn)

        # R19 语音录音条（点 🎙 出现；含计时/完成/取消，默认隐藏）
        voice_bg = sk.get("voice_bg", "#fff2e6")
        self._voice_bar = tk.Frame(right, bg=voice_bg)
        self._rec_lbl = tk.Label(self._voice_bar, text="● 录音中 0.0s", fg="#e03e3e",
                                 font=f, bg=voice_bg)
        self._rec_lbl.pack(side="left", padx=6, pady=3)
        tk.Button(self._voice_bar, text="完成并发送", font=f, relief="flat",
                  bg=voice_bg, padx=6,
                  command=lambda: self._stop_record(True)).pack(side="left")
        tk.Button(self._voice_bar, text="取消", font=f, relief="flat",
                  bg=voice_bg, padx=6,
                  command=lambda: self._stop_record(False)).pack(side="left")
        self._voice_bar.pack(fill="x")
        self._voice_bar.pack_forget()                    # 默认隐藏
        # R19 录音状态
        self._recorder = None
        self._rec_th = None
        self._rec_lock = threading.Lock()
        self._rec_data = bytearray()
        self._rec_start = 0.0
        self._rec_ticks = 0

    # ---------- 事件轮询（主线程） ----------
    def _poll(self) -> None:
        if self._closed:
            return
        try:
            try:
                while True:
                    ev = self.core.events.get_nowait()
                    self._handle(ev)
                    if self._closed:
                        return
            except queue.Empty:
                pass
            # 热键 → 切换假工作窗
            if CFG.global_hotkeys_enabled:
                try:
                    while True:
                        self._hotkey.q.get_nowait()
                        self._toggle_boss()
                except queue.Empty:
                    pass
            # Alt+A → 区域截图即发
            if CFG.global_hotkeys_enabled:
                try:
                    while True:
                        self._shot_hotkey.q.get_nowait()
                        self._start_snip()
                except queue.Empty:
                    pass
            # 自动发现 → 未连上时自动切到最新候选服务器（约 1.2s 一次）
            self._disco_ticks += 1
            if CFG.discovery_enabled and self._disco is not None and self._disco_ticks % 10 == 0:
                self._disco_ticks = 0
                self._auto_target()
            # C5：未读/置顶/搜索变化后统一重绘名单与群（批量，避免逐条刷新）
            if self._list_dirty:
                self._list_dirty = False
                self._refresh_lists()
            self._pump_scheduled()          # R14：到点触发定时发送
            self._rec_tick()                 # R19：录音计时（约 120ms/拍）
            self._fish_tick(time.time())     # R69A3：摸鱼报告（停留时长/游戏局数）
            # R25A：约 1s 一次刷新标题（typing 3s 过期，惰性消失）
            self._typing_ticks += 1
            if self._typing_ticks % 8 == 0:
                self._typing_ticks = 0
                self._refresh_chan_label()
            # R29B：约 1.2s 一次把当前会话草稿推给服务器（输入防抖）
            self._draft_ticks += 1
            if self._draft_dirty and self._draft_ticks % 10 == 0:
                self._draft_ticks = 0
                self._draft_dirty = False
                self._push_draft(self._hist_key())
                self._list_dirty = True          # R32B1：草稿前缀联动会话列表
        finally:
            # Tk still reports unexpected callbacks; keep polling only while
            # this window is alive, including when a callback raises.
            if not self._closed:
                self.root.after(120, self._poll)

    def _handle(self, ev: dict) -> None:
        epoch = ev.get("_connection_epoch")
        if epoch is not None and epoch != getattr(self.core, "connection_epoch", 0):
            return  # Queued authentication/state replies from an old connection.
        if hasattr(self.core, "accepts_ui_event") and not self.core.accepts_ui_event(ev):
            return
        t = ev.get("t")
        if t == "state":
            self._on_state(ev.get("state"))
            self._refresh_retirement_results()
        elif t == "welcome":
            self._on_welcome(ev)
        elif t == "chat":
            self._fish_add(msgs=1)             # R69A3：摸鱼报告消息数（仅实时新消息）
            self._append_msg(ev)
        elif t == "poll":
            self._append_msg(ev)               # R26A：投票消息同聊天渲染（气泡）
        elif t == "edit":
            self._on_msg_edit(ev)
        elif t == "del":
            self._on_msg_del(ev)
        elif t == "reaction":
            self._on_msg_reaction(ev)
        elif t == "read":
            self._on_msg_read(ev)
        elif t == "read_detail":
            self._on_read_detail_resp(ev)       # R33③：已读详情回帧 → 浮示成员
        elif t == "msg_readers":
            self._on_msg_readers_resp(ev)       # C9②：群@已读逐人统计回帧 → 浮示已读/未读
        elif t == "thread_history":
            self._on_thread_history(ev)         # R34：话题回复回帧 → 合并窗口
        elif t == "call":
            self._on_call_event(ev)             # R38：语音通话事件 → 通话窗
        elif t == "room":
            self._on_room_event(ev)              # R72：语音房事件 → 语音房窗
        elif t in ("geo_live", "geo_stop"):
            self._on_geo_live_evt(ev)           # R72：实时位置事件 → 更新共享标记 + 刷新标题
        elif t == "typing":
            self._refresh_chan_label()          # R25A：有人输入 → 标题即时刷新
        elif t == "nudge":
            self._on_nudge(ev)                  # R67：拍一拍 → 轻量行/提醒
        elif t == "shake":
            self._on_shake(ev)                  # R68：窗口抖动 → 抖动窗口/提醒
        elif t == "draft":
            self._on_draft_sync(ev)             # R29B：换端带回草稿 → 合并恢复
        elif t == "pin":
            self._on_msg_pin(ev)
        elif t == "poll_state":
            self._on_poll_state(ev)          # R26A：权威票数更新
        elif t == "preview":
            self._on_preview(ev)             # R26D：链接预览补发
        elif t == "admin_groups_roster":
            self._on_admin_groups_roster(ev)  # 系统管理员：群目录回帧 → 群管理面板
        elif t == "retirement_status":
            self._on_retirement_status(ev)
        elif t == "admin_user_info":
            self._on_admin_user_info(ev)     # 系统管理员：某人信息+所属群 回帧
        elif t == "invis_ack":
            on = bool(ev.get("on"))
            self._append_sys("已开启隐身上线：仅你自己和管理员可见" if on
                             else "已关闭隐身上线：现恢复正常可见")
        elif t == "remark_ack":
            # R69C9：备注名回帧（服务器权威）→ 提示 + 列表/预览按新名刷新
            rem = str(ev.get("remark") or "").strip()
            self._append_sys(f"备注名已更新为「{rem}」" if rem else "备注名已清除")
            self._refresh_lists()
        elif t == "system":
            self._append_sys(ev.get("text", ""))
        elif t == "image":
            self._append_msg(ev)               # A7 收到的图片 → 缩略图消息行
        elif t == "roster":
            self._refresh_roster()
            self._request_avatars()          # R52：新头像懒拉取
            self._refresh_chan_label()      # R25B：在线/最后上线实时刷新标题
        elif t == "block_list":
            self._refresh_roster()          # R50：屏蔽名单变化 → 名单刷新
        elif t == "avatar_data":
            self._on_avatar_data(ev)        # R52：头像字节到手 → 注册+重绘
        elif t == "group_avatar_data":
            self._on_group_avatar_data(ev)  # R9H：群头像字节到手 → 注册+重绘
        elif t == "group_file_list":
            self._on_group_file_list(ev)    # 群文件列表回帧 → 填充库窗口
        elif t == "group_file_upload_info":
            self._on_group_file_upload_info(ev)  # 服务器分配 fid → 开始传块
        elif t == "group_file_data":
            self._on_group_file_data(ev)    # 下载数据块 → 落盘
        elif t == "group_file_notify":
            self._on_group_file_notify(ev)  # 群内增删通知 → 刷新库窗口
        elif t == "task_state":
            self._on_task_state(ev)         # R69B6/B7：群任务清单回填/提示
        elif t == "group_file_list_res":    # 兼容：老协议别名（防御性）
            self._on_group_file_list(ev)
        elif t == "moment_feed":
            self._on_moment_feed(ev)        # 朋友圈：拉全量时间轴
        elif t == "moment_new":
            self._on_moment_update(ev)      # 朋友圈：新动态（post 全量）→ 置顶
        elif t == "moment_update":
            self._on_moment_update(ev)      # 朋友圈：更新（赞/评）或删除（post=None）
        elif t == "moment_data":
            self._on_moment_data(ev, ev.get("data", b""))  # 朋友圈：图片字节回填
        elif t == "moment_cover":
            self._on_moment_cover(ev, ev.get("data", b""))  # 朋友圈：封面回帧/广播
        elif t == "sched_list":
            self._on_sched_sync(ev)         # R51：定时消息列表（创建/取消/拉取回帧）
        elif t == "group_list":
            self._refresh_groups()
            self._apply_channel_ro()         # R26B：频道 kind/owner 可能随刷新变化
        elif t == "group_state":
            self._refresh_groups()
            self._append_sys(ev.get("text", ""))
            if self.view[0] == "group" and self.view[1] == ev.get("gid"):
                self._refresh_announce_bar()
            if self._members_dlg is not None:
                d = self._members_dlg
                if d["gid"] == ev.get("gid"):
                    if not d["dlg"].winfo_exists():
                        self._members_dlg = None
                    else:
                        try:
                            d["reload"]()
                        except Exception:
                            self._members_dlg = None
        elif t == "history":
            for m in ev.get("msgs", []):
                self._append_msg(m)
        elif t == "sticker_list":
            self._build_stickers()
            self.msg_list.stickers_updated()   # R30C：清单变化 → 贴纸行重绘
        elif t == "sticker_data":
            self.msg_list.stickers_updated()   # R30C：贴纸图到手 → 未就绪行补图
        elif t == "sticker_pack_cover_data":
            self._build_stickers()             # R64：包封面到手 → 导航条补图
        elif t == "sticker_shop_list":
            self._build_stickers()             # R35：商店目录到手 → 面板按订阅重绘
            self._refresh_shop_dlg()
        elif t == "sticker_sub":
            self._build_stickers()             # R35：订阅变化 → 面板按订阅重绘
            self._refresh_shop_dlg()
        elif t == "group_invite":
            # R28：服务器单播回邀请码 → 复制到剪贴板并提示（R55-5：改 toast，长停留便于抄码）
            code = ev.get("code") or ""
            self._copy_text(code)
            self.show_toast(f"群邀请码已复制：{code}", duration=6000)
        elif t == "file_offer":
            self._on_file_offer(ev)
        elif t == "file_progress":
            self._on_file_progress(ev)
        elif t == "error":
            self._on_error(ev)
        elif t == "cleared":
            self._on_cleared(ev)          # R53：管理员清理广播 → 清空本地历史+刷新
        elif t == "e2ee_rotated":          # R42：密钥轮转完成
            self._append_sys("🔄 密聊密钥已轮转（此前消息密钥已废弃，前向保密）")
        # pong/其他忽略

    def _on_cleared(self, ev: dict) -> None:
        """R53 cleared 事件：服务器权威清理广播（core 已清本地历史），
        刷新当前会话与全部列表预览，并提示结果。"""
        if ev.get("all"):
            self._load_view_history()
            self._refresh_lists()
            self._append_sys("🧹 管理员已清空全部聊天记录，本地历史已同步清空")
        elif ev.get("uid") is not None:
            uid = ev["uid"]
            u = self.core.roster.get(uid) or self.core.known.get(uid) or {}
            nick = u.get("nick", f"用户{uid}")
            if self.view[1] == uid or self.view[0] in ("public",):
                self._load_view_history()
            self._refresh_lists()
            self._append_sys(f"🧹 管理员已清空用户 {nick} 的全部消息，本地历史已同步")

    def _on_state(self, state: str) -> None:
        m = {"online": ("●", "#2e7d32", "已连接"),
             "connecting": ("◐", "#b26a00", "连接中…"),
             "offline": ("○", "#999", "离线，自动重连…"),
             "idle": ("○", "#999", "未启动")}
        dot, color, text = m.get(state, ("○", "#999", state))
        self.status_dot.config(text=dot, fg=color)
        self.status_text.config(text=text)
        # R38：连接断开时强制结束通话（音频链路不可用，信令也发不出去）
        if state != "online" and self.core.calls.state != "idle":
            self.core.calls.shutdown()
            if self._call_win is not None and self._call_win.winfo_exists():
                self._call_win.update_state({"t": "call", "state": "failed",
                                             "text": "连接已断开，通话结束"})
            else:
                self._call_win = None

    def _on_welcome(self, ev: dict) -> None:
        self.status_text.config(text=f"已连接 · {self.core.nick}")
        self.msg_list.set_me_uid(self.core.uid)
        self._refresh_roster()
        self._refresh_groups()
        self.core.request_sticker_shop()        # R64：拉商店目录，包导航条才能列出内置包
        self._build_stickers()
        self._load_view_history()
        self._draw_icon_avatar()            # R52：图标栏自己头像
        self._request_avatars()             # R52：懒拉取在线/已知用户头像
        # R13：欢迎后按当前会话恢复回执与置顶横幅（历史/置顶都随连接带回）
        self.msg_list.set_reads(self.core.reads.get(self._pin_key(*self.view), {}))
        self._refresh_pin_bar()
        # R12：welcome 可能晚于用户已开始的输入到达（异步派发）——只在输入框
        # 仍为空时恢复草稿，避免覆盖正在打的字（切换会话的清空由 _switch_view 负责）
        if not self._entry_text().strip():
            self._restore_draft()
        # R51：登录对齐定时消息（welcome 已带回；无则主动拉取）
        if ev.get("scheds") is not None:
            self._on_sched_sync({"items": ev.get("scheds")})
        else:
            self.core.sched_list()
        self._arm_reminders()                   # R68：登录后恢复未到期的消息提醒

    # ---------- R68 消息「提醒我」（纯客户端，prefs 持久化 + after 定时） ----------
    def _reminders(self) -> list:
        r = self._prefs.get("reminders")
        return r if isinstance(r, list) else []

    def _save_reminders(self, lst) -> None:
        self._prefs.set("reminders", lst)
        self._arm_reminders()

    def _arm_reminders(self) -> None:
        """按最近到期时间排一次 after；到点弹出全部到期提醒并重排。"""
        job = getattr(self, "_rem_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
            self._rem_job = None
        now = time.time()
        lst = self._reminders()
        due = [r for r in lst if float(r.get("at") or 0) <= now]
        fut = [r for r in lst if float(r.get("at") or 0) > now]
        if due and getattr(self, "_boss_active", False):
            # R69A2：伪装态冻结弹窗 → 到期提醒顺延 60s（不丢，退出后自然弹出）
            for r in due:
                r["at"] = now + 60
            self._save_reminders(due + fut)
            return
        if due:
            for r in due:
                self._fire_reminder(r)
            self._save_reminders(fut)            # 已弹出 → 从队列移除并重新排程
            return
        if fut:
            nxt = min(float(r.get("at") or 0) for r in fut)
            self._rem_job = self.root.after(
                max(int((nxt - now) * 1000), 50), self._arm_reminders)

    def _fire_reminder(self, r: dict) -> None:
        """到点提醒：右下角 toast + 提示音 + 任务栏闪烁。"""
        nick = str(r.get("nick") or "有人")
        text = str(r.get("text") or "").strip().replace("\n", " ")
        msg = f"⏰ 提醒：{nick}：{text[:40]}" if text else f"⏰ 提醒：{nick} 的消息"
        self.show_toast(msg, 4200, warn=True)
        self._play_notify_sound()
        try:
            _flash_window(self.root.winfo_id())
        except Exception:
            pass

    def _add_reminder(self, idx: int, minutes: float) -> None:
        """给某条消息设提醒（同消息重复设置则覆盖时间）。"""
        raw = self.msg_list.get_row(idx)
        if not raw:
            return
        key = self._pin_key(*self.view)
        seq = raw.get("seq")
        at = time.time() + minutes * 60
        lst = [r for r in self._reminders()
               if not (r.get("key") == key and r.get("seq") == seq)]
        lst.append({"key": key, "seq": seq, "at": at,
                    "nick": raw.get("nick") or "有人",
                    "text": self.msg_list.body_text(idx) or ""})
        self._save_reminders(lst)
        label = f"{int(minutes)} 分钟后" if minutes < 60 \
            else f"{minutes / 60:g} 小时后"
        self._append_sys(f"⏰ 已设置提醒（{label}）")

    # ---------- R52 头像与个人资料 ----------
    def _open_contacts_panel(self) -> None:
        """联系人/👥 按钮：打开独立通讯录面板（在线 + 离线联系人，双击进会话）。

        注意：不能叫 _focus_search —— 类里已有同名方法（Ctrl+F 聊天内搜索）
        定义在其后，会覆盖本方法导致按钮点击无效。
        """
        self._select_navigation('people')
        if getattr(self, "_contacts_win", None) and self._contacts_win.winfo_exists():
            self._contacts_win.lift()
            self._contacts_win.focus_force()
            return
        dp = self._dp
        f = self._f
        dlg = tk.Toplevel(self.root)
        self._contacts_win = dlg
        dlg.bind('<Destroy>', lambda event:self._navigation_dialog_closed(event,dlg), add='+')
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("通讯录")
        dlg.transient(self.root)
        dlg.geometry("320x540+" + str(self.root.winfo_x() + 200) + "+"
                     + str(self.root.winfo_y() + 60))
        dlg.configure(bg=dp["win"])
        self._apply_apple_dialog(dlg, "通讯录")

        # 标题 + 关闭
        head = tk.Frame(dlg, bg=dp["win"])
        head.pack(fill="x", padx=12, pady=(10, 2))
        tk.Label(head, text="通讯录", bg=dp["win"], fg=dp["fg"],
                 font=(FONT_FAMILY, FONT_SIZE + 2, "bold")).pack(side="left")
        tk.Button(head, text="✕", bg=dp["win"], fg=dp["sub"], relief="flat",
                  font=(FONT_FAMILY, 11), command=dlg.destroy,
                  activebackground=dp["win"]).pack(side="right")
        # 搜索
        search_var = tk.StringVar()
        search_ent = tk.Entry(dlg, textvariable=search_var, font=f,
                              bg=dp["input"], fg=dp["fg"],
                              insertbackground=dp["fg"], relief="flat",
                              highlightthickness=1,
                              highlightbackground=dp["border"])
        search_ent.pack(fill="x", padx=12, pady=(4, 4))
        # 在线人数
        stat = tk.Label(dlg, text="", bg=dp["win"], fg=dp["sub"], font=(FONT_FAMILY, 9),
                        anchor="w")
        stat.pack(fill="x", padx=12)

        def build() -> list:
            q = search_var.get().strip().lower()
            items = []
            online = 0
            user_list: list = []
            seen: set = set()
            for u in self.core.roster.values():
                user_list.append(dict(u))
                seen.add(u["uid"])
            for uid, info in self.core.known.items():
                if uid == self.core.uid:              # R25C：收藏夹不进通讯录
                    continue
                if uid in seen:
                    continue
                user_list.append({"uid": uid, "nick": info.get("nick", f"用户{uid}")})
            # 在线优先，再按昵称
            user_list.sort(key=lambda u: (u["uid"] not in self.core.roster,
                                          u.get("nick") or ""))
            for u in user_list:
                if u["uid"] == self.core.uid:
                    continue
                info = self.core.known.get(u["uid"], {})
                name = (info.get("nick") or u.get("nick") or f"用户{u['uid']}")
                if q and q not in name.lower():
                    continue
                is_online = u["uid"] in self.core.roster
                online += 1 if is_online else 0
                sign = info.get("sign")
                last_on = info.get("last_online", 0)
                # R68：多状态点色（在线/离开/忙碌/离线）
                st = ((u.get("status") or info.get("status") or "online")
                      if is_online else "offline")
                st_txt = {"online": "在线", "away": "离开", "busy": "忙碌"}.get(st, "")
                pv = sign or (st_txt or
                              (("最后上线 " + time.strftime("%m-%d %H:%M",
                                                            time.localtime(last_on)))
                               if last_on else "离线"))
                items.append({
                    "key": self._pin_key("private", u["uid"]),
                    "name": name,
                    "preview": pv,
                    "status": st,
                    "uid": u["uid"],
                })
            return items

        def reload(*_a) -> None:
            it = build()
            contacts.set_items(it)
            stat.config(text=f"{sum(x['status'] == 'online' for x in it)} 在线 · "
                             f"{len(it)} 人")

        def on_pick(_e=None) -> str:
            sel = contacts.curselection()
            if not sel:
                return "break"
            uid = contacts._contact_order[sel[0]] if \
                sel[0] < len(contacts._contact_order) else None
            if uid is None:
                return "break"
            self._switch_view("private", uid)
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            return "break"

        from widgets.session_list import SessionList
        contacts = SessionList(dlg, font=f, height=8 * 56,
                               on_pick=on_pick, avatars=self._avatars)
        contacts._contact_order: list = []
        contacts.set_colors({"bg": dp["win"], "fg": dp["fg"], "sub": dp["sub"],
                             "accent": dp["accent"], "selected_fg": "#ffffff",
                             "muted": dp["sub"], "hover": dp["tab_bg"]})
        # 让 on_pick 拿得到 uid 顺序：包装 SessionList.set_items 记录顺序
        _orig_set = contacts.set_items

        def _set_and_remember(items):
            contacts._contact_order = [i.get("uid") for i in items]
            _orig_set(items)
        contacts.set_items = _set_and_remember
        contacts.pack(fill="both", expand=True, padx=6, pady=(0, 8))
        search_var.trace_add("write", reload)
        search_ent.focus_set()
        reload()

    def _my_avatar_known(self) -> str:
        """我当前头像 ext（known 或 me 缓存）。"""
        return str((self.core.known.get(self.core.uid) or {}).get("avatar")
                   or self.core.me.get("avatar") or "")

    def _draw_icon_avatar(self) -> None:
        """图标栏自己的圆形头像（图片优先，否则首字色块）。"""
        cv = getattr(self, "icon_avatar", None)
        if cv is None or not getattr(self, "core", None) or not self.core.uid:
            return
        cv.delete("all")
        size = int(40 * (getattr(self, "_dpi_scale", 1.0) or 1.0))   # 随 DPI 等比缩放头像
        self._avatars.draw(cv, 0, 0, size, self.core.nick,
                           uid=self.core.uid, font=(FONT_FAMILY, 11, "bold"))

    def _request_avatars(self) -> None:
        """懒拉取：roster/known 中带 avatar 标记且本机未缓存 → AVATAR_GET。
        只对新 uid 发起，避免重复请求风暴。"""
        if not getattr(self, "core", None) or not self.core.uid:
            return
        wanted = []
        for u in list(self.core.roster.values()) + list(self.core.known.values()):
            uid = u.get("uid")
            if (uid and uid != self.core.uid
                    and u.get("avatar")
                    and uid not in self._avatars._img
                    and uid not in self.core.avatars):
                wanted.append(uid)
        for uid in wanted:
            self.core.send_avatar_get(uid)

    def _on_avatar_data(self, ev: dict) -> None:
        """AVATAR_DATA：字节注册进全局缓存 → 各处重绘。"""
        try:
            uid = int(ev.get("uid"))
        except (TypeError, ValueError):
            return
        ext = str(ev.get("ext") or "")
        data = self.core.avatars.get(uid, (None, b""))[1] if ext else b""
        if ext and data:
            self._avatars.set_image(uid, ext, data)
        else:
            self._avatars.clear_image(uid)
        self._draw_icon_avatar()          # 自己的头像可能刚回来
        self.roster_list._redraw()
        self.group_list._redraw()
        self.msg_list.redraw_all()

    def _on_group_avatar_data(self, ev: dict) -> None:
        """R9H：群头像字节注册进全局缓存（负 gid 命名空间，避与用户 uid 撞键）→ 重绘。"""
        try:
            gid = int(ev.get("gid"))
        except (TypeError, ValueError):
            return
        ext = str(ev.get("ext") or "")
        data = self.core.group_avatars.get(gid, (None, b""))[1] if ext else b""
        nkey = -gid
        if ext and data:
            self._avatars.set_image(nkey, ext, data)
        else:
            self._avatars.clear_image(nkey)
        self.group_list._redraw()

    # ---------- 朋友圈（📸 图标 → 独立时间轴窗口） ----------
    def _open_moments(self) -> None:
        self._select_navigation('moments')
        from widgets.moment_list import MomentList
        if getattr(self, "_moments_win", None) and self._moments_win.winfo_exists():
            self._moments_win.lift()
            self._moments_win.focus_force()
            return
        dp = self._dp
        f = self._f
        dlg = tk.Toplevel(self.root)
        self._moments_win = dlg
        dlg.bind('<Destroy>', lambda event:self._navigation_dialog_closed(event,dlg), add='+')
        ui_fx.fade_in(dlg)
        dlg.title("朋友圈")
        dlg.transient(self.root)
        dlg.geometry("420x620+" + str(self.root.winfo_x() + 220) + "+"
                     + str(self.root.winfo_y() + 40))
        dlg.configure(bg=dp["win"])
        skin = self._skin
        head = tk.Frame(dlg, bg=dp["win"])
        head.pack(fill="x", padx=14, pady=(10, 4))
        tk.Label(head, text="📸 朋友圈", bg=dp["win"], fg=dp["fg"],
                 font=(FONT_FAMILY, FONT_SIZE + 3, "bold")).pack(side="left")
        tk.Button(head, text="刷 新", bg=dp["win"], fg=dp["fg"], relief="flat",
                  font=(FONT_FAMILY, 10), activebackground=dp["win"],
                  command=lambda: self.core.send_moment_feed()).pack(side="right")
        tk.Button(head, text="✕", bg=dp["win"], fg=dp["sub"], relief="flat",
                  font=(FONT_FAMILY, 11), command=dlg.destroy,
                  activebackground=dp["win"]).pack(side="right", padx=(0, 4))
        self.moment_list = MomentList(dlg, font=f, skin=skin,
                                      uid=self.core.uid, host=self)
        self.moment_list.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        self.core.send_moment_feed()      # 打开即拉全量
        self.moment_list.set_me(self.core.nick)      # 封面昵称/签名
        self.moment_list.set_sign(self.core.me.get("sign") or "")
        self.core.send_moment_cover_get()            # 拉我的封面
        self._mom_unread = 0                     # R68：打开即清红点
        self._update_mom_badge()

    # ---------- R68 朋友圈互动红点 ----------
    def _moments_open(self) -> bool:
        w = getattr(self, "_moments_win", None)
        try:
            return bool(w and w.winfo_exists())
        except Exception:
            return False

    def _update_mom_badge(self) -> None:
        """把未读数画到 📸 图标右上角（0 隐藏）。"""
        lbl = getattr(self, "_mom_badge", None)
        btn = getattr(self, "_mom_btn", None)
        if lbl is None or btn is None:
            return
        n = int(getattr(self, "_mom_unread", 0))
        try:
            if n <= 0:
                lbl.place_forget()
                return
            lbl.configure(text=str(n) if n < 100 else "99+")
            self.icon_bar.update_idletasks()
            bx = btn.winfo_x() + btn.winfo_width() - 16
            by = btn.winfo_y() - 2
            lbl.place(x=max(bx, 0), y=max(by, 0))
            lbl.lift()
        except Exception:
            pass

    def _bump_moment_unread(self, ev: dict) -> None:
        """R68：窗口未打开时，他人新动态 / 新赞 / 新评 → 未读 +1。"""
        post = ev.get("post")
        if not isinstance(post, dict):
            return                                    # 删除等：无快照
        pid = post.get("pid") or ev.get("pid")
        likes = {u for u in (post.get("likes") or [])}
        cmts = post.get("comments") or []
        prev = self._mom_sig.get(pid)
        if ev.get("t") == "moment_new":
            from_other = post.get("uid") != self.core.uid
        elif prev is not None:
            added_likes = likes - prev[0]
            added_cmts = cmts[prev[1]:]
            from_other = any(u != self.core.uid for u in added_likes) or \
                any((c or {}).get("uid") != self.core.uid for c in added_cmts)
        else:
            from_other = False
        self._mom_sig[pid] = (likes, len(cmts))
        if from_other and not self._moments_open():
            self._mom_unread += 1
            self._update_mom_badge()

    # 朋友圈 host 桥：widget 回调 → client_core
    def publish_moment(self, text, paths):
        self.core.send_moment_publish(text, paths)

    def toggle_like(self, pid, on):
        self.core.send_moment_like(pid, on)

    def comment_moment(self, pid, text, reply_uid=None, reply_nick=""):
        self.core.send_moment_comment(pid, text, reply_uid, reply_nick)

    def del_moment(self, pid):
        self.core.send_moment_del(pid)

    def fetch_img(self, fn):
        self.core.send_moment_img_get(fn)

    def cover_set_preset(self, preset):
        self.core.send_moment_cover_set_preset(preset)

    def cover_set_img(self, path):
        self.core.send_moment_cover_set_img(path)

    def cover_del(self):
        self.core.send_moment_cover_del()

    def set_sign(self, text):
        self.core.send_sign_set(text)

    # 朋友圈服务器事件：feed 初始化 / 新增 / 更新或删除 / 图片回填
    def _on_moment_feed(self, ev):
        posts = ev.get("posts") or []
        if getattr(self, "moment_list", None):
            self.moment_list.render_feed(posts)
        for p in posts:                          # R68：重建互动签名基线
            if isinstance(p, dict) and p.get("pid") is not None:
                self._mom_sig[p["pid"]] = (
                    {u for u in (p.get("likes") or [])},
                    len(p.get("comments") or []))
        self._mom_unread = 0                     # 拉全量=正在查看 → 清红点
        self._update_mom_badge()

    def _on_moment_update(self, ev):
        if getattr(self, "moment_list", None):
            self.moment_list.upsert(ev.get("post"), ev.get("pid"))
        self._bump_moment_unread(ev)             # R68：他人互动 → 红点

    def _on_moment_data(self, ev, body):
        if getattr(self, "moment_list", None):
            self.moment_list.feed_img(ev.get("fn"), ev.get("ext", ""),
                                      bytes(body or b""))

    def _on_moment_cover(self, ev, body):
        if ev.get("uid") != self.core.uid:
            return
        if getattr(self, "moment_list", None):
            self.moment_list.apply_cover(ev.get("cover"),
                                         bytes(body or b""))

    def _on_profile(self) -> None:
        """个人资料窗口：头像（上传/删除）+ 昵称（只读）+ 个性签名 + 改密码。"""
        if getattr(self, "_profile_win", None) and self._profile_win.winfo_exists():
            self._profile_win.lift()
            return
        dlg = tk.Toplevel(self.root)
        self._profile_win = dlg
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("个人资料")
        dlg.transient(self.root)
        dlg.geometry("+" + str(self.root.winfo_x() + 160) + "+"
                     + str(self.root.winfo_y() + 120))
        dlg.attributes("-topmost", True)
        dlg.resizable(False, False)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "个人资料")
        f = self._f
        sk = self._skin
        me = self.core.me if self.core else {}
        my_uid = self.core.uid if self.core else None

        # 大头像（96px 圆形；左键换图，右键删除）
        av = tk.Canvas(dlg, width=120, height=120, bg=sk["panel_bg"],
                       highlightthickness=0)
        av.pack(pady=(14, 4))
        av.bind("<Button-1>", lambda e: self._pick_avatar_upload(dlg))
        av.bind("<Button-3>", lambda e: self._on_avatar_menu(dlg))
        self._draw_profile_avatar(av, 120, 96, my_uid)

        tk.Label(dlg, text="点击头像更换 · 右键删除", fg=sk["sub"], font=(FONT_FAMILY, 9),
                 bg=sk["panel_bg"]).pack()

        # 昵称（登录标识，只读）
        nick_row = tk.Frame(dlg, bg=sk["panel_bg"])
        nick_row.pack(fill="x", padx=16, pady=(12, 2))
        tk.Label(nick_row, text="昵称", fg=sk["sub"], font=f,
                 bg=sk["panel_bg"]).pack(side="left")
        tk.Label(nick_row, text=self.core.nick if self.core else "?", fg=sk["fg"],
                 font=(FONT_FAMILY, 10, "bold"),
                 bg=sk["panel_bg"]).pack(side="left", padx=8)
        tk.Label(dlg, text="昵称即登录标识，不可修改", fg=self._dp["sub"],
                 font=(FONT_FAMILY, 10), bg=sk["panel_bg"]).pack(padx=16, anchor="w")

        # 个性签名（编辑 + 保存）
        sign_row = tk.Frame(dlg, bg=sk["panel_bg"])
        sign_row.pack(fill="x", padx=16, pady=(10, 2))
        tk.Label(sign_row, text="个性签名", fg=sk["sub"], font=f,
                 bg=sk["panel_bg"]).pack(side="left")
        sign_var = tk.StringVar(value=(me.get("sign") or "")
                                if me else "")
        sign_ent = tk.Entry(sign_row, textvariable=sign_var, font=f, width=20,
                            bg=sk["input_bg"], fg=sk["fg"],
                            insertbackground=sk["fg"], relief="flat",
                            highlightthickness=1,
                            highlightbackground=sk.get("glass_border",
                                                        sk["input_bg"]))
        sign_ent.pack(side="left", padx=8, fill="x", expand=True)

        def _save_sign() -> None:
            sign = sign_var.get().strip()
            if self.core:
                self.core.send_sign_set(sign)
                if self.core.uid is not None:
                    self.core.me["sign"] = sign
                    self.core.known.setdefault(self.core.uid, {})["sign"] = sign
            self._refresh_roster()
            self._refresh_chan_label()
            self.show_toast("个性签名已保存，已同步全员")

        tk.Button(dlg, text="保存签名", command=_save_sign, font=f).pack(
            padx=16, pady=(2, 4), fill="x")

        # 修改昵称密码（复用现有对话框）
        tk.Button(dlg, text="修改昵称密码…", command=self._set_nick_pwd_dialog,
                  font=f).pack(padx=16, pady=(4, 2), fill="x")
        tk.Button(dlg, text="关闭", command=dlg.destroy, font=f).pack(
            padx=16, pady=(0, 12), fill="x")

    def _draw_profile_avatar(self, cv, csize: int, avsize: int,
                             uid: int | None) -> None:
        """在资料窗画大头像（居中，圆形）。"""
        cv.delete("all")
        if not self.core:
            return
        x = (csize - avsize) // 2
        y = (csize - avsize) // 2
        self._avatars.draw(cv, x, y, avsize, self.core.nick,
                           uid=uid, font=(FONT_FAMILY, 26, "bold"))

    def _pick_avatar_upload(self, dlg) -> None:
        """选本地图片上传为头像（≤1MB；服务器校验）。"""
        path = filedialog.askopenfilename(
            parent=dlg, title="选择头像图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.gif *.webp *.bmp"),
                       ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            from widgets import dialogbox
            dialogbox.show_message("头像", f"读取文件失败：{exc}",
                                   kind="error", parent=dlg)
            return
        if len(data) > CFG.avatar_max_bytes:
            from widgets import dialogbox
            dialogbox.show_message("头像", "图片不能超过 1MB",
                                   kind="error", parent=dlg)
            return
        ext = os.path.splitext(path)[1].lstrip(".").lower() or "png"
        if self.core:
            self.core.send_avatar_set(ext, data)
        self._append_sys("⏳ 头像上传中…")

    def _on_avatar_menu(self, dlg) -> None:
        """头像右键菜单（删除头像）。"""
        m = tk.Menu(dlg, tearoff=0)
        m.add_command(label="删除头像",
                      command=lambda: self._del_avatar(dlg))
        try:
            m.tk_popup(dlg.winfo_pointerx(), dlg.winfo_pointery())
        finally:
            m.grab_release()

    def _del_avatar(self, dlg) -> None:
        if self.core:
            self.core.send_avatar_del()
        self._append_sys("头像已删除")

    def _on_error(self, ev: dict) -> None:
        code = ev.get("code")
        if code in ("kicked", "deleted") or (code == "retired" and ev.get("manual_login_required") is True):
            if not self._closed:
                self.request_switch_account()
        elif code in ("conn", "offline"):
            self.status_text.config(text=ev.get("text", "连接异常"))
        elif code == "pwd":
            # 输完密码 drop 重连的窗口期内，旧错误帧/未带密码的 hello 可能再触发
            # 一次同因 "pwd"，导致同一正确密码也要输两次。抑制窗内不重弹；
            # 3s 后若仍报 pwd（真密码错误）则照常再弹。
            if time.time() < getattr(self, "_pwd_muted_until", 0.0):
                return
            self._ask_nick_password(ev.get("text", ""))   # R47-B：需昵称密码
        else:
            self._append_sys(f"⚠ {ev.get('text', '')}")

    def _ask_nick_password(self, reason: str) -> None:
        """R47-B：服务器要求昵称密码（登录校验失败）→ 弹框取密码 →
        core.set_password + drop 触发重连（下一轮 hello 携带）。
        重连循环期间同一原因只弹一次，避免错误帧风暴连环弹框。
        自绘模态框（不用 simpledialog）：切号流程重开第二个 Tk 主窗时，
        simpledialog 的嵌套事件循环在本机偶发原生崩溃导致「切号直接退出」，
        改在 self.root 上 wait_window，杜绝该崩溃点。"""
        if getattr(self, "_pwd_prompt_open", False):
            return
        self._pwd_prompt_open = True
        try:
            pwd = self._ask_nick_password_dialog(reason or "该昵称已设密码")
        finally:
            self._pwd_prompt_open = False
        if pwd:
            self.core.set_password(pwd.strip())
            self.core.drop()               # 触发重连，hello 带密码重试
            self._pwd_muted_until = time.time() + 3.0   # 抑制重连窗口内的重复弹框
        else:
            self._append_sys("⚠ 未输入密码，将无法登录该昵称（可改用其他昵称）")

    def _ask_nick_password_dialog(self, reason: str):
        """R47-B：卡片风「昵称密码」模态框。
        返回输入的密码串（取消/关闭 → None）。
        自绘（不用 simpledialog）：切号流程重开第二个 Tk 主窗时，
        simpledialog 的嵌套事件循环在本机偶发原生崩溃导致「切号直接退出」，
        统一走 widgets.dialogbox 的 wait_window 逻辑，杜绝该崩溃点。"""
        from widgets import dialogbox
        pwd = dialogbox.ask_string(
            "昵称密码", str(reason) + "\n请输入密码：", show="*", parent=self.root)
        return pwd.strip() if pwd else None

    # ---------- 名单 / 群 ----------
    def _pin_key(self, ch: str, to) -> str:
        if ch == "public":
            return "public"
        if ch == "private":
            a, b = sorted((int(self.core.uid), int(to)))
            return f"private:{a}:{b}"
        if ch == "e2ee":
            a, b = sorted((int(self.core.uid), int(to)))
            return f"e2ee:{a}:{b}"
        return f"group:{int(to)}"

    # ---------- R39B 云同步会话状态（采集/应用/变更时刻） ----------
    def _touch_conv_state(self, key: str) -> None:
        """本地会话状态（已读/未读/置顶/归档/静音/草稿）变更时刻。"""
        self._conv_state_ts[key] = time.time()

    def _toggle_pin_conv(self, key: str) -> None:
        self._prefs.toggle_pin(key)
        self._touch_conv_state(key)

    def _toggle_star_conv(self, key: str) -> None:
        """⭐ 置星/取消星标当前会话（更强置顶，显示于置顶分组之上）。"""
        try:
            self._prefs.toggle_star(key)
        except StarsPreservationError as exc:
            self._append_sys(str(exc))
            return
        self._touch_conv_state(key)

    def _toggle_mute_conv(self, key: str) -> None:
        self._prefs.toggle_mute(key)
        self._touch_conv_state(key)

    def _toggle_archive_conv(self, key: str) -> None:
        self._prefs.toggle_archive(key)
        self._touch_conv_state(key)

    def _collect_conv_states(self) -> dict:
        """云备份采集：{pin_key: {ts,read,unread,draft,pin,muted,archived}}。"""
        keys = set(self._last_read) | set(self._drafts) | set(self._conv_state_ts)
        for ch, to in list(self._unread):
            keys.add(self._pin_key(ch, to))
        keys |= set(self._prefs.pinned()) | set(self._prefs.muted()) \
            | set(self._prefs.archived())
        out: dict = {}
        for key in keys:
            ch, to = self._split_draft_key(key)
            if ch is None:
                continue
            out[key] = {
                "ts": max(self._draft_ts.get(key, 0.0),
                          self._conv_state_ts.get(key, 0.0)),
                "read": int(self._last_read.get(key) or 0),
                "unread": int(self._unread.get((ch, to), 0)),
                "draft": str(self._drafts.get(key, "")),
                "pin": self._prefs.is_pinned(key),
                "muted": self._prefs.is_muted(key),
                "archived": self._prefs.is_archived(key),
            }
        return out

    def _apply_conv_states(self, states: dict) -> None:
        """云恢复应用：per 会话键 ts 新者胜；已读游标只前进；刷新列表。"""
        for key, st in (states or {}).items():
            if not isinstance(st, dict):
                continue
            key = str(key)
            ch, to = self._split_draft_key(key)
            if ch is None:
                continue
            ts = float(st.get("ts") or 0)
            if ts and ts <= self._conv_state_ts.get(key, 0.0):
                continue                      # 本地更新 → 保留本地
            read = int(st.get("read") or 0)
            if read > int(self._last_read.get(key) or 0):
                self._last_read[key] = read   # 游标单调前进，不回滚
            if key != self._hist_key():       # 正在看的会话未读不动
                n = int(st.get("unread") or 0)
                if n > 0:
                    self._unread[(ch, to)] = n
                else:
                    self._unread.pop((ch, to), None)
            text = str(st.get("draft") or "")
            if ts >= self._draft_ts.get(key, 0.0):
                if text:
                    self._drafts[key] = text
                    self._draft_ts[key] = ts
                else:
                    self._drafts.pop(key, None)
                    self._draft_ts.pop(key, None)
            if bool(st.get("pin")) != self._prefs.is_pinned(key):
                self._prefs.toggle_pin(key)
            if bool(st.get("muted")) != self._prefs.is_muted(key):
                self._prefs.toggle_mute(key)
            if bool(st.get("archived")) != self._prefs.is_archived(key):
                self._prefs.toggle_archive(key)
            self._conv_state_ts[key] = max(ts, self._conv_state_ts.get(key, 0.0))
        self._refresh_lists()
        self._refresh_archived()
        self._persist_drafts()

    def _line(self, text: str, unread: int = 0, pinned: bool = False,
              archived: bool = False) -> str:
        """会话行文本：置顶 📌 + [归档 📦] + 文本 + 未读徽标 (n)"""
        pre = ("📦 " if archived else "") + ("📌 " if pinned else "")
        suf = f" ({unread})" if unread > 0 else ""
        return pre + text + suf

    # ---------- C6 归档 / 会话静音辅助 ----------
    def _key_to_convo(self, key: str):
        """prefs key -> (ch, to)；会话已不在名单/群则返回 None。"""
        if key == "public":
            return ("public", None)
        if key.startswith("group:"):
            try:
                gid = int(key.split(":", 1)[1])
            except ValueError:
                return None
            return ("group", gid) if gid in self.core.groups else None
        if key.startswith("private:"):
            try:
                _, a, b = key.split(":")
                a, b = int(a), int(b)
            except ValueError:
                return None
            uid = b if self.core.uid == a else a
            if uid in self.core.roster or uid in self.core.known:
                return ("private", uid)      # R25B：离线用户也在名单（known 补）
        if key.startswith("e2ee:"):
            try:
                _, a, b = key.split(":")
                a, b = int(a), int(b)
            except ValueError:
                return None
            uid = b if self.core.uid == a else a
            if uid in self.core.roster or uid in self.core.known:
                return ("e2ee", uid)         # R36：密聊会话（历史侧栏入口）
        return None

    def _convo_label(self, ch: str, to) -> str:
        if ch == "public":
            return "公共频道"
        if ch == "e2ee":
            return f"🔒 {self.core.display_name(to)}"       # R36/R69C9
        if ch == "private":
            if to == self.core.uid:
                return "收藏夹"              # R25C：发给自己
            return self.core.display_name(to)   # R69C9：备注优先，无备注回退昵称
        g = self.core.groups.get(to)
        return f"{g['name'] if g else to}({g.get('member_count', 0)})" if g else f"群{to}"

    def _channel_muted(self, ch: str, to) -> bool:
        return self._prefs.is_muted(self._pin_key(ch, to))

    def _keyword_hit(self, text: str) -> bool:
        """R60：正文是否命中任一关键词提醒词（大小写不敏感，空列表→False）。"""
        if not text:
            return False
        lower = str(text).lower()
        return any(w in lower for w in self._prefs.keywords())

    # ---------- R25D 会话文件夹（prefs 分组 + 列表过滤渲染） ----------
    def _rebuild_folder_bar(self) -> None:
        """重建文件夹标签行：全部 + 各文件夹 + ＋新建；当前文件夹高亮。"""
        for w in self._folder_bar.winfo_children():
            w.destroy()
        f = self._f

        def _mk(label, cmd, active=False, menu_on=None):
            b = tk.Button(self._folder_bar, text=label, font=f, relief="flat",
                          padx=3, command=cmd,
                          fg="#fff" if active else self._skin["sub"],
                          bg=self._skin["accent"] if active else self._skin.get("hover_bg", "#eef1f5"))
            b.pack(side="left", padx=(0, 2))
            if menu_on:
                b.bind("<Button-3>", menu_on)
            return b

        _mk("全部", lambda: self._set_active_folder(None),
            active=self._active_folder is None)
        for fo in self._prefs.folders():
            nm = fo["name"]
            _mk(nm, lambda nm=nm: self._set_active_folder(nm),
                active=self._active_folder == nm,
                menu_on=lambda e, nm=nm: self._folder_chip_menu(e, nm))
        _mk("＋", self._create_folder)

    def _set_active_folder(self, name: str | None) -> None:
        """R25D：切换当前文件夹（None=全部），重绘标签与名单/群。"""
        self._active_folder = name
        self._rebuild_folder_bar()
        self._refresh_lists()

    def _folder_keys(self):
        """R25D：当前文件夹包含的会话键集合；全部模式返回 None（不过滤）。"""
        if self._active_folder is None:
            return None
        for fo in self._prefs.folders():
            if fo["name"] == self._active_folder:
                return set(fo["keys"])
        return set()

    def _folder_add(self, key: str, folder: dict) -> None:
        """R25D：把会话加入文件夹（已在则忽略）。"""
        folders = self._prefs.folders()
        for fo in folders:
            if fo["name"] == folder["name"] and key not in fo["keys"]:
                fo["keys"].append(key)
                break
        self._prefs.set_folders(folders)
        self._append_sys(f"已加入文件夹「{folder['name']}」")
        self._refresh_lists()

    def _folder_remove(self, key: str) -> None:
        """R25D：把会话移出当前文件夹。"""
        folders = self._prefs.folders()
        for fo in folders:
            if fo["name"] == self._active_folder and key in fo["keys"]:
                fo["keys"] = [k for k in fo["keys"] if k != key]
                break
        self._prefs.set_folders(folders)
        self._append_sys("已移出当前文件夹")
        self._refresh_lists()

    def _create_folder(self) -> None:
        """R25D：新建空文件夹。"""
        from widgets import dialogbox
        name = dialogbox.ask_string("新建文件夹", "文件夹名称：", parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()
        folders = self._prefs.folders()
        if any(f["name"] == name for f in folders):
            self._append_sys(f"文件夹「{name}」已存在")
            return
        folders.append({"name": name, "keys": []})
        self._prefs.set_folders(folders)
        self._rebuild_folder_bar()

    def _folder_chip_menu(self, ev, name: str) -> None:
        """R25D：右键文件夹标签 → 删除文件夹（仅解散分组，会话保留）。"""
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="删除文件夹",
                         command=lambda: self._delete_folder(name))
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def _delete_folder(self, name: str) -> None:
        folders = [f for f in self._prefs.folders() if f["name"] != name]
        self._prefs.set_folders(folders)
        if self._active_folder == name:
            self._active_folder = None            # 当前文件夹被删 → 回到全部
        self._rebuild_folder_bar()
        self._refresh_lists()

    def _folder_menu_items(self, menu: tk.Menu, key: str) -> None:
        """R25D：右键菜单里的文件夹子菜单（加入/移出）。"""
        folders = self._prefs.folders()
        if folders:
            sub = tk.Menu(menu, tearoff=0)
            for fo in folders:
                sub.add_command(label=fo["name"],
                                command=lambda fo=fo: self._folder_add(key, fo))
            menu.add_cascade(label="加入文件夹", menu=sub)
        if self._active_folder is not None and key in self._folder_keys():
            menu.add_command(label="移出当前文件夹",
                             command=lambda: self._folder_remove(key))

    def _font_scale(self) -> int:
        """当前字号档下标（0小/1中/2大，prefs 键 font_scale）。"""
        try:
            return max(0, min(len(_FONT_SCALES) - 1,
                              int(self._prefs.get("font_scale", 1))))
        except Exception:
            return 1

    def _font_scale_size(self) -> int:
        """当前字号档对应 pt 字号。"""
        return _FONT_SCALES[self._font_scale()]

    def _apply_font_scale(self, f=None) -> None:
        """R-字号：把当前字号立即注入 消息区+会话列表+输入区（设置变更即时生效）。"""
        if f is None:
            mist = self._skin.get('name', '').startswith('雾岸')
            family, base = body_font() if mist else (FONT_FAMILY, _FONT_SCALES[1])
            f = (family, self._font_scale_size() + base - _FONT_SCALES[1])
        self._f = f
        for w in (getattr(self, "msg_list", None),
                  getattr(self, "roster_list", None),
                  getattr(self, "group_list", None)):
            if w is not None and hasattr(w, "set_font"):
                try:
                    w.set_font(f)
                except Exception:
                    pass
        if getattr(self, "entry", None) is not None:
            try:
                self.entry.config(font=f)
            except Exception:
                pass

    def _refresh_lists(self) -> None:
        self._refresh_roster()
        self._refresh_groups()
        self._refresh_archived()

    # ---------- R63 最后上线相对时间（TG last seen / 微信「最近在线」） ----------
    @staticmethod
    def _last_online_text(last_online: float) -> str:
        """离线用户「最后在线 X 前」相对文案；>7 天回退绝对日期。"""
        if not last_online:
            return "最后在线：未知"
        age = time.time() - float(last_online)
        if age < 0:
            age = 0
        if age < 60:
            return "最后在线 刚刚"
        if age < 3600:
            return f"最后在线 {int(age // 60)} 分钟前"
        if age < 86400:
            return f"最后在线 {int(age // 3600)} 小时前"
        if age < 7 * 86400:
            return f"最后在线 {int(age // 86400)} 天前"
        return "最后在线 " + time.strftime("%Y-%m-%d", time.localtime(last_online))

    def _schedule_lastonline_refresh(self) -> None:
        """低频（30s）刷新离线用户「最后在线」相对文案；跳过无此需求时。"""
        if not getattr(self, "roster_list", None) or not self.core.known:
            self.root.after(30000, self._schedule_lastonline_refresh)
            return
        try:
            self._refresh_roster()
        except Exception:
            pass
        self.root.after(30000, self._schedule_lastonline_refresh)

    def _refresh_roster(self) -> None:
        order: list = []
        q = self._search
        pinned_keys = set(self._prefs.pinned())
        star_keys = set(self._prefs.starred())      # ⭐ 星标会话（置于置顶之上）
        muted_keys = set(self._prefs.muted())
        arch_keys = set(self._prefs.archived())
        mark_keys = set(self._prefs.unread_marks())     # R69C11：手动未读标记
        folder_keys = self._folder_keys()         # R25D：当前文件夹会话键（None=全部）
        # R25B：在线（roster）∪ 离线（known，含 last_online）合并出名单
        users: list = []
        seen: set = set()
        for u in self.core.roster.values():
            users.append(dict(u))
            seen.add(u["uid"])
        for uid, info in self.core.known.items():
            if uid in seen or uid == self.core.uid:
                continue
            users.append({"uid": uid, "nick": info.get("nick", f"用户{uid}")})
        users = [u for u in users
                 if not q or q in u["nick"].lower()
                 or q in self.core.display_name(u["uid"]).lower()]   # R69C9：备注名可搜索
        # 收藏夹（自己）恒置顶；其后星标优先、置顶次之，再按 uid 稳定排序
        users.sort(key=lambda x: (x["uid"] != self.core.uid,
                                  self._pin_key("private", x["uid"]) not in star_keys,
                                  self._pin_key("private", x["uid"]) not in pinned_keys,
                                  x["uid"]))
        items = []
        for u in users:
            key = self._pin_key("private", u["uid"])
            if key in arch_keys:
                continue                          # C6：归档会话不进主名单
            if folder_keys is not None and key not in folder_keys:
                continue                          # R25D：文件夹过滤
            unread = self._unread.get(("private", u["uid"]), 0)
            if u["uid"] == self.core.uid:
                name = "收藏夹"                   # R25C：发给自己
            else:
                name = self.core.display_name(u["uid"])   # R69C9：备注名优先
            pr = self._preview.get(("private", u["uid"]))
            pv = pr[0] if pr else None
            is_bot = (self.core.known.get(u["uid"], {}).get("type") == "bot")  # R35
            if is_bot:
                status = "online"             # bot 永远在线
                name = f"🤖 {u['nick']}"
                if not pv:
                    pv = "机器人 · 私聊发「帮助」"
            else:
                status = "online" if u["uid"] in self.core.roster else "offline"
                last_online = self.core.known.get(u["uid"], {}).get("last_online", 0)
                if status == "offline" and not pv and last_online:
                    pv = self._last_online_text(last_online)
            items.append({
                "key": key,
                "name": name,
                "preview": pv,
                "draft": self._drafts.get(key, ""),          # R32B1 草稿前缀
                "ts": pr[1] if pr else None,
                "unread": unread,
                "pinned": key in pinned_keys,
                "starred": key in star_keys,          # ⭐ 星标会话标记
                "muted": key in muted_keys,
                "mark_unread": key in mark_keys,      # R69C11
                "status": status,
            })
            order.append(u["uid"])
        self.roster_list.set_items(items)
        self._roster_order = order

    def _refresh_groups(self) -> None:
        order: list = []
        q = self._search
        pinned_keys = set(self._prefs.pinned())
        star_keys = set(self._prefs.starred())      # ⭐ 星标会话（置于置顶之上）
        muted_keys = set(self._prefs.muted())
        arch_keys = set(self._prefs.archived())
        mark_keys = set(self._prefs.unread_marks())     # R69C11：手动未读标记
        folder_keys = self._folder_keys()         # R25D：当前文件夹会话键（None=全部）
        groups = [g for g in self.core.groups.values()
                  if not q or q in g["name"].lower()]
        groups.sort(key=lambda x: (self._pin_key("group", x["gid"]) not in star_keys,
                                   self._pin_key("group", x["gid"]) not in pinned_keys,
                                   x["gid"]))
        items = []
        for g in groups:
            key = self._pin_key("group", g["gid"])
            if key in arch_keys:
                continue                          # C6：归档群不进主名单
            if folder_keys is not None and key not in folder_keys:
                continue                          # R25D：文件夹过滤
            unread = self._unread.get(("group", g["gid"]), 0)
            name = f"{'[公] ' if g.get('public') else ''}{g['name']}({g['member_count']})"  # R54：公开群标记
            pr = self._preview.get(("group", g["gid"]))
            items.append({
                "key": key,
                "name": name,
                "preview": pr[0] if pr else None,
                "draft": self._drafts.get(key, ""),          # R32B1 草稿前缀
                "ts": pr[1] if pr else None,
                "unread": unread,
                "pinned": key in pinned_keys,
                "starred": key in star_keys,          # ⭐ 星标会话标记
                "muted": key in muted_keys,
                "mark_unread": key in mark_keys,      # R69C11
                "uid": -g["gid"],        # R9H：负 gid 命名空间，让群列表画群头像（避与用户 uid 撞键）
            })
            order.append(g["gid"])
        self.group_list.set_items(items)
        self._group_order = order
        # R9H：有群头像但本地无缓存 → 懒拉取
        for g in groups:
            if g.get("avatar") and g["gid"] not in self.core.group_avatars:
                self.core.send_group_avatar_get(g["gid"])

    def _refresh_archived(self) -> None:
        """C6：归档会话折叠区（不展开则跳过渲染但保持计数）。"""
        if not getattr(self, "_archived_list", None):
            return
        self._archived_list.delete(0, "end")
        keys: list = []
        for key in self._prefs.archived():
            cv = self._key_to_convo(key)
            if cv is None:
                continue
            ch, to = cv
            unread = self._unread.get((ch, to), 0)
            label = self._convo_label(ch, to)
            label += self._preview_suffix(ch, to)   # T4 归档会话末条预览
            self._archived_list.insert("end", self._line(label, unread, archived=True))
            if self._channel_muted(ch, to):
                self._archived_list.itemconfig(self._archived_list.size() - 1,
                                               fg=self._dp["sub"])
            keys.append(key)
        self._archived_keys = keys

    def _toggle_archived_panel(self, _e=None) -> str:
        """C6：展开/收起归档折叠区（按钮 / Ctrl+9）。"""
        self._archived_show = not self._archived_show
        if self._archived_show:
            self._refresh_archived()
            self._archived_list.pack(fill="x", pady=(0, 2))
            self._arch_btn.config(text="已归档 ▴")
        else:
            self._archived_list.pack_forget()
            self._arch_btn.config(text="已归档 ▾")
        return "break"

    def _on_archived_select(self, _ev=None) -> None:
        sel = self._archived_list.curselection()
        self._archived_sel = sel[0] if sel else None

    def _archived_key(self, idx: int):
        if 0 <= idx < len(self._archived_keys):
            return self._archived_keys[idx]
        return None

    def _open_archived(self, _ev=None) -> None:
        """双击归档会话：打开并取消归档（避免"凭空消失"困惑）。"""
        sel = getattr(self, "_archived_sel", None)
        key = self._archived_key(sel)
        if key is None:
            return
        cv = self._key_to_convo(key)
        if cv is None:
            return
        ch, to = cv
        self._switch_view(ch, to)
        if self._prefs.is_archived(key):
            self._toggle_archive_conv(key)
        self._refresh_lists()
        self._toggle_archived_panel()          # 收起折叠区回到主名单

    def _on_archived_menu(self, ev) -> None:
        sel = self._archived_list.nearest(ev.y)
        key = self._archived_key(sel)
        if key is None:
            return
        cv = self._key_to_convo(key)
        if cv is None:
            return
        ch, to = cv
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="取消归档",
                         command=lambda: (self._toggle_archive_conv(key),
                                          self._refresh_lists(), self._refresh_archived()))
        if self._unread.get((ch, to), 0) > 0:
            menu.add_command(label="标记已读",
                             command=lambda: (self._clear_unread(ch, to),
                                              self._mark_read_key(ch, to),
                                              self._refresh_lists()))
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def _build_stickers(self) -> None:
        """R64：包导航条 + 当前包贴纸行（最近 / 自定义包 / 内置订阅包 / 未订阅试看）。"""
        self._stk_gif_stop()
        for w in self._sticker_nav.winfo_children():
            w.destroy()
        for w in self._sticker_row.winfo_children():
            w.destroy()
        packs = self.core.sticker_packs()
        sel = self._sticker_pack_sel
        if sel.startswith("p:") and sel[2:] not in packs:
            sel = self._sticker_pack_sel = ""     # 包被删除/改名 → 回落「最近」
        self._build_sticker_nav(packs)
        if sel == "":
            if not self._fill_recent_fav():
                self._fill_shop_pack(self._first_sub_pack())   # 无最近/收藏 → 回退首个订阅包
        elif sel.startswith("p:"):
            for code in packs.get(sel[2:], {}):
                self._mk_sticker_btn(code, True)
        else:
            self._fill_shop_pack(sel[2:])

    def _build_sticker_nav(self, packs: dict) -> None:
        """包导航条：🕘最近 | 自定义包（封面/包名）| 内置包（未订阅加🔒）| 🛍 ＋。"""
        sel = self._sticker_pack_sel

        def _tab(text, key, *, image=None):
            active = (key == sel)
            b = tk.Button(self._sticker_nav, text=text, font=(FONT_FAMILY, 9),
                          image=image, compound="left", relief="flat",
                          padx=5, pady=0, cursor="hand2",
                          bg=(self._dp["tab_on_bg"] if active
                              else self._sticker_nav["bg"]),
                          fg=(self._dp["tab_fg"] if active
                              else self._dp["sub"]),
                          command=lambda k=key: self._pick_sticker_pack(k))
            if image is not None:
                b._img = image                # 保引用，防 PhotoImage 被 GC
            b.pack(side="left", padx=1)
            return b

        _tab("🕘", "")
        for name in packs:
            _tab(name, "p:" + name, image=self._pack_cover_thumb(name))
            self._sticker_nav.winfo_children()[-1].bind(
                "<Button-3>", lambda e, n=name: self._pack_menu(n, e))
        subs = set(self.core.sticker_subs or ["basic"])
        for p in (self.core.sticker_shop or []):
            pid = str(p.get("pack_id") or "")
            if not pid:
                continue
            on = pid in subs
            _tab(((p.get("name") or pid) + ("" if on else "🔒")), "s:" + pid)
            self._sticker_nav.winfo_children()[-1].bind(
                "<Button-3>",
                lambda e, i=pid, n=p.get("name") or pid, o=on:
                    self._shop_tab_menu(i, n, o, e))
        tk.Button(self._sticker_nav, text="🛍", font=(FONT_FAMILY, 11),
                  relief="flat", padx=3, pady=0, fg="#4c7de8",
                  command=self._open_sticker_shop).pack(side="left", padx=(6, 1))
        tk.Button(self._sticker_nav, text="＋", font=(FONT_FAMILY, 11),
                  relief="flat", padx=3, pady=0, fg="#4c7de8",
                  command=self._sticker_manager).pack(side="left", padx=1)

    def _pack_cover_thumb(self, pack: str):
        """自定义包封面缩略图（16px 方形）；无封面返回 None（回退纯文字标签）。"""
        path = self.core.pack_cover_path(pack)
        if not path:
            return None
        try:
            from PIL import Image, ImageTk
            im = Image.open(path)
            im.thumbnail((16, 16))
            return ImageTk.PhotoImage(im)
        except Exception:
            return None

    def _pick_sticker_pack(self, key: str) -> None:
        """切换当前包标签（空串=最近），重建贴纸行。"""
        self._sticker_pack_sel = key
        self._build_stickers()

    def _fill_recent_fav(self) -> bool:
        """「最近」页：最近使用 + 收藏；都没内容返回 False（调用方回退首个订阅包）。"""
        subs = self.core.subscribed_stickers()
        recents = [c for c in self._recent_stickers
                   if c in self.core.custom_stickers
                   or any(x.get("code") == c for x in subs)]
        favs = [c for c in self._fav_stickers
                if c in self.core.custom_stickers
                or any(x.get("code") == c for x in subs)]
        for c in recents:
            self._mk_sticker_btn(c, c in self.core.custom_stickers)
        if recents:
            tk.Frame(self._sticker_row, width=1,
                     bg=self._dp["doc_h"]).pack(
                side="left", fill="y", padx=3, pady=4)
        for c in favs:
            self._mk_sticker_btn(c, c in self.core.custom_stickers)
        return bool(recents or favs)

    def _first_sub_pack(self) -> str:
        """默认回退包：首个已订阅内置包；无订阅则取首个内置包。"""
        packs = self.core.sticker_shop or []
        subs = set(self.core.sticker_subs or ["basic"])
        for p in packs:
            if str(p.get("pack_id") or "") in subs:
                return str(p.get("pack_id"))
        return str((packs[0] or {}).get("pack_id") or "") if packs else ""

    def _fill_shop_pack(self, pid: str) -> None:
        """内置包页：已订阅→正常可发；未订阅→试看（灰显 + 订阅按钮）。"""
        pack = next((p for p in (self.core.sticker_shop or [])
                     if str(p.get("pack_id")) == pid), None)
        if pack is None:
            if not self._sticker_row.winfo_children():   # 目录未到时给个占位提示
                tk.Label(self._sticker_row, text="表情包目录加载中…",
                         font=(FONT_FAMILY, 9), fg=self._dp["sub"],
                         bg=self._sticker_row["bg"]).pack(side="left", padx=6)
            return
        on = pid in set(self.core.sticker_subs or ["basic"])
        items = (pack.get("items") or [])[:STICKER_TRIAL_MAX] if not on \
            else (pack.get("items") or [])
        for s in items:
            code = str(s.get("code") or "")
            if not code:
                continue
            if on:
                self._mk_sticker_btn(code, False)
            else:                              # R64 试看：灰显，点击引导订阅
                tk.Button(self._sticker_row, text=s.get("emoji", "?"),
                          font=(FONT_FAMILY, 12), relief="flat", padx=1, pady=0,
                          fg="#9aa0a6",
                          command=lambda n=pack.get("name") or pid:
                              self._trial_hint(n)).pack(side="left", padx=1)
        if not on:
            tk.Label(self._sticker_row, text="试看中 · 未订阅",
                     font=(FONT_FAMILY, 8), fg="#9aa0a6",
                     bg=self._sticker_row["bg"]).pack(side="left", padx=4)
            tk.Button(self._sticker_row, text="＋ 订阅",
                      font=(FONT_FAMILY, 9), relief="flat", padx=4, pady=0,
                      fg="#ffffff", bg="#4c7de8", cursor="hand2",
                      command=lambda i=pid: self.core.send_sticker_sub(i, True)
                      ).pack(side="left", padx=2)

    def _trial_hint(self, name: str) -> None:
        self.show_toast(f"「{name}」未订阅（试看中）：右键标签可订阅", warn=True)

    def _mk_sticker_btn(self, code: str, custom: bool):
        """生成贴纸按钮（内置 emoji 文本 / 自定义缩略图，GIF 缩略图逐帧轮播）；
        点击发送，右键收藏/排序/删除。"""
        if custom:
            meta = self.core.custom_stickers.get(code) or {}
            path = self.core.custom_sticker_path(code)
            btn = None
            if path:
                try:
                    from PIL import Image, ImageTk
                    im = Image.open(path)
                    im.thumbnail((22, 22))
                    ph = ImageTk.PhotoImage(im)
                    btn = tk.Button(
                        self._sticker_row, image=ph, relief="flat",
                        padx=1, pady=0,
                        command=lambda c=code: self._use_custom_sticker(c))
                    btn._img = ph              # 保引用，防 PhotoImage 被 GC
                except Exception:
                    btn = None
            if btn is None:
                btn = tk.Button(
                    self._sticker_row,
                    text=":" + str(meta.get("label") or code) + ":",
                    font=(FONT_FAMILY, 9), relief="flat", padx=2, pady=0,
                    command=lambda c=code: self._use_custom_sticker(c))
            elif str(meta.get("ext") or "").lower() == "gif":
                self._stk_gif_anim(btn, path)   # R64：选择器内 GIF 预览也动画
        else:
            s = next((x for x in self.core.stickers
                      if x.get("code") == code), None)
            btn = tk.Button(
                self._sticker_row, text=(s or {}).get("emoji", "?"),
                font=(FONT_FAMILY, 12), relief="flat", padx=1, pady=0,
                command=lambda c=code: self._use_sticker(c))
        btn.pack(side="left", padx=1)
        btn.bind("<Button-3>", lambda e, c=code: self._sticker_menu(c, e))
        return btn

    # ---------- R64 选择器内 GIF 缩略图轮播 ----------
    def _stk_gif_stop(self) -> None:
        """停表并解绑全部 GIF 缩略图（重建/收起贴纸面板时调用）。"""
        if self._stk_gif_job is not None:
            try:
                self.root.after_cancel(self._stk_gif_job)
            except Exception:
                pass
            self._stk_gif_job = None
        self._stk_gif_btns.clear()

    def _stk_gif_anim(self, btn, path: str) -> None:
        """抽帧（≤STICKER_GIF_FRAMES、缩略 22px）挂到按钮，交给统一时钟推进。"""
        try:
            from PIL import Image, ImageSequence, ImageTk
            im = Image.open(path)
            if not getattr(im, "is_animated", False) or im.n_frames <= 1:
                return
            frames = []
            for fr in ImageSequence.Iterator(im):
                if len(frames) >= STICKER_GIF_FRAMES:
                    break
                fr.load()
                fr.thumbnail((22, 22))
                frames.append(fr.copy())
            if len(frames) < 2:
                return
            phs = [ImageTk.PhotoImage(f) for f in frames]
        except Exception:
            return
        btn._img = phs[0]
        self._stk_gif_btns[btn] = [phs, 0]
        if self._stk_gif_job is None:
            self._stk_gif_job = self.root.after(STICKER_GIF_MS,
                                                self._stk_gif_tick)

    def _stk_gif_tick(self) -> None:
        """推进全部 GIF 缩略图一帧；无存活按钮则自停（不空转）。"""
        self._stk_gif_job = None
        alive = False
        for btn, st in list(self._stk_gif_btns.items()):
            try:
                if not btn.winfo_exists():
                    self._stk_gif_btns.pop(btn, None)
                    continue
                phs, idx = st
                idx = (idx + 1) % len(phs)
                st[1] = idx
                btn.configure(image=phs[idx])
                btn._img = phs[idx]
                alive = True
            except Exception:
                self._stk_gif_btns.pop(btn, None)
        if alive:
            self._stk_gif_job = self.root.after(STICKER_GIF_MS,
                                                self._stk_gif_tick)

    # ---------- R64 包管理菜单 ----------
    def _pack_menu(self, pack: str, ev) -> None:
        """自定义包标签右键：重命名 / 封面 / 删除包。"""
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="✏ 重命名包",
                         command=lambda: self._rename_pack_dlg(pack))
        menu.add_command(label="🖼 设置封面",
                         command=lambda: self._pack_cover_dlg(pack))
        if pack in self.core.sticker_pack_meta:
            menu.add_command(label="♻ 清除封面",
                             command=lambda: self.core.clear_sticker_pack_cover(pack))
        menu.add_separator()
        menu.add_command(label="🗑 删除包（含包内贴纸）",
                         command=lambda: self._del_pack_dlg(pack))
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def _shop_tab_menu(self, pid: str, name: str, on: bool, ev) -> None:
        """内置包标签右键：订阅 / 退订（多包订阅开关）。"""
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label=("退订此包" if on else "订阅此包"),
                         command=lambda: self.core.send_sticker_sub(pid, not on))
        menu.add_separator()
        menu.add_command(label=f"打开商店（{name}）", command=self._open_sticker_shop)
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def _rename_pack_dlg(self, pack: str) -> None:
        from widgets import dialogbox
        new = dialogbox.ask_string(
            "重命名贴纸包", "新包名（1~16 位中英文/数字/空格/_-）：",
            parent=self.root, initialvalue=pack)
        new = (new or "").strip()
        if new and new != pack:
            self.core.rename_sticker_pack(pack, new)

    def _pack_cover_dlg(self, pack: str) -> None:
        """选本地图片作为包封面（≤512KB，服务端按扩展名白名单落盘）。"""
        path = filedialog.askopenfilename(
            title=f"选择「{pack}」的封面（≤512KB）",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.gif *.webp *.bmp")],
            parent=self.root)
        if not path:
            return
        if os.path.getsize(path) > STICKER_MAX_BYTES:
            self.show_toast("封面超过 512KB，请压缩后再上传", warn=True)
            return
        ext = os.path.splitext(path)[1].lower().lstrip(".") or "png"
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as exc:
            self.show_toast(f"读取失败：{exc}", warn=True)
            return
        if self.core.set_sticker_pack_cover(pack, ext, data):
            self._append_sys(f"包「{pack}」封面已更新，等待服务器同步")

    def _del_pack_dlg(self, pack: str) -> None:
        from widgets import dialogbox
        if dialogbox.ask_yesno(
                "删除贴纸包",
                f"删除包「{pack}」？包内全部贴纸将一并删除，不可恢复。",
                parent=self.root):
            self.core.del_sticker_pack(pack)

    # ---------- R35 贴纸商店 ----------
    def _open_sticker_shop(self) -> None:
        """打开/置顶贴纸商店窗；先拉最新目录（回帧驱动刷新）。"""
        if self._shop_dlg is not None and self._shop_dlg.winfo_exists():
            self._shop_dlg.lift()
            self.core.request_sticker_shop()
            return
        self.core.request_sticker_shop()
        from widgets.sticker_shop import StickerShop
        self._shop_dlg = StickerShop(
            self.root, core=self.core,
            on_toggle=lambda pid, on: self.core.send_sticker_sub(pid, on))
        ui_fx.fade_in(self._shop_dlg)             # R43A1 弹窗淡入

    def _refresh_shop_dlg(self) -> None:
        """商店窗开着 → 回帧驱动刷新目录/订阅态。"""
        if self._shop_dlg is not None and self._shop_dlg.winfo_exists():
            try:
                self._shop_dlg.refresh()
            except Exception:
                pass

    def _sticker_menu(self, code: str, ev) -> None:
        """R32B2：贴纸右键菜单——收藏/取消收藏；自定义贴纸另有排序与删除项。"""
        menu = tk.Menu(self.root, tearoff=0)
        if code in self._fav_stickers:
            menu.add_command(label="★ 取消收藏",
                             command=lambda: self._toggle_fav_sticker(code))
        else:
            menu.add_command(label="☆ 加入收藏",
                             command=lambda: self._toggle_fav_sticker(code))
        if code in self.core.custom_stickers:
            # R64 包内排序（服务端重排 order 后广播，客户端只读渲染）
            sort_menu = tk.Menu(menu, tearoff=0)
            for label, d in (("⬆ 上移", "up"), ("⬇ 下移", "down"),
                             ("⏫ 置顶", "top"), ("⏬ 置底", "bottom")):
                sort_menu.add_command(
                    label=label,
                    command=lambda x=d: self.core.reorder_sticker(code, x))
            menu.add_cascade(label="⇅ 包内排序", menu=sort_menu)
            menu.add_separator()
            menu.add_command(label="删除贴纸",
                             command=lambda: self._del_custom_sticker(code))
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def _toggle_fav_sticker(self, code: str) -> None:
        """R32B2：收藏/取消收藏（内置或自定义），prefs 持久化并重排贴纸条。"""
        if code in self._fav_stickers:
            self._fav_stickers.remove(code)
            self._append_sys(f"已取消收藏 :{code}:")
        else:
            if len(self._fav_stickers) >= FAV_STICKER_MAX:
                self._append_sys(f"收藏已满（{FAV_STICKER_MAX} 个），请先取消部分收藏")
                return
            self._fav_stickers.insert(0, code)
            self._append_sys(f"已收藏 :{code}:（显示在贴纸条最前，右键可取消）")
        self._prefs.set("fav_stickers", self._fav_stickers)
        self._build_stickers()

    def _touch_recent_sticker(self, code: str) -> None:
        """表情/贴纸「最近使用」：用过的 code 置前（去重），落盘并重绘贴纸条。"""
        code = str(code or "")
        if not code:
            return
        rec = [c for c in self._recent_stickers if c != code]
        rec.insert(0, code)
        self._recent_stickers = rec[:STICKER_RECENT_MAX]
        self._prefs.set("sticker_recent", self._recent_stickers)
        if getattr(self, "_sticker_on", False):
            self._build_stickers()

    def _use_custom_sticker(self, code: str) -> None:
        """R30C：空输入直接发独立贴纸短码；有输入则追加到末尾。"""
        self._touch_recent_sticker(code)
        token = f"[:{code}:]"
        if not self._entry_text().strip():
            ch, to = self.view
            self.core.send_chat(token, channel=ch, to=to)
        else:
            self.entry.insert("end", token)

    def _del_custom_sticker(self, code: str) -> None:
        """R30C：右键自定义贴纸按钮 → 确认删除（服务器广播清单更新）。"""
        from widgets import dialogbox
        if dialogbox.ask_yesno("删除贴纸", f"删除自定义贴纸 :{code}: ？",
                               parent=self.root):
            self.core.del_custom_sticker(code)

    def _fetch_sticker_img(self, code: str) -> None:
        """R30C：msg_list 渲染贴纸行缺图时触发一次拉取（仅已知短码）。"""
        if code in self.core.custom_stickers:
            self.core.get_custom_sticker(code)

    def _sticker_manager(self) -> None:
        """R30C 自定义表情包管理：选本地图上传（code 唯一，≤512KB）。"""
        path = filedialog.askopenfilename(
            title="选择贴纸（图片或 Lottie .json，≤512KB）",
            filetypes=[("贴纸", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.json")],
            parent=self.root)
        if not path:
            return
        if os.path.getsize(path) > STICKER_MAX_BYTES:
            self.show_toast("图片超过 512KB，请压缩后再上传", warn=True)
            return
        from widgets import dialogbox
        code = dialogbox.ask_string(
            "贴纸短码", "给贴纸取个短码（1~24 位字母/数字/下划线）：",
            parent=self.root)
        code = (code or "").strip()
        if not code:
            return
        if not is_valid_custom_code(code):
            self.show_toast("短码只能用 1~24 位字母/数字/下划线", warn=True)
            return
        ext = os.path.splitext(path)[1].lower().lstrip(".") or "png"
        label = dialogbox.ask_string("贴纸名称", "显示名称（可留空）：",
                                     parent=self.root) or ""
        pack = dialogbox.ask_string("贴纸包", "所属贴纸包名（可留空=归入「我的贴纸」）：",
                                    parent=self.root) or ""
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as exc:
            self.show_toast(f"读取失败：{exc}", warn=True)
            return
        if self.core.add_custom_sticker(code, str(label), ext, data, str(pack)):
            self._append_sys(f"贴纸 :{code}: 已上传，等待服务器同步")
        else:
            self._append_sys("贴纸上传失败（未连接）")

    # ---------- 聊天渲染 ----------
    def _with_remark(self, m: dict) -> dict:
        """R69C9：给消息注入展示昵称（本人视图的备注名优先，无备注回退原昵称）。"""
        uid = m.get("uid")
        if uid is not None and uid != self.core.uid:
            disp = self.core.display_name(uid)
            if disp:
                m["disp_nick"] = disp
        return m

    def _append_msg(self, m: dict) -> None:
        self._with_remark(m)                      # R69C9：备注名优先渲染
        if m.get("thread_root") is not None:      # R34：话题回复不进主列表
            self._on_thread_reply(m)
            return
        self._update_preview(m)               # T4：先刷新会话末条预览（含对方/自己）
        # R15 全透明黑字模式：符合过滤的新消息实时滚入字幕，并重置停留计时
        if self._ghost and not self._in_view(m) and self._ghost_in_filter(m):
            self.msg_list.append(m)
            self._ghost_kick_ttl()
        me = m.get("uid") == self.core.uid
        if me and m.get("seq") is not None:
            self._confirm_pending(m)              # P0 三态：服务器回显 → 发送中行转正
        if not me:
            self._maybe_auto_reply(m)             # R70G：伪装态收 1v1 消息 → 自动回复
        if self._in_view(m):
            if not me:
                self._clear_unread(*self.view)   # 正在看的会话：新消息即清零未读
            self._render_msg(m, me=me)
        elif not me:
            self._bump_unread(m)                  # 其它会话：累计未读 + 红点
            ch, to = self._convo_of_msg(m)
            if not self._channel_muted(ch, to):   # C6：静音会话不闪烁
                if self._in_dnd():
                    # 勿扰时段：不打扰（_flash_taskbar 本身就抑制），
                    # 但自动上报已读回执，让发送方知道自己已读到（本端仍正常计数未读）
                    seq = m.get("seq")
                    if seq is not None:
                        self.core.send_read(ch, to, seq)
                else:
                    self._flash_taskbar(m)        # C7/R31D：未在看 → 闪烁+Toast
            elif self._keyword_hit(m.get("text", "")) and not self._in_dnd():
                # R60 关键词提醒：会话已静音但正文命中关键词 → 例外放行通知。
                # 勿扰（_in_dnd）仍最高优先，此处显式守卫，勿扰内绝不打扰。
                self._flash_taskbar(m)

    def _render_msg(self, m: dict, me: bool = False) -> None:
        self.msg_list.append(m)
        self._refresh_search_hits()       # 新消息到达时保持搜索高亮新鲜（C1）
        self._send_read_now()             # R13：在看会话收到消息即上报已读

    def _send_read_now(self) -> None:
        """R13：把当前会话最新 seq 上报为已读（幂等，服务器只前进）。"""
        ch, to = self.view
        seq = self.core.latest_seq(ch, to)
        if seq is not None:
            self.core.send_read(ch, to, seq)

    # ---------- R70G 忙碌自动回复（仅伪装态；纯本地） ----------
    def _maybe_auto_reply(self, m: dict) -> None:
        """伪装态（老板键）收到 1v1 消息 → 按对端冷却自动回复一条「忙」提示。

        防环路：带 auto 标记的消息不再触发；群/频道不自动回复；老板键关闭时不回复。
        """
        if not self._auto_reply_on or not getattr(self, "_boss_active", False):
            return
        if m.get("channel") != "private" or m.get("auto") or m.get("deleted"):
            return
        uid = m.get("uid")
        text = (self._auto_reply_text or "").strip()
        if uid is None or uid == self.core.uid or not text:
            return
        now = time.time()
        if now - self._auto_reply_at.get(uid, 0.0) < self._auto_reply_cd:
            return
        self._auto_reply_at[uid] = now
        if self.core.send_chat(text, channel="private", to=uid, auto=True):
            self._append_sys("🕶 伪装态：已自动回复对方「忙」提示")

    def _ev_in_view(self, ev: dict) -> bool:
        """edit/del 事件 → 是否属于当前会话视图。"""
        ch = ev.get("channel")
        vch, vto = self.view
        if ch == "public":
            return vch == "public"
        if ch == "private":
            if vch != "private":
                return False
            other = ev.get("uid")
            if ev.get("uid") == self.core.uid:
                other = ev.get("to")
            return other == vto
        return vch == "group" and ev.get("to") == vto

    def _on_msg_edit(self, ev: dict) -> None:
        if self._ev_in_view(ev):
            self.msg_list.update_text(ev.get("seq"), ev.get("text", ""),
                                      ev.get("rich"), ev.get("edits"))

    def _on_msg_del(self, ev: dict) -> None:
        if self._ev_in_view(ev):
            self.msg_list.mark_deleted(ev.get("seq"))

    def _on_msg_reaction(self, ev: dict) -> None:
        """R13 表情回应事件：当前会话内命中才重绘该行回应条。"""
        if self._ev_in_view(ev):
            self.msg_list.set_reactions(ev.get("seq"), ev.get("reactions") or {})

    def _on_msg_read(self, ev: dict) -> None:
        """R13 已读回执事件：更新当前会话回执并重绘（自己消息显 ✓已读）。"""
        key = ev.get("key")
        if key and key == self._pin_key(*self.view):
            self.msg_list.set_reads(self.core.reads.get(key, {}))

    def _on_msg_pin(self, ev: dict) -> None:
        """R13 置顶事件：更新置顶快照；若是当前会话则显示/隐藏横幅。"""
        key = ev.get("key")
        if key == self._pin_key(*self.view):
            self._refresh_pin_bar()

    # ---------- R34 群内话题 Threads ----------
    def _open_thread(self, row) -> None:
        """点根消息「N 条回复」徽标 → 打开/聚焦话题窗口。"""
        raw = getattr(row, "raw", None) or {}
        root_seq = raw.get("seq")
        if root_seq is None:
            return
        root_seq = int(root_seq)
        ch, to = self.view
        key = self._pin_key(ch, to)
        # 已开着同一话题 → 置前即可
        tw = self._thread_win
        if tw is not None and tw.winfo_exists():
            if tw.root_seq == root_seq and tw.key == key:
                try:
                    tw.lift()
                    tw.focus_force()
                except Exception:
                    pass
                return
            tw.destroy()                      # 换话题：关旧窗（on_close 回调清引用）
            self._thread_win = None
        # 窗口内 MsgList 复用主列表的渲染管线（贴纸/回应/菜单等），双击=窗口内引用
        def make_msglist(parent):
            return MsgList(parent, self._f, colors=msg_colors(self._skin),
                           on_row_menu=self._on_msg_menu,
                           on_row_double=lambda idx: self._thread_win and
                           self._thread_win.set_reply(idx),
                           on_row_image=self._on_row_image,
                           on_link=self._on_msg_link,
                           on_voice=self._on_voice,
                           on_voice_end=self._on_voice_end,     # D14 语音连播
                           on_transcribe=(self._voice_stt
                                          if optional.has_stt() else None),  # R批次③ 转文字
                           on_poll_vote=self._on_poll_vote,
                           on_react=self._on_react_seq,
                           on_mention=self._on_mention_click,
                           on_quick_more=self._on_quick_more,
                           on_hashtag=self._on_hashtag_click,
                           on_react_detail=self._on_react_detail,
                           on_sticker_path=self.core.custom_sticker_path,
                           on_sticker_fetch=self._fetch_sticker_img,
                           on_profile=self._open_user_card,   # R69C10 资料卡
                           on_card=self._open_user_card,      # R71 名片卡
                           on_vmemo=self._open_vmemo_player,    # R72 视频留言
                           on_edit_history=self._show_edit_history)  # R70B 编辑历史

        def send(text, reply=None):
            self.core.send_chat(text, channel=ch, to=to,
                                thread_root=root_seq, reply=reply)

        def on_close(_seq):
            self._thread_win = None

        tw = ThreadWindow(self.root, root_msg=raw, key=key,
                          me_uid=self.core.uid, make_msglist=make_msglist,
                          send=send, on_close=on_close)
        ui_fx.fade_in(tw)                         # R43A1 弹窗淡入
        self._thread_win = tw
        # 初始装载：本地历史 + 服务器环形过滤兜底（覆盖重装/换端场景）
        tw.load_msgs(self.core.history(ch, to), me_uid=self.core.uid)
        try:
            self.core.send_thread_fetch(ch, to, root_seq)
        except Exception:
            pass

    def _on_thread_reply(self, m: dict) -> None:
        """话题回复到达：徽标计数 + 话题窗口实时追加 + 会话未读合并（以 seq 为准）。"""
        try:
            root = int(m.get("thread_root"))
        except (TypeError, ValueError):
            return
        me = m.get("uid") == self.core.uid
        in_view = self._in_view(m)
        self._thread_counts[root] = self._thread_counts.get(root, 0) + 1
        if in_view:
            self.msg_list.set_thread_count(root, self._thread_counts[root])
            if not me:
                self._clear_unread(*self.view)
            tw = self._thread_win
            if tw is not None and tw.winfo_exists() and tw.root_seq == root:
                tw.append_msg(m)
            self._send_read_now()
        elif not me:
            self._bump_unread(m)                  # 未读合并：话题回复计入会话未读
            ch, to = self._convo_of_msg(m)
            if not self._channel_muted(ch, to):
                self._flash_taskbar(m)

    def _on_thread_history(self, ev: dict) -> None:
        """THREAD_HISTORY 回帧：合并进窗口（按 seq 去重重建），同时刷新徽标计数。"""
        root = ev.get("root_seq")
        tw = self._thread_win
        if tw is None or not tw.winfo_exists() or tw.root_seq != root:
            return
        msgs = ev.get("msgs") or []
        tw.load_msgs(msgs, me_uid=self.core.uid)
        ch, to = self._convo_of_msg(msgs[0]) if msgs else self.view
        # 以服务器环形为准修正本地徽标（本地环形 300 条可能比服务器少）
        self._thread_counts[root] = len(msgs)
        if self._pin_key(ch, to) == self._pin_key(*self.view):
            self.msg_list.set_thread_count(root, len(msgs))

    # ---------- R13 置顶横幅 ----------
    def _refresh_pin_bar(self) -> None:
        """按当前会话是否有置顶快照显示/隐藏横幅。"""
        key = self._pin_key(*self.view)
        snap = self.core.pins.get(key)
        if snap and (snap.get("text") or snap.get("sticker")):
            txt = snap.get("text") or "表情"
            nick = snap.get("nick", "?")
            self._pin_label.config(text=f"📌 {nick}: {txt[:28]}")
            self.pin_bar.pack(fill="x", before=self._wrap_frame)
        else:
            self.pin_bar.pack_forget()

    def _unpin_current(self) -> None:
        """横幅 ✕：取消当前会话置顶。"""
        ch, to = self.view
        key = self._pin_key(ch, to)
        snap = self.core.pins.get(key)
        if snap:
            self.core.send_pin(ch, to, snap["seq"], on=False)
            self.pin_bar.pack_forget()

    # ---------- R16 群公告横幅 ----------
    def _refresh_announce_bar(self) -> None:
        """按当前会话（群频道）是否公告显示/隐藏横幅。"""
        ch, to = self.view
        announce = ""
        slow = 0
        if ch == "group":
            announce = self.core.group_announces.get(to) or ""
            slow = int((self.core.groups.get(to) or {}).get("slow") or 0)   # R70D
        parts = []
        if announce:
            parts.append(f"📢 {announce}")
        if slow > 0:                              # R70D：群慢速模式当前档位提示
            parts.append(f"🐢 慢速 {slow} 秒")
        if parts:
            self._announce_label.config(text="   ".join(parts))
            self.announce_bar.pack(fill="x", before=self._wrap_frame)
        else:
            self.announce_bar.pack_forget()

    def _apply_apple_dialog(self, dlg, title: str) -> None:
        """弹窗套苹果风：无边框 + 红绿灯标题栏（DialogTitleBar）。

        仅在 Windows 无边框模式下生效；overrideredirect 或标题栏创建失败时
        静默回退原样（不抛异常、绝不阻断启动）。须在建好 dlg、设完 title 之后、
        pack 任何子组件之前调用，DialogTitleBar 才会 pack 在顶部。
        """
        if not (os.name == "nt" and getattr(self, "_frameless", False)):
            return
        try:
            from widgets.title_bar import DialogTitleBar
            dlg.overrideredirect(True)
            DialogTitleBar(dlg, title=title, on_close=dlg.destroy)
        except Exception:
            pass

    def _set_group_announce_dialog(self, gid: int) -> None:
        """群公告设置框：owner/admin 可发布/清除当前群公告。"""
        g = self.core.groups.get(gid)
        if g is None:
            self._append_sys("该群不存在或已解散")
            return
        me = self.core.uid
        if self.group_role(gid, me) not in ("owner", "admin"):
            self._append_sys("仅群主/管理员可设置公告")
            return
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title(f"群公告 · {g.get('name', gid)}")
        dlg.geometry("420x220")
        dlg.attributes("-topmost", True)
        f = self._f
        dp = self._dp
        dlg.configure(bg=dp["win"])
        self._apply_apple_dialog(dlg, "群公告")
        tk.Label(dlg, text="输入群公告内容（留空并发布=清除公告）",
                 fg=dp["sub"], font=f, anchor="w", bg=dp["win"]).pack(fill="x", padx=10, pady=(8, 2))
        box = tk.Text(dlg, height=4, font=f,
                      highlightthickness=1, highlightbackground=dp["border"],
                      bg=dp["input"], fg=dp["fg"])
        box.pack(fill="both", expand=True, padx=10, pady=4)
        box.insert("1.0", self.core.group_announces.get(gid) or "")
        bar = tk.Frame(dlg, bg=dp["win"])
        bar.pack(fill="x", pady=6)

        def _publish() -> None:
            text = box.get("1.0", "end").strip()
            self.core.send_group_announce(gid, text)
            dlg.destroy()

        def _clear() -> None:
            self.core.send_group_announce(gid, "")
            dlg.destroy()

        tk.Button(bar, text="发布", font=f, relief="flat", bg=dp["tab_on_bg"],
                  fg=dp["fg"], command=_publish).pack(side="left", padx=10)
        tk.Button(bar, text="清除", font=f, relief="flat", bg=dp["win"],
                  fg=dp["sub"], command=_clear).pack(side="left")
        tk.Button(bar, text="取消", font=f, relief="flat", bg=dp["win"],
                  fg=dp["sub"], command=dlg.destroy).pack(side="right", padx=10)
        box.focus_force()

    # ---------- R9H 群资料：群简介 / 群头像 ----------
    def _set_group_about_dialog(self, gid: int) -> None:
        """群简介设置框：owner/admin 可发布/清除当前群简介（≤80 字）。"""
        g = self.core.groups.get(gid)
        if g is None:
            self._append_sys("该群不存在或已解散")
            return
        me = self.core.uid
        if self.group_role(gid, me) not in ("owner", "admin"):
            self._append_sys("仅群主/管理员可编辑群简介")
            return
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)
        dlg.title(f"群简介 · {g.get('name', gid)}")
        dlg.geometry("420x220")
        dlg.attributes("-topmost", True)
        f = self._f
        dp = self._dp
        dlg.configure(bg=dp["win"])
        self._apply_apple_dialog(dlg, "群简介")
        tk.Label(dlg, text="输入群简介（≤80 字，留空并保存=清除简介）",
                 fg=dp["sub"], font=f, anchor="w", bg=dp["win"]).pack(
            fill="x", padx=10, pady=(8, 2))
        box = tk.Text(dlg, height=4, font=f, wrap="word",
                      highlightthickness=1, highlightbackground=dp["border"],
                      bg=dp["input"], fg=dp["fg"])
        box.pack(fill="both", expand=True, padx=10, pady=4)
        box.insert("1.0", g.get("about") or "")
        box.bind("<KeyRelease>",
                 lambda e: _len_lbl.config(
                     text=f"{len(box.get('1.0', 'end-1c'))}/80"))
        cnt = tk.Frame(dlg, bg=dp["win"])
        cnt.pack(fill="x", padx=10)
        _len_lbl = tk.Label(cnt, text=f"{len(g.get('about') or '')}/80",
                            fg=dp["sub"], font=(FONT_FAMILY, 8), anchor="e",
                            bg=dp["win"])
        _len_lbl.pack(side="right")
        bar = tk.Frame(dlg, bg=dp["win"])
        bar.pack(fill="x", pady=6)

        def _save() -> None:
            text = box.get("1.0", "end-1c").strip()[:CFG.group_about_max]
            self.core.send_group_about(gid, text)
            dlg.destroy()

        tk.Button(bar, text="保存", font=f, relief="flat", bg=dp["tab_on_bg"],
                  fg=dp["fg"], command=_save).pack(side="left", padx=10)
        tk.Button(bar, text="取消", font=f, relief="flat", bg=dp["win"],
                  fg=dp["sub"], command=dlg.destroy).pack(side="right", padx=10)
        box.focus_force()

    def _set_group_avatar_dialog(self, gid: int) -> None:
        """选本地图片上传为群头像（≤1MB；owner/admin；服务器校验格式权限）。"""
        path = filedialog.askopenfilename(
            parent=self.root, title="选择群头像",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.gif *.webp *.bmp"),
                       ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            from widgets import dialogbox
            dialogbox.show_message("群头像", f"读取文件失败：{exc}",
                                   kind="error", parent=self.root)
            return
        if len(data) > CFG.avatar_max_bytes:
            from widgets import dialogbox
            dialogbox.show_message("群头像", "图片不能超过 1MB",
                                   kind="error", parent=self.root)
            return
        ext = os.path.splitext(path)[1].lstrip(".").lower() or "png"
        self.core.send_group_avatar_set(gid, ext, data)
        self._append_sys("⏳ 群头像上传中…")

    def _clear_group_avatar(self, gid: int) -> None:
        """清除群头像（owner/admin；服务器回 GROUP_AVATAR_DATA 清缓存）。"""
        self.core.send_group_avatar_del(gid)
        self._append_sys("已清除群头像")

    def _append_sys(self, text: str) -> None:
        self.msg_list.append_sys(text)

    def _append_nudge(self, text: str) -> None:
        """R67 拍一拍轻量行：居中灰字斜体，会话内临时渲染，不落盘。"""
        self.msg_list.append({"ts": time.time(), "text": text, "nudge": True},
                             is_system=True)

    # ---------- R55-5 轻量 toast：非阻塞提示，替代信息弹窗（保留确认框） ----------
    def show_toast(self, message: str, duration: int = 2600,
                   warn: bool = False) -> None:
        """右下角滑入的轻提示，自动消失、不抢焦点、不打断操作。

        R69A2：伪装态下冻结所有弹窗（避免老板键挡不住 Toast 暴露摸鱼）。
        """
        if getattr(self, "_boss_active", False):
            return
        try:
            root = self.root
            sk = self._skin
            bg = "#fff3e0" if warn else sk.get("toast_bg", sk["card_bg"])
            fg = "#b26a00" if warn else sk.get("toast_fg", sk["fg"])
            t = tk.Toplevel(root)
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            t.configure(bg=bg)
            lab = tk.Label(t, text=message, bg=bg, fg=fg,
                           font=(FONT_FAMILY, 10), padx=14, pady=8,
                           wraplength=340, justify="left")
            lab.pack()
            t.update_idletasks()
            # 右下角定位（跟随主窗右下角，向内偏移 16px）
            x = root.winfo_rootx() + max(root.winfo_width() - t.winfo_width() - 16, 0)
            y = root.winfo_rooty() + max(root.winfo_height() - t.winfo_height() - 16, 0)
            t.geometry(f"+{x}+{y}")
            # 淡入
            for i in range(1, 11):
                try:
                    t.attributes("-alpha", i / 10)
                except tk.TclError:
                    break
                t.update_idletasks()
            # 停留 + 淡出
            t.after(duration, self._toast_fadeout, t)
        except Exception:
            pass   # 极低概率布局/销毁竞态：静默降级

    def _toast_fadeout(self, t: tk.Toplevel) -> None:
        try:
            for i in range(10, 0, -1):
                t.attributes("-alpha", i / 10)
                t.update_idletasks()
            t.destroy()
        except tk.TclError:
            pass

    # ---------- 未读计数（C2/C5） ----------
    def _convo_of_msg(self, m: dict):
        ch = m.get("channel")
        if ch == "public":
            return ("public", None)
        if ch == "private":
            return ("private", m.get("uid"))
        return ("group", m.get("to"))

    def _bump_unread(self, m: dict) -> None:
        k = self._convo_of_msg(m)
        self._unread[k] = self._unread.get(k, 0) + 1
        self._list_dirty = True

    # ---------- T4 会话列表最后消息预览 ----------
    def _update_preview(self, m: dict) -> None:
        """T4：为新到消息（含自己）更新会话末条摘要+时间。私聊对齐到"对端"键。"""
        ch = m.get("channel")
        if ch == "public":
            k = ("public", None)
        elif ch == "private":
            me = self.core.uid
            other = m.get("to") if m.get("uid") == me else m.get("uid")
            k = ("private", other)
        elif ch == "e2ee":
            me = self.core.uid
            other = m.get("to") if m.get("uid") == me else m.get("uid")
            k = ("e2ee", other)               # R36：密聊会话预览
        else:
            k = ("group", m.get("to"))
        self._preview[k] = (self._preview_text(m), m.get("ts", time.time()))
        self._list_dirty = True

    def _preview_text(self, m: dict) -> str:
        """T4：把原始消息压成一行预览摘要（撤回/表情/图片/已编辑/群昵称前缀）。"""
        if m.get("deleted"):
            return "（消息已撤回）"
        parts = []
        st = m.get("sticker", "")
        if st:
            parts.append(STICKER_BY_CODE.get(st, {}).get("emoji", st))
        if m.get("text"):
            parts.append(m.get("text"))
        if isinstance(m.get("poll"), dict):        # R26A：投票预览占位
            parts.append(f"[投票] {str(m['poll'].get('question', '') or '')[:60]}")
        if m.get("image_path"):
            parts.append("[图片]")
        body = " ".join(parts).strip()
        if m.get("edited"):
            body = f"{body} ✎已编辑" if body else "✎已编辑"
        if body and m.get("channel") == "group":
            if m.get("uid") != self.core.uid and \
                    (m.get("everyone") or self.core.uid in (m.get("mentions") or [])):
                body = f"📣@我 {body}"
            body = f"{m.get('disp_nick') or m.get('nick', '?')}: {body}"   # R69C9 备注优先
        return body

    def _preview_suffix(self, ch: str, to) -> str:
        """T4：会话行尾追加 "· 末条摘要 HH:MM"；无预览则空串。"""
        hit = self._preview.get((ch, to))
        if not hit or not hit[0]:
            return ""
        text, ts = hit
        hhmm = time.strftime("%H:%M", time.localtime(ts))
        return f"  ·  {text}  {hhmm}"

    def _clear_unread(self, ch: str, to) -> None:
        k = (ch, to)
        if self._unread.pop(k, None) is not None:
            self._list_dirty = True
            self._touch_conv_state(self._pin_key(ch, to))   # R39B

    # ---------- R69C11 标为未读 + 稍后处理 ----------
    def _unmark_unread(self, ch: str, to) -> None:
        """清除某会话的「标为未读」标记（打开会话时调用）。"""
        key = self._pin_key(ch, to)
        if self._prefs.is_unread_mark(key):
            self._prefs.set_unread_mark(key, False)
            self._touch_conv_state(key)
            self._list_dirty = True

    def _toggle_unread_mark(self, ch: str, to) -> None:
        """右键「标为未读 / 取消未读标记」。"""
        key = self._pin_key(ch, to)
        on = self._prefs.toggle_unread_mark(key)
        self._touch_conv_state(key)
        self._refresh_lists()
        self.show_toast("已标为未读" if on else "已取消未读标记")

    def _open_snooze(self) -> None:
        """R69C11「稍后处理」清单：列出全部标为未读的会话，双击跳转。"""
        from widgets.stars_panel import SnoozePanel
        marks = []
        for key in self._prefs.unread_marks():
            cv = self._key_to_convo(key)
            if cv is None:
                continue
            ch, to = cv
            pv = self._preview.get((ch, to)) or ("", 0)
            marks.append({"key": key, "label": self._convo_label(ch, to),
                          "preview": pv[0]})
        panel = SnoozePanel(self.root, marks, self._goto_convo,
                            on_clear=self._clear_snooze)
        ui_fx.fade_in(panel)                      # R43A1 弹窗淡入

    def _clear_snooze(self, key: str) -> None:
        """清单内取消某条标记（面板清除按钮）。"""
        self._prefs.set_unread_mark(key, False)
        self._touch_conv_state(key)
        try:
            self._refresh_lists()
        except Exception:
            pass

    def _in_view(self, m: dict) -> bool:
        ch = m.get("channel")
        vch, vto = self.view
        if ch == "public":
            return vch == "public"
        if ch == "e2ee":
            return vch == "e2ee" and (m.get("uid") == vto or m.get("to") == vto)
        if ch == "private":
            return vch == "private" and (m.get("uid") == vto or m.get("to") == vto)
        return vch == "group" and m.get("to") == vto

    def _load_view_history(self) -> None:
        ch, to = self.view
        self._clear_unread(ch, to)                # 进入会话即清零未读
        self._unmark_unread(ch, to)               # R69C11：打开会话即清「标为未读」
        label = {"public": "公共频道", "private": "私聊", "group": "群聊",
                 "e2ee": "密聊"}.get(ch, "会话")
        if ch == "e2ee":
            u = self.core.roster.get(to) or self.core.known.get(to)
            label += f" 🔒: {u['nick'] if u else to}"     # R36：密聊会话标题
            ready = self.core.e2ee_ready(to)
            label += "" if ready else "（会话未建立）"
        elif ch == "private":
            if to == self.core.uid:
                label = "收藏夹"                  # R25C：发给自己（saved）
            else:
                u = self.core.roster.get(to) or self.core.known.get(to)
                label += f": {u['nick'] if u else to}"
                # R25B：在线状态 / 最后上线
                if to in self.core.roster:
                    label += "（在线）"
                elif u and u.get("last_online"):
                    label += "（最后上线 " + time.strftime(
                        "%H:%M", time.localtime(u["last_online"])) + "）"
                else:
                    label += "（离线）"
        elif ch == "group":
            g = self.core.groups.get(to)
            label += f": {g['name'] if g else to}"
        self._chan_base = label                   # R25A/B：基础文案，typing 后缀另加
        self._refresh_chan_label()
        # R34：话题回复不进主列表；重算各根消息徽标计数（切换会话需确定性重建）
        # R39C：首开只装载磁盘最新一页（100 条），更旧的滚到顶再翻
        try:
            msgs = self.core.history_tail(ch, to, self.msg_list.HIST_PAGE)
            if not msgs:
                msgs = self.core.history(ch, to)     # 磁盘无历史时回退内存环（兜底）
            counts: dict = {}
            for m in msgs:
                tr = m.get("thread_root")
                if tr is not None:
                    counts[int(tr)] = counts.get(int(tr), 0) + 1
            for root, n in counts.items():
                self._thread_counts[root] = n
            self.msg_list.load([m for m in msgs if m.get("thread_root") is None],
                               me_uid=self.core.uid)
        except Exception:
            # R-残：装载失败也强制清屏，杜绝上个会话（如公开频道）的头像/气泡残留
            self.msg_list.load([], me_uid=self.core.uid)
            raise
        # R30A：进入会话即按上次读到的位置画未读分隔线（滚到底自动撤线）
        self.msg_list.set_unread_seq(self._last_read.get(self._pin_key(ch, to)))
        self._refresh_search_hits()           # 切会话后重跑当前搜索词（C1）

    def _load_older_page(self, before_seq: int, n: int) -> list:
        """R39C MsgList 懒加载回调：取 seq<before_seq 的更旧一页（升序）。

        磁盘 JSONL 按行号索引 O(页) 读取；话题回复照旧累计徽标计数但不进主列表。
        """
        ch, to = self.view
        page = self.core.history_page(ch, to, before_seq, n)
        for m in page:
            tr = m.get("thread_root")
            if tr is not None:
                k = int(tr)
                self._thread_counts[k] = self._thread_counts.get(k, 0) + 1
        return [m for m in page if m.get("thread_root") is None]

    def _refresh_chan_label(self) -> None:
        """R25A/B：会话标题 = 基础文案 + 「正在输入…」（typing 3s 惰性过期）。"""
        text = self._chan_base
        key = self._pin_key(*self.view)
        typing = self.core.typing_for(key)
        if typing and not (self.view[0] == "private" and self.view[1] == self.core.uid):
            text += " · " + "、".join(typing[:2]) + " 正在输入…"
        # R72 优化：本会话内实时位置共享标记（点标题打开地图）
        sharing = sorted(self._current_geo_markers())
        if sharing:
            text += " · 📍 " + "、".join(self._marker_name(u) for u in sharing[:3]) + " 正在共享位置"
        self.chan_label.config(text=text)
        compose_target = getattr(self, '_compose_target', None)
        if compose_target is not None:
            compose_target.configure(text='发送到：'+self._chan_base)
        if hasattr(self, "_excel_chrome"):
            self._excel_chrome.set_context(text)
        if sharing:
            self.chan_label.configure(cursor="hand2", fg=self._skin.get("accent") or "#06c")
        else:
            self.chan_label.configure(cursor="", fg=self._skin.get("fg") or "#333")
        # 免打扰时段：当前会话标题加「🔕勿扰中」灰标（仅本端视觉，不染未读计数）
        badge = getattr(self, "_dnd_badge", None)
        if badge is None:
            return
        if self._in_dnd():
            if not badge.winfo_ismapped():
                badge.pack(side="right", padx=4)
        else:
            badge.pack_forget()

    def _in_dnd(self) -> bool:
        """是否处于免打扰：开关《_dnd》或处于免打扰时段（R30B dnd_range）。"""
        if getattr(self, "_dnd", False):
            return True
        try:
            return in_dnd_range(self._prefs.dnd_range())
        except Exception:
            return False

    def _maybe_typing(self) -> None:
        """R25A：输入变化时向当前会话广播正在输入（收藏夹/编辑态不广播）。"""
        if self._pending_edit_seq is not None:
            return
        ch, to = self.view
        if ch == "private" and to == self.core.uid:
            return                                # 收藏夹：只有自己，无需指示
        self.core.send_typing(ch, to if ch in ("private", "group") else None)

    # ---------- 视图切换 ----------
    def _on_pick_roster(self, _ev=None) -> None:
        sel = self.roster_list.curselection()
        if not sel:
            return
        uid = self._roster_order[sel[0]] if sel[0] < len(self._roster_order) else None
        if uid is None:
            return
        self._switch_view("private", uid)     # R25C：含自己 → 收藏夹（发给自己）

    def _on_pick_group(self, _ev=None) -> None:
        sel = self.group_list.curselection()
        if not sel:
            return
        gid = self._group_order[sel[0]] if sel[0] < len(self._group_order) else None
        if gid is None:
            return
        self._switch_view("group", gid)

    # ---------- R-：会话列表 hover 快捷操作（标已读/归档/删除） ----------
    def _on_roster_hover_act(self, i: int, act: str) -> None:
        """私聊 hover 操作：复用既有 _clear_unread/归档/删除，不新造后端逻辑。"""
        if not (0 <= i < len(self._roster_order)):
            return
        uid = self._roster_order[i]
        if act == "read":
            self._clear_unread("private", uid)
            self._refresh_roster()
        elif act == "archive":
            self._toggle_archive_conv(self._pin_key("private", uid))
            self._refresh_lists()
        elif act == "delete":
            self._drop_session("private", uid)
            self._refresh_roster()

    def _on_group_hover_act(self, i: int, act: str) -> None:
        """群聊 hover 操作：复用既有 _clear_unread/归档/删除。"""
        if not (0 <= i < len(self._group_order)):
            return
        gid = self._group_order[i]
        if act == "read":
            self._clear_unread("group", gid)
            self._refresh_groups()
        elif act == "archive":
            self._toggle_archive_conv(self._pin_key("group", gid))
            self._refresh_lists()
        elif act == "delete":
            self._drop_session("group", gid)
            self._refresh_groups()

    def _go_public(self) -> None:
        self._switch_view("public", None)

    # ---------- 群操作 ----------
    def _selected_group_id(self):
        sel = self.group_list.curselection()
        if not sel:
            return None
        return self._group_order[sel[0]] if sel[0] < len(self._group_order) else None

    def _on_create_group(self) -> None:
        from widgets import dialogbox
        name = dialogbox.ask_string("建群", "群名称：", parent=self.root)
        if name and name.strip():
            is_pub = dialogbox.ask_yesno(
                "建群",
                "设为公开群？\n\n公开群：所有人都能看到并直接加入。\n私有群（默认）：仅群成员可见，需凭邀请码加入。",
                parent=self.root)
            is_forum = dialogbox.ask_yesno(
                "群类型",
                "设为论坛频道？\n\n论坛：主列表按贴展示，评论走话题窗口。\n否：普通群（自由聊天）。",
                parent=self.root)
            kw = {"public": bool(is_pub)}
            if is_forum:
                kw["forum"] = True
            self.core.create_group(name.strip(), **kw)

    def _on_join_group(self) -> None:
        """R28 加群：凭邀请码入群 + 从列表选群 两路。"""
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("加入群聊")
        dlg.geometry("360x170")
        dlg.attributes("-topmost", True)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "加入群聊")
        f = self._f
        tk.Label(dlg, text="输入群邀请码加入：", fg=self._dp["fg"], font=f,
                 anchor="w").pack(fill="x", padx=10, pady=(8, 2))
        entry = tk.Entry(dlg, font=f)
        entry.pack(fill="x", padx=10, pady=4)

        def _by_invite():
            code = entry.get().strip()
            if not code:
                self.show_toast("请输入邀请码", warn=True)
                return
            dlg.destroy()
            self.core.join_group_by_invite(code)

        def _from_list():
            dlg.destroy()
            gid = self._selected_group_id()
            if gid is None:
                self.show_toast("先在左侧选中一个群", warn=True)
                return
            self.core.join_group(gid)

        tk.Button(dlg, text="凭邀请码加入", command=_by_invite, font=f,
                  width=18).pack(fill="x", padx=10, pady=4)
        tk.Button(dlg, text="从左侧列表选群加入", command=_from_list, font=f,
                  width=18).pack(fill="x", padx=10, pady=(0, 8))

    def _rename_group_dialog(self, gid: int) -> None:
        """R28 群改名框（owner/admin；仿公告设置框 _set_group_announce_dialog）。"""
        g = self.core.groups.get(gid)
        if g is None:
            self._append_sys("该群不存在或已解散")
            return
        me = self.core.uid
        if self.group_role(gid, me) not in ("owner", "admin"):
            self._append_sys("仅群主/管理员可改群名")
            return
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title(f"重命名群 · {g.get('name', gid)}")
        dlg.geometry("360x150")
        dlg.attributes("-topmost", True)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "重命名群")
        f = self._f
        tk.Label(dlg, text="输入新的群名称：", fg=self._dp["sub"], font=f,
                 anchor="w").pack(fill="x", padx=10, pady=(8, 2))
        box = tk.Entry(dlg, font=f)
        box.pack(fill="x", padx=10, pady=4)
        box.insert("0", g.get("name", ""))

        def _do():
            name = box.get().strip()
            dlg.destroy()
            if not name:
                self._append_sys("群名不能为空")
                return
            self.core.rename_group(gid, name)

        tk.Button(dlg, text="确定", command=_do, font=f).pack(pady=6)

    def _on_leave_group(self) -> None:
        gid = self._selected_group_id()
        if gid is None:
            return
        self.core.leave_group(gid)

    # ---------- C8 群管理：成员管理对话框 ----------
    def group_role(self, gid: int, uid: int) -> str:
        """我的/某人 在群 gid 中的角色（owner/admin/member/空）。"""
        g = self.core.groups.get(gid)
        if g is None:
            return ""
        if g.get("owner") == uid:
            return "owner"
        if uid in self.core.group_admins.get(gid, set()):
            return "admin"
        if uid in (m.get("uid") for m in self.core.group_members.get(gid, [])):
            return "member"
        return ""

    def _group_member_muted(self, gid: int, uid: int) -> bool:
        until = self.core.group_mutes.get(gid, {}).get(uid)
        return until is not None and time.time() < until

    def _status_color(self, status: str) -> str:
        """R68：在线状态点色（在线绿/离开黄/忙碌红/离线灰）。"""
        return {"online": "#2e9e5b", "away": "#e0a33e",
                "busy": "#e05252"}.get(status, "#b9bec4")

    def _group_members_dialog(self, gid: int) -> None:
        g = self.core.groups.get(gid)
        if g is None:
            self._append_sys("该群不存在或已解散")
            return
        if self.core.uid is None:
            return
        me = self.core.uid
        my_role = self.group_role(gid, me)
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title(f"群成员 · {g.get('name', gid)}")
        dlg.geometry("380x440")
        f = self._f
        dp = self._dp
        dlg.configure(bg=dp["win"])
        self._apply_apple_dialog(dlg, "群成员")

        n = len(self.core.group_members.get(gid, []))
        m_max = g.get("member_max")
        if m_max:
            header = f"成员（{n}/{m_max}）  ·  权限：{my_role}"
            fg = dp["danger"] if n >= m_max else dp["sub"]
        else:                                     # 旧数据无 member_max 时保持原样
            header = f"成员（{n}）  ·  权限：{my_role}"
            fg = dp["sub"]
        tk.Label(dlg, text=header, fg=fg, font=f, anchor="w", bg=dp["win"]).pack(
            fill="x", padx=10, pady=6)
        hide_inv = tk.BooleanVar(value=False)      # R57：普通成员可选隐藏隐身上线者
        by_status = tk.BooleanVar(value=True)      # R69C12：按在线状态分组（默认开）
        members = list(self.core.group_members.get(gid, []))
        members.sort(key=lambda m: (self.group_role(gid, m["uid"]) not in
                                    ("owner", "admin"), m["uid"]))

        box = tk.Frame(dlg, bg=dp["win"])
        box.pack(side="left", fill="both", expand=True, padx=10, pady=4)
        sb = tk.Scrollbar(box)
        sb.pack(side="right", fill="y")
        body = tk.Canvas(box, yscrollcommand=sb.set, highlightthickness=0,
                         bg=dp["bg"])
        body.pack(side="left", fill="both", expand=True)
        sb.config(command=body.yview)
        inner = tk.Frame(body, bg=dp["bg"])
        win = body.create_window((0, 0), window=inner, anchor="nw")

        role_lbl = {"owner": "👑群主", "admin": "🛡管理", "member": ""}

        def _refresh_inner():
            for w in inner.winfo_children():
                w.destroy()

        def _row(m):
            uid = m["uid"]
            role = self.group_role(gid, uid)
            muted = self._group_member_muted(gid, uid)
            row = tk.Frame(inner, bg=dp["bg"], padx=4, pady=2)
            row.pack(fill="x")
            nick = m.get("nick", str(uid))
            if uid == me:
                nick += "（我）"
            # R68：群成员在线状态点（QQ 风格；以实时 roster 为准）
            ro = self.core.roster.get(uid)
            st = ((ro.get("status") or m.get("status") or "online")
                  if ro else "offline")
            tk.Label(row, text="●", fg=self._status_color(st), bg=dp["bg"],
                     font=f).pack(side="left")
            inv = "👻" if m.get("invisible") else ""   # R57：隐身上线者标记
            badge = role_lbl.get(role, "") + ("🔇禁言" if muted else "") + \
                (" " + inv if inv else "")
            tk.Label(row, text=f"{nick} {badge}", fg=dp["fg"], font=f,
                     anchor="w", bg=dp["bg"]).pack(side="left")
            can_manage = ((my_role == "owner" and role in ("member", "admin") and uid != me)
                          or (my_role == "admin" and role == "member"))
            if can_manage:
                btn = tk.Menubutton(row, text="管理", font=f, relief="raised",
                                    bg=dp["tab_on_bg"])
                btn.menu = tk.Menu(btn, tearoff=0)
                if my_role == "owner":
                    if role == "admin":
                        btn.menu.add_command(
                            label="取消管理员", font=f,
                            command=lambda u=uid: (self.core.set_admin(gid, u, False),
                                                   msg("已请求取消其管理员资格")))
                    else:
                        btn.menu.add_command(
                            label="设为管理员", font=f,
                            command=lambda u=uid: (self.core.set_admin(gid, u, True),
                                                   msg("已请求设为管理员")))
                    btn.menu.add_separator()
                for mins in (10, 30, 60):
                    btn.menu.add_command(
                        label=f"禁言 {mins} 分钟", font=f,
                        command=lambda mm=mins, u=uid: (self.core.mute_member(
                            gid, u, mm * 60), msg(f"已请求禁言 {mm} 分钟")))
                btn.menu.add_command(
                    label="自定义禁言…", font=f,
                    command=lambda u=uid: self._mute_custom(gid, u))
                if muted:
                    btn.menu.add_command(
                        label="解除禁言", font=f,
                        command=lambda u=uid: (self.core.mute_member(gid, u, 0),
                                               msg("已请求解除禁言")))
                btn.menu.add_separator()
                btn.menu.add_command(
                    label="移出群聊", font=f,
                    command=lambda u=uid, n=nick: self._kick_confirm(gid, u, n))
                btn["menu"] = btn.menu
                btn.pack(side="right")
            row.bind("<Button-3>",
                     lambda e, u=uid, r=role: self._member_row_menu(e, gid, u, r))

        def _reload():
            # 重新按当前 server 状态刷新；成员来自 core.group_members
            _refresh_inner()
            live = [m for m in list(self.core.group_members.get(gid, []))
                    if not (hide_inv.get() and m.get("invisible"))]  # R57：过滤隐身上线者
            if by_status.get():                     # R69C12：按状态分组 + 组内角色优先
                live.sort(key=lambda m: (MEMBER_STATUS_ORDER.index(_status_of(m))
                                         if _status_of(m) in MEMBER_STATUS_ORDER else 9,
                                         self.group_role(gid, m["uid"]) not in
                                         ("owner", "admin"), m["uid"]))
                counts = {}
                for m in live:
                    counts[_status_of(m)] = counts.get(_status_of(m), 0) + 1
                cur = None
                for m in live:
                    s = _status_of(m)
                    if s != cur:
                        cur = s
                        tk.Label(inner,
                                 text=f"● {MEMBER_STATUS_LABEL.get(s, s)}（{counts.get(s, 0)}）",
                                 fg=self._status_color(s), bg=dp["bg"],
                                 font=(FONT_FAMILY, 8, "bold"), anchor="w").pack(
                            fill="x", padx=4, pady=(5, 1))
                    _row(m)
            else:                                   # 原行为：仅角色优先
                live.sort(key=lambda m: (self.group_role(gid, m["uid"]) not in
                                         ("owner", "admin"), m["uid"]))
                for m in live:
                    _row(m)
            inner.update_idletasks()
            body.config(scrollregion=body.bbox("all"))

        def _status_of(m):
            """R69C12：成员当前在线状态（实时 roster 优先，离线/未知一律 offline）。"""
            ro = self.core.roster.get(m["uid"])
            return ((ro.get("status") or m.get("status") or "online")
                    if ro else "offline")

        def msg(t):
            self._append_sys(t)

        def _kick_confirm(gid_, uid_, nick_):
            from widgets import dialogbox
            if dialogbox.ask_yesno("移出群聊", f"确定将 {nick_} 移出群聊？",
                                   parent=dlg):
                self.core.kick_member(gid_, uid_)
                msg(f"已请求将 {nick_} 移出群聊")

        def _mute_custom(gid_, uid_):
            from widgets import dialogbox
            s = dialogbox.ask_string("自定义禁言", "禁言时长（分钟，正整数）：",
                                     parent=dlg)
            if not s:
                return
            try:
                mins = int(s)
            except ValueError:
                dialogbox.show_message("输入有误", "请输入分钟数",
                                       kind="warning", parent=dlg)
                return
            if mins <= 0:
                dialogbox.show_message("输入有误", "需为正整数",
                                       kind="warning", parent=dlg)
                return
            self.core.mute_member(gid_, uid_, mins * 60)
            msg(f"已请求禁言 {mins} 分钟")

        def _member_row_menu(ev, gid_, uid_, role_):
            if not (my_role == "owner" or (my_role == "admin" and role_ == "member")):
                return
            rmenu = tk.Menu(dlg, tearoff=0)
            if my_role == "owner" and uid_ != me:
                if role_ == "admin":
                    rmenu.add_command(label="取消管理员",
                                      command=lambda: self.core.set_admin(gid_, uid_, False))
                elif role_ == "member":
                    rmenu.add_command(label="设为管理员",
                                      command=lambda: self.core.set_admin(gid_, uid_, True))
                rmenu.add_separator()
            for mins in (10, 30, 60):
                rmenu.add_command(label=f"禁言 {mins} 分钟",
                                  command=lambda mm=mins: self.core.mute_member(gid_, uid_, mm * 60))
            if self._group_member_muted(gid_, uid_):
                rmenu.add_command(label="解除禁言",
                                  command=lambda: self.core.mute_member(gid_, uid_, 0))
            rmenu.add_separator()
            rmenu.add_command(label="移出群聊",
                              command=lambda: self._kick_confirm(gid_, uid_, "该成员"))
            try:
                rmenu.tk_popup(ev.x_root, ev.y_root)
            finally:
                rmenu.grab_release()

        _reload()
        # R69C12：按在线状态分组（在线/离开/忙碌/离线）；关闭则回到「角色优先」平铺
        tk.Checkbutton(dlg, text="按在线状态分组 ●", variable=by_status,
                       command=_reload, bg=dp["win"], fg=dp["fg"], font=f,
                       selectcolor=dp["bg"], anchor="w").pack(
            fill="x", padx=10)
        # R57：普通成员可选开关——开启后不再显示「隐身上线」的成员
        tk.Checkbutton(dlg, text="隐藏隐身上线成员 👻", variable=hide_inv,
                       command=_reload, bg=dp["win"], fg=dp["fg"], font=f,
                       selectcolor=dp["bg"], anchor="w").pack(
            fill="x", padx=10, pady=(0, 4))
        self._members_dlg = {"gid": gid, "reload": _reload, "dlg": dlg}
        dlg.protocol("WM_DELETE_WINDOW",
                     lambda: (setattr(self, "_members_dlg", None), dlg.destroy()))

    # ---------- C7 通知：任务栏闪烁 + 免打扰 + R31D 隐身 Toast ----------
    def _flash_taskbar(self, m: dict | None = None) -> None:
        """新消息到达且本窗口未在前台时闪烁任务栏 +（B1）右下角假办公 Toast。"""
        if getattr(self, "_boss_active", False):
            return                                    # R69A2/A4：伪装态绝不打断（只记未读）
        if getattr(self, "_dnd", False):
            return                                    # 免打扰：不闪烁
        if in_dnd_range(self._prefs.dnd_range()):     # R30B：免打扰时段内同样免闪
            return
        if self.core.uid is None:
            return
        # 前台 = 主窗可见且未隐藏到迷你条/boss
        try:
            if self.root.state() == "normal" and self.root.focus_displayof():
                return
        except Exception:
            pass
        try:
            hwnd = self.root.winfo_id()
            _flash_window(hwnd)
        except Exception:
            pass
        self._play_notify_sound()                 # R67：新消息提示音（后台提醒时发声）
        if m is not None and not getattr(self, "_ghost", False):
            self._toast_notify(m)                 # R31D：字幕模式已有展示，不重复弹

    def _play_notify_sound(self) -> None:
        """R67 新消息提示音：读 prefs['notify_sound']（off/soft/default/ding，与网页端语义一致）。"""
        if getattr(self, "_boss_active", False):
            return                                    # R69A2：伪装态一律静音
        if not CFG.hardware_enabled:
            return                                    # REL-01：硬件禁用不播放系统声音
        if winsound is None:
            return
        s = str(self._prefs.get("notify_sound", "default") or "default")
        try:
            if s == "off":
                return
            if s == "soft":
                winsound.MessageBeep(winsound.MB_OK)                  # 轻短
            elif s == "ding":
                winsound.MessageBeep(winsound.MB_ICONASTERISK)        # 系统叮
            else:                                                     # default
                winsound.MessageBeep(winsound.MB_ICONINFORMATION)
        except Exception:
            pass

    def _toast_notify(self, m: dict) -> None:
        """R31D B1：隐身友好 Toast。默认假办公文案（不透出昵称/正文）；
        prefs['toast_stealth']=False 时显示真实「昵称：摘要」。"""
        try:
            from widgets.stealth_toast import stealth_text
            if self._prefs.get("toast_stealth", True):
                body = stealth_text()
            else:
                nick = str(m.get("nick") or "同事")
                preview = str(m.get("text") or "").strip().replace("\n", " ")
                body = f"{nick}：{preview[:40]}" if preview \
                    else f"{nick} 发来新消息"
            self._toast.show(body)
        except Exception:
            pass

    # ---------- R67 拍一拍：轻量行渲染 + 后台提醒 + 发送 ----------
    def _on_nudge(self, ev: dict) -> None:
        """R67 拍一拍事件：当前会话渲染轻量行；非当前会话闪烁+提示音+定制 Toast。"""
        nick = str(ev.get("nick") or "有人")
        me = ev.get("uid") == self.core.uid
        target_me = ev.get("target") is not None and ev.get("target") == self.core.uid
        if me and not self._in_view(ev):
            return                                    # 自己在别处拍的：不打扰
        if target_me:
            text = f"{nick} 拍了拍你"
        else:
            tn = str(ev.get("target_nick") or "ta")
            text = f"{nick} 拍了拍 {tn}"
        if self._in_view(ev):
            self._append_nudge(text)
            return
        if me:
            return
        self._flash_taskbar()                         # 只闪烁（无 Toast，避免 40 字摘要）
        if not getattr(self, "_ghost", False):
            self._toast.show(text)                    # R31D 语义：隐身字幕模式不弹

    def _send_nudge(self, raw: dict) -> None:
        """R67 发送拍一拍：target=被拍者 uid；私聊 to=对端 uid，群聊 to=gid。
        发送成功且当前会话 → 本地乐观渲染。"""
        ch, to = self.view
        target = raw.get("uid")
        if ch == "private" and target == self.core.uid:
            return                                    # 收藏夹等自己会话不拍
        if not self.core.send_nudge(ch, to if ch in ("private", "group") else None,
                                    target=target):
            self._append_sys("拍一拍发送失败（5 秒内只能拍一次）")
            return
        if self._in_view({"channel": ch, "uid": target, "to": to}):
            tname = str(raw.get("nick") or "ta")
            self._append_nudge(f"{self.core.nick} 拍了拍 {tname}")

    # ---------- R68 窗口抖动：抖动本窗口 + 提醒 + 发送 ----------
    def _shake_window(self) -> None:
        """R68 窗口抖动：读取当前几何，按偏移序列抖动后复原（~40ms×8）。"""
        try:
            size = f"{self.root.winfo_width()}x{self.root.winfo_height()}"
            ox, oy = self.root.winfo_x(), self.root.winfo_y()
        except Exception:
            return
        offsets = [(10, 0), (-10, 0), (8, 4), (-8, -4),
                   (6, 0), (-6, 0), (3, 0), (-3, 0)]

        def step(i: int) -> None:
            try:
                if i >= len(offsets):
                    self.root.geometry(f"{size}+{ox}+{oy}")     # 复原
                    return
                dx, dy = offsets[i]
                self.root.geometry(f"{size}+{ox + dx}+{oy + dy}")
            except tk.TclError:
                return
            self.root.after(40, lambda: step(i + 1))

        step(0)

    def _on_shake(self, ev: dict) -> None:
        """R68 窗口抖动事件：抖本窗口 + 闪烁任务栏 + 提示音；当前会话额外渲染一行。"""
        if ev.get("uid") == self.core.uid:
            return                                    # 自己发的（服务器已排除，兜底）
        nick = str(ev.get("nick") or "有人")
        text = f"{nick} 向你发送了窗口抖动"
        self._shake_window()
        if self._in_view(ev):
            self._append_sys(text)
        self._flash_taskbar()
        if not getattr(self, "_ghost", False):
            self._toast.show(text)

    def _send_shake(self) -> None:
        """R68 发送窗口抖动：私聊抖对端，群聊抖群全体（复用拍一拍链路）。"""
        ch, to = self.view
        if not self.core.send_shake(ch, to if ch in ("private", "group") else None):
            self._append_sys("窗口抖动发送失败（10 秒内只能发送一次）")
            return
        self._append_sys("已发送窗口抖动")

    def _shake_roster(self, i: int) -> None:
        """R68 双击私聊头像 → 向该好友发送窗口抖动。"""
        if not (0 <= i < len(self._roster_order)):
            return
        uid = self._roster_order[i]
        if uid is None or uid == self.core.uid:
            return                                    # 收藏夹（自己）不抖
        if self.core.send_shake("private", uid):
            self.show_toast("已发送窗口抖动")
        else:
            self.show_toast("窗口抖动发送失败（10 秒内只能发送一次）", warn=True)

    def _shake_group(self, i: int) -> None:
        """R68 双击群头像 → 向该群发送窗口抖动。"""
        if not (0 <= i < len(self._group_order)):
            return
        gid = self._group_order[i]
        if gid is None:
            return
        if self.core.send_shake("group", gid):
            self.show_toast("已发送窗口抖动")
        else:
            self.show_toast("窗口抖动发送失败（10 秒内只能发送一次）", warn=True)

    # ---------- R30A 未读分隔线：记录各会话"读到哪" ----------
    def _mark_read_current(self) -> None:
        """把当前会话最新 seq 记入 _last_read（切走前调用，供下次进入画分隔线）。"""
        ch, to = self.view
        self._mark_read_key(ch, to)

    def _mark_read_key(self, ch: str, to) -> None:
        seq = self.core.latest_seq(ch, to)
        if seq is not None:
            key = self._pin_key(ch, to)
            self._last_read[key] = seq
            self._touch_conv_state(key)       # R39B：状态变更入云同步快照

    # R60 关键词提醒：设置页保存（字符串含中文逗号也可解析）
    def _save_kw_remind(self, entry) -> None:
        try:
            val = entry.get() if entry.winfo_exists() else ""
        except Exception:
            val = ""
        self._prefs.set_keywords(str(val))
        n = len(self._prefs.keywords())
        self._append_sys(f"🔔 关键词提醒已保存（{n} 个关键词）")

    def _toggle_dnd(self) -> None:
        self._dnd = not getattr(self, "_dnd", False)
        self._append_sys(("已开启免打扰" if self._dnd else "已关闭免打扰")
                         + "（新消息不再闪烁任务栏）")
        self._refresh_chan_label()        # 即时刷新标题🔕灰标
        # 免打扰状态也写进本地偏好，重启保留
        try:
            self._prefs.set("dnd", self._dnd)
        except Exception:
            pass

    # ---------- 发送 / 表情 ----------
    def _entry_text(self) -> str:
        """Text 输入框全文（去尾换行）"""
        return self.entry.get("1.0", "end-1c")

    def _insert_evbody(self) -> None:
        """把 @全体 插进输入框光标处（服务器据此做群内全员广播，识别 @全体/@全员）。"""
        self.entry.insert("insert", "@全体 ")
        self.entry.focus_set()

    def _refresh_evbody(self) -> None:
        """「📣@所有」刷新：群聊时显示为可用彩色；非群聊时灰显禁用 + 点击提示原因。"""
        try:
            if getattr(self, "_evbody_btn", None) is None:
                return
            b = self._evbody_btn
            show = self.view[0] == "group"
            if show != bool(b.winfo_manager()):
                if show:
                    b.pack(side="left", before=self._send_btn)
                else:
                    b.pack_forget()
            if not show:                       # 非群聊：灰显并置禁用（bind 仍给提示）
                b.config(state="disabled", fg="#b0b0b0")
            else:
                b.config(state="normal", fg=self._skin.get("accent", "#4f6ef2"))
        except Exception:
            pass

    def _ime_composing(self) -> bool:
        """R56 Windows：查询焦点是否处于输入法组字（composition）状态。

        组字未确认时敲回车是「提交候选字」，不应触发发送。非 Windows 或
        查询失败一律返回 False（按不组字处理，保证回车仍可发送）。
        """
        if os.name != "nt":
            return False
        try:
            import ctypes
            from ctypes import wintypes as wt
            u32 = ctypes.windll.user32
            imm = ctypes.windll.imm32
        except Exception:
            return False
        try:
            imm.ImmReleaseContext.restype = wt.BOOL
            imm.ImmReleaseContext.argtypes = [wt.HWND, ctypes.c_void_p]
            imm.ImmGetContext.restype = ctypes.c_void_p
            imm.ImmGetContext.argtypes = [wt.HWND]
            imm.ImmGetOpenStatus.restype = wt.BOOL
            imm.ImmGetOpenStatus.argtypes = [ctypes.c_void_p]
            imm.ImmGetCompositionStringW.restype = ctypes.c_long
            imm.ImmGetCompositionStringW.argtypes = [
                ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, wt.DWORD]
        except Exception:
            return False
        try:
            hwnd = u32.GetForegroundWindow()
            himc = imm.ImmGetContext(hwnd)
            if not himc:
                return False
            try:
                if imm.ImmGetOpenStatus(himc) == 0:
                    return False
                GCS_COMPSTR = 0x0008          # 进行中的组字串
                n = imm.ImmGetCompositionStringW(himc, GCS_COMPSTR, None, 0)
                return n > 0
            finally:
                imm.ImmReleaseContext(hwnd, himc)
        except Exception:
            return False

    def _on_entry_return(self, _e=None):
        if self._ac_top is not None:         # 候选列表打开时 Enter=选中
            self._ac_choose()
            return "break"
        if self._ime_composing():
            return "break"                   # R56 中文组字未确认：回车提交候选而非发送
        if time.time() - self._last_send < _ENTRY_SEND_GAP:
            return "break"                   # 丢弃 Hold 回车自动重复，防连发
        self._send()
        return "break"                       # 阻止 Text 默认插入换行

    def _on_entry_newline(self, _e=None):
        self.entry.insert("insert", "\n")    # Shift+Enter 显式换行
        return "break"

    # ---------- R32A2 输入框多行自适应 ----------
    def _on_entry_modified(self, _e=None) -> None:
        """内容任何变化（键入/粘贴/撤销/程序写入）→ 空闲时重算高度。"""
        self.entry.edit_modified(False)      # 复位标志，下次修改仍触发
        self.root.after_idle(self._adjust_entry_height)

    def _adjust_entry_height(self) -> None:
        """输入框随内容自适应。纯自动：1→6 行；若用户曾手动拖高把手，
        则手动高度为下限，内容超出时继续顶高（自动+手动混合，双击把手可清除）。"""
        try:
            n = self.entry.count("1.0", "end-1c", "displaylines")
            n = n[0] if isinstance(n, tuple) else n
        except Exception:
            n = 1
        n = int(n or 1)
        manual = getattr(self, "_entry_manual_lines", 0)
        if manual > 0:
            target = max(n, manual)          # 内容多少行就多高，但至少 manual 行
        else:
            target = max(3, min(6, n))       # 输入区保留三行；手动高度仍优先
        if int(self.entry.cget("height")) != target:
            self.entry.config(height=target)

    # ---------- B5 @提及 + emoji 补全 ----------
    def _bind_autocomplete(self) -> None:
        self._ac_top = None
        self._ac_list = None
        self._ac_kind = None                 # "at" | "emoji" | "cmd"(R46)
        self._ac_vals = []                   # R46：候选值（cmd 候选为 (cmd,desc) 元组）
        self.entry.bind("<KeyRelease>", self._on_entry_key)
        self.entry.bind("<Up>", self._ac_key_nav)
        self.entry.bind("<Down>", self._ac_key_nav)
        self.entry.bind("<Tab>", self._ac_tab)
        self.entry.bind("<Escape>", self._ac_escape)

    def _ac_close(self) -> None:
        if self._ac_top is not None:
            self._ac_top.destroy()
            self._ac_top = None
            self._ac_list = None
            self._ac_kind = None
            self._ac_vals = []

    def _ac_prefix(self):
        """光标前最后一个 @xxx / :xxx 前缀 → (kind, prefix)；无则 (None, None)。"""
        txt = self.entry.get("1.0", "insert")
        at, colon = txt.rfind("@"), txt.rfind(":")
        if at < 0 and colon < 0:
            return None, None
        if at > colon:
            after = txt[at + 1:]
            if after and " " not in after and "\n" not in after:
                return "at", after
        elif colon >= 0:
            after = txt[colon + 1:]
            if after and " " not in after and "\n" not in after:
                return "emoji", after
        return None, None

    def _on_entry_key(self, ev) -> None:
        # TG：纯导航/修饰键不重算候选（Left/Right/Home/End 移动光标不重建补全）
        nav = frozenset(("Return", "Escape", "Tab", "Up", "Down",
                         "Left", "Right", "Home", "End", "Prior", "Next",
                         "Shift_L", "Shift_R", "Control_L", "Control_R",
                         "Alt_L", "Alt_R"))
        if ev.keysym in nav:
            return
        self._refresh_ac()
        self._maybe_typing()              # R25A：输入变化 → 广播正在输入
        self._draft_dirty = True          # R29B：输入变化 → 节流推草稿（_poll 兜底）

    def _refresh_ac(self) -> None:
        kind, prefix = self._ac_prefix()
        if kind:
            self._ac_show(kind, prefix)
            return
        # R46：bot 私聊会话 → 输入为单个 token（无空格/换行）时补全 bot 命令
        if self.view[0] == "private" and self.view[1] in BOT_BY_UID:
            raw = self._entry_text()
            tok = raw.strip()
            if tok and (" " in tok or "\n" in raw):
                self._ac_close()             # 已在打正文 → 不再干扰
            elif self._ac_candidates("cmd", tok):
                self._ac_show("cmd", tok)
            else:
                self._ac_close()
        else:
            self._ac_close()

    def _ac_candidates(self, kind: str, prefix: str) -> list:
        if kind == "at":
            # R29C：群内优先 @ 群成员（含离线成员），其次在线好友；去重保序
            seen, out = set(), []
            if self.view[0] == "group":
                gid = self.view[1]
                for m in self.core.group_members.get(gid, []):
                    nick = str(m.get("nick") or "")
                    if (nick and nick != self.core.nick
                            and nick.lower().startswith(prefix.lower())
                            and nick not in seen):
                        seen.add(nick)
                        out.append(nick)
            for u in sorted(self.core.roster.values(), key=lambda x: x["uid"]):
                nick = u.get("nick") or ""
                if (u["uid"] != self.core.uid and nick
                        and nick.lower().startswith(prefix.lower())
                        and nick not in seen):
                    seen.add(nick)
                    out.append(nick)
            return out
        if kind == "cmd":                     # R46：bot 命令候选（值= (cmd,desc) 元组）
            bot = BOT_BY_UID.get(self.view[1])
            if not bot:
                return []
            low = (prefix or "").lower()
            return [(cmd, desc) for cmd, desc in bot.commands
                    if cmd.lower().startswith(low)]
        return [c for c in STICKER_BY_CODE
                if c.lower().startswith(prefix.lower())]

    def _ac_show(self, kind: str, prefix: str) -> None:
        cands = self._ac_candidates(kind, prefix)
        if not cands:
            self._ac_close()
            return
        if self._ac_top is None:
            self._ac_top = tk.Toplevel(self.root)
            self._ac_top.overrideredirect(True)
            self._ac_list = tk.Listbox(self._ac_top, height=min(6, len(cands)),
                                       font=self._f, exportselection=False)
            self._ac_list.pack()
            self._ac_list.bind("<Button-1>", lambda e: self._ac_choose())
            _make_draggable(self._ac_top)
        else:
            self._ac_list.delete(0, "end")
        self._ac_kind = kind
        self._ac_vals = cands
        for c in cands:
            # cmd 候选显示「命令 — 说明」，其余直接显示字符串
            self._ac_list.insert("end",
                                 c if isinstance(c, str) else f"{c[0]}  — {c[1]}")
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height()
        self._ac_top.geometry(f"+{x}+{y}")
        self._ac_top.lift()
        self._ac_list.selection_clear(0, "end")
        self._ac_list.selection_set(0)

    def _ac_move(self, step: int) -> None:
        lb = self._ac_list
        if lb is None or lb.size() == 0:
            return
        sel = lb.curselection()
        i = (sel[0] + step) % lb.size() if sel else (0 if step > 0 else lb.size() - 1)
        lb.selection_clear(0, "end")
        lb.selection_set(i)
        lb.see(i)

    def _ac_key_nav(self, ev):
        if self._ac_top is None:
            # R12：无补全时 ↑/↓ 翻本会话已发送历史（对齐 TG field 历史回显）
            return self._hist_nav(1 if ev.keysym == "Up" else -1)
        self._ac_move(1 if ev.keysym == "Down" else -1)
        return "break"

    # ---------- R12 输入历史 ↑/↓ 回显（对齐 TG input field history） ----------
    def _hist_key(self) -> str:
        """本会话的输入历史键（与草稿同键）。"""
        ch, to = self.view
        return self._pin_key(ch, to)

    def _record_send(self, text: str) -> None:
        """发送成功后记录（去重相邻重复；新→旧序；上限 _HIST_N）。"""
        if not text.strip():
            return
        key = self._hist_key()
        lst = self._send_hist.setdefault(key, [])
        if lst and lst[0] == text:
            return
        lst.insert(0, text)
        del lst[_HIST_N:]

    def _hist_nav(self, delta: int) -> str | None:
        """↑(1)/↓(-1) 翻历史。进入浏览前暂存当前输入；↓ 到底恢复暂存。"""
        key = self._hist_key()
        lst = self._send_hist.get(key) or []
        if not lst:
            return None
        if self._hist_cur != key:
            self._hist_cur = key
            self._hist_pos[key] = -1
            self._hist_draft[key] = self._entry_text()   # 暂存进入前的输入
        pos = self._hist_pos.get(key, -1) + delta
        pos = max(-1, min(pos, len(lst) - 1))
        self._hist_pos[key] = pos
        if pos < 0:                                       # 退到底 → 恢复暂存
            self.entry.delete("1.0", "end")
            self.entry.insert("1.0", self._hist_draft.get(key, ""))
        else:
            self.entry.delete("1.0", "end")
            self.entry.insert("1.0", lst[pos])
        self.entry.see("end")
        self.entry.focus_set()
        return "break"

    def _reset_hist(self) -> None:
        """切换会话时清理浏览态（历史数据保留）。"""
        self._hist_cur = None

    # ---------- R12 草稿自动保存（会话级 + prefs['drafts'] 持久化） ----------
    def _save_draft(self) -> None:
        """切走前把当前输入存为本会话草稿（空内容则清除，内存态）。
        若正在↑翻历史且未改动 → 保存进入浏览前的暂存草稿。
        R29B：记录本地时间并推给服务器（换端恢复）。"""
        ch, to = self.view
        key = self._pin_key(ch, to)
        text = self._entry_text()
        pos = self._hist_pos.get(key, -1)
        lst = self._send_hist.get(key) or []
        if 0 <= pos < len(lst) and text == lst[pos]:
            text = self._hist_draft.get(key, "")
        if text.strip():
            self._drafts[key] = text
            self._draft_ts[key] = time.time()
        else:
            self._drafts.pop(key, None)
            self._draft_ts.pop(key, None)
        self._push_draft(key)

    def _push_draft(self, key: str) -> None:
        """R29B：把某会话草稿推给服务器（空=清除）。未登录/断线跳过，重连 welcome 会带回。"""
        if getattr(self.core, "uid", None) is None:
            return
        ch, to = self._split_draft_key(key)
        if ch:
            self.core.send_draft(ch, to, self._drafts.get(key, ""))

    @staticmethod
    def _split_draft_key(key: str) -> tuple:
        """会话键 → (channel, to)；public/private:a:b/e2ee:a:b/group:gid 形态。"""
        if key == "public":
            return "public", None
        if key.startswith("group:"):
            try:
                return "group", int(key.split(":", 1)[1])
            except (IndexError, ValueError):
                return None, None
        if key.startswith("private:"):
            try:
                parts = key.split(":")
                return "private", int(parts[2])
            except (IndexError, ValueError):
                return None, None
        if key.startswith("e2ee:"):
            try:
                parts = key.split(":")
                return "e2ee", int(parts[2])      # R36：密聊会话草稿
            except (IndexError, ValueError):
                return None, None
        return None, None

    def _on_draft_sync(self, ev: dict) -> None:
        """R29B：welcome 带回服务器草稿 → 按 ts 合并（新者胜）；
        本地更新于服务器的会话反向推给服务器补同步。"""
        cur_key = self._hist_key()
        current_typed = self._entry_text().strip()
        for d in ev.get("drafts") or []:
            key = str(d.get("key") or "")
            if not key:
                continue
            text = str(d.get("text") or "")
            ts = float(d.get("ts") or 0)
            self._remote_ts[key] = ts
            if key in self._drafts and self._draft_ts.get(key, 0) >= ts:
                continue                       # 本地更新 → 保留本地
            self._drafts[key] = text
            self._draft_ts[key] = ts
            if key == cur_key and not current_typed and not self._hist_pos.get(key, -1) >= 0:
                self.entry.delete("1.0", "end")
                if text:
                    self.entry.insert("1.0", text)
                    self.entry.see("end")
        # 本地比服务器新 → 反推同步（防旧服务器值覆盖后漏推）
        for key, text in list(self._drafts.items()):
            if self._draft_ts.get(key, 0) > self._remote_ts.get(key, 0):
                self._push_draft(key)
        self._persist_drafts()

    def _restore_draft(self) -> None:
        """进入会话后回填该会话草稿（无草稿则清空输入框，防跨会话串字）。"""
        text = self._drafts.get(self._hist_key())
        self.entry.delete("1.0", "end")
        if text:
            self.entry.insert("1.0", text)
            self.entry.see("end")

    def _clear_draft(self, key: str) -> None:
        """发送成功后清草稿：内存 + 磁盘同步移除；R29B 同时清服务器草稿。"""
        self._drafts.pop(key, None)
        self._draft_ts.pop(key, None)
        self._push_draft(key)
        try:
            d = dict(self._prefs.get("drafts", {}) or {})
            if key in d:
                d.pop(key)
                self._prefs.set("drafts", d)
        except Exception:
            pass

    def _persist_drafts(self) -> None:
        """退出前把全部内存草稿合并写盘（去空条目）。"""
        try:
            d = dict(self._prefs.get("drafts", {}) or {})
            for k, v in self._drafts.items():
                if v and v.strip():
                    d[k] = v
                else:
                    d.pop(k, None)
            for k in [k for k, v in d.items() if not v or not v.strip()]:
                d.pop(k)
            self._prefs.set("drafts", d)
        except Exception:
            pass

    def _ac_tab(self, _e=None):
        if self._ac_top is not None:
            self._ac_choose()
            return "break"
        # R46：bot 私聊空/单 token 输入 → Tab 列出全部命令
        if self.view[0] == "private" and self.view[1] in BOT_BY_UID:
            tok = self._entry_text().strip()
            if " " not in tok and self._ac_candidates("cmd", tok):
                self._ac_show("cmd", tok)
                return "break"
        return None

    def _ac_escape(self, _e=None):
        if self._ac_top is not None:
            self._ac_close()
            return "break"
        return None

    def _ac_choose(self) -> None:
        lb = self._ac_list
        if lb is None:
            return
        sel = lb.curselection()
        if not sel:
            return
        idx = sel[0]
        kind = self._ac_kind
        vals = self._ac_vals
        self._ac_close()
        self.entry.focus_set()
        if kind == "cmd":                    # R46：整行替换为命令（bot 私聊无前缀触发符）
            if idx < len(vals):
                cmd = vals[idx][0] if isinstance(vals[idx], tuple) else vals[idx]
                self.entry.delete("1.0", "end")
                self.entry.insert("1.0", cmd + " ")
                self.entry.mark_set("insert", "end")
            return
        value = lb.get(idx)
        txt = self.entry.get("1.0", "insert")
        trig = "@" if kind == "at" else ":"
        idx = txt.rfind(trig)
        if idx < 0:
            return
        plen = len(txt) - idx
        self.entry.delete(f"insert-{plen - 1}c", "insert")   # 保留 @ / : 触发符
        if kind == "at":
            self.entry.insert("insert", value + " ")
        else:
            self.entry.insert("insert", value + ":")

    def _use_sticker(self, code: str) -> None:
        self._touch_recent_sticker(code)
        if not self._entry_text().strip():
            ch, to = self.view
            self.core.send_chat("", sticker=code, channel=ch, to=to)
        else:
            self.entry.insert("end", f":{code}:")

    def _toggle_stickers(self) -> None:
        self._sticker_on = not self._sticker_on
        if self._sticker_on:
            self._build_stickers()               # R64：展开时按当前包/订阅态重建
            self._sticker_nav.pack(fill="x", pady=(2, 0))
            self._sticker_row.pack(fill="x", pady=(2, 0))
        else:
            self._stk_gif_stop()                 # 收起即停 GIF 缩略图轮播
            self._sticker_nav.pack_forget()
            self._sticker_row.pack_forget()

    def _send(self) -> None:
        raw_lines = self._entry_text().split("\n")
        # R41F：引用标记只可能是首行（_quote 固定插在 1.0）→ 只剥首行，
        # 正文里以「↩ 」开头的行不再被误删
        is_quote = bool(raw_lines) and raw_lines[0].startswith("↩ ")
        lines = raw_lines[1:] if is_quote else raw_lines
        text = "\n".join(lines).strip()
        # R59：发送/编辑时解析富文本 → [[text,kind,href],...]（服务器白名单清洗后存储）
        rich_wire = ([[seg[0], seg[1], seg[2] if len(seg) > 2 and seg[2] else ""]
                      for seg in rich.parse(text)] if text else None)
        if not is_quote:
            # 用户手动删掉了 ↩ 引用行 → 清掉残留引用快照，防止误挂引用发出
            self._pending_reply = None
        ch, to = self.view
        # C3 编辑：带待编辑 seq → 发编辑请求而非新消息
        if self._pending_edit_seq is not None:
            seq = self._pending_edit_seq
            self._pending_edit_seq = None
            self._drop_reply_state()              # 编辑中可能引用过 → 防泄漏到下一发
            self.entry.delete("1.0", "end")
            if not text:
                return
            self._last_send = time.time()
            self.core.send_edit(seq, text, rich=rich_wire)
            self._clear_draft(self._pin_key(ch, to))   # R12：编辑发送后清草稿
            return
        if not text:
            if self._pending_reply is not None:
                # 引用模式下空发送：客户端提前拦，避免服务器回 ⚠「消息不能为空」
                self._pending_reply = None
                self.entry.delete("1.0", "end")   # 清掉 ↩ 引用标记行
                self._append_sys("已取消引用（发送内容不能为空）")
            return
        reply = self._pending_reply               # C4 引用回复快照
        self._pending_reply = None
        self.entry.delete("1.0", "end")
        self._last_send = time.time()
        self._record_send(text)                   # R12：写入本会话输入历史
        self._clear_draft(self._pin_key(ch, to))  # R12：发送成功清草稿
        if ch == "e2ee":                          # R36：密聊会话走端到端加密发送
            if not self.core.send_e2ee_chat(text, to):
                self._append_failed_row(text, channel=ch, to=to, reply=reply,
                                        burn=False, silent=False)
            return
        ok = self.core.send_chat(text, channel=ch, to=to, reply=reply,
                                 burn=self._burn_mode,      # R14：阅后即焚模式
                                 silent=self._silent_mode,  # R26C：静默发送
                                 disguise=self._disguise_mode,  # R70E：消息伪装
                                 rich=rich_wire)            # R59：富文本段
        if ok:                                    # P0 三态：先本地「发送中」行，回显后移除
            self._append_pending(text, channel=ch, to=to, reply=reply,
                                 burn=self._burn_mode,
                                 silent=self._silent_mode,
                                 disguise=self._disguise_mode,
                                 rich=rich_wire)
        else:                                     # R31C：失败 → 本地失败气泡 + ❗ 重发
            self._append_failed_row(text, channel=ch, to=to, reply=reply,
                                    burn=self._burn_mode,
                                    silent=self._silent_mode,
                                    disguise=self._disguise_mode,
                                    rich=rich_wire)

    def _drop_reply_state(self) -> None:
        """C4/C3 状态卫生：丢弃挂起的引用（编辑态退出/清输入框处同步调用，
        防止引用快照泄漏到下一次发送）。"""
        self._pending_reply = None

    def _on_kb_click(self, bot_uid, cmd: str) -> None:
        """R46：点 bot 消息下的键盘按钮 = 向该 bot 发送指令文本（等同手敲）。
        当前不在该 bot 会话时先切过去，让回复即时可见。"""
        if bot_uid is None or not cmd:
            return
        if self.view != ("private", bot_uid):
            self._switch_view("private", bot_uid)
        if not self.core.send_chat(cmd, channel="private", to=bot_uid):
            self._append_failed_row(cmd, channel="private", to=bot_uid,
                                    reply=None, burn=False, silent=False)

    def _append_failed_row(self, text: str, **payload) -> None:
        """R31C：发送失败 → 本地乐观追加自己气泡（failed 标记 + 重发参数），
        气泡右侧画红 ❗，点击重发；成功后 drop_local_row 移除避免回显重复。"""
        self.msg_list.append({
            "ts": time.time(), "uid": self.core.uid, "seq": None,
            "nick": getattr(self.core, "nick", "?") or "?",
            "text": text, "failed": True, "resend": payload,
        })

    def _resend_failed(self, idx: int) -> None:
        """R31C：点击 ❗ 重发；成功 → 移除本地失败行（等服务器回显正式消息）。"""
        raw = self.msg_list.get_row(idx)
        if not raw or not raw.get("failed"):
            return
        payload = dict(raw.get("resend") or {})
        if payload.get("channel") == "e2ee":      # R36：密聊失败重发走加密通道
            if self.core.send_e2ee_chat(raw.get("text", ""), payload.get("to")):
                self.msg_list.drop_local_row(raw)
                self._append_sys("已重新发送")
            else:
                self._append_sys("重发仍失败：请检查连接后再次点击 ❗")
            return
        if self.core.send_chat(raw.get("text", ""), **payload):
            self.msg_list.drop_local_row(raw)
            self._append_sys("已重新发送")
        else:
            self._append_sys("重发仍失败：请检查连接后再次点击 ❗")

    # ---------- P0 三态：发送中（本地乐观行）→ 服务器确认 → 已送达/已读 ----------
    _PENDING_TTL = 8.0                        # 秒：超时未确认 → 转失败行（❗ 可重发）

    def _append_pending(self, text: str, **payload) -> None:
        """发送成功 → 本地乐观插入「发送中」行；服务器回显后由 _confirm_pending 移除。

        复用失败行的字段骨架（seq=None），另打 pending 标记渲染 ⏳发送中。"""
        raw = {
            "ts": time.time(), "uid": self.core.uid, "seq": None,
            "nick": getattr(self.core, "nick", "?") or "?",
            "text": text, "pending": True,
            "channel": payload.get("channel", "public"),
            "to": payload.get("to"),
        }
        for k in ("reply", "burn", "silent", "disguise", "rich", "thread_root"):
            if payload.get(k) is not None:
                raw[k] = payload[k]
        self._pending_rows.append(raw)
        self.msg_list.append(raw)
        self.root.after(int(self._PENDING_TTL * 1000),
                        lambda: self._pending_timeout(raw))

    def _pending_timeout(self, raw: dict) -> None:
        """P0 三态：发送中行超时未获服务器确认 → 降级为失败行（❗ 可重发）。"""
        if raw not in self._pending_rows:
            return
        raw["pending"] = False
        raw["failed"] = True
        payload = {k: raw.get(k) for k in
                   ("channel", "to", "reply", "burn", "silent",
                    "disguise", "rich", "thread_root")}
        raw["resend"] = payload
        self._pending_rows.remove(raw)
        self.msg_list.redraw_all()

    def _confirm_pending(self, m: dict) -> None:
        """P0 三态：收到服务器回显的自己消息（带 seq）→ 移除对应发送中行。

        匹配：同会话 + 同正文 + 时间接近（局域网回显即时，顺序匹配列表头）。"""
        if not self._pending_rows:
            return
        ch, to = m.get("channel"), m.get("to")
        mt = m.get("ts")
        if isinstance(mt, (int, float)) and abs(mt - time.time()) > 2:
            mt = None                             # 历史装载的同文本消息不误删
        for raw in list(self._pending_rows):
            if raw.get("channel") == ch and raw.get("to") == to \
                    and raw.get("text") == m.get("text") \
                    and mt is not None \
                    and abs(raw.get("ts", 0) - mt) < 2.0:
                self.msg_list.drop_local_row(raw)
                self._pending_rows.remove(raw)
                return

    # ---------- R19 语音：录音（R41A winmm waveIn 直录 → PCM → WAV） + 播放 ----------
    _VOICE_RATE = 8000                       # 与 voice_api.SAMPLE_RATE 对齐（单声道 16bit）
    _VOICE_MIN = 0.5                         # 最短录音秒数（过短不发）

    def _on_voice(self, idx: int, path: str, rate=1.0) -> None:
        """点击语音气泡播放：winsound 异步播放本地 WAV（点方自己后台播放，不阻塞 UI）。

        功能③ 倍速：rate != 1.0 时先用 voice_api.resample_wav 对 PCM 变速重采样
        后写临时 WAV 再播放（winsound 不支持 rate 参数，详见 voice_api）。
        """
        if not os.path.exists(path):
            self.show_toast("本地语音文件不存在（可能是历史缓存已清理）", warn=True)
            return
        if not CFG.hardware_enabled:
            self.show_toast("本地试用已禁用音频设备", warn=True)
            return
        if winsound is None:
            self.show_toast("当前系统无音频播放支持", warn=True)
            return
        try:
            speed = float(rate or 1.0)
            if abs(speed - 1.0) < 1e-9:
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return
            try:
                import voice_api, tempfile
                with open(path, "rb") as f:
                    wav = f.read()
                new_wav = voice_api.resample_wav(wav, speed)
                tmp = os.path.join(tempfile.gettempdir(), "moeyu_voice_rate.wav")
                with open(tmp, "wb") as f:
                    f.write(new_wav)
                winsound.PlaySound(tmp, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                # 重采样/写盘失败 → 降级正常速播放，不让语音不可用
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            self.show_toast("播放失败（文件损坏或格式不支持）", warn=True)

    def _on_voice_end(self, idx: int) -> None:
        """D14 语音连播：一条播完 → 开关开启时自动播下一条有本地文件的语音。"""
        if not self._prefs.get("voice_autoplay"):
            return
        rows = getattr(self.msg_list, "_rows", None)
        if not rows:
            return
        rate = getattr(self.msg_list, "_voice_rate", 1.0)
        for j in range(int(idx) + 1, len(rows)):
            r = rows[j]
            p = getattr(r, "voice_path", None)
            if getattr(r, "voice", False) and p and os.path.exists(p):
                self.msg_list.voice_started(j, getattr(r, "voice_dur", 0.0), rate)
                self._on_voice(j, p, rate)
                return

    def _toggle_voice_autoplay(self) -> None:
        """D14「＋」菜单：语音连播开关（prefs 持久化，无系统行）。"""
        on = not self._prefs.get("voice_autoplay")
        self._prefs.set("voice_autoplay", bool(on))
        self.show_toast("🔁 语音连播已开启" if on else "语音连播已关闭")

    def _toggle_record(self) -> None:
        """🎙 切换：未录音 → 开始；录音中 → 忽略（需在录音条点完成/取消）。

        R41A：voice_api.MicRecorder（winmm waveIn）直采 8kHz/16bit/单声道，
        不再依赖外部 ffmpeg 进程；无输入设备/启动失败均明确提示。
        """
        if self._recorder is not None:
            return
        import voice_api
        if not voice_api.available():
            self.show_toast("未找到可用麦克风（系统无音频输入设备）", warn=True)
            return
        rec = voice_api.MicRecorder()
        if not rec.start():
            self.show_toast("无法启动录音（麦克风可能被占用）", warn=True)
            return
        self._recorder = rec
        self._rec_data = bytearray()
        self._rec_start = time.time()
        self._rec_ticks = 0
        self._rec_th = threading.Thread(target=self._rec_drain, daemon=True)
        self._rec_th.start()
        self._vrec_btn.config(text="⏺", bg="#ffd9d9")
        self._voice_bar.pack(fill="x")
        self._rec_lbl.config(text="● 录音中 0.0s")

    def _rec_tick(self) -> None:
        """主线程轮询：录音中刷新计时标签（不碰子线程数据锁太久）。"""
        if self._recorder is None:
            return
        el = time.time() - self._rec_start
        self._rec_ticks += 1
        if self._rec_ticks % 4 == 0:               # 约 0.5s 刷新一次文本
            self._rec_lbl.config(text=f"● 录音中 {el:.1f}s")

    def _rec_drain(self) -> None:
        """子线程：把 MicRecorder 帧队列搬进 _rec_data（8kHz/16bit/单声道 PCM）。"""
        rec = self._recorder
        while rec is not None and self._recorder is rec:
            try:
                frame = rec.frames.get(timeout=0.2)
            except queue.Empty:
                continue
            with self._rec_lock:
                self._rec_data.extend(frame)

    def _stop_record(self, send: bool) -> None:
        """完成/取消：停设备、收尾数据，send=True 且时长足够则发语音。"""
        rec, self._recorder = self._recorder, None
        if rec is not None:
            rec.stop()
        if self._rec_th is not None and self._rec_th.is_alive():
            self._rec_th.join(timeout=2)
        self._rec_th = None
        with self._rec_lock:
            data = bytes(self._rec_data)
        self._vrec_btn.config(text="🎙", bg=self._vrec_default_bg)
        self._voice_bar.pack_forget()
        if not send:
            return
        # 8kHz/单声道/16bit → 每样本 2 字节；不足最短时长则报短
        dur = round(len(data) / (self._VOICE_RATE * 2), 1)
        if not data or dur < self._VOICE_MIN:
            self.show_toast("录音过短，未发送", warn=True)
            return
        wav = self._pcm_to_wav(data, self._VOICE_RATE, 1, 2)
        ch, to = getattr(self, "view", ("public", None))
        if not self.core.send_voice(ch, to, wav, dur):
            self.show_toast("发送失败（可能未连接或权限不足）", warn=True)

    @staticmethod
    def _pcm_to_wav(pcm: bytes, rate: int, channels: int, sampwidth: int) -> bytes:
        """PCM(签名字节) → 合法 WAV 字节流（wave 模块正确写头，长度可靠）。"""
        import io
        import wave
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(sampwidth)
            w.setframerate(rate)
            w.writeframes(pcm)
        return buf.getvalue()

    # ---------- 快捷键（对标 TG；避开 Ctrl+Alt+H boss 全局热键） ----------
    def _bind_shortcuts(self) -> None:
        # 全局快捷键：按下注册表 + 用户偏好（r5b 可改绑/禁用），先解绑旧绑定再重绑
        for p, _ in getattr(self, "_bound", []):
            try:
                self.root.unbind(p)
            except Exception:
                pass
        self._bound = []
        hotkeys = self._prefs.get("hotkeys", {}) or {}
        for sc in SHORTCUTS:
            pattern = hotkeys.get(sc["id"], sc["default"])
            if not pattern:                     # 用户禁用该键
                continue
            handler = getattr(self, sc["handler"])
            self.root.bind(pattern, handler)
            self._bound.append((pattern, handler))
        # Ctrl+↑/↓ 在聚焦的名单/群列表内上下移动选择（输入框内不抢键）
        for lb, pick in ((self.roster_list, self._on_pick_roster),
                         (self.group_list, self._on_pick_group)):
            lb.bind("<Control-Up>", lambda e, l=lb, p=pick: self._list_move(l, p, -1))
            lb.bind("<Control-Down>", lambda e, l=lb, p=pick: self._list_move(l, p, 1))
        # R31B/R65：Esc 逐层收起（全局搜索→聊天内搜索→消息多选→编辑/引用→归档区）
        self.root.bind("<Escape>", self._esc_layer)

    def _mark_current_read(self, _e=None) -> str:
        """Ctrl+R：标记当前会话已读（配合 C2/C5 未读徽标；R30A 同时记读位）。"""
        ch, to = self.view
        self._clear_unread(ch, to)
        self._mark_read_key(ch, to)           # R30A：下次进入不再画未读分隔线
        self._refresh_lists()
        return "break"

    def _focus_search(self, _e=None) -> str:
        """Ctrl+F：开关聊天内搜索条（C1；全局名单/群过滤走左侧小框点击）。"""
        excel = getattr(self, "_excel_chrome", None)
        if getattr(self, "_skin_name", "") == "excel" and excel is not None and not excel._native:
            return excel.find_cell()
        if self.chat_search.winfo_ismapped():
            self._close_chat_search()
            return "break"
        self.chat_search.grid()              # 显示（grid_remove 后回到原行）
        self.chat_search_entry.focus_set()
        self.chat_search_entry.selection_range(0, "end")
        if self.chat_search_entry.get().strip():
            self._do_chat_search()
        return "break"

    def _do_chat_search(self) -> int:
        """执行当前词全文检索并刷新计数（键盘/事件后调用）。"""
        n = self.msg_list.search_all(self.chat_search_entry.get())
        self._update_search_count()
        if n == 0:
            self.chat_search_count.config(fg="#c0392b")
        else:
            self.chat_search_count.config(fg=self._dp["sub"])
        return n

    def _chat_search_goto(self, delta: int = 1):
        self.msg_list.search_next(delta)
        self._update_search_count()
        return "break"

    def _close_chat_search(self):
        self.msg_list.search_clear()
        self.chat_search.grid_remove()
        try:
            self.entry.focus_set()
        except tk.TclError:
            pass

    def _update_search_count(self) -> None:
        n = self.msg_list.search_count()
        act = self.msg_list.search_active_index()
        idx = (act + 1) if act >= 0 else 0
        self.chat_search_count.config(text=f"{idx}/{n if n else 0}")

    def _refresh_search_hits(self) -> None:
        """装载/新消息后保持搜索高亮新鲜（仅在搜索活跃时重跑）。"""
        if self.chat_search_entry.get().strip():
            self.msg_list.search_all(self.chat_search_entry.get())
            self._update_search_count()

    # ---------- R9 全局消息搜索（跨会话 + 磁盘全量） ----------
    def _focus_global_search(self, _e=None) -> str:
        """打开/聚焦全局搜索结果窗（Ctrl+Shift+F；保持 Ctrl+F 会话内搜索不变）。"""
        from widgets.global_search import GlobalSearchBox
        gs = getattr(self, "_global_search_box", None)
        if gs is not None and gs.winfo_exists():
            try:
                gs.deiconify()
                gs.lift()
                gs.entry.focus_set()
                gs.entry.selection_range(0, "end")
            except tk.TclError:
                pass
            return "break"
        box = GlobalSearchBox(
            self.root, self.core._history._dir if hasattr(self.core, "_history") else "",
            roster=getattr(self.core, "roster", {}),
            groups=getattr(self.core, "groups", {}),
            me_uid=getattr(self.core, "uid", None),
            skin=getattr(self, "_skin_name", "office"),
            on_pick=self._gs_pick, font=getattr(self, "_font", None))
        ui_fx.fade_in(box)                        # R43A1 弹窗淡入
        self._global_search_box = box
        return "break"

    def _gs_pick(self, ch, to, seq, query: str) -> None:
        """点全局搜索某条命中：切到该会话并滚动定位、高亮到这条消息。"""
        try:
            if ch == "public":
                self._switch_view("public", None)
            elif ch == "private" and isinstance(to, (tuple, list)) and to:
                me = self.core.uid
                other = to[1] if to[0] == me else to[0]
                self._switch_view("private", other)
            else:
                self._switch_view("group", to)
            self.msg_list.locate_seq(seq, (query or "").strip())
        except (tk.TclError, Exception):
            pass

    def _jump_unread(self, _e=None) -> str:
        """跳到最早未读会话（按会话自然顺序）"""
        for ch, to in self._session_order():
            if self._unread.get((ch, to), 0) > 0:
                if (ch, to) != self.view:
                    self._switch_view(ch, to)
                return "break"
        # R61 细节：无未读是临时提示，不该作为系统行写进当前聊天区
        self.show_toast("没有未读会话", warn=True)
        return "break"

    def _jump_unread_dir(self, step: int) -> str:
        """Alt+↑/↓：沿会话自然顺序跳到上/下一条未读会话（跳过当前会话）。"""
        order = self._session_order()
        n = len(order)
        if n == 0:
            return "break"
        try:
            i = order.index(self.view)
        except ValueError:
            i = -1 if step > 0 else 0
        for k in range(1, n + 1):
            ch, to = order[(i + step * k) % n]
            if self._unread.get((ch, to), 0) > 0:
                self._switch_view(ch, to)
                return "break"
        self.show_toast("没有未读会话", warn=True)
        return "break"

    def _jump_unread_prev(self, _e=None) -> str:
        return self._jump_unread_dir(-1)

    def _jump_unread_next(self, _e=None) -> str:
        return self._jump_unread_dir(1)

    def _mute_current(self, _e=None) -> str:
        """Ctrl+Shift+M：静音/取消静音当前会话（只停闪烁与提示音，未读计数照记）。"""
        ch, to = self.view
        key = self._pin_key(ch, to)
        self._toggle_mute_conv(key)
        muted = self._prefs.is_muted(key)
        self.show_toast("已静音本会话（不再闪烁/提示音）" if muted else "已取消静音")
        self._refresh_lists()
        return "break"

    def _cancel_pending_input(self) -> None:
        """Esc 第 4 层：取消编辑态（清空编辑内容）或引用态（移除输入框引用行）。"""
        if self._pending_edit_seq is not None:
            self._pending_edit_seq = None
            self._drop_reply_state()
            self.entry.delete("1.0", "end")
            self._append_sys("已取消编辑")
        else:
            self._pending_reply = None
            if self.entry.get("1.0", "1.end").startswith("↩ "):
                self.entry.delete("1.0", "2.0")
            self._append_sys("已取消引用")
        try:
            self.entry.focus_set()
        except tk.TclError:
            pass

    def _esc_layer(self, _e=None) -> str | None:
        """Esc 逐层收起（R65）：全局搜索窗 → 聊天内搜索条 → 消息多选 → 编辑/引用态
        → 归档折叠区。任何一层都没命中时不拦截（输入框内 Esc 保持自身语义）。"""
        gs = getattr(self, "_global_search_box", None)
        if gs is not None and gs.winfo_exists():
            gs.destroy()
            self._global_search_box = None
            return "break"
        if self.chat_search.winfo_ismapped():
            self._close_chat_search()
            return "break"
        if self.msg_list.in_select_mode():
            self.msg_list.exit_select_mode()
            return "break"
        if self._pending_edit_seq is not None or self._pending_reply is not None:
            self._cancel_pending_input()
            return "break"
        if getattr(self, "_archived_show", False):
            self._toggle_archived_panel()
            return "break"
        return None

    def _list_move(self, lb, pick, step) -> str:
        """名单/群列表：Ctrl+↑/↓ 移动选择并打开对应会话"""
        n = lb.size()
        if n == 0:
            return "break"
        sel = lb.curselection()
        i = sel[0] if sel else (-step if step > 0 else 0)
        i = (i + step) % n
        lb.selection_clear(0, "end")
        lb.selection_set(i)
        lb.see(i)
        pick()
        return "break"

    def _session_order(self) -> list:
        """会话顺序：公共 → 在线名单（按 uid）→ 群列表（按 gid）"""
        order = [("public", None)]
        order += [("private", u["uid"])
                  for u in sorted(self.core.roster.values(), key=lambda x: x["uid"])
                  if u["uid"] != self.core.uid]
        order += [("group", g["gid"])
                  for g in sorted(self.core.groups.values(), key=lambda x: x["gid"])]
        return order

    def _cycle_chat(self, step) -> str:
        order = self._session_order()
        if len(order) < 2:
            return "break"
        cur = self.view
        try:
            i = order.index(cur)
        except ValueError:
            i = 0
        ch, to = order[(i + step) % len(order)]
        self._switch_view(ch, to)
        return "break"

    def _next_chat(self, _e=None):
        return self._cycle_chat(1)

    def _prev_chat(self, _e=None):
        return self._cycle_chat(-1)

    def _switch_view(self, ch: str, to) -> None:
        """统一切会话：设置 view、装载历史、联动名单/群高亮"""
        self._select_navigation('chat')
        self._mark_read_current()              # R30A：切走前记录本会话读到哪
        self._save_draft()                     # R12：切走前保存当前会话草稿
        self._reset_hist()                     # R12：跨会话不串历史浏览态
        self._thread_counts = {}               # R34：重置话题回复徽标，避免上个会话残留
        self.view = (ch, to)
        self._load_view_history()
        self._restore_draft()                  # R12：进入后恢复目标会话草稿
        self._refresh_evbody()                 # @全体：仅群聊显示「📣@所有」
        # R13：装入该会话回执并渲染；有置顶则显示横幅；上报已读
        key = self._pin_key(ch, to)
        self.msg_list.set_reads(self.core.reads.get(key, {}))
        # C9②：群会话给成员总数，供 @ 消息「✓✓ N/M 已读」；非群置 0。
        ginfo = self.core.groups.get(to) if ch == "group" else None
        self.msg_list.set_group_total(ginfo.get("member_count", 0) if ginfo else 0)
        self._refresh_pin_bar()
        self._refresh_announce_bar()
        self._send_read_now()
        if ch == "public":
            self.roster_list.selection_clear(0, "end")
            self.group_list.selection_clear(0, "end")
        elif ch in ("private", "e2ee"):
            self._select_eid(self.roster_list, self._roster_order, to)
        else:
            self._select_eid(self.group_list, self._group_order, to)
        self._apply_channel_ro()            # R26B：频道只读态随会话切换

    @staticmethod
    def _select_eid(lb, order: list, eid) -> None:
        """按实体 id 在 listbox 中定位并高亮（order[idx]->eid）"""
        for i, e in enumerate(order):
            if e == eid:
                lb.selection_clear(0, "end")
                lb.selection_set(i)
                lb.see(i)
                break

    def _go_public_shortcut(self, _e=None) -> str:
        self._switch_view("public", None)
        return "break"

    def _focus_contacts(self, _e=None) -> str:
        self.roster_list.focus_set()
        return "break"

    def _edit_last_own(self, _e=None) -> str:
        """Ctrl+E：取消进行中的编辑；否则把当前会话自己最后一条消息带回输入框。"""
        if self._pending_edit_seq is not None:
            self._pending_edit_seq = None
            self._drop_reply_state()             # 取消编辑 → 同步清引用
            self.entry.delete("1.0", "end")
            self.entry.focus_set()
            self._append_sys("已取消编辑")
            return "break"
        uid = self.core.uid
        for row in reversed(self.msg_list._rows):
            raw = row.raw
            # 仅纯文本消息可编辑（文件/贴纸/转发/投票/已撤回跳过）
            if raw.get("uid") == uid and raw.get("text") \
                    and not raw.get("deleted") and not raw.get("file") \
                    and not raw.get("sticker") and not raw.get("fp") \
                    and not isinstance(raw.get("poll"), dict):
                self._begin_edit(raw)
                return "break"
        self._append_sys("没有可编辑的自己消息")
        return "break"

    # ---------- 消息右键菜单（B2）+ 双击回复（B4）+ C3/C4 ----------
    def _build_msg_menu(self, idx: int) -> tk.Menu | None:
        """按消息类型裁剪菜单：自己=复制/编辑/撤回/引用回复；他人=复制/引用回复；系统=None"""
        raw = self.msg_list.get_row(idx)
        if not raw or raw.get("uid") is None:      # 系统行无菜单
            return None
        body = self.msg_list.body_text(idx)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="复制", command=lambda: self._copy_text(body))
        menu.add_command(label="选择文本", command=lambda: self._select_text(idx))
        # R31B：进入多选模式（首条 = 右键的消息）
        menu.add_command(label="多选",
                         command=lambda: self.msg_list.enter_select_mode(idx))
        if raw.get("seq") is not None and not raw.get("deleted"):
            is_own = raw.get("uid") == self.core.uid
            # 编辑仅限自己的纯文本消息（文件/贴纸/转发/投票/已撤回不可编辑）
            if is_own and raw.get("text") and not raw.get("file") \
                    and not raw.get("sticker") and not raw.get("fp") \
                    and not isinstance(raw.get("poll"), dict):
                menu.add_command(label="编辑", command=lambda: self._edit_msg(idx))
            # R70B：有历史版本 → 可查看编辑历史
            if raw.get("edits"):
                menu.add_command(label="查看编辑历史",
                                 command=lambda r=raw:
                                 self._show_edit_history(r))
            # R51：私聊双方可撤回对方消息（scope=both）；本人任何频道可撤
            # R53：管理员可撤回任何频道/任何人的消息（scope=self 即可，服务器放行）
            if is_own or self.view[0] == "private" or self.core.is_admin:
                scope = "self" if is_own else "both"
                menu.add_command(label="撤回",
                                 command=lambda: self._del_msg(idx, scope))
        menu.add_command(label="引用回复", command=lambda: self._quote(idx))
        # R68 ⏰ 提醒我：预设时间子菜单（纯客户端，到点 toast + 提示音 + 闪烁）
        if raw.get("seq") is not None and not raw.get("deleted"):
            rem = tk.Menu(menu, tearoff=0)
            for lab, mins in (("1 分钟后", 1), ("5 分钟后", 5), ("30 分钟后", 30),
                              ("1 小时后", 60), ("明天此时", 24 * 60)):
                rem.add_command(label=lab,
                                command=lambda m=mins, i=idx: self._add_reminder(i, m))
            if self._reminders():
                rem.add_separator()
                rem.add_command(label="清空全部提醒",
                                command=lambda: self._save_reminders([]))
            menu.add_cascade(label="⏰ 提醒我", menu=rem)
        # R67 拍一拍：私聊拍对端、群聊拍被右键消息的作者（含自己，对齐微信）
        if self.view[0] in ("private", "group") and raw.get("uid") is not None:
            menu.add_command(label="👋 拍一拍", command=lambda: self._send_nudge(raw))
        # R68 窗口抖动：私聊抖对端、群聊抖群全体（复用拍一拍链路）
        if self.view[0] in ("private", "group"):
            menu.add_command(label="📳 窗口抖动", command=self._send_shake)
        # R69C10 用户资料卡：右键他人消息 → 查看其资料
        if raw.get("uid") is not None and raw.get("uid") != self.core.uid:
            menu.add_command(label="👤 查看资料",
                             command=lambda: self._open_user_card(raw.get("uid")))
        # R71 联系人名片：选一位成员，把其名片发到当前会话
        menu.add_command(label="👤 发送名片…", command=self._send_card_dialog)
        # R71 消息永久链接：复制指向网页端的深链（定位并高亮该条）
        if raw.get("seq") is not None and not raw.get("deleted"):
            menu.add_command(label="🔗 复制消息链接",
                             command=lambda s=raw.get("seq"): self._copy_msg_link(s))
        # R38B：语音转文字（缺 vosk 或模型时隐藏；已转写可查看/重转）
        if raw.get("voice") and raw.get("voice_path") and optional.has_stt():
            note_path = str(raw["voice_path"]) + ".txt"
            if os.path.isfile(note_path):
                menu.add_command(label="📝 查看转写",
                                 command=lambda: self._view_voice_note(note_path))
                menu.add_command(label="📝 重新转写",
                                 command=lambda: self._voice_stt(idx))
            else:
                menu.add_command(label="📝 转文字",
                                 command=lambda: self._voice_stt(idx))
        # R38B：消息翻译（prefs 默认关 + 需装 deep-translator；开启时有隐私确认）
        if (body and self._prefs.get("translate_on")
                and optional.has_translator()):
            menu.add_command(label="🌐 翻译",
                             command=lambda: self._translate_msg(body))
        # R13：表情回应 / 转发 / 置顶（转发对无 seq 的本地图片行同样开放）
        has_seq = raw.get("seq") is not None
        if not raw.get("deleted") and (has_seq or raw.get("image_path")):
            menu.add_separator()
            if has_seq:
                menu.add_command(label="表情回应…", command=lambda: self._reaction_picker(idx))
            menu.add_command(label="转发…",
                             command=lambda: self._forward(idx))
            if has_seq:
                key = self._pin_key(*self.view)
                pin_snap = self.core.pins.get(key)
                is_pinned = bool(pin_snap and pin_snap.get("seq") == raw.get("seq"))
                menu.add_command(label="取消置顶" if is_pinned else "置顶",
                                 command=lambda: self._toggle_pin_msg(idx))
                # R14：收藏 / 阅后即焚
                if body:
                    star_key = key
                    is_starred = star_key in self._stars and raw.get("seq") in self._stars.get(star_key, {})
                    menu.add_command(label="取消收藏" if is_starred else "收藏",
                                     command=lambda: self._toggle_star(idx))
                    menu.add_command(label="🔥 阅后即焚发送",
                                     command=lambda: self._resend_burn(idx))
        return menu

    # ---------- R71 联系人名片 / 消息永久链接 / @别名 ----------
    def _send_card_dialog(self) -> None:
        """选一位通讯录成员，把其名片发到当前会话（public/private/group）。

        名片的 nick 用对方真实昵称（接收端各按自己的备注显示，不复用本机备注）。
        """
        ch, to = self.view
        if ch not in ("public", "private", "group"):
            self.show_toast("当前会话不支持发送名片", warn=True)
            return
        people, seen = [], set()
        for src in (self.core.roster, self.core.known):
            for uid, u in src.items():
                if uid == self.core.uid or uid in seen:
                    continue
                nick = str(u.get("nick") or "").strip()
                if not nick:
                    continue
                seen.add(uid)
                people.append((uid, nick))
        if not people:
            self.show_toast("通讯录里还没有可发送的联系人", warn=True)
            return
        people.sort(key=lambda t: t[1])
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("发送名片")
        dlg.transient(self.root)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "发送名片")
        dlg.geometry("+%d+%d" % (self.root.winfo_rootx() + 60,
                                 self.root.winfo_rooty() + 60))
        f = (FONT_FAMILY, 10)
        tk.Label(dlg, text="选择要发送的联系人", font=f, anchor="w"
                 ).pack(fill="x", padx=8, pady=(8, 2))
        lb = tk.Listbox(dlg, font=f, width=30, height=10)
        lb.pack(fill="both", expand=True, padx=8, pady=4)
        for uid, nick in people:
            label = self.core.display_name(uid)
            if label != nick:                     # 有备注 → 附注真实昵称
                label = f"{label}（{nick}）"
            lb.insert("end", label)

        def _do(_e=None):
            sel = lb.curselection()
            if not sel or not (0 <= sel[0] < len(people)):
                return
            uid, nick = people[sel[0]]
            self.core.send_chat("", channel=ch, to=to,
                                card={"uid": uid, "nick": nick})
            dlg.destroy()

        lb.bind("<Double-Button-1>", _do)
        lb.bind("<Return>", _do)
        tk.Button(dlg, text="发送", font=f, command=_do).pack(side="left", padx=8, pady=6)
        tk.Button(dlg, text="取消", font=f, command=dlg.destroy).pack(side="right",
                                                                      padx=8, pady=6)

    def _msg_link_key(self) -> str:
        """当前会话的网页端会话键（与 web 端 convKey 对齐；私聊按 uid 小:大 排序）。"""
        ch, to = self.view
        if ch == "public":
            return "public"
        if ch == "group":
            return f"group:{to}" if to is not None else ""
        if ch in ("private", "e2ee"):
            try:
                other = int(to)
            except (TypeError, ValueError):
                return ""
            me = int(self.core.uid)
            lo, hi = (me, other) if me <= other else (other, me)
            return f"private:{lo}:{hi}"
        return ""

    def _copy_msg_link(self, seq) -> None:
        """R71：复制该消息的网页端永久链接（#<会话键>/<seq>，打开即定位并高亮）。"""
        key = self._msg_link_key()
        if not key or seq is None:
            self.show_toast("当前会话不支持消息链接", warn=True)
            return
        host = str(self.core.host or "").strip() or "localhost"
        self._copy_text(f"https://{host}:{WEB_PORT}/#{key}/{int(seq)}")
        self.show_toast("🔗 已复制消息链接")

    def _handles_settings(self) -> None:
        """R71 别名设置：维护 prefs['handles'] = {别名: uid}，供 @别名 点击直达该人。"""
        handles = dict(self._prefs.get("handles") or {})
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("别名设置")
        dlg.transient(self.root)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "别名设置")
        dlg.geometry("+%d+%d" % (self.root.winfo_rootx() + 60,
                                 self.root.winfo_rooty() + 60))
        f = (FONT_FAMILY, 10)
        tk.Label(dlg, text="消息里写 @别名 后点击即可直达该成员私聊；"
                           "未设别名的 @昵称 仍按群成员昵称匹配。",
                 font=f, anchor="w", justify="left", wraplength=320
                 ).pack(fill="x", padx=8, pady=(8, 2))
        row = tk.Frame(dlg, bg=self._dp["win"])
        row.pack(fill="x", padx=8)
        tk.Label(row, text="别名", font=f, bg=self._dp["win"]).pack(side="left")
        e_name = tk.Entry(row, font=f, width=10)
        e_name.pack(side="left", padx=4)
        tk.Label(row, text="成员（昵称或ID）", font=f,
                 bg=self._dp["win"]).pack(side="left")
        e_user = tk.Entry(row, font=f, width=14)
        e_user.pack(side="left", padx=4)
        lb = tk.Listbox(dlg, font=f, width=36, height=8)
        lb.pack(fill="both", expand=True, padx=8, pady=6)

        def _refresh():
            lb.delete(0, "end")
            for h in sorted(handles):
                lb.insert("end", f"@{h} → {self.core.display_name(handles[h])}"
                                  f"（{handles[h]}）")

        def _add(_e=None):
            name = e_name.get().strip().lstrip("@")
            who = e_user.get().strip()
            if not name or not who:
                self.show_toast("请填写别名和成员", warn=True)
                return
            uid = int(who) if who.isdigit() else None
            if uid is None:                       # 昵称原文 → 在线名单/已知用户里找
                for src in (self.core.roster, self.core.known):
                    for k, u in src.items():
                        if str(u.get("nick") or "") == who:
                            uid = k
                            break
                    if uid is not None:
                        break
            if uid is None:
                self.show_toast("找不到该成员（请填昵称原文或用户ID）", warn=True)
                return
            handles[name] = uid
            self._prefs.set("handles", handles)
            e_name.delete(0, "end")
            e_user.delete(0, "end")
            _refresh()

        def _del(_e=None):
            sel = lb.curselection()
            if not sel:
                return
            handles.pop(sorted(handles)[sel[0]], None)
            self._prefs.set("handles", handles)
            _refresh()

        e_name.bind("<Return>", lambda _e: e_user.focus_set())
        e_user.bind("<Return>", _add)
        btns = tk.Frame(dlg, bg=self._dp["win"])
        btns.pack(fill="x", padx=8, pady=(0, 8))
        tk.Button(btns, text="添加", font=f, command=_add).pack(side="left")
        tk.Button(btns, text="删除选中", font=f, command=_del).pack(side="left", padx=6)
        tk.Button(btns, text="关闭", font=f, command=dlg.destroy).pack(side="right")
        _refresh()

    # ---------- R14 收藏 / 星标（本地快照） ----------
    def _toggle_star(self, idx: int) -> None:
        """收藏/取消收藏当前消息（本地 prefs['stars']，跨会话聚合浏览）。"""
        raw = self.msg_list.get_row(idx)
        if not raw or raw.get("seq") is None or not self.msg_list.body_text(idx):
            return
        try:
            self._prefs.check_stars_write(message_favorites=True)
        except StarsPreservationError as exc:
            self._append_sys(str(exc))
            return
        updated = deepcopy(self._stars)
        key = self._pin_key(*self.view)
        stars = updated.setdefault(key, {})
        seq = raw["seq"]
        if seq in stars:
            stars.pop(seq, None)
        else:
            snap = {"nick": raw.get("nick"), "text": self.msg_list.body_text(idx),
                    "ts": raw.get("ts"), "channel": raw.get("channel")}
            if isinstance(raw.get("sticker"), dict):   # R61：贴纸消息可收藏快照
                snap["sticker"] = raw["sticker"]
            stars[seq] = snap
        # 限量 200：去重由 dict 键保证，超限删最旧（复用可单测的纯函数）
        trim_stars(stars, 200)
        if not stars:
            updated.pop(key, None)
        try:
            self._prefs.set("stars", updated)
        except StarsPreservationError as exc:
            self._append_sys(str(exc))
            return
        self._stars = updated
        self._append_sys("已收藏" if seq in self._stars.get(key, {}) else "已取消收藏")

    def _open_stars(self) -> None:
        """打开收藏面板：列出全部收藏，双击跳转到原会话。"""
        from widgets.stars_panel import StarsPanel
        panel = StarsPanel(self.root, self._stars, self._goto_convo)
        ui_fx.fade_in(panel)                      # R43A1 弹窗淡入

    def _goto_convo(self, key: str, seq=None) -> None:
        """把收藏面板的会话键解析为 (channel, to) 并切换；带 seq 时定位到该消息。"""
        if key == "public":
            ch, to = "public", None
        elif key.startswith("private:"):
            ch = "private"
            to = int(key.split(":")[2])
        elif key.startswith("e2ee:"):
            ch = "e2ee"
            _, a, b = key.split(":")
            a, b = int(a), int(b)
            to = b if self.core.uid == a else a       # R36：密聊会话
        elif key.startswith("group:"):
            ch = "group"
            to = int(key.split(":", 1)[1])
        else:
            return
        self._switch_view(ch, to)
        if seq is not None:               # R61：跳回原会话并定位收藏的消息序号
            try:
                if not self.msg_list.jump_to_seq(seq):
                    self.msg_list.locate_seq(seq)
            except Exception:
                pass

    def _resend_burn(self, idx: int) -> None:
        """🔥 阅后即焚发送：把当前消息以 burn 模式重发到当前会话。"""
        raw = self.msg_list.get_row(idx)
        text = self.msg_list.body_text(idx)
        if not text:
            return
        ch, to = self.view
        self.core.send_chat(text, channel=ch, to=to, burn=True)

    def _purge_view(self) -> None:
        """R14 会话清理：丢弃当前会话截至最新 seq 的旧消息（本地+服务器广播）。"""
        ch, to = self.view
        until = self.core.latest_seq(ch, to)
        if until:
            self.core.send_purge(ch, to, until)
            self._append_sys("已清理本会话旧消息")

    # ---------- R14/R51 定时/延时发送（服务器权威托管 + 列表管理） ----------
    def _schedule_dialog(self) -> None:
        """R51 定时发送管理：列出待发队列（时间+剩余+正文预览），可取消/新建。

        队列由服务器权威托管（SCHED_SET/CANCEL/LIST 帧），本窗只是服务器
        列表的展示与操作入口。
        """
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("定时发送")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "定时发送")
        f = self._f
        top = tk.Frame(dlg)
        top.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(top, text="待发送队列（服务器托管）",
                 font=(FONT_FAMILY, 11, "bold")).pack(side="left")
        tk.Button(top, text="＋ 新建定时…", font=f,
                  command=lambda: (dlg.destroy(), self._schedule_new_dialog())).pack(side="right")
        lb = tk.Listbox(dlg, width=56, height=10, font=f, exportselection=False)
        lb.pack(padx=10, pady=4)

        def _reload() -> None:
            lb.delete(0, "end")
            for r in sorted(self._scheduled, key=lambda x: x["fire_at"]):
                remain = max(0, int(r["fire_at"] - time.time()))
                hh = time.strftime("%H:%M", time.localtime(r["fire_at"]))
                lb.insert("end", f"[{hh}] 剩{remain // 60}分{remain % 60:02d}秒  "
                                 f"{str(r.get('text', ''))[:22]}")

        def _cancel() -> None:
            sel = lb.curselection()
            if not sel:
                return
            r = sorted(self._scheduled, key=lambda x: x["fire_at"])[sel[0]]
            self.core.sched_cancel(r["rid"])      # R51：服务器删除，回帧 SCHED_LIST 同步
            self._scheduled.remove(r)             # 乐观移除（服务器权威回帧兜底）
            _reload()

        _reload()
        self._sched_dlg = dlg
        self._sched_reload = _reload
        dlg.protocol("WM_DELETE_WINDOW", self._sched_dlg_close)
        bt = tk.Frame(dlg)
        bt.pack(padx=10, pady=(2, 10))
        tk.Button(bt, text="取消选中", font=f, command=_cancel).pack(side="left", padx=6)
        tk.Button(bt, text="关闭", font=f, command=self._sched_dlg_close).pack(side="left", padx=6)

    def _sched_dlg_close(self) -> None:
        if self._sched_dlg is not None:
            try:
                self._sched_dlg.destroy()
            except Exception:
                pass
        self._sched_dlg = None
        self._sched_reload = None

    def _schedule_new_dialog(self) -> None:
        """定时发送：选几分钟后，把当前输入内容在目标会话定时发出（服务器托管）。"""
        text = self._entry_text().strip()
        if not text:
            self._append_sys("先把要定时发送的内容打好")
            return
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("定时发送")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "定时发送")
        tk.Label(dlg, text="几分钟后发送？").pack(padx=14, pady=(10, 2))
        var = tk.IntVar(value=1)
        sp = tk.Spinbox(dlg, from_=1, to=120, textvariable=var, width=6)
        sp.pack(padx=14, pady=2)
        def _ok():
            mins = max(1, var.get())
            ch, to = self.view
            self._schedule_send(text, ch, to, mins)
            dlg.destroy()
        tk.Button(dlg, text="确定", command=_ok).pack(pady=(8, 10))
        sp.focus_set()

    def _schedule_send(self, text: str, ch: str, to, minutes: int) -> None:
        """R51 定时发送：把消息交给服务器队列（fire_at 到点由服务器发出）。

        客户端离线也会到点投递；服务器回 SCHED_LIST 帧刷新本地展示队列。
        """
        when = time.time() + minutes * 60
        if not self.core.sched_set(text, channel=ch, to=to, fire_at=when):
            self._append_sys("定时失败：未连接服务器")
            return
        hh = time.strftime("%H:%M", time.localtime(when))
        self._append_sys(f"已定时 {hh} 发送（⏰ 服务器托管，可管理/取消）")

    def _on_sched_sync(self, ev: dict) -> None:
        """R51：服务器 SCHED_LIST 回帧 → 覆盖本地展示队列（权威对齐）。"""
        now = time.time()
        self._scheduled = [r for r in ev.get("items", [])
                           if isinstance(r, dict) and r.get("fire_at", 0) > now]
        if self._sched_dlg is not None and self._sched_reload is not None:
            try:
                if self._sched_dlg.winfo_exists():
                    self._sched_reload()
            except Exception:
                pass

    def _pump_scheduled(self) -> None:
        """R51：到点消息由服务器发出（离线也在）；本地只做展示剪枝。"""
        now = time.time()
        before = len(self._scheduled)
        self._scheduled = [r for r in self._scheduled if now < r.get("fire_at", 0)]
        if len(self._scheduled) != before and self._sched_reload is not None:
            try:
                if self._sched_dlg is not None and self._sched_dlg.winfo_exists():
                    self._sched_reload()
            except Exception:
                pass

    # ---------- R14 快捷短语 ----------
    def _quick_menu(self) -> None:
        """快捷短语：点击即插入输入框；"管理…"进入编辑列表。"""
        menu = tk.Menu(self.root, tearoff=0)
        for phrase in self._quick:
            menu.add_command(label=phrase, command=lambda p=phrase: self._insert_quick(p))
        menu.add_separator()
        menu.add_command(label="管理快速短语…", command=self._quick_dialog)
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def _insert_quick(self, phrase: str) -> None:
        self.entry.insert("end", phrase)

    def _quick_dialog(self) -> None:
        """快捷短语管理：新增 / 双击删除，写回 prefs['quick']。"""
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("快速短语")
        dlg.transient(self.root)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "快速短语")
        lb = tk.Listbox(dlg, height=8, width=36)
        lb.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        sb = tk.Scrollbar(dlg, command=lb.yview)
        sb.pack(side="left", fill="y")
        lb.config(yscrollcommand=sb.set)
        for p in self._quick:
            lb.insert("end", p)
        entry = tk.Entry(dlg, width=36)
        entry.pack(fill="x", padx=6, pady=(0, 2))
        def _add():
            p = entry.get().strip()
            if p and p not in self._quick:
                self._quick.append(p)
                self._prefs.set("quick", self._quick)
                lb.insert("end", p)
            entry.delete(0, "end")
        def _del_sel():
            sel = lb.curselection()
            if sel:
                i = sel[0]
                lb.delete(i)
                self._quick.pop(i)
                self._prefs.set("quick", self._quick)
        tk.Button(dlg, text="添加", command=_add).pack(side="left", padx=6)
        tk.Button(dlg, text="删除选中", command=_del_sel).pack(side="left")
        entry.bind("<Return>", lambda e: _add())
        entry.focus_set()

    # ---------- R14 阅后即焚模式 ----------
    def _toggle_burn_mode(self) -> None:
        """🔥 开关：后续发送的消息都用阅后即焚（全体读完自动删除）。"""
        self._burn_mode = not self._burn_mode
        self._prefs.set("burn_mode", self._burn_mode)
        self._update_burn_badge()
        self._append_sys("阅后即焚已开启" if self._burn_mode else "阅后即焚已关闭")

    # ---------- R37 加密云历史 ----------
    def _cloud_upload_dialog(self) -> None:
        """☁ 全量本地历史加密上传（口令两次确认；口令不落盘不上传）。"""
        from widgets import dialogbox
        pw = dialogbox.ask_string("云备份", "设置备份口令（忘记口令将无法恢复备份）：",
                                  parent=self.root, show="*")
        if not pw:
            return
        pw2 = dialogbox.ask_string("云备份", "再输入一次口令确认：",
                                   parent=self.root, show="*")
        if pw2 != pw:
            self._append_sys("⚠ 两次口令不一致，已取消备份")
            return
        self._append_sys("☁ 正在加密并上传本地历史…")

        def _work():
            ok, msg = self.core.cloud_upload(pw)
            self.root.after(0, lambda: self._append_sys(("☁ " if ok else "⚠ ") + msg))

        threading.Thread(target=_work, daemon=True, name="cloud-put").start()

    def _cloud_restore_dialog(self) -> None:
        """☁ 从云端拉回备份，口令解密后与本地历史合并（去重只补缺）。"""
        from widgets import dialogbox
        pw = dialogbox.ask_string("云恢复", "输入备份口令：", parent=self.root, show="*")
        if not pw:
            return
        self._append_sys("☁ 正在从云端拉取备份…")

        def _work():
            ok, msg = self.core.cloud_restore(pw)
            self.root.after(0, lambda: self._append_sys(("☁ " if ok else "⚠ ") + msg))

        threading.Thread(target=_work, daemon=True, name="cloud-get").start()

    def _update_burn_badge(self) -> None:
        """R31：阅后即焚徽标——激活时显示在发送左侧，点徽标即取消。"""
        if self._burn_mode:
            self._burn_btn.pack(side="left")
        else:
            self._burn_btn.pack_forget()

    # ---------- R26C 静默发送 ----------
    def _toggle_silent_mode(self) -> None:
        """🔕 开关：后续发送的消息免通知（接收端不弹提醒，未读照常累计）。"""
        self._silent_mode = not self._silent_mode
        self._prefs.set("silent_mode", self._silent_mode)
        self._update_silent_badge()
        self._append_sys("静默发送已开启" if self._silent_mode else "静默发送已关闭")

    def _update_silent_badge(self) -> None:
        """R31：静默发送徽标——激活时显示在发送左侧，点徽标即取消。"""
        if self._silent_mode:
            self._silent_btn.pack(side="left")
        else:
            self._silent_btn.pack_forget()

    # ---------- R70E 消息伪装 ----------
    _DISGUISE_LABELS = {"": "关闭", "code": "代码", "log": "日志", "excel": "表格"}

    def _cycle_disguise(self) -> None:
        """🎭 循环切换伪装风格（关 → code → log → excel → 关），仅改外观不改数据。"""
        ring = ("",) + tuple(CFG.disguise_styles)
        try:
            nxt = ring[(ring.index(self._disguise_mode) + 1) % len(ring)]
        except ValueError:
            nxt = ""
        self._disguise_mode = nxt
        self._prefs.set("disguise_mode", nxt)
        self._update_disguise_badge()
        self._append_sys("消息伪装：已关闭" if not nxt
                         else f"消息伪装：{self._DISGUISE_LABELS.get(nxt, nxt)} 外观"
                              "（正文遮盖，点击可揭示）")

    def _update_disguise_badge(self) -> None:
        """伪装徽标——非关闭态显示在发送左侧。"""
        if self._disguise_mode:
            self._disguise_btn.pack(side="left")
        else:
            self._disguise_btn.pack_forget()

    # ---------- R70F 敏感词自动打码（纯本地显示层） ----------
    def _guard_enabled_now(self) -> bool:
        """打码此刻是否生效：开关开 + 时段命中（时段留空=全天）。

        时段格式 ``9-18`` 或 ``9:30-12,14-18``（逗号分隔多段，支持跨天如 22-6）。
        """
        if not self._guard_on:
            return False
        spec = (self._guard_hours or "").strip()
        if not spec:
            return True
        cur = time.localtime()
        now = cur.tm_hour * 60 + cur.tm_min
        for part in spec.replace("，", ",").split(","):
            part = part.strip()
            if "-" not in part:
                continue
            a, _, b = part.partition("-")
            try:
                h1, m1 = [int(x) for x in (a.strip().split(":") + ["0"])[:2]]
                h2, m2 = [int(x) for x in (b.strip().split(":") + ["0"])[:2]]
            except ValueError:
                continue
            lo, hi = h1 * 60 + m1, h2 * 60 + m2
            if lo <= hi:
                if lo <= now < hi:
                    return True
            elif now >= lo or now < hi:          # 跨天段
                return True
        return False

    def _refresh_guard(self) -> None:
        """把当前词表/开关/时段落到 prefs 并即时重渲染消息区。"""
        self._prefs.set("guard_on", bool(self._guard_on))
        self._prefs.set("guard_words", list(self._guard_words))
        self._prefs.set("guard_hours", self._guard_hours)
        self.msg_list.set_guard(self._guard_words, self._guard_enabled_now())

    def _edit_guard_words(self) -> None:
        """敏感词表编辑框：每行一个词（或逗号分隔），保存后立即生效。"""
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)
        dlg.title("敏感词表")
        dlg.transient(self.root)
        dlg.attributes("-topmost", True)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "敏感词表")
        f = self._f
        tk.Label(dlg, text="每行一个敏感词（也可逗号分隔）。仅本机打码显示，"
                           "不影响消息存储、搜索与复制。",
                 font=f, fg=self._dp["sub"], wraplength=320, justify="left").pack(
            fill="x", padx=10, pady=6)
        txt = tk.Text(dlg, font=f, width=34, height=10, bg=self._dp.get("inp", "#ffffff"),
                      fg=self._dp["fg"], relief="flat", highlightthickness=1,
                      highlightbackground=self._dp["border"], wrap="word")
        txt.pack(fill="both", expand=True, padx=10)
        txt.insert("1.0", "\n".join(self._guard_words))

        def _save() -> None:
            raw = txt.get("1.0", "end").replace("，", ",")
            words, seen = [], set()
            for chunk in raw.replace(",", "\n").splitlines():
                w = chunk.strip()
                if w and w not in seen:
                    seen.add(w)
                    words.append(w[:32])          # 单词限长，防超长正则
            self._guard_words = words
            self._refresh_guard()
            dlg.destroy()
            self._append_sys(f"敏感词表已保存（{len(words)} 个词）")

        bar = tk.Frame(dlg, bg=self._dp["win"])
        bar.pack(fill="x", padx=10, pady=8)
        tk.Button(bar, text="保存", font=f, relief="flat", bd=0, cursor="hand2",
                  bg=self._dp.get("acc", "#3b7ddd"), fg="#ffffff",
                  command=_save).pack(side="right", padx=(4, 0))
        tk.Button(bar, text="取消", font=f, relief="flat", bd=0, cursor="hand2",
                  bg=self._dp.get("card", "#ffffff"), fg=self._dp["fg"],
                  command=dlg.destroy).pack(side="right")

    _GUARD_HOUR_LABELS = ["全天", "9-18", "9:30-12,14-18", "22-6"]
    _GUARD_HOUR_KEYS = {"全天": "", "9-18": "9-18",
                        "9:30-12,14-18": "9:30-12,14-18", "22-6": "22-6"}

    def _on_guard_hours_pick(self, label: str) -> None:
        self._guard_hours = self._GUARD_HOUR_KEYS.get(label, "")
        self._refresh_guard()

    # ---------- R31 更多菜单（TG 风格收纳） ----------
    def _build_more_menu(self) -> tk.Menu:
        """构建「＋」更多菜单（开关项带 ✓ 勾选态）；拆出便于冒烟验证。"""
        m = tk.Menu(self.root, tearoff=0, font=(FONT_FAMILY, 10))
        ch, to = self.view
        if ch == "private" and to != self.core.uid:
            on = self.core.e2ee_ready(to)
            m.add_command(label=("✓ " if on else "") + "🔒 密聊（查看指纹）",
                          command=self._toggle_e2ee)          # R36：1v1 密聊
            if on:                                            # R42：手动轮转
                m.add_command(label="🔄 轮转密钥", command=self._rotate_e2ee)
            m.add_command(label="📞 语音通话",
                          command=self._start_voice_call)     # R38：1v1 对讲
            m.add_command(                                    # R39A：全双工开关
                label=("✓ " if self.core.calls.is_duplex() else "")
                + "🎙 通话全双工",
                command=self._toggle_call_duplex)
        elif ch == "group" and to is not None:
            on = self.core.group_e2ee_on(to)
            m.add_command(label=("✓ " if on else "") + "🔒 群密聊",
                          command=self._toggle_group_e2ee)    # R36：群密聊
            m.add_command(label="🎙 进入语音房",              # R72：多人语音房
                          command=self._join_voice_room)
        m.add_command(label="📍 发送位置", command=self._send_geo)     # R72 位置共享
        m.add_command(label=("✓ " if self._geo_live_active else "")
                      + "📍 实时位置共享", command=self._send_geo_live)  # R72 实时位置
        m.add_command(label="⭕ 视频留言", command=self._start_vmemo)    # R72 圆形视频留言
        m.add_command(label="⏰ 定时发送", command=self._schedule_dialog)
        m.add_command(label="📋 快捷短语", command=self._quick_menu)
        m.add_command(label="📅 日期跳转", command=self._date_jump_dialog)
        m.add_command(label=("✓ " if self._prefs.get("voice_autoplay") else "")
                      + "🔁 语音连播", command=self._toggle_voice_autoplay)   # D14
        m.add_command(label="🔒 发起投票", command=self._poll_dialog)   # 低频投票收纳于此
        m.add_command(label="🖼 贴纸管理", command=self._sticker_manager)
        if optional.has_translator():           # R38B：翻译开关（缺依赖不显示）
            m.add_command(label=("✓ " if self._prefs.get("translate_on") else "")
                          + "🌐 消息翻译", command=self._toggle_translate)
        if optional.has_stt():                  # R38B：语音转写模型设置
            m.add_command(label="📝 语音转写设置…", command=self._stt_settings)
        m.add_command(label="＠ 别名设置…", command=self._handles_settings)   # R71
        m.add_separator()
        m.add_command(label="★ 收藏", command=self._open_stars)
        m.add_command(label="⏳ 稍后处理", command=self._open_snooze)   # R69C11 未读标记清单
        m.add_command(label="📤 导出对话", command=self._export_conversation)
        m.add_command(label="☁ 备份到云端…", command=self._cloud_upload_dialog)
        m.add_command(label="☁ 从云端恢复…", command=self._cloud_restore_dialog)
        m.add_command(label="🧹 清空视图", command=self._purge_view)
        # 阅后即焚 / 静默发送：工具行仅在激活时闪现 🔥/🔕 徽标，故此处保留为常驻开关入口。
        m.add_command(label=("✓ " if self._burn_mode else "") + "🔥 阅后即焚",
                      command=self._toggle_burn_mode)
        m.add_command(label=("✓ " if self._silent_mode else "") + "🔕 静默发送",
                      command=self._toggle_silent_mode)
        return m

    def _more_menu(self) -> None:
        """「＋」更多菜单：低频功能收纳，在按钮上方弹出。"""
        m = self._build_more_menu()
        x = self._more_btn.winfo_rootx()
        y = self._more_btn.winfo_rooty() - m.winfo_reqheight() - 2
        if y < 0:                                 # 顶部放不下 → 按钮下方弹
            y = self._more_btn.winfo_rooty() + self._more_btn.winfo_reqheight()
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    # ---------- R36 E2EE 密聊 UI ----------
    def _toggle_e2ee(self) -> None:
        """1v1 密聊开关：未建立 → 后台握手 + 指纹窗；已建立 → 查看指纹/切密聊会话。"""
        ch, to = self.view
        if ch != "private" or to == self.core.uid:
            return
        if self.core.e2ee_ready(to):
            self._show_fingerprint(to)
            self._switch_view("e2ee", to)         # 已有会话 → 直接切入密聊视图
            return
        self._append_sys("正在建立密聊（端到端加密）…")

        def _handshake():
            fp = self.core.start_e2ee(to)
            self.root.after(0, lambda: self._e2ee_handshake_done(to, fp))

        threading.Thread(target=_handshake, daemon=True, name="e2ee-hs").start()

    def _e2ee_handshake_done(self, to: int, fp: str | None) -> None:
        if fp is None:
            self._append_sys("密聊建立失败（对方不在线或超时）")
            return
        self._append_sys("密聊已建立，请核对指纹 🔒")
        self._show_fingerprint(to, fp)
        self._switch_view("e2ee", to)

    def _rotate_e2ee(self) -> None:
        """R42 菜单「🔄 轮转密钥」：手动触发 DH 轮转（新根混入临时 DH）。"""
        ch, to = self.view
        if ch not in ("e2ee", "private") or to is None:
            return
        if self.core.rotate_e2ee_key(int(to)):
            self._append_sys("🔄 正在轮转密聊密钥（后台 DH 交换）…")

    def _toggle_group_e2ee(self) -> None:
        """群密聊开关：开启（含自动握手+密钥分发，后台执行）→ 切群密聊态。"""
        ch, to = self.view
        if ch != "group" or to is None:
            return
        if self.core.group_e2ee_on(to):
            self._append_sys("群密聊已开启（成员变动会自动重新分发密钥）")
            return
        self._append_sys("正在开启群密聊（与成员建立会话并分发密钥）…")

        def _open():
            ok, err = self.core.open_group_e2ee(to)
            self.root.after(0, lambda: self._group_e2ee_done(to, ok, err))

        threading.Thread(target=_open, daemon=True, name="e2ee-gopen").start()

    def _group_e2ee_done(self, gid: int, ok: bool, err: str) -> None:
        if ok:
            self._append_sys("群密聊已开启 🔒（密聊消息仅成员可解密）")
        else:
            self._append_sys(f"群密聊开启失败：{err}")

    def _show_fingerprint(self, to: int, fp: str | None = None) -> None:
        """R36 指纹比对窗：emoji 序列人工核对防中间人。"""
        from widgets.fingerprint import FingerprintDialog
        u = self.core.roster.get(to) or self.core.known.get(to) or {}
        if fp is None:
            fp = self.core.e2ee_fingerprint(to)
        fp_dlg = FingerprintDialog(self.root, peer_nick=u.get("nick") or f"用户{to}",
                                   fingerprint=fp)
        ui_fx.fade_in(fp_dlg)                     # R43A1 弹窗淡入

    # ---------- R72 位置共享 UI ----------
    def _send_geo(self) -> None:
        """菜单「📍 发送位置」：粘贴坐标+填地点名 → 解析预览 → 确认发送。

        R72 优化：坐标与地点名同屏输入，减少一次弹窗；地点名在消息徽标中显示。"""
        import tkinter as tk
        from widgets import dialogbox

        dlg = tk.Toplevel(self.root)
        dlg.title("发送位置")
        dlg.configure(bg="#1e1e2e")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.update_idletasks()
        w, h = 380, 280
        x = self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        tk.Label(dlg, text="坐标 / 地图链接",
                 bg="#1e1e2e", fg="#888",
                 font=("Microsoft YaHei UI", 9)).pack(
            anchor="w", padx=24, pady=(20, 4))
        coord_entry = tk.Entry(dlg, bg="#2a2a3a", fg="#eee",
                               relief="flat", bd=0, insertbackground="#888",
                               font=("Microsoft YaHei UI", 11))
        coord_entry.pack(fill="x", padx=24, ipady=8)
        coord_entry.focus_set()

        tk.Label(dlg, text="地点名称（可选）",
                 bg="#1e1e2e", fg="#888",
                 font=("Microsoft YaHei UI", 9)).pack(
            anchor="w", padx=24, pady=(16, 4))
        name_entry = tk.Entry(dlg, bg="#2a2a3a", fg="#eee",
                              relief="flat", bd=0, insertbackground="#888",
                              font=("Microsoft YaHei UI", 11))
        name_entry.pack(fill="x", padx=24, ipady=8)

        preview_lbl = tk.Label(dlg, text="", bg="#1e1e2e", fg="#6ab",
                               font=("Microsoft YaHei UI", 9))
        preview_lbl.pack(anchor="w", padx=24, pady=(10, 0))

        err_lbl = tk.Label(dlg, text="", bg="#1e1e2e", fg="#ff6b6b",
                           font=("Microsoft YaHei UI", 9))
        err_lbl.pack(anchor="w", padx=24, pady=(4, 0))

        btn_frame = tk.Frame(dlg, bg="#1e1e2e")
        btn_frame.pack(side="bottom", pady=16, padx=24, fill="x")

        result = {"ok": False, "lat": 0.0, "lon": 0.0, "name": ""}

        def on_preview(*_):
            raw = coord_entry.get().strip()
            if not raw:
                preview_lbl.config(text="")
                err_lbl.config(text="")
                return
            hit = geo_api.parse(raw)
            if not hit:
                preview_lbl.config(text="")
                err_lbl.config(text="无法解析坐标，请检查格式")
                return
            lat, lon = hit["lat"], hit["lon"]
            err_lbl.config(text="")
            if hit.get("ambiguous"):
                preview_lbl.config(
                    text=f"📍 {lat:.6f}, {lon:.6f}（坐标有歧义，按纬度,经度）",
                    fg="#e6a23c")
            else:
                preview_lbl.config(
                    text=f"📍 {lat:.6f}, {lon:.6f}", fg="#6ab")

        coord_entry.bind("<KeyRelease>", on_preview)

        def do_cancel():
            dlg.destroy()

        def do_send():
            raw = coord_entry.get().strip()
            name = name_entry.get().strip()[:64]
            if not raw:
                err_lbl.config(text="请输入坐标或地图链接")
                return
            hit = geo_api.parse(raw)
            if not hit:
                err_lbl.config(text="无法解析坐标，请检查格式")
                return
            result["ok"] = True
            result["lat"] = hit["lat"]
            result["lon"] = hit["lon"]
            result["name"] = name
            dlg.destroy()

        tk.Button(btn_frame, text="取消", command=do_cancel,
                  bg="#3a3a4a", fg="#ccc", activebackground="#4a4a5a",
                  activeforeground="#fff", relief="flat", bd=0,
                  padx=18, pady=7, font=("Microsoft YaHei UI", 10)).pack(
            side="left")
        send_btn = tk.Button(btn_frame, text="发送", command=do_send,
                             bg="#4f8cff", fg="white",
                             activebackground="#6699ff",
                             activeforeground="white", relief="flat", bd=0,
                             padx=22, pady=7,
                             font=("Microsoft YaHei UI", 10, "bold"))
        send_btn.pack(side="right")

        dlg.bind("<Return>", lambda _e: do_send())
        dlg.bind("<Escape>", lambda _e: do_cancel())
        dlg.wait_window()

        if not result["ok"]:
            return
        ch, to = self.view
        geo = {"lat": result["lat"], "lon": result["lon"],
               "name": result["name"], "live": 0}
        self.core.send_chat(channel=ch, to=to, geo=geo)

    def _send_geo_live(self) -> None:
        """菜单「📍 实时共享」：开始定时发送位置（5 分钟自动停止）。"""
        if self._geo_live_active:
            self._stop_geo_live()
            return
        import dialogbox
        raw = dialogbox.ask_string("实时位置共享",
                                   "粘贴当前坐标或地图链接：\n（将每 30 秒刷新一次，持续 5 分钟）",
                                   parent=self.root)
        if not raw:
            return
        hit = geo_api.parse(raw)
        if not hit:
            self.show_toast("无法解析坐标", warn=True)
            return
        ch, to = self.view
        self._geo_live_active = True
        self._geo_live_self = True
        self._geo_live_session = f"live_{int(time.time())}"
        self._geo_live_count = 0
        self._geo_live_max = int(self.core.cfg.geo_live_ttl / self.core.cfg.geo_live_interval)
        if ch == "group":
            self._set_geo_marker(ch, to, self.core.uid, hit["lat"], hit["lon"])
            self._refresh_chan_label()
        self._geo_live_tick(ch, to, hit["lat"], hit["lon"])
        self._append_sys("📍 已开始实时位置共享（每 30 秒刷新，最长 5 分钟）")

    def _geo_live_tick(self, ch: str, to, lat: float, lon: float) -> None:
        """定时重发实时位置帧（GEO_LIVE 不入历史，同 typing 待遇）。"""
        if not self._geo_live_active:
            return
        self._geo_live_count += 1
        if self._geo_live_count > self._geo_live_max:
            self._stop_geo_live()
            return
        geo = {"lat": lat, "lon": lon, "name": "", "live": 1,
               "expire": time.time() + self.core.cfg.geo_live_ttl,
               "session": self._geo_live_session}
        self.core.send_geo_live(ch, to, geo)
        if ch == "group":
            self._set_geo_marker(ch, to, self.core.uid, lat, lon)
            self._refresh_chan_label()
        self.root.after(int(self.core.cfg.geo_live_interval * 1000),
                        lambda: self._geo_live_tick(ch, to, lat, lon))

    def _stop_geo_live(self) -> None:
        """停止实时位置共享。"""
        if not self._geo_live_active:
            return
        self._geo_live_active = False
        self._geo_live_self = False
        ch, to = self.view
        self.core.send_geo_stop(ch, to, self._geo_live_session)
        self._geo_live_session = ""
        self._drop_geo_marker(ch, to, self.core.uid)
        self._append_sys("📍 已停止实时位置共享")
        self._refresh_chan_label()

    # ---------- R72 优化：实时位置接收侧标记（标题「正在共享位置」） ----------
    def _set_geo_marker(self, ch: str, to, uid: int, lat: float,
                        lon: float, name: str = "") -> None:
        """写入某会话的共享标记（本端发送或收到对端 GEO_LIVE 共用）。"""
        m = self._geo_live_markers.setdefault((ch, to), {})
        m[uid] = {"lat": lat, "lon": lon, "name": name,
                  "expire": time.time() + self.core.cfg.geo_live_ttl}

    def _drop_geo_marker(self, ch: str, to, uid: int) -> None:
        """摘除某会话的共享标记；空会话整个移除。"""
        m = self._geo_live_markers.get((ch, to))
        if not m:
            return
        m.pop(uid, None)
        if not m:
            self._geo_live_markers.pop((ch, to), None)

    def _current_geo_markers(self) -> dict:
        """当前会话的共享标记（顺带清过期项）。"""
        now = time.time()
        stale = [k for k, v in self._geo_live_markers.items()
                 if any(exp <= now for exp in
                        (x["expire"] for x in v.values()))]
        for k in stale:
            m = self._geo_live_markers[k]
            m = {u: x for u, x in m.items() if x["expire"] > now}
            if m:
                self._geo_live_markers[k] = m
            else:
                self._geo_live_markers.pop(k, None)
        return self._geo_live_markers.get(tuple(self.view), {})

    def _on_geo_live_evt(self, ev: dict) -> None:
        """收到 GEO_LIVE/GEO_STOP：更新「本会话内正在共享位置」标记并刷新标题。

        GEO_LIVE 不入历史，接收方凭标记知道谁在共享、点标题即可打开地图。"""
        t = ev.get("t")
        uid = ev.get("uid")
        ch = ev.get("channel") or "group"
        to = ev.get("to")
        if ch != "group" or uid is None:
            return
        cur_ch, cur_to = self.view
        if not (cur_ch == "group" and cur_to == to):
            return                                  # 只关心当前会话
        geo = ev.get("geo") or {}
        try:
            expire = float(geo.get("expire") or 0)  # 服务器把 expire 放在 geo 子对象
        except (TypeError, ValueError):
            expire = 0.0
        if t == "geo_stop" or expire <= time.time():
            self._drop_geo_marker(ch, to, uid)
        else:
            self._set_geo_marker(ch, to, uid, float(geo.get("lat") or 0),
                                 float(geo.get("lon") or 0),
                                 str(geo.get("name") or "").strip())
        self._refresh_chan_label()

    def _marker_name(self, uid: int) -> str:
        """标记显示名：备注名/昵称优先，取不到回退 uid。"""
        try:
            return self.core.display_name(uid)
        except Exception:
            return f"#{uid}"

    def _on_chan_label_click(self, _ev=None) -> None:
        """点会话标题的「正在共享位置」→ 打开第一个（最近的）共享者地图。"""
        m = self._current_geo_markers()
        if not m:
            return
        uid = min(m, key=lambda u: m[u].get("expire", 0))
        pos = m[uid]
        import webbrowser
        webbrowser.open(geo_api.osm_url(pos["lat"], pos["lon"]))

    # ---------- R72 圆形视频留言 UI ----------
    def _start_vmemo(self) -> None:
        """菜单「⭕ 视频留言」：按住录制 → 松手预览 → 发送。"""
        if self._vmemo_rec is not None and self._vmemo_rec.is_active():
            self._vmemo_rec.finish()
            return
        import voice_api
        if not voice_api.available():
            self.show_toast("无可用音频设备，无法录制视频留言", warn=True)
            return
        import video_api
        if not video_api.available():
            self.show_toast("无可用摄像头，无法录制视频留言", warn=True)
            return
        self._vmemo_rec = vmemo_api.VmemoRecorder(
            on_done=self._on_vmemo_done, on_error=self._on_vmemo_error,
            fps=self.core.cfg.vmemo_max_fps,
            max_dur=self.core.cfg.vmemo_max_dur,
            max_bytes=self.core.cfg.vmemo_max_bytes)
        if not self._vmemo_rec.start():
            self.show_toast("摄像头/麦克风打开失败", warn=True)
            return
        self.show_toast("⭕ 正在录制视频留言…（最长 5 秒）")
        self.root.after(100, self._vmemo_poll)

    def _vmemo_poll(self) -> None:
        """轮询录制器：仍在录则继续，已结束则等 finish 回调。"""
        if self._vmemo_rec is not None and self._vmemo_rec.is_active():
            self.root.after(100, self._vmemo_poll)

    def _on_vmemo_done(self, blob: bytes) -> None:
        """录制完成：弹预览确认窗，用户确认后再发送（R72 优化：避免误发）。"""
        dur = self._vmemo_rec.elapsed() if self._vmemo_rec else 0.0
        self._show_vmemo_preview(blob, dur)

    def _show_vmemo_preview(self, blob: bytes, dur: float) -> None:
        """视频留言预览确认窗：首帧缩略图 + 时长 + 重录/取消/发送。"""
        import tkinter as tk
        from PIL import Image, ImageTk
        import io

        first_frame = vmemo_api.first_frame_png(blob)
        if not first_frame:
            # 解不出首帧就直接发（兜底）
            ch, to = self.view
            self.core.send_vmemo(ch, to, blob, duration=dur)
            self.show_toast("⭕ 视频留言已发送")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("视频留言预览")
        dlg.configure(bg="#1e1e2e")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)

        # 居中
        dlg.update_idletasks()
        w, h = 280, 340
        x = self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        # 圆形首帧预览
        try:
            img = Image.open(io.BytesIO(first_frame))
            img = img.resize((200, 200), Image.LANCZOS)
            # 圆形遮罩
            mask = Image.new("L", (200, 200), 0)
            from PIL import ImageDraw
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, 200, 200), fill=255)
            bg = Image.new("RGBA", (200, 200), (30, 30, 46, 0))
            bg.paste(img.convert("RGBA"), (0, 0), mask)
            photo = ImageTk.PhotoImage(bg)
        except Exception:
            photo = None

        canvas = tk.Canvas(dlg, width=220, height=220, bg="#1e1e2e",
                           highlightthickness=0)
        canvas.pack(pady=(20, 8))
        if photo:
            canvas.image = photo  # 防 GC
            canvas.create_image(110, 110, image=photo)
        else:
            canvas.create_text(110, 110, text="⭕", fill="#888", font=("Arial", 48))

        # 时长
        dur_lbl = tk.Label(dlg, text=f"{dur:.1f} 秒",
                           fg="#aab", bg="#1e1e2e",
                           font=("Microsoft YaHei UI", 10))
        dur_lbl.pack()

        # 按钮区
        btn_frame = tk.Frame(dlg, bg="#1e1e2e")
        btn_frame.pack(side="bottom", pady=16)

        def do_cancel():
            dlg.destroy()

        def do_rerecord():
            dlg.destroy()
            self._start_vmemo()

        def do_send():
            ch, to = self.view
            self.core.send_vmemo(ch, to, blob, duration=dur)
            dlg.destroy()
            self.show_toast("⭕ 视频留言已发送")

        tk.Button(btn_frame, text="重录", command=do_rerecord,
                  bg="#3a3a4a", fg="#ccc", activebackground="#4a4a5a",
                  activeforeground="#fff", relief="flat", bd=0,
                  padx=16, pady=6, font=("Microsoft YaHei UI", 10)).pack(
            side="left", padx=6)
        tk.Button(btn_frame, text="取消", command=do_cancel,
                  bg="#3a3a4a", fg="#ccc", activebackground="#4a4a5a",
                  activeforeground="#fff", relief="flat", bd=0,
                  padx=16, pady=6, font=("Microsoft YaHei UI", 10)).pack(
            side="left", padx=6)
        send_btn = tk.Button(btn_frame, text="发送", command=do_send,
                             bg="#4f8cff", fg="white",
                             activebackground="#6699ff",
                             activeforeground="white", relief="flat", bd=0,
                             padx=18, pady=6,
                             font=("Microsoft YaHei UI", 10, "bold"))
        send_btn.pack(side="left", padx=6)
        send_btn.focus_set()

        # 回车发送，ESC 取消
        dlg.bind("<Return>", lambda _e: do_send())
        dlg.bind("<Escape>", lambda _e: do_cancel())

    def _on_vmemo_error(self, text: str) -> None:
        """录制失败：提示用户。"""
        self.show_toast(f"视频留言录制失败：{text}", warn=True)

    def _open_vmemo_player(self, path: str, title: str = "视频留言") -> None:
        """打开视频留言播放窗（从落盘缓存读 VMA1）。"""
        try:
            with open(path, "rb") as f:
                blob = f.read()
        except OSError:
            self.show_toast("视频留言缓存已过期", warn=True)
            return
        win = VmemoPlayer(self.root, blob=blob, title=title,
                          on_close=lambda: self._vmemo_players.remove(win)
                          if win in self._vmemo_players else None)
        self._vmemo_players.append(win)

    # ---------- R38 1v1 语音对讲 UI ----------
    def _start_voice_call(self) -> None:
        """菜单「📞 语音通话」：仅私聊可用；无音频设备/不在密聊态均明确提示。"""
        ch, to = self.view
        if ch != "private" or to == self.core.uid:
            return
        if not self.core.connected:
            self.show_toast("未连接服务器，无法发起通话", warn=True)
            return
        import voice_api
        if not voice_api.available():
            self.show_toast("本机没有可用的音频输入设备，无法语音通话", warn=True)
            return
        if not self.core.calls.start_call(int(to)):
            return                    # 已在通话中：CallManager 已提示
        nick = (self.core.roster.get(to) or self.core.known.get(to) or {}).get("nick")
        self._ensure_call_window(nick=nick)

    def _on_call_event(self, ev: dict) -> None:
        """call 事件统一入口：维持唯一通话窗，转发状态给窗口刷新。

        收尾态（ended/failed）：窗口还在就刷新（自动关窗）；窗口已没了只留系统行，
        不再为失败弹新窗。warn 同理（无窗时降级为系统提示）。
        R45 video/video_frame 仅刷新已有窗口（绝不因此弹新窗）。
        """
        state = str(ev.get("state") or "")
        exists = self._call_win is not None and self._call_win.winfo_exists()
        if state in ("ended", "failed"):
            self._append_sys(f"📞 语音通话：{ev.get('text', '已结束')}")
            if exists:
                self._call_win.update_state(ev)
            return
        if state == "warn":
            if exists:
                self._call_win.update_state(ev)
            elif ev.get("text"):
                self._append_sys(f"⚠ 语音通话：{ev.get('text')}")
            return
        if state in ("video", "video_frame", "video_local"):
            if exists:
                self._call_win.update_state(ev)
            return
        win = self._ensure_call_window(nick=ev.get("nick"))
        win.update_state(ev)
        # R45 prefs['call_video']：接通即自动开摄像头（对端支持且尚未开启）
        if state == "incall" and self._prefs.get("call_video") \
                and self.core.calls.video_supported() \
                and not self.core.calls.is_video_on():
            self.core.calls.set_video(True)

    def _ensure_call_window(self, nick: str | None) -> CallWindow:
        """通话窗懒创建（同一时刻至多一个）；旧窗已销毁则重建。"""
        if self._call_win is not None and self._call_win.winfo_exists():
            if nick:
                self._call_win.lbl_nick.config(text=nick)
            return self._call_win
        self._call_win = CallWindow(self.root, manager=self.core.calls,
                                    peer_nick=nick or "",
                                    persist_mode=self._persist_call_duplex,
                                    persist_video=self._persist_call_video)
        return self._call_win

    # ---------- R72 多人语音房 ----------

    def _on_room_event(self, ev: dict) -> None:
        """room 事件统一入口：维持唯一语音房窗，转发状态给窗口刷新。"""
        state = str(ev.get("state") or "")
        exists = self._voice_room_win is not None and self._voice_room_win.winfo_exists()
        if state in ("left", "failed"):
            if ev.get("text"):
                self._append_sys(f"🎙 语音房：{ev['text']}")
            if exists:
                self._voice_room_win.update_event(ev)
            self._voice_room_win = None
            return
        if state in ("warn", "peer_failed"):
            if exists:
                self._voice_room_win.update_event(ev)
            elif ev.get("text"):
                self._append_sys(f"⚠ 语音房：{ev['text']}")
            return
        if not exists:
            self._ensure_voice_room_window()
            exists = True
        if exists:
            self._voice_room_win.update_event(ev)

    def _ensure_voice_room_window(self) -> VoiceRoomWindow:
        """语音房窗懒创建（同一时刻至多一个）；旧窗已销毁则重建。"""
        if self._voice_room_win is not None and self._voice_room_win.winfo_exists():
            return self._voice_room_win
        room_name = "语音房"
        if self.core.voice_room.room:
            room_name = self.core.voice_room.room
        self._voice_room_win = VoiceRoomWindow(
            self.root, manager=self.core.voice_room,
            avatar=self._avatars, room_name=room_name,
            on_leave=self._on_voice_room_closed)
        return self._voice_room_win

    def _on_voice_room_closed(self) -> None:
        """语音房窗关闭回调（清引用）。"""
        self._voice_room_win = None

    def _join_voice_room(self, room: str = "") -> None:
        """从群面板/菜单进入语音房（room 缺省取当前会话键）。"""
        if not room:
            ch, to = self.view
            if ch == "group" and to is not None:
                room = f"group:{int(to)}"
            else:
                room = "public"
        self._ensure_voice_room_window()
        self.core.voice_room.join(room)

    def _toggle_call_duplex(self) -> None:
        """R39A「＋」菜单：通话全双工开关（热生效 + prefs 持久化）。"""
        on = not self.core.calls.is_duplex()
        self.core.calls.set_duplex(on)
        self._persist_call_duplex(on)
        self._append_sys("🎙 语音通话已切换为全双工（建议戴耳机）" if on
                         else "🖐 语音通话已切换为按住说话（PTT）")

    def _persist_call_duplex(self, on: bool) -> None:
        self._prefs.set("call_duplex", bool(on))

    def _persist_call_video(self, on: bool) -> None:
        """R45 摄像头开关记忆：接通后是否自动开摄像头由 prefs['call_video']。"""
        self._prefs.set("call_video", bool(on))

    # ---------- R38B STT/翻译（可选依赖，缺则入口隐藏） ----------
    def _voice_stt(self, idx: int, _path: str | None = None) -> None:
        """语音转文字：vosk 纯本地识别，结果写 <wav>.txt 旁注（绝不上传）。
        _path 供语音气泡内「⇄转文字」chip 传入（本函数按 idx 取已缓冲行，忽略之）。"""
        raw = self.msg_list.get_row(idx)
        path = raw and raw.get("voice_path")
        if not path or not os.path.isfile(path):
            self.show_toast("本地语音文件不存在（可能已过期）", warn=True)
            return
        model_dir = optional.find_model_dir(
            str(self._prefs.get("vosk_model_dir") or ""))
        if not model_dir:
            from widgets import dialogbox
            dialogbox.show_message(
                "转文字",
                "未找到随包内置的 vosk 模型（可能未随包分发或已损坏）。\n\n"
                "可在「＋」菜单 → 语音转写设置 里指定本机模型目录"
                "（vosk-model-small-cn-*），或用环境变量 VOSK_MODEL 指定。",
                parent=self.root)
            return
        self._append_sys("📝 正在本地转写（vosk，不上传）…")

        def _run():
            try:
                text = optional.transcribe_wav(path, model_dir)
                err = None
            except Exception as exc:            # 模型损坏/音频异常 → 可读错误
                text, err = None, str(exc)
            self.root.after(0, lambda: self._stt_done(path, text, err))

        threading.Thread(target=_run, daemon=True, name="voice-stt").start()

    def _stt_done(self, path: str, text: str | None, err: str | None) -> None:
        if err or not text:
            self._append_sys(f"⚠ 转写失败：{err or '未识别到内容'}")
            return
        try:
            with open(path + ".txt", "w", encoding="utf-8") as fh:
                fh.write(text)                  # 本地旁注文件（不上传）
        except OSError as exc:
            self._append_sys(f"⚠ 转写结果保存失败：{exc}")
            return
        self._append_sys("📝 转写完成（已写入本地旁注）")
        self.msg_list._render()                 # 重绘出旁注行
        self._view_voice_note(path + ".txt")

    def _view_voice_note(self, path: str) -> None:
        from theme import msg_colors
        try:
            with open(path, "r", encoding="utf-8") as fh:
                body = fh.read()
        except OSError as exc:
            self._append_sys(f"⚠ 读取转写失败：{exc}")
            return
        tv = TextViewer(self.root, body or "（空）", font=self._f,
                        title="语音转写（仅本地）", colors=msg_colors(self._skin))
        ui_fx.fade_in(tv)                         # R43A1 弹窗淡入

    def _show_edit_history(self, row) -> None:
        """R70B：查看消息的编辑历史（服务器下发的历史版本快照，逐版本列出）。"""
        raw = getattr(row, "raw", row) or {}
        edits = raw.get("edits")
        if not isinstance(edits, list) or not edits:
            self._append_sys("该消息没有更早的版本")
            return
        blocks = []
        for n, snap in enumerate(edits, 1):
            ts = snap.get("ts")
            when = (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
                    if ts else "?")
            blocks.append(f"—— 版本 {n} · {when} ——\n"
                          f"{str(snap.get('text') or '（空）')}")
        blocks.append(f"—— 当前版本 ——\n{str(raw.get('text') or '（空）')}")
        from theme import msg_colors
        tv = TextViewer(self.root, "\n\n".join(blocks), font=self._f,
                        title=f"编辑历史（{len(edits)} 个更早版本）",
                        colors=msg_colors(self._skin))
        ui_fx.fade_in(tv)                         # R43A1 弹窗淡入

    def _stt_settings(self) -> None:
        """配置 vosk 模型目录（prefs 持久化；留空清除）。"""
        cur = str(self._prefs.get("vosk_model_dir") or "")
        d = filedialog.askdirectory(title="选择 vosk 模型目录",
                                    initialdir=cur or None, parent=self.root)
        if d:
            self._prefs.set("vosk_model_dir", d)
            self._append_sys(f"📝 vosk 模型目录已设置：{d}")
        elif cur:
            self._prefs.set("vosk_model_dir", "")
            self._append_sys("📝 已清除 vosk 模型目录配置")

    def _toggle_translate(self) -> None:
        """🌐 翻译开关（默认关）：首次开启弹隐私确认（文本将发往第三方服务）。"""
        if self._prefs.get("translate_on"):
            self._prefs.set("translate_on", False)
            self._append_sys("🌐 消息翻译已关闭")
            return
        from widgets import dialogbox
        if not dialogbox.ask_yesno(
                "开启消息翻译",
                "翻译功能需要联网：被翻译的消息文本将发送给第三方翻译服务"
                "（Google 端点）。\n\n仅在你主动右键选择「翻译」时才会发送。"
                "是否开启？",
                parent=self.root):
            return
        self._prefs.set("translate_on", True)
        self._append_sys("🌐 消息翻译已开启（右键消息 → 翻译）")

    def _translate_msg(self, text: str) -> None:
        """右键翻译：网络请求放后台线程，结果弹窗（原文+译文，不改原消息）。"""
        self._append_sys("🌐 正在翻译…")

        def _run():
            try:
                result = optional.translate_text(text)
                err = None
            except Exception as exc:
                result, err = None, str(exc)
            self.root.after(0, lambda: self._translate_done(text, result, err))

        threading.Thread(target=_run, daemon=True, name="msg-translate").start()

    def _translate_done(self, src: str, result: str | None,
                        err: str | None) -> None:
        if err or not result:
            self._append_sys(f"⚠ 翻译失败：{err or '空结果'}")
            return
        from theme import msg_colors
        tv = TextViewer(self.root, f"原文：\n{src}\n\n译文：\n{result}",
                        font=self._f, title="翻译结果", colors=msg_colors(self._skin))
        ui_fx.fade_in(tv)                         # R43A1 弹窗淡入

    # ---------- R26A 投票 ----------
    def _on_poll_vote(self, idx: int, option: int) -> None:
        """点击投票气泡某选项 → 发 poll_vote（服务器聚合后回广播 poll_state）。"""
        raw = self.msg_list.get_row(idx)
        if not raw or not isinstance(raw.get("poll"), dict):
            return
        seq = raw.get("seq")
        if seq is None:
            self._append_sys("投票尚未同步，请稍后再投")
            return
        if time.time() >= float(raw["poll"].get("end") or 0):
            self._append_sys("投票已结束")
            return
        self.core.send_poll_vote(seq, int(option))

    def _poll_dialog(self) -> None:
        """R26A 发起投票对话框：问题 + 2~10 个选项 → 发送到当前会话。"""
        if self._ro_mode:
            self._append_sys("频道只读，无法发起投票")
            return
        ch, to = self.view
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("发起投票")
        dlg.transient(self.root)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "发起投票")
        frm = tk.Frame(dlg, padx=12, pady=10)
        frm.pack()
        tk.Label(frm, text="投票问题：").grid(row=0, column=0, sticky="w")
        q_entry = tk.Entry(frm, width=42)
        q_entry.grid(row=0, column=1, pady=2)
        opts = []
        for r in range(3):                     # 默认 3 个选项位（空位忽略）
            tk.Label(frm, text=f"选项{r + 1}：").grid(row=1 + r, column=0, sticky="w")
            e = tk.Entry(frm, width=42)
            e.grid(row=1 + r, column=1, pady=2)
            opts.append(e)
        # R70C：匿名 / 多选 / 测验（指定正确项）三开关
        v_anon = tk.IntVar(value=0)
        v_multi = tk.IntVar(value=0)
        v_quiz = tk.IntVar(value=0)
        tk.Checkbutton(frm, text="🕶 匿名投票（不显示投票人）",
                       variable=v_anon).grid(row=4, column=1, sticky="w")
        tk.Checkbutton(frm, text="☑ 多选（可投多项，再点取消）",
                       variable=v_multi).grid(row=5, column=1, sticky="w")
        tk.Checkbutton(frm, text="🎯 测验（结束前不公布答案）",
                       variable=v_quiz).grid(row=6, column=1, sticky="w")
        tk.Label(frm, text="正确选项序号（测验用，1 起）：").grid(row=7, column=0, sticky="w")
        correct_entry = tk.Entry(frm, width=8)
        correct_entry.grid(row=7, column=1, sticky="w", pady=2)
        q_entry.focus_set()

        def _do() -> None:
            question = q_entry.get().strip()
            options = [o.get().strip() for o in opts if o.get().strip()]
            if not question:
                self._append_sys("投票问题不能为空")
                return
            if len(options) < 2:
                self._append_sys("至少需要两个选项")
                return
            quiz = bool(v_quiz.get())
            correct = None
            if quiz:                           # 测验必须给出合法正确项
                try:
                    correct = int(correct_entry.get().strip()) - 1
                except ValueError:
                    correct = -1
                if correct < 0 or correct >= len(options):
                    self._append_sys("请填写有效的正确选项序号（1 起）")
                    return
            if not self.core.send_poll(channel=ch, to=to, question=question,
                                       options=options, anonymous=bool(v_anon.get()),
                                       multi=bool(v_multi.get()), quiz=quiz,
                                       correct=correct):
                self._append_sys("投票发送失败（未连接）")
                return
            self._append_sys("投票已发起")
            dlg.destroy()

        bar = tk.Frame(dlg)
        bar.pack(pady=(0, 8))
        tk.Button(bar, text="发送", command=_do, padx=10).pack(side="left", padx=4)
        tk.Button(bar, text="取消", command=dlg.destroy, padx=10).pack(side="left")
        q_entry.bind("<Return>", lambda e: _do())

    def _on_poll_state(self, ev: dict) -> None:
        """服务器 poll_state：当前会话内的投票行刷权威票数（core 已落盘）。"""
        self.msg_list.set_poll_state(ev.get("seq"), ev)

    def _on_preview(self, ev: dict) -> None:
        """服务器 preview：当前会话内消息附链接预览卡片（core 已落盘）。"""
        self.msg_list.set_preview(ev.get("seq"), ev.get("preview") or {})

    # ---------- R26B 频道只读 ----------
    def _apply_channel_ro(self) -> None:
        """频道只读：当前会话为频道（broadcast 群）且非创建者 → 输入/操作全禁用。"""
        ch, to = self.view
        ro = False
        is_forum = False
        if ch == "group":
            g = self.core.groups.get(to)
            ro = bool(g and g.get("kind") == "channel"
                      and g.get("owner") != self.core.uid)
            is_forum = bool(g and g.get("kind") == "forum")
        self.msg_list.set_forum_mode(is_forum)      # R72：论坛频道按贴展示
        if ro == self._ro_mode:
            self.msg_list.set_comment_entry(ro)   # R71：即便未变化也同步评论入口标志
            return
        self._ro_mode = ro
        state = "disabled" if ro else "normal"
        self.entry.config(state=state)
        self.msg_list.set_comment_entry(ro)       # R71：频道内 0 评论也显示「💬 评论」入口

        def _all_buttons(w):                      # R31：按钮嵌套进工具行，需递归
            for c in w.winfo_children():
                if isinstance(c, tk.Button):
                    yield c
                yield from _all_buttons(c)

        for b in _all_buttons(self._bottom_frame):
            b.config(state=state)
        if ro and self._sticker_row.winfo_manager():
            self._sticker_on = False
            self._stk_gif_stop()                 # R64：收起贴纸条同时停 GIF 轮播
            self._sticker_nav.pack_forget()
            self._sticker_row.pack_forget()
        if ro:
            self._append_sys("📢 当前为频道（仅创建者可发言）")
        else:
            self._append_sys("已恢复发言权限")

    # ---------- R14 会话导出 ----------
    def _export_conversation(self) -> None:
        """导出当前会话全部消息为 .md（含昵称/时间/系统行/图片占位）。"""
        ch, to = self.view
        msgs = self.core.history(ch, to)
        label = "公共频道" if ch == "public" else \
            (f"私聊 {to}" if ch == "private" else f"群 {to}")
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".md",
            initialfile=f"chat_{label}-{time.strftime('%Y%m%d-%H%M')}.md",
            filetypes=[("Markdown", "*.md"), ("文本", "*.txt")])
        if not path:
            return
        lines = ["# 会话导出", "", f"会话：{label}", f"条数：{len(msgs)}",
                 f"导出时间：{time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
        for m in msgs:
            if m.get("deleted"):
                lines.append("- （消息已撤回）")
                continue
            nick = m.get("nick", "?"); hh = time.strftime("%H:%M", time.localtime(m.get("ts", 0)))
            lines.append(f"- **{nick}** {hh}: {self._export_body(m)}")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            self._append_sys(f"已导出 {len(msgs)} 条 → {path}")
        except OSError as exc:
            self._append_sys(f"导出失败: {exc}")

    def _export_body(self, m: dict) -> str:
        """把单条消息转导出用纯文本（对齐 TG 官方导出轻量版）：
        富文本转纯文本、贴纸、语音、文件引用、投票、回复/转发前缀。"""
        parts = []
        text = m.get("text", "")
        # R59 富文本：段文本直接拼回纯文本（无则退 tag 原始正文）
        r = m.get("rich")
        if isinstance(r, list) and r:
            text = rich.plain_text(r)
        sticker = m.get("sticker", "")
        if sticker:
            parts.append(STICKER_BY_CODE.get(sticker, {}).get("emoji", f":{sticker}:"))
        if text:
            parts.append(expand_shortcodes(text))
        if m.get("image_path"):
            parts.append(f"[图片] {os.path.basename(m['image_path'])}")
        if m.get("voice"):
            parts.append(f"[语音] {m.get('duration', 0):g} 秒")
        if m.get("poll"):
            parts.append(f"[投票] {str(m['poll'].get('question') or '')[:60]}")
        f = m.get("file") if isinstance(m.get("file"), dict) else None
        if f:
            tag = "图片" if f.get("kind") == "image" else "文件"
            parts.append(f"[{tag}] {str(f.get('name') or '')[:24]}")
            size = f.get("size") or 0
            if size:
                parts.append(f"（{_hsize(size)}）")
            parts.append("（网页端文件）")
        if m.get("file_id"):
            nm = m.get("filename") or m.get("name") or ""
            parts.append(f"[文件] {nm}" if nm else "[文件]")
        body = " ".join(p for p in parts if p).strip()
        if m.get("reply"):
            body = f"↩ 回复 {m['reply'].get('nick', '?')}: {body}"
        if m.get("forward"):
            fwd = m["forward"]
            fw = fwd.get("text") or STICKER_BY_CODE.get(fwd.get("sticker", ""), {}).get("emoji", "")
            body = f"↳ 转发自 {fwd.get('nick', '?')}: {fw} | {body}"
        return body

    def _toggle_pin_msg(self, idx: int) -> None:
        """R13 置顶/取消置顶当前消息。"""
        raw = self.msg_list.get_row(idx)
        if not raw or raw.get("seq") is None:
            return
        ch, to = self.view
        key = self._pin_key(ch, to)
        snap = self.core.pins.get(key)
        on = not (snap and snap.get("seq") == raw.get("seq"))
        self.core.send_pin(ch, to, raw["seq"], on=on)

    def _forward(self, idx: int) -> None:
        """R13 转发：打开会话选择器，把原消息快照作为 forward 新消息发出。
        桌面图片/网页文件消息同样可转发（图片走真实文件传输，网页文件转文本引用）。"""
        fwd = self._fwd_snapshot(self.msg_list.get_row(idx))
        if not fwd:
            self._append_sys("该消息暂不支持转发")
            return
        self._forward_pick(fwd)

    def _fwd_snapshot(self, raw) -> dict | None:
        """单条消息 → 可转发快照；不支持的类型返回 None。

        - 文本/表情：原文快照（R13）
        - 桌面图片（image_path）：带本地路径，转发时真实重发文件
          （caption 另存，避免被占位文本覆盖）
        - 网页端文件/图片（file 字典）：转文本引用（仅服务端可下载）
        """
        if not raw or raw.get("deleted"):
            return None
        fwd = {"nick": raw.get("nick", "?"), "seq": raw.get("seq"),
               "ts": raw.get("ts")}
        path = raw.get("image_path")
        f = raw.get("file") if isinstance(raw.get("file"), dict) else None
        if path:
            fwd["image_path"] = path
            fwd["caption"] = str(raw.get("text") or "").strip()
            fwd["text"] = f"[图片] {os.path.basename(path)}"
        elif f:
            tag = "图片" if f.get("kind") == "image" else "文件"
            nm = str(f.get("name") or "")[:24]
            sz = f.get("size") or 0
            fwd["text"] = f"[{tag}] {nm}" + (f"（{_hsize(sz)}）" if sz else "")
        elif raw.get("text"):
            fwd["text"] = raw.get("text")
        elif raw.get("sticker"):
            fwd["sticker"] = raw.get("sticker")
        else:
            return None
        return fwd

    def _sel_forward_snaps(self) -> list:
        """R31B：收集选中行的可转发快照（文本/表情/图片/网页文件）。"""
        fwds = []
        for idx in self.msg_list.selected_rows():
            fwd = self._fwd_snapshot(self.msg_list.get_row(idx))
            if fwd:
                fwds.append(fwd)
        return fwds

    def _multi_forward(self) -> None:
        """R31B：多选转发——把选中消息逐条转发到目标会话。"""
        fwds = self._sel_forward_snaps()
        if not fwds:
            self._append_sys("选中内容没有可转发的消息")
            return
        self._forward_pick(fwds)

    def _merge_forward(self) -> None:
        """R39D③：多选合并转发——打包为一条「合并转发」卡片消息发往目标会话。
        仅文本/表情/网页文件可入包（需服务器 seq；桌面图片无 seq 自动跳过）。"""
        items = self._sel_forward_snaps()
        items = [it for it in items if it.get("seq") is not None]
        if not items:
            self._append_sys("选中内容没有可合并转发的消息（需带序号的文本/表情/网页文件）")
            return
        if len(items) > 30:                   # 与服务器 fp 白名单上限一致
            self._append_sys("合并转发最多 30 条，超出部分已截断")
            items = items[:30]
        self._forward_pick(items, merged=True)

    def _multi_delete(self) -> None:
        """R31B：多选删除——撤回选中的自己消息；他人消息/无序号跳过并提示。"""
        n_del = n_skip = 0
        for idx in self.msg_list.selected_rows():
            raw = self.msg_list.get_row(idx)
            if not raw or raw.get("seq") is None \
                    or raw.get("uid") != self.core.uid:
                n_skip += 1
                continue
            if self._pending_edit_seq == raw.get("seq"):
                self._pending_edit_seq = None
                self._drop_reply_state()         # 批量撤回命中编辑中消息 → 同步清引用
                self.entry.delete("1.0", "end")
            self.core.send_del(raw["seq"])
            n_del += 1
        self.msg_list.exit_select_mode()
        if n_del and n_skip:
            self._append_sys(f"已撤回 {n_del} 条，跳过 {n_skip} 条（仅能删除自己的消息）")
        elif n_del:
            self._append_sys(f"已撤回 {n_del} 条消息")
        elif n_skip:
            self._append_sys("只能删除自己的消息")

    def _on_sel_change(self, mode: bool, count: int) -> None:
        """R31B：选择模式/勾选数变化 → 顶栏显隐 + 计数 + 按钮可用态。"""
        if mode:
            self.sel_count_lbl.config(text=f"已选 {count} 条")
            state = "normal" if count else "disabled"
            self.sel_fwd_btn.config(state=state)
            self.sel_merge_btn.config(state=state)
            self.sel_del_btn.config(state=state)
            if not self.sel_bar.winfo_manager():
                self.sel_bar.place(relx=0, rely=0, relwidth=1)
            self.sel_bar.lift()
        elif self.sel_bar.winfo_manager():
            self.sel_bar.place_forget()

    def _forward_pick(self, fwd, merged: bool = False) -> None:
        """转发目标选择器：公共 + 在线名单 + 我加入的群（R13 单条 / R31B 多条 /
        R39D③ merged=打包为一条合并转发卡）。"""
        if isinstance(fwd, dict):
            fwd = [fwd]
        # R64：合并转发只提交「源会话 + 源消息 seq」，条目由服务器聚合（不可伪造）
        src_ch, src_to = self.view
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("转发到…")
        dlg.transient(self.root)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "转发到…")
        dlg.geometry("+%d+%d" % (self.root.winfo_rootx() + 60,
                                 self.root.winfo_rooty() + 60))
        f = (FONT_FAMILY, 10)
        if merged:
            preview = f"合并转发 {len(fwd)} 条消息"
        elif len(fwd) == 1:
            preview = fwd[0].get("text", "表情")[:24]
        else:
            preview = f"{len(fwd)} 条消息"
        tk.Label(dlg, text=f"↳ 转发: {preview}",
                 font=f, anchor="w").pack(fill="x", padx=8, pady=4)
        lb = tk.Listbox(dlg, font=f, width=30, height=10)
        lb.pack(fill="both", expand=True, padx=8, pady=4)
        targets = [("public", None, "公共频道")]
        for uid, u in self.core.roster.items():
            if uid != self.core.uid:
                targets.append(("private", uid, u.get("nick", f"私聊{uid}")))
        for gid, g in self.core.groups.items():
            targets.append(("group", gid, g.get("name", f"群{gid}")))
        for _ch, _to, label in targets:
            lb.insert("end", label)

        def _do():
            sel = lb.curselection()
            if not sel or not (0 <= sel[0] < len(targets)):
                return
            ch, to, _label = targets[sel[0]]
            if merged:                        # R39D③：打包为一条合并转发卡
                seqs = [it.get("seq") for it in fwd if it.get("seq") is not None]
                if not seqs:
                    self._append_sys("无法合并转发：缺少源消息序号")
                    return
                src = {"type": src_ch}
                if src_ch == "private" and src_to is not None:
                    src["uid"] = src_to
                elif src_ch == "group" and src_to is not None:
                    src["gid"] = src_to
                self.core.send_chat("", channel=ch, to=to,
                                    fwd_seqs=seqs, fwd_from=src)
            else:
                for _fwd in fwd:              # R31B：多条逐条转发（单条=1 次循环）
                    path = _fwd.get("image_path")
                    if path and os.path.isfile(path) and ch == "private" \
                            and to is not None:
                        # P0：图片真实转发——走文件传输，对端免确认自动收图渲染
                        fid = self.core.files.send_file(
                            path, to, caption=_fwd.get("caption", ""))
                        if fid:
                            self._append_msg({
                                "t": "image", "channel": "private",
                                "uid": self.core.uid, "to": to,
                                "nick": self.core.nick,
                                "file_id": fid, "image_path": path,
                                "text": _fwd.get("caption", ""),
                                "ts": time.time()})
                            self._append_sys(f"📎 正在转发图片给 {_label}…")
                        continue
                    self.core.send_chat(_fwd.get("text", ""),
                                        sticker=_fwd.get("sticker", ""),
                                        channel=ch, to=to, forward=_fwd)
            self.msg_list.exit_select_mode()  # 多选转发完成后退出选择模式
            dlg.destroy()

        tk.Button(dlg, text="关闭", command=dlg.destroy, font=f).pack(
            side="left", padx=8, pady=6)
        tk.Button(dlg, text="转发", command=_do, font=f).pack(
            side="right", padx=8, pady=6)
        lb.bind("<Double-Button-1>", lambda e: _do())

    def _open_fwd_pack(self, idx: int) -> None:
        """R39D③：双击合并转发卡 → 只读窗逐条浏览（昵称加粗 + 时间灰字 + 正文可复制）。"""
        raw = self.msg_list.get_row(idx)
        fp = raw.get("fp") if isinstance(raw, dict) else None
        items = [it for it in (fp or {}).get("items", [])
                 if isinstance(it, dict)] if isinstance(fp, dict) else []
        if not items:
            return
        win = tk.Toplevel(self.root)
        ui_fx.fade_in(win)                        # R43A1 弹窗淡入
        win.title(f"合并转发 · {len(items)} 条")
        win.transient(self.root)
        win.geometry("460x420+%d+%d" % (self.root.winfo_rootx() + 80,
                                        self.root.winfo_rooty() + 60))
        win.configure(bg=self._dp["win"])
        self._apply_apple_dialog(win, "合并转发")
        txt = tk.Text(win, wrap="word", font=self._f, relief="flat",
                      padx=12, pady=8, bg=self._skin.get("panel_bg", "#ffffff"),
                      fg=self._skin.get("fg", "#222222"))
        bar = tk.Scrollbar(win, command=txt.yview)
        txt.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        txt.pack(fill="both", expand=True)
        txt.tag_config("nick", font=(FONT_FAMILY, 10, "bold"))
        txt.tag_config("when", foreground=self._dp["sub"],
                       font=(FONT_FAMILY, 9))
        for it in items:
            ts = it.get("ts")
            try:
                when = time.strftime("%m-%d %H:%M", time.localtime(float(ts)))
            except (TypeError, ValueError):
                when = ""
            txt.insert("end", str(it.get("nick", "?")), "nick")
            if when:
                txt.insert("end", f"   {when}", "when")
            txt.insert("end", "\n" + str(it.get("text", "") or "") + "\n\n")
        txt.configure(state="disabled")       # 只读，但仍可框选复制
        tk.Button(win, text="关闭", command=win.destroy, width=8,
                  font=self._f).pack(pady=6)
        win.grab_set()

    def _reaction_picker(self, idx: int) -> None:
        """R13 表情回应：弹网格选表情（点选即加/摘）。"""
        raw = self.msg_list.get_row(idx)
        if not raw or raw.get("seq") is None:
            return
        emoji_set = ["👍", "❤️", "😂", "😮", "😢", "🔥", "🎉", "🙏"]
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("表情回应")
        dlg.transient(self.root)
        self._apply_apple_dialog(dlg, "表情回应")
        dlg.configure(bg=self._dp["win"])
        dlg.geometry("+%d+%d" % (self.root.winfo_rootx() + 80,
                                 self.root.winfo_rooty() + 80))
        f = (FONT_FAMILY, 16)
        wrap = tk.Frame(dlg)
        wrap.pack(padx=6, pady=6)
        reactions = raw.get("reactions") or {}
        me = str(self.core.uid)
        for i, emoji in enumerate(emoji_set):
            own = me in (reactions.get(emoji) or {})
            btn = tk.Button(wrap, text=emoji, font=f, relief="flat",
                        bg=self._dp["tab_on_bg"] if own else self._dp["tab_bg"],
                        command=lambda e=emoji: self._react(idx, e))
            btn.grid(row=i // 4, column=i % 4, padx=2, pady=2)
        close = tk.Button(dlg, text="✕", font=(FONT_FAMILY, 10), relief="flat",
                          command=dlg.destroy)
        close.grid(in_=wrap, row=(len(emoji_set) - 1) // 4 + 1, column=0,
                   columnspan=4, sticky="e", padx=2, pady=2)

    def _on_mention_click(self, nick: str) -> None:
        """R29C：点消息里的 @昵称 → 跳到该成员私聊（需在群会话内）。
        R71：先查 prefs['handles'] 别名表（全局生效，任意会话可用），未命中再按群成员昵称匹配。"""
        name = str(nick or "").lstrip("@")
        if not name:
            return
        hu = (self._prefs.get("handles") or {}).get(name)
        if hu is not None:
            try:
                hu = int(hu)
            except (TypeError, ValueError):
                hu = None
            if hu is not None:
                if hu == self.core.uid:
                    self._open_user_card(hu)
                else:
                    self._switch_view("private", hu)
                return
        if self.view[0] != "group":
            return
        gid = self.view[1]
        for m in self.core.group_members.get(gid, []):
            if str(m.get("nick") or "") == name:
                try:
                    self._switch_view("private", int(m["uid"]))
                except (KeyError, TypeError, ValueError):
                    pass
                return

    def _on_react_seq(self, seq: int, emoji: str) -> None:
        """R27 快速回应：按全局 seq 定位行并切换回应（hover 悬浮条/药丸点击共用）。"""
        idx = self.msg_list.seq_index(seq)
        if idx is not None:
            self._react(idx, emoji)

    def _react(self, idx: int, emoji: str) -> None:
        """R13 发送回应切换（同消息同表情：若我已回则摘下，否则加上）。"""
        raw = self.msg_list.get_row(idx)
        if not raw or raw.get("seq") is None:
            return
        reactions = raw.get("reactions") or {}
        me = str(self.core.uid)
        on = me not in (reactions.get(emoji) or {})
        self.core.send_reaction(raw["seq"], emoji, on=on)
        if on:                                     # R29D：仅"加上"时记入最近使用
            self._touch_recent_react(emoji)

    def _touch_recent_react(self, emoji: str) -> None:
        """R29D：表情记入最近使用（去重前置，最多 REACT_RECENT_MAX），落盘并刷新悬浮条。"""
        emoji = str(emoji or "")
        if not emoji:
            return
        rec = [e for e in self._recent_reacts if e != emoji]
        rec.insert(0, emoji)
        self._recent_reacts = rec[:REACT_RECENT_MAX]
        self._prefs.set("react_recent", self._recent_reacts)
        self.msg_list.set_quick_emojis(self._recent_reacts)

    def _on_quick_more(self, seq: int) -> None:
        """R29D：悬浮条"＋"→ 多分类全表情选择器（点选即回应并记入最近使用）。"""
        idx = self.msg_list.seq_index(seq)
        if idx is None:
            return
        raw = self.msg_list.get_row(idx)
        if not raw or raw.get("seq") is None:
            return
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("更多表情回应")
        dlg.transient(self.root)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "更多表情回应")
        dlg.resizable(False, False)
        dlg.geometry("+%d+%d" % (self.root.winfo_rootx() + 100,
                                 self.root.winfo_rooty() + 100))
        f = (FONT_FAMILY, 14)
        cats = list(REACT_GROUPS)
        cats.insert(0, ("常用", list(self._recent_reacts
                                     or self.msg_list.QUICK_EMOJIS)))
        body = tk.Frame(dlg)
        body.pack(padx=6, pady=6)
        tabs = tk.Frame(body)
        tabs.pack(fill="x", pady=(0, 4))
        gridf = tk.Frame(body)
        gridf.pack()
        tab_btns = {}

        def _show(name: str) -> None:
            for w in gridf.winfo_children():
                w.destroy()
            for n, _e in cats:
                tab_btns[n].configure(bg=self._dp["tab_on_bg"] if n == name
                                      else self._dp["tab_bg"])
            for i, e in enumerate(dict.fromkeys(dict(cats)[name])):
                tk.Button(gridf, text=e, font=f, relief="flat",
                          bg=self._dp["tab_bg"],
                          command=lambda em=e: (self._react(idx, em), dlg.destroy())
                          ).grid(row=i // 8, column=i % 8, padx=2, pady=2)

        for name, _e in cats:
            b = tk.Button(tabs, text=name, font=(FONT_FAMILY, 10),
                          relief="flat", bg=self._dp["tab_on_bg"] if name == "常用"
                          else self._dp["tab_bg"],
                          command=lambda n=name: _show(n))
            b.pack(side="left", padx=2)
            tab_btns[name] = b
        _show("常用")

    # ---------- R30E hashtag 点击 / R30D 回应详情 / R30A 日期跳转 ----------
    def _on_hashtag_click(self, word: str) -> None:
        """R30E：点 #话题 → 打开全局搜索并自动搜该话题（去掉 # 后搜正文）。"""
        tag = str(word or "").strip().lstrip("#")
        if not tag:
            return
        self._focus_global_search()
        gs = getattr(self, "_global_search_box", None)
        if gs is None or not gs.winfo_exists():
            return
        gs.entry.delete(0, "end")
        gs.entry.insert(0, tag)
        gs._debounce()                     # 直接触发后台扫描

    def _on_react_detail(self, seq, emoji, ev) -> None:
        """R30D：药丸 hover → 浮示谁回应了该表情；ev=None → 收起提示。"""
        tip = self._react_tip
        if seq is None or emoji is None or ev is None:
            if tip is not None and tip.winfo_exists():
                tip.destroy()
            self._react_tip = None
            return
        idx = self.msg_list.seq_index(seq)
        if idx is None:
            return
        raw = self.msg_list.get_row(idx) or {}
        users = (raw.get("reactions") or {}).get(emoji) or {}
        names = []
        for u in users:
            if str(u) == str(self.core.uid):
                names.append("我")
                continue
            try:
                ui = int(u)
            except (TypeError, ValueError):
                ui = None
            r = (self.core.roster.get(ui) if ui is not None else None) \
                or (self.core.known.get(ui) if ui is not None else None)
            names.append(str(r.get("nick")) if r else f"用户{u}")
        if not names:
            return
        text = f"{emoji} " + "、".join(names[:8]) + ("…" if len(names) > 8 else "")
        if tip is not None and tip.winfo_exists():
            tip.destroy()
        tip = tk.Toplevel(self.root)
        tip.overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(tip, text=text, font=(FONT_FAMILY, 9), bg=self._dp["warn_bg"],
                 fg=self._dp["fg"], relief="solid", bd=1, padx=6, pady=3).pack()
        tip.geometry(f"+{self.root.winfo_pointerx() + 12}"
                     f"+{self.root.winfo_pointery() - 30}")
        _make_draggable(tip)
        self._react_tip = tip
        # 4s 自动收起（防鼠标快速移出时 Leave 丢失导致残留）
        self.root.after(4000, lambda: self._on_react_detail(None, None, None))

    def _on_read_hover(self, row, ev) -> None:
        """R33③：hover 自己消息的 ✓已读 标记 → 请求服务器已读详情；
        row/ev 为 None → 收起浮示。回帧见 _on_read_detail_resp。"""
        tip = getattr(self, "_read_tip", None)
        if row is None or ev is None:
            aft = getattr(self, "_read_tip_after", None)
            if aft is not None:
                try:
                    self.root.after_cancel(aft)
                except Exception:
                    pass
                self._read_tip_after = None
            if tip is not None and tip.winfo_exists():
                tip.destroy()
            self._read_tip = None
            return
        self._read_hover_row = row
        self._read_tip_at = (self.root.winfo_pointerx(),
                             self.root.winfo_pointery())
        try:
            # C9②：群会话用 MSG_READERS（含未读成员 + N/M）；私聊/公聊沿用 READ_DETAIL
            if self.view[0] == "group":
                self.core.send_msg_readers(self._hist_key(), int(row.raw.get("seq") or 0))
            else:
                self.core.send_read_detail(self._hist_key())
        except Exception:
            pass

    def _on_read_detail_resp(self, ev) -> None:
        """R33③：READ_DETAIL 回帧 → 指针处浮示已读成员（读到本条者，4s 自动收起）。"""
        row = getattr(self, "_read_hover_row", None)
        at = getattr(self, "_read_tip_at", None)
        if row is None or at is None:
            return
        rseq = row.raw.get("seq")
        names = []
        for rd in ev.get("readers") or []:
            try:
                if rseq is not None and int(rd.get("seq") or 0) < int(rseq):
                    continue               # 该成员只读到更早，尚未读这条
            except (TypeError, ValueError):
                continue
            uid = rd.get("uid")
            if str(uid) == str(self.core.uid):
                names.append("我")
            else:
                names.append(str(rd.get("nick") or f"用户{uid}"))
        if not names:
            return
        tip = getattr(self, "_read_tip", None)
        if tip is not None and tip.winfo_exists():
            tip.destroy()
        text = "👀 已读：" + "、".join(names[:8]) + ("…" if len(names) > 8 else "")
        tip = tk.Toplevel(self.root)
        tip.overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(tip, text=text, font=(FONT_FAMILY, 9), bg=self._dp["warn_bg"],
                 fg=self._dp["fg"], relief="solid", bd=1, padx=6, pady=3).pack()
        tip.geometry(f"+{at[0] + 12}+{at[1] - 30}")
        _make_draggable(tip)
        self._read_tip = tip
        self._read_hover_row = None
        # 4s 自动收起（防 Leave 丢失残留）；换新的先取消旧定时器防误收
        aft = getattr(self, "_read_tip_after", None)
        if aft is not None:
            try:
                self.root.after_cancel(aft)
            except Exception:
                pass
        self._read_tip_after = self.root.after(4000, self._dismiss_read_tip)

    def _dismiss_read_tip(self) -> None:
        tip = getattr(self, "_read_tip", None)
        if tip is not None and tip.winfo_exists():
            tip.destroy()
        self._read_tip = None
        self._read_tip_after = None

    def _on_msg_readers_resp(self, ev) -> None:
        """C9②：MSG_READERS 回帧 → 指针处浮示「已读 N/M」+ 已读成员 + 未读成员(黄标)。"""
        row = getattr(self, "_read_hover_row", None)
        at = getattr(self, "_read_tip_at", None)
        if row is None or at is None:
            return
        total = int(ev.get("total") or 0)
        read_m = ev.get("members") or []
        unread_m = ev.get("unread") or []
        if not read_m and total == 0:
            self._dismiss_read_tip()
            return
        nick = lambda d: "我" if str(d.get("uid")) == str(self.core.uid) \
            else str(d.get("nick") or f"用户{d.get('uid')}")
        read_names = [nick(d) for d in read_m]
        unread_names = [nick(d) for d in unread_m]
        tip = getattr(self, "_read_tip", None)
        if tip is not None and tip.winfo_exists():
            tip.destroy()
        text = f"👀 已读 {len(read_m)}/{total or '?'}"
        if read_names:
            text += "\n已读：" + "、".join(read_names[:8]) + ("…" if len(read_names) > 8 else "")
        if unread_names:
            text += "\n⚠未读：" + "、".join(unread_names[:8]) + ("…" if len(unread_names) > 8 else "")
        tip = tk.Toplevel(self.root)
        tip.overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(tip, text=text, font=(FONT_FAMILY, 9), bg=self._dp["warn_bg"],
                 fg=self._dp["fg"], relief="solid", bd=1, padx=6, pady=3).pack()
        tip.geometry(f"+{at[0] + 12}+{at[1] - 30}")
        _make_draggable(tip)
        self._read_tip = tip
        self._read_hover_row = None
        aft = getattr(self, "_read_tip_after", None)
        if aft is not None:
            try:
                self.root.after_cancel(aft)
            except Exception:
                pass
        self._read_tip_after = self.root.after(4000, self._dismiss_read_tip)

    def _date_jump_dialog(self) -> None:
        """R30A：日期跳转 —— 列出本会话有消息的日期，点选滚到该日第一条。"""
        days = self.msg_list.dates()
        if not days:
            # R61 细节：空会话是临时提示，不该作为系统行写进当前聊天区
            self.show_toast("本会话还没有消息")
            return
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("跳转到日期")
        dlg.transient(self.root)
        self._apply_apple_dialog(dlg, "跳转到日期")
        dlg.resizable(False, False)
        dlg.configure(bg=self._dp["win"])
        lb = tk.Listbox(dlg, height=min(10, len(days)), width=26,
                        font=self._f, exportselection=False)
        lb.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        today = time.strftime("%Y-%m-%d")
        yest = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))

        def _fmt(d: str) -> str:
            if d == today:
                return f"{d}（今天）"
            if d == yest:
                return f"{d}（昨天）"
            return d

        for d in days:
            lb.insert("end", _fmt(d))

        def _go(_e=None) -> None:
            sel = lb.curselection()
            if sel and self.msg_list.jump_to_date(days[sel[0]]):
                dlg.destroy()

        lb.bind("<Double-Button-1>", _go)
        lb.bind("<Return>", _go)
        lb.selection_set(0)
        lb.focus_set()
        bar = tk.Frame(dlg)
        bar.pack(pady=(0, 8))
        tk.Button(bar, text="跳转", command=_go, padx=10).pack(side="left", padx=4)
        tk.Button(bar, text="取消", command=dlg.destroy, padx=10).pack(side="left")

    def _dnd_range_dialog(self) -> None:
        """R30B：免打扰时段设置（支持跨天如 23:00~08:00），写 prefs['dnd_range']。"""
        rng = self._prefs.dnd_range()
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.configure(bg=self._dp["win"])
        dlg.title("免打扰时段")
        dlg.transient(self.root)
        self._apply_apple_dialog(dlg, "免打扰时段")
        dlg.resizable(False, False)
        frm = tk.Frame(dlg, padx=12, pady=10)
        frm.pack()
        on_var = tk.BooleanVar(value=bool(rng.get("on")))
        tk.Checkbutton(frm, text="启用免打扰时段（时段内不闪烁任务栏）",
                       variable=on_var, font=self._f).grid(
            row=0, column=0, columnspan=4, sticky="w")
        tk.Label(frm, text="开始", font=self._f).grid(row=1, column=0, sticky="w")
        e1 = tk.Entry(frm, width=6)
        e1.insert(0, rng.get("start", "23:00"))
        e1.grid(row=1, column=1, padx=4)
        tk.Label(frm, text="结束", font=self._f).grid(row=1, column=2, sticky="w")
        e2 = tk.Entry(frm, width=6)
        e2.insert(0, rng.get("end", "08:00"))
        e2.grid(row=1, column=3, padx=4)
        tk.Label(frm, text="格式 HH:MM；开始>结束 视为跨天（如 23:00~08:00）",
                 fg=self._dp["sub"], font=self._f).grid(row=2, column=0, columnspan=4,
                                               sticky="w", pady=(4, 0))

        def _ok(x: str) -> bool:
            return (len(x) == 5 and x[2] == ":"
                    and x[:2].isdigit() and x[3:].isdigit())

        def _save() -> None:
            s, t = e1.get().strip(), e2.get().strip()
            if not (_ok(s) and _ok(t)):
                self.show_toast("时间格式应为 HH:MM", warn=True)
                return
            self._prefs.set_dnd_range(on_var.get(), s, t)
            self._append_sys("免打扰时段已保存" if on_var.get()
                             else "免打扰时段已停用")
            self._refresh_chan_label()        # 即时刷新标题🔕灰标
            dlg.destroy()

        bar = tk.Frame(dlg)
        bar.pack(pady=(0, 8))
        tk.Button(bar, text="保存", command=_save, padx=10).pack(side="left", padx=4)
        tk.Button(bar, text="取消", command=dlg.destroy, padx=10).pack(side="left")

    def _on_msg_menu(self, ev, idx: int) -> None:
        menu = self._build_msg_menu(idx)
        if menu is None:                       # R32B4：系统行/无菜单 → 壁纸入口兜底
            menu = tk.Menu(self.root, tearoff=0)
        menu.add_separator()
        menu.add_command(label="聊天壁纸…", command=self._wallpaper_picker)
        if not hasattr(self, "_fade_var"):     # R39D②：气泡淡入开关（prefs 持久化）
            self._fade_var = tk.BooleanVar(
                value=bool(self._prefs.get("bubble_fade")))
        menu.add_checkbutton(label="新消息气泡淡入", variable=self._fade_var,
                             command=self._toggle_fade)
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    # ---------- R32B4 聊天壁纸（右键色板 + prefs 持久化） ----------
    WALLPAPERS = (                             # TG 风格柔和色板（名称, 十六进制色）
        ("米色", "#e8dcc8"), ("暖黄", "#f0e0b0"), ("淡绿", "#d6e6d0"),
        ("淡蓝", "#cfe0ef"), ("淡粉", "#efd9e2"), ("淡紫", "#dcd4ec"),
        ("灰蓝", "#d3dde3"), ("奶茶", "#e5d5c0"),
    )

    def _wallpaper_picker(self) -> None:
        """R32B4：色板弹窗——TG 柔和色块网格 + 恢复默认。"""
        sk = self._skin
        win = tk.Toplevel(self.root)
        ui_fx.fade_in(win)                        # R43A1 弹窗淡入
        win.title("聊天壁纸")
        win.transient(self.root)
        win.resizable(False, False)
        win.configure(bg=sk["bg"])
        self._apply_apple_dialog(win, "聊天壁纸")
        tk.Label(win, text="选择聊天背景", bg=sk["bg"], fg=sk["sub"],
                 font=self._f).pack(padx=14, pady=(10, 6))
        grid = tk.Frame(win, bg=sk["bg"])
        grid.pack(padx=14, pady=(0, 8))
        for k, (name, color) in enumerate(self.WALLPAPERS):
            r, c = divmod(k, 4)
            cell = tk.Button(grid, bg=color, width=8, height=2, relief="flat",
                             activebackground=color, cursor="hand2",
                             command=lambda col=color: (win.destroy(),
                                                        self._apply_wallpaper(col)))
            cell.grid(row=r * 2, column=c, padx=4, pady=2)
            tk.Label(grid, text=name, bg=sk["bg"], fg=sk["fg"],
                     font=(self._f[0], 8)).grid(row=r * 2 + 1, column=c,
                                                padx=4, pady=(0, 4))
        tk.Button(win, text="恢复默认", relief="flat", cursor="hand2",
                  bg=sk["input_bg"] if "input_bg" in sk else sk["bg"],
                  fg=sk["fg"], activebackground=sk["accent"],
                  command=lambda: (win.destroy(), self._apply_wallpaper(None))
                  ).pack(fill="x", padx=14, pady=(0, 12))
        win.grab_set()

    def _apply_wallpaper(self, color: str | None) -> None:
        """R32B4：应用/清除壁纸并持久化（空串=默认）。"""
        self.msg_list.set_wallpaper(color)
        self._prefs.set("chat_wallpaper", color or "")
        self._append_sys("聊天壁纸已恢复默认" if not color else "聊天壁纸已更新")

    def _toggle_fade(self) -> None:
        """R39D②：切换新消息 own 气泡淡入并持久化（prefs: bubble_fade）。"""
        on = bool(self._fade_var.get())
        self.msg_list.set_fade_enabled(on)
        self._prefs.set("bubble_fade", on)

    def _on_msg_double(self, idx: int) -> None:
        """B4：双击消息 = 引用回复（填充引用前缀到输入框）"""
        self._quote(idx)

    def _on_bubble_act(self, idx, act: str) -> None:
        """R58C：气泡悬停操作条（回复/复制/删除）——回调直接复用既有动作。"""
        if idx is None:
            return
        if act == "reply":
            self._quote(idx)
        elif act == "copy":
            body = self.msg_list.body_text(idx)
            if body:
                self._copy_text(body)
                self._append_sys("已复制到剪贴板")
        elif act == "delete":
            self._del_msg(idx)

    def _copy_text(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _select_text(self, idx: int) -> None:
        """R12：打开只读文本窗，正文可拖选/Ctrl+C 复制部分内容。"""
        body = self.msg_list.body_text(idx)
        if not body:
            return
        from theme import msg_colors
        colors = msg_colors(self._skin)
        tv = TextViewer(self.root, body, font=self._f,
                        title="选择文本", colors=colors)
        ui_fx.fade_in(tv)                         # R43A1 弹窗淡入

    def _on_row_image(self, idx: int, path: str) -> None:
        """R39D①：点击消息缩略图 → 全屏灯箱（缩放/平移/多图切换；缩略图先行）。"""
        if not os.path.exists(path):
            self._append_sys(f"图片文件不存在：{os.path.basename(path)}")
            return
        paths = [p for _, p in self.msg_list.image_rows()]
        src = paths.index(path) if path in paths else 0
        lb = Lightbox(self.root, paths, index=src, font=self._f,
                      thumb_of=self.msg_list._img_photo.get)
        ui_fx.fade_in(lb)                         # R43A1 灯箱淡入

    def _group_album_dialog(self, gid: int) -> None:
        """R69B5：群图片墙（九宫格相册）——聚合当前会话已加载图片，点击进灯箱。"""
        if self.view != ("group", gid):
            self._append_sys("请先打开该群聊，再查看图片墙（图片墙聚合当前会话已加载图片）")
            return
        existing = getattr(self, "_album_dlg", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()                          # 已开 → 置顶（同一时间只一个）
            return
        paths = [p for _, p in self.msg_list.image_rows()]
        if not paths:
            self.show_toast("本会话暂无图片", warn=True)
            return
        for p in paths:
            self.msg_list._request_img(p)            # 复用缩略图解码线程
        g = self.core.groups.get(gid) or {}
        wall = ImageWall(self.root, paths,
                         thumb_of=self.msg_list._img_photo.get,
                         on_pick=lambda i: self._open_album_image(paths, i),
                         font=self._f, colors=self._dp,
                         title=f"🖼 图片墙 · {g.get('name', gid)}")
        self._album_dlg = wall
        wall.bind("<Destroy>", lambda e: setattr(self, "_album_dlg", None)
                  if e.widget is wall else None, add="+")
        ui_fx.fade_in(wall)                          # R43A1 弹窗淡入

    def _open_album_image(self, paths: list, idx: int) -> None:
        """图片墙点图 → 全屏灯箱（可左右翻页，共用消息缩略图缓存）。"""
        if not (0 <= idx < len(paths)):
            return
        if not os.path.exists(paths[idx]):
            self.show_toast("图片文件不存在", warn=True)
            return
        lb = Lightbox(self.root, paths, index=idx, font=self._f,
                      thumb_of=self.msg_list._img_photo.get)
        ui_fx.fade_in(lb)

    def _group_tasks_dialog(self, gid: int) -> None:
        """R69B6/B7：群任务面板（待办/接龙/签到）——服务端权威，改动走 TASK_* 帧。"""
        existing = getattr(self, "_task_dlg", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            self.core.send_task_list(gid)            # 置顶即刷新
            return
        g = self.core.groups.get(gid)
        if not g:
            return
        panel = TaskPanel(
            self.root, gid, g.get("name", gid), self.core.uid,
            name_of=lambda u: _nick_of(self.core, u),
            on_add=lambda text, mode: self.core.send_task_add(gid, text, mode=mode),
            on_do=lambda tid, on: self.core.send_task_do(gid, tid, on),
            on_del=lambda tid: self.core.send_task_del(gid, tid),
            on_refresh=lambda: self.core.send_task_list(gid),
            font=self._f, colors=self._dp)
        self._task_dlg = panel
        panel.bind("<Destroy>", lambda e: setattr(self, "_task_dlg", None)
                   if e.widget is panel else None, add="+")
        ui_fx.fade_in(panel)                         # R43A1 弹窗淡入
        self.core.send_task_list(gid)                # 首帧清单

    def _on_task_state(self, ev: dict) -> None:
        """群任务清单回帧/广播 → 面板打开则回填；群会话内提示变更。"""
        gid = ev.get("gid")
        panel = getattr(self, "_task_dlg", None)
        if panel is not None and panel.winfo_exists() and panel.gid == gid:
            panel.set_tasks(ev.get("tasks") or [])
        text = ev.get("text") or ""
        if text and self.view == ("group", gid):
            self._append_sys(f"🧾 {text}")

    def _on_msg_link(self, url: str) -> None:
        """R11：点击富文本链接 → 用系统默认浏览器打开（www. 已在 msg_list 补 http://）。"""
        import webbrowser
        try:
            webbrowser.open(url, new=1)
        except Exception:                     # noqa：打开失败不打断聊天
            self._append_sys(f"无法打开链接：{url}")

    def _begin_edit(self, raw: dict) -> None:
        """把待编辑消息载入输入框，记录 seq（C3：发送时发 edit 而非新消息）。"""
        self._pending_edit_seq = raw.get("seq")
        self._drop_reply_state()                 # 进入编辑丢弃引用态（防泄漏）
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", raw.get("text", ""))
        self.entry.focus_set()
        self._append_sys("✎ 正在编辑该条，Enter 确认，Ctrl+E 取消")

    def _edit_msg(self, idx: int) -> None:
        raw = self.msg_list.get_row(idx)
        if not raw:
            return
        self._begin_edit(raw)

    def _del_msg(self, idx: int, scope: str = "self") -> None:
        """撤回消息（C3/R51）：scope=self 仅本人；scope=both 私聊双方可删对方消息。"""
        raw = self.msg_list.get_row(idx)
        if not raw or raw.get("seq") is None:
            self._append_sys("该消息不支持撤回（无服务器序号）")
            return
        if self._pending_edit_seq == raw.get("seq"):
            self._pending_edit_seq = None
            self._drop_reply_state()             # 撤回目标在编辑中 → 同步清引用
            self.entry.delete("1.0", "end")
        self.core.send_del(raw["seq"], scope=scope)

    def _quote(self, idx: int) -> None:
        """C4 引用回复：记录快照 + 输入框顶部插入引用标记行。"""
        if self._pending_edit_seq is not None:
            # R41F：编辑中引用会污染编辑框（发送时虽被剥离，状态也已被编辑分支清理），
            # 直接提示，闭环交互
            self._append_sys("✎ 编辑中：先发送或 Ctrl+E 取消编辑，再引用")
            return
        raw = self.msg_list.get_row(idx)
        if not raw:
            return
        nick = raw.get("nick", "?")
        body = self.msg_list.body_text(idx)
        first = self.entry.get("1.0", "1.end")
        if first.startswith("↩ "):
            # R41F：连续引用 → 移除旧引用标记行，避免输入框残留两行 ↩
            self.entry.delete("1.0", "2.0")
        self._pending_reply = {"nick": nick, "text": raw.get("text", ""),
                               "seq": raw.get("seq")}
        self.entry.insert("1.0", f"↩ {nick}: {body}\n")
        self.entry.mark_set("insert", "end")     # 光标落在引用块之后
        self.entry.focus_set()
        self._append_sys(f"↩ 正在引用 {nick} 的消息")

    def _on_jump_reply(self, seq) -> None:
        """R41F：点气泡内引用前缀 → 定位原消息并高亮；不可达时提示。"""
        if not self.msg_list.jump_to_seq(seq):
            self._append_sys("原消息不在当前视图（可能已撤回或超出加载范围）")

    # ---------- 会话右键菜单（B3 + C5/C6：置顶 / 标记已读 / 删除记录） ----------
    def _build_roster_menu(self, uid: int) -> tk.Menu | None:
        u = self.core.roster.get(uid) or self.core.known.get(uid)   # R25B：离线也可见
        if u is None:
            return None
        if u.get("type") == "bot":          # R46：机器人不可屏蔽
            bot_blocked = True
            blocked_now = False
        else:
            bot_blocked = False
            blocked_now = uid in self.core.blocked   # R50
        u = None if bot_blocked else u
        key = self._pin_key("private", uid)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="取消置顶" if self._prefs.is_pinned(key) else "置顶",
                         command=lambda: (self._toggle_pin_conv(key), self._refresh_roster()))
        menu.add_command(label="⭐ 取消星标" if self._prefs.is_starred(key) else "⭐ 置星",
                         command=lambda: (self._toggle_star_conv(key), self._refresh_roster()))
        if uid != self.core.uid:                 # R69C10：查看他人资料卡
            menu.add_command(label="👤 查看资料",
                             command=lambda: self._open_user_card(uid))
        if not bot_blocked and uid != self.core.uid:
            # R69C9：好友备注名（本人视角，服务器持久；置空即清除）
            has_rem = bool(str((u or {}).get("remark") or ""))
            menu.add_command(label="✏ 修改备注名" if has_rem else "✏ 设置备注名",
                             command=lambda: self._set_remark_dialog(uid))
        menu.add_command(label="取消静音" if self._prefs.is_muted(key) else "静音",
                         command=lambda: (self._toggle_mute_conv(key), self._refresh_roster()))
        menu.add_command(label="取消归档" if self._prefs.is_archived(key) else "归档",
                         command=lambda: (self._toggle_archive_conv(key),
                                          self._refresh_lists()))
        if self._unread.get(("private", uid), 0) > 0:
            menu.add_command(label="标记已读",
                             command=lambda: (self._clear_unread("private", uid),
                                              self._refresh_roster()))
        menu.add_command(                        # R69C11：本地「标为未读」标记
            label="取消未读标记" if self._prefs.is_unread_mark(key) else "标为未读",
            command=lambda: self._toggle_unread_mark("private", uid))
        self._folder_menu_items(menu, key)        # R25D：加入/移出文件夹
        menu.add_command(
            label="解除屏蔽" if blocked_now else "屏蔽此人",   # R50：服务器权威拦截
            command=lambda: self._toggle_block(uid))
        menu.add_separator()
        if self.core.is_admin:                       # R53：管理员清理权限（仅管理员可见）
            online = uid in self.core.roster
            menu.add_command(label="🔨 踢下线" if online else "踢下线（该用户离线）",
                             command=lambda: self._admin_kick(uid),
                             state="normal" if online else "disabled")
            menu.add_command(label="🧹 清空该用户全部消息",
                             command=lambda: self._admin_clear_uid(uid))
            menu.add_separator()
        menu.add_command(label="删除会话记录",
                         command=lambda: self._drop_session("private", uid))
        return menu

    def _admin_kick(self, uid: int) -> None:
        """R53 管理员：踢指定用户下线（目标端收到 error/kicked 并断线）。"""
        u = self.core.roster.get(uid) or self.core.known.get(uid) or {}
        nick = u.get("nick", f"用户{uid}")
        from widgets import dialogbox
        if not dialogbox.ask_yesno("管理员操作",
                                   f"确认将用户 {nick} 强制下线？", parent=self.root):
            return
        self.core.send_admin_kick(uid)
        self._append_sys(f"🔨 已向服务器提交：将 {nick} 强制下线")

    def _admin_clear_uid(self, uid: int) -> None:
        """R53 管理员：清空指定用户全部消息（跨全部频道，全员本地历史同步）。"""
        u = self.core.roster.get(uid) or self.core.known.get(uid) or {}
        nick = u.get("nick", f"用户{uid}")
        from widgets import dialogbox
        if not dialogbox.ask_yesno("管理员操作",
                                   f"确认清空用户 {nick} 的全部消息？"
                                   "\n（全员本地历史将同步删除，不可恢复）",
                                   parent=self.root):
            return
        self.core.send_admin_clear_uid(uid)
        self._append_sys(f"🧹 已向服务器提交：清空用户 {uid} 的全部消息")

    # ---------- 群文件库（服务端权威，独立于 1v1 文件传输） ----------
    def _group_files_dialog(self, gid: int) -> None:
        """打开/置顶群文件库窗口：列表 + 上传/下载/删除/刷新。"""
        existing = getattr(self, "_gf_dlg", None)
        if existing and existing.get("gid") == gid and existing["dlg"].winfo_exists():
            existing["dlg"].lift()
            self.core.send_group_file_list(gid)   # 置顶即刷新
            return
        if existing and existing["dlg"].winfo_exists():
            try:
                existing["dlg"].destroy()          # 同一时间只维护一个库窗
            except Exception:
                pass
        g = self.core.groups.get(gid) or {}
        sk = self._skin
        dp = self._dp
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                          # R43A1 弹窗淡入
        dlg.title(f"群文件 · {g.get('name', gid)}")
        dlg.transient(self.root)
        dlg.configure(bg=dp["win"])
        dlg.geometry("460x360")
        dlg.protocol("WM_DELETE_WINDOW", lambda: (dlg.destroy(),
                                                 setattr(self, "_gf_dlg", None)))
        self._apply_apple_dialog(dlg, "群文件库")
        f = self._f
        tk.Label(dlg, text=f"群文件库 · {g.get('name', gid)}",
                 fg=dp["fg"], font=f, anchor="w", bg=dp["win"]).pack(
            fill="x", padx=10, pady=6)
        me = self.core.uid
        role = self.group_role(gid, me)
        sub = dp["sub"]
        tk.Label(dlg, text=f"权限：{'👑群主' if role == 'owner' else ('🛡管理' if role == 'admin' else '成员')}"
                           "  ·  删除需上传者或群主/管理",
                 fg=sub, font=(FONT_FAMILY, 8), anchor="w",
                 bg=dp["win"]).pack(fill="x", padx=10)

        # R69B8：搜索框 + 按类型（全部/图片/文档/压缩包）过滤
        flt = tk.Frame(dlg, bg=dp["win"])
        flt.pack(fill="x", padx=10, pady=(2, 0))
        tk.Label(flt, text="🔍", fg=sub, bg=dp["win"], font=f).pack(side="left")
        qv = tk.StringVar(value="")
        ent = tk.Entry(flt, textvariable=qv, font=(FONT_FAMILY, 9))
        ent.pack(side="left", fill="x", expand=True, padx=4)
        kind_btns = {}

        def _refilter():
            st = getattr(self, "_gf_dlg", None)
            if st is None:
                return
            st["records"] = self._gf_fill(lb, st.get("raw") or [])

        def _set_kind(k):
            st = getattr(self, "_gf_dlg", None)
            if st is not None:
                st["kind"] = k
            for kk, b in kind_btns.items():
                b.config(relief="sunken" if kk == k else "flat")
            _refilter()

        for k, lbl in GF_KIND_LABELS:
            b = tk.Button(flt, text=lbl, font=(FONT_FAMILY, 8),
                          relief="sunken" if k == "all" else "flat",
                          bg=dp["tab_bg"], fg=dp["fg"], padx=6,
                          command=lambda kk=k: _set_kind(kk))
            b.pack(side="left", padx=2)
            kind_btns[k] = b
        def _on_q(*_a):
            st = getattr(self, "_gf_dlg", None)
            if st is not None:
                st["q"] = qv.get()
            _refilter()

        qv.trace_add("write", _on_q)                     # 逐字实时过滤

        box = tk.Frame(dlg, bg=dp["win"])
        box.pack(fill="both", expand=True, padx=10, pady=4)
        sb = tk.Scrollbar(box)
        sb.pack(side="right", fill="y")
        lb = tk.Listbox(box, yscrollcommand=sb.set, activestyle="none",
                        bg=dp["bg"], fg=dp["fg"],
                        selectbackground=dp.get("tab_on_bg", "#cfe8ff"),
                        highlightthickness=0, font=(FONT_FAMILY, 9))
        lb.pack(side="left", fill="both", expand=True)
        sb.config(command=lb.yview)

        bar = tk.Frame(dlg, bg=dp["win"])
        bar.pack(fill="x", padx=10, pady=(0, 8))

        def _btn(text, cmd):
            tk.Button(bar, text=text, font=(FONT_FAMILY, 9), relief="flat",
                      bg=dp["tab_bg"], fg=dp["fg"], padx=8,
                      command=cmd).pack(side="left", padx=3)

        self._gf_dlg = {"gid": gid, "dlg": dlg, "lb": lb, "records": [],
                        "raw": [], "q": "", "kind": "all"}   # R69B8：过滤态

        def _render(records):
            self._gf_dlg["raw"] = records
            self._gf_dlg["records"] = self._gf_fill(lb, records)

        def _refresh():
            self.core.send_group_file_list(gid)

        def _sel():
            i = lb.curselection()
            if not i:
                return None
            recs = self._gf_dlg.get("records") or []
            return recs[i[0]] if 0 <= i[0] < len(recs) else None

        def _upload():
            path = filedialog.askopenfilename(
                title="选择要上传到群文件的文件", parent=dlg)
            if not path:
                return
            name = os.path.basename(path)
            try:
                size = os.path.getsize(path)
            except OSError as exc:
                self.show_toast(f"读取失败：{exc}", warn=True); return
            if size <= 0:
                self.show_toast("文件为空", warn=True); return
            if size > getattr(CFG, "group_file_max_bytes", 32 * 1024 * 1024):
                self.show_toast("文件超过 32MB 上限", warn=True); return
            self._gf_upload["gid"] = gid
            self._gf_upload["path"] = path
            self._gf_upload["size"] = size
            self._gf_upload["fh"] = None
            self._gf_upload["off"] = 0
            self._gf_upload["fid"] = None
            self.core.send_group_file_upload_start(gid, name, size)
            self.show_toast(f"正在上传「{name}」…")

        def _download():
            r = _sel()
            if not r:
                self.show_toast("请先选择要下载的文件", warn=True); return
            dstdir = CFG.downloads_dir
            try:
                os.makedirs(dstdir, exist_ok=True)
            except OSError:
                dstdir = os.path.expanduser("~")
            dest = os.path.join(dstdir, self._gf_safe_name(r.get("name") or r["fid"]))
            try:
                fh = open(dest, "wb")
            except OSError as exc:
                self.show_toast(f"无法保存：{exc}", warn=True); return
            self._gf_download[r["fid"]] = {"fh": fh, "size": r.get("size") or 0,
                                           "written": 0, "path": dest}
            self.core.send_group_file_get(gid, r["fid"])
            self.show_toast(f"正在下载「{r.get('name')}」…")

        def _delete():
            r = _sel()
            if not r:
                self.show_toast("请先选择要删除的文件", warn=True); return
            from widgets import dialogbox
            if not dialogbox.ask_yesno(
                    "删除群文件", f"确定删除群文件「{r.get('name')}」？",
                    parent=dlg):
                return
            self.core.send_group_file_del(gid, r["fid"])

        _btn("上传", _upload); _btn("下载", _download)
        _btn("删除", _delete); _btn("刷新", _refresh)
        _refresh()

    def _gf_fill(self, lb, records: list) -> list:
        """R69B8：按当前搜索词/类型过滤后填充列表；返回过滤结果（与选中下标对齐）。"""
        st = getattr(self, "_gf_dlg", None) or {}
        q = str(st.get("q") or "").strip().lower()
        kind = st.get("kind") or "all"
        out = []
        for r in records:
            name = str(r.get("name") or "")
            if kind != "all" and gf_kind(name) != kind:
                continue
            if q and q not in name.lower() and \
                    q not in str(r.get("nick") or "").lower():
                continue
            out.append(r)
        dp = self._dp
        lb.delete(0, "end")
        for r in out:
            try:
                t = time.strftime("%m-%d %H:%M", time.localtime(r.get("ts") or 0))
            except Exception:
                t = "-"
            size = self._gf_humansize(r.get("size") or 0)
            upd = r.get("nick") or f"用户{r.get('uid')}"
            lb.insert("end", f"{r.get('name')}    {size}   {upd}   {t}")
            lb.itemconfig("end", fg=dp["fg"])
        return out

    @staticmethod
    def _gf_humansize(n: int) -> str:
        n = int(n or 0)
        if n < 1024:
            return f"{n}B"
        if n < 1024 * 1024:
            return f"{n / 1024:.1f}KB"
        return f"{n / 1024 / 1024:.1f}MB"

    @staticmethod
    def _gf_safe_name(name: str) -> str:
        name = str(name or "file").strip()
        for ch in ('/', "\\", ":", "*", "?", '"', "<", ">", "|", "\u0000"):
            name = name.replace(ch, "_")
        return name[:120] or "file"

    def _on_group_file_list(self, ev: dict) -> None:
        """群文件列表回帧 → 填充库窗口（若打开）。"""
        gid = ev.get("gid")
        dlg = getattr(self, "_gf_dlg", None)
        if not dlg or dlg.get("gid") != gid or not dlg["dlg"].winfo_exists():
            return                                 # 窗口已关 → 忽略（下次打开再拉）
        records = ev.get("records") or []
        lb = dlg["lb"]
        dlg["raw"] = records                      # R69B8：原始列表（供搜索/过滤重算）
        dlg["records"] = self._gf_fill(lb, records)

    def _on_group_file_upload_info(self, ev: dict) -> None:
        """服务器分配 fid → 逐块上传（after 泵送保持 UI 响应）。"""
        gid = ev.get("gid")
        fid = str(ev.get("fid") or "")
        data = self._gf_upload
        if not gid or not fid or data.get("gid") != gid:
            self.show_toast("上传会话失效，请重试", warn=True)
            return
        data["fid"] = fid
        try:
            data["fh"] = open(data["path"], "rb")
        except OSError as exc:
            self.show_toast(f"读取失败：{exc}", warn=True); return
        data["off"] = 0

        def _step():
            fh = data.get("fh")
            if fh is None:
                return
            try:
                block = fh.read(CFG.chunk_size)
            except OSError:
                self.show_toast("读取失败", warn=True); self._gf_upload_cleanup(); return
            if not block:
                self.core.send_group_file_upload_done(gid, fid, data.get("off", 0))
                self._gf_upload_cleanup()
                self.show_toast("上传完成")
                return
            self.core.send_group_file_upload(gid, fid, data.get("off", 0), block)
            data["off"] = data.get("off", 0) + len(block)
            self.root.after(0, _step)
        _step()

    def _gf_upload_cleanup(self) -> None:
        d = self._gf_upload
        if d.get("fh") is not None:
            try:
                d["fh"].close()
            except Exception:
                pass
        self._gf_upload = {}

    def _on_group_file_data(self, ev: dict) -> None:
        """下载数据块 → 追加写盘；more=0 收尾。"""
        fid = str(ev.get("fid") or "")
        st = self._gf_download.get(fid)
        if not st:
            return                                 # 没有发起下载 → 忽略（防御）
        body = ev.get("data") or b""
        if body:
            try:
                st["fh"].write(body)
            except OSError as exc:
                self.show_toast(f"保存失败:{exc}", warn=True)
                self._gf_download_finish(fid, delete=True)
                return
            st["written"] += len(body)
        if not (ev.get("more")):
            self._gf_download_finish(fid)

    def _gf_download_finish(self, fid: str, delete: bool = False) -> None:
        st = self._gf_download.pop(fid, None)
        if not st:
            return
        try:
            st["fh"].close()
        except Exception:
            pass
        if delete:
            try:
                os.remove(st["path"])
            except OSError:
                pass
            self.show_toast("下载失败", warn=True)
        else:
            self.show_toast(f"已下载到 {st['path']}")

    def _on_group_file_notify(self, ev: dict) -> None:
        """群内文件增删广播 → 若库窗开着则自动刷新列表。"""
        gid = ev.get("gid")
        dlg = getattr(self, "_gf_dlg", None)
        if dlg and dlg.get("gid") == gid and dlg["dlg"].winfo_exists():
            self.core.send_group_file_list(gid)

    def _build_group_menu(self, gid: int) -> tk.Menu | None:
        if gid not in self.core.groups:
            return None
        key = self._pin_key("group", gid)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="取消置顶" if self._prefs.is_pinned(key) else "置顶",
                         command=lambda: (self._toggle_pin_conv(key), self._refresh_groups()))
        menu.add_command(label="⭐ 取消星标" if self._prefs.is_starred(key) else "⭐ 置星",
                         command=lambda: (self._toggle_star_conv(key), self._refresh_groups()))
        menu.add_command(label="取消静音" if self._prefs.is_muted(key) else "静音",
                         command=lambda: (self._toggle_mute_conv(key), self._refresh_groups()))
        menu.add_command(label="取消归档" if self._prefs.is_archived(key) else "归档",
                         command=lambda: (self._toggle_archive_conv(key),
                                          self._refresh_lists()))
        if self._unread.get(("group", gid), 0) > 0:
            menu.add_command(label="标记已读",
                             command=lambda: (self._clear_unread("group", gid),
                                              self._refresh_groups()))
        menu.add_command(                        # R69C11：本地「标为未读」标记
            label="取消未读标记" if self._prefs.is_unread_mark(key) else "标为未读",
            command=lambda: self._toggle_unread_mark("group", gid))
        menu.add_command(label="群成员管理",
                         command=lambda: self._group_members_dialog(gid))
        menu.add_command(label="📁 群文件",
                         command=lambda: self._group_files_dialog(gid))
        menu.add_command(label="🖼 图片墙",        # R69B5：会话图片墙（聚合已加载图片）
                         command=lambda: self._group_album_dialog(gid))
        menu.add_command(label="🧾 群任务",        # R69B6/B7：待办/接龙/签到
                         command=lambda: self._group_tasks_dialog(gid))
        me = self.core.uid
        if self.group_role(gid, me) in ("owner", "admin"):
            menu.add_command(label="复制邀请码",        # R28：单播回码→复制提示
                             command=lambda: self.core.get_group_invite(gid))
            menu.add_command(label="重命名群",
                             command=lambda: self._rename_group_dialog(gid))
            has = bool(self.core.group_announces.get(gid))
            menu.add_command(
                label="清除群公告" if has else "发布群公告",
                command=lambda: self._set_group_announce_dialog(gid))
            # C9①「仅公告说话模式」开关（owner/admin）
            ann_mode = bool((self.core.groups.get(gid) or {}).get("announce_mode"))
            menu.add_command(
                label="关闭「仅公告说话」模式" if ann_mode else "开启「仅公告说话」模式",
                command=lambda: self.core.send_group_ann_mode(gid, not ann_mode))
            # R70D 群慢速模式（owner/admin）：档位下拉，0=关闭
            slow_cur = int((self.core.groups.get(gid) or {}).get("slow") or 0)
            slow_menu = tk.Menu(menu, tearoff=0)
            for sec in CFG.group_slow_options:
                label = ("关闭" if not sec else
                         (f"{sec // 60} 分钟" if sec >= 60 else f"{sec} 秒"))
                slow_menu.add_command(
                    label=("● " if sec == slow_cur else "○ ") + label,
                    command=lambda s=sec: self.core.send_group_slow(gid, s))
            menu.add_cascade(label=("群慢速：关闭" if not slow_cur else
                                    f"群慢速：{slow_cur} 秒"), menu=slow_menu)
            menu.add_separator()                    # R9H：群资料
            menu.add_command(label="编辑群简介",
                             command=lambda: self._set_group_about_dialog(gid))
            has_av = bool((self.core.groups.get(gid) or {}).get("avatar"))
            menu.add_command(label="设置/更换群头像",
                             command=lambda: self._set_group_avatar_dialog(gid))
            if has_av:
                menu.add_command(label="清除群头像",
                                 command=lambda: self._clear_group_avatar(gid))
        self._folder_menu_items(menu, key)        # R25D：加入/移出文件夹
        menu.add_command(label="删除会话记录",
                         command=lambda: self._drop_session("group", gid))
        return menu

    def _on_roster_menu(self, ev) -> None:
        sel = self.roster_list.nearest(ev.y)
        uid = self._roster_order[sel] if 0 <= sel < len(self._roster_order) else None
        if uid is None:
            return
        menu = self._build_roster_menu(uid)
        if menu is None:
            return
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def _on_group_menu(self, ev) -> None:
        sel = self.group_list.nearest(ev.y)
        gid = self._group_order[sel] if 0 <= sel < len(self._group_order) else None
        if gid is None:
            return
        menu = self._build_group_menu(gid)
        if menu is None:
            return
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def _set_remark_dialog(self, uid: int) -> None:
        """R69C9：设置/清除好友备注名（本人视角；留空即清除，≤24 字）。"""
        u = self.core.roster.get(uid) or self.core.known.get(uid) or {}
        cur = str(u.get("remark") or "")
        from widgets import dialogbox
        val = dialogbox.ask_string(
            "好友备注名",
            f"给 {u.get('nick') or ('用户%d' % uid)} 设置备注名（留空=清除，≤24 字）：",
            parent=self.root, initialvalue=cur)
        if val is None:
            return
        self.core.send_remark(uid, str(val).strip()[:24])

    # ---------- R69C10 用户资料卡（点消息头像 / 右键「查看资料」） ----------
    def _common_groups(self, uid: int) -> list:
        """R69C10：我与 uid 的共同群（按群名排序；仅统计已同步成员表的群）。"""
        out = []
        for gid, members in self.core.group_members.items():
            try:
                hit = any(int(m.get("uid")) == uid for m in members)
            except (TypeError, ValueError, AttributeError):
                continue
            if hit:
                g = self.core.groups.get(gid) or {}
                out.append((str(g.get("name") or gid), gid))
        out.sort()
        return out

    def _open_user_card(self, uid) -> None:
        """R69C10 用户资料卡：头像 / 昵称(备注优先) / 状态 / 签名 / 共同群 / 发消息。

        只读卡片：自己 → 直接转个人资料窗口；bot → 不显示发消息。
        """
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            return
        if self.core is None or uid == self.core.uid:
            self._on_profile()
            return
        u = self.core.roster.get(uid) or self.core.known.get(uid)
        if u is None:
            self._append_sys("该用户资料不可用")
            return
        win = getattr(self, "_ucard_win", None)
        if win is not None and win.winfo_exists():
            win.destroy()
        dlg = tk.Toplevel(self.root)
        self._ucard_win = dlg
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("用户资料")
        dlg.transient(self.root)
        dlg.attributes("-topmost", True)
        dlg.resizable(False, False)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "用户资料")
        sk = self._skin
        f = self._f
        is_bot = str(u.get("type") or "") == "bot"

        # 大头像（96px 圆形，无点击交互）
        av = tk.Canvas(dlg, width=104, height=104, bg=sk["panel_bg"],
                       highlightthickness=0)
        av.pack(pady=(12, 4))
        self._avatars.draw(av, 4, 4, 96, str(u.get("nick") or ""), uid=uid,
                           font=(FONT_FAMILY, 26, "bold"))

        name = self.core.display_name(uid)
        tk.Label(dlg, text=("🤖 " if is_bot else "") + name, fg=sk["fg"],
                 bg=sk["panel_bg"], font=(FONT_FAMILY, 12, "bold")
                 ).pack(padx=18, anchor="w")
        nick = str(u.get("nick") or "")
        if nick and nick != name:                 # 有备注 → 附注真实昵称
            tk.Label(dlg, text=f"昵称：{nick}", fg=sk["sub"], bg=sk["panel_bg"],
                     font=(FONT_FAMILY, 9)).pack(padx=18, anchor="w")

        # 在线状态（未出现在 roster 即离线，可能带最后在线）
        online = uid in self.core.roster
        st = str(u.get("status") or ("online" if online else "offline"))
        st_text = {"online": "在线", "away": "离开", "busy": "忙碌",
                   "offline": "离线"}.get(st, st)
        srow = tk.Frame(dlg, bg=sk["panel_bg"])
        srow.pack(fill="x", padx=18, pady=(6, 0))
        tk.Label(srow, text="●", fg=self._status_color(st), bg=sk["panel_bg"],
                 font=(FONT_FAMILY, 11)).pack(side="left")
        extra = ""
        if not online and u.get("last_online"):
            extra = "（" + self._last_online_text(u["last_online"]) + "）"
        tk.Label(srow, text=st_text + extra, fg=sk["sub"], bg=sk["panel_bg"],
                 font=f).pack(side="left", padx=4)

        # 个性签名
        tk.Label(dlg, text="个性签名", fg=sk["sub"], bg=sk["panel_bg"],
                 font=(FONT_FAMILY, 9)).pack(padx=18, anchor="w", pady=(8, 0))
        tk.Label(dlg, text=(str(u.get("sign") or "").strip() or "（未设置）"),
                 fg=sk["fg"], bg=sk["panel_bg"], font=f, wraplength=240,
                 justify="left").pack(padx=18, anchor="w")

        # 共同群（最多列 8 个）
        cgs = self._common_groups(uid)
        tk.Label(dlg, text=f"共同群（{len(cgs)}）", fg=sk["sub"],
                 bg=sk["panel_bg"], font=(FONT_FAMILY, 9)
                 ).pack(padx=18, anchor="w", pady=(8, 0))
        if cgs:
            for gname, gid in cgs[:8]:
                tk.Label(dlg, text="· " + gname, fg=sk["fg"], bg=sk["panel_bg"],
                         font=f, anchor="w",
                         cursor="hand2").pack(padx=22, anchor="w")
            if len(cgs) > 8:
                tk.Label(dlg, text=f"…等 {len(cgs)} 个群", fg=sk["sub"],
                         bg=sk["panel_bg"], font=(FONT_FAMILY, 9)
                         ).pack(padx=22, anchor="w")
        else:
            tk.Label(dlg, text="（暂无共同群）", fg=sk["sub"], bg=sk["panel_bg"],
                     font=(FONT_FAMILY, 9)).pack(padx=22, anchor="w")

        def _dm() -> None:
            dlg.destroy()
            self._switch_view(("private", uid))

        brow = tk.Frame(dlg, bg=sk["panel_bg"])
        brow.pack(fill="x", padx=18, pady=(12, 12))
        if not is_bot:
            tk.Button(brow, text="发消息", font=f, command=_dm).pack(
                side="left", fill="x", expand=True)
            tk.Button(brow, text="备注名…", font=f,
                      command=lambda: self._set_remark_dialog(uid)).pack(
                side="left", fill="x", expand=True, padx=(6, 0))
        tk.Button(brow, text="关闭", font=f, command=dlg.destroy).pack(
            side="left", fill="x", expand=True, padx=(6, 0))

    def _toggle_block(self, uid: int) -> None:
        """R50：屏蔽/解除当前用户（服务器权威拦截其私聊、密聊、语音）。"""
        on = uid not in self.core.blocked
        self.core.set_block(uid, on)
        self._refresh_roster()
        if uid == (self.view[1] if self.view[0] == "private" else None) and on:
            self._switch_view(("public", 0))   # 正在看被屏蔽者的私聊 → 退回公共频道
        self._append_sys("已屏蔽该用户，其私聊/密聊/通话将不再送达"
                         if on else "已解除对该用户的屏蔽")

    def _drop_session(self, ch: str, to) -> None:
        self.core.drop_history(ch, to)
        if self.view == (ch, to):
            self._load_view_history()          # 当前会话立即清空
        self._append_sys("已删除该会话本地记录")

    def _shortcut_settings(self) -> None:
        """r5b：快捷键设置页——查看当前绑定、逐项改绑、一键恢复默认。"""
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("快捷键设置")
        dlg.geometry("360x400")
        dlg.attributes("-topmost", True)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "快捷键设置")
        f = self._f
        tk.Label(dlg, text="单击「改绑」后按下新组合键（Esc 取消）",
                 fg=self._dp["sub"], font=f, anchor="w").pack(fill="x", padx=10,
                                                              pady=(6, 2))

        canvas = tk.Canvas(dlg, highlightthickness=0)
        inner = tk.Frame(canvas)
        vsb = tk.Scrollbar(dlg, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        def _reload() -> None:
            for w in inner.winfo_children():
                w.destroy()
            cur = self._prefs.get("hotkeys", {}) or {}
            for sc in SHORTCUTS:
                pat = cur.get(sc["id"], sc["default"])
                row = tk.Frame(inner)
                row.pack(fill="x", padx=8, pady=2)
                tk.Label(row, text=sc["desc"], font=f, fg=self._dp["fg"], width=16,
                         anchor="w").pack(side="left")
                tk.Label(row, text=_pattern_label(pat), font=f, fg=self._dp["self"],
                         width=14, anchor="w").pack(side="left")
                tk.Button(row, text="改绑", font=f, relief="flat",
                          command=lambda i=sc["id"]: _bind(i)).pack(side="left", padx=2)
                tk.Button(row, text="恢复", font=f, relief="flat",
                          command=lambda i=sc["id"]: _reset(i)).pack(side="left")

        def _apply(id_, pat) -> None:
            prefs = self._prefs.get("hotkeys", {}) or {}
            if pat:
                prefs[id_] = pat
            else:
                prefs.pop(id_, None)
            self._prefs.set("hotkeys", prefs)
            self._bind_shortcuts()                 # 立即生效
            _reload()

        def _reset(id_) -> None:
            _apply(id_, "")

        def _bind(id_) -> None:
            cap = tk.Toplevel(dlg)
            cap.title("绑定快捷键")
            cap.geometry("300x120")
            cap.attributes("-topmost", True)
            cap.configure(bg=self._dp["win"])
            tk.Label(cap, text="按下新组合键…（Esc 取消）",
                     font=f, fg=self._dp["fg"]).pack(expand=True)
            cap.focus_force()

            def _capture(ev) -> str:
                if ev.keysym == "Escape":
                    cap.destroy()
                    return "break"
                pat = _event_to_pattern(ev)
                if not pat:
                    return "break"
                cap.destroy()
                _apply(id_, pat)
                return "break"

            cap.bind("<KeyPress>", _capture)

        bar = tk.Frame(dlg)
        bar.pack(fill="x", pady=4)
        tk.Button(bar, text="恢复全部默认", font=f,
                  command=lambda: (self._prefs.set("hotkeys", {}),
                                   self._bind_shortcuts(), _reload())
                  ).pack(side="left", padx=10)
        tk.Button(bar, text="关闭", font=f, command=dlg.destroy).pack(side="right", padx=10)
        _reload()

    def _close_settings(self) -> None:
        """R交互：关闭内嵌全屏设置面板（隐藏保留，可再次打开）。"""
        self._select_navigation('chat')
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.place_forget()

    def _apply_mode_skin(self) -> None:
        """R交互：应用当前交互模式绑定的专属皮肤（复用现有换肤链路）。"""
        if self._mode_cfg.get("skin"):
            self._on_skin_change(self._mode_cfg["skin"])

    def _set_mode(self, mode: str) -> None:
        """R交互：切换交互模式（写 prefs 并应用其专属皮肤；其余三件套重启后生效）。"""
        if mode not in MODE_CONFIG:
            return
        self._prefs.set("interaction_mode", mode)
        self._mode = mode
        self._mode_cfg = MODE_CONFIG[mode]
        self._apply_mode_skin()

    def _bind_send_key(self, entry) -> None:
        """R交互：按交互模式绑定发送键（TG/微信 Enter 发送；QQ Ctrl+Enter 发送）。"""
        if self._mode_cfg["send"] == "ctrl_enter":   # QQ 桌面：Enter 换行、Ctrl+Enter 发送
            entry.bind("<Return>", self._on_entry_newline)        # 复用现有换行 handler
            entry.bind("<Control-Return>", self._on_entry_return)  # 复用现有发送 handler
        else:                                        # TG/微信：Enter 发送、Shift+Enter 换行
            entry.bind("<Return>", self._on_entry_return)
            entry.bind("<Shift-Return>", self._on_entry_newline)

    def _on_skin_change(self, name: str) -> None:
        """T3：设置页切换皮肤的选项变化 → 应用并持久化。"""
        if name not in skin_names():
            return
        self._skin_name = name
        self._apply_skin()

    # ---------- R41D 深色模式跟随系统 ----------
    def _resolve_system_skin(self) -> str:
        """系统深浅 → 对应皮肤名（None/浅色 → 浅色 Apple）。"""
        from theme import SYSTEM_DARK_SKIN, SYSTEM_LIGHT_SKIN, system_prefers_dark
        return SYSTEM_DARK_SKIN if system_prefers_dark() else SYSTEM_LIGHT_SKIN

    def _poll_sys_theme(self) -> None:
        """每 2s 探测系统深浅；「跟随系统」开启且变化时自动换肤。

        轮询注册表成本极低；拆出独立方法便于测试（不真的 after 循环）。
        """
        try:
            if self._prefs.get("skin_follow_system"):
                want = self._resolve_system_skin()
                if want != self._skin_name:
                    self._on_skin_change(want)
        except Exception:
            pass                           # 探测失败不搅扰主循环
        try:
            self._sys_theme_after = self.root.after(2000, self._poll_sys_theme)
        except tk.TclError:
            pass                           # 窗口已销毁，停止轮询

    def _set_default_colors(self) -> None:
        """R57B：把 Tk 控件类默认底色/文字接到当前皮肤（option_add）。

        Tk 里 Frame/Button/Checkbutton/Entry 等若未显式指定 bg，会用系统浅色
        而非继承父级——这正是"设置等弹窗内部控件仍是浅色/白"的根因。这里通过
        option 数据库给「未指定颜色的控件」一个跟随皮肤的默认值；构造时显式
        传了 bg 的控件优先级更高、不受影响。皮肤切换时重调即可全局刷新。
        """
        r = getattr(self, "root", None)
        if r is None:
            return                      # root 尚未创建：默认颜色延后到 root 就绪后接入
        dp = self._dp
        win, fg, sub = dp["win"], dp["fg"], dp["sub"]
        acc, border, inp = dp["accent"], dp["border"], dp["input"]

        def opt(name, v):
            try:
                r.option_add(name, v)
            except tk.TclError:
                pass

        opt("*Frame.background", win)
        opt("*Frame.foreground", fg)
        opt("*Label.background", win)
        opt("*Label.foreground", fg)
        opt("*Button.background", win)
        opt("*Button.foreground", fg)
        opt("*Button.activebackground", border)
        opt("*Button.activeforeground", fg)
        opt("*Checkbutton.background", win)
        opt("*Checkbutton.foreground", fg)
        opt("*Checkbutton.activebackground", win)
        opt("*Radiobutton.background", win)
        opt("*Radiobutton.foreground", fg)
        opt("*Menubutton.background", win)
        opt("*Menubutton.foreground", fg)
        opt("*OptionMenu.background", win)
        opt("*OptionMenu.foreground", fg)
        opt("*Menu.background", win)
        opt("*Menu.foreground", fg)
        opt("*Menu.activebackground", acc)
        opt("*Menu.activeforeground", "#ffffff")
        opt("*Entry.background", inp)
        opt("*Entry.foreground", fg)
        opt("*Entry.selectbackground", acc)
        opt("*Listbox.background", inp)
        opt("*Listbox.foreground", fg)
        opt("*Text.background", inp)
        opt("*Text.foreground", fg)
        opt("*Scrollbar.background", win)
        opt("*Scrollbar.troughcolor", border)

    def _apply_skin(self, name: str | None = None, palette: dict | None = None, *, persist=True) -> None:
        """T3：按当前 _skin_name（或给定 palette，R15 ghost 全透明黑字）应用 Token
        到顶层控件 + msg_list；palette 由 R15 toggle_ghost 注入，不改写 _skin_name。"""
        previous = self._skin
        self._skin = palette if palette else get_skin(name if name else self._skin_name)
        sk = self._skin
        self._recolor_chat_surfaces(previous, sk)
        self._dp = dialog_pal(sk)      # R57：对话框/独立面板派生配色（含深色）
        self._set_default_colors()     # R57B：未指定颜色的控件默认跟随皮肤
        self.root.configure(bg=sk["window_bg"])
        # Excel chrome 只在主皮肤为 excel 时显示；ghost 透明模式暂时隐藏，
        # 恢复原皮肤后再按持久化皮肤显示，避免装饰层破坏字幕模式。
        ec = getattr(self, "_excel_chrome", None)
        if ec is not None:
            try:
                ec.set_theme(sk)
                ec.set_visible(palette is None and self._skin_name == "excel")
                self._sync_excel_layout(palette is None and self._skin_name == "excel")
            except tk.TclError:
                pass
        body = getattr(self, "_body_frame", None)
        if body is not None:
            try:
                is_excel = palette is None and self._skin_name == "excel"
                body.configure(highlightthickness=1 if is_excel else 0,
                               highlightbackground=sk.get("glass_border", "#d0d7de"))
            except tk.TclError:
                pass
        # 状态条标签与按钮
        for w in (getattr(self, "status_dot", None),
                  getattr(self, "status_text", None)):
            if w is not None:
                try:
                    w.configure(bg=sk["window_bg"], fg=sk["sub"])
                except tk.TclError:
                    pass
        for b in getattr(self, "_top_btns", []):
            try:
                b.configure(bg=sk["window_bg"], fg=sk["sub"])
            except tk.TclError:
                pass
        # 左侧面板标签/按钮
        for b in getattr(self, "_left_btns", []):
            try:
                b.configure(bg=sk["list_bg"], fg=sk["accent"])
            except tk.TclError:
                pass
        if hasattr(self, "_arch_btn") and self._arch_btn:
            try:
                self._arch_btn.configure(bg=sk["list_bg"], fg=sk["sub"])
            except tk.TclError:
                pass
        if hasattr(self, "search_entry") and self.search_entry:
            try:
                self.search_entry.configure(bg=sk["input_bg"], fg=sk["fg"],
                                            insertbackground=sk["fg"],
                                            highlightbackground=sk["glass_border"])
            except tk.TclError:
                pass
        # 右侧面板标签/输入框/按钮
        if hasattr(self, "chan_label") and self.chan_label:
            try:
                self.chan_label.configure(bg=sk["panel_bg"], fg=sk["fg"])
            except tk.TclError:
                pass
        if hasattr(self, "entry") and self.entry:
            try:
                self.entry.configure(bg=sk["input_bg"], fg=sk["fg"],
                                      insertbackground=sk["fg"],
                                      highlightbackground=sk["glass_border"],
                                      highlightcolor=sk["accent"])
            except tk.TclError:
                pass
        # R31：输入区容器与工具行背景跟随主题
        for w in (getattr(self, "_bottom_frame", None),
                  getattr(self, "_toolbar_bar", None)):
            if w is not None:
                try:
                    w.configure(bg=sk["panel_bg"])
                except tk.TclError:
                    pass
        # R63 拖拽把手细条：独立刷为 sub 色（保持可见），不吃 panel_bg
        db = getattr(self, "_drag_bar", None)
        if db is not None:
            try:
                db.configure(bg=sk["glass_border"])
            except tk.TclError:
                pass
        for b in getattr(self, "_bottom_btns", []):
            try:
                b.configure(bg=sk["panel_bg"], fg=sk["sub"])
            except tk.TclError:
                pass
        # R31：开关徽标跟随主题（bg 用输入框底色）
        for b in (getattr(self, "_burn_btn", None),
                  getattr(self, "_silent_btn", None),
                  getattr(self, "_disguise_btn", None)):   # R70E：伪装徽标
            if b:
                try:
                    b.configure(bg=sk["input_bg"])
                except tk.TclError:
                    pass
        if hasattr(self, "_send_btn") and self._send_btn:
            try:
                self._send_btn.configure(bg=sk["accent"], fg="#ffffff")
            except tk.TclError:
                pass
        # 左侧会话/群 SessionList（两行 Canvas）整批换色
        sl_pal = {
            "bg": sk["list_bg"],
            "fg": sk["fg"],
            "sub": sk["sub"],
            "accent": sk["accent"],
            "selected_fg": sk['fg'] if sk.get('name', '').startswith('雾岸') else "#ffffff",
            "selected_bg": design_color('selected_background', sk.get('name') == '雾岸深色') if sk.get('name', '').startswith('雾岸') else sk['accent'],
            "muted": sk["sub"],
            "hover": sk.get("hover_bg", "#ececec"),
        }
        for sl in (getattr(self, "roster_list", None),
                   getattr(self, "group_list", None)):
            if sl is not None:
                sl.set_colors(sl_pal)
        # R8 自绘标题栏换色
        tb = getattr(self, "title_bar", None)
        if tb is not None:
            tb.set_colors(sk)
        # 归档 Listbox 底色与文字
        lb = getattr(self, "_archived_list", None)
        if lb is not None:
            lb.configure(bg=sk["list_bg"], fg=sk["fg"],
                         selectbackground=sk["accent"],
                         selectforeground="#ffffff")
        # 消息列表整体换色（含气泡）
        self.msg_list.set_colors(msg_colors(sk))
        self.msg_list.set_grid(
            sk["glass_border"] if palette is None and self._skin_name == "excel" else None)
        self._apply_chat_theme()        # 聊天主题叠层：在皮肤 token 上叠加气泡主题色
        # R32B4：壁纸在换肤后恢复（启动首次 apply_theme 也走这里）
        try:
            self.msg_list.set_wallpaper(str(self._prefs.get("chat_wallpaper") or "") or None)
        except Exception:
            pass
        # R56：三条通知横幅（置顶/公告/录音）跟随主题，避免深色皮肤下白块刺眼
        self._tint_notif_bar("pin_bar", "pin_bg", "pin_label", "pin_fg",
                             default_bg="#fff8e1", default_fg="#b26a00",
                             tint_fg=True)
        self._tint_notif_bar("announce_bar", "ann_bg", "announce_label", "ann_fg",
                             default_bg="#fce8ee", default_fg="#7b2d4e",
                             tint_fg=True)
        # 录音条只跟随底色：录音红字是语义色，两种模式都需醒目，不强改前景
        self._tint_notif_bar("_voice_bar", "voice_bg", None, None,
                             default_bg="#fff2e6", default_fg="#e03e3e",
                             tint_fg=False)
        for button in getattr(self, '_design_buttons', ()):
            button.set_palette(sk)
        self._apply_font_scale()
        if persist:
            self._prefs.set("skin", self._skin_name)

    def _recolor_chat_surfaces(self, previous, current):
        backgrounds = {previous[key]: current[key] for key in
                       ('window_bg','list_bg','icon_bg','panel_bg','input_bg')}
        foregrounds = {previous[key]: current[key] for key in ('fg','sub')}
        def visit(widget):
            if isinstance(widget, tk.Toplevel):
                return
            options = widget.keys()
            updates = {}
            if 'background' in options:
                old = str(widget.cget('background'))
                if old in backgrounds:
                    updates['background'] = backgrounds[old]
            if 'foreground' in options:
                old = str(widget.cget('foreground'))
                if old in foregrounds:
                    updates['foreground'] = foregrounds[old]
            if updates:
                widget.configure(**updates)
            for child in widget.winfo_children():
                visit(child)
        for container in (getattr(self,'_body_frame',None),getattr(self,'_status_bar_frame',None)):
            if container is not None:
                visit(container)
        if getattr(self,'icon_bar',None) is not None:
            self.icon_bar.configure(bg=current['icon_bg'])
            self.icon_avatar.configure(bg=current['icon_bg'])
        for attribute,role in (('_body_frame','window_bg'),('_session_frame','list_bg'),
                               ('_folder_bar','list_bg'),('_chat_frame','panel_bg'),
                               ('_wrap_frame','panel_bg'),('chan_label_row','panel_bg'),
                               ('_bottom_frame','panel_bg'),('_toolbar_bar','panel_bg'),
                               ('_compose_footer','panel_bg')):
            frame=getattr(self,attribute,None)
            if frame is not None:
                frame.configure(bg=current[role])
                for child in frame.winfo_children():
                    if isinstance(child,tk.Label):
                        child.configure(bg=current[role])
        if getattr(self,'_compose_target',None) is not None:
            self._compose_target.configure(bg=current['panel_bg'],fg=current['sub'])

    def _apply_chat_theme(self) -> None:
        """聊天主题叠层：在已套的皮肤 token 之上再叠气泡/聊天区主题色，
        并整列重绘（msg_list.set_colors 内部已 _render）。"""
        overlay = theme_chat_overlay(self._prefs.chat_theme())
        if overlay:
            self.msg_list.set_colors(overlay)

    def _on_chat_theme_pick(self, label: str) -> None:
        """设置页「聊天主题」下拉 → 存 prefs + 立即换肤并整列重绘。"""
        key = next((k for k in chat_theme_names()
                    if chat_theme_display(k) == label), "")
        self._prefs.set_chat_theme(key)
        self._apply_chat_theme()

    def _tint_notif_bar(self, bar_attr, bg_tok, label_attr, fg_tok,
                        default_bg="#ffffff", default_fg="#000000",
                        tint_fg=True) -> None:
        """按主题 token 刷单条通知横幅。tint_fg=False 时只改底色（保留语义红字）。"""
        sk = self._skin
        bar = getattr(self, bar_attr, None)
        if bar is None:
            return
        try:
            bg = sk.get(bg_tok, default_bg)
            bar.configure(bg=bg)
            if not tint_fg:
                # 仅改变底色，不改 label/button 前景（录音红字保持）
                for child in bar.winfo_children():
                    if hasattr(child, "configure"):
                        try:
                            child.configure(bg=bg)
                        except tk.TclError:
                            pass
                return
            fg = sk.get(fg_tok, default_fg)
            for child in bar.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg=bg, fg=fg)
                elif isinstance(child, tk.Button):
                    child.configure(bg=bg, fg=fg)
        except tk.TclError:
            pass

    # ---------- R15 全透明黑字模式（F1 切换，游戏字幕叠层） ----------
    def toggle_ghost(self, _e=None) -> str:
        """F1：在「完整 UI」与「全透明黑字」之间切换。返回 "break" 拦掉后续键。"""
        if not self._ghost:
            self._force_ghost_colors(True)      # 先强改所有普通控件为挖空/黑字
            self._apply_ghost_palette()         # 按当前衬底深浅刷 token（气泡混白/挖空）
            try:
                self.root.attributes("-transparentcolor", GHOST_PUNCH)
                self.root.attributes("-topmost", True)
            except tk.TclError:
                pass
            self.root.attributes("-alpha", 1.0)  # 避免黑字被窗 alpha 淡化
            self.msg_list.set_halo(GHOST_HALO if self._ghost_halo_on else None)  # R17 描边
            self._ghost_set_click_through(True)  # R17 点击穿透，不抢后台焦点
            self._fill_ghost_messages()
            self._ghost = True
            self._show_ghost_exit_tip()          # R31：可见的恢复入口（点击即回）
            self._ghost_kick_ttl()              # 启动字幕停留计时
        else:
            self._ghost_cancel_fade()
            self._ghost_cancel_ttl()
            try:
                self.root.attributes("-transparentcolor", "")
                self.root.attributes("-topmost", False)
            except tk.TclError:
                pass
            self.root.attributes("-alpha", self._chat_alpha)
            self.msg_list.set_halo(None)         # R17 还原无描边
            self._ghost_set_click_through(False) # R17 还原可交互
            self._hide_ghost_exit_tip()          # R31：收起恢复提示条
            self._apply_skin()                   # token 级还原原皮肤
            self._force_ghost_colors(False)      # 普通控件恢复缓存原色
            try:
                self._load_view_history()        # 还原当前会话历史
            except Exception:
                pass
            self._ghost = False
        return "break"

    def _apply_ghost_palette(self) -> None:
        """按 _ghost_back（0→纯透，1→白底）生成 ghost token 刷到消息列表。"""
        self._apply_skin(palette=ghost_palette(self._ghost_back))
        if self._ghost:                          # R17 衬底同步不覆盖描边开关
            self.msg_list.set_halo(GHOST_HALO if self._ghost_halo_on else None)

    def ghost_back_inc(self, _e=None) -> str:
        """Ctrl+←：字幕衬底变浅（亮背景更清晰）。只在 ghost 生效。"""
        if not self._ghost:
            return "break"
        self._ghost_back = min(1.0, self._ghost_back + GHOST_BACK_STEP)
        self._apply_ghost_palette()
        return "break"

    def ghost_back_dec(self, _e=None) -> str:
        """Ctrl+→：字幕衬底变深（回到纯透黑字）。只在 ghost 生效。"""
        if not self._ghost:
            return "break"
        self._ghost_back = max(0.0, self._ghost_back - GHOST_BACK_STEP)
        self._apply_ghost_palette()
        return "break"

    def ghost_cycle_filter(self, _e=None) -> str:
        """F2：字幕频道过滤循环：全部 → 仅公聊 → 仅@我。只在 ghost 生效并重建字幕。"""
        if not self._ghost:
            return "break"
        order = self._FILTER_ORDER
        self._ghost_filter = order[(order.index(self._ghost_filter) + 1) % len(order)]
        self._fill_ghost_messages()
        self._ghost_kick_ttl()
        return "break"

    def _ghost_in_filter(self, m: dict) -> bool:
        """字幕频道过滤判定：all 全收；public 仅公聊；atme 仅 @我/私聊我。"""
        f = self._ghost_filter
        if f == "all":
            return True
        if f == "public":
            return m.get("channel") == "public"
        if f == "atme":
            if m.get("channel") == "private":
                return True
            mentions = m.get("mentions") or []
            if mentions:                                  # R14 群@提及字段
                mine = getattr(self.core, "nick", "")
                return any(mm.get("uid") == self.core.uid
                           or mm.get("nick") == mine for mm in mentions)
            return f"@{getattr(self.core, 'nick', '')}" in (m.get("text") or "")
        return True

    def _ghost_kick_ttl(self) -> None:
        """重置字幕停留计时；到期（GHOST_TTL 秒无新消息）清空字幕。"""
        self._ghost_cancel_ttl()
        self._ghost_after = self.root.after(int(GHOST_TTL * 1000), self._ghost_expire)

    def _ghost_cancel_ttl(self) -> None:
        if self._ghost_after is not None:
            try:
                self.root.after_cancel(self._ghost_after)
            except Exception:
                pass
            self._ghost_after = None

    def _ghost_expire(self) -> None:
        """字幕到期：平滑淡化后清空，保留 ghost 状态（新消息来重现）。"""
        self._ghost_after = None
        if not self._ghost:
            return
        fade_s = max(0.05, GHOST_FADE)
        steps = max(2, GHOST_FADE_STEPS)
        dt = int(fade_s / steps * 1000)

        def step(i: int) -> None:
            if not self._ghost:                  # 中途退出：直接收尾
                self.root.attributes("-alpha", 1.0)
                self.msg_list.clear()
                return
            if i >= steps:
                self.root.attributes("-alpha", 1.0)   # 淡完复位（next 字幕不被淡化）
                self.msg_list.clear()
                return
            alpha = 1.0 - (i / steps) * 0.85      # 淡到 ~15% 后清除
            self.root.attributes("-alpha", max(0.0, min(1.0, alpha)))
            self._ghost_fade_job = self.root.after(dt, lambda: step(i + 1))

        self._ghost_fade_job = self.root.after(int(GHOST_FADE * 1000), step, 0)

    def _ghost_cancel_fade(self) -> None:
        """取消进行中的淡出动画并把窗 alpha 复位（退出 ghost 时幂等）。"""
        if self._ghost_fade_job is not None:
            try:
                self.root.after_cancel(self._ghost_fade_job)
            except Exception:
                pass
            self._ghost_fade_job = None
        try:
            self.root.attributes("-alpha", 1.0)
        except tk.TclError:
            pass

    def ghost_toggle_halo(self, _e=None) -> str:
        """F3：字幕黑字描边光晕开关（亮/暗背景都可读）。只在 ghost 生效。"""
        if not self._ghost:
            return "break"
        self._ghost_halo_on = not self._ghost_halo_on
        self.msg_list.set_halo(GHOST_HALO if self._ghost_halo_on else None)
        return "break"

    def _ghost_set_click_through(self, on: bool) -> None:
        """R17 字幕穿透：layered + transparentcolor 已让挖空像素点击穿透；
        R31 修复：不再叠加窗口级 WS_EX_TRANSPARENT（那会让整窗连字幕/恢复
        提示都点不到、F1 也因无焦点失效，程序像卡死）。现在只穿透挖空区，
        字幕文字与「点击恢复」提示条可交互。非 Windows 或失败静默。"""
        if os.name != "nt":
            return
        if on == self._ghost_click_thru:
            return
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            hwnd = int(self.root.winfo_id())
            cur = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if on:
                new = cur | WS_EX_LAYERED           # 挖空像素穿透依赖 layered
                new = new & ~WS_EX_TRANSPARENT      # 不再全窗穿透（R31）
            else:
                new = cur & ~(WS_EX_LAYERED | WS_EX_TRANSPARENT)
            if new != cur:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new)
            self._ghost_click_thru = on
        except Exception:
            pass

    # ---------- R31 字幕模式恢复入口 ----------
    def _show_ghost_exit_tip(self) -> None:
        """R31：字幕模式顶部提示条——原来只能靠 F1（需焦点）退出，
        全穿透下几乎无法发现；现在点击提示条即可恢复完整界面。
        R55F3：ghost 下标题栏被挖空成穿透区拖不动，提示条兼作拖动句柄
        （按住拖动移窗，单击恢复）。"""
        if getattr(self, "_ghost_exit_tip", None) is None:
            tip = tk.Label(self.root,
                           text="💬 字幕模式 · 按住拖动窗口 · 单击恢复（F1）",
                           bg="#2b2b2b", fg="#ffffff", padx=10, pady=3,
                           font=(FONT_FAMILY, 9), cursor="fleur")

            def _press(ev):
                self._gx, self._gy = ev.x_root, ev.y_root
                self._gwx, self._gwy = self.root.winfo_x(), self.root.winfo_y()
                self._g_drag = False

            def _drag(ev):
                dx, dy = ev.x_root - self._gx, ev.y_root - self._gy
                if abs(dx) + abs(dy) > 3:
                    self._g_drag = True
                self.root.geometry(
                    f"+{self._gwx + dx}+{self._gwy + dy}")

            def _up(ev):
                if not self._g_drag:              # 无位移 = 单击恢复
                    self.toggle_ghost()

            tip.bind("<Button-1>", _press)
            tip.bind("<B1-Motion>", _drag)
            tip.bind("<ButtonRelease-1>", _up)
            self._ghost_exit_tip = tip
        # walk 挖空遍历会把缓存色改掉 → 每次显示时强制回显色
        self._ghost_exit_tip.configure(bg="#2b2b2b", fg="#ffffff")
        self._ghost_exit_tip.place(relx=0.5, y=4, anchor="n")
        self._ghost_exit_tip.lift()

    def _hide_ghost_exit_tip(self) -> None:
        tip = getattr(self, "_ghost_exit_tip", None)
        if tip is not None:
            tip.place_forget()

    def _fill_ghost_messages(self) -> None:
        """把消息区替换为全局最近 GHOST_N 条（过滤后）跨会话消息（昵称缺失补当前昵称）。"""
        hist = getattr(self.core, "_history", None)
        msgs = hist.recent_global(GHOST_N) if hist else []
        mine = getattr(self.core, "nick", "")
        filtered = []
        for m in msgs:
            if not m.get("nick") and m.get("uid") == self.core.uid:
                m["nick"] = mine
            if self._ghost_in_filter(m):
                filtered.append(m)
        self.msg_list.load(filtered, self.core.uid)

    def _force_ghost_colors(self, enter: bool) -> None:
        """遍历整棵控件树：enter 后台→挖空色/字→黑并缓存原色；False 恢复缓存。
        覆盖 _apply_skin 未触及的手写色控件（底栏按钮/输入区/标签等）。"""
        if not enter:
            for w, (bg, fg) in list(self._ghost_cache.items()):
                if bg is not None:
                    try:
                        w.configure(bg=bg)
                    except tk.TclError:
                        pass
                if fg is not None:
                    try:
                        w.configure(fg=fg)
                    except tk.TclError:
                        pass
            self._ghost_cache.clear()
            return
        self._ghost_cache.clear()

        def walk(w):
            bg = fg = None
            try:
                bg = w.cget("bg")
            except tk.TclError:
                pass
            try:
                fg = w.cget("fg")
            except tk.TclError:
                pass
            self._ghost_cache[w] = (bg, fg)
            try:
                w.configure(bg=GHOST_PUNCH)
            except tk.TclError:
                pass
            try:
                w.configure(fg=GHOST_BLACK)
            except tk.TclError:
                pass
            for c in w.winfo_children():
                walk(c)

        walk(self.root)

    def _apply_dwm_corner(self) -> None:
        """win32 DWM 圆角（DWMWA_WINDOW_CORNER_PREFERENCE=2 圆角）。非 win32/失败静默。"""
        if os.name != "nt":
            return
        try:
            import ctypes
            val = ctypes.c_int(2)
            hwnd = int(self.root.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(val), ctypes.sizeof(val))
        except Exception:
            pass                       # Win10 或不支持：回落直角，功能无损

    # ---------- R10 运行时锁屏（隐藏主窗 + 全屏遮罩防任务栏偷窥） ----------
    def _set_dwm_peek(self, lock: bool) -> None:
        """锁定置 FORCE_ICONIC_REPRESENTATION/HAS_ICONIC_BITMAP=1（防实时预览），
        解锁还原=0。非 win32/失败静默（隐藏主窗已足够防偷窥）。"""
        if os.name != "nt":
            return
        try:
            import ctypes
            val = ctypes.c_int(1 if lock else 0)
            hwnd = int(self.root.winfo_id())
            for attr in (10, 11):              # DWMWA_FORCE_ICONIC_REPRESENTATION/HAS_ICONIC_BITMAP
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(val), ctypes.sizeof(val))
        except Exception:
            pass

    def lock_app(self, _e=None):
        """🔒/Ctrl+L：运行时锁定。需已设解锁码；锁定=隐藏主窗+全屏 LockOverlay。"""
        if getattr(self, "_locked", False):
            return
        if not self._prefs.has_passcode():
            from widgets import dialogbox
            dialogbox.show_message("锁定", "请先在「⚙ 设置 → 本机解锁码」中设置解锁码，"
                                       "再使用锁定（防偷窥）。", parent=self.root)
            return
        self._set_dwm_peek(True)
        self.root.withdraw()                   # 任务栏彻底无主窗预览
        from auth import verify
        from widgets.lock_screen import LockOverlay
        stored = self._prefs.passcode()
        overlay = LockOverlay(self.root,
                              verifier=lambda c, s=stored: verify(c, s),
                              on_unlock=self.unlock_app, on_cancel=self.unlock_app,
                              skin=self._skin)
        self._locked = True
        self._lock_overlay = overlay

    def unlock_app(self) -> None:
        """解锁遮罩：清 DWM 防偷窥属性并恢复主窗。"""
        if not getattr(self, "_locked", False):
            return
        ov = self._lock_overlay
        self._lock_overlay = None
        if ov is not None:
            ov.destroy()
        self._set_dwm_peek(False)
        self._locked = False
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _set_passcode_dialog(self) -> None:
        """设置/修改本机解锁码：有码先验证旧码（Scrim+PasscodeBox），再进设置框。"""
        from widgets.scrim import Scrim
        from widgets.passcode import PasscodeBox
        from auth import verify
        stored = self._prefs.passcode()
        if not stored:
            self._show_set_passcode_dlg()
            return
        scrim = Scrim(self.root)
        scrim.show()

        def on_ok() -> None:
            scrim.hide()
            self._show_set_passcode_dlg()

        def on_cancel() -> None:
            scrim.hide()

        PasscodeBox(self.root, title="验证解锁码", about="请输入当前解锁码：",
                    verifier=lambda c: verify(c, stored),
                    on_ok=on_ok, on_cancel=on_cancel,
                    colors={"bg": self._skin["panel_bg"],
                            "fg": self._skin["fg"],
                            "sub": self._skin["sub"]})

    def _show_set_passcode_dlg(self) -> None:
        """新解锁码（两次一致）/ 清除 / 关闭。"""
        from auth import make
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("本机解锁码")
        dlg.transient(self.root)
        dlg.geometry("+" + str(self.root.winfo_x() + 80) + "+" + str(self.root.winfo_y() + 80))
        dlg.attributes("-topmost", True)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "本机解锁码")
        f = self._f
        tk.Label(dlg, text="解锁码用于进入本客户端时验证，可防他人误开。",
                 font=f, fg=self._dp["sub"], wraplength=280, justify="left").pack(
            fill="x", padx=10, pady=6)
        tk.Label(dlg, text="新解锁码：", font=f, anchor="w").pack(fill="x", padx=10)
        e1 = tk.Entry(dlg, show="*", font=f)
        e1.pack(fill="x", padx=10)
        tk.Label(dlg, text="再次输入：", font=f, anchor="w").pack(fill="x", padx=10)
        e2 = tk.Entry(dlg, show="*", font=f)
        e2.pack(fill="x", padx=10)
        err = tk.Label(dlg, text="", fg="#e03e3e", font=f)
        err.pack(fill="x", padx=10)

        def _set() -> None:
            v1, v2 = e1.get(), e2.get()
            if not v1:
                err.config(text="请输入解锁码")
                return
            if v1 != v2:
                err.config(text="两次输入不一致")
                return
            self._prefs.set_passcode(make(v1))
            dlg.destroy()

        def _clear() -> None:
            self._prefs.set_passcode(None)
            dlg.destroy()

        btns = tk.Frame(dlg)
        btns.pack(fill="x", padx=10, pady=8)
        tk.Button(btns, text="设置", command=_set, font=f).pack(side="left", padx=2)
        if self._prefs.has_passcode():
            tk.Button(btns, text="清除", command=_clear, font=f).pack(side="left", padx=2)
        tk.Button(btns, text="关闭", command=dlg.destroy, font=f).pack(side="left", padx=2)

    def _set_nick_pwd_dialog(self) -> None:
        """R47-B：设置/修改/清除昵称密码（new 空=清除）。结果经服务器
        system（成功 ✅）/ error（失败 ⚠）帧异步反馈到聊天区。"""
        from widgets import dialogbox

        def _validate(vals) -> str | None:
            if vals[1] != vals[2]:
                return "两次输入的新密码不一致"
            return None

        res = dialogbox.ask_fields(
            "昵称密码",
            "昵称密码用于防止他人冒用你的昵称登录。\n新密码留空 = 清除密码。",
            [("旧密码（未设过可留空）：", "*"),
             ("新密码（留空=清除）：", "*"),
             ("再次输入新密码：", "*")],
            parent=self.root, validator=_validate)
        if res is not None:
            self.core.send_set_pwd(res[0].strip(), res[1].strip())

    # ---------- R46 伪装包 ----------
    def _camo_title(self) -> str:
        """伪装标题：prefs['camo'] 非空则主窗/任务栏/托盘都显示它。"""
        return str(self._prefs.get("camo", "") or "") or APP_NAME

    def _apply_camo(self) -> None:
        """应用伪装：主窗标题（任务栏随之）+ 托盘 tooltip 即时生效。"""
        t = self._camo_title()
        try:
            self.root.title(t)
        except Exception:
            pass
        if getattr(self, "_tray", None):
            self._tray.set_tip("" if t == APP_NAME else t)

    def _sett_wheel(self, e):
        """设置面板全局滚轮路由：鼠标在设置内容区内滚动时滚动该画布。"""
        t = getattr(e, "widget", None)
        if t is None or t == "":
            return None
        for cv_, inner in getattr(self, "_scrl", ()):
            node = t
            while node is not None and node is not inner:
                node = getattr(node, "master", None)
            if node is inner:
                cv_.yview_scroll(-int(e.delta / 120), "units")
                return "break"
        return None

    def _on_settings(self) -> None:
        """设置：R57B3 全自绘控件（勾选框/滑杆/下拉/按钮），精确贴合主窗 Apple 蓝调；
        热键状态 + 分组设置行 + 发现的服务器（双击连接）+ 手动 IP/端口兜底。"""
        self._select_navigation('settings')
        dp = self._dp
        win, fg, sub = dp["win"], dp["fg"], dp["sub"]
        acc, inp, border = dp["accent"], dp["input"], dp["border"]
        card = dp.get("card", win)
        sec_bg = dp.get("doc_h", border)     # 次要按钮浅底
        f = self._f
        ds = float(getattr(self, "_dpi_scale", 1.0) or 1.0)

        # ---------- 自绘控件工厂（Canvas，Apple 圆角 + 蓝色强调） ----------
        def rrect(cv, x1, y1, x2, y2, r, **kw):
            r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
            pts = (x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
                   x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1)
            return cv.create_polygon(pts, smooth=True, **kw)

        def make_chk(cv, var, on_cmd=None, bg=card):
            # R43C：勾选动画 —— 选中填充按进度自底部→顶部生长 + 勾线逐段画出
            # （约 100ms，ease 逼近；动画期间再次点击落在目标方向，绝无残留闪烁）
            size = 21 * ds
            cv.configure(width=int(size * 1.2), height=int(size * 1.2),
                         bg=bg, highlightthickness=0, bd=0)
            st = {"t": 1.0 if bool(var.get()) else 0.0, "job": None}
            CHK_MS, CHK_STEP = 100, 16
            def render():
                try:
                    cv.delete("all")
                    pad = size * 0.1
                    b = pad
                    t = max(0.0, min(1.0, st["t"]))
                    if t < 0.999:                      # 未完全选中 → 画边框底色
                        rrect(cv, b, b, b + size, b + size, 6 * ds,
                              fill=card, outline=border, width=max(1, int(ds)))
                    if t > 0.01:                       # 选中填充：自底部向上生长
                        fh = size * t
                        rrect(cv, b, b + size - fh, b + size, b + size,
                              min(6 * ds, fh / 2), fill=acc, outline=acc, width=1)
                    if t >= 0.30:                      # 勾线：沿折线按进度生长
                        lt = (t - 0.30) / 0.70
                        p1 = (b + size * 0.28, b + size * 0.52)
                        pm = (b + size * 0.42, b + size * 0.68)
                        p2 = (b + size * 0.76, b + size * 0.32)
                        s1 = (pm[0] - p1[0], pm[1] - p1[1])
                        s2 = (p2[0] - pm[0], p2[1] - pm[1])
                        L1 = (s1[0] ** 2 + s1[1] ** 2) ** 0.5
                        L2 = (s2[0] ** 2 + s2[1] ** 2) ** 0.5
                        L = lt * (L1 + L2)
                        if L < L1:
                            k = L / L1 if L1 else 1.0
                            pts = (p1[0], p1[1], p1[0] + s1[0] * k, p1[1] + s1[1] * k)
                        else:
                            k = (L - L1) / L2 if L2 else 1.0
                            pts = (p1[0], p1[1], pm[0], pm[1],
                                   pm[0] + s2[0] * k, pm[1] + s2[1] * k)
                        cv.create_line(*pts, fill="#ffffff", width=int(2.3 * ds),
                                       capstyle="round", joinstyle="round")
                except Exception:
                    pass
            def tick():
                try:
                    if not cv.winfo_exists():
                        return
                    target = 1.0 if bool(var.get()) else 0.0
                    d = target - st["t"]
                    if abs(d) < 0.012:
                        st["t"] = target
                        st["job"] = None
                        render()
                        return
                    st["t"] += d * 0.34                 # ease 逼近（渐快→渐慢达不到则收敛）
                    render()
                    st["job"] = cv.after(CHK_STEP, tick)
                except Exception:
                    st["job"] = None
            def click(_e):
                var.set(not bool(var.get()))
                if st["job"] is not None:               # 动画期间再点 → 取消防抖、直达目标
                    try:
                        cv.after_cancel(st["job"])
                    except Exception:
                        pass
                    st["job"] = None
                tick()
                if on_cmd:
                    on_cmd()
            cv.bind("<Button-1>", click)
            render()
            return cv

        def make_slider(cv, low, high, var, on_cmd, w=150, h=30, bg=card):
            track_h = max(4, int(5 * ds))
            thumb_r = int(8 * ds)
            cv.configure(width=int(w + 2 * ds), height=h, bg=bg,
                         highlightthickness=0, bd=0)
            drag = {"on": False}
            def t_x():
                t = max(low, min(high, float(var.get())))
                f_ = (t - low) / (high - low) if high > low else 0.0
                return thumb_r + f_ * (w - 2 * thumb_r)
            def draw():
                cv.delete("all")
                y = h / 2
                x = t_x()
                rrect(cv, thumb_r, y - track_h / 2, w - thumb_r, y + track_h / 2,
                      track_h / 2, fill=border, outline="")
                if x > thumb_r + track_h:
                    rrect(cv, thumb_r, y - track_h / 2, x, y + track_h / 2,
                          track_h / 2, fill=acc, outline="")
                cv.create_oval(x - thumb_r, y - thumb_r, x + thumb_r, y + thumb_r,
                               fill="#ffffff", outline=acc, width=max(1, int(1.5 * ds)))
                # R43C：数值圆泡（当前透明度 %），跟随滑块实时更新（释放亦然）
                try:
                    if high > low:
                        pct = int(round((float(var.get()) - low) / (high - low) * 100))
                    else:
                        pct = 0
                    txt = f"{pct}%"
                    small = (f[0], max(7, int(f[1]) - 3))
                    bh = 12 * ds
                    bw = len(txt) * 7 * ds + 6 * ds
                    bxp = max(bw / 2 + 2, min(w - bw / 2 - 2, x))
                    byy = y - track_h / 2 - thumb_r - bh / 2 - 2
                    if byy < bh / 2 + 1:
                        byy = bh / 2 + 1
                    rrect(cv, bxp - bw / 2, byy - bh / 2, bxp + bw / 2,
                          byy + bh / 2, bh / 2, fill=acc, outline="")
                    cv.create_text(bxp, byy, text=txt, fill="#ffffff", font=small)
                except Exception:
                    pass
            def to_v(x):
                x = max(thumb_r, min(w - thumb_r, x))
                f_ = (x - thumb_r) / (w - 2 * thumb_r) if w > 2 * thumb_r else 0
                v = max(low, min(high, round((low + f_ * (high - low)) / 0.05) * 0.05))
                var.set(v)
                if on_cmd:
                    on_cmd(str(v))
            def press(e):
                drag["on"] = True
                to_v(e.x)
                draw()
            def move(e):
                if drag["on"]:
                    to_v(e.x)
                    draw()
            def release(_e):
                drag["on"] = False
            cv.bind("<Button-1>", press)
            cv.bind("<B1-Motion>", move)
            cv.bind("<ButtonRelease-1>", release)
            draw()
            return cv

        def make_field(cv, var, labels, on_cmd, w=150, h=27, get_enabled=lambda: True,
                       bg=card):
            cv.configure(width=int(w + 2 * ds), height=h, bg=bg,
                         highlightthickness=0, bd=0)
            def draw():
                cv.delete("all")
                y = h / 2
                en = get_enabled() if get_enabled else True
                fe, be = (fg, card) if en else (sub, border)
                rrect(cv, 1, 1, w - 1, h - 1, 6 * ds, fill=be, outline=border,
                      width=max(1, int(ds)))
                cv.create_text(w - h, y, text=str(var.get()), fill=fe,
                               anchor="center", font=f)
                cv.create_text(w - h * 0.45, y, text="▾", fill=fe, anchor="center")
            menu = tk.Menu(cv, tearoff=0, bg=card, fg=fg, activebackground=acc,
                           activeforeground="#ffffff", font=f)
            for lab in labels:
                menu.add_command(label=lab,
                                 command=lambda l=lab: (var.set(l), on_cmd(l), draw()))
            def click(e):
                if (get_enabled() if get_enabled else False):
                    try:
                        menu.tk_popup(cv.winfo_rootx(), cv.winfo_rooty() + h + 2)
                    finally:
                        menu.grab_release()
            cv.bind("<Button-1>", click)
            cv._refresh = draw        # 供外部刷新（如跟随系统浅深切换后重绘禁用态）
            draw()
            return cv

        def make_btn(cv, text, cmd, w=116, h=28, fill0=sec_bg, textfg=None,
                     bg=card, hover_acc=True):
            tfg = textfg if textfg is not None else fg
            st = {"hover": False}
            def draw():
                cv.delete("all")
                ww = cv.winfo_width() or w
                hh = cv.winfo_height() or h
                yy = hh / 2
                if st["hover"] and hover_acc:
                    rrect(cv, 1, 1, ww - 1, hh - 1, 7 * ds, outline=acc,
                          width=max(1, int(ds)))
                    rrect(cv, 2, 2, ww - 2, hh - 2, 6 * ds, fill=fill0,
                          outline="")
                else:
                    rrect(cv, 1, 1, ww - 1, hh - 1, 6 * ds, fill=fill0,
                          outline=("" if fill0 == acc else border),
                          width=0 if fill0 == acc else max(1, int(ds)))
                cv.create_text(ww / 2, yy, text=text, fill=tfg, font=f)
            def sync(_e=None):
                st["hover"] = False
                draw()
            cv.bind("<Configure>", sync)
            cv.bind("<Enter>", lambda e: (st.__setitem__("hover", True), draw()))
            cv.bind("<Leave>", lambda e: (st.__setitem__("hover", False), draw()))
            cv.bind("<Button-1>", lambda e: cmd())
            cv.configure(width=int(w * 1.18), height=h, bg=bg,
                         highlightthickness=0, bd=0)
            draw()
            return cv

        # R交互：设置改为主窗内嵌的**全屏面板**，采用 Telegram 式「左侧栏分类 + 右侧短子页」。
        # 换肤撕裂修复：每次打开都整体重建（destroy 旧面板）。否则旧的自绘控件会把
        # 当时的皮肤色 baked 在画布里，多次打开叠加出重复行，且皮肤切换后新旧两色的
        # 面板共存 → 上下半浅深撕裂 + checkbox 状态错乱。
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.destroy()
        self._settings_win = tk.Frame(self.root, bg=win)
        self._settings_win.place(x=0, y=0, relwidth=1, relheight=1)
        dlg = self._settings_win

        # 顶部返回栏
        _tp = tk.Frame(self._settings_win, bg=win)
        _tp.pack(side="top", fill="x")
        tk.Button(_tp, text="← 返回聊天", font=f, fg=acc, bg=win,
                  relief="flat", bd=0, activebackground=win, activeforeground=acc,
                  command=self._close_settings).pack(side="left", padx=16, pady=10)
        tk.Label(_tp, text="设置", font=(FONT_FAMILY, FONT_SIZE + 2, "bold"),
                 bg=win, fg=fg).pack(side="left", padx=(4, 12))
        tk.Frame(self._settings_win, bg=border, height=1).pack(side="top", fill="x")

        # —— 主体：左导航 + 右子页（随窗伸缩，右侧留白，不上下载入） ——
        host = tk.Frame(self._settings_win, bg=win)
        host.pack(side="top", fill="both", expand=True)
        nav = tk.Frame(host, bg=win, width=int(172 * ds))
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)                 # 固定侧栏宽度，不被子页挤压
        rightpane = tk.Frame(host, bg=win)
        rightpane.pack(side="left", fill="both", expand=True)
        page_host = tk.Frame(rightpane, bg=win)
        page_host.pack(fill="both", expand=True, padx=int(14 * ds), pady=int(12 * ds))
        sw = tk.Frame(page_host, bg=card)
        sw.pack(fill="both", expand=True)          # 子页卡片：随窗口自适应，防边缘裁切
        sw.pack_propagate(True)

        hover_bg = dp.get("hover", border)
        sub_c = dp.get("sub", sub)

        # —— Telegram 式菜单行（整行可点，左标题 + 右 ›），替代全宽次要按钮 ——
        def make_row(cv, text, cmd, h=None, danger=False, bgc=None):
            hh = int((h if h else 30) * ds)
            cv.configure(width=200, height=hh, highlightthickness=0, bd=0)
            st = {"hover": False}
            def draw():
                cv.delete("all")
                ww = cv.winfo_width() or 200
                if st["hover"]:
                    rrect(cv, 1, 1, ww - 1, hh - 1, 7 * ds, fill=hover_bg, outline="")
                tcol = ("#b71c1c" if danger else fg)
                cv.create_text(int(14 * ds), hh / 2, text=text, fill=tcol,
                               font=f, anchor="w")
                cv.create_text(ww - int(16 * ds), hh / 2, text="›", fill=sub_c,
                               font=f, anchor="center")
            cv.bind("<Configure>", lambda e: draw())
            cv.bind("<Enter>", lambda e: (st.__setitem__("hover", True), draw()))
            cv.bind("<Leave>", lambda e: (st.__setitem__("hover", False), draw()))
            cv.bind("<Button-1>", lambda e: cmd())
            cv.configure(bg=bgc if bgc else card)
            draw()
            return cv

        # —— 分组卡片内的公共行构造（P=父卡片；复用上面自绘动效控件） ——
        def add_toggle(P, text, var, on_cmd=None):
            r = tk.Frame(P, bg=card)
            r.pack(fill="x", padx=int(12 * ds), pady=int(3 * ds))
            tk.Label(r, text=text, bg=card, fg=fg, font=f, anchor="w",
                     wraplength=int(300 * ds), justify="left").pack(side="left")
            cv = tk.Canvas(r)
            make_chk(cv, var, on_cmd, bg=card)
            cv.pack(side="right")
            return var
        def add_field_row(P, text, var, labels, on_cmd, get_enabled=lambda: True):
            r = tk.Frame(P, bg=card)
            r.pack(fill="x", padx=int(12 * ds), pady=int(3 * ds))
            tk.Label(r, text=text, bg=card, fg=fg, font=f).pack(side="left")
            cv = tk.Canvas(r)
            make_field(cv, var, labels, on_cmd, get_enabled=get_enabled, bg=card)
            cv.pack(side="right")
            return cv
        def add_slider_row(P, text, from_, to_, var, on_cmd):
            r = tk.Frame(P, bg=card)
            r.pack(fill="x", padx=int(12 * ds), pady=int(3 * ds))
            tk.Label(r, text=text, bg=card, fg=fg, font=f).pack(side="left")
            cv = tk.Canvas(r)
            make_slider(cv, from_, to_, var, on_cmd, w=int(130 * ds), bg=card)
            cv.pack(side="right")
            return cv
        def add_row(P, text, cmd, danger=False):
            cv = tk.Canvas(P)
            make_row(cv, text, cmd, danger=danger, bgc=card)
            cv.pack(fill="x", padx=int(8 * ds), pady=int(1 * ds))
        def add_primary(P, text, cmd):
            cv = tk.Canvas(P)
            make_btn(cv, text, cmd, w=300, h=30, fill0=acc, textfg="#ffffff", bg=card)
            cv.pack(fill="x", padx=int(12 * ds), pady=int(6 * ds))
        def div(P):
            tk.Frame(P, bg=border, height=1).pack(fill="x", padx=0)

        # —— 持久变量（页面间切换复用，不丢状态） ——
        dnd_var = tk.BooleanVar(value=self._dnd)
        inv_var = tk.BooleanVar(value=bool(self.core.me.get("invisible")))
        _skin_keys = skin_names()
        _skin_labels = [skin_display(k) for k in _skin_keys]
        skin_var = tk.StringVar(value=skin_display(self._skin_name))
        follow_var = tk.BooleanVar(value=bool(self._prefs.get("skin_follow_system")))
        _ctheme_names = chat_theme_names()
        _ctheme_labels = [chat_theme_display(k) for k in _ctheme_names]
        ctheme_var = tk.StringVar(value=chat_theme_display(self._prefs.chat_theme()))
        _mode_labels = ["Telegram", "微信", "QQ"]
        _mode_map = dict(zip(["tg", "wechat", "qq"], _mode_labels))
        mode_var = tk.StringVar(value=_mode_map.get(
            self._prefs.get("interaction_mode", "tg"), "Telegram"))
        # R67 新消息提示音（off/soft/default/ding，与网页端语义一致）
        _sound_labels = ["关闭", "轻柔", "默认", "叮咚"]
        _sound_keys = {"关闭": "off", "轻柔": "soft", "默认": "default", "叮咚": "ding"}
        _sound_disp = {v: k for k, v in _sound_keys.items()}
        sound_var = tk.StringVar(value=_sound_disp.get(
            str(self._prefs.get("notify_sound", "default") or "default"), "默认"))
        def _on_sound_pick(label):
            self._prefs.set("notify_sound", _sound_keys[label])
            self._play_notify_sound()
        # R68 在线状态（online/away/busy，服务器权威、与隐身正交）
        _status_labels = ["在线", "离开", "忙碌"]
        _status_keys = {"在线": "online", "离开": "away", "忙碌": "busy"}
        _status_disp = {v: k for k, v in _status_keys.items()}
        status_var = tk.StringVar(value=_status_disp.get(
            str(self.core.me.get("status", "online") or "online"), "在线"))
        def _on_status_pick(label):
            self.core.send_status(_status_keys[label])   # 服务器权威；status_ack 回帧校准
            self._append_sys(f"在线状态已切换为「{label}」")
        # R70F 敏感词打码（纯本地显示层，默认关）
        guard_var = tk.BooleanVar(value=self._guard_on)
        _guard_hour_disp = {v: k for k, v in self._GUARD_HOUR_KEYS.items()}
        guard_hours_var = tk.StringVar(
            value=_guard_hour_disp.get(self._guard_hours, "全天"))
        def _on_guard_toggle():
            self._guard_on = bool(guard_var.get())
            self._refresh_guard()
        # R70G 忙碌自动回复（伪装态私聊自动应答）
        auto_reply_var = tk.BooleanVar(value=self._auto_reply_on)
        _ar_cd_labels = ["1 分钟", "5 分钟", "10 分钟", "30 分钟"]
        _ar_cd_keys = {"1 分钟": 60.0, "5 分钟": 300.0,
                       "10 分钟": 600.0, "30 分钟": 1800.0}
        _ar_cd_disp = {v: k for k, v in _ar_cd_keys.items()}
        auto_cd_var = tk.StringVar(value=_ar_cd_disp.get(self._auto_reply_cd, "10 分钟"))
        def _on_auto_toggle():
            self._auto_reply_on = bool(auto_reply_var.get())
            self._prefs.set("auto_reply_on", self._auto_reply_on)
        def _on_auto_text():
            from widgets import dialogbox
            v = dialogbox.ask_string(
                "自动回复文案", "伪装态（老板键）收到私聊时自动回复的内容：",
                initialvalue=self._auto_reply_text, parent=dlg)
            if v is not None:
                self._auto_reply_text = v.strip()[:200]
                self._prefs.set("auto_reply_text", self._auto_reply_text)
        def _on_auto_cd(label):
            self._auto_reply_cd = _ar_cd_keys.get(label, 600.0)
            self._prefs.set("auto_reply_cooldown", self._auto_reply_cd)
        # R70H 摸鱼排行榜（opt-in，默认关：开启后每结束一局向服务器上报 1 分）
        fish_var = tk.BooleanVar(value=self._fish_upload)
        def _on_fish_toggle():
            self._fish_upload = bool(fish_var.get())
            self._prefs.set("fish_upload", self._fish_upload)
        # R69A1 伪装皮肤（老板键假工作窗；右键菜单/F2 亦可轮换）
        boss_skin_var = tk.StringVar(value=BOSS_SKIN_LABELS.get(
            self._boss.skin, BOSS_SKIN_LABELS["excel"]))
        _boss_skin_labels = [BOSS_SKIN_LABELS[s] for s in BOSS_SKINS]
        def _on_boss_skin_pick(label):
            sk = next((s for s in BOSS_SKINS
                       if BOSS_SKIN_LABELS[s] == label), "excel")
            self._boss.set_skin(sk)
            self._prefs.set("boss_skin", sk)
        alpha_var = tk.DoubleVar(value=self._chat_alpha)
        _cur_camo = str(self._prefs.get("camo", "") or "")
        _camo_labels = [n for n, _v in CAMO_PRESETS] + ["自定义…"]
        def _camo_label(val):
            return next((n for n, v in CAMO_PRESETS if v == val),
                        val if val else "关闭")
        camo_var = tk.StringVar(value=_camo_label(_cur_camo))
        f_cnt = tk.IntVar(value=1 if self._frameless else 0)
        s_cnt = tk.IntVar(value=1 if self._prefs.get("scrim", True) else 0)
        font_var = tk.StringVar(value=_FONT_LABELS[self._font_scale()])  # R-字号
        def _on_font_pick(lab):
            idx = _FONT_LABELS.index(lab)
            self._prefs.set("font_scale", idx)      # 持久化
            self._apply_font_scale()                # 即时注入消息区/会话列表/输入区
        skin_cv = None                     # 在 _on_settings 作用域声明，供外观页/勾选回调共享

        def _on_invis_cmd():
            on = bool(inv_var.get())
            self.core.send_invis_set(on)     # 服务器权威持久；ack 回帧再校准
            self._append_sys("隐身状态已请求，等待服务器确认…" if True else "")
        def _skin_to_key(label):
            for k in _skin_keys:
                if skin_display(k) == label:
                    self._on_skin_change(k)
                    break
        def _follow_on():
            on = bool(follow_var.get())
            self._prefs.set("skin_follow_system", on)
            if on:
                self._on_skin_change(self._resolve_system_skin())
                skin_var.set(skin_display(self._skin_name))
            skin_cv._refresh()
        def _on_mode_pick(label):
            for k, lab in zip(["tg", "wechat", "qq"], _mode_labels):
                if lab == label:
                    self._set_mode(k)
                    self._append_sys("交互模式已保存，重启后生效")
                    break
        def _alpha_on(v):
            a = float(v)
            self.root.attributes("-alpha", a)
            self._prefs.set("chat_alpha", a)
        def _on_camo_pick(label):
            if label == "自定义…":
                from widgets import dialogbox
                val = dialogbox.ask_string(
                    "伪装标题", "输入自定义窗口标题（留空恢复默认）：",
                    initialvalue=self._camo_title(), parent=dlg)
                if val is None:
                    camo_var.set(_camo_label(str(self._prefs.get("camo", "") or "")))
                    return
                self._prefs.set("camo", val.strip()[:40])
            else:
                self._prefs.set("camo", dict(CAMO_PRESETS).get(label, ""))
            self._apply_camo()
            camo_var.set(_camo_label(str(self._prefs.get("camo", "") or "")))

        # —— 各分类子页（每页短、无滚动、随窗伸缩） ——
        _hot_state = (f"✅ 全局热键 {self._hotkey.desc} 已启用"
                      if self._hotkey_ok
                      else "⚠ 全局热键注册失败，可用下方按钮手动隐藏")
        _shot_state = ("✅ 截图热键 Alt+A 已启用（私聊内框选即发）"
                       if self._shot_hotkey_ok
                       else "⚠ 截图热键 Alt+A 注册失败")

        def pg_general(P):
            tk.Label(P, text=_hot_state, fg=sub, bg=card, font=f, anchor="w",
                     wraplength=int(300 * ds), justify="left").pack(
                fill="x", padx=int(12 * ds), pady=(int(10 * ds), int(4 * ds)))
            tk.Label(P, text=_shot_state, fg=sub, bg=card, font=f, anchor="w",
                     wraplength=int(300 * ds), justify="left").pack(
                fill="x", padx=int(12 * ds), pady=(0, int(4 * ds)))
            add_primary(P, "快速隐藏 · 弹出假工作窗",
                        lambda: (self._toggle_boss(), self._close_settings()))
            g = tk.Frame(P, bg=card); g.pack(fill="x", padx=0)
            # R69A1：伪装皮肤切换（老板键弹出的假工作窗）
            add_field_row(g, "伪装皮肤", boss_skin_var, _boss_skin_labels,
                          _on_boss_skin_pick)
            # R69A3：本地摸鱼报告入口
            add_row(g, "🐟 查看摸鱼报告", self._fish_report_dialog)
            # R70H：摸鱼排行榜（opt-in 上报；本机报告仍为纯本地）
            add_row(g, "🏆 摸鱼排行榜…", self._fish_board_dialog)
            add_toggle(g, "参与摸鱼排行榜（每局上报 1 分）", fish_var, _on_fish_toggle)
            tk.Label(g, text="opt-in：默认关闭。开启后每结束一局游戏向本机服务器累加 1 分，"
                             "榜单仅显示昵称与总分，关闭即停止上报",
                     fg=sub, bg=card, font=("Microsoft YaHei", 8), anchor="w",
                     justify="left").pack(fill="x", padx=int(12 * ds),
                                          pady=(0, int(4 * ds)))
            add_toggle(g, "免打扰（新消息不闪烁任务栏）", dnd_var, self._toggle_dnd)
            add_row(g, "免打扰时段…", self._dnd_range_dialog)
            # 免打扰实时状态小字：随开关/当前时段刷新
            dnd_status = tk.Label(g, text="", fg=sub, bg=card,
                                  font=("Microsoft YaHei", 8), anchor="w",
                                  justify="left")
            dnd_status.pack(fill="x", padx=int(12 * ds), pady=(0, int(4 * ds)))

            def _dnd_status_text():
                if self._in_dnd():
                    rng = self._prefs.dnd_range()
                    if rng.get("on"):
                        return (f"🔕 当前处于免打扰时段"
                                f"（{rng.get('start')}~{rng.get('end')}）")
                    return "🔕 当前处于免打扰（手动开关）"
                return "当前不在免打扰时段"
            dnd_status.config(text=_dnd_status_text())
            dnd_var.trace_add("write",
                              lambda *_: dnd_status.config(text=_dnd_status_text()))
            # 周期（1s）同步，捕捉到点进入/退出免打扰时段
            def _dnd_status_loop():
                try:
                    if dnd_status.winfo_exists():
                        dnd_status.config(text=_dnd_status_text())
                        self.settings_dnd_job = self.root.after(1000, _dnd_status_loop)
                except Exception:
                    pass
            self.settings_dnd_job = self.root.after(1000, _dnd_status_loop)
            div(g)
            # R60 关键词提醒：静音会话命中关键词仍例外放行通知
            tk.Label(g, text="🔔 关键词提醒（逗号分隔）", fg=sub, bg=card,
                     font=f, anchor="w").pack(fill="x",
                     padx=int(12 * ds), pady=(int(6 * ds), 0))
            kw_row = tk.Frame(g, bg=card)
            kw_row.pack(fill="x", padx=int(12 * ds))
            kw_entry = tk.Entry(kw_row, font=f, bg=dp["input"], fg=dp["fg"],
                                insertbackground=dp["fg"],
                                highlightthickness=1,
                                highlightbackground=border, relief="flat")
            kw_entry.insert(0, str(self._prefs.get("kw_words", "") or ""))
            kw_entry.pack(side="left", fill="x", expand=True, ipady=3)
            kw_btn = tk.Button(kw_row, text="保存", font=f, relief="flat", bd=0,
                               fg=dp["win"], bg=acc, cursor="hand2",
                               command=lambda: self._save_kw_remind(kw_entry))
            kw_btn.pack(side="left", padx=(6, 0))
            tk.Label(g, text="收到正文含关键词的消息时，即使该会话已静音也提示"
                             "（免打扰仍最高优先）",
                     fg=sub, bg=card, font=("Microsoft YaHei", 8), anchor="w",
                     justify="left").pack(fill="x",
                     padx=int(12 * ds), pady=(0, int(6 * ds)))
            div(g)
            add_toggle(g, "隐身上线（不出现在他人可见名单）", inv_var, _on_invis_cmd)
            tk.Label(g, text="开启后仅自己和服务器管理员可见，聊天照常", fg=sub,
                     bg=card, font=("Microsoft YaHei", 8), anchor="w",
                     justify="left").pack(fill="x", padx=int(12 * ds), pady=(0, int(4 * ds)))
            div(g)
            add_field_row(g, "在线状态", status_var, _status_labels, _on_status_pick)
            tk.Label(g, text="在线/离开/忙碌，与隐身正交：隐身控制是否出现在名单，状态控制点色",
                     fg=sub, bg=card, font=("Microsoft YaHei", 8), anchor="w",
                     justify="left").pack(fill="x", padx=int(12 * ds), pady=(0, int(4 * ds)))
            div(g)
            add_field_row(g, "新消息提示音", sound_var, _sound_labels, _on_sound_pick)
            add_field_row(g, "交互模式", mode_var, _mode_labels, _on_mode_pick)
            div(g)
            add_toggle(g, "伪装态私聊自动回复（老板键）", auto_reply_var, _on_auto_toggle)
            add_row(g, "自动回复文案…", _on_auto_text)
            add_field_row(g, "同人冷却", auto_cd_var, _ar_cd_labels, _on_auto_cd,
                          get_enabled=lambda: bool(auto_reply_var.get()))
            tk.Label(g, text="仅伪装态生效：1v1 首条消息自动回复，同一人冷却内不重复；"
                             "带 auto 标记的消息不再触发，群/频道不回复",
                     fg=sub, bg=card, font=("Microsoft YaHei", 8), anchor="w",
                     justify="left").pack(fill="x", padx=int(12 * ds),
                                          pady=(0, int(4 * ds)))

        def pg_appearance(P):
            nonlocal skin_cv
            g = tk.Frame(P, bg=card); g.pack(fill="x", padx=0, pady=(int(6 * ds), 0))
            skin_cv = add_field_row(g, "皮肤", skin_var, _skin_labels, _skin_to_key,
                                    get_enabled=lambda: not follow_var.get())
            add_toggle(g, "跟随系统深浅", follow_var, _follow_on)
            div(g)
            add_field_row(g, "聊天主题", ctheme_var, _ctheme_labels,
                          self._on_chat_theme_pick)
            add_slider_row(g, "背景透明度", 0.60, 1.0, alpha_var, _alpha_on)
            add_field_row(g, "伪装标题", camo_var, _camo_labels, _on_camo_pick)
            div(g)
            add_field_row(g, "字体大小", font_var, list(_FONT_LABELS), _on_font_pick)
            div(g)
            add_toggle(g, "无边框圆角窗（重启生效）", f_cnt,
                       lambda: self._prefs.set("frameless", bool(f_cnt.get())))
            add_toggle(g, "对话框暗化遮罩", s_cnt,
                       lambda: self._prefs.set("scrim", bool(s_cnt.get())))

        def pg_privacy(P):
            g = tk.Frame(P, bg=card); g.pack(fill="x", padx=0, pady=(int(6 * ds), 0))
            add_row(g, "本机解锁码…", self._set_passcode_dialog)
            add_row(g, "昵称密码…", self._set_nick_pwd_dialog)
            div(g)
            add_row(g, "快捷键设置…", self._shortcut_settings)
            div(g)
            add_toggle(g, "敏感词打码（仅本机显示）", guard_var, _on_guard_toggle)
            add_row(g, "敏感词表…", self._edit_guard_words)
            add_field_row(g, "打码时段", guard_hours_var, self._GUARD_HOUR_LABELS,
                          self._on_guard_hours_pick,
                          get_enabled=lambda: bool(guard_var.get()))
            tk.Label(g, text="命中词在气泡内遮盖，点击可揭示；不影响消息存储、搜索与复制",
                     fg=sub, bg=card, font=("Microsoft YaHei", 8), anchor="w",
                     justify="left").pack(fill="x", padx=int(12 * ds),
                                          pady=(0, int(4 * ds)))

        def pg_account(P):
            g = tk.Frame(P, bg=card); g.pack(fill="x", padx=0, pady=(int(6 * ds), 0))
            add_row(g, "切换账号…", self.request_switch_account)
            if self.core.is_admin:                     # R53：管理员面板（仅管理员可见）
                div(g)
                add_row(g, "🧹 管理员面板…", self._admin_panel, danger=True)

        def pg_server(P):
            tk.Label(P, text="发现的服务器（双击连接）", fg=sub, bg=card, font=f,
                     anchor="w").pack(fill="x", padx=int(12 * ds), pady=(int(10 * ds), int(2 * ds)))
            box = tk.Listbox(P, font=f, height=4, bg=inp, fg=fg, relief="flat",
                             highlightthickness=1, highlightbackground=border,
                             selectbackground=acc, selectforeground="#ffffff")
            box.pack(fill="x", padx=int(12 * ds))
            self._refill_disco_box(box)
            box.bind("<Double-Button-1>", lambda e: self._connect_to(box, dlg))
            def _fresh():
                self._refill_disco_box(box)
            ref_cv = tk.Canvas(P)
            make_btn(ref_cv, "刷新", _fresh, w=int(110 * ds), bg=card)
            ref_cv.pack(anchor="w", padx=int(12 * ds), pady=(int(4 * ds), int(2 * ds)))
            div(P)
            # 手动连接（防火墙拦广播时兜底）
            row = tk.Frame(P, bg=card)
            row.pack(fill="x", padx=int(12 * ds), pady=(int(8 * ds), int(2 * ds)))
            def B_entry(width):
                e = tk.Entry(row, font=f, width=width, bg=inp, fg=fg,
                             insertbackground=fg, relief="flat",
                             highlightthickness=1, highlightbackground=border)
                return e
            tk.Label(row, text="IP:", bg=card, fg=sub, font=f).pack(side="left")
            ip_ent = B_entry(13)
            ip_ent.insert(0, self.core.host)
            ip_ent.pack(side="left", padx=2)
            tk.Label(row, text="端口:", bg=card, fg=sub, font=f).pack(side="left")
            port_ent = B_entry(6)
            port_ent.insert(0, str(self.core.port))
            port_ent.pack(side="left", padx=2)
            def _manual() -> None:
                port = None
                try:
                    port = int(port_ent.get().strip() or 0) or None
                except ValueError:
                    pass
                self.core.set_host(ip_ent.get().strip(), port)
                self.core.drop()
                self._close_settings()
            conn_cv = tk.Canvas(row)
            make_btn(conn_cv, "连接", _manual, w=int(80 * ds), bg=card)
            conn_cv.pack(side="left", padx=4)

        _PAGES = {"通用": pg_general, "外观": pg_appearance,
                  "隐私": pg_privacy, "账号": pg_account, "服务器": pg_server}
        _ORDER = ["通用", "外观", "隐私", "账号", "服务器"]
        if not hasattr(self, "_settings_page") or self._settings_page not in _PAGES:
            self._settings_page = "通用"

        # —— 左侧分类导航（点击切换子页，当前项高亮） ——
        nav_rows = {}
        def _nav_redraw():
            for name, ncv in nav_rows.items():
                ncv.delete("all")
                ww = ncv.winfo_width() or int(160 * ds)
                act = (name == self._settings_page)
                if act:
                    rrect(ncv, 2, 2, ww - 2, int(30 * ds) - 2, 8 * ds,
                          fill=dp.get("doc_h", border), outline="")
                ncv.create_text(int(14 * ds), int(15 * ds), text=name,
                                fill=(fg if act else sub_c), font=f, anchor="w")
        def _show(name):
            self._settings_page = name
            for ch in sw.winfo_children():
                ch.destroy()
            _PAGES[name](sw)
            _nav_redraw()
        for name in _ORDER:
            cv = tk.Canvas(nav, height=int(32 * ds), bg=win, highlightthickness=0, bd=0)
            cv.pack(fill="x", padx=4, pady=2)
            cv.bind("<Button-1>", lambda e, n=name: _show(n))
            nav_rows[name] = cv
        tk.Frame(nav, bg=border, height=1).pack(fill="x", padx=12, pady=4)
        tk.Label(nav, text="摸鱼助手", fg=sub_c, bg=win, font=("Microsoft YaHei", 8),
                 anchor="w").pack(fill="x", padx=14)

        _show(self._settings_page)

    # ---------- R53 管理员面板（仅管理员可见，最高清理权限） ----------
    def _admin_panel(self) -> None:
        """管理员面板：清空全部聊天记录 + 在线用户踢人/清空其消息（快捷入口）。"""
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)                        # R43A1 弹窗淡入
        dlg.title("管理员面板")
        dlg.geometry("420x520")
        dlg.attributes("-topmost", True)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "管理员面板")
        f = self._f
        tk.Label(dlg, text="🧹 管理员 · 最高清理权限",
                 fg="#b71c1c", font=(FONT_FAMILY, FONT_SIZE + 2, "bold"),
                 anchor="w").pack(fill="x", padx=10, pady=(10, 2))
        tk.Label(dlg, text="以下操作对全员生效，且不可恢复，请谨慎使用。",
                 fg=self._dp["sub"], font=f, anchor="w").pack(fill="x", padx=10,
                                                              pady=(0, 8))

        tk.Button(dlg, text="🧹 清空全部聊天记录（全员）",
                  font=f, bg="#fdecea", fg="#b71c1c",
                  activebackground="#fbdcd9", activeforeground="#b71c1c",
                  command=self._admin_clear_all).pack(fill="x", padx=10, pady=4)
        tk.Button(dlg, text="👥 群管理（增删成员 / 解散群）", font=f,
                  command=self._admin_groups_panel).pack(fill="x", padx=10, pady=4)
        tk.Button(dlg, text="退役结果与查询", font=f, command=self._retirement_results).pack(fill="x", padx=10, pady=4)
        tk.Label(dlg, text="全部账号（●在线 ○离线，支持离线管理）", fg=self._dp["sub"],
                 font=f, anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        tk.Button(dlg, text="🔍 双击账号 → 进入「单个用户操作」",
                  font=f, fg="#5b6af0", bg=self._dp["win"],
                  activebackground="#eef0ff", cursor="hand2",
                  command=lambda: self._admin_user_ops(box)).pack(
            fill="x", padx=10, pady=(4, 2))
        box = tk.Listbox(dlg, font=f, height=11)
        box.bind("<Double-Button-1>", lambda _e: self._admin_user_ops(box))
        box.pack(fill="both", expand=True, padx=10)
        btns = tk.Frame(dlg)
        btns.pack(fill="x", padx=10, pady=6)
        for col in range(2):
            btns.grid_columnconfigure(col, weight=1)
        for index, (label, command) in enumerate((
                ("踢下线", lambda: self._admin_panel_kick(box, dlg)),
                ("清空其全部消息", lambda: self._admin_panel_clear(box)),
                ("隐身 / 显身", lambda: self._admin_panel_invis(box)),
                ("账号退役…", lambda: self._admin_panel_del(box)))):
            tk.Button(btns, text=label, font=f, command=command).grid(
                row=index//2, column=index%2, sticky="ew", padx=2, pady=2)

        def _reload() -> None:
            self._reload_admin_rows(box)

        _reload()
        # 主动刷新：仅在右侧操作台操作后触发，不打扰轮询
        def _safe_reload() -> None:
            if not dlg.winfo_exists():
                return
            try:
                _reload()
            except Exception:
                pass
        self._admin_reload = _safe_reload

    def _admin_clear_all(self) -> None:
        from widgets import dialogbox
        if not dialogbox.ask_yesno("管理员操作",
                                   "确认清空全部聊天记录？\n（全员本地历史将同步"
                                   "删除，不可恢复）", parent=self.root):
            return
        self.core.send_admin_clear_all()
        self._append_sys("🧹 已向服务器提交：清空全部聊天记录")

    @staticmethod
    def _admin_selected(box):
        selection = box.curselection()
        rows = getattr(box, "_admin_rows", ())
        return rows[selection[0]] if selection and selection[0] < len(rows) else None

    def _reload_admin_rows(self, box) -> None:
        selected = self._admin_selected(box)
        selected_uid = selected[0] if selected else None
        fraction = box.yview()[0] if box.size() else 0.0
        roster, known = dict(self.core.roster), dict(self.core.known)
        users = {**known, **roster}
        rows = tuple(sorted(((int(uid), str(data.get("nick") or f"用户{uid}"), uid in roster,
                              bool(data.get("invisible"))) for uid, data in users.items()),
                            key=lambda row: (row[1], row[0])))
        box.delete(0, "end")
        box._admin_rows = rows
        for index, (uid, nick, online, invisible) in enumerate(rows):
            box.insert("end", f"{'👻 ' if invisible else ''}{'●' if online else '○'} {nick}  #{uid}")
            if uid == selected_uid:
                box.selection_set(index)
        box.yview_moveto(fraction)

    def _admin_panel_kick(self, box, dlg) -> None:
        row = self._admin_selected(box)
        if row:
            dlg.destroy()
            self._admin_kick(row[0])

    def _admin_panel_clear(self, box) -> None:
        row = self._admin_selected(box)
        if row:
            self._admin_clear_uid(row[0])

    def _admin_panel_invis(self, box) -> None:
        row = self._admin_selected(box)
        if not row:
            return
        uid, nick, _online, invisible = row
        self.core.send_admin_force_invis(uid, not invisible)
        self._append_sys(f"已请求让 @{nick} {'显身' if invisible else '隐身'}")

    def _admin_panel_del(self, box) -> None:
        row = self._admin_selected(box)
        if row:
            self._confirm_del_uid(row[0], row[1])


    def _admin_user_ops(self, box) -> None:
        """R58B：点进/双击单个用户，弹出该用户独立操作台
        （查看详情 / 踢下线 / 清空其消息 / 隐身显身 / 删除账号）。"""
        from widgets import dialogbox
        row = self._admin_selected(box)
        if not row:
            self._append_sys("请先在列表里选中一个用户")
            return
        uid, nick, _online, _invisible = row
        if uid == self.core.uid:
            self._append_sys("不能对自己执行操作")
            return
        online = uid in self.core.roster
        cur_inv = bool((self.core.roster.get(uid) or {}).get("invisible"))

        dlg = tk.Toplevel(self.root); ui_fx.fade_in(dlg)
        dlg.title(f"用户操作 · {nick}")
        dlg.geometry("320x360+" + str(self.root.winfo_x() + 220) + "+"
                     + str(self.root.winfo_y() + 80))
        dlg.attributes("-topmost", True)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, f"用户操作 · {nick}")
        f = self._f
        dp = self._dp
        tk.Label(dlg, text=f"👤 {nick}  #{uid}", fg="#5b6af0",
                 font=(FONT_FAMILY, FONT_SIZE + 2, "bold"), anchor="w",
                 bg=dp["win"]).pack(fill="x", padx=14, pady=(10, 2))
        if cur_inv:
            state = "● 在线（当前隐身）"
        else:
            state = "● 在线" if online else "○ 离线"
        tk.Label(dlg, text=state, font=f, fg=dp["sub"], anchor="w",
                 bg=dp["win"]).pack(fill="x", padx=14, pady=(0, 8))

        def _mk(text, cmd, danger=False, close=True, bold=False):
            """实心按钮：背景明显区别于窗口、白字，一眼可点。"""
            ft = (FONT_FAMILY, FONT_SIZE, "bold") if bold else f
            if danger:
                bg, fg, abg, afg = "#d63a3a", "#ffffff", "#b62a2a", "#ffffff"
            else:
                bg, fg, abg, afg = "#5b6af0", "#ffffff", "#434dc0", "#ffffff"
            def _go():
                cmd()
                self._refresh_admin_after()
                if close:
                    try:
                        dlg.destroy()
                    except Exception:
                        pass
            tk.Button(dlg, text=text, font=ft, bg=bg, fg=fg,
                      activebackground=abg, activeforeground=afg,
                      anchor="w", padx=14, pady=6, relief="flat", bd=0,
                      cursor="hand2", command=_go).pack(fill="x", padx=14, pady=3)

        _mk("👤 查看详情（所属群 · 在线状态）",
            lambda: self.core.send_admin_user_groups(uid))
        _mk("🔨 踢下线", lambda: self._admin_kick(uid))
        _mk("🧹 清空其全部消息", lambda: self._admin_clear_uid(uid))
        _mk("👻 隐身 / 显身（当前 " + ("隐身" if cur_inv else "显身") + "）",
            lambda: self.core.send_admin_force_invis(uid, not cur_inv))
        _mk("账号退役（昵称保留）…",
            lambda: self._confirm_del_uid(uid, nick), danger=True, close=True)

    def _confirm_del_uid(self, uid: int, nick: str) -> None:
        """Both administrator entry points use the same identity and M1 promise."""
        from widgets import dialogbox
        if uid == self.core.uid:
            self._append_sys("不能退役当前管理员自身")
            return
        scope = self.core.retirement_scope
        epoch = self.core.connection_epoch
        if scope is None:
            self._append_sys("请先连接目标服务器并以系统管理员身份登录")
            return
        if not dialogbox.ask_yesno(
                "账号退役",
                f"确认退役「{nick}  #{uid}」？\n服务器：{scope.host}:{scope.port}\n\n"
                "身份将停止使用，昵称仍保留；按既有规则清理本人状态和作者消息、移出群聊。\n"
                "共享内容与他人副本不会全部删除。只有服务器持久确认后才算完成。\n\n"
                "确认后会先核对目标；失败或结果未知时请在退役结果中查询。",
                parent=self.root):
            return
        if self.core.connection_epoch != epoch or self.core.retirement_scope != scope:
            self._append_sys("确认期间连接或管理员身份已改变，请重新核对目标")
            return
        self._retirement_results()
        self.core.send_admin_user_del(uid, expected_nick=nick, expected_scope=scope, expected_epoch=epoch)
        self._refresh_retirement_results()

    def _on_retirement_status(self, _ev) -> None:
        # Called only by the Tk event pump. Network callbacks never create UI.
        self._refresh_retirement_results()
        reload_rows = getattr(self, "_admin_reload", None)
        if reload_rows:
            reload_rows()

    def _retirement_results(self) -> None:
        from tkinter import ttk
        old = getattr(self, "_retirement_ui", None)
        if old and old["dlg"].winfo_exists():
            old["dlg"].lift()
            self._refresh_retirement_results()
            return
        dp = self._dp
        dlg = tk.Toplevel(self.root)
        dlg.title("账号退役 · 结果与查询")
        dlg.geometry("760x580")
        dlg.minsize(640, 480)
        dlg.configure(bg=dp["win"])
        # An opaque system-framed result window keeps status readable.
        body = tk.Frame(dlg, bg=dp["win"])
        body.pack(fill="both", expand=True, padx=16, pady=16)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(3, weight=1)
        tk.Label(body, text="退役结果", font=(FONT_FAMILY, FONT_SIZE+3, "bold"),
                 bg=dp["win"], fg=dp.get("fg", "#202b27"), anchor="w").grid(row=0, column=0, sticky="ew")
        hint = tk.Label(body, text="发送、名单变化和持久确认是不同阶段。关闭窗口不会取消服务器处理。",
                        bg=dp["win"], fg=dp["sub"], font=self._f, anchor="w", wraplength=580)
        hint.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        query_row = tk.Frame(body, bg=dp["win"])
        query_row.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        tk.Label(query_row, text="UID 或昵称", font=self._f, bg=dp["win"], fg=dp.get("fg", "#202b27")).pack(side="left", padx=(0, 8))
        target = tk.Entry(query_row, font=self._f)
        target.pack(side="left", fill="x", expand=True, padx=(0, 8))
        query_button = tk.Button(query_row, text="查询服务器状态", font=self._f, command=self._retirement_manual_query)
        query_button.pack(side="left")
        target.bind("<Return>", lambda _event: self._retirement_manual_query())
        table_area = tk.Frame(body, bg=dp["win"])
        table_area.grid(row=3, column=0, sticky="nsew")
        style = ttk.Style(dlg)
        style.configure("Retirement.Treeview", font=self._f, rowheight=30)
        table = ttk.Treeview(table_area, columns=("target", "server", "phase"), show="headings",
                             selectmode="browse", height=6, style="Retirement.Treeview")
        for column, title, width in (("target", "目标", 190), ("server", "服务端结果", 160), ("phase", "当前请求", 220)):
            table.heading(column, text=title)
            table.column(column, width=width, minwidth=100, stretch=True)
        scrollbar = ttk.Scrollbar(table_area, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        table.pack(fill="both", expand=True)
        detail_area = tk.Frame(body, bg=dp["win"])
        detail_area.grid(row=4, column=0, sticky="ew", pady=(12, 8))
        detail = tk.Text(detail_area, height=5, font=self._f, wrap="word", relief="solid", bd=1,
                         bg=dp["win"], fg=dp.get("fg", "#202b27"), padx=10, pady=8)
        detail_scroll = ttk.Scrollbar(detail_area, orient="vertical", command=detail.yview)
        detail.configure(yscrollcommand=detail_scroll.set, state="disabled")
        detail_scroll.pack(side="right", fill="y")
        detail.pack(fill="both", expand=True)
        actions = tk.Frame(body, bg=dp["win"])
        actions.grid(row=5, column=0, sticky="ew")
        buttons = {}
        for action, label in (("query", "查询所选事项"), ("retry", "重试原操作…"), ("cancel", "取消本地预核对")):
            button = tk.Button(actions, text=label, font=self._f,
                               command=lambda operation=action: self._retirement_selected_action(operation))
            button.pack(side="left", padx=(0, 8))
            buttons[action] = button
        tk.Button(actions, text="更新视图", font=self._f, command=self._refresh_retirement_results).pack(side="right")
        footer = tk.Label(body, font=self._f, bg=dp["win"], fg=dp["sub"], anchor="w", wraplength=580)
        footer.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        body.bind("<Configure>", lambda event: (hint.config(wraplength=max(100, event.width)),
                                                footer.config(wraplength=max(100, event.width))))
        self._retirement_ui = {"dlg": dlg, "table": table, "target": target, "query_button": query_button,
                               "detail": detail, "buttons": buttons, "footer": footer, "records": {}}
        table.bind("<<TreeviewSelect>>", lambda _event: self._render_retirement_selection())
        self._refresh_retirement_results()
        target.focus_set()

    def _retirement_manual_query(self) -> None:
        ui = getattr(self, "_retirement_ui", None)
        if ui and ui["dlg"].winfo_exists():
            self.core.query_admin_retirement(ui["target"].get())
            self._refresh_retirement_results()

    _RETIRE_STATES = {"pending": "处理中 · 未持久确认", "failed": "持久处理失败",
                      "unknown": "持久结果未知", "confirmed": "已持久确认"}
    _RETIRE_PHASES = {"idle": "未开始", "preflight": "核对中 · 未发退役命令", "sending": "正在发送",
                      "waiting": "已发送 · 等待结果", "querying": "正在查询", "query_failed": "查询未完成",
                      "rejected": "本次请求被拒绝", "unverified": "当前连接尚未核验", "cancelled": "本地预核对已取消",
                      "no_record": "未报告退役记录", "pending": "等待持久结果", "failed": "请查看失败信息",
                      "unknown": "结果未知 · 仅可查询", "confirmed": "确认完成"}

    def _refresh_retirement_results(self) -> None:
        ui = getattr(self, "_retirement_ui", None)
        if not ui or not ui["dlg"].winfo_exists():
            return
        records = self.core.retirement_snapshot()
        table = ui["table"]
        selection = table.selection()
        selected = selection[0] if selection else None
        current = {record.intent_id: record for record in records}
        for row in table.get_children():
            if row not in current:
                table.delete(row)
        for record in records:
            receipt = record.confirmed or record.receipt
            server = self._RETIRE_STATES.get(receipt.status, "未收到结果") if receipt else "未收到结果"
            if receipt and not record.current_verified:
                server += "（历史）"
            values = (f"{record.nick or record.target}  #{record.uid or '待解析'}", server,
                      self._RETIRE_PHASES.get(record.phase, record.phase))
            if table.exists(record.intent_id):
                table.item(record.intent_id, values=values)
            else:
                table.insert("", "end", iid=record.intent_id, values=values)
        ui["records"] = current
        if selected in current:
            table.selection_set(selected)
        elif current:
            table.selection_set(next(reversed(current)))
        online = self.core.retirement_scope is not None
        ui["query_button"].config(state="normal" if online else "disabled")
        ui["footer"].config(text=f"本次客户端 {len(records)} / 64 条临时记录；历史事项不跨进程保存。"
                            + ("" if online else " 当前未以管理员身份连接。"))
        self._render_retirement_selection()

    def _render_retirement_selection(self) -> None:
        ui = self._retirement_ui
        selection = ui["table"].selection()
        record = ui["records"].get(selection[0]) if selection else None
        for action, attribute in (("query", "can_query"), ("retry", "can_retry"), ("cancel", "can_cancel")):
            ui["buttons"][action].config(state="normal" if record and getattr(record, attribute) else "disabled")
        text = "输入 UID 或昵称可查询已从名单消失的目标。查询不会发起退役。"
        if record:
            text = (f"目标：{record.nick or record.target} / UID {record.uid or '待解析'}\n"
                    f"服务器：{record.scope.host}:{record.scope.port} · 管理员 UID {record.scope.admin_uid}\n"
                    f"当前请求：{self._RETIRE_PHASES.get(record.phase, record.phase)}\n")
            receipt = record.confirmed or record.receipt
            if receipt:
                origin = {"written": "写入完成", "reconciled_current_json": "当前保存状态对账确认",
                          "restored_valid_json": "从已有保存状态恢复"}.get(receipt.origin, "未提供")
                text += (f"服务端结果：{self._RETIRE_STATES[receipt.status]}"
                         + ("（历史，本连接尚未核验）" if not record.current_verified else "")
                         + f"\n操作号：{receipt.operation_id}\n确认来源：{origin}\n")
                if receipt.persistence_phase is None:
                    text += "撤权阶段：未提供撤权阶段（旧服务器结果）\n"
                else:
                    phase = {"intent": "退役意图", "snapshot": "状态快照"}[receipt.persistence_phase]
                    effect = {
                        "not_started": "尚未开始撤权",
                        "revoked": "已撤销身份权限；持久结果以上方服务端结果为准",
                        "unverified": "撤权效果未核实；服务器恢复后请重新查询",
                    }[receipt.identity_effect]
                    text += f"持久阶段：{phase}\n身份效果：{effect}\n"
                if receipt.content_sha256 is not None:
                    text += f"内容摘要：{receipt.content_sha256}\n"
                if receipt.content_length is not None:
                    text += f"内容长度：{receipt.content_length} bytes\n"
                if receipt.failed_stage or receipt.error_code:
                    text += f"失败阶段：{receipt.failed_stage or '未提供'} · {receipt.error_code or '未提供'}\n"
            if record.diagnostic:
                text += f"提示：{record.diagnostic}\n"
        ui["detail"].config(state="normal")
        ui["detail"].delete("1.0", "end")
        ui["detail"].insert("1.0", text)
        ui["detail"].config(state="disabled")

    def _retirement_selected_action(self, action) -> None:
        ui = self._retirement_ui
        selection = ui["table"].selection()
        record = ui["records"].get(selection[0]) if selection else None
        if not record:
            return
        if action == "query":
            self.core.query_admin_retirement(intent_id=record.intent_id)
        elif action == "cancel":
            self.core.cancel_admin_retirement(record.intent_id)
        elif action == "retry":
            from widgets import dialogbox
            if not record.can_retry or not dialogbox.ask_yesno(
                    "重试原退役操作", f"为「{record.nick} #{record.uid}」重试保存原操作？\n"
                    "不会重新执行一次身份清理；仍以服务器返回结果为准。", parent=ui["dlg"]):
                return
            self.core.retry_admin_retirement(record.intent_id)
        self._refresh_retirement_results()


    def _refresh_admin_after(self) -> None:
        """操作后主动刷新左侧账号列表：立即刷新 + 延迟两拍，等服务器状态同步。
        不再做常驻轮询，避免打扰用户浏览。"""
        ref = getattr(self, "_admin_reload", None)
        if not ref:
            return

        def _go() -> None:
            try:
                ref()
            except Exception:
                pass

        _go()
        for t in (800, 1800):
            self.root.after(t, _go)

    # ---------- 系统管理员群管理（服务端逐项校验 is_admin） ----------
    def _admin_groups_panel(self) -> None:
        """系统管理员：群管理面板入口（拉取全量群目录+成员花名册）。"""
        old = getattr(self, "_admin_grp_ui", None)
        if old and old["dlg"].winfo_exists():
            old["dlg"].destroy()
        self._admin_groups_data = []
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)
        dlg.title("群管理 · 系统管理员")
        dlg.geometry("480x540")
        dlg.attributes("-topmost", True)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "群管理 · 系统管理员")
        f = self._f
        self._admin_grp_ui = {"dlg": dlg}

        tk.Label(dlg, text="👥 群管理 · 系统管理员",
                 fg="#b71c1c", font=(FONT_FAMILY, FONT_SIZE + 2, "bold"),
                 anchor="w").pack(fill="x", padx=10, pady=(10, 2))
        tk.Label(dlg, text="选中群查看成员；可增删成员或直接解散群。",
                 fg=self._dp["sub"], font=f, anchor="w").pack(fill="x", padx=10,
                                                              pady=(0, 6))

        tk.Label(dlg, text="群聊", fg=self._dp["sub"], font=f, anchor="w").pack(
            fill="x", padx=10)
        grp = tk.Listbox(dlg, font=f, height=7)
        grp.pack(fill="x", padx=10, pady=(0, 4))
        self._admin_grp_ui["grp"] = grp

        tk.Label(dlg, text="成员（选中成员可移除）", fg=self._dp["sub"], font=f,
                 anchor="w").pack(fill="x", padx=10)
        mem = tk.Listbox(dlg, font=f, height=8)
        mem.pack(fill="both", expand=True, padx=10)
        self._admin_grp_ui["mem"] = mem

        btns = tk.Frame(dlg)
        btns.grid_columnconfigure((1, 2, 3, 4), weight=1, uniform="b")
        btns.pack(fill="x", padx=10, pady=6)
        tk.Button(btns, text="➕ 加成员", font=f,
                  command=self._admin_grp_add).grid(row=0, column=0,
                                                    padx=2, sticky="ew")
        tk.Button(btns, text="⌨ 按昵称加", font=f,
                  command=self._admin_grp_add_nick).grid(row=0, column=1,
                                                         padx=2, sticky="ew")
        tk.Button(btns, text="➖ 移除", font=f,
                  command=self._admin_grp_remove).grid(row=0, column=2,
                                                       padx=2, sticky="ew")
        tk.Button(btns, text="🔍 所属群", font=f,
                  command=self._admin_grp_user_groups).grid(row=0, column=3,
                                                             padx=2, sticky="ew")
        tk.Button(btns, text="💣 解散", font=f, bg="#fdecea", fg="#b71c1c",
                  activebackground="#fbdcd9", activeforeground="#b71c1c",
                  command=self._admin_grp_dissolve).grid(row=0, column=4,
                                                         padx=2, sticky="ew")

        grp.bind("<<ListboxSelect>>",
                 lambda e: self._admin_grp_refresh_members())
        self.core.send_admin_groups()          # 拉取目录，回帧后填充

    def _on_admin_groups_roster(self, ev):
        """系统管理员：群目录回帧 → 填充群管理面板。"""
        self._admin_groups_data = ev.get("groups", [])
        ui = getattr(self, "_admin_grp_ui", None)
        if not (ui and ui["dlg"].winfo_exists()):
            return
        grp = ui["grp"]
        if grp.size():
            grp.delete(0, "end")
        for g in self._admin_groups_data:
            kind = g.get("kind", "")
            tag = "公共" if g.get("public") else ("群" if kind else "私")
            grp.insert("end",
                       f"[{tag}] {g.get('name', '')}  "
                       f"({g.get('member_count', 0)}人/{g.get('member_max', '?')})")
        self._admin_grp_refresh_members()

    def _admin_grp_refresh_members(self) -> None:
        ui = getattr(self, "_admin_grp_ui", None)
        if not (ui and ui["dlg"].winfo_exists()):
            return
        grp, mem = ui["grp"], ui["mem"]
        mem.delete(0, "end")
        sel = grp.curselection()
        if not sel or sel[0] >= len(self._admin_groups_data):
            return
        g = self._admin_groups_data[sel[0]]
        for m in sorted(g.get("members", []), key=lambda x: x.get("nick", "")):
            tag = "👑" if m["uid"] == g.get("owner") else "🛡" \
                if m["uid"] in g.get("admins", []) else ""
            inv = "👻 " if m.get("invisible") else ""   # R57：管理员可见隐身上线者
            mem.insert("end", f"{tag}{inv}{m.get('nick', '')}  #{m['uid']}")

    def _admin_grp_add(self) -> None:
        """系统管理员：向选中群添加成员（从未在群内且在线的花名册里挑选）。"""
        ui = getattr(self, "_admin_grp_ui", None)
        if not (ui and ui["dlg"].winfo_exists()):
            return
        sel = ui["grp"].curselection()
        if not sel or sel[0] >= len(self._admin_groups_data):
            self._append_sys("请先选择一个群")
            return
        g = self._admin_groups_data[sel[0]]
        gid = g["gid"]; in_ids = {m["uid"] for m in g.get("members", [])}
        pw = tk.Toplevel(self.root); ui_fx.fade_in(pw)
        pw.title(f"加成员 → {g['name']}"); pw.geometry("360x360")
        pw.attributes("-topmost", True); pw.configure(bg=self._dp["win"])
        self._apply_apple_dialog(pw, "加群成员")
        f = self._f
        tk.Label(pw, text="选择要加入的成员：", font=f, fg=self._dp["sub"],
                 anchor="w").pack(fill="x", padx=10, pady=(10, 4))
        box = tk.Listbox(pw, font=f)
        box.pack(fill="both", expand=True, padx=10)
        for u in sorted(self.core.roster.values(), key=lambda x: x.get("nick", "")):
            if u["uid"] not in in_ids:
                box.insert("end", f"{u.get('nick', '')}  #{u['uid']}")
        tk.Button(pw, text="➕ 加入该群", font=f,
                  command=lambda: self._admin_grp_add_pick(pw, gid, box)).pack(
            fill="x", padx=10, pady=6)

    def _admin_grp_add_pick(self, pw, gid, box) -> None:
        sel = box.curselection()
        if not sel:
            return
        uid = int(box.get(sel[0]).split("#")[1])
        pw.destroy()
        self.core.send_admin_group_set("add", gid, uid)
        self._append_sys(f"🕓 已请求把 #{uid} 加入群 {gid}")
        self.core.send_admin_groups()          # 刷新目录

    def _admin_grp_remove(self) -> None:
        ui = getattr(self, "_admin_grp_ui", None)
        if not (ui and ui["dlg"].winfo_exists()):
            return
        gsel = ui["grp"].curselection()
        msel = ui["mem"].curselection()
        if not gsel or not msel or gsel[0] >= len(self._admin_groups_data):
            self._append_sys("请先选择群和要移除的成员")
            return
        g = self._admin_groups_data[gsel[0]]
        if msel[0] >= len(g.get("members", [])):
            return
        uid = g["members"][msel[0]]["uid"]
        if uid == g.get("owner"):
            self._append_sys("⚠ 不能移除群主，请先解散群或转移")
            return
        self.core.send_admin_group_set("remove", gid=g["gid"], uid=uid)
        self._append_sys(f"🕓 已请求从群 {g['gid']} 移除 #{uid}")
        self.core.send_admin_groups()

    def _admin_grp_dissolve(self) -> None:
        from widgets import dialogbox
        ui = getattr(self, "_admin_grp_ui", None)
        if not (ui and ui["dlg"].winfo_exists()):
            return
        sel = ui["grp"].curselection()
        if not sel or sel[0] >= len(self._admin_groups_data):
            self._append_sys("请先选择一个群")
            return
        g = self._admin_groups_data[sel[0]]
        if g.get("public"):
            self._append_sys("⚠ 公共频道是系统频道，不支持解散")
            return
        if not dialogbox.ask_yesno("解散群",
                                   f"确认解散群「{g['name']}」？\n"
                                   f"（将移除全部成员且不可恢复）", parent=self.root):
            return
        self.core.send_admin_group_set("dissolve", gid=g["gid"])
        self._append_sys(f"🕓 已请求解散群 {g['gid']}")
        self.core.send_admin_groups()

    def _admin_grp_add_nick(self) -> None:
        """系统管理员：按昵称/uid 加入任意群（支持离线用户，服务器权威校验）。"""
        ui = getattr(self, "_admin_grp_ui", None)
        if not (ui and ui["dlg"].winfo_exists()):
            return
        sel = ui["grp"].curselection()
        if not sel or sel[0] >= len(self._admin_groups_data):
            self._append_sys("请先选择一个群")
            return
        g = self._admin_groups_data[sel[0]]
        from widgets import dialogbox
        s = dialogbox.ask_string("按昵称加入",
                                 f"输入要加入群「{g['name']}」的昵称或uid：\n"
                                 f"（不在线也能加，需服务器已知该用户）",
                                 parent=self.root)
        if not s or not s.strip():
            return
        target = s.strip()
        try:
            target = int(target)
        except ValueError:
            pass
        self.core.send_admin_group_set("add", g["gid"], target)
        self._append_sys(f"🕓 已请求把「{s}」加入群 {g['gid']}")
        self.core.send_admin_groups()

    def _admin_grp_user_groups(self) -> None:
        """系统管理员：查看选中成员所属的全部群+在线状态。"""
        ui = getattr(self, "_admin_grp_ui", None)
        if not (ui and ui["dlg"].winfo_exists()):
            return
        gsel = ui["grp"].curselection()
        msel = ui["mem"].curselection()
        if not gsel or not msel or gsel[0] >= len(self._admin_groups_data):
            self._append_sys("请先在成员列表选中一个人")
            return
        g = self._admin_groups_data[gsel[0]]
        if msel[0] >= len(g.get("members", [])):
            return
        uid = g["members"][msel[0]]["uid"]
        self.core.send_admin_user_groups(uid)
        self._append_sys(f"🕓 正在查询 #{uid} 的所属群…")

    def _on_admin_user_info(self, ev) -> None:
        """系统管理员：某人信息+所属群 回帧 → 用户详情框。"""
        uid = ev.get("uid"); nick = ev.get("nick", ""); online = ev.get("online")
        groups = ev.get("groups", [])
        dlg = tk.Toplevel(self.root)
        ui_fx.fade_in(dlg)
        dlg.title("用户详情 · 系统管理员")
        dlg.geometry("360x420")
        dlg.attributes("-topmost", True)
        dlg.configure(bg=self._dp["win"])
        self._apply_apple_dialog(dlg, "用户详情 · 系统管理员")
        f = self._f
        status = "● 在线" if online else "○ 离线"
        color = "#2e7d32" if online else "#888"
        if ev.get("invisible"):                    # R57：管理员可见隐身态
            status += "  👻 隐身"
            color = "#8e24aa"
        tk.Label(dlg, text=f"👤 {nick}  #{uid}",
                 fg="#b71c1c", font=(FONT_FAMILY, FONT_SIZE + 2, "bold"),
                 anchor="w").pack(fill="x", padx=10, pady=(10, 2))
        tk.Label(dlg, text=f"状态：{status}", fg=color, font=f,
                 anchor="w").pack(fill="x", padx=10, pady=(0, 2))
        if ev.get("correlated") is False:
            tk.Label(dlg, text="旧服务器详情未关联；不能作为退役确认", fg=self._dp["sub"],
                     font=f, anchor="w").pack(fill="x", padx=10, pady=(2, 4))
        tk.Label(dlg, text="所属群（共 %d 个）：" % len(groups),
                 fg=self._dp["sub"], font=f, anchor="w").pack(fill="x", padx=10,
                                                              pady=(6, 2))
        box = tk.Listbox(dlg, font=f, height=10)
        box.pack(fill="both", expand=True, padx=10)
        if groups:
            for g in sorted(groups, key=lambda x: x["gid"]):
                role = {"owner": "👑群主", "admin": "🛡管理",
                        "member": "成员"}.get(g.get("role"), "成员")
                box.insert("end",
                           f"[{g['gid']}] {g.get('name', '')}  · {role}")
        else:
            box.insert("end", "（未加入任何群）")
        btns = tk.Frame(dlg)
        btns.pack(fill="x", padx=10, pady=6)
        tk.Button(btns, text="🔨 踢下线", font=f,
                  command=lambda: self._admin_kick(uid)).pack(side="left", padx=2)
        tk.Button(btns, text="🧹 清空其消息", font=f,
                  command=lambda: self._admin_clear_uid(uid)).pack(side="left", padx=2)
        tk.Button(btns, text="关闭", font=f, command=dlg.destroy).pack(
            side="right", padx=2)

    def _refill_disco_box(self, box) -> None:
        box.delete(0, "end")
        for ip, name, port in (self._disco.candidates()
                               if CFG.discovery_enabled and self._disco else []):
            box.insert("end", f"{name}  {ip}:{port}")

    def _connect_to(self, box, dlg) -> None:
        sel = box.curselection()
        if not sel:
            return
        cands = (self._disco.candidates()
                 if CFG.discovery_enabled and self._disco else [])
        if sel[0] >= len(cands):
            return
        ip, name, port = cands[sel[0]]
        self.core.set_host(ip, port)
        self.core.drop()
        self._append_sys(f"切换到服务器 {name}（{ip}:{port}）")
        dlg.destroy()

    def _auto_target(self) -> None:
        """未连上时自动切到最新发现的服务器（只切一次，防抖动）"""
        if not CFG.discovery_enabled or self._disco is None:
            return
        if self.core.connected or self.core.state == "idle":
            return
        cands = self._disco.candidates()
        if not cands:
            return
        ip, name, port = cands[0]
        if (self.core.host, self.core.port) == (ip, port):
            return
        if self._disco_target == (ip, port):
            return
        self._disco_target = (ip, port)
        self.core.set_host(ip, port)
        self.core.drop()
        self._append_sys(f"自动连接服务器 {name}（{ip}:{port}）")

    # ---------- 快速隐藏（热键/按钮 → 假工作窗） ----------
    @staticmethod
    def _visible_window(win) -> bool:
        try:
            return bool(win is not None and win.winfo_exists()
                        and win.state() not in ("withdrawn", "iconic"))
        except (tk.TclError, AttributeError):
            return False

    def _capture_collapse_snapshot(self) -> None:
        """Capture object identity/visibility once for mini or boss nesting."""
        if self._collapse_snapshot is not None:
            return
        gw = getattr(self, "_game_win", None)
        board = getattr(gw, "_board_win", None) if gw is not None else None
        self._collapse_snapshot = {
            "root_visible": self._visible_window(getattr(self, "root", None)),
            "mini_visible": self._visible_window(
                getattr(getattr(self, "_mini", None), "win", None)),
            "game": gw if self._visible_window(getattr(gw, "win", None)) else None,
            "board": board if board is not None and board.active() else None,
        }

    def _restore_collapse_snapshot(self, force_root: bool = False) -> None:
        snap = self._collapse_snapshot
        self._collapse_snapshot = None
        if self._mini is not None:
            self._mini.hide()
        if getattr(self, "_boss", None) is not None and self._boss.visible():
            self._boss.hide()
        if not snap:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            return
        if force_root or snap.get("root_visible", True):
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        else:
            self.root.withdraw()
        if (not force_root and self._mini is not None
                and snap.get("mini_visible", False)):
            self._mini.show()
        gw = snap.get("game")
        if (gw is not None and not getattr(gw, "_closed", False)
                and getattr(gw, "_restore_allowed", True)):
            try:
                gw.show()
            except Exception:
                pass
        board = snap.get("board")
        if (board is not None and not getattr(board, "_closed", False)
                and getattr(board, "_restore_allowed", True)):
            try:
                board.show(reason="collapse")
            except Exception:
                pass

    def _toggle_boss(self) -> None:
        """藏起全部摸鱼窗（主窗/迷你条/游戏窗），弹出假工作窗；再按切回。

        R69A2：进入伪装态时静默联动（静音/停音效/冻结弹窗与任务栏闪烁/切忙碌），
        退出时自动复原；R69A4：伪装态下新消息只累积未读，绝不打断。
        """
        recovery_only_close = (not CFG.tray_enabled
                               and not CFG.global_hotkeys_enabled)
        if self._boss.visible():
            if recovery_only_close:
                self._boss.win.protocol("WM_DELETE_WINDOW", self._boss.hide)
            self._boss.hide()
            self._boss_exit_silent()
            self._restore_collapse_snapshot()
            return
        self._capture_collapse_snapshot()
        if recovery_only_close:
            # With tray and global hotkeys disabled, the Boss window's native
            # close button is the only visible recovery affordance.
            self._boss.win.protocol("WM_DELETE_WINDOW", self._toggle_boss)
        self._boss_enter_silent()
        self.root.withdraw()
        if self._mini is not None:
            self._mini.hide()
        gw = getattr(self, "_game_win", None)
        if gw is not None:
            gw.hide(reason="collapse")
        self._boss.show()

    # ---------- R69A2/A4：伪装态静默联动 ----------
    def _boss_enter_silent(self) -> None:
        """进入伪装态：置忙、静音（_flash_taskbar/_play_notify_sound 早退）并提示一次。"""
        if getattr(self, "_boss_active", False):
            return
        self._boss_active = True
        me = getattr(self.core, "me", None) or {}
        prev = str(me.get("status") or "online")
        self._boss_prev_status = prev if prev in ("online", "away", "busy") else "online"
        if self._boss_prev_status != "busy":
            try:
                self.core.send_status("busy")
            except Exception:
                pass
        if not CFG.tray_enabled and not CFG.global_hotkeys_enabled:
            self._append_sys("🕶 已进入伪装态：静音、停音效、冻结弹窗与任务栏闪烁"
                             "（关闭伪装工作窗即可恢复原界面）")
        else:
            self._append_sys("🕶 已进入伪装态：静音、停音效、冻结弹窗与任务栏闪烁"
                             "（新消息只记未读，再按热键恢复）")

    def _boss_exit_silent(self) -> None:
        """退出伪装态：恢复进入前的在线状态。"""
        if not getattr(self, "_boss_active", False):
            return
        self._boss_active = False
        prev = getattr(self, "_boss_prev_status", "online")
        try:
            if prev != "busy":
                self.core.send_status(prev)
        except Exception:
            pass
        self._append_sys("🕶 已退出伪装态：通知与在线状态已恢复")

    # ---------- R69A3：本地摸鱼报告（纯本地，不上传） ----------
    _FISH_OVER_PHASES = {"ended", "done", "result", "over", "gameover", "finished"}
    _FISH_KEEP_DAYS = 60

    def _fish_days(self) -> dict:
        raw = self._prefs.get("fish_stats", {}) or {}
        days = raw.get("days") if isinstance(raw, dict) else None
        return days if isinstance(days, dict) else {}

    def _fish_add(self, sec: float = 0.0, games: int = 0, msgs: int = 0) -> None:
        """累加今日摸鱼数据（停留秒数/游戏局数/消息数）并持久化，仅保留最近 60 天。"""
        day = time.strftime("%Y-%m-%d")
        days = fish_add_day(self._fish_days(), day, sec, games, msgs,
                            keep=self._FISH_KEEP_DAYS)
        self._prefs.set("fish_stats", {"days": days})

    def _fish_report(self) -> dict:
        """汇总报告：今日 + 近 7 天（含今日）三项合计。"""
        return fish_summary(self._fish_days(), time.strftime("%Y-%m-%d"), 7)

    def _fish_tick(self, now: float) -> None:
        """累计停留时长（进入伪装态期间不计），并把游戏结束相位折算为一局。"""
        last = getattr(self, "_fish_last", 0.0)
        self._fish_last = now
        if last and not getattr(self, "_boss_active", False):
            self._fish_add(sec=min(now - last, 5.0))   # 卡顿/休眠钳制
        st = getattr(self.core, "game_state", None)
        if isinstance(st, dict) and st is not getattr(self, "_fish_last_state", None):
            self._fish_last_state = st
            phase = str(st.get("phase") or "")
            if st.get("over") is True or phase in self._FISH_OVER_PHASES:
                self._fish_add(games=1)
                self._report_fish_score()     # R70H：opt-in 上报本局积分

    def _report_fish_score(self) -> None:
        """R70H：opt-in 上报摸鱼积分（1 分/局，按当前房间游戏名；未开开关则不发）。"""
        if not self._fish_upload:
            return
        room = getattr(self.core, "game_room", None) or {}
        game = str(room.get("game") or "")
        if game:
            self.core.send_fish_score(game, 1)

    def _fish_board_games(self) -> list:
        """排行榜可选游戏：注册目录 ∪ 已知榜单 ∪ 当前房间游戏（去重、稳定排序）。"""
        names = set(getattr(self.core, "game_meta", {}) or {})
        names |= set(getattr(self.core, "fish_board", {}) or {})
        room = getattr(self.core, "game_room", None) or {}
        if room.get("game"):
            names.add(str(room["game"]))
        return sorted(n for n in names if n)

    def _fish_board_dialog(self) -> None:
        """R70H 摸鱼排行榜：只读展示某游戏「昵称 + 总分」Top N（数据来自服务器广播）。"""
        games = self._fish_board_games()
        room = getattr(self.core, "game_room", None) or {}
        cur = (self._fish_board_game if self._fish_board_game in games
               else str(room.get("game") or "") or (games[0] if games else ""))

        dlg = tk.Toplevel(self.root)
        dlg.title("摸鱼排行榜")
        dlg.geometry("380x420")
        dlg.transient(self.root)
        tk.Label(dlg, text="🏆 摸鱼排行榜", font=(FONT_FAMILY, 12, "bold"),
                 anchor="w").pack(fill="x", padx=16, pady=(14, 2))
        tk.Label(dlg, text="按游戏累计积分（每结束一局 +1），仅显示昵称与总分",
                 fg="#888", font=(FONT_FAMILY, 8), anchor="w").pack(fill="x", padx=16)
        game_var = tk.StringVar(value=cur)
        listbox = tk.Listbox(dlg, font=(FONT_FAMILY, 10), activestyle="none",
                             relief="flat", highlightthickness=0)
        listbox.pack(fill="both", expand=True, padx=16, pady=10)

        def _render():
            listbox.delete(0, "end")
            entries = (getattr(self.core, "fish_board", {}) or {}).get(game_var.get()) or []
            if not entries:
                listbox.insert("end", "（暂无数据，点击「刷新」拉取）")
                return
            for i, e in enumerate(entries, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                listbox.insert("end", f"{medal} {e.get('nick', '?')}  —  "
                                      f"{int(e.get('score') or 0)} 分")

        def _refresh():
            self._fish_board_game = game_var.get()
            if game_var.get():
                self.core.request_fish_board(game_var.get())
            dlg.after(250, _render)          # 等回帧落到 core.fish_board 后重绘

        def _on_pick(_evt=None):
            self._fish_board_game = game_var.get()
            _refresh()

        row = tk.Frame(dlg)
        row.pack(fill="x", padx=16)
        if games:
            om = tk.OptionMenu(row, game_var, *games, command=lambda _v: _on_pick())
            om.config(font=(FONT_FAMILY, 9), relief="flat")
            om.pack(side="left")
        tk.Button(row, text="刷新", command=_refresh).pack(side="right")
        tk.Label(dlg, text="未开启「参与摸鱼排行榜」时不会上报自己的积分",
                 fg="#888", font=(FONT_FAMILY, 8)).pack(pady=6)
        tk.Button(dlg, text="关闭", command=dlg.destroy).pack(pady=(0, 12))
        _render()
        if cur:
            _refresh()

    def _fish_report_dialog(self) -> None:
        """摸鱼报告：今日 + 近 7 天汇总（纯本地显示）。"""
        rep = self._fish_report()

        def _fmt(sec, games, msgs):
            sec = int(sec)
            h, m = divmod(sec // 60, 60)
            dur = f"{h} 小时 {m} 分" if h else f"{m} 分 {sec % 60} 秒"
            return (f"   停留时长：{dur}\n"
                    f"   游戏局数：{games} 局\n"
                    f"   消息条数：{msgs} 条\n")

        dlg = tk.Toplevel(self.root)
        dlg.title("摸鱼报告")
        dlg.geometry("360x300")
        dlg.transient(self.root)
        tk.Label(dlg, text="🐟 今日摸鱼", font=(FONT_FAMILY, 12, "bold"),
                 anchor="w").pack(fill="x", padx=16, pady=(14, 2))
        tk.Label(dlg, text=_fmt(**rep["today"]), justify="left", anchor="w",
                 font=(FONT_FAMILY, 9)).pack(fill="x", padx=16)
        tk.Label(dlg, text=f"📅 近 {rep['week_days']} 天合计",
                 font=(FONT_FAMILY, 12, "bold"), anchor="w").pack(
            fill="x", padx=16, pady=(12, 2))
        tk.Label(dlg, text=_fmt(**rep["week"]), justify="left", anchor="w",
                 font=(FONT_FAMILY, 9)).pack(fill="x", padx=16)
        tk.Label(dlg, text="（纯本地统计，不含任何上传）", fg="#888",
                 font=(FONT_FAMILY, 8)).pack(pady=10)
        tk.Button(dlg, text="关闭", command=dlg.destroy).pack(pady=(0, 12))

    # ---------- 游戏入口 ----------
    def open_game(self) -> None:
        """打开游戏协作面板（游戏 + 游戏内聊天 overlay）"""
        self._select_navigation('game')
        if getattr(self, "_game_win", None) is None:
            self._game_win = GameWindow(self, pal=self._dp)
        self._game_win.show()

    # ---------- 文件收发 ----------
    def _on_send_file(self) -> None:
        """附件按钮（B6，输入区📎）：私聊发附件；选中的图片直接作为图片消息渲染。"""
        ch, to = self.view
        if ch != "private" or to is None:
            self._append_sys("附件发送仅限私聊：先在左侧选中一位好友")
            return
        path = filedialog.askopenfilename(parent=self.root, title="选择附件")
        if not path:
            return
        nick = (self.core.roster.get(to) or {}).get("nick", str(to))
        # R32B3：输入框有文字 → 作为图片 caption 随图发送（文件不受影响）
        cap = ""
        if is_image_path(path):
            cap = self._entry_text().strip()
            if cap:
                self.entry.delete("1.0", "end")
        self._send_attachment(path, to, nick, caption=cap)

    def _send_attachment(self, path: str, to, nick: str,
                         caption: str = "") -> None:
        """发送单个附件（R32A1：📎 按钮与拖拽共用）：图片走图片消息，其余走文件传输。"""
        if is_image_path(path):
            # A7：图片走同一套 file 传输，发送方立即可渲染缩略图消息
            fid = self.core.files.send_file(path, to, caption=caption)
            if fid:
                self._append_msg({"t": "image", "channel": "private",
                                  "uid": self.core.uid, "to": to,
                                  "nick": self.core.nick,
                                  "file_id": fid, "image_path": path,
                                  "text": caption,          # R32B3 caption
                                  "ts": time.time()})
                self._append_sys(f"📎 正在向 {nick} 发送图片…")
            return
        fid = self.core.files.send_file(path, to)
        if fid:
            self._append_sys(f"📎 正在向 {nick} 发送文件…")

    def _drop_target(self, px, py):
        """把拖放落点（toplevel 客户区坐标）映射到目标会话 (ch,to)。
        命中会话列表/群列表某行则定向它；否则返回 None（回退当前会话）。"""
        if px is None or py is None:
            return None
        root = self.root
        for w, order, is_group in (
            (self.roster_list, getattr(self, "_roster_order", []), False),
            (self.group_list, getattr(self, "_group_order", []), True),
        ):
            if not getattr(w, "winfo_exists", lambda: False)():
                continue
            try:
                wx = w.winfo_rootx() - root.winfo_rootx()
                wy = w.winfo_rooty() - root.winfo_rooty()
                ww, wh = w.winfo_width(), w.winfo_height()
            except Exception:
                continue
            if ww <= 1 or wh <= 1:
                continue
            if wx <= px < wx + ww and wy <= py < wy + wh:
                idx = w.nearest(py - wy)
                if 0 <= idx < len(order):
                    return ("group", order[idx]) if is_group else ("private", order[idx])
                return None
        return None

    def _drop_to_group(self, paths: list, gid: int) -> None:
        """把拖入的文件上传到指定群文件库（复用群文件库上传流程）。"""
        for p in paths:
            name = os.path.basename(p)
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            if size <= 0:
                self._append_sys(f"跳过空文件：{name}")
                continue
            if size > getattr(CFG, "group_file_max_bytes", 32 * 1024 * 1024):
                self._append_sys(f"跳过超限文件（>32MB）：{name}")
                continue
            self._gf_upload["gid"] = gid
            self._gf_upload["path"] = p
            self._gf_upload["size"] = size
            self._gf_upload["fh"] = None
            self._gf_upload["off"] = 0
            self._gf_upload["fid"] = None
            self.core.send_group_file_upload_start(gid, name, size)
            self._append_sys(f"📎 正在向群「{(self.core.groups.get(gid) or {}).get('name', gid)}」上传 {name}…")

    def _on_paste_clipboard(self, _ev=None):
        """Ctrl+V：剪贴板含图片/文件 → 走既有发送链路；否则放行默认文本粘贴。"""
        paths, _img = _clipboard_paths_and_image()
        if not paths:
            return None                       # 放行 Tk 默认粘贴（纯文本）
        ch, to = self.view
        if ch != "private" or to is None:
            self._append_sys("粘贴图片/文件仅限私聊：先从左侧选中好友")
            return "break"
        self._on_drop_files(paths, confirm=False)     # 粘贴免二次确认
        return "break"

    def _start_snip(self) -> None:
        """Alt+A：区域截图 → 落临时 PNG → 复用图片发送链路（仅私聊）。"""
        if self._snip is not None:             # 已有选框在进行中
            return
        ch, to = self.view
        if ch != "private" or to is None:
            self._append_sys("截图发送仅限私聊：先从左侧选中好友")
            return
        try:
            from widgets.snip import SnipOverlay
        except Exception as e:
            self._append_sys(f"截图不可用：{e}")
            return

        def _done(img):
            self._snip = None
            if img is None:
                return
            p = _save_image_temp(img)
            if not p:
                self._append_sys("截图保存失败")
                return
            self._on_drop_files([p], confirm=False)

        try:
            self._snip = SnipOverlay(self.root, on_done=_done)
        except Exception as e:
            self._snip = None
            self._append_sys(f"截图失败：{e}")

    def _on_drop_files(self, paths: list, x: int = None, y: int = None,
                       confirm: bool = True) -> None:
        """R32A1+R63b 拖拽发送：拖入文件按落点定向发送——
        命中会话列表某行 → 定向该会话；否则回退当前会话（不破坏既有拖拽行为）。
        confirm=False 供粘贴/截图复用：跳过二次确认弹窗。"""
        if not paths:
            return
        tgt = self._drop_target(x, y)
        if tgt is not None and tgt[0] == "group":
            self._drop_to_group(paths, tgt[1])
            return
        ch, to = (tgt if tgt is not None else self.view)
        if ch != "private" or to is None:
            self._append_sys("附件发送仅限私聊：先从左侧选中好友，或拖到会话列表某一行")
            return
        imgs = [p for p in paths if is_image_path(p)]
        oths = [p for p in paths if not is_image_path(p)]
        if confirm:
            kinds = "、".join(k for k, n in (("图片", len(imgs)), ("文件", len(oths)))
                              if n)
            detail = "\n".join("· " + os.path.basename(p) for p in paths[:8])
            if len(paths) > 8:
                detail += f"\n… 等共 {len(paths)} 个"
            from widgets import dialogbox
            if not dialogbox.ask_yesno("工作资料", f"发送{kinds}？\n\n{detail}",
                                       parent=self.root):
                return
        nick = (self.core.roster.get(to) or {}).get("nick", str(to))
        if tgt is not None:                       # 定向发送：提示目标
            self._append_sys(f"📎 定向发给 {nick}")
        # R32B3：拖入当前会话时输入框文字作首图 caption（定向发送不用输入框文本）
        cap = ""
        if imgs and tgt is None:
            cap = self._entry_text().strip()
            if cap:
                self.entry.delete("1.0", "end")
        for i, p in enumerate(imgs + oths):   # 先图后文件，与 TG 习惯一致
            self._send_attachment(p, to, nick, caption=cap if i == 0 else "")

    def _on_file_offer(self, ev: dict) -> None:
        """收到文件邀请：弹窗确认保存到下载目录（同意=接收，拒绝=回绝）"""
        text = ev.get("text") or "收到文件"
        from widgets import dialogbox
        ok = dialogbox.ask_yesno("工作资料", f"{text}\n\n保存到下载目录？",
                                 parent=self.root)
        if ok:
            self.core.files.accept(ev["file_id"])
        else:
            self.core.files.reject(ev["file_id"])

    def _on_file_progress(self, ev: dict) -> None:
        """传输进度：fid 维度更新一行「文件卡片」（T1：名/大小/进度/pct），
        实时速率 + ETA，传输中提供「取消」；完成接收端保留「打开目录」，失败销毁留底。"""
        fid = ev.get("file_id")
        state = ev.get("state", "")
        text = ev.get("text", "")
        name = ev.get("name") or ev.get("filename") or "文件"
        size = ev.get("size") or ev.get("total") or 0
        pct = ev.get("pct")
        if not fid:                       # 无 fid 的全局失败，仅留底系统消息
            if state in ("failed", "cancelled", "rejected") and text:
                self._append_sys(f"⚠ {text}")
            elif state == "done" and text:
                self._append_sys(f"✅ {text}")
            return
        # R9F：速率/ETA 滑动统计（EMA），随后拼入状态文案
        rate, eta_txt = 0.0, ""
        if pct is not None and state not in ("done", "failed", "cancelled", "rejected"):
            done = ev.get("done", 0)
            now = time.time()
            prev = self._xfflow.get(fid)
            if prev:
                dt = now - prev[1]
                if dt > 0.02 and done >= prev[0]:
                    inst = (done - prev[0]) / dt
                    prev[2] = inst if prev[2] <= 0 else prev[2] * 0.6 + inst * 0.4
                    rate = prev[2]
                else:
                    rate = prev[2]
                prev[0], prev[1] = done, now
            else:
                self._xfflow[fid] = [done, now, 0.0]
            rem = max(0, size - done)
            if rate > 0 and rem > 0:
                eta_txt = self._xfer_eta(rem / rate)
        card = self._xfer_bars.get(fid)
        if card is None:
            card = _FileCard(self.xfer_area, name, size, pal=self._dp)
            card.pack(fill="x", pady=1)
            self._xfer_bars[fid] = card
        if pct is not None:
            disp = text or f"{pct}%"
            if rate:
                disp += f" · {_hsize(rate)}/s"
            if eta_txt:
                disp += f" · {eta_txt}"
            card.set_progress(pct, disp)
        else:
            card.set_status(text)
        # 非终结态自动补「取消」入口（协议层断点取消已就绪，这里只是 UI 化）
        if state not in ("done", "failed", "cancelled", "rejected"):
            card.add_cancel(lambda fid=fid: self.core.files.cancel(fid))
        if state in ("failed", "cancelled", "rejected"):
            self._xfer_bars.pop(fid, None)
            self._xfflow.pop(fid, None)
            card.destroy()
            if text:
                self._append_sys(f"⚠ {text}")
        elif state == "done":
            self._xfflow.pop(fid, None)
            card.set_progress(100, "✅ 完成")
            if ev.get("role") == "receive" and ev.get("path"):
                card.add_open(ev["path"])
            if text:
                self._append_sys(f"✅ {text}")

    def _xfer_eta(self, seconds: float) -> str:
        """ETA 文案：<60s → s，否则 ·m·s。"""
        if seconds < 1:
            return "即时"
        s = int(seconds)
        if s < 60:
            return f"剩 {s}s"
        m, s = divmod(s, 60)
        return f"剩 {m}m{s}s"

    # ---------- 迷你条 / 隐藏 ----------
    def hide_to_mini(self) -> None:
        self._capture_collapse_snapshot()
        if self._mini is None:
            self._mini = MiniBar(self, pal=self._dp)
        first = not getattr(self, "_mini_hint_shown", False)
        self._mini_hint_shown = True
        self.root.withdraw()
        self._mini.show()
        gw = getattr(self, "_game_win", None)
        if gw is not None:
            gw.hide(reason="collapse")
        if first:
            self._toast.show("已最小化到右下角托盘/迷你条。\n"
                             "点击图标可恢复窗口，右键菜单可退出程序。",
                             dur=4.5)

    def show_main(self) -> None:
        if self._collapse_snapshot is not None:
            # A user selecting “显示主窗” from the mini bar explicitly wants
            # the main window back, even when the captured state was mini-only
            # (root withdrawn). Boss-mode exit still uses the exact snapshot.
            self._restore_collapse_snapshot(force_root=True)
            return
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        if self._mini is not None:
            self._mini.hide()
        if getattr(self, "_boss", None) is not None and self._boss.visible():
            self._boss.hide()

    def quit_app(self) -> None:
        self._closed = True
        # R10：退出前关闭锁定遮罩，避免隐藏主窗遗留
        ov = getattr(self, "_lock_overlay", None)
        if ov is not None:
            try:
                ov.destroy()
            except Exception:
                pass
            self._lock_overlay = None
        gw = getattr(self, "_game_win", None)
        if gw is not None:
            gw.close()
        if self._mini is not None:
            self._mini.win.destroy()
        if getattr(self, "_boss", None) is not None:
            self._boss.close()
        self._hotkey.stop()
        self._shot_hotkey.stop()
        if self._disco is not None:
            try:
                self._disco.stop.set()
            except Exception:
                pass
        if getattr(self, "_tray", None) is not None:
            self._tray.stop()              # R31D：退出前移除托盘图标
        self._persist_drafts()             # R12：退出前把内存草稿写盘
        # Stop this interpreter's timers without deleting child-owned Python
        # callback commands through root.after_cancel. Widget.destroy owns that
        # command bookkeeping and removes each command from its proper owner.
        try:
            for job in self.root.tk.splitlist(self.root.tk.call("after", "info")):
                self.root.tk.call("after", "cancel", job)
        except tk.TclError:
            pass
        self.root.destroy()
        self.core.stop()

    def teardown_quiet(self) -> None:
        """launcher 兜底清理：已关则仅确保 core 停止；未关则走 quit_app。幂等。"""
        try:
            if not self._closed:
                self.quit_app()
            else:
                self.core.stop()
        except Exception:
            pass

    def request_switch_account(self) -> None:
        """切账号：置退出语义后走 quit_app，launcher 外层据此重弹登录。"""
        self._exit_reason = "switch"
        self.quit_app()


# 游戏动作配置：按钮 -> 动作（fixed=直接发；key+kind=取输入框内容构造）
_GAME_ACTIONS = {
    "guess_number": [
        ("出题", {"key": "secret", "kind": "int"}, "输入 1~100 数字（出题）"),
        ("猜数字", {"key": "guess", "kind": "int"}, "输入 1~100 数字（猜）"),
    ],
    "gomoku": [("落子", {"key": None, "kind": "pos"}, "输入 x,y（0 起，用逗号分隔）")],
    "rps": [
        ("✊ 石头", {"fixed": {"choice": "rock"}}, ""),
        ("✌️ 剪刀", {"fixed": {"choice": "scissors"}}, ""),
        ("✋ 布", {"fixed": {"choice": "paper"}}, ""),
    ],
    "spy": [
        ("描述", {"key": "describe", "kind": "text"}, "输入描述（别说出关键词）"),
        ("投票", {"key": "vote", "kind": "uid"}, "输入怀疑对象的 uid"),
    ],
    "uno": [
        ("摸牌", {"fixed": {"draw": True}}, ""),
        ("出牌", {"key": "card", "kind": "card"}, "输入 牌id [颜色]"),
    ],
    "blackjack": [
        ("要牌", {"fixed": {"action": "hit"}}, ""),
        ("停牌", {"fixed": {"action": "stand"}}, ""),
    ],
    "drawguess": [
        ("笔画", {"key": "stroke", "kind": "stroke"}, "画手输入 x1,y1,x2,y2"),
        ("猜词", {"key": "guess", "kind": "text"}, "输入你的猜测"),
    ],
    "connect4": [("落子", {"key": "col", "kind": "int"}, "输入列号 0~6")],
    "othello": [("落子", {"key": None, "kind": "pos"}, "输入 x,y（0 起）")],
    "calc24": [("作答", {"key": "expr", "kind": "text"}, "输入凑 24 的表达式，如 1+2+3*4")],
    "matchpairs": [("摸牌", {"fixed": {"draw": True}}, "")],
    "betrayal": [
        ("⬆ 上", {"fixed": {"move": "up"}}, ""),
        ("⬇ 下", {"fixed": {"move": "down"}}, ""),
        ("⬅ 左", {"fixed": {"move": "left"}}, ""),
        ("➡ 右", {"fixed": {"move": "right"}}, ""),
        ("结束回合", {"fixed": {"end": True}}, ""),
        ("使用道具", {"key": "use", "kind": "text"}, "输入道具名，如 急救包"),
        ("攻击", {"key": "attack", "kind": "uid"}, "输入同一房间的目标 uid（惊魂阶段）"),
        ("全员撤离", {"fixed": {"escape": True}}, ""),
    ],
    "davinci": [
        ("摸明牌", {"fixed": {"op": "draw", "open": True}}, ""),
        ("摸暗牌", {"fixed": {"op": "draw", "open": False}}, ""),
        ("猜牌", {"key": "gtv", "kind": "gtv"}, "输入 target pos val（空格分隔，val 可为 black）"),
    ],
    "kalah": [("播子", {"key": "hole", "kind": "int"}, "输入己方洞号 1~6")],
    "lovelove": [
        ("弃牌出效果", {"key": "ldisc", "kind": "ldisc"}, "输入 play [target [val]] 空格分隔"),
    ],
    "halloween": [
        ("翻牌", {"fixed": {"op": "flip"}}, ""),
        ("拍铃", {"fixed": {"op": "slap"}}, ""),
        ("过", {"fixed": {"op": "pass"}}, ""),
    ],
    "tictactoe": [("落子", {"key": None, "kind": "pos"}, "输入 x,y（0 起，用逗号分隔）")],
    "go": [
        ("落子", {"key": None, "kind": "pos"}, "输入 x,y（0 起，用逗号分隔）"),
        ("过一手", {"fixed": {"pass": True}}, "弃一手（轮流连续过则终局）"),
    ],
    "halma": [("走子", {"key": None, "kind": "halmamove"}, "输入 fx,fy tx,ty（直移或隔子直跳）")],
    "checkers": [("走子", {"key": None, "kind": "halmamove"}, "输入 fx,fy tx,ty（斜移/斜跳吃子）")],
    "blokus": [("放置", {"key": None, "kind": "blok"}, "输入 拼块名 方向号 x y")],
    "ludo": [
        ("掷骰", {"fixed": {"op": "roll"}}, ""),
        ("走机", {"key": None, "kind": "ludomove"}, "输入机号 0~3"),
        ("结束回合", {"fixed": {"op": "skip"}}, ""),
    ],
    "onewolf": [
        ("🔮预言看一人", {"op": "peek", "key": "look_one", "kind": "uid"}, "输入目标 uid（预言家）"),
        ("🔮预言看中心", {"fixed": {"op": "peek", "look_center": [0, 1]}}, "预言家看中心两张"),
        ("🗡️强盗换牌", {"op": "swap", "key": "rob", "kind": "uid"}, "输入交换目标 uid（强盗）"),
        ("🗳️投票", {"op": "vote", "key": "target", "kind": "uid"}, "输入处决目标 uid"),
    ],
    "werewolf": [
        ("🔮预言验人", {"op": "check", "key": "target", "kind": "uid"}, "输入查验目标 uid"),
        ("🐺狼人刀人", {"op": "kill", "key": "target", "kind": "uid"}, "输入刀杀目标 uid"),
        ("💊女巫救", {"fixed": {"op": "save"}}, "女巫使用解药"),
        ("☠️女巫毒", {"op": "poison", "key": "target", "kind": "uid"}, "输入毒杀目标 uid"),
        ("🏹猎人开枪", {"op": "shoot", "key": "target", "kind": "uid"}, "输入带走目标 uid"),
        ("🗳️投票", {"op": "vote", "key": "target", "kind": "uid"}, "输入放逐目标 uid，0 弃票"),
    ],
    "avalon": [
        ("👑提名团队", {"op": "nominate", "key": "team", "kind": "uids"}, "团队成员 uid（逗号分隔）"),
        ("✅赞同", {"fixed": {"op": "teamvote", "approve": True}}, "赞同当前团队"),
        ("❌否决", {"fixed": {"op": "teamvote", "approve": False}}, "否决当前团队"),
        ("✅任务成功", {"fixed": {"op": "quest", "success": True}}, "任务成功"),
        ("💥任务失败", {"fixed": {"op": "quest", "success": False}}, "任务失败"),
        ("🎯指认梅林", {"op": "guess", "key": "target", "kind": "uid"}, "刺客指认梅林"),
    ],
    "liar": [
        ("🃏出牌", {"op": "play", "key": None, "kind": "liarplay"}, "输入 牌值 报数（空格分隔，牌值须在手牌中，报数可虚报 0~9）"),
        ("💥挑战", {"fixed": {"op": "challenge"}}, "挑战上一位的报数"),
    ],
    "ninja": [
        ("🗡️攻击", {"key": None, "kind": "ninjaattack"}, "输入攻击目标 uid（忍者之夜）"),
        ("🛡️防御", {"fixed": {"op": "move", "move": "guard"}}, "本回合防御，攻击者反伤"),
        ("👉下一回合", {"fixed": {"op": "next"}}, "结算后进入下一回合"),
    ],
    "coc": [
        ("🎭开局(KP)", {"fixed": {"op": "begin"}}, "KP 开始调查（需全员已选卡）"),
        ("🔰选卡", {"op": "choose_card", "key": "card_id", "kind": "text"}, "输入调查员 id（setup 阶段）"),
        ("🎲检定", {"op": "check", "key": "skill", "kind": "text"}, "输入技能名发起 d100 检定"),
        ("🗒️剧情(KP)", {"op": "set_scene", "key": "scene", "kind": "text"}, "KP 更新场景文案"),
        ("🏁结束(KP)", {"fixed": {"op": "end"}}, "KP 收尾本局"),
    ],
    "rummikub": [
        ("🎴组新组", {"op": "meld", "sel_key": "rmk"}, "先在棋盘点选手牌，再点此组新组（≥3 张同数异色/同色连号）"),
        ("🔧接续", {"op": "extend", "sel_key": "rmk", "need_row": True}, "点选手牌后接续到桌面某一组"),
        ("🂠摸牌", {"fixed": {"op": "draw"}}, "本回合未出牌时摸一张并结束回合"),
        ("✅结束回合", {"fixed": {"op": "done"}}, "结束本回合"),
    ],
    "balatro": [
        ("🎮 出牌", {"fixed": {"op": "play"}}, "结算当前出战的牌型"),
    ],
    "balatro_solo": [
        ("🎮 出牌", {"fixed": {"op": "play"}}, "结算当前出战的牌型"),
        ("🛒 逛店", {"fixed": {"op": "shop"}}, "过关后开商店淘货（购Joker/消耗品）"),
        ("▶ 继续", {"fixed": {"op": "next"}}, "商店结束，进下一盲注"),
    ],
}

# 参数动作的友好输入窗：kind -> callable(win, title, hint, label) -> str|None
def _KIND_INPUTS():
    from widgets import dialogbox as _db

    def _one(win, title, hint, label="输入值"):
        return _db.ask_string(title, hint, parent=win)

    return {
        "int":   lambda w, t, h: _one(w, t, h, "数值"),
        "text":  lambda w, t, h: _one(w, t, h, "内容"),
        "uid":   lambda w, t, h: _one(w, t, h, "玩家 uid"),
        "uids":  lambda w, t, h: _one(w, t, h, "玩家 uid（逗号分隔）"),
        "pos":   lambda w, t, h: _one(w, t, h, "坐标 x,y"),
        "card":  lambda w, t, h: _one(w, t, h, "牌 id 与颜色"),
        "stroke": lambda w, t, h: _one(w, t, h, "笔画 x1,y1,x2,y2"),
        "gtv":   lambda w, t, h: _one(w, t, h, "target pos val"),
        "ldisc": lambda w, t, h: _one(w, t, h, "play [target [val]]"),
        "liarplay": lambda w, t, h: _one(w, t, h, "牌值 报数"),
        "halmamove": lambda w, t, h: _one(w, t, h, "fx,fy tx,ty"),
        "ludomove": lambda w, t, h: _one(w, t, h, "机号 0~3"),
        "blok": lambda w, t, h: _one(w, t, h, "拼块名 方向号 x y"),
        "ninjaattack": lambda w, t, h: _one(w, t, h, "目标 uid"),
    }


_KIND_INPUTS = _KIND_INPUTS()

# 桌游卡片图标（大厅可视化）
_GAME_ICON = {
    "guess_number": "🔢", "gomoku": "⚫", "rps": "✊", "spy": "🕵️",
    "uno": "🃏", "blackjack": "🂠", "drawguess": "🎨",
    "connect4": "🔴", "othello": "◐", "calc24": "➗", "matchpairs": "🃏",
    "betrayal": "🏚️",
    "davinci": "🔐", "kalah": "🥜", "lovelove": "💌", "halloween": "🔔",
    "onewolf": "🐺",
    "werewolf": "🐺",
    "avalon": "⚔️",
    "liar": "🎲",
    "ninja": "🥷",
    "coc": "🔮",
    # 补齐剩余23款专属图标（此前兜底 🎲）
    "xiangqi": "🀄", "chess": "♞", "go": "🖤", "shogi": "🏯",
    "junqi": "🎖️", "dou": "🃁", "halma": "⭐", "checkers": "♟️",
    "blokus": "🔷", "ludo": "✈️", "rummikub": "🀄", "yahtzee": "🎰",
    "nimmt": "🐂", "azul": "🧱", "kaituo": "⛏️",
    "lingdi": "🗺️", "tielu": "🚂", "gongfang": "🏗️", "chengzhu": "🏰",
    "gemcity": "💎", "siji": "🍀", "bolan": "🌊", "tictactoe": "⭕",
    "balatro": "🃏",
    "balatro_solo": "🃏",
}


# 桌游封面渐变色（对齐网页端 GART 前两色，QQ游戏大厅式彩色封面）。
# 棋类（xiangqi/chess/go/shogi/junqi/dou）网页端无 GART，用统默认蓝灰渐变。
_GAME_GRAD = {
    "guess_number": ("#5b8def", "#3b6fd4"), "gomoku": ("#b07c45", "#8a5a2b"),
    "rps": ("#e2634b", "#c24a33"), "spy": ("#7b5fb0", "#5d4592"),
    "uno": ("#e4483c", "#c2362c"), "blackjack": ("#2f6f4f", "#1f5236"),
    "drawguess": ("#e08ac0", "#c265a4"), "connect4": ("#3f6fe0", "#2955b8"),
    "othello": ("#3a3d42", "#23262b"), "calc24": ("#e0a13c", "#c38427"),
    "matchpairs": ("#37a25f", "#21804a"), "betrayal": ("#5a3f78", "#3e2a56"),
    "kaituo": ("#c98a3d", "#a96a28"), "lingdi": ("#4f7a54", "#37603c"),
    "tielu": ("#3d5a86", "#2c4366"), "gongfang": ("#8a6f4a", "#6a5336"),
    "chengzhu": ("#7f5b3f", "#5f422c"), "gemcity": ("#8a5fbf", "#6a45a0"),
    "siji": ("#3f8f6a", "#2a6b4d"), "bolan": ("#5b6ca8", "#42528a"),
    "azul": ("#3f8f8a", "#2f6f70"), "rummikub": ("#3f8f6a", "#2a6b4d"),
    "yahtzee": ("#e0a13c", "#c38427"), "nimmt": ("#8a5a2b", "#6a4121"),
    "davinci": ("#5b6ca8", "#42528a"), "kalah": ("#8a5fbf", "#6a45a0"),
    "lovelove": ("#e08ac0", "#c265a4"), "halloween": ("#e05555", "#c2362c"),
    "tictactoe": ("#3f6fe0", "#2955b8"), "halma": ("#4f7a54", "#37603c"),
    "checkers": ("#8a5a2b", "#6a4121"), "blokus": ("#37a25f", "#21804a"),
    "ludo": ("#e0a13c", "#c38427"),
    "onewolf": ("#4a3b6b", "#32264d"), "werewolf": ("#5a2d3a", "#3c1826"),
    "avalon": ("#4f7a9e", "#355c7d"), "liar": ("#c9853e", "#8a5a2b"),
    "ninja": ("#33415a", "#1d2736"),
    "xiangqi": ("#5a4a2d", "#3d3018"), "chess": ("#39424e", "#232a33"),
    "go": ("#33415a", "#1d2736"), "shogi": ("#5d4592", "#3a2d63"),
    "junqi": ("#5b8def", "#3b6fd4"), "dou": ("#4f7a54", "#37603c"),
    "coc": ("#1f5236", "#123022"),
    "balatro": ("#5b1f2a", "#2a1030"),
    "balatro_solo": ("#5b1f2a", "#2a1030"),
}

_GAME_GRAD_DEF = ("#4a4f5a", "#333842")     # 未知游戏兜底渐变

# CC-03 desktop completion map: these entries remain registered/server
# capable, but their desktop action path is known to be incomplete.  The
# lobby explains the boundary and blocks accidental creation/join; the other
# games remain available with an explicit "unverified" notice.
_DESKTOP_UNSUPPORTED_GAMES = {
    "azul", "bolan", "chengzhu", "gemcity", "gongfang", "kaituo",
    "lingdi", "nimmt", "siji", "tielu", "yahtzee",
}


def _desktop_game_status(name: str) -> tuple[str, str]:
    if name in _DESKTOP_UNSUPPORTED_GAMES:
        return "unsupported", "桌面端当前不支持主要操作"
    if name in ("gomoku", "connect4"):
        return "flagship", "Windows 旗舰桌面流程"
    if name in ("balatro", "balatro_solo"):
        return "unverified", "桌面端未验证（私有信息显示有已知缺陷）"
    return "unverified", "桌面端流程未验证"


def _nick_of(core, uid: int) -> str:
    u = core.roster.get(uid)
    return u["nick"] if u else f"玩家{uid}"


_DEFAULT_PAL = {
    "bg": "#fffdf7", "win": "#fff7ec", "fg": "#5b4636", "sub": "#b7a48e",
    "tab_on_bg": "#ffe3d0", "tab_bg": "#f1e6d6", "input": "#fffdf6",
    "border": "#efdcc4", "doc_h": "#ead6ba", "self": "#0e4a32", "priv": "#6b5239",
    "warn_bg": "#fff3d6", "warn_fg": "#8d6e2e",
    "accent": "#ff8a5c", "accent_fg": "#ffffff", "accent_hover": "#ed7a4e",
    "card_bg": "#fffdf7", "soft_bg": "#f5ead9",
    "danger": "#e05252", "link": "#2f6fed",
}


class _FileCard(tk.Frame):
    """文件卡片（T1）：文件名 + 大小 + 细进度条 + 状态字。
    传输中实时更新进度；完成后（接收端）可「打开目录」"""

    def __init__(self, parent, name: str, size: int = 0,
                 card_bg=None, fg=None, sub=None,
                 bar_bg=None, fill="#4caf50", bar_w: int = 140,
                 bar_h: int = 6, pal: dict | None = None):
        self._pal = pal or _DEFAULT_PAL
        card_bg = card_bg or self._pal["bg"]
        fg = fg or self._pal["fg"]
        sub = sub or self._pal["sub"]
        bar_bg = bar_bg or self._pal.get("border", "#e0e0e0")
        super().__init__(parent, bg=card_bg, padx=8, pady=4,
                         highlightthickness=1,
                         highlightbackground=self._pal.get("border", "#e3e6ea"))
        self._card_bg = card_bg
        self._bar_w = bar_w
        self._open = None
        self.row1 = tk.Frame(self, bg=card_bg)
        self.row1.pack(fill="x")
        tk.Label(self.row1, text=f"📎 {name}", bg=card_bg, fg=fg, anchor="w",
                 font=(FONT_FAMILY, 9)).pack(side="left")
        if size:
            tk.Label(self.row1, text=_hsize(size), bg=card_bg, fg=sub,
                     anchor="e", font=(FONT_FAMILY, 8)).pack(side="right")
        self.row2 = tk.Frame(self, bg=card_bg)
        self.row2.pack(fill="x", pady=(2, 0), anchor="w")
        self._track = tk.Frame(self.row2, width=bar_w, height=bar_h, bg=bar_bg)
        self._track.pack_propagate(False)
        self._track.pack(side="left")
        self._fill_f = tk.Frame(self._track, width=0, height=bar_h, bg=fill)
        self._fill_f.pack(side="left", fill="y")
        self._status = tk.Label(self.row2, text="等待中…", bg=card_bg, fg=sub,
                                anchor="w", font=(FONT_FAMILY, 8))
        self._status.pack(side="left", padx=(6, 0))

    def set_progress(self, pct: int, text: str = "") -> None:
        w = max(1, int(self._bar_w * min(1.0, max(0, pct) / 100.0)))
        self._fill_f.config(width=w)
        self._status.config(text=text or f"{pct}%")

    def set_status(self, text: str) -> None:
        self._status.config(text=text or "")

    def add_cancel(self, cb) -> None:
        """R9F：传输中提供「取消」入口（断点中止，回调 UI 触发 FileManager.cancel）。"""
        if getattr(self, "_cancel", None) is not None:
            return
        self._cancel = tk.Button(self.row2, text="取消", relief="flat",
                                 padx=5, pady=0, bg=self._card_bg,
                                 fg=self._pal.get("danger", "#e05252"),
                                 activebackground=self._card_bg,
                                 cursor="hand2", font=(FONT_FAMILY, 8),
                                 command=cb)
        self._cancel.pack(side="left", padx=(8, 0))

    def add_open(self, path: str) -> None:
        if self._open is not None or not path:
            return
        self._open = tk.Button(self.row2, text="打开目录", relief="flat",
                               padx=4, pady=0, bg=self._card_bg,
                               fg=self._pal.get("link", "#2f6fed"),
                               cursor="hand2", font=(FONT_FAMILY, 8),
                               command=lambda: self._open_dir(path))
        self._open.pack(side="left", padx=(8, 0))

    def _open_dir(self, path: str) -> None:
        try:
            os.startfile(os.path.dirname(path) or path, "explore")
        except Exception:
            self.show_toast(f"无法打开目录：{path}", warn=True)


class _ProgressBar(tk.Frame):
    """细进度条：灰底 + 绿色填充（房间人数可视化）"""

    def __init__(self, parent, ratio: float, width: int = 90, height: int = 6,
                 pal: dict | None = None):
        self._pal = pal or _DEFAULT_PAL
        super().__init__(parent, width=width, height=height,
                         bg=self._pal.get("border", "#e0e0e0"))
        self.pack_propagate(False)
        self.fill = tk.Frame(self, width=max(1, int(width * ratio)),
                             height=height, bg="#4caf50")
        self.fill.pack(side="left", fill="y")


class _CardBase(tk.Frame):
    """可点击卡片基类：hover 高亮 + 单击选中 + 双击快捷动作 + 右键菜单。

    子控件建好后统一绑定事件（点卡片任意位置都生效），key 为卡片标识。
    """

    def __init__(self, parent, key, on_click=None, on_double=None, on_menu=None,
                 pal: dict | None = None, **kw):
        self._pal = pal or _DEFAULT_PAL
        super().__init__(parent, **kw)
        self.key = key
        self._on_click = on_click
        self._on_double = on_double
        self._on_menu = on_menu
        self._selected = False
        self.bind("<Enter>", self._hover_on)
        self.bind("<Leave>", self._hover_off)
        self.after(1, self._bind_all)          # 等子控件建好后统一绑定

    def _all(self):
        def walk(w):
            for c in w.winfo_children():
                yield c
                yield from walk(c)
        return list(walk(self))

    def _bind_all(self):
        for w in self._all():
            if getattr(w, "_no_card_bind", False):   # 独立控件（如「创建」按钮）不抢卡片点击
                continue
            w.bind("<Button-1>", self._click)
            w.bind("<Double-Button-1>", self._double)
            if self._on_menu:
                w.bind("<Button-3>", self._menu)
            w.bind("<Enter>", self._hover_on)
            w.bind("<Leave>", self._hover_off)

    def _click(self, _e=None):
        if self._on_click:
            self._on_click(self.key)

    def _double(self, _e=None):
        if self._on_double:
            self._on_double(self.key)

    def _menu(self, ev):
        if self._on_menu:
            self._on_menu(ev, self.key)

    def _hover_on(self, _e=None):
        if not self._selected:
            self._paint(hover=True)

    def _hover_off(self, _e=None):
        if not self._selected:
            self._paint(hover=False)

    def set_selected(self, sel: bool):
        self._selected = sel
        self._paint(hover=False)

    def _paint(self, hover: bool):
        raise NotImplementedError


class _GameCard(_CardBase):
    """桌游卡片（QQ游戏大厅风）：顶部彩色渐变封面 + 大图标 + 底部白色「创建」药丸按钮。

    单击选中看规则（on_click），双击创建房间（on_double），封面上的「＋创建」
    按钮单击也直接创建。渐变取自 _GAME_GRAD，对齐网页端 GART。
    """

    _COVER_H = 64                       # 封面条高度
    _CARD_H = 156                       # 卡片统一总高（封面64 + 标题 + 副标题2行），同行严格等高

    def __init__(self, parent, name, meta, on_click, on_double,
                 pal: dict | None = None):
        self.meta = meta
        self._desktop_status, self._desktop_note = _desktop_game_status(name)
        self._grad = _GAME_GRAD.get(name, _GAME_GRAD_DEF)
        self._pal = pal or _DEFAULT_PAL
        super().__init__(parent, name, on_click=on_click, on_double=on_double,
                         bg=self._pal["bg"], highlightthickness=1,
                         highlightbackground=self._pal.get("border", "#e0e0e0"),
                         cursor="hand2", pal=pal)
        need = f"{meta['min']}人" + (f"~{meta['max']}人" if meta.get("max") else "人+")

        # 渐变封面条（内部画纵向渐变 + 大图标；高度固定）
        self.cover = tk.Canvas(self, height=self._COVER_H, highlightthickness=0,
                               cursor="hand2")
        self.cover.pack(fill="x")
        self.cover.bind("<Configure>", lambda e: self._paint_cover())

        # 封面底部居中的「创建」药丸按钮：白色底 + 深色字，干净不抢眼
        self.create_btn = tk.Button(self.cover,
                                    text=("桌面端暂不支持" if self._desktop_status == "unsupported"
                                          else "＋ 创建"), relief="flat",
                                    bg="#ffffff", fg="#1f2a33",
                                    activebackground="#eef2f7", activeforeground="#1f2a33",
                                    font=(FONT_FAMILY, FONT_SIZE - 1, "bold"),
                                    cursor="hand2", padx=16, pady=1,
                                    highlightthickness=0)
        self.create_btn._no_card_bind = True
        self.create_btn.configure(command=lambda: on_double(name))
        if self._desktop_status == "unsupported":
            self.create_btn.configure(state="disabled", disabledforeground="#8b8b8b")
        self.create_btn.place(relx=0.5, rely=1.0, y=-6, anchor="s")

        # 标题 + 副标题（名称 / 人数 · 一句话玩法）
        # 统一卡片总高，副标题文字在固定高度内用 wraplength 最多撑 2 行，
        # 超出部分截断加省略号——保证同一行内所有卡片严格等高、不被网格裁切。
        self.title = tk.Label(self, text=meta['label'], bg=self._pal["bg"],
                              fg=self._pal["fg"],
                              font=(FONT_FAMILY, FONT_SIZE + 2, "bold"), anchor="w")
        self.title.pack(fill="x", padx=8, pady=(6, 1))
        self.sub = tk.Label(self, bg=self._pal["bg"], fg=self._pal["sub"],
                            font=(FONT_FAMILY, FONT_SIZE - 1), anchor="nw",
                            justify="left")
        self.sub.pack(fill="x", padx=8, pady=(1, 8))
        self.configure(height=self._CARD_H)
        self.pack_propagate(False)
        self._set_sub_text(f"{need} · {meta.get('desc', '')} · {self._desktop_note}")
        self.bind("<Configure>", lambda e: self._fit_text())

    def _fit_text(self):
        """按当前卡片宽度设置标题/副标题换行宽，避免长名/长描述被裁。"""
        w = self.winfo_width() - 14
        if w < 40:
            return
        self.title.configure(wraplength=max(40, w))
        self.sub.configure(wraplength=max(40, w))
        self._reclip_sub()

    def _set_sub_text(self, text: str) -> None:
        """设置副标题原文（保留用于重排后截断）。"""
        self._sub_full = text
        self._reclip_sub()

    def _reclip_sub(self) -> None:
        """副标题固定最多 2 行：按字宽估算每行可容纳字符，超限直接截断加省略号。
        （不依赖 reqheight 判高——卡片固定高内预留空间可容纳更多行，与"想排成
        2 行"的美观目标是两回事，故用字宽硬截到 2 行。）"""
        MAXL = 2                                        # 副标题最多 2 行，天然整齐、不挤占规则区
        char_w = max(7, (FONT_SIZE - 1) * 16 // 10)     # 中文字符像素宽 ≈ 行高（9pt≈14px）
        per_line = max(8, int((self.winfo_width() - 14) / char_w))
        keep = per_line * MAXL
        text = self._sub_full
        if len(text) > keep:
            text = text[:keep - 1] + "…"
        self.sub.configure(text=text,
                           wraplength=max(40, self.winfo_width() - 14))

    def _paint_cover(self):
        cv = self.cover
        cv.delete("all")
        w, h = cv.winfo_width(), cv.winfo_height()
        if w < 2 or h < 2:
            return

        def _hex(c):
            c = c.lstrip('#')
            return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))

        a, b = _hex(self._grad[0]), _hex(self._grad[1])
        for y in range(h):                     # 逐行插值画纵向渐变
            t = y / max(1, h - 1)
            r = int(a[0] + (b[0] - a[0]) * t)
            g = int(a[1] + (b[1] - a[1]) * t)
            bl = int(a[2] + (b[2] - a[2]) * t)
            cv.create_line(0, y, w, y, fill=f"#{r:02x}{g:02x}{bl:02x}")
        icon = _GAME_ICON.get(self.key, "🎲")   # 居中偏上的大图标（下方留给药丸按钮）
        cv.create_text(w // 2, h // 2 - 3, text=icon,
                       fill="#ffffff", font=(FONT_FAMILY, int(FONT_SIZE * 2.0), "bold"))

    def _paint(self, hover):
        if self._selected:
            bg, hi = self._pal["tab_on_bg"], self._pal.get("accent", "#1a73e8")
        elif hover:
            bg, hi = self._pal["bg"], self._pal.get("border", "#c5d4e8")
        else:
            bg, hi = self._pal["bg"], self._pal.get("border", "#e0e0e0")
        self.configure(bg=bg, highlightbackground=hi)
        self.title.configure(bg=bg)
        self.sub.configure(bg=bg)


class _RoomCard(_CardBase):
    """房间卡片：房主标记 + 人数进度条 + 状态徽标"""

    def __init__(self, parent, room_id, room, core, on_click, on_double, on_menu,
                 pal: dict | None = None):
        self.room = room
        self._pal = pal or _DEFAULT_PAL
        super().__init__(parent, room_id, on_click=on_click, on_double=on_double,
                         on_menu=on_menu, bg=self._pal["bg"], highlightthickness=1,
                         highlightbackground=self._pal.get("border", "#e0e0e0"),
                         cursor="hand2", pal=pal)
        meta = core.game_meta.get(room["game"], {})
        label = meta.get("label", room["game"])
        icon = _GAME_ICON.get(room["game"], "🎲")
        me = core.uid
        owner = room.get("owner_uid")
        host_nick = _nick_of(core, owner) if owner else "?"
        status = room["status"]
        status_cn = {"created": "大厅", "playing": "进行中",
                     "ended": "结算中"}.get(status, status)
        badge_bg, badge_fg = {"created": ("#e8f5e9", "#2e7d32"),
                              "playing": ("#fff3e0", "#e65100"),
                              "ended": ("#eceff1", "#607d8b")}.get(status, ("#eee", "#666"))
        players = len(room.get("players", []))
        maxp = meta.get("max")

        self.row1 = tk.Frame(self, bg=self._pal["bg"])
        self.row1.pack(fill="x", padx=4, pady=(3, 0))
        mark = "★ " if owner == me else ""
        l1 = tk.Label(self.row1, text=f"{mark}{icon} {label} {room['room_id']}",
                      bg=self._pal["bg"], fg=self._pal["fg"],
                      font=(FONT_FAMILY, FONT_SIZE, "bold"))
        l1.pack(side="left")
        l2 = tk.Label(self.row1, text=f"房主 {host_nick}", bg=self._pal["bg"],
                      fg=self._pal["sub"],
                      font=(FONT_FAMILY, FONT_SIZE - 2))
        l2.pack(side="right")

        self.row2 = tk.Frame(self, bg=self._pal["bg"])
        self.row2.pack(fill="x", padx=4, pady=(0, 3))
        cap = maxp or max(8, players)
        _ProgressBar(self.row2, min(1.0, players / cap) if cap else 0.0,
                     pal=self._pal).pack(side="left")
        cap_txt = f"/{maxp}" if maxp else "人+"
        l3 = tk.Label(self.row2, text=f"{players}{cap_txt}", bg=self._pal["bg"],
                      fg=self._pal["fg"],
                      font=(FONT_FAMILY, FONT_SIZE - 2))
        l3.pack(side="left", padx=(4, 0))
        self.badge = tk.Label(self.row2, text=status_cn, bg=badge_bg, fg=badge_fg,
                              font=(FONT_FAMILY, FONT_SIZE - 2), padx=4)
        self.badge.pack(side="right")
        self._texts = [l1, l2, l3]

    def _paint(self, hover):
        if self._selected:
            bg, hi = self._pal["tab_on_bg"], self._pal.get("accent", "#1a73e8")
        elif hover:
            bg, hi = self._pal["bg"], self._pal.get("border", "#c5d4e8")
        else:
            bg, hi = self._pal["bg"], self._pal.get("border", "#e0e0e0")
        self.configure(bg=bg, highlightbackground=hi)
        self.row1.configure(bg=bg)
        self.row2.configure(bg=bg)
        for w in self._texts:
            w.configure(bg=bg)


class GameWindow:
    """游戏协作面板（无边框半透明小窗）：
    - 左：卡片式大厅——桌游卡片网格（图标/人数/一句话玩法，双击创建，点选看规则）
         + 内嵌规则说明 + 房间卡片（房主/人数进度条/状态徽标，双击加入，右键菜单）
         + 房间筛选（全部/可加入/进行中/我的）与排序（默认/人最多/人最少）
    - 右：房间状态（快照 + 事件流 + 私密信息）+ 按游戏定制的动作区
    - 底部：聊天 overlay（半透明小面板，随时可聊，走公共频道）
    事件不消费 core.events（避免与主窗抢队列），全部由 core 状态快照驱动。
    """

    def __init__(self, app: ChatWindow, pal: dict | None = None) -> None:
        self.app = app
        self.core = app.core
        self._pal = pal or _DEFAULT_PAL
        self._closed = False
        self._hide_reason = None
        self._restore_allowed = True
        self._chat_open = False
        self._last_list = None
        self._last_room = None
        self._last_state = None
        self._last_private = None
        self._events_shown = 0
        self._last_hist = None
        self._pending = None          # (key, kind) 等待输入的模式
        self._sel_game = None         # 卡片式大厅：当前选中的桌游/房间
        self._sel_room = None
        self.game_cards: dict = {}
        self.room_cards: dict = {}
        self._build()
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self.win.after(200, self._poll)
        self.core.game_list()
        # 首帧可能抢在 GAME_LIST 回复前：延时补发几次，自愈空列表
        for _delay in (600, 1800, 3500):
            self.win.after(_delay, lambda c=self.core: c.game_list())

    # ---------- UI ----------
    def _build(self) -> None:
        win = tk.Toplevel(self.app.root)
        try:
            win.attributes("-alpha", 0.95)
        except tk.TclError:
            pass
        win.attributes("-topmost", True)
        try:
            win.title(self.app._camo_title())   # 窗口标题跟随伪装名（与托盘一致）
        except Exception:
            pass
        win.configure(bg=self._pal["win"])
        f = (FONT_FAMILY, FONT_SIZE)
        win.geometry(f"760x600+{_screen_w(win) - 800}+40")
        win.minsize(640, 480)                      # 可自由调整大小（不少于该值防卡片塌缩）
        win.resizable(True, True)
        self.win = win
        # 苹果风一致性：无边框 + 自绘红绿灯标题栏（与主窗同款，去掉原生 −□✕）
        frameless = (os.name == "nt" and bool(self.app._frameless))
        if frameless:
            try:
                win.overrideredirect(True)
            except tk.TclError:
                frameless = False

        if frameless:
            self._build_apple_bar(win)
        else:
            self._build_plain_bar(win)

        _make_draggable(self.win)

        body = tk.Frame(win, bg=self._pal["win"])
        body.pack(fill="both", expand=True, padx=4, pady=(2, 0))
        self._build_left(body)
        self._build_right(body)
        self._build_chat(win)

    def _build_apple_bar(self, win) -> None:
        """苹果红绿灯标题栏：左红黄绿圆点，中居中标题，右「聊」钮；可拖动/双击最大化。"""
        from theme import BASE, get_skin
        sk = getattr(self.app, "_skin", None) or get_skin(None)
        bg = sk.get("titlebar_bg", "#ececee")
        fg = sk.get("titlebar_fg", "#1d1d1f")
        btn_fg = sk.get("titlebar_btn", "#86868b")
        hh = int(sk.get("titlebar_h", BASE["titlebar_h"]))
        bar = tk.Frame(win, bg=bg, height=hh)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)
        for w in (bar, ):                     # 标题栏可拖动整窗
            w.bind("<Button-1>", self._bar_press)
            w.bind("<B1-Motion>", self._bar_drag)
            w.bind("<Double-Button-1>", lambda _e: self._bar_max())
        # 红黄绿圆点
        for sym, col, hov, cmd in (
                ("✕", "#ff5f57", "#e4443e", self.hide),      # 红=收起到大厅/托盘
                ("—", "#febc2e", "#e0a423", self.hide),      # 黄=收起
                ("⤢", "#28c840", "#1aab2e", self._bar_max)): # 绿=最大化/还原
            dot = tk.Label(bar, text="●", font=("TkDefaultFont", 11),
                           bg=bg, fg=col, cursor="hand2", width=2)
            dot.pack(side="left", padx=1)
            dot.bind("<Button-1>", lambda _e, c=cmd: c())
            dot.bind("<Enter>", lambda _e, d=dot, s=sym, c=col:
                     d.config(text=s, fg=c))
            dot.bind("<Leave>", lambda _e, d=dot: d.config(text="●"))
        # 居中标题
        tk.Label(bar, text="🀄 桌游 · 协作大厅", bg=bg, fg=fg, font=(FONT_FAMILY, 11),
                 anchor="center").pack(side="left", fill="x", expand=True)
        # 右侧「聊」钮
        tk.Label(bar, text="聊", width=3, font=(FONT_FAMILY, 10), bg=bg, fg=btn_fg,
                 cursor="hand2").pack(side="right", padx=(0, 8))
        self._apple_bar = bar

    def _build_plain_bar(self, win) -> None:
        """原生边框兜底：仅标题 + 迷你「聊/隐藏」工具钮。"""
        bar = tk.Frame(win, bg=self._pal["win"])
        bar.pack(fill="x")
        self.title_label = tk.Label(bar, text="🀄 桌游 · 协作大厅", bg=self._pal["win"],
                                    fg=self._pal["sub"], font=(FONT_FAMILY, 11))
        self.title_label.pack(side="left", padx=8, pady=2)
        tk.Button(bar, text="—", width=2, command=self.hide,
                  font=(FONT_FAMILY, 10), relief="flat", fg=self._pal["sub"],
                  bg=self._pal["win"]).pack(side="right")
        tk.Button(bar, text="聊", width=3, command=self._toggle_chat,
                  font=(FONT_FAMILY, 10), relief="flat", fg=self._pal["sub"],
                  bg=self._pal["win"]).pack(side="right")

    # ---------- 苹果标题栏拖拽/最大化 ----------
    def _bar_press(self, ev) -> None:
        self._bar_offx, self._bar_offy = ev.x_root, ev.y_root
        self._bar_wx, self._bar_wy = self.win.winfo_x(), self.win.winfo_y()
        self._bar_maxed = bool(getattr(self, "_bar_maxed", False))

    def _bar_drag(self, ev) -> None:
        self.win.geometry(f"+{self._bar_wx + (ev.x_root - self._bar_offx)}+"
                          f"{self._bar_wy + (ev.y_root - self._bar_offy)}")

    def _bar_max(self) -> None:
        if not getattr(self, "_bar_maxed", False):
            self._bar_norm = self.win.geometry()
            sw = self.win.winfo_screenwidth()
            sh = max(20, self.win.winfo_screenheight())
            self.win.geometry(f"{sw}x{sh}+0+0")
            self._bar_maxed = True
        else:
            self.win.geometry(self._bar_norm)
            self._bar_maxed = False

    def _build_left(self, body) -> None:
        """卡片式大厅：桌游卡片网格（双击创建）+ 内嵌规则 + 房间卡片（双击加入/筛选/排序/进度）"""
        left = tk.Frame(body, width=360)
        left.pack(side="left", fill="both", expand=True, padx=(0, 4))
        left.pack_propagate(False)
        f = self._f = (FONT_FAMILY, FONT_SIZE)

        # 动作按钮行先 bottom 锚定：卡片/房间内容再多也挤压不到它，开局/退出始终可用
        btns = tk.Frame(left, bg=self._pal["win"])
        btns.pack(side="bottom", fill="x", pady=(0, 2))
        pal = self._pal
        acc = pal.get("accent", "#4f6ef2")
        acc_fg = pal.get("accent_fg", "#ffffff")
        acc_hover = pal.get("accent_hover", "#3d5be0")
        soft_bg = pal.get("soft_bg", "#eef0f5")
        for text, cmd, primary in (
                ("创建", self._on_create, True),
                ("加入", lambda: self._room_do("join"), False),
                ("观战", lambda: self._room_do("spectate"), False),
                ("离开", self._on_leave, False),
                ("刷新", lambda: self.core.game_list(), False)):
            b = tk.Button(btns, text=text, command=cmd, font=f, relief="flat",
                          padx=2, activebackground=acc_hover,
                          activeforeground=acc_fg, cursor="hand2")
            if primary:
                b.config(bg=acc, fg=acc_fg)
                b.bind("<Enter>", lambda e: e.widget.config(bg=acc_hover))
                b.bind("<Leave>", lambda e: e.widget.config(bg=acc))
            else:
                b.config(bg=soft_bg, fg=pal["fg"])
            b.pack(side="left", padx=(0, 2))
        tk.Button(btns, text="开始", command=self._on_start, font=f, relief="flat",
                  padx=2, bg=soft_bg, fg="teal").pack(side="left", padx=(0, 2))

        tk.Label(left, text="桌游 · 双击创建", fg=self._pal["sub"], font=f, anchor="w",
                 bg=self._pal["win"]).pack(fill="x")
        wrap, self.game_inner = self._scroll_area(left, height=self._game_zone_h)
        wrap.pack(fill="both", expand=True)
        self.game_inner.bind("<Configure>", lambda e: self._apply_game_grid())

        # 规则说明内嵌：点选桌游卡片即显示该游戏规则
        rules = tk.Frame(left, bg=self._pal["warn_bg"], height=64)
        rules.pack(fill="x", pady=(2, 0))
        rules.pack_propagate(False)
        self.rules_label = tk.Label(rules, text="点选桌游卡片查看规则；双击卡片直接创建房间",
                                    bg=self._pal["warn_bg"], fg=self._pal["warn_fg"],
                                    font=(FONT_FAMILY, FONT_SIZE - 2),
                                    wraplength=236, justify="left", anchor="nw",
                                    padx=4, pady=2)
        self.rules_label.pack(fill="both", expand=True)

        # 房间标题 + 筛选/排序
        flt = tk.Frame(left, bg=self._pal["win"])
        flt.pack(fill="x", pady=(2, 0))
        tk.Label(flt, text="房间 · 双击加入", fg=self._pal["sub"], font=f, anchor="w",
                 bg=self._pal["win"]).pack(side="left")
        self.sort_var = tk.StringVar(value="默认")
        tk.OptionMenu(flt, self.sort_var, "默认", "人最多", "人最少",
                      command=lambda _: self._refresh_rooms()).pack(side="right")
        self.filter_var = tk.StringVar(value="全部")
        tk.OptionMenu(flt, self.filter_var, "全部", "可加入", "进行中", "我的",
                      command=lambda _: self._refresh_rooms()).pack(side="right")

        wrap, self.room_inner = self._scroll_area(left)
        wrap.pack(fill="both", expand=True, pady=(0, 2))

    # 桌游区固定可视高度（容纳 2 行等高卡片 = 2×(156+10)）；超出内容自动滚动
    _game_zone_h = 2 * (156 + 10)

    def _scroll_area(self, parent, height=None):
        """返回 (外层容器, 内部滚动 Frame)：卡片网格/列表放入 inner，支持滚轮滚动。"""
        wrap = tk.Frame(parent, bg=self._pal["win"])
        canvas = tk.Canvas(wrap, bg=self._pal["win"], highlightthickness=0, height=height)
        sb = tk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=sb.set)      # 滚动条反映内容范围，否则永远显示不动
        inner = tk.Frame(canvas, bg=self._pal["win"])
        iid = canvas.create_window((0, 0), window=inner, anchor="nw")

        refresh = getattr(self, "_scroll_refresh", None)
        if refresh is None:
            self._scroll_refresh = []
        self._scroll_refresh.append(self)            # 占位：下面用闭包真正填充

        def _cfg(_e=None):
            # 高度取 inner 请求高：否则 canvas 的 window item 固定为 1x1，
            # scrollregion 永远算不出内容，滚动条/滚轮都滚不动。宽取画布宽。
            canvas.itemconfigure(iid, width=canvas.winfo_width(),
                                 height=max(1, inner.winfo_reqheight()))
            canvas.configure(scrollregion=canvas.bbox("all"))

        self._scroll_refresh[-1] = _cfg              # 把真正刷新回调注册回去

        inner.bind("<Configure>", _cfg)
        canvas.bind("<Configure>", _cfg)
        # 滚轮只在 canvas/inner 上绑定是无效的：Tk 事件沿 bindtags 链分发，不按几何父级
        # 冒泡——鼠标悬停在卡片（inner 的内部子控件）上滚动时，事件根本不落到 canvas/inner。
        # 故用 bind_all 统一分发：按悬停控件归属到对应滚动画布再滚动。
        regions = getattr(self, "_scroll_regions", None)
        if regions is None:
            self._scroll_regions = []                       # 每个 (canvas, inner) 一条
            # 用 Tk 根绑一次全局滚轮（wrap.winfo_toplevel() 通用，不依赖 self.root）
            wrap.winfo_toplevel().bind_all(
                "<MouseWheel>", self._dispatch_wheel)
        self._scroll_regions.append((canvas, inner))

        def _wheel(e):
            canvas.yview_scroll(-int(e.delta / 120), "units")
        canvas.bind("<MouseWheel>", _wheel)                 # 悬停画布本体时的兜底
        return wrap, inner

    def _dispatch_wheel(self, e):
        """全局滚轮：鼠标停留在哪个滚动区内的子控件上，就滚动对应的画布。"""
        target = getattr(e, "widget", None)
        if target is None or target == "":
            return None
        for canvas, inner in getattr(self, "_scroll_regions", ()):
            node = target
            while node is not None and node is not inner:
                node = getattr(node, "master", None)
            if node is inner:
                canvas.yview_scroll(-int(e.delta / 120), "units")
                return "break"                               # 阻止其它滚动处理
        return None

    def _build_right(self, body) -> None:
        right = tk.Frame(body, bg=self._pal["win"])
        right.pack(side="left", fill="both", expand=True)
        f = self._f
        wrap = tk.Frame(right, bg=self._pal["win"])
        wrap.pack(fill="both", expand=True)
        # 桌游对局图形区（Canvas 棋盘，鼠标点击直接交互）：独占弹性空间，
        # 窗口拉大时棋盘随之放大（日志区不再与其平分空间）。
        self._cv_ui = {"sel": {}}
        self.game_cv = tk.Canvas(wrap, bg=self._pal["win"], highlightthickness=0,
                                 height=1)
        self.game_cv.pack(fill="both", expand=True)
        self.game_cv.bind("<Configure>", self._on_cv_resize)
        self.game_cv.bind("<Button-1>", self._on_cv_click)
        self.game_cv.bind("<Motion>", self._on_cv_motion)
        # 日志区（系统事件 / 私密信息 / 规则提示）：底部固定高度，不抢对局面板
        self.state_text = tk.Text(right, font=f, state="disabled", wrap="word",
                                  relief="flat", bg=self._pal["win"], height=5)
        sb = tk.Scrollbar(right, command=self.state_text.yview)
        self.state_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.state_text.pack(side="bottom", fill="x")
        self.state_text.tag_configure("head", foreground=self._pal["fg"],
                                      font=(FONT_FAMILY, FONT_SIZE, "bold"))
        self.state_text.tag_configure("sys", foreground=self._pal["sub"])
        self.state_text.tag_configure("mine", foreground=self._pal["self"])
        self.state_text.tag_configure("priv", foreground=self._pal["priv"])

        # 动作区（顶部固定「游戏规则」按钮：入房看当前游戏，未入房看选中桌游）
        act = tk.Frame(right, bg=self._pal["win"])
        act.pack(fill="x", pady=(2, 0))
        tool = tk.Frame(act, bg=self._pal["win"])
        tool.pack(fill="x")
        tk.Button(tool, text="规则", command=self._show_rules_popup,
                  font=f, relief="flat", fg=self._pal["warn_fg"]).pack(
                      side="left", fill="x", expand=True, padx=2)
        tk.Button(tool, text="棋盘", command=self._focus_board,
                  font=f, relief="flat", padx=2, cursor="hand2",
                  bg=self._pal.get("accent", "#4f6ef2"),
                  fg=self._pal.get("accent_fg", "#ffffff"),
                  activebackground=self._pal.get("accent_hover", "#3d5be0"))\
            .pack(side="left", fill="x", expand=True, padx=2)
        tk.Button(tool, text="专注窗", command=self._spawn_board_win,
                  font=f, relief="flat", padx=0, cursor="hand2",
                  fg=self._pal["fg"], bg=self._pal.get("soft_bg", "#eef0f5"),
                  activebackground=self._pal.get("accent_hover", "#3d5be0"))\
            .pack(side="left", fill="x", expand=True, padx=2)
        self.act_btns = tk.Frame(act, bg=self._pal["win"])
        self.act_btns.pack(fill="x")
        self.act_hint = tk.Label(act, text="", fg=self._pal["sub"], font=f, anchor="w",
                                 bg=self._pal["win"])
        self.act_hint.pack(fill="x")

    def _build_chat(self, win) -> None:
        """聊天 overlay 面板：默认收起（点顶栏「聊」展开）"""
        f = self._f
        self.chat_panel = tk.Frame(win, bg=self._pal["win"])
        self.chat_text = tk.Text(self.chat_panel, font=f, state="disabled",
                                 wrap="word", relief="flat",
                                 bg=self._pal["input"], height=5)
        self.chat_text.tag_configure("self", foreground=self._pal["self"])
        sb = tk.Scrollbar(self.chat_panel, command=self.chat_text.yview)
        self.chat_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.chat_text.pack(side="left", fill="both", expand=True)
        crow = tk.Frame(self.chat_panel, bg=self._pal["win"])
        crow.pack(fill="x")
        self.chat_entry = tk.Entry(crow, font=f)
        self.chat_entry.pack(side="left", fill="x", expand=True)
        self.chat_entry.bind("<Return>", lambda e: self._send_overlay())
        tk.Button(crow, text="发送", command=self._send_overlay,
                  font=f, padx=6).pack(side="left")

    # ---------- 事件轮询（状态快照驱动，不抢主窗队列） ----------
    def _poll(self) -> None:
        if self._closed:
            return
        try:
            self._sync()
        except Exception:
            pass
        self.win.after(200, self._poll)

    def _sync(self) -> None:
        core = self.core
        if (core.game_meta, core.game_rooms) != self._last_list:
            self._last_list = (dict(core.game_meta), list(core.game_rooms))
            self._refresh_lists()
        if (core.game_room, core.game_state) != (self._last_room, self._last_state):
            left_room = self._last_room is not None and core.game_room is None
            self._last_room = core.game_room
            self._last_state = core.game_state
            self._render_state()
            self._events_shown = 0  # 文本区重建后按本轮 core 记录重画，不能按旧长度跳过。
            if left_room:
                self.hide(reason="state")
        if core.game_private != self._last_private:
            self._last_private = core.game_private
            self._render_private()
        if len(core.game_events) < self._events_shown:
            self._events_shown = 0
        if len(core.game_events) > self._events_shown:
            new = list(core.game_events)[self._events_shown:]
            self._events_shown = len(core.game_events)
            for line in new:
                self._append_state(line, "sys")
        if self._chat_open:
            hist = core.history("public")
            if hist != self._last_hist:
                self._last_hist = hist
                self._render_chat(hist)

    # ---------- 列表（卡片式） ----------
    def _refresh_lists(self) -> None:
        self._refresh_games()
        self._refresh_rooms()
        if not self.core.game_room:
            self._render_state()          # 未入房时同步右侧选中预览

    def _refresh_games(self) -> None:
        core = self.core
        scroll = self._scroll_regions[0][0]
        scroll_y = scroll.yview()[0]
        # The column cache only describes the old widget generation.
        self._cols_active = None
        for w in self.game_inner.winfo_children():
            w.destroy()
        self.game_cards = {}
        self._game_order = sorted(core.game_meta.keys())
        if self._sel_game not in core.game_meta:
            self._sel_game = None
        if not self._game_order:                   # 空状态：别让大厅变成一片空白
            tk.Label(self.game_inner, text="正在获取桌游列表…\n请确认已连接服务器（桌游随服务器端启停）",
                     bg=self._pal["win"], fg=self._pal["sub"], justify="center",
                     font=(FONT_FAMILY, FONT_SIZE)).grid(
                row=0, column=0, columnspan=6, sticky="nsew", padx=8, pady=12)
            self.game_inner.grid_columnconfigure(0, weight=1)
            for column in range(1, 6):
                self.game_inner.grid_columnconfigure(column, weight=0)
            self.game_inner.update_idletasks()
            self._game_scroll_refresh()
            scroll.yview_moveto(0)
            self._highlight_game()
            return
        for name in self._game_order:
            card = _GameCard(self.game_inner, name, core.game_meta[name],
                             on_click=self._on_pick_game,
                             on_double=self._on_create_game, pal=self._pal)
            self.game_cards[name] = card
        self._apply_game_grid()
        self._highlight_game()
        scroll.yview_moveto(scroll_y)

    def _game_cols(self) -> int:
        """按当前左栏宽度自适应列数（2~6 列），拉宽窗口桌游卡横向铺开。"""
        try:
            w = self.game_inner.winfo_width()
        except Exception:
            w = 0
        cols = int(max(2, min(6, (w - 6) // 158)))
        return cols

    def _apply_game_grid(self) -> None:
        if not hasattr(self, "_game_order"):
            return
        cols = self._game_cols()
        # 列数未变就保持现有布局：避免一边拖拽窗口一边反复重排导致卡片「跳动」
        if cols == getattr(self, "_cols_active", None) and \
                hasattr(self, "_cols_active"):
            self.game_inner.update_idletasks()
            self._game_scroll_refresh()
            return
        self._cols_active = cols
        for i, name in enumerate(self._game_order):
            self.game_cards[name].grid(row=i // cols, column=i % cols,
                                       padx=5, pady=5, sticky="nsew")
        for c in range(6):                  # Also clear weights of removed columns.
            self.game_inner.grid_columnconfigure(c, weight=int(c < cols))
        self.game_inner.update_idletasks()
        self._game_scroll_refresh()

    def _game_scroll_refresh(self) -> None:
        """布局变化后刷新桌游滚动区范围：canvas 的 window item 高度要跟随网格内容，
        否则 scrollregion 停在 1x1，滚动条/滚轮都滚不动。"""
        try:
            cb = getattr(self, "_scroll_refresh", None)
            if cb:
                cb[0]()
        except Exception:
            pass

    def _refresh_rooms(self) -> None:
        core = self.core
        for w in self.room_inner.winfo_children():
            w.destroy()
        self.room_cards = {}
        for r in self._filter_rooms():
            card = _RoomCard(self.room_inner, r["room_id"], r, core,
                             on_click=self._on_pick_room,
                             on_double=self._on_double_room,
                             on_menu=self._on_room_menu, pal=self._pal)
            card.pack(fill="x", padx=3, pady=2)
            self.room_cards[r["room_id"]] = card
        self._highlight_room()
        try:                                    # 房间区也要刷新 scrollregion（区域 index=1）
            cb = getattr(self, "_scroll_refresh", None)
            if cb and len(cb) > 1:
                cb[1]()
        except Exception:
            pass

    def _filter_rooms(self) -> list:
        """房间筛选 + 排序（全部/可加入/进行中/我的 × 默认/人最多/人最少）"""
        core = self.core
        me = core.uid
        flt = self.filter_var.get()
        rooms = list(core.game_rooms)
        if flt == "可加入":
            rooms = [r for r in rooms if r["status"] == "created" and not self._room_full(r)]
        elif flt == "进行中":
            rooms = [r for r in rooms if r["status"] == "playing"]
        elif flt == "我的":
            rooms = [r for r in rooms if r.get("owner_uid") == me or
                     me in r.get("players", []) or me in r.get("spectators", [])]
        srt = self.sort_var.get()
        if srt == "人最多":
            rooms.sort(key=lambda r: len(r.get("players", [])), reverse=True)
        elif srt == "人最少":
            rooms.sort(key=lambda r: len(r.get("players", [])))
        return rooms

    def _room_full(self, r) -> bool:
        maxp = self.core.game_meta.get(r["game"], {}).get("max")
        return bool(maxp) and len(r.get("players", [])) >= maxp

    def _room_by_id(self, rid: str):
        for r in self.core.game_rooms:
            if r["room_id"] == rid:
                return r
        return None

    def _highlight_game(self) -> None:
        for name, card in getattr(self, "game_cards", {}).items():
            card.set_selected(name == self._sel_game)

    def _highlight_room(self) -> None:
        for rid, card in getattr(self, "room_cards", {}).items():
            card.set_selected(rid == self._sel_room)

    # ---------- 卡片交互（单击选中 / 双击快捷动作 / 右键菜单） ----------
    def _on_pick_game(self, name: str) -> None:
        self._sel_game = name
        self._highlight_game()
        self._render_rules()
        self._render_state()

    def _on_create_game(self, name: str) -> None:
        status, note = _desktop_game_status(name)
        if status == "unsupported":
            self._append_state(f"{name}：{note}，保留服务器/Web入口；本端不创建房间", "warn")
            return
        self._sel_game = name
        self._highlight_game()
        self._render_rules()
        self.core.game_create(name)

    def _render_rules(self) -> None:
        m = self.core.game_meta.get(self._sel_game or "")
        status, note = _desktop_game_status(self._sel_game or "")
        suffix = f"\n\n桌面入口：{note}" if status != "flagship" else ""
        self.rules_label.config(
            text=((m.get("rules", "") + suffix) if m
                  else "点选桌游卡片查看规则；双击卡片直接创建房间"))

    def _show_rules_popup(self) -> None:
        """游戏内规则弹窗：入房取当前房间游戏，未入房取选中桌游；规则来自 GAME_META"""
        name = (self.core.game_room or {}).get("game") or self._sel_game
        meta = self.core.game_meta.get(name or "")
        if not meta:
            self._append_state("未选中桌游/未加入房间，无法查看规则", "sys")
            return
        pop = tk.Toplevel(self.win)
        pop.title(f"{meta.get('label', name)} · 规则")
        pop.configure(bg=self._pal["warn_bg"])
        pop.geometry(f"420x380+{_screen_w(pop) - 500}+120")
        try:
            pop.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(pop, text=f"{meta.get('label', name)} · 规则",
                 font=(FONT_FAMILY, FONT_SIZE, "bold"), bg=self._pal["warn_bg"],
                 fg=self._pal["warn_fg"]
                 ).pack(anchor="w", padx=10, pady=(8, 2))
        box = tk.Text(pop, font=(FONT_FAMILY, FONT_SIZE), wrap="word",
                      bg=self._pal["warn_bg"], relief="flat", padx=8, pady=4)
        box.insert("1.0", meta.get("rules", "") or "（暂无规则说明）")
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        tk.Button(pop, text="关闭", command=pop.destroy,
                  font=(FONT_FAMILY, FONT_SIZE), relief="flat").pack(pady=(0, 8))

    def _on_pick_room(self, rid: str) -> None:
        self._sel_room = rid
        self._highlight_room()
        self._render_state()

    def _on_double_room(self, rid: str) -> None:
        """双击房间卡片：可加入则加入，满员/进行中自动转观战"""
        r = self._room_by_id(rid)
        if not r:
            return
        status, note = _desktop_game_status(r.get("game", ""))
        if status == "unsupported":
            self._append_state(f"{r.get('game', '')}：{note}，本端不加入/观战", "warn")
            return
        if r["status"] != "playing" and not self._room_full(r):
            self.core.game_join(rid)
        else:
            self.core.game_spectate(rid)

    def _spectate_room(self, rid: str) -> None:
        r = self._room_by_id(rid)
        if r is not None and _desktop_game_status(r.get("game", ""))[0] == "unsupported":
            self._append_state(f"{r.get('game', '')}：桌面端当前不支持主要操作，本端不观战", "warn")
            return
        self.core.game_spectate(rid)

    def _on_room_menu(self, ev, rid: str) -> None:
        menu = tk.Menu(self.win, tearoff=0)
        menu.add_command(label="加入", command=lambda: self._on_double_room(rid))
        menu.add_command(label="观战", command=lambda: self._spectate_room(rid))
        menu.add_command(label="刷新", command=lambda: self.core.game_list())
        menu.tk_popup(ev.x_root, ev.y_root)
        menu.grab_release()

    # ---------- 状态渲染 ----------
    def _render_state(self) -> None:
        self._render_canvas()          # 同步图形区（非对局会自动清空）
        self.state_text.configure(state="normal")
        self.state_text.delete("1.0", "end")
        self.state_text.configure(state="disabled")
        room = self.core.game_room
        st = self.core.game_state
        if not room:
            r = self._room_by_id(self._sel_room) if self._sel_room else None
            if r:
                # 未入房：右侧预览选中的房间卡片
                meta = self.core.game_meta.get(r["game"], {})
                label = meta.get("label", r["game"])
                status = {"created": "大厅", "playing": "进行中",
                          "ended": "结算中"}.get(r["status"], r["status"])
                players = [self._nick(u) for u in r.get("players", [])]
                spec = r.get("spectators", []) or []
                self._append_state(f"{label} {r['room_id']} · {status}", "head")
                self._append_state(f"玩家：{'、'.join(players) or '无'}", "sys")
                if spec:
                    self._append_state(f"观战：{len(spec)} 人", "sys")
                self._append_state("双击卡片加入；满员或进行中自动转观战", "sys")
                self._rebuild_actions(None)
                return
            m = self.core.game_meta.get(self._sel_game or "") or {}
            hint = (f"已选桌游：{m.get('label', '')}——双击卡片创建房间"
                    if self._sel_game
                    else "未加入房间：双击桌游卡片创建，或双击房间卡片加入")
            self._append_state(hint, "head")
            self._rebuild_actions(None)
            return
        label = self.core.game_meta.get(room.get("game"), {}).get("label",
                                                                  room.get("game"))
        status = {"created": "大厅", "playing": "对局中", "ended": "结算中"}.get(
            room.get("status"), room.get("status", ""))
        me = self.core.uid
        players = [f"{self._nick(u)}{'(我)' if u == me else ''}"
                   for u in room.get("players", [])]
        spec = room.get("spectators", []) or []
        head = (f"{label} · {room.get('room_id')} · {status}"
                f" · 第 {room.get('round', 0)} 轮")
        self._append_state(head, "head")
        self._append_state(f"玩家：{'、'.join(players) or '无'}", "sys")
        if spec:
            self._append_state(f"观战：{len(spec)} 人", "sys")
        if room.get("owner_uid") == me and room.get("status") == "created":
            self._append_state("你是房主，可开始对局", "mine")
        if st is None:
            if room.get("status") == "created":
                self._append_state("等待房主开始对局…", "sys")
            self._rebuild_actions(room.get("game"))
            return
        self._append_state(self._fmt_state(st), "sys")
        self._rebuild_actions(room.get("game"))

    def _render_canvas(self, force: bool = False) -> None:
        """桌游对局 Canvas 图形渲染（棋盘/手牌/角色面板）。
        持独立专注窗时改画到专注窗；否则画到大厅内嵌棋盘。"""
        if getattr(self, "_board_win", None) and self._board_win.active():
            self._board_win.redraw(force=force)
            return
        self._cv_ui["_after_owner"] = self.win
        self._render_to(self.game_cv, self._cv_ui)

    def _cancel_repaint(self, ui) -> None:
        job = ui.pop("_after_id", None)
        if job is None:
            return
        owner = ui.get("_after_owner") or self.win
        try:
            owner.after_cancel(job)
        except (tk.TclError, AttributeError):
            pass

    def _schedule_repaint(self, cv, ui, delay=40) -> None:
        """Queue one finite flagship animation frame on the owning window."""
        if ui.get("_after_id") is not None:
            return
        owner = ui.get("_after_owner") or self.win
        context = ui.get("_room_context")
        try:
            if owner.state() in ("withdrawn", "iconic") or not cv.winfo_exists():
                return
        except (tk.TclError, AttributeError):
            return

        def _tick():
            ui["_after_id"] = None
            try:
                if (self._closed or owner.state() in ("withdrawn", "iconic")
                        or not cv.winfo_exists()
                        or ui.get("_room_context") != context):
                    return
            except (tk.TclError, AttributeError):
                return
            self._render_to(cv, ui)

        try:
            ui["_after_id"] = owner.after(max(1, int(delay)), _tick)
        except (tk.TclError, AttributeError):
            ui.pop("_after_id", None)

    def _render_to(self, cv, ui) -> None:
        """通用棋盘渲染核心：把当前对局快照画到指定 canvas
        （大厅内嵌 game_cv 与独立专注窗 BoardFocusWindow 共用）。"""
        room = self.core.game_room
        st = self.core.game_state
        context = ((room or {}).get("room_id"), (room or {}).get("round"))
        if ui.get("_room_context") != context:
            self._cancel_repaint(ui)
        ui["_room_context"] = context
        ui["room"] = room
        ui["state"] = st
        ui["connected"] = bool(getattr(self.core, "connected", False))
        ui["_cancel_repaint"] = lambda target_ui=ui: self._cancel_repaint(target_ui)
        ui["_schedule_repaint"] = (
            lambda delay=40, target_cv=cv, target_ui=ui:
            self._schedule_repaint(target_cv, target_ui, delay))
        if not room or not st or room.get("status") not in ("playing", "ended"):
            self._cancel_repaint(ui)
            ui["can_move"] = False
            ui["game"] = None
            cv.delete("all")
            return
        game = room.get("game")
        ui["game"] = game
        ui["can_move"] = (
            client_gameui.flagship_can_move(room, st, self.core.uid,
                                             getattr(self.core, "connected", False))
            if game in ("gomoku", "connect4") else False
        )
        ui["submit"] = lambda action, target_ui=ui: self._do_action(action, target_ui)
        ui["repaint"] = lambda target_cv=cv, target_ui=ui: self._render_to(
            target_cv, target_ui)
        ui["nick"] = self._nick
        ui["me"] = self.core.uid
        client_gameui.render(cv, game, st, self.core.uid, self._nick,
                             ui["submit"], ui["repaint"], ui,
                             self.core.game_private,
                             cv.winfo_width(), cv.winfo_height())

    def _on_cv_resize(self, _evt) -> None:
        try:
            self.win.after_idle(self._render_canvas)
        except Exception:
            pass

    def _on_cv_click(self, evt) -> None:
        try:
            client_gameui.handle_click(self._cv_ui, evt.x, evt.y)
        except Exception:
            pass

    def _on_cv_motion(self, evt) -> None:
        # 悬停高亮：仅在进入/离开格子时重绘，避免抖动
        try:
            ui = self._cv_ui
            if not ui.get("game"):
                return
            cur = client_gameui._cell_of(ui, evt.x, evt.y)
            prev = ui.get("_hover")
            # 卡牌/可点区悬停：命中 ui['_hov'] 里登记的矩形 → 记录索引用于上浮
            hidx = None
            for i, (a0, a1, a2, a3) in enumerate(ui.get("_hov") or ()):
                if a0 <= evt.x <= a2 and a1 <= evt.y <= a3:
                    hidx = i
                    break
            prevh = ui.get("_hov_idx")
            if cur != prev or hidx != prevh:
                if cur is None:
                    ui.pop("_hover", None)
                else:
                    ui["_hover"] = cur
                if hidx is None:
                    ui.pop("_hov_idx", None)
                else:
                    ui["_hov_idx"] = hidx
                self.win.after_idle(self._render_canvas)
        except Exception:
            pass

    def _fmt_state(self, st: dict) -> str:
        """公开快照 → 可读文本（按游戏定制 + 兜底 key-value）"""
        game = st.get("game", "")
        lines = []
        if st.get("status") == "await_secret":
            lines.append("等待出题者设置数字…")
        elif st.get("status") == "playing" and game == "guess_number":
            lg = st.get("last_guess")
            if lg:
                lines.append(f"上轮 {self._nick(lg['uid'])} 猜 {lg['val']}：{lg['dir']}")
            lines.append(f"区间 {st.get('low')}~{st.get('high')}")
        elif game == "gomoku" and "board" in st:
            board = st["board"]
            lines.append("  " + " ".join(str(i % 10) for i in range(len(board[0]))))
            for y, row in enumerate(board):
                lines.append(f"{y%10} " + " ".join("●" if c == 1 else
                                                   "○" if c == 2 else "·" for c in row))
            if st.get("turn_uid"):
                lines.append(f"轮到 {self._nick(st['turn_uid'])}")
            if st.get("winner_uid"):
                lines.append(f"🏆 {self._nick(st['winner_uid'])} 获胜")
            elif st.get("draw"):
                lines.append("平局")
        elif game == "rps":
            sub = st.get("submitted") or {}
            lines.append(f"已出拳：{len(sub)}/{len(st.get('players', []))}")
        elif game == "blackjack":
            hands = st.get("hands") or {}
            for u, cards in hands.items():
                who = "我" if int(u) == self.core.uid else self._nick(int(u))
                lines.append(f"{who}：{' '.join(cards)}")
            if st.get("dealer"):
                lines.append(f"庄家：{' '.join(st['dealer'])}")
            if st.get("results"):
                lines.append("结算：" + "，".join(
                    f"{self._nick(int(u))} {'胜' if r == 'win' else '平' if r == 'draw' else '负'}"
                    for u, r in st["results"].items()))
        elif game == "uno":
            if st.get("top"):
                lines.append(f"弃牌堆顶：{st['top']}（当前色 {st.get('top_color')}）")
            if st.get("turn_uid"):
                lines.append(f"轮到 {self._nick(st['turn_uid'])}")
            if st.get("scores"):
                lines.append("积分：" + "、".join(
                    f"{self._nick(int(u))} {s}" for u, s in st["scores"].items()))
        elif game == "spy":
            alive = st.get("alive") or []
            lines.append(f"存活 {len(alive)} 人，第 {st.get('round', 1)} 轮描述中")
        elif game == "onewolf":
            ph = {"night": "🌙 夜晚行动", "vote": "🗳️ 投票处决", "result": "🏁 揭晓"}.get(
                st.get("phase"), st.get("phase"))
            lines.append(f"阶段：{ph} · {len(st.get('players') or [])} 人")
            if st.get("need_act"):
                lines.append("待行动：" + "、".join(self._nick(u) for u in st["need_act"]))
            if st.get("acted"):
                lines.append("已行动：" + "、".join(self._nick(u) for u in st["acted"]))
            if st.get("dead"):
                lines.append("⚖️ 被处决：" + "、".join(self._nick(u) for u in st["dead"]))
            if st.get("phase") == "result":
                rev = st.get("reveal") or {}
                lines.append("身份揭晓：" + "、".join(
                    f"{self._nick(u)} {r}" for u, r in rev.items()))
                lines.append("🎉 好人获胜" if st.get("winner") else "🐺 狼人获胜")
        elif game == "werewolf":
            ph = {"night_seer": "🔮 预言家验人", "night_wolf": "🐺 狼人刀人",
                  "night_witch": "🧪 女巫用药", "shoot": "🏹 猎人开枪",
                  "day": "☀️ 白天投票", "done": "🏁 已结束"}.get(st.get("phase"), st.get("phase"))
            alive = st.get("alive") or []
            lines.append(f"第 {st.get('night', 1)} 夜 · {ph} · 存活 {len(alive)} 人")
            if st.get("phase") == "day" and st.get("voted"):
                lines.append("已投票：" + "、".join(self._nick(u) for u in st["voted"]))
            if st.get("lynched"):
                lines.append(f"⚖️ 被放逐：{self._nick(st['lynched'])}")
            if st.get("done"):
                lines.append("🎉 好人获胜" if st.get("winner") else "🐺 狼人获胜")
        elif game == "avalon":
            ph = {"nominate": "👑 领袖组队", "teamvote": "🗳️ 团队投票",
                  "quest": "🃏 执行任务", "final": "🎯 刺客指认",
                  "done": "🏁 已结束"}.get(st.get("phase"), st.get("phase"))
            lines.append(f"任务 {st.get('quest', 0)}/5 · {ph} · 需 {st.get('need_size', 0)} 人")
            results = "".join("✅" if r else "💥" for r in st.get("results", []))
            lines.append(f"结果：{results or '—'}")
            if st.get("leader"):
                lines.append(f"👑 领袖：{self._nick(st['leader'])}")
            if st.get("team"):
                lines.append("当前团队：" + "、".join(self._nick(u) for u in st["team"]))
            if st.get("need"):
                lines.append("待行动：" + "、".join(self._nick(u) for u in st["need"]))
            if st.get("done"):
                lines.append("🛡️ 好人获胜" if st.get("winner") else "🗡️ 坏人获胜")
        elif game == "liar":
            is_me = st.get("turn") == self.core.uid
            lines.append("🎲 骗子酒馆 · " + ("轮到你行动" if is_me else "等待行动"))
            pend = st.get("pending")
            if pend:
                lines.append(f"🃏 {self._nick(pend['uid'])} 报数 {pend['claim']}（真值保密）")
            else:
                lines.append("🃏 桌面空，先出牌")
            drink = st.get("drink") or {}
            if drink:
                lines.append("酒量：" + "、".join(
                    f"{self._nick(int(u))} {c}杯" for u, c in drink.items()))
            hs = st.get("hand_size") or {}
            lines.append("手牌：" + "、".join(
                f"{self._nick(int(u))}×{c}" for u, c in hs.items()))
            if st.get("done"):
                lines.append(f"🏆 {self._nick(st['winner'])} 最后留在桌上获胜")
        elif game == "ninja":
            lines.append(f"🥷 忍者之夜 · 第 {st.get('round', 1)} 回合 · "
                         + ("暗选行动中" if st.get("phase") == "pick" else "结算中"))
            alive = st.get("alive") or []
            hp = st.get("hp") or {}
            lines.append("存活：" + "、".join(
                f"{self._nick(u)}({hp.get(str(u), 0)}血)" for u in alive))
            if st.get("last"):
                lines.append("⚡ " + "；".join(st["last"]))
            if st.get("done"):
                lines.append(f"🏆 {self._nick(st['winner'])} 是最后存活的忍者")
        elif game == "drawguess":
            if st.get("phase") == "round_end":
                lines.append(f"答案揭晓：{st.get('word')}")
            else:
                lines.append(f"画手：{self._nick(st.get('drawer_uid'))}，大家猜词")
        elif game == "connect4" and "board" in st:
            board = st["board"]
            lines.append("  " + " ".join(str(i) for i in range(len(board[0]))))
            for row in board:
                lines.append("  " + " ".join("🔴" if c == 1 else
                                             "🔵" if c == 2 else "·" for c in row))
            if st.get("turn_uid"):
                lines.append(f"轮到 {self._nick(st['turn_uid'])}")
            if st.get("winner_uid"):
                lines.append(f"🏆 {self._nick(st['winner_uid'])} 获胜")
            elif st.get("draw"):
                lines.append("平局")
        elif game == "othello" and "board" in st:
            board = st["board"]
            lines.append("  " + " ".join(str(i % 10) for i in range(len(board[0]))))
            uid0, uid1 = st.get("players", [None, None])
            for y, row in enumerate(board):
                marks = []
                for c in row:
                    if c == 1:
                        marks.append("●")
                    elif c == 2:
                        marks.append("○")
                    else:
                        marks.append("·")
                lines.append(f"{y%10} " + " ".join(marks))
            if st.get("passing"):
                lines.append("对手让过，轮到你连下")
            if st.get("scores"):
                b, w = st["scores"].values()
                lines.append(f"⚫ {b}   ⚪ {w}")
            elif st.get("turn_uid"):
                lines.append(f"轮到 {self._nick(st['turn_uid'])}")
            if uid0 is not None:
                lines.append(f"⚫ {self._nick(uid0)} ⚪ {self._nick(uid1)}")
        elif game == "calc24":
            if st.get("cards"):
                face = "、".join(map(str, st["cards"]))
                if st.get("status") == "answering":
                    lines.append(f"牌：{face}  等待作答（剩 {st.get('wait', 0)}s）")
                elif st.get("solved_uid"):
                    lines.append(f"牌：{face}  已被 {self._nick(st['solved_uid'])} 答对")
            if st.get("win_expr"):
                lines.append(f"答案：{st['win_expr']} = 24")
            if st.get("scores"):
                lines.append("积分：" + "、".join(
                    f"{self._nick(int(u))} {s}" for u, s in st["scores"].items()))
        elif game == "matchpairs":
            if st.get("safe"):
                lines.append("已安全：" + "、".join(self._nick(u) for u in st["safe"]))
            if st.get("hand_size"):
                lines.append("余牌：" + "、".join(
                    f"{self._nick(int(u))} {n}张" for u, n in st["hand_size"].items()))
            if st.get("turn_uid"):
                lines.append(f"轮到 {self._nick(st['turn_uid'])} 摸下一家")
            if st.get("loser_uid"):
                lines.append(f"🐢 {self._nick(st['loser_uid'])} 成为王八！")
        elif game == "betrayal":
            rooms = st.get("rooms") or {}
            pos = {int(u): tuple(map(int, v.split(",")))
                   for u, v in (st.get("pos") or {}).items()}
            seats = {int(u): n for u, n in (st.get("seats") or {}).items()}
            if rooms:
                pts = [tuple(map(int, k.split(","))) for k in rooms]
                occ = {}
                for u, p in pos.items():
                    occ.setdefault(p, []).append(seats.get(u, "?"))
                for y in range(min(p[1] for p in pts), max(p[1] for p in pts) + 1):
                    row = [rooms.get(f"{x},{y}", "·")
                           for x in range(min(p[0] for p in pts), max(p[0] for p in pts) + 1)]
                    lines.append("  " + " ".join(row))
                for (x, y), ss in sorted(occ.items()):
                    lines.append(f"  {rooms.get(f'{x},{y}', '?')}({x},{y})："
                                 + "、".join(f"{s}号" for s in ss))
            alive = set(st.get("alive") or [])
            items = st.get("items") or {}
            for u, s in (st.get("stats") or {}).items():
                ui = int(u)
                extra = f"｜{'、'.join(items.get(u, []))}" if items.get(u) else ""
                lines.append(f"{seats.get(ui, '?')}号 {self._nick(ui)}"
                             f"{'☠' if ui not in alive else ''}"
                             f" 力{s['might']} 速{s['speed']}"
                             f" 智{s['sanity']} 知{s['knowledge']}{extra}")
            if st.get("phase") == "haunt" and st.get("haunt"):
                h = st["haunt"]
                lines.append(f"⚡ 惊魂降临《{h['scenario']}》 叛徒：{self._nick(h['traitor'])}")
                lines.append(f"🚪 出口之门位于 ({h['exit']})，幸存者全员抵达后可全员撤离")
            else:
                lines.append(f"预兆 {st.get('omens', 0)} 枚（每抽一枚需做惊魂检定）")
            if st.get("turn_uid"):
                lines.append(f"轮到 {self._nick(st['turn_uid'])}"
                             f"（剩余 {st.get('steps_left', 0)} 步）")
        elif game == "davinci":
            lbl = st.get("label") or {}
            def lav(v): return lbl.get(str(v), v)
            for u, tiles in (st.get("hands") or {}).items():
                me = "（你）" if int(u) == self.core.uid else ""
                disp = " ".join((lav(t["v"]) if t["open"] else "▮?") for t in tiles)
                lines.append(f"{self._nick(int(u))}{me}：" + disp)
            lines.append(f"轮到 {self._nick(st.get('turn'))} · 牌堆剩 {st.get('draw_left')} 张")
            if st.get("dead"):
                lines.append("出局：" + "、".join(self._nick(u) for u in st["dead"]))
        elif game == "kalah":
            c = st.get("cells") or []
            lines.append("对手(上)：" + " ".join(str(c[i]) for i in range(13, 7, -1))
                         + f"  库 {c[7] if len(c) > 7 else '?'}")
            lines.append("你(下)　：" + " ".join(str(c[i]) for i in range(0, 6))
                         + f"  库 {c[6] if len(c) > 6 else '?'}")
            lines.append(f"轮到 {self._nick(st.get('turn'))} 播子")
        elif game == "lovelove":
            lines.append("存活：" + (", ".join(self._nick(u) for u in (st.get("alive") or [])) or "无"))
            if st.get("dead"):
                lines.append("出局：" + ", ".join(self._nick(u) for u in st["dead"]))
            lines.append("废牌：" + "、".join(str(x[1]) for x in (st.get("discard") or []))
                         + f"　牌堆剩 {st.get('deck_left')} 张")
            lines.append(f"轮到 {self._nick(st.get('cur'))}")
        elif game == "halloween":
            lines.append("轮到：" + self._nick(st.get("turn")))
            lines.append("桌上：「" + " ".join(st.get("area") or []) + "」　"
                         + "　".join(f"{f}×{n}" for f, n in (st.get("counts") or {}).items()))
            if st.get("can_slap"):
                lines.append("🔔 已有 5 个相同水果，可拍铃！")
            lines.append("得分：" + "、".join(
                f"{self._nick(int(u))} {v}" for u, v in (st.get("score") or {}).items()))
        if st.get("scores") and game not in ("uno",):
            lines.append("积分：" + "、".join(
                f"{self._nick(int(u))} {s}" for u, s in st["scores"].items()))
        elif game == "coc":
            ph = {"setup": "🔰 选择调查员", "play": "🎭 自由调查"}.get(
                st.get("phase"), st.get("phase"))
            lines.append(f"{ph} · KP：{self._nick(st.get('kp_uid'))}")
            picked = st.get("picked") or {}
            lines.append(f"已选卡：{'、'.join(self._nick(int(u)) + '=' + c
                                             for u, c in picked.items()) or '无'}"
                         + f"　未选 {len(st.get('players') or []) - len(picked)} 人")
            if st.get("scene"):
                lines.append("🗒️ 场景：" + st["scene"])
            for log in (st.get("logs") or [])[-8:]:
                lines.append(log)
        if st.get("secret") is not None and game == "guess_number":
            lines.append(f"本轮答案：{st['secret']}")
        if not lines:
            lines.append(self._fmt_generic(st))
        return "\n".join(lines)

    def _fmt_generic(self, st: dict) -> str:
        """无定制渲染的游戏：只输出自然语言轮次/胜负/玩家，不dump原始状态。"""
        bits = []
        turn = st.get("turn_uid", st.get("turn"))
        if turn is not None:
            bits.append(f"轮到 {self._nick(turn)}")
        for wkey, emoji in (("winner_uid", "🏆"), ("winner", "🏆")):
            win = st.get(wkey)
            if win is not None:
                bits.append(f"{emoji} {self._nick(win)} 获胜")
                break
        if st.get("draw"):
            bits.append("平局")
        if st.get("round"):
            bits.append(f"第 {st['round']} 轮")
        phase = st.get("phase") or st.get("status")
        if isinstance(phase, str) and phase and phase != "playing":
            bits.append(f"{phase}")
        if not bits:
            bits.append("对局进行中")
        return " · ".join(bits)

    def _render_private(self) -> None:
        p = self.core.game_private
        if not p:
            return
        self._append_state("—— 你的私密信息 ——", "priv")
        if "hp" in p and set(p.keys()) == {"hp"}:    # 忍者之夜
            self._append_state(f"你的生命：{p['hp']}/3", "priv")
        elif isinstance(p.get("hand"), int):   # 情书：密信牌值
            self._append_state(f"你的密信牌：{p['hand']}", "priv")
        elif isinstance(p.get("hand"), list) and p["hand"] and isinstance(p["hand"][0], int):  # 骗子酒馆
            self._append_state("你的手牌：" + "、".join(str(v) for v in p["hand"]), "priv")
        elif "hand" in p:            # UNO
            self._append_state("手牌：" + " ".join(p["hand"]), "priv")
        elif "origin" in p:          # 一夜狼人
            self._append_state("你的身份：" + p["name"]
                               + (f"（初始：{p['origin']}）" if p.get("origin") != p.get("name") else ""), "priv")
            if p.get("role") == 1:   # 狼人
                mates = p.get("teammates") or []
                self._append_state("狼队友：" + ("、".join(self._nick(m) for m in mates) if mates else "仅你一人"), "priv")
            if p.get("seer_view"):
                v = p["seer_view"]
                self._append_state(f"🔮 看到 {self._nick(v['uid'])} 是 {v['name']}", "priv")
            if p.get("seer_center"):
                c = p["seer_center"]
                self._append_state(f"🔮 中心两张：{c['role_a']} / {c['role_b']}", "priv")
            if p.get("robbed_role"):
                self._append_state(f"🗡️ 换牌后你的身份：{p['robbed_role']}", "priv")
        elif "name" in p and isinstance(p.get("role"), int):    # 狼人杀
            self._append_state("你的身份：" + p["name"], "priv")
            if p.get("role") == 1:
                mates = p.get("teammates") or []
                self._append_state("狼队友：" + ("、".join(self._nick(m) for m in mates) if mates else "仅你一人"), "priv")
            if p.get("hunter"):
                self._append_state("🏹 你是猎人：死亡时可开枪带走一人", "priv")
            if p.get("seer_view"):
                v = p["seer_view"]
                self._append_state(f"🔮 查验 {self._nick(v['target'])} 是 {v['name']}", "priv")
            if p.get("witch_kill"):
                self._append_state(f"🩸 本晚被刀目标：{self._nick(p['witch_kill'])}", "priv")
            if p.get("saved_by_witch"):
                self._append_state("🧪 你被女巫用解药救活了", "priv")
        elif "evil" in p:    # 阿瓦隆
            self._append_state("你的身份：" + p["name"], "priv")
            if p.get("role") == 1:  # 梅林
                self._append_state("🌑 叛军：" + ", ".join(self._nick(u) for u in p["evil"]), "priv")
            elif p.get("role") in (2, 3):  # 刺客/莫德雷德（坏人）
                self._append_state("队友：" + ", ".join(self._nick(u) for u in p["teammates"]), "priv")
                if p.get("role") == 2 and p.get("guess_required"):
                    self._append_state("🗡️ 需要你指认梅林", "priv")
        elif "role" in p:          # 谁是卧底
            self._append_state(f"身份：{p['role']} · 词：{p['word']}", "priv")
        elif "word" in p:          # 你画我猜
            self._append_state(f"你的词：{p['word']}，把 TA 画出来", "priv")
        elif "stats" in p:         # 山屋惊魂
            s = p["stats"]
            self._append_state(f"属性：力量{s['might']} 速度{s['speed']}"
                               f" 理智{s['sanity']} 知识{s['knowledge']}", "priv")
            self._append_state("随身道具：" + ("、".join(p["items"]) or "无"), "priv")
            self._append_state(f"位置：({p['pos']}) {p['room']} · 身份：{p['side']}", "priv")
        elif "hand" in p:          # 抽牌配对
            self._append_state("手牌：" + " ".join(p["hand"]), "priv")
        elif "row" in p:     # 达芬奇密码：自己知道所有牌
            self._append_state("我的手牌：" + " ".join(
                (str(t["v"]) if t["open"] else f"暗{t['v']}") for t in p["row"]), "priv")
        elif isinstance(p.get("hand"), int):   # 情书：密信牌值
            self._append_state(f"你的密信牌：{p['hand']}", "priv")
        elif "deck" in p:    # COC 选卡阶段：展示可选卡池
            self._append_state("可选调查员（输入 id 选卡）：", "priv")
            for c in p["deck"]:
                self._append_state(f"  {c['emoji']} {c['name']}（{c['id']}）{c.get('desc', '')}", "priv")
        elif "card" in p:    # COC 自由剧情：展示自己的调查员卡
            c = p["card"]
            self._append_state(f"{c.get('emoji', '')} 调查员：{c['name']}（{c['id']}）", "priv")
            attrs = c.get("attrs") or {}
            self._append_state("属性：" + " ".join(f"{k}{v}" for k, v in attrs.items()), "priv")
            sig = c.get("sig") or {}
            self._append_state("技能：" + " ".join(f"{k}{v}" for k, v in sig.items()), "priv")

    def _append_state(self, text: str, tag: str) -> None:
        if not text:
            return
        self.state_text.configure(state="normal")
        self.state_text.insert("end", text + "\n", tag)
        self.state_text.configure(state="disabled")
        self.state_text.see("end")

    # ---------- 动作区 ----------
    def _focus_board(self) -> None:
        """「进入棋盘」：把对局浮窗置顶到最前，聚焦图形画布并刷新到最新状态。"""
        try:
            self.win.lift()
            self.win.attributes("-topmost", True)
            self.win.after(100, lambda: self.win.attributes("-topmost", True))
            self.game_cv.focus_set()
            self._render_canvas()          # 立即重绘棋盘到当前最新状态
        except Exception:
            pass

    def _spawn_board_win(self) -> None:
        """「弹出专注窗」：把当前对局棋盘单独拉到一个独立可缩放/最大化的大窗口里专注玩。"""
        try:
            if getattr(self, "_board_win", None) is None:
                self._board_win = BoardFocusWindow(self)
            self._board_win.show()
            self._board_win.redraw(force=True)
        except Exception:
            pass

    def _rebuild_actions(self, game: str | None) -> None:
        for w in self.act_btns.winfo_children():
            w.destroy()
        self.act_hint.config(text="")
        if not game or (self.core.game_room or {}).get("status") != "playing":
            return
        desktop_status, desktop_note = _desktop_game_status(game)
        if desktop_status == "unsupported":
            self.act_hint.config(text=f"{desktop_note}；本端只读")
            return
        acc = self._pal.get("accent", "#4f6ef2")
        acc_hover = self._pal.get("accent_hover", "#3d5be0")
        acc_fg = self._pal.get("accent_fg", "#ffffff")
        soft = self._pal.get("soft_bg", "#eef0f5")
        street = self._pal["fg"]
        for label, spec, hint in _GAME_ACTIONS.get(game, []):
            primary = "fixed" in spec          # 可直接执行的按钮用强调主色
            b = tk.Button(self.act_btns, text=label, font=self._f, relief="flat",
                          padx=3, cursor="hand2",
                          command=lambda s=spec, h=hint: self._set_pending(s, h))
            if primary:
                b.config(bg=acc, fg=acc_fg, activebackground=acc_hover,
                         activeforeground=acc_fg)
                b.bind("<Enter>", lambda e, w=b: w.config(bg=acc_hover))
                b.bind("<Leave>", lambda e, w=b: w.config(bg=acc))
            else:
                b.config(bg=soft, fg=street, activebackground=acc_hover,
                         activeforeground=acc_fg)
                b.bind("<Enter>", lambda e, w=b: w.config(
                    bg=client_gameui._shade(soft, -0.10)))
                b.bind("<Leave>", lambda e, w=b: w.config(bg=soft))
            # Keyboard users can focus the action row and press Enter; this
            # follows the same _set_pending/_do_action gate as mouse clicks.
            b.bind("<Return>", lambda _e, w=b: (w.invoke(), "break")[1])
            b.bind("<KP_Enter>", lambda _e, w=b: (w.invoke(), "break")[1])
            b.pack(side="left", padx=(0, 2))

    def _set_pending(self, spec: dict, hint: str) -> None:
        """按钮动作：fixed=直接发；sel_key=取棋盘勾选；否则按 kind 弹友好参数窗。"""
        source_ui = (self._board_win._cv_ui
                     if getattr(self, "_board_win", None)
                     and self._board_win.active() else self._cv_ui)
        if "fixed" in spec:
            self.act_hint.config(text="")
            self._do_action(spec["fixed"], source_ui)
            return
        if "sel_key" in spec:
            self._submit_sel(spec, source_ui)
            return
        self._ask_params(spec, hint)

    def _submit_sel(self, spec: dict, source_ui) -> None:
        """把棋盘上勾选的牌（ui.sel[sel_key]）作为 tiles 提交，可选补一个行号。"""
        ids = list((source_ui.get("sel") or {}).get(spec["sel_key"], []))
        if not ids:
            self.act_hint.config(text="先在棋盘上点选要出的牌")
            return
        action = {"op": spec["op"], "tiles": ids}
        if spec.get("need_row"):
            from widgets import dialogbox as _db
            label = self.core.game_meta.get(self._cur_game(), {}).get("label", "游戏")
            r = _db.ask_string(f"{label} · 接续",
                               "接续到第几组（桌面左侧编号，从 1 起）",
                               parent=self.win)
            if r is None:
                self.act_hint.config(text="")
                return
            try:
                action["row"] = int(r) - 1
            except (TypeError, ValueError):
                self.act_hint.config(text="行号无效")
                return
        # 提交后清空勾选，避免旧选择残留
        (source_ui.get("sel") or {}).pop(spec["sel_key"], None)
        self.act_hint.config(text="")
        self._do_action(action, source_ui)

    def _ask_params(self, spec: dict, hint: str) -> None:
        """参数动作：根据 kind 弹出对应输入窗，友好收集参数后发送。"""
        from widgets import dialogbox as _db
        key = spec.get("key")
        kind = spec.get("kind")
        op = spec.get("op")
        gm = self.core.game_meta.get(self._cur_game(), {})
        title = f"{gm.get('label', '游戏')} · 操作"
        res = _KIND_INPUTS[kind](self.win, title, hint)
        if res is None:
            self.act_hint.config(text="")
            return
        action = self._parse_action(key, kind, res)
        if action is None:
            self.act_hint.config(text="输入有误，请重试")
            _db.show_message(title, "输入格式有误，请重新操作", kind="warning",
                             parent=self.win)
            return
        if op:
            action = dict(action)
            action["op"] = op
        self.act_hint.config(text="")
        source_ui = (self._board_win._cv_ui
                     if getattr(self, "_board_win", None)
                     and self._board_win.active() else self._cv_ui)
        self._do_action(action, source_ui)

    def _cur_game(self) -> str:
        return (self.core.game_room or {}).get("game") or self._sel_game or ""

    def _parse_action(self, key, kind, text) -> dict | None:
        try:
            if kind == "int":
                return {key: int(text)}
            if kind == "text":
                return {key: text}
            if kind == "uid":
                return {key: int(text)}
            if kind == "uids":
                return {key: [int(x) for x in text.replace(",", " ").split()
                              if x.strip()]}
            if kind == "pos":
                x, y = (int(v) for v in text.split(","))
                return {"x": x, "y": y}
            if kind == "liarplay":   # 骗子酒馆：牌值 报数
                card, claim = (int(v) for v in text.split())
                return {"card": card, "claim": claim}
            if kind == "ninjaattack":   # 忍者之夜：攻击目标
                return {"op": "move", "move": "attack", "target": int(text)}
            if kind == "card":
                parts = text.split()
                act = {"card": int(parts[0])}
                if len(parts) > 1:
                    act["color"] = parts[1]
                return act
            if kind == "stroke":
                x1, y1, x2, y2 = (int(v) for v in text.split(","))
                return {"stroke": {"type": "line", "x1": x1, "y1": y1,
                                   "x2": x2, "y2": y2, "color": "black", "width": 3}}
            if kind == "gtv":          # 达芬奇密码：target pos val
                parts = text.split()
                if len(parts) < 3:
                    return None
                val = parts[2]
                return {"op": "guess", "target": int(parts[0]),
                        "pos": int(parts[1]) if parts[1].lstrip("-").isdigit() else None,
                        "val": val if val.lower() in ("black", "黑", "b") else int(val)}
            if kind == "ldisc":        # 情书：play [target] [val]
                parts = text.split()
                act = {"op": "discard", "play": int(parts[0])}
                if len(parts) > 1:
                    act["target"] = int(parts[1])
                if len(parts) > 2:
                    act["val"] = int(parts[2])
                return act
            if kind == "halmamove":    # 跳棋/国际跳棋：fx,fy tx,ty
                a = list(map(int, text.replace(",", " ").split()))
                return {"fx": a[0], "fy": a[1], "tx": a[2], "ty": a[3]}
            if kind == "ludomove":     # 飞行棋：机号
                return {"op": "move", "idx": int(text)}
            if kind == "blok":         # 角斗士棋：拼块名 方向号 x y
                parts = text.split()
                return {"op": "place", "piece": parts[0], "oi": int(parts[1]),
                        "x": int(parts[2]), "y": int(parts[3])}
        except (ValueError, TypeError):
            return None
        return None

    def _do_action(self, action: dict, source_ui=None) -> None:
        room = self.core.game_room or {}
        st = self.core.game_state or {}
        rid = room.get("room_id")
        game = room.get("game")
        if _desktop_game_status(game or "")[0] == "unsupported":
            self._append_state("桌面端当前不支持主要操作，本端只读", "warn")
            return
        if game in ("gomoku", "connect4"):
            context = (room.get("room_id"), room.get("round"))
            if source_ui is not None and source_ui.get("_room_context") != context:
                return
            if not client_gameui.flagship_can_move(
                    room, st, self.core.uid,
                    getattr(self.core, "connected", False)):
                return
        if rid and room.get("status") == "playing":
            self.core.game_action(rid, action)

    # ---------- 房间操作 ----------
    def _on_create(self) -> None:
        name = self._sel_game or next(iter(self.core.game_meta), None)
        if not name:
            self._append_state("先点选一张桌游卡片", "sys")
            return
        self._on_create_game(name)

    def _room_do(self, op: str) -> None:
        rid = self._sel_room
        if rid is None:
            self._append_state("先点选一个房间卡片", "sys")
            return
        if op == "join":
            self._on_double_room(rid)
        else:
            self._spectate_room(rid)

    def _on_leave(self) -> None:
        rid = (self.core.game_room or {}).get("room_id")
        if rid:
            self.core.game_leave(rid)

    def _on_start(self) -> None:
        rid = (self.core.game_room or {}).get("room_id")
        if rid:
            self.core.game_start(rid)

    # ---------- 聊天 overlay ----------
    def _toggle_chat(self) -> None:
        self._chat_open = not self._chat_open
        if self._chat_open:
            self.chat_panel.pack(fill="both", expand=True, pady=(2, 0))
            self.chat_entry.focus_set()
        else:
            self.chat_panel.pack_forget()

    def _render_chat(self, hist: list) -> None:
        self.chat_text.configure(state="normal")
        self.chat_text.delete("1.0", "end")
        for m in hist[-20:]:
            nick = m.get("nick", "?")
            body = m.get("text", "")
            sticker = m.get("sticker", "")
            if sticker:
                body = (body + " " if body else "") + \
                    STICKER_BY_CODE.get(sticker, {}).get("emoji", sticker)
            if not body:
                continue
            ts = time.strftime("%H:%M", time.localtime(m.get("ts", time.time())))
            tag = "self" if m.get("uid") == self.core.uid else None
            self.chat_text.insert("end", f"{ts} {nick}: {body}\n", tag)
        self.chat_text.configure(state="disabled")
        self.chat_text.see("end")

    def _send_overlay(self) -> None:
        text = self.chat_entry.get().strip()
        self.chat_entry.delete(0, "end")
        if text:
            self.core.send_chat(text, channel="public")

    # ---------- 工具 ----------
    def _nick(self, uid: int) -> str:
        u = self.core.roster.get(uid)
        return u["nick"] if u else f"玩家{uid}"

    def show(self) -> None:
        self._restore_allowed = True
        self._hide_reason = None
        self.win.deiconify()
        self.win.lift()
        self.core.game_list()
        try:
            self._render_state()
        except Exception:
            pass

    def hide(self, reason="manual") -> None:
        select = getattr(self.app, '_select_navigation', None)
        if select is not None:
            select('chat')
        if reason != "collapse":
            self._restore_allowed = False
        self._hide_reason = reason
        try:
            self._cancel_repaint(self._cv_ui)
        except Exception:
            pass
        self.win.withdraw()
        bwin = getattr(self, "_board_win", None)
        if bwin is not None:
            bwin.hide(reason=reason)

    def close(self) -> None:
        self._closed = True
        self._restore_allowed = False
        try:
            self._cancel_repaint(self._cv_ui)
        except Exception:
            pass
        bwin = getattr(self, "_board_win", None)
        if bwin is not None:
            try:
                bwin.destroy()
            except Exception:
                pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def _press(self, ev) -> None:
        self._drag_x, self._drag_y = ev.x_root, ev.y_root
        self._win_x, self._win_y = self.win.winfo_x(), self.win.winfo_y()

    def _drag(self, ev) -> None:
        dx, dy = ev.x_root - self._drag_x, ev.y_root - self._drag_y
        self.win.geometry(f"+{self._win_x + dx}+{self._win_y + dy}")


class BoardFocusWindow:
    """棋盘独立专注窗：把当前对局棋盘单独拉到一个可自由缩放/最大化的大窗口里专注玩。
    - 复用 GameWindow._render_to 的渲染核心与 _do_action 动作提交，交互/动效与大厅一致；
    - 提供独立 canvas + 自己的动效 ui 状态，不抢大厅的 _cv_ui（两处棋盘互不干扰）；
    - 鼠标点击/悬停/缩放事件绑定在此画布上，对局状态由大厅 _poll 驱动持续重绘。
    """

    def __init__(self, host: "GameWindow", pal: dict | None = None) -> None:
        self.host = host
        self.app = host.app
        self.core = host.core
        self._pal = pal or host._pal
        self._closed = False
        self._restore_allowed = True
        self._cv_ui = {"sel": {}}
        self._build()

    def _build(self) -> None:
        win = tk.Toplevel(self.host.win)
        try:
            win.attributes("-alpha", 0.97)
        except tk.TclError:
            pass
        win.attributes("-topmost", True)
        win.configure(bg=self._pal["win"])
        f = (FONT_FAMILY, FONT_SIZE)
        sw = _screen_w(self.app.root)
        win.geometry(f"920x720+{max(0, (sw - 940) // 2)}+60")
        win.minsize(480, 400)
        win.resizable(True, True)
        self.win = win

        # 简洁顶部条：标题 + 提示（可拖动，便于随手摆放）
        bar = tk.Frame(win, bg=self._pal["win"])
        bar.pack(fill="x")
        tk.Label(bar, text="棋盘 · 专注对局", bg=self._pal["win"],
                 fg=self._pal["fg"], font=(FONT_FAMILY, FONT_SIZE)
                 ).pack(side="left", padx=8, pady=4)
        tk.Label(bar, text="（点棋盘落子/操作 · 自动刷新状态）", bg=self._pal["win"],
                 fg=self._pal["sub"], font=(FONT_FAMILY, FONT_SIZE - 3)
                 ).pack(side="left", padx=4)
        tk.Button(bar, text="✕", width=2, command=self.hide,
                  font=(FONT_FAMILY, FONT_SIZE), relief="flat",
                  fg=self._pal["sub"], bg=self._pal["win"],
                  activebackground=self._pal.get("soft_bg", "#eef0f5")
                  ).pack(side="right")
        _make_draggable(win)

        # 棋盘画布：独占全部剩余空间，随窗口拉伸；事件全部转发到渲染/交互核心
        cv = tk.Canvas(win, bg=self._pal["win"], highlightthickness=0)
        cv.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.game_cv = cv
        cv.bind("<Configure>", self._on_resize)
        cv.bind("<Button-1>", self._on_click)
        cv.bind("<Motion>", self._on_motion)

        win.protocol("WM_DELETE_WINDOW", self.hide)

    # ---------- 渲染（复用大厅渲染核心，独立画布 + 独立动效状态） ----------
    def redraw(self, force: bool = False) -> None:
        try:
            self._cv_ui["_after_owner"] = self.win
            self.host._render_to(self.game_cv, self._cv_ui)
        except Exception:
            pass

    def _on_resize(self, _evt) -> None:
        try:
            self.win.after_idle(self.redraw)
        except Exception:
            pass

    def _on_click(self, evt) -> None:
        try:
            client_gameui.handle_click(self._cv_ui, evt.x, evt.y)
        except Exception:
            pass

    def _on_motion(self, evt) -> None:
        """悬停高亮（进入/离开格子或可点矩形才重绘，避免抖动）——与大厅内嵌棋盘一致。"""
        try:
            ui = self._cv_ui
            if not ui.get("game"):
                return
            cur = client_gameui._cell_of(ui, evt.x, evt.y)
            prev = ui.get("_hover")
            hidx = None
            for i, (a0, a1, a2, a3) in enumerate(ui.get("_hov") or ()):
                if a0 <= evt.x <= a2 and a1 <= evt.y <= a3:
                    hidx = i
                    break
            prevh = ui.get("_hov_idx")
            if cur != prev or hidx != prevh:
                if cur is None:
                    ui.pop("_hover", None)
                else:
                    ui["_hover"] = cur
                if hidx is None:
                    ui.pop("_hov_idx", None)
                else:
                    ui["_hov_idx"] = hidx
                self.win.after_idle(self.redraw)
        except Exception:
            pass

    # ---------- 生命周期 ----------
    def active(self) -> bool:
        """专注窗可见且存在（主导重绘目标），退出或销毁后回退大厅内嵌棋盘。"""
        if self._closed:
            return False
        try:
            return bool(self.win.winfo_exists()) and self.win.state() not in (
                "withdrawn", "iconic")
        except tk.TclError:
            return False

    def show(self, reason="manual") -> None:
        try:
            if reason != "collapse":
                self._restore_allowed = True
            self.win.deiconify()
            self.win.lift()
            self.win.attributes("-topmost", True)
            self.win.after(80, lambda: self.win.attributes("-topmost", True))
            self.redraw(force=True)
        except tk.TclError:
            pass

    def hide(self, reason="manual") -> None:
        if reason != "collapse":
            self._restore_allowed = False
        try:
            self._cv_ui.get("_cancel_repaint", lambda: None)()
        except Exception:
            pass
        try:
            self.win.withdraw()
        except tk.TclError:
            pass
        try:
            # The embedded canvas may not have been painted while focus owned
            # the latest state; reveal the current snapshot when focus closes.
            self.host._render_canvas(force=True)
        except Exception:
            pass

    def destroy(self) -> None:
        self._closed = True
        self._restore_allowed = False
        try:
            self._cv_ui.get("_cancel_repaint", lambda: None)()
        except Exception:
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class MiniBar:
    """悬浮迷你条：形似系统小部件，点一下弹回主窗，右键菜单退出"""

    # 迷你条底色；用 -transparentcolor 打掉即只留文字悬浮（默认开，prefs 可关）
    _BG = "#eef1f4"

    def __init__(self, app: ChatWindow, pal: dict | None = None) -> None:
        self.app = app
        self._pal = pal or _DEFAULT_PAL
        self._bg = self._pal["win"]
        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=self._bg)
        self.label = tk.Label(self.win, text="", font=(FONT_FAMILY, 8),
                              bg=self._bg, fg=self._pal["fg"], padx=6, pady=2)
        self.label.pack()
        _make_draggable(self.win)
        # 透明背景：该底色区域全透明且点击穿透（仅 Windows 支持）→ 只剩时钟文字悬浮
        if self.app._prefs.get("mini_transparent", True):
            try:
                self.win.attributes("-transparentcolor", self._bg)
            except tk.TclError:
                pass                            # 非 win32 平台不支持 → 保持实心
        self.win.geometry(f"{MINI_W}x{MINI_H}+{_screen_w(app.root) - MINI_W - 8}+4")
        for w in (self.win, self.label):
            w.bind("<Button-1>", self._press)
            w.bind("<B1-Motion>", self._drag)
            w.bind("<Button-3>", self._menu)
            w.bind("<Enter>", self._tip_enter)     # R61 细节：悬停展示连接/未读/待收提示
            w.bind("<Leave>", self._tip_leave)
        self._drag_x = self._drag_y = 0
        self._tip = None
        self._update()

    def show(self) -> None:
        self.win.deiconify()
        self.win.lift()

    def hide(self) -> None:
        self.win.withdraw()

    def _update(self) -> None:
        if self.win.winfo_exists():
            dot = "●" if self.app.core.connected else "○"
            with self.app.core.files._lock:
                inbox = sum(1 for x in self.app.core.files.xfers.values()
                            if x.role == "receive" and x.status == "offering")
            txt = f"{dot} {_now_str()}" + (" 📥" if inbox else "")
            self.label.config(text=txt)
            self.win.after(1000, self._update)

    def _press(self, ev) -> None:
        self._drag_x, self._drag_y = ev.x_root, ev.y_root
        self._win_x, self._win_y = self.win.winfo_x(), self.win.winfo_y()

    def _drag(self, ev) -> None:
        dx, dy = ev.x_root - self._drag_x, ev.y_root - self._drag_y
        self.win.geometry(f"+{self._win_x + dx}+{self._win_y + dy}")

    def _menu(self, ev) -> None:
        menu = tk.Menu(self.win, tearoff=0)
        menu.add_command(label="显示主窗", command=self.app.show_main)
        menu.add_command(label="退出", command=self.app.quit_app)
        menu.tk_popup(ev.x_root, ev.y_root)
        menu.grab_release()

    # ---------- R61 细节：悬停提示（连接态 + 未读总数 + 待收文件） ----------
    def _tip_text(self) -> str:
        """按当前状态拼一句话：连接态、未读总数、文件名待收数。"""
        parts = ["已连接" if self.app.core.connected else "未连接"]
        try:
            unread = sum(self.app._unread.values())
        except Exception:
            unread = 0
        if unread:
            parts.append(f"{unread} 条未读")
        with self.app.core.files._lock:
            inbox = sum(1 for x in self.app.core.files.xfers.values()
                        if x.role == "receive" and x.status == "offering")
        if inbox:
            parts.append(f"{inbox} 个文件待收")
        return " · ".join(parts)

    def _tip_enter(self, _ev=None) -> str:
        try:
            if self._tip is None or not self._tip.winfo_exists():
                tl = tk.Toplevel(self.win)
                tl.overrideredirect(True)
                tl.attributes("-topmost", True)
                tl.configure(bg="#333333")
                lbl = tk.Label(tl, text="", bg="#333333", fg="#ffffff",
                               font=(FONT_FAMILY, 9), padx=8, pady=3)
                lbl.pack()
                self._tip = tl
            self._tip.winfo_children()[0].config(text=self._tip_text())
            x = self.win.winfo_x()
            y = self.win.winfo_rooty() - 32
            self._tip.geometry(f"+{max(4, x)}+{max(4, y)}")
            self._tip.deiconify()
            self._tip.lift()
        except (tk.TclError, Exception):
            pass
        return "break"

    def _tip_leave(self, _ev=None) -> str:
        if self._tip is not None and self._tip.winfo_exists():
            self._tip.withdraw()
        return "break"


def _screen_w(root: tk.Tk) -> int:
    try:
        return root.winfo_screenwidth()
    except Exception:
        return 1920


# ---- 单例保护（稳定性：根治「时开时不开 / 双击变幽灵进程」）----
# 用 Windows 命名互斥锁保证同一账号本地只跑一个实例：正常实例全程持有锁；
# 重复双击/启动时检测到锁已被占用 → 把已有实例的主窗唤起到前台后退出，
# 不再另起进程、不再产生互相干扰的死亡残留。进程退出（即使崩溃）内核自动
# 释放锁，因此不会有「占着锁却又打不开」的死锁。非 Windows/异常一律放行。
_INSTANCE_MUTEX = None          # 持有锁的句柄，必须保活到进程退出，不能 GC
_INSTANCE_LOCK_NAME = "Local\\MoYuHelperSingle_" + (
    os.getenv("USERNAME") or "user")


def _acquire_single_instance() -> bool:
    """尝试取得单例锁。返回 True=本实例应继续跑；False=已有实例且已唤醒其可见窗，应退出。

    稳定性要点：当已有实例但**没有可见主窗**（被藏在迷你条/托盘/隐身）时，返回 True
    放行新实例继续启动——宁可多开，也绝不"双击无反馈"地静默退出。"""
    global _INSTANCE_MUTEX
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.CreateMutexW(None, False, _INSTANCE_LOCK_NAME)
        if k.GetLastError() == 183:          # ERROR_ALREADY_EXISTS
            try:
                k.CloseHandle(h)
            except Exception:
                pass
            # 只有"能唤醒可见主窗"才退出；否则放行新实例，保证双击一定有窗+托盘反馈
            return not _raise_existing_instance()
        _INSTANCE_MUTEX = h                  # 保活句柄
        return True
    except Exception:
        return True                          # 非 Windows/失败 → 不强制单例


def _raise_existing_instance() -> bool:
    """把已在运行的 client.exe 的主窗唤到前台（尽力而为）。

    返回 True=成功唤醒封了可见主窗（新实例应退出）；
    返回 False=没找到可见主窗（旧实例藏在迷你条/托盘），新实例应继续启动。"""
    bootlog("single instance exists -> try raise existing window")
    try:
        import ctypes
        import ctypes.wintypes
        import subprocess
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                         ctypes.c_void_p)
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p,
                                                    ctypes.POINTER(ctypes.c_ulong)]
        user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
        user32.GetWindowRect.argtypes = [ctypes.c_void_p,
                                         ctypes.POINTER(ctypes.wintypes.RECT)]
        # 收集所有正在运行的 client.exe 进程号
        s = subprocess.run(["tasklist", "/FI", "IMAGENAME eq client.exe"],
                           capture_output=True, text=True).stdout
        ids = set()
        for line in s.splitlines():
            p = line.split()
            if len(p) >= 2 and p[0] == "client.exe":
                try:
                    ids.add(int(p[1]))
                except ValueError:
                    pass
        if not ids:
            return False
        # 枚举第一个「可见且尺寸>100」的应用窗口（跳过屏外宿主/IME），唤到前台
        found = []

        def cb(hwnd, _):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in ids:
                return True
            if not user32.IsWindowVisible(hwnd):
                return True
            r = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if r.right - r.left >= 100 and r.bottom - r.top >= 100:
                found.append(hwnd)
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        if found:
            hwnd = found[0]
            user32.ShowWindow(hwnd, 9)             # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            bootlog(f"raised window hwnd={int(hwnd)}")
            return True
        # 旧实例没有任何可见应用窗（藏在迷你条/托盘/隐身）→ 无从唤起，放行新实例
        bootlog("no visible window to raise -> allow new instance")
        return False
    except Exception as e:
        bootlog(f"raise existing failed: {e!r}")
        return False


# ---- 早期托盘（登录前的启动反馈）----
# 登录/确认身份阶段还没有 ChatWindow，自然也就没有正式托盘。这里在 main()
# 一开始就放一个托盘图标，让用户双击后立刻知道程序在跑（哪怕停在登录窗）。
# 登录完成后，ChatWindow 会先 stop 掉它再建正式托盘，保证始终只有一个图标。
_early_tray = None          # 进程级占位托盘引用
_early_root = None          # 早期托盘宿主 root（stop 时一并销毁，杜绝泄漏）


def _raise_current_window() -> None:
    """把本进程当前最靠前的可见应用窗口唤到前台（纯 WinAPI，跨线程安全）。"""
    try:
        import ctypes
        import ctypes.wintypes
        user32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        pid = k32.GetCurrentProcessId()
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p,
                                                    ctypes.POINTER(ctypes.c_ulong)]
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                         ctypes.c_void_p)
        tops = []                                  # (z序, hwnd)
        order = [0]

        def cb(hwnd, _):
            p = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value != pid:
                return True
            if not user32.IsWindowVisible(hwnd):
                return True
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            if rect.right - rect.left < 100 or rect.bottom - rect.top < 100:
                return True
            # 跳过离屏窗口（历史多屏/隐藏位置会残留在虚拟屏外，拉起后仍看不见）
            vx = user32.GetSystemMetrics(76)       # SM_XVIRTUALSCREEN
            vy = user32.GetSystemMetrics(77)       # SM_YVIRTUALSCREEN
            vw = user32.GetSystemMetrics(78)       # SM_CXVIRTUALSCREEN
            vh = user32.GetSystemMetrics(79)       # SM_CYVIRTUALSCREEN
            cx = (rect.left + rect.right) // 2
            cy = (rect.top + rect.bottom) // 2
            if not (vx <= cx < vx + vw and vy <= cy < vy + vh):
                return True
            tops.append((order[0], hwnd))
            order[0] += 1
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        if tops:
            _z, hwnd = tops[0]                     # 枚举序 = Z 序自上而下 → 首个即最靠前
            user32.ShowWindow(hwnd, 9)             # SW_RESTORE（藏起的确认窗先还原）
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _start_early_tray() -> None:
    """进程一启动就放一个前台托盘图标（登录阶段也可见）。pystray 缺失自动降级为 None。

    回调在**主线程**执行：Tray 用 root.after 调 pump，而登录/确认弹窗的
    wait_window 与 ChatWindow 的 mainloop 都在主线程跑同一个 Tcl 事件队列，
    会顺带驱动本 root 的 after——因此**绝不另起线程去 update()，避免与弹窗
    抢 Tcl 事件循环导致弹窗不弹/进程闪退**。"""
    global _early_tray, _early_root
    if not CFG.tray_enabled:
        _early_tray = None
        _early_root = None
        return
    try:
        from widgets.tray import Tray
        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)                # 不出现任务栏/桌面条目，纯宿主
        from config import bootlog as _log

        def _on_show():
            _log("early tray open -> raise current window")
            _raise_current_window()

        def _on_quit():
            _log("early tray quit")
            try:
                os._exit(0)
            except Exception:
                pass

        _early_root = root
        _early_tray = Tray(root, on_show=_on_show,
                           on_boss=lambda: None,
                           on_ghost=lambda: None,
                           on_quit=_on_quit,
                           tip="办公助手")
    except Exception:
        _early_tray = None
        _early_root = None


def _stop_early_tray() -> None:
    """登录完成后移除早期占位托盘并销毁其宿主（ChatWindow 会另建正式托盘）。"""
    global _early_tray, _early_root
    t = _early_tray
    r = _early_root
    _early_tray = None
    _early_root = None
    if t is not None:
        try:
            t.stop()
        except Exception:
            pass
    if r is not None:
        try:
            r.destroy()                            # 销毁后其 after 回调一并作废
        except Exception:
            pass


def main() -> int:
    # --windowed 打包下 sys.stdout 为 None（无控制台），须判空以免启动即崩
    enable_crashlog()                        # R48：Tk 原生崩溃堆栈常开写 crash.log
    bootlog("client.main start")
    if not _acquire_single_instance():       # 已有实例且已唤醒其可见窗 → 退出
        bootlog("client single-instance exit")
        return 0
    out = getattr(sys, "stdout", None)
    if out is not None:
        try:
            out.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--nick", default="")
    args = ap.parse_args()
    import launcher
    from prefs import Prefs
    try:                                      # R43C：首个 Tk 前声明 DPI 感知（prefs 可关）
        _dpi_on = bool(Prefs().get("dpi_aware", True))
    except Exception:
        _dpi_on = True
    from dpi import apply_early
    apply_early(_dpi_on)
    if CFG.tray_enabled:
        _start_early_tray()                  # DPI声明必须先于托盘的隐藏Tk/ HWND
    if args.nick.strip():
        # --nick 快速通道：跳过账号门禁，直接以指定昵称进主窗
        launcher.run_chat(args.host, args.port, Prefs(), args.nick.strip())
        return 0
    return launcher.launch(args.host, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
