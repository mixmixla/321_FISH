# -*- coding: utf-8 -*-
"""launcher.py —— 登录门禁：微信式登录窗（先选服务器→再输账号密码）。

- 微信式登录窗：服务器行默认折叠隐藏（UDP 自动发现 + 手动 IP 兜底），
  账号/密码输入后点「登录」，返回 {nick,pwd,host,port,name,remember}。
- 快速路径：已「记住此身份」的默认账号且无本机解锁码 → 自动登录直达上次服务器。
- 本机密码锁：有解锁码则先弹 PasscodeBox（Scrim 全屏遮罩后），通过才进主窗。
- 切账号：ChatWindow.request_switch_account() → run_chat 返回 "switch" → 外层重弹登录窗。
门禁只在此层，ChatWindow 构造路径不触发，保证直接构造的既有 smoke 零回归。
"""
import tkinter as tk

import tkguard                       # 跨线程 Tk 守卫（登录门禁在 client 加载前建 Tk，须提前接入）

import auth
from prefs import Prefs
from config import CFG, bootlog
from widgets.passcode import PasscodeBox
from widgets.scrim import Scrim
from widgets import dialogbox
from widgets.login_box import show_login


def passcode_gate(check) -> bool:
    """全屏 Scrim 遮罩 + 解锁框。check(code)->bool；通过返回 True，否则 False。"""
    root = tk.Tk()
    from dpi import fix_scaling               # R43C 高分屏缩放校正
    fix_scaling(root)
    dialogbox._hide_owner(root)               # 不用 root.withdraw：会同步隐藏 transient 子窗
    state = {"ok": False}
    scrim = Scrim(root, fullscreen=True)
    scrim.show()

    def finish(ok: bool) -> None:
        state["ok"] = ok
        scrim.hide()
        root.after(320, root.destroy)

    PasscodeBox(root, verifier=lambda c: check(c),
                on_ok=lambda: finish(True),
                on_cancel=lambda: finish(False))
    root.mainloop()
    return state["ok"]


def run_chat(host: str, port, prefs: Prefs, nick: str, pwd: str = "") -> str:
    """跑一轮完整主会话；返回退出语义 "quit"|"switch"。"""
    import client
    import client_core
    core = client_core.ClientCore(host=host, port=port, nick=nick, pwd=pwd)
    app = client.ChatWindow(core, prefs_path=prefs._path)
    core.start()
    # 启动自恢复：进入主循环后强制置顶亮出主窗，避免"进程在但窗口不出现"。
    # 必须在 mainloop 之后（deiconify 对尚未 map 的窗口无效），故用 after 调度。
    app.root.after(40, app.show_main)
    app.root.mainloop()
    app.teardown_quiet()
    return app._exit_reason


def _last_server(prefs: Prefs, host: str, port) -> tuple:
    """上次使用的服务器作为快速路径默认目标；无记录则回落传入默认值。"""
    ls = prefs.get("last_server") or {}
    if ls.get("host"):
        try:
            return str(ls["host"]), int(ls.get("port") or CFG.tcp_port)
        except Exception:
            pass
    return host, port or CFG.tcp_port


def launch(host: str, port=None, prefs: Prefs | None = None) -> int:
    """进程入口：微信式登录门禁（先选服务器→再输账号密码）+ 会话循环。

    - 已「记住此身份」的默认账号且无本机解锁码 → 自动登录直达上次服务器；
      否则一律弹微信式登录窗（服务器行默认折叠隐藏，可点「更换」展开）。
    - 登录窗返回后：记住所选服务器 → 本机密码锁（若有）→ run_chat 带
      host/port/pwd 进入主会话；「切换账号」回到登录窗循环。
    - R35 多账号：档案随账号切换（pinned/muted/archived/drafts）。"""
    prefs = prefs or Prefs()
    switching = False
    for _ in range(8):
        prefs = Prefs(prefs._path)     # 每轮重读：run_chat 内的变更已落盘
        # ---- 快速路径：已记住此身份的默认账号 → 直达上次服务器 ----
        if not switching:
            nick = prefs.default_account()
            if nick and prefs.trusted_nick(nick) and not prefs.has_passcode():
                h, p = _last_server(prefs, host, port)
                bootlog(f"launch: auto-login trusted {nick!r} -> {h}:{p}")
                prefs.remember_account(nick)
                prefs.switch_profile(nick)
                reason = run_chat(h, p, prefs, nick, "")
                bootlog(f"launch: run_chat returned {reason!r}")
                if reason != "switch":
                    return 0
                switching = True
                continue
        # ---- 微信式登录窗：先选服务器，再输账号密码 ----
        r = show_login(prefs=prefs, default_host=host, default_port=port)
        if not r:
            bootlog("launch: login cancelled")
            return 0
        nick = r["nick"]
        try:
            prefs.set("last_server", {"host": r["host"], "port": int(r["port"]),
                                      "name": r["name"]})
        except Exception:
            pass
        if r["remember"]:
            try:
                prefs.toggle_trust(nick)
            except Exception:
                pass
        if prefs.has_passcode():
            bootlog("launch: passcode_gate shown")
            stored = prefs.passcode()
            if not passcode_gate(lambda c, s=stored: auth.verify(c, s)):
                bootlog("launch: passcode rejected")
                return 0
        prefs.remember_account(nick)
        prefs.switch_profile(nick)
        bootlog(f"launch: run_chat start nick={nick!r}")
        reason = run_chat(r["host"], int(r["port"]), prefs, nick, r["pwd"])
        bootlog(f"launch: run_chat returned {reason!r}")
        if reason != "switch":
            return 0
        switching = True
    return 0