# -*- coding: utf-8 -*-
"""原始桌游对局美术素材契约（P3）。

素材全部由 _gen_boardgame.py 程序化生成（原创，无外部/网络素材依赖），
产物为 assets/boardgame/*.png 与内嵌模块 _art_boardgame.py。

该测试断言：
  1. _art_boardgame.ASSETS 结构（29 个键、值均为 PNG data URL）；
  2. 每键解码后的像素尺寸符合生成器规格；
  3. assets/boardgame/<key>.png 源文件存在、非空，且与模块内嵌 base64 像素一致
     （源文件默认保存、内嵌为 optimize=True 压缩，故只比对解码后的像素）。

不引入屏幕截图，仅做纯结构与字节校验，故可在无 Tk 的 CI 环境默认运行。
"""

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import _art_boardgame  # noqa: E402


# key -> (w, h)，与 _gen_boardgame.py 各 make_* 默认参数保持一致。
_EXPECTED_WH = {
    "wood": (256, 256),
    "felt": (256, 256),
    "paper": (256, 256),
    "card_frame": (96, 136),
    "card_back": (96, 136),
    "coin": (48, 48),
    "token": (40, 40),
    "panel": (60, 60),
    "azul_bowl": (128, 128),
    "azulejo": (256, 256),
    "azul_board": (96, 96),
    "azul_score_track": (96, 48),
}
for _n in range(1, 7):
    _EXPECTED_WH[f"die_face{_n}"] = (48, 48)
for _k in ("b", "k", "r", "w", "y"):
    _EXPECTED_WH[f"azul_tile_{_k}"] = (44, 44)
for _k in ("o", "d", "r", "e", "s", "g"):
    _EXPECTED_WH[f"gem_{_k}"] = (40, 40)

_PNG_PREFIX = "data:image/png;base64,"


def _payload(data_url):
    assert data_url.startswith(_PNG_PREFIX), "素材值必须是 PNG data URL"
    return data_url[len(_PNG_PREFIX):]


def test_assets_module_exposes_exactly_expected_keys():
    assert set(_art_boardgame.ASSETS) == set(_EXPECTED_WH)
    assert len(_art_boardgame.ASSETS) == 29


def test_every_asset_is_decodable_png_of_expected_size():
    from PIL import Image
    import io

    assert _art_boardgame.ASSETS, "ASSETS 不能为空"
    for key, (w, h) in _EXPECTED_WH.items():
        raw = base64.b64decode(_payload(_art_boardgame.ASSETS[key]))
        assert raw[:8] == b"\x89PNG\r\n\x1a\n", f"{key}: 非 PNG magic"
        with Image.open(io.BytesIO(raw)) as im:
            assert im.size == (w, h), f"{key}: 尺寸 {im.size} != ({w}, {h})"


def test_assets_dir_png_matches_embedded_pixels():
    from PIL import Image
    import io

    out_dir = ROOT / "assets" / "boardgame"
    assert out_dir.is_dir(), "assets/boardgame 目录缺失"
    for key in _EXPECTED_WH:
        path = out_dir / f"{key}.png"
        assert path.is_file(), f"缺少素材源文件 {path.name}"
        raw = path.read_bytes()
        assert raw, f"{path.name} 为空文件"
        embedded = base64.b64decode(_payload(_art_boardgame.ASSETS[key]))
        with Image.open(io.BytesIO(raw)) as a, \
                Image.open(io.BytesIO(embedded)) as b:
            assert a.size == b.size, f"{path.name}: 源文件与内嵌尺寸不一致"
            assert a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes(), \
                f"{path.name} 与内嵌 base64 像素不一致（需重跑生成器）"
