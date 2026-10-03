"""C2 regressions: uncertain ownership or path safety must stop execution."""
import os
from pathlib import Path
import sys
import uuid

import pytest

import test_gate


@pytest.mark.parametrize("pid", [None, 0, 123456])
def test_resume_without_proven_process_exit_fails_closed(tmp_path, monkeypatch, pid):
    monkeypatch.setattr(test_gate, "process_image_path", lambda _pid: None)
    monkeypatch.setattr(test_gate, "process_state", lambda _pid: "unknown", raising=False)
    progress = {"results": [{"file": "tests/test_probe.py", "status": "running",
                             "attempts": [{"pid": pid, "status": "running"}]}]}
    test_gate._mark_stale_attempts(progress, tmp_path)
    assert progress["results"][0]["status"] == "infrastructure_error"
    assert progress["results"][0]["attempts"][0]["cleanup_ok"] is False


def test_cleanup_failure_stops_before_next_file(tmp_path, monkeypatch):
    source = tmp_path / "candidate"
    (source / "tests").mkdir(parents=True)
    for name in ("test_a.py", "test_b.py"):
        (source / "tests" / name).write_text("def test_ok(): assert True\n", encoding="utf-8")
    executed = []

    def uncertain_cleanup(**kwargs):
        record = kwargs["record"]
        executed.append(record["file"])
        record.update(status="timeout", exit_code=124, counts={})
        record["attempts"].append({"status": "timeout", "cleanup_ok": False})

    monkeypatch.setattr(test_gate, "_execute_one", uncertain_cleanup)
    result = test_gate.main(["--source-dir", str(source), "--run-dir", str(tmp_path / "run")])
    assert result == 2
    assert executed == ["tests/test_a.py"]


@pytest.mark.skipif(os.name != "nt", reason="Windows junction safety contract")
@pytest.mark.parametrize("entry", ["resume", "new-run"])
def test_explicit_junction_is_rejected_before_resolution(tmp_path, entry):
    import _winapi

    target, alias = tmp_path / "target", tmp_path / "alias"
    target.mkdir()
    _winapi.CreateJunction(str(target), str(alias))
    try:
        with pytest.raises(ValueError, match="reparse|junction"):
            if entry == "resume":
                test_gate._resolve_resume_dir(str(alias), None, "")
            else:
                source = tmp_path / "candidate"
                (source / "tests").mkdir(parents=True)
                file = source / "tests" / "test_probe.py"
                file.write_text("def test_ok(): assert True\n", encoding="utf-8")
                args = test_gate._parse(["--source-dir", str(source), "--run-dir", str(alias)])
                test_gate._make_new_run(args, source, [file])
    finally:
        # Remove only the junction itself; never recurse into its target.
        os.rmdir(alias)


@pytest.mark.skipif(os.name != "nt", reason="Windows native standard handle contract")
@pytest.mark.parametrize("operation", ["stdin", "stderr_independent"])
def test_private_child_has_valid_independent_standard_streams(tmp_path, operation):
    from test_sandbox import launch_process

    script = ("import os; assert os.read(0, 1) == b''; print('stdin-ok')" if operation == "stdin" else
              "import os; sink=open(os.devnull,'w'); os.dup2(sink.fileno(),1); "
              "os.write(2,b'stderr-marker\\n')")
    log = tmp_path / "native-stdio.log"
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP")
           if key in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    process = launch_process([sys.executable, "-c", script], cwd=str(tmp_path),
                             env=env, log_path=log, desktop_name="MoyuStdio-" + uuid.uuid4().hex[:10])
    try:
        assert process.wait(timeout=10) == 0
    finally:
        if process.poll() is None:
            assert process.terminate_tree()
        process.close()
    expected = "stdin-ok" if operation == "stdin" else "stderr-marker"
    assert expected in log.read_text(encoding="utf-8")
