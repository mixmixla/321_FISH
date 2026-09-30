# -*- coding: utf-8 -*-
"""R65 网页端贴纸包深化：登录数据面 / 商店订阅 / 包管理 / 封面直出 / 前端已铺。

覆盖：
- 登录 & whoami 回包带 sticker_pack_meta + sticker_subs（导航条与 🔒 判定依据）
- POST /api/shop：list（拉目录）/ sub（订阅/退订）→ 落 Hub 权威状态
- POST /api/pack：rename / del / cover_set / cover_del / reorder → 落 Hub 权威状态
- GET /api/packcover：设封面后 200 出图；无封面 404；鉴权缺失 401
- 前端已铺标记：包导航条 / 试看常量 / 封面端点 / 商店回帧分支
"""
import base64
import http.client
import json
import os
import socket
import threading
import time
import urllib.parse
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, serve as serve_tcp
from web import serve as serve_web

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c626001000000ffff030000060005"
    "57bfabd40000000049454e44ae426082")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Web:
    """轻量 web HTTP 客户端（登录拿 token + POST/GET，可读原始字节）。"""

    def __init__(self, port, nick):
        self.port = port
        self.token = None
        self.uid = None
        self.last_login = None
        self.login(nick)

    def _post(self, path, body):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", path, json.dumps(body).encode(),
                     {"Content-Type": "application/json"})
        r = conn.getresponse()
        raw = r.read()
        conn.close()
        try:
            data = json.loads(raw.decode() or "{}")
        except ValueError:
            data = {}
        return r.status, data

    def _raw_get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, data

    def login(self, nick):
        st, d = self._post("/api/login", {"nick": nick})
        assert st == 200 and d["ok"], d
        self.token = d["token"]
        self.uid = d["uid"]
        self.last_login = d
        return d

    def shop(self, **kw):
        return self._post("/api/shop", {"token": self.token, **kw})

    def pack(self, **kw):
        return self._post("/api/pack", {"token": self.token, **kw})


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
    try:
        httpd.shutdown()
    except Exception:
        pass
    time.sleep(0.2)


def _seed_custom(h, code="w1", pack="网包"):
    """直接在 Hub 里造一条自定义贴纸（含图片文件），返回其 meta。"""
    h.custom_stickers[code] = {"code": code, "label": code,
                               "pack": pack, "ext": "png", "order": 0}
    with open(os.path.join(h.sticker_dir, f"{code}.png"), "wb") as f:
        f.write(PNG_1PX)
    return h.custom_stickers[code]


# ================= 登录数据面 =================

def test_login_and_whoami_expose_pack_meta_and_subs(hub):
    h, port, wport, _ = hub
    w = _Web(wport, "网页甲")
    d = w.last_login
    assert "sticker_pack_meta" in d and "sticker_subs" in d
    assert d["sticker_subs"] == h._sticker_subs_for(w.uid)
    # whoami 同款字段
    st, d2 = w._post("/api/login", {"nick": "网页甲"})   # 二次登录等价探活
    assert st == 200 and d2["ok"]
    assert "sticker_pack_meta" in d2 and "sticker_subs" in d2


# ================= 商店（订阅/退订） =================

def test_shop_list_and_sub_toggle(hub):
    h, port, wport, _ = hub
    w = _Web(wport, "订阅君")
    st, d = w.shop(op="list")
    assert st == 200 and d["ok"]
    # 订阅未默认订阅的包
    st, d = w.shop(op="sub", pack_id="mood", on=True)
    assert st == 200 and d["ok"]
    assert "mood" in h._sticker_subs_for(w.uid)
    # 退订
    st, d = w.shop(op="sub", pack_id="mood", on=False)
    assert st == 200 and d["ok"]
    assert "mood" not in h._sticker_subs_for(w.uid)
    # 非法操作
    st, d = w.shop(op="nope")
    assert st == 400 and not d["ok"]


def test_shop_requires_login(hub):
    h, port, wport, _ = hub
    st, d = _Web(wport, "临时").shop(op="list")
    assert st == 200 and d["ok"]                     # 有 token 正常
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn.request("POST", "/api/shop", b"{}",
                 {"Content-Type": "application/json"})
    r = conn.getresponse()
    assert r.status == 401
    conn.close()


# ================= 包管理（映射 STICKER_* 帧） =================

def test_pack_rename_via_web(hub):
    h, port, wport, _ = hub
    w = _Web(wport, "改名君")
    _seed_custom(h, "w1", "旧包")
    st, d = w.pack(op="rename", pack="旧包", new="新包")
    assert st == 200 and d["ok"]
    assert h.custom_stickers["w1"]["pack"] == "新包"


def test_pack_del_via_web(hub):
    h, port, wport, _ = hub
    w = _Web(wport, "删包君")
    _seed_custom(h, "w1", "待删包")
    st, d = w.pack(op="del", pack="待删包")
    assert st == 200 and d["ok"]
    assert "w1" not in h.custom_stickers
    # 缺包名 → 400
    st, d = w.pack(op="del")
    assert st == 400 and not d["ok"]


def test_pack_cover_set_get_clear_via_web(hub):
    h, port, wport, _ = hub
    w = _Web(wport, "封面君")
    _seed_custom(h, "w1", "封面网包")
    b64 = base64.b64encode(PNG_1PX).decode()
    st, d = w.pack(op="cover_set", pack="封面网包",
                   img={"ext": "png", "data": b64})
    assert st == 200 and d["ok"]
    assert h.pack_meta["封面网包"]["cover"] == "png"
    # 封面直出（包名 URL 编码，中文包名不可裸拼）
    q = urllib.parse.urlencode({"token": w.token, "pack": "封面网包"})
    st, raw = w._raw_get(f"/api/packcover?{q}")
    assert st == 200 and raw == PNG_1PX
    # 清除 → 404
    st, d = w.pack(op="cover_del", pack="封面网包")
    assert st == 200 and d["ok"]
    assert "封面网包" not in h.pack_meta
    st, _ = w._raw_get(f"/api/packcover?{q}")
    assert st == 404


def test_pack_cover_set_rejects_bad_ext_and_empty(hub):
    h, port, wport, _ = hub
    w = _Web(wport, "封面君")
    _seed_custom(h, "w1", "封面网包")
    b64 = base64.b64encode(PNG_1PX).decode()
    st, d = w.pack(op="cover_set", pack="封面网包",
                   img={"ext": "exe", "data": b64})
    assert st == 400 and not d["ok"]
    st, d = w.pack(op="cover_set", pack="封面网包",
                   img={"ext": "png", "data": ""})
    assert st == 400 and not d["ok"]
    assert "封面网包" not in h.pack_meta


def test_pack_reorder_via_web(hub):
    h, port, wport, _ = hub
    w = _Web(wport, "排序君")
    _seed_custom(h, "a1", "排序包")
    _seed_custom(h, "a2", "排序包")
    _seed_custom(h, "a3", "排序包")
    # a2 置顶
    st, d = w.pack(op="reorder", code="a2", dir="top")
    assert st == 200 and d["ok"]
    order = {c: h.custom_stickers[c]["order"] for c in ("a1", "a2", "a3")}
    assert order["a2"] == 0 and order["a1"] == 1 and order["a3"] == 2


def test_pack_unknown_op_and_requires_login(hub):
    h, port, wport, _ = hub
    w = _Web(wport, "操作君")
    st, d = w.pack(op="bogus")
    assert st == 400 and not d["ok"]
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn.request("POST", "/api/pack", b"{}",
                 {"Content-Type": "application/json"})
    r = conn.getresponse()
    assert r.status == 401
    conn.close()


def test_packcover_requires_login(hub):
    h, port, wport, _ = hub
    w = _Web(wport, "临时")
    # 有 token（无封面）→ 404
    st, _ = w._raw_get("/api/packcover?token=" + w.token + "&pack=x")
    assert st == 404
    # 无 token → 401
    conn = http.client.HTTPConnection("127.0.0.1", wport, timeout=5)
    conn.request("GET", "/api/packcover?pack=x")
    r = conn.getresponse()
    assert r.status == 401
    conn.close()


# ================= 前端已铺标记 =================

def test_frontend_pack_ui_shipped():
    from web import _SERVED_PAGE
    html = _SERVED_PAGE().decode("utf-8")
    assert "STICKER_TRIAL_MAX" in html                  # 试看条数常量
    assert 'id="epacks"' in html or "epacks" in html    # 包导航条
    assert "/api/packcover" in html                     # 封面缩略图端点
    assert "/api/shop" in html and "/api/pack" in html  # 商店 / 包管理端点
    assert "sticker_shop_list" in html and "sticker_sub" in html  # 回帧分支
    assert "customPackGroups" in html                   # 自定义包分组
    assert "renderShop" in html and "packMenu" in html  # 商店视图 / 右键包管理
    assert "reorderSticker" in html                     # 包内排序