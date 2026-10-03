# -*- coding: utf-8 -*-
"""CC-02A RESTORE：真实 JSON 往返后继续执行群/已读权限操作。"""

import copy
import time
from dataclasses import replace

import pytest

from config import CFG
from server import Hub, Session


class _Capture:
    __test__ = False

    def __init__(self):
        self.frames = []

    def send(self, payload, body=b""):
        self.frames.append((copy.deepcopy(payload), bytes(body or b"")))


@pytest.fixture()
def hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"), admin_pwd="")
    h = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))
    yield h
    h.audit.close()


def _attach(hub, nick):
    out = _Capture()
    sess = Session(0, nick, "tcp", "127.0.0.1", out.send)
    assert hub._attach(sess)
    return sess, out


def _group(gid, owner, members, admin, muted):
    return {
        "gid": gid,
        "name": "restore-group",
        "owner": owner,
        "admins": [admin],
        "members": {uid: nick for uid, nick in members.items()},
        "mutes": {muted: time.time() + 600},
        "announce": "",
        "announce_mode": 0,
        "invite": "",
        "kind": "",
        "public": 1,
        "slow": 0,
    }


def test_real_json_restore_keeps_group_roles_mutes_and_read_monotonicity(
        tmp_path):
    store_dir = tmp_path / "store"
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit1"),
                  web_files_dir=str(tmp_path / "web1"), admin_pwd="")
    h1 = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit1"),
             store_dir=str(store_dir))
    try:
        owner, _owner_out = _attach(h1, "restore-owner")
        member, _member_out = _attach(h1, "restore-member")
        admin, _admin_out = _attach(h1, "restore-admin")
        gid = 7
        h1.groups[gid] = _group(
            gid, owner.uid,
            {owner.uid: owner.nick, member.uid: member.nick,
             admin.uid: admin.nick},
            admin.uid, member.uid)
        h1.reads[f"group:{gid}"] = {member.uid: 5}
        h1.reads["public"] = {admin.uid: 2}
        h1._persist_flush()
    finally:
        h1.audit.close()

    cfg2 = replace(CFG, audit_dir=str(tmp_path / "audit2"),
                   web_files_dir=str(tmp_path / "web2"), admin_pwd="")
    h2 = Hub(cfg=cfg2, audit_dir=str(tmp_path / "audit2"),
             store_dir=str(store_dir))
    try:
        group = h2.groups[gid]
        assert group["owner"] == owner.uid
        assert group["admins"] == {admin.uid}
        assert set(group["members"]) == {owner.uid, member.uid, admin.uid}
        assert set(group["mutes"]) == {member.uid}
        assert h2.reads[f"group:{gid}"] == {member.uid: 5}
        assert h2.reads["public"] == {admin.uid: 2}

        owner2, _ = _attach(h2, "restore-owner")
        member2, member2_out = _attach(h2, "restore-member")
        admin2, _ = _attach(h2, "restore-admin")
        member2_out.frames.clear()

        # 重启后成员仍被禁言；字符串键未被当作“无禁言”而放行。
        h2.dispatch(member2, {"t": "chat", "channel": "group",
                              "to": gid, "text": "should-be-muted"})
        assert any(frame.get("code") == "muted"
                   for frame, _body in member2_out.frames)
        assert not any(frame.get("text") == "should-be-muted"
                       for frame, _body in member2_out.frames)

        # 管理员/群主关系恢复后仍可解除禁言。
        h2.dispatch(admin2, {"t": "group_mute", "gid": gid,
                              "target": member2.uid, "duration": 0})
        assert member2.uid not in h2.groups[gid]["mutes"]

        # 已读不能因恢复键类型变化而回退/重复写入；更大游标可继续前进。
        h2._on_read(member2, {"channel": "group", "to": gid, "seq": 3})
        assert h2.reads[f"group:{gid}"] == {member2.uid: 5}
        h2._on_read(member2, {"channel": "group", "to": gid, "seq": 7})
        assert h2.reads[f"group:{gid}"] == {member2.uid: 7}
        assert owner2.uid == owner.uid
    finally:
        h2.audit.close()


def test_restore_rejects_invalid_groups_and_reads_without_widening_permissions(
        hub):
    valid = _group(3, 30, {30: "owner", 31: "member"}, 31, 31)
    state = {
        "groups": {
            # "1"/"01" 归一化到同一个 GID，两个版本都拒绝。
            "1": _group(1, 10, {10: "one"}, 10, 10),
            "01": _group(1, 10, {10: "one"}, 10, 10),
            # bool 不能作为 owner；整个群拒绝，避免形成宽松授权状态。
            "2": dict(_group(2, 20, {20: "two"}, 20, 20), owner=True),
            "3": valid,
        },
        "reads": {
            # 同一会话的 UID 键归一化冲突，整份会话 reads 拒绝。
            "group:1": {"1": 5, "01": 9},
            # bool 不是合法已读游标；整份 public reads 拒绝。
            "public": {"2": True, "3": 4},
            # 独立资源 key 原样保留，合法 UID 键规范化。
            "group:01": {"30": 8},
            "private:30:31": {"30": 2},
        },
    }

    hub._restore(state)

    assert 1 not in hub.groups
    assert 2 not in hub.groups
    assert hub.groups[3]["owner"] == 30
    assert hub.groups[3]["admins"] == {31}
    assert set(hub.groups[3]["members"]) == {30, 31}
    assert set(hub.groups[3]["mutes"]) == {31}
    assert "group:1" not in hub.reads
    assert "public" not in hub.reads
    assert hub.reads["group:01"] == {30: 8}
    assert hub.reads["private:30:31"] == {30: 2}


@pytest.mark.parametrize("case", [
    "admin_non_member",
    "mute_non_member",
    "members_invalid",
    "mutes_invalid",
    "members_uid_conflict",
    "mutes_uid_conflict",
])
def test_bad_group_is_rejected_while_independent_group_survives(hub, case):
    """覆盖异常群形状/角色，确认坏群不会拖宽权限或吞掉正常群。"""
    bad = _group(8, 80, {80: "坏群主", 81: "坏成员"}, 81, 81)
    if case == "admin_non_member":
        bad["admins"] = [999]
    elif case == "mute_non_member":
        bad["mutes"] = {999: time.time() + 600}
    elif case == "members_invalid":
        bad["members"] = ["not-an-object"]
    elif case == "mutes_invalid":
        bad["mutes"] = ["not-an-object"]
    elif case == "members_uid_conflict":
        bad["members"] = {"80": "坏群主", "080": "重复键", "81": "坏成员"}
    elif case == "mutes_uid_conflict":
        bad["mutes"] = {"81": 10, "081": 20}
    else:  # pragma: no cover - guarded by pytest parameters
        raise AssertionError(case)

    good = _group(9, 90, {90: "好群主", 91: "好成员"}, 91, 91)
    hub._restore({"groups": {"8": bad, "9": good}})

    assert 8 not in hub.groups
    assert hub.groups[9]["owner"] == 90
    assert hub.groups[9]["admins"] == {91}
    assert set(hub.groups[9]["members"]) == {90, 91}
    assert set(hub.groups[9]["mutes"]) == {91}
