"""Synthetic identity boundaries for local, account-owned history."""

from pathlib import Path
from dataclasses import replace
import os
import queue
import stat
import socket
import threading
import time
from types import SimpleNamespace
import pytest

import client_core
import local_identity
from client_core import ClientCore
from config import CFG
from server import Hub, serve as serve_tcp
from server_recovery import StoreCoordinator
from protocol import MsgType


SCOPE = "a" * 32


def _welcome(core, uid, scope=SCOPE):
    core._dispatch({"t": "welcome", "uid": uid,
                    "auth": {"store_mode": "durable", "store_scope_id": scope}})


def test_unverified_nick_cannot_read_or_claim_legacy_files(tmp_path, monkeypatch):
    root = tmp_path / "history"
    legacy = root / "same"
    legacy.mkdir(parents=True)
    original = b'{"seq": 7, "text": "legacy-secret"}\n'
    (legacy / "public.jsonl").write_bytes(original)
    monkeypatch.setattr(client_core, "_default_history_dir", lambda: str(root))

    core = ClientCore(nick="same")
    try:
        assert core.history_tail("public") == []
        assert Path(core._history._dir) != legacy
        _welcome(core, 11)
        assert all(m.get("text") != "legacy-secret" for m in core.history_tail("public"))
        assert (legacy / "public.jsonl").read_bytes() == original
    finally:
        core.stop()


def test_same_nick_distinct_uids_do_not_share_history(tmp_path):
    root = tmp_path / "history"
    first = ClientCore(nick="same", history_dir=str(root))
    second = None
    try:
        _welcome(first, 11)
        first_dir = Path(first._history._dir)
        first._store_chat({"t": "chat", "channel": "public", "uid": 11,
                           "seq": 1, "text": "only-uid-11"})
        first.stop()
        second = ClientCore(nick="same", history_dir=str(root))
        _welcome(second, 12)
        assert all(m.get("text") != "only-uid-11"
                   for m in second.history_tail("public"))
        assert first_dir != Path(second._history._dir)
    finally:
        first.stop()
        if second is not None:
            second.stop()


def test_same_uid_new_display_nick_reuses_history(tmp_path, monkeypatch):
    root = tmp_path / "history"
    monkeypatch.setattr(client_core, "_default_history_dir", lambda: str(root))
    first = ClientCore(nick="first")
    second = None
    try:
        _welcome(first, 11)
        first_dir = Path(first._history._dir)
        first._store_chat({"t": "chat", "channel": "public", "uid": 11,
                           "seq": 2, "text": "uid-owned"})
        first.stop()
        second = ClientCore(nick="renamed")
        _welcome(second, 11)
        assert first_dir == Path(second._history._dir)
        assert any(m.get("text") == "uid-owned"
                   for m in second.history_tail("public"))
    finally:
        first.stop()
        if second is not None:
            second.stop()


def test_same_uid_other_store_and_volatile_are_fresh(tmp_path):
    root = tmp_path / "history"
    first = ClientCore(nick="same", history_dir=str(root))
    second = third = None
    try:
        _welcome(first, 11)
        first._store_chat({"t": "chat", "channel": "public", "uid": 11,
                           "seq": 5, "text": "store-a"})
        first_dir = Path(first._history._dir)
        second = ClientCore(nick="same", history_dir=str(root))
        _welcome(second, 11, "b" * 32)
        assert Path(second._history._dir) != first_dir
        assert second.history_tail("public") == []
        third = ClientCore(nick="same", history_dir=str(root))
        third._dispatch({"t": "welcome", "uid": 11,
                         "auth": {"store_mode": "volatile", "store_scope_id": SCOPE}})
        assert Path(third._history._dir) != first_dir
        assert third.local_identity is None and third.history_tail("public") == []
        assert not (root / "same").exists()
    finally:
        for core in (first, second, third):
            if core is not None:
                core.stop()


@pytest.mark.parametrize("bad_uid", [True, False, 0, -1, "11"])
def test_invalid_welcome_uid_cannot_bind_or_create_account_path(tmp_path, bad_uid):
    root = tmp_path / "history"
    core = ClientCore(nick="same", history_dir=str(root))
    try:
        core._dispatch({"t": "welcome", "uid": bad_uid,
                        "auth": {"store_mode": "durable", "store_scope_id": SCOPE}})
        assert core.uid is None and core.local_identity is None
        assert core.history_tail("public") == []
        assert not (root / "v2").exists()
        assert core._manual_login_required
    finally:
        core.stop()


@pytest.mark.parametrize("auth", [
    {"store_mode": "durable"},
    {"store_mode": "durable", "store_scope_id": "bad"},
    {"store_mode": "durable", "store_scope_id": "A" * 32},
    {"store_mode": "volatile", "store_scope_id": SCOPE},
])
def test_missing_or_invalid_durable_scope_remains_fresh(tmp_path, auth):
    root = tmp_path / "history"
    first = ClientCore(nick="same", history_dir=str(root))
    second = None
    try:
        _welcome(first, 11)
        first._store_chat({"t": "chat", "channel": "public", "uid": 11,
                           "seq": 14, "text": "durable-only"})
        second = ClientCore(nick="same", history_dir=str(root))
        second._dispatch({"t": "welcome", "uid": 11, "auth": auth})
        assert second.local_identity is None
        assert second.history_tail("public") == []
        assert "v2" not in Path(second._history._dir).parts
    finally:
        first.stop()
        if second is not None:
            second.stop()


def test_same_durable_store_scope_ignores_host_alias(tmp_path):
    root = tmp_path / "history"
    first = ClientCore(host="127.0.0.1", nick="same", history_dir=str(root))
    second = None
    try:
        _welcome(first, 11)
        first._store_chat({"t": "chat", "channel": "public", "uid": 11,
                           "seq": 15, "text": "scope-owned"})
        first.stop()
        second = ClientCore(host="localhost", nick="renamed", history_dir=str(root))
        _welcome(second, 11)
        assert second.local_identity == (SCOPE, 11)
        assert any(m.get("text") == "scope-owned"
                   for m in second.history_tail("public"))
    finally:
        first.stop()
        if second is not None:
            second.stop()


def test_target_change_revokes_old_bundle_and_keeps_old_bytes(tmp_path):
    root = tmp_path / "history"
    core = ClientCore(nick="same", history_dir=str(root))
    try:
        _welcome(core, 11)
        core._store_chat({"t": "chat", "channel": "public", "uid": 11,
                          "seq": 8, "text": "old-target"})
        old = Path(core._history._dir) / "public.jsonl"
        core._history.close()
        original = old.read_bytes()
        core.set_host("127.0.0.2", 23991)
        assert core.uid is None and core.local_identity is None
        assert core.history_tail("public") == []
        assert old.read_bytes() == original
        _welcome(core, 12, "b" * 32)
        assert core.history_tail("public") == []
        assert old.read_bytes() == original
    finally:
        core.stop()


def test_temp_creation_failure_revokes_old_identity_without_fallback(tmp_path, monkeypatch):
    root = tmp_path / "history"
    core = ClientCore(nick="same", history_dir=str(root))
    try:
        _welcome(core, 11)
        core._store_chat({"t": "chat", "channel": "public", "uid": 11,
                          "seq": 41, "text": "private-old"})
        old = Path(core._history._dir) / "public.jsonl"
        core._history.close()
        original = old.read_bytes()
        core.me = {"uid": 11, "nick": "same"}
        core.known = {11: {"nick": "same"}}
        monkeypatch.setattr(core, "_make_local_bundle",
                            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("synthetic temp failure")))
        with pytest.raises(OSError, match="synthetic temp failure"):
            core._reset_local_identity()
        assert core.uid is None and core.local_identity is None
        assert core.me == {} and core.known == {}
        assert core.history_tail("public") == []
        assert old.read_bytes() == original
    finally:
        core.stop()


def test_old_connection_welcome_cannot_commit_after_target_change(tmp_path, monkeypatch):
    core = ClientCore(host="127.0.0.1", port=21111, nick="same",
                      history_dir=str(tmp_path / "history"))
    old = client_core._Connection(epoch=1, host="127.0.0.1", port=21111)
    core._connection = old
    core._epoch = 1
    monkeypatch.setattr(core.retirement, "authenticate", lambda *_: True)
    entered = threading.Event()
    release = threading.Event()
    real_scope = client_core.scoped_directory

    def gated_scope(root, identity):
        entered.set()
        assert release.wait(3)
        return real_scope(root, identity)

    monkeypatch.setattr(client_core, "scoped_directory", gated_scope)
    worker = None
    try:
        worker = threading.Thread(target=core._dispatch,
                                  args=({"t": "welcome", "uid": 11,
                                         "auth": {"store_mode": "durable",
                                                  "store_scope_id": SCOPE}},),
                                  kwargs={"connection": old})
        worker.start()
        assert entered.wait(3)
        core._end_connection(old)
        release.set()
        worker.join(3)
        assert not worker.is_alive()
        core.set_host("127.0.0.2", 22222)
        assert core.uid is None and core.local_identity is None
        assert core.history_tail("public") == []
        assert not any(e.get("t") == "welcome" for e in list(core.events.queue))
    finally:
        release.set()
        if worker is not None:
            worker.join(3)
        core.stop()


def test_target_change_cannot_interleave_post_bind_welcome_effects(tmp_path, monkeypatch):
    core = ClientCore(host="127.0.0.1", port=21111, nick="same",
                      history_dir=str(tmp_path / "history"))
    old = client_core._Connection(epoch=1, host="127.0.0.1", port=21111)
    core._connection = old
    core._epoch = 1
    monkeypatch.setattr(core.retirement, "authenticate", lambda *_: True)
    entered = threading.Event()
    release = threading.Event()
    target_started = threading.Event()
    target_done = threading.Event()
    errors = []
    real_sync = core._sync_custom_stickers

    def gated_sync(items):
        entered.set()  # Identity is bound; roster/history/UI side effects remain.
        assert release.wait(3)
        return real_sync(items)

    def welcome():
        try:
            core._dispatch({"t": "welcome", "uid": 11,
                            "auth": {"store_mode": "durable", "store_scope_id": SCOPE},
                            "history": [{"t": "chat", "channel": "public", "uid": 11,
                                         "seq": 71, "text": "stale-welcome-content"}]},
                           connection=old)
        except BaseException as exc:
            errors.append(exc)

    def switch():
        target_started.set()
        try:
            core.set_host("127.0.0.2", 22222)
        except BaseException as exc:
            errors.append(exc)
        finally:
            target_done.set()

    monkeypatch.setattr(core, "_sync_custom_stickers", gated_sync)
    welcome_thread = threading.Thread(target=welcome)
    target_thread = threading.Thread(target=switch)
    try:
        welcome_thread.start()
        assert entered.wait(3)
        target_thread.start()
        assert target_started.wait(3)
        assert not target_done.wait(0.2)
        release.set()
        welcome_thread.join(3)
        target_thread.join(3)
        assert not welcome_thread.is_alive() and not target_thread.is_alive()
        assert errors == []
        assert core.uid is None and core.local_identity is None
        assert core.me == {} and core.roster == {}
        assert core.history_tail("public") == []
        assert not any(e.get("t") == "welcome"
                       and e.get("_local_generation") == core._local_generation
                       for e in list(core.events.queue))
    finally:
        release.set()
        welcome_thread.join(3)
        if target_thread.ident is not None:
            target_thread.join(3)
        core.stop()


@pytest.mark.parametrize("old_frame", [
    {"t": MsgType.POLL.value, "channel": "public", "uid": 11,
     "seq": 9191, "text": "old-poll"},
    {"t": "error", "code": "pwd", "text": "old-password-rejection"},
])
def test_target_changed_before_drop_rejects_old_connection_frame(tmp_path, old_frame):
    core = ClientCore(host="127.0.0.1", port=21111, nick="same",
                      history_dir=str(tmp_path / "history"))
    old = client_core._Connection(epoch=1, host="127.0.0.1", port=21111)
    core._connection = old
    core._epoch = 1
    try:
        _welcome(core, 11)
        core.set_host("127.0.0.2", 22222)
        # The caller has not dropped the old socket yet; epoch/current alone
        # still consider this captured connection live.
        assert core._connection_current(old)
        assert not old.stop.is_set()
        _welcome(core, 12, "b" * 32)
        generation = core._local_generation
        core._dispatch(old_frame, connection=old)
        assert core.uid == 12 and core._local_generation == generation
        assert core.history_tail("public") == []
        assert not core._manual_login_required
        assert not any(e.get("seq") == 9191 or e.get("text") == "old-password-rejection"
                       for e in list(core.events.queue))
    finally:
        core.stop()


@pytest.mark.parametrize("old_frame", [
    {"t": MsgType.POLL.value, "channel": "public", "uid": 11,
     "seq": 9192, "text": "old-poll-entered"},
    {"t": "error", "code": "pwd", "text": "old-pwd-entered"},
])
def test_entered_frame_finishes_before_target_revocation(tmp_path, monkeypatch, old_frame):
    core = ClientCore(host="127.0.0.1", port=21111, nick="same",
                      history_dir=str(tmp_path / "history"))
    old = client_core._Connection(epoch=1, host="127.0.0.1", port=21111)
    core._connection = old
    core._epoch = 1
    entered = threading.Event()
    release = threading.Event()
    switched = threading.Event()
    errors = []
    real_dispatch = core._dispatch_locked

    def gated_dispatch(*args, **kwargs):
        entered.set()  # The frame is inside the captured transition.
        assert release.wait(3)
        return real_dispatch(*args, **kwargs)

    def run_frame():
        try:
            core._dispatch(old_frame, connection=old)
        except BaseException as exc:
            errors.append(exc)

    def change_target():
        try:
            core.set_host("127.0.0.2", 22222)
        except BaseException as exc:
            errors.append(exc)
        finally:
            switched.set()

    frame_thread = threading.Thread(target=run_frame)
    target_thread = threading.Thread(target=change_target)
    try:
        _welcome(core, 11)
        monkeypatch.setattr(core, "_dispatch_locked", gated_dispatch)
        frame_thread.start()
        assert entered.wait(3)
        target_thread.start()
        assert not switched.wait(0.2)
        release.set()
        frame_thread.join(3)
        target_thread.join(3)
        assert not frame_thread.is_alive() and not target_thread.is_alive()
        assert errors == [] and switched.is_set()
        assert core.uid is None and core.local_identity is None
        assert core.history_tail("public") == []
        assert not any(e.get("t") in (MsgType.POLL.value, "error")
                       and e.get("_local_generation") == core._local_generation
                       and e.get("text") in ("old-poll-entered", "old-pwd-entered")
                       for e in list(core.events.queue))
    finally:
        release.set()
        if frame_thread.ident is not None:
            frame_thread.join(3)
        if target_thread.ident is not None:
            target_thread.join(3)
        core.stop()


def test_target_change_closes_captured_socket_before_waiting_for_send(tmp_path, monkeypatch):
    core = ClientCore(host="127.0.0.1", port=21111, nick="same",
                      history_dir=str(tmp_path / "history"))
    sending = threading.Event()
    closed = threading.Event()
    changed = threading.Event()
    errors = []

    class OldSocket:
        def shutdown(self, _how):
            closed.set()

        def close(self):
            closed.set()

    class BlockedChannel:
        def send_frame(self, _header, _body=b""):
            sending.set()
            assert closed.wait(3)
            raise OSError("captured socket closed")

    old_sock = OldSocket()
    old = client_core._Connection(epoch=1, host="127.0.0.1", port=21111,
                                  sock=old_sock, chan=BlockedChannel())
    core._connection = old
    core._epoch = 1
    core._conn_alive.set()
    monkeypatch.setattr(core.retirement, "authenticate", lambda *_: True)
    monkeypatch.setattr(core, "_sync_custom_stickers",
                        lambda _items: core._send_frame({"t": "synthetic-send"}))

    def accept():
        try:
            core._dispatch({"t": "welcome", "uid": 11,
                            "auth": {"store_mode": "durable", "store_scope_id": SCOPE}},
                           connection=old)
        except BaseException as exc:
            errors.append(exc)

    def switch():
        try:
            core.set_host("127.0.0.2", 22222)
        except BaseException as exc:
            errors.append(exc)
        finally:
            changed.set()

    receiver = threading.Thread(target=accept)
    target = threading.Thread(target=switch)
    try:
        receiver.start()
        assert sending.wait(3)
        target.start()
        assert changed.wait(3)
        receiver.join(3)
        target.join(3)
        assert not receiver.is_alive() and not target.is_alive()
        assert errors == [] and closed.is_set()
        assert core.uid is None and core.local_identity is None
        assert core.history_tail("public") == []
    finally:
        closed.set()
        if receiver.ident is not None:
            receiver.join(3)
        if target.ident is not None:
            target.join(3)
        core.stop()


def test_corrupt_durable_identity_fails_without_overwriting_or_old_account(tmp_path):
    root = tmp_path / "history"
    core = ClientCore(nick="same", history_dir=str(root))
    try:
        _welcome(core, 11)
        core._store_chat({"t": "chat", "channel": "public", "uid": 11,
                          "seq": 6, "text": "old-account"})
        bad_dir = root / "v2" / ("b" * 32) / "uid-12"
        bad_dir.mkdir(parents=True)
        bad = bad_dir / "e2ee_identity.json"
        raw = b'{"priv":"broken"}'
        bad.write_bytes(raw)
        _welcome(core, 12, "b" * 32)
        assert bad.read_bytes() == raw
        assert core.local_identity is None and core.uid is None
        assert core.history_tail("public") == []
        assert not any(e.get("t") == "welcome" and e.get("uid") == 12
                       for e in list(core.events.queue))
        assert any(e.get("code") == "local_storage" for e in list(core.events.queue))
    finally:
        core.stop()


def test_reparse_account_dir_and_nonfile_history_fail_closed(tmp_path, monkeypatch):
    root = tmp_path / "history"
    target = root / "v2" / SCOPE / "uid-11"
    target.mkdir(parents=True)
    marker = target / "keep.txt"
    marker.write_bytes(b"preserve-me")
    real_lstat = local_identity.os.lstat

    def synthetic_reparse(path, *args, **kwargs):
        info = real_lstat(path, *args, **kwargs)
        if str(path) == str(target):
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    core = ClientCore(nick="same", history_dir=str(root))
    try:
        monkeypatch.setattr(local_identity.os, "lstat", synthetic_reparse)
        _welcome(core, 11)
        assert core.local_identity is None and core.uid is None
        assert marker.read_bytes() == b"preserve-me"
        assert core.history_tail("public") == []
    finally:
        monkeypatch.setattr(local_identity.os, "lstat", real_lstat)
        core.stop()

    nonfile = target / "public.jsonl"
    nonfile.mkdir()
    core = ClientCore(nick="same", history_dir=str(root))
    try:
        _welcome(core, 11)
        assert core.local_identity is None and core.uid is None
        assert nonfile.is_dir() and marker.read_bytes() == b"preserve-me"
    finally:
        core.stop()


@pytest.mark.parametrize("kind", ["voice", "vmemo", "sticker", "cover"])
def test_durable_cache_rejects_reparse_leaf_without_overwriting(tmp_path, monkeypatch, kind):
    core = ClientCore(nick="same", history_dir=str(tmp_path / "history"))
    try:
        _welcome(core, 11)
        paths = {
            "voice": Path(core._voice_dir) / "voice_101.wav",
            "vmemo": Path(core._vmemo_dir) / "vmemo_101.vma",
            "sticker": Path(core._sticker_dir) / "code.png",
            "cover": Path(core._pack_cover_dir) / core._cover_name("pack", "png"),
        }
        target = paths[kind]
        original = b"account-owned-original"
        target.write_bytes(original)
        real_lstat = os.lstat

        def marked_lstat(path, *args, **kwargs):
            info = real_lstat(path, *args, **kwargs)
            if Path(path) == target:
                return SimpleNamespace(st_mode=stat.S_IFREG | 0o600,
                                       st_file_attributes=0x400)
            return info

        def receive():
            if kind == "voice":
                core._attach_voice({"seq": 101}, b"new-cache")
            elif kind == "vmemo":
                core._attach_vmemo({"seq": 101}, b"new-cache")
            elif kind == "sticker":
                core._on_sticker_data({"code": "code", "ext": "png"}, b"new-cache")
            else:
                core._on_sticker_pack_cover_data({"pack": "pack", "ext": "png"},
                                                b"new-cache")

        with monkeypatch.context() as patch:
            patch.setattr(local_identity.os, "lstat", marked_lstat)
            receive()
        assert target.read_bytes() == original
        receive()
        assert target.read_bytes() == b"new-cache"
    finally:
        core.stop()

def test_old_cloud_restore_does_not_merge_into_new_uid(tmp_path, monkeypatch):
    core = ClientCore(nick="same", history_dir=str(tmp_path / "history"))
    entered = threading.Event()
    release = threading.Event()
    result = []
    try:
        _welcome(core, 11)

        def send(_header, _body=b"", **_kwargs):
            request = core._cloud_wait["get"]
            request["blob"] = b"synthetic"
            request["ev"].set()
            return True

        def unpack(_blob, _password):
            entered.set()
            assert release.wait(3)
            return {"channels": {"public": [{"seq": 77, "text": "old-cloud"}]}}

        monkeypatch.setattr(core, "_send_frame", send)
        monkeypatch.setattr(client_core, "_cloud_unpack", unpack)
        worker = threading.Thread(target=lambda: result.append(core.cloud_restore("password")))
        worker.start()
        assert entered.wait(3)
        _welcome(core, 12)
        release.set()
        worker.join(3)
        assert not worker.is_alive()
        assert result and result[0][0] is False
        assert core.history_tail("public") == []
    finally:
        release.set()
        core.stop()


def test_old_media_frame_cannot_write_new_uid_cache(tmp_path, monkeypatch):
    core = ClientCore(nick="same", history_dir=str(tmp_path / "history"))
    entered = threading.Event()
    release = threading.Event()
    worker = None
    switch = None
    switch_done = threading.Event()
    switch_errors = []
    try:
        _welcome(core, 11)
        original_attach = core._attach_voice

        def blocked_attach(header, body, *, local_generation=None):
            entered.set()
            assert release.wait(3)
            return original_attach(header, body, local_generation=local_generation)

        monkeypatch.setattr(core, "_attach_voice", blocked_attach)
        worker = threading.Thread(target=core._dispatch,
                                  args=({"t": "chat", "channel": "public", "uid": 11,
                                         "seq": 88, "voice": True, "vmemo": True,
                                         "text": "old-frame"}, b"synthetic-media"))
        worker.start()
        assert entered.wait(3)
        def change_identity():
            try:
                _welcome(core, 12)
            except BaseException as exc:
                switch_errors.append(exc)
            finally:
                switch_done.set()

        switch = threading.Thread(target=change_identity)
        switch.start()
        assert not switch_done.wait(0.2)
        release.set()
        worker.join(3)
        switch.join(3)
        assert not worker.is_alive() and not switch.is_alive()
        assert switch_done.is_set()
        assert switch_errors == []
        assert not list(Path(core._voice_dir).iterdir())
        assert not list(Path(core._vmemo_dir).iterdir())
        assert core.history_tail("public") == []
    finally:
        release.set()
        if worker is not None:
            worker.join(3)
        if switch is not None:
            switch.join(3)
        core.stop()


def test_old_sticker_cover_frame_cannot_write_new_uid_cache(tmp_path, monkeypatch):
    core = ClientCore(nick="same", history_dir=str(tmp_path / "history"))
    entered = threading.Event()
    release = threading.Event()
    worker = None
    switch = None
    switch_done = threading.Event()
    switch_errors = []
    try:
        _welcome(core, 11)
        original = core._on_sticker_pack_cover_data

        def blocked_cover(header, body, *, local_generation=None):
            entered.set()
            assert release.wait(3)
            return original(header, body, local_generation=local_generation)

        monkeypatch.setattr(core, "_on_sticker_pack_cover_data", blocked_cover)
        worker = threading.Thread(target=core._dispatch,
                                  args=({"t": MsgType.STICKER_PACK_COVER_DATA.value,
                                         "pack": "synthetic", "ext": "png"}, b"old-cover"))
        worker.start()
        assert entered.wait(3)
        def change_identity():
            try:
                _welcome(core, 12)
            except BaseException as exc:
                switch_errors.append(exc)
            finally:
                switch_done.set()

        switch = threading.Thread(target=change_identity)
        switch.start()
        assert not switch_done.wait(0.2)
        release.set()
        worker.join(3)
        switch.join(3)
        assert not worker.is_alive() and not switch.is_alive()
        assert switch_done.is_set()
        assert switch_errors == []
        assert not list(Path(core._pack_cover_dir).iterdir())
        assert not any(e.get("t") == "sticker_pack_cover_data"
                       and e.get("_local_generation") == core._local_generation
                       for e in list(core.events.queue))
    finally:
        release.set()
        if worker is not None:
            worker.join(3)
        if switch is not None:
            switch.join(3)
        core.stop()


def test_old_e2ee_rotation_cannot_send_after_uid_switch(tmp_path, monkeypatch):
    core = ClientCore(nick="same", history_dir=str(tmp_path / "history"))
    entered = threading.Event()
    release = threading.Event()
    sent = []
    worker = None
    try:
        _welcome(core, 11)
        old_engine = core.e2ee
        generation = core._local_generation

        def begin(_my_uid, _peer):
            entered.set()
            assert release.wait(3)
            return b"synthetic-rotation"

        monkeypatch.setattr(old_engine, "rotate_begin", begin)
        monkeypatch.setattr(old_engine, "seal_ratchet", lambda *_: b"synthetic-envelope")
        monkeypatch.setattr(old_engine, "rotate_abort", lambda *_: None)
        monkeypatch.setattr(core, "_send_frame", lambda *args, **kwargs: sent.append(args) or True)
        worker = threading.Thread(target=core._rotate_peer,
                                  args=(71, 0.1, generation))
        worker.start()
        assert entered.wait(3)
        _welcome(core, 12)
        release.set()
        worker.join(3)
        assert not worker.is_alive()
        assert core.e2ee is not old_engine and sent == []
        assert core._e2ee_rot_wait == {}
    finally:
        release.set()
        if worker is not None:
            worker.join(3)
        core.stop()


def test_cloud_upload_cannot_send_old_blob_on_new_connection(tmp_path, monkeypatch):
    core = ClientCore(host="127.0.0.1", port=21111, nick="same",
                      history_dir=str(tmp_path / "history"))
    entered = threading.Event()
    release = threading.Event()
    result = []
    worker = None

    class RecordingChannel:
        def __init__(self):
            self.frames = []

        def send_frame(self, header, body=b""):
            self.frames.append((header, body))

    try:
        _welcome(core, 11)
        core._store_chat({"t": "chat", "channel": "public", "uid": 11,
                          "seq": 70, "text": "account-a-only"})
        first_chan = RecordingChannel()
        first = client_core._Connection(epoch=1, host="127.0.0.1", port=21111,
                                        chan=first_chan)
        core._epoch = 1
        core._connection = first
        core._conn_alive.set()
        real_send = core._send_frame

        def delayed_send(header, body=b"", **kwargs):
            entered.set()
            assert release.wait(3)
            return real_send(header, body, **kwargs)

        monkeypatch.setattr(core, "_send_frame", delayed_send)
        worker = threading.Thread(target=lambda: result.append(core.cloud_upload("synthetic-secret")))
        worker.start()
        assert entered.wait(3)
        core._reset_local_identity()
        second_chan = RecordingChannel()
        second = client_core._Connection(epoch=2, host="127.0.0.1", port=21111,
                                         chan=second_chan)
        core._epoch = 2
        core._connection = second
        _welcome(core, 12)
        release.set()
        worker.join(3)
        assert not worker.is_alive()
        assert result and result[0][0] is False
        assert first_chan.frames == [] and second_chan.frames == []
        assert core.history_tail("public") == []
    finally:
        release.set()
        if worker is not None:
            worker.join(3)
        core.stop()


def test_real_durable_welcome_and_refused_password_leave_no_claim(tmp_path):
    store = tmp_path / "store"
    StoreCoordinator.initialize_new(store)
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"),
                  admin_nick="keeper", admin_pwd="synthetic-secret",
                  bind_host="127.0.0.1", discovery_enabled=False,
                  tray_enabled=False)
    hub = Hub(cfg=cfg, store_dir=str(store))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    stop = threading.Event()
    thread = threading.Thread(target=serve_tcp, args=(hub, port, stop, False), daemon=True)
    thread.start()
    root = tmp_path / "history"
    accepted = refused = None
    try:
        deadline = time.monotonic() + 5
        while not hub._service_started:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        accepted = ClientCore(host="127.0.0.1", port=port, nick="same",
                              history_dir=str(root))
        accepted.start()
        while accepted.state != "online" or not accepted.local_identity:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert accepted.local_identity[1] == accepted.uid
        bound = Path(accepted._history._dir)
        accepted.stop()
        assert bound.exists()
        accepted.start()
        deadline = time.monotonic() + 5
        while accepted.state != "online" or Path(accepted._history._dir) != bound:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        refused = ClientCore(host="127.0.0.1", port=port, nick="keeper",
                             pwd="wrong-secret", history_dir=str(root))
        refused.start()
        deadline = time.monotonic() + 5
        while not any(e.get("t") == "error" and e.get("code") == "pwd"
                      for e in list(refused.events.queue)):
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert refused.local_identity is None and refused.uid is None
        assert refused.history_tail("public") == []
        assert not (root / "keeper").exists()
    finally:
        if accepted is not None:
            accepted.stop()
        if refused is not None:
            refused.stop()
        stop.set()
        thread.join(10)
        assert not thread.is_alive()


def test_new_volatile_hub_same_uid_cannot_rejoin_old_group(tmp_path, monkeypatch):
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"),
                  bind_host="127.0.0.1", discovery_enabled=False,
                  tray_enabled=False)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    first = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit1"))
    first_stop = threading.Event()
    first_thread = threading.Thread(target=serve_tcp,
                                    args=(first, port, first_stop, False), daemon=True)
    first_thread.start()
    core = None
    second_stop = threading.Event()
    second_thread = None
    try:
        deadline = time.monotonic() + 5
        while not first._service_started:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        core = ClientCore(host="127.0.0.1", port=port, nick="same",
                          history_dir=str(tmp_path / "history"),
                          reconnect_base=0.05, reconnect_max=0.2)
        core.start()
        while core.state != "online":
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert core.create_group("Grp", public=True)
        while not core._joined_groups:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        old_epoch = core._epoch
        assert core._volatile_rejoin_fence[0] == first._server_epoch
        first_stop.set()
        first_thread.join(10)
        assert not first_thread.is_alive()

        sent_joins = []
        real_send = core._send_frame

        def observed_send(header, body=b"", **kwargs):
            if header.get("t") == MsgType.GROUP_JOIN.value:
                sent_joins.append(header.get("gid"))
            return real_send(header, body, **kwargs)

        monkeypatch.setattr(core, "_send_frame", observed_send)
        second = Hub(cfg=cfg, audit_dir=str(tmp_path / "audit2"))
        assert second._server_epoch != first._server_epoch
        second_thread = threading.Thread(target=serve_tcp,
                                         args=(second, port, second_stop, False), daemon=True)
        second_thread.start()
        deadline = time.monotonic() + 5
        while (core._epoch <= old_epoch or core.state != "online"
               or core._volatile_rejoin_fence is None
               or core._volatile_rejoin_fence[0] != second._server_epoch):
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert core.uid == 1
        assert not sent_joins and not core._joined_groups
    finally:
        if core is not None:
            core.stop()
        first_stop.set()
        first_thread.join(10)
        second_stop.set()
        if second_thread is not None:
            second_thread.join(10)
            assert not second_thread.is_alive()


def test_durable_store_restart_keeps_scope_and_local_only_history(tmp_path):
    store = tmp_path / "store"
    StoreCoordinator.initialize_new(store)
    cfg = replace(CFG, audit_dir=str(tmp_path / "audit"),
                  web_files_dir=str(tmp_path / "web"),
                  bind_host="127.0.0.1", discovery_enabled=False,
                  tray_enabled=False)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    first = Hub(cfg=cfg, store_dir=str(store))
    first_stop = threading.Event()
    first_thread = threading.Thread(target=serve_tcp,
                                    args=(first, port, first_stop, False), daemon=True)
    first_thread.start()
    first_core = second_core = None
    second_stop = threading.Event()
    second_thread = None
    try:
        deadline = time.monotonic() + 5
        while not first._service_started:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        root = tmp_path / "history"
        first_core = ClientCore(host="127.0.0.1", port=port, nick="same",
                                history_dir=str(root))
        first_core.start()
        while first_core.state != "online" or first_core.local_identity is None:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        identity = first_core.local_identity
        first_core._store_chat({"t": "chat", "channel": "public", "uid": identity[1],
                                "seq": 999991, "text": "local-only-marker"})
        first_core.stop()
        first_stop.set()
        first_thread.join(10)
        assert not first_thread.is_alive()

        second = Hub(cfg=cfg, store_dir=str(store))
        second_thread = threading.Thread(target=serve_tcp,
                                         args=(second, port, second_stop, False), daemon=True)
        second_thread.start()
        deadline = time.monotonic() + 5
        while not second._service_started:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        second_core = ClientCore(host="localhost", port=port, nick="same",
                                 history_dir=str(root))
        second_core.start()
        while second_core.state != "online" or second_core.local_identity is None:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert second_core.local_identity == identity
        assert any(m.get("text") == "local-only-marker"
                   for m in second_core.history_tail("public"))
        assert not any(m.get("text") == "local-only-marker"
                       for m in second.bus.history("all"))
    finally:
        if first_core is not None:
            first_core.stop()
        if second_core is not None:
            second_core.stop()
        first_stop.set()
        first_thread.join(10)
        second_stop.set()
        if second_thread is not None:
            second_thread.join(10)
            assert not second_thread.is_alive()
