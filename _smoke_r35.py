# -*- coding: utf-8 -*-
"""R35 生态包冒烟（真服务器 + 真客户端核心）：
- Bots：known 含机器人；私聊发回声 bot 得复读；发送方收到自己消息回显
- 贴纸商店：拉目录 → sticker_shop_list；订阅 → sticker_sub 全量回帧；
  面板按订阅过滤（subscribed_stickers）
- 多档案：按昵称历史子目录隔离；prefs 档案切换 pinned/drafts 跟随
"""
import os
import socket
import tempfile
import threading
import time
from dataclasses import replace

import bots as _bots
from client_core import ClientCore, _nick_safe
from config import CFG
from prefs import Prefs
from server import Hub, serve as serve_tcp


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="r35_")
    ok = True
    results = []

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    stop = threading.Event()
    try:
        cfg = replace(CFG, audit_dir=os.path.join(tmp, "audit"),
                      web_files_dir=os.path.join(tmp, "web"))
        hub = Hub(cfg=cfg, audit_dir=os.path.join(tmp, "audit"))
        port = _free_port()
        threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                         daemon=True).start()
        time.sleep(0.2)

        # 1. Bots：注册 + 私聊回复链路
        events = []
        core = ClientCore(host="127.0.0.1", port=port, nick="甲",
                          history_dir=os.path.join(tmp, "h_jia"),
                          on_event=events.append)
        core.start()
        check("上线", _wait(events, "welcome", 5) is not None)
        check("known 含机器人",
              any(u.get("type") == "bot" for u in core.known.values()))

        core.send_private("hello123", to_uid=_bots.BOT_ECHO.uid)
        ev = _wait(events, "chat", 5, pred=lambda m:
                   m.get("uid") == _bots.BOT_ECHO.uid)
        check("回声 bot 复读", ev is not None and "🔁 hello123" in
              (ev.get("text") or ""), str((ev or {}).get("text")))
        ev = _wait(events, "chat", 3, pred=lambda m:
                   m.get("uid") == core.uid and m.get("to") == _bots.BOT_ECHO.uid)
        check("发送方收到回显", ev is not None and ev.get("text") == "hello123")

        core.send_private("骰子", to_uid=_bots.BOT_DICE.uid)
        ev = _wait(events, "chat", 5, pred=lambda m:
                   m.get("uid") == _bots.BOT_DICE.uid)
        check("骰子 bot 掷骰", ev is not None and "掷出了" in (ev.get("text") or ""))

        # 2. 贴纸商店：目录 + 订阅
        core.request_sticker_shop()
        ev = _wait(events, "sticker_shop_list", 5)
        check("商店目录回帧", ev is not None and len(ev.get("packs") or []) >= 3)
        check("默认订阅 basic", core.sticker_subs == ["basic"])
        codes = {s["code"] for s in core.subscribed_stickers()}
        check("面板按订阅过滤", "smile" in codes and "fish" not in codes)

        core.send_sticker_sub("fun", True)
        ev = _wait(events, "sticker_sub", 5)
        check("订阅回帧全量", ev is not None and "fun" in core.sticker_subs,
              str(core.sticker_subs))
        codes = {s["code"] for s in core.subscribed_stickers()}
        check("订阅后摸鱼包入面板", "fish" in codes and "cool" not in codes)

        core.stop()
        time.sleep(0.3)

        # 3. 多档案：昵称子目录隔离（不指定 history_dir 时生效） + prefs 切换
        import client_core as cc
        orig_dir_fn = cc._default_history_dir
        cc._default_history_dir = lambda: os.path.join(tmp, "base")
        try:
            core3 = ClientCore(nick="丙")     # 不连接，仅验证目录归属
            check("未指定目录时按昵称分子目录",
                  os.path.basename(core3._history._dir) == _nick_safe("丙"),
                  core3._history._dir)
        finally:
            cc._default_history_dir = orig_dir_fn
        check("显式目录优先生效",
              core._history._dir == os.path.abspath(os.path.join(tmp, "h_jia")))
        prefs = Prefs(os.path.join(tmp, "prefs.json"))
        prefs.toggle_pin("private:2")
        prefs.remember_account("甲")
        prefs.switch_profile("乙")
        check("切乙后状态清空", not prefs.is_pinned("private:2"))
        prefs.remember_account("甲")
        prefs.switch_profile("甲")
        check("切回甲状态恢复", prefs.is_pinned("private:2"))

        core2 = ClientCore(host="127.0.0.1", port=port, nick="乙",
                           history_dir=os.path.join(tmp, "h_yi"),
                           on_event=events.append)
        core2.start()
        check("乙独立上线", _wait(events, "welcome", 5,
                                  pred=lambda h: h.get("nick") == "乙") is not None)
        core2.stop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        check("异常", False, f"{type(e).__name__}: {e}")
    finally:
        stop.set()
        time.sleep(0.2)

    print("\n".join(results))
    print("R35 冒烟:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


def _wait(events, t, timeout, pred=None):
    """从事件流里取第一个命中帧（轮询 + 抽走已扫过的不匹配项不影响断言）"""
    deadline = time.time() + timeout
    seen = 0
    while time.time() < deadline:
        while seen < len(events):
            ev = events[seen]
            seen += 1
            if ev.get("t") == t and (pred is None or pred(ev)):
                return ev
        time.sleep(0.02)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
