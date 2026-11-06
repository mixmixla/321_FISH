"""Production card presentation and action contracts, without a visible browser."""
import json
from pathlib import Path
import shutil
import subprocess

from boardgames.card_table_web import WEB_JS
import web


def test_card_tables_are_injected_into_the_real_page():
    html = web._SERVED_PAGE().decode("utf-8")
    assert "@@CARD_TABLE" not in html
    assert "const CardTableWeb =" in html
    assert "/game-art/" in html and "lovelove-court.webp" in html


def test_production_card_actions_collection_privacy_and_legacy_fallback(tmp_path):
    source = Path(web.__file__).read_text(encoding="utf-8")
    start = source.index("gemcity(box,s){")
    data = tmp_path / "card-table.json"
    data.write_text(json.dumps({"js": WEB_JS, "gemcity": source[start:source.index("  siji(box,s){", start)]}), encoding="utf-8")
    node = shutil.which("node")
    assert node, "Production JavaScript checks require Node"
    result = subprocess.run([node, str(Path(__file__).with_name("card_table_web_probe.cjs")), str(data)],
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["collection_cards"] == 31 and report["drawn_guard"]
    assert report["spectator_private_hidden"] and report["gem_actions"]
