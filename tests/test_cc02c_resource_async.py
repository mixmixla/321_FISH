# -*- coding: utf-8 -*-
"""CC-02C RESOURCE：bot/提醒/Agent/preview 的最终内存 C 回归。

固定合成输入：owner nick ``async-owner``、target nick ``async-target``、
URL ``https://preview.example/a`` / ``https://preview.example/b``，所有结果
只写隔离 Hub 的内存历史。异步顺序用 Event/Barrier 或直接锁状态断言，不用
sleep 证明排序；Agent 只替换本地 adapter 函数，不执行 324 外部工具。
"""
import copy
import threading
import time

import pytest

from server import Hub, Session
from config import CFG
from dataclasses import replace


URL_U = "https://preview.example/a"
URL_V = "https://preview.example/b"
AGENT_TEXT = "合成 Agent 结果"


class _Capture:
    __test__ = False

    def __init__(self):
        self.frames = []

    def send(self, payload, body=b""):
        self.frames.append((copy.deepcopy(payload), bytes(body or b"")))


def _hub(tmp_path):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"), admin_pwd="")
    return Hub(cfg=cfg, audit_dir=str(tmp_path / "audit"))


def _attach(hub, nick, stype="tcp"):
    out = _Capture()
    sess = Session(0, nick, stype, "127.0.0.1", out.send)
    assert hub._attach(sess)
    out.frames.clear()
    return sess, out


def _history(hub, uid, to):
    key = hub.bus.key("private", uid, to)
    return hub.bus.history(key)


def _seed_public(hub, sess, text):
    message = hub.bus.publish({"t": "chat", "channel": "public",
                               "uid": sess.uid, "nick": sess.nick,
                               "text": text, "ts": time.time()})
    hub._route(message)
    return message


def test_bot_say_owner_context_commits_before_fence_and_rejects_after(tmp_path):
    import bots

    h = _hub(tmp_path)
    owner, out = _attach(h, "async-owner")
    bot = bots.BOT_ECHO
    h.bot_say(bot, owner.uid, "before", owner_uid=owner.uid,
              source_kind="agent", request_seq=7)
    before = _history(h, bot.uid, owner.uid)
    assert any(m.get("text") == "before" and m.get("uid") == bot.uid
               for m in before)
    out.frames.clear()
    with h.lock:
        h.retired[owner.uid] = {"nick": owner.nick, "retired_at": time.time(),
                                "operation_id": "retire-async"}
    h.bot_say(bot, owner.uid, "after", owner_uid=owner.uid,
              source_kind="agent", request_seq=8)
    after = _history(h, bot.uid, owner.uid)
    assert not any(m.get("text") == "after" for m in after)
    assert not any(p.get("text") == "after" for p, _body in out.frames)


def test_bot_say_error_result_uses_same_owner_gate(tmp_path):
    import bots

    h = _hub(tmp_path)
    owner, _out = _attach(h, "async-error")
    h.bot_say(bots.BOT_ECHO, owner.uid, "error branch",
              owner_uid=owner.uid, source_kind="agent-error", request_seq=9)
    messages = _history(h, bots.BOT_ECHO.uid, owner.uid)
    assert messages and messages[-1]["text"] == "error branch"


def test_bot_offline_and_other_uid_are_not_blocked_by_one_owner_fence(tmp_path):
    import bots

    h = _hub(tmp_path)
    owner, _owner_out = _attach(h, "bot-fenced")
    other, _other_out = _attach(h, "bot-other")
    with h.lock:
        h.retired[owner.uid] = {"nick": owner.nick, "retired_at": time.time(),
                                "operation_id": "retire-bot-fenced"}
    # The bot target is an always-known actor; a fenced owner is rejected,
    # while a different owner remains able to receive a normal bot result.
    assert not h.bot_say(bots.BOT_ECHO, owner.uid, "blocked",
                         owner_uid=owner.uid, source_kind="offline")
    assert h.bot_say(bots.BOT_ECHO, other.uid, "other",
                     owner_uid=other.uid, source_kind="offline")
    assert any(m.get("text") == "other"
               for m in _history(h, bots.BOT_ECHO.uid, other.uid))


def test_reminder_enqueue_take_due_and_owner_cancel_are_hub_atomic(tmp_path):
    import bots

    h = _hub(tmp_path)
    owner, _owner_out = _attach(h, "remind-owner")
    other, _other_out = _attach(h, "remind-other")
    h._bot_reminder_enqueue(owner.uid, time.time() - 1, "owner note",
                            bots.BOT_REMIND.uid)
    h._bot_reminder_enqueue(other.uid, time.time() - 1, "other note",
                            bots.BOT_REMIND.uid)
    due = h._bot_reminder_take_due(time.time())
    assert {r["uid"] for r in due} == {owner.uid, other.uid}
    h._bot_reminder_enqueue(owner.uid, time.time() + 3600, "future",
                            bots.BOT_REMIND.uid)
    h._bot_reminder_cancel_owner(owner.uid)
    assert all(r.get("uid") != owner.uid for r in h.bot_reminders)
    assert any(r.get("uid") == other.uid for r in h.bot_reminders) is False


def test_sweep_reminder_result_is_final_bot_context(tmp_path):
    import bots

    h = _hub(tmp_path)
    owner, _out = _attach(h, "remind-sweep")
    h._bot_reminder_enqueue(owner.uid, time.time() - 1, "到期内容",
                            bots.BOT_REMIND.uid)
    bots.sweep_reminders(h)
    hist = _history(h, bots.BOT_REMIND.uid, owner.uid)
    assert any("到期内容" in (m.get("text") or "") for m in hist)


def test_reminder_owner_cancel_preserves_other_owner(tmp_path):
    import bots

    h = _hub(tmp_path)
    owner, _owner_out = _attach(h, "remind-cancel")
    other, _other_out = _attach(h, "remind-keep")
    h._bot_reminder_enqueue(owner.uid, time.time() + 3600, "mine",
                            bots.BOT_REMIND.uid)
    h._bot_reminder_enqueue(other.uid, time.time() + 3600, "theirs",
                            bots.BOT_REMIND.uid)
    h._bot_reminder_cancel_owner(owner.uid)
    assert all(item.get("uid") != owner.uid for item in h.bot_reminders)
    assert any(item.get("uid") == other.uid for item in h.bot_reminders)


def test_agent_success_and_exception_reenter_bot_gate(tmp_path, monkeypatch):
    import agent_bot
    import bots

    h = _hub(tmp_path)
    owner, _out = _attach(h, "agent-owner")
    monkeypatch.setattr(agent_bot, "_adapter_answer",
                        lambda _text, _mock: AGENT_TEXT)
    monkeypatch.setattr(agent_bot, "_has_adapter", lambda: True)
    monkeypatch.setattr(agent_bot, "_324_ROOT", object())
    agent_bot._run_async(h, "写代码 合成", owner.uid,
                         owner_uid=owner.uid, source_kind="agent",
                         request_seq=11)
    hist = _history(h, bots.get_agent_bot().uid, owner.uid)
    assert any(m.get("text") == AGENT_TEXT for m in hist)
    monkeypatch.setattr(agent_bot, "_adapter_answer",
                        lambda _text, _mock: (_ for _ in ()).throw(
                            RuntimeError("synthetic adapter failure")))
    agent_bot._run_async(h, "研究 合成", owner.uid,
                         owner_uid=owner.uid, source_kind="agent",
                         request_seq=12)
    assert any("执行失败" in (m.get("text") or "")
               for m in _history(h, bots.get_agent_bot().uid, owner.uid))


def test_agent_late_result_after_owner_fence_does_not_publish(tmp_path,
                                                              monkeypatch):
    import agent_bot
    import bots

    h = _hub(tmp_path)
    owner, out = _attach(h, "agent-late")
    with h.lock:
        h.retired[owner.uid] = {"nick": owner.nick, "retired_at": time.time(),
                                "operation_id": "retire-agent"}
    monkeypatch.setattr(agent_bot, "_adapter_answer", lambda *_args: AGENT_TEXT)
    agent_bot._run_async(h, "写代码 合成", owner.uid,
                         owner_uid=owner.uid, source_kind="agent",
                         request_seq=13)
    assert not any(m.get("uid") == bots.get_agent_bot().uid
                   for m in _history(h, bots.get_agent_bot().uid, owner.uid))
    assert not any(p.get("text") == AGENT_TEXT for p, _body in out.frames)


def test_preview_cache_hit_releases_preview_lock_before_callback(tmp_path,
                                                                  monkeypatch):
    h = _hub(tmp_path)
    owner, _out = _attach(h, "preview-cache")
    meta = {"title": "cache", "desc": "", "domain": "preview.example",
            "url": URL_U, "image": ""}
    with h._preview_lock:
        h._preview_cache[URL_U] = (time.time(), meta)
    observed = []

    def callback(seq, url, value, **_kwargs):
        acquired = h._preview_lock.acquire(blocking=False)
        observed.append(acquired)
        if acquired:
            h._preview_lock.release()

    monkeypatch.setattr(h, "_preview_ready", callback)
    message = _seed_public(h, owner, f"看 {URL_U}")
    h._maybe_fetch_preview(URL_U, message)
    assert observed == [True]


def test_preview_worker_result_is_dropped_after_author_fence(tmp_path, monkeypatch):
    import server

    h = _hub(tmp_path)
    owner, _out = _attach(h, "preview-worker-fence")
    message = _seed_public(h, owner, f"worker {URL_U}")
    entered = threading.Event()
    release = threading.Event()

    def fetch(_url, _cfg):
        entered.set()
        assert release.wait(3.0)
        return {"title": "late", "desc": "", "domain": "preview.example",
                "url": URL_U, "image": ""}

    monkeypatch.setattr(server, "fetch_preview", fetch)
    thread = threading.Thread(target=h._fetch_preview_worker,
                              args=(URL_U, message["seq"], "public",
                                    owner.uid, None), daemon=True)
    thread.start()
    assert entered.wait(3.0)
    with h.lock:
        h.retired[owner.uid] = {"nick": owner.nick, "retired_at": time.time(),
                                "operation_id": "retire-preview-worker"}
    release.set()
    thread.join(3.0)
    assert not thread.is_alive()
    assert "preview" not in message


def test_preview_callback_rechecks_final_url_and_deleted_state(tmp_path):
    h = _hub(tmp_path)
    owner, out = _attach(h, "preview-edit")
    message = _seed_public(h, owner, f"首链 {URL_U}")
    expected = {"seq": message["seq"], "url": URL_U,
                "channel": "public", "uid": owner.uid, "to": None}
    h._on_edit(owner, {"t": "msg_edit", "seq": message["seq"],
                       "text": f"改链 {URL_V}"})
    h._preview_ready(message["seq"], URL_U,
                     {"title": "stale", "url": URL_U}, expected=expected)
    assert "preview" not in message
    out.frames.clear()
    h._on_edit(owner, {"t": "msg_edit", "seq": message["seq"],
                       "text": f"改回 {URL_U}"})
    h._preview_ready(message["seq"], URL_U,
                     {"title": "final", "url": URL_U}, expected=expected)
    assert message.get("preview", {}).get("title") == "final"
    assert any(p.get("t") == "preview" for p, _body in out.frames)
    h._on_del(owner, {"t": "msg_del", "seq": message["seq"]})
    h._preview_ready(message["seq"], URL_U,
                     {"title": "deleted", "url": URL_U}, expected=expected)
    assert message["text"] == ""
    assert message["preview"]["title"] == "final"


def test_preview_private_target_fence_rejects_callback(tmp_path):
    h = _hub(tmp_path)
    owner, _owner_out = _attach(h, "preview-private-owner")
    target, target_out = _attach(h, "preview-private-target")
    message = h.bus.publish({"t": "chat", "channel": "private",
                             "uid": owner.uid, "nick": owner.nick,
                             "to": target.uid, "text": f"私链 {URL_U}",
                             "ts": time.time()})
    h._route(message)
    with h.lock:
        h.retired[target.uid] = {"nick": target.nick, "retired_at": time.time(),
                                 "operation_id": "retire-preview-target"}
    h._preview_ready(message["seq"], URL_U,
                     {"title": "late", "url": URL_U},
                     expected={"seq": message["seq"], "url": URL_U,
                               "channel": "private", "uid": owner.uid,
                               "to": target.uid})
    assert "preview" not in message
    assert not any(p.get("t") == "preview" for p, _body in target_out.frames)


def test_preview_same_url_other_message_is_not_patched(tmp_path):
    h = _hub(tmp_path)
    owner, _out = _attach(h, "preview-two")
    first = _seed_public(h, owner, f"one {URL_U}")
    second = _seed_public(h, owner, f"two {URL_U}")
    h._preview_ready(first["seq"], URL_U,
                     {"title": "one", "url": URL_U},
                     expected={"seq": first["seq"], "url": URL_U,
                               "channel": "public", "uid": owner.uid,
                               "to": None})
    assert first.get("preview", {}).get("title") == "one"
    assert "preview" not in second


def test_edit_del_and_preview_event_have_no_bus_to_hub_lock_inversion(tmp_path):
    h = _hub(tmp_path)
    owner, _out = _attach(h, "preview-lock-order")
    message = _seed_public(h, owner, f"lock {URL_U}")
    done = threading.Event()

    def worker():
        h._preview_ready(message["seq"], URL_U,
                         {"title": "lock-safe", "url": URL_U},
                         expected={"seq": message["seq"], "url": URL_U,
                                   "channel": "public", "uid": owner.uid,
                                   "to": None})
        done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    assert done.wait(3.0)
    assert not thread.is_alive()
