# -*- coding: utf-8 -*-
"""R47 EXE 冒烟：server.exe 的 web 通道验证僵尸释放/会话恢复/昵称密码（跑完即删）。"""
import http.client
import json
import os
import socket
import ssl
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dist", "server.exe")
WEB_PORT = 19529

_CTX = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _req(method, path, body=None, cookie=""):
    conn = http.client.HTTPSConnection("127.0.0.1", WEB_PORT, timeout=8,
                                       context=_CTX)
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    data = json.dumps(body).encode() if body is not None else None
    if data:
        headers["Content-Type"] = "application/json"
    conn.request(method, path, data, headers)
    r = conn.getresponse()
    raw = r.read().decode() or "{}"
    sc = r.getheader("Set-Cookie") or ""
    conn.close()
    try:
        return r.status, json.loads(raw), sc
    except json.JSONDecodeError:
        return r.status, {}, sc


def main() -> int:
    env = dict(os.environ, MOYU_TCP_PORT="19527", MOYU_UDP_PORT="19528",
               MOYU_WEB_PORT=str(WEB_PORT))
    proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE), env=env)
    results = []
    try:
        ready = False
        t = time.time() + 10
        while time.time() < t:
            try:
                with socket.create_connection(("127.0.0.1", WEB_PORT), timeout=1):
                    ready = True
                    break
            except OSError:
                time.sleep(0.3)
        if not ready:
            print("server.exe 未在 10s 内监听 web 端口")
            return 1

        # 首登带密码 → 绑定
        st, d, ck = _req("POST", "/api/login", {"nick": "冒烟甲", "password": "p47"})
        results.append(("首登带密码登录+绑定", st == 200 and d.get("ok")))
        uid = d.get("uid")

        # whoami 会话恢复
        st, d2, _ = _req("GET", "/api/whoami", cookie=ck.split(";")[0])
        results.append(("whoami Cookie 恢复", st == 200 and d2.get("uid") == uid))

        # 原会话退出 → 缺密码被拒 → 对密码过（onefile 有引导子进程，须整树杀）
        _req("POST", "/api/passwd", {"old": "p47", "new": "p47"}, cookie=ck.split(";")[0])
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       capture_output=True)
        proc.wait(timeout=5)
        time.sleep(1.0)
        proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE), env=env)
        t = time.time() + 10
        ready = False
        while time.time() < t:
            try:
                with socket.create_connection(("127.0.0.1", WEB_PORT), timeout=1):
                    ready = True
                    break
            except OSError:
                time.sleep(0.3)
        if not ready:
            print("server.exe 重启未就绪")
            return 1
        st, d3, _ = _req("POST", "/api/login", {"nick": "冒烟甲"})
        results.append(("重启后已设密码缺密码被拒",
                        st == 403 and "密码" in d3.get("error", "")))
        st, d4, ck4 = _req("POST", "/api/login", {"nick": "冒烟甲", "password": "p47"})
        results.append(("重启后对密码登录过（持久化）", st == 200 and d4.get("ok")))
        if st != 200:
            print(f"    对密码登录失败详情: status={st} resp={d4}")

        ok = all(k for _, k in results)
        for line, good in results:
            print(f"[{'OK' if good else 'FAIL'}] {line}")
        print("R47 EXE SMOKE", "OK" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       capture_output=True)
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
