import json, re
import web

def _extract_bg_literal(html):
    m = re.search(r'const BG=JSON\.parse\("((?:[^"\\]|\\.)*)"\);', html)
    assert m, "BG literal not found"
    return json.loads(json.loads('"' + m.group(1) + '"'))

def test_served_page_has_no_placeholder_and_bg_subset():
    html = web._SERVED_PAGE().decode("utf-8")
    assert "@@UX_BG_ASSETS@@" not in html
    bg = _extract_bg_literal(html)
    for k in ("azulejo", "azul_bowl", "azul_tile_r", "gem_o", "azul_board", "azul_score_track", "panel"):
        assert k in bg, k
        assert bg[k].startswith("data:image/png;base64,")

def test_missing_assets_module_degrades_to_empty(monkeypatch):
    monkeypatch.setattr(web, "_bg_assets", None)
    html = web._SERVED_PAGE().decode("utf-8")
    assert "@@UX_BG_ASSETS@@" not in html
    assert _extract_bg_literal(html) == {}
