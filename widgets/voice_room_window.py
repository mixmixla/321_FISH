# -*- coding: utf-8 -*-
"""R72 多人语音房窗：成员网格 · 说话者高亮 · 闭麦/离开。

- 状态完全由 `VoiceRoom` 的 room 事件驱动（`update_event`），窗口自身不判状态机
- 成员网格复用 `widgets/avatar.py`（图片头像优先，缺则首字色块圆形）
- 说话者高亮：200ms 轮询 `voice_room.speaker_levels()`（uid→0..1，uid=0 为本端），
  超阈值点亮外圈 + 昵称变绿；电平衰减由 VoiceRoom 侧负责，UI 只做阈值判定
- 底部「🎤 闭麦/🔇 开麦」热生效，「离开」退房；✕ 关闭等同离开
- 收尾态（left/failed）1.5s 后自动收窗（与通话窗同款体验）
"""
import tkinter as tk

FONT_FAMILY = "Microsoft YaHei UI"

_BG = "#ffffff"
_GREEN = "#2e9e5b"
_RED = "#d9534f"
_GREY = "#f2f3f5"
_BLUE = "#4c7de8"
_AMBER = "#c77700"
_DIM = "#9aa0a6"

_TILE_W, _TILE_H = 96, 112      # 成员格子尺寸
_AVATAR = 56                    # 头像直径
_RING_R = 34                    # 高亮圈半径（头像半径 28 + 6 空隙）
_SPEAK_ON = 0.12                # 说话判定阈值（speaker_levels 值域 0..1）


class VoiceRoomWindow(tk.Toplevel):
    """语音房窗（置顶小窗；一个客户端同开一个，由 client 持引用复用）。"""

    def __init__(self, master, *, manager, room_name: str = "",
                 avatar=None, on_leave=None):
        super().__init__(master)
        self.manager = manager
        self._avatar = avatar        # AvatarCache（None → 纯首字色块）
        self._on_leave = on_leave    # 离房回调（client 清引用）
        self._closed = False
        self._finished = False
        self._rings = {}             # uid -> 高亮圈 item id
        self._name_items = {}        # uid -> 昵称 text item id
        self._room_name = room_name or "语音房"

        self.title("语音房")
        self.geometry("380x420")
        self.minsize(300, 340)
        self.configure(bg=_BG)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.lbl_title = tk.Label(self, text=self._room_name, name="room_name",
                                  font=(FONT_FAMILY, 13, "bold"),
                                  bg=_BG, fg="#222")
        self.lbl_title.pack(pady=(12, 0))
        self.lbl_count = tk.Label(self, text="正在进入…", name="room_count",
                                  font=(FONT_FAMILY, 9), bg=_BG, fg=_DIM)
        self.lbl_count.pack(pady=(2, 6))

        self.canvas = tk.Canvas(self, name="room_canvas", bg=_BG,
                               highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8)
        self.canvas.bind("<Configure>", lambda _e: self._redraw())

        self.lbl_status = tk.Label(self, text=" ", name="room_status",
                                   font=(FONT_FAMILY, 9), bg=_BG, fg=_DIM)
        self.lbl_status.pack(pady=(2, 2))

        bar = tk.Frame(self, bg=_BG, name="room_bar")
        bar.pack(pady=(0, 12))
        self.btn_mic = tk.Label(bar, text="🎤 闭麦", name="room_mic",
                                font=(FONT_FAMILY, 10), bg=_GREY, fg="#333",
                                padx=18, pady=7, cursor="hand2")
        self.btn_mic.bind("<ButtonPress-1>", self._toggle_mic)
        self.btn_mic.pack(side="left", padx=6)
        self.btn_leave = tk.Label(bar, text="离开", name="room_leave",
                                  font=(FONT_FAMILY, 10, "bold"), bg=_RED,
                                  fg="#ffffff", padx=22, pady=7, cursor="hand2")
        self.btn_leave.bind("<ButtonPress-1>", self._leave)
        self.btn_leave.pack(side="left", padx=6)

        self.after(200, self._tick)
        self.lift()

    # ---------- 事件驱动（client 转发 room 事件） ----------

    def update_event(self, ev: dict) -> None:
        """按 VoiceRoom 事件刷新；窗口已关/已收尾则忽略。"""
        if self._closed or self._finished:
            return
        state = str(ev.get("state") or "")
        text = str(ev.get("text") or "")
        if state in ("roster", "peers"):
            self._redraw()
            return
        if state == "mic":
            self._apply_mic()
            return
        if state in ("warn", "peer_failed"):
            if text:
                self.lbl_status.config(text=text, fg=_AMBER)
            return
        if state == "joining":
            self.lbl_status.config(text=text or "正在进入语音房…", fg=_BLUE)
            return
        if state == "joined":
            self._apply_mic()
            self._redraw()
            self.lbl_status.config(text=text or "已进入语音房", fg=_GREEN)
            return
        if state in ("left", "failed"):
            self._finished = True
            self.lbl_status.config(
                text=text or ("已离开语音房" if state == "left" else "语音房已断开"),
                fg=(_RED if state == "failed" else _DIM))
            self.after(1500, self._just_close)

    # ---------- 成员网格 ----------

    def _redraw(self) -> None:
        """按当前名册重绘成员网格（配置变化/名册变化时调用）。"""
        c = self.canvas
        c.delete("all")
        self._rings = {}
        self._name_items = {}
        try:
            members = self.manager.member_list()
        except Exception:
            members = []
        w = max(c.winfo_width(), 1)
        h = max(c.winfo_height(), 1)
        if not members:
            c.create_text(w / 2, h / 2, text="等待房友…", fill=_DIM,
                          font=(FONT_FAMILY, 10))
            return
        cols = max(1, min(4, int((w - 12) // _TILE_W))) or 1
        rows = (len(members) + cols - 1) // cols
        ox = (w - cols * _TILE_W) / 2          # 网格水平居中
        oy = max(0.0, (h - rows * _TILE_H) / 2)
        try:
            me = int(getattr(self.manager.core, "uid", 0) or 0)
        except Exception:
            me = 0
        for idx, m in enumerate(members):
            uid = int(m.get("uid") or 0)
            nick = str(m.get("nick") or "") or f"用户{uid}"
            col, row = idx % cols, idx // cols
            self._draw_tile(uid, nick, ox + col * _TILE_W,
                            oy + row * _TILE_H, is_me=(uid == me))
        self._apply_levels()
        self._refresh_count()

    def _draw_tile(self, uid: int, nick: str, x: float, y: float,
                   is_me: bool = False) -> None:
        """画一个成员格子：高亮圈（底层）+ 头像 + 昵称。"""
        c = self.canvas
        cx, cy = x + _TILE_W / 2, y + _AVATAR / 2 + 6
        # 说话高亮圈：先画（被头像覆盖内半，仅外圈可见）；静默时与底色同色＝隐形
        self._rings[uid] = c.create_oval(
            cx - _RING_R, cy - _RING_R, cx + _RING_R, cy + _RING_R,
            outline=_BG, width=3)
        ax = cx - _AVATAR / 2
        ay = cy - _AVATAR / 2
        label = f"{nick}（我）" if is_me else nick
        drawn = False
        if self._avatar is not None:
            try:
                self._avatar.draw(c, ax, ay, _AVATAR, nick, uid=uid,
                                  font=(FONT_FAMILY, 20, "bold"))
                drawn = True
            except Exception:
                drawn = False
        if not drawn:                       # 无共享缓存 → 朴素色块圆形
            c.create_oval(ax, ay, ax + _AVATAR, ay + _AVATAR,
                          fill="#9e9e9e", outline="")
        self._name_items[uid] = c.create_text(
            cx, y + _AVATAR + 20, text=self._ellipsis(label, 8),
            fill="#444", font=(FONT_FAMILY, 9))

    @staticmethod
    def _ellipsis(text: str, limit: int) -> str:
        return text if len(text) <= limit else text[:limit - 1] + "…"

    def _apply_levels(self) -> None:
        """按最新电平刷新高亮（仅 itemconfig，不重建 item）。"""
        try:
            levels = self.manager.speaker_levels()
        except Exception:
            levels = {}
        try:
            me = int(getattr(self.manager.core, "uid", 0) or 0)
        except Exception:
            me = 0
        for uid, ring in self._rings.items():
            key = 0 if (uid == me) else uid
            on = float(levels.get(key, 0.0) or 0.0) >= _SPEAK_ON
            self.canvas.itemconfig(ring, outline=(_GREEN if on else _BG))
            name = self._name_items.get(uid)
            if name is not None:
                self.canvas.itemconfig(name,
                                       fill=(_GREEN if on else "#444"))

    def _refresh_count(self) -> None:
        """刷新「N/上限 人 · 直连 x/y」标题行。"""
        try:
            n = len(self.manager.member_list())
            cap = int(getattr(self.manager, "room_max", 0) or 0)
            conn = self.manager.connected_count()
            links = self.manager.link_count()
        except Exception:
            return
        cap_s = f"/{cap}" if cap else ""
        self.lbl_count.config(text=f"🎙 {n}{cap_s} 人 · 直连 {conn}/{links}",
                              fg=_GREEN if self.manager.in_room() else _DIM)

    # ---------- 轮询与交互 ----------

    def _tick(self) -> None:
        if self._closed:
            return
        if not self._finished:
            self._apply_levels()
            self._refresh_count()
            self._refresh_status()
        self.after(200, self._tick)

    def _refresh_status(self) -> None:
        """通话时长 + 连通状态（未被警告文字覆盖时刷新）。"""
        if self.lbl_status.cget("fg") == _AMBER:
            return
        try:
            if not self.manager.in_room():
                return
            d = int(self.manager.duration())
            self.lbl_status.config(
                text=f"语音房中 {d // 60:02d}:{d % 60:02d} · 建议戴耳机",
                fg=_GREEN)
        except Exception:
            pass

    def _apply_mic(self) -> None:
        try:
            on = self.manager.is_mic_on()
        except Exception:
            return
        self.btn_mic.config(text=("🎤 闭麦" if on else "🔇 开麦"),
                            fg=("#333" if on else _RED))

    def _toggle_mic(self, _e=None) -> None:
        try:
            self.manager.set_mic(not self.manager.is_mic_on())
        except Exception:
            pass
        self._apply_mic()

    def _leave(self, _e=None) -> None:
        """离开按钮：退房（状态由 left 事件收尾）。"""
        if self._finished:
            return
        try:
            self.manager.leave()
        except Exception:
            pass

    def _on_close(self) -> None:
        """✕：等同离开（未在房内直接收窗）。"""
        if not self._finished:
            self._finished = True
            try:
                self.manager.leave()
            except Exception:
                pass
        self._just_close()

    def _just_close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._on_leave is not None:
            try:
                self._on_leave()
            except Exception:
                pass
        self.destroy()