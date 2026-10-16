# -*- coding: utf-8 -*-
"""Azul 展示包素材：键集、尺寸、data-URI 形态、PNG 可解码、瓷砖墙无缝。"""
import base64
import io

import pytest

pytest.importorskip("PIL")
from PIL import Image

from boardgames.azul import _art

_EXPECTED_WH = {
    "azul_wall_bg": (512, 512), "azul_plate": (160, 160),
    "azul_plate_center": (160, 160), "azul_board": (384, 288),
    "azul_track_ring": (512, 512), "azul_chip": (64, 64), "azul_floor": (48, 48),
    **{f"azul_tile_{c}": (48, 48) for c in "rwbyk"},
    **{f"azul_wall_cell_{c}": (48, 48) for c in "rwbyk"},
    **{f"azul_marker_{c}": (40, 40) for c in "rwbyk"},
}


def test_azul_assets_expose_exactly_expected_keys():
    assert set(_art.ASSETS) == set(_EXPECTED_WH)
    assert len(_art.ASSETS) == 22


def test_azul_legacy_web_keys_are_gone():
    """第二批：网页端已改用新键，旧键与其生成函数一并删除。"""
    from boardgames.azul import sprites as sp
    for k in ("azul_table", "azul_boardface", "azul_track"):
        assert k not in _art.ASSETS, k
        assert not hasattr(sp, "make_legacy_" + {"azul_table": "table",
                                                  "azul_boardface": "boardface",
                                                  "azul_track": "track"}[k]), k


def test_azul_wall_bg_is_seamless():
    raw = base64.b64decode(_art.ASSETS["azul_wall_bg"].split(",", 1)[1])
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    p = 512 // 4                      # ornament_tile(cells=4) ⇒ 周期 128
    for x, y in ((64, 64), (96, 160), (128, 224)):     # 取样远离边缘
        assert img.getpixel((x, y)) == img.getpixel((x + p, y))
        assert img.getpixel((x, y)) == img.getpixel((x, y + p))


@pytest.mark.parametrize("key,wh", sorted(_EXPECTED_WH.items()))
def test_azul_asset_is_png_data_uri_with_expected_size(key, wh):
    url = _art.ASSETS[key]
    assert url.startswith("data:image/png;base64,")
    raw = base64.b64decode(url.split(",", 1)[1])
    img = Image.open(io.BytesIO(raw))
    assert img.size == wh
