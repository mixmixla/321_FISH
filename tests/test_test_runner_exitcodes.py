"""验证 Tcl 收尾绕过不会掩盖失败、收集错误或空测试集。"""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize(("source", "expected"), [
    ("def test_ok():\n    assert True\n", 0),
    ("def test_fail():\n    assert False\n", 1),
    ("def test_broken(:\n    pass\n", 2),
    ("# no tests\n", 5),
])
def test_real_pytest_exit_status_survives_cleanup(tmp_path, source, expected):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "conftest.py").write_text(
        (root / "tests" / "conftest.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "test_probe.py").write_text(source, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(tmp_path)],
        cwd=tmp_path, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == expected, result.stdout + result.stderr
