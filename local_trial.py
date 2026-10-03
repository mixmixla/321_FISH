# -*- coding: utf-8 -*-
"""REL-01 Windows local-trial build and launch harness.

The harness creates a clean source copy for PyInstaller and runs the two
resulting executables with synthetic profiles on a private Windows desktop.
It deliberately imports only ``launch_process`` from ``test_sandbox``; no
pytest runtime guard or monkeypatch environment is injected into an EXE.

Examples (PowerShell 7):

    python local_trial.py probe
    python local_trial.py build
    python local_trial.py run --source-dir <build-source>

``run`` uses loopback TCP/HTTP, disables discovery, tray, global hotkeys and
hardware, and records process identity, profile inventory, hashes, logs and
cleanup status under its run directory.  It never sends desktop input.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

from test_sandbox import (
    launch_process,
    private_desktop_probe,
    process_image_path,
    process_state,
)
from test_gate import source_manifest, _safe_source_path


ROOT = Path(__file__).resolve().parent
DEFAULT_RUN_ROOT = ROOT / "_tmp_gui" / "local-trial-runs"
EXCLUDED_DIRS = {
    ".git", ".venv", "__pycache__", ".pytest_cache", "_tmp_gui",
    "audit", "server_state", "web_tls", "web_files", "downloads",
    "history", "models", "build", "dist",
}
EXCLUDED_NAMES = {"prefs.json", "crash.log", "crash.log.1"}
SAFE_ENV_KEYS = {
    "ALLUSERSPROFILE", "APPDATA", "COMSPEC", "COMMONPROGRAMFILES",
    "COMMONPROGRAMFILES(X86)", "COMMONPROGRAMW6432", "HOMEDRIVE",
    "HOMEPATH", "LOCALAPPDATA", "NUMBER_OF_PROCESSORS", "OS", "PATH",
    "PATHEXT", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER",
    "PROCESSOR_LEVEL", "PROCESSOR_REVISION", "PROGRAMDATA", "PROGRAMFILES",
    "PROGRAMFILES(X86)", "PROGRAMW6432", "PUBLIC", "SYSTEMDRIVE",
    "SYSTEMROOT", "USERNAME", "USERDOMAIN", "VIRTUAL_ENV", "WINDIR",
    "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "TZ",
}
GATE_ENV_KEYS = {
    "MOYU_GATE_SANDBOX", "MOYU_GATE_SANDBOX_REPORT", "MOYU_GATE_RUN_ID",
    "MOYU_GATE_SOURCE_ROOT", "MOYU_GATE_DESKTOP_NAME", "MOYU_GATE_PROFILE",
}
TRIAL_FLAGS = {
    "MOYU_BIND_HOST": "127.0.0.1",
    "MOYU_DISCOVERY": "0",
    "MOYU_TRAY": "0",
    "MOYU_GLOBAL_HOTKEYS": "0",
    "MOYU_HARDWARE": "0",
    "MOYU_WEB_HTTPS": "0",
}


def _utc_id(prefix: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{now}-{uuid.uuid4().hex[:10]}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_reparse(path: Path) -> bool:
    """Reject symlink/junction entries in owned evidence trees."""
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction is not None and is_junction():
            return True
        if os.name == "nt":
            return bool(path.stat().st_file_attributes & 0x400)
    except OSError:
        return True
    return False


def _assert_relative_path(value: str) -> None:
    path = Path(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"inventory path is not a safe relative path: {value!r}")


def _owned_inventory(root: Path) -> list[dict]:
    """Inventory only an owned root using relative paths and content hashes."""
    root = root.resolve()
    if not root.is_dir() or _is_reparse(root):
        raise ValueError(f"owned inventory root is unsafe: {root}")
    entries = [{"path": ".", "type": "dir", "size": 0, "sha256": None}]
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        if _is_reparse(path):
            raise ValueError(f"owned inventory contains symlink/junction: {path}")
        rel = path.relative_to(root).as_posix()
        _assert_relative_path(rel)
        if path.is_dir():
            entries.append({"path": rel, "type": "dir", "size": 0, "sha256": None})
        elif path.is_file():
            entries.append({"path": rel, "type": "file", "size": path.stat().st_size,
                            "sha256": _sha256(path)})
        else:
            raise ValueError(f"owned inventory contains unsupported entry: {path}")
    return entries


def _tree_fingerprint(root: Path) -> tuple[str, int]:
    """Fingerprint an owned source tree and validate all relative paths."""
    entries = _owned_inventory(root)
    data = json.dumps(entries, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest(), len(entries)


def _source_fingerprint(root: Path) -> tuple[str, int]:
    """Read approved source inputs only, never runtime/IDE/credential files."""
    entries, digest = source_manifest(root)
    return digest, len(entries)


def _executable_inventory(source_copy: Path) -> tuple[dict, list[str]]:
    """Require two non-empty executable files before a build can pass."""
    exes = {}
    missing = []
    for name in ("server.exe", "client.exe"):
        path = (source_copy / "dist" / name).resolve()
        if not path.is_file() or path.stat().st_size <= 0:
            missing.append(name)
            continue
        exes[name] = {"path": str(path), "size": path.stat().st_size,
                      "sha256": _sha256(path)}
    return exes, missing


def _safe_copy_tree(source: Path, target: Path) -> None:
    """Copy only reviewed source inputs, including current uncommitted code."""
    source = source.resolve()
    entries, _digest = source_manifest(source)
    target.mkdir(parents=True, exist_ok=False)
    for entry in entries:
        path = source / entry["path"]
        if not _safe_source_path(path, source):
            raise RuntimeError(f"unsafe source path: {entry['path']}")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"source changed during copy: {entry['path']}")
        output = target / entry["path"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)


def _clean_env(*, profile: Path | None = None, flags: dict[str, str] | None = None,
               ports: tuple[int, int] | None = None) -> dict[str, str]:
    """Build a small OS-only environment; never copy deployment secrets."""
    env = {key: value for key, value in os.environ.items()
           if key.upper() in SAFE_ENV_KEYS}
    for key in GATE_ENV_KEYS:
        env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    if profile is not None:
        profile = profile.resolve()
        appdata = profile / "AppData" / "Roaming"
        local = profile / "AppData" / "Local"
        temp = profile / "Temp"
        for path in (profile, appdata, local, temp):
            path.mkdir(parents=True, exist_ok=True)
        env.update({
            "USERPROFILE": str(profile),
            "HOMEDRIVE": profile.anchor.rstrip("\\/"),
            "HOMEPATH": str(profile)[len(profile.drive):] or "\\",
            "APPDATA": str(appdata),
            "LOCALAPPDATA": str(local),
            "TEMP": str(temp),
            "TMP": str(temp),
        })
    if flags:
        env.update(flags)
    if ports:
        env["MOYU_TCP_PORT"] = str(ports[0])
        env["MOYU_WEB_PORT"] = str(ports[1])
    return env


def _new_run_dir(root: Path, prefix: str) -> Path:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    run = root / _utc_id(prefix)
    run.mkdir()
    return run


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _ports() -> tuple[int, int]:
    first = _free_port()
    second = _free_port()
    while second == first:
        second = _free_port()
    return first, second


def _build_env(profile: Path | None = None) -> dict[str, str]:
    env = _clean_env(profile=profile, flags={})
    # Build subprocesses must not inherit a gate runtime hook or an arbitrary
    # PYTHONPATH/tool integration from the calling desktop session.
    env.pop("PYTHONPATH", None)
    return env


def build_candidate(source: Path, output_root: Path) -> tuple[int, Path, dict]:
    run_dir = _new_run_dir(output_root, "build")
    source_copy = run_dir / "source"
    _safe_copy_tree(source, source_copy)
    log_path = run_dir / "build.log"
    command = [sys.executable, "build.py"]
    started = time.time()
    with log_path.open("wb") as log:
        result = subprocess.run(command, cwd=str(source_copy), env=_build_env(run_dir / "build-profile"),
                                stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT, check=False,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    exes, missing = _executable_inventory(source_copy)
    build_ok = result.returncode == 0 and not missing
    exit_code = int(result.returncode) if result.returncode else (0 if build_ok else 5)
    summary = {
        "schema_version": "REL-01.v1.build",
        "run_id": run_dir.name,
        "source": str(source.resolve()),
        "source_copy": str(source_copy),
        "command": command,
        "python": sys.executable,
        "exit_code": exit_code,
        "build_ok": build_ok,
        "missing_executables": missing,
        "duration_seconds": round(time.time() - started, 3),
        "log": str(log_path),
        "executables": exes,
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return exit_code, source_copy, summary


def _wait_tcp(port: int, timeout: float = 12.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def _web_probe(port: int, timeout: float = 6.0) -> dict:
    url = f"http://127.0.0.1:{port}/"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(256)
            return {"ok": True, "status": int(response.status),
                    "bytes_read": len(body), "url": url}
    except Exception as exc:
        return {"ok": False, "url": url, "error_type": type(exc).__name__}


def _wait_login_audit(profile: Path, nick: str, timeout: float = 12.0) -> dict:
    """Prove that the launched client.exe logged in through the TCP path."""
    audit_dir = profile / "moeyu_helper" / "audit"
    expected = {"type": "login", "nick": nick, "via": "tcp",
                "peer": "127.0.0.1"}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if audit_dir.is_dir():
            for path in sorted(audit_dir.glob("audit-*.jsonl")):
                try:
                    lines = path.read_text(encoding="utf-8").splitlines()
                except OSError:
                    continue
                for line in reversed(lines):
                    try:
                        event = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    if all(event.get(key) == value for key, value in expected.items()):
                        # Keep only non-secret audit metadata in the result.
                        kept = {key: event.get(key) for key in
                                ("type", "uid", "nick", "peer", "via", "ts", "time")}
                        return {"ok": True, "source": "client.exe",
                                "audit_dir": str(audit_dir), "event": kept}
        time.sleep(0.15)
    return {"ok": False, "source": "client.exe",
            "audit_dir": str(audit_dir), "expected": expected,
            "error_type": "login_audit_timeout"}


def _image_matches(image: str | None, expected: Path) -> bool:
    if not image:
        return False
    try:
        return os.path.normcase(os.path.abspath(image)) == os.path.normcase(
            os.path.abspath(expected))
    except (TypeError, OSError):
        return False


def _path_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _process_record(proc, *, desktop: str, command: list[str],
                    expected_exe: Path | None = None) -> dict:
    pid = int(getattr(proc, "pid", 0) or 0)
    image = process_image_path(pid) if pid else None
    return {
        "pid": pid,
        "session_id": getattr(proc, "session_id", None),
        "desktop": desktop,
        "image": image,
        "image_matches_expected": (_image_matches(image, expected_exe)
                                    if expected_exe is not None else None),
        "state": process_state(pid),
        "command": command,
    }


def run_candidate(source: Path, run_root: Path, server_exe: Path | None = None,
                  client_exe: Path | None = None) -> tuple[int, dict]:
    run_dir = _new_run_dir(run_root, "run")
    profiles = {"server": run_dir / "profile-server",
                "client": run_dir / "profile-client"}
    logs = {role: run_dir / f"{role}.log" for role in profiles}
    for profile in profiles.values():
        profile.mkdir(parents=True, exist_ok=True)
    source = source.resolve()
    server_exe = (server_exe or source / "dist" / "server.exe").resolve()
    client_exe = (client_exe or source / "dist" / "client.exe").resolve()
    try:
        source_fingerprint_before, source_entry_count = _source_fingerprint(source)
    except Exception as exc:
        summary = {"schema_version": "REL-01.v1.run", "run_id": run_dir.name,
                   "source": str(source), "exit_code": 5,
                   "error": {"type": type(exc).__name__}}
        (run_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return 5, summary
    if not _path_inside(server_exe, source) or not _path_inside(client_exe, source):
        summary = {"schema_version": "REL-01.v1.run", "run_id": run_dir.name,
                   "source": str(source), "exit_code": 2,
                   "error": "executable must be inside source candidate",
                   "server_exe": str(server_exe), "client_exe": str(client_exe),
                   "source_fingerprint_before": source_fingerprint_before}
        (run_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2, summary
    if not server_exe.is_file() or not client_exe.is_file():
        summary = {"schema_version": "REL-01.v1.run", "run_id": run_dir.name,
                   "source": str(source), "exit_code": 2,
                   "error": "server.exe/client.exe missing",
                   "server_exe": str(server_exe), "client_exe": str(client_exe),
                   "source_fingerprint_before": source_fingerprint_before,
                   "source_entry_count": source_entry_count}
        (run_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2, summary

    tcp_port, web_port = _ports()
    desktop = f"MoyuTrial-{os.getpid()}-{uuid.uuid4().hex[:10]}"
    probe = private_desktop_probe()
    if os.name == "nt" and not probe.get("available"):
        summary = {"schema_version": "REL-01.v1.run", "run_id": run_dir.name,
                   "source": str(source), "exit_code": 3,
                   "error": "private desktop unavailable",
                   "private_desktop_probe": probe}
        (run_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return 3, summary

    server_env = _clean_env(profile=profiles["server"], flags=TRIAL_FLAGS,
                             ports=(tcp_port, web_port))
    client_env = _clean_env(profile=profiles["client"], flags=TRIAL_FLAGS,
                             ports=(tcp_port, web_port))
    profile_before = {role: _owned_inventory(path)
                      for role, path in profiles.items()}
    server_cmd = [str(server_exe)]
    client_cmd = [str(client_exe), "--host", "127.0.0.1", "--port",
                  str(tcp_port), "--nick", "REL_trial_client"]
    server_proc = client_proc = None
    result = {
        "schema_version": "REL-01.v1.run", "run_id": run_dir.name,
        "source": str(source), "desktop": desktop,
        "session_id": None, "ports": {"tcp": tcp_port, "web": web_port},
        "flags": {key: value for key, value in TRIAL_FLAGS.items()},
        "private_desktop_probe": probe, "processes": {}, "probes": {},
        "cleanup_ok": False, "logs": {key: str(value) for key, value in logs.items()},
        "source_fingerprint_before": source_fingerprint_before,
        "source_fingerprint_scope": "approved source manifest; not a whole-system IO trace",
        "source_entry_count": source_entry_count,
        "profiles": {role: {"root": str(path), "inventory_before": profile_before[role]}
                     for role, path in profiles.items()},
    }
    code = 1
    try:
        server_proc = launch_process(server_cmd, cwd=str(source), env=server_env,
                                     log_path=logs["server"], desktop_name=desktop)
        result["processes"]["server"] = _process_record(
            server_proc, desktop=desktop, command=server_cmd,
            expected_exe=server_exe)
        result["session_id"] = server_proc.session_id
        ready = _wait_tcp(tcp_port)
        result["probes"]["tcp_listen"] = {"ok": ready}
        if ready:
            result["probes"]["web"] = _web_probe(web_port)
        client_proc = launch_process(client_cmd, cwd=str(source), env=client_env,
                                     log_path=logs["client"], desktop_name=desktop)
        result["processes"]["client"] = _process_record(
            client_proc, desktop=desktop, command=client_cmd,
            expected_exe=client_exe)
        result["client_started"] = client_proc.poll() is None
        result["probes"]["login"] = _wait_login_audit(
            profiles["server"], "REL_trial_client") if ready else {
                "ok": False, "source": "client.exe", "error_type": "server_not_ready"}
        # Allow client boot/login to write its crash log without interacting
        # with the private desktop.  A live process is the expected result.
        time.sleep(3.0)
        result["client_after_wait"] = _process_record(
            client_proc, desktop=desktop, command=client_cmd,
            expected_exe=client_exe)
        result["server_after_wait"] = _process_record(
            server_proc, desktop=desktop, command=server_cmd,
            expected_exe=server_exe)
        client_alive = result["client_after_wait"].get("state") == "running"
        server_alive = result["server_after_wait"].get("state") == "running"
        image_ok = (result["client_after_wait"].get("image_matches_expected") is True
                    and result["server_after_wait"].get("image_matches_expected") is True)
        code = 0 if (result["probes"].get("tcp_listen", {}).get("ok")
                     and result["probes"].get("login", {}).get("ok")
                     and result["probes"].get("web", {}).get("ok")
                     and result.get("client_started")
                     and client_alive and server_alive and image_ok) else 1
    except Exception as exc:
        result["error"] = {"type": type(exc).__name__}
        code = 1
    finally:
        cleanup = {}
        for role, proc in (("client", client_proc), ("server", server_proc)):
            if proc is None:
                cleanup[role] = {"attempted": False, "ok": True}
                continue
            try:
                ok = bool(proc.terminate_tree())
            except Exception as exc:
                ok = False
                cleanup[role] = {"attempted": True, "ok": False,
                                 "error_type": type(exc).__name__}
            else:
                cleanup[role] = {"attempted": True, "ok": ok,
                                 "state": process_state(proc.pid)}
            try:
                proc.close()
            except Exception:
                pass
        result["cleanup"] = cleanup
        result["cleanup_ok"] = all(item.get("ok") for item in cleanup.values())
        try:
            for role, path in profiles.items():
                result["profiles"][role]["inventory_after"] = _owned_inventory(path)
            source_fingerprint_after, source_after_count = _source_fingerprint(source)
            result["source_fingerprint_after"] = source_fingerprint_after
            result["source_entry_count_after"] = source_after_count
            result["source_unchanged"] = (
                source_fingerprint_after == source_fingerprint_before
                and source_after_count == source_entry_count)
            result["profile_paths_scoped"] = True
        except Exception as exc:
            result["profile_inventory_error"] = {"type": type(exc).__name__}
            result["profile_paths_scoped"] = False
            result["source_unchanged"] = False
        if not result["cleanup_ok"]:
            code = 4
        if not result.get("source_unchanged") or not result.get("profile_paths_scoped"):
            code = 5
        result["exit_code"] = code
        (run_dir / "summary.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return code, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="REL-01 local trial harness")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("probe", help="probe private desktop capability only")

    build = sub.add_parser("build", help="copy source and build both EXEs")
    build.add_argument("--source-dir", type=Path, default=ROOT)
    build.add_argument("--output-root", type=Path, default=DEFAULT_RUN_ROOT)

    run = sub.add_parser("run", help="run built EXEs on a private desktop")
    run.add_argument("--source-dir", type=Path, default=ROOT)
    run.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    run.add_argument("--server-exe", type=Path, default=None)
    run.add_argument("--client-exe", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.command == "probe":
        result = private_desktop_probe()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if (os.name != "nt" or result.get("available")) else 3
    if args.command == "build":
        code, _source, summary = build_candidate(
            args.source_dir.resolve(), args.output_root.resolve())
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return code
    code, summary = run_candidate(
        args.source_dir.resolve(), args.run_root.resolve(),
        server_exe=args.server_exe, client_exe=args.client_exe)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
