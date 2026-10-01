# -*- coding: utf-8 -*-
"""一对一文件传输的服务器端参与者鉴权回归。"""
import copy
from dataclasses import replace

import pytest

from config import CFG
from filexfer import TransferMeta, XferStatus
from protocol import MsgType
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


def _session(hub, nick, stype="tcp", peer_ip="10.0.0.1"):
    out = _Capture()
    sess = Session(0, nick, stype, peer_ip, out.send)
    assert hub._attach(sess)
    return sess, out


def _clear(*captures):
    for capture in captures:
        capture.frames.clear()


def _seed(hub, fid, sender, receiver, status=XferStatus.OFFERING.value):
    rec = TransferMeta(
        file_id=fid, filename="报告.bin", size=9, chunk_size=3,
        md5="0" * 32, sender_uid=sender.uid, receiver_uid=receiver.uid,
        status=status, sender_nick=sender.nick, sender_ip=sender.peer_ip,
        sender_port=4567, acked=[0],
    )
    rec.created_at = 1234.5
    hub.xfers[fid] = rec
    return rec


def _dispatch(hub, sess, t, fid, body=b"", **fields):
    header = {"t": t, "file_id": fid,
              "uid": 999999, "from_uid": 999999, "to": 999999}
    header.update(fields)
    assert hub.dispatch(sess, header, body) is True


def _real_ids(sender, receiver, role="sender"):
    if role == "receiver":
        return {"uid": receiver.uid, "from_uid": receiver.uid,
                "to": sender.uid}
    return {"uid": sender.uid, "from_uid": sender.uid,
            "to": receiver.uid}


@pytest.mark.parametrize(
    ("operation", "bad_role", "status"),
    [
        (MsgType.FILE_REJECT.value, "sender", XferStatus.OFFERING.value),
        (MsgType.FILE_REJECT.value, "outsider", XferStatus.OFFERING.value),
        (MsgType.FILE_VERIFY.value, "sender", XferStatus.ACCEPTED.value),
        (MsgType.FILE_VERIFY.value, "outsider", XferStatus.ACCEPTED.value),
        (MsgType.FILE_CANCEL.value, "outsider", XferStatus.ACCEPTED.value),
    ],
)
def test_denied_file_action_preserves_record_then_legal_action_continues(
        hub, operation, bad_role, status):
    sender, sender_out = _session(hub, "sender")
    receiver, receiver_out = _session(hub, "receiver")
    outsider, outsider_out = _session(hub, "outsider")
    _clear(sender_out, receiver_out, outsider_out)
    bad = {"sender": sender, "outsider": outsider}[bad_role]
    fid = f"follow-{operation}"
    rec = _seed(hub, fid, sender, receiver, status)
    before = copy.deepcopy(rec.to_dict())
    sender_before = list(sender_out.frames)
    receiver_before = list(receiver_out.frames)

    claimed_role = ("receiver"
                    if operation in (MsgType.FILE_REJECT.value,
                                     MsgType.FILE_VERIFY.value)
                    else "sender")
    _dispatch(hub, bad, operation, fid, ok=True, index=1,
              **_real_ids(sender, receiver, claimed_role))

    assert hub.xfers.get(fid) is rec
    assert rec.to_dict() == before
    assert sender_out.frames == sender_before
    assert receiver_out.frames == receiver_before

    if operation == MsgType.FILE_REJECT.value:
        _dispatch(hub, receiver, operation, fid,
                  **_real_ids(sender, receiver, "receiver"))
        expected = {"t": MsgType.FILE_REJECT.value, "file_id": fid,
                    "text": "对方拒绝了文件"}
        assert sender_out.frames[-1] == (expected, b"")
    elif operation == MsgType.FILE_VERIFY.value:
        _dispatch(hub, receiver, operation, fid, ok=True,
                  **_real_ids(sender, receiver, "receiver"))
        expected = {"t": MsgType.FILE_VERIFY.value, "file_id": fid,
                    "ok": True}
        assert sender_out.frames[-1] == (expected, b"")
    else:
        _dispatch(hub, sender, operation, fid,
                  **_real_ids(sender, receiver, "sender"))
        expected = {"t": MsgType.FILE_CANCEL.value, "file_id": fid,
                    "text": "传输已取消"}
        assert receiver_out.frames[-1] == (expected, b"")
    assert fid not in hub.xfers


def test_direct_ok_requires_sender_and_allows_same_uid_second_session(hub):
    sender, sender_out = _session(hub, "sender")
    sender_web, sender_web_out = _session(hub, "sender", "web", "10.0.0.2")
    receiver, receiver_out = _session(hub, "receiver")
    receiver_web, receiver_web_out = _session(hub, "receiver", "web", "10.0.0.3")
    outsider, outsider_out = _session(hub, "outsider")
    assert sender_web.uid == sender.uid
    assert receiver_web.uid == receiver.uid
    _clear(sender_out, sender_web_out, receiver_out, receiver_web_out,
           outsider_out)
    fid = "direct-role"
    rec = _seed(hub, fid, sender, receiver, XferStatus.ACCEPTED.value)
    before = copy.deepcopy(rec.to_dict())

    _dispatch(hub, receiver_web, MsgType.FILE_DIRECT_OK.value, fid,
              **_real_ids(sender, receiver))
    _dispatch(hub, outsider, MsgType.FILE_DIRECT_OK.value, fid,
              **_real_ids(sender, receiver))
    assert rec.to_dict() == before
    assert not rec.direct
    assert sender_out.frames == receiver_out.frames == []

    _dispatch(hub, sender_web, MsgType.FILE_DIRECT_OK.value, fid,
              **_real_ids(sender, receiver))
    assert rec.direct is True
    assert sender_out.frames == receiver_out.frames == []


def test_same_uid_second_sessions_keep_legal_roles_and_notify_counterpart(hub):
    sender, sender_out = _session(hub, "sender")
    sender_web, sender_web_out = _session(hub, "sender", "web", "10.0.0.2")
    receiver, receiver_out = _session(hub, "receiver")
    receiver_web, receiver_web_out = _session(hub, "receiver", "web", "10.0.0.3")
    assert sender_web.uid == sender.uid
    assert receiver_web.uid == receiver.uid
    _clear(sender_out, sender_web_out, receiver_out, receiver_web_out)
    sender_ids = _real_ids(sender, receiver, "sender")
    receiver_ids = _real_ids(sender, receiver, "receiver")

    reject_fid = "second-receiver-reject"
    _seed(hub, reject_fid, sender, receiver)
    _dispatch(hub, receiver_web, MsgType.FILE_REJECT.value, reject_fid,
              **receiver_ids)
    assert reject_fid not in hub.xfers
    assert sender_web_out.frames == [({
        "t": MsgType.FILE_REJECT.value, "file_id": reject_fid,
        "text": "对方拒绝了文件",
    }, b"")]
    assert sender_out.frames == []
    assert receiver_web_out.frames == []

    verify_fid = "second-receiver-verify"
    _seed(hub, verify_fid, sender, receiver, XferStatus.ACCEPTED.value)
    _dispatch(hub, receiver_web, MsgType.FILE_VERIFY.value, verify_fid,
              ok=True, **receiver_ids)
    assert verify_fid not in hub.xfers
    assert sender_web_out.frames[-1] == ({
        "t": MsgType.FILE_VERIFY.value, "file_id": verify_fid,
        "ok": True,
    }, b"")
    assert receiver_web_out.frames == []

    sender_cancel_fid = "second-sender-cancel"
    _seed(hub, sender_cancel_fid, sender, receiver,
          XferStatus.ACCEPTED.value)
    _dispatch(hub, sender_web, MsgType.FILE_CANCEL.value,
              sender_cancel_fid, **sender_ids)
    assert sender_cancel_fid not in hub.xfers
    assert receiver_web_out.frames == [({
        "t": MsgType.FILE_CANCEL.value, "file_id": sender_cancel_fid,
        "text": "传输已取消",
    }, b"")]
    assert sender_web_out.frames[-1][0]["file_id"] == verify_fid

    receiver_cancel_fid = "second-receiver-cancel"
    _seed(hub, receiver_cancel_fid, sender, receiver,
          XferStatus.ACCEPTED.value)
    _dispatch(hub, receiver_web, MsgType.FILE_CANCEL.value,
              receiver_cancel_fid, **receiver_ids)
    assert receiver_cancel_fid not in hub.xfers
    assert sender_web_out.frames[-1] == ({
        "t": MsgType.FILE_CANCEL.value, "file_id": receiver_cancel_fid,
        "text": "传输已取消",
    }, b"")
    assert receiver_web_out.frames[-1][0]["file_id"] == sender_cancel_fid


def test_accept_checks_receiver_before_status_change_and_legal_flow(hub):
    sender, sender_out = _session(hub, "sender")
    receiver, receiver_out = _session(hub, "receiver")
    outsider, outsider_out = _session(hub, "outsider")
    _clear(sender_out, receiver_out, outsider_out)
    fid = "accept-role"
    rec = _seed(hub, fid, sender, receiver)
    before = copy.deepcopy(rec.to_dict())

    _dispatch(hub, outsider, MsgType.FILE_ACCEPT.value, fid, acked=[2],
              **_real_ids(sender, receiver, "receiver"))
    assert rec.to_dict() == before
    assert sender_out.frames == []
    assert receiver_out.frames == []

    _dispatch(hub, receiver, MsgType.FILE_ACCEPT.value, fid, acked=[1],
              **_real_ids(sender, receiver, "receiver"))
    assert rec.status == XferStatus.ACCEPTED.value
    assert sender_out.frames[-1] == ({
        "t": MsgType.FILE_ACCEPT.value, "file_id": fid,
        "receiver_ip": receiver.peer_ip, "acked": [1],
    }, b"")
    assert receiver_out.frames[-1] == ({
        "t": MsgType.FILE_ACCEPT.value, "file_id": fid,
        "sender_ip": sender.peer_ip, "filename": rec.filename,
        "size": rec.size, "md5": rec.md5, "acked": [1],
    }, b"")


def test_listen_checks_sender_before_mutation_and_notifies_receiver(hub):
    sender, sender_out = _session(hub, "sender")
    receiver, receiver_out = _session(hub, "receiver")
    outsider, outsider_out = _session(hub, "outsider")
    _clear(sender_out, receiver_out, outsider_out)
    fid = "listen-role"
    rec = _seed(hub, fid, sender, receiver, XferStatus.ACCEPTED.value)
    before = copy.deepcopy(rec.to_dict())

    _dispatch(hub, receiver, MsgType.FILE_LISTEN.value, fid, port=1111,
              **_real_ids(sender, receiver))
    _dispatch(hub, outsider, MsgType.FILE_LISTEN.value, fid, port=2222,
              **_real_ids(sender, receiver))
    assert rec.to_dict() == before
    assert sender_out.frames == receiver_out.frames == []

    _dispatch(hub, sender, MsgType.FILE_LISTEN.value, fid, port=3333,
              **_real_ids(sender, receiver, "sender"))
    assert rec.sender_port == 3333
    assert receiver_out.frames[-1] == ({
        "t": MsgType.FILE_DIRECT.value, "file_id": fid,
        "ip": rec.sender_ip, "port": 3333,
    }, b"")


def test_data_checks_sender_before_forwarding_and_legal_body_reaches_receiver(hub):
    sender, sender_out = _session(hub, "sender")
    receiver, receiver_out = _session(hub, "receiver")
    outsider, outsider_out = _session(hub, "outsider")
    _clear(sender_out, receiver_out, outsider_out)
    fid = "data-role"
    rec = _seed(hub, fid, sender, receiver, XferStatus.ACCEPTED.value)
    before = copy.deepcopy(rec.to_dict())

    _dispatch(hub, receiver, MsgType.FILE_DATA.value, fid, b"bad", index=0,
              **_real_ids(sender, receiver))
    _dispatch(hub, outsider, MsgType.FILE_DATA.value, fid, b"bad", index=1,
              **_real_ids(sender, receiver))
    assert rec.to_dict() == before
    assert sender_out.frames == receiver_out.frames == []

    _dispatch(hub, sender, MsgType.FILE_DATA.value, fid, b"abc", index=0,
              **_real_ids(sender, receiver, "sender"))
    assert rec.created_at > before["created_at"]
    assert receiver_out.frames[-1] == ({
        "t": MsgType.FILE_DATA.value, "file_id": fid, "index": 0,
    }, b"abc")


def test_chunk_ack_checks_receiver_before_forwarding_and_legal_ack(hub):
    sender, sender_out = _session(hub, "sender")
    receiver, receiver_out = _session(hub, "receiver")
    outsider, outsider_out = _session(hub, "outsider")
    _clear(sender_out, receiver_out, outsider_out)
    fid = "ack-role"
    rec = _seed(hub, fid, sender, receiver, XferStatus.ACCEPTED.value)
    before = copy.deepcopy(rec.to_dict())

    _dispatch(hub, sender, MsgType.FILE_CHUNK_ACK.value, fid, index=0,
              **_real_ids(sender, receiver, "receiver"))
    _dispatch(hub, outsider, MsgType.FILE_CHUNK_ACK.value, fid, index=1,
              **_real_ids(sender, receiver, "receiver"))
    assert rec.to_dict() == before
    assert sender_out.frames == receiver_out.frames == []

    _dispatch(hub, receiver, MsgType.FILE_CHUNK_ACK.value, fid, index=2,
              **_real_ids(sender, receiver, "receiver"))
    assert sender_out.frames[-1] == ({
        "t": MsgType.FILE_CHUNK_ACK.value, "file_id": fid, "index": 2,
    }, b"")


@pytest.mark.parametrize(
    ("operation", "fields", "body"),
    [
        (MsgType.FILE_REJECT.value, {}, b""),
        (MsgType.FILE_VERIFY.value, {"ok": True}, b""),
        (MsgType.FILE_CANCEL.value, {}, b""),
        (MsgType.FILE_DIRECT_OK.value, {}, b""),
        (MsgType.FILE_LISTEN.value, {"port": 4000}, b""),
        (MsgType.FILE_DATA.value, {"index": 0}, b"abc"),
        (MsgType.FILE_CHUNK_ACK.value, {"index": 0}, b""),
    ],
)
def test_unknown_file_id_is_ignored_without_peer_notification(
        hub, operation, fields, body):
    sender, sender_out = _session(hub, "sender")
    receiver, receiver_out = _session(hub, "receiver")
    outsider, outsider_out = _session(hub, "outsider")
    _clear(sender_out, receiver_out, outsider_out)
    _dispatch(hub, outsider, operation, "missing-file-id", body, **fields)
    assert hub.xfers == {}
    assert sender_out.frames == []
    assert receiver_out.frames == []
