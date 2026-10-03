# -*- coding: utf-8 -*-
"""widgets/login_box.py —— 微信式登录窗（R73）。

设计对齐「先选服务器 → 再输账号密码」：
- 服务器选择默认折叠隐藏：平时只显示一行「服务器 · 名称 ip:port」+「更换」，
  点「更换」展开候选面板（UDP 自动发现列表 + 手动 IP/端口兜底）；
  没有可用目标时面板自动展开并提示手动输入。
- 账号/密码两行圆角输入框 + 微信绿(#07C160)整宽圆角登录按钮。
- 账号默认带出 prefs.default_account()；「记住此身份」映射 prefs.toggle_trust。
- 返回 {"nick","pwd","host","port","name","remember"} 或 None（取消）。

与 launcher 门禁同层：ChatWindow 构造路径不触发，既有 smoke 零回归。
"""
import tkinter as tk

import tkguard                       # noqa: F401  建 Tk 前安装跨线程守卫

from config import APP_NAME, CFG
from discovery import DiscoveryClient
from widgets.title_bar import DialogTitleBar

_GREEN = "#07C160"
_GREEN_HOVER = "#06AD56"
_FIELD_BG = "#F2F2F2"
_SUB = "#8a8f98"
_TX = "#1a1a1a"
_WHITE = "#ffffff"
_FAM = "Microsoft YaHei UI"
_VISIBILITY_TIMEOUT_MS = 2000


def _rrect_pts(x1, y1, x2, y2, r):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return (x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1)


def _force_foreground(win) -> bool:
    """尽力置顶并激活实际的 Win32 顶层窗口，不能使用 Tk 的 client HWND。"""
    try:
        if not win.winfo_exists() or not win.winfo_viewable():
            return False
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND,
                                       ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        hwnd = user32.GetAncestor(int(win.winfo_id()), 2)  # GA_ROOT: Tk wrapper
        if not hwnd or not user32.IsWindow(hwnd):
            return False
        placed = user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0,
                                     0x0001 | 0x0002)  # NOSIZE | NOMOVE
        activated = user32.SetForegroundWindow(hwnd)
        return bool(placed and activated)
    except Exception:
        return False


class LoginDialog:
    """微信式登录窗。result 为 {"nick","pwd","host","port","name","remember"}。"""

    def __init__(self, root, prefs, default_host="127.0.0.1",
                 default_port=None, *, owner_hidden=False) -> None:
        self.root = root
        self.prefs = prefs
        self.result = None
        self._disco = None
        self._poll_job = None
        self._raise_job = None
        self._panel_open = False

        dlg = tk.Toplevel(root)
        self.dlg = dlg
        dlg.withdraw()  # 布局完成再映射，避免空白窗和提前取得不可见窗口的 grab。
        dlg.title(APP_NAME)
        dlg.configure(bg=_WHITE)
        try:
            dlg.overrideredirect(True)
        except Exception:
            pass
        DialogTitleBar(dlg, APP_NAME, on_close=self._cancel)
        try:
            dlg.attributes("-topmost", True)
        except Exception:
            pass
        # transient 会跟随 owner 的 withdrawn 状态；独立登录的 root 仅是 Tcl 宿主。
        # 现有可见主窗作为 master 时保留窗口归属，不修改其它弹窗的宿主策略。
        if not owner_hidden and root.state() == "normal":
            dlg.transient(root)
        dlg.resizable(False, False)
        dlg.protocol("WM_DELETE_WINDOW", self._cancel)

        # ---- 当前目标服务器（折叠行显示）----
        ls = prefs.get("last_server") or {}
        if default_port is not None or default_host != "127.0.0.1":
            cur = {"host": default_host, "port": default_port or CFG.tcp_port,
                   "name": "手动指定", "src": "explicit"}
        elif ls.get("host"):
            cur = {"host": str(ls.get("host")),
                   "port": int(ls.get("port") or CFG.tcp_port),
                   "name": str(ls.get("name") or "上次服务器"), "src": "last"}
        else:
            cur = {"host": default_host, "port": default_port or CFG.tcp_port,
                   "name": "本机（默认）", "src": "fallback"}
        self.cur = cur

        body = tk.Frame(dlg, bg=_WHITE)
        body.pack(fill="both", expand=True, padx=44, pady=(6, 18))

        # ---- Logo + 应用名（微信式居中头部）----
        logo = tk.Canvas(body, width=84, height=84, bg=_WHITE,
                         highlightthickness=0, bd=0)
        logo.pack(pady=(10, 8))
        logo.create_oval(2, 2, 82, 82, fill=_GREEN, outline="")
        logo.create_text(42, 42, text="内", fill=_WHITE,
                         font=(_FAM, 30, "bold"))
        tk.Label(body, text=APP_NAME, bg=_WHITE, fg=_TX,
                 font=(_FAM, 16, "bold")).pack()

        # ---- 服务器行（默认折叠；点「更换」展开候选面板）----
        srv_row = tk.Frame(body, bg=_WHITE)
        srv_row.pack(fill="x", pady=(14, 0))
        self._srv_row = srv_row
        tk.Label(srv_row, text="服务器", bg=_WHITE, fg=_SUB,
                 font=(_FAM, 10)).pack(side="left")
        self._srv_lbl = tk.Label(srv_row, text="", bg=_WHITE, fg=_TX,
                                 font=(_FAM, 10), anchor="w")
        self._srv_lbl.pack(side="left", padx=(8, 0), fill="x", expand=True)
        self._srv_btn = tk.Label(srv_row, text="更换", bg=_WHITE, fg=_GREEN,
                                 font=(_FAM, 10), cursor="hand2")
        self._srv_btn.pack(side="right")
        self._srv_btn.bind("<Button-1>", lambda _e: self._toggle_panel())
        self._refresh_srv_lbl()

        # ---- 候选面板（默认隐藏）----
        _BORDER = "#E8E8E8"
        panel = tk.Frame(body, bg="#fafafa", highlightthickness=1,
                         highlightbackground=_BORDER)
        self._panel = panel
        self._cand_lb = tk.Listbox(panel, height=4, relief="flat", bd=0,
                                   font=(_FAM, 10), bg=_WHITE,
                                   selectbackground=_GREEN,
                                   selectforeground=_WHITE,
                                   highlightthickness=0)
        self._cand_lb.pack(fill="x", padx=8, pady=(8, 2))
        self._cand_lb.bind("<ButtonRelease-1>", lambda _e: self._pick_cand())

        hint = tk.Frame(panel, bg="#fafafa")
        hint.pack(fill="x", padx=8)
        tk.Label(hint, text="IP:", bg="#fafafa", fg=_SUB,
                 font=(_FAM, 9)).pack(side="left")
        self._ip_ent = tk.Entry(hint, width=13, relief="flat", bd=0,
                                bg=_WHITE, fg=_TX, font=(_FAM, 10))
        self._ip_ent.pack(side="left", padx=(2, 6))
        tk.Label(hint, text="端口:", bg="#fafafa", fg=_SUB,
                 font=(_FAM, 9)).pack(side="left")
        self._port_ent = tk.Entry(hint, width=6, relief="flat", bd=0,
                                  bg=_WHITE, fg=_TX, font=(_FAM, 10))
        self._port_ent.pack(side="left", padx=(2, 6))
        self._port_ent.insert(0, str(self.cur["port"]))
        btn_apply = tk.Label(hint, text="应用", bg="#fafafa", fg=_GREEN,
                             font=(_FAM, 9), cursor="hand2")
        btn_apply.pack(side="right")
        btn_apply.bind("<Button-1>", lambda _e: self._apply_manual())
        self._port_ent.bind("<Return>", lambda _e: self._apply_manual())

        self._cand_hint = tk.Label(panel, text="", bg="#fafafa", fg=_SUB,
                                   font=(_FAM, 8), anchor="w")
        self._cand_hint.pack(fill="x", padx=8, pady=(0, 6))

        # ---- 账号 / 密码（圆角输入框）----
        self._nick_ent = self._round_field(body, "账号")
        self._pwd_ent = self._round_field(body, "密码", show="*")
        self._nick_ent.bind("<Return>",
                            lambda _e: self._pwd_ent.focus_set())
        self._pwd_ent.bind("<Return>", lambda _e: self._login())

        default_nick = prefs.default_account() or ""
        self._nick_ent.insert(0, default_nick)

        # ---- 记住此身份 + 登录 ----
        self._rem = tk.BooleanVar(
            value=bool(default_nick and prefs.trusted_nick(default_nick)))
        tk.Checkbutton(body, text="记住此身份，下次自动登录（免弹窗直达）", variable=self._rem,
                       bg=_WHITE, fg=_SUB, activebackground=_WHITE,
                       font=(_FAM, 9), selectcolor=_WHITE,
                       highlightthickness=0, bd=0, anchor="w").pack(
            fill="x", pady=(8, 0))

        self._round_btn(body, "登 录", self._login, w=252, h=44)
        self._err_lbl = tk.Label(body, text="", bg=_WHITE, fg="#e03e3e",
                                 font=(_FAM, 9), anchor="w")
        self._err_lbl.pack(fill="x", pady=(6, 0))
        tk.Label(body, text="仅限局域网内使用 · 聊天数据不经过外网", bg=_WHITE,
                 fg=_SUB, font=(_FAM, 8)).pack(side="bottom", pady=(8, 0))

        dlg.bind("<Escape>", lambda _e: self._cancel())

        dlg.update_idletasks()
        w = dlg.winfo_reqwidth() + 12
        h = dlg.winfo_reqheight() + 12
        try:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            x, y = (sw - w) // 2, max(8, (sh - h) // 2 - 20)
        except Exception:
            x, y = 100, 100
        dlg.geometry("%dx%d+%d+%d" % (w, h, x, y))
        dlg.deiconify()
        dlg.update_idletasks()
        if not dlg.winfo_viewable():
            # WM 拒绝映射或宿主在此时关闭时，不能无限等待，也不能抓住输入。
            timeout_job = dlg.after(_VISIBILITY_TIMEOUT_MS, self._cancel)
            try:
                dlg.wait_visibility()
            except tk.TclError:
                self._stop()
                try:
                    if dlg.winfo_exists():
                        dlg.destroy()
                except tk.TclError:
                    pass  # 宿主也可能已被外部关闭。
                return
            finally:
                try:
                    dlg.after_cancel(timeout_job)
                except tk.TclError:
                    pass
            if not dlg.winfo_viewable():
                self._cancel()
                return
        dlg.grab_set()
        try:
            from widgets import ui_fx
            ui_fx.fade_in(dlg)
        except Exception:
            pass
        # 后台启动时 Windows 前台锁会吞掉 lift/focus_force（登录窗被其它窗口盖住，
        # 表现就是"进程在跑但没显示"）。SetWindowPos(HWND_TOPMOST) 不受前台锁限制，
        # 再延时重试一次覆盖窗口刚 map 时未生效的情况。
        self._activate(initial=True)
        self._raise_job = dlg.after(400, self._activate)

        self._start_disco()

    def _activate(self, initial=False):
        if not initial:
            self._raise_job = None
        try:
            if not self.dlg.winfo_exists() or not self.dlg.winfo_viewable():
                return
            self.dlg.lift()
            _force_foreground(self.dlg)
            # 重试不能把用户正在输入密码的焦点又移回账号框。
            if initial or self.dlg.focus_get() is None:
                self._nick_ent.focus_force()
        except tk.TclError:
            pass

    # ---------- 自绘圆角输入框 / 按钮 ----------
    def _round_field(self, parent, label, show=""):
        row = tk.Frame(parent, bg=_WHITE)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=_WHITE, fg=_SUB,
                 font=(_FAM, 10)).pack(side="left", padx=(0, 10))
        cv = tk.Canvas(row, width=170, height=36, bg=_WHITE,
                       highlightthickness=0, bd=0)
        cv.pack(side="right", fill="x", expand=True)
        cv.create_polygon(_rrect_pts(0, 0, 170, 36, 18), smooth=True,
                          fill=_FIELD_BG, outline="")
        ent = tk.Entry(cv, bg=_FIELD_BG, fg=_TX, relief="flat", bd=0,
                       insertbackground=_TX, show=show,
                       font=(_FAM, 11))
        ent.place(x=12, y=5, relwidth=1.0, width=-24)
        return ent

    def _round_btn(self, parent, text, cmd, w=252, h=44, bg=_GREEN):
        cv = tk.Canvas(parent, width=w, height=h, bg=_WHITE,
                       highlightthickness=0, bd=0)
        cv.pack(pady=(6, 0))
        state = {"hover": False}

        def draw():
            cv.delete("all")
            col = _GREEN_HOVER if state["hover"] else bg
            cv.create_polygon(_rrect_pts(0, 0, w, h, h // 2), smooth=True,
                              fill=col, outline="")
            cv.create_text(w // 2, h // 2, text=text, fill=_WHITE,
                           font=(_FAM, 13, "bold"))
        cv.bind("<Enter>", lambda _e: (state.__setitem__("hover", True),
                                       draw()))
        cv.bind("<Leave>", lambda _e: (state.__setitem__("hover", False),
                                       draw()))
        cv.bind("<Button-1>", lambda _e: cmd())
        draw()
        return cv

    # ---------- 服务器选择 ----------
    def _refresh_srv_lbl(self):
        c = self.cur
        self._srv_lbl.config(text=f"· {c['name']}  {c['host']}:{c['port']}")

    def _toggle_panel(self):
        if self._panel_open:
            self._panel.pack_forget()
            self._panel_open = False
            self._srv_btn.config(text="更换")
        else:
            self._panel.pack(fill="x", pady=(6, 0), after=self._srv_row)
            self._panel_open = True
            self._srv_btn.config(text="收起")
            self._fill_cands(force=True)

    def _start_disco(self):
        if not CFG.discovery_enabled:
            # Explicit/manual host remains the sole target when discovery is
            # disabled; do not create a listener or replace ``self.cur``.
            self._disco = None
            self._poll()
            return
        try:
            self._disco = DiscoveryClient(CFG)
            self._disco.start()
        except Exception:
            self._disco = None
        self._poll()

    def _poll(self):
        try:
            if not self.dlg.winfo_exists():
                return
            if self._disco is not None:
                cands = self._disco.candidates()
                # 兜底态（未指定/未发现）有候选到达 → 自动切到第一个
                if cands and self.cur["src"] == "fallback":
                    ip, name, port = cands[0]
                    self.cur = {"host": ip, "port": port,
                                "name": name, "src": "disco"}
                    self._refresh_srv_lbl()
                    if self._panel_open:
                        self._fill_cands(force=True)
                elif self._panel_open:
                    self._fill_cands()
        finally:
            try:
                if self.dlg.winfo_exists():
                    self._poll_job = self.dlg.after(1500, self._poll)
            except Exception:
                self._poll_job = None

    def _fill_cands(self, force=False):
        if not self._panel_open:
            return
        cands = self._disco.candidates() if self._disco else []
        if not cands:
            self._cand_hint.config(text="未发现服务器（自动发现中）"
                                        "· 可手动输入 IP 与端口")
            return
        self._cand_hint.config(text="双击或点选自动发现的服务器")
        if self._cand_lb.size() != len(cands):
            self._cand_lb.delete(0, "end")
            for ip, name, port in cands:
                self._cand_lb.insert("end", f"{name}  {ip}:{port}")

    def _pick_cand(self):
        sel = self._cand_lb.curselection()
        if not sel:
            return
        cands = self._disco.candidates() if self._disco else []
        if 0 <= sel[0] < len(cands):
            ip, name, port = cands[sel[0]]
            self.cur = {"host": ip, "port": port, "name": name, "src": "disco"}
            self._refresh_srv_lbl()
            self._toggle_panel()

    def _apply_manual(self):
        ip = self._ip_ent.get().strip() or self.cur["host"]
        try:
            port = int(self._port_ent.get().strip() or self.cur["port"])
        except ValueError:
            self._err_lbl.config(text="端口需为数字")
            return
        self.cur = {"host": ip, "port": port, "name": ip, "src": "manual"}
        self._refresh_srv_lbl()
        if self._panel_open:
            self._toggle_panel()

    # ---------- 登录 / 取消 ----------
    def _login(self):
        nick = self._nick_ent.get().strip()
        if not nick:
            self._err_lbl.config(text="请输入账号（昵称）")
            self._nick_ent.focus_set()
            return
        self.result = {"nick": nick, "pwd": self._pwd_ent.get(),
                       "host": self.cur["host"], "port": int(self.cur["port"]),
                       "name": self.cur["name"],
                       "remember": bool(self._rem.get())}
        self._stop()
        self.dlg.destroy()

    def _cancel(self):
        self._stop()
        self.dlg.destroy()

    def _stop(self):
        if self._raise_job is not None:
            try:
                self.dlg.after_cancel(self._raise_job)
            except tk.TclError:
                pass
            self._raise_job = None
        try:
            if self.dlg.grab_current() == self.dlg:
                self.dlg.grab_release()
        except tk.TclError:
            pass
        if self._poll_job is not None:
            try:
                self.dlg.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        if self._disco is not None:
            try:
                self._disco.stop.set()
            except Exception:
                pass
            self._disco = None


def show_login(master=None, prefs=None, default_host="127.0.0.1",
               default_port=None) -> dict | None:
    """弹微信式登录窗（模态）。返回 {"nick","pwd","host","port","name",
    "remember"} 或 None（取消/关闭）。"""
    from prefs import Prefs
    prefs = prefs or Prefs()
    root = master or tk.Tk()
    if master is None:
        root.withdraw()  # 宿主不显示、不占任务栏；登录窗不 transient 到它。
        from dpi import fix_scaling               # R43C 高分屏缩放校正
        fix_scaling(root)
    once = master is None
    box = None
    try:
        box = LoginDialog(root, prefs, default_host, default_port,
                          owner_hidden=once)
        try:
            if box.dlg.winfo_exists():
                root.wait_window(box.dlg)
        except tk.TclError:
            pass  # 等待期间外部关闭宿主，按取消处理并执行 finally 清理。
        return box.result
    finally:
        if box is not None:
            box._stop()  # 外部销毁/异常退出也停止发现线程与定时回调。
        if once:
            try:
                root.destroy()
            except tk.TclError:
                pass
