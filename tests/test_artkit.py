# -*- coding: utf-8 -*-
"""artkit 共享绘制原语：尺寸、alpha、明暗关系、异常安全。"""
import pytest

pytest.importorskip("PIL")
from PIL import Image

from boardgames import artkit


def _lum(px):
    return 0.299 * px[0] + 0.587 * px[1] + 0.114 * px[2]


def test_no_tkinter_import():
    # 隔离子进程校验：artkit 自身不得把 tkinter 拉进 sys.modules。
    # 不能在本进程内断言 —— tests/conftest.py import tkguard，而 tkguard 顶层
    # 就 `import tkinter`，会在任何用例运行前污染 sys.modules。
    import subprocess
    import sys
    from pathlib import Path
    code = "import sys; import boardgames.artkit; print('tkinter' in sys.modules)"
    r = subprocess.run([sys.executable, "-c", code],
                       cwd=str(Path(__file__).resolve().parents[1]),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "False"


def test_canvas_supersamples_and_finish_converges():
    img, dr, s = artkit.canvas(24, 16)
    assert s == artkit.SS
    assert img.size == (24 * s, 16 * s)
    assert img.mode == "RGBA"
    assert artkit.finish(img, 24, 16).size == (24, 16)


def test_color_normalizes_hex_tuple_and_junk():
    assert artkit.color("#FF8000") == (255, 128, 0, 255)
    assert artkit.color((1, 2, 3)) == (1, 2, 3, 255)
    assert artkit.color((1, 2, 3, 4)) == (1, 2, 3, 4)
    assert artkit.color("nonsense") == (0, 0, 0, 255)


def test_rrect_fills_and_respects_reverse_box():
    img, dr, s = artkit.canvas(20, 20)
    artkit.rrect(dr, (2, 2, 18, 18), 4, s=s, fill="#3366FF")
    assert artkit.finish(img, 20, 20).getpixel((10, 10)) == (51, 102, 255, 255)
    # 反向/空框：静默跳过，不抛
    artkit.rrect(dr, (10, 10, 4, 4), 3, s=s, fill="#fff")
    artkit.rrect(dr, None, 3, s=s, fill="#fff")


def test_rrect_bevel_top_edge_is_brighter_than_bottom():
    img, _dr, s = artkit.canvas(60, 60)
    img = artkit.rrect_bevel(img, (6, 6, 54, 54), 8, "#8899AA", s=s, depth=2)
    out = artkit.finish(img, 60, 60)
    assert _lum(out.getpixel((30, 7))) > _lum(out.getpixel((30, 52)))


def test_recess_top_inner_edge_is_darker_than_bottom():
    img, _dr, s = artkit.canvas(60, 60)
    img = artkit.recess(img, (6, 6, 54, 54), 8, "#BFB6A4", s=s, depth=2)
    out = artkit.finish(img, 60, 60)
    assert _lum(out.getpixel((30, 7))) < _lum(out.getpixel((30, 52)))


def test_shadow_makes_translucent_pixels_outside_box():
    img = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
    img = artkit.shadow(img, (20, 20, 60, 60), 8, spread=4, alpha=90,
                        offset=(0, 3))
    assert img.size == (80, 80)
    a = img.getpixel((40, 66))[3]
    assert 0 < a < 255
    assert img.getpixel((2, 2))[3] == 0


def test_image_ops_return_new_image_and_keep_input():
    src = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    out = artkit.shadow(src, (8, 8, 32, 32), 6, spread=3, alpha=60)
    assert out is not src
    assert src.getpixel((20, 20)) == (0, 0, 0, 0)


def test_gradient_is_vertical_by_default_and_clear_outside_box():
    img = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    out = artkit.gradient(img, (4, 4, 44, 44), 6, "#FFFFFF", "#202020")
    assert out.size == (48, 48)
    assert _lum(out.getpixel((24, 8))) > _lum(out.getpixel((24, 40)))
    assert out.getpixel((1, 1))[3] == 0


def test_gradient_horizontal_direction():
    img = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    out = artkit.gradient(img, (4, 4, 44, 44), 6, "#FFFFFF", "#202020",
                          direction="h")
    assert _lum(out.getpixel((8, 24))) > _lum(out.getpixel((40, 24)))


def test_radial_center_brighter_than_far_edge():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    out = artkit.radial(img, (4, 4, 60, 60), "#FFFFFF", "#101820")
    assert _lum(out.getpixel((32, 32))) > _lum(out.getpixel((10, 32)))
    assert out.getpixel((0, 0))[3] == 0


def test_linen_is_deterministic_and_keeps_outside_clear():
    img = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    kw = dict(s=1, amount=6, seed=7)
    a = artkit.linen(img, (4, 4, 36, 36), 6, "#C8BE9E", **kw)
    b = artkit.linen(img, (4, 4, 36, 36), 6, "#C8BE9E", **kw)
    assert a.tobytes() == b.tobytes()
    assert a.getpixel((20, 20))[3] == 255
    assert a.getpixel((1, 1))[3] == 0
    c = artkit.linen(img, (4, 4, 36, 36), 6, "#C8BE9E", s=1, amount=6, seed=8)
    assert c.tobytes() != a.tobytes()


def test_ornament_tile_is_seamless_when_cells_divide_size():
    size, cells = 64, 2
    tile = artkit.ornament_tile(size, "#F7FAFC", "#4A7DE0", "#2B5E8C", cells=cells)
    assert tile.size == (size, size)
    assert size % cells == 0
    p = size // cells
    # 取样必须远离画布边缘（重采样核会越界，边缘像素不满足周期相等）
    for x, y in ((8, 8), (12, 17), (24, 28), (28, 5)):
        assert tile.getpixel((x, y)) == tile.getpixel((x + p, y))
        assert tile.getpixel((x, y)) == tile.getpixel((x, y + p))


def test_disc_has_bright_center_and_transparent_corner():
    img = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    out = artkit.disc(img, (2, 2, 46, 46), "#2E4A63", "#F7FAFC")
    assert out.getpixel((1, 1))[3] == 0          # 四角透明
    assert out.getpixel((24, 24))[3] == 255      # 盘面不透明
    assert _lum(out.getpixel((24, 24))) > _lum(out.getpixel((24, 5)))   # 中心亮于边缘


def test_chip_is_opaque_in_center_and_transparent_at_corner():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    out = artkit.chip(img, (2, 2, 62, 62), "#4A7DE0", label="3")
    assert out.size == (64, 64)
    assert out.getpixel((32, 32))[3] == 255
    assert out.getpixel((0, 0))[3] == 0


def test_gem_tile_and_marker_shapes():
    tile = artkit.gem(Image.new("RGBA", (48, 48), (0, 0, 0, 0)), (3, 3, 45, 45),
                      "#D2534F", shape="tile")
    assert tile.getpixel((0, 0))[3] == 0
    assert tile.getpixel((24, 24))[3] == 255
    assert _lum(tile.getpixel((24, 9))) > _lum(tile.getpixel((24, 39)))
    mk = artkit.gem(Image.new("RGBA", (40, 40), (0, 0, 0, 0)), (2, 2, 38, 38),
                    "#3A3A3A", shape="marker")
    assert mk.size == (40, 40)
    assert mk.getpixel((20, 20))[3] == 255
