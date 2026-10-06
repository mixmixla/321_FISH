"""KICK stops the old desktop authentication; ordinary reconnect remains separate."""
import queue
import threading
from types import SimpleNamespace

import pytest

from client import ChatWindow
from client_core import ClientCore


@pytest.fixture
def core(tmp_path):
    value = ClientCore(nick="synthetic-kick", history_dir=str(tmp_path / "history"),
                       reconnect_base=.001, reconnect_max=.001)
    yield value
    value.stop()


def test_kicked_ends_reconnector_before_another_login_attempt(core):
    attempts = []

    def connect_once():
        attempts.append("hello")
        core._set_state("online")
        if len(attempts) == 1:
            core._dispatch({"t": "error", "code": "kicked", "text": "synthetic kick"})
        else:
            core._stop.set()  # bounds the original behavior without hiding the second attempt
        return True

    core._connect_once = connect_once
    thread = threading.Thread(target=core._run)
    thread.start()
    thread.join(2)
    assert not thread.is_alive()
    assert attempts == ["hello"]
    assert core.state == "offline"


def test_kicked_blocks_send_and_late_welcome(core):
    sent = []
    core._chan = SimpleNamespace(send_frame=lambda h, b: sent.append(h))
    core._conn_alive.set()
    core.uid = 7
    core._set_state("online")
    core._dispatch({"t": "error", "code": "kicked", "text": "synthetic kick"})
    assert core._send_frame({"t": "chat", "text": "must not send"}) is False
    assert sent == []
    core._dispatch({"t": "welcome", "uid": 7, "nick": core.nick,
                    "roster": [], "groups": [], "history": []})
    assert not core.connected
    assert core.state == "offline"


def test_deleted_blocks_old_session_and_late_welcome(core):
    core._dispatch({"t": "error", "code": "deleted"})
    assert core._manual_login_required and core._stop.is_set()
    core._dispatch({"t": "welcome", "uid": 7, "nick": core.nick,
                    "roster": [], "groups": [], "history": []})
    assert core.uid is None and not core.connected


@pytest.mark.parametrize("authenticating", [True, False])
def test_retired_revokes_only_the_current_authentication_attempt(core, authenticating):
    from client_core import _Connection
    connection = _Connection(1, core.host, core.port, authenticating=authenticating)
    core._connection, core._epoch = connection, 1
    core._dispatch({"t": "error", "code": "retired", "manual_login_required": True,
                    "_connection_epoch": 999}, connection=connection)
    assert core._manual_login_required is authenticating
    error = next(e for e in list(core.events.queue) if e.get("t") == "error")
    assert error["_connection_epoch"] == 1
    assert error.get("manual_login_required", False) is authenticating


def test_late_revocation_and_welcome_cannot_mutate_a_new_connection(core):
    from client_core import _Connection
    old = _Connection(1, core.host, core.port)
    current = _Connection(2, core.host, core.port)
    core._connection, core._epoch = current, 2
    for event in ({"t": "error", "code": "deleted"},
                  {"t": "welcome", "uid": 77, "nick": "old-login"}):
        core._dispatch(event, connection=old)
    assert core.uid is None and not core._manual_login_required
    assert not current.stop.is_set()


def test_start_does_not_clear_stop_or_replace_a_living_connector(core):
    entered = threading.Event()
    release = threading.Event()
    old = threading.Thread(target=lambda: (entered.set(), release.wait(4)))
    old.start()
    assert entered.wait(1)
    core._reconnector = old
    core._stop.set()
    try:
        with pytest.raises(RuntimeError, match="has not stopped"):
            core.start()
        assert core._stop.is_set() and core._reconnector is old
    finally:
        release.set()
        old.join(2)


def test_closed_connection_keeps_ordinary_offline_feedback(core):
    from client_core import _Connection
    connection = _Connection(1, core.host, core.port)
    core._connection, core._epoch = connection, 1
    connection.stop.set()
    assert not core._send_frame({'t': 'chat', 'text': 'synthetic offline'})
    assert any(e.get('code') == 'offline' for e in list(core.events.queue))


def test_kicked_uses_existing_manual_login_exit():
    calls = []
    app = SimpleNamespace(_closed=False, request_switch_account=lambda: calls.append("switch"),
                          _append_sys=lambda text: calls.append(text))
    ChatWindow._on_error(app, {"t": "error", "code": "kicked", "text": "synthetic kick"})
    assert calls == ["switch"]


def test_poll_returns_immediately_when_kick_closes_window():
    events = queue.Queue()
    events.put({"t": "error", "code": "kicked"})
    events.put({"t": "welcome"})
    handled = []
    app = SimpleNamespace(_closed=False, core=SimpleNamespace(events=events))

    def handle(event):
        assert not app._closed, "polled another event after the window closed"
        handled.append(event["t"])
        app._closed = True

    app._handle = handle
    ChatWindow._poll(app)
    assert handled == ["error"]
    assert events.qsize() == 1


@pytest.mark.parametrize("discovery_enabled", [False, True])
def test_quit_cancels_pending_callbacks_before_destroying_root(discovery_enabled):
    events = []
    def tcl_call(*args):
        if args == ("after", "info"):
            return ("after#1", "after#2")
        assert args[:2] == ("after", "cancel")
        events.append(args[2])

    root = SimpleNamespace(tk=SimpleNamespace(call=tcl_call, splitlist=lambda value: value),
                           after_cancel=lambda job: pytest.fail("must preserve child-owned command bookkeeping"),
                           destroy=lambda: events.append("destroy"))
    app = SimpleNamespace(_closed=False, root=root, _mini=None,
                          _disco=(SimpleNamespace(stop=SimpleNamespace(
                              set=lambda: events.append("discovery-stop")))
                              if discovery_enabled else None),
                          _hotkey=SimpleNamespace(stop=lambda: None),
                          _shot_hotkey=SimpleNamespace(stop=lambda: None),
                          _persist_drafts=lambda: None,
                          core=SimpleNamespace(stop=lambda: events.append("core-stop")))
    ChatWindow.quit_app(app)
    assert app._closed is True
    assert events == (["discovery-stop"] if discovery_enabled else []) + [
        "after#1", "after#2", "destroy", "core-stop"]
