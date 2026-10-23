"""Account chat state must not inherit legacy nickname preferences."""

import json
import queue
import threading
import tkinter as tk
import pytest

import client_core
import prefs as prefs_module

from client import ChatWindow
from client_core import ClientCore
from config import CFG
from launcher import _prepare_profile
from prefs import Prefs
from protocol import MsgType


SCOPE = "b" * 32


def test_uid_chat_view_keeps_legacy_content_unclaimed(tmp_path):
    path = tmp_path / "prefs.json"
    legacy = {"drafts": {"public": "old-draft"},
              "stars": {"public": {"1": {"text": "old-favorite"}}},
              "profiles": {"same": {"drafts": {"public": "old-profile"},
                                    "stars": {"public": {"2": {"text": "old-star"}}}}},
              "active_profile": "same", "skin": "office"}
    path.write_text(json.dumps(legacy), encoding="utf-8")
    prefs = Prefs(str(path))
    prefs.enable_uid_chat_view()
    assert prefs.get("drafts") == {}
    assert prefs.get("stars") == {}
    assert prefs.pinned() == []
    assert _prepare_profile(prefs, "same")
    assert prefs.get("drafts") == {}
    prefs.bind_uid_chat_view((SCOPE, 11))
    assert prefs.get("drafts") == {}
    prefs.set("drafts", {"public": "uid-11"})
    prefs.set("stars", {"public": {"3": {"text": "uid-star"}}})
    prefs.toggle_pin("public")
    prefs.bind_uid_chat_view((SCOPE, 12))
    assert prefs.get("drafts") == {} and prefs.get("stars") == {}
    assert prefs.pinned() == []
    prefs.bind_uid_chat_view((SCOPE, 11))
    assert prefs.get("drafts") == {"public": "uid-11"}
    assert prefs.get("stars")["public"]["3"]["text"] == "uid-star"
    assert prefs.pinned() == ["public"]
    saved = json.loads(path.read_text(encoding="utf-8"))
    for key in ("drafts", "stars", "profiles", "skin"):
        assert saved[key] == legacy[key]


def test_volatile_uid_chat_view_never_persists(tmp_path):
    path = tmp_path / "prefs.json"
    prefs = Prefs(str(path))
    prefs.enable_uid_chat_view()
    prefs.bind_uid_chat_view(None)
    prefs.set("drafts", {"public": "temporary"})
    prefs.set("stars", {"public": {"4": {"text": "temporary"}}})
    assert not path.exists()
    prefs.bind_uid_chat_view(None)
    assert prefs.get("drafts") == {} and prefs.get("stars") == {}


def test_uid_save_failure_preserves_legacy_file_bytes(tmp_path, monkeypatch):
    path = tmp_path / "prefs.json"
    original = b'{"drafts":{"public":"old"},"stars":{"opaque":42}}'
    path.write_bytes(original)
    prefs = Prefs(str(path))
    prefs.enable_uid_chat_view()
    prefs.bind_uid_chat_view((SCOPE, 11))

    def refuse(_source, _target):
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(prefs_module.os, "replace", refuse)
    with pytest.raises(OSError, match="synthetic replace failure"):
        prefs.set("drafts", {"public": "uid-owned"})
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".prefs-uid-*"))


def test_invalid_existing_prefs_cannot_be_claimed_or_rewritten(tmp_path):
    path = tmp_path / "prefs.json"
    original = b'{"profiles":'
    path.write_bytes(original)
    prefs = Prefs(str(path))
    prefs.enable_uid_chat_view()
    assert prefs.get("drafts") == {}
    with pytest.raises(OSError, match="original file preserved"):
        prefs.bind_uid_chat_view((SCOPE, 11))
    with pytest.raises(OSError, match="original file preserved"):
        prefs.remember_login_nick("same")
    with pytest.raises(OSError, match="original file preserved"):
        prefs.set("dnd", True)
    assert path.read_bytes() == original


@pytest.mark.parametrize("bad", [{"drafts": ["wrong"]}, {"pinned": {"wrong": 1}},
                                       {"stars": ["legacy-list"]}, "broken-entry"])
def test_malformed_uid_chat_entry_fails_closed(tmp_path, bad):
    path = tmp_path / "prefs.json"
    original = json.dumps({"uid_profiles": {f"{SCOPE}:uid-11": bad},
                           "profiles": {"same": {"drafts": {"public": "old"}}}}).encode()
    path.write_bytes(original)
    prefs = Prefs(str(path))
    prefs.enable_uid_chat_view()
    with pytest.raises(ValueError, match="account preferences"):
        prefs.bind_uid_chat_view((SCOPE, 11))
    assert prefs.get("drafts") == {} and prefs.get("stars") == {}
    assert path.read_bytes() == original


def test_real_tk_does_not_show_nickname_draft_or_favorite(tmp_path, monkeypatch):
    for name in ("hardware_enabled", "discovery_enabled", "global_hotkeys_enabled",
                 "tray_enabled"):
        monkeypatch.setattr(CFG, name, False)
    path = tmp_path / "prefs.json"
    path.write_text(json.dumps({"drafts": {"public": "legacy-draft"},
                                "stars": {"public": {"9": {"text": "legacy-star"}}},
                                "profiles": {"same": {"drafts": {"public": "old"}}}}),
                    encoding="utf-8")
    core = ClientCore(nick="same", history_dir=str(tmp_path / "history"))
    window = None
    try:
        window = ChatWindow(core, prefs_path=str(path))
        assert window._drafts == {} and window._stars == {}
        assert "legacy-draft" not in window.entry.get("1.0", "end")
        core._dispatch({"t": "welcome", "uid": 11,
                        "auth": {"store_mode": "durable", "store_scope_id": SCOPE}})
        window._poll()
        assert window._drafts == {} and window._stars == {}
        window._prefs.set("drafts", {"public": "uid-11-draft"})
        window._prefs.set("stars", {"public": {"10": {"text": "uid-11-star"}}})
        window._draft_ts["public"] = 9999999999.0
        window._remote_ts["public"] = 9999999999.0
        window._draft_dirty = True
        window._send_hist["public"] = ["uid-11-sent"]
        window._hist_draft["public"] = "uid-11-unsent"
        window._pending_reply = {"nick": "same", "text": "uid-11-reply"}
        applied = []
        window._apply_conv_states = lambda states: applied.append(states)
        window._queue_conv_states({"public": {"draft": "old-callback"}})
        core._push({"t": "chat", "channel": "public", "uid": 11,
                    "seq": 99, "text": "queued-from-uid-11"})
        core._dispatch({"t": "welcome", "uid": 12,
                        "auth": {"store_mode": "durable", "store_scope_id": SCOPE}})
        window.root.update()
        window._poll()
        assert applied == []
        assert window._draft_ts == {} and window._remote_ts == {}
        assert not window._draft_dirty
        assert window._send_hist == {} and window._hist_draft == {}
        assert window._pending_reply is None
        assert not any(row.get("text") == "queued-from-uid-11"
                       for row in window.msg_list._rows)
        assert window._drafts == {} and window._stars == {}
        assert "uid-11-draft" not in window.entry.get("1.0", "end")
        assert "legacy-draft" not in window.entry.get("1.0", "end")
    finally:
        if window is not None:
            window.quit_app()
        else:
            core.stop()


def test_full_event_queue_does_not_block_tk_target_change(tmp_path, monkeypatch):
    for name in ("hardware_enabled", "discovery_enabled", "global_hotkeys_enabled",
                 "tray_enabled"):
        monkeypatch.setattr(CFG, name, False)
    core = ClientCore(nick="same", history_dir=str(tmp_path / "history"))
    window = None
    worker = None
    rescue = None
    try:
        window = ChatWindow(core, prefs_path=str(tmp_path / "prefs.json"))
        core._dispatch({"t": "welcome", "uid": 11,
                        "auth": {"store_mode": "durable", "store_scope_id": SCOPE}})
        window._poll()
        core.events = queue.Queue(maxsize=1)
        core.events.put_nowait({"t": "seed"})
        emitting = threading.Event()
        switched = threading.Event()
        rescued = threading.Event()
        real_emit = core._emit_event

        def observed_emit(event):
            if event.get("t") == MsgType.POLL.value:
                emitting.set()
            return real_emit(event)

        monkeypatch.setattr(core, "_emit_event", observed_emit)
        worker = threading.Thread(target=core._dispatch,
                                  args=({"t": MsgType.POLL.value, "channel": "public",
                                         "uid": 11, "seq": 331, "text": "old-queued-poll"},))
        worker.start()
        assert emitting.wait(3)

        def bounded_rescue():
            if not switched.wait(3):
                rescued.set()
                # Cleanup only if a regression blocked the Tk owner.
                for _ in range(4):
                    try:
                        core.events.get(timeout=0.5)
                    except queue.Empty:
                        if switched.is_set():
                            break

        rescue = threading.Thread(target=bounded_rescue)
        rescue.start()
        core.set_host("127.0.0.2", 22222)  # Tk owner thread, while queue is full.
        switched.set()
        assert not rescued.is_set()
        assert core.events.qsize() <= core.events.maxsize + 1
        for _ in range(6):
            core._push_retirement_state()
        assert core.events.qsize() <= core.events.maxsize + 1
        window._poll()
        worker.join(3)
        assert not worker.is_alive()
        window._poll()
        assert not any(row.get("text") == "old-queued-poll"
                       for row in window.msg_list._rows)
    finally:
        if worker is not None:
            while core.events.full():
                try:
                    core.events.get_nowait()
                except queue.Empty:
                    break
            worker.join(3)
        if rescue is not None:
            rescue.join(3)
        if window is not None:
            window.quit_app()
        else:
            core.stop()


def test_cloud_restore_origin_survives_late_tk_hook(tmp_path, monkeypatch):
    for name in ("hardware_enabled", "discovery_enabled", "global_hotkeys_enabled",
                 "tray_enabled"):
        monkeypatch.setattr(CFG, name, False)
    core = ClientCore(nick="same", history_dir=str(tmp_path / "history"))
    window = None
    worker = None
    entered = threading.Event()
    release = threading.Event()
    result = []
    try:
        window = ChatWindow(core, prefs_path=str(tmp_path / "prefs.json"))
        core._dispatch({"t": "welcome", "uid": 11,
                        "auth": {"store_mode": "durable", "store_scope_id": SCOPE}})
        window._poll()
        applied = []
        monkeypatch.setattr(window, "_apply_conv_states", lambda states: applied.append(states))
        original_applyer = core._conv_applyer

        def gated_applyer(states, generation):
            entered.set()  # Core checked A; the callback has not queued Tk work.
            assert release.wait(3)
            original_applyer(states, generation)

        def synthetic_get(_header, _body=b"", **_kwargs):
            if _header.get("t") != MsgType.CLOUD_GET.value:
                return False
            request = core._cloud_wait["get"]
            request["blob"] = b"synthetic-cloud"
            request["ev"].set()
            return True

        monkeypatch.setattr(core, "_conv_applyer", gated_applyer)
        monkeypatch.setattr(core, "_send_frame", synthetic_get)
        monkeypatch.setattr(client_core, "_cloud_unpack",
                            lambda *_: {"channels": {},
                                        "conv_states": {"public": {"draft": "A-only"}}})
        worker = threading.Thread(target=lambda: result.append(core.cloud_restore("secret")))
        worker.start()
        assert entered.wait(3)
        core._dispatch({"t": "welcome", "uid": 12,
                        "auth": {"store_mode": "durable", "store_scope_id": SCOPE}})
        window._poll()
        release.set()
        worker.join(3)
        assert not worker.is_alive()
        window.root.update()
        window._poll()
        assert result and result[0][0]
        assert applied == [] and window._drafts == {}
        assert "A-only" not in window.entry.get("1.0", "end")
    finally:
        release.set()
        if worker is not None:
            worker.join(3)
        if window is not None:
            window.quit_app()
        else:
            core.stop()
