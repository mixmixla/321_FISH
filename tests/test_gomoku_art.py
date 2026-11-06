"""Generated sprite contracts and safe degradation, with no Tk root or devices."""
from PIL import Image

from boardgames import gomoku_art as art


def test_generated_stones_have_real_alpha_and_read_at_small_size():
    with Image.open(art.ART_DIR / art.STONES_NAME) as image:
        assert image.mode == "RGBA"
        assert image.size == (512, 256)
        for value in (1, 2):
            cell = image.crop(((value - 1) * 256, 0, value * 256, 256))
            alpha = cell.getchannel("A")
            assert alpha.getpixel((0, 0)) == alpha.getpixel((255, 255)) == 0
            assert alpha.getpixel((128, 128)) == 255
            # Equal size and centring matter when adjacent pieces are only 14px.
            x0, y0, x1, y1 = alpha.point(lambda a: 255 if a > 128 else 0).getbbox()
            assert 210 <= x1 - x0 <= 226 and 210 <= y1 - y0 <= 226
            assert abs((x0 + x1) / 2 - 128) < 3
            assert abs((y0 + y1) / 2 - 128) < 3
            small = cell.resize((16, 16), Image.Resampling.LANCZOS)
            rgb = small.getpixel((8, 8))[:3]
            assert (max(rgb) < 65) if value == 1 else (min(rgb) > 190)
            assert small.getpixel((0, 0))[3] == 0


def test_non_canvas_uses_existing_renderer_fallback(monkeypatch):
    from PIL import ImageTk

    def forbidden(*args, **kwargs):
        raise AssertionError("headless fallback created a Tk image")

    monkeypatch.setattr(ImageTk, "PhotoImage", forbidden)
    assert art.draw_board(object(), 0, 0, 320, 320) is False
    assert art.draw_stone(object(), 100, 100, 8, 1) is False
    assert art.draw_stone(object(), 100, 100, 8, 2) is False


def test_missing_art_degrades_without_raising(monkeypatch, tmp_path):
    art._source.cache_clear()
    try:
        monkeypatch.setattr(art, "ART_DIR", tmp_path)
        assert art._source(art.BOARD_NAME) is None
        assert art._source(art.STONES_NAME) is None
    finally:
        art._source.cache_clear()
