# -*- coding: utf-8 -*-
"""Azul 展示包素材：键集、尺寸、data-URI 形态、PNG 可解码。"""
import base64
import io

import pytest

pytest.importorskip("PIL")
from PIL import Image

from boardgames.azul import _art

_EXPECTED_WH = {
    "azul_table": (128, 128), "azul_boardface": (256, 256),
    "azul_plate": (128, 128), "azul_track": (96, 48), "azul_floor": (48, 48),
    **{f"azul_wall_cell_{c}": (48, 48) for c in "rwbyk"},
    **{f"azul_tile_{c}": (44, 44) for c in "rwbyk"},
}


def test_azul_assets_expose_exactly_expected_keys():
    assert set(_art.ASSETS) == set(_EXPECTED_WH)
    assert len(_art.ASSETS) == 15


@pytest.mark.parametrize("key,wh", sorted(_EXPECTED_WH.items()))
def test_azul_asset_is_png_data_uri_with_expected_size(key, wh):
    url = _art.ASSETS[key]
    assert url.startswith("data:image/png;base64,")
    raw = base64.b64decode(url.split(",", 1)[1])
    img = Image.open(io.BytesIO(raw))
    assert img.size == wh
