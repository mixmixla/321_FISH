# -*- coding: utf-8 -*-
"""VB-01：可恢复的隔离逐文件 pytest 门禁。

入口只编排测试，不导入项目业务模块。每个 ``tests/test_*.py`` 在新的
pytest 进程中执行，运行目录、源码副本、配置 profile、basetemp 与日志都
绑定到本次唯一 run。失败项保留原日志；``--resume`` 只重跑上次未结束的项。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid

from test_sandbox import (
    launch_process, private_desktop_probe, process_image_path, process_state,
    process_session_id,
)


SCHEMA_VERSION = "VB-01.v1"
ROOT = Path(__file__).resolve().parent
RUNS_ROOT = ROOT / "_tmp_gui" / "test-gate"
TERMINAL_STATUSES = {
    "passed", "failed", "collection", "empty", "crash", "timeout",
    "error", "infrastructure_error",
}
SENSITIVE_NAME_RE = re.compile(
    r"(?:PASSWORD|PASSWD|TOKEN|SECRET|PRIVATE|CREDENTIAL|API[_-]?KEY|"
    r"ACCESS[_-]?KEY|MODEL|MCP|OPENAI|ANTHROPIC|AZURE|AWS|GITHUB)", re.I
)
EXCLUDED_PARTS = {
    ".git", ".venv", "__pycache__", ".pytest_cache", "_tmp_gui",
    "history", "audit", "server_state", "web_tls", "models", "web_files",
    "downloads",
}
EXCLUDED_NAMES = {"prefs.json", "crash.log", "crash.log.1"}
ALLOWED_ENV_KEYS = {
    "ALLUSERSPROFILE", "APPDATA", "COMSPEC", "COMMONPROGRAMFILES",
    "COMMONPROGRAMFILES(X86)", "COMMONPROGRAMW6432", "HOMEDRIVE",
    "HOMEPATH", "LOCALAPPDATA", "NUMBER_OF_PROCESSORS", "OS", "PATH",
    "PATHEXT", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER",
    "PROCESSOR_LEVEL", "PROCESSOR_REVISION", "PROGRAMDATA", "PROGRAMFILES",
    "PROGRAMFILES(X86)", "PROGRAMW6432", "PSMODULEPATH", "PUBLIC",
    "SYSTEMDRIVE", "SYSTEMROOT", "TEMP", "TMP", "USERDOMAIN",
    "USERNAME", "VIRTUAL_ENV", "WINDIR", "LANG", "LANGUAGE", "LC_ALL",
    "LC_CTYPE", "TZ",
}
VOLATILE_ENV_KEYS = {
    "PYTHONPATH", "PYTHONIOENCODING", "PYTHONUTF8", "PYTHONUNBUFFERED",
    "MOYU_GATE_RUN_ID", "MOYU_GATE_SANDBOX", "MOYU_GATE_SANDBOX_REPORT",
    "MOYU_GATE_SOURCE_ROOT", "MOYU_GATE_DESKTOP_NAME", "MOYU_GATE_PROFILE",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(value) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(data)


def _atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    os.replace(temp, path)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _is_reparse_point(path: Path) -> bool:
    """Reject symlinks and Windows junctions instead of copying through them."""
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction is not None and is_junction():
            return True
        # FILE_ATTRIBUTE_REPARSE_POINT; this catches junctions on Python
        # versions where Path.is_junction is unavailable.
        if os.name == "nt":
            attrs = getattr(path.stat(), "st_file_attributes", 0)
            return bool(attrs & 0x400)
    except OSError:
        return True
    return False


def _safe_source_path(path: Path, root: Path) -> bool:
    """Reject a symlink/junction anywhere between root and the input file."""
    try:
        current = path
        root_abs = root.absolute()
        while True:
            if _is_reparse_point(current):
                return False
            if current.absolute() == root_abs:
                return True
            parent = current.parent
            if parent == current:
                return False
            current = parent
    except OSError:
        return False


def _no_reparse_ancestors(path: Path) -> bool:
    """Check existing output path components without following a link first."""
    try:
        current = path
        while True:
            if os.path.lexists(current) and _is_reparse_point(current):
                return False
            parent = current.parent
            if parent == current:
                return True
            current = parent
    except OSError:
        return False


def _validate_run_layout(run_dir: Path, manifest: dict | None = None,
                         progress: dict | None = None) -> None:
    run_dir = run_dir.expanduser().absolute()
    if not _no_reparse_ancestors(run_dir):
        raise ValueError(f"run 输出路径含 symlink/junction: {run_dir}")
    if manifest is None:
        return
    for key in ("source_snapshot", "profile_root"):
        value = manifest.get(key)
        if not value:
            raise ValueError(f"run manifest 缺少 {key}")
        path = Path(value).expanduser()
        if not _inside(path, run_dir) or not _no_reparse_ancestors(path):
            raise ValueError(f"run manifest {key} 越出 run 或含 reparse: {path}")
    for record in (progress or {}).get("results", []):
        for key in ("log", "sandbox_report", "basetemp", "source_cwd", "profile"):
            value = record.get(key)
            if value is None:
                continue
            path = Path(value)
            if path.is_absolute() or not _inside(run_dir / path, run_dir):
                raise ValueError(f"run 证据路径越界: {value}")
            if not _no_reparse_ancestors(run_dir / path):
                raise ValueError(f"run 证据路径含 reparse: {value}")
        for attempt in record.get("attempts", []):
            for key in ("log", "sandbox_report", "basetemp", "source_cwd", "profile"):
                value = attempt.get(key)
                if value is None:
                    continue
                path = Path(value)
                if path.is_absolute() or not _inside(run_dir / path, run_dir):
                    raise ValueError(f"run 证据路径越界: {value}")
                if not _no_reparse_ancestors(run_dir / path):
                    raise ValueError(f"run 证据路径含 reparse: {value}")


def _safe_run_artifact(path: Path, run_dir: Path) -> bool:
    return (_inside(path, run_dir) and _no_reparse_ancestors(path)
            and (not path.exists() or not _is_reparse_point(path)))


def _allowed_relative(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    if parts & {x.lower() for x in EXCLUDED_PARTS}:
        return False
    if path.name.lower() in {x.lower() for x in EXCLUDED_NAMES}:
        return False
    # Snapshot only executable project inputs and static assets. Governance
    # Markdown, old review logs and local notes cannot affect pytest behavior
    # and must not make an otherwise identical resume stale.
    lowered = [part.lower() for part in path.parts]
    top = lowered[0] if lowered else ""
    if top == "tests":
        return path.suffix.lower() == ".py"
    if top in {"games_pkg", "widgets", "assets"}:
        return True
    if len(lowered) != 1:
        return False
    if path.name.lower() in {".python-version", "dev.ps1", "trial_start.ps1", "app.ico"}:
        return True
    return path.suffix.lower() in {".py", ".pyw", ".spec", ".txt", ".json", ".toml", ".ini"}


def _git_tracked_files(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "-z"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    files = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            rel = Path(raw.decode("utf-8"))
        except UnicodeDecodeError:
            continue
        if rel.is_absolute() or not _allowed_relative(rel):
            continue
        path = root / rel
        if (path.is_file() and _safe_source_path(path, root)
                and _inside(path, root)):
            files.append(path)
    return files


def _source_files(root: Path) -> list[Path]:
    """Return tracked source/static files plus current test inputs.

    Newly created test files are included even before a commit so the runner
    validates the exact working-tree candidate. Runtime directories and files
    remain excluded regardless of Git state.
    """
    found = {p.resolve() for p in _git_tracked_files(root)}
    mandatory = [
        root / "test_gate.py", root / "test_sandbox.py", root / "tests" / "conftest.py",
    ]
    mandatory.extend(root.glob("*.py"))
    tests_dir = root / "tests"
    if tests_dir.is_dir():
        mandatory.extend(tests_dir.glob("test_*.py"))
    # Include newly added, not-yet-tracked Python modules in the two project
    # packages used by the application.  Their bytes belong in the candidate
    # fingerprint just like tracked files.
    for package in ("games_pkg", "widgets"):
        package_dir = root / package
        if package_dir.is_dir():
            mandatory.extend(package_dir.rglob("*.py"))
    assets = root / "assets"
    if assets.is_dir():
        mandatory.extend(p for p in assets.rglob("*") if p.is_file())
    # A non-Git synthetic source used by runner tests still needs its .py
    # modules and static assets; do not recursively copy ignored runtime data.
    if not found:
        for pattern in ("*.py", "*.ps1", "*.txt", "*.ini", "*.toml", "*.spec"):
            mandatory.extend(root.glob(pattern))
    for path in mandatory:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if (not resolved.is_file() or not _safe_source_path(path, root)
                or not _inside(resolved, root)):
            continue
        try:
            rel = resolved.relative_to(root.resolve())
        except ValueError:
            continue
        if _allowed_relative(rel):
            found.add(resolved)
    return sorted(found, key=lambda p: p.relative_to(root.resolve()).as_posix().lower())


def source_manifest(root: Path) -> tuple[list[dict], str]:
    root = root.resolve()
    entries = []
    for path in _source_files(root):
        rel = path.relative_to(root).as_posix()
        entries.append({"path": rel, "size": path.stat().st_size,
                        "sha256": _sha256_file(path)})
    return entries, _stable_id(entries)


def dependency_manifest(root: Path) -> tuple[list[dict], str]:
    root = root.resolve()
    names = [".python-version", "requirements.txt", "requirements-dev.txt", "dev.ps1"]
    entries = []
    for name in names:
        path = root / name
        if path.is_file():
            entries.append({"path": name, "size": path.stat().st_size,
                            "sha256": _sha256_file(path)})
    return entries, _stable_id(entries)


def _test_manifest(root: Path, paths: list[Path]) -> list[dict]:
    out = []
    root = root.resolve()
    for path in paths:
        if not _safe_source_path(path, root):
            raise ValueError(f"测试文件不能是 symlink/junction: {path}")
        path = path.resolve()
        rel = path.relative_to(root).as_posix()
        out.append({"path": rel, "size": path.stat().st_size,
                    "sha256": _sha256_file(path)})
    return out


def discover_test_files(root: Path, explicit: list[str] | None = None) -> list[Path]:
    root = root.resolve()
    if not explicit:
        tests_dir = root / "tests"
        if tests_dir.exists() and not _safe_source_path(tests_dir, root):
            raise ValueError(f"测试目录含 symlink/junction: {tests_dir}")
        candidates = list(tests_dir.glob("test_*.py"))
        unsafe = [path for path in candidates if not _safe_source_path(path, root)]
        if unsafe:
            raise ValueError(f"测试目录含 symlink/junction: {unsafe[0]}")
        return sorted((path for path in candidates if path.is_file()),
                      key=lambda p: p.name.lower())
    paths = []
    for item in explicit:
        raw = Path(item)
        path = raw if raw.is_absolute() else root / raw
        if path.is_dir():
            if not _safe_source_path(path, root):
                raise ValueError(f"测试目录不能是 symlink/junction: {item}")
            paths.extend(path.glob("test_*.py"))
        elif path.is_file():
            paths.append(path)
        else:
            raise ValueError(f"测试文件不存在: {item}")
    unique = {}
    for path in paths:
        original_path = path
        path = path.resolve()
        if not _safe_source_path(original_path, root):
            raise ValueError(f"测试文件不能是 symlink/junction: {item}")
        if not _inside(path, root):
            raise ValueError(f"测试文件必须位于 source-dir 内: {path}")
        if not path.is_file():
            raise ValueError(f"不是测试文件: {path}")
        unique[path.as_posix()] = path
    return sorted(unique.values(), key=lambda p: p.relative_to(root).as_posix().lower())


def _interpreter_info() -> dict:
    executable = Path(sys.executable).resolve()
    info = {
        "path": str(executable),
        "implementation": sys.implementation.name,
        "version": platform.python_version(),
        "cache_tag": getattr(sys.implementation, "cache_tag", None),
    }
    try:
        info.update({"size": executable.stat().st_size,
                     "sha256": _sha256_file(executable)})
    except OSError:
        info.update({"size": None, "sha256": None})
    return info


def _base_environment(profile: Path, source: Path, run_id: str,
                      report_path: Path, desktop_name: str | None) -> tuple[dict, dict]:
    profile = profile.resolve()
    for child in ("Temp", "AppData/Roaming", "AppData/Local"):
        (profile / child).mkdir(parents=True, exist_ok=True)
    env = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if upper in ALLOWED_ENV_KEYS and not SENSITIVE_NAME_RE.search(upper):
            env[key] = value
    env.update({
        "PYTHONPATH": str(source),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONUNBUFFERED": "1",
        "MOYU_GATE_RUN_ID": run_id,
        "MOYU_GATE_SANDBOX": "1",
        "MOYU_GATE_SANDBOX_REPORT": str(report_path.resolve()),
        "MOYU_GATE_SOURCE_ROOT": str(source.resolve()),
        "MOYU_GATE_PROFILE": str(profile),
        "USERPROFILE": str(profile),
        "HOME": str(profile),
        "APPDATA": str(profile / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(profile / "AppData" / "Local"),
        "TEMP": str(profile / "Temp"),
        "TMP": str(profile / "Temp"),
    })
    if desktop_name:
        env["MOYU_GATE_DESKTOP_NAME"] = desktop_name
    # Explicitly remove deployment/model/Agent variables even if a platform
    # uses unusual casing for them.
    for key in list(env):
        if key.upper() in {
            "MOYU_ADMIN_PASSWORD", "MOYU_WEB_PASSWORD", "MOYU_ADMIN_NICK",
            "VOSK_MODEL", "VOSK_MODEL_DIR", "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY", "MCP_SERVER", "AGENT_ROOT",
        } or SENSITIVE_NAME_RE.search(key):
            env.pop(key, None)
    identity = {k: v for k, v in env.items() if k.upper() not in VOLATILE_ENV_KEYS
                and k.upper() not in {"USERPROFILE", "HOME", "APPDATA",
                                      "LOCALAPPDATA", "TEMP", "TMP"}}
    policy = {
        "allowed_inherited_keys": sorted(k for k in env if k in os.environ),
        "cleared_inherited_keys": sorted(k for k in os.environ if k not in env),
        "identity_fingerprint": _stable_id(identity),
        "profile_root": str(profile),
        "cwd_root": str(source.resolve()),
        "network": "loopback_only",
        "agent": "blocked",
        "hardware": "blocked",
        "desktop": desktop_name,
    }
    return env, policy


def _gui_hint(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    return bool(re.search(
        r"(?im)^\s*(?:from\s+tkinter\b|import\s+tkinter\b|"
        r".*importorskip\(\s*['\"]tkinter|.*__import__\(\s*['\"]tkinter|"
        r"pytest\.mark\.visual\b|.*\.mainloop\s*\()", text))


def _run_identity(source_root: Path, test_paths: list[Path], pytest_args: list[str],
                 timeout: float, run_visual: bool, run_hardware: bool) -> dict:
    sources, source_id = source_manifest(source_root)
    deps, deps_id = dependency_manifest(source_root)
    tests = _test_manifest(source_root, test_paths)
    gui_required = any(_gui_hint(path) for path in test_paths)
    desktop = private_desktop_probe() if gui_required else {
        "available": True, "required": False,
    }
    # The probe's random desktop name is per-run, while availability and
    # Windows session are the resume-relevant desktop identity.
    desktop.pop("name", None)
    desktop["required"] = gui_required
    desktop["session_id"] = process_session_id(os.getpid())
    return {
        "schema_version": SCHEMA_VERSION,
        "source_origin": str(source_root.resolve()),
        "source_files": sources,
        "source_content_id": source_id,
        "dependencies": deps,
        "dependency_content_id": deps_id,
        "tests": tests,
        "tests_content_id": _stable_id(tests),
        "pytest_args": list(pytest_args),
        "timeout_seconds": float(timeout),
        "run_visual": bool(run_visual),
        "run_hardware": bool(run_hardware),
        "interpreter": _interpreter_info(),
        "runner_tool_sha256": _sha256_file(Path(__file__).resolve()),
        "sandbox_tool_sha256": _sha256_file(
            Path(__file__).resolve().with_name("test_sandbox.py")),
        "desktop": desktop,
        "command_template": [
            "{interpreter}", "-m", "pytest", "-q", "-rs", "-p", "test_sandbox",
            "{test_file}", "--basetemp", "{basetemp}",
            "-o", "faulthandler_timeout=60",
            "{capture_mode}",
            *pytest_args,
        ],
    }


def _immutable_identity(manifest: dict) -> dict:
    keys = (
        "schema_version", "source_origin", "source_content_id",
        "dependency_content_id", "tests", "tests_content_id", "pytest_args",
        "timeout_seconds", "run_visual", "run_hardware", "interpreter",
        "runner_tool_sha256", "sandbox_tool_sha256", "desktop", "command_template",
    )
    return {key: manifest.get(key) for key in keys}


def _fingerprint(manifest: dict, env_policy: dict | None = None) -> str:
    value = _immutable_identity(manifest)
    if env_policy is not None:
        value["environment_identity_fingerprint"] = env_policy.get("identity_fingerprint")
    return _stable_id(value)


def _copy_snapshot(source_root: Path, destination: Path,
                   entries: list[dict]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        src = source_root / Path(entry["path"])
        dst = destination / Path(entry["path"])
        if not src.is_file() or not _safe_source_path(src, source_root):
            raise RuntimeError(f"源码在快照期间消失: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def _new_run_dir(label: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", label).strip(".-") or "default"
    if not _no_reparse_ancestors(RUNS_ROOT):
        raise ValueError(f"默认 run 根目录含 symlink/junction: {RUNS_ROOT}")
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    return RUNS_ROOT / f"{safe}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:10]}"


def _resolve_resume_dir(value: str | None, explicit: Path | None, label: str) -> Path:
    if value:
        return _checked_run_path(Path(value))
    if explicit:
        return _checked_run_path(explicit)
    candidates = []
    _checked_run_path(RUNS_ROOT)
    if RUNS_ROOT.is_dir():
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", label).strip(".-") or "default"
        candidates = sorted(RUNS_ROOT.glob(f"{safe}-*"), key=lambda p: p.stat().st_mtime,
                           reverse=True)
    if not candidates:
        raise ValueError("没有可恢复的门禁 run；请先运行一次或传 --resume <run-dir>")
    return _checked_run_path(candidates[0])


def _checked_run_path(path: Path) -> Path:
    # Resolve only after checking the original path; resolving first erases
    # junction/symlink evidence. Also protect the first resume manifest read.
    raw = path.expanduser().absolute()
    _validate_run_layout(raw)
    for name in ("manifest.json", "progress.json"):
        if not _no_reparse_ancestors(raw / name):
            raise ValueError(f"run 元数据含 symlink/junction: {raw / name}")
    return raw.resolve()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_progress(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "results": []}
    value = _load_json(path)
    if isinstance(value, list):  # no old formal format is trusted; retain readability
        return {"schema_version": SCHEMA_VERSION, "results": value}
    if not isinstance(value, dict) or not isinstance(value.get("results", []), list):
        raise ValueError("progress.json 格式无效")
    return value


def _write_progress(path: Path, progress: dict) -> None:
    progress["updated_at"] = _now()
    _atomic_json(path, progress)


def _record_for(progress: dict, name: str) -> dict | None:
    for record in progress.get("results", []):
        if record.get("file") == name:
            return record
    return None


def _new_record(progress: dict, name: str) -> dict:
    record = _record_for(progress, name)
    if record is None:
        record = {"file": name, "status": "pending", "attempts": []}
        progress.setdefault("results", []).append(record)
    return record


def _summary_line(output: str) -> tuple[str, dict]:
    lines = output.splitlines()
    summary = next((line.strip() for line in reversed(lines)
                    if re.search(r"\d+ (?:passed|failed|skipped|errors?|xfailed|xpassed)", line)),
                   "no pytest summary")
    counts = {}
    for number, kind in re.findall(
            r"(\d+) (passed|failed|skipped|error|errors|xfailed|xpassed)", summary):
        key = "errors" if kind == "error" else kind
        counts[key] = counts.get(key, 0) + int(number)
    return summary, counts


def _classify_exit(code: int | None, timed_out: bool, output: str) -> str:
    if timed_out:
        return "timeout"
    if code is None:
        return "crash"
    if code == 0:
        summary, _ = _summary_line(output)
        if summary == "no pytest summary":
            return "infrastructure_error"
        return "passed"
    if code == 5:
        return "empty"
    if code == 2:
        return "collection"
    if code < 0 or code in {
        3221225477, 3221225781, 3221226505, 2147483651, 2147483647,
    }:
        return "crash"
    if code == 1:
        return "failed"
    return "error"


def _append_log_marker(log_path: Path, text: str) -> None:
    with log_path.open("a", encoding="utf-8", errors="replace") as fh:
        fh.write("\n" + text.rstrip() + "\n")


def _unexpected_skips(output: str, counts: dict, *, run_visual=False,
                      run_hardware=False) -> list[str]:
    """Require an exact -rs reason for every skip; counts alone aren't proof."""
    expected = int(counts.get("skipped", 0))
    if not expected:
        return []
    allowed = set()
    if not run_visual:
        allowed.add("需显式启用 --run-visual")
    if not run_hardware:
        allowed.add("需显式启用 --run-hardware")
    found, unexpected = 0, []
    # Collection-time marker skips have no line number; setup skips do.
    for number, reason in re.findall(r"^SKIPPED \[(\d+)\] .*?: (.*)$", output, re.MULTILINE):
        found += int(number)
        if reason.strip() not in allowed:
            unexpected.append(reason.strip())
    if found != expected:
        unexpected.append(f"skip reason count mismatch: {found} != {expected}")
    return unexpected


def _terminal_record_complete(record: dict, run_dir: Path) -> bool:
    if record.get("status") not in TERMINAL_STATUSES:
        return False
    attempt = record.get("attempts", [])[-1] if record.get("attempts") else record
    log = attempt.get("log") or record.get("log")
    if not log or not (run_dir / log).is_file():
        return False
    if not attempt.get("ended_at") and not record.get("ended_at"):
        return False
    if attempt.get("exit_code", record.get("exit_code")) is None:
        return False
    expected = attempt.get("log_sha256") or record.get("log_sha256")
    return bool(expected and _sha256_file(run_dir / log) == expected)


def _read_sandbox_report(path: Path) -> dict | None:
    try:
        value = _load_json(path)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _valid_sandbox_report(report: dict | None, attempt: dict) -> bool:
    if not isinstance(report, dict):
        return False
    if report.get("schema_version") != SCHEMA_VERSION or report.get("installed") is not True:
        return False
    policy = report.get("policy")
    if not isinstance(policy, dict) or policy.get("network") != "loopback_only":
        return False
    if policy.get("agent") != "blocked" or policy.get("hardware") != "blocked":
        return False
    if policy.get("wildcard_bind") != "remap_to_loopback":
        return False
    if policy.get("broadcast_sendto") != "remap_to_loopback_and_record":
        return False
    if report.get("desktop") != attempt.get("desktop"):
        return False
    if not isinstance(report.get("blocked_events"), int):
        return False
    if not isinstance(report.get("remapped_events"), int):
        return False
    return isinstance(report.get("events"), list)


def _execute_one(*, record: dict, test_entry: dict, run_dir: Path,
                 source_snapshot: Path, timeout: float, run_visual: bool,
                 run_hardware: bool, pytest_args: list[str], index: int,
                 total: int) -> None:
    name = test_entry["path"]
    attempt_number = len(record.setdefault("attempts", [])) + 1
    log_rel = Path("logs") / (Path(name).stem + f".attempt{attempt_number}.log")
    report_rel = Path("sandbox") / (Path(name).stem + f".attempt{attempt_number}.json")
    log_path = run_dir / log_rel
    report_path = run_dir / report_rel
    base_temp = run_dir / "basetemp" / (Path(name).stem + f"-{attempt_number}-{uuid.uuid4().hex[:8]}")
    base_temp.mkdir(parents=True, exist_ok=True)
    case_rel = Path("cases") / (Path(name).stem + f"-{attempt_number}-{uuid.uuid4().hex[:8]}")
    case_source = run_dir / case_rel
    # Each file gets a pristine source copy. config._log_dir() and prefs.py
    # resolve beside __file__, so sharing one cwd would leak runtime state
    # from an earlier test file into the next process.
    shutil.copytree(source_snapshot, case_source)
    profile_rel = Path("profiles") / (Path(name).stem + f"-{attempt_number}-{uuid.uuid4().hex[:8]}")
    case_profile = run_dir / profile_rel
    gui = _gui_hint(case_source / Path(name))
    desktop_name = f"MoyuGate-{os.getpid()}-{uuid.uuid4().hex[:10]}" if gui and os.name == "nt" else None
    env, _ = _base_environment(case_profile, case_source, run_dir.name,
                               report_path, desktop_name)
    command = [
        sys.executable, "-m", "pytest", "-q", "-rs", "-p", "test_sandbox",
        name, "--basetemp", str(base_temp), "-o", "faulthandler_timeout=60",
        # Native Tk can retain C runtime handles across fixture roots. Keep
        # pytest from swapping those handles; the parent log still receives
        # native stdout/stderr, and explicit capfd fixtures keep their behavior.
        "--capture=sys" if gui else "--capture=fd",
    ]
    if run_visual:
        command.append("--run-visual")
    if run_hardware:
        command.append("--run-hardware")
    command.extend(pytest_args)
    started = time.monotonic()
    attempt = {
        "attempt": attempt_number,
        "status": "running",
        "started_at": _now(),
        "pid": None,
        "session_id": None,
        "log": log_rel.as_posix(),
        "sandbox_report": report_rel.as_posix(),
        "basetemp": base_temp.relative_to(run_dir).as_posix(),
        "source_cwd": case_rel.as_posix(),
        "profile": profile_rel.as_posix(),
        "command": command,
        "gui": gui,
        "desktop": desktop_name,
    }
    record["attempts"].append(attempt)
    record["status"] = "running"
    record["file"] = name
    # Persist before starting the child.  If the parent is terminated at any
    # point after this write, the next --resume can keep the interrupted
    # evidence.  A live PID is never killed unless the current process still
    # owns its handle; stale resume refuses when ownership is not provable.
    _write_progress(run_dir / "progress.json", _CURRENT_PROGRESS)

    process = None
    output = ""
    timed_out = False
    cleanup_ok = True
    spawn_error = None
    artifact_error = False
    try:
        process = launch_process(command, cwd=str(case_source), env=env,
                                 log_path=log_path, desktop_name=desktop_name)
        attempt["pid"] = process.pid
        attempt["session_id"] = getattr(process, "session_id", None)
        _write_progress(run_dir / "progress.json", _CURRENT_PROGRESS)
        try:
            process.wait(timeout=max(0.1, timeout))
        except (TimeoutError, subprocess.TimeoutExpired):
            timed_out = True
            cleanup_ok = bool(process.terminate_tree())
            try:
                process.wait(timeout=10)
            except Exception:
                pass
            if _safe_run_artifact(log_path, run_dir):
                _append_log_marker(log_path, f"VB-01 timeout after {timeout:.2f}s; cleanup verified={cleanup_ok}")
                if not cleanup_ok:
                    _append_log_marker(log_path, "VB-01 process-tree cleanup could not be verified")
            else:
                artifact_error = True
        code = 124 if timed_out else process.poll()
    except Exception as exc:
        if process is not None:
            try:
                cleanup_ok = bool(process.terminate_tree())
            except Exception:
                cleanup_ok = False
        spawn_error = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        if _safe_run_artifact(log_path, run_dir):
            _append_log_marker(log_path, "VB-01 child launch error\n" + spawn_error)
        else:
            artifact_error = True
        code = None
    finally:
        if process is not None:
            try:
                process.close()
            except Exception:
                cleanup_ok = False
    if _safe_run_artifact(log_path, run_dir):
        try:
            output = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            output = ""
            artifact_error = True
    else:
        output = ""
        artifact_error = True
    if spawn_error:
        status = "infrastructure_error"
    else:
        status = _classify_exit(code, timed_out, output)
    summary, counts = _summary_line(output)
    unexpected_skips = _unexpected_skips(output, counts, run_visual=run_visual,
                                         run_hardware=run_hardware)
    if status == "passed" and unexpected_skips:
        status = "infrastructure_error"
        _append_log_marker(log_path, "VB-01 unexpected skip: " + "; ".join(unexpected_skips))
    sandbox_report = (_read_sandbox_report(report_path)
                      if _safe_run_artifact(report_path, run_dir) else None)
    if status == "passed" and (artifact_error
                                or not _valid_sandbox_report(sandbox_report, attempt)):
        status = "infrastructure_error"
        _append_log_marker(log_path, "VB-01 sandbox report missing or policy schema invalid")
    attempt.update({
        "status": status,
        "ended_at": _now(),
        "exit_code": code,
        "seconds": round(time.monotonic() - started, 3),
        "summary": summary,
        "counts": counts,
        "log_sha256": _sha256_file(log_path) if log_path.is_file() else None,
        "sandbox_report_present": sandbox_report is not None,
        "sandbox": sandbox_report,
        "artifact_error": artifact_error,
        "cleanup_ok": cleanup_ok,
        "unexpected_skips": unexpected_skips,
    })
    record.update({
        "status": status,
        "exit_code": code,
        "summary": summary,
        "counts": counts,
        "ended_at": attempt["ended_at"],
        "seconds": attempt["seconds"],
        "log": attempt["log"],
        "log_sha256": attempt["log_sha256"],
        "sandbox_report": attempt["sandbox_report"],
        "unexpected_skips": unexpected_skips,
    })
    _write_progress(run_dir / "progress.json", _CURRENT_PROGRESS)
    print(json.dumps({
        "event": "file", "index": index, "total": total, "file": name,
        "status": status, "exit_code": code, "seconds": attempt["seconds"],
        "summary": summary,
    }, ensure_ascii=False), flush=True)


_CURRENT_PROGRESS: dict = {}


def _mark_stale_attempts(progress: dict, run_dir: Path) -> bool:
    changed = False
    for record in progress.get("results", []):
        if record.get("status") != "running":
            continue
        attempt = record.get("attempts", [])[-1] if record.get("attempts") else record
        pid = attempt.get("pid")
        # A stale PID alone never authorizes killing a live process.  If the
        # recorded process is still present, resume fails closed and leaves it
        # untouched; only an already-exited PID may be marked interrupted and
        # retried.
        state = process_state(pid) if pid else "unknown"
        if state != "exited":
            attempt.update({
                "status": "infrastructure_error", "ended_at": _now(),
                "reason": f"recorded process is {state}; exit not provable; not terminated",
                "cleanup_ok": False,
            })
            record["status"] = "infrastructure_error"
            changed = True
            continue
        cleanup_ok = True
        attempt.update({"status": "interrupted", "ended_at": _now(),
                        "reason": "parent process ended before completion",
                        "cleanup_ok": cleanup_ok})
        record["status"] = "interrupted"
        changed = True
    if changed:
        _write_progress(run_dir / "progress.json", progress)
    return changed


def _make_new_run(args, source_root: Path, test_paths: list[Path]) -> tuple[Path, dict, dict]:
    run_dir = (_checked_run_path(args.run_dir) if args.run_dir
               else _new_run_dir(args.label))
    _validate_run_layout(run_dir)
    if run_dir.exists() and any(run_dir.iterdir()):
        raise ValueError(f"run 目录已存在且非空：{run_dir}；新运行必须使用唯一目录")
    run_dir.mkdir(parents=True, exist_ok=True)
    source_snapshot = run_dir / "source"
    profile = run_dir / "profile"
    identity = _run_identity(source_root, test_paths, args.pytest_args,
                             args.timeout, args.run_visual, args.run_hardware)
    _copy_snapshot(source_root, source_snapshot, identity["source_files"])
    # The gate tool is an execution dependency for synthetic sources, not
    # project runtime data. Include the current tool copy if absent.
    tool_path = Path(__file__).resolve().with_name("test_sandbox.py")
    tool_rel = Path("test_sandbox.py")
    if not (source_snapshot / tool_rel).is_file() and tool_path.is_file():
        shutil.copyfile(tool_path, source_snapshot / tool_rel)
    env, policy = _base_environment(profile, source_snapshot, run_dir.name,
                                    run_dir / "sandbox" / "placeholder.json", None)
    identity["environment"] = policy
    identity.update({"run_id": run_dir.name, "created_at": _now(),
                     "run_dir": str(run_dir),
                     "source_snapshot": str(source_snapshot),
                     "profile_root": str(profile)})
    identity["content_fingerprint"] = _fingerprint(identity, policy)
    manifest = dict(identity)
    manifest["sandbox_policy"] = {
        "source_copy": "git_tracked_plus_current_tests",
        "runtime_data_excluded": sorted(EXCLUDED_PARTS | EXCLUDED_NAMES),
        "network": "loopback_only",
        "agent": "blocked",
        "hardware": "blocked",
        "gui": "private_Windows_desktop_when_available",
    }
    _atomic_json(run_dir / "manifest.json", manifest)
    progress = {"schema_version": SCHEMA_VERSION, "run_id": run_dir.name,
                "fingerprint": manifest["content_fingerprint"],
                "results": [], "started_at": _now()}
    _write_progress(run_dir / "progress.json", progress)
    return run_dir, manifest, progress


def _resume_run(args, source_root: Path, test_paths: list[Path]) -> tuple[Path, dict, dict]:
    run_dir = _resolve_resume_dir(args.resume, args.run_dir, args.label)
    _validate_run_layout(run_dir)
    for name in ("manifest.json", "progress.json"):
        path = run_dir / name
        if _is_reparse_point(path):
            raise ValueError(f"resume 元数据含 symlink/junction: {path}")
    manifest = _load_json(run_dir / "manifest.json")
    progress = _load_progress(run_dir / "progress.json")
    _validate_run_layout(run_dir, manifest, progress)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("拒绝 resume：门禁版本不匹配")
    current = _run_identity(source_root, test_paths, args.pytest_args,
                            args.timeout, args.run_visual, args.run_hardware)
    prior = _immutable_identity(manifest)
    if _immutable_identity(current) != prior:
        raise ValueError("拒绝 resume：源码/测试/依赖/命令/解释器不匹配")
    if progress.get("fingerprint") != manifest.get("content_fingerprint"):
        raise ValueError("拒绝 resume：progress 与 manifest 指纹不匹配")
    summary_path = run_dir / "summary.json"
    summary_complete = False
    if summary_path.is_file() and not _is_reparse_point(summary_path):
        try:
            summary = _load_json(summary_path)
            summary_complete = (isinstance(summary, dict)
                                and summary.get("schema_version") == SCHEMA_VERSION
                                and summary.get("content_fingerprint")
                                == manifest.get("content_fingerprint"))
        except (OSError, ValueError, json.JSONDecodeError):
            summary_complete = False
    if not summary_complete:
        statuses = [record.get("status") for record in progress.get("results", [])]
        if statuses and len(statuses) == len(manifest.get("tests", [])) \
                and all(status in TERMINAL_STATUSES for status in statuses):
            raise ValueError("拒绝 resume：已结束 run 的 summary.json 缺失或无效")
    source_snapshot = Path(manifest.get("source_snapshot", run_dir / "source"))
    if not source_snapshot.is_dir():
        raise ValueError("拒绝 resume：源快照缺失")
    # A prior run's snapshot is authoritative only after the current source
    # content has matched its recorded ID above.
    _mark_stale_attempts(progress, run_dir)
    if any(record.get("status") == "infrastructure_error"
           for record in progress.get("results", [])):
        raise ValueError("拒绝 resume：旧进程退出无法确认（存活/缺PID/查询不确定），未执行 kill")
    return run_dir, manifest, progress


def _write_summary(run_dir: Path, manifest: dict, progress: dict,
                   started: float, final_code: int) -> dict:
    results = progress.get("results", [])
    totals = {}
    for record in results:
        for kind, number in (record.get("counts") or {}).items():
            totals[kind] = totals.get(kind, 0) + int(number)
    failures = [record for record in results
                if record.get("status") != "passed"]
    cleanup_failures = []
    for record in results:
        for attempt in record.get("attempts", []):
            if attempt.get("cleanup_ok") is False:
                cleanup_failures.append({"file": record.get("file"),
                                         "attempt": attempt.get("attempt")})
    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest.get("run_id"),
        "run_dir": str(run_dir),
        "source_origin": manifest.get("source_origin"),
        "source_snapshot": manifest.get("source_snapshot"),
        "source_content_id": manifest.get("source_content_id"),
        "tests_content_id": manifest.get("tests_content_id"),
        "dependency_content_id": manifest.get("dependency_content_id"),
        "content_fingerprint": manifest.get("content_fingerprint"),
        "interpreter": manifest.get("interpreter"),
        "runner_tool_sha256": manifest.get("runner_tool_sha256"),
        "sandbox_tool_sha256": manifest.get("sandbox_tool_sha256"),
        "desktop": manifest.get("desktop"),
        "command_template": manifest.get("command_template"),
        "environment": manifest.get("environment"),
        "sandbox_policy": manifest.get("sandbox_policy"),
        "files": len(results),
        "failures": failures,
        "cleanup_failures": cleanup_failures,
        "totals": totals,
        "seconds": round(time.monotonic() - started, 3),
        "exit_code": int(final_code),
        "started_at": progress.get("started_at"),
        "ended_at": _now(),
        "results": results,
    }
    _atomic_json(run_dir / "summary.json", report)
    return report


def _parse(argv: list[str] | None):
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description="VB-01 isolated per-file pytest gate")
    parser.add_argument("test_files", nargs="*", help="测试文件；省略则按 tests/test_*.py 排序")
    parser.add_argument("--label", default="default")
    parser.add_argument("--source-dir", type=Path, default=ROOT)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--resume", nargs="?", const="", default=None,
                        help="恢复最近 run，或传入已有 run 目录")
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--run-visual", action="store_true")
    parser.add_argument("--run-hardware", action="store_true")
    parser.add_argument("--max-files", type=int, default=None)
    args, pytest_args = parser.parse_known_args(raw_argv)
    if any(str(value).startswith("--basetemp") for value in pytest_args):
        parser.error("--basetemp 由逐文件门禁管理")
    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    args.pytest_args = [value for value in pytest_args if value != "--"]
    args._timeout_explicit = any(value == "--timeout" or value.startswith("--timeout=")
                                 for value in raw_argv)
    args._source_dir_explicit = any(value == "--source-dir" or value.startswith("--source-dir=")
                                    for value in raw_argv)
    args._visual_explicit = "--run-visual" in raw_argv
    args._hardware_explicit = "--run-hardware" in raw_argv
    args._pytest_args_explicit = bool(args.pytest_args)
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    source_root = args.source_dir.expanduser().resolve()
    if args.resume is not None and not args._source_dir_explicit:
        try:
            prior_dir = _resolve_resume_dir(args.resume, args.run_dir, args.label)
            prior_manifest = _load_json(prior_dir / "manifest.json")
            source_root = Path(prior_manifest["source_origin"]).expanduser().resolve()
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
            print(f"VB-01 refused: cannot resolve recorded source: {exc}", file=sys.stderr)
            return 2
    if not source_root.is_dir():
        print(f"VB-01 source-dir 不存在: {source_root}", file=sys.stderr)
        return 2
    try:
        test_paths = discover_test_files(source_root, args.test_files)
        if args.max_files is not None:
            test_paths = test_paths[:max(0, args.max_files)]
        if args.resume is None:
            run_dir, manifest, progress = _make_new_run(args, source_root, test_paths)
        else:
            # A resume with no positional files means "the same selection as
            # the recorded run", rather than rediscovering the whole suite.
            if not args.test_files:
                prior_dir = _resolve_resume_dir(args.resume, args.run_dir, args.label)
                prior_manifest = _load_json(prior_dir / "manifest.json")
                test_paths = [source_root / Path(entry["path"])
                              for entry in prior_manifest.get("tests", [])]
                # Resume defaults to the immutable command/options recorded
                # by the original run. Explicit overrides remain subject to
                # the normal fingerprint mismatch refusal.
                if not args._timeout_explicit:
                    args.timeout = float(prior_manifest.get("timeout_seconds", args.timeout))
                if not args._visual_explicit:
                    args.run_visual = bool(prior_manifest.get("run_visual", args.run_visual))
                if not args._hardware_explicit:
                    args.run_hardware = bool(prior_manifest.get("run_hardware", args.run_hardware))
                if not args._pytest_args_explicit:
                    args.pytest_args = list(prior_manifest.get("pytest_args", []))
            run_dir, manifest, progress = _resume_run(args, source_root, test_paths)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"VB-01 refused: {exc}", file=sys.stderr)
        return 2
    global _CURRENT_PROGRESS
    _CURRENT_PROGRESS = progress
    source_snapshot = Path(manifest["source_snapshot"])
    profile_root = Path(manifest["profile_root"])
    base_env, env_policy = _base_environment(
        profile_root, source_snapshot, manifest["run_id"],
        run_dir / "sandbox" / "placeholder.json", None,
    )
    # The environment policy is immutable for resume; do not include volatile
    # per-file profile/report paths in the identity comparison.
    if manifest.get("environment", {}).get("identity_fingerprint") != env_policy.get("identity_fingerprint"):
        print("VB-01 refused: environment configuration changed", file=sys.stderr)
        return 2
    started = time.monotonic()
    desktop = manifest.get("desktop") or {}
    if desktop.get("required") and not desktop.get("available"):
        print("VB-01 infrastructure failure: private Windows desktop unavailable",
              file=sys.stderr)
        _write_summary(run_dir, manifest, progress, started, 2)
        return 2
    _write_progress(run_dir / "progress.json", progress)
    total = len(manifest.get("tests", []))
    for index, entry in enumerate(manifest.get("tests", []), 1):
        name = entry["path"]
        record = _new_record(progress, name)
        if record.get("status") in TERMINAL_STATUSES:
            if not _terminal_record_complete(record, run_dir):
                print(f"VB-01 refused: terminal record/log incomplete: {name}",
                      file=sys.stderr)
                _write_summary(run_dir, manifest, progress, started, 2)
                return 2
            continue
        # interrupted records remain as history and are deliberately rerun.
        _execute_one(
            record=record, test_entry=entry, run_dir=run_dir,
            source_snapshot=source_snapshot,
            timeout=float(manifest["timeout_seconds"]),
            run_visual=bool(manifest.get("run_visual")),
            run_hardware=bool(manifest.get("run_hardware")),
            pytest_args=list(manifest.get("pytest_args", [])),
            index=index, total=total,
        )
        if any(attempt.get("cleanup_ok") is False
               for attempt in record.get("attempts", [])):
            # Never let a possibly surviving process overlap the next file.
            _write_progress(run_dir / "progress.json", progress)
            _write_summary(run_dir, manifest, progress, started, 2)
            print("VB-01 stopped: process cleanup could not be verified", file=sys.stderr)
            return 2
    failures = [record for record in progress.get("results", [])
                if record.get("status") != "passed"]
    cleanup_failed = any(
        attempt.get("cleanup_ok") is False
        for record in progress.get("results", [])
        for attempt in record.get("attempts", [])
    )
    if total == 0:
        final_code = 5
    else:
        final_code = 1 if (failures or cleanup_failed
                           or len(progress.get("results", [])) != total) else 0
    report = _write_summary(run_dir, manifest, progress, started, final_code)
    try:
        if not (run_dir / "summary.json").is_file():
            raise OSError("summary.json missing after write")
        _load_json(run_dir / "summary.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"VB-01 infrastructure failure: summary unavailable: {exc}",
              file=sys.stderr)
        return 2
    print("GATE " + json.dumps({
        "run_id": report["run_id"], "run_dir": report["run_dir"],
        "files": report["files"], "totals": report["totals"],
        "failures": [r.get("file") for r in report["failures"]],
        "exit_code": final_code, "seconds": report["seconds"],
        "source_content_id": report["source_content_id"],
        "content_fingerprint": report["content_fingerprint"],
    }, ensure_ascii=False), flush=True)
    return final_code


if __name__ == "__main__":
    raise SystemExit(main())
