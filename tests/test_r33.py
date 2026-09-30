# -*- coding: utf-8 -*-
"""R33 快赢包回归：回应条覆盖语音/图片行 / 网页端回应增量 / 已读人数详情。

- R33① msg_list：语音/图片/贴纸/投票行可回应（_row_reactable），带回应时
  估算含 REACT_PAD 且渲染不崩溃（估算≈实测前提）；投票行补画回应条。
- R33② 服务器 REACTION 回帧带增量字段 emoji/actor/on（网页端 DOM 级加/摘用），
  且保留全量 reactions 兼容桌面端。
- R33③ READ_DETAIL：runs 新 READ_MARK 段；_heading_segs 已读标记独立段；
  服务器 _readers_for 权限（public/私聊双方/群成员）+ readers 列表；
  网页端 /api/read_detail 复用同一权限与数据。
"""
import http.client
import json
import socket
import threading
import time
from dataclasses import replace

import pytest

from client_core import ClientCore
from config import CFG
from server import Hub, serve as serve_tcp
from web import serve as serve_web
from widgets import runs
from widgets.msg_list import MsgList

FONT = ("Microsoft YaHei UI", 9)
REACT_PAD = MsgList.REACT_PAD


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    wport = _free_port()
    httpd = serve_web(h, port=wport)
    time.sleep(0.2)
    yield h, port, wport, stop
    stop.set()
    time.sleep(0.2)


class _Cli:
    """加密握手测试客户端。"""
    __test__ = False

    def __init__(self, port, nick):
        from crypto import client_handshake
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.chan = client_handshake(self.sock)
        self.nick = nick
        self.uid = None
        self.events = []
        self._lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            while True:
                hb, b = self.chan.recv_frame()
                with self._lock:
                    self.events.append((hb, b))
        except Exception:
            pass

    def send(self, header, body=b""):
        self.chan.send_frame(header, body)

    def wait(self, t, timeout=3.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, (h, b) in enumerate(self.events):
                    if h.get("t") == t and (pred is None or pred(h)):
                        del self.events[i]
                        return h, b
            time.sleep(0.01)
        return None, None

    def hello(self):
        self.send({"t": "hello", "nick": self.nick})
        h, _ = self.wait("welcome")
        if h:
            self.uid = h["uid"]
        return h

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ================= R33① 回应条覆盖语音/图片/贴纸/投票行 =================

@pytest.fixture(scope="module")
def root():
    try:
        import tkinter as tk
        r = tk.Tk()
    except Exception as exc:
        pytest.skip(f"无可用 Tk 显示环境: {exc}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except Exception:
        pass


def _mk_ml(root, me_uid=None):
    ml = MsgList(root, FONT, me_uid=me_uid)
    ml.configure(width=400, height=400)
    ml.pack()
    root.update_idletasks()
    return ml


def test_row_reactable_covers_voice_image_sticker_poll(root, tmp_path):
    """R33①：语音/图片/贴纸/投票行不再是回应盲区（非系统、有 seq 即可回应）。"""
    from PIL import Image
    ml = _mk_ml(root, me_uid=1)
    img = tmp_path / "p.png"
    Image.new("RGB", (30, 20), "#38f").save(str(img))
    msgs = [
        {"uid": 2, "nick": "乙", "channel": "public", "ts": time.time(),
         "text": "语音：", "voice": {"duration": 1.5}, "seq": 101},
        {"uid": 2, "nick": "乙", "channel": "public", "ts": time.time(),
         "image_path": str(img), "seq": 102},
        {"uid": 2, "nick": "乙", "channel": "public", "ts": time.time(),
         "text": "[:cat:]", "sticker_custom": "cat", "seq": 103},
        {"uid": 2, "nick": "乙", "channel": "public", "ts": time.time(),
         "text": "投票", "poll": {"question": "Q", "options": ["a", "b"],
                                  "end": time.time() + 600}, "seq": 104},
    ]
    for m in msgs:
        ml.append(m)
    for i in range(4):
        assert ml._row_reactable(i), f"第 {i} 行应可回应"
    ml.destroy()


def test_estimate_includes_react_pad_for_special_rows(root):
    """R33①：带回应的语音/图片/贴纸行，估算高度含回应条占位（与绘制一致）。"""
    from PIL import Image
    ml = _mk_ml(root, me_uid=1)
    import tempfile, os
    fd, p = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    Image.new("RGB", (30, 20), "#38f").save(p)
    base = [
        {"uid": 2, "nick": "乙", "channel": "public", "ts": time.time(),
         "text": "语音", "voice": {"duration": 2.0}},
        {"uid": 2, "nick": "乙", "channel": "public", "ts": time.time(),
         "image_path": p},
        {"uid": 2, "nick": "乙", "channel": "public", "ts": time.time(),
         "text": "[:cat:]", "sticker_custom": "cat"},
    ]
    reacts = {"👍": {"2": time.time()}}
    for k, m in enumerate(base):
        # 每行独立 uid：避免相邻图片触发 R31 相册分组（成员行 0 高，估算不可比）
        a = dict(m, uid=10 + 2 * k, seq=200 + 2 * k + 1)
        b = dict(m, uid=11 + 2 * k, seq=200 + 2 * k + 2, reactions=dict(reacts))
        ml.append(a)
        i0 = ml.count - 1
        est0 = ml._estimate(i0, ml._rows[i0])
        ml.append(b)
        i1 = ml.count - 1
        est1 = ml._estimate(i1, ml._rows[i1])
        assert est1 > est0, f"特殊行 {k} 带回应的估算应含回应条占位"
    ml._render()                          # 渲染一遍不崩溃
    os.remove(p)
    ml.destroy()


# ================= R33② REACTION 增量字段 =================

def test_reaction_frame_carries_incremental_fields(hub):
    h, port, _w, _ = hub
    a = _Cli(port, "作者")
    b = _Cli(port, "回应者")
    assert a.hello() and b.hello()
    a.send({"t": "chat", "channel": "public", "text": "看看这条"})
    ch, _ = b.wait("chat", pred=lambda x: x.get("uid") == a.uid)
    assert ch and ch.get("seq")
    seq = ch["seq"]
    b.send({"t": "reaction", "seq": seq, "emoji": "👍", "on": True})
    rf, _ = a.wait("reaction", pred=lambda x: x.get("seq") == seq)
    assert rf
    # 全量字段保留（桌面端兼容）+ 增量字段齐备（网页端 DOM 级加/摘）
    assert rf["reactions"]["👍"]                      # 全量
    assert rf["emoji"] == "👍" and rf["actor"] == b.uid and rf["on"] is True
    # 摘下也带增量
    b.send({"t": "reaction", "seq": seq, "emoji": "👍", "on": False})
    rf2, _ = a.wait("reaction", pred=lambda x: x.get("seq") == seq)
    assert rf2 and rf2["on"] is False and "👍" not in rf2["reactions"]
    a.close()
    b.close()


# ================= R33③ 已读人数详情 =================

def test_runs_read_mark_kind_flows_through_wrap():
    """READ_MARK 段经 wrap_segments 保留类型（可绑定渲染），宽度度量与 plain 一致。"""
    meas = lambda s: len(s) * 10
    segs = [("12:00 甲: ", runs.PLAIN), ("✓已读  ", runs.READ_MARK)]
    lines = runs.wrap_segments(segs, 400, meas)
    assert lines and lines[0][0][1] == runs.PLAIN
    kinds = {k for _t, k in lines[0]}
    assert runs.READ_MARK in kinds
    assert runs.line_width(lines[0], meas) > 0


def test_heading_segs_split_read_marker(root):
    """自己消息已读 → 行头含独立 ✓已读 READ_MARK 段；他人消息/未读不含。"""
    ml = _mk_ml(root, me_uid=1)
    ml.append({"uid": 1, "nick": "甲", "channel": "public",
               "ts": time.time(), "text": "我的消息", "seq": 301})
    ml.append({"uid": 2, "nick": "乙", "channel": "public",
               "ts": time.time(), "text": "别人的消息", "seq": 302})
    own_row = ml._rows[0]
    other_row = ml._rows[1]
    # 未读：无 READ_MARK 段
    assert all(k != runs.READ_MARK for _t, k in ml._heading_segs(own_row, False, True))
    ml.set_reads({2: 301})                     # 乙读到 301
    kinds_own = [k for _t, k in ml._heading_segs(own_row, False, True)]
    assert runs.READ_MARK in kinds_own
    assert all(k != runs.READ_MARK for _t, k in ml._heading_segs(other_row, False, False))
    ml.destroy()


def test_server_readers_for_permission_and_payload(hub):
    """_readers_for：public/私聊双方有权；外人无权；payload 带 nick/seq。"""
    h, port, _w, _ = hub
    a = _Cli(port, "甲")
    b = _Cli(port, "乙")
    c = _Cli(port, "丙")
    assert a.hello() and b.hello() and c.hello()
    a.send({"t": "chat", "channel": "public", "text": "已读测试"})
    ch, _ = b.wait("chat", pred=lambda x: x.get("uid") == a.uid)
    seq = ch["seq"]
    b.send({"t": "read", "channel": "public", "seq": seq})
    b.wait("read")
    time.sleep(0.1)
    # public：请求者甲有权，readers 含乙（nick 补全）
    lst = h._readers_for("public", a.uid)
    assert lst is not None
    hit = [r for r in lst if r["uid"] == b.uid]
    assert hit and hit[0]["nick"] == "乙" and hit[0]["seq"] >= seq
    # 私聊：参与者有权；外人无权
    key = f"private:{min(a.uid, b.uid)}:{max(a.uid, b.uid)}"
    assert h._readers_for(key, a.uid) is not None
    assert h._readers_for(key, c.uid) is None
    # 不存在的会话键：空列表（有权但没人已读）
    assert h._readers_for("public", c.uid) is not None
    a.close()
    b.close()
    c.close()


def test_read_detail_frame_roundtrip(hub):
    """桌面协议：READ_DETAIL 请求 → 单播回 readers 列表。"""
    h, port, _w, _ = hub
    a = _Cli(port, "甲")
    b = _Cli(port, "乙")
    assert a.hello() and b.hello()
    a.send({"t": "chat", "channel": "public", "text": "回帧测试"})
    ch, _ = b.wait("chat", pred=lambda x: x.get("uid") == a.uid)
    seq = ch["seq"]
    b.send({"t": "read", "channel": "public", "seq": seq})
    b.wait("read")
    time.sleep(0.1)
    a.send({"t": "read_detail", "key": "public"})
    rd, _ = a.wait("read_detail")
    assert rd and rd["key"] == "public"
    assert any(r["uid"] == b.uid and r["seq"] >= seq for r in rd["readers"])
    # 无权键 → error 帧
    a.send({"t": "read_detail", "key": "private:999:998"})
    err, _ = a.wait("error")
    assert err and err.get("code") == "forbid"
    a.close()
    b.close()


def test_web_read_detail_api(hub):
    """网页端 /api/read_detail：登录 → 查询成功；外人查私聊键 → 403。"""
    h, _port, wport, _ = hub
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn.request("POST", "/api/login", json.dumps({"nick": "网页乙"}).encode(),
                 {"Content-Type": "application/json"})
    d = json.loads(conn.getresponse().read().decode())
    assert d["ok"]
    token = d["token"]
    body = json.dumps({"token": token, "key": "public"}).encode()
    conn.request("POST", "/api/read_detail", body,
                 {"Content-Type": "application/json"})
    r = json.loads(conn.getresponse().read().decode())
    assert r["ok"] and isinstance(r["readers"], list)
    # 外人查私聊键（不包含自己 uid）→ 403
    body2 = json.dumps({"token": token, "key": "private:999:998"}).encode()
    conn.request("POST", "/api/read_detail", body2,
                 {"Content-Type": "application/json"})
    resp = conn.getresponse()
    r2 = json.loads(resp.read().decode())
    assert resp.status == 403 and not r2["ok"]
    conn.close()


def test_client_core_send_read_detail(tmp_path):
    """core.send_read_detail 发出 {t=read_detail, key}。"""
    core = ClientCore(host="127.0.0.1", port=1, nick="核心君",
                      history_dir=str(tmp_path / "h"))
    sent = []
    core._send_frame = lambda header, body=b"": sent.append(header) or True
    assert core.send_read_detail("public")
    assert sent and sent[0]["t"] == "read_detail" and sent[0]["key"] == "public"
