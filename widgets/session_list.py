# -*- coding: utf-8 -*-
"""widgets/session_list.py —— 会话列表两行 Canvas 控件（对标 TG dialogs）。

把左侧会话列表从「单行 tk.Listbox」升级为「两行布局」：
- 上行：首字色块头像 + 名称（置顶 📌 前缀）
- 下行：末条摘要预览（按宽截断加 …）
- 右上：时间 HH:MM；右下：未读圆角角标（>99 → 99+）
- 选中整行 accent 高亮；静音整行灰化保留摘要与角标

未做行虚拟化（名单数量级小），`set_items` 全量 delete+重绘最稳。

为缩回归面，暴露了与 Listbox 兼容的外层 API：
size/get/curselection/selection_clear/selection_set/see/nearest/cget，
使 client 的 _select_eid/_switch_view/_list_move/_on_pick_* 一行不改。
此例参考 widgets/msg_list.py（Canvas 渲染 + set_colors 换色）与
widgets/avatar.py（AvatarCache 首字头像）。
"""
import time
import tkinter as tk
from tkinter import font as tkfont

from widgets.avatar import AvatarCache


def fmt_unread(n: int) -> str:
    """未读数 → 角标文案：>99 压成 99+（防多位数撑爆布局）。"""
    n = max(0, int(n))
    return "99+" if n > 99 else (str(n) if n else "")


def fmt_list_time(ts: float) -> str:
    """R32A3 会话列表时间（对齐 TG）：今天 HH:MM / 昨天 / 周X / M月D日 / Y年M月D日。"""
    if not ts:
        return ""
    lt = time.localtime(ts)
    now = time.localtime(time.time())
    if (lt.tm_year, lt.tm_yday) == (now.tm_year, now.tm_yday):
        return time.strftime("%H:%M", lt)
    yest = time.localtime(time.time() - 86400)
    if (lt.tm_year, lt.tm_yday) == (yest.tm_year, yest.tm_yday):
        return "昨天"
    if lt.tm_year == now.tm_year:
        if 0 < now.tm_yday - lt.tm_yday <= 6:      # 近 7 天 → 周X
            return "周" + "一二三四五六日"[lt.tm_wday]
        return f"{lt.tm_mon}月{lt.tm_mday}日"
    return f"{lt.tm_year}年{lt.tm_mon}月{lt.tm_mday}日"


class SessionList(tk.Canvas):
    """两行会话列表控件。数据经 set_items 注入，交互绑定内部处理器。"""

    ROW_H = 56                 # 行高（对标 TG dialogsRowHeight，tk 紧凑化）
    PAD = 10                   # 左右留白
    AVATAR = 34                # 圆形头像直径
    AV_GAP = 10                # 头像 → 名称间隙
    NAME_Y = 7                 # 名称行 top
    PREV_Y = 32                # 预览行 top
    BADGE_H = 18               # 未读角标高
    BADGE_R = 9                # 角标圆角
    # R交互：三种布局密度的行高/纵坐标/角标参数（wechat 宽松、qq 紧凑+角标显眼）
    LAYOUTS = {
        "tg":     {"ROW_H": 56, "NAME_Y": 7,  "PREV_Y": 32, "BADGE_H": 18},
        "wechat": {"ROW_H": 64, "NAME_Y": 10, "PREV_Y": 37, "BADGE_H": 18},
        "qq":     {"ROW_H": 50, "NAME_Y": 5,  "PREV_Y": 29, "BADGE_H": 20},
    }
    PALETTE = {
        "bg": "#ececee",
        "fg": "#1d1d1f",
        "sub": "#86868b",
        "accent": "#007aff",
        "draft": "#e03e3e",    # R32B1 草稿前缀（TG 风格红色）
        "selected_fg": "#ffffff",
        "muted": "#86868b",
        "hover": "#e3e3e5",        # 非选中行 hover 高亮
        # R__ 手柄配色（主题化可覆盖）
        "hnd_track": "#d8d8dc",
        "hnd_thumb": "#b4b4ba",
        "hnd_tip_bg": "#333333",
        "hnd_tip_fg": "#ffffff",
    }
    _TEXT_L = 10 + 34 + 10     # = PAD + AVATAR + AV_GAP（正文左边缘）
    SECTION_H = 26             # R58D：置顶会话分区头高度（对齐 TG「钉住」分组条）
    SECTION_PAD = 8
    # R-：hover 快捷操作条（标已读/归档/删除），右侧小圆钮
    ACT_W = 22                 # 按钮边长
    ACT_GAP = 6                # 按钮间距
    ACT_R = 6                  # 圆角
    ACTS = (("✓", "read"), ("档", "archive"), ("🗑", "delete"))
    # R__：右侧「时间定位手柄」（对齐微信/QQ 列表右侧可拖灰条按时间定位到会话）
    HND_W = 12                  # 手柄宽（细长条）
    HND_PAD = 3                 # 手柄与右缘留白
    HND_MIN_H = 16              # 大拇指最小高（列表很长时也能抓住）
    _HND_TAG = "slhnd"          # 手柄 tag（供 tag_bind 事件绑定）

    def __init__(self, parent, font, height=5 * 56, on_pick=None,
                 avatars=None, layout="tg", on_act=None, on_avatar_dbl=None, scale=1.0, **kw):
        self._font = tkfont.Font(root=parent, font=font)
        # 手柄状态：None=未启用；dict 记录拖动区间（避免滚动条/滚轮干扰）
        self._hnd = None
        self._hnd_drag = False
        self._hnd_job = None
        # R交互：按布局密度覆盖行高/纵坐标/角标参数（实例属性遮蔽类常量）
        for _k, _v in self.LAYOUTS.get(layout, self.LAYOUTS["tg"]).items():
            setattr(self, _k, _v)
        self._scale = max(0.5, float(scale))
        for key in ('ROW_H', 'PAD', 'AVATAR', 'AV_GAP', 'NAME_Y', 'PREV_Y',
                    'BADGE_H', 'BADGE_R', 'SECTION_H', 'SECTION_PAD',
                    'ACT_W', 'ACT_GAP', 'ACT_R', 'HND_W', 'HND_PAD', 'HND_MIN_H'):
            setattr(self, key, max(1, round(getattr(self, key) * self._scale)))
        self._TEXT_L = self.PAD + self.AVATAR + self.AV_GAP
        family = self._font.actual("family")
        self._name_font = tkfont.Font(root=parent, font=(family, 10, "bold"))
        self._prev_font = tkfont.Font(root=parent, font=(family, 9))
        self._time_font = tkfont.Font(root=parent, font=(family, 9))
        self._badge_font = tkfont.Font(root=parent, font=(family, 10, "bold"))
        self._section_font = tkfont.Font(root=parent, font=(family, 9, "bold"))
        self._avatar_font = (family, 9, "bold")
        self._sec_linespace = self._section_font.metrics("linespace")
        try:
            self._linespace_name = self._name_font.metrics("linespace")
            self._linespace_prev = self._prev_font.metrics("linespace")
        except Exception:
            self._linespace_name = 14
            self._linespace_prev = 12
        self._pal = dict(self.PALETTE)
        kw.setdefault("bg", self._pal["bg"])
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("relief", "flat")
        super().__init__(parent, height=round(height * self._scale), **kw)
        self._on_pick = on_pick
        self._on_act = on_act        # R-：hover 快捷操作回调(i, 'read'|'archive'|'delete')
        self._on_avatar_dbl = on_avatar_dbl   # R68：双击头像回调(i)（窗口抖动）
        self._items: list = []       # 每项 dict（set_items 注入）
        self._sel: int = -1          # 选中下标（-1=无）——兼容层事实来源
        self._hover: int = -1        # hover 行（-1=无）R8 过场高亮
        # R-66：文本测量/截断 LRU 缓存（_truncate 二分反复 measure 全量行时为热点）
        self._meas_cache = {}
        self._meas_max = 2048
        self._trunc_cache = {}
        self._trunc_max = 2048
        # R58E：滚轮缓动惯性（对齐 msg_list 手感；会话列表原先瞬时硬跳）
        self._anim_job = None
        self._s_from = 0.0
        self._s_to = 0.0
        self._s_t0 = 0.0
        # R52：可共享 AvatarCache（桌面端全局共用一份，头像到达一次注册全界面生效）
        self._avatars = avatars or AvatarCache()
        self.bind("<Button-1>", self._on_click)
        self.bind("<Double-Button-1>", self._on_dbl)
        self.bind("<Return>", self._on_return)
        self.bind("<Up>", self._on_up)
        self.bind("<Down>", self._on_down)
        self.bind("<Home>", self._on_home)
        self.bind("<End>", self._on_end)
        self.bind("<Configure>", self._on_configure)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", lambda e: self._on_wheel_step(1))
        self.bind("<Button-5>", lambda e: self._on_wheel_step(-1))
        # R__ 时间定位手柄（tag 绑定；只在溢出时画出手柄从而命中 tag）
        self.tag_bind(self._HND_TAG, "<ButtonPress-1>", self._hnd_press)
        self.tag_bind(self._HND_TAG, "<B1-Motion>", self._hnd_motion)
        self.tag_bind(self._HND_TAG, "<ButtonRelease-1>", self._hnd_release)
        self.tag_bind(self._HND_TAG, "<Enter>",
                      lambda e: self.configure(cursor="sb_v_double_arrow"))
        self.tag_bind(self._HND_TAG, "<Leave>",
                      lambda e: self.configure(cursor=""))
        # 浮动位置提示（会话名+时间），用 Toplevel 无边框浮层
        self._hnd_tip = None

    # ---------- 数据注入与兼容 API ----------
    def set_items(self, items: list) -> None:
        """替换整表；尽力保留当前选中的行（按 key）避免周期性刷新跳选择。"""
        prev_key = None
        if 0 <= self._sel < len(self._items):
            prev_key = self._items[self._sel].get("key")
        self._items = items
        self._sel = -1
        if prev_key is not None:
            for i, it in enumerate(items):
                if it.get("key") == prev_key:
                    self._sel = i
                    break
        self._redraw()

    def size(self) -> int:
        return len(self._items)

    def _text_of(self, i: int) -> str:
        it = self._items[i]
        pre = ("⭐ " if it.get("starred") else "") + ("📌 " if it.get("pinned") else "")
        name = pre + it.get("name", "")
        t = it.get("ts")
        parts = [name]
        draft = (it.get("draft") or "").replace("\n", " ").strip()
        pv = ("草稿: " + draft) if draft else it.get("preview")
        if pv:
            parts.append("·")
            parts.append(pv)
            if t:
                parts.append(fmt_list_time(t))
        s = " ".join(parts)
        n = it.get("unread", 0)
        if n > 0:
            s += f" ({n})"
        return s

    def get(self, first, last=None):
        """兼容 Listbox.get(first[, last])：单下标返回字符串，区间返回元组。"""
        n = len(self._items)
        def idx(x):
            return n - 1 if x == "end" else int(x)
        start = idx(first)
        if start < 0 or start >= n:
            return "" if last is None else ()
        if last is None:
            return self._text_of(start)
        end = idx(last)
        end = min(end, n - 1)
        return tuple(self._text_of(i) for i in range(start, end + 1))

    def curselection(self) -> tuple:
        if 0 <= self._sel < len(self._items):
            return (self._sel,)
        return ()

    def selection_clear(self, first=0, last=None) -> None:
        if self._sel != -1:
            self._sel = -1
            self._redraw()

    def selection_set(self, index, last=None) -> None:
        i = int(index)
        if 0 <= i < len(self._items):
            self._sel = i
            self._redraw()

    def see(self, index) -> None:
        n = len(self._items)
        i = int(index)
        if not 0 <= i < n:
            return
        top = i * self.ROW_H
        bot = (i + 1) * self.ROW_H
        vis = self.winfo_height()
        total = max(self._scroll_h(), 1)
        ytop = self.yview()[0] * total
        if top < ytop:
            self._scroll_frac(top)
        elif bot > ytop + vis:
            self._scroll_frac(bot - vis)

    def nearest(self, y: int) -> int:
        n = len(self._items)
        if n == 0:
            return 0
        cy = int(self.canvasy(y) // self.ROW_H)   # 视口坐标→画布坐标（随滚动偏移）
        return max(0, min(cy, n - 1))

    def cget(self, key: str):
        if key == "bg":
            return self._pal["bg"]
        try:
            return super().cget(key)
        except tk.TclError:
            return None

    def set_colors(self, pal: dict) -> None:
        """整批替换调色板并重绘（msg_list.set_colors 同款）。"""
        self._pal.update(pal)
        self.configure(bg=self._pal["bg"])
        self._redraw()

    def set_font(self, font) -> None:
        """R-字号：重建会话列表字体档链（名称/预览/时间/角标/分区头）并重绘。"""
        if getattr(self, "_last_font", None) == tuple(font):
            return
        self._last_font = tuple(font)
        self._font = tkfont.Font(root=self, font=font)
        family = self._font.actual("family")
        size = max(9, abs(int(self._font.cget('size'))))
        self._name_font = tkfont.Font(root=self, font=(family, size, "bold"))
        self._prev_font = tkfont.Font(root=self, font=(family, max(9, size-1)))
        self._time_font = tkfont.Font(root=self, font=(family, max(9, size-1)))
        self._badge_font = tkfont.Font(root=self, font=(family, 10, "bold"))
        self._section_font = tkfont.Font(root=self, font=(family, 9, "bold"))
        self._avatar_font = (family, 9, "bold")
        try:
            self._sec_linespace = self._section_font.metrics("linespace")
            self._linespace_name = self._name_font.metrics("linespace")
            self._linespace_prev = self._prev_font.metrics("linespace")
        except Exception:
            pass
        # R-66：字体档已重建 → 清空测量/截断缓存（f.name 变更，旧键不可复用）
        self._meas_cache.clear()
        self._trunc_cache.clear()
        self._redraw()

    # ---------- 内部键盘/鼠标 ----------
    def _row_from_event_y(self, ev) -> int | None:
        n = len(self._items)
        if n == 0:
            return None
        cy = self.canvasy(int(ev.y))
        i = int(cy // self.ROW_H)
        return i if 0 <= i < n else None

    def _on_motion(self, ev) -> str:
        i = self._row_from_event_y(ev)
        if i != self._hover:
            self._hover = -1 if i is None else i
            self._redraw()
        return "break"

    def _on_leave(self, _ev=None) -> str:
        if self._hover != -1:
            self._hover = -1
            self._redraw()
        return "break"

    def _on_click(self, ev) -> str:
        i = self._row_from_event_y(ev)
        if i is None:
            return "break"
        self._sel = i
        self._redraw()
        self.focus_set()
        if self._on_pick:
            self._on_pick(i)
        return "break"

    def _on_return(self, _ev=None) -> str:
        if 0 <= self._sel < len(self._items) and self._on_pick:
            self._on_pick(self._sel)
        return "break"

    def _on_dbl(self, ev) -> str:
        """R68 双击头像：仅当横坐标落在头像区域内才触发（回调由宿主注入）。"""
        i = self._row_from_event_y(ev)
        if i is None or self._on_avatar_dbl is None:
            return "break"
        try:
            cx = self.canvasx(int(ev.x))
        except Exception:
            return "break"
        if cx <= self.PAD + self.AVATAR:
            self._on_avatar_dbl(i)
        return "break"

    def _move_sel(self, step: int) -> None:
        n = len(self._items)
        if n == 0:
            return
        cur = self._sel if 0 <= self._sel < n else (0 if step > 0 else n - 1)
        self._sel = max(0, min(n - 1, cur + step))
        self._redraw()
        self.see(self._sel)

    def _on_up(self, _e=None) -> str:
        self._move_sel(-1)
        return "break"

    def _on_down(self, _e=None) -> str:
        self._move_sel(1)
        return "break"

    def _on_home(self, _e=None) -> str:
        self._sel = min(len(self._items) - 1, 0) if self._items else -1
        if self._items:
            self._redraw()
            self.see(0)
        return "break"

    def _on_end(self, _e=None) -> str:
        if self._items:
            self._sel = len(self._items) - 1
            self._redraw()
            self.see(self._sel)
        return "break"

    def _on_configure(self, _ev=None) -> None:
        self._redraw()

    def _on_wheel(self, ev) -> str:
        d = getattr(ev, "delta", 0)
        self._on_wheel_step(1 if d < 0 else -1)
        return "break"

    def _on_wheel_step(self, dirn: int) -> None:
        step_px = 2 * self.ROW_H
        self._anim_to(self._current_top() + dirn * step_px)

    # ---------- 滚动辅助 ----------
    def _top_seg_counts(self):
        """返回 (星标数, 置顶数)：顶部连续段星标在最前，随后置顶，其余普通。"""
        n = len(self._items)
        star = 0
        while star < n and self._items[star].get("starred"):
            star += 1
        pin = 0
        while star + pin < n and self._items[star + pin].get("pinned"):
            pin += 1
        return star, pin

    def _scroll_h(self) -> int:
        star, pin = self._top_seg_counts()
        secs = (1 if star else 0) + (1 if pin else 0)
        return len(self._items) * self.ROW_H + secs * self.SECTION_H

    def _current_top(self) -> int:
        total = max(self._scroll_h(), 1)
        return int(self.yview()[0] * total)

    def _scroll_frac(self, px: int) -> None:
        total = max(self._scroll_h(), 1)
        frac = max(0.0, min(1.0, px / total))
        self.yview_moveto(frac)
        self._redraw()                      # R-66：虚拟化后移动视口需重绘可见行

    # ---------- R58E 缓动滚动（ease-out cubic，对齐 msg_list 惯性手感） ----------
    _ANIM_MS = 260

    @staticmethod
    def _ease_out_cubic(t: float) -> float:
        t = max(0.0, min(1.0, t))
        u = 1 - t
        return 1 - u * u * u

    def _clamp_px(self, px: float) -> float:
        total = max(self._scroll_h(), 1)
        return max(0.0, min(float(total), px))

    def _anim_to(self, px: float) -> None:
        if self._anim_job:
            self.after_cancel(self._anim_job)
            self._anim_job = None
        self._s_from = float(self._current_top())
        self._s_to = self._clamp_px(px)
        self._s_t0 = time.time()
        self._anim_job = self.after(16, self._anim_tick)

    def _anim_tick(self) -> None:
        self._anim_job = None
        total = max(self._scroll_h(), 1)
        if total <= 0:
            return
        k = (time.time() - self._s_t0) * 1000.0 / self._ANIM_MS
        if k >= 1.0:
            self.yview_moveto(self._clamp_px(self._s_to) / total)
            self._redraw()              # R-66：虚拟化后每帧重绘可见行
            return
        y = self._s_from + (self._s_to - self._s_from) * self._ease_out_cubic(k)
        self.yview_moveto(max(0.0, min(1.0, y / total)))
        self._redraw()                  # R-66：虚拟化后每帧重绘可见行
        self._anim_job = self.after(16, self._anim_tick)

    # ---------- 渲染 ----------
    def _measure(self, f: tkfont.Font, s: str) -> int:
        """带 LRU 缓存的字体像素宽（id 稳定：f.name 由 Font 创建时分配且唯一）。"""
        key = (f.name, s)
        hit = self._meas_cache.get(key)
        if hit is not None:
            return hit
        try:
            w = f.measure(s)
        except Exception:
            w = len(s) * 8
        if len(self._meas_cache) >= self._meas_max:
            self._meas_cache.pop(next(iter(self._meas_cache)))       # 淘汰最旧
        self._meas_cache[key] = w
        return w

    def _truncate(self, text: str, f: tkfont.Font, width: int) -> str:
        if width <= 0 or not text:
            return ""
        ck = (f.name, text, width)
        hit = self._trunc_cache.get(ck)
        if hit is not None:
            return hit
        if self._measure(f, text) <= width:
            res = text
        else:
            ell = "…"
            ew = self._measure(f, ell)
            hi = len(text)
            lo = 0
            while lo < hi:                   # 二分缩短 + 省略号
                mid = (lo + hi + 1) // 2
                if self._measure(f, text[:mid]) + ew <= width:
                    lo = mid
                else:
                    hi = mid - 1
            res = text[:lo].rstrip() + ell
        if len(self._trunc_cache) >= self._trunc_max:
            self._trunc_cache.pop(next(iter(self._trunc_cache)))
        self._trunc_cache[ck] = res
        return res

    def _badge_w(self, n: int) -> int:
        s = fmt_unread(n)
        if not s:
            return 0
        return max(18, min(40, self._measure(self._badge_font, s) + 10))

    def _round_rect(self, x0, y0, x1, y1, r, fill, outline="", tags=()):
        r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
        pts = [
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
            x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
            x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
        ]
        return self.create_polygon(pts, smooth=True, fill=fill, outline=outline,
                                   width=1, tags=tags)

    def _draw_row(self, i: int, it: dict, y: int, win_w: int) -> None:
        sel = (i == self._sel)
        muted = bool(it.get("muted"))
        n = int(it.get("unread", 0))
        time_s = fmt_list_time(it.get("ts", 0))
        if sel:
            # Apple 风格：圆角蓝色选中高亮（内缩 2px）
            self._round_rect(2, y + 2, win_w - 2, y + self.ROW_H - 2,
                             6, fill=self._pal.get("selected_bg", self._pal["accent"]))
        elif i == self._hover:
            # Apple 风格：圆角灰色 hover 高亮
            self._round_rect(2, y + 2, win_w - 2, y + self.ROW_H - 2,
                             6, fill=self._pal.get("hover", "#e3e3e5"))
        fg = self._pal["selected_fg"] if sel else (self._pal["muted"] if muted
                                                   else self._pal["fg"])
        sub = self._pal["selected_fg"] if sel else (self._pal["muted"] if muted
                                                    else self._pal["sub"])
        # 头像（R52：uid 有图片头像则贴图，否则首字色块）
        avatar_y = y + (self.ROW_H - self.AVATAR) // 2
        self._avatars.draw(self, self.PAD, avatar_y, self.AVATAR, it.get("name", "?"),
                           uid=it.get("uid"), font=self._avatar_font)
        # 右侧预留：时间 + 角标（hover 时改为操作条宽度）
        hover = (not sel and i == self._hover and self._on_act is not None)
        if hover:
            right_w = 3 * self.ACT_W + 2 * self.ACT_GAP + self.PAD
        else:
            right_w = (self._measure(self._time_font, time_s) if time_s else 0)
            bw = self._badge_w(n)
            if bw:
                right_w += bw + 8
        avail = win_w - self._TEXT_L - self.PAD - right_w
        name_x = self._TEXT_L
        # R69C11 标为未读：名称前蓝点（有数字角标时不重复画）
        if it.get("mark_unread") and not n:
            self.create_oval(name_x + 2, y + self.NAME_Y + 6,
                             name_x + 8, y + self.NAME_Y + 12,
                             fill=self._pal.get("accent", "#3d7bff"),
                             outline="")
            name_x += 11
            avail -= 11
        # R25B 在线状态点；R68 扩展为多状态（在线绿/离开黄/忙碌红/离线灰）
        sdot = {"online": "#2e9e5b", "away": "#e0a33e", "busy": "#e05252",
                "offline": "#b9bec4"}.get(it.get("status"))
        if sdot:
            self.create_oval(name_x, y + self.NAME_Y + 6,
                             name_x + 7, y + self.NAME_Y + 13,
                             fill=sdot, outline="")
            name_x += 11
            avail -= 11
        # 名称（置顶前缀计入截断；极窄列时保底 16px，避免整名整行消失）
        name = ("⭐ " if it.get("starred") else "") + ("📌 " if it.get("pinned") else "") + it.get("name", "")
        self.create_text(name_x, y + self.NAME_Y, anchor="nw",
                         text=self._truncate(name, self._name_font,
                                             max(16, avail)),
                         font=self._name_font, fill=fg)
        # 预览（R32B1：草稿优先，红色「草稿:」前缀 + 草稿正文，替代旧预览）
        draft = (it.get("draft") or "").replace("\n", " ").strip()
        pv = it.get("preview")
        if draft:
            pre = "草稿: "
            pre_w = self._measure(self._prev_font, pre)
            self.create_text(self._TEXT_L, y + self.PREV_Y, anchor="nw",
                             text=pre, font=self._prev_font,
                             fill=self._pal.get("draft", "#e03e3e"))
            self.create_text(self._TEXT_L + pre_w, y + self.PREV_Y, anchor="nw",
                             text=self._truncate(draft, self._prev_font,
                                                 max(24, avail - pre_w)),
                             font=self._prev_font, fill=sub)
        elif pv:
            self.create_text(self._TEXT_L, y + self.PREV_Y, anchor="nw",
                             text=self._truncate(pv, self._prev_font, avail),
                             font=self._prev_font, fill=sub)
        if hover:                     # R-：hover 快捷操作条（替代时间/角标，防重叠）
            self._draw_act_strip(i, y, win_w)
        else:
            # 时间（最右）
            if time_s:
                self.create_text(win_w - self.PAD, y + 8, anchor="ne",
                                 text=time_s, font=self._time_font, fill=sub)
            # R58B：静音喇叭 + 斜杠（对齐 TG 静音会话图标）。画在时间左侧，灰化底座上更醒目
            if muted:
                tw = self._measure(self._time_font, time_s) if time_s else 0
                sx = win_w - self.PAD - tw - 20
                sy = y + 9
                speaker = ((sx, sy), (sx + 4, sy),
                           (sx + 8, sy - 4), (sx + 8, sy + 4),
                           (sx + 4, sy))           # 喇叭机身（朝左）
                self.create_polygon(speaker, fill=sub, outline="")
                self.create_polygon(sx + 8, sy - 3, sx + 13, sy - 6, sx + 13, sy + 6,
                                    sx + 8, sy + 3, fill=sub, outline="")   # 漏斗
                self.create_line(sx + 3, sy - 6, sx + 15, sy + 6,
                                 fill=sub, width=2)   # 静音斜杠
            # 未读角标（时间左侧）
            if n > 0:
                bw = self._badge_w(n)
                x_right = win_w - self.PAD - (self._measure(self._time_font, time_s) if time_s else 0) - 8
                bx = x_right - bw
                by = y + self.NAME_Y
                badge_fill = self._pal["muted"] if muted else "#e0413f"
                self._round_rect(bx, by, bx + bw, by + self.BADGE_H,
                                 self.BADGE_R, fill=badge_fill)
                self.create_text(bx + bw / 2, by + self.BADGE_H / 2,
                                 text=fmt_unread(n), font=self._badge_font,
                                 fill=self._pal["selected_fg"])

    def _draw_act_strip(self, i: int, y: int, win_w: int) -> None:
        """R-：hover 行右侧竖排 3 个快捷钮（标已读/归档/删除）。
        静默失败：未接 on_act 回调则不画；点击回调 (i, 'read'|'archive'|'delete')。"""
        if not self._on_act:
            return
        b = self.ACT_W
        g = self.ACT_GAP
        total = len(self.ACTS) * b + (len(self.ACTS) - 1) * g
        x0 = win_w - self.PAD - total
        top = y + (self.ROW_H - b) // 2
        accent = self._pal.get("accent", "#007aff")
        for k, (glyph, act) in enumerate(self.ACTS):
            bx = x0 + k * (b + g)
            tag = f"sact{i}_{act}"          # 稳定唯一 tag（原用 find_all() 全扫描，O(全部 item)）
            self._round_rect(bx, top, bx + b, top + b, self.ACT_R,
                             fill=self._pal.get("bg", "#ececee"), outline="#c8cdd4")
            self.create_text(bx + b / 2, top + b / 2, anchor="center",
                             text=glyph, font=self._name_font, fill=accent, tags=(tag,))
            self.tag_bind(tag, "<Enter>",
                          lambda e: self.configure(cursor="hand2"))
            self.tag_bind(tag, "<Leave>",
                          lambda e: self.configure(cursor=""))
            self.tag_bind(tag, "<Button-1>",
                          lambda _e, a=act: ((self._on_act(i, a)), "break")[-1])

    def _seg_unread(self, start: int, count: int) -> int:
        """分区内未读会话数（对齐 TG 分区右上未读计数）。"""
        return sum(1 for it in self._items[start:start + count]
                   if int(it.get("unread", 0)) > 0)

    def _draw_section_header(self, label: str, start: int, count: int,
                             ytop: int, win_w: int) -> int:
        """画一个分区头（星标/置顶），返回所需高度。count<=0 时不画。"""
        if count <= 0:
            return 0
        y0, y1 = ytop + 2, ytop + self.SECTION_H - 2
        hfill = self._pal.get("hover", "#e3e3e5")
        hfg = self._pal.get("accent", "#007aff")
        self._round_rect(2, y0, win_w - 2, y1, 6, fill=hfill)
        un = self._seg_unread(start, count)
        if un:
            label += f" · {un} 条未读"
        self.create_text(self.SECTION_PAD, (y0 + y1) / 2, anchor="w",
                         text=label, font=self._section_font, fill=hfg)
        return self.SECTION_H

    def _redraw(self) -> None:
        """R-66：只画可见行（虚拟化）——原先逐行全量重建，会话多时 hover/刷新卡顿。
        scrollregion 仍按全量高度设置，滚动用 yview_moveto 移动视口后再触发本方法。"""
        self.delete("all")
        win_w = self.winfo_width()
        if win_w <= 1:
            win_w = 250
        # 顶部连续段：⭐ 星标在置顶之上，随后 📌 置顶，其余普通
        star, pin = self._top_seg_counts()
        n = len(self._items)
        header = ((1 if star else 0) + (1 if pin else 0)) * self.SECTION_H
        total_h = header + n * self.ROW_H
        # 先落 scrollregion（长度变化时 Tk 会钳位视口）；再取视口偏移算可见区间
        self.configure(scrollregion=(0, 0, win_w, total_h))
        vis = self.winfo_height()
        if vis <= 1:                       # 尚未布局：退化为全量（一次性）
            top, bottom = 0, total_h
        else:
            top = self.canvasy(0)
            bottom = top + vis
        y = 0
        if star and y + self.SECTION_H > top and y < bottom:
            self._draw_section_header("⭐ 已星标", 0, star, y, win_w)
        y += self.SECTION_H if star else 0
        if pin and y + self.SECTION_H > top and y < bottom:
            self._draw_section_header("📌 已置顶", star, pin, y, win_w)
        # 可见行区间：上下各多留一行，避免滚动/裁切误差
        i0 = max(0, int((top - header) // self.ROW_H) - 1)
        i1 = min(n, int((bottom - header) // self.ROW_H) + 2)
        for i in range(i0, i1):
            self._draw_row(i, self._items[i], y + i * self.ROW_H, win_w)
        self._draw_handle(win_w)

    # ---------- R__ 右侧时间定位手柄（拖动 → 按最后活跃时间跳到对应会话） ----------
    def _hnd_area(self, win_w, vis):
        """手柄轨道矩形（右缘细长条）。返回 (x0, y0, x1, y1)。"""
        x1 = win_w - self.HND_PAD
        x0 = x1 - self.HND_W
        return (x0, 2, x1, vis - 2)

    def _hnd_should_show(self, vis) -> bool:
        """仅当列表内容超高（溢出）才显示手柄：一条多屏才有定位意义。"""
        return len(self._items) > 0 and self._scroll_h() > vis

    def _draw_handle(self, win_w) -> None:
        """按当前滚动状态在右侧画手柄（轨道+大拇指）；不溢出则不画。"""
        vis = self.winfo_height()
        if not self._hnd_should_show(vis):
            self._hnd = None
            return
        x0, y0, x1, y1 = self._hnd_area(win_w, vis)
        self._hnd = {"x0": x0, "x1": x1, "y0": y0, "y1": y1}
        total = max(self._scroll_h(), 1)
        self._round_rect(x0, y0, x1, y1, 6,
                         fill=self._pal.get("hnd_track", "#d8d8dc"))
        # 大拇指：高度 ∝ 视口/内容比，位置 ∝ 当前滚动比例
        frac = self._current_top() / total
        th_h = max(self.HND_MIN_H, (y1 - y0) * (vis / total))
        ty0 = y0 + (y1 - y0 - th_h) * frac
        ty1 = ty0 + th_h
        self._round_rect(x0, ty0, x1, ty1, 6,
                         fill=self._pal.get("hnd_thumb", "#b4b4ba"), tags=(self._HND_TAG,))

    def _hnd_frac_from_y(self, y) -> float:
        """把鼠标 y 映射为手柄方向比例 [0,1]（锚定轨道范围内）。"""
        if not self._hnd:
            return 0.0
        span = self._hnd["y1"] - self._hnd["y0"]
        if span <= 0:
            return 0.0
        return max(0.0, min(1.0, (y - self._hnd["y0"]) / span))

    def _hnd_index_of_frac(self, frac: float) -> int:
        """按比例推目标会话下标：把轨道比例映射到滚动绘区→由行高反解行号。"""
        n = len(self._items)
        if n == 0:
            return -1
        total = max(self._scroll_h(), 1)
        vis = self.winfo_height()
        top_px = frac * max(total - vis, 0)
        header = ((1 if self._top_seg_counts()[0] else 0)
                  + (1 if self._top_seg_counts()[1] else 0)) * self.SECTION_H
        idx = int((top_px - header) / max(self.ROW_H, 1))
        return max(0, min(n - 1, idx))

    def _hnd_build_tip(self):
        if self._hnd_tip is None or not self._hnd_tip.winfo_exists():
            tl = tk.Toplevel(self)
            tl.overrideredirect(True)
            tl.configure(bg=self._pal.get("hnd_tip_bg", "#333333"))
            lbl = tk.Label(tl, bg=self._pal.get("hnd_tip_bg", "#333333"),
                           fg=self._pal.get("hnd_tip_fg", "#ffffff"),
                           font=self._prev_font, padx=8, pady=3)
            lbl.pack()
            self._hnd_tip = tl
        return self._hnd_tip

    def _hnd_move_tip(self, y: int) -> None:
        it = self._items[self._hnd_index_of_frac(self._hnd_frac_from_y(y))]
        name = str(it.get("name", ""))
        t = fmt_list_time(it.get("ts", 0))
        tl = self._hnd_build_tip()
        self._hnd_tip.winfo_children()[0].config(text=f"{name} · {t}")
        x = self._hnd["x0"] - 10
        ty = y - 12
        try:
            self.winfo_rootx()
            tl.geometry(f"+{self.winfo_rootx() + max(2, x - 160)}+{self.winfo_rooty() + ty}")
        except tk.TclError:
            pass

    def _hnd_hide_tip(self) -> None:
        if self._hnd_tip is not None and self._hnd_tip.winfo_exists():
            self._hnd_tip.withdraw()

    def _hnd_press(self, ev) -> str:
        self._hnd_drag = True
        self._hnd_last_y = ev.y
        self._hnd_move_tip(ev.y)
        return "break"

    def _hnd_motion(self, ev) -> str:
        if not self._hnd_drag:
            return "break"
        self._hnd_last_y = ev.y
        self._hnd_move_tip(ev.y)
        self._hnd_draw_thumbs()
        return "break"

    def _hnd_release(self, ev) -> str:
        if not self._hnd_drag:
            return "break"
        self._hnd_drag = False
        frac = self._hnd_frac_from_y(ev.y)
        idx = self._hnd_index_of_frac(frac)
        # 松开 → 跳转到目标会话（滚到该行对齐视口顶）
        total = max(self._scroll_h(), 1)
        vis = self.winfo_height()
        header = ((1 if self._top_seg_counts()[0] else 0)
                  + (1 if self._top_seg_counts()[1] else 0)) * self.SECTION_H
        top_px = max(0, min(total - vis, header + idx * self.ROW_H))
        self._anim_to(top_px)
        self._hnd_hide_tip()
        self._redraw()
        return "break"

    def _hnd_draw_thumbs(self) -> None:
        """拖动时轻量刷新大拇指（不动整列）。"""
        if not self._hnd:
            return
        self.delete(self._HND_TAG)
        total = max(self._scroll_h(), 1)
        vis = self.winfo_height()
        x0, y0, x1, y1 = self._hnd["x0"], self._hnd["y0"], self._hnd["x1"], self._hnd["y1"]
        frac = self._hnd_frac_from_y2()
        th_h = max(self.HND_MIN_H, (y1 - y0) * (vis / total))
        ty0 = y0 + (y1 - y0 - th_h) * frac
        self._round_rect(x0, ty0, x1, ty0 + th_h, 6,
                         fill=self._pal.get("hnd_thumb", "#b4b4ba"), tags=(self._HND_TAG,))

    def _hnd_frac_from_y2(self) -> float:
        """拖动时用最近一次鼠标 y 的比例（motion ev 不重塑轨道）。"""
        if not getattr(self, "_hnd_last_y", None):
            return 0.0
        return self._hnd_frac_from_y(self._hnd_last_y)
