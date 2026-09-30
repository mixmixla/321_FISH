# -*- coding: utf-8 -*-
"""R23 网页端图片/文件消息冒烟：
- 上传图片/文件 → /api/upload 返回 fid；/api/send 带 file 发消息进历史
- 对端 GET /api/file 下载：内容一致、图片 inline / 附件 attachment
- 超限上传拒绝、伪造/非法 fid 拒绝（历史不增加、下载 404）
- 桌面端（TCP）收到 file 消息 → client_core 历史含 file；msg_list _Row 渲染 [图片]/[文件] 占位
- 页面 HTML 含上传/渲染逻辑
"""
import base64
import http.client
import json
import os
import shutil
import socket
import threading
import time
from dataclasses import replace

from config import CFG
from crypto import client_handshake
from server import Hub, serve as serve_tcp
from client_core import ClientCore
from client import ChatWindow
from widgets.msg_list import _Row
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
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("POST", path, json.dumps(body).encode(),
                  {"Content-Type": "application/json"})
        r = c.getresponse(); d = json.loads(r.read().decode() or "{}"); c.close()
        return r.status, d
    def login(self, nick):
        st, d = self.post("/api/login", {"nick": nick})
        assert st == 200 and d["ok"], d
        self.token = d["token"]; self.uid = d["uid"]
    def upload(self, name, kind, data):
        return self.post("/api/upload",
                         {"token": self.token, "name": name, "kind": kind,
                          "data": base64.b64encode(data).decode()})
    def send_file(self, f, channel="public", to=None):
        body = {"token": self.token, "channel": channel, "file": f}
        if to is not None:
            body["to"] = to
        return self.post("/api/send", body)
    def history(self, channel="public", to=None):
        q = f"/api/history?token={self.token}&channel={channel}"
        if to is not None:
            q += f"&to={to}"
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", q); r = c.getresponse()
        d = json.loads(r.read().decode() or "{}"); c.close()
        return d.get("msgs", [])
    def download(self, fid):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", f"/api/file?token={self.token}&fid={fid}")
        r = c.getresponse(); data = r.read()
        hdrs = dict(r.getheaders()); c.close()
        return r.status, data, hdrs

def main() -> int:
    global OK
    shutil.rmtree("_tmp_gui/web_files", ignore_errors=True)
    cfg = replace(CFG, audit_dir="_tmp_gui/audit", web_files_dir="_tmp_gui/web_files",
                  web_file_max=20000)          # 调小上限便于测超限拒绝
    hub = Hub(cfg=cfg, audit_dir="_tmp_gui/audit")
    tport = _free_port(); wport = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(hub, tport, stop, False), daemon=True).start()
    httpd = serve_web(hub, port=wport)
    time.sleep(0.3)

    # 桌面端（TCP）挂线，验证 web 文件消息能送达桌面端
    core = ClientCore(host="127.0.0.1", port=tport, nick="桌端甲")
    app = ChatWindow(core)
    core.start()
    deadline = time.time() + 6
    while not core.connected and time.time() < deadline:
        app.root.update(); time.sleep(0.03)

    a = Web(wport, "网页甲"); b = Web(wport, "网页乙")

    # 1) 上传图片 + 文件
    img = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
                           "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")  # 1x1 PNG
    st, d = a.upload("小图.png", "image", img)
    check("上传图片成功", st == 200 and d["ok"] and d["file"]["kind"] == "image",
          f"st={st}")
    if not d["ok"]:
        print("\n".join(RESULTS)); return 1
    fimg = d["file"]
    st, d = a.upload("报告.txt", "file", b"hello web file \xe6\x96\x87\xe6\xa1\xa3")
    check("上传文件成功", st == 200 and d["ok"] and d["file"]["kind"] == "file")
    ffile = d["file"]

    # 2) 发送 file 消息 → 对端历史可见
    st, d = a.send_file(fimg)
    check("发送图片消息成功", st == 200 and d["ok"])
    st, d = a.send_file(ffile)
    check("发送文件消息成功", st == 200 and d["ok"])
    time.sleep(0.4)
    msgs = b.history("public")
    m_img = next((m for m in msgs if m.get("file", {}).get("fid") == fimg["fid"]), None)
    m_file = next((m for m in msgs if m.get("file", {}).get("fid") == ffile["fid"]), None)
    check("对端历史含图片消息", m_img is not None)
    check("对端历史含文件消息", m_file is not None)
    check("消息 file 元数据完整", bool(m_img and m_img["file"].get("name") == "小图.png"
                                        and m_img["file"].get("size") == len(img)))

    # 3) 下载：内容一致 + 图片 inline / 附件 attachment
    st, data, hdrs = b.download(fimg["fid"])
    check("图片下载 200 且内容一致", st == 200 and data == img, f"st={st} len={len(data)}")
    check("图片 Content-Type=image/png", hdrs.get("Content-Type") == "image/png",
          hdrs.get("Content-Type", ""))
    check("图片 inline", "inline" in hdrs.get("Content-Disposition", ""),
          hdrs.get("Content-Disposition", ""))
    st, data, hdrs = b.download(ffile["fid"])
    check("文件下载 200 且内容一致", st == 200 and data == b"hello web file \xe6\x96\x87\xe6\xa1\xa3")
    check("文件 attachment", "attachment" in hdrs.get("Content-Disposition", ""),
          hdrs.get("Content-Disposition", ""))

    # 4) 超限拒绝
    st, d = a.upload("超大.bin", "file", b"x" * 30000)
    check("超限上传被拒", st == 400 and not d["ok"], f"st={st} d={d}")

    # 5) 伪造 fid 发送不产生消息；非法 fid 下载 404
    n0 = len(b.history("public"))
    st, d = a.send_file({"fid": "f" * 32, "name": "伪造.bin", "size": 1, "kind": "file"})
    time.sleep(0.3)
    check("伪造 fid 发送被拒（历史不增加）", len(b.history("public")) == n0,
          f"n0={n0} n1={len(b.history('public'))}")
    st, _d, _h = b.download("../server.py")
    check("非法 fid 下载 404", st == 404, f"st={st}")

    # 6) 桌面端收到 file 消息：client_core 历史 + msg_list 占位渲染
    hist = core.history("public")
    d_img = next((m for m in hist if m.get("file", {}).get("fid") == fimg["fid"]), None)
    check("桌面端历史含图片消息", d_img is not None)
    row = _Row(d_img)
    check("msg_list 渲染 [图片] 占位", "[图片] 小图.png" in row.body, row.body)
    d_file = next((m for m in hist if m.get("file", {}).get("fid") == ffile["fid"]), None)
    rowf = _Row(d_file)
    check("msg_list 渲染 [文件] 占位", "[文件] 报告.txt" in rowf.body
          and "（21B）" in rowf.body, rowf.body)

    # 7) 页面 HTML 含上传/渲染逻辑
    check("HTML 含 uploadSend", "function uploadSend" in PAGE)
    check("HTML 含 fmtSize", "function fmtSize" in PAGE)
    check("HTML 含图片按钮", 'id="btnImg"' in PAGE and 'id="fimg"' in PAGE)
    check("HTML 含图片渲染", "f.kind===\"image\"" in PAGE and ".bub img" in PAGE)

    print("\n".join(RESULTS))
    httpd.shutdown(); stop.set()
    print("WEB FILE SMOKE OK" if OK else "WEB FILE SMOKE FAIL")
    return 0 if OK else 1

if __name__ == "__main__":
    raise SystemExit(main())
