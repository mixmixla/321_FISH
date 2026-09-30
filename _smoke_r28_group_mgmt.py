# -*- coding: utf-8 -*-
"""R28 群管理补全冒烟（web + TCP 双通道）：
- 网页端：owner 建群 → 取邀请码（8 位大写十六进制，复用不变）→ 他人凭码入群（小写容错）
  → detail 成员数/上限 → owner 改名 → 普通成员改名被拒 → 非成员取码被拒 → 未知 action 400
- TCP 桌面端：owner 取码、凭码入群、改名同步 group_state/self.groups、成员上限字段
全程走真实 HTTP/SSE/协议帧，无需浏览器与手工 GUI。"""
import http.client
import json
import socket
import threading
import time
from dataclasses import replace

from config import CFG
from server import Hub, serve as serve_tcp
from web import serve as serve_web
from client_core import ClientCore

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
        return st, d

    def detail(self, gid):
        st, d = self.get(f"/api/group_detail?token={self.token}&gid={gid}")
        assert st == 200 and d["ok"], d
        return d


class Collector:
    def __init__(self, core):
        self.events = []
        self._lock = threading.Lock()
        core._on_event = self._on

    def _on(self, ev):
        with self._lock:
            self.events.append(ev)

    def wait(self, t, timeout=3.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, e in enumerate(self.events):
                    if e.get("t") == t and (pred is None or pred(e)):
                        del self.events[i]
                        return e
            time.sleep(0.01)
        return None


def _spawn(port, nick, hist):
    core = ClientCore(host="127.0.0.1", port=port, nick=nick,
                      history_dir=hist, heartbeat_interval=0.1,
                      heartbeat_timeout=0.8, reconnect_base=0.05, reconnect_max=0.3)
    col = Collector(core)
    core.start()
    assert col.wait("welcome") is not None, f"{nick} 未上线"
    assert col.wait("state", pred=lambda e: e.get("state") == "online")
    return core, col


def main() -> int:
    global OK
    cfg = replace(CFG, audit_dir="_tmp_gui/audit")
    hub = Hub(cfg=cfg, audit_dir="_tmp_gui/audit")
    tport = _free_port(); wport = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, tport, stop, False), daemon=True).start()
    httpd = serve_web(hub, port=wport)
    time.sleep(0.3)

    # ---- 网页端流程 ----
    a = Web(wport, "红宝"); b = Web(wport, "蓝宝"); x = Web(wport, "外人")
    st, d = a.group("create", name="开黑群")
    gid = next(g["gid"] for g in d["groups"] if g["name"] == "开黑群")
    check("web create + member_max", st == 200 and d["ok"]
          and all("member_max" in g for g in d["groups"]), f"gid={gid}")

    st, d = a.group("invite", gid=gid)
    code = hub.groups[gid]["invite"]
    check("web invite get", st == 200 and d["ok"]
          and len(code) == 8 and code == code.upper()
          and all(c in "0123456789ABCDEF" for c in code), f"code={code}")

    st, d = a.group("invite", gid=gid)
    check("invite reuse", st == 200 and hub.groups[gid]["invite"] == code)

    st, d = b.group("join_invite", code=code.lower())      # 小写容错
    check("web join by invite", st == 200 and d["ok"] and b.uid in hub.groups[gid]["members"])

    dt = a.detail(gid)
    check("detail members+max", len(dt["members"]) == 2
          and dt["member_max"] == hub.cfg.group_max_members, f"n={len(dt['members'])}")

    st, d = a.group("rename", gid=gid, name="开黑一队")
    check("web rename", st == 200 and d["ok"] and hub.groups[gid]["name"] == "开黑一队")
    check("detail renamed", a.detail(gid)["name"] == "开黑一队")

    st, d = b.group("rename", gid=gid, name="抢名")        # 成员无权 → 服务端拒绝
    check("member rename denied", st == 200 and hub.groups[gid]["name"] == "开黑一队")

    st, d = x.group("invite", gid=gid)                     # 非成员取码 → 拒绝
    check("outsider invite denied", st == 200 and hub.groups[gid]["invite"] == code)

    st, d = a.group("nonsense")
    check("unknown action 400", st == 400 and not d["ok"])

    # ---- TCP 桌面端流程 ----
    alice, ac = _spawn(tport, "tcp-a", "_tmp_gui/h_a")
    bob, bc = _spawn(tport, "tcp-b", "_tmp_gui/h_b")
    try:
        assert alice.create_group("TCP 群")
        gs = ac.wait("group_state", pred=lambda e: e.get("name") == "TCP 群")
        gid2 = gs["gid"]
        assert alice.get_group_invite(gid2)
        ev = ac.wait("group_invite", pred=lambda e: e.get("gid") == gid2)
        code2 = ev["code"]
        check("tcp invite 8-hex", len(code2) == 8 and code2 == code2.upper())

        assert bob.join_group_by_invite(code2)
        got = bc.wait("group_state", pred=lambda e: e.get("gid") == gid2
                      and "凭邀请码加入" in (e.get("text") or ""))
        check("tcp join by invite", got is not None and gid2 in bob._joined_groups)

        assert alice.rename_group(gid2, "改名了")
        gs2 = ac.wait("group_state", pred=lambda e: e.get("gid") == gid2
                      and e.get("name") == "改名了")
        check("tcp rename sync", gs2 is not None and alice.groups[gid2]["name"] == "改名了")
        ac.wait("group_list", pred=lambda e: any(
            g["gid"] == gid2 and g["member_max"] == hub.cfg.group_max_members
            for g in e["groups"]))
        check("tcp member_max field", alice.groups[gid2].get("member_max")
              == hub.cfg.group_max_members)
    finally:
        alice.stop(); bob.stop()

    print("\n".join(RESULTS))
    httpd.shutdown(); stop.set()
    print("R28 SMOKE OK" if OK else "R28 SMOKE FAIL")
    return 0 if OK else 1


if __name__ == "__main__":
    raise SystemExit(main())
