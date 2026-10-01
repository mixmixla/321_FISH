# -*- coding: utf-8 -*-
"""系统管理员（L57）群管理回归：群目录 + 增删成员 + 解散群。

- 非管理员调用一律 forbid；
- admin_groups → 全量群目录（含成员花名册），不论公开/私有、是否已加入；
- admin_group_set add/remove/dissolve → 超管 override，无视群内权限；
- 移除群主自动转让给其他成员；移空/解散即删除该群并广播。
"""
import time
import secrets
import socket
import threading
from dataclasses import replace

import pytest

from config import CFG
from protocol import MsgType

from test_r53 import _Sess, _admin_session  # 复用真实 hello 登录


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def admin_password() -> str:
    """为本模块显式注入一次随机部署管理员口令。"""
    return secrets.token_urlsafe(24)


@pytest.fixture()
def hub(tmp_path, admin_password):
    from server import Hub, serve as serve_tcp
    cfg = replace(CFG, admin_nick="L57", audit_dir=str(tmp_path / "audit"),
                  admin_pwd=admin_password)
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    h._test_admin_password = admin_password
    h._test_admin_nick = cfg.admin_nick
    port = _free_port()
    stop = threading.Event()
    threading.Thread(target=serve_tcp, args=(h, port, stop, False),
                     daemon=True).start()
    time.sleep(0.2)
    yield h, port, stop
    stop.set()
    time.sleep(0.1)


def make_group(hub, gid, name, owner, nick, members=None, public=0, kind=""):
    """直接构造一组群（绕开创建流程，聚焦超管增删/解散逻辑）。"""
    mem = {owner: nick}
    for u, n in (members or {}).items():
        mem[u] = n
    hub.groups[gid] = {"gid": gid, "name": name, "owner": owner,
                       "members": mem, "admins": set(), "mutes": {},
                       "announce": "", "invite": "", "kind": kind,
                       "public": public}


def test_non_admin_forbidden(hub):
    """非管理员（普通成员）调用群管理 → forbid。"""
    h, _w, _ = hub
    u = _Sess(h, "外包" + str(int(time.time() % 10000)))
    h.dispatch(u, {"t": MsgType.ADMIN_GROUPS.value})
    assert any(f.get("code") == "forbid" for f in u.frames)


def test_admin_directory_lists_all_groups(hub):
    """超管目录含全部群 + 成员花名册（含私有群、非本群组）。"""
    h, _w, _ = hub
    make_group(h, 1, "公共频道", owner=5, nick="甲", members={5: "甲", 6: "乙"})
    make_group(h, 2, "私有小群", owner=7, nick="丙",
               members={7: "丙", 8: "丁"}, public=0)
    a = _admin_session(h)
    h.dispatch(a, {"t": MsgType.ADMIN_GROUPS.value})
    roster = a.last_frame(MsgType.ADMIN_GROUPS_ROSTER.value)
    assert roster and roster.get("groups")
    groups = {g["gid"]: g for g in roster["groups"]}
    assert set(groups) >= {1, 2}
    # 花名册含 uid+nick
    g1 = groups[1]
    assert g1["member_count"] == 2
    assert {"u": 5, "n": "甲"} == {"u": g1["members"][0]["uid"],
                                   "n": g1["members"][0]["nick"]}


def test_admin_add_member_to_private_group(hub):
    """超管将非成员加入私有群（override 私有/非成员限制）。"""
    h, _w, _ = hub
    make_group(h, 3, "私有群X", owner=7, nick="丙", members={7: "丙"})
    a = _admin_session(h); a.uid = 99; a.nick = h._test_admin_nick
    h.dispatch(a, {"t": MsgType.ADMIN_GROUP_SET.value,
                   "gid": 3, "op": "add", "uid": 8})
    assert 8 in h.groups[3]["members"]
    assert h.groups[3]["mutes"].get(8) is None


def test_admin_add_duplicate_rejected(hub):
    h, _w, _ = hub
    make_group(h, 4, "重复群", owner=7, nick="丙", members={7: "丙", 8: "丁"})
    a = _admin_session(h)
    h.dispatch(a, {"t": MsgType.ADMIN_GROUP_SET.value,
                   "gid": 4, "op": "add", "uid": 8})
    assert any(f.get("code") == "member" for f in a.frames)


def test_admin_remove_transfers_owner(hub):
    """移除群主 → 群主自动转让给其余成员。"""
    h, _w, _ = hub
    make_group(h, 5, "转让群", owner=7, nick="丙",
               members={7: "丙", 8: "丁", 9: "戊"})
    a = _admin_session(h)
    h.dispatch(a, {"t": MsgType.ADMIN_GROUP_SET.value,
                   "gid": 5, "op": "remove", "uid": 7})
    assert 8 in h.groups[5]["members"]
    assert h.groups[5]["owner"] in (8, 9)


def test_admin_remove_last_dissolves(hub):
    """移除最后一名成员 → 群自动解散。"""
    h, _w, _ = hub
    make_group(h, 6, "独雁群", owner=7, nick="丙", members={7: "丙"})
    a = _admin_session(h)
    h.dispatch(a, {"t": MsgType.ADMIN_GROUP_SET.value,
                   "gid": 6, "op": "remove", "uid": 7})
    assert 6 not in h.groups


def test_admin_dissolve_group(hub):
    """超管直接解散群 → 从目录移除 + 广播 system。"""
    h, _w, _ = hub
    make_group(h, 7, "待解散", owner=7, nick="丙",
               members={7: "丙", 8: "丁"})
    a = _admin_session(h)
    h.dispatch(a, {"t": MsgType.ADMIN_GROUP_SET.value,
                   "gid": 7, "op": "dissolve"})
    assert 7 not in h.groups
    assert any(f.get("t") == "system" and "解散" in f.get("text", "")
               for f in a.frames)


def test_admin_user_info_and_nick_add(hub):
    """超管：按昵称添加（含离线）+ 查某人所属群/在线状态。"""
    h, _w, _ = hub
    t = _Sess(h, "佐助")                       # 登录注册为已知用户
    make_group(h, 31, "乙女心", owner=5, nick="甲", members={5: "甲"})
    a = _admin_session(h)
    # 按昵称把 佐助 加入群（服务器 known 解析，不依赖 uid）
    h.dispatch(a, {"t": MsgType.ADMIN_GROUP_SET.value,
                   "gid": 31, "op": "add", "uid": "佐助"})
    assert t.uid in h.groups[31]["members"]
    # 查某人所属群（按昵称）
    h.dispatch(a, {"t": MsgType.ADMIN_USER_GET.value, "uid": "佐助"})
    info = a.last_frame(MsgType.ADMIN_USER_INFO.value)
    assert info and info["uid"] == t.uid and info["nick"] == "佐助"
    assert 31 in {g["gid"] for g in info["groups"]}
    # 非管理员查 → forbid
    t.frames.clear()
    h.dispatch(t, {"t": MsgType.ADMIN_USER_GET.value, "uid": 5})
    assert any(f.get("code") == "forbid" for f in t.frames)


def test_admin_user_info_by_uid(hub):
    """超管：按 uid 查某人信息（非法 uid → 拒绝）。"""
    h, _w, _ = hub
    t = _Sess(h, "鸣人")
    a = _admin_session(h)
    h.dispatch(a, {"t": MsgType.ADMIN_USER_GET.value, "uid": t.uid})
    info = a.last_frame(MsgType.ADMIN_USER_INFO.value)
    assert info and info["uid"] == t.uid and info["online"] is True
    # 不存在的昵称 → uid 无效
    h.dispatch(a, {"t": MsgType.ADMIN_USER_GET.value, "uid": "不存在的人X"})
    assert any(f.get("code") == "uid" for f in a.frames)


def test_admin_kick_by_nick_and_audit(hub):
    """超管按昵称踢下线 + 审计落库。"""
    h, _w, _ = hub
    t = _Sess(h, "露西")
    a = _admin_session(h)
    h.dispatch(a, {"t": MsgType.ADMIN_KICK.value, "uid": "露西"})
    assert t.uid not in h.sessions
    # 审计：踢人已记录
    ev = [e for e in h.audit.recent(100, "admin") if e.get("type") == "admin_kick"]
    assert ev and ev[-1]["target"] == t.uid
    # 普通成员踢人 → forbid
    t2 = _Sess(h, "香英")
    h.dispatch(t2, {"t": MsgType.ADMIN_KICK.value, "uid": "路人Z"})
    assert any(f.get("code") == "forbid" for f in t2.frames)


def test_admin_kick_invalid_nick(hub):
    """超管踢不存在的昵称 → 目标无效错误。"""
    h, _w, _ = hub
    a = _admin_session(h)
    h.dispatch(a, {"t": MsgType.ADMIN_KICK.value, "uid": "不存在的人Y"})
    assert any(f.get("code") == "uid" for f in a.frames)


def test_admin_group_roster_marks_invisible(hub):
    """R57：管理员群目录成员花名册携带 invisible 标记（隐身上线者）。"""
    h, _w, _ = hub
    stamp = str(int(time.time() % 100000))
    nick = "影A" + stamp
    inv = _Sess(h, nick)                      # 登录成为已知用户
    make_group(h, 41, "隐身群", owner=inv.uid, nick=nick,
               members={inv.uid: nick, 61: "正常乙"})
    h.dispatch(inv, {"t": MsgType.INV_SET.value, "on": True})   # 开启隐身
    a = _admin_session(h)
    h.dispatch(a, {"t": MsgType.ADMIN_GROUPS.value})
    roster = a.last_frame(MsgType.ADMIN_GROUPS_ROSTER.value)
    g = next(x for x in roster["groups"] if x["gid"] == 41)
    m = next(x for x in g["members"] if x["uid"] == inv.uid)
    assert m["invisible"] is True
    # 非隐身成员不带标记
    other = next(x for x in g["members"] if x["uid"] != inv.uid)
    assert other["invisible"] is False


def test_admin_user_info_marks_invisible(hub):
    """R57：管理员查某人资料时返回 invisible 隐身态。"""
    h, _w, _ = hub
    stamp = str(int(time.time() % 100000))
    u = _Sess(h, "影B" + stamp)
    h.dispatch(u, {"t": MsgType.INV_SET.value, "on": True})
    a = _admin_session(h)
    h.dispatch(a, {"t": MsgType.ADMIN_USER_GET.value, "uid": u.uid})
    info = a.last_frame(MsgType.ADMIN_USER_INFO.value)
    assert info and info["invisible"] is True
    # 恢复显身后为 False
    h.dispatch(u, {"t": MsgType.INV_SET.value, "on": False})
    h.dispatch(a, {"t": MsgType.ADMIN_USER_GET.value, "uid": u.uid})
    info2 = a.last_frame(MsgType.ADMIN_USER_INFO.value)
    assert info2["invisible"] is False


def test_admin_users_includes_offline_and_invisible(hub):
    """R58：管理员全量账号（在线/离线都有）——离线账户也在列，隐身带标记。"""
    h, _w, _ = hub
    stamp = str(int(time.time() % 100000))
    off = _Sess(h, "离线X" + stamp)            # 登录 → 进入 known
    a = _admin_session(h)
    h.dispatch(a, {"t": MsgType.ADMIN_KICK.value, "uid": off.uid})  # 使其离线
    assert off.uid not in h.sessions          # 已下线但保留 known 记录
    inv = _Sess(h, "隐身X" + stamp)
    h.dispatch(inv, {"t": MsgType.INV_SET.value, "on": True})
    users = {u["uid"]: u for u in h._admin_users()}
    assert users[off.uid]["online"] is False   # 离线账号仍可列出/管理
    assert users[off.uid]["nick"] == off.nick
    assert users[inv.uid]["online"] is True
    assert users[inv.uid]["invisible"] is True
