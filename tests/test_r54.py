# -*- coding: utf-8 -*-
"""R54 回归：群「公开/私有」可见性 + 管理员 L57 全量可见（参考 Telegram）。

- 群默认私有：未加入者列表不可见、GROUP_JOIN 被拒、只能凭邀请码加入；
- 公开群：所有人列表可见、可直接加入；但消息/历史仍只发给成员（未加入收不到）；
- 管理员 L57：所有群（含私有）列表+消息+历史全部可见，无需加入；
- 群列表项带 public 标记；GROUP_CREATE 帧带 public 字段；
- 网页端 /api/login /api/group /api/group_detail 均按查看者过滤；
- 快照持久化 public 字段，旧快照（无 public）restore 兼容。
"""
import json
import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from protocol import MsgType
from server import Hub, serve as serve_tcp
from web import serve as serve_web


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
    yield h, wport, stop
    stop.set()
    time.sleep(0.2)


class _Sess:
    """伪造 TCP 会话：走真实 hello 登录（校验管理员密码并置 is_admin）。"""
    __test__ = False

    def __init__(self, hub: Hub, nick: str, pwd: str = ""):
        self.hub = hub
        self.frames = []
        self.uid = 0
        self.nick = nick
        self.type = "tcp"
        self.peer_ip = "127.0.0.1"
        self.closed = False
        self.last_seen = time.time()
        self.is_admin = False
        self.close_conn = lambda: None
        self.send = lambda payload: self.frames.append(payload)
        hub._on_hello(self, {"t": MsgType.HELLO.value, "nick": nick,
                             "pwd": pwd})
        self.welcome = self.last_frame("welcome")

    def touch(self):
        self.last_seen = time.time()

    def last_frame(self, t: str) -> dict | None:
        for f in reversed(self.frames):
            if f.get("t") == t:
                return f
        return None

    def errors(self) -> list:
        return [f for f in self.frames if f.get("t") == "error"]

    def seen_gids(self) -> set:
        """该会话当前可见的群 gid 集合（最新 group_list 帧，welcome 兜底）。"""
        w = self.welcome or {}
        gl = self.last_frame("group_list")
        groups = gl.get("groups") if gl else (w.get("groups") or [])
        return {g["gid"] for g in groups}


class _Web:
    """轻量 web 客户端：登录拿 token；POST/GET 封装。"""
    __test__ = False

    def __init__(self, port, nick, pwd=""):
        self.port = port
        self.token = None
        self.uid = None
        self.last_login = None
        self.login(nick, pwd)

    def _req(self, method, path, body=None):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        if body is not None:
            conn.request(method, path, json.dumps(body).encode(),
                         {"Content-Type": "application/json"})
        else:
            conn.request(method, path)
        r = conn.getresponse()
        data = json.loads(r.read().decode() or "{}")
        conn.close()
        return r.status, data

    def login(self, nick, pwd=""):
        st, d = self._req("POST", "/api/login",
                          {"nick": nick, "password": pwd})
        if st != 200 or not d.get("ok"):
            self.last_login = d
            return
        self.token = d["token"]
        self.uid = d["uid"]
        self.last_login = d

    def group(self, body):
        body = dict(body)
        body["token"] = self.token
        return self._req("POST", "/api/group", body)

    def group_detail(self, gid):
        return self._req("GET", f"/api/group_detail?gid={gid}&token={self.token}")

    def send(self, channel="public", to=None, text="hi"):
        body = {"token": self.token, "channel": channel, "text": text}
        if to is not None:
            body["to"] = to
        return self._req("POST", "/api/send", body)


def _gid_by_name(h, name: str) -> int:
    for g in h.groups.values():
        if g["name"] == name:
            return g["gid"]
    raise AssertionError(f"群不存在: {name}")


# ================= 私有群：不可见 / 不可直接加入 / 邀请码可入 =================

def test_private_group_invisible_and_join_rejected(hub):
    """私有群（默认）：非成员列表不可见、GROUP_JOIN 被拒。"""
    h, _w, _ = hub
    a = _Sess(h, "甲")
    b = _Sess(h, "乙")
    h.dispatch(a, {"t": MsgType.GROUP_CREATE.value, "name": "内部群"})
    gid = _gid_by_name(h, "内部群")
    assert not g.get("public") if (g := h.groups.get(gid)) else False
    # 非成员列表不可见
    assert gid not in b.seen_gids()
    assert gid not in {g2["gid"] for g2 in h._group_list(b.uid)}
    # 创建者（成员）列表可见
    assert gid in a.seen_gids()
    # 直接加入 → 拒绝
    h.dispatch(b, {"t": MsgType.GROUP_JOIN.value, "gid": gid})
    assert any(f.get("code") == "private" for f in b.errors())
    assert b.uid not in h.groups[gid]["members"]


def test_private_group_join_by_invite(hub):
    """私有群凭邀请码可加入，加入后列表可见。"""
    h, _w, _ = hub
    a = _Sess(h, "甲")
    b = _Sess(h, "乙")
    h.dispatch(a, {"t": MsgType.GROUP_CREATE.value, "name": "密群"})
    gid = _gid_by_name(h, "密群")
    h.dispatch(a, {"t": MsgType.GROUP_INVITE_GET.value, "gid": gid})
    code = a.last_frame(MsgType.GROUP_INVITE.value)["code"]
    h.dispatch(b, {"t": MsgType.GROUP_JOIN_INVITE.value, "code": code})
    assert b.uid in h.groups[gid]["members"]
    assert gid in {g2["gid"] for g2 in h._group_list(b.uid)}


def test_public_group_visible_and_joinable(hub):
    """公开群：所有人列表可见、可直接加入。"""
    h, _w, _ = hub
    a = _Sess(h, "甲")
    b = _Sess(h, "乙")
    h.dispatch(a, {"t": MsgType.GROUP_CREATE.value, "name": "公告群",
                   "public": 1})
    gid = _gid_by_name(h, "公告群")
    assert h.groups[gid]["public"] == 1
    # 非成员可见
    assert gid in b.seen_gids()
    assert gid in {g2["gid"] for g2 in h._group_list(b.uid)}
    # 可直接加入
    h.dispatch(b, {"t": MsgType.GROUP_JOIN.value, "gid": gid})
    assert b.uid in h.groups[gid]["members"]
    assert not any(f.get("code") == "private" for f in b.errors())


# ================= 群消息/历史：仅成员可见 =================

def test_non_member_no_group_messages_no_history(hub):
    """非成员收不到群消息（公开群同样）也拉不到群历史。"""
    h, _w, _ = hub
    a = _Sess(h, "甲")
    b = _Sess(h, "乙")
    h.dispatch(a, {"t": MsgType.GROUP_CREATE.value, "name": "私密小群"})
    gid = _gid_by_name(h, "私密小群")
    h.dispatch(a, {"t": MsgType.CHAT.value, "channel": "group",
                   "to": gid, "text": "内部消息"})
    assert b.last_frame("chat") is None            # 非成员未收到
    assert a.last_frame("chat") is not None        # 成员收到
    # 非成员拉历史 → deny
    h.dispatch(b, {"t": MsgType.HISTORY.value, "channel": "group", "to": gid})
    assert any(f.get("code") == "deny" for f in b.errors())
    # 公开群同样：未加入者收不到消息
    h.dispatch(a, {"t": MsgType.GROUP_CREATE.value, "name": "公开广场",
                   "public": 1})
    gid2 = _gid_by_name(h, "公开广场")
    h.dispatch(a, {"t": MsgType.CHAT.value, "channel": "group",
                   "to": gid2, "text": "公屏"})
    assert b.last_frame("chat") is None            # 未加入公开群也收不到
    assert a.last_frame("chat")["to"] == gid2


def test_admin_sees_all_private_groups(hub):
    """管理员 L57：私有群列表可见、可收群消息、可拉群历史，无需加入。"""
    h, _w, _ = hub
    a = _Sess(h, "甲")
    adm = _Sess(h, "L57", pwd="L57")
    assert adm.is_admin
    h.dispatch(a, {"t": MsgType.GROUP_CREATE.value, "name": "绝密群"})
    gid = _gid_by_name(h, "绝密群")
    # 管理员列表可见（无需加入）
    assert gid in adm.seen_gids()
    assert gid in {g2["gid"] for g2 in h._group_list(adm.uid)}
    # 管理员可收该群消息（非成员）
    h.dispatch(a, {"t": MsgType.CHAT.value, "channel": "group",
                   "to": gid, "text": "绝密内容"})
    chat = adm.last_frame("chat")
    assert chat is not None and chat.get("to") == gid
    # 管理员可拉该群历史
    h.dispatch(adm, {"t": MsgType.HISTORY.value, "channel": "group",
                     "to": gid})
    hist = adm.last_frame("history")
    assert hist is not None and hist.get("msgs")


# ================= 网页端 =================

def test_web_groups_filtered_and_detail(hub):
    h, wport, _ = hub
    a = _Sess(h, "甲")
    h.dispatch(a, {"t": MsgType.GROUP_CREATE.value, "name": "私密W"})
    priv = _gid_by_name(h, "私密W")
    h.dispatch(a, {"t": MsgType.GROUP_CREATE.value, "name": "公开W",
                   "public": 1})
    pub = _gid_by_name(h, "公开W")
    u = _Web(wport, "普通")
    seen = {g["gid"] for g in (u.last_login.get("groups") or [])}
    assert pub in seen and priv not in seen          # 登录 groups 已过滤
    # 私有群 detail → 404（视为不存在）；公开群 detail → 200 可加入
    st, d = u.group_detail(priv)
    assert st == 404
    st, d = u.group_detail(pub)
    assert st == 200 and d.get("member") is False
    # 管理员 web 登录：私有群也可见
    adm = _Web(wport, "L57", pwd="L57")
    assert adm.last_login.get("is_admin") is True
    assert priv in {g["gid"] for g in (adm.last_login.get("groups") or [])}


def test_web_create_public_group(hub):
    """网页端建公开群：public 透传，其他用户列表可见。"""
    h, wport, _ = hub
    a = _Web(wport, "甲")
    st, d = a.group({"action": "create", "name": "网页公开",
                     "public": 1})
    assert st == 200 and d.get("ok")
    gid = _gid_by_name(h, "网页公开")
    assert h.groups[gid]["public"] == 1
    b = _Web(wport, "乙")
    assert gid in {g["gid"] for g in (b.last_login.get("groups") or [])}
    # 不带 public → 默认私有
    st, d = a.group({"action": "create", "name": "网页私密"})
    gid2 = _gid_by_name(h, "网页私密")
    assert h.groups[gid2]["public"] == 0


# ================= 快照持久化 =================

def test_snapshot_persist_public(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"))
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    a = _Sess(h, "甲")
    h.dispatch(a, {"t": MsgType.GROUP_CREATE.value, "name": "存档群",
                   "public": 1})
    h.dispatch(a, {"t": MsgType.GROUP_CREATE.value, "name": "存档密群"})
    state = h._snapshot_state()
    groups = state["groups"]
    pub = _gid_by_name(h, "存档群")
    priv = _gid_by_name(h, "存档密群")
    assert groups[str(pub)]["public"] == 1
    assert groups[str(priv)]["public"] == 0
    # 旧快照（无 public 字段）restore 不崩且缺省为私有
    old = {"groups": {str(pub): {"gid": pub, "name": "旧群",
                                 "owner": a.uid, "members": {a.uid: "甲"},
                                 "admins": [], "mutes": {}, "announce": "",
                                 "invite": "", "kind": ""}}}
    h2 = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit2"))
    h2._restore(old)
    assert h2.groups[pub].get("public", 0) == 0
    assert h2.groups[pub]["name"] == "旧群"
