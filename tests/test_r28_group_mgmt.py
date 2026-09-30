# -*- coding: utf-8 -*-
"""R28 群管理补全回归：邀请码（取/复用/凭码入群/已在群/满员/权限/坏码）、
群改名（同步/空名/超长截断/重名/无权限）、成员上限字段、持久化，
以及网页端 /api/group 三个新 action（invite / join_invite / rename）。

夹具仿 test_r27.py（hub 起 TCP + Web）与 test_r26.py（Collector + _spawn）。
"""
import glob
import json
import os
import socket
import threading
import time
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, serve as serve_tcp
from web import serve as serve_web
from client_core import ClientCore


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
    httpd = serve_web(h, port=wport)
    time.sleep(0.2)
    yield h, port, wport, stop
    stop.set()
    time.sleep(0.2)


class Collector:
    """on_event 收集器：wait 匹配即移除（与 TestClient.wait 同语义）。"""
    __test__ = False

    def __init__(self, core: ClientCore) -> None:
        self.events = []
        self._lock = threading.Lock()
        core._on_event = self._on

    def _on(self, ev: dict) -> None:
        with self._lock:
            self.events.append(ev)

    def wait(self, t: str, timeout: float = 3.0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for i, e in enumerate(self.events):
                    if e.get("t") == t and (pred is None or pred(e)):
                        del self.events[i]
                        return e
            time.sleep(0.01)
        return None

    def has(self, t: str, pred=None) -> bool:
        with self._lock:
            return any(e.get("t") == t and (pred is None or pred(e))
                       for e in self.events)


def _make_core(port: int, nick: str, tmp_path, **kw):
    kw.setdefault("heartbeat_interval", 0.1)
    kw.setdefault("heartbeat_timeout", 0.8)
    kw.setdefault("reconnect_base", 0.05)
    kw.setdefault("reconnect_max", 0.3)
    hist_dir = kw.pop("history_dir", str(tmp_path / f"hist_{nick}"))
    return ClientCore(host="127.0.0.1", port=port, nick=nick,
                      history_dir=hist_dir, **kw)


def _spawn(port: int, nick: str, tmp_path):
    core = _make_core(port, nick, tmp_path)
    col = Collector(core)
    core.start()
    w = col.wait("welcome", timeout=8.0)
    assert w is not None, f"{nick} 未收到 welcome"
    return core, col


def _online(col, timeout: float = 3.0):
    return col.wait("state", timeout=timeout,
                    pred=lambda e: e.get("state") == "online")


def _err(col, code: str, timeout: float = 3.0):
    return col.wait("error", timeout=timeout, pred=lambda e: e.get("code") == code)


def _mk_group(a, ac, name="摸鱼群") -> int:
    """owner 建群并等回 group_state，返回 gid。
    R54：默认建公开群——私有群不可直接加入，群管理回归的关注点是权限/邀请码，
    统一建公开群以保留「bob 直接 join」的既有测试语义。"""
    assert a.create_group(name, public=True)
    gs = ac.wait("group_state", pred=lambda e: e.get("name") == name)
    assert gs is not None, "未收到建群 group_state"
    return gs["gid"]


def _join(a, ac, gid, nick="bob") -> None:
    """bob 加入群并等 owner/自身两端 group_state 同步。"""
    b, bc = a, ac
    assert b.join_group(gid)
    assert bc.wait("group_state", pred=lambda e: e.get("gid") == gid
                   and "加入" in (e.get("text") or ""))


class _Web:
    """轻量 web HTTP 客户端：登录拿 token + 通用 POST/GET。"""
    __test__ = False

    def __init__(self, port, nick):
        self.port = port
        self.token = None
        self.uid = None
        self.login(nick)

    def _post(self, path, body):
        import http.client
        import json
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", path, json.dumps(body).encode(),
                     {"Content-Type": "application/json"})
        r = conn.getresponse()
        data = json.loads(r.read().decode() or "{}")
        conn.close()
        return r.status, data

    def _get(self, path):
        import http.client
        import json
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        r = conn.getresponse()
        data = json.loads(r.read().decode() or "{}")
        conn.close()
        return r.status, data

    def login(self, nick):
        st, d = self._post("/api/login", {"nick": nick})
        assert st == 200 and d["ok"], d
        self.token = d["token"]
        self.uid = d["uid"]

    def group(self, action, data=None):
        return self._post("/api/group", dict({"token": self.token,
                                              "action": action}, **(data or {})))

    def group_detail(self, gid):
        st, d = self._get(f"/api/group_detail?token={self.token}&gid={gid}")
        assert st == 200 and d["ok"], d
        return d


# ---------- 邀请码：取 / 复用 ----------
def test_invite_get_and_reuse(hub, tmp_path):
    """owner 取码：8 位大写十六进制；再取不变（复用）；单播不广播。"""
    _, port, _, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        gid = _mk_group(a, ac)
        assert a.get_group_invite(gid)
        ev = ac.wait("group_invite", pred=lambda e: e.get("gid") == gid)
        assert ev and len(ev["code"]) == 8
        assert ev["code"] == ev["code"].upper()
        assert all(c in "0123456789ABCDEF" for c in ev["code"])
        code = ev["code"]
        # 再取复用同一码
        assert a.get_group_invite(gid)
        ev2 = ac.wait("group_invite", pred=lambda e: e.get("gid") == gid)
        assert ev2["code"] == code
        # bob 不是成员收不到单播
        assert not bc.has("group_invite")
    finally:
        a.stop(); b.stop()


# ---------- 邀请码：凭码入群 ----------
def test_invite_join_success(hub, tmp_path):
    """他人凭码入群：双端 group_state 广播 + group_list 成员数更新。"""
    _, port, _, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        gid = _mk_group(a, ac)
        assert a.get_group_invite(gid)
        code = ac.wait("group_invite", pred=lambda e: e.get("gid") == gid)["code"]
        assert b.join_group_by_invite(code)
        gs = bc.wait("group_state", pred=lambda e: e.get("gid") == gid
                     and "凭邀请码加入" in (e.get("text") or ""))
        assert gs is not None
        ac.wait("group_state", pred=lambda e: e.get("gid") == gid
                and b.uid in [m["uid"] for m in e.get("members", [])])
        # owner 端 group_list 成员数同步（client_core 由 group_list 事件刷新 self.groups）
        ac.wait("group_list", pred=lambda e: any(
            g["gid"] == gid and g["member_count"] >= 2 for g in e["groups"]))
        assert a.groups[gid]["member_count"] >= 2
        assert gid in b._joined_groups
    finally:
        a.stop(); b.stop()


def test_invite_join_already_in(hub, tmp_path):
    """已在群再凭码 → error code=group。"""
    _, port, _, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        gid = _mk_group(a, ac)
        assert a.get_group_invite(gid)
        code = ac.wait("group_invite", pred=lambda e: e.get("gid") == gid)["code"]
        assert b.join_group_by_invite(code)
        bc.wait("group_state", pred=lambda e: e.get("gid") == gid
                and "凭邀请码加入" in (e.get("text") or ""))
        assert b.join_group_by_invite(code)
        assert _err(bc, "group") is not None
    finally:
        a.stop(); b.stop()


def test_invite_join_full(hub, tmp_path):
    """塞满 64 人后再凭码 → error code=full 且文案含 64/64。"""
    h, port, _, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        gid = _mk_group(a, ac)
        assert a.get_group_invite(gid)
        code = ac.wait("group_invite", pred=lambda e: e.get("gid") == gid)["code"]
        # 直接塞满服务器内存态（owner 1 + 63 填充 = 64）
        fill = h.cfg.group_max_members - 1
        with h.lock:
            h.groups[gid]["members"].update({uid: f"f{uid}"
                                             for uid in range(100, 100 + fill)})
        assert b.join_group_by_invite(code)
        err = _err(bc, "full")
        assert err is not None and "64/64" in (err.get("text") or "")
    finally:
        a.stop(); b.stop()


def test_invite_perm(hub, tmp_path):
    """普通成员取码 → error perm；升 admin 后可取。"""
    _, port, _, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        gid = _mk_group(a, ac)
        assert b.join_group(gid)
        bc.wait("group_state", pred=lambda e: e.get("gid") == gid
                and "加入" in (e.get("text") or ""))
        # 普通成员无权
        assert b.get_group_invite(gid)
        assert _err(bc, "perm") is not None
        # owner 升 bob 为管理员
        assert a.set_admin(gid, b.uid, True)
        ac.wait("group_state", pred=lambda e: e.get("gid") == gid
                and b.uid in e.get("admins", []))
        # admin 可取码
        assert b.get_group_invite(gid)
        ev = bc.wait("group_invite", pred=lambda e: e.get("gid") == gid)
        assert ev and len(ev["code"]) == 8
    finally:
        a.stop(); b.stop()


def test_invite_join_bad_code(hub, tmp_path):
    """坏码 / 空码 → error code=invite。"""
    _, port, _, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        _mk_group(a, ac)
        assert b.join_group_by_invite("BADCODE00")
        assert _err(bc, "invite") is not None
        assert b.join_group_by_invite("")
        assert _err(bc, "invite") is not None
    finally:
        a.stop(); b.stop()


# ---------- 群改名 ----------
def test_rename_ok(hub, tmp_path):
    """owner 改名：双端 group_state.name + group_list + 网页 group_detail 同步。"""
    h, port, wport, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        gid = _mk_group(a, ac, "旧名字")
        assert b.join_group(gid)
        bc.wait("group_state", pred=lambda e: e.get("gid") == gid
                and "加入" in (e.get("text") or ""))
        assert a.rename_group(gid, "开黑一队")
        gs = ac.wait("group_state", pred=lambda e: e.get("gid") == gid
                     and e.get("name") == "开黑一队")
        assert gs is not None
        bc.wait("group_state", pred=lambda e: e.get("gid") == gid
                and e.get("name") == "开黑一队")
        assert a.groups[gid]["name"] == "开黑一队"
        ac.wait("group_list", pred=lambda e: any(
            g["gid"] == gid and g["name"] == "开黑一队" for g in e["groups"]))
        # 网页 group_detail 同步（webby 非成员也能看名）
        w = _Web(wport, "webby")
        d = w.group_detail(gid)
        assert d["name"] == "开黑一队" and d["member_max"] == h.cfg.group_max_members
    finally:
        a.stop(); b.stop()


def test_rename_validation_and_perm(hub, tmp_path):
    """改名校验：空名 error name；超长截断 16；重名 error dup；普通成员 error perm。"""
    _, port, _, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    c, cc = _spawn(port, "charlie", tmp_path)
    try:
        assert _online(ac) and _online(bc) and _online(cc)
        gid = _mk_group(a, ac, "开黑群")
        assert b.join_group(gid)
        bc.wait("group_state", pred=lambda e: e.get("gid") == gid
                and "加入" in (e.get("text") or ""))
        # 空名
        assert a.rename_group(gid, "   ")
        assert _err(ac, "name") is not None
        # 超长 → 截断到 GROUP_NAME_MAX(16)
        assert a.rename_group(gid, "长群名" * 30)
        gs = ac.wait("group_state", pred=lambda e: e.get("gid") == gid
                     and "改名" in (e.get("text") or ""))
        assert gs is not None and gs["name"] == "长群名" * 5 + "长"  # [:16] 截断
        # 重名（charlie 建同名牌，排除自身）
        gid2 = _mk_group(c, cc, "新群")
        assert a.rename_group(gid, "新群")
        assert _err(ac, "dup") is not None
        # 普通成员无权
        assert b.rename_group(gid, "我改名")
        assert _err(bc, "perm") is not None
        assert gid2 != gid
    finally:
        a.stop(); b.stop(); c.stop()


# ---------- 成员上限字段 ----------
def test_member_max_field(hub, tmp_path):
    """_group_list() / group_detail() 均带 member_max == 配置上限。"""
    h, port, _, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    try:
        assert _online(ac)
        gid = _mk_group(a, ac)
        gl = next(g for g in h._group_list() if g["gid"] == gid)
        assert gl["member_max"] == h.cfg.group_max_members
        d = h.group_detail(gid, a.uid)
        assert d["member_max"] == h.cfg.group_max_members
        assert d["member"] is True and d["my_role"] == "owner"
    finally:
        a.stop()


# ---------- 持久化 ----------
def test_invite_persist(hub, tmp_path):
    """快照含 invite；恢复后保留；旧数据缺字段 setdefault 补空不崩。"""
    h, port, _, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    try:
        assert _online(ac)
        gid = _mk_group(a, ac)
        assert a.get_group_invite(gid)
        code = ac.wait("group_invite", pred=lambda e: e.get("gid") == gid)["code"]
        state = h._snapshot_state()
        assert state["groups"][str(gid)]["invite"] == code
        h2 = Hub(cfg=h.cfg, audit_dir=str(tmp_path / "audit2"))
        h2._restore(state)
        assert h2.groups[gid]["invite"] == code
        h3 = Hub(cfg=h.cfg, audit_dir=str(tmp_path / "audit3"))
        h3._restore({"groups": {str(gid): {"gid": gid, "name": "旧", "owner": 1,
                                           "admins": [], "members": {1: "a"}}}})
        assert h3.groups[gid]["invite"] == ""
    finally:
        a.stop()


# ---------- 网页端 /api/group ----------
def test_web_group_mgmt(hub, tmp_path):
    """网页端 invite/rename/join_invite 三 action：HTTP ok + 服务端状态生效。"""
    h, port, wport, _ = hub
    wa = _Web(wport, "web-owner")
    wb = _Web(wport, "web-guest")
    st, d = wa.group("create", {"name": "网页群"})
    assert st == 200 and d["ok"] and d["groups"]
    assert all("member_max" in g for g in d["groups"])
    gid = next(g["gid"] for g in d["groups"] if g["name"] == "网页群")
    # invite：owner 取码（HTTP 同步回 ok；码落服务器 invite 字段）
    st, d = wa.group("invite", {"gid": gid})
    assert st == 200 and d["ok"]
    code = h.groups[gid]["invite"]
    assert len(code) == 8 and code == code.upper()
    # rename：owner 改名
    st, d = wa.group("rename", {"gid": gid, "name": "网页群改名"})
    assert st == 200 and d["ok"]
    assert h.groups[gid]["name"] == "网页群改名"
    # join_invite：他人凭码入群
    st, d = wb.group("join_invite", {"code": code.lower()})   # 服务端 uppercase 容错
    assert st == 200 and d["ok"]
    assert wb.uid in h.groups[gid]["members"]
    dd = wa.group_detail(gid)
    assert len(dd["members"]) >= 2 and dd["member_max"] == h.cfg.group_max_members
    # 普通 web 用户不能 rename
    st, d = wb.group("rename", {"gid": gid, "name": "抢名"})
    assert st == 200 and d["ok"]              # HTTP 恒 200，错误走 SSE error
    assert h.groups[gid]["name"] == "网页群改名"
    assert d["groups"]
    # 非成员 web 用户取码 → 拒绝
    wc = _Web(wport, "web-outsider")
    st, d = wc.group("invite", {"gid": gid})
    assert st == 200 and d["ok"] and h.groups[gid]["invite"] == code
    # 未知 action → 400
    st, d = wa.group("nonsense")
    assert st == 400 and not d["ok"]


# ---------- 审计 ----------
def test_audit_logs(hub, tmp_path):
    """三类群管理操作各留审计日志。"""
    _, port, _, _ = hub
    a, ac = _spawn(port, "alice", tmp_path)
    b, bc = _spawn(port, "bob", tmp_path)
    try:
        assert _online(ac) and _online(bc)
        gid = _mk_group(a, ac)
        assert a.get_group_invite(gid)
        code = ac.wait("group_invite", pred=lambda e: e.get("gid") == gid)["code"]
        assert b.join_group_by_invite(code)
        bc.wait("group_state", pred=lambda e: e.get("gid") == gid
                and "凭邀请码加入" in (e.get("text") or ""))
        assert a.rename_group(gid, "审计名")
        ac.wait("group_state", pred=lambda e: e.get("gid") == gid
                and e.get("name") == "审计名")
        logs = []
        for p in glob.glob(os.path.join(str(tmp_path / "audit"), "audit-*.jsonl")):
            with open(p, encoding="utf-8") as f:
                logs += [json.loads(l) for l in f if l.strip()]
        types = [e.get("type") for e in logs]
        assert "group_invite_get" in types
        assert "group_join_invite" in types
        assert "group_rename" in types
    finally:
        a.stop(); b.stop()
