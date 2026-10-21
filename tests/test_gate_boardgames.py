"""Real child-gate imports/assets, tracked and working-tree package parity."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("tracked", [True, False], ids=["tracked", "untracked"])
@pytest.mark.parametrize("changed", ["boardgames/azul/desktop.py",
                                    "boardgames/azul/assets/nested/tile.png"],
                         ids=["module-change", "asset-change"])
def test_gate_copies_boardgames_and_refuses_changed_resume(tmp_path, tracked, changed):
    source = tmp_path / "candidate"
    files = {
        "helper.py": b"VALUE = 42\n",
        "boardgames/__init__.py": b"",
        "boardgames/azul/__init__.py": b"",
        "boardgames/azul/desktop.py": b"VALUE = 42\n",
        # Synthetic asset bytes: the child reads exact bytes, without image decoding.
        "boardgames/azul/assets/nested/tile.png": b"synthetic-tile-bytes",
        "boardgames/azul/assets/prefs.json": b"synthetic-private-prefs",
        "boardgames/azul/assets/history/private.py": b"synthetic-private-history",
        "boardgames/azul/web_tls/private.pem": b"synthetic-private-key",
        "boardgames/azul/__pycache__/private.py": b"synthetic-cache",
        "tests/test_package.py": (
            b"from pathlib import Path\n"
            b"from importlib.resources import files\n"
            b"from boardgames.azul.desktop import VALUE\n"
            b"def test_package():\n"
            b"    assert VALUE == 42\n"
            b"    assert files('boardgames.azul').joinpath(\n"
            b"        'assets/nested/tile.png').read_bytes() == b'synthetic-tile-bytes'\n"
            b"    assert not Path('boardgames/azul/assets/prefs.json').exists()\n"
            b"    assert not Path('boardgames/azul/assets/history').exists()\n"
            b"    assert not Path('boardgames/azul/web_tls').exists()\n"
        ),
    }
    for name, content in files.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    # A real Git index distinguishes tracked inputs from newly added files.
    # No user identity, commit, hooks, or network is needed.
    git = shutil.which("git")
    assert git, "Git is required for tracked/untracked snapshot parity"
    for args in (("init", "-q"), ("add", "--", "." if tracked else "helper.py")):
        result = subprocess.run([git, "-C", str(source), *args],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr

    run_dir = tmp_path / "run"
    command = [sys.executable, str(ROOT / "test_gate.py"), "--source-dir", str(source),
               "--run-dir", str(run_dir), "tests/test_package.py"]
    first = subprocess.run(command, cwd=ROOT, capture_output=True,
                           text=True, encoding="utf-8", timeout=40)
    assert first.returncode == 0, first.stdout + first.stderr
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    entries = {item["path"]: item for item in manifest["source_files"]}
    expected = {"helper.py", "tests/test_package.py", "boardgames/__init__.py",
                "boardgames/azul/__init__.py", "boardgames/azul/desktop.py",
                "boardgames/azul/assets/nested/tile.png"}
    assert expected.issubset(entries)
    assert not (set(files) - expected) & entries.keys()
    snapshot = Path(manifest["source_snapshot"])
    for name in expected:
        assert (snapshot / name).read_bytes() == files[name]
        assert entries[name]["sha256"] == hashlib.sha256(files[name]).hexdigest()

    # Resume must bind both code and asset bytes, and preserve the original
    # completed attempt rather than rerun it after input changes.
    summary_path = run_dir / "summary.json"
    summary_before = summary_path.read_bytes()
    original = json.loads(summary_before)
    log = run_dir / original["results"][0]["log"]
    log_before = log.read_bytes()
    (source / changed).write_bytes(files[changed] + b"\n# changed\n")
    resumed = subprocess.run(
        [sys.executable, str(ROOT / "test_gate.py"), "--resume", str(run_dir)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=40,
    )
    assert resumed.returncode == 2, resumed.stdout + resumed.stderr
    assert "refused" in resumed.stderr.lower()
    assert summary_path.read_bytes() == summary_before
    assert log.read_bytes() == log_before
