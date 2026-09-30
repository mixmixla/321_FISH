# -*- coding: utf-8 -*-
"""联调检测端：连接打包的 server.exe，登录后检查 roster 是否含指定昵称。

配合启动打包 client.exe（GUI，--nick 直通）使用——若 client.exe 完整跑通
（reconfigure 修复 + 连接 + GUI mainloop 存活），服务器名单会看到它上线。
用法：python _smoke_exe_probe.py <昵称>
"""
import socket
import sys
import time

from crypto import client_handshake

PORT = 9527


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "打包丙"
    sock = socket.create_connection(("127.0.0.1", PORT), timeout=8)
    chan = client_handshake(sock)
    chan.send_frame({"t": "hello", "nick": "probe_探"})
    ok = False
    deadline = time.time() + 6
    while time.time() < deadline:
        try:
            h, _b = chan.recv_frame()
        except Exception:
            break
        if h.get("t") == "welcome":
            nicks = [u["nick"] for u in h.get("roster", [])]
            print("roster =", nicks)
            ok = target in nicks
            break
    sock.close()
    print("PROBE ROASTER", "OK" if ok else "FAIL", "目标:", target)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())