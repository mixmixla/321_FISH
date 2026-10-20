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
    for k in ("azulejo", "azul_tile_r", "gem_o", "azul_wall_bg", "azul_board", "azul_plate", "azul_track_ring", "azul_chip", "azul_marker_r", "azul_plate_center", "panel"):
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
                        lambda: {"azul_wall_bg": "data:image/png;base64,AAAA"})
    html = web._SERVED_PAGE().decode("utf-8")
    assert "@@UX_BG_ASSETS@@" not in html

def test_panel_css_and_renderers_use_bitmaps():
    html = web._SERVED_PAGE().decode("utf-8")
    assert "body.hasBgArt #gpanel .card" in html
    assert "function bgImg(" in html
    # Azul 渲染器迁入展示包后改用包内新键（由 web_parts 注入，仍在服务页内）。
    for mark in ('bgImg("azul_wall_bg")', 'bgImg("azul_plate")',
                 'bgImg("azul_board")', 'bgImg("azul_track_ring")', 'bgImg("panel")'):
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


def test_azul_renderer_comes_from_package_not_inline_template():
    from web import PAGE
    # 模板里不再内联 azul 渲染器
    assert "azul(box,s){" not in PAGE
    html = web._SERVED_PAGE().decode("utf-8")
    # 由包注入
    assert "Object.assign(GRENDER,{" in html
    assert 'op:"take"' in html and 'op:"place"' in html and 'op:"floor"' in html
    for k in ("azul_wall_bg", "azul_board", "azul_plate", "azul_track_ring"):
        assert k in html, k


def test_azul_web_js_is_a_single_selfcontained_statement():
    from boardgames.azul import web as azweb
    assert azweb.WEB_JS.strip().startswith("Object.assign(GRENDER,{")
    assert azweb.WEB_JS.strip().endswith(");")


def test_azul_web_layout_renders_all_players_and_grid():
    """BGA 重排：遍历所有玩家板 + grid 结构 + 动作契约不变。"""
    from boardgames.azul import web as azweb
    js = azweb.WEB_JS
    assert "s.players" in js                      # 修「只画一块板」：逐人一块板
    for mark in ("azul_wall_bg", "azul_board", "azul_track_ring", "azul_chip",
                 "azul_marker_", "azul_plate_center", "azgrid", "azboards"):
        assert mark in js, mark
    assert 'op:"take"' in js and 'op:"place"' in js and 'op:"floor"' in js
    assert js.strip().startswith("Object.assign(GRENDER,{")
    assert js.strip().endswith(");")
    css = azweb.WEB_CSS
    assert "grid-template-areas" in css
    assert "azgrid" in css and ".azboard" in css


def test_azul_web_js_compiles_in_node(tmp_path):
    """注入串必须语法合法（node --check）。"""
    import shutil, subprocess
    if shutil.which("node") is None:
        import pytest; pytest.skip("node unavailable")
    from boardgames.azul import web as azweb
    p = tmp_path / "az_js.js"
    p.write_text(azweb.WEB_JS, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_web_has_enlarge_button_and_azul_drag_wiring():
    """网页端：对局面板可一键放大；花砖支持拖拽取砖（不再只靠下拉框）。"""
    html = web._SERVED_PAGE().decode("utf-8")
    assert "state.gfull" in html and "card.full" in html
    assert "⛶ 放大" in html and "⛶ 还原" in html
    from boardgames.azul import web as azweb
    js = azweb.WEB_JS
    for mark in ("data-azsrc", "data-azdrop", "pointerdown", "pointerup",
                 "azghost", "canRow"):
        assert mark in js, mark
    assert 'op:"take"' in js and 'op:"place"' in js and 'op:"floor"' in js
    css = azweb.WEB_CSS
    for mark in (".azghost", ".azdrop.azok", ".azdrop.azsel", ".aztile"):
        assert mark in css, mark


def test_gomoku_web_renderer_gates_input_and_shows_coordinates():
    """五子棋网页端：只在自己回合点空点落子，并显示 A~O / 1~15 坐标。"""
    html = web._SERVED_PAGE().decode("utf-8")
    assert "gomoku(box,s){" in html
    assert "s.turn_uid===state.uid" in html          # 只在自己回合可点
    assert "s.board[y][x])return" in html           # 已有棋子的点不提交
    assert "String.fromCharCode(65+i)" in html      # 列坐标 A~O


def test_subset_no_longer_serves_legacy_azul_keys():
    html = web._SERVED_PAGE().decode("utf-8")
    bg = _extract_bg_literal(html)
    for k in ("azul_table", "azul_boardface", "azul_track"):
        assert k not in bg, k
    for k in ("azul_wall_bg", "azul_board", "azul_track_ring", "azul_chip", "azul_marker_r"):
        assert k in bg, k
