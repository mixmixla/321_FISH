# -*- coding: utf-8 -*-
"""打包双端联调：spawn dist/server.exe，两个真实 crypto 客户端经它互发公聊/私聊。

验证打包产物 server.exe 的消息中继链路完整可用：
  - 两个端 hello 登录后，各自 welcome 的 roster 都能看到对方（服务端名单正确）
  - 端A 发 public → 端B 收到同 channel/同 uid/同 text
  - 端B 私聊(to=A) → 端A 收到且 to 正确
  - 端A 再发 public → 端B 收到（双向无丢）
用法：python _smoke_exe_pair.py
"""
import os
import socket
import subprocess
import sys
import time

from crypto import client_handshake

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dist", "server.exe")
PORT = 9527


def _connect(nick: str):
    sock = socket.create_connection(("127.0.0.1", PORT), timeout=8)
    chan = client_handshake(sock)
    sock.settimeout(None)
    chan.send_frame({"t": "hello", "nick": nick})
    while True:
        h, _b = chan.recv_frame()
        if h.get("t") == "welcome":
            return chan, h
        if h.get("t") == "error":
            raise RuntimeError(f"login error: {h}")


def _wait_event(chan, ttype, text, timeout=6):
    t = time.time() + timeout
    while time.time() < t:
        h, _b = chan.recv_frame()
        if h.get("t") == ttype and h.get("text") == text:
            return h
    return None


def main() -> int:
    if not os.path.exists(EXE):
        print(f"EXE 不存在: {EXE}")
        return 1
    proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    ok = True
    results = []
    try:
        # 等 9527 就绪
        ready = False
        t = time.time() + 8
        while time.time() < t:
            try:
                with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                    ready = True
                    break
            except OSError:
                time.sleep(0.3)
        if not ready:
            print("server.exe 未在 8s 内监听 9527")
            return 1

        chanA, wA = _connect("联调甲")
        chanB, wB = _connect("联调乙")
        # 甲先连、乙后连：甲的 welcome roster 在乙上线前取出，不该含乙（时序自然）
        # 只看乙连线时刻 roster 能看到已在线的甲
        rostersB = [u["nick"] for u in wB.get("roster", [])]
        results.append(("[OK] 乙 welcome roster 含甲（已上线者可见）", "联调甲" in rostersB))

        # 甲 → 公聊 → 乙
        chanA.send_frame({"t": "chat", "channel": "public", "text": "公聊A消息"})
        r = _wait_event(chanB, "chat", "公聊A消息")
        results.append(("[OK] 甲→公聊→乙收到", bool(r)))
        results.append(("[OK] 公聊转发 channel/uid 正确",
                        bool(r and r.get("channel") == "public"
                               and r.get("uid") == wA.get("uid"))))

        # 乙 → 私聊 -> 甲
        uidA = wA.get("uid")
        chanB.send_frame({"t": "chat", "channel": "private",
                          "to": uidA, "text": "私聊到甲"})
        r2 = _wait_event(chanA, "chat", "私聊到甲")
        results.append(("[OK] 乙→私聊→甲收到", bool(r2)))
        results.append(("[OK] 私聊 to 正确", bool(r2 and r2.get("to") == uidA)))

        # 乙 → 公聊 → 甲（双向）
        chanB.send_frame({"t": "chat", "channel": "public", "text": "公聊B消息"})
        r3 = _wait_event(chanA, "chat", "公聊B消息")
        results.append(("[OK] 乙→公聊→甲收到（双向）", bool(r3)))

        ok = all(k for _, k in results)
        for line, good in results:
            status = "OK" if good else "FAIL"
            print(f"[{status}] {line.strip('[]OK ')}")
    finally:
        for c in ("chanB", "chanA"):
            if f := locals().get(c):
                try:
                    f.send_frame({"t": "bye"})
                except Exception:
                    pass
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    print("EXE PAIR SMOKE", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())