# -*- coding: utf-8 -*-
"""R20 网页端增强冒烟：
- 网页端建群/加入/成员面板 detail（角色/禁言/公告）
- 公聊 + 已读：A 发消息 → B 上报已读 → A 的 SSE 流收到 read 事件（uid/seq）
全程走真实 HTTP + SSE，无需浏览器。"""
import http.client
import json
import socket
import threading
import time
from dataclasses import replace

from config import CFG
from server import Hub, serve as serve_tcp
from web import serve as serve_web

OK = True
RESULTS = []

def check(name, cond, extra=""):
    global OK
    OK = OK and cond
    RESULTS.append(f"[{'OK' if cond else 'FAIL'}] {name} {extra}")

def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

class Web:
    def __init__(self, port, nick):
        self.port = port
        self.login(nick)
    def post(self, path, body):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=8)
        c.request("POST", path, json.dumps(body).encode(),
                  {"Content-Type": "application/json"})
        r = c.getresponse(); d = json.loads(r.read().decode() or "{}"); c.close()
        return r.status, d
    def get(self, path):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=8)
        c.request("GET", path); r = c.getresponse()
        d = json.loads(r.read().decode() or "{}"); c.close()
        return r.status, d
    def login(self, nick):
        st, d = self.post("/api/login", {"nick": nick})
        assert st == 200 and d["ok"], d
        self.token = d["token"]; self.uid = d["uid"]
    def group(self, action, **kw):
        st, d = self.post("/api/group", {"token": self.token, "action": action, **kw})
        assert st == 200 and d["ok"], d
        return d
    def detail(self, gid):
        st, d = self.get(f"/api/group_detail?token={self.token}&gid={gid}")
        assert st == 200 and d["ok"], d
        return d

def main() -> int:
    global OK
    cfg = replace(CFG, audit_dir="_tmp_gui/audit")
    hub = Hub(cfg=cfg, audit_dir="_tmp_gui/audit")
    tport = _free_port(); wport = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, tport, stop, False), daemon=True).start()
    httpd = serve_web(hub, port=wport)
    time.sleep(0.3)
    a = Web(wport, "红灯甲"); b = Web(wport, "紫灯乙")

    # 1) 建群 + 加入 + detail 成员/角色
    d = a.group("create", name="巡检组")
    gid = next(g["gid"] for g in d["groups"] if g["name"] == "巡检组")
    a.group("announce", gid=gid, text="交班前跑完巡检")
    b.group("join", gid=gid)
    dt = a.detail(gid)
    check("create+join+announce", dt["announce"] == "交班前跑完巡检"
          and {m["nick"] for m in dt["members"]} == {"红灯甲", "紫灯乙"},
          f"members={[m['nick'] for m in dt['members']]}")
    a.group("admin", gid=gid, target=b.uid, enable=True)
    r = next(m for m in a.detail(gid)["members"] if m["uid"] == b.uid)
    check("set admin persists", r["role"] == "admin")
    a.group("kick", gid=gid, target=b.uid)
    check("kick removes member", all(m["uid"] != b.uid for m in a.detail(gid)["members"]))

    # 2) SSE 已读回传：A 发公聊 → B 上报已读 → A 流收 read 事件
    events = []  # (uid, seq)
    done = threading.Event()
    def sse():
        c = http.client.HTTPConnection("127.0.0.1", wport, timeout=10)
        c.request("GET", "/api/events?token=" + a.token)
        r = c.getresponse()
        while not done.is_set():
            ln = r.readline()
            if not ln:
                break
            line = ln.decode("utf-8", "replace")
            if line.startswith("data:") and '"t": "read"' in line:
                d = json.loads(line[6:].strip())
                events.append((d.get("uid"), d.get("seq")))
                pt = d
                if pt.get("key") == "public":
                    done.set()
        c.close()
    th = threading.Thread(target=sse, daemon=True)
    th.start()
    a.post("/api/send", {"token": a.token, "channel": "public", "text": "点名"})
    time.sleep(0.4)
    seq = None
    st, d = a.get("/api/history?token=" + a.token + "&channel=public")
    for m in d.get("msgs", []):
        if m.get("text") == "点名":
            seq = m.get("seq")
    check("send+history seq", seq is not None, f"seq={seq}")
    assert seq is not None
    b.post("/api/read", {"token": b.token, "channel": "public", "seq": seq})
    done.wait(5)
    check("A sees read(uid,seq)", any(u == b.uid and s >= seq for u, s in events),
          f"events={events}")

    print("\n".join(RESULTS))
    done.set(); httpd.shutdown(); stop.set()
    print("WEB SMOKE OK" if OK else "WEB SMOKE FAIL")
    return 0 if OK else 1

if __name__ == "__main__":
    raise SystemExit(main())