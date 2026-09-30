# -*- coding: utf-8 -*-
"""R71 冒烟：频道评论区 / 联系人名片 / 消息永久链接 / STT 内置模型。

进程内起真实 Hub + TCP 服务 + web 服务（HTTPS 关），用两个真 ClientCore
做双端联调；网页端只做「页面是否下发 R71 钩子」的静态校验；STT 校验
find_model_dir 的优先级链。跑完即删。
"""
import http.client
import os
import socket
import sys
import tempfile
import threading
import time
from dataclasses import replace

HERE = os.path.dirname(os.path.abspath(__file__))
# 端口 & 关 HTTPS：置 env 要先于 import config/server/web
os.environ["MOYU_TCP_PORT"] = "19647"
os.environ["MOYU_UDP_PORT"] = "19648"
os.environ["MOYU_WEB_PORT"] = "19649"
os.environ["MOYU_WEB_HTTPS"] = "0"

import server                        # noqa: E402
from config import CFG               # noqa: E402
from protocol import MsgType         # noqa: E402
from client_core import ClientCore   # noqa: E402
import optional                      # noqa: E402

WEB_PORT = 19649
TCP_PORT = 19647
_FAIL = []


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


def need(cond, msg):
    if cond:
        print(f"[OK] {msg}")
    else:
        _FAIL.append(msg)
        print(f"[FAIL] {msg}")


def _http(method, path, body=None, cookie=""):
    import json
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
    conn.close()
    return r.status, raw


# ---------- 频道评论区 ----------
def _channel_flow(cores):
    A, bA = cores["甲"]
    B, bB = cores["乙"]
    need(A.create_group("📢 公告", broadcast=True, public=True), "R71 建频道")
    gs = wait_for(bA, lambda e: e.get("t") == "group_state"
                  and e.get("name") == "📢 公告")
    gid = (gs or {}).get("gid")
    if not gid:
        _FAIL.append("R71 跳过：未取到频道 gid")
        return
    B.join_group(gid)
    wait_for(bB, lambda e: e.get("t") == "group_state" and e.get("gid") == gid)

    B.send_chat("我要发贴", channel="group", to=gid)
    need(wait_for(bB, lambda e: e.get("t") == "error"
                  and e.get("code") == "readonly") is not None,
         "R71 非创建者裸发贴被拒（readonly）")

    A.send_chat("正式公告", channel="group", to=gid)
    root = wait_for(bA, lambda e: e.get("t") == "chat" and e.get("text") == "正式公告")
    rseq = (root or {}).get("seq")
    if not rseq:
        _FAIL.append("R71 跳过：未取到根贴 seq")
        return

    B.send_chat("收到", channel="group", to=gid, thread_root=rseq)
    cm = wait_for(bB, lambda e: e.get("t") == "chat"
                  and e.get("thread_root") == rseq)
    need(cm is not None and cm.get("uid") == B.uid,
         "R71 非创建者带 thread_root 评论放行")

    B.send_thread_fetch("group", gid, rseq)
    th = wait_for(bB, lambda e: e.get("t") == MsgType.THREAD_HISTORY.value)
    msgs = (th or {}).get("msgs") or []
    need(th is not None and len(msgs) == 1 and msgs[0].get("text") == "收到",
         f"R71 THREAD_FETCH 取到频道评论 -> {[m.get('text') for m in msgs]}")


# ---------- 联系人名片 ----------
def _card_flow(cores):
    A, _bA = cores["甲"]
    B, bB = cores["乙"]
    need(A.send_chat("", channel="public",
                     card={"uid": B.uid, "nick": B.nick,
                           "__proto__": {"x": 1}, "extra": "junk"}),
         "R71 发送纯名片消息（无正文）")
    ev = wait_for(bB, lambda e: e.get("t") == "chat" and e.get("card"))
    need(ev is not None and ev["card"] == {"uid": B.uid, "nick": B.nick},
         f"R71 名片白名单化透传 -> {(ev or {}).get('card')}")


# ---------- 群慢速 × 话题豁免 ----------
def _slow_flow(cores):
    A, bA = cores["甲"]
    B, bB = cores["乙"]
    need(A.create_group("慢速群", public=True), "R71 建普通公开群")
    gs = wait_for(bA, lambda e: e.get("t") == "group_state"
                  and e.get("name") == "慢速群")
    gid = (gs or {}).get("gid")
    if not gid:
        _FAIL.append("R71 跳过：未取到慢速群 gid")
        return
    B.join_group(gid)
    wait_for(bB, lambda e: e.get("t") == "group_state" and e.get("gid") == gid)
    A.send_group_slow(gid, 5)
    wait_for(bB, lambda e: e.get("t") == "group_state"
             and e.get("gid") == gid and e.get("slow") == 5)
    B.send_chat("第一条", channel="group", to=gid)
    need(wait_for(bB, lambda e: e.get("t") == "chat"
                  and e.get("text") == "第一条") is not None, "R71 慢速档内首条放行")
    B.send_chat("第二条", channel="group", to=gid)
    need(wait_for(bB, lambda e: e.get("t") == "error"
                  and e.get("code") == "slow") is not None,
         "R71 慢速档内二次发言被拒")

    A.send_chat("根贴", channel="group", to=gid)
    root = wait_for(bA, lambda e: e.get("t") == "chat" and e.get("text") == "根贴")
    B.send_chat("档内回帖", channel="group", to=gid,
                thread_root=(root or {}).get("seq"))
    need(wait_for(bB, lambda e: e.get("t") == "chat"
                  and e.get("text") == "档内回帖") is not None,
         "R71 话题回帖豁免慢速")


# ---------- 消息永久链接（键格式对齐 web convKey） ----------
def _link_flow():
    from client import ChatWindow
    core = type("C", (), {"uid": 3})()
    s = type("S", (), {"core": core})()
    key = ChatWindow._msg_link_key.__get__(s)
    s.view = ("public", None)
    need(key() == "public", "R71 永久链接：公聊键 = public")
    s.view = ("group", 7)
    need(key() == "group:7", "R71 永久链接：群键 = group:<gid>")
    s.view = ("private", 9)
    need(key() == "private:3:9", "R71 永久链接：私聊键按 uid 小:大 排序")
    s.view = ("private", 1)
    need(key() == "private:1:3", "R71 永久链接：私聊键反向也归一化")
    s.view = ("e2ee", 2)
    need(key() == "private:2:3", "R71 永久链接：e2ee 复用私聊键")


# ---------- 网页端静态产出 ----------
def _web_sanity():
    st, raw = _http("GET", "/")
    need(st == 200, f"R71 网页首页可访问（{st}）")
    for token, desc in (
            ("data-card-uid", "名片卡片渲染钩子"),
            ("parseDeepLink", "永久链接深链解析"),
            ("hashchange", "深链 hashchange 监听"),
            ("curIsChannel", "频道只读/评论入口判定"),
            ("频道仅创建者可发言", "频道只读 placeholder")):
        need(token in raw, f"R71 页面下发：{desc}")


# ---------- STT 模型定位优先级 ----------
def _stt_flow():
    tmp = tempfile.mkdtemp(prefix="r71vosk_")
    d1 = os.path.join(tmp, "m1")
    d2 = os.path.join(tmp, "m2")
    for d in (d1, d2):
        os.makedirs(os.path.join(d, "am"), exist_ok=True)
        with open(os.path.join(d, "am", "final.mdl"), "wb") as fh:
            fh.write(b"m")
    old = os.environ.get("VOSK_MODEL")
    try:
        os.environ["VOSK_MODEL"] = d1
        need(optional.find_model_dir() == d1, "R71 STT：env 指定的模型被采用")
        need(optional.find_model_dir(pref_dir=d2) == d2,
             "R71 STT：prefs 指定压过 env")
        os.environ.pop("VOSK_MODEL", None)
        need(optional.find_model_dir(pref_dir=d2) == d2,
             "R71 STT：无 env 时仍认 prefs")
    finally:
        if old is not None:
            os.environ["VOSK_MODEL"] = old
        else:
            os.environ.pop("VOSK_MODEL", None)


def main() -> int:
    store = tempfile.mkdtemp(prefix="r71srv_")
    hub = server.Hub(cfg=CFG, store_dir=store)
    stop = threading.Event()
    threading.Thread(target=server.serve, args=(hub, None, stop, True),
                     daemon=True).start()

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
    try:
        for nick in ("甲", "乙"):
            c = ClientCore(host="127.0.0.1", port=TCP_PORT, nick=nick,
                           history_dir=os.path.join(
                               tempfile.mkdtemp(prefix="r71h_"), "h"))
            b = []
            c._smoke_stop = False
            threading.Thread(target=pump, args=(c, b), daemon=True).start()
            cores[nick] = (c, b)
            c.start()
        for nick in ("甲", "乙"):
            uid = wait_uid(*cores[nick])
            if uid is None:
                _FAIL.append(f"桌面端 {nick} 未上线")
            else:
                print(f"[..] {nick} uid={uid}")
        if _FAIL:
            return 1

        _channel_flow(cores)
        _card_flow(cores)
        _slow_flow(cores)
        _link_flow()
        _web_sanity()
        _stt_flow()
    finally:
        for _nick, (c, _b) in cores.items():
            c._smoke_stop = True
            try:
                c.stop()
            except Exception:
                pass
        stop.set()

    if _FAIL:
        for f in _FAIL:
            print(f"[FAIL] {f}")
        print("R71 SMOKE FAIL")
        return 1
    print("R71 SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())