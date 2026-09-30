# -*- coding: utf-8 -*-
"""R38/R39 1v1 语音通话窗：来电（接听/拒绝）· 呼叫中 · 通话中 · 模式切换 · 挂断。

- 状态完全由 CallManager 的 call 事件驱动（update_state），窗口自身不判状态机
- R39A 默认全双工（连通即双方常开麦，建议戴耳机防回声）；「🖐/🎤」一键切 PTT，
  热生效；PTT 模式按住「讲话」开麦、松开停，空格键等同按住
- 通话中点 ✕ 关闭 = 挂断；结束/失败 1.6s 后自动关窗
- R45 视频：双方具备摄像头能力时「📷」开关热生效；对端画面嵌在通话窗内
  （320×240 PNG @10fps，Tk 原生解码）
- D15：「🖥 共享屏幕」换采集源为屏幕（与摄像头互斥，再点＝停止）；
  「🅿 画中画」把画面脱离通话窗成无边框置顶小窗（widgets/pip_window.py）
"""
import base64
import tkinter as tk

FONT_FAMILY = "Microsoft YaHei UI"

_GREEN = "#2e9e5b"
_RED = "#d9534f"
_BLUE = "#4c7de8"
_GREY = "#f2f3f5"
_AMBER = "#c77700"


class CallWindow(tk.Toplevel):
    """语音通话窗（置顶小窗；一个客户端同开一个，由 client 持引用复用）。"""

    def __init__(self, master, *, manager, peer_nick: str = "",
                 persist_mode=None, persist_video=None):
        super().__init__(master)
        self.manager = manager
        self._persist_mode = persist_mode    # 模式切换回调（client 写 prefs）
        self._persist_video = persist_video  # 摄像头开关回调（client 写 prefs）
        self.title("语音通话")
        self.geometry("300x360")
        self.resizable(False, False)
        self.configure(bg="#ffffff")
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._nick = peer_nick
        self._state = "idle"
        self._closed = False

        tk.Label(self, text="📞", font=(FONT_FAMILY, 38),
                 bg="#ffffff").pack(pady=(16, 0))
        self.lbl_nick = tk.Label(self, text=peer_nick or " ", name="call_nick",
                                 font=(FONT_FAMILY, 13, "bold"),
                                 bg="#ffffff", fg="#222")
        self.lbl_nick.pack()
        self.lbl_status = tk.Label(self, text=" ", name="call_status",
                                   font=(FONT_FAMILY, 10),
                                   bg="#ffffff", fg="#888")
        self.lbl_status.pack(pady=(2, 6))

        # PTT 按钮（半双工模式通话中才显示）：Label 当按钮用，好按住变色
        self.btn_ptt = tk.Label(self, text="按住 讲话", name="call_ptt",
                                font=(FONT_FAMILY, 13, "bold"),
                                bg=_GREY, fg="#333", padx=26, pady=16,
                                cursor="hand2")
        self.btn_ptt.bind("<ButtonPress-1>", self._ptt_on)
        self.btn_ptt.bind("<ButtonRelease-1>", self._ptt_off)
        self.bind("<KeyPress-space>", self._ptt_on)
        self.bind("<KeyRelease-space>", self._ptt_off)

        # R39A 模式切换（通话中显示）+ 全双工戴耳机提示
        self.btn_mode = tk.Button(self, name="call_mode",
                                  font=(FONT_FAMILY, 9), relief="flat",
                                  cursor="hand2", bg="#ffffff", fg="#4c7de8",
                                  activebackground="#ffffff",
                                  activeforeground="#2a5bc0",
                                  command=self._toggle_mode)
        self.lbl_hint = tk.Label(self, text="建议戴耳机，避免回声",
                                 name="call_hint", font=(FONT_FAMILY, 8),
                                 bg="#ffffff", fg="#999")

        # R45 视频区：摄像头开关（双方支持才显示）+ 对端画面（开摄像头后显示）
        self.btn_cam = tk.Label(self, text="📷 打开摄像头", name="call_cam",
                                font=(FONT_FAMILY, 10), bg=_GREY, fg="#333",
                                padx=18, pady=6, cursor="hand2")
        self.btn_cam.bind("<ButtonPress-1>", self._toggle_cam)
        # D15 屏幕共享 + 画中画（共享需本机可抓屏，画中画需有画面）
        self.btn_share = tk.Label(self, text="🖥 共享屏幕", name="call_share",
                                  font=(FONT_FAMILY, 10), bg=_GREY, fg="#333",
                                  padx=18, pady=6, cursor="hand2")
        self.btn_share.bind("<ButtonPress-1>", self._toggle_share)
        self.btn_pip = tk.Label(self, text="🅿 画中画", name="call_pip",
                                font=(FONT_FAMILY, 10), bg=_GREY, fg="#333",
                                padx=18, pady=6, cursor="hand2")
        self.btn_pip.bind("<ButtonPress-1>", self._toggle_pip)
        self._pip = None                 # D15 画中画悬浮窗（惰性创建）
        self._last_png = None            # 最近一帧（远端优先），开画中画时立即补帧
        self._got_remote = False         # 是否已收到对端画面（本地镜像不覆盖远端）
        self.lbl_video = tk.Label(self, name="call_video", bg="#000000")
        self.lbl_local = tk.Label(self, name="call_local", bg="#111111")
        self._photo = None               # PhotoImage 引用（防 GC 花屏）
        self._photo_local = None         # 本端镜像预览 PhotoImage 引用

        # 来电双按钮（incoming 才显示）
        self.frm_incoming = tk.Frame(self, bg="#ffffff", name="call_incoming")
        tk.Button(self.frm_incoming, text="✓ 接听", name="call_accept",
                  font=(FONT_FAMILY, 11, "bold"), bg=_GREEN, fg="#ffffff",
                  relief="flat", cursor="hand2", width=8,
                  command=self._accept).pack(side="left", padx=8)
        tk.Button(self.frm_incoming, text="✕ 拒绝", name="call_reject",
                  font=(FONT_FAMILY, 11, "bold"), bg=_RED, fg="#ffffff",
                  relief="flat", cursor="hand2", width=8,
                  command=self._reject).pack(side="left", padx=8)

        # 挂断/关闭（呼叫中与通话中显示）
        self.btn_end = tk.Button(self, text="挂断", name="call_end",
                                 font=(FONT_FAMILY, 11, "bold"),
                                 bg=_RED, fg="#ffffff", relief="flat",
                                 cursor="hand2", width=8,
                                 command=self._end)

        self.after(1000, self._tick)
        self.lift()
        self.focus_force()

    # ---------- 事件驱动（client 转发 call 事件） ----------
    def update_state(self, ev: dict) -> None:
        """按 CallManager 事件刷新界面；窗口已关则忽略。"""
        if self._closed:
            return
        state = str(ev.get("state") or "")
        text = str(ev.get("text") or "")
        nick = str(ev.get("nick") or "")
        if nick:
            self._nick = nick
            self.lbl_nick.config(text=nick)
        if state == "warn":                    # 非致命提示：只刷状态行
            if text:
                self.lbl_status.config(text=text, fg=_AMBER)
            return
        if state == "video_frame":             # R45 对端视频帧：仅刷画面
            self._show_video_frame(ev.get("png"))
            return
        if state == "video_local":             # 任务4 本端镜像预览
            self._show_local_frame(ev.get("png"))
            return
        if state == "video":                   # R45 本端摄像头开关状态
            self._apply_video(ev)
            return
        self._state = state
        if state == "incoming":
            self.lbl_status.config(text=text or "请求语音通话", fg=_BLUE)
            self.btn_ptt.pack_forget()
            self.btn_mode.pack_forget()
            self.lbl_hint.pack_forget()
            self.btn_end.pack_forget()
            self.frm_incoming.pack(pady=(12, 4))
        elif state == "ringing":
            self.lbl_status.config(text=text or "正在呼叫…", fg="#888")
            self.frm_incoming.pack_forget()
            self.btn_ptt.pack_forget()
            self.btn_mode.pack_forget()
            self.lbl_hint.pack_forget()
            self.btn_end.pack(pady=(10, 8))
        elif state == "connecting":
            self.lbl_status.config(text=text or "建立直连…", fg="#888")
            self.frm_incoming.pack_forget()
            self.btn_ptt.pack_forget()
            self.btn_mode.pack_forget()
            self.lbl_hint.pack_forget()
        elif state == "incall":
            self.lbl_status.config(text="已连通", fg=_GREEN)
            self.frm_incoming.pack_forget()
            self.btn_end.pack(pady=(10, 8))
            self.btn_mode.pack(pady=(0, 2), before=self.btn_end)
            self._apply_mode()
            # R45/D15 视频开关：按支持情况逐个出现（顺序：摄像头 / 共享 / 画中画）
            if self.manager.video_supported():
                self.btn_cam.config(text=("📷 关闭摄像头" if
                                          self.manager.is_video_on()
                                          else "📷 打开摄像头"))
                self.btn_cam.pack(pady=(2, 2), before=self.btn_mode)
            else:
                self.btn_cam.pack_forget()
            if self.manager.screen_supported():
                self.btn_share.config(text=("🖥 停止共享" if
                                            self._video_from_screen()
                                            else "🖥 共享屏幕"))
                self.btn_share.pack(pady=(2, 2), before=self.btn_mode)
            else:
                self.btn_share.pack_forget()
            if self._last_png:
                self.btn_pip.pack(pady=(2, 2), before=self.btn_mode)
            else:
                self.btn_pip.pack_forget()

        elif state in ("ended", "failed"):
            self._ptt_off()
            self.frm_incoming.pack_forget()
            self.btn_ptt.pack_forget()
            self.btn_mode.pack_forget()
            self.lbl_hint.pack_forget()
            self.btn_cam.pack_forget()
            self.btn_share.pack_forget()
            self.btn_pip.pack_forget()
            self._close_pip()
            self._hide_video()
            self.btn_end.config(text="关闭", command=self._just_close)
            self.btn_end.pack(pady=(10, 8))
            self.lbl_status.config(
                text=text or "通话结束",
                fg=(_RED if state == "failed" else "#888"))
            self.after(1600, self._just_close)   # 自动收窗

    # ---------- R39A 模式切换 ----------
    def _apply_mode(self) -> None:
        """按当前模式刷新模式钮/PTT 钮/提示行（全双工藏 PTT，半双工反之）。"""
        duplex = bool(self.manager.is_duplex())
        if duplex:
            self.btn_mode.config(text="🖐 切换为按住说话")
            self.btn_ptt.pack_forget()
            self.lbl_hint.pack(after=self.btn_mode)
        else:
            self.btn_mode.config(text="🎤 切换为全双工")
            self.lbl_hint.pack_forget()
            if self._state == "incall":
                self.btn_ptt.config(bg=_GREY, fg="#333", text="按住 讲话")
                self.btn_ptt.pack(pady=(0, 2), before=self.btn_mode)

    def _toggle_mode(self) -> None:
        if self._state != "incall":
            return
        new = not self.manager.is_duplex()
        self.manager.set_duplex(new)           # 热生效（含麦克风开关）
        if self._persist_mode is not None:
            try:
                self._persist_mode(new)        # client 写 prefs
            except Exception:
                pass
        self._apply_mode()
        self.lbl_status.config(text=("全双工 · 建议戴耳机" if new else "PTT 按住说话"),
                               fg=_BLUE)

    # ---------- R45 视频 ----------
    def _toggle_cam(self, _e=None) -> None:
        if self._state != "incall" or not self.manager.video_supported():
            return
        on = not self.manager.is_video_on()
        if on:
            self.btn_cam.config(text="📷 启动中…")     # 实际状态由 video 事件确认
        self.manager.set_video(on)
        if self._persist_video is not None:
            try:
                self._persist_video(on)                # client 写 prefs
            except Exception:
                pass

    def _apply_video(self, ev: dict) -> None:
        """本端视频开关结果（异步启动完成/失败）刷新；按来源区分按钮文案。"""
        text = str(ev.get("text") or "")
        src = str(ev.get("source") or self.manager.video_source())
        if ev.get("on"):
            self.btn_cam.config(text="📷 关闭摄像头" if src == "cam"
                                else "📷 打开摄像头")
            self.btn_share.config(text="🖥 停止共享" if src == "screen"
                                  else "🖥 共享屏幕")
            # 画中画布局：远端主画面居中（保留 320×240 content 尺寸），
            # 本端镜像以小窗叠在右上角（place 用 content 尺寸，不回拉宽度）
            self.lbl_video.place_forget()
            self.lbl_video.place(relx=0.5, rely=0.5, anchor="center")
            self.lbl_local.place(relx=1.0, x=-8, y=8, anchor="ne")
            self.geometry("340x460")
            if text:
                self.lbl_status.config(text=text, fg=_AMBER)
        else:
            self.btn_cam.config(text="📷 打开摄像头")
            self.btn_share.config(text="🖥 共享屏幕")
            self._hide_video()
            if text:
                self.lbl_status.config(text=text, fg=_AMBER)

    # ---------- D15 屏幕共享 / 画中画 ----------

    def _video_from_screen(self) -> bool:
        """当前视频是否来自屏幕共享（开关文案用）。"""
        try:
            return bool(self.manager.is_video_on()
                        and self.manager.video_source() == "screen")
        except Exception:
            return False

    def _toggle_share(self, _e=None) -> None:
        """共享屏幕：与摄像头互斥（开启即换采集源；再点＝停止）。"""
        if self._state != "incall" or not self.manager.screen_supported():
            return
        if self._video_from_screen():
            self.manager.set_video(False)
            return
        if self.manager.is_video_on():          # 摄像头开着 → 先关，避免双源抢占
            self.manager.set_video(False)
        self.btn_share.config(text="🖥 启动中…")
        self.manager.set_video(True, source="screen")

    def _toggle_pip(self, _e=None) -> None:
        """画中画：无边框置顶小窗显示最新帧；已开则收窗。"""
        if self._pip is not None and self._pip.alive():
            self._close_pip()
            return
        from widgets.pip_window import PipWindow
        self._pip = PipWindow(self, on_close=self._on_pip_closed,
                              title=f"与 {self._nick or '对方'} 通话")
        if not self._last_png:
            self._pip.set_hint("等待画面…")
        self._push_pip()

    def _on_pip_closed(self) -> None:
        self._pip = None

    def _close_pip(self) -> None:
        p = self._pip
        self._pip = None
        if p is not None:
            try:
                p.close()
            except Exception:
                pass

    def _push_pip(self) -> None:
        """把最新帧推给画中画窗（无画面/未开窗时无操作）。"""
        p = self._pip
        if p is not None and p.alive() and self._last_png:
            p.set_frame(self._last_png)

    def _show_video_frame(self, png) -> None:
        """对端视频帧：Tk 原生 PNG 解码（10fps 内开销可忽略）。"""
        if self._state != "incall" or not png:
            return
        self._got_remote = True
        self._last_png = png
        try:
            self._photo = tk.PhotoImage(data=base64.b64encode(png))
            self.lbl_video.config(image=self._photo, width=self._photo.width(),
                                  height=self._photo.height())
        except Exception:
            pass
        self._push_pip()
        if self._state == "incall" and not self.btn_pip.winfo_manager():
            self.btn_pip.pack(pady=(2, 2), before=self.btn_mode)

    def _show_local_frame(self, png) -> None:
        """本端镜像预览（画中画小窗）：1/4 抽稀 + 左右镜像翻转（贴主流
        IM「自拍镜像」观感；PIL 翻转重编码，仅预览小图，开销可接受）。"""
        if self._state != "incall" or not png:
            return
        try:
            from io import BytesIO
            from PIL import Image
            img = Image.open(BytesIO(png)).convert("RGB")
            w, h = img.size
            # 压到 ≤160 宽做小窗，翻转后转 PNG
            scale = max(1, w // 160)
            img = img.reduce(scale).transpose(Image.FLIP_LEFT_RIGHT)
            bio = BytesIO()
            img.save(bio, format="PNG")
            self._photo_local = tk.PhotoImage(
                data=base64.b64encode(bio.getvalue()))
            self.lbl_local.config(image=self._photo_local)
        except Exception:
            pass
        # D15：没有对端画面时，画中画退而显示本端镜像（有远端则保持远端优先）
        if not self._got_remote:
            self._last_png = png
            self._push_pip()
            if self._state == "incall" and not self.btn_pip.winfo_manager():
                self.btn_pip.pack(pady=(2, 2), before=self.btn_mode)

    def _hide_video(self) -> None:
        self.lbl_video.place_forget()
        self.lbl_local.place_forget()
        self._photo = None
        self._photo_local = None
        self.lbl_video.config(image="")
        self.lbl_local.config(image="")
        self.geometry("300x360")
        # D15：视频下线则画中画一并收起（避免留一帧冻结画面）
        self._close_pip()
        self.btn_pip.pack_forget()
        self._last_png = None
        self._got_remote = False

    # ---------- 交互 ----------
    def _ptt_on(self, _e=None) -> None:
        if self._state == "incall" and not self.manager.is_duplex():
            self.btn_ptt.config(bg=_BLUE, fg="#ffffff", text="讲话中…")
            self.manager.set_ptt(True)

    def _ptt_off(self, _e=None) -> None:
        self.manager.set_ptt(False)            # 非 incall 时为安全空操作
        if self._state == "incall" and not self.manager.is_duplex():
            self.btn_ptt.config(bg=_GREY, fg="#333", text="按住 讲话")

    def _accept(self) -> None:
        self.manager.accept_call()

    def _reject(self) -> None:
        self.manager.reject_call()

    def _end(self) -> None:
        self.manager.end_call()

    def _tick(self) -> None:
        if self._closed:
            return
        if self._state == "incall":
            d = int(self.manager.duration())
            suffix = " 🎧" if self.manager.is_duplex() else ""
            self.lbl_status.config(text=f"通话中 {d // 60:02d}:{d % 60:02d}{suffix}",
                                   fg=_GREEN)
        self.after(1000, self._tick)

    def _on_close(self) -> None:
        """✕：通话中/来电一律先收尾（来电=拒绝，其余=挂断）。"""
        if self._state == "incoming":
            self.manager.reject_call()
        elif self._state != "idle":
            self.manager.end_call()
        self._just_close()

    def _just_close(self) -> None:
        if not self._closed:
            self._closed = True
            self._close_pip()          # D15：通话窗关闭 → 画中画一并收窗
            self.destroy()
