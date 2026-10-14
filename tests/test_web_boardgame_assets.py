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
    monkeypatch.setattr(web, "_bg_assets_all", lambda: {})
    html = web._SERVED_PAGE().decode("utf-8")
    assert "@@UX_BG_ASSETS@@" not in html
    assert _extract_bg_literal(html) == {}

def test_served_page_has_no_game_injection_placeholders():
    html = web._SERVED_PAGE().decode("utf-8")
    assert "@@UX_GAME_RENDERERS@@" not in html
    assert "@@UX_GAME_CSS@@" not in html

def test_bg_subset_merges_package_assets(monkeypatch):
    monkeypatch.setattr(web, "_bg_assets_all",
                        lambda: {"azul_table": "data:image/png;base64,AAAA"})
    html = web._SERVED_PAGE().decode("utf-8")
    assert "@@UX_BG_ASSETS@@" not in html

def test_panel_css_and_renderers_use_bitmaps():
    html = web._SERVED_PAGE().decode("utf-8")
    assert "body.hasBgArt #gpanel .card" in html
    assert "function bgImg(" in html
    for mark in ('bgImg("azul_bowl")', 'bgImg("azul_board")',
                 'bgImg("azul_score_track")', 'bgImg("panel")'):
        assert mark in html, mark
    assert 'BG["gem_' in html
    assert 'BG["azul_tile_' in html
    # 动作契约不回归
    assert '{op:"take"' in html and '{op:"place"' in html and '{op:"floor"' in html
    assert 'op:"take2"' in html and 'op:"buy"' in html and 'op:"reserve"' in html

def test_bg_img_fragment_survives_single_quoted_style_attribute():
    # bgImg 输出的片段会被拼进单引号包裹的 style 属性（如 style='...+bgImg(...)+...'）。
    # 若片段内含单引号（旧写法 background:url('...')），首个 ' 会提前闭合 style 属性，
    # 导致位图不显示、后续声明（如 display:grid）丢失、DOM 结构损坏。
    html = web._SERVED_PAGE().decode("utf-8")
    assert "background:url('" not in html
    m = re.search(r"function bgImg\(key,extra\)\{[^\n]*\}", html)
    assert m, "bgImg definition not found"
    fragment_src = m.group(0)
    assert "'" not in fragment_src, fragment_src
    assert "background:url(" in fragment_src
