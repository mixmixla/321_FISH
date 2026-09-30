# -*- coding: utf-8 -*-
"""EXE 冒烟：用真实 crypto 客户端连接 dist/server.exe，验证握手+登录"""
import socket
import time

from crypto import client_handshake


def main() -> int:
    sock = socket.create_connection(("127.0.0.1", 9527), timeout=8)
    chan = client_handshake(sock)
    chan.send_frame({"t": "hello", "nick": "exe_smoke"})
    ok = False
    deadline = time.time() + 8
    while time.time() < deadline:
        h, _b = chan.recv_frame()
        if h.get("t") == "welcome":
            ok = True
            print("WELCOME uid=", h.get("uid"),
                  "roster=", [u["nick"] for u in h.get("roster", [])],
                  "stickers=", len(h.get("stickers") or []))
            break
        if h.get("t") == "error":
            print("ERROR", h)
            break
    sock.close()
    print("EXE SERVER SMOKE", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
