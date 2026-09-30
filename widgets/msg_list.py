# -*- coding: utf-8 -*-
"""widgets/msg_list.py —— 虚拟化消息列表（对标 TG history_view_list_widget）。

核心机制（对应清单 A1/A4）：
- 消息对象列表 + 行高缓存（实际 bbox 高度优先，字体估算兜底）
- 累计高度前缀和数组 + 二分查找 → 只创建可见区间 [top_idx, bottom_idx] 的 Canvas 元素
- 滚动 / 追加 / 清空只重绘可见区（增量重绘），万条消息不卡
- 新消息自动吸底；用户上翻阅读时不动
- 短文本 Canvas create_text 渲染；颜色走主题色表（浅/深两套预留）

只消费已有的 chat/private/group/system 事件结构，不依赖 server/protocol 改动。
"""
import bisect
import os
import re
import threading
import time
import tkinter as tk
from collections import deque
from queue import Queue
from tkinter import font as tkfont

from config import CFG                     # R70E：伪装风格白名单
from stickers import STICKER_BY_CODE, expand_shortcodes, is_custom_sticker_text, custom_tokens
from theme import _hex_mix                    # R39D②：气泡淡入渐混色
from widgets.ui_fx import ease_out            # R43C：滑入/滚动惯性的缓动插值
from widgets.avatar import AvatarCache

try:                                          # 功能③：语音倍速档（纯标准库，可选加载）
    from voice_api import _RIFF_SPEEDS as _RIFF_SPEEDS
except Exception:
    _RIFF_SPEEDS = (0.5, 1.0, 1.5, 2.0)
from widgets import runs, rich, lottie_label     # R38C：lottie 动画贴纸；R59：富文本解析

# ---------- 图片消息（A7）：缩略图尺寸上限（保持宽高比，防超大图撑爆布局） ----------
IMG_MAX_W = 240
IMG_MAX_H = 150
# R31B2 相册分组：同人连续图片合并为 2 列网格气泡（单元格尺寸取上限均分）
ALBUM_COLS = 2
ALBUM_GAP = 3
# R30C 自定义贴纸：独立成条时按贴纸尺寸渲染（小于普通图片）
STICKER_MAX = 110
_IMG_EXT = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"})


def is_image_path(path) -> bool:
    """按扩展名判断是否为图片（消息渲染用它决定是否走缩略图分支）。"""
    return bool(path) and os.path.splitext(path)[1].lower() in _IMG_EXT


def _sanitize_kb(kb) -> list | None:
    """R46：bot inline 键盘形状校验 [[{t,c},...],...] → 规范化，畸形返回 None。
    按钮文本/指令限长（渲染安全），行数限 4、每行按钮限 4（防撑爆布局）。"""
    if not isinstance(kb, list):
        return None
    rows = []
    for r in kb[:4]:
        if not isinstance(r, list):
            return None
        btns = []
        for b in r[:4]:
            if not isinstance(b, dict):
                return None
            t, c = b.get("t"), b.get("c")
            if not isinstance(t, str) or not isinstance(c, str) or not t or not c:
                return None
            btns.append({"t": t[:24], "c": c[:120]})
        if btns:
            rows.append(btns)
    return rows or None


def count_quote_refs(rows) -> dict:
    """功能① 纯函数：统计「被引用次数」映射 seq -> 引用了它的行下标列表。

    遍历已加载行，凡 reply_seq（该行回复/引用指向的服务器 seq）能匹配到某行本身
    的 seq 才计入——只统计双方都在当前历史内的引用关系（引用目标已删除/未加载
    则不计，避免指向空）。返回 {seq: [行下标, ...]}，被引用次数 = len(该列表)。
    """
    seqs = {r.raw.get("seq") for r in rows if r.raw.get("seq") is not None}
    out: dict = {}
    for i, r in enumerate(rows):
        rs = r.reply_seq
        if rs is not None and rs in seqs:
            out.setdefault(rs, []).append(i)
    return out


_EDITED_SUFFIX = "  ✎已编辑"       # R70B：正文尾部的「已编辑」标记（可点查看历史）


class _Row:
    """单条消息行：渲染所需全部信息 + 高度缓存（None=尚未实测）。"""

    __slots__ = ("raw", "ts", "nick", "body", "tag", "reply", "image_path",
                 "voice", "voice_path", "voice_dur", "voice_note", "poll",
                 "preview", "sticker_custom", "caption", "fwd_pack", "kb",
                 "reply_prefix", "reply_seq", "fwd_prefix", "rich", "_edited", "disguise",
                 "vmemo", "vmemo_path", "vmemo_dur")

    def __init__(self, msg: dict, is_system: bool = False):
        self.raw = msg
        self.ts = time.strftime("%H:%M", time.localtime(msg.get("ts", time.time())))
        # R69-C9：好友备注名优先（客户端注入 disp_nick），无则回退昵称
        self.nick = msg.get("disp_nick") or msg.get("nick", "?")
        self.reply = msg.get("reply") if isinstance(msg.get("reply"), dict) else None
        self.reply_prefix = ""                 # R41F：引用前缀（body 开头，绘制时拆 REPLY 可点段）
        self.reply_seq = None                  # 被引用消息的服务器 seq（None=不可点）
        self.tag = "sys" if is_system else None
        self.image_path = msg.get("image_path") if not is_system else None
        # R32B3：图片说明文字（caption），随图显示在缩略图/网格下方
        self.caption = (str(msg.get("text") or "").strip()
                        if (self.image_path and not msg.get("deleted")) else "")
        self.sticker_custom = None              # R30C：自定义贴纸短码（编译正文时填）
        self.voice = bool(msg.get("voice")) if not is_system else False   # R19
        self.voice_path = msg.get("voice_path") if (not is_system and self.voice) else None
        self.voice_dur = msg.get("duration", 0.0) if self.voice else 0.0
        # R38B：本地转写旁注（同目录 <wav>.txt，仅本地存在，绝不上传）
        self.voice_note = None
        if self.voice_path and os.path.isfile(self.voice_path + ".txt"):
            try:
                with open(self.voice_path + ".txt", "r",
                          encoding="utf-8") as fh:
                    self.voice_note = (fh.read() or "").strip() or None
            except OSError:
                pass
        self.poll = msg.get("poll") if isinstance(msg.get("poll"), dict) else None  # R26A
        self.preview = msg.get("preview") if isinstance(msg.get("preview"), dict) else None  # R26D
        # R46：bot inline 键盘 [[{t,c},...],...] —— 防御性校验形状（畸形当无键盘）
        self.kb = _sanitize_kb(msg.get("kb")) if not is_system else None
        # R39D③ 合并转发：fp={n, items:[{nick,ts,text}]}（服务器白名单透传）
        self.fwd_pack = (msg.get("fp")
                         if (not is_system and isinstance(msg.get("fp"), dict))
                         else None)
        self.body = self._compile_body(msg)
        self._edited = bool(msg.get("edited"))    # R59：已编辑标记（rich 渲染追加 ✎）
        self.rich = self._san_rich(msg.get("rich"))   # R59：富文本段（无则退 tag_entities）
        # R70E 消息伪装：仅接受白名单风格（code/log/excel），未知一律回落普通气泡
        d = str(msg.get("disguise") or "")
        self.disguise = d if d in CFG.disguise_styles else ""
        # R72 圆形视频留言：vmemo_path 由 client_core 落盘后注入
        self.vmemo = bool(msg.get("vmemo")) if not is_system else False
        self.vmemo_path = msg.get("vmemo_path") if (not is_system and self.vmemo) else None
        self.vmemo_dur = msg.get("duration", 0.0) if self.vmemo else 0.0

    def _compile_body(self, msg: dict) -> str:
        """根据原始消息生成渲染正文：引用块前缀 + 表情展开 + 已编辑/已撤回标记。"""
        t = msg.get("text", "")
        # R30C：整条消息就是单个自定义贴纸短码（非系统行）→ 按贴纸行渲染
        self.sticker_custom = is_custom_sticker_text(t) if self.tag != "sys" else None
        if msg.get("deleted"):
            return "（消息已撤回）"
        parts = []
        sticker = msg.get("sticker", "")
        if sticker:
            parts.append(STICKER_BY_CODE.get(sticker, {}).get("emoji", sticker))
        if t:
            if self.sticker_custom:             # 搜索/复制用占位，正文走图片分支
                parts.append(f"[贴纸] :{self.sticker_custom}:")
            else:
                parts.append(expand_shortcodes(t))
        if self.image_path:                     # A7：图片行正文换成 [图片] 占位（搜索/复制用）
            parts.append(f"[图片] {os.path.basename(self.image_path)}")
        if msg.get("voice"):                    # R19：语音行正文占位（搜索/复制用）
            parts.append(f"[语音] {msg.get('duration', 0):g} 秒")
        if msg.get("poll"):                     # R26A：投票行正文占位（搜索/复制/导出用）
            parts.append(f"[投票] {str(msg['poll'].get('question', '') or '')[:60]}")
        if self.fwd_pack and not msg.get("deleted"):   # R39D③：合并转发行占位
            parts.append(f"[合并转发] {self.fwd_pack.get('n', '?')} 条消息")
        f = msg.get("file") if isinstance(msg.get("file"), dict) else None
        if f:                                   # R23：网页端图片/文件消息占位
            tag = "图片" if f.get("kind") == "image" else "文件"
            parts.append(f"[{tag}] {str(f.get('name', '') or '')[:24]}")
            size = f.get("size") or 0
            if size:
                parts.append(f"（{self._fmt_size(size)}）")
            parts.append("（网页端文件，可登录网页端下载）")
        body = " ".join(parts).strip()
        if self.reply:
            rnick = self.reply.get("nick", "?")
            rtext = self.reply.get("text", "")[:20]
            self.reply_prefix = (f"↩ {rnick}: {rtext} | " if body
                                 else f"↩ {rnick}: {rtext}")
            self.reply_seq = self.reply.get("seq")
            body = self.reply_prefix + body
        fwd = msg.get("forward") if isinstance(msg.get("forward"), dict) else None
        self.fwd_prefix = ""                 # R59：转发前缀（body 开头，绘制时作 PLAIN 段）
        if fwd:
            fnick = fwd.get("nick", "?")
            ftext = (fwd.get("text") or STICKER_BY_CODE.get(fwd.get("sticker", ""),
                    {}).get("emoji", ""))[:24]
            self.fwd_prefix = f"↳ 转发自 {fnick}: {ftext}"
            body = f"{self.fwd_prefix}{(' | ' + body) if body else ''}"
        if msg.get("edited"):
            self._edited = True
            body = f"{body}{_EDITED_SUFFIX}"
        return body

    def _san_rich(self, raw) -> list | None:
        """R59：把服务器白名单清洗过的 rich（[[text,kind,href],...]）转渲染段。

        仅接受文本 + 有限种类的 3 元组；畸形/为空 → None（走 tag_entities 回退）。
        """
        if not isinstance(raw, list) or not raw:
            return None
        segs = []
        for item in raw:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            t = str(item[0])
            if not t:
                continue
            k = str(item[1])
            if k not in rich.ALLOWED_KINDS:
                continue
            href = str(item[2]) if len(item) > 2 and item[2] else None
            segs.append((t, k, href))
        return segs if segs else None

    @property
    def empty(self) -> bool:
        return not self.body

    @staticmethod
    def _fmt_size(n) -> str:                    # R23：网页端文件大小展示
        n = float(n or 0)
        if n < 1024:
            return f"{n:g}B"
        if n < 1048576:
            return f"{n / 1024:.1f}KB"
        return f"{n / 1048576:.1f}MB"


class MsgList(tk.Canvas):
    """虚拟化消息列表控件（自含滚动条，pack 即用）。

    外部 API：
        append(msg, is_system=False)  追加一条消息（自动吸底/增量重绘）
        append_sys(text)              追加系统行（灰色 · 前缀）
        load(msgs, me_uid=None)       清空并批量装载（会话切换）
        clear()                       清空
        scroll_to_end()               滚动到底部
        set_me_uid(uid)               设置"我"的 uid（着色自己消息）
        count / at_bottom / first_visible
    """

    # 主题色表：浅色默认值；深色皮肤可整体替换（A5/A6 主题化时扩展）
    COLORS = {
        "bg": "#fafafa",
        "sys": "#aaaaaa",
        "self": "#0e4a32",
        "priv": "#5f4b38",
        "normal": "#544438",
        "hit": "#ffefd2",          # 搜索命中行高亮（暖黄）
        "hit_active": "#ffd180",   # 当前命中行（深黄）
        "bubble_in": "#fffbf3",    # 他人气泡（柔暖白，微衬线区分于 bg）
        "bubble_out": "#54cd9b",   # 自己气泡（清亮薄荷）
        "bubble_inline": "#e9d7c0",
        "bubble_outline": "#a5e6c8",
        # @全体 广播消息的醒目气泡底色（非本人收到的 @全体/@全员）
        "everyone": "#ffe9dc",
        # R11 富文本：@提及 与 链接 着色（链接由 client 打开外部浏览器）
        "mention": "#9b6bd8",
        "link": "#ff7e67",
        # Apple 风格自适应色：薄荷底气泡上的提及/链接浅色变体（可选）
        "mention_self": None,       # None=回退到 mention
        "link_self": None,          # None=回退到 link
        # R12 消息分组/日期分隔（对齐 TG HistoryView）
        "date": "#a98e72",           # 日期分隔条文字（今天/昨天/具体日期）
        # R13 表情回应 / 已读回执
        "react_bg": "#ffe8d4",       # 回应条底色（小药丸）
        "react_fg": "#5b4636",
        "react_own": "#ff8a5c",      # 我已回应的表情标色/描边
        "read": "#a98e72",           # ✓已读 标记颜色
        "pending": "#b3a98f",        # P0 三态：发送中标记颜色（浅灰棕，弱于已读）
        "unread": "#e0574f",         # R30A 未读分隔线（与网页端未读角标同色）
        # R31B 消息多选
        "sel_band": "#ffe3d0",       # 选中行整行高亮带
        "sel_ring": "#cfb49a",       # 未勾选空心圈描边
        # R70A 剧透遮盖药丸（默认遮住，点击揭示）
        "spoiler_bg": "#c9c3ba",
        "spoiler_fg": "#f7f4ef",
        # R70E 消息伪装三风格底色/线（code 深色终端 / log 灰底日志 / excel 白底表格）
        "disguise_code_bg": "#1f2633",
        "disguise_log_bg": "#f2f3f5",
        "disguise_excel_bg": "#ffffff",
        "disguise_line": "#9aa4b2",
    }
    PAD_X = 6
    PAD_TOP = 3                      # 行内上/下留白（行距来源）
    GROUP_WINDOW = 180               # 同人连续消息分组时间窗（秒，对齐 TG 3 分钟）
    GROUP_PAD_V = 2                  # 组内消息气泡上下留白（紧凑）
    DATE_H = 26                      # 日期分隔条高度
    UNREAD_H = 24                    # R30A 未读分隔条高度
    AVATAR = 18                      # 头像圆直径（A5 首字色块）
    GUTTER = 4                       # 头像与正文间距
    BUBBLE_PAD_H = 8                 # 气泡左右内边距
    BUBBLE_PAD_V = 5                 # 气泡上下内边距
    MIN_BUBBLE_W = 120               # 气泡最小宽
    BUBBLE_R = 10                    # 气泡圆角半径（近似圆角）
    CAP_RATIO = 0.62                 # 气泡文本换行宽度 ≈ 行宽 * 此比例
    REACT_PAD = 18                   # R13：回应条在气泡下方占的行高（含留白）
    # R46 bot inline 键盘：按钮药丸高度/间距（气泡下方，估算与绘制共用）
    KB_BTN_H = 20
    KB_GAP = 3
    # R27 快速回应：hover 消息时浮出的表情条（对齐 TG quick reaction bar）
    QUICK_EMOJIS = ["👍", "❤️", "😂", "😮", "🔥"]
    QUICK_BAR_H = 22                 # 悬浮条高
    QUICK_BAR_PAD = 4                # 悬浮条内边距
    QUICK_BAR_TOP = 2                # 悬浮条与气泡间距
    QUICK_BAR_BAND = 6               # hover 判定向上扩展带（悬浮条越出本行顶部时保持命中）
    # R26D 链接预览卡片：标题/域名/描述三行 + 边距（估算与绘制共用同一常量）
    PREVIEW_PAD = 4                  # 卡片与气泡正文间距

    def _preview_h(self) -> int:
        return 3 * self._linespace + 12

    def __init__(self, parent, font, colors=None, me_uid=None, avatars=None,
                 on_row_menu=None, on_row_double=None, on_row_image=None,
                 on_link=None, on_voice=None, on_transcribe=None,
                 on_voice_end=None,    # D14：语音播完回调(i)，client 依开关连播下一条
                 on_poll_vote=None, on_react=None,
                 on_mention=None, on_quick_more=None, on_hashtag=None,
                 on_react_detail=None, on_sticker_path=None, on_sticker_fetch=None,
                 on_failed=None, on_read_detail=None, on_open_thread=None,
                 on_fwd_open=None, on_jump_reply=None, on_kb=None,
                 on_bubble_act=None,   # R58C：悬停操作条(回复/复制/删除)回调(i, act)
                 on_profile=None,      # R69C10：点消息头像 → 用户资料卡回调(uid)
                 on_edit_history=None,  # R70B：点「✎已编辑」→ 查看编辑历史回调(row)
                 on_card=None,         # R71：点联系人名片卡 → 资料卡回调(uid)
                 on_vmemo=None,        # R72：点视频留言徽标 → 播放回调(path)
                 read_mark="✓已读  ",   # R交互：已读标记文案（qq 传 None 隐藏回执）
                 **kw):
        self._font = tkfont.Font(root=parent, font=font)
        try:
            self._linespace = self._font.metrics("linespace")
        except Exception:
            self._linespace = font[1] + 3
        self._meas_cache: dict = {}          # R11：富文本换行宽度缓存（词粒度，LRU 限长）
        # R39C：文本换行行数 LRU —— (text, inner, font_sig) -> lines，估算/绘制共用
        self._wrap_cache: dict = {}
        self._MEAS_CACHE_MAX = 4096          # 词宽 LRU 上限：防长会话消息词缓存无界增长
        self._font_sig = f"{self._font.actual('family')}/{self._font.actual('size')}"
        self._avatar_font = (self._font.actual("family"), 9, "bold")
        self._date_font = (self._font.actual("family"), 9)   # R12：日期分隔条
        # R52：可共享 AvatarCache（桌面端全局共用一份，头像到达一次注册全界面生效）
        self._avatars = avatars or AvatarCache()
        self._pal = dict(self.COLORS)
        if colors:
            self._pal.update(colors)
        self._wallpaper: str | None = None    # R32B4：聊天壁纸（None=主题默认 bg）
        self._grid_color: str | None = None  # Excel 皮肤的视口网格；不影响消息行/滚动位置
        kw.setdefault("bg", self._pal["bg"])
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("relief", "flat")
        super().__init__(parent, **kw)
        self._me_uid = me_uid
        self._read_mark = read_mark           # R交互：已读标记文案（None=隐藏回执）
        self._rows: list = []                 # _Row 列表（消息序号=渲染序号）
        self._heights: list = []              # 每行高度（估算或实测）
        self._seen_seq: set = set()           # 已展示的 seq（历史装载与实时事件去重）
        # R70A：已揭示的剧透段 {（id(row), run_idx)…}——仅内存态，不落盘、不跨会话
        self._spoiler_open: set = set()
        # R70F：敏感词本地打码（纯显示层，默认关；词表/开关由 client 注入）
        self._guard_on = False
        self._guard_words: tuple = ()
        self._guard_rx = None
        self._cum = [0]                       # 前缀和：cum[i] = 前 i 行高度和
        self._cum_dirty = False
        self._item_ids: list = []             # 当前可见行创建的 canvas item
        self._first_visible = 0
        self._wrap_w = 0
        self._at_bottom = True
        self._on_row_menu = on_row_menu
        self._on_row_double = on_row_double
        self._on_row_image = on_row_image
        self._on_link = on_link              # R11：点击链接回调（client 打开浏览器）
        self._on_voice = on_voice            # R19：点语音气泡播放回调(row_idx, path)
        self._on_voice_end = on_voice_end    # D14：语音播完回调(row_idx)（连播用）
        # R批次③ 语音转文字：气泡内「⇄转文字」chip 回调(row_idx, path)。
        # 缺 vosk/模型时由 client 不传回调 → 本控件不画 chip（如实降级）。
        self._on_transcribe = on_transcribe
        # 功能③ 语音倍速：本控件级倍速档（1x→1.5x→2x→0.5x→1x 循环），仅 UI 态
        self._voice_rate = 1.0
        self._on_poll_vote = on_poll_vote    # R26A：点投票选项回调(row_idx, option)
        self._on_react = on_react            # R27：点回应（药丸/悬浮条）回调(seq, emoji)
        self._on_mention = on_mention        # R29C：点 @昵称 回调（跳该成员私聊）
        self._on_quick_more = on_quick_more  # R29D：悬浮条"＋"→ 打开全表情选择器回调(seq)
        self._on_hashtag = on_hashtag        # R30E：点 #话题 → 全局搜索回调(text)
        self._on_react_detail = on_react_detail  # R30D：药丸 hover → 回应详情(seq,emoji,ev|None)
        self._sticker_path = on_sticker_path     # R30C：code → 本地缓存图片路径（None=未缓存）
        self._sticker_fetch = on_sticker_fetch   # R30C：触发向服务器拉取贴纸图(code)
        self._on_failed = on_failed          # R31C：点发送失败 ❗ 重发回调(row_idx)
        self._on_read_detail = on_read_detail  # R33③：✓已读 hover → 已读详情回调(row|None, ev|None)
        self._on_open_thread = on_open_thread  # R34：点「N 条回复」徽标 → 打开话题窗口(row)
        self.on_jump_reply = on_jump_reply    # R41F：点引用前缀 → 跳转原消息回调(seq)
        self._on_kb = on_kb                  # R46：点 bot 键盘按钮回调(bot_uid, cmd)
        self._on_bubble_act = on_bubble_act  # R58C：悬停操作条回调(i, act)
        self._on_profile = on_profile        # R69C10：点头像 → 资料卡(uid)
        self._on_edit_history = on_edit_history  # R70B：点「✎已编辑」→ 查看历史(row)
        self._on_card = on_card              # R71：点联系人名片卡 → 资料卡(uid)
        self._on_vmemo = on_vmemo             # R72：点视频留言徽标 → 播放(path)
        self._comment_entry = False          # R71：频道会话下即使 0 条评论也显示「💬 评论」入口
        self._forum_mode = False             # R72：论坛频道下主列表按贴展示
        self._thread_counts = {}             # R72 优化：root_seq -> 回复数（O(1) 查找，替代线性扫描）
        self._quick_emojis = None            # R29D：最近使用快捷集（None=回退 QUICK_EMOJIS）
        self._resize_job = None
        self._render_job = None               # 合并渲染定时器（append 防抖）
        self._stick_bottom = False            # 待钉底：渲染定稿 region 后重新滚到底
        self._last_rendered = None            # (count,width) 防重复重绘

        # R39C 本地历史懒加载：滚到顶向 client 取更旧一页（同步读，页=100）
        self._hist_loader = None              # (before_seq, n) -> list[dict] | None
        self._hist_done = False               # 已翻到最早（收到短页/空页后置位）
        self._hist_busy = False               # 重入保护（wheel 事件连发）

        # R39D② 滚动伪惯性 + 气泡淡入
        self._scroll_target = None            # 滚轮目标位（fraction 0~1）
        self._smooth_job = None               # 插值帧定时器
        self._smooth_frames = 0
        self._momentum = 0.0                  # R43C：滚轮动量（滚停后衰减滑行）
        self._fade_enabled = False            # 新消息气泡淡入（prefs 可关，默认关）
        self._fading: dict = {}               # 行下标 -> 淡入起始 time.time()
        self._fade_job = None

        # R43C 新消息气泡滑入：上滑入场（y +SLIDE_DY → 0），重绘即静默回基线
        self._slide_row = -1                  # 待滑入的新行下标（-1=无）
        self._slide_started = False           # 已为 _slide_row 启动滑入
        self._slide_begin = None              # 滑入起始 time.time()（惰性：首个渲染帧起算）
        self._slide_off = 0.0                 # 当前应施加的垂直偏移（最后归零）
        self._slide_mark = -1                 # _item_ids 中滑入行 item 起始位
        self._slide_items = None              # 滑入作用的 item id 列表（None=未启用）
        self._slide_job = None                # 推进滑入的定时器

        # C1 聊天内搜索：查询词 + 命中行下标 + 当前活动命中下标（-1=未跳转）
        self._search_q = ""
        self._search_hits: list = []
        self._search_active = -1
        self._hit_idx: set = set()            # 命中行下标快速判定

        # R41F 引用跳转：点前缀后短暂高亮的目标行 + 定时器句柄
        self._jump_hi = -1
        self._jump_hi_after = None

        # 功能① 引用聚合：目标 seq -> 被引用次数；目标 seq -> 引用它的行下标列表。
        # 仅统计「当前已加载历史」内 reply->seq 指向（本地统计，服务器历史为权威但无需改协议）。
        self._quote_refs: dict = {}       # seq -> [行下标,...]
        self._quote_hi: set = set()       # 当前高亮的引用行下标集合（点「被引用 N」徽标时置）
        self._quote_hi_after = None

        # R13 已读回执：uid -> 读到的最远 seq（自己消息显示 ✓已读）
        self._read_seqs: dict = {}
        # C9② 群成员总数（供 @ 消息气泡显示「✓✓ N/M 已读」；0=未知则退回原 N 显示）
        self._group_total: int = 0

        # R30A 未读分隔线：last_read 之上的第一条消息上方画「未读消息」条
        self._unread_seq = None

        # R30C 自定义贴纸：贴纸尺寸 PhotoImage 缓存 + 已发起拉取的短码去重集
        self._stk_photo: dict = {}
        self._stk_req: set = set()

        # R30D 回应详情：药丸 hover 500ms 后回调（延时器句柄）
        self._pill_job = None

        # R17 字幕可读性增强：正文文字描边光晕色（None=关闭）。在 ghost 亮背景下，
        # 给黑字加一圈浅色偏移副本形成描边，使黑字在任意背景（亮/暗）都清晰可辨。
        self._halo = None

        # R13 表情回应：避免每次渲染重扫全部行的廉价缓存
        self._react_font = (self._font.actual("family"), 8)
        # R27 快速回应：hover 行下标 + 弹入动画目标 (seq, emoji)（含清除定时器）
        self._hover_row = None
        self._anim = None
        self._anim_job = None
        # R26A 投票问题加粗（独立 Font 对象，宽度测量用 _meas_bold）
        self._bold_font = tkfont.Font(root=parent, font=(self._font.actual("family"),
                                                         self._font.cget("size"), "bold"))
        # R59 富文本字体档：斜体 / 等宽 / 粗斜体
        _fam = self._font.actual("family")
        _sz = self._font.cget("size")
        self._italic_font = tkfont.Font(root=parent, font=(_fam, _sz, "italic"))
        self._mono_font = tkfont.Font(root=parent, font=("Consolas", _sz))
        self._bolditalic_font = tkfont.Font(root=parent, font=(_fam, _sz, ("bold", "italic")))
        # 行高取字体档最大值，保证斜/粗/等宽行不向下挤压（均匀网格 → 所见即所估）
        try:
            self._linespace = max(
                f.metrics("linespace")
                for f in (self._font, self._bold_font, self._italic_font,
                          self._mono_font, self._bolditalic_font))
        except Exception:
            pass

        # A7 图片缩略图：子线程 Pillow 缩放 + 主线程 PhotoImage 缓存（不阻塞滚动）
        self._img_pil: dict = {}              # path -> PIL.Image | False（子线程写）
        self._img_photo: dict = {}            # path -> ImageTk.PhotoImage（主线程写）
        self._img_cell_photo: dict = {}       # R31B2：path -> 相册单元格 PhotoImage
        self._img_pending: set = set()        # 已排队/加载中的 path
        self._img_ready: deque = deque()      # 子线程完成队列 -> 主线程 poll
        self._img_queue: Queue = Queue()
        self._img_thread: threading.Thread | None = None
        self._img_inflight = 0                # 子线程待完成数（空闲自停的判据，见 _img_tick）
        self._img_job = None                  # 轮询 after id（None=未排程）
        # R61 应用层 GIF 分帧轮播（PIL 帧序列 + PhotoImage + _img_tick 推进）
        self._gif_frames: dict = {}           # path -> [PIL.Image, ...] | False（子线程写；动画帧）
        self._gif_photo: dict = {}            # path -> [ImageTk.PhotoImage, ...]（主线程惰性生成）
        self._gif_item: dict = {}             # path -> canvas photo item id（正在展示的最后一行）
        self._gif_idx: dict = {}              # path -> 当前帧下标
        # R68 语音播放进度条：{idx: (t0单调时钟, 有效时长秒)}；None=未播放
        self._voice_playing = None
        self._voice_job = None                # 进度推进 after id

        # 自含滚动条（A6：12px 细条、trough 即底色、hover 变深，对标 TG 参数）
        self._sb = tk.Scrollbar(self, orient="vertical", command=self._scroll_cmd,
                                width=12, relief="flat", highlightthickness=0,
                                troughcolor=self._pal["bg"],
                                bg=self._pal.get("bubble_inline", "#e9d7c0"),
                                activebackground=self._pal.get("date", "#a98e72"),
                                borderwidth=0, elementborderwidth=0)
        self._sb.pack(side="right", fill="y")
        self.configure(yscrollcommand=self._sb.set)

        self.bind("<MouseWheel>", lambda e: self._wheel(e.delta))
        self.bind("<Button-4>", lambda e: self._wheel(120))    # Linux 上滚
        self.bind("<Button-5>", lambda e: self._wheel(-120))   # Linux 下滚
        self.bind("<Configure>", self._on_configure)
        # R27：hover 出快速回应条；离开/滚动即隐藏
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda e: self._set_hover(None))
        if on_row_menu:
            self.bind("<Button-3>", self._on_right_click)
        if on_row_double:
            self.bind("<Double-Button-1>", self._on_double_click)
        # A7 缩略图轮询由 _request_img 按需启动（空闲不排程，见 _img_kick/_img_tick）

        # R31A jump-to-bottom：滚离底部/离底收到新消息 → 右下角浮动「⬇ N」
        # （对齐 TG corner_buttons：快速回到底部 + 未读计数导航）
        self._jump_new = 0                    # 离开底部期间新到消息数
        self._jump_btn = tk.Button(
            self, text="⬇", font=(self._font.actual("family"), 10, "bold"),
            relief="flat", bd=0, cursor="hand2", padx=10, pady=3,
            bg=self._pal["self"], fg="#ffffff",
            activebackground=self._pal["self"], activeforeground="#ffffff",
            command=self._jump_bottom)
        self._jump_btn.place_forget()         # 默认隐藏（到底自动收起）

        # R31B 消息多选：选择模式下点行切换勾选（TG 选择模式），操作栏由 client 挂载
        self._sel_mode = False
        self._sel_rows: set = set()
        self._on_sel_change = None            # (mode, count) -> None

    # ---------- R31B 消息多选 ----------
    SEL_R = 8                                 # 勾选圈半径（px）

    def set_sel_cb(self, cb) -> None:
        """选择模式/选择集变化回调：(in_mode, count) -> None。"""
        self._on_sel_change = cb

    def in_select_mode(self) -> bool:
        return self._sel_mode

    def selected_rows(self) -> list:
        """已勾选的行号（升序）。"""
        return sorted(self._sel_rows)

    def _row_sel_ok(self, i: int) -> bool:
        """可勾选行：非系统行（系统行无 seq，不可删/转）。"""
        if not (0 <= i < len(self._rows)):
            return False
        return self._rows[i].tag != "sys"

    def enter_select_mode(self, first_idx: int | None = None) -> None:
        """进入选择模式（可带首条勾选，右键菜单「多选」入口）。"""
        self._sel_mode = True
        self._sel_rows = set()
        self._set_hover(None)
        if first_idx is not None and self._row_sel_ok(first_idx):
            self._sel_rows.add(first_idx)
            for j in self._album_rows(first_idx):   # R31B2：相册整组一起勾选
                if self._row_sel_ok(j):
                    self._sel_rows.add(j)
        self._notify_sel()
        self._render()

    def exit_select_mode(self, notify: bool = True) -> None:
        """退出选择模式并清空勾选（转发/删除完成后 client 也会调用）。"""
        if not self._sel_mode:
            return
        self._sel_mode = False
        self._sel_rows = set()
        if notify:
            self._notify_sel()
        self._render()

    def _toggle_select(self, idx: int) -> None:
        if not self._sel_mode or not self._row_sel_ok(idx):
            return
        if idx in self._sel_rows:
            self._sel_rows.discard(idx)
            for j in self._album_rows(idx):    # R31B2：相册整组一起取消
                self._sel_rows.discard(j)
        else:
            self._sel_rows.add(idx)
            for j in self._album_rows(idx):    # R31B2：相册整组一起勾选
                if self._row_sel_ok(j):
                    self._sel_rows.add(j)
        self._notify_sel()
        self._render()

    def _notify_sel(self) -> None:
        if self._on_sel_change is not None:
            self._on_sel_change(self._sel_mode, len(self._sel_rows))

    def _draw_sel_overlay(self, lo: int, hi: int) -> None:
        """选择模式覆盖层（每帧最后绘制）：选中高亮带 + 左缘勾选圈 +
        整行透明命中块（stipple 可命中且挡住下层链接点击，对齐 TG）。"""
        if not self._sel_mode:
            return
        rw = max(80, self.winfo_width())
        y = self._cum[lo]
        for i in range(lo, min(hi, len(self._rows))):
            h = self._heights[i] or 0
            if h <= 0:                       # R31B2：相册成员行 0 高 → 无覆盖层
                y += h
                continue
            if self._row_sel_ok(i):
                sel = i in self._sel_rows
                if sel:
                    band = self.create_rectangle(
                        0, y, rw, y + h, fill=self._pal["sel_band"],
                        outline="")
                    self._item_ids.append(band)
                    self.tag_lower(band)      # 垫底，不盖气泡文字
                cy = y + h / 2
                cx = self.PAD_X + self.SEL_R + 2
                r = self.SEL_R
                if sel:
                    self._item_ids.append(self.create_oval(
                        cx - r, cy - r, cx + r, cy + r,
                        fill=self._pal["self"], outline=self._pal["self"]))
                    self._item_ids.append(self.create_text(
                        cx, cy, text="✓", anchor="center",
                        font=(self._font.actual("family"), 9, "bold"),
                        fill="#ffffff"))
                else:
                    self._item_ids.append(self.create_oval(
                        cx - r, cy - r, cx + r, cy + r,
                        fill="", outline=self._pal["sel_ring"], width=1))
            tag = f"r31sel{i}"
            # fill="" 的矩形不参与命中 → 用 gray12 stipple 近似透明但可点击
            rect = self.create_rectangle(0, y, rw, y + h, fill="#010203",
                                         outline="", stipple="gray12",
                                         tags=(tag,))
            self._item_ids.append(rect)
            self.tag_bind(tag, "<Button-1>",
                          lambda _e, idx=i: self._toggle_select(idx))
            y += h

    # ---------- 对外 API ----------
    def set_me_uid(self, uid) -> None:
        """登录后拿到自己 uid：重绘一次即可（着色按 uid 实时判定）。"""
        if self._me_uid == uid:
            return
        self._me_uid = uid
        self._render()

    def set_grid(self, color: str | None) -> None:
        if color != self._grid_color:
            self._grid_color = color
            self._render()

    def _draw_grid(self) -> None:
        self.delete("excel_grid")
        if not self._grid_color:
            return
        w, h = self.winfo_width(), self.winfo_height()
        top = self.canvasy(0)
        # 只绘制视口内的线，消息历史长度不会增加 Canvas item 数量。
        for x in range(0, max(w, 1), 88):
            self.create_line(x, top, x, top + h, fill=self._grid_color,
                             tags=("excel_grid",))
        first = int(top // 24) * 24
        for y in range(first, int(top + h) + 24, 24):
            self.create_line(0, y, w, y, fill=self._grid_color,
                             tags=("excel_grid",))
        self.tag_lower("excel_grid")

    def set_colors(self, colors: dict) -> None:
        """T3：主题切换——整批替换颜色表并重绘（不改行数据/滚动位置）。
        Apple 风格皮肤可通过 bubble_r/bubble_pad_h/bubble_pad_v token 覆盖几何常量。"""
        if not colors:
            return
        self._pal.update(colors)
        self.configure(bg=self._wallpaper or self._pal["bg"])
        # Apple 风格气泡几何覆盖（可选 token → 实例属性遮蔽类常量）
        if "bubble_r" in colors and colors["bubble_r"]:
            self.BUBBLE_R = int(colors["bubble_r"])
        if "bubble_pad_h" in colors and colors["bubble_pad_h"]:
            self.BUBBLE_PAD_H = int(colors["bubble_pad_h"])
        if "bubble_pad_v" in colors and colors["bubble_pad_v"]:
            self.BUBBLE_PAD_V = int(colors["bubble_pad_v"])
        if getattr(self, "_jump_btn", None):   # R31A：浮动按钮跟随主题
            self._jump_btn.config(bg=self._pal["self"],
                                  activebackground=self._pal["self"])
        # R56：自含滚动条跟随皮肤（原滑轨/把手硬编码浅灰，深色下跳色）
        if getattr(self, "_sb", None):
            self._sb.config(
                troughcolor=self._pal["bg"],
                bg=self._pal.get("react_bg") or "#d8d8d8",
                activebackground=self._pal.get("hit_active") or "#b0b0b0")
        self._render()

    def set_font(self, font) -> None:
        """R-字号：重建消息区字体档链（正文+粗/斜/等宽/粗斜+头像/日期/回应字号），
        清空宽度/换行缓存并整列重估（调用方设置面板「字体大小」变更时注入）。"""
        if font == getattr(self, "_last_font", None):
            return
        self._last_font = tuple(font)
        self._font = tkfont.Font(root=self, font=font)
        try:
            self._linespace = self._font.metrics("linespace")
        except Exception:
            self._linespace = font[1] + 3
        _fam = self._font.actual("family")
        _sz = self._font.cget("size")
        self._font_sig = f"{_fam}/{_sz}"
        self._avatar_font = (_fam, 9, "bold")
        self._date_font = (_fam, 9)
        self._react_font = (_fam, 8)
        self._bold_font = tkfont.Font(root=self, font=(_fam, _sz, "bold"))
        self._italic_font = tkfont.Font(root=self, font=(_fam, _sz, "italic"))
        self._mono_font = tkfont.Font(root=self, font=("Consolas", _sz))
        self._bolditalic_font = tkfont.Font(root=self,
                                            font=(_fam, _sz, ("bold", "italic")))
        try:
            self._linespace = max(
                f.metrics("linespace")
                for f in (self._font, self._bold_font, self._italic_font,
                          self._mono_font, self._bolditalic_font))
        except Exception:
            pass
        self._meas_cache.clear()
        self._wrap_cache.clear()
        for i in range(len(self._heights)):      # 行高全部作废重估
            self._heights[i] = None
        self._cum_dirty = True
        if self._at_bottom:
            self._stick_bottom = True
        if getattr(self, "_jump_btn", None):     # 浮动按钮跟随字号
            self._jump_btn.config(font=(_fam, 10, "bold"))
        self._render()

    def set_wallpaper(self, color: str | None) -> None:
        """R32B4：聊天壁纸（None=恢复主题默认 bg）；换肤 set_colors 后仍保留。"""
        self._wallpaper = color or None
        self.configure(bg=self._wallpaper or self._pal["bg"])
        self._render()

    # ---------- R17 字幕可读性增强 ----------
    def set_halo(self, color: str | None) -> None:
        """开关/更换正文字描边光晕色（None=关闭）。开启后正文字后补一圈该色副本。"""
        if color == self._halo:
            return
        self._halo = color
        self._render()

    def _text(self, x, y, text, font, fill, anchor="nw", halos=((1, 0), (-1, 0), (0, 1), (0, -1)),
              width=None):
        """R17：建文本 item；若开了光晕，先按 4 邻域偏移画 fill 色副本形成描边，再画主色。
        返回主色 item id；光晕副本一并登记进 _item_ids 供重绘清理。"""
        if self._halo and text:
            for dx, dy in halos:
                self._item_ids.append(self.create_text(
                    x + dx, y + dy, anchor=anchor, text=text, font=font,
                    fill=self._halo, width=width))
        item = self.create_text(x, y, anchor=anchor, text=text, font=font,
                                fill=fill, width=width)
        self._item_ids.append(item)
        return item

    # ---------- R13 表情回应 / 已读回执 ----------
    def set_thread_count(self, seq, n: int) -> None:
        """R34 群内话题：更新根消息的「N 条回复」徽标计数（n<=0 摘除徽标）。"""
        i = self.seq_index(seq) if seq is not None else None
        if i is None or not (0 <= i < len(self._rows)):
            return
        raw = self._rows[i].raw
        if n and n > 0:
            raw["thread_count"] = n
        else:
            raw.pop("thread_count", None)
        self._heights[i] = None
        self._cum_dirty = True
        if self._at_bottom:
            self._stick_bottom = True
        self._render()

    # ---------- R71 频道评论入口 ----------
    def set_comment_entry(self, on: bool) -> None:
        """频道会话（非创建者）下即使 0 条评论也显示「💬 评论」入口。
        切换时整表重估高（徽标占位变化），并重绘。"""
        on = bool(on)
        if on == self._comment_entry:
            return
        self._comment_entry = on
        self._heights = [None] * len(self._heights)
        self._cum_dirty = True
        if self._at_bottom:
            self._stick_bottom = True
        self._render()

    def set_forum_mode(self, on: bool) -> None:
        """R72 论坛频道：主列表按贴展示（评论入口始终可见 + 帖子卡片化）。
        复用 _comment_entry 让每条帖子都显示「💬 评论」入口。"""
        on = bool(on)
        if on == self._forum_mode:
            return
        self._forum_mode = on
        self.set_comment_entry(on)
        if on:
            self._recompute_forum_counts()
        # 全部行高重算（论坛模式切换影响所有行高度）
        self._heights = [None] * len(self._rows)
        self._cum_dirty = True
        if self._at_bottom:
            self._stick_bottom = True
        self._render()

    def _recompute_forum_counts(self) -> None:
        """R72 论坛模式：统计每条根贴的回复数，写回 raw['thread_count'] + 同步索引 + 孤儿标记。"""
        counts = {}
        for r in self._rows:
            tr = r.raw.get("thread_root")
            if tr:
                counts[tr] = counts.get(tr, 0) + 1
        root_seqs = {r.raw.get("seq") for r in self._rows}
        for r in self._rows:
            seq = r.raw.get("seq")
            tr = r.raw.get("thread_root")
            if seq and seq in counts:
                r.raw["thread_count"] = counts[seq]
            # 孤儿回复（根贴不在列表中）：标记为降级显示
            if tr and tr not in root_seqs:
                r.raw["_orphan_thread"] = True
            else:
                r.raw.pop("_orphan_thread", None)
        self._thread_counts = counts

    def set_reactions(self, seq, reactions: dict) -> None:
        """重设某条消息的回应状态（同一条 dict 已被 core 原地更新，这里仅重算高度重绘）。
        R27：若最近一次变化在 2s 内，对该表情药丸做弹入高亮动画。"""
        i = self.seq_index(seq) if seq is not None else None
        if i is None:
            return
        recent = self._recent_emoji(reactions)
        self._anim = (seq, recent) if recent else None
        self._heights[i] = None
        self._cum_dirty = True
        if self._at_bottom:
            self._stick_bottom = True
        self._render()
        self._schedule_anim_clear(seq)

    # ---------- R27 快速回应 ----------
    @staticmethod
    def _recent_emoji(reactions: dict) -> str | None:
        """reactions 中最近一次变化的表情（时间戳最大且距今 <2s），无则 None。
        客户端本地点击经由服务器回包同样触发（弹入动画可见）。"""
        best, best_ts = None, 0.0
        for emoji, users in (reactions or {}).items():
            for u, ts in (users or {}).items():
                try:
                    ts = float(ts)
                except (TypeError, ValueError):
                    continue
                if ts > best_ts:
                    best, best_ts = emoji, ts
        if best and time.time() - best_ts < 2.0:
            return best
        return None

    def _schedule_anim_clear(self, seq) -> None:
        if self._anim_job is not None:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
        self._anim_job = self.after(700, lambda: self._clear_anim(seq))

    def _clear_anim(self, seq) -> None:
        self._anim_job = None
        if self._anim and self._anim[0] == seq:
            self._anim = None
            if self.seq_index(seq) is not None:
                self._render()

    def _row_reactable(self, idx: int) -> bool:
        """该行能否回应：非系统行、未撤回、有全局 seq；选择模式下不弹回应条。"""
        if self._sel_mode:                     # R31B：多选时不弹悬浮回应条
            return False
        if not (0 <= idx < len(self._rows)):
            return False
        row = self._rows[idx]
        return row.tag != "sys" and not row.raw.get("deleted") and \
            row.raw.get("seq") is not None

    def _set_hover(self, idx) -> None:
        """更新 hover 行（不可回应行一律视为未 hover）；变化才重绘。"""
        if idx is not None and not self._row_reactable(idx):
            idx = None
        if idx == self._hover_row:
            return
        self._hover_row = idx
        self._render()

    def _on_motion(self, ev) -> None:
        """鼠标移动：定位 hover 行。悬浮条画在气泡上方可能越出本行顶部，
        因此在原 hover 行上方留一条 QUICK_BAR_BAND 带保持命中，防"追着跑"。"""
        if not self._on_react or not self._rows:
            return
        cy = self.canvasy(ev.y)
        if self._hover_row is not None:
            try:
                top = self._cum[self._hover_row]
            except IndexError:
                top = 0
            bot = top + (self._heights[self._hover_row] or 0) + self.QUICK_BAR_BAND
            if top - self.QUICK_BAR_BAND <= cy <= bot:
                return
        idx = self.row_at(ev.y)
        self._set_hover(idx if idx is not None and self._row_reactable(idx) else None)

    def _draw_quick_bar(self, i: int, row: _Row, bub_x: int, bub_y: int,
                        bub_w: int, own: bool) -> None:
        """R27/R29D：气泡上方浮出快速回应条（最近使用一排 + "＋"打开全表情选择器）。
        我回应的表情药丸标主题色；条宽超右缘时左移钳制。"""
        if not self._on_react or not self._row_reactable(i):
            return
        reactions = row.raw.get("reactions") or {}
        seq = row.raw.get("seq")
        emojis = list(self._quick_emojis or self.QUICK_EMOJIS)
        mine: set = set()
        if self._me_uid is not None:
            me = str(self._me_uid)
            for emoji in emojis:
                if me in (reactions.get(emoji) or {}):
                    mine.add(emoji)
        pad = self.QUICK_BAR_PAD
        em_w = [self._meas(e) for e in emojis]
        plus_w = self._meas("＋") + 6
        w = sum(em_w) + plus_w + pad * (len(em_w) + 2)
        h = self.QUICK_BAR_H
        if own:
            x0 = bub_x + bub_w - w
        else:
            x0 = bub_x
        x0 = max(self.PAD_X, min(x0, self.winfo_width() - w - self.PAD_X))
        y0 = max(0, bub_y - h - self.QUICK_BAR_TOP)
        self._item_ids.append(self._round_rect(
            x0, y0, x0 + w, y0 + h, h // 2,
            fill="#ffffff", outline="#c8cdd4"))
        x = x0 + pad
        for emoji, ew in zip(emojis, em_w):
            tag = f"r27q{len(self._item_ids)}"
            is_mine = emoji in mine
            self._item_ids.append(self.create_rectangle(
                x, y0 + 2, x + ew + 6, y0 + h - 2, fill=(self._pal["react_own"] if is_mine else self._pal["react_bg"]),
                outline="", tags=(tag,)))
            self._item_ids.append(self.create_text(
                x + (ew + 6) / 2, y0 + h / 2, anchor="center", text=emoji,
                font=self._font,
                fill=self._pal["react_own"] if is_mine else self._pal["react_fg"]))
            self.tag_bind(tag, "<Enter>", lambda e: self.configure(cursor="hand2"))
            self.tag_bind(tag, "<Leave>", lambda e: self.configure(cursor=""))
            self.tag_bind(tag, "<Button-1>",
                          lambda _e, s=seq, em=emoji: self._on_react and
                          self._on_react(s, em))
            x += ew + pad + 4
        # R29D："＋" → 打开全表情选择器（on_quick_more 回调）
        tag = f"r29p{len(self._item_ids)}"
        self._item_ids.append(self.create_rectangle(
            x, y0 + 2, x + plus_w + 6, y0 + h - 2, fill=self._pal["react_bg"], outline="", tags=(tag,)))
        self._item_ids.append(self.create_text(
            x + (plus_w + 6) / 2, y0 + h / 2, anchor="center", text="＋",
            font=self._font, fill=self._pal["react_fg"]))
        self.tag_bind(tag, "<Enter>", lambda e: self.configure(cursor="hand2"))
        self.tag_bind(tag, "<Leave>", lambda e: self.configure(cursor=""))
        self.tag_bind(tag, "<Button-1>",
                      lambda _e, s=seq: self._on_quick_more and self._on_quick_more(s))

    def set_quick_emojis(self, emojis: list) -> None:
        """R29D：刷新快捷表情集（最近使用），并重绘当前悬浮条。"""
        self._quick_emojis = [str(e) for e in (emojis or []) if str(e)][:5]
        if self._hover_row is not None:
            self._schedule_redraw()

    # ---------- R58C 气泡悬停操作条（回复/复制/删除，对齐 TG hover action bar） ----------
    _STRIP_BTN = 22           # 按钮边长
    _STRIP_GAP = 5            # 按钮间距
    _STRIP_PAD = 8            # 操作条与气泡间隙

    def _draw_hover_strip(self, i: int, row: _Row, bub_x: int, bub_y: int,
                          bub_w: int, bub_h: int, own: bool) -> None:
        """气泡外侧竖排 3 个小圆钮：回复/复制/删除。自己气泡→左、他人→右（悬停才浮现）。

        静默失败：未接回调则完全不画（不炸渲染）；点击回调 (i, 'reply'|'copy'|'delete')。"""
        if not self._on_bubble_act or not row or not row.raw.get("text"):
            return
        acts = ["reply", "copy", "delete"]
        glyphs = {"reply": "↩", "copy": "⧉", "delete": "🗑"}
        b = self._STRIP_BTN
        g = self._STRIP_GAP
        h = len(acts) * b + (len(acts) - 1) * g
        top = bub_y + max(0, (bub_h - h) // 2)
        win_w = self.winfo_width()
        if win_w <= 1:
            win_w = bub_x + bub_w + b * 3 + self.PAD_X * 2
        if own:
            x0 = bub_x - self._STRIP_PAD - b     # 左侧空lane
        else:
            x0 = bub_x + bub_w + self._STRIP_PAD  # 右侧空lane
            if x0 + b > win_w:                    # 右侧不足 → 翻到左侧（他人气泡旁通常留足）
                x0 = bub_x - self._STRIP_PAD - b
        x0 = max(self.PAD_X, min(x0, win_w - b - self.PAD_X))
        seq = row.raw.get("seq")
        for k, act in enumerate(acts):
            y0 = top + k * (b + g)
            bt = f"r58c{len(self._item_ids)}"
            self._item_ids.append(self._round_rect(
                x0, y0, x0 + b, y0 + b, 6,
                fill="#ffffff", outline="#c8cdd4"))
            self._item_ids.append(self.create_text(
                x0 + b / 2, y0 + b / 2, anchor="center",
                text=glyphs[act], font=self._font, fill="#5b4636",
                tags=(bt,)))
            if seq is not None:
                self.tag_bind(bt, "<Enter>",
                              lambda e: self.configure(cursor="hand2"))
                self.tag_bind(bt, "<Leave>",
                              lambda e: self.configure(cursor=""))
                self.tag_bind(bt, "<Button-1>",
                              lambda _e, s=seq, a=act: (
                                  (self._on_bubble_act and
                                   self._on_bubble_act(self.seq_index(s), a)),
                                  "break")[-1])

    # ---------- R26A 投票：权威票数更新 ----------
    def set_poll_state(self, seq, payload: dict) -> None:
        """R26A/R70C 服务器 poll_state 事件：重设某投票行的票数状态
        （同一条 dict 已被 core 原地更新，这里仅重算高度重绘，保证票数/高亮即时刷新）。

        payload 为服务器 poll_state：新形状 {counts,total,mine?,correct?} 落
        `poll["state"]`；旧形状 {votes:{uid:idx}} 落 `poll["votes"]`。"""
        i = self.seq_index(seq) if seq is not None else None
        if i is None:
            return
        row = self._rows[i]
        if not isinstance(row.raw.get("poll"), dict):
            return
        payload = payload if isinstance(payload, dict) else {}
        if ("counts" in payload or "mine" in payload or "correct" in payload):
            st = row.raw["poll"].setdefault("state", {})
            for k in ("counts", "total", "mine", "correct", "end"):
                if k in payload:
                    st[k] = payload[k]
        else:
            row.raw["poll"]["votes"] = payload.get("votes") or {}
        self._heights[i] = None
        self._cum_dirty = True
        if self._at_bottom:
            self._stick_bottom = True
        self._render()

    # ---------- R26D 链接预览：补发卡片 ----------
    def set_preview(self, seq, preview: dict) -> None:
        """服务器 preview 事件：给某消息附上链接预览卡片（晚到事件按 seq 幂等）。"""
        i = self.seq_index(seq) if seq is not None else None
        if i is None:
            return
        row = self._rows[i]
        row.raw["preview"] = preview or {}
        row.preview = row.raw["preview"]
        self._heights[i] = None
        self._cum_dirty = True
        if self._at_bottom:
            self._stick_bottom = True
        self._render()

    def set_reads(self, reads: dict) -> None:
        """设置当前会话的已读回执 {uid: seq}（渲染自己消息的 ✓已读）。"""
        self._read_seqs = {int(u): s for u, s in (reads or {}).items()}
        self._render()

    def clear_reads(self) -> None:
        if self._read_seqs:
            self._read_seqs = {}
            self._render()

    def set_group_total(self, total: int) -> None:
        """C9② 设置当前群的成员总数，供 @ 消息气泡显示「✓✓ N/M 已读」。"""
        total = int(total or 0)
        if total != self._group_total:
            self._group_total = total
            self._render()

    # ---------- R30A 未读分隔线 / 日期跳转 ----------
    def set_unread_seq(self, seq) -> None:
        """设置未读边界：seq 之上的第一条消息上方画「未读消息」分隔条；None=清除。
        会话切换时装载历史后调用（client 记录各频道 last_read seq）。"""
        if self._unread_seq == seq:
            return
        self._unread_seq = seq
        if not self._rows:
            self._update_jump_btn()           # R31A：空会话也同步按钮
            return
        for i in range(len(self._rows)):      # 分隔条占行高，全部高度缓存作废重估
            self._heights[i] = None
        self._cum_dirty = True
        if self._at_bottom:
            self._stick_bottom = True
        self._render()

    def _unread_label(self, i: int) -> bool:
        """行 i 上方是否画「未读消息」分隔条：首条 seq 超过边界的消息行。"""
        seq = self._unread_seq
        if seq is None or not (0 <= i < len(self._rows)):
            return False
        s = self._rows[i].raw.get("seq")
        if s is None or s <= seq:
            return False
        prev = self._rows[i - 1].raw.get("seq") if i > 0 else None
        return prev is None or prev <= seq

    def dates(self) -> list:
        """当前会话有消息的日期（升序 YYYY-MM-DD，行序即时序，去重保序）。"""
        out = []
        for r in self._rows:
            d = self._day(r.raw.get("ts", 0))
            if not out or out[-1] != d:
                out.append(d)
        return out

    def jump_to_date(self, day: str) -> bool:
        """日期跳转：滚到该日期第一条消息；无该日期返回 False。"""
        for i, r in enumerate(self._rows):
            if self._day(r.raw.get("ts", 0)) == day:
                self._scroll_to_row(i)
                self._render()
                return True
        return False

    # ---------- R30C 自定义贴纸 ----------
    def stickers_updated(self) -> None:
        """贴纸清单/图片到达（sticker_list / sticker_data 事件）后调用：
        清除拉取去重集并重绘，让未就绪的贴纸行补上图片。"""
        self._stk_req.clear()
        self._render()

    def _is_read(self, row: _Row) -> bool:
        """自己消息是否已被对端读到（忽略自己，取大于等于该消息 seq 的阅读记录）。"""
        if not self._me_uid or row.raw.get("deleted"):
            return False
        seq = row.raw.get("seq")
        if seq is None or not self._read_seqs:
            return False
        return any(u != self._me_uid and s >= seq for u, s in self._read_seqs.items())

    def _is_group_msg(self, row: _Row) -> bool:
        """是否群聊/公共频道消息：群聊不回执单勾，仅对端已读时显示双勾+已读人数。"""
        return row.raw.get("channel") in ("group", "public")

    def _read_count(self, row: _Row) -> int:
        """已读该消息的对端人数（忽略自己，seq ≥ 该消息 seq 的阅读记录数）。"""
        seq = row.raw.get("seq")
        if seq is None:
            return 0
        return sum(1 for u, s in self._read_seqs.items()
                   if u != self._me_uid and s >= seq)

    @staticmethod
    def _reaction_items(reactions: dict) -> list:
        """reactions={emoji:{uid:ts}} → 降序 [(emoji, count, my)]；无则 []。"""
        if not reactions:
            return []
        rows = []
        for emoji, users in reactions.items():
            if not users:
                continue
            rows.append((emoji, len(users), bool(users)))
        rows.sort(key=lambda r: r[1], reverse=True)
        return rows

    def _row_heading(self, row: _Row, in_group: bool, own: bool) -> str:
        """行头基础段（时间+昵称 / 组内空）；已读标记拆为独立段（见 _heading_segs）。
        渲染与估算共用，防虚拟化高度漂移。"""
        return "" if in_group else f"{row.ts} {row.nick}: "

    def _heading_segs(self, row: _Row, in_group: bool, own: bool) -> list:
        """R-：行头 segments = 基础头 + 已读回执。
        私聊：未读/已发达时仅单勾 ✓（SENT_MARK），对端已读→双勾 ✓✓已读（READ_MARK）。
        群聊/公共（_is_group_msg）：未读不画勾，已读→双勾 ✓✓已读 [+N 已读人数]（READ_MARK）。
        P0 三态：本地已发未确认（pending）→ 灰「⏳发送中」标记，优先于单勾/双勾。
        qq 模式（read_mark=None）整段关闭，保持 test_interaction_mode 契约。"""
        base = self._row_heading(row, in_group, own)
        segs = [(base, runs.PLAIN)] if base else []
        if own and row.raw.get("pending"):
            segs.append(("⏳发送中  ", runs.PENDING))
        elif own and self._is_read(row) and self._read_mark:
            if self._is_group_msg(row):
                n = self._read_count(row)
                # C9② @消息气泡显示「✓✓ N/M 已读」（M=群成员总数，未知时退回 N 显示）
                if (row.raw.get("mentions") or row.raw.get("everyone")) \
                        and self._group_total:
                    segs.append((f"✓✓ {n}/{self._group_total} 已读", runs.READ_MARK))
                else:
                    segs.append(("✓✓已读" + (f" {n}" if n and n > 1 else ""),
                                 runs.READ_MARK))
            else:
                segs.append(("✓✓已读  ", runs.READ_MARK))
        elif own and self._read_mark and not self._is_group_msg(row):
            if row.raw.get("seq") is not None:          # 私聊未读：单勾（已发，对端未读）
                segs.append(("✓ ", runs.SENT_MARK))
        return segs

    def _bubble_segs(self, row: _Row, in_group: bool, own: bool) -> list:
        """R41F：气泡正文 segs（估算/绘制共用，保证所见即所估）。

        行头 + 引用前缀(REPLY 可点段) + 剥离前缀后的正文实体段。
        row.body 保持含前缀（搜索/复制用），仅在分段时拆出。
        """
        head_segs = self._heading_segs(row, in_group, own)
        if row.disguise:                          # R70E 消息伪装：风格表头 + 正文整体遮盖
            pre = []
            if row.reply_prefix:
                pre.append((row.reply_prefix, runs.REPLY, None))
            return head_segs + pre + [
                (self._disguise_header(row.disguise), runs.DISGUISE, None),
                (self._disguise_payload(row), rich.SPOILER, "0"),
            ]
        if row.rich:                              # R59：富文本优先（引用/转发前缀作独立段）
            segs = []
            if row.reply_prefix:
                segs.append((row.reply_prefix, runs.REPLY, None))
            if row.fwd_prefix:
                segs.append((row.fwd_prefix, runs.PLAIN, None))
            # R70A：剧透段用它在本行的序号占位 href（换行拆分后仍能定位揭示态）
            si = 0
            for seg in row.rich:
                if seg[1] == rich.SPOILER:
                    segs.append((seg[0], rich.SPOILER, str(si)))
                    si += 1
                else:
                    segs.append(seg)
            if row._edited:
                segs.append((_EDITED_SUFFIX, runs.EDIT_MARK, None))
            return self._guard_mask_segs(head_segs + segs)
        if row.reply_prefix:
            body_wo = row.body[len(row.reply_prefix):]
            pre = [(row.reply_prefix, runs.REPLY)]
        else:
            body_wo = row.body
            pre = []
        # R70B：正文尾部「✎已编辑」拆成独立可点段（点开编辑历史）
        tail = []
        if row._edited and body_wo.endswith(_EDITED_SUFFIX):
            body_wo = body_wo[:-len(_EDITED_SUFFIX)]
            tail.append((_EDITED_SUFFIX, runs.EDIT_MARK, None))
        return self._guard_mask_segs(
            head_segs + pre + runs.tag_entities(body_wo) + tail)

    @staticmethod
    def _disguise_header(style: str) -> str:
        """R70E：伪装风格表头文案（假文件名 / 日志时间戳 / 表头行）。"""
        if style == "code":
            return "📄 config.py · UTF-8 · LF"
        if style == "log":
            return time.strftime("[%H:%M:%S] INFO  connection established")
        if style == "excel":
            return "Sheet1     A     B     C"
        return ""

    @staticmethod
    def _disguise_payload(row: "_Row") -> str:
        """R70E：伪装遮盖的正文（剥引用前缀与已编辑后缀，保持与存储原文一致）。"""
        body = row.body
        if row.reply_prefix and body.startswith(row.reply_prefix):
            body = body[len(row.reply_prefix):]
        if row._edited and body.endswith(_EDITED_SUFFIX):
            body = body[:-len(_EDITED_SUFFIX)]
        return body or " "

    def _draw_disguise_chrome(self, row: "_Row", x: int, y: int, w: int, h: int,
                              own: bool) -> None:
        """R70E：按风格画伪装底色/装饰（纯外观层，不影响布局与数据）。

        code=深色终端块 + 标题分隔线；log=灰底 + 左侧会话栏；excel=白底 + 单元格网格。
        """
        line = self._pal.get("disguise_line", "#9aa4b2")
        if row.disguise == "code":
            bg = self._pal.get("disguise_code_bg", "#1f2633")
        elif row.disguise == "log":
            bg = self._pal.get("disguise_log_bg", "#f2f3f5")
        else:
            bg = self._pal.get("disguise_excel_bg", "#ffffff")
        self._item_ids.append(self.create_rectangle(
            x + 1, y + 1, x + w - 1, y + h - 1, fill=bg, outline=""))
        top = y + self._linespace + 2
        if row.disguise == "code":
            self._item_ids.append(self.create_line(x + 1, top, x + w - 1, top,
                                                   fill=line))
        elif row.disguise == "log":
            self._item_ids.append(self.create_line(x + 2, y + 1, x + 2, y + h - 1,
                                                   fill=line, width=2))
        elif row.disguise == "excel":
            self._item_ids.append(self.create_line(x + 1, top, x + w - 1, top,
                                                   fill=line))
            yy = top + self._linespace
            while yy < y + h - 1:
                self._item_ids.append(self.create_line(x + 1, yy, x + w - 1, yy,
                                                       fill=line))
                yy += self._linespace

    def _toggle_spoiler(self, row, run_idx: int) -> None:
        """R70A：点击剧透遮盖 → 揭示 / 重新遮盖（仅内存态，不落盘、不跨会话）。"""
        key = (id(row), int(run_idx))
        if key in self._spoiler_open:
            self._spoiler_open.discard(key)
        else:
            self._spoiler_open.add(key)
        self._render()

    def set_guard(self, words, enabled: bool) -> None:
        """R70F：注入敏感词表与开关（纯显示层；不影响存储、搜索、复制）。

        词表变化会改变分段 → 全部行高作废重估（复用字号变更的失效流程）。
        """
        wl = tuple(str(w) for w in (words or ()) if str(w))
        on = bool(enabled)
        if (wl, on) == (self._guard_words, self._guard_on):
            return
        self._guard_words, self._guard_on = wl, on
        if wl and on:
            # 长词优先，保证 "密码abc" 中的长词先命中而非被短词切碎
            pat = "|".join(re.escape(w) for w in sorted(wl, key=len, reverse=True))
            self._guard_rx = re.compile(f"({pat})", re.IGNORECASE)
        else:
            self._guard_rx = None
        self._wrap_cache.clear()
        for i in range(len(self._heights)):      # 行高全部作废重估
            self._heights[i] = None
        self._cum_dirty = True
        self._render()

    def _guard_mask_segs(self, segs: list) -> list:
        """R70F：把 PLAIN 段中命中敏感词的片段转为 SPOILER 遮盖段。

        run 索引走 1000+ 命名空间，避免与 R70A 富文本剧透（0 起）的揭示态串键。
        """
        if not self._guard_on or self._guard_rx is None:
            return segs
        out, kidx = [], 0
        for seg in segs:
            text = seg[0]
            kind = seg[1] if len(seg) > 1 else runs.PLAIN
            if kind != runs.PLAIN or not text:
                out.append(seg)
                continue
            pos = 0
            for m in self._guard_rx.finditer(text):
                if m.start() > pos:
                    out.append((text[pos:m.start()], runs.PLAIN, None))
                out.append((m.group(0), rich.SPOILER, str(1000 + kidx)))
                kidx += 1
                pos = m.end()
            if pos < len(text):
                out.append((text[pos:], runs.PLAIN, None))
        return out

    def _reaction_height(self, row: _Row) -> int:
        return self.REACT_PAD if self._reaction_items(row.raw.get("reactions")) else 0

    # ---------- R34 群内话题徽标 / R71 频道评论入口 ----------
    def _thread_badge_h(self, row: _Row) -> int:
        """「N 条回复」徽标占位高（气泡正下方、回应条之上；估算与绘制共用）。
        R71：频道会话（_comment_entry）下即使 0 条评论也占位，作为「💬 评论」入口。"""
        if row.raw.get("deleted"):
            return 0
        if not row.raw.get("thread_count") and not self._comment_entry:
            return 0
        return self._linespace + 8

    def _draw_thread_badge(self, i: int, row: _Row, y: int, wrap_w: int,
                           own: bool) -> int:
        """R34：气泡正下方画「💬 N 条回复」徽标，点击回调 on_open_thread(row)。
        R71：0 条时文案改为「💬 评论」，同样点击开话题窗（=评论区）。"""
        if not self._thread_badge_h(row):
            return 0
        n = row.raw.get("thread_count") or 0
        lbl = f"💬 {n} 条回复" if n else "💬 评论"
        bh = self._linespace + 6
        bw = self._meas(lbl) + 14
        bx = (max(self.winfo_width(), 1) - bw - self.PAD_X) if own else self.PAD_X
        tag = f"r34t{i}"
        self._item_ids.append(self.create_rectangle(
            bx, y + 1, bx + bw, y + 1 + bh,
            fill=self._pal.get("react_bg", "#ececec"), outline="", tags=(tag,)))
        self._item_ids.append(self.create_text(
            bx + 7, y + 1 + bh / 2, anchor="w", text=lbl,
            font=self._react_font, fill=self._pal.get("link") or "#06c",
            tags=(tag,)))
        if self._on_open_thread:
            self.tag_bind(tag, "<Button-1>",
                          lambda _e, rw=row: self._on_open_thread(rw))
            self.tag_bind(tag, "<Enter>",
                          lambda e: self.configure(cursor="hand2"))
            self.tag_bind(tag, "<Leave>",
                          lambda e: self.configure(cursor=""))
        return self._linespace + 8

    # ---------- R71 联系人名片卡（气泡正下方、话题徽标之下） ----------
    def _card_data(self, row) -> dict | None:
        """取合法名片数据 {uid,nick}；缺失/非法 → None（不占位）。"""
        c = row.raw.get("card")
        if not isinstance(c, dict):
            return None
        return c if (c.get("uid") is not None or c.get("nick")) else None

    def _card_badge_h(self, row: _Row) -> int:
        """名片卡占位高（估算与绘制共用）。"""
        if row.raw.get("deleted") or not self._card_data(row):
            return 0
        return self._linespace + 20

    def _draw_card_badge(self, i: int, row: _Row, y: int, own: bool) -> int:
        """R71：画一张可点联系人名片（头像占位 + 昵称），点击回调 on_card(uid)。
        头像位用 👤 字形占位，不额外拉取图片（名片只携带 uid/nick）。"""
        c = self._card_data(row)
        if not c or not self._card_badge_h(row):
            return 0
        uid = c.get("uid")
        nick = str(c.get("nick") or (f"#{uid}" if uid is not None else "?"))
        lbl = "👤 " + nick
        bh = self._linespace + 18
        maxw = max(self.winfo_width() - 2 * self.PAD_X, 80)
        bw = min(self._meas(lbl) + 26, maxw)
        bx = (max(self.winfo_width(), 1) - bw - self.PAD_X) if own else self.PAD_X
        tag = f"r71c{i}"
        pal = self._pal
        self._item_ids.append(self.create_rectangle(
            bx, y + 1, bx + bw, y + 1 + bh,
            fill=pal.get("card_bg", "#eef3fb"), outline=pal.get("line", "#d8d8d8"),
            tags=(tag,)))
        self._item_ids.append(self.create_text(
            bx + 9, y + 1 + bh / 2, anchor="w", text=lbl, font=self._react_font,
            fill=pal.get("link") or "#06c", tags=(tag,),
            width=max(bw - 16, 1)))
        if self._on_card:
            self.tag_bind(tag, "<Button-1>",
                          lambda _e, u=uid: self._on_card(u))
            self.tag_bind(tag, "<Enter>",
                          lambda e: self.configure(cursor="hand2"))
            self.tag_bind(tag, "<Leave>",
                          lambda e: self.configure(cursor=""))
        return self._linespace + 20

    # ---------- R72 位置徽标 ----------
    def _geo_data(self, row: _Row) -> dict | None:
        """取合法位置数据 {lat,lon,name?}；缺失 → None。"""
        g = row.raw.get("geo")
        if not isinstance(g, dict):
            return None
        lat = g.get("lat")
        lon = g.get("lon")
        if lat is None or lon is None:
            return None
        return g

    def _geo_badge_h(self, row: _Row) -> int:
        """位置卡占位高。"""
        if row.raw.get("deleted") or not self._geo_data(row):
            return 0
        return self._linespace + 20

    def _draw_geo_badge(self, i: int, row: _Row, y: int, own: bool) -> int:
        """R72：画可点位置卡（📍 地点名 / 经纬度 → 点击打开 OSM 链接）。"""
        g = self._geo_data(row)
        if not g or not self._geo_badge_h(row):
            return 0
        import geo_api
        lat, lon = float(g.get("lat")), float(g.get("lon"))
        name = str(g.get("name") or "").strip()
        lbl = "📍 " + (name or geo_api.format_pair(lat, lon))
        bh = self._linespace + 18
        maxw = max(self.winfo_width() - 2 * self.PAD_X, 80)
        bw = min(self._meas(lbl) + 26, maxw)
        bx = (max(self.winfo_width(), 1) - bw - self.PAD_X) if own else self.PAD_X
        tag = f"r72g{i}"
        pal = self._pal
        self._item_ids.append(self.create_rectangle(
            bx, y + 1, bx + bw, y + 1 + bh,
            fill=pal.get("card_bg", "#eef3fb"), outline=pal.get("line", "#d8d8d8"),
            tags=(tag,)))
        self._item_ids.append(self.create_text(
            bx + 9, y + 1 + bh / 2, anchor="w", text=lbl, font=self._react_font,
            fill=pal.get("link") or "#06c", tags=(tag,),
            width=max(bw - 16, 1)))
        url = geo_api.osm_url(lat, lon)
        import webbrowser
        self.tag_bind(tag, "<Button-1>",
                      lambda _e, u=url: webbrowser.open(u))
        self.tag_bind(tag, "<Enter>",
                      lambda e: self.configure(cursor="hand2"))
        self.tag_bind(tag, "<Leave>",
                      lambda e: self.configure(cursor=""))
        return self._linespace + 20

    # ---------- R72 视频留言徽标 ----------
    def _vmemo_badge_h(self, row: _Row) -> int:
        """视频留言占位高。"""
        if not row.vmemo or row.raw.get("deleted"):
            return 0
        return self._linespace + 20

    def _draw_vmemo_badge(self, i: int, row: _Row, y: int, own: bool) -> int:
        """R72：画可点视频留言徽标（⭕ 时长 → 点击弹播放窗）。"""
        if not row.vmemo or not self._vmemo_badge_h(row):
            return 0
        dur = row.vmemo_dur or 0.0
        lbl = f"⭕ 视频留言 {dur:.1f}s"
        bh = self._linespace + 18
        maxw = max(self.winfo_width() - 2 * self.PAD_X, 80)
        bw = min(self._meas(lbl) + 26, maxw)
        bx = (max(self.winfo_width(), 1) - bw - self.PAD_X) if own else self.PAD_X
        tag = f"r72v{i}"
        pal = self._pal
        self._item_ids.append(self.create_rectangle(
            bx, y + 1, bx + bw, y + 1 + bh,
            fill=pal.get("card_bg", "#eef3fb"), outline=pal.get("line", "#d8d8d8"),
            tags=(tag,)))
        self._item_ids.append(self.create_text(
            bx + 9, y + 1 + bh / 2, anchor="w", text=lbl, font=self._react_font,
            fill=pal.get("link") or "#06c", tags=(tag,),
            width=max(bw - 16, 1)))
        path = row.vmemo_path or ""
        if path and self._on_vmemo:
            self.tag_bind(tag, "<Button-1>",
                          lambda _e, p=path: self._on_vmemo(p))
            self.tag_bind(tag, "<Enter>",
                          lambda e: self.configure(cursor="hand2"))
            self.tag_bind(tag, "<Leave>",
                          lambda e: self.configure(cursor=""))
        return self._linespace + 20

    # ---------- R34/R71/R72 气泡下方徽标总槽位（话题/评论 + 名片 + 位置 + 视频留言） ----------
    def _badges_h(self, row: _Row) -> int:
        """徽标总占位高；后续元素（回应条/键盘/引用徽标）据此下移。"""
        return (self._thread_badge_h(row) + self._card_badge_h(row)
                + self._geo_badge_h(row) + self._vmemo_badge_h(row))

    def _draw_badges(self, i: int, row: _Row, y: int, wrap_w: int,
                     own: bool) -> int:
        """依次画话题徽标、名片卡、位置卡、视频留言徽标，返回总占位高。"""
        y2 = y
        h = self._draw_thread_badge(i, row, y2, wrap_w, own)
        y2 += h
        h += self._draw_card_badge(i, row, y2, own)
        y2 = y + h
        h += self._draw_geo_badge(i, row, y2, own)
        y2 = y + h
        h += self._draw_vmemo_badge(i, row, y2, own)
        return h

    # ---------- 功能① 被引用聚合徽标（仅统计当前已加载历史，本地计数） ----------
    def _quote_count(self, row) -> int:
        """取该行被引用的次数（无 seq / 已删除 → 0，不显示徽标）。"""
        if row.raw.get("deleted"):
            return 0
        seq = row.raw.get("seq")
        return len(self._quote_refs.get(seq, [])) if seq is not None else 0

    def _draw_quote_badge(self, i: int, row: _Row, bub_x: int, bub_y: int,
                          bub_w: int, bub_h: int, own: bool) -> None:
        """在气泡外缘浮一个小「↩N」徽标（放留白槽位，不占行高），点击高亮所有引用行。"""
        n = self._quote_count(row)
        if n <= 0:
            return
        seq = row.raw.get("seq")
        lbl = f"↩{n}"
        bh = self._linespace + 2
        bw = self._meas(lbl) + 10
        mid = bub_y + bub_h // 2
        if own:
            bx = max(self.PAD_X, bub_x - bw - 6)      # 右气泡 → 徽标放左侧留白
        else:
            bx = bub_x + bub_w + 6                    # 左气泡 → 徽标放右侧留白
        tag = f"qbadge{i}"
        self._item_ids.append(self.create_rectangle(
            bx, mid - bh // 2, bx + bw, mid + bh // 2,
            fill=self._pal.get("react_bg", "#ececec"), outline="", tags=(tag,)))
        self._item_ids.append(self.create_text(
            bx + 5, mid, anchor="w", text=lbl,
            font=self._react_font, fill=self._pal.get("link") or "#06c",
            tags=(tag,)))
        self.tag_bind(tag, "<Button-1>",
                      lambda _e, s=seq: self._show_quotes(s))
        self.tag_bind(tag, "<Enter>", lambda e: self.configure(cursor="hand2"))
        self.tag_bind(tag, "<Leave>", lambda e: self.configure(cursor=""))

    def _show_quotes(self, seq) -> None:
        """功能①：高亮所有引用了 seq 的行（点「被引用 N」徽标时调用）。"""
        refs = self._quote_refs.get(seq)
        if not refs:
            return
        self._quote_hi = set(refs)
        if self._quote_hi_after is not None:
            try:
                self.after_cancel(self._quote_hi_after)
            except Exception:
                pass
        self._render()
        self._quote_hi_after = self.after(1800, self._clear_quote_hi)

    def _clear_quote_hi(self) -> None:
        self._quote_hi_after = None
        if not self._quote_hi:
            return
        self._quote_hi.clear()
        self._render()

    def _draw_reaction_bar(self, row: _Row, y: int, wrap_w: int, own: bool) -> None:
        """气泡下方画回应条（小药丸：emoji+计数；我回应的标主题色）。
        R27：药丸可点（切换回应）；最近变化的表情描边高亮做弹入动画。"""
        items = self._reaction_items(row.raw.get("reactions"))
        if not items:
            return
        seq = row.raw.get("seq")
        anim_emoji = self._anim[1] if (self._anim and self._anim[0] == seq) else None
        row_w = max(wrap_w, 1)
        # 拼接 "👍 2 · ❤ 1"；用测量预排，避免逐字符 create_text 对不齐
        parts = [(f"{emoji} {count}", emoji) for emoji, count, _my in items]
        # 计算每个 pill 宽并列排
        sp = self._meas(" ")
        pad = 6
        pill_w = [sum(self._meas(ch) for ch in lbl) for lbl, _e in parts]
        x = max(wrap_w - sum(pill_w) - pad * len(parts) -
                (len(parts) - 1) * int(sp * 0.6), wrap_w - self.PAD_X) if own \
            else self.PAD_X
        x = min(x, row_w - 2)
        py = y + 3
        ph = self.REACT_PAD - 6
        for lbl, emoji in parts:
            lw = self._meas(lbl)
            is_mine = self._me_uid and \
                f"{self._me_uid}" in (row.raw.get("reactions", {}).get(emoji) or {})
            bg = self._pal["react_own"] if is_mine else self._pal["react_bg"]
            # R27：弹入动画目标表情 → 主题色描边加粗
            is_anim = emoji == anim_emoji
            tag = f"r27r{len(self._item_ids)}"
            item = self.create_rectangle(x, py, x + lw + pad, py + ph,
                                         fill=bg,
                                         outline=self._pal["link"] if is_anim else bg,
                                         width=2 if is_anim else 1, tags=(tag,))
            self._item_ids.append(item)
            item = self.create_text(x + pad / 2, py + ph / 2, anchor="center",
                                    text=lbl, font=self._react_font,
                                    fill=self._pal["react_fg"])
            self._item_ids.append(item)
            if self._on_react and seq is not None:   # R27：药丸可点切换回应
                # R30D：hover 500ms → 回应详情（谁点了这个表情），移出即取消
                self.tag_bind(tag, "<Enter>",
                              lambda e, s=seq, em=emoji: self._pill_hover(s, em, e))
                self.tag_bind(tag, "<Leave>", lambda e: self._pill_hover_end())
                self.tag_bind(tag, "<Button-1>",
                              lambda _e, s=seq, em=emoji: self._on_react and
                              self._on_react(s, em))
            x += lw + pad + int(sp * 0.6)

    # ---------- R30D 回应详情（药丸 hover 提示） ----------
    def _pill_hover(self, seq, emoji, ev) -> None:
        if self._pill_job is not None:
            try:
                self.after_cancel(self._pill_job)
            except Exception:
                pass
            self._pill_job = None
        self.configure(cursor="hand2")
        if self._on_react_detail:
            self._pill_job = self.after(
                500, lambda: self._on_react_detail(seq, emoji, ev))

    def _pill_hover_end(self) -> None:
        self.configure(cursor="")
        if self._pill_job is not None:
            try:
                self.after_cancel(self._pill_job)
            except Exception:
                pass
            self._pill_job = None
        if self._on_react_detail:                # ev=None → client 收起提示
            self._on_react_detail(None, None, None)

    def _dup_seq(self, raw: dict) -> bool:
        """按服务器全局 seq 去重：历史装载与实时事件可能携带同一条消息。"""
        seq = raw.get("seq")
        if seq is None:
            return False
        if seq in self._seen_seq:
            return True
        self._seen_seq.add(seq)
        if len(self._seen_seq) > 20000:        # 防无限膨胀，只保留最近一半
            self._seen_seq = set(list(self._seen_seq)[-10000:])
        return False

    def append(self, msg: dict, is_system: bool = False) -> None:
        row = _Row(msg, is_system=is_system)
        if row.empty:
            return
        if not is_system and self._dup_seq(row.raw):
            return                              # 历史已装载过，跳过重复
        # R72 论坛模式：新回复 → 根贴计数 +1，根贴行高失效（徽标变化）
        # 优化：用 _thread_counts dict O(1) 查计数；根贴行定位只扫一次并顺带判断孤儿
        if self._forum_mode and row.raw.get("thread_root"):
            tr = row.raw["thread_root"]
            cur = self._thread_counts.get(tr, 0)
            self._thread_counts[tr] = cur + 1
            root_found = False
            for j, r in enumerate(self._rows):
                if r.raw.get("seq") == tr:
                    r.raw["thread_count"] = cur + 1
                    self._heights[j] = None
                    root_found = True
                    break
            # 孤儿回复（根贴不在列表中）：降级为普通消息显示在主列表
            if not root_found:
                row.raw["_orphan_thread"] = True
        self._rows.append(row)
        self._heights.append(None)
        if not is_system and self._is_image_row(row):
            self._invalidate_album_around(len(self._rows) - 1)   # R31B2：并入相册 → 锚点重算
        if self._cum_dirty:
            self._rebuild_cum()
        else:
            self._heights[-1] = self._estimate(len(self._rows) - 1, row)
            self._cum.append(self._cum[-1] + self._heights[-1])
        if self._at_bottom:
            self._stick_bottom = True         # 渲染定稿 region 后再钉底（实测高度会漂移）
            self._cancel_smooth()             # R39D②：钉底优先，打断在途惯性
            self._set_scrollregion()          # 先同步总高，滚动才落到真实底部
            self.yview_moveto(1.0)            # 吸底：新消息自动滚到底
        else:
            self._jump_new += 1               # R31A：离底新消息 → 浮动按钮 +N
        if self._fade_enabled and not is_system \
                and row.raw.get("uid") is not None \
                and row.raw.get("uid") == self._me_uid:
            self._fading[len(self._rows) - 1] = time.time()   # R39D②：own 气泡淡入
            self._start_fade()
        if not is_system and row.raw.get("uid") is not None \
                and row.raw.get("uid") == self._me_uid and self._at_bottom:
            # R43C：吸底新消息滑入（own 气泡）；首个渲染帧起算，重绘静默回基线
            self._slide_row = len(self._rows) - 1
            self._slide_started = True
            self._slide_begin = None
        self._schedule_render()               # 合并渲染：连续追加只重绘一次

    def _schedule_render(self) -> None:
        """把重绘推迟到下一帧（30ms 防抖），批量 append 只触发一次。"""
        if self._render_job is None:
            self._render_job = self.after(30, self._flush_render)

    def _flush_render(self) -> None:
        self._render_job = None
        self._render()

    def _cancel_render(self) -> None:
        if self._render_job is not None:
            try:
                self.after_cancel(self._render_job)
            except Exception:
                pass
            self._render_job = None

    def append_sys(self, text: str) -> None:
        if text:
            self.append({"ts": time.time(), "text": text}, is_system=True)

    def drop_local_row(self, raw: dict) -> bool:
        """R31C：按 raw dict 身份移除本地失败行（重发成功、避免与回显重复）。
        返回是否找到并移除。"""
        for i, r in enumerate(self._rows):
            if r.raw is raw:
                del self._rows[i]
                del self._heights[i]
                self._rebuild_cum()
                self._seen_seq.discard(None)
                self._render()
                return True
        return False

    # ---------- R39C 本地历史懒加载 ----------
    HIST_PAGE = 100                       # 每页装载条数
    _WRAP_CACHE_MAX = 2048                # 换行行数 LRU 上限

    def set_history_loader(self, cb) -> None:
        """R39C：注入懒加载回调 cb(before_seq, n) -> list[dict]（升序更旧一页）。"""
        self._hist_loader = cb

    def prepend(self, msgs: list) -> int:
        """头部插入一批更旧消息（懒加载翻页），保持视口锚定不跳动；返回插入行数。"""
        rows = []
        for m in msgs or []:
            if not isinstance(m, dict):
                continue
            row = _Row(m)
            if row.empty:
                continue
            s = m.get("seq")
            if s is not None and s in self._seen_seq:
                continue                  # 回放/翻页重叠去重
            rows.append(row)
        if not rows:
            return 0
        # 视口锚点：插入前顶部像素位（按当前 region 比例还原），插入后平移新增块高度
        total_before = max(1, self._cum[-1])
        top_px = self.yview()[0] * total_before
        self._rows[:0] = rows
        self._heights[:0] = [None] * len(rows)
        for r in rows:
            s = r.raw.get("seq")
            if s is not None:
                self._seen_seq.add(s)
        self._rebuild_cum()               # 插入后全量重估（跨天/分组/未读线重算）
        added_h = sum(self._heights[:len(rows)])
        self._cancel_smooth()             # R39D②：视口锚定优先，打断在途惯性
        self._set_scrollregion()
        self.yview_moveto(min(1.0, (top_px + added_h) / max(1, self._cum[-1])))
        self._render()                    # 实测高度修正（估算→实测的微小漂移容忍）
        return len(rows)

    def _maybe_load_top(self) -> None:
        """滚到顶时向 loader 取更旧一页并头部插入（收到短页/空页即认为翻尽）。"""
        if self._hist_done or self._hist_busy or self._hist_loader is None:
            return
        if not self._rows or self.canvasy(0) > 2:
            return
        seqs = [r.raw.get("seq") for r in self._rows if r.raw.get("seq") is not None]
        if not seqs:
            self._hist_done = True        # 整屏本地行（无 seq）：无处可翻
            return
        self._hist_busy = True
        try:
            page = self._hist_loader(min(seqs), self.HIST_PAGE)
        except Exception:
            page = None                   # loader 异常不崩 UI，停翻即可
        finally:
            self._hist_busy = False
        if not page:
            self._hist_done = True
            return
        self.prepend(page)
        if len(page) < self.HIST_PAGE:
            self._hist_done = True

    def _wrap_lines(self, segs: list, inner: int) -> list:
        """R39C 带行数 LRU 的换行：估算与绘制同源同参，命中即免重测。
        键含段落种类（R59 富文本换行/绘制同参一致）。"""
        try:
            key = (self._font_sig,
                   tuple((s[0], s[1] if len(s) > 1 else "") for s in segs),
                   inner)
        except Exception:
            key = (self._font_sig, "".join(str(w) for w, *_ in segs), inner)
        lines = self._wrap_cache.get(key)
        if lines is not None:
            self._wrap_cache[key] = self._wrap_cache.pop(key)   # 命中移到队尾
            return lines
        try:
            lines = runs.wrap_segments(segs, inner, self._meas_kind)
        except Exception:
            lines = [[("".join(w for w, _k in segs), runs.PLAIN)]]
        if len(self._wrap_cache) >= self._WRAP_CACHE_MAX:
            self._wrap_cache.pop(next(iter(self._wrap_cache)))  # 淘汰最旧
        self._wrap_cache[key] = lines
        return lines

    def load(self, msgs: list, me_uid=None) -> None:
        if me_uid is not None:
            self._me_uid = me_uid
        self.clear()
        self._hist_done = False               # R39C：新会话重置懒加载翻尽标记
        for m in msgs:
            row = _Row(m)
            if row.empty:
                continue
            self._rows.append(row)
            self._heights.append(None)
        self._rebuild_cum()
        self._seen_seq = {r.raw.get("seq") for r in self._rows if r.raw.get("seq") is not None}
        self._quote_refs = count_quote_refs(self._rows)   # 功能①：本地统计被引用次数
        self._quote_hi.clear()
        if self._quote_hi_after is not None:
            try:
                self.after_cancel(self._quote_hi_after)
            except Exception:
                pass
            self._quote_hi_after = None
        self._stick_bottom = True
        self._cancel_smooth()                 # R39D②：切会话打断在途惯性
        self._set_scrollregion()
        self.yview_moveto(1.0)
        self._render()

    def clear(self) -> None:
        self._cancel_render()
        self._rows = []
        self._heights = []
        self._seen_seq = set()
        self._thread_counts = {}              # R72 优化：清空论坛回复计数索引
        self._spoiler_open = set()            # R70A：切会话清空已揭示剧透（不跨会话）
        self._stick_bottom = False
        self._cum = [0]
        self._cum_dirty = False
        self._first_visible = 0
        self._hover_row = None                # R27：清空会话时同时隐藏悬浮回应条
        self._unread_seq = None               # R30A：清空会话同时撤未读分隔线
        if self._sel_mode or self._sel_rows:  # R31B：清空会话同时退选择模式
            self._sel_mode = False
            self._sel_rows = set()
            self._notify_sel()
        self._jump_new = 0                    # R31A：清空会话同时复位浮动按钮
        if getattr(self, "_jump_btn", None):
            self._jump_btn.place_forget()
        self._stk_req.clear()                 # R30C：清拉取去重（新会话可再请求）
        self._quote_refs.clear()              # 功能①：清空引用聚合统计
        self._quote_hi.clear()
        if self._quote_hi_after is not None:
            try:
                self.after_cancel(self._quote_hi_after)
            except Exception:
                pass
            self._quote_hi_after = None
        self._clear_slide()                   # R43C：清空会话同时撤在途滑入动画
        self._delete_items()
        self._set_scrollregion()
        self._at_bottom = True

    def scroll_to_end(self) -> None:
        self._cancel_render()
        self._stick_bottom = True
        self._cancel_smooth()                 # R39D②：程序性跳底打断在途惯性
        self.yview_moveto(1.0)
        self._render()

    @property
    def count(self) -> int:
        return len(self._rows)

    @property
    def at_bottom(self) -> bool:
        return self._at_bottom

    def row_at(self, y_px: int) -> int | None:
        """画布坐标 → 行下标（右键/双击定位用）；越界返回 None。"""
        if not self._rows:
            return None
        if self._cum_dirty:
            self._rebuild_cum()
        cy = self.canvasy(y_px)
        if cy < 0 or cy > self._cum[-1]:
            return None
        i = bisect.bisect_right(self._cum, cy) - 1
        return i if 0 <= i < len(self._rows) else None

    def get_row(self, i: int) -> dict | None:
        """行下标 → 原始消息 dict（右键菜单/引用回复取数据）。"""
        if 0 <= i < len(self._rows):
            return self._rows[i].raw
        return None

    def body_text(self, i: int) -> str:
        """行下标 → 已展开 emoji 的正文（复制/引用用）。"""
        if 0 <= i < len(self._rows):
            return self._rows[i].body
        return ""

    def seq_index(self, seq) -> int | None:
        """服务器 seq → 行下标；没有则 None（C3 编辑/撤回定位用）。"""
        if seq is None:
            return None
        for i, row in enumerate(self._rows):
            if row.raw.get("seq") == seq:
                return i
        return None

    def update_text(self, seq, new_text: str, rich=None, edits=None) -> bool:
        """C3 编辑：原地改文本，标注已编辑，重算高度后重绘。R59 同步富文本段。
        R70B：edits 为该消息的历史版本快照（服务器下发），落 raw 供「✎已编辑」查看。"""
        i = self.seq_index(seq)
        if i is None or 0 > i or i >= len(self._rows):
            return False
        row = self._rows[i]
        raw = row.raw
        if raw.get("deleted") or isinstance(raw.get("poll"), dict):
            return False                          # R26A：投票消息结构固定，禁编辑
        raw["text"] = new_text
        raw["edited"] = True
        raw.pop("sticker", None)             # 编辑以文本为准
        if rich is None:                     # R59：编辑为纯文本 → 清旧富文本
            raw.pop("rich", None)
        elif isinstance(rich, list):         # R59：带新富文本段
            raw["rich"] = rich
        if isinstance(edits, list) and edits:   # R70B：历史版本快照
            raw["edits"] = edits
        row.body = row._compile_body(raw)
        row.rich = row._san_rich(raw.get("rich"))   # R59：编辑后富文本段同步刷新
        self._heights[i] = None
        self._cum_dirty = True
        if self._at_bottom:
            self._stick_bottom = True
        self._render()
        return True

    def mark_deleted(self, seq) -> bool:
        """C3 撤回：标记墓碑并渲染「消息已撤回」。"""
        i = self.seq_index(seq)
        if i is None or 0 > i or i >= len(self._rows):
            return False
        row = self._rows[i]
        raw = row.raw
        # 注：del 事件到达时，client_core 的历史存储可能已把同一条 dict 置
        # deleted=True（GUI 行与历史存储共享该对象）。因此这里不因已 deleted
        # 而跳过——无论如何都重编译正文，保证墓碑立刻渲染。
        raw["deleted"] = True
        raw["text"] = ""
        row.body = row._compile_body(raw)
        if row.image_path:                    # R31B2：相册成员撤回 → 整链重算
            self._invalidate_album_around(i)
        self._heights[i] = None
        self._cum_dirty = True
        if self._at_bottom:
            self._stick_bottom = True
        self._render()
        return True

    # ---------- C1 聊天内搜索 ----------
    def search_all(self, query: str) -> int:
        """全文检索已装载历史：query 匹配行正文（大小写不敏感），高亮全部命中。"""
        q = (query or "").strip().lower()
        self._search_q = q
        if not q:
            return self.search_clear()
        hits = [i for i, r in enumerate(self._rows) if q in r.body.lower()]
        self._search_hits = hits
        self._hit_idx = set(hits)
        self._search_active = -1
        self._render()
        return len(hits)

    def search_next(self, delta: int = 1) -> str | None:
        """跳到下一/上一命中（±1，循环）；命中行滚入视野并高亮当前项。"""
        if not self._search_hits:
            return None
        n = len(self._search_hits)
        if self._search_active < 0:
            self._search_active = 0 if delta > 0 else n - 1
        else:
            self._search_active = (self._search_active + delta) % n
        target = self._search_hits[self._search_active]
        self._scroll_to_row(target)
        self._render()
        return self._rows[target].body

    def search_count(self) -> int:
        return len(self._search_hits)

    def search_active_index(self) -> int:
        return self._search_active

    def search_is_active(self) -> bool:
        return bool(self._search_q) and bool(self._search_hits)

    def search_clear(self) -> int:
        """清除搜索高亮与导航状态。"""
        self._search_q = ""
        self._search_hits = []
        self._hit_idx = set()
        self._search_active = -1
        if not self._rows:
            return 0
        self._render()
        return 0

    def _hit_kind(self, i: int) -> str | None:
        if i not in self._hit_idx:
            return None
        if self._search_active >= 0 and i == self._search_hits[self._search_active]:
            return "active"
        return "hit"

    def locate_seq(self, seq, query: str = "") -> int:
        """R9+ 全局搜索跳转：滚动定位并高亮到指定 seq 的消息行。

        ``query`` 非空时先标记同词命中（可循坏跳转）；否则单独把该行高亮为当前项。
        返回命中行下标，找不到返回 -1。
        """
        idx = -1
        for i, r in enumerate(self._rows):
            if r.raw.get("seq") == seq:
                idx = i
                break
        if idx < 0:
            return -1
        q = (query or "").strip().lower()
        if q:
            self.search_all(q)                     # 高亮本会话全部同词命中
            for k, h in enumerate(self._search_hits):
                if h == idx:
                    self._search_active = k
                    self._render()
                    break
        else:
            self.search_clear()
            self._search_q = q
            self._search_hits = [idx]
            self._hit_idx = {idx}
            self._search_active = 0
            self._render()
        self._scroll_to_row(idx)
        return idx

    def _scroll_to_row(self, i: int) -> None:
        """把行 i 滚入可见区（搜索跳转用）。"""
        if not self._rows or not (0 <= i < len(self._rows)):
            return
        if self._cum_dirty:
            self._rebuild_cum()
        if not self._cum or not self.winfo_height():
            return
        y = self._cum[i]
        h = self._heights[i] or self._estimate(i, self._rows[i])
        top = self.canvasy(0)
        if y < top or y + h > top + self.winfo_height():
            total = self._cum[-1]
            self.yview_moveto(max(0.0, min(1.0, y / total)))
        self._stick_bottom = self._yview_bottom_float() >= 0.999

    def _yview_bottom_float(self) -> float:
        try:
            return self.yview()[1]
        except Exception:
            return 0.0

    def jump_to_seq(self, seq) -> bool:
        """R41F：定位并短暂高亮 seq 对应消息（点引用前缀跳转）。找不到→False。"""
        if seq is None:
            return False
        idx = next((i for i, r in enumerate(self._rows)
                    if r.raw.get("seq") == seq), None)
        if idx is None:
            return False
        self._scroll_to_row(idx)
        if self._jump_hi_after is not None:
            try:
                self.after_cancel(self._jump_hi_after)
            except Exception:
                pass
            self._jump_hi_after = None
        self._jump_hi = idx
        self._render()
        self._jump_hi_after = self.after(1500, self._clear_jump_hi)
        return True

    def _clear_jump_hi(self) -> None:
        """跳转高亮到期消退。"""
        self._jump_hi_after = None
        if self._jump_hi < 0:
            return
        self._jump_hi = -1
        self._render()

    # ---------- 内部：高度/前缀和 ----------
    def _wrap_width(self, width: int) -> int:
        """正文换行宽度：扣除左右留白与头像槽（sys 行无头像但留同样宽度不影响）。"""
        return max(80, width - 2 * self.PAD_X - self.AVATAR - self.GUTTER)

    def _meas(self, s: str) -> int:
        """带缓存的文本像素宽（R11 runs 换行/定位共用；字体不变时复用）。
        LRU 限长：超过上限淘汰最早插入项，且为自加粗键，防止文本词缓存无界增长。"""
        if s in self._meas_cache:
            w = self._meas_cache.pop(s)     # 命中移到队尾
        else:
            try:
                w = self._font.measure(s)
            except Exception:
                w = len(s) * 8
        if len(self._meas_cache) >= self._MEAS_CACHE_MAX:
            self._meas_cache.pop(next(iter(self._meas_cache)))  # 淘汰最旧
        self._meas_cache[s] = w
        return w

    # ---------- R59 富文本：按段落种类选字体档的测量 ----------
    def _font_for(self, kind) -> object:
        """kind → 字体档（b/i/c/粗斜；缺省正文）。"""
        k = str(kind or "")
        if k in (rich.CODE, runs.DISGUISE):    # R70E：伪装表头同样走等宽档
            return self._mono_font
        if k == rich.BOLD:
            return self._bold_font
        if k == rich.ITALIC:
            return self._italic_font
        return self._font

    def _meas_kind(self, s: str, kind=None) -> int:
        """按段落种类字体测量像素宽（换行/绘制共用，防富文本换行漂移）。"""
        font = self._font_for(kind)
        key = f"{id(font)}:{s}"
        if key in self._meas_cache:
            w = self._meas_cache.pop(key)
        else:
            try:
                w = font.measure(s)
            except Exception:
                w = self._meas(s)
        if len(self._meas_cache) >= self._MEAS_CACHE_MAX:
            self._meas_cache.pop(next(iter(self._meas_cache)))
        self._meas_cache[key] = w
        return w

    # ---------- R12 消息分组 / 日期分隔（对齐 TG HistoryView） ----------
    @staticmethod
    def _day(ts) -> str:
        return time.strftime("%Y-%m-%d", time.localtime(ts))

    @classmethod
    def _fmt_date(cls, ts) -> str:
        """今天/昨天/N天前（<7天）/今年 M月D日 / 跨年 Y年M月D日。"""
        lt = time.localtime(ts)
        now = time.localtime(time.time())
        if cls._day(ts) == cls._day(time.time()):
            return "今天"
        if cls._day(ts) == cls._day(time.time() - 86400):
            return "昨天"
        days = int((time.time() - ts) // 86400)      # R68：近一周显示「N 天前」
        if 2 <= days < 7:
            return f"{days}天前"
        if lt.tm_year == now.tm_year:
            return f"{lt.tm_mon}月{lt.tm_mday}日"
        return f"{lt.tm_year}年{lt.tm_mon}月{lt.tm_mday}日"

    def _in_group(self, i: int) -> bool:
        """行 i 是否与前一行同组：同 uid、同 channel、非系统/贴纸行、时间差 ≤ GROUP_WINDOW。
        R31B2：同人连续图片行并入相册组（成员行高度归零，由锚点统一画网格）。"""
        if i <= 0:
            return False
        a, b = self._rows[i - 1], self._rows[i]
        if a.tag == "sys" or b.tag == "sys":
            return False
        ai = bool(a.image_path) and not a.raw.get("deleted")
        bi = bool(b.image_path) and not b.raw.get("deleted")
        if ai and bi:                            # 相册组：图片+图片可合并
            if a.raw.get("uid") != b.raw.get("uid"):
                return False
            if a.raw.get("channel") != b.raw.get("channel"):
                return False
            if (b.raw.get("ts", 0) - a.raw.get("ts", 0)) > self.GROUP_WINDOW:
                return False
            # 成员行高度为 0，不能携带分隔条 → 未读线/跨天处断开相册
            return not self._unread_label(i) and not self._date_label(i)
        if ai or bi:                             # 图片行不与文本/贴纸行并入同组
            return False
        if a.sticker_custom or b.sticker_custom:  # R30C：贴纸行同样独立
            return False
        if a.raw.get("uid") != b.raw.get("uid"):
            return False
        if a.raw.get("channel") != b.raw.get("channel"):
            return False
        return (b.raw.get("ts", 0) - a.raw.get("ts", 0)) <= self.GROUP_WINDOW

    # ---------- R31B2 相册分组（同人连续图片合并网格气泡） ----------
    @staticmethod
    def _is_image_row(row: _Row) -> bool:
        """有效图片行（未撤回）：撤回行显示墓碑文本，不参与相册。"""
        return bool(row.image_path) and not row.raw.get("deleted")

    def _album_rows(self, i: int) -> list:
        """锚点 i 起的相册成员行下标（含锚点；非图片行返回 [i]）。"""
        out = [i]
        j = i + 1
        while j < len(self._rows) and self._is_image_row(self._rows[j]) \
                and self._in_group(j):
            out.append(j)
            j += 1
        return out

    def _album_chain(self, i: int) -> tuple:
        """行 i 所在连续图片链（仅按 uid/channel/时间窗，忽略撤回态）→ (lo, hi)。
        撤回只改 deleted 标记，不清 image_path，故删除后仍能定位原相册做高度失效。"""
        rows = self._rows
        lo = hi = i
        while lo > 0:
            a, b = rows[lo - 1], rows[lo]
            if not (a.image_path and b.image_path
                    and a.raw.get("uid") == b.raw.get("uid")
                    and a.raw.get("channel") == b.raw.get("channel")
                    and b.raw.get("ts", 0) - a.raw.get("ts", 0) <= self.GROUP_WINDOW):
                break
            lo -= 1
        while hi + 1 < len(rows):
            a, b = rows[hi], rows[hi + 1]
            if not (a.image_path and b.image_path
                    and a.raw.get("uid") == b.raw.get("uid")
                    and a.raw.get("channel") == b.raw.get("channel")
                    and b.raw.get("ts", 0) - a.raw.get("ts", 0) <= self.GROUP_WINDOW):
                break
            hi += 1
        return lo, hi

    def _album_cell(self) -> tuple:
        """相册网格单元格尺寸（IMG 上限均分，固定值保证估算=实测不抖动）。"""
        return ((IMG_MAX_W - ALBUM_GAP) // ALBUM_COLS,
                (IMG_MAX_H - ALBUM_GAP) // ALBUM_COLS)

    def _album_grid_h(self, n: int) -> int:
        cw, ch = self._album_cell()
        nrows = (n + ALBUM_COLS - 1) // ALBUM_COLS
        return nrows * ch + (nrows - 1) * ALBUM_GAP

    def _cap_h(self, cap: str, wrap_w: int | None = None) -> int:
        """R32B3：caption 高度 = 行数 × 行高 + 上间距（与 _draw_album 折行同参）。"""
        if not wrap_w:
            wrap_w = self._wrap_w or self._wrap_width(self.winfo_width())
        inner = max(self.MIN_BUBBLE_W, int(wrap_w * self.CAP_RATIO))
        n = len(self._wrap_lines([(cap, runs.PLAIN)], inner))   # R39C LRU
        return n * self._linespace + self.PAD_TOP

    def _invalidate_album_around(self, i: int) -> None:
        """相册成员增删后失效整条链的高度（锚点网格高度依赖成员数）。"""
        lo, hi = self._album_chain(i)
        for j in range(lo, hi + 1):
            self._heights[j] = None
        self._cum_dirty = True

    def _date_label(self, i: int):
        """行 i 上方是否画日期分隔条 → 文案；无需返回 None。
        首条非今天显示；之后跨天显示（今天/昨天/日期）。"""
        if not (0 <= i < len(self._rows)):
            return None
        ts = self._rows[i].raw.get("ts", 0)
        if i == 0:
            return self._fmt_date(ts) if self._day(ts) != self._day(time.time()) else None
        pts = self._rows[i - 1].raw.get("ts", 0)
        if self._day(ts) != self._day(pts):
            return self._fmt_date(ts)
        return None

    def _estimate(self, i: int, row: _Row) -> int:
        """行高估算：与 _draw_row 同用 runs 布局（R11/R12），保证预测量≈实测量。"""
        # R72 论坛模式：话题回复不在主列表显示（高度归零），但孤儿回复例外
        if (self._forum_mode and row.raw.get("thread_root")
                and not row.raw.get("_orphan_thread")):
            return 0
        in_group = self._in_group(i)
        if row.poll:                             # R26A：投票气泡（问题换行 + 选项 + 状态行）
            if not self._wrap_w:
                self._wrap_w = self._wrap_width(self.winfo_width())
            inner = max(self.MIN_BUBBLE_W, int(self._wrap_w * self.CAP_RATIO))
            q = str(row.poll.get("question") or "投票")
            nq = len(self._wrap_lines([(q, runs.PLAIN)],
                                      inner - 2 * self.BUBBLE_PAD_H))   # R39C LRU
            n = nq + len(row.poll.get("options") or []) + 1     # +1 状态行
            pv = self.GROUP_PAD_V if in_group else self.BUBBLE_PAD_V
            h = n * self._linespace + 2 * pv + self.PAD_TOP
            if not in_group:
                h = max(h, self.AVATAR + self.PAD_TOP)
            else:
                h = max(h, self._linespace + self.PAD_TOP)
        elif row.voice:                              # R19：语音气泡高（▶+时长+跑道）
            pv = self.GROUP_PAD_V if in_group else self.BUBBLE_PAD_V
            h = self._linespace + 2 * pv + (6 if row.voice_path else 0) + self.PAD_TOP
        elif row.image_path and not row.raw.get("deleted"):   # A7/R31B2
            if self._in_group(i):                # 相册成员行：高度归零（锚点画网格）
                return 0
            n = len(self._album_rows(i))         # 锚点：头部行 + 网格占位高
            h = self._linespace + 2 * self.PAD_TOP
            h += IMG_MAX_H if n <= 1 else self._album_grid_h(n)
            if row.caption:                      # R32B3：图下 caption
                h += self._cap_h(row.caption, wrap_w=None)
            h = max(h, self.AVATAR + self.PAD_TOP)
        elif row.sticker_custom and not row.raw.get("deleted"):
            # R30C：贴纸行 = 头部行 + 贴纸占位高（未缓存时实测修正为文字高）
            h = max(self._linespace + STICKER_MAX + 2 * self.PAD_TOP,
                    self.AVATAR + self.PAD_TOP)
        elif row.fwd_pack and not row.raw.get("deleted"):
            # R39D③ 合并转发卡：与 _draw_fwd_pack 同源（2 固定行 + min(len,3) 预览行），
            # 高度与换行宽无关（预览恒单行），免依赖 _wrap_w
            n_prev = min(max(sum(1 for it in (row.fwd_pack.get("items") or [])
                                 if isinstance(it, dict)), 1), 3)
            pv = self.GROUP_PAD_V if in_group else self.BUBBLE_PAD_V
            h = (2 + n_prev) * self._linespace + 2 * pv + self.PAD_TOP + 4
        else:
            if not self._wrap_w:
                self._wrap_w = self._wrap_width(self.winfo_width())
            inner = max(self.MIN_BUBBLE_W, int(self._wrap_w * self.CAP_RATIO))
            segs = self._bubble_segs(row, in_group, self._row_tag(row) == "self")
            n = len(self._wrap_lines(segs, inner))      # R39C LRU
            pv = self.GROUP_PAD_V if in_group else self.BUBBLE_PAD_V
            h = n * self._linespace + 2 * pv + self.PAD_TOP
            if not in_group:                   # 组首/独立行带头像：需头像槽高度兜底
                h = max(h, self._linespace + self.PAD_TOP, self.AVATAR + self.PAD_TOP)
            else:                              # 组内行紧凑：无头像，仅文本高
                h = max(h, self._linespace + self.PAD_TOP)
        if row.preview:                      # R26D：链接预览卡片占位高度（正文之下）
            h += self._preview_h() + self.PREVIEW_PAD
        h += self._badges_h(row)              # R34/R71：话题徽标+名片卡占位（气泡正下方）
        h += self._reaction_height(row)       # R13：回应条占位高度
        h += self._kb_height(row)             # R46：bot 键盘占位高度
        if self._date_label(i):
            h += self.DATE_H
        if self._unread_label(i):            # R30A：未读分隔条占位
            h += self.UNREAD_H
        return h

    def _rebuild_cum(self) -> None:
        cum = [0]
        s = 0
        for i, row in enumerate(self._rows):
            h = self._heights[i] if self._heights[i] is not None else self._estimate(i, row)
            self._heights[i] = h
            s += h
            cum.append(s)
        self._cum = cum
        self._cum_dirty = False

    def _set_scrollregion(self) -> None:
        total = self._cum[-1] if self._cum else 0
        w = max(80, self.winfo_width())
        self.configure(scrollregion=(0, 0, w, total))

    # ---------- 手绘涂鸦留白背景（原创美术·高级交互：奶油渐变 + 云朵/星星/笑脸） ----------
    _DOODLE_TAG = "doodle"

    def _doodle_pal(self) -> dict:
        try:
            b = self._pal.get("bg", "#ffffff")
            r, g, bl = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
            dark = (0.299 * r + 0.587 * g + 0.114 * bl) < 128
        except Exception:
            dark = False
        if dark:
            return {"ink": "#43382f", "fill": "#3a3028", "ac": "#4a7a5e"}
        return {"ink": "#f0e0c2", "fill": "#f5e7cd", "ac": "#ffd9b0"}

    def _draw_doodles(self) -> None:
        if self._grid_color:
            self.delete(self._DOODLE_TAG)
            self._draw_grid()
            return
        self.delete("excel_grid")
        """只在「最后一条消息下方的留白区」铺一层淡手绘涂鸦。用独立 tag 管理，
        不进入 _item_ids，因此不影响滚动区计算，也绝不会压在文字/气泡上。"""
        self.delete(self._DOODLE_TAG)
        w = self.winfo_width()
        vh = self.winfo_height()
        if w <= 10 or vh <= 10:
            return
        if self._rows and self._cum:
            y0 = self._cum[-1]                  # 内容底（canvas 坐标）
            y1 = self.canvasy(vh)               # 视口底
            if y1 - y0 < 140:                   # 留白太窄不画，保持干净
                return
            top = y0
        else:
            top = 0
            y1 = vh
        p = self._doodle_pal()
        ink, fill, ac = p["ink"], p["fill"], p["ac"]
        w1 = max(1, int(w * 0.012))             # 线宽随窗口
        row_h = 170
        cxm = (int(w * 0.16), int(w * 0.50), int(w * 0.84))
        r0 = top + 20
        r = 0
        while r0 < y1 - 40:
            for k, cx in enumerate(cxm):
                s = 18 + (30 if k % 2 == 0 else 22)   # 云/笑脸/星交替大小
                if (r + k) % 3 == 0:            # 云朵
                    self.create_oval(cx - s, r0 + int(s * 0.3), cx, r0 + int(s * 0.9),
                                     fill=fill, outline=ink, width=w1,
                                     tags=(self._DOODLE_TAG,))
                    self.create_oval(cx - int(s * 0.5), r0, cx + int(s * 0.4), r0 + int(s * 0.6),
                                     fill=fill, outline=ink, width=w1,
                                     tags=(self._DOODLE_TAG,))
                elif (r + k) % 3 == 1:          # 笑脸弧
                    rr = int(s * 0.45)
                    yc = r0 + int(s * 0.5)
                    self.create_oval(cx - rr, yc - rr, cx + rr, yc + rr, width=w1,
                                     outline=ink, tags=(self._DOODLE_TAG,))
                    self.create_oval(cx - int(s * 0.2), yc - int(s * 0.25),
                                     cx - int(s * 0.05), yc - int(s * 0.1),
                                     fill=ink, outline=ink, tags=(self._DOODLE_TAG,))
                    self.create_oval(cx + int(s * 0.05), yc - int(s * 0.25),
                                     cx + int(s * 0.2), yc - int(s * 0.1),
                                     fill=ink, outline=ink, tags=(self._DOODLE_TAG,))
                    self.create_arc(cx - int(s * 0.28), yc - int(s * 0.1),
                                    cx + int(s * 0.28), yc + int(s * 0.2),
                                    start=20, extent=140, style="arc", outline=ac,
                                    width=w1, tags=(self._DOODLE_TAG,))
                else:                           # 星星＋圆点
                    self.create_text(cx, r0 + int(s * 0.4), text="✦", fill=ac, font=self._font,
                                     tags=(self._DOODLE_TAG,))
                    self.create_oval(cx + int(s * 0.6), r0, cx + int(s * 0.85), r0 + int(s * 0.25),
                                     fill=ac, outline=ac, tags=(self._DOODLE_TAG,))
            r0 += row_h
            r += 1

    # ---------- 渲染 ----------
    def _render(self, _depth: int = 0) -> None:
        self._cancel_render()
        lottie_label.detach_canvas(self)       # R38C：重绘会重建 item，先停旧轮播
        # R43C：重绘会重建 item → 取消在途滑入定时器并清掉旧 item 快照；
        # 保留 _slide_row/_begin 状态，本轮若该行仍可见则重新施加当前偏移（不闪烁）。
        if self._slide_job is not None:
            try:
                self.after_cancel(self._slide_job)
            except Exception:
                pass
            self._slide_job = None
        self._slide_items = None
        self._slide_mark = -1
        if not self._rows:
            self._delete_items()
            self._set_scrollregion()
            self._draw_doodles()
            self._at_bottom = True
            return
        if self._cum_dirty:
            self._rebuild_cum()
        w = self.winfo_width()
        wrap_w = self._wrap_width(w)
        self._wrap_w = wrap_w
        vh = self.winfo_height()
        top = self.canvasy(0)
        bottom = self.canvasy(vh) if vh > 0 else top + 400
        # 可见区间：上边界多退一行，避免裁切误差
        i = max(0, bisect.bisect_right(self._cum, top) - 1)
        if i > 0:
            i -= 1
        self._delete_items()
        y = self._cum[i]
        self._first_visible = i
        guard = 0
        while i < len(self._rows) and y < bottom and guard < 400:
            if self._slide_started and i == self._slide_row:
                self._slide_mark = len(self._item_ids)   # R43C：记录滑入行 item 起始位
            h = self._draw_row(i, self._rows[i], y, wrap_w)
            if self._heights[i] != h:
                self._heights[i] = h
                self._cum_dirty = True
            y += h
            i += 1
            guard += 1
        if self._cum_dirty:
            self._rebuild_cum()
            if _depth < 1:
                self._render(_depth + 1)     # 高度实测修正后重排一次即收敛
            return
        self._advance_slide()                # R43C：对滑入行 item 施加当前偏移并推进动画
        self._set_scrollregion()             # 先落 region，再按真实总高判定吸底
        if self._stick_bottom:
            self.yview_moveto(1.0)           # 实测高度已定稿，重新钉到底部
            self._stick_bottom = False
        self._at_bottom = self.yview()[1] >= 0.999
        self._update_jump_btn()              # R31A：浮动按钮随渲染同步显隐/计数
        self._draw_doodles()                 # F2：留白区手绘涂鸦（在消息之后 / 选择层之前）
        self._draw_sel_overlay(self._first_visible, i)   # R31B：选择覆盖层最后画

    def _draw_row(self, i: int, row: _Row, y: int, wrap_w: int) -> int:
        # R72 论坛模式：话题回复不画（高度归零，主列表只显贴子），孤儿回复例外
        if (self._forum_mode and row.raw.get("thread_root")
                and not row.raw.get("_orphan_thread")):
            return 0
        dy = 0
        dl = self._date_label(i)                 # R12：跨天日期分隔条（画在行首）
        if dl:
            dy = self.DATE_H
            item = self._text(self.winfo_width() / 2, y + dy / 2,
                              text=dl, anchor="center",
                              font=self._date_font, fill=self._pal["date"])
        if self._unread_label(i):                # R30A：未读分隔条（红线 + 居中文字断开）
            uy = y + dy
            dy += self.UNREAD_H
            mid = self.winfo_width() / 2
            my = uy + self.UNREAD_H / 2
            tw = self._meas("未读消息")
            self._item_ids.append(self.create_line(
                self.PAD_X, my, mid - tw / 2 - 4, my, fill=self._pal["unread"]))
            self._item_ids.append(self.create_line(
                mid + tw / 2 + 4, my, self.winfo_width() - self.PAD_X, my,
                fill=self._pal["unread"]))
            self._text(mid, my, text="未读消息", anchor="center",
                       font=self._date_font, fill=self._pal["unread"])
        y += dy
        tag = self._row_tag(row)
        if tag == "sys":
            # 系统行：居中灰字，无头像；R67 拍一拍行复用 sys 样式但斜体
            fnt = self._italic_font if row.raw.get("nudge") else self._font
            item = self._text(self.PAD_X, y + self.PAD_TOP, text=f"· {row.body}",
                              anchor="nw", font=fnt,
                              fill=self._pal["sys"], width=wrap_w)
            try:
                h = (self.bbox(item)[3] - self.bbox(item)[1]) + self.PAD_TOP
            except Exception:
                h = self._estimate(i, row) - dy
            return h + dy
        color = self._pal.get(tag or "normal")
        if row.fwd_pack and not row.raw.get("deleted"):
            # R39D③ 合并转发卡片：堆叠卡样式，双击展开逐条
            in_group_f = self._in_group(i)
            return self._draw_fwd_pack(i, row, y, wrap_w, in_group_f) + dy
        if row.voice:
            # R19 语音消息：独立紧凑播放气泡（见 _draw_voice）
            in_group_v = self._in_group(i)
            return self._draw_voice(i, row, y, wrap_w, in_group_v) + dy
        if row.poll:
            # R26A 投票消息：独立气泡（问题 + 可点选项 + 状态行）
            in_group_p = self._in_group(i)
            h, px, py, pw, phh = self._draw_poll(i, row, y, wrap_w, in_group_p)
            if row.preview:                  # R26D：投票行罕见带预览时同样附卡片
                self._draw_preview_card(i, row, py + phh + self.PREVIEW_PAD, px, pw)
                h += self.PREVIEW_PAD + self._preview_h()
            tb_h = self._badges_h(row)           # R34/R71：徽标+名片（投票气泡下方）
            if tb_h:
                self._draw_badges(i, row, py + phh, wrap_w,
                                  self._row_tag(row) == "self")
            if self._reaction_height(row):       # R33①：投票行回应条补齐（估算已计高）
                self._draw_reaction_bar(row, py + phh + tb_h, wrap_w,
                                        self._row_tag(row) == "self")
                h += self.REACT_PAD
            if self._on_react and i == self._hover_row:  # R27：投票行快速回应
                self._draw_quick_bar(i, row, px, py, pw, self._row_tag(row) == "self")
            self._hit_back(i, y, h)
            return h + dy
        if row.sticker_custom and not row.raw.get("deleted"):
            # R30C 自定义贴纸行：头部 + 贴纸尺寸图片（未缓存时回退短码文本）
            return self._draw_custom_sticker(i, row, y, wrap_w) + dy
        if row.image_path and not row.raw.get("deleted"):
            # A7/R31B2 图片行：成员行高度归零；锚点画「头部 + 相册网格」
            if self._in_group(i):
                return dy                          # dy 恒 0（_in_group 在分隔条处断组）
            return self._draw_album(i, row, y, wrap_w) + dy
        # 普通/私聊/自己：左右气泡（自己右对齐无头像，他人左带头像）—— R11 富文本 runs
        in_group = self._in_group(i)             # R12：组内行省头像/头部前缀、紧凑留白
        own = tag == "self"
        head = self._row_heading(row, in_group, own)   # R13：已读带 ✓已读 标记
        ph, pv = self.BUBBLE_PAD_H, (self.GROUP_PAD_V if in_group else self.BUBBLE_PAD_V)
        row_w = self.winfo_width()
        if row_w <= 1:
            row_w = wrap_w
        inner = max(self.MIN_BUBBLE_W, int(row_w * self.CAP_RATIO))
        segs = self._bubble_segs(row, in_group, own)
        lines = self._wrap_lines(segs, inner)       # R39C LRU（估算同参免重测）
        n = len(lines)
        th = n * self._linespace
        bub_w = max(min(max((runs.line_width(ln, self._meas_kind) for ln in lines),
                            default=0), inner) + 2 * ph, self.MIN_BUBBLE_W)
        bub_h = th + 2 * pv
        bub_y = y + self.PAD_TOP
        if own:
            bub_x = row_w - self.PAD_X - bub_w     # 右缘留 PAD_X
        else:
            if not in_group:                       # R12：组内行不再重复画头像（缩进保留）
                self._draw_msg_avatar(self.PAD_X, bub_y, row)
            bub_x = self.PAD_X + self.AVATAR + self.GUTTER
        self._item_ids.append(self._round_rect(
            bub_x, bub_y, bub_x + bub_w, bub_y + bub_h, self.BUBBLE_R,
            fill=self._bubble_fill(i, own),
            outline=self._pal["bubble_outline" if own else "bubble_inline"]))
        # R58：气泡尾部小三角（对齐 TG/iMessage 气泡尾巴）。自己靠右外、他人靠左外；
        # 尾巴与气泡同填充（无描边），且仅当文本超过一行时绘制避免矮泡的「小钉子」显得突兀。
        if n >= 2 and not row.raw.get("failed"):
            fill = self._bubble_fill(i, own)
            mid = bub_y + bub_h // 2
            tail = 7
            if own:
                self._item_ids.append(self.create_polygon(
                    bub_x + bub_w, mid,
                    bub_x + bub_w + tail, mid - tail,
                    bub_x + bub_w + tail, mid + tail,
                    fill=fill, outline=""))
            else:
                self._item_ids.append(self.create_polygon(
                    bub_x, mid,
                    bub_x - tail, mid - tail,
                    bub_x - tail, mid + tail,
                    fill=fill, outline=""))
        # B 仿毛玻璃：磨砂雾层（极淡白色 stipple，注释在下方文字绘制之后，
        # 因此文字/代码/链接始终位于雾层之上，保证可读性）
        self._item_ids.append(self.create_rectangle(
            bub_x, bub_y, bub_x + bub_w - 1, bub_y + bub_h - 1,
            fill="#ffffff", stipple="gray12", outline=""))
        if row.disguise:                        # R70E：伪装底色/装饰（画在正文之下）
            self._draw_disguise_chrome(row, bub_x, bub_y, bub_w, bub_h, own)
        # 功能①：被引用聚合徽标（气泡外缘浮 + 点击高亮引用它的行）
        self._draw_quote_badge(i, row, bub_x, bub_y, bub_w, bub_h, own)
        # 逐 run 渲染：R59 富文本（粗/斜/代码/链接）+ 提及/话题/裸链着色，链接可点 + 下划线
        # Apple 风格：蓝底气泡用 link_self/mention_self 浅色变体保证对比度
        sp = self._meas(" ")
        base_x, y0 = bub_x + ph, bub_y + pv
        for li, ln in enumerate(lines):
            x = base_x
            yy = y0 + li * self._linespace
            for seg in ln:
                w = seg[0]
                kind = seg[1] if len(seg) > 1 else ""           # R59：段可能 3 元组
                href = seg[2] if len(seg) > 2 else None
                rfont = self._font_for(kind)                     # 粗/斜/代码用对应字体档
                if kind == rich.CODE:                            # 行内代码：等宽 + 浅底
                    cfill = self._pal.get("code_bg", "#ececec")
                    ww = self._meas_kind(w, kind)
                    self._item_ids.append(self.create_rectangle(
                        x, yy - 1, x + ww + 3, yy + self._linespace,
                        fill=cfill, outline=""))
                    self._item_ids.append(self.create_text(
                        x + 1, yy, anchor="nw", text=w, font=rfont, fill=color))
                    x += ww + 3 + sp
                    continue
                if kind == runs.DISGUISE:                        # R70E：伪装风格表头（等宽 + 风格配色）
                    if row.disguise == "code":
                        dcolor = "#8fd3a8"       # 终端绿
                    elif row.disguise == "log":
                        dcolor = "#5b6b7c"       # 日志灰蓝
                    else:
                        dcolor = "#3c4a3f"       # 表格墨绿
                    self._item_ids.append(self.create_text(
                        x, yy, anchor="nw", text=w, font=rfont, fill=dcolor))
                    x += self._meas_kind(w, kind) + sp
                    continue
                if kind == rich.SPOILER:                         # R70A：剧透遮盖药丸
                    ww = self._meas_kind(w, kind)                # 遮盖宽=真实文本宽（换行不漂移）
                    try:
                        run_i = int(href or 0)
                    except (TypeError, ValueError):
                        run_i = 0
                    if (id(row), run_i) in self._spoiler_open:   # 已揭示 → 正常绘制
                        self._item_ids.append(self.create_text(
                            x, yy, anchor="nw", text=w, font=rfont, fill=color))
                    else:
                        tag = f"r70sp{len(self._item_ids)}"
                        self._item_ids.append(self.create_rectangle(
                            x, yy, x + ww, yy + self._linespace,
                            fill=self._pal.get("spoiler_bg", "#c9c3ba"),
                            outline="", tags=(tag,)))
                        mask = ("▮▮▮" if self._meas("▮▮▮") + 4 <= ww
                                else "▮")
                        if self._meas(mask) + 3 <= ww:
                            self._item_ids.append(self.create_text(
                                x + ww / 2, yy + self._linespace / 2,
                                anchor="center", text=mask, font=rfont,
                                fill=self._pal.get("spoiler_fg", "#f7f4ef"),
                                tags=(tag,)))
                        self.tag_bind(tag, "<Enter>",
                                      lambda e: self.configure(cursor="hand2"))
                        self.tag_bind(tag, "<Leave>",
                                      lambda e: self.configure(cursor=""))
                        self.tag_bind(tag, "<Button-1>",
                                      lambda _e, rw=row, ri=run_i:
                                      self._toggle_spoiler(rw, ri))
                    x += ww + sp
                    continue
                if kind == runs.LINK:
                    fill = self._pal.get("link_self" if own else "link") or self._pal["link"]
                    tag = f"r11lnk{len(self._item_ids)}"
                    item = self.create_text(x, yy, anchor="nw", text=w,
                                            font=rfont, fill=fill)
                    self.addtag_withtag(tag, item)
                    self.tag_bind(tag, "<Enter>",
                                  lambda e: self.configure(cursor="hand2"))
                    self.tag_bind(tag, "<Leave>",
                                  lambda e: self.configure(cursor=""))
                    self.tag_bind(tag, "<Button-1>",
                                  lambda _e, u=(href or w): self._on_link and
                                  self._on_link(runs.normalize_url(u)))
                    ww = self._meas_kind(w, kind)
                    self._item_ids.append(item)
                    try:
                        _, ty, _b, by = self.bbox(item)
                        self._item_ids.append(
                            self.create_line(x, by - 1, x + ww, by - 1,
                                             fill=fill))
                    except Exception:
                        pass
                elif kind == runs.MENTION:
                    mfill = self._pal.get("mention_self" if own else "mention") or self._pal["mention"]
                    item = self._text(x, yy, text=w, anchor="nw",
                                      font=rfont,
                                      fill=mfill)
                    if self._on_mention:                    # R29C：@昵称 可点跳私聊
                        tag = f"r29m{len(self._item_ids)}"
                        self.addtag_withtag(tag, item)
                        self.tag_bind(tag, "<Enter>",
                                      lambda e: self.configure(cursor="hand2"))
                        self.tag_bind(tag, "<Leave>",
                                      lambda e: self.configure(cursor=""))
                        self.tag_bind(tag, "<Button-1>",
                                      lambda _e, nick=w: self._on_mention and
                                      self._on_mention(nick))
                    ww = self._meas_kind(w, kind)
                elif kind == runs.HASHTAG:          # R30E：#话题 → 点击全局搜索
                    hfill = self._pal.get("link_self" if own else "link") or self._pal["link"]
                    item = self._text(x, yy, text=w, anchor="nw",
                                      font=rfont, fill=hfill)
                    if self._on_hashtag:
                        htag = f"r30h{len(self._item_ids)}"
                        self.addtag_withtag(htag, item)
                        self.tag_bind(htag, "<Enter>",
                                      lambda e: self.configure(cursor="hand2"))
                        self.tag_bind(htag, "<Leave>",
                                      lambda e: self.configure(cursor=""))
                        self.tag_bind(htag, "<Button-1>",
                                      lambda _e, word=w: self._on_hashtag and
                                      self._on_hashtag(word))
                    ww = self._meas_kind(w, kind)
                elif kind == runs.SENT_MARK:         # R-：私聊未读单勾（已发/未读，不互动）
                    self._text(x, yy, text=w, anchor="nw",
                               font=rfont, fill=self._pal["read"])
                    ww = self._meas_kind(w, kind)
                elif kind == runs.PENDING:           # P0 三态：发送中标记（灰，不互动）
                    self._text(x, yy, text=w, anchor="nw",
                               font=rfont, fill=self._pal["pending"])
                    ww = self._meas_kind(w, kind)
                elif kind == runs.READ_MARK:        # R33③：✓已读 独立段 → hover 弹已读详情
                    item = self._text(x, yy, text=w, anchor="nw",
                                      font=rfont, fill=self._pal["read"])
                    if self._on_read_detail:
                        rtag = f"r33rd{len(self._item_ids)}"
                        self.addtag_withtag(rtag, item)
                        self.tag_bind(rtag, "<Enter>",
                                      lambda e, rw=row: (
                                          self.configure(cursor="hand2"),
                                          self._on_read_detail(rw, e)))
                        self.tag_bind(rtag, "<Leave>",
                                      lambda e: (
                                          self.configure(cursor=""),
                                          self._on_read_detail(None, None)))
                    ww = self._meas_kind(w, kind)
                elif kind == runs.REPLY:            # R41F：引用前缀段 → 点击跳转原消息
                    item = self._text(x, yy, text=w, anchor="nw", font=rfont,
                                      fill=self._pal.get("reply") or self._pal["link"])
                    if row.reply_seq is not None and self.on_jump_reply:
                        jtag = f"r41jp{len(self._item_ids)}"
                        self.addtag_withtag(jtag, item)
                        self.tag_bind(jtag, "<Enter>",
                                      lambda e: self.configure(cursor="hand2"))
                        self.tag_bind(jtag, "<Leave>",
                                      lambda e: self.configure(cursor=""))
                        self.tag_bind(jtag, "<Button-1>",
                                      lambda _e, seq=row.reply_seq:
                                      self.on_jump_reply(seq))
                    ww = self._meas_kind(w, kind)
                elif kind == runs.EDIT_MARK:        # R70B：✎已编辑 → 点开编辑历史
                    item = self._text(x, yy, text=w, anchor="nw", font=rfont,
                                      fill=self._pal.get("read") or self._pal["sys"])
                    if row.raw.get("edits"):
                        etag = f"r70ed{len(self._item_ids)}"
                        self.addtag_withtag(etag, item)
                        self.tag_bind(etag, "<Enter>",
                                      lambda e: self.configure(cursor="hand2"))
                        self.tag_bind(etag, "<Leave>",
                                      lambda e: self.configure(cursor=""))
                        self.tag_bind(etag, "<Button-1>",
                                      lambda _e, rw=row:
                                      self._on_edit_history and
                                      self._on_edit_history(rw))
                    ww = self._meas_kind(w, kind)
                else:
                    item = self._text(x, yy, text=w, anchor="nw",
                                      font=rfont, fill=color)
                    ww = self._meas_kind(w, kind)
                x += ww + sp
        h = bub_y + bub_h - y + self.PAD_TOP
        h = max(h, self._linespace + self.PAD_TOP)
        tb_h = self._badges_h(row)                # R34/R71：徽标+名片（气泡正下方）
        if tb_h:
            self._draw_badges(i, row, bub_y + bub_h, row_w, own)
        if self._reaction_height(row):            # R13：气泡下方画回应条
            self._draw_reaction_bar(row, bub_y + bub_h + tb_h, row_w, own)
            h += self.REACT_PAD
        kb_h = self._kb_height(row)               # R46：bot 键盘（回应条之下）
        if kb_h:
            self._draw_kb(i, row, bub_y + bub_h + tb_h
                          + (self.REACT_PAD if self._reaction_height(row) else 0))
            h += kb_h
        if self._on_react and i == self._hover_row:  # R27：hover 快速回应条（悬浮不占行高）
            self._draw_quick_bar(i, row, bub_x, bub_y, bub_w, own)
        if i == self._hover_row:               # R58C：hover 外侧操作条（回复/复制/删除）
            self._draw_hover_strip(i, row, bub_x, bub_y, bub_w, bub_h, own)
        if row.preview:                           # R26D：正文之下附链接预览卡片
            self._draw_preview_card(i, row,
                                    bub_y + bub_h + tb_h + self.PREVIEW_PAD,
                                    bub_x, bub_w)
            h += self.PREVIEW_PAD + self._preview_h()
        if own and row.raw.get("failed"):         # R31C：发送失败 → 气泡右侧红 ❗ 可点重发
            fx = bub_x + bub_w + 6
            fy = bub_y + bub_h / 2
            tag = f"r31f{i}"
            self._item_ids.append(self.create_oval(
                fx, fy - 9, fx + 18, fy + 9, fill="#e03e3e", outline="",
                tags=(tag,)))
            self._item_ids.append(self.create_text(
                fx + 9, fy, text="!", anchor="center",
                font=(self._font.actual("family"), 9, "bold"), fill="#ffffff",
                tags=(tag,)))
            self.tag_bind(tag, "<Enter>", lambda e: self.configure(cursor="hand2"))
            self.tag_bind(tag, "<Leave>", lambda e: self.configure(cursor=""))
            self.tag_bind(tag, "<Button-1>",
                          lambda _e, idx=i: self._on_failed and self._on_failed(idx))
        self._hit_back(i, y, h)
        return h + dy                        # dy：日期条/未读分隔条占位（R30A）

    # ---------- R46 bot inline 键盘 ----------
    def _kb_height(self, row) -> int:
        """bot 键盘占位高：行数 ×（按钮高 + 行距）。"""
        return len(row.kb) * (self.KB_BTN_H + self.KB_GAP) if row.kb else 0

    def _draw_kb(self, i, row, top) -> None:
        """bot 气泡下方画 inline 键盘（药丸按钮，点击=向 bot 发送指令文本）。"""
        uid = row.raw.get("uid")
        x0 = self.PAD_X + self.AVATAR + self.GUTTER   # 与他人气泡左缘对齐
        y = top
        for r, btns in enumerate(row.kb):
            x = x0
            for c, b in enumerate(btns):
                w = self._meas(b["t"]) + 2 * self.BUBBLE_PAD_H + 8
                tag = f"r46kb{i}_{r}_{c}"
                self._item_ids.append(self.create_rectangle(
                    x, y, x + w, y + self.KB_BTN_H, fill=self._pal["react_bg"],
                    outline=self._pal["bubble_inline"], tags=(tag,)))
                self._item_ids.append(self.create_text(
                    x + w / 2, y + self.KB_BTN_H / 2, text=b["t"],
                    anchor="center", font=self._font,
                    fill=self._pal.get("text") or self._pal["react_fg"]))
                self.tag_bind(tag, "<Enter>",
                              lambda e: self.configure(cursor="hand2"))
                self.tag_bind(tag, "<Leave>",
                              lambda e: self.configure(cursor=""))
                self.tag_bind(tag, "<Button-1>",
                              lambda _e, u=uid, cmd=b["c"]:
                              self._on_kb and self._on_kb(u, cmd))
                x += w + self.KB_GAP
            y += self.KB_BTN_H + self.KB_GAP

    # ---------- R26A 投票气泡 ----------
    def _meas_bold(self, s: str) -> int:
        """加粗字体测量（独立缓存键，与正文测量互不污染）。"""
        key = "b:" + s
        if key in self._meas_cache:
            w = self._meas_cache.pop(key)   # 命中移到队尾
        else:
            try:
                w = self._bold_font.measure(s)
            except Exception:
                w = self._meas(s)
        if len(self._meas_cache) >= self._MEAS_CACHE_MAX:
            self._meas_cache.pop(next(iter(self._meas_cache)))
        self._meas_cache[key] = w
        return w

    def _draw_poll(self, i: int, row: _Row, y: int, wrap_w: int,
                   in_group: bool) -> tuple:
        """R26A 投票气泡：加粗问题 + 可点选项（票数/占比进度条）+ 状态行。
        返回 (h, bub_x, bub_y, bub_w, bub_h) 供调用方在其下续画预览卡片。"""
        own = self._row_tag(row) == "self"
        color = self._pal.get("self" if own else "normal")
        ph, pv = self.BUBBLE_PAD_H, (self.GROUP_PAD_V if in_group else self.BUBBLE_PAD_V)
        row_w = self.winfo_width()
        if row_w <= 1:
            row_w = wrap_w
        inner = max(self.MIN_BUBBLE_W, int(row_w * self.CAP_RATIO))
        opline = inner - 2 * ph                      # 选项/问题可用宽
        q = str(row.poll.get("question") or "投票")
        try:
            qlines = runs.wrap_segments([(q, runs.PLAIN)], opline,
                                         lambda s, k: self._meas_bold(s))
        except Exception:
            qlines = [[(q, runs.PLAIN)]]
        opts = row.poll.get("options") or []
        poll = row.poll
        st = poll.get("state") if isinstance(poll.get("state"), dict) else None
        anon = bool(poll.get("anonymous"))       # R70C：匿名（不列投票人）
        multi = bool(poll.get("multi"))          # R70C：多选（可投多项）
        quiz = bool(poll.get("quiz"))            # R70C：测验（结束揭示答案）
        me = self._me_uid
        if st is not None:
            counts = [int(c) for c in (st.get("counts") or [])]
            if len(counts) < len(opts):
                counts += [0] * (len(opts) - len(counts))
            total = int(st.get("total") if st.get("total") is not None
                        else sum(counts))
            mine = ([int(x) for x in st["mine"]] if st.get("mine") is not None
                    else None)
            correct = st.get("correct")
            end_ts = float(st.get("end") or poll.get("end") or 0)
        else:
            votes = poll.get("votes") or {}
            counts = [0] * len(opts)
            by_uid = {}
            for u, v in votes.items():
                idxs = list(v) if isinstance(v, (list, tuple)) else [v]
                try:
                    by_uid[int(u)] = [int(x) for x in idxs]
                except (TypeError, ValueError):
                    continue
                for vi in by_uid[int(u)]:
                    if 0 <= vi < len(opts):
                        counts[vi] += 1
            total = sum(counts)
            mine = by_uid.get(me) if me is not None else None
            if mine is None and isinstance(poll.get("mine"), list):
                mine = [int(x) for x in poll["mine"]]   # 匿名历史里服务器只回本人 mine
            correct = poll.get("correct")
            end_ts = float(poll.get("end") or 0)
        mine = mine or []
        if not mine and me is not None and isinstance(poll.get("votes"), dict):
            # 非匿名广播只带 votes（无 mine）：按本人 uid 反查已投项
            for u, vv in poll["votes"].items():
                try:
                    if int(u) != int(me):
                        continue
                except (TypeError, ValueError):
                    continue
                mine = [int(x) for x in (vv if isinstance(vv, (list, tuple)) else [vv])]
                break
        ended = time.time() >= end_ts
        rows_ = []
        for oi, o in enumerate(opts):
            txt = str(o or "")[:32]                  # 展示截断（服务器已限 64 字）
            cnt = counts[oi]
            pct = round(cnt * 100 / total) if total else 0
            suffix = f"  {cnt}票 {pct}%" if total else ""
            mark = "  ✓ 已投" if oi in mine else ""
            if quiz and correct is not None:         # 结束揭示：标正确项/选错
                if oi == int(correct):
                    mark += "  ✅ 正确答案"
                elif oi in mine:
                    mark = "  ❌ 选错"
            rows_.append((txt, suffix, mark, oi, cnt, pct))
        qw = max((runs.line_width(ln, lambda s, k: self._meas_bold(s)) for ln in qlines), default=0)
        rw = max((self._meas(t) + self._meas(s) + self._meas(m)
                  for t, s, m, *_ in rows_), default=0)
        bub_w = min(max(qw, rw, self.MIN_BUBBLE_W) + 2 * ph, inner + 2 * ph)
        bub_h = (len(qlines) + len(rows_) + 1) * self._linespace + 2 * pv
        bub_y = y + self.PAD_TOP
        if own:
            bub_x = row_w - self.PAD_X - bub_w       # 右缘留 PAD_X
        else:
            if not in_group:                       # R12：组内行不再重复画头像（缩进保留）
                self._draw_msg_avatar(self.PAD_X, bub_y, row)
            bub_x = self.PAD_X + self.AVATAR + self.GUTTER
        self._item_ids.append(self._round_rect(
            bub_x, bub_y, bub_x + bub_w, bub_y + bub_h, self.BUBBLE_R,
            fill=self._bubble_fill(i, own),
            outline=self._pal["bubble_outline" if own else "bubble_inline"]))
        base_x, y0 = bub_x + ph, bub_y + pv
        yy = y0
        sp = self._meas(" ")
        for ln in qlines:                            # 加粗问题
            x = base_x
            for w, _kind in ln:
                item = self.create_text(x, yy, anchor="nw", text=w,
                                        font=self._bold_font, fill=color)
                self._item_ids.append(item)
                x += self._meas_bold(w) + sp
            yy += self._linespace
        for txt, suffix, mark, oi, cnt, pct in rows_:  # 选项行
            tag = f"r26poll{i}_{oi}"
            t_w = self._meas(txt)
            if cnt:                                  # 票数占比进度条（底衬）
                bar_w = int(opline * pct / 100) if pct else 0
                if bar_w > 0:
                    self._item_ids.append(self.create_rectangle(
                        base_x, yy + 1, base_x + bar_w, yy + self._linespace - 1,
                        fill="#e0ecfb", outline=""))
            self._text(base_x, yy, text=txt, anchor="nw",
                       font=self._font, fill=color)
            if suffix:
                self._text(base_x + t_w + sp, yy, text=suffix, anchor="nw",
                           font=self._font, fill=self._pal["sys"])
            if mark:
                self._text(base_x + t_w + self._meas(suffix) + 2 * sp, yy,
                           text=mark, anchor="nw", font=self._font,
                           fill=self._pal.get("link_self" if own else "link") or self._pal["link"])
            if not ended and self._on_poll_vote:     # 热区：未结束才可点投票
                hit = self.create_rectangle(base_x, yy,
                                            base_x + opline, yy + self._linespace,
                                            fill="", outline="", tags=(tag,))
                self._item_ids.append(hit)
                self.tag_bind(tag, "<Enter>",
                              lambda e: self.configure(cursor="hand2"))
                self.tag_bind(tag, "<Leave>",
                              lambda e: self.configure(cursor=""))
                self.tag_bind(tag, "<Button-1>",
                              lambda _e, oi=oi: self._on_poll_vote and
                              self._on_poll_vote(i, oi))
            yy += self._linespace
        if ended:                                    # 状态行
            status = f"已结束 · 共 {total} 票"
        else:
            left = max(0, int(end_ts - time.time()))
            if left >= 3600:
                status = f"剩余 {left // 3600} 小时"
            elif left >= 60:
                status = f"剩余 {left // 60} 分钟"
            else:
                status = f"剩余 {max(left, 1)} 秒"
            status += f" · 共 {total} 票"
        tags_ = []                                   # R70C：模式标记
        if anon:
            tags_.append("🕶 匿名")
        if multi:
            tags_.append("☑ 多选")
        if quiz:
            tags_.append("🎯 测验")
        if tags_:
            status = " · ".join(tags_) + " · " + status
        self._text(base_x, yy, text=status, anchor="nw",
                   font=self._font, fill=self._pal["sys"])
        h = bub_y + bub_h - y + self.PAD_TOP
        h = max(h, self._linespace + self.PAD_TOP)
        return h, bub_x, bub_y, bub_w, bub_h

    # ---------- R26D 链接预览卡片 ----------
    def _truncate(self, s: str, width: int) -> str:
        """按像素宽截断文本并追加 …（宽度测量走缓存）。"""
        s = str(s or "")
        if width <= 0 or self._meas(s) <= width:
            return s
        while s and self._meas(s + "…") > width:
            s = s[:-1]
        return s + "…"

    def _draw_preview_card(self, i: int, row: _Row, y: int, x0: int,
                           w: int) -> None:
        """R26D 链接预览卡片：域名 + 标题 + 描述（固定 3 行高，宽=气泡宽）。"""
        p = row.preview or {}
        card_w = max(w, self.MIN_BUBBLE_W)
        card_h = self._preview_h()
        self._item_ids.append(self._round_rect(
            x0, y, x0 + card_w, y + card_h, 6,
            fill=self._pal["bubble_in"], outline=self._pal["bubble_inline"]))
        cx = x0 + 8
        cy = y + 4
        inner = card_w - 16
        domain = str(p.get("domain") or "")
        title = str(p.get("title") or "链接预览")
        desc = str(p.get("desc") or "")
        if domain:
            self._text(cx, cy, text=self._truncate(domain, inner), anchor="nw",
                       font=self._react_font, fill=self._pal["link"])
            cy += self._linespace
        self._text(cx, cy, text=self._truncate(title, inner), anchor="nw",
                   font=self._font, fill=self._pal["normal"])
        cy += self._linespace
        if desc:
            self._text(cx, cy, text=self._truncate(desc, inner), anchor="nw",
                       font=self._react_font, fill=self._pal["sys"])

    # ---------- R19 语音播放气泡 ----------
    def _draw_voice(self, i: int, row: _Row, y: int, wrap_w: int,
                    in_group: bool) -> int:
        """语音消息渲染：▶ 播放按钮 + 时长 + 跑道。有 voice_path 可点播放，
        否则（历史重放/服务端 TTL 过期）灰显"已过期"。"""
        own = self._row_tag(row) == "self"
        color = self._pal.get("self" if own else "normal")
        ph, pv = self.BUBBLE_PAD_H, (self.GROUP_PAD_V if in_group else self.BUBBLE_PAD_V)
        row_w = self.winfo_width()
        if row_w <= 1:
            row_w = wrap_w
        dur = float(row.voice_dur or 0.0)
        playable = bool(row.voice_path)
        note = (row.voice_note or "")[:48] if playable else ""    # R38B 旁注
        can_tts = bool(playable and self._on_transcribe)   # R批次③：可转文字
        run_h = 6 if playable else 0                    # 跑道条高度（纯装饰）
        note_h = (self._linespace + 4) if (note or can_tts) else 0
        internal_h = self._linespace + 2 * pv + run_h + note_h
        # ▶ + 时长 文本宽度
        glyph = "▶ "
        dur_txt = f"{dur:g} 秒" if playable else "语音已过期"
        g_w = self._meas(glyph)
        d_w = self._meas(dur_txt)
        runway = 46 if playable else 0
        bub_w = max(self.MIN_BUBBLE_W, g_w + d_w + 2 * ph + runway)
        bub_y = y + self.PAD_TOP
        bub_h = internal_h
        if own:
            bub_x = row_w - self.PAD_X - bub_w          # 右缘留 PAD_X
        else:
            if not in_group:                       # R12：组内行不再重复画头像（缩进保留）
                self._draw_msg_avatar(self.PAD_X, bub_y, row)
            bub_x = self.PAD_X + self.AVATAR + self.GUTTER
        self._item_ids.append(self._round_rect(
            bub_x, bub_y, bub_x + bub_w, bub_y + bub_h, self.BUBBLE_R,
            fill=self._bubble_fill(i, own),
            outline=self._pal["bubble_outline" if own else "bubble_inline"]))
        base_x, y0 = bub_x + ph, bub_y + pv
        if not playable:
            self._text(base_x + g_w - self._meas(" "), y0, text="🚫",
                       anchor="nw", font=self._font, fill=self._pal["sys"])
            self._text(base_x + g_w - self._meas(" ") + self._meas("🚫"),
                       y0, text=dur_txt, anchor="nw", font=self._font,
                       fill=self._pal["sys"])
            h = bub_y + bub_h - y + self.PAD_TOP
            tb_h = self._badges_h(row)           # R34/R71：徽标+名片（语音气泡下方）
            if tb_h:
                self._draw_badges(i, row, bub_y + bub_h, row_w, own)
            if self._reaction_height(row):       # R33①：语音行气泡下方也画回应条
                self._draw_reaction_bar(row, bub_y + bub_h + tb_h, row_w, own)
                h += self.REACT_PAD
            if self._on_react and i == self._hover_row:   # R33①：语音行 hover 快速条
                self._draw_quick_bar(i, row, bub_x, bub_y, bub_w, own)
            self._hit_back(i, y, h)
            return h
        self._text(base_x, y0, text=glyph, anchor="nw",
                   font=self._font, fill=self._pal.get("link_self" if own else "link") or self._pal["link"])
        self._text(base_x + g_w, y0, text=dur_txt, anchor="nw",
                   font=self._font, fill=color)
        # 跑道条：空槽 + 起点游标（R68：播放中按进度填充实时推进）
        rw = g_w + d_w + runway
        ry = y0 + self._linespace + 2
        self._item_ids.append(self.create_rectangle(
            base_x, ry, base_x + rw, ry + 3,
            fill=self._pal["bubble_outline" if own else "bubble_inline"],
            outline=""))
        self._item_ids.append(self.create_oval(
            base_x - 1, ry - 1, base_x + 3, ry + 3, fill=color, outline=""))
        prog = self._voice_progress(i)
        if prog is not None:                          # R68：播放进度（0.0~1.0）
            fill_x = base_x + max(0.0, min(1.0, prog)) * rw
            self._item_ids.append(self.create_rectangle(
                base_x, ry, fill_x, ry + 3,
                fill=self._pal.get("link_self" if own else "link")
                or self._pal["link"], outline=""))
            self._item_ids.append(self.create_oval(
                fill_x - 3, ry - 3, fill_x + 3, ry + 3, fill=color, outline=""))
        if note:                                     # R38B：转写旁注（本地）
            self._text(base_x, ry + 8, text="📝 " + note, anchor="nw",
                       font=self._font, fill=self._pal.get("sys") or "#888")
        if can_tts:                                  # R批次③：气泡内「⇄转文字」chip
            lbl = "⇄重转" if note else "⇄转文字"
            tx = self._text(base_x + (self._meas("📝 " + note) if note else 0),
                            ry + 8, text="  " + lbl + "  ", anchor="nw",
                            font=self._react_font,
                            fill=self._pal.get("link_self" if own else "link")
                            or self._pal["link"])
            self._item_ids.append(tx)
            tag = f"r61tts{i}"
            self.itemconfig(tx, tags=(tag,))
            self.tag_bind(tag, "<Enter>", lambda e: self.configure(cursor="hand2"))
            self.tag_bind(tag, "<Leave>", lambda e: self.configure(cursor=""))
            self.tag_bind(
                tag, "<Button-1>", lambda _e, p=row.voice_path,
                k=i: self._on_transcribe and self._on_transcribe(k, p))
        # 热区：整条气泡可点播放（closure 捕获 i / path / rate，重绘即重建）
        tag = f"r19voice{i}"
        hit = self.create_rectangle(bub_x, bub_y, bub_x + bub_w, bub_y + bub_h,
                                    fill="", outline="", tags=(tag,))
        self._item_ids.append(hit)
        self.tag_bind(tag, "<Enter>", lambda e: self.configure(cursor="hand2"))
        self.tag_bind(tag, "<Leave>", lambda e: self.configure(cursor=""))
        self.tag_bind(tag, "<Button-1>",
                      lambda _e, p=row.voice_path, rv=self._voice_rate,
                      k=i, dd=row.voice_dur:
                      (self.voice_started(k, dd, rv),
                       self._on_voice and self._on_voice(k, p, rv)))
        # 功能③ 倍速档：气泡内右侧小「×N」chip，点击循环 1x→1.5x→2x→0.5x
        rate_lbl = f"×{self._voice_rate:g}"
        rtag = f"r61rate{i}"
        rcx = bub_x + bub_w - ph - self._meas(rate_lbl)
        rcy = y0 + self._linespace // 2
        self._item_ids.append(self.create_text(
            rcx, rcy + 4, text=rate_lbl, anchor="w",
            font=self._react_font, fill=self._pal.get("link_self" if own
            else "link") or self._pal["link"], tags=(rtag,)))
        self.tag_bind(rtag, "<Button-1>", lambda _e: self._cycle_voice_rate())
        self.tag_bind(rtag, "<Enter>", lambda e: self.configure(cursor="hand2"))
        self.tag_bind(rtag, "<Leave>", lambda e: self.configure(cursor=""))
        # 功能①：语音气泡同样支持被引用聚合徽标
        self._draw_quote_badge(i, row, bub_x, bub_y, bub_w, bub_h, own)
        h = bub_y + bub_h - y + self.PAD_TOP
        tb_h = self._thread_badge_h(row)         # R34：话题徽标（语音气泡下方）
        if tb_h:
            self._draw_thread_badge(i, row, bub_y + bub_h, row_w, own)
        if self._reaction_height(row):           # R33①：语音行气泡下方也画回应条
            self._draw_reaction_bar(row, bub_y + bub_h + tb_h, row_w, own)
            h += self.REACT_PAD
        if self._on_react and i == self._hover_row:   # R33①：语音行 hover 快速条
            self._draw_quick_bar(i, row, bub_x, bub_y, bub_w, own)
        self._hit_back(i, y, h)
        return h

    def _voice_progress(self, i: int) -> float | None:
        """R68：该行语音的播放进度 0.0~1.0；非当前播放行返回 None。"""
        vp = self._voice_playing
        if not vp or vp[0] != i:
            return None
        t0, dur = vp[1], vp[2]
        if dur <= 0:
            return None
        return max(0.0, min(1.0, (time.monotonic() - t0) / dur))

    def voice_started(self, idx: int, dur: float, rate: float = 1.0) -> None:
        """R68：播放开始 → 记录起点并按帧推进进度条（播完自停）。"""
        try:
            dur = float(dur)
        except (TypeError, ValueError):
            dur = 0.0
        rt = float(rate or 1.0) or 1.0
        eff = dur / rt if dur > 0 else 0.0    # 倍速下实际播放时长
        self._voice_playing = (int(idx), time.monotonic(), eff) if eff > 0 else None
        if self._voice_job is not None:
            try:
                self.after_cancel(self._voice_job)
            except Exception:
                pass
            self._voice_job = None
        if self._voice_playing is not None:
            self._voice_job = self.after(self.VOICE_TICK_MS, self._voice_tick)
            self._render()

    def _voice_tick(self) -> None:
        """R68：进度条推进帧；播完清状态并重绘一次复位。"""
        self._voice_job = None
        vp = self._voice_playing
        if not vp:
            return
        if time.monotonic() - vp[1] >= vp[2]:
            self._voice_playing = None
            self._render()
            # D14：进度条判定播完 → 通知 client（连播开关开启时自动播下一条）
            if self._on_voice_end:
                try:
                    self._on_voice_end(vp[0])
                except Exception:
                    pass
            return
        self._render()
        self._voice_job = self.after(self.VOICE_TICK_MS, self._voice_tick)

    def _cycle_voice_rate(self) -> None:
        """功能③：点击倍速 chip → 循环 1x→1.5x→2x→0.5x→1x，重绘生效。"""
        rates = list(_RIFF_SPEEDS)
        try:
            nxt = rates[(rates.index(self._voice_rate) + 1) % len(rates)]
        except ValueError:
            nxt = 1.0
        self._voice_rate = nxt
        self._render()

    def _hit_back(self, i: int, y: int, h: int) -> None:
        """搜索命中/引用跳转行高亮（垫在气泡/文字之下，不遮挡正文）。"""
        kind = self._hit_kind(i)
        if not kind and i == self._jump_hi:    # R41F：跳转目标行用活动命中色
            kind = "active"
        if not kind and i in self._quote_hi:   # 功能①：被引用聚合高亮引用它的行
            kind = "active"
        if not kind:
            return
        rw = self.winfo_width()
        if rw <= 1:
            rw = self._wrap_w or self.PAD_X * 2 + self.AVATAR + self.GUTTER + 200
        rw = max(rw, self.PAD_X + self.AVATAR + self.GUTTER + 200)
        rect = self.create_rectangle(
            self.PAD_X, y, self.PAD_X + rw, y + h,
            fill=self._pal["hit_active" if kind == "active" else "hit"],
            outline="")
        self.tag_lower(rect)          # 垫到气泡/文字之下
        self._item_ids.append(rect)

    def _round_rect(self, x0, y0, x1, y1, r, fill, outline):
        """Canvas polygon smooth 近似圆角矩形（tk 无原生圆角）。"""
        r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
        pts = [
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
            x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
            x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
        ]
        return self.create_polygon(pts, smooth=True, fill=fill,
                                   outline=outline, width=1)

    # ---------- R39D③ 合并转发卡片 ----------
    def _ellipsis(self, text: str, max_w: int) -> str:
        """按像素宽截断，超出加 …（预览行单行显示）。"""
        if max_w <= 0 or self._meas(text) <= max_w:
            return text
        out = text
        while out and self._meas(out + "…") > max_w:
            out = out[:-1]
        return out + "…"

    def _draw_fwd_pack(self, i: int, row: _Row, y: int, wrap_w: int,
                       in_group: bool) -> int:
        """R39D③ 合并转发卡：两层错位底卡 + 主卡（头行/预览/提示），双击展开。"""
        own = self._row_tag(row) == "self"
        color = self._pal.get("self" if own else "normal")
        ph, pv = self.BUBBLE_PAD_H, (self.GROUP_PAD_V if in_group else self.BUBBLE_PAD_V)
        row_w = self.winfo_width()
        if row_w <= 1:
            row_w = wrap_w
        inner = max(self.MIN_BUBBLE_W, int(row_w * self.CAP_RATIO))
        items = [it for it in (row.fwd_pack.get("items") or [])
                 if isinstance(it, dict)] or [{"nick": "?", "text": ""}]
        n = int(row.fwd_pack.get("n") or len(items))
        head_t = f"📚 合并转发 · {n} 条消息"
        prevs = [self._ellipsis(f"{it.get('nick', '?')}: {str(it.get('text') or '')}",
                                inner - 2 * ph - 8)
                 for it in items[:3]]
        w = max([self._meas(head_t)] + [self._meas(t) for t in prevs])
        bub_w = min(max(w + 2 * ph, self.MIN_BUBBLE_W), inner + 2 * ph)
        nlines = 2 + len(prevs)
        bub_h = nlines * self._linespace + 2 * pv
        bub_y = y + self.PAD_TOP
        if own:
            bub_x = row_w - self.PAD_X - bub_w
        else:
            if not in_group:                       # R12：组内行不再重复画头像（缩进保留）
                self._draw_msg_avatar(self.PAD_X, bub_y, row)
            bub_x = self.PAD_X + self.AVATAR + self.GUTTER
        outline = self._pal["bubble_outline" if own else "bubble_inline"]
        for dx in (4, 2):                    # 堆叠底卡（错位投影）
            self._item_ids.append(self._round_rect(
                bub_x + dx, bub_y + dx, bub_x + bub_w, bub_y + bub_h,
                self.BUBBLE_R, fill=outline, outline=""))
        self._item_ids.append(self._round_rect(
            bub_x, bub_y, bub_x + bub_w, bub_y + bub_h, self.BUBBLE_R,
            fill=self._bubble_fill(i, own), outline=outline))
        # B 仿毛玻璃：磨砂雾层（极淡白色 stipple，文字绘制在其上不受影响）
        self._item_ids.append(self.create_rectangle(
            bub_x, bub_y, bub_x + bub_w - 1, bub_y + bub_h - 1,
            fill="#ffffff", stipple="gray12", outline=""))
        base_x, yy = bub_x + ph, bub_y + pv
        self._text(base_x, yy, text=head_t, anchor="nw", font=self._bold_font,
                   fill=color)
        yy += self._linespace
        for t in prevs:
            self._text(base_x, yy, text=t, anchor="nw", font=self._font,
                       fill=self._pal["sys"])
            yy += self._linespace
        self._text(base_x, yy, text="双击查看", anchor="nw",
                   font=self._date_font, fill=self._pal["sys"])
        # B 仿毛玻璃：磨砂雾层（极淡白色 stipple，置于文字之后，覆盖气泡底不遮文字）
        self._item_ids.append(self.create_rectangle(
            bub_x, bub_y, bub_x + bub_w - 1, bub_y + bub_h - 1,
            fill="#ffffff", stipple="gray12", outline=""))
        self._hit_back(i, y, bub_h + self.PAD_TOP)
        return bub_h + self.PAD_TOP + 4

    def _row_tag(self, row: _Row):
        if row.tag == "sys":
            return "sys"
        uid = row.raw.get("uid")
        if self._me_uid is not None and uid is not None and uid == self._me_uid:
            return "self"
        if row.raw.get("channel") == "private":
            return "priv"
        return None

    def _delete_items(self) -> None:
        """清空当前可见 item。清掉已在内存登记的 id 绝不会抛异常，但防御包裹：
        万一某 id 已不存在（滑入动画并行操作），静默忽略、绝不中断渲染。"""
        try:
            if self._item_ids:
                self.delete(*self._item_ids)
        except Exception:
            pass
        finally:
            self._item_ids = []
            for path in list(self._gif_item):      # R61：旧 item 已销毁，解绑轮播源
                if path in self._gif_item:
                    self._gif_item[path] = None

    # ---------- A7 缩略图：子线程 Pillow 缩放 + 主线程 PhotoImage ----------
    # ---------- R30C 自定义贴纸渲染 ----------
    def _sticker_photo(self, path: str):
        """贴纸尺寸（STICKER_MAX）PhotoImage：主线程内从已解码 PIL 缩放缓存。"""
        ph = self._stk_photo.get(path)
        if ph is not None:
            return ph
        pil = self._img_pil.get(path)
        if not pil:                              # 未解码 / 解码失败
            return None
        try:
            from PIL import ImageTk
            im = pil.copy()
            im.thumbnail((STICKER_MAX, STICKER_MAX))
            ph = ImageTk.PhotoImage(im)
        except Exception:
            return None
        self._stk_photo[path] = ph
        return ph

    def _draw_sticker_item(self, row: _Row, x: int, y: int) -> int:
        """画自定义贴纸图：就绪→图片；未解码→占位块并排队解码；未缓存→短码文本
        并触发一次拉取（client 回调，去重防刷屏）。返回该贴纸占的高度。"""
        code = row.sticker_custom
        path = self._sticker_path(code) if self._sticker_path else None
        if not path:
            if self._sticker_fetch and code not in self._stk_req:
                self._stk_req.add(code)
                try:
                    self._sticker_fetch(code)
                except Exception:
                    pass
            item = self.create_text(x, y, anchor="nw", text=f"[:{code}:]",
                                    font=self._font, fill=self._pal["sys"])
            self._item_ids.append(item)
            return self._linespace
        if path.lower().endswith(".json"):     # R38C：lottie 动画贴纸
            return self._draw_lottie_sticker(code, path, x, y)
        photo = self._sticker_photo(path)
        if photo is not None:
            item = self.create_image(x, y, image=photo, anchor="nw")
            self._item_ids.append(item)
            if path in self._gif_frames and self._gif_frames.get(path):
                self._gif_item[path] = item          # R61：GIF 贴纸同样轮播
            return photo.height() + self.PAD_TOP
        if path not in self._img_pil:
            self._request_img(path)              # 排队解码，完成后 _img_tick 重绘
        self._item_ids.append(self.create_rectangle(
            x, y, x + STICKER_MAX, y + STICKER_MAX,
            fill="#ececec", outline="#cccccc"))
        self._item_ids.append(self.create_text(
            x + STICKER_MAX / 2, y + STICKER_MAX / 2, text=f":{code}:",
            fill="#888888", anchor="center", font=self._font))
        return STICKER_MAX + self.PAD_TOP

    def _draw_lottie_sticker(self, code: str, path: str, x: int, y: int) -> int:
        """R38C：lottie 动画贴纸——就绪画首帧并轮播；解码中/失败画占位块+🎞；
        缺 rlottie/Pillow 依赖则静态 glyph 行（同行高不跳版）。"""
        if not lottie_label.available():
            item = self.create_text(x, y, anchor="nw", text=f"🎞 [:{code}:]",
                                    font=self._font, fill=self._pal["sys"])
            self._item_ids.append(item)
            return self._linespace
        lf = lottie_label.load_async(path, STICKER_MAX, self,
                                     lambda _lf: self._render())
        if lf is not None and lf.ready:
            item = self.create_image(x, y, image=lf.photos[0], anchor="nw")
            self._item_ids.append(item)
            lottie_label.attach(self, item, lf)
            return lf.photos[0].height() + self.PAD_TOP
        # 解码中（等待回调重绘）/ 解码失败：占位块 + 🎞（高度稳定不跳版）
        self._item_ids.append(self.create_rectangle(
            x, y, x + STICKER_MAX, y + STICKER_MAX,
            fill="#ececec", outline="#cccccc"))
        self._item_ids.append(self.create_text(
            x + STICKER_MAX / 2, y + STICKER_MAX / 2,
            text=lottie_label.GLYPH, fill="#888888", anchor="center",
            font=self._font))
        return STICKER_MAX + self.PAD_TOP

    def _draw_msg_avatar(self, x: int, y: int, row: _Row) -> None:
        """R69C10：画消息头像并把点击绑到资料卡回调（uid 缺失时仅画不绑）。

        统一入口，避免 6 处头像绘制各写一遍 tag_bind；`_item_ids` 照常登记，
        保证换会话时随画布一起清空。
        """
        uid = row.raw.get("uid")
        ids = self._avatars.draw(self, x, y, self.AVATAR, row.nick,
                                 uid=uid, font=self._avatar_font)
        if self._on_profile and uid is not None:
            tag = f"r69c10_{len(self._item_ids)}"
            for it in ids:
                self.addtag_withtag(tag, it)
            self.tag_bind(tag, "<Enter>",
                          lambda e: self.configure(cursor="hand2"))
            self.tag_bind(tag, "<Leave>", lambda e: self.configure(cursor=""))
            self.tag_bind(tag, "<Button-1>",
                          lambda _e, u=uid: self._on_profile and
                          self._on_profile(u))
        self._item_ids.extend(ids)

    def _draw_custom_sticker(self, i: int, row: _Row, y: int, wrap_w: int) -> int:
        """R30C 贴纸行：头部（头像+时间昵称）+ 贴纸图，与图片行同构（尺寸更小）。"""
        color = self._pal.get(self._row_tag(row) or "normal")
        ax = self.PAD_X
        ay = y + self.PAD_TOP
        self._draw_msg_avatar(ax, ay, row)
        tx = ax + self.AVATAR + self.GUTTER
        item = self.create_text(tx, ay, anchor="nw",
                                text=f"{row.ts} {row.nick}:",
                                font=self._font, fill=color)
        self._item_ids.append(item)
        sy = ay + self._linespace + self.PAD_TOP
        sh = self._draw_sticker_item(row, tx, sy)
        h = (sy + sh) - y + self.PAD_TOP
        h = max(h, self._linespace + self.PAD_TOP, self.AVATAR + self.PAD_TOP)
        tb_h = self._thread_badge_h(row)         # R34：话题徽标（贴纸下方）
        if tb_h:
            self._draw_thread_badge(i, row, sy + sh, wrap_w,
                                    self._row_tag(row) == "self")
        if self._reaction_height(row):       # R33①：贴纸行也画回应条
            self._draw_reaction_bar(row, sy + sh + tb_h, wrap_w, self._row_tag(row) == "self")
            h += self.REACT_PAD
        if self._on_react and i == self._hover_row:   # R33①：贴纸行 hover 快速条
            self._draw_quick_bar(i, row, tx, ay, STICKER_MAX, self._row_tag(row) == "self")
        self._hit_back(i, y, h)
        return h

    def _draw_album(self, i: int, row: _Row, y: int, wrap_w: int) -> int:
        """R31B2 相册锚点行：头像 + 昵称/时间 + 图片网格（单图沿用原缩略图）。"""
        members = self._album_rows(i)
        ax = self.PAD_X
        ay = y + self.PAD_TOP
        self._draw_msg_avatar(ax, ay, row)
        tx = ax + self.AVATAR + self.GUTTER
        color = self._pal.get(self._row_tag(row) or "normal")
        item = self.create_text(tx, ay, anchor="nw",
                                text=f"{row.ts} {row.nick}:",
                                font=self._font, fill=color)
        self._item_ids.append(item)
        iy = ay + self._linespace + self.PAD_TOP
        if len(members) <= 1:
            img_h = self._draw_image_item(i, row, tx, iy, wrap_w)
        else:
            img_h = self._draw_album_grid(members, tx, iy)
        h = (iy + img_h) - y + self.PAD_TOP
        cap_extra = 0
        bar_y = iy + img_h
        if row.caption:                      # R32B3：图下 caption（折行同 _cap_h，估算≈实测）
            inner = max(self.MIN_BUBBLE_W, int(wrap_w * self.CAP_RATIO))
            try:
                lines = runs.wrap_segments([(row.caption, runs.PLAIN)],
                                           inner, lambda s, k: self._meas(s))
            except Exception:
                lines = [[(row.caption, runs.PLAIN)]]
            cy = iy + img_h
            fill = self._pal.get("normal") or "#333333"
            for ln in lines:
                item = self.create_text(tx, cy, anchor="nw",
                                        text="".join(w for w, _ in ln),
                                        font=self._font, fill=fill)
                self._item_ids.append(item)
                cy += self._linespace
            cap_extra = len(lines) * self._linespace + self.PAD_TOP
            h += cap_extra
            bar_y = iy + img_h + cap_extra
        h = max(h, self._linespace + self.PAD_TOP, self.AVATAR + self.PAD_TOP)
        tb_h = self._thread_badge_h(row)         # R34：话题徽标（图/说明下方）
        if tb_h:
            self._draw_thread_badge(i, row, bar_y, wrap_w,
                                    self._row_tag(row) == "self")
        if self._reaction_height(row):       # R33①：相册行图/说明下方也画回应条
            self._draw_reaction_bar(row, bar_y + tb_h, wrap_w, self._row_tag(row) == "self")
            h += self.REACT_PAD
        if self._on_react and i == self._hover_row:   # R33①：相册行 hover 快速条
            if len(members) <= 1:
                alb_w = min(IMG_MAX_W, max(40, wrap_w))
            else:
                cw, _ch = self._album_cell()
                alb_w = ALBUM_COLS * cw + (ALBUM_COLS - 1) * ALBUM_GAP
            self._draw_quick_bar(i, row, tx, ay, alb_w, self._row_tag(row) == "self")
        self._hit_back(i, y, h)
        return h

    def _draw_album_grid(self, members: list, x: int, y: int) -> int:
        """相册网格：固定单元格（真图裁切适配 / 灰块占位），点击热区开对应大图。"""
        cw, ch = self._album_cell()
        gap = ALBUM_GAP
        for k, ri in enumerate(members):
            r, c = divmod(k, ALBUM_COLS)
            cx = x + c * (cw + gap)
            cy = y + r * (ch + gap)
            path = self._rows[ri].image_path
            tag = f"imgrow{ri}"
            if self._on_row_image:
                self.tag_bind(tag, "<Button-1>",
                              lambda _e, idx=ri, p=path: self._on_row_image(idx, p))
            photo = self._cell_photo(path, cw, ch)
            if photo is not None:
                self._item_ids.append(self.create_image(
                    cx, cy, image=photo, anchor="nw", tags=(tag,)))
            else:
                if path not in self._img_pil:
                    self._request_img(path)    # 未解码 → 排队子线程
                self._item_ids.append(self.create_rectangle(
                    cx, cy, cx + cw, cy + ch, fill="#ececec",
                    outline="#cccccc", tags=(tag,)))
                self._item_ids.append(self.create_text(
                    cx + cw / 2, cy + ch / 2, text="[图片]",
                    fill="#888888", anchor="center", tags=(tag,)))
        return self._album_grid_h(len(members))

    def _cell_photo(self, path: str, cw: int, ch: int):
        """相册单元格 PhotoImage：主线程从已解码 PIL 裁切适配（缓存防重复开销）。"""
        photo = self._img_cell_photo.get(path)
        if photo is not None:
            return photo
        pil = self._img_pil.get(path)
        if not pil:                              # None=未解码 / False=解码失败
            return None
        try:
            from PIL import ImageOps, ImageTk
            photo = ImageTk.PhotoImage(ImageOps.fit(pil.convert("RGB"), (cw, ch)))
            self._img_cell_photo[path] = photo
            return photo
        except Exception:
            return None

    def _draw_image_item(self, idx: int, row: _Row, x: int, y: int,
                         wrap_w: int) -> int:
        """绘制图片行的缩略图（就绪=真图，否则灰块占位后请求后台解码）。"""
        path = row.image_path
        pw = min(IMG_MAX_W, max(40, wrap_w))
        tag = f"imgrow{idx}"                     # 点击热区：真图或占位都可点开
        if self._on_row_image:
            self.tag_bind(tag, "<Button-1>",
                          lambda e, i=idx, p=path: self._on_row_image(i, p))
        photo = self._img_photo.get(path)
        if photo is not None:
            item = self.create_image(x, y, image=photo, anchor="nw", tags=(tag,))
            self._item_ids.append(item)
            if path in self._gif_frames and self._gif_frames.get(path):
                self._gif_item[path] = item          # R61：登记为轮播源
            return photo.height() + self.PAD_TOP
        if path not in self._img_pil:
            self._request_img(path)               # 未解码 → 排队子线程
        ph = IMG_MAX_H
        rect = self.create_rectangle(x, y, x + pw, y + ph,
                                     fill="#ececec", outline="#cccccc",
                                     tags=(tag,))
        self.create_text(x + pw / 2, y + ph / 2,
                         text=f"[图片] {os.path.basename(path)}",
                         fill="#888888", anchor="center")
        self._item_ids.append(rect)
        return ph + self.PAD_TOP

    def image_rows(self) -> list:
        """全部图片行的 [(行下标, 本地路径)] 快照（供图片查看器前后翻页）。"""
        return [(i, r.image_path) for i, r in enumerate(self._rows)
                if r.image_path]

    def _request_img(self, path) -> None:
        if not path or path in self._img_pil or path in self._img_pending:
            return
        self._img_pending.add(path)
        self._img_inflight += 1
        self._img_queue.put(path)
        if self._img_thread is None:
            self._img_thread = threading.Thread(target=self._img_worker,
                                                daemon=True, name="img-thumb")
            self._img_thread.start()
        self._img_kick()

    def _img_kick(self) -> None:
        """有解码任务时启动轮询；已在排程中则什么也不做（幂等）。"""
        if self._img_job is None:
            self._img_job = self.after(60, self._img_tick)

    IMG_CACHE_MAX = 512                  # 缩略图缓存 LRU 上限：防长会话图片驻留内存无界
    def _trim_img_cache(self) -> None:
        while len(self._img_pil) > self.IMG_CACHE_MAX:
            self._img_pil.pop(next(iter(self._img_pil)))     # 淘汰最旧
        while len(self._img_photo) > self.IMG_CACHE_MAX:
            self._img_photo.pop(next(iter(self._img_photo)))
        # R61：GIF 帧缓存同步限幅淘汰（懒淘汰，不影响进行中轮播）
        if len(self._gif_frames) > self.IMG_CACHE_MAX:
            for k in list(self._gif_frames)[:len(self._gif_frames) - self.IMG_CACHE_MAX]:
                self._gif_frames.pop(k, None)
                self._gif_photo.pop(k, None)
                self._gif_item.pop(k, None)
                self._gif_idx.pop(k, None)

    def _img_worker(self) -> None:
        import io as _io
        from PIL import Image, ImageSequence
        while True:
            path = self._img_queue.get()          # 阻塞取任务（daemon，随进程退出）
            if path is None:
                break
            self._img_pending.discard(path)
            try:
                im = Image.open(path)
                im.load()
                # R61 GIF 校验帧数 + 抽帧（上限防超大内存），静态图回退单帧
                if getattr(im, "is_animated", False) and im.n_frames > 1:
                    frames = []
                    try:
                        for fr in ImageSequence.Iterator(im):
                            fr.load()
                            if len(frames) >= self.GIF_MAX_FRAMES:
                                frames.append(frames[-1])  # 末帧续帧，保证循环连续
                                break
                            if hasattr(fr, "thumbnail"):
                                fr.thumbnail((IMG_MAX_W, IMG_MAX_H))
                            frames.append(fr.copy())
                    except Exception:
                        frames = []
                    if frames:
                        self._gif_frames[path] = frames
                        self._img_pil[path] = frames[0].convert("RGB")
                        self._gif_photo.pop(path, None)
                        self._gif_item.pop(path, None)
                        self._gif_idx[path] = 0
                        self._img_ready.append(path)
                        self._img_inflight -= 1
                        self._trim_img_cache()
                        continue
                im.thumbnail((IMG_MAX_W, IMG_MAX_H))   # 保持宽高比缩到上限内
                self._img_pil[path] = im.convert("RGB")
            except Exception:
                self._img_pil[path] = False            # 解码失败：此后恒用占位
            self._img_ready.append(path)               # 先入队再减计数，避免 poll 抢跑
            self._img_inflight -= 1
            self._trim_img_cache()

    def _img_tick(self) -> None:
        """轮询解码完成队列；排空且无在途解码时自停（空闲不占 5.5Hz 唤醒）。"""
        self._img_job = None
        need = False
        while self._img_ready:
            path = self._img_ready.popleft()
            pil = self._img_pil.get(path)
            if not pil:                               # None/False 跳过
                continue
            try:
                from PIL import ImageTk
                self._img_photo[path] = ImageTk.PhotoImage(pil)
                need = True
            except Exception:
                pass
        self._trim_img_cache()
        if need and self._rows:
            self._cum_dirty = True
            self._img_tick_anim()             # R61：就绪的 GIF 行启动帧轮播
            self._render()                            # 真图就绪 → 该行重排重绘
        if self._img_ready or self._img_inflight > 0:
            self._img_job = self.after(180, self._img_tick)

    # ---------- R61 应用层 GIF 分帧轮播 ----------
    GIF_FRAME_MS = 80          # 帧切换间隔（ms，GIF 原速不可得时用固定节奏）
    VOICE_TICK_MS = 100        # R68：语音进度条推进帧间隔（ms）
    GIF_MAX_FRAMES = 48         # 单格抽取帧上限（防超大 GIf 撑爆内存）
    _gif_job = None

    def _gif_photos(self, path: str):
        """惰性生成并缓存某 GIF 的全部帧 PhotoImage（主线程）。未就绪返回空列表。"""
        cached = self._gif_photo.get(path)
        if cached:
            return cached
        frames = self._gif_frames.get(path)
        if not frames:
            return []
        try:
            from PIL import ImageTk
            phs = [ImageTk.PhotoImage(f) for f in frames]
        except Exception:
            return []
        self._gif_photo[path] = phs
        return phs

    def _img_tick_anim(self) -> None:
        """扫描已就绪 GIF：为该 path 展示中的 canvas item 绑定首帧并启动推进。"""
        for path in list(self._gif_frames):
            item = self._gif_item.get(path)
            if item is None:
                continue
            phs = self._gif_photos(path)
            if not phs:
                continue
            try:
                self.itemconfig(item, image=phs[0])
            except Exception:
                continue
            if self._gif_job is None:
                self._gif_job = self.after(self.GIF_FRAME_MS, self._gif_loop)

    def _gif_loop(self) -> None:
        """推进全部可见 GIF 一帧；没有活跃行则自停，避免空转耗电。"""
        self._gif_job = None
        active = False
        for path in list(self._gif_item):
            item = self._gif_item.get(path)
            phs = self._gif_photos(path)
            if item is None or not phs:
                continue
            idx = (self._gif_idx.get(path, 0) + 1) % len(phs)
            self._gif_idx[path] = idx
            try:
                self.itemconfig(item, image=phs[idx])
            except Exception:
                continue
            active = True
        if active:
            self._gif_job = self.after(self.GIF_FRAME_MS, self._gif_loop)

    # ---------- 滚动（R39D② 伪惯性：滚轮推目标位，插值帧逼近） ----------
    SMOOTH_FRAC = 0.10        # 每格滚轮的目标位移（≈视口高 1/10，与旧 unit 手感一致）
    SMOOTH_EASE = 0.38        # 每帧向目标逼近比例（越大越「硬」）
    SMOOTH_MS = 16            # 帧间隔（~60fps）
    SMOOTH_MAX_FRAMES = 8     # 帧数上限（顶/底钳制时兜底退出）

    def _wheel(self, delta: int) -> None:
        # R43C：滚轮/触控板统一走 _scroll_to 的平滑+惯性通道
        self._scroll_to(delta)

    def _scroll_to(self, delta: int) -> None:
        """滚轮/触控板统一平滑滚动入口：累计动量并由 _smooth_tick 衰减滑行。
        delta>0 上滚（看更早消息）、<0 下滚；目标位就地 clamp（顶/底不过头）。
        R43C：既保留逐格缓动逼近，又叠加滚停后的小幅惯性衰减。"""
        try:
            self._set_hover(None)                  # R27：滚动即隐藏悬浮回应条
            n = min(3, max(-3, int(delta / 120)))  # 单脉冲钳制，防触控板大跳
            if n:
                self._momentum = min(0.30, self._momentum + n * self.SMOOTH_FRAC)
            top = self.yview()[0]
            self._scroll_target = min(1.0, max(0.0, top - n * self.SMOOTH_FRAC))
            if self._smooth_job is None:
                self._smooth_frames = 0
                self._smooth_job = self.after(self.SMOOTH_MS, self._smooth_tick)
            else:
                self._smooth_frames = 0            # 连续滚动重置帧预算，长距离不提前停
            self._render()
        except Exception:
            pass

    def _smooth_tick(self) -> None:
        self._smooth_job = None
        if self._scroll_target is not None:
            top = self.yview()[0]
            diff = self._scroll_target - top
            self._smooth_frames += 1
            if abs(diff) < 0.001 or self._smooth_frames >= self.SMOOTH_MAX_FRAMES:
                self.yview_moveto(self._scroll_target)   # 收敛/边界钳制：贴齐目标
                self._scroll_target = None
            else:
                self.yview_moveto(top + diff * self.SMOOTH_EASE)
                self._smooth_job = self.after(self.SMOOTH_MS, self._smooth_tick)
        # R43C：惯性——目标到位后，剩余动量按阻尼衰减小幅滑行；顶/底就地停
        if self._scroll_target is None:
            if self._momentum:
                self._momentum *= 0.82
                if abs(self._momentum) < 0.004:
                    self._momentum = 0.0
                else:
                    nb = min(1.0, max(0.0, self.yview()[0] - self._momentum))
                    self.yview_moveto(nb)
                    self._smooth_job = self.after(self.SMOOTH_MS, self._smooth_tick)
        self._set_stick_from_view()
        self._maybe_load_top()                 # R39C：到顶续读更旧一页
        self._render()

    def _cancel_smooth(self) -> None:
        """程序性滚动（钉底/翻页/切会话/拖滚动条）取消在途惯性动画。"""
        if self._smooth_job is not None:
            try:
                self.after_cancel(self._smooth_job)
            except Exception:
                pass
            self._smooth_job = None
        self._scroll_target = None
        self._momentum = 0.0                   # R43C：打断惯性滑行

    def _scroll_cmd(self, *args) -> None:
        self._set_hover(None)                  # R27：拖滚动条同样隐藏
        self._cancel_smooth()                  # R39D②：直接拖动不经过惯性
        self.yview(*args)
        self._set_stick_from_view()
        self._maybe_load_top()                 # R39C：到顶续读更旧一页
        self._render()

    # ---------- R39D② 新消息气泡淡入（Tk 无逐像素 alpha，用 2~3 步颜色渐混模拟） ----------
    FADE_MS = 120                              # 总时长（theme.anim.fast 量级）
    FADE_STEP_MS = 40                          # 帧间隔 → 3 帧渐变

    # ---------- R43C 新消息气泡滑入（y +SLIDE_DY → 0，ease_out 缓动） ----------
    SLIDE_MS = 120                             # 总时长
    SLIDE_STEP_MS = 16                         # 帧间隔 → ~7~8 帧
    SLIDE_DY = 12                              # 起始下移量（px）

    def _advance_slide(self) -> None:
        """渲染帧后：对刚绘制的滑入行 item 施加当前偏移并调度下一帧。
        滑入行不可见/无 item → 静默停止（重绘即回基线）。全流程 try 包裹。"""
        try:
            if not (self._slide_started and self._slide_row >= 0):
                return
            if self._slide_begin is None:              # 惰性起算：首个渲染帧从满偏移开始
                self._slide_begin = time.time()
            t = (time.time() - self._slide_begin) * 1000.0 / self.SLIDE_MS
            if t >= 1.0:
                self._finish_slide()                   # 归零完成，坐标恢复基线
                return
            if self._slide_mark < 0:
                return                                  # 该行本轮未绘制（已滚出）→ 不推进
            self._slide_items = self._item_ids[self._slide_mark:]
            if not self._slide_items:
                return                                  # 无可见 item（0 高相册成员）→ 静默停
            self._slide_off = self.SLIDE_DY * (1 - ease_out(min(1.0, t)))
            self.move(*self._slide_items, 0, self._slide_off)   # 逐帧重设垂直位移
            if self._slide_job is None:
                self._slide_job = self.after(self.SLIDE_STEP_MS, self._render)
        except Exception:
            self._finish_slide()

    def _finish_slide(self) -> None:
        """滑入收尾：等同 _clear_slide，但语义上动画已自然结束。"""
        self._clear_slide()

    def _clear_slide(self) -> None:
        """复位滑入状态（重绘打断 / 动画结束 / 会话清空时调用，静默回基线）。"""
        self._slide_job = None
        self._slide_items = None
        self._slide_mark = -1
        self._slide_row = -1
        self._slide_started = False
        self._slide_begin = None
        self._slide_off = 0.0

    def set_fade_enabled(self, on: bool) -> None:
        """R39D②：开/关新消息 own 气泡淡入（prefs 持久化；默认关）。"""
        self._fade_enabled = bool(on)
        if not on:
            self._fading.clear()

    def _start_fade(self) -> None:
        if self._fade_job is None:
            self._fade_job = self.after(self.FADE_STEP_MS, self._fade_tick)

    def _fade_tick(self) -> None:
        self._fade_job = None
        if self._fading:
            self._fade_job = self.after(self.FADE_STEP_MS, self._fade_tick)
        self._render()                         # 渐变色随进度重绘可见行

    def _bubble_fill(self, i: int, own: bool) -> str:
        """行 i 气泡填充色：own 且在淡入期 → 背景色向气泡色按进度渐混，否则纯色。
        非本人收到的 @全体/@全员 群广播消息 → 用醒目 high 色区别普通消息。"""
        base = self._pal["bubble_out" if own else "bubble_in"]
        try:
            raw = self._rows[i].raw
            if not own and isinstance(raw, dict) and raw.get("everyone"):
                base = self._pal.get("everyone") or base
        except Exception:
            pass
        if own and i in self._fading:
            t = min(1.0, (time.time() - self._fading[i]) * 1000.0 / self.FADE_MS)
            if t < 1.0:
                return _hex_mix(self._pal["bg"], base, max(0.25, t))
        return base

    def _set_stick_from_view(self) -> None:
        """用户滚动后：到底则恢复钉底（region 渲染中定稿），离开底部则解除。
        R30A：滚到底 = 已读全部 → 自动撤未读分隔线。
        R31A：同步浮动「⬇ N」按钮显隐。"""
        at_bottom = self.yview()[1] >= 0.999
        self._stick_bottom = at_bottom
        if at_bottom and self._unread_seq is not None:
            self.set_unread_seq(None)
        self._update_jump_btn()

    # ---------- R31A jump-to-bottom 浮动按钮 ----------
    def _update_jump_btn(self) -> None:
        """不在底部 → 显示「⬇ N」；到底 → 收起并清零离底计数。"""
        if not getattr(self, "_jump_btn", None):
            return
        if self.yview()[1] >= 0.999:
            self._jump_new = 0
            if self._jump_btn.winfo_manager():
                self._jump_btn.place_forget()
            return
        n = self._unread_count() or self._jump_new
        label = f"⬇ {n}" if n > 0 else "⬇"
        if str(self._jump_btn.cget("text")) != label:
            self._jump_btn.config(text=label)
        if not self._jump_btn.winfo_manager():
            self._jump_btn.place(relx=1.0, rely=1.0, x=-20, y=-20,
                                 anchor="se")
        self._jump_btn.lift()

    def _unread_count(self) -> int:
        """未读分隔线之下的消息条数（无分隔线 = 0）。"""
        seq = self._unread_seq
        if seq is None:
            return 0
        n = 0
        for r in self._rows:
            s = r.raw.get("seq")
            if s is not None and s > seq:
                n += 1
        return n

    def _jump_bottom(self) -> None:
        """点击浮动按钮：滚到最新、恢复钉底、清零计数（到底=已读，撤未读线）。"""
        self._jump_new = 0
        self._stick_bottom = True         # _render 定稿 region 后重新钉底（勿用
        self._set_scrollregion()          #  _set_stick_from_view：估算高会误判离底）
        self.yview_moveto(1.0)
        self._render()
        if self._unread_seq is not None:
            self.set_unread_seq(None)     # 到底=已读，撤未读分隔线

    def _on_configure(self, _ev=None) -> None:
        """窗口宽度变化 → 换行宽度变了，全部行高作废，防抖后重排。"""
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(120, self._on_resize_flush)

    def _on_resize_flush(self) -> None:
        self._resize_job = None
        if not self._rows:
            return
        for i, row in enumerate(self._rows):
            self._heights[i] = None          # 换行宽变化，实测缓存全部作废
        self._cum_dirty = True
        if self._at_bottom:
            self._stick_bottom = True        # 底部用户：重排后保持吸底
        self._render()

    # ---------- 交互 ----------
    def _on_right_click(self, ev) -> None:
        idx = self.row_at(ev.y)
        if idx is not None and self._on_row_menu:
            self._on_row_menu(ev, idx)

    def _on_double_click(self, ev) -> None:
        idx = self.row_at(ev.y)
        if idx is None:
            return
        row = self._rows[idx] if 0 <= idx < len(self._rows) else None
        if row is not None and row.fwd_pack and not row.raw.get("deleted") \
                and self._on_fwd_open:
            self._on_fwd_open(idx)          # R39D③：合并转发卡双击展开逐条
            return
        if self._on_row_double:
            self._on_row_double(idx)
