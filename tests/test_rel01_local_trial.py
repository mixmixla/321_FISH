# -*- coding: utf-8 -*-
"""REL-01 local-trial gates.

These checks exercise only synthetic configuration/listener doubles and the
explicit hardware/discovery gates.  They never enumerate a device, register a
hotkey, broadcast UDP, or connect to an external address.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _config_probe(env_updates: dict[str, str | None]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    for key in ("MOYU_BIND_HOST", "MOYU_DISCOVERY", "MOYU_TRAY",
                "MOYU_GLOBAL_HOTKEYS", "MOYU_HARDWARE"):
        env.pop(key, None)
    for key, value in env_updates.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    code = (
        "import config, json; "
        "print(json.dumps({'host': config.CFG.bind_host, "
        "'discovery': config.CFG.discovery_enabled, "
        "'tray': config.CFG.tray_enabled, "
        "'hotkeys': config.CFG.global_hotkeys_enabled, "
        "'hardware': config.CFG.hardware_enabled}, sort_keys=True))"
    )
    return subprocess.run(
        [sys.executable, "-c", code], cwd=str(ROOT), env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, check=False,
    )


def test_rel01_config_defaults_and_zero_gates():
    result = _config_probe({})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "host": "0.0.0.0", "discovery": True, "tray": True,
        "hotkeys": True, "hardware": True,
    }

    result = _config_probe({
        "MOYU_BIND_HOST": "127.0.0.1",
        "MOYU_DISCOVERY": "0",
        "MOYU_TRAY": "0",
        "MOYU_GLOBAL_HOTKEYS": "0",
        "MOYU_HARDWARE": "0",
    })
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "host": "127.0.0.1", "discovery": False, "tray": False,
        "hotkeys": False, "hardware": False,
    }


@pytest.mark.parametrize("value", ["", "localhost", "::1", "not-an-ip"])
def test_rel01_bind_host_rejects_non_literal_or_empty(value):
    result = _config_probe({"MOYU_BIND_HOST": value})
    assert result.returncode != 0
    assert "MOYU_BIND_HOST" in result.stderr


def test_rel01_server_and_web_use_same_literal_bind(monkeypatch):
    import server
    import web

    class FakeSocket:
        def __init__(self):
            self.bound = None

        def setsockopt(self, *_args):
            pass

        def bind(self, address):
            self.bound = address

        def listen(self, _backlog):
            pass

        def settimeout(self, _timeout):
            pass

        def close(self):
            pass

    tcp_socket = FakeSocket()
    monkeypatch.setattr(server.socket, "socket",
                        lambda *_args, **_kwargs: tcp_socket)
    stop = threading.Event()
    stop.set()
    cfg = SimpleNamespace(
        bind_host="127.0.0.1", tcp_port=39127, web_port=39129,
        discovery_enabled=False, sweep_interval=1.0, game_auto_tick=1.0,
        tcp_idle_seconds=1.0,
    )
    logs = []
    hub = SimpleNamespace(
        cfg=cfg, audit=SimpleNamespace(log=lambda **kw: logs.append(kw)),
        _admin_pwd_hash="",
    )
    server.serve(hub, port=cfg.tcp_port, stop=stop, start_web=False)
    assert tcp_socket.bound == ("127.0.0.1", cfg.tcp_port)

    web_address = []

    class FakeHttpd:
        def __init__(self, address, _handler):
            web_address.append(address)
            self.server_address = address
            self.daemon_threads = False
            self.allow_reuse_address = False
            self.socket = object()

        def serve_forever(self, **_kwargs):
            return None

    monkeypatch.setattr(web, "_QuietServer", FakeHttpd)
    web.serve(hub, port=cfg.web_port, stop=stop, https=False)
    assert web_address == [("127.0.0.1", cfg.web_port)]


def test_rel01_loopback_lan_hint_does_not_route_probe(monkeypatch):
    import server

    def unexpected_socket(*_args, **_kwargs):
        raise AssertionError("loopback hint must not create a route-probe socket")

    monkeypatch.setattr(server.socket, "socket", unexpected_socket)
    assert server._lan_ip("127.0.0.1") == "127.0.0.1"


def test_rel01_real_loopback_tcp_and_web_bind():
    """Bind both real listeners on loopback and close them without broadcast."""
    import server
    import web

    def free_port():
        probe = __import__("socket").socket()
        try:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]
        finally:
            probe.close()

    tcp_port, web_port = free_port(), free_port()
    stop = threading.Event()
    stop.set()
    logs = []
    cfg = SimpleNamespace(
        bind_host="127.0.0.1", tcp_port=tcp_port, web_port=web_port,
        discovery_enabled=False, sweep_interval=1.0, game_auto_tick=1.0,
        tcp_idle_seconds=1.0,
    )
    hub = SimpleNamespace(
        cfg=cfg, audit=SimpleNamespace(log=lambda **kw: logs.append(kw)),
        _admin_pwd_hash="",
    )
    server.serve(hub, port=tcp_port, stop=stop, start_web=False)
    assert any(item.get("type") == "server_start" for item in logs)

    httpd = web.serve(hub, port=web_port, stop=stop, https=False)
    try:
        assert httpd.server_address[0] == "127.0.0.1"
        deadline = time.monotonic() + 1.0
        while httpd._BaseServer__shutdown_request and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_rel01_discovery_hotkey_and_tray_gates(monkeypatch):
    import client
    import widgets.login_box as login_box

    class CandidateBomb:
        def candidates(self):
            raise AssertionError("discovery candidate lookup was not gated")

    core = SimpleNamespace(connected=False, state="connecting",
                           host="127.0.0.1", port=9527)
    app = object.__new__(client.ChatWindow)
    app.core = core
    app._disco = CandidateBomb()
    app._disco_target = None
    monkeypatch.setattr(client.CFG, "discovery_enabled", False)
    app._auto_target()
    assert (core.host, core.port) == ("127.0.0.1", 9527)

    calls = []
    manager = SimpleNamespace(start=lambda: calls.append("start") or True)
    monkeypatch.setattr(client.CFG, "global_hotkeys_enabled", False)
    assert client._start_global_hotkey(manager) is False
    assert calls == []

    monkeypatch.setattr(client.CFG, "tray_enabled", False)
    client._early_tray = object()
    client._early_root = object()
    client._start_early_tray()
    assert client._early_tray is None and client._early_root is None

    dialog = object.__new__(login_box.LoginDialog)
    dialog._disco = object()
    dialog._poll = lambda: None
    monkeypatch.setattr(login_box.CFG, "discovery_enabled", False)
    dialog._start_disco()
    assert dialog._disco is None


def test_rel01_hardware_gate_skips_audio_video_probe(monkeypatch, tmp_path):
    import client
    import video_api
    import voice_api
    import voice_call

    monkeypatch.setattr(voice_api.CFG, "hardware_enabled", False)
    monkeypatch.setattr(voice_api, "_AVAILABLE", None)
    monkeypatch.setattr(voice_api, "_winmm",
                        lambda: (_ for _ in ()).throw(
                            AssertionError("winmm probe was not gated")))
    assert voice_api.available() is False

    calls = []
    monkeypatch.setattr(video_api.CFG, "hardware_enabled", False)
    monkeypatch.setattr(video_api, "_AVAILABLE", None)
    monkeypatch.setattr(video_api, "_probe_available",
                        lambda _box: calls.append("probe"))
    assert video_api.available() is False
    assert calls == []

    monkeypatch.setattr(voice_call.CFG, "hardware_enabled", False)
    monkeypatch.setattr(voice_call.video_api, "available",
                        lambda: (_ for _ in ()).throw(
                            AssertionError("CallManager preheat was not gated")))
    manager = voice_call.CallManager(SimpleNamespace())
    assert manager._has_cam is False

    notify = object.__new__(client.ChatWindow)
    notify._boss_active = False
    notify._prefs = SimpleNamespace(get=lambda *_args: "default")
    monkeypatch.setattr(client, "winsound",
                        SimpleNamespace(MessageBeep=lambda *_args: calls.append("beep"),
                                        PlaySound=lambda *_args: calls.append("play")))
    notify._play_notify_sound()
    wav = tmp_path / "owned.wav"
    wav.write_bytes(b"RIFFowned")
    notify.show_toast = lambda *_args, **_kwargs: calls.append("toast")
    notify._on_voice(0, str(wav))
    assert "beep" not in calls and "play" not in calls
    assert "toast" in calls


def test_rel01_build_exit_zero_missing_exe_fails(monkeypatch, tmp_path):
    """A green PyInstaller process is insufficient without both real files."""
    import local_trial

    source = tmp_path / "source"
    source.mkdir()

    def fake_copy(_source, target):
        (target / "dist").mkdir(parents=True)
        (target / "dist" / "server.exe").write_bytes(b"server")

    monkeypatch.setattr(local_trial, "_safe_copy_tree", fake_copy)
    monkeypatch.setattr(
        local_trial.subprocess, "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )
    code, _copy, summary = local_trial.build_candidate(
        source, tmp_path / "runs")
    assert code != 0
    assert summary["build_ok"] is False
    assert summary["missing_executables"] == ["client.exe"]


def test_rel01_audit_and_owned_inventory_are_scoped(tmp_path):
    import local_trial

    profile = tmp_path / "profile"
    audit_dir = profile / "moeyu_helper" / "audit"
    audit_dir.mkdir(parents=True)
    (audit_dir / "audit-20990101.jsonl").write_text(
        json.dumps({"type": "login", "nick": "wrong", "via": "tcp",
                    "peer": "127.0.0.1"}) + "\n"
        + json.dumps({"type": "login", "uid": 7,
                      "nick": "REL_trial_client", "via": "tcp",
                      "peer": "127.0.0.1", "ts": 1.0}) + "\n",
        encoding="utf-8")
    audit = local_trial._wait_login_audit(profile, "REL_trial_client", timeout=0.1)
    assert audit["ok"] is True
    assert audit["source"] == "client.exe"
    assert audit["event"]["via"] == "tcp"

    owned = tmp_path / "owned"
    (owned / "nested").mkdir(parents=True)
    (owned / "nested" / "result.log").write_text("owned", encoding="utf-8")
    inventory = local_trial._owned_inventory(owned)
    assert all(not Path(item["path"]).is_absolute() for item in inventory)
    file_entry = next(item for item in inventory if item["type"] == "file")
    assert file_entry["path"] == "nested/result.log"
    assert file_entry["size"] == 5
    assert file_entry["sha256"] == local_trial._sha256(owned / file_entry["path"])
    digest, count = local_trial._tree_fingerprint(owned)
    assert digest and count == len(inventory)
    assert local_trial._image_matches(str(owned / "nested" / "result.log"),
                                      owned / "nested" / "result.log")
