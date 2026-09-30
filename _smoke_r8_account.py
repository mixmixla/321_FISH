# -*- coding: utf-8 -*-
"""R8 冒烟：launcher 登录门禁（微信式登录窗 + 记住此身份自动登录）。

monkeypatch run_chat / show_login，不启真实 UI：
- A: 已「记住此身份」的默认账号且无解锁码 → 自动登录直达，run_chat 收到昵称+空密码
- B: run_chat 返回 "switch" → 回到登录窗循环（最多 8 轮），host/pwd 随登录窗结果传入
- C: 无默认账号且弹窗取消 → 直接退出，run_chat 不被调用
- D: 登录窗返回账号/密码/服务器 → run_chat 收到完整参数，勾选记住 → trusted_nick 置位
"""
import tempfile
from pathlib import Path

import launcher
from prefs import Prefs


def main() -> int:
    tmp = Path(tempfile.mkdtemp()) / "prefs.json"
    p = Prefs(str(tmp))
    results = []
    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    orig_run = launcher.run_chat
    orig_show = launcher.show_login

    try:
        # A: 记住此身份 + 无解锁码 → 自动登录，不弹登录窗，run_chat 收到昵称（空密码）
        p.set_default_account("账号A")
        p.toggle_trust("账号A")
        calls = []
        launcher.run_chat = lambda host, port, prefs, nick, pwd="": (
            calls.append((host, nick, pwd)) or "quit")
        rc = launcher.launch("127.0.0.1", None, prefs=p)
        check("auto-login trusted account",
              calls == [("127.0.0.1", "账号A", "")], calls)
        check("launch rc", rc == 0)

        # B: 切账号语义：run_chat 返回 "switch" → 重弹登录窗（最多 8 轮）
        calls = []
        shown = []
        fake = {"nick": "账号B", "pwd": "pw", "host": "10.0.0.2",
                "port": 8001, "name": "t", "remember": False}

        def fake_show(prefs=None, default_host="127.0.0.1", default_port=None):
            shown.append((default_host, default_port))
            return dict(fake)

        launcher.show_login = fake_show
        launcher.run_chat = lambda host, port, prefs, nick, pwd="": (
            calls.append((host, nick, pwd)) or "switch")
        launcher.launch("127.0.0.1", None, prefs=p)
        check("switch loops to login dialog",
              len(calls) == 8 and len(shown) == 7, f"calls={len(calls)} shown={len(shown)}")
        check("switch carries dialog host/pwd",
              calls[1] == ("10.0.0.2", "账号B", "pw"), calls[1])

        # C: 无默认账号且登录窗取消 → 直接退出，run_chat 不被调用
        p.set_default_account(None)
        p.set("trusted_nicks", [])
        launcher.show_login = lambda prefs=None, default_host="127.0.0.1", default_port=None: None
        calls = []
        launcher.run_chat = lambda host, port, prefs, nick, pwd="": (
            calls.append(nick) or "quit")
        rc = launcher.launch("127.0.0.1", None, prefs=p)
        check("cancel login exits cleanly", rc == 0 and calls == [], calls)

        # D: 登录窗返回完整参数 → run_chat 收到；勾选记住 → trusted_nick 置位
        p.set("trusted_nicks", [])
        fake["remember"] = True
        launcher.show_login = lambda prefs=None, default_host="127.0.0.1", default_port=None: dict(fake)
        calls = []
        launcher.run_chat = lambda host, port, prefs, nick, pwd="": (
            calls.append((host, nick, pwd)) or "quit")
        launcher.launch("127.0.0.1", None, prefs=p)
        check("login dialog result forwarded",
              calls == [("10.0.0.2", "账号B", "pw")], calls)
        p2 = Prefs(p._path)          # launch 内部每轮重读 Prefs，外层缓存已过期 → 重新读盘
        check("remember sets trust", p2.trusted_nick("账号B"))
        check("last_server persisted",
              (p2.get("last_server") or {}).get("host") == "10.0.0.2",
              p2.get("last_server"))
    finally:
        launcher.run_chat = orig_run
        launcher.show_login = orig_show

    print("\n".join(results))
    print("GUI ACCOUNT SMOKE OK" if ok else "GUI ACCOUNT SMOKE FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
