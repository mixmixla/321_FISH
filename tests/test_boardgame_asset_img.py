# -*- coding: utf-8 -*-
"""原始桌游对局美术（P3）的渲染层接入契约。

覆盖两条路径：
  1. 真 Tk Canvas —— _asset_img/_asset_at/_asset_nine/_asset_nine_at/_asset_bg
     成功返回位图/True，且 render("azul"/"gemcity") 能画出含 image item 的对局画面；
  2. 假画布桩（headless）—— 所有素材入口返回 None/False 且不产生任何绘制调用，
     证明未触碰 ImageTk.PhotoImage(master=cv)，保持无显示环境安全。

真 Tk 不可用的机器报环境 skip（区别于 GUI 验证通过）；本测试只创建自有合成
画布与像素，不做屏幕截图。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import client_gameui as cu  # noqa: E402


class _StubCanvas:
    """最小画布桩：只记录绘制调用，绝不实例化 tk / ImageTk。"""

    def __init__(self):
        self.n = 0

    def create_image(self, *a, **k):
        self.n += 1

    def create_oval(self, *a, **k):
        self.n += 1


def _azul_state():
    return {
        "game": "azul", "status": "playing", "round": 2, "turn_uid": 7,
        "offers": [
            [{"c": "r", "n": 1}, {"c": "r", "n": 1}, {"c": "b", "n": 1},
             {"c": "w", "n": 1}],
            [{"c": "b", "n": 1}, {"c": "y", "n": 1}, {"c": "k", "n": 1}],
            [{"c": "y", "n": 1}, {"c": "y", "n": 1}, {"c": "r", "n": 1}],
        ],
        "center": [{"c": "w", "n": 1}, {"c": "k", "n": 1}, {"c": "b", "n": 1}],
        "rows": {"7": {"0": ["r"], "1": ["b", "b"]}, "8": {"0": ["y"]}},
        "wall": {"7": {"0,0": "b"}, "8": {}},
        "floor": {"7": 1, "8": 0},
        "score": {"7": 5, "8": 3},
        "players": [7, 8], "winner_uid": None,
    }


def _gemcity_state():
    return {
        "game": "gemcity", "status": "playing", "turn_uid": 7,
        "winner_uid": None,
        "bank": {"o": 4, "d": 4, "r": 4, "e": 4, "s": 4, "g": 5},
        "market": {
            "1": [{"tier": 1, "disc": "r", "pts": 0, "cost": {"r": 1}},
                  {"tier": 1, "disc": "d", "pts": 1, "cost": {"r": 2}},
                  {"tier": 1, "disc": "s", "pts": 0, "cost": {"e": 1}},
                  {"tier": 1, "disc": "e", "pts": 0, "cost": {"s": 1}}],
            "2": [{"tier": 2, "disc": "s", "pts": 2, "cost": {"s": 3}},
                  {"tier": 2, "disc": "r", "pts": 2, "cost": {"d": 3}},
                  {"tier": 2, "disc": "d", "pts": 1, "cost": {"o": 3}},
                  {"tier": 2, "disc": "e", "pts": 3, "cost": {"o": 4}}],
            "3": [{"tier": 3, "disc": "r", "pts": 4, "cost": {"r": 5}},
                  {"tier": 3, "disc": "d", "pts": 5, "cost": {"d": 6}},
                  {"tier": 3, "disc": "s", "pts": 4, "cost": {"s": 5}},
                  {"tier": 3, "disc": "e", "pts": 3, "cost": {"e": 4}}],
        },
        "tokens": {"7": {"r": 2, "s": 1}, "8": {"d": 1}},
        "discount": {"7": {"r": 1}, "8": {}},
        "score": {"7": 9, "8": 6},
        "nobles": [{"r": 3, "g": 3}],
        "players": [7, 8],
    }


# --------------------------------------------------------------- headless 桩
def test_asset_helpers_are_safe_on_headless_stub():
    """假画布桩：素材入口一律 None/False，且不产生任何绘制调用。"""
    st = _StubCanvas()
    assert cu._real_cv(st) is False
    assert cu._asset_img(st, "felt") is None
    assert cu._asset_at(st, "felt", 0, 0, 32) is False
    assert cu._asset_nine(st, "panel", 80, 40) is None
    assert cu._asset_nine_at(st, "panel", 0, 0, 80, 40) is False
    assert cu._asset_bg(st, "felt", 0, 0, 300, 200) is False
    assert st.n == 0, "桩画布不应收到任何绘制调用（headless 安全）"
    # 缺键解码短路返回 None（不依赖 Pillow / Tk）
    assert cu._decode_asset("no_such_key") is None


def test_decode_asset_produces_png_pixels():
    """_decode_asset 无 Tk 也能把内嵌 PNG 解码/缩放为 RGBA。"""
    if cu._PILImage is None or cu._BG_ASSETS is None:
        pytest.skip("Pillow 或内嵌素材模块不可用")
    assert cu._decode_asset("gem_r", 24).size == (24, 24)
    assert cu._decode_asset("gem_r", (30, 20)).size == (30, 20)
    felt = cu._decode_asset("felt")
    assert felt is not None and felt.size == (256, 256)
    assert felt.mode == "RGBA"


# --------------------------------------------------------------- 真 Tk 渲染
def test_real_tk_bitmap_helpers_and_render():
    if cu._BG_ASSETS is None or cu._PILImage is None or cu._PILImageTk is None:
        pytest.skip("Pillow / ImageTk / 内嵌素材模块不可用")
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.geometry("820x600+40+40")
    root.deiconify()
    cv = tk.Canvas(root, width=800, height=560, highlightthickness=0)
    cv.pack(fill="both", expand=True)
    try:
        root.update_idletasks()
        root.update()
        # 1) 旗舰对局渲染：画布上出现 image item（位图 / 矢量图标）
        for game, state in (("azul", _azul_state()),
                            ("gemcity", _gemcity_state())):
            ui = {}
            cu.render(cv, game, state, 7, lambda uid: f"P{uid}",
                      lambda msg: None, lambda: None, ui, None,
                      cv.winfo_width(), cv.winfo_height())
            items = cv.find_all()
            assert items, f"{game}: 画布为空"
            types = {}
            for it in items:
                t = cv.type(it)
                types[t] = types.get(t, 0) + 1
            assert types.get("image", 0) > 0, f"{game}: 未绘制任何位图/图标"
            assert types.get("text", 0) > 0, f"{game}: 未绘制任何文本"

        # 2) render 入口已写入 cv._gkey（真画布判定契约），此时低层素材入口成功
        assert cu._real_cv(cv) is True
        assert cu._asset_img(cv, "felt") is not None
        assert cu._asset_at(cv, "gem_r", 12, 12, 24) is True
        assert cu._asset_nine(cv, "panel", 80, 40) is not None
        assert cu._asset_nine_at(cv, "panel", 0, 0, 80, 40) is True
        assert cu._asset_bg(cv, "felt", 0, 0, 300, 200) is True
    finally:
        root.destroy()
