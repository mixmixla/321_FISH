# -*- coding: utf-8 -*-
"""R36 E2EE 密聊冒烟（真服务器 + 真客户端核心）：
- 1v1：握手 → 双方就绪 + 指纹一致；密聊互通；服务器 audit 落盘不含明文
- 群：开群密聊（自动握手+sender key 分发）→ 群密聊互通 → 踢人 re-key 后仍互通
- 边界：未握手时发密聊被拒（错误提示）
"""
import os
import socket
import tempfile
import threading
import time

from client_core import ClientCore
from config import CFG
from server import Hub, serve as serve_tcp


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="r36_")
    ok = True
    results = []

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and cond
        results.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

    stop = threading.Event()
    try:
        cfg = replace_cfg(tmp)
        hub = Hub(cfg=cfg, audit_dir=os.path.join(tmp, "audit"))
        port = _free_port()
        threading.Thread(target=serve_tcp, args=(hub, port, stop, False),
                         daemon=True).start()
        time.sleep(0.2)

        a, ea = _spawn(port, "甲", tmp)
        b, eb = _spawn(port, "乙", tmp)

        # 1. 1v1 握手 + 指纹
        fp = a.start_e2ee(b.uid)
        check("握手成功", bool(fp))
        check("双方就绪", a.e2ee_ready(b.uid) and b.e2ee_ready(a.uid))
        check("指纹一致", fp == a.e2ee_fingerprint(b.uid) ==
              b.e2ee_fingerprint(a.uid))

        # 2. 密聊互通 + 服务器不落明文
        secret = "冒烟机密#1"
        check("密聊发送", a.send_e2ee_chat(secret, b.uid))
        ev = _wait(eb, "chat", 5, pred=lambda m: m.get("channel") == "e2ee")
        check("乙收到明文（端侧解密）",
              ev is not None and ev.get("text") == secret,
              str((ev or {}).get("text")))
        audit_txt = _read_audit(os.path.join(tmp, "audit"))
        check("服务器 audit 无明文", secret not in audit_txt)

        # 3. 未握手的第三人发密聊 → 拒绝
        c, _ec = _spawn(port, "丙", tmp)
        check("未握手发密聊被拒", not c.send_e2ee_chat("x", a.uid))

        # 4. 群密聊：建群 → 开密聊（自动握手+key 分发）→ 互通
        assert a.create_group("冒烟密群")
        gid = _wait(ea, "group_state", 5)["gid"]
        assert b.join_group(gid) and c.join_group(gid)
        _wait(ea, "group_state", 5,
              pred=lambda e: e.get("gid") == gid
              and len(e.get("members") or []) == 3)
        ok_open, err = a.open_group_e2ee(gid)
        check("开群密聊", ok_open, err)
        ok_open_b, _ = b.open_group_e2ee(gid)
        check("成员开群密聊", ok_open_b)
        deadline = time.time() + 5
        while time.time() < deadline and \
                (a.e2ee.peer_sender_entry(gid, b.uid) is None
                 or b.e2ee.peer_sender_entry(gid, a.uid) is None):
            time.sleep(0.05)
        # R44 DFSS：v2 种子即擦，按登记 entry 判互持
        check("sender key 互持", a.e2ee.peer_sender_entry(gid, b.uid) is not None
              and b.e2ee.peer_sender_entry(gid, a.uid) is not None)

        gmsg = "群密冒烟#2"
        check("群密聊发送", a.send_e2ee_group(gmsg, gid))
        ev = _wait(eb, "chat", 5, pred=lambda m: m.get("channel") == "group"
                   and m.get("e2ee") is True)
        check("乙收到群密聊", ev is not None and ev.get("text") == gmsg,
              str((ev or {}).get("text")))

        # 5. 踢人 re-key → 剩余成员仍互通
        epoch0 = a.e2ee.group_epoch(gid)
        assert a.kick_member(gid, c.uid)
        deadline = time.time() + 8
        while time.time() < deadline and a.e2ee.group_epoch(gid) <= epoch0:
            time.sleep(0.1)
        check("踢人触发 re-key", a.e2ee.group_epoch(gid) > epoch0)
        gmsg2 = "rekey后#3"
        check("re-key 后发送", b.send_e2ee_group(gmsg2, gid))
        ev = _wait(ea, "chat", 5, pred=lambda m: m.get("text") == gmsg2)
        check("re-key 后甲收到", ev is not None)

        a.stop(); b.stop(); c.stop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        check("异常", False, f"{type(e).__name__}: {e}")
    finally:
        stop.set()
        time.sleep(0.2)

    print("\n".join(results))
    print("R36 冒烟:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


def replace_cfg(tmp):
    from dataclasses import replace
    return replace(CFG, audit_dir=os.path.join(tmp, "audit"),
                   web_files_dir=os.path.join(tmp, "web"))


def _spawn(port, nick, tmp):
    events = []
    core = ClientCore(host="127.0.0.1", port=port, nick=nick,
                      history_dir=os.path.join(tmp, f"h_{nick}"),
                      on_event=events.append)
    core.start()
    assert _wait(events, "welcome", 5) is not None, f"{nick} 未上线"
    return core, events


def _read_audit(audit_dir):
    parts = []
    if os.path.isdir(audit_dir):
        for fn in os.listdir(audit_dir):
            p = os.path.join(audit_dir, fn)
            if os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        parts.append(f.read())
                except OSError:
                    pass
    return "\n".join(parts)


def _wait(events, t, timeout, pred=None):
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
