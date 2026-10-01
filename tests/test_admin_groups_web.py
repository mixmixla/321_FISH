# -*- coding: utf-8 -*-
"""网页端系统管理员群管理回归（R56）：/api/admin op=groups / group_add / remove / dissolve。
复用 test_r53 的 hub（同时起 TCP+Web）与 _Web 登录会话。
"""
import time

from test_admin_groups import make_group
from test_r53 import _Web, _admin_web, admin_password, hub  # noqa: F401 共享 Hub/口令 fixture


def test_web_groups_directory(hub):
    """超管登录 → 拉群目录含成员花名册。"""
    _h, port, _s = hub
    make_group(_h, 21, "网页群", owner=5, nick="甲", members={5: "甲", 6: "乙"})
    w = _admin_web(_h, port)
    st, d = w.admin({"op": "groups"})
    assert st == 200 and d.get("ok")
    gmap = {g["gid"]: g for g in d["groups"]}
    assert gmap[21]["member_count"] == 2
    assert {m["uid"] for m in gmap[21]["members"]} == {5, 6}


def test_web_group_add_and_remove(hub):
    """超管经网页端加成员 + 移除成员。"""
    _h, port, _s = hub
    make_group(_h, 22, "增删群", owner=5, nick="甲", members={5: "甲"})
    w = _admin_web(_h, port)
    st, d = w.admin({"op": "group_add", "gid": 22, "uid": 9})
    assert st == 200 and d.get("ok")
    assert 9 in _h.groups[22]["members"]
    st, d = w.admin({"op": "group_remove", "gid": 22, "uid": 9})
    assert st == 200 and d.get("ok")
    assert 9 not in _h.groups[22]["members"]


def test_web_group_dissolve(hub):
    """超管经网页端解散群。"""
    _h, port, _s = hub
    make_group(_h, 23, "解散群", owner=5, nick="甲", members={5: "甲", 6: "乙"})
    w = _admin_web(_h, port)
    st, d = w.admin({"op": "group_dissolve", "gid": 23})
    assert st == 200 and d.get("ok")
    assert 23 not in _h.groups


def test_web_admin_groups_requires_admin(hub):
    """普通成员调群管理接口 → 403。"""
    _h, port, _s = hub
    w = _Web(port, "路人" + str(int(time.time() % 10000)))
    st, d = w.admin({"op": "groups"})
    assert st == 403 and "仅管理员" in (d.get("error") or "")


def test_web_group_add_nick_and_user_groups(hub):
    """网页端：按昵称加成员（可离线）+ 查某人所属群。"""
    _h, port, _s = hub
    make_group(_h, 32, "网页昵称群", owner=5, nick="甲", members={5: "甲"})
    u = _Web(port, "佐助尚")                    # 普通用户登录 → 服务器 known
    a = _admin_web(_h, port)
    st, d = a.admin({"op": "group_add_nick", "gid": 32, "uid": "佐助尚"})
    assert st == 200 and d.get("ok")
    assert u.uid in _h.groups[32]["members"]
    st, d = a.admin({"op": "user_groups", "uid": "佐助尚"})
    assert st == 200 and d.get("ok")
    assert d["nick"] == "佐助尚" and 32 in {g["gid"] for g in d["groups"]}
    # 未知昵称 → 404
    st, d = a.admin({"op": "user_groups", "uid": "无名氏X"})
    assert st == 404


def test_web_kick_by_nick_and_audit(hub):
    """网页端：按昵称踢人 + 审计日志接口。"""
    _h, port, _s = hub
    u = _Web(port, "须佐")
    a = _admin_web(_h, port)
    st, d = a.admin({"op": "kick", "uid": "须佐"})
    assert st == 200 and d.get("ok")
    assert u.uid not in _h.sessions
    st, d = a.admin({"op": "audit"})
    assert st == 200 and d.get("ok")
    kinds = {r["type"] for r in d["rows"]}
    assert "admin_kick" in kinds


def test_web_audit_requires_admin(hub):
    """普通成员拉审计 → 403。"""
    _h, port, _s = hub
    w = _Web(port, "路人甲" + str(int(time.time() % 10000)))
    st, d = w.admin({"op": "audit"})
    assert st == 403


def test_web_admin_users_full_list(hub):
    """R58：网页端管理员拉全量账号——离线账号也在列，供管理所有账户。"""
    _h, port, _s = hub
    u = _Web(port, "须佐离")
    a = _admin_web(_h, port)
    a.admin({"op": "kick", "uid": u.uid})       # 使其离线
    assert u.uid not in _h.sessions
    st, d = a.admin({"op": "users"})
    assert st == 200 and d.get("ok")
    um = {x["uid"]: x for x in d["users"]}
    assert u.uid in um and um[u.uid]["online"] is False   # 离线账号可管理
    # 普通成员调 users 接口 → 403
    w = _Web(port, "路人乙" + str(int(time.time() % 10000)))
    st2, d2 = w.admin({"op": "users"})
    assert st2 == 403
