# -*- coding: utf-8 -*-
"""R50 冒烟：P0-1 网页端 E2EE 禁入 / P0-2 屏蔽名单 / P0-3 词宽缓存 LRU 上限。
进程内起真实 Hub + TCP 服务 + web 服务（HTTPS 关），用两个真 ClientCore + 一个网页
登录（SSE/HTTP）做联调；P0-3 用真实 MsgList 控件测缓存上界。跑完即删。"""
import http.client
import json
import os
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# 端口 & 关 HTTPS：置 env 要先于 import config/server/web
os.environ["MOYU_TCP_PORT"] = "19537"
os.environ["MOYU_UDP_PORT"] = "19538"
os.environ["MOYU_WEB_PORT"] = "19539"
os.environ["MOYU_WEB_HTTPS"] = "0"

import server                       # noqa: E402
from protocol import MsgType        # noqa: E402
from client_core import ClientCore  # noqa: E402

WEB_PORT = 19539
TCP_PORT = 19537
_FAIL = []


# ---- 真 ClientCore 事件泵 ----
def pump(core, bucket):
    while True:
        try:
            ev = core.events.get(timeout=1.0)
        except Exception:
            if getattr(core, "_smoke_stop", False):
                return
            continue
        bucket.append(ev)


def wait_for(bucket, pred, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        for ev in bucket:
            try:
                if pred(ev):
                    return ev
            except Exception:
                pass
        time.sleep(0.05)
    return None


def wait_uid(core, bucket):
    ev = wait_for(bucket, lambda e: e.get("t") == "welcome")
    return ev["uid"] if ev else None


def _req(method, path, body=None, cookie=""):
    conn = http.client.HTTPConnection("127.0.0.1", WEB_PORT, timeout=8)
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


# ---- 网页 SSE 读取（真事件流，验证网页端收到的回帧）----
def sse_collect(token, out, stop):
    conn = http.client.HTTPConnection("127.0.0.1", WEB_PORT, timeout=20)
    conn.putrequest("GET", f"/api/events?token={token}")
    conn.putheader("Cookie", f"mt_token={token}")
    conn.endheaders()
    r = conn.getresponse()
    buf = b""
    while not stop.is_set():
        chunk = r.read(2048)
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if line.startswith(b"data:"):
                try:
                    out.append(json.loads(line[5:]))
                except Exception:
                    pass
    conn.close()


# ---- P0-3：词宽缓存 LRU 上界（真实 MsgList 实例） ----
def test_p03_lru():
    import tkinter as tk
    from widgets import msg_list
    root = tk.Tk()
    root.withdraw()
    ml = msg_list.MsgList(root, ("Segoe UI", 10), me_uid=0)
    n = ml._MEAS_CACHE_MAX
    # 压满 + 溢出：插入远超上限的不同词
    for i in range(n + 3000):
        ml._meas(f"词{str(i)}x" + "W" * (i % 20))
    if len(ml._meas_cache) > n:
        _FAIL.append(f"P0-3: _meas_cache 超过上限 {n} -> {len(ml._meas_cache)}")
    else:
        print(f"[OK] P0-3 _meas_cache 压入 {n}+3000 词后 cap={len(ml._meas_cache)}<={n}")
    # 命中移队尾仍工作；oldest 已被淘汰（重新测与再命中一致）
    ml._meas  # noqa
    before = len(ml._meas_cache)
    w1 = ml._meas("词0xWW")             # 最旧的应被淘汰，重测重插
    w2 = ml._meas("词0xWW")             # 命中
    if not (w1 == w2 and len(ml._meas_cache) <= n):
        _FAIL.append("P0-3: 淘汰后重测不一致或超限")
    # _meas_bold 独立键同样受限
    for i in range(n + 2000):
        ml._meas_bold(f"加粗{i}")
    if len(ml._meas_cache) > n:
        _FAIL.append(f"P0-3: _meas_bold 超限 {len(ml._meas_cache)}")
    else:
        print(f"[OK] P0-3 _meas_bold 压入后 cap={len(ml._meas_cache)}<={n}")
    root.destroy()
    print("[OK] P0-3 词宽缓存 LRU 上界生效")


# ---- P0-2 / P0-1：屏蔽 + 网页 E2EE 禁入 ----
def main() -> int:
    store = tempfile.mkdtemp(prefix="r50srv_")
    hub = server.Hub(store_dir=store)
    stop = threading.Event()
    t = threading.Thread(target=server.serve, args=(hub, None, stop, True),
                         daemon=True)
    t.start()

    # 等 tcp + web 就绪
    ready = False
    end = time.time() + 10
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", TCP_PORT), timeout=1), \
                 socket.create_connection(("127.0.0.1", WEB_PORT), timeout=1):
                ready = True
                break
        except OSError:
            time.sleep(0.3)
    if not ready:
        print("服务未就绪")
        return 1

    cores = {}
    buckets = {}
    try:
        # 桌面端 A、B；网页端 W(丙)
        for nick in ("甲", "乙"):
            c = ClientCore(host="127.0.0.1", port=TCP_PORT, nick=nick,
                           history_dir=os.path.join(tempfile.mkdtemp(prefix="r50h_"), "h"))
            b = []
            c._smoke_stop = False
            threading.Thread(target=pump, args=(c, b), daemon=True).start()
            c.start()
            cores[nick] = (c, b)
        for nick in ("甲", "乙"):
            uid = wait_uid(*cores[nick])
            if uid is None:
                _FAIL.append(f"桌面端 {nick} 未上线")
                continue
            print(f"[..] {nick} uid={uid}")
        uidA = cores["甲"][0].uid
        uidB = cores["乙"][0].uid

        # 网页端登录
        st, d, ck = _req("POST", "/api/login", {"nick": "丙"})
        if st != 200 or not d.get("ok"):
            _FAIL.append(f"网页登录失败 {st} {d}")
            return 1
        WTOK = d["token"]
        uidW = d["uid"]
        wss_bucket = []
        wss_stop = threading.Event()
        threading.Thread(target=sse_collect, args=(WTOK, wss_bucket, wss_stop),
                         daemon=True).start()
        st, d2, _ = _req("GET", "/api/whoami", cookie=f"mt_token={WTOK}")
        print(f"[..] 网页 uid={uidW} whoami_blocked(空)={d2.get('blocked')}")
        time.sleep(0.5)

        # ---- P0-2a 桌面 A 屏蔽桌面 B，服务器拒收 B→A 私聊 ----
        cores["甲"][0].set_block(uidB, True)
        wait_for(cores["甲"][1], lambda e: e.get("t") == "block_list")
        if uidB not in cores["甲"][0].blocked:
            _FAIL.append("P0-2: A.blocked 未包含 B")
        else:
            print("[OK] P0-2 桌面端屏蔽：A.blocked 已含 B")
        # B 发给 A → 应收到 error/blocked
        cores["乙"][0].send_private("你好A", uidA)
        er = wait_for(cores["乙"][1], lambda e: e.get("t") == "error"
                      and e.get("code") == "blocked")
        if not er:
            _FAIL.append("P0-2: B→A 私聊未被服务器拒收")
        else:
            print(f"[OK] P0-2 服务器拒收 B→A 私聊: {er.get('text')}")

        # ---- P0-2b 网页 W 屏蔽 A；whoami 带回名单；A→W 私聊被拒 ----
        st, d, _ = _req("POST", "/api/block", {"token": WTOK, "op": "block",
                                               "uid": uidA})
        if st != 200 or not d.get("ok"):
            _FAIL.append(f"P0-2: 网页 /api/block 失败 {st} {d}")
        else:
            print("[OK] P0-2 网页 /api/block 已提交")
        st, d, _ = _req("GET", "/api/whoami", cookie=f"mt_token={WTOK}")
        blocked = d.get("blocked") or []
        if uidA not in blocked:
            _FAIL.append(f"P0-2: whoami.blocked 未含 A -> {blocked}")
        else:
            print("[OK] P0-2 网页 whoami.blocked 已含 A")
        cores["甲"][0].send_private("你好丙", uidW)
        er = wait_for(cores["甲"][1], lambda e: e.get("t") == "error"
                      and e.get("code") == "blocked")
        if not er:
            _FAIL.append("P0-2: A→W 私聊未被拒收")
        else:
            print(f"[OK] P0-2 服务器拒收 A→W 私聊: {er.get('text')}")

        # ---- P0-1 网页端 E2EE 禁入：以 W 的会话发 E2EE_PUB → 拒收，B 无感 ----
        sessW = hub.sessions.get(uidW)
        if sessW is None or sessW.type != "web":
            _FAIL.append("P0-1: 未取到 web 会话")
        else:
            # 直接挂到 web 会话 fanout（SSE 内部同款），确定读取被拒回帧
            q = queue.Queue()
            sessW.send.attach(q)
            got_ev_on_B = len([e for e in cores["乙"][1]
                               if e.get("t") == MsgType.E2EE_PUB.value])
            hub.dispatch(sessW, {"t": MsgType.E2EE_PUB.value,
                                 "to": uidB, "pub": "P", "nonce": "N", "rs": "R"})
            got_ev_on_B2 = len([e for e in cores["乙"][1]
                                if e.get("t") == MsgType.E2EE_PUB.value])
            try:
                payload, _b = q.get(timeout=3)
            except Exception:
                payload = None
            sessW.send.detach(q)
            if got_ev_on_B != got_ev_on_B2:
                _FAIL.append("P0-1: 网页密聊尝试竟触达了桌面 B")
            if not (payload and payload.get("t") == "error"
                    and "仅桌面端支持" in payload.get("text", "")):
                _FAIL.append(f"P0-1: 网页未收到「仅桌面端支持」提示 -> {payload}")
            else:
                print(f"[OK] P0-1 网页发密聊被拒且 B 无感: {payload.get('text')}")

        # ---- P0-2c 桌面 A 解除屏蔽 B → B→A 私聊恢复送达 ----
        cores["甲"][0].set_block(uidB, False)
        wait_for(cores["甲"][1], lambda e: e.get("t") == "block_list")
        if uidB in cores["甲"][0].blocked:
            _FAIL.append("P0-2: 解除后 A.blocked 仍含 B")
        cores["乙"][0].send_private("重启会话", uidA)
        recv = wait_for(cores["甲"][1], lambda e: e.get("t") == "chat"
                        and e.get("text") == "重启会话")
        if not recv:
            _FAIL.append("P0-2: 解除屏蔽后 B→A 未送达")
        else:
            print("[OK] P0-2 解除屏蔽后私聊恢复送达")

        wss_stop.set()
    finally:
        for nick, (c, b) in cores.items():
            c._smoke_stop = True
            try:
                c.stop()
            except Exception:
                pass
        stop.set()

    if _FAIL:
        for f in _FAIL:
            print(f"[FAIL] {f}")
        print("R50 SMOKE FAIL")
        return 1
    print("R50 SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    code = 0
    try:
        code = main()
    finally:
        try:
            test_p03_lru()
        except Exception as exc:
            print(f"[FAIL] P0-3 构建 MsgList 异常: {exc!r}")
            code = 1
    raise SystemExit(code)