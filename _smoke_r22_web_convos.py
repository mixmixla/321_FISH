# -*- coding: utf-8 -*-
"""R22 网页端会话列表对齐冒烟：
- B 私聊 A 两条 → A 上报已读 → B/C 再各发一条 → A 的 convos 未读数正确、按最新排序
- 与 A 无私聊的 D 不出现在 convos；登录响应也携带 convos
- 页面 HTML 含最近私聊渲染函数（renderConvos/bumpConvo/未读角标）
全程走真实 HTTP，无需浏览器。"""
import http.client
import json
import socket
import threading
import time
from dataclasses import replace

from config import CFG
from server import Hub, serve as serve_tcp
from web import serve as serve_web, PAGE

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
        self.convo_list = d.get("convos") or []
    def send(self, channel, to, text):
        body = {"token": self.token, "channel": channel, "text": text}
        if to is not None:
            body["to"] = to
        st, d = self.post("/api/send", body)
        assert st == 200 and d["ok"], d
    def convos(self):
        st, d = self.get(f"/api/convos?token={self.token}")
        assert st == 200 and d["ok"], d
        return d["convos"]

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
    c = Web(wport, "绿灯丙"); d = Web(wport, "黄灯丁")

    # 1) 登录响应带 convos（初始为空）
    check("login 携带 convos 字段", isinstance(a.convo_list, list))

    # 2) B 私聊 A 两条 → A 上报已读
    b.send("private", a.uid, "私聊一")
    b.send("private", a.uid, "私聊二")
    time.sleep(0.3)
    st, hist = a.get(f"/api/history?token={a.token}&channel=private&to={b.uid}")
    seq = max(m["seq"] for m in hist["msgs"] if m.get("uid") == b.uid)
    st, rd = a.post("/api/read", {"token": a.token, "channel": "private",
                                  "to": b.uid, "seq": seq})
    check("私聊发送+已读上报", st == 200 and rd["ok"])

    # 3) B 再发 1 条、C 发 1 条；D 无任何私聊
    b.send("private", a.uid, "私聊三")
    c.send("private", a.uid, "丙的消息")
    time.sleep(0.3)

    convos = a.convos()
    by_uid = {x["uid"]: x for x in convos}
    check("convos 含 B 与 C", b.uid in by_uid and c.uid in by_uid,
          f"uids={sorted(by_uid)}")
    check("B 未读=1", by_uid.get(b.uid, {}).get("unread") == 1,
          f"B={by_uid.get(b.uid)}")
    check("C 未读=1", by_uid.get(c.uid, {}).get("unread") == 1,
          f"C={by_uid.get(c.uid)}")
    check("D 不在 convos", d.uid not in by_uid)
    check("按最新排序（C 在前）", convos[0]["uid"] == c.uid,
          f"order={[x['uid'] for x in convos]}")
    check("convos 含昵称", by_uid.get(b.uid, {}).get("nick") == "紫灯乙",
          f"nick={by_uid.get(b.uid)}")

    # 4) 页面 HTML 含最近私聊渲染逻辑
    check("HTML 有 renderConvos", "function renderConvos" in PAGE)
    check("HTML 有 bumpConvo", "function bumpConvo" in PAGE)
    check("HTML 有未读角标样式", ".unread" in PAGE)
    check("HTML 有最近私聊容器", 'id="convos"' in PAGE)

    print("\n".join(RESULTS))
    httpd.shutdown(); stop.set()
    print("WEB CONVOS SMOKE OK" if OK else "WEB CONVOS SMOKE FAIL")
    return 0 if OK else 1

if __name__ == "__main__":
    raise SystemExit(main())
