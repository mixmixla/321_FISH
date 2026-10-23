"""C2 regressions: uncertain ownership or path safety must stop execution."""
import os
from pathlib import Path
import sys
import uuid

import pytest

import test_gate
import test_sandbox


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


@pytest.mark.parametrize("native", [False, True], ids=["popen", "native"])
@pytest.mark.parametrize("outcome", ["exited", "timeout", "error", "unknown", "descendant_unknown"])
def test_termination_waits_for_owned_exit_and_keeps_uncertainty(monkeypatch, native, outcome):
    """Termination can return while the owned process is still unsignaled."""
    calls = []
    state = {"code": None}
    owned = [73101, 73102]

    class FailedTaskkill:
        def wait(self, timeout):
            return 1

    def taskkill(command, **kwargs):
        assert command[0] == "taskkill" and int(command[2]) in owned
        return FailedTaskkill()

    def waited(timeout):
        calls.append(("wait", timeout))
        assert 0 < timeout <= 10
        if outcome == "timeout":
            raise TimeoutError("synthetic delayed exit")
        if outcome == "error":
            raise OSError("synthetic wait failure")
        state["code"] = None if outcome == "unknown" else 124
        return state["code"]

    class Popen:
        pid = owned[0]

        def poll(self):
            return state["code"]

        def kill(self):
            calls.append(("terminate", self.pid))

        wait = staticmethod(waited)

    class Kernel:
        def TerminateProcess(self, handle, code):
            assert handle == 917 and code == 124
            calls.append(("terminate", owned[0]))
            return True

    def descendants(pids):
        assert pids == owned
        calls.append(("descendants", tuple(pids)))
        return outcome != "descendant_unknown"

    monkeypatch.setattr(test_sandbox, "process_session_id", lambda _pid: 1)
    monkeypatch.setattr(test_sandbox, "process_tree_pids", lambda _pid: owned)
    monkeypatch.setattr(test_sandbox, "_ORIGINAL_POPEN", taskkill)
    monkeypatch.setattr(test_sandbox, "_windows_handles", lambda: (Kernel(), None))
    monkeypatch.setattr(test_sandbox, "_wait_owned_processes_gone", descendants)
    process = test_sandbox.DesktopProcess(
        popen=None if native else Popen(), process_handle=917 if native else None,
        pid=owned[0],
    )
    if native:
        monkeypatch.setattr(process, "poll", lambda: state["code"])
        monkeypatch.setattr(process, "wait", waited)
    result = process.terminate_tree()
    assert result is (outcome == "exited")
    assert calls[:2] == [("terminate", owned[0]), ("wait", 10)]
    assert any(c[0] == "descendants" for c in calls) is (outcome in {"exited", "descendant_unknown"})


@pytest.mark.skipif(os.name != "nt", reason="Windows owned process exit contract")
@pytest.mark.parametrize("native", [False, True], ids=["popen", "native"])
def test_owned_real_process_fallback_termination(tmp_path, monkeypatch, native):
    """Exercise real held process/handle cleanup when taskkill is unavailable."""
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP")
           if key in os.environ}
    process = test_sandbox.launch_process(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=str(tmp_path), env=env, log_path=tmp_path / "owned-exit.log",
        desktop_name="MoyuExit-" + uuid.uuid4().hex[:10] if native else None,
    )
    try:
        assert process.poll() is None
        with monkeypatch.context() as patch:
            def unavailable(command, **kwargs):
                assert command[0] == "taskkill"
                raise OSError("synthetic taskkill unavailable")
            patch.setattr(test_sandbox, "_ORIGINAL_POPEN", unavailable)
            assert process.terminate_tree()
        assert process.poll() is not None
        assert test_sandbox.process_state(process.pid) == "exited"
    finally:
        failure = sys.exception()
        try:
            if process.poll() is None:
                assert process.terminate_tree(), "owned child cleanup failed"
            process.wait(timeout=10)
        except BaseException as exc:
            if failure is None:
                raise
            failure.add_note("owned child cleanup: " + type(exc).__name__)
        finally:
            process.close()
