# -*- coding: utf-8 -*-
"""服务端安全回归：群文件归属、删号会话失效、朋友圈图片生命周期。"""
import secrets
from dataclasses import replace

from config import CFG
from protocol import MsgType
from server import Hub, Session


class _Rec:
    def __init__(self):
        self.frames = []

    def send(self, payload, body=b""):
        item = dict(payload)
        if body:
            item["_body"] = body
        self.frames.append(item)


def _hub(tmp_path):
    admin_password = secrets.token_urlsafe(24)
    cfg = replace(CFG, admin_nick="L57", audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"),
                  admin_pwd=admin_password)
    # CC-02A-RETIRE-CORE：删号/退役必须在真实隔离 Store 上验证；
    # 无 Store 的 Hub 应在 t0 前拒绝永久退役。
    hub = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"),
              store_dir=str(tmp_path / "store"))
    hub._test_admin_password = admin_password
    return hub


def _session(hub, nick, stype="tcp", pwd=""):
    rec = _Rec()
    sess = Session(0, nick, stype, "127.0.0.1", rec.send)
    if nick == hub._admin_nick:
        assert hub._on_hello(sess, {"t": MsgType.HELLO.value,
                                    "nick": nick, "pwd": pwd})
    else:
        assert hub._attach(sess)
    return sess, rec


def _group(hub, gid, members):
    hub.groups[gid] = {
        "gid": gid, "name": "安全回归群", "owner": next(iter(members)),
        "members": dict(members), "admins": set(), "mutes": {},
        "announce": "", "announce_mode": 0, "invite": "", "kind": "",
        "public": 0, "slow": 0,
    }


def test_group_file_upload_requires_owner_and_serialized_offset(tmp_path):
    hub = _hub(tmp_path)
    owner, owner_rec = _session(hub, "owner")
    member, member_rec = _session(hub, "member")
    outsider, outsider_rec = _session(hub, "outsider")
    _group(hub, 7, {owner.uid: owner.nick, member.uid: member.nick})

    hub.dispatch(owner, {"t": MsgType.GROUP_FILE_UPLOAD_START.value,
                         "gid": 7, "name": "a.txt", "size": 3})
    info = next(f for f in owner_rec.frames
                if f.get("t") == MsgType.GROUP_FILE_UPLOAD_INFO.value)
    fid = info["fid"]

    # 群成员可以看到群，但不能接管别人的上传。
    hub.dispatch(member, {"t": MsgType.GROUP_FILE_UPLOAD.value,
                          "gid": 7, "fid": fid, "off": 0}, b"x")
    assert any(f.get("t") == MsgType.ERROR.value for f in member_rec.frames)
    assert (hub._gf_uploading or {}).get(fid) == 0
    path = hub._gf_write_dir(7) + "\\" + fid
    assert not __import__("os").path.exists(path)

    # 非成员不能用 DONE 提前触发列表返回。
    hub.dispatch(outsider, {"t": MsgType.GROUP_FILE_UPLOAD_DONE.value,
                            "gid": 7, "fid": fid, "off": 0})
    assert any(f.get("t") == MsgType.ERROR.value for f in outsider_rec.frames)
    assert not any(f.get("t") == MsgType.GROUP_FILE_LIST_RES.value
                   for f in outsider_rec.frames)

    # 正常客户端流程：分块推进后再发 DONE，文件完成且列表只回给上传者。
    hub.dispatch(owner, {"t": MsgType.GROUP_FILE_UPLOAD.value,
                         "gid": 7, "fid": fid, "off": 0}, b"abc")
    hub.dispatch(owner, {"t": MsgType.GROUP_FILE_UPLOAD_DONE.value,
                         "gid": 7, "fid": fid, "off": 3})
    assert not hub._gf_uploading.get(fid)
    assert any(f.get("t") == MsgType.GROUP_FILE_LIST_RES.value
               for f in owner_rec.frames)
    assert hub.group_files[7][0]["uid"] == owner.uid


def test_admin_delete_invalidates_all_sessions_and_tokens(tmp_path):
    hub = _hub(tmp_path)
    admin, _ = _session(hub, hub._admin_nick,
                        pwd=hub._test_admin_password)
    assert admin.is_admin
    first, first_rec = _session(hub, "victim", "tcp")
    second, second_rec = _session(hub, "victim", "web")
    token = "old-web-token"
    hub.web_tokens[token] = second
    assert first.uid == second.uid

    hub.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value,
                         "uid": first.uid})

    assert first.closed and second.closed
    assert first.uid not in hub._uid_clients
    assert first.uid not in hub.sessions
    assert first.uid not in hub.known
    assert token not in hub.web_tokens
    assert any(f.get("code") == "deleted" for f in first_rec.frames)
    assert any(f.get("code") == "deleted" for f in second_rec.frames)
    # close_conn/底层读循环竞态下，旧 TCP 会话也不能继续发帧。
    assert hub.dispatch(first, {"t": MsgType.CHAT.value,
                                "channel": "public", "text": "stale"}) is False


def test_dispatch_requires_registered_session_even_when_not_closed(tmp_path):
    hub = _hub(tmp_path)
    active, rec = _session(hub, "active")
    assert hub.dispatch(active, {"t": MsgType.PING.value}) is True
    assert any(frame.get("t") == "pong" for frame in rec.frames)

    # 模拟底层连接刚注销、但 close_conn 尚未把 Session 对象标成 closed 的
    # 窗口：仅凭 uid 不能恢复权限，在线注册集/代表映射缺失时必须拒绝。
    uid = active.uid
    hub._uid_clients.pop(uid, None)
    hub.sessions.pop(uid, None)
    active.closed = False
    before = len(rec.frames)
    assert hub.dispatch(active, {"t": MsgType.PING.value}) is False
    assert len(rec.frames) == before + 1
    assert rec.frames[-1].get("t") == MsgType.ERROR.value


def test_moment_delete_removes_files_and_orphan_is_unreadable(tmp_path):
    hub = _hub(tmp_path)
    owner, rec = _session(hub, "moment-owner")
    image = "12_0.png"
    path = hub._moment_image_path(image)
    assert path
    with open(path, "wb") as fh:
        fh.write(b"png")
    hub.moments[12] = {"pid": 12, "uid": owner.uid, "nick": owner.nick,
                       "text": "", "ts": 0, "images": [image],
                       "likes": [], "comments": []}
    assert hub._moment_image_active(image)
    hub.dispatch(owner, {"t": MsgType.MOMENT_IMG_GET.value, "fn": image})
    assert any(f.get("t") == MsgType.MOMENT_DATA.value for f in rec.frames)

    hub.dispatch(owner, {"t": MsgType.MOMENT_DEL.value, "pid": 12})
    assert not __import__("os").path.exists(path)
    assert not hub._moment_image_active(image)
    hub.dispatch(owner, {"t": MsgType.MOMENT_IMG_GET.value, "fn": image})
    assert rec.frames[-1].get("t") == MsgType.ERROR.value
