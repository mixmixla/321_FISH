# -*- coding: utf-8 -*-
"""widgets/avatar.py —— 头像渲染（首字色块 + R52 图片头像缓存）。

按昵称 → (底色, 字色) 确定性映射并缓存；draw 只做两次 Canvas create
（圆形 + 首字），不重复计算配色。R52：支持按 uid 注册图片头像（PIL
裁剪/圆形掩码/多尺寸缩放 → PhotoImage 缓存，LRU 上限防内存泄漏）。

线程无关：只在 GUI 主线程使用。
"""
import hashlib
import io as _io

# TG 会话头像常见的鲜艳色板（与 UI 灰调形成对比）
_PALETTE = (
    "#e91e63", "#9c27b0", "#673ab7", "#3f51b5", "#2196f3",
    "#03a9f4", "#009688", "#4caf50", "#8bc34a", "#ff9800",
    "#ff5722", "#795548", "#607d8b", "#f44336", "#00bcd4",
)
_FG = "#ffffff"

# 功能④ 头像相框/描边样式（none/ring/gold/glow）。全局默认 + 各实例可覆盖，
# client 启动时从 prefs["avatar_frame"] 写入全局默认，所有头像统一生效。
_DEFAULT_FRAME = "none"
_FRAME_STYLES = ("", "none", "ring", "gold", "glow")      # 合法样式枚举（坏数据回退 none）
_FRAME_COLORS = {"ring": "#3d7bff", "gold": "#f0b429", "glow": "#2e9e5b"}


def parse_frame(style):
    """功能④：把任意值解析为合法相框样式键（不是在枚举内一律回退 "none"）。"""
    return style if style in _FRAME_STYLES else "none"


def set_default_frame(style) -> None:
    """功能④：设置全局默认相框样式（client 启动时从 prefs 注入）。"""
    global _DEFAULT_FRAME
    _DEFAULT_FRAME = parse_frame(style)

# R52：预渲染头像尺寸集（会话列表/消息/资料窗/图标栏通用）
_AVATAR_SIZES = (24, 32, 40, 48, 56, 64, 96, 128)
_MAX_IMG_UIDS = 512          # 图片头像缓存 uid 上限（LRU 淘汰，防内存泄漏）

try:
    from PIL import Image, ImageDraw, ImageTk
    _PIL = True
except Exception:            # Pillow 未装（打包期/极简环境）→ 降级首字色块
    _PIL = False


class AvatarCache:
    """昵称 → 头像样式缓存；uid → 图片头像缓存（LRU）。"""

    def __init__(self, frame: str | None = None) -> None:
        self._mem: dict = {}            # nick -> (bg, char)
        self._img: dict = {}            # uid -> {size: PhotoImage}
        self._lru: list = []            # uid 访问序（尾=最近）
        # 功能④：本实例优先的相框样式；None → 用全局默认（client 注入）
        self._frame = frame if (frame is not None and frame != "") else None

    # ---------- 首字色块 ----------
    def style(self, nick: str):
        """取（缓存）昵称的 (底色, 首字)。首字取第一个非空白字符。"""
        st = self._mem.get(nick)
        if st is None:
            n = nick.strip()
            char = n[0] if n else "?"
            idx = int(hashlib.md5(nick.encode("utf-8", "ignore")).hexdigest(),
                      16) % len(_PALETTE)
            st = (_PALETTE[idx], char)
            self._mem[nick] = st
        return st

    # ---------- R52 图片头像 ----------
    def _touch(self, uid: int) -> None:
        """LRU 记账：uid 移到最近使用位；超限淘汰最久未用。"""
        try:
            self._lru.remove(uid)
        except ValueError:
            pass
        self._lru.append(uid)
        while len(self._lru) > _MAX_IMG_UIDS:
            old = self._lru.pop(0)
            self._img.pop(old, None)

    def has_image(self, uid: int) -> bool:
        return uid in self._img

    def set_image(self, uid: int, ext: str, data: bytes) -> bool:
        """注册 uid 的图片头像（PIL 处理；失败返回 False 降级首字色块）。

        处理链：解码 → 中心方形裁剪 → 等比缩放到各尺寸 → 圆形掩码 →
        PhotoImage 入缓存。ext 仅用于解码提示（实际以内容识别）。
        """
        if not _PIL or not data:
            return False
        try:
            img = Image.open(_io.BytesIO(data)).convert("RGBA")
        except Exception:
            return False
        w, h = img.size
        if w < 4 or h < 4:
            return False
        # 中心方形裁剪
        side = min(w, h)
        x0, y0 = (w - side) // 2, (h - side) // 2
        img = img.crop((x0, y0, x0 + side, y0 + side))
        sizes = {}
        for s in _AVATAR_SIZES:
            sm = img.resize((s, s), Image.LANCZOS)
            mask = Image.new("L", (s, s), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, s - 1, s - 1), fill=255)
            sm.putalpha(mask)
            sizes[s] = ImageTk.PhotoImage(sm)
        self._img[uid] = sizes
        self._touch(uid)
        return True

    def clear_image(self, uid: int) -> None:
        """移除 uid 图片头像（删除/换头像后回退首字色块）。"""
        self._img.pop(uid, None)
        try:
            self._lru.remove(uid)
        except ValueError:
            pass

    def get_photo(self, uid: int, size: int):
        """取最接近 size 的 PhotoImage（取 ≥size 的最小档，否则最大档）。"""
        sizes = self._img.get(uid)
        if not sizes:
            return None
        best = None
        for s in sorted(sizes):
            if s >= size:
                best = s
                break
        if best is None and sizes:
            best = max(sizes)
        self._touch(uid)
        return sizes.get(best)

    def draw(self, canvas, x: int, y: int, size: int, nick: str,
             uid: int | None = None, font=None) -> list:
        """在 canvas 上画一个 size×size 圆形头像（左下角 (x,y)）。

        uid 有图片头像 → 贴图；否则回退首字色块圆形。
        返回创建的 canvas item id 列表（供调用方登记进自管列表以便清空，
        否则会话切换后这些 item 会残留画布导致「换会话头像还在」）。
        """
        ids: list = []
        if uid is not None:
            photo = self.get_photo(uid, size)
            if photo is not None:
                ids.append(canvas.create_image(
                    x + size / 2, y + size / 2, image=photo, anchor="center"))
                ids += self._draw_frame(canvas, x, y, size)
                return ids
        bg, char = self.style(nick)
        ids.append(canvas.create_oval(x, y, x + size, y + size,
                                      fill=bg, outline=""))
        ids.append(canvas.create_text(
            x + size / 2, y + size / 2, text=char,
            fill=_FG, font=font or ("TkDefaultFont", 9, "bold")))
        ids += self._draw_frame(canvas, x, y, size)
        return ids

    # ---------- 功能④ 相框/描边（头像外圈；none=无） ----------
    def _draw_frame(self, canvas, x: int, y: int, size: int) -> list:
        """按当前样式在头像外圈画相框：ring/gold 单环，glow 双环渐变光晕。"""
        style = parse_frame(self._frame if self._frame else _DEFAULT_FRAME)
        if style == "none":
            return []
        base = int(size * 0.06) + 1
        pad = int(size * 0.08) + 1
        ids = []
        if style == "glow":
            col = _FRAME_COLORS["glow"]
            ids.append(canvas.create_oval(
                x - pad, y - pad, x + size + pad, y + size + pad,
                outline=col, width=1))           # 外圈浅光晕
            ids.append(canvas.create_oval(
                x - base, y - base, x + size + base, y + size + base,
                outline=col, width=2))           # 内圈主环
        else:
            col = _FRAME_COLORS.get(style, _FRAME_COLORS["ring"])
            w = 3 if style == "gold" else 2
            ids.append(canvas.create_oval(
                x - base, y - base, x + size + base, y + size + base,
                outline=col, width=w))
        return ids
