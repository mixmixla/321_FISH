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


def test_azul_painter_consumes_package_assets():
    if cu._BG_ASSETS is None or cu._PILImage is None or cu._PILImageTk is None:
        pytest.skip("Pillow/Tk assets unavailable")
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    try:
        cv = tk.Canvas(root, width=820, height=580)
        cv.pack(); root.update_idletasks(); root.update()
        ui = {}
        cu.render(cv, "azul", _azul_state(), 7, lambda uid: f"P{uid}",
                  lambda m: None, lambda: None, ui, None,
                  cv.winfo_width(), cv.winfo_height())
        img_keys = {k[0] for k in getattr(cv, "_asset_img_cache", {})}
        nine_keys = {k[0] for k in getattr(cv, "_asset_nine_cache", {})}
        assert "azul_wall_bg" in img_keys       # 桌面底：无缝瓷砖墙（_asset_bg 走 img 缓存）
        assert "azul_board" in img_keys         # 玩家板面（元组尺寸 → 非正方形拉伸）
        assert "azul_plate" in img_keys         # 工厂盘
        assert "azul_plate_center" in img_keys  # 中央池
        assert "azul_track_ring" in img_keys    # 圆形计分轨
        assert "azul_marker_r" in img_keys      # 计分棋子（uid 7 → "r"）
        assert "azul_chip" in img_keys          # 分数筹码（信息条 + 板面铭牌行）
        assert "azul_floor" in img_keys         # 地板槽
        assert "azul_tile_r" in img_keys        # 花砖（自己第 1 行有红砖、工厂盘里也有）
    finally:
        try: root.destroy()
        except Exception: pass


def test_gemcity_painter_switches_felt_to_azulejo():
    if cu._BG_ASSETS is None or cu._PILImage is None or cu._PILImageTk is None:
        pytest.skip("Pillow/Tk assets unavailable")
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    try:
        cv = tk.Canvas(root, width=800, height=560)
        cv.pack()
        root.update_idletasks()
        root.update()
        ui = {}
        cu.render(cv, "gemcity", _gemcity_state(), 7, lambda uid: f"P{uid}",
                  lambda m: None, lambda: None, ui, None,
                  cv.winfo_width(), cv.winfo_height())
        cache = getattr(cv, "_asset_img_cache", {})
        assert ("azulejo", None) in cache
        assert ("felt", None) not in cache
    finally:
        try: root.destroy()
        except Exception: pass


# ------------------------------------------------- headless 键序遥测（新画师契约）
class _ProbeCanvas:
    """接收任意绘制调用的画布桩：只兜住属性、不做记录断言。"""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _call(*a, **k):
            self.calls.append(name)
            return None
        return _call


def test_azul_headless_painter_requests_all_new_keys(monkeypatch):
    """无 Tk / 无显示也验证：Azul 画师确实按新键集取材，且不再请求旧三键（本批仍生成、仅供网页端）。

    shell 组件是 `from client_gameui import _asset_at` 的**直接引用**，故必须同时
    打桩 `boardgames.shell` 与 `client_gameui` 两处，否则拿不到调用遥测。
    """
    from boardgames import shell as bshell

    asked = []

    def _rec_at(cv, key, x, y, size, anchor="nw"):
        asked.append(key)
        return False                     # 立刻失败 → 矢量回退，不触碰 ImageTk

    def _rec_bg(cv, key, x0, y0, x1, y1):
        asked.append(key)
        return False

    monkeypatch.setattr(bshell, "_asset_at", _rec_at)
    monkeypatch.setattr(bshell, "_asset_bg", _rec_bg)
    monkeypatch.setattr(cu, "_asset_at", _rec_at)
    monkeypatch.setattr(cu, "_asset_bg", _rec_bg)
    # 顶栏矢量游戏图标走 widgets.design_controls.game_icon_image（非 _asset_* 路径），
    # 桩画布非真 Tk、无 tk.call，故短路 `_banner_icon`，使本遥测不依赖 Tk。
    monkeypatch.setattr(cu, "_banner_icon", lambda *a, **k: None)
    cv = _ProbeCanvas()
    cu.render(cv, "azul", _azul_state(), 7, lambda uid: f"P{uid}",
              lambda msg: None, lambda: None, {}, None, 900, 640)
    for k in ("azul_wall_bg", "azul_board", "azul_plate", "azul_plate_center",
              "azul_track_ring", "azul_marker_r", "azul_chip", "azul_floor",
              "azul_tile_r", "azul_wall_cell_b"):
        assert k in asked, k
    for k in ("azul_table", "azul_boardface", "azul_track"):
        assert k not in asked, k
