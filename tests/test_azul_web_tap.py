"""Production Azul JavaScript, deferred SSE/HTTP, and real-rule move parity."""
import json
from pathlib import Path
import subprocess

from boardgames.azul.web import WEB_JS
from games_pkg.azul import AzulGame, MARKER


def _game():
    game = AzulGame([1, 2], seed=3)
    game.offers = [list("rrry"), ["b"], [], [], []]
    game.center = list("rrk")
    game.rows[1][0] = ["r"]
    game.rows[1][1] = ["b"]
    game.wall[1][(2, 2)] = "r"
    game.rows[1][3] = ["r", "r"]
    game.floor[1] = ["y"]
    return game


def test_renderer_tap_drag_pending_and_room_fences(tmp_path):
    payload = tmp_path / "azul.json"
    payload.write_text(json.dumps({"js": WEB_JS, "snapshot": _game().snapshot()}), encoding="utf-8")
    result = subprocess.run(
        ["node", str(Path(__file__).with_name("azul_web_probe.cjs")), str(payload)],
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    for key in ("tapActions", "dragActions"):
        game = _game()
        for action in report[key]:
            game.act(1, action)
        assert game.rows[1][3] == ["r"] * 4
        assert game.floor[1] == ["y", "r"]
        assert game.pending is None
        assert game.snapshot()["turn_uid"] == 2
        assert game.center == list("rrky")
    game = _game()
    for action in report["centralActions"]:
        game.act(1, action)
    assert game.floor[1] == ["y", MARKER, "r", "r"]
    assert game.pending is None
    game = _game()
    game.pending = ["r"] * 3
    for action in report["floorActions"]:
        game.act(1, action)
    assert game.floor[1] == ["y"] + ["r"] * 3
    assert game.pending is None
