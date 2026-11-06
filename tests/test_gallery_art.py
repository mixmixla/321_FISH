"""Shared image assets: exact names, safe reads, compact real artwork, fallback."""
from io import BytesIO

import pytest
from PIL import Image

from boardgames import gallery


def test_five_distinct_compact_covers_and_shared_gomoku_art():
    names = set(gallery.COVERS.values())
    assert len(names) == 5
    assert gallery.COVERS["gomoku"] == gallery.COVERS["gomoku_solo"]
    pixels = []
    total = 0
    for name in names:
        data, mime = gallery.read_resource(name)
        assert mime == "image/webp"
        total += len(data)
        with Image.open(BytesIO(data)) as image:
            assert image.format == "WEBP"
            assert image.size == (768, 384)
            pixels.append(image.tobytes())
    assert len(set(pixels)) == 5
    assert total < 600_000


@pytest.mark.parametrize("name", [
    "../web.py", "cover-tielu.webp.bak",
])
def test_only_exact_allowlisted_names_are_readable(name):
    with pytest.raises(FileNotFoundError):
        gallery.read_resource(name)


def test_missing_file_fails_closed_and_preserves_ui_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(gallery, "ART_ROOT", tmp_path)
    with pytest.raises(FileNotFoundError):
        gallery.read_resource("cover-tielu.webp")
    assert gallery.cover_url("unknown") == ""
    assert gallery.paint_cover(object(), "tielu", 180, 80) is False


def test_future_gameplay_assets_are_exact_names_and_png_mime(tmp_path, monkeypatch):
    monkeypatch.setattr(gallery, "ART_ROOT", tmp_path)
    (tmp_path / "gomoku-stones.png").write_bytes(b"synthetic-png-bytes")
    assert gallery.read_resource("gomoku-stones.png") == (b"synthetic-png-bytes", "image/png")
    assert {"tile2048-atlas.webp", "gomoku-board.webp", "gomoku-stones.png"} <= gallery.ART_FILES


def test_featured_order_preserves_the_other_games():
    names = ["chess", "tielu", "uno", "tile2048", "gomoku_solo", "azul", "gemcity", "go"]
    assert gallery.prioritise(names) == [*gallery.FEATURED, "chess", "uno", "go"]
    assert gallery.prioritise(["chess", "go"]) == ["chess", "go"]


def test_http_art_returns_real_image_bytes_and_blocks_other_files():
    import http.client
    from http.server import ThreadingHTTPServer
    import threading
    from web import _Handler

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        for filename in set(gallery.COVERS.values()):
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
            try:
                conn.request("GET", "/game-art/" + filename)
                response = conn.getresponse()
                data = response.read()
                assert response.status == 200
                assert response.getheader("Content-Type") == "image/webp"
                assert response.getheader("X-Content-Type-Options") == "nosniff"
                assert data == gallery.resource_path(filename).read_bytes()
            finally:
                conn.close()
        for filename in ("../web.py", "cover-tielu.webp.bak"):
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
            try:
                conn.request("GET", "/game-art/" + filename)
                response = conn.getresponse()
                response.read()
                assert response.status == 404
            finally:
                conn.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(5)
        assert not thread.is_alive()


def test_live_tk_filtering_reuses_decoded_art_and_keeps_create_actions():
    import tkinter as tk
    from types import SimpleNamespace
    import client
    from games_pkg import GAME_META
    from test_flagship_gui import _fake_game_core

    root = tk.Tk()
    root.withdraw()
    gallery._cover_source.cache_clear()
    core = _fake_game_core()
    core.game_meta = dict(GAME_META)
    core.game_room = core.game_state = None
    created = []
    core.game_create = lambda name, options=None: created.append(name)
    app = SimpleNamespace(root=root, core=core, _frameless=False, _camo_title=lambda: "Synthetic art gallery")
    host = client.GameWindow(app, pal=client._DEFAULT_PAL)
    try:
        host._sync()
        root.update()
        assert host._game_order[:5] == list(gallery.FEATURED)
        for query in ("", "g", "go", "gomoku", "", "铁路", "花砖", "", "2048", ""):
            host.game_query_var.set(query)
            root.update()
        assert gallery._cover_source.cache_info().misses == 5
        for name in gallery.FEATURED:
            assert host.game_cards[name].cover.find_withtag("gallery-cover")
            host.game_cards[name].create_btn.invoke()
        assert created == list(gallery.FEATURED)
    finally:
        host.close()
        root.destroy()
