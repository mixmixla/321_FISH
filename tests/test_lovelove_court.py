"""Court role identity and priest observations follow real hand/private boundaries."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from boardgames import card_table_tk as table
from boardgames.card_table_web import WEB_JS
from games_pkg.lovelove import LoveLoveGame, _names
from test_card_table_tk import Canvas, _labels


def _game():
    game = LoveLoveGame([7, 8, 9], seed=3)
    game.hand = {7: 2, 8: 6, 9: 4}
    game.deck = [1, 1, 1, 5, 3]
    return game


def _peek(game):
    return game.act(7, {"play": 2, "target": 8})


def test_priest_result_is_delivered_only_to_actor_and_is_a_copy():
    game = _game()
    events = _peek(game)
    assert any("查看了 玩家8" in message for message in events)
    assert not any("国王" in message or "（6）" in message for message in events)
    assert game.private(7)["peek"] == {"target": 8, "value": 6}
    assert "peek" not in game.private(8) and "peek" not in game.private(9)
    assert game.private(99) is None
    assert "peek" not in game.snapshot() and "hand" not in game.snapshot()
    game.private(7)["peek"]["value"] = 8
    assert game.private(7)["peek"]["value"] == 6


@pytest.mark.parametrize("play", [5, 6])
def test_priest_observation_expires_on_redraw_or_exchange(play):
    game = _game(); _peek(game)
    game.turn_idx = game.alive.index(9)
    game.hand[9] = play
    game.act(9, {"play": play, "target": 8})
    assert "peek" not in game.private(7)


def test_priest_observation_expires_when_target_plays_or_leaves():
    game = _game(); _peek(game)
    game.act(8, {"play": 6, "target": 9})
    assert "peek" not in game.private(7)
    game = _game(); _peek(game)
    game.player_left(8)
    assert "peek" not in game.private(7)


def test_priest_observation_expires_on_actor_leave_or_game_end():
    game = _game(); _peek(game)
    game.player_left(7)
    assert "peek" not in game.private(7)
    game = _game(); game.deck = [3]
    _peek(game)
    assert game.game_over and "peek" not in game.private(7)


@pytest.mark.parametrize("value", range(1, 9))
def test_tk_role_name_value_and_atlas_cell_stay_together(value, monkeypatch):
    asked = []
    monkeypatch.setattr(table, "art", lambda *args, **kwargs: asked.append(args[1:5]))
    canvas = Canvas()
    table._portrait(canvas, value, (0, 0, 160, 220), "测试角色")
    assert asked == [("lovelove-court.webp", value - 1, 4, 2)]
    assert f"{value} · {_names(value)}" in _labels(canvas)


def test_tk_peek_never_renders_for_target_spectator_or_ended_game():
    game = _game(); _peek(game)
    for me, ended, visible in [(7, False, True), (8, False, False), (99, False, False), (7, True, False)]:
        canvas = Canvas()
        state = dict(game.snapshot(), status="ended" if ended else "playing")
        ui = {"room": {"players": game.players}, "state": state, "me": me}
        # Deliberately supply the actor frame to prove UI ownership gates as well.
        table.paint_lovelove(canvas, state, me, str, lambda action: None, lambda: None,
                             ui, game.private(7) if me != 8 else game.private(8), 480, 400)
        assert ("牧师私见" in _labels(canvas)) is visible


def test_visual_web_controls_and_priest_private_result(tmp_path):
    data = tmp_path / "court.json"
    data.write_text(json.dumps({"js": WEB_JS}), encoding="utf-8")
    node = shutil.which("node")
    assert node
    result = subprocess.run([node, str(Path(__file__).with_name("lovelove_court_web_probe.cjs")), str(data)],
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["visual_guard_action"]
