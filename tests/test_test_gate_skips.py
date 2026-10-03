"""Only explicitly disabled visual/hardware opt-ins may count as gate skips."""
import pytest

from test_test_gate import _run, _source


def test_unexpected_environment_skip_is_a_gate_failure(tmp_path):
    source = _source(tmp_path, **{
        "test_probe.py": "import pytest\ndef test_probe():\n    pytest.skip('broken Tk installation')\n",
    })
    result, _, summary = _run(tmp_path, source, "tests/test_probe.py")
    assert result.returncode != 0
    assert summary["results"][0]["status"] == "infrastructure_error"
    assert summary["totals"]["skipped"] == 1  # keep the actual pytest outcome


@pytest.mark.parametrize("option", ["--run-visual", "--run-hardware"])
def test_known_disabled_opt_in_reason_remains_allowed(tmp_path, option):
    source = _source(tmp_path, **{
        "test_probe.py": f"import pytest\ndef test_probe():\n    pytest.skip('需显式启用 {option}')\n",
    })
    result, _, summary = _run(tmp_path, source, "tests/test_probe.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert summary["totals"]["skipped"] == 1


def test_allowed_skip_cannot_mask_an_unexpected_skip(tmp_path):
    source = _source(tmp_path, **{
        "test_probe.py": (
            "import pytest\n"
            "def test_optin(): pytest.skip('需显式启用 --run-visual')\n"
            "def test_broken(): pytest.skip('unexpected missing file')\n"
        ),
    })
    result, _, summary = _run(tmp_path, source, "tests/test_probe.py")
    assert result.returncode != 0
    assert summary["results"][0]["status"] == "infrastructure_error"
    assert summary["totals"]["skipped"] == 2


def test_r41_fixture_cannot_hide_tk_initialization_errors(monkeypatch):
    import inspect
    import tkinter as tk
    import test_r41

    def broken_tk():
        raise tk.TclError("synthetic missing ttk.tcl")

    monkeypatch.setattr(tk, "Tk", broken_tk)
    try:
        with pytest.raises(tk.TclError, match="synthetic missing"):
            next(inspect.unwrap(test_r41.root)())
    except pytest.skip.Exception:
        pytest.fail("A required Tk fixture must expose initialization failures, not skip")


@pytest.mark.parametrize("location", ["tests/test_visual_screenshot.py",
                                     "tests/test_probe.py:42", r"C:\case\test_probe.py:42"])
def test_allowed_skip_location_with_or_without_line_number(location):
    from test_gate import _unexpected_skips
    output = f"SKIPPED [1] {location}: 需显式启用 --run-visual\n1 skipped in 0.1s\n"
    assert _unexpected_skips(output, {"skipped": 1}) == []
    assert _unexpected_skips(output, {"skipped": 1}, run_visual=True)
    assert _unexpected_skips("1 skipped in 0.1s", {"skipped": 1})
