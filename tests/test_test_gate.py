# -*- coding: utf-8 -*-
"""VB-01 runner contract tests use only synthetic source trees."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "test_gate.py"


def _source(tmp_path: Path, *, root_files: dict[str, str] | None = None,
            **files: str) -> Path:
    root = tmp_path / "candidate"
    tests = root / "tests"
    tests.mkdir(parents=True)
    for name, text in (root_files or {}).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for name, text in files.items():
        path = tests / name
        path.write_text(text, encoding="utf-8")
    return root


def _run(tmp_path: Path, source: Path, *names: str, timeout: float = 20,
         run_timeout: float | None = None):
    run_dir = tmp_path / "run"
    command = [sys.executable, str(GATE), "--source-dir", str(source),
               "--run-dir", str(run_dir), "--timeout", str(timeout)]
    command.extend(names)
    result = subprocess.run(command, cwd=ROOT, capture_output=True,
                            text=True, encoding="utf-8", errors="replace",
                            timeout=run_timeout or max(30, timeout + 15))
    summary = None
    if (run_dir / "summary.json").is_file():
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    return result, run_dir, summary


def test_gate_runs_each_file_and_keeps_profile_isolated(tmp_path):
    source = _source(
        tmp_path,
        **{"test_alpha.py": (
            "from pathlib import Path\n"
            "def test_alpha():\n"
            "    assert Path.home() == Path(__import__('os').environ['MOYU_GATE_PROFILE'])\n"
            "    assert Path.cwd() == Path(__import__('os').environ['MOYU_GATE_SOURCE_ROOT'])\n"
            "    Path('prefs.json').write_text('synthetic', encoding='utf-8')\n"
        ), "test_beta.py": "def test_beta():\n    assert True\n"},
    )
    result, run_dir, summary = _run(tmp_path, source, "tests/test_beta.py",
                                    "tests/test_alpha.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert [item["file"] for item in summary["results"]] == [
        "tests/test_alpha.py", "tests/test_beta.py"
    ]
    assert all(item["status"] == "passed" for item in summary["results"])
    assert summary["environment"]["network"] == "loopback_only"
    # The test may write synthetic runtime data, but only inside the copied
    # source.  The original candidate tree remains untouched.
    assert list((run_dir / "cases").rglob("prefs.json"))
    assert not (source / "prefs.json").exists()
    assert (run_dir / "summary.json").is_file()
    for item in summary["results"]:
        assert (run_dir / item["log"]).is_file()
        assert item["log_sha256"]


def test_gate_snapshots_untracked_root_and_package_python(tmp_path):
    source = _source(
        tmp_path,
        root_files={
            "helper.py": "VALUE = 7\n",
            "widgets/__init__.py": "\n",
            "widgets/new_module.py": "VALUE = 35\n",
        },
    )
    # Keyword syntax cannot express a dotted filename, so write this test
    # after creating the synthetic tree.
    test_path = source / "tests" / "test_imports.py"
    test_path.write_text(
        "from helper import VALUE as ROOT_VALUE\n"
        "from widgets.new_module import VALUE as PACKAGE_VALUE\n"
        "def test_imports():\n"
        "    assert ROOT_VALUE + PACKAGE_VALUE == 42\n",
        encoding="utf-8",
    )
    result, run_dir, summary = _run(tmp_path, source, "tests/test_imports.py")
    assert result.returncode == 0, result.stdout + result.stderr
    paths = {item["path"] for item in json.loads(
        (run_dir / "manifest.json").read_text(encoding="utf-8")
    )["source_files"]}
    assert {"helper.py", "widgets/new_module.py"}.issubset(paths)


def test_gate_keeps_ended_failure_and_resume_does_not_rerun(tmp_path):
    source = _source(tmp_path, **{
        "test_fail.py": "def test_fail():\n    assert False\n",
    })
    first, run_dir, summary = _run(tmp_path, source, "tests/test_fail.py")
    assert first.returncode == 1
    record = summary["results"][0]
    assert record["status"] == "failed"
    assert len(record["attempts"]) == 1
    log_hash = record["log_sha256"]
    resumed = subprocess.run(
        [sys.executable, str(GATE), "--resume", str(run_dir)], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30,
    )
    assert resumed.returncode == 1
    after = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert len(after["results"][0]["attempts"]) == 1
    assert after["results"][0]["log_sha256"] == log_hash


def test_gate_refuses_resume_when_candidate_changes(tmp_path):
    source = _source(tmp_path, **{
        "test_ok.py": "def test_ok():\n    assert True\n"
    })
    first, run_dir, _ = _run(tmp_path, source, "tests/test_ok.py")
    assert first.returncode == 0
    path = source / "tests" / "test_ok.py"
    path.write_text("def test_ok():\n    assert 1 == 2\n", encoding="utf-8")
    resumed = subprocess.run(
        [sys.executable, str(GATE), "--resume", str(run_dir)], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert resumed.returncode == 2
    assert "refused" in resumed.stderr.lower()


def test_gate_does_not_kill_a_live_unproven_stale_pid(tmp_path):
    import test_gate

    run_dir = tmp_path / "stale"
    run_dir.mkdir()
    progress = {
        "schema_version": test_gate.SCHEMA_VERSION,
        "results": [{
            "file": "tests/test_probe.py",
            "status": "running",
            "attempts": [{"attempt": 1, "status": "running",
                           "pid": os.getpid()}],
        }],
    }
    test_gate._atomic_json(run_dir / "progress.json", progress)
    assert test_gate._mark_stale_attempts(progress, run_dir)
    assert progress["results"][0]["status"] == "infrastructure_error"
    assert "not terminated" in progress["results"][0]["attempts"][0]["reason"]


def test_gate_preserves_timeout_and_collection_empty_statuses(tmp_path):
    source = _source(tmp_path, **{
        "test_timeout.py": "import time\ndef test_timeout():\n    time.sleep(10)\n",
        "test_broken.py": "def test_broken(:\n    pass\n",
        "test_empty.py": "# intentionally empty\n",
    })
    result, run_dir, summary = _run(
        tmp_path, source, "tests/test_timeout.py", "tests/test_broken.py",
        "tests/test_empty.py", timeout=3.0, run_timeout=40,
    )
    assert result.returncode == 1
    statuses = {item["file"]: item["status"] for item in summary["results"]}
    assert statuses["tests/test_timeout.py"] == "timeout"
    assert statuses["tests/test_broken.py"] == "collection"
    assert statuses["tests/test_empty.py"] == "empty"
    timeout_item = next(item for item in summary["results"]
                        if item["file"] == "tests/test_timeout.py")
    text = (run_dir / timeout_item["log"]).read_text(encoding="utf-8")
    assert "timeout" in text.lower()


def test_gate_loopback_and_agent_guard_are_reported(tmp_path):
    source = _source(tmp_path, **{
        "test_guard.py": (
            "import importlib\n"
            "import socket\n"
            "import pytest\n"
            "from test_sandbox import AgentBlocked, NetworkBlocked\n"
            "def test_guard():\n"
            "    with pytest.raises(NetworkBlocked):\n"
            "        socket.create_connection(('8.8.8.8', 80), timeout=0.1)\n"
            "    with pytest.raises(AgentBlocked):\n"
            "        importlib.import_module('04_mcp_im.adapter')\n"
        ),
    })
    result, _, summary = _run(tmp_path, source, "tests/test_guard.py")
    assert result.returncode == 0, result.stdout + result.stderr
    sandbox = summary["results"][0]["attempts"][0]["sandbox"]
    assert sandbox["policy"]["network"] == "loopback_only"
    assert sandbox["policy"]["agent"] == "blocked"
    assert sandbox["blocked_events"] >= 2


@pytest.mark.skipif(os.name != "nt", reason="VB-01 private desktop is Windows-only")
def test_gate_runs_tk_on_private_desktop(tmp_path):
    source = _source(tmp_path, **{
        "test_gui.py": (
            "import tkinter as tk\n"
            "import os\n"
            "def test_gui():\n"
            "    os.write(1, b'native-stdout-retained\\n')\n"
            "    os.write(2, b'native-stderr-retained\\n')\n"
            "    root = tk.Tk()\n"
            "    root.withdraw()\n"
            "    root.update()\n"
            "    root.destroy()\n"
        ),
    })
    result, run_dir, summary = _run(tmp_path, source, "tests/test_gui.py", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    attempt = summary["results"][0]["attempts"][0]
    assert attempt["gui"] is True
    assert attempt["desktop"]
    assert attempt["sandbox"]["desktop"] == attempt["desktop"]
    assert "--capture=sys" in attempt["command"]
    log = (run_dir / attempt["log"]).read_text(encoding="utf-8")
    assert "native-stdout-retained" in log and "native-stderr-retained" in log
