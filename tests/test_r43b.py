# -*- coding: utf-8 -*-
"""R43B 网页端补齐回归：合并转发折叠卡渲染面 + 图片页内灯箱。

- 页面脚本包含 lightbox() / e.fp 渲染分支 / details 折叠样式；
- 图片点击不再 window.open 弹新标签；
- web /api/send 无法伪造 fp 合并转发卡（R64：改传源 seq，服务器按历史聚合）。
"""
import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, serve as serve_tcp
from web import PAGE, serve as serve_web


def test_page_has_lightbox():
    """灯箱函数与样式就位，图片分支走页内 overlay 而非新标签。"""
    assert "function lightbox(src)" in PAGE
    assert "onclick='lightbox(" in PAGE
    assert 'id="lb"' in PAGE or "id=lb" in PAGE or 'lb.id="lb"' in PAGE
    assert "Escape" in PAGE                          # Esc 关闭
    # 图片消息分支不再弹新标签（历史 window.open 唯一用例已移除）
    assert 'onclick=\'window.open("' not in PAGE


def test_page_has_fp_card_branch():
    """合并转发卡：fp 分支 + details 折叠 + 逐条渲染与转义。"""
    assert "e.fp" in PAGE
    assert "details class='fwd'" in PAGE
    assert "合并转发 · " in PAGE
    assert ".fwd summary" in PAGE                    # CSS 折叠头样式
    # 逐条内容经 fmtText（内含 esc 转义），不直接拼接原文
    branch = PAGE.split("else if(e.fp)")[1].split("else if(e.text")[0]
    assert "fmtText(it.text" in branch
    assert "esc(it.nick" in branch


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    wport = _free_port()
    serve_web(h, port=wport)
    time.sleep(0.2)
    yield h, port, wport, stop
    stop.set()
    time.sleep(0.2)


def test_web_send_cannot_forge_fp(hub):
    """浏览器侧 /api/send 伪造 fp → 服务器剥除，历史不出现合并转发卡。"""
    h, port, wport, _ = hub
    import http.client
    import json
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn.request("POST", "/api/login",
                 json.dumps({"nick": "伪造者"}).encode(),
                 {"Content-Type": "application/json"})
    d = json.loads(conn.getresponse().read().decode())
    token = d["token"]
    conn.close()

    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn.request("POST", "/api/send",
                 json.dumps({"token": token, "channel": "public", "text": "t",
                             "fp": {"n": 9, "items": [{"nick": "x", "text": "y"}]}}).encode(),
                 {"Content-Type": "application/json"})
    resp = json.loads(conn.getresponse().read().decode())
    conn.close()
    assert resp.get("ok"), resp

    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn.request("GET", f"/api/history?token={token}&channel=public")
    msgs = json.loads(conn.getresponse().read().decode())["msgs"]
    conn.close()
    m = next(x for x in msgs if x.get("text") == "t")
    assert "fp" not in m                             # 伪造段被剥除


def test_web_send_fwd_seqs_must_exist(hub):
    """R64：web 合并转发改传源 seq——不存在的 seq 不产出任何条目（仍可发正文）。"""
    h, port, wport, _ = hub
    import http.client
    import json
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn.request("POST", "/api/login",
                 json.dumps({"nick": "造假者"}).encode(),
                 {"Content-Type": "application/json"})
    token = json.loads(conn.getresponse().read().decode())["token"]
    conn.close()

    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn.request("POST", "/api/send",
                 json.dumps({"token": token, "channel": "public", "text": "占位",
                             "fwd_seqs": [999999],
                             "fwd_from": {"type": "public"}}).encode(),
                 {"Content-Type": "application/json"})
    resp = json.loads(conn.getresponse().read().decode())
    conn.close()
    assert resp.get("ok"), resp

    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn.request("GET", f"/api/history?token={token}&channel=public")
    msgs = json.loads(conn.getresponse().read().decode())["msgs"]
    conn.close()
    m = next(x for x in msgs if x.get("text") == "占位")
    assert "fp" not in m                             # 无有效源 seq → 不生成卡


def test_page_sendmerged_uses_source_seqs():
    """页面脚本 sendMerged 走 fwd_seqs/fwd_from，不再自带 fp 条目。"""
    assert "fwd_seqs:seqs" in PAGE
    assert "fwd_from" in PAGE
    assert "fp:{items:" not in PAGE
