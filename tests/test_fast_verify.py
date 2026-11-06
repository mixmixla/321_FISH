"""Bounded synthetic checks for priority, cooperative stop and exact coverage."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import fast_verify
import test_gate


ROOT = Path(__file__).resolve().parents[1]


def _source(tmp_path, files):
    source = tmp_path / "candidate"
    (source / "tests").mkdir(parents=True)
    for name, text in files.items():
        (source / "tests" / name).write_text(text, encoding="utf-8")
    return source


def _run(tmp_path, source, *args):
    run = tmp_path / "run"
    result = subprocess.run(
        [sys.executable, str(ROOT / "fast_verify.py"), "--source-dir", str(source),
         "--run-dir", str(run), "--timeout", "15", *args], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    return result, run, json.loads((run / "summary.json").read_text(encoding="utf-8"))


def test_priority_is_not_repeated_and_unknown_files_stay_serial():
    files = ["tests/test_go_solo.py", "tests/test_new_gui.py", "tests/test_tielu_play.py"]
    lanes = fast_verify.partition(files, [files[0]], serial=False)
    assert lanes == {"priority": [files[0]], "serial": [files[1]], "rules": [files[2]]}
    assert sorted(name for names in lanes.values() for name in names) == sorted(files)
    nested = fast_verify.partition(["tests/test_fast_verify.py", *files], [], False)
    assert nested["exclusive"] == ["tests/test_fast_verify.py"]
    gui_first = fast_verify.partition(files, [], gui_files=[files[1]])
    assert gui_first["gui"] == [files[1]]
    assert "serial" not in gui_first
    assert sorted(name for names in gui_first.values() for name in names) == sorted(files)


def test_priority_failure_preserves_failure_and_does_not_start_remaining_lanes(tmp_path):
    source = _source(tmp_path, {
        "test_go_solo.py": "def test_red():\n    assert False, 'intentional red'\n",
        "test_tielu_play.py": "def test_rule():\n    assert True\n",
        "test_unknown.py": "def test_serial():\n    assert True\n",
    })
    result, run, report = _run(tmp_path, source, "--priority", "tests/test_go_solo.py")
    assert result.returncode == report["exit_code"] == 1, result.stdout + result.stderr
    assert report["totals"] == {"failed": 1}
    assert report["missing"] == ["tests/test_tielu_play.py", "tests/test_unknown.py"]
    assert set(report["lanes"]) == {"priority"}
    assert not (run / "rules").exists()
    native = json.loads((run / "priority" / "summary.json").read_text(encoding="utf-8"))
    assert native["results"][0]["status"] == "failed"
    assert len(native["results"][0]["attempts"]) == 1


def test_two_lanes_cover_all_files_once(tmp_path):
    source = _source(tmp_path, {
        "test_go_solo.py": "def test_rule():\n    assert True\n",
        "test_unknown.py": "def test_serial():\n    assert True\n",
    })
    result, run, report = _run(tmp_path, source)
    assert result.returncode == report["exit_code"] == 0, result.stdout + result.stderr
    assert report["full_suite"] and report["files"] == report["planned_files"] == 2
    assert report["totals"] == {"passed": 2}
    assert report["missing"] == report["duplicates"] == report["extra"] == []
    assert set(report["lanes"]) == {"serial", "rules"}
    native_path = run / "serial" / "summary.json"
    native = test_gate._load_json(native_path)
    native.update(exit_code=2, cleanup_failures=[])
    test_gate._atomic_json(native_path, native)
    report["lanes"]["serial"]["exit_code"] = 2
    assert fast_verify.collect(run, test_gate._load_json(run / "plan.json"),
                               report["lanes"])["exit_code"] == 2


def test_native_fail_fast_and_resume_do_not_reexecute_red_file(tmp_path):
    source = _source(tmp_path, {
        "test_a_red.py": "def test_red():\n    assert False\n",
        "test_b_green.py": "def test_green():\n    assert True\n",
    })
    run = tmp_path / "native"
    command = [sys.executable, str(ROOT / "run.py"), "test-all", "--source-dir", str(source),
               "--run-dir", str(run), "--fail-fast"]
    first = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=30)
    assert first.returncode == 1
    before = test_gate._load_json(run / "summary.json")
    assert before["files"] == 1 and before["planned_files"] == 2
    assert before["pending_files"] == ["tests/test_b_green.py"]
    assert before["stop_reason"] == "fail_fast"
    again = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "test-all", "--resume", str(run), "--fail-fast"],
        cwd=ROOT, capture_output=True, timeout=30,
    )
    assert again.returncode == 1
    after = test_gate._load_json(run / "summary.json")
    assert after["results"] == before["results"]


def test_native_stop_file_drains_current_file_then_leaves_next_pending(tmp_path):
    stop = tmp_path / "STOP"
    source = _source(tmp_path, {
        "test_a.py": "from pathlib import Path\ndef test_stop():\n"
                     f"    Path({str(stop)!r}).touch()\n    assert True\n",
        "test_b.py": "def test_next():\n    assert False, 'must stay pending'\n",
    })
    run = tmp_path / "native"
    result = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "test-all", "--source-dir", str(source),
         "--run-dir", str(run), "--stop-file", str(stop)], cwd=ROOT,
        capture_output=True, timeout=30,
    )
    assert result.returncode == 1
    report = test_gate._load_json(run / "summary.json")
    assert report["totals"] == {"passed": 1}
    assert report["pending_files"] == ["tests/test_b.py"]
    assert report["stop_reason"] == "stop_file"


def test_failure_in_one_lane_stops_both_queues_without_killing_current_file(tmp_path):
    serial_started = tmp_path / "serial-started"
    stop = tmp_path / "run" / "STOP"
    imports = "from pathlib import Path\nimport time\n"
    source = _source(tmp_path, {
        "test_go_solo.py": imports + "def test_red():\n"
            "    deadline = time.monotonic() + 5\n"
            f"    while not Path({str(serial_started)!r}).exists() and time.monotonic() < deadline:\n"
            "        time.sleep(.01)\n"
            f"    assert Path({str(serial_started)!r}).exists()\n"
            "    assert False, 'intentional concurrent red'\n",
        "test_tielu_play.py": "def test_pending_rule():\n    assert False\n",
        "test_a_slow.py": imports + "def test_drain():\n"
            f"    Path({str(serial_started)!r}).touch()\n"
            "    deadline = time.monotonic() + 5\n"
            f"    while not Path({str(stop)!r}).exists() and time.monotonic() < deadline:\n"
            "        time.sleep(.01)\n"
            f"    assert Path({str(stop)!r}).exists()\n",
        "test_b_pending.py": "def test_pending_serial():\n    assert False\n",
    })
    result, _, report = _run(tmp_path, source)
    assert result.returncode == report["exit_code"] == 1, result.stdout + result.stderr
    assert report["totals"] == {"passed": 1, "failed": 1}
    assert report["missing"] == ["tests/test_b_pending.py", "tests/test_tielu_play.py"]
    assert report["errors"] == []
