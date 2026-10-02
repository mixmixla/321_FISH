# -*- coding: utf-8 -*-
"""CC-02A-RETIRE-CORE: M1 退役屏障与核心内存提交回归。"""
import json
import secrets
import threading
import time
from dataclasses import replace

import pytest

import bots
import auth
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


def _cfg(tmp_path, password=None):
    return replace(
        CFG,
        admin_nick="L57",
        admin_pwd=password or secrets.token_urlsafe(24),
        audit_dir=str(tmp_path / "audit"),
        web_files_dir=str(tmp_path / "web"),
        persist_interval=0.0,
    )


def _hub(tmp_path, *, store=True, password=None):
    password = password or secrets.token_urlsafe(24)
    cfg = _cfg(tmp_path, password)
    h = Hub(
        cfg=cfg,
        audit_dir=str(tmp_path / "audit"),
        store_dir=str(tmp_path / "store") if store else None,
    )
    h._test_admin_password = password
    return h


def _login(hub, nick, password=""):
    rec = _Rec()
    sess = Session(0, nick, "tcp", "127.0.0.1", rec.send)
    ok = hub._on_hello(sess, {"t": MsgType.HELLO.value,
                              "nick": nick, "pwd": password})
    return sess, rec, ok


def _admin_and_user(tmp_path):
    h = _hub(tmp_path)
    admin, admin_rec, ok = _login(h, h._admin_nick, h._test_admin_password)
    assert ok and admin.is_admin
    victim, victim_rec, ok = _login(h, "retire-me")
    assert ok
    return h, admin, admin_rec, victim, victim_rec


def test_retire_keeps_minimal_tombstone_and_rejects_relogin_after_restart(tmp_path):
    h, admin, _admin_rec, victim, victim_rec = _admin_and_user(tmp_path)
    uid = victim.uid

    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": uid})
    assert uid not in h.known
    assert h.nick_to_uid.get("retire-me") == uid
    assert set(h.retired[uid]) == {"nick", "retired_at", "operation_id"}
    assert h.retired[uid]["nick"] == "retire-me"
    assert h.retired[uid]["operation_id"]
    assert victim.closed

    h._persist_flush()
    state = h.store.load()
    assert set(state["retired"][str(uid)]) == {"nick", "retired_at", "operation_id"}
    assert str(uid) not in state.get("known", {})

    restored = _hub(tmp_path)
    # Use the same store directory explicitly; the helper's tmp path is the
    # same isolated directory and therefore models a fresh Hub instance.
    assert restored.retired[uid]["nick"] == "retire-me"
    assert restored.nick_to_uid["retire-me"] == uid
    rejected, rejected_rec, ok = _login(restored, "retire-me")
    assert not ok and rejected.uid == 0
    assert not restored.known.get(uid)

    fresh, _fresh_rec, ok = _login(restored, "new-user")
    assert ok and fresh.uid != uid
    assert restored.nick_to_uid["retire-me"] == uid


def test_admin_and_bot_identity_are_protected_without_side_effect(tmp_path):
    h, admin, admin_rec, victim, _victim_rec = _admin_and_user(tmp_path)
    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": admin.uid})
    assert admin.uid not in h.retired
    assert admin.uid in h.known
    assert any(f.get("code") == "uid" for f in admin_rec.frames)

    bot_uid = bots.BOTS[0].uid
    assert bot_uid in h.known
    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": bot_uid})
    assert bot_uid not in h.retired
    assert bot_uid in h.known
    assert bots.BOT_BY_UID[bot_uid].nick == h.known[bot_uid]["nick"]
    assert victim.uid not in h.retired


def test_retired_final_commit_rejects_chat_draft_schedule_profile_and_private_meta(tmp_path):
    h, admin, _admin_rec, victim, _victim_rec = _admin_and_user(tmp_path)
    other, _other_rec, ok = _login(h, "other")
    assert ok
    uid = victim.uid
    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": uid})

    late = Session(uid, "retire-me", "tcp", "127.0.0.1", _Rec().send)
    h._on_draft_set(late, {"channel": "public", "text": "late draft"})
    h._on_sched_set(late, {"channel": "public", "text": "late schedule",
                           "fire_at": 4102444800})
    h._on_sign_set(late, {"sign": "late sign"})
    h._on_status_set(late, {"status": "busy"})
    h._on_remark_set(late, {"uid": other.uid, "remark": "late remark"})
    h._on_block_set(late, {"target": other.uid, "on": True})
    h._on_read(late, {"channel": "public", "seq": 99})
    h._on_chat(late, {"t": MsgType.CHAT.value, "channel": "public",
                      "text": "late chat"})

    assert not any(k[0] == uid for k in h._drafts)
    assert uid not in h.scheds
    assert uid not in h.blocks
    assert uid not in h.known
    assert not any(m.get("text") == "late chat"
                   for m in h.bus.history("all"))
    assert uid not in h.reads.get("public", {})


def test_retire_cleans_private_records_but_preserves_other_shared_state(tmp_path):
    h, admin, _admin_rec, victim, _victim_rec = _admin_and_user(tmp_path)
    other, _other_rec, ok = _login(h, "other")
    assert ok
    uid = victim.uid
    h.dispatch(victim, {"t": MsgType.CHAT.value, "channel": "public",
                        "text": "victim message"})
    h.dispatch(other, {"t": MsgType.CHAT.value, "channel": "public",
                       "text": "other message"})
    h._drafts[(uid, "public")] = {"text": "draft", "ts": 1}
    h._drafts[(other.uid, "public")] = {"text": "other draft", "ts": 1}
    h.blocks[uid] = {other.uid}
    h.blocks[other.uid] = {uid}
    h.reads["public"] = {uid: 2, other.uid: 2}
    h._burn[33] = {"channel": "public", "uid": uid, "to": None,
                    "ts": 1, "pend": {other.uid}}
    h._burn[34] = {"channel": "public", "uid": other.uid, "to": None,
                    "ts": 1, "pend": {uid}}

    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": uid})
    assert all(m.get("uid") != uid for m in h.bus.history("all"))
    assert (other.uid, "public") in h._drafts
    assert uid not in h.blocks
    assert h.blocks.get(other.uid) == {uid}
    assert uid not in h.reads.get("public", {})
    assert 33 not in h._burn
    assert 34 in h._burn and uid in h._burn[34]["pend"]


def test_admin_user_info_exposes_retirement_state_and_same_uid_retry(tmp_path):
    h, admin, admin_rec, victim, _victim_rec = _admin_and_user(tmp_path)
    uid = victim.uid
    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": uid})
    first = h._admin_user_payload(uid)
    assert first["uid"] == uid
    assert first["retirement"]["target_uid"] == uid
    assert first["retirement"]["status"] == "confirmed"
    op_id = first["retirement"]["operation_id"]

    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": uid})
    second = h._admin_user_payload(uid)
    assert second["retirement"]["operation_id"] == op_id
    assert second["retirement"]["status"] == "confirmed"
    assert len([x for x in h.retired if x == uid]) == 1
    assert any(f.get("retirement", {}).get("operation_id") == op_id
               for f in admin_rec.frames if f.get("t") == MsgType.ADMIN_USER_INFO.value)


def test_retire_requires_store_before_t0(tmp_path):
    h = _hub(tmp_path, store=False)
    admin, admin_rec, ok = _login(h, h._admin_nick, h._test_admin_password)
    assert ok and admin.is_admin
    victim, _victim_rec, ok = _login(h, "no-store-user")
    assert ok
    uid = victim.uid

    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": uid})
    assert uid in h.known
    assert uid not in h.retired
    assert not victim.closed
    assert any(f.get("code") == "store_required" for f in admin_rec.frames)


def test_password_claim_paused_before_hash_cannot_report_success_after_retire(tmp_path, monkeypatch):
    h, admin, _admin_rec, victim, _victim_rec = _admin_and_user(tmp_path)
    started = threading.Event()
    release = threading.Event()
    result = []
    original_make = auth.make

    def paused_make(password):
        started.set()
        assert release.wait(5)
        return original_make(password)

    monkeypatch.setattr(auth, "make", paused_make)
    thread = threading.Thread(target=lambda: result.append(
        h._pwd_claim(victim.uid, "claim-after-retire")))
    thread.start()
    assert started.wait(5)
    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": victim.uid})
    release.set()
    thread.join(5)
    assert not thread.is_alive() and result == [False]
    assert victim.uid not in h.known
    assert h.retired[victim.uid]["nick"] == "retire-me"


def test_admin_profile_target_parsed_before_retire_cannot_recreate_known(tmp_path, monkeypatch):
    h, admin, admin_rec, victim, _victim_rec = _admin_and_user(tmp_path)
    started = threading.Event()
    release = threading.Event()
    original_alias = h._alias_to_uid

    def paused_alias(known, key):
        result = original_alias(known, key)
        if result == victim.uid:
            started.set()
            assert release.wait(5)
        return result

    monkeypatch.setattr(h, "_alias_to_uid", paused_alias)
    thread = threading.Thread(target=lambda: h._on_admin_invis_set(
        admin, {"uid": victim.uid, "on": True}))
    thread.start()
    assert started.wait(5)
    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": victim.uid})
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    assert victim.uid not in h.known
    assert h.retired[victim.uid]["nick"] == "retire-me"
    assert not any(f.get("t") == "invis_ack" and f.get("on")
                   for f in admin_rec.frames)


def test_chat_prepare_then_retire_rejects_final_publish_c(tmp_path, monkeypatch):
    h, admin, _admin_rec, victim, _victim_rec = _admin_and_user(tmp_path)
    started = threading.Event()
    release = threading.Event()
    original_geo = h._san_geo

    def paused_geo(raw):
        started.set()
        assert release.wait(5)
        return original_geo(raw)

    monkeypatch.setattr(h, "_san_geo", paused_geo)
    thread = threading.Thread(target=lambda: h.dispatch(
        victim, {"t": MsgType.CHAT.value, "channel": "public",
                 "text": "prepared then retired", "geo": {"lat": 1, "lon": 2}}))
    thread.start()
    assert started.wait(5)
    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": victim.uid})
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    assert not any(m.get("text") == "prepared then retired"
                   for m in h.bus.history("all"))


def test_draft_and_sched_prepare_then_retire_reject_final_c(tmp_path, monkeypatch):
    h, admin, _admin_rec, victim, _victim_rec = _admin_and_user(tmp_path)
    other, _other_rec, ok = _login(h, "other")
    assert ok

    draft_started = threading.Event()
    draft_release = threading.Event()
    original_conv_key = h._conv_key

    def paused_conv_key(channel, uid, to):
        if uid == victim.uid:
            draft_started.set()
            assert draft_release.wait(5)
        return original_conv_key(channel, uid, to)

    monkeypatch.setattr(h, "_conv_key", paused_conv_key)
    draft_thread = threading.Thread(target=lambda: h._on_draft_set(
        victim, {"channel": "public", "text": "late draft"}))
    draft_thread.start()
    assert draft_started.wait(5)
    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": victim.uid})
    draft_release.set()
    draft_thread.join(5)
    assert not draft_thread.is_alive()
    assert not any(k[0] == victim.uid for k in h._drafts)

    sched_started = threading.Event()
    sched_release = threading.Event()
    original_known_uid = h._known_uid

    def paused_known_uid(uid):
        if uid == other.uid:
            sched_started.set()
            assert sched_release.wait(5)
        return original_known_uid(uid)

    monkeypatch.setattr(h, "_known_uid", paused_known_uid)
    # The first victim is already retired; create a fresh target owner for the
    # due scheduling race and retire it after validation has started.
    owner, _owner_rec, ok = _login(h, "sched-owner")
    assert ok
    sched_thread = threading.Thread(target=lambda: h._on_sched_set(
        owner, {"channel": "private", "to": other.uid,
                 "text": "late schedule", "fire_at": time.time() + 3600}))
    sched_thread.start()
    # private scheduling validates the target; pause on that target instead.
    assert sched_started.wait(5)
    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": owner.uid})
    sched_release.set()
    sched_thread.join(5)
    assert not sched_thread.is_alive()
    assert owner.uid not in h.scheds


def test_web_attach_before_token_publish_then_retire_returns_no_token(tmp_path, monkeypatch):
    h, admin, _admin_rec, _victim, _victim_rec = _admin_and_user(tmp_path)
    started = threading.Event()
    release = threading.Event()
    original_attach = h._attach

    def paused_attach(sess):
        ok = original_attach(sess)
        if ok and sess.nick == "web-late":
            started.set()
            assert release.wait(5)
        return ok

    monkeypatch.setattr(h, "_attach", paused_attach)
    result = []
    thread = threading.Thread(target=lambda: result.append(
        h.login_web("web-late", "127.0.0.1")))
    thread.start()
    assert started.wait(5)
    uid = h.nick_to_uid["web-late"]
    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": uid})
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    assert result and result[0][0] is None
    assert all(s.uid != uid for s in h.web_tokens.values())
    assert uid not in h.known


def test_failed_retire_keeps_fence_and_same_operation_retries_to_confirmed(tmp_path):
    h, admin, admin_rec, victim, _victim_rec = _admin_and_user(tmp_path)
    original_save = h.store.save
    h.store.save = lambda _state: False
    uid = victim.uid
    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": uid})
    op_id = h.retired[uid]["operation_id"]
    assert uid not in h.known
    assert h._retire_ops[uid]["status"] == "failed"
    assert any(f.get("retirement", {}).get("status") == "failed"
               for f in admin_rec.frames if f.get("t") == MsgType.ADMIN_USER_INFO.value)
    h.store.save = original_save
    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": uid})
    assert h._retire_ops[uid]["status"] == "confirmed"
    assert h.retired[uid]["operation_id"] == op_id
    assert h._admin_user_payload(uid)["retirement"]["status"] == "confirmed"


def test_read_keeps_existing_burn_ttl_sweep(tmp_path):
    h, _admin, _admin_rec, victim, _victim_rec = _admin_and_user(tmp_path)
    other, _other_rec, ok = _login(h, "other")
    assert ok
    h.cfg = replace(h.cfg, burn_ttl=1.0)
    h._burn[777] = {"channel": "public", "uid": victim.uid, "to": None,
                    "ts": 0.0, "pend": {other.uid}}
    h._on_read(other, {"channel": "public", "seq": 1})
    assert 777 not in h._burn


@pytest.mark.parametrize("valid_after_retire", [False, True])
def test_taken_due_rechecks_retire_before_final_publish(tmp_path, monkeypatch,
                                                        valid_after_retire):
    h, admin, _admin_rec, victim, _victim_rec = _admin_and_user(tmp_path)
    h.scheds[victim.uid] = {
        "due": {"channel": "public", "to": None,
                "text": "taken due", "fire_at": 0.0, "created": 0.0}}
    entered = threading.Event()
    release = threading.Event()
    original_valid = h._sched_still_valid

    def paused_valid(uid, record):
        entered.set()
        assert release.wait(5)
        return True if valid_after_retire else original_valid(uid, record)

    monkeypatch.setattr(h, "_sched_still_valid", paused_valid)
    thread = threading.Thread(target=lambda: h._sweep_scheds(now=1.0))
    thread.start()
    assert entered.wait(5)
    h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": victim.uid})
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    assert not any(m.get("text") == "taken due" for m in h.bus.history("all"))


def test_chat_publish_and_burn_are_one_memory_commit_before_retire(tmp_path, monkeypatch):
    h, admin, _admin_rec, victim, _victim_rec = _admin_and_user(tmp_path)
    publish_entered = threading.Event()
    release_publish = threading.Event()
    burn_seen = threading.Event()
    release_route = threading.Event()
    retire_invoked = threading.Event()
    allow_retire = threading.Event()
    original_publish = h.bus.publish
    original_route = h._route

    def paused_publish(message):
        out = original_publish(message)
        publish_entered.set()
        assert release_publish.wait(5)
        return out

    def inspect_route(message):
        if (message.get("uid") == victim.uid
                and message.get("text") == "burn commit"):
            assert message["seq"] in h._burn
            burn_seen.set()
            assert release_route.wait(5)
        return original_route(message)

    def retire_call():
        retire_invoked.set()
        assert allow_retire.wait(5)
        h.dispatch(admin, {"t": MsgType.ADMIN_USER_DEL.value, "uid": victim.uid})

    monkeypatch.setattr(h.bus, "publish", paused_publish)
    monkeypatch.setattr(h, "_route", inspect_route)
    result = []
    chat_thread = threading.Thread(target=lambda: result.append(h.dispatch(
        victim, {"t": MsgType.CHAT.value, "channel": "public",
                 "text": "burn commit", "burn": True})))
    chat_thread.start()
    assert publish_entered.wait(5)
    retire_thread = threading.Thread(target=retire_call)
    retire_thread.start()
    try:
        assert retire_invoked.wait(5)
        # The paused publish is inside Hub.lock; the administrator thread has
        # invoked dispatch but cannot acquire that lock until publish/burn C ends.
        probe_acquired = h.lock.acquire(blocking=False)
        if probe_acquired:
            h.lock.release()
        assert probe_acquired is False
        release_publish.set()
        assert burn_seen.wait(5)
        allow_retire.set()
        release_route.set()
    finally:
        release_publish.set()
        allow_retire.set()
        release_route.set()
        chat_thread.join(5)
        retire_thread.join(5)
    assert not chat_thread.is_alive() and not retire_thread.is_alive()
    assert result == [True]
    assert victim.uid in h.retired and victim.uid not in h.known
