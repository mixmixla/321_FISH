"""Production manor renderer: DOM actions/map/history, no foreground UI."""
import json
from pathlib import Path
import shutil
import subprocess

from boardgames.manor_catalog import ATLASES
from boardgames.manor_web import WEB_JS
import web


def test_manor_is_injected_into_the_formal_page():
    html = web._SERVED_PAGE().decode("utf-8")
    assert "@@MANOR_" not in html
    assert "ManorWeb.paint(box,s)" in html
    assert "betrayal-rooms.webp" in html


def test_manor_production_map_actions_archive_and_legacy_fields(tmp_path):
    node = shutil.which("node")
    assert node, "Production Web checks require Node"
    data = tmp_path / "manor.json"
    data.write_text(json.dumps({"js": WEB_JS, "catalog": ATLASES}), encoding="utf-8")
    result = subprocess.run([node, str(Path(__file__).with_name("manor_web_probe.cjs")), str(data)],
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["multiple_cards"]
