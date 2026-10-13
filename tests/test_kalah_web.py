"""Execute the actual PAGE Kalah renderer; DOM is synthetic and has no network."""
import subprocess
from pathlib import Path


def test_actual_page_kalah_inputs():
    result = subprocess.run(["node", str(Path(__file__).with_name("kalah_web_probe.cjs"))],
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"b_turn":true' in result.stdout
