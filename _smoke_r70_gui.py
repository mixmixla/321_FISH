# -*- coding: utf-8 -*-
"""R70 冒烟：TG 残余补齐与摸鱼差异化（A 剧透 / B 编辑历史 / D 群慢速 / C 投票增强
/ E 消息伪装 / F 敏感词打码 / G 忙碌自动回复 / H 摸鱼排行榜）。

进程内起真实 Hub + TCP 服务 + web 服务（HTTPS 关），用两个真 ClientCore + 一个
网页登录（HTTP/SSE）做双端联调；F 用真实 MsgList 控件验证遮盖段；H 额外验证
网页端只读接口。跑完即删。
"""
import http.client
import json
import os
import socket
import sys
import tempfile
import threading
import time
from dataclasses import replace

HERE = os.path.dirname(os.path.abspath(__file__))
# 端口 & 关 HTTPS：置 env 要先于 import config/server/web
os.environ["MOYU_TCP_PORT"] = "19547"
os.environ["MOYU_UDP_PORT"] = "19548"
os.environ["MOYU_WEB_PORT"] = "19549"
os.environ["MOYU_WEB_HTTPS"] = "0"

import server                        # noqa: E402
from config import CFG               # noqa: E402
from protocol import MsgType         # noqa: E402
from client_core import ClientCore   # noqa: E402

WEB_PORT = 19549
TCP_PORT = 19547
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


# ---------- A/B/D/C/E：双端协议联调 ----------
def _desktop_flow(hub, cores):
    A = cores["甲"][0]
    B = cores["乙"][0]
    bA = cores["甲"][1]
    bB = cores["乙"][1]

    # ---- R70A 剧透：rich 段随消息透传（服务器白名单清洗 spoiler） ----
    rich_segs = [["前 ", "plain", ""], ["秘密", "spoiler", ""],
                 [" 后", "plain", ""]]
    need(A.send_chat("前 ||秘密|| 后", rich=rich_segs), "R70A 发送带 spoiler 富文本")
    ev = wait_for(bB, lambda e: e.get("t") == "chat"
                  and any(s[1] == "spoiler" for s in (e.get("rich") or [])
                          if isinstance(s, (list, tuple)) and len(s) > 1))
    need(ev is not None, "R70A 对端收到 spoiler 段（服务器未清洗掉）")

    # ---- R70B 编辑历史：旧版本入 edits ----
    seq = (ev or {}).get("seq")
    if seq:
        need(A.send_edit(seq, "前 ||改后|| 后"), "R70B 发送编辑")
        e2 = wait_for(bB, lambda e: e.get("t") == "edit" and e.get("seq") == seq)
        need(e2 is not None and [x["text"] for x in (e2.get("edits") or [])]
             == ["前 ||秘密|| 后"], f"R70B 编辑历史含旧版本 -> {(e2 or {}).get('edits')}")
    else:
        _FAIL.append("R70B 跳过：未取到消息 seq")

    # ---- R70D 群慢速：档内二次发言被拒 + 群主豁免 ----
    need(A.create_group("慢速群", public=True), "R70D 建公开群")
    gs = wait_for(bA, lambda e: e.get("t") == "group_state"
                  and e.get("name") == "慢速群")
    gid = (gs or {}).get("gid")
    if not gid:
        _FAIL.append("R70D 跳过：未取到 gid")
    else:
        B.join_group(gid)
        wait_for(bB, lambda e: e.get("t") == "group_state" and e.get("gid") == gid)
        need(A.send_group_slow(gid, 5), "R70D 设置 5 秒慢速")
        wait_for(bB, lambda e: e.get("t") == "group_state"
                 and e.get("gid") == gid and e.get("slow") == 5)
        B.send_chat("第一条", channel="group", to=gid)
        need(wait_for(bB, lambda e: e.get("t") == "chat"
                      and e.get("text") == "第一条") is not None, "R70D 档内首条放行")
        B.send_chat("第二条", channel="group", to=gid)
        need(wait_for(bB, lambda e: e.get("t") == "error"
                      and e.get("code") == "slow") is not None,
             "R70D 档内二次发言被拒（slow）")
        A.send_chat("管理一", channel="group", to=gid)
        A.send_chat("管理二", channel="group", to=gid)
        need(wait_for(bB, lambda e: e.get("t") == "chat"
                      and e.get("text") == "管理二") is not None,
             "R70D 群主连发豁免")

    # ---- R70C 投票增强：匿名（只广播计数，按人单播 mine）----
    need(A.send_poll(channel="public", question="午饭吃啥",
                     options=["面", "饭", "沙拉"], anonymous=True),
         "R70C 发起匿名投票")
    pev = wait_for(bB, lambda e: e.get("t") == "poll"
                   and e.get("poll", {}).get("anonymous"))
    pseq = (pev or {}).get("seq")
    if not pseq:
        _FAIL.append("R70C 跳过：未取到 poll seq")
    else:
        B.send_poll_vote(pseq, 1)
        # 匿名：先广播「只带计数、无 votes/mine」，再按人单播 mine
        bcast = wait_for(bB, lambda e: e.get("t") == "poll_state"
                         and e.get("seq") == pseq and e.get("total") == 1
                         and "mine" not in e)
        need(bcast is not None and bcast.get("counts") == [0, 1, 0]
             and "votes" not in bcast,
             f"R70C 匿名投票：只广播计数不泄露 votes -> {bcast}")
        mine = wait_for(bB, lambda e: e.get("t") == "poll_state"
                        and e.get("seq") == pseq and e.get("mine") == [1])
        need(mine is not None,
             f"R70C 匿名投票：本人 mine 单播 -> {mine}")
        with hub.bus._lock:
            _k, pmsg = hub.bus.find(pseq)
        need(not (pmsg.get("poll") or {}).get("votes"),
             "R70C 匿名投票不落 bus（回放不泄露）")

    # ---- R70E 消息伪装：disguise 头透传 ----
    need(A.send_chat("假装是日志", disguise="log"), "R70E 发送伪装消息")
    need(wait_for(bB, lambda e: e.get("t") == "chat"
                  and e.get("disguise") == "log") is not None,
         "R70E disguise 头透传对端")

    # ---- R70G 忙碌自动回复：auto 标记透传（接收端据此不再回环）----
    need(A.send_chat("我在忙，稍后回复你～", channel="private", to=B.uid, auto=True),
         "R70G 发送带 auto 标记的私聊")
    need(wait_for(bB, lambda e: e.get("t") == "chat"
                  and e.get("text") == "我在忙，稍后回复你～"
                  and e.get("auto") is True) is not None,
         "R70G auto 标记透传（防环路依据）")


# ---------- F：MsgList 遮码段（真控件） ----------
def _guard_flow():
    try:
        import tkinter as tk
    except Exception as exc:
        _FAIL.append(f"R70F 无 Tk：{exc!r}")
        return
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"[skip] R70F 无可用 Tk 显示环境: {exc}")
        return
    from widgets import msg_list, rich
    try:
        root.withdraw()
        ml = msg_list.MsgList(root, ("Microsoft YaHei UI", 9))
        ml.set_guard(("机密", "secret"), True)
        ml.append({"t": "chat", "seq": 90, "uid": 1, "nick": "甲",
                   "channel": "public", "ts": time.time(),
                   "text": "这是机密文件 secret 内容"})
        root.update_idletasks(); root.update()
        row = ml._rows[-1]
        sp = [s for s in ml._bubble_segs(row, False, False)
              if s[1] == rich.SPOILER]
        need([s[0] for s in sp] == ["机密", "secret"],
             f"R70F 命中词成遮盖段 -> {[s[0] for s in sp]}")
        need(all(int(s[2]) >= 1000 for s in sp), "R70F 遮盖段用 1000+ 命名空间")
        ml._toggle_spoiler(row, int(sp[0][2]))
        need((id(row), int(sp[0][2])) in ml._spoiler_open, "R70F 遮盖可点击揭示")
        ml.set_guard((), False)
        root.update()
        need(not any(s[1] == rich.SPOILER
                     for s in ml._bubble_segs(row, False, False)),
             "R70F 关闭后遮盖段还原")
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


# ---------- H：排行榜（桌面上报 → 双端广播 → 网页只读） ----------
def _fish_flow(cores, wtok):
    A = cores["甲"][0]
    bB = cores["乙"][1]
    need(A.send_fish_score("gomoku", 3), "R70H 上报摸鱼积分")
    ev = wait_for(bB, lambda e: e.get("t") == "fish_board"
                  and e.get("game") == "gomoku")
    need(ev is not None and [(x["nick"], x["score"]) for x in ev["entries"]]
         == [("甲", 3)], f"R70H 排行榜广播 -> {(ev or {}).get('entries')}")
    need(all(set(x) == {"uid", "nick", "score"} for x in (ev or {}).get("entries") or []),
         "R70H 榜单仅昵称+分数（隐私最小化）")
    A.send_fish_score("gomoku", 4)
    ev2 = wait_for(bB, lambda e: e.get("t") == "fish_board"
                   and e.get("game") == "gomoku"
                   and (e.get("entries") or [{}])[0].get("score") == 7)
    need(ev2 is not None, "R70H 积分累加（3+4=7）")
    st, d, _ = _req("GET", f"/api/fish_board?game=gomoku", cookie=f"mt_token={wtok}")
    need(st == 200 and d.get("ok")
         and [(x["nick"], x["score"]) for x in d.get("entries") or []] == [("甲", 7)],
         f"R70H 网页端只读榜单 -> {d.get('entries')}")
    st2, d2, _ = _req("GET", "/api/fish_board?game=gomoku")
    need(st2 == 401 and d2.get("ok") is False, "R70H 未登录拉榜被拒（401）")


def main() -> int:
    store = tempfile.mkdtemp(prefix="r70srv_")
    cfg = replace(CFG, fish_board_enabled=True)
    hub = server.Hub(cfg=cfg, store_dir=store)
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
                               tempfile.mkdtemp(prefix="r70h_"), "h"))
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

        _desktop_flow(hub, cores)
        _guard_flow()

        st, d, _ = _req("POST", "/api/login", {"nick": "丙"})
        if st != 200 or not d.get("ok"):
            _FAIL.append(f"R70H 网页登录失败 {st} {d}")
        else:
            print(f"[..] 网页 uid={d['uid']}")
            _fish_flow(cores, d["token"])
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
        print("R70 SMOKE FAIL")
        return 1
    print("R70 SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
