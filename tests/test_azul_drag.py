# -*- coding: utf-8 -*-
"""花砖物语拖拽取砖：热区（画与命中同源）→ 客户端门禁 → 既有 take/place/floor 契约。

全 headless：画布桩无字符串 _gkey，故 `_real_cv` 为 False，素材入口一律短路，
不触碰 ImageTk.PhotoImage(master=cv)。合法行判定与引擎 `AzulGame._place` 逐格对拍，
确保客户端镜像规则写错时不会静默拒掉合法落点（拒掉＝玩家没法出牌）。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import client_gameui as cu  # noqa: E402
from boardgames.azul import desktop as az  # noqa: E402


def _nick(uid):
    return f"P{uid}"


class Probe:
    """记录绘制调用的画布桩；无 _gkey 字符串 → 素材入口一律短路（headless 安全）。"""

    def __init__(self):
        self.calls = []

    def _rec(self, name, *a, **k):
        self.calls.append((name, a, k))
        return len(self.calls)

    def create_rectangle(self, *a, **k):
        return self._rec("create_rectangle", *a, **k)

    def create_oval(self, *a, **k):
        return self._rec("create_oval", *a, **k)

    def __getattr__(self, name):
        def _f(*a, **k):
            self.calls.append((name, a, k))
            return None
        return _f


def _state(**over):
    """一份可用的对局快照：7 号轮到、地板 1、墙上 (0,0) 已占（故第 1 行对红砖非法）。"""
    st = {
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
        "floor": {"7": 1, "8": 0}, "score": {"7": 5, "8": 3},
        "players": [7, 8], "winner_uid": None, "bag": 40,
    }
    st.update(over)
    return st


def _ui(st, sent, cv=None):
    ui = {"game": "azul", "state": st, "room": {"status": "playing"},
          "me": 7, "connected": True, "submit": sent.append}
    if cv is not None:
        ui["repaint"] = lambda: cu.render(
            cv, "azul", st, 7, _nick, sent.append, ui["repaint"], ui, None, 900, 640)
    return ui


# ------------------------------------------------------------ 画师：热区与归堆
def test_pile_groups_center_by_color_in_engine_color_order():
    tiles = [{"c": "k", "n": 1}, {"c": "r", "n": 1}, {"c": "k", "n": 1}]
    assert az._pile(tiles) == [{"c": "r", "n": 1}, {"c": "k", "n": 2}]
    assert az._pile([]) == []
    assert az._pile(None) == []


def test_ring_hits_cover_every_tile_and_carry_its_color():
    hits = az._ring_hits(100.0, 100.0, 30.0, [{"c": "r"}, {"c": "r"}, {"c": "b"}], 2)
    assert [h[4] for h in hits] == [2, 2, 2]          # 同盘同源
    assert [h[5] for h in hits] == ["r", "r", "b"]    # 每片砖各带自己的色
    x0, y0, x1, y1, _s, _c = hits[2]
    assert cu._azul_src_at({"azul_src": hits}, (x0 + x1) / 2, (y0 + y1) / 2) \
        == (2, "b")
    assert cu._azul_src_at({"azul_src": hits}, 900, 900) is None
    assert cu._azul_src_at({}, 10, 10) is None


def test_src_hit_prefers_nearest_tile_when_regions_overlap():
    ui = {"azul_src": [(0, 0, 20, 20, 0, "r"), (14, 0, 34, 20, "center", "b")]}
    assert cu._azul_src_at(ui, 14, 10) == (0, "r")
    assert cu._azul_src_at(ui, 20, 10) == ("center", "b")


def test_dst_hit_rows_are_half_open_and_floor_is_the_last_band():
    ui = {"azul_dst": [(0, 0, 100, 10, 0), (0, 10, 100, 20, 1), (0, 20, 100, 30, -1)]}
    assert cu._azul_dst_at(ui, 50, 9.9) == 0
    assert cu._azul_dst_at(ui, 50, 10) == 1          # 下边界归下一带，不双命中
    assert cu._azul_dst_at(ui, 100, 25) == -1
    assert cu._azul_dst_at(ui, 100.1, 25) is None
    assert cu._azul_dst_at({}, 10, 10) is None


# ------------------------------------------------------- 客户端行规则 vs 引擎
def _engine_place_ok(r0, c0, col):
    """引擎能否把 col 落在第 r0 行（墙 (r0,c0) 已被同色占位时该色应被拒）。"""
    from games_pkg.azul import AzulGame
    from games_pkg.base import GameRuleError

    g = AzulGame([7, 8], seed=3)
    if c0 is not None:
        g.wall[7][(r0, c0)] = "w"
    try:
        g.pending = [col]
        g._place(7, {"row": r0})
        return True
    except GameRuleError:
        return False


@pytest.mark.parametrize("col", ["r", "w", "b", "y", "k"])
def test_row_rule_matches_engine_on_empty_wall(col):
    from games_pkg.azul import AzulGame

    snap = AzulGame([7, 8], seed=3).snapshot()
    for m in range(5):
        assert az._row_ok(snap["rows"]["7"], snap["wall"]["7"], m, col) is True
        assert _engine_place_ok(m, None, col) is True


@pytest.mark.parametrize(("r0", "c0"), [(r, c) for r in range(5) for c in range(5)])
def test_row_rule_matches_engine_on_occupied_wall_cell(r0, c0):
    """逐格对拍：拉丁方落点被占时，客户端必须与引擎一致地拒掉那一个色。"""
    from games_pkg.azul import AzulGame

    snap = AzulGame([7, 8], seed=3).snapshot()
    snap["wall"]["7"][f"{r0},{c0}"] = "w"
    for col in "rwbyk":
        assert az._row_ok(snap["rows"]["7"], snap["wall"]["7"], r0, col) \
            is _engine_place_ok(r0, c0, col), (r0, c0, col)


def test_row_rule_rejects_row_holding_another_color():
    rows = {"1": ["b", "b"]}                 # 画师传的是“本人”那一份（per-player）
    assert az._row_ok(rows, {}, 1, "b") is True
    assert az._row_ok(rows, {}, 1, "r") is False
    assert az._row_ok({}, {}, 0, "not_a_color") is False


# ------------------------------------------------------------ 拖拽门禁与动作
def _dragged(ui, x=10, y=10):
    return "_azul_drag" in ui


def test_drag_needs_my_turn_playing_sitting_player_and_connection():
    for over, key in (({"turn_uid": 8}, "turn"), ({"winner_uid": 8}, "winner"),
                      ({"players": [8, 9]}, "spectator")):
        st = _state(**over)
        ui = _ui(st, [])
        ui["azul_src"] = [(0, 0, 20, 20, 0, "r")]
        cu.handle_drag(None, ui, 10, 10, "down")
        assert not _dragged(ui), key
    for over in ({"connected": False},):
        ui = _ui(_state(), [])
        ui.update(over)
        ui["azul_src"] = [(0, 0, 20, 20, 0, "r")]
        cu.handle_drag(None, ui, 10, 10, "down")
        assert not _dragged(ui)
    ui = _ui(_state(), [])
    ui["room"] = {"status": "waiting"}
    ui["azul_src"] = [(0, 0, 20, 20, 0, "r")]
    cu.handle_drag(None, ui, 10, 10, "down")
    assert not _dragged(ui)


def test_drag_down_on_blank_never_starts_and_never_submits():
    sent = []
    ui = _ui(_state(), sent)
    ui["azul_src"] = [(0, 0, 20, 20, 0, "r")]
    ui["azul_dst"] = [(0, 100, 100, 110, 0)]
    cu.handle_drag(None, ui, 80, 80, "down")
    assert not _dragged(ui)
    cu.handle_drag(None, ui, 50, 105, "up")
    assert sent == []


def test_drag_release_on_row_submits_take_then_place():
    sent = []
    ui = _ui(_state(), sent)
    ui["azul_src"] = [(0, 0, 20, 20, 0, "r")]
    ui["azul_dst"] = [(0, 100, 100, 110, 0), (0, 110, 100, 120, 3)]
    ui["azul_ok"] = [3]
    cu.handle_drag(None, ui, 10, 10, "down")
    assert ui["_azul_drag"]["col"] == "r" and ui["_azul_drag"]["src"] == 0
    cu.handle_drag(None, ui, 50, 115, "move")
    assert ui["_azul_drag"]["row"] == 3
    cu.handle_drag(None, ui, 50, 115, "up")
    assert sent == [{"op": "take", "src": 0, "col": "r"},
                    {"op": "place", "row": 3}]
    assert not _dragged(ui) and "azul_ok" not in ui


def test_drag_release_on_floor_submits_take_then_floor():
    sent = []
    ui = _ui(_state(), sent)
    ui["azul_src"] = [(0, 0, 20, 20, "center", "k")]
    ui["azul_dst"] = [(0, 100, 100, 110, 0), (0, 110, 100, 120, -1)]
    ui["azul_ok"] = [-1]
    cu.handle_drag(None, ui, 10, 10, "down")
    cu.handle_drag(None, ui, 50, 115, "up")
    assert sent == [{"op": "take", "src": "center", "col": "k"},
                    {"op": "floor"}]


def test_drag_release_off_target_or_on_illegal_row_submits_nothing():
    sent = []
    ui = _ui(_state(), sent)
    ui["azul_src"] = [(0, 0, 20, 20, 0, "r")]
    ui["azul_dst"] = [(0, 100, 100, 110, 0), (0, 110, 100, 120, 1)]
    ui["azul_ok"] = []                              # 两行都被墙格/异色占住
    cu.handle_drag(None, ui, 10, 10, "down")
    cu.handle_drag(None, ui, 50, 105, "up")         # 抬手落在非法行上
    assert sent == [] and not _dragged(ui)
    cu.handle_drag(None, ui, 10, 10, "down")
    cu.handle_drag(None, ui, 500, 500, "up")        # 抬手落在空白处
    assert sent == [] and not _dragged(ui)


def test_drag_up_without_down_is_ignored():
    sent = []
    ui = _ui(_state(), sent)
    ui["azul_dst"] = [(0, 100, 100, 110, 0)]
    cu.handle_drag(None, ui, 50, 105, "up")
    cu.handle_drag(None, ui, 50, 105, "move")
    assert sent == []


# ------------------------------------------------- 画与命中同源（走真画师渲染）
def _hide_banner_icon(monkeypatch):
    """顶栏矢量图标走 design_controls 的 PhotoImage(master=cv)，桩画布非真 Tk → 短路。"""
    monkeypatch.setattr(cu, "_banner_icon", lambda *a, **k: None)


def test_painter_regions_and_drag_round_trip(monkeypatch):
    _hide_banner_icon(monkeypatch)
    sent = []
    cv = Probe()
    st = _state()
    ui = _ui(st, sent, cv)
    cu.render(cv, "azul", st, 7, _nick, sent.append, ui["repaint"], ui, None,
              900, 640)

    src_hits = ui["azul_src"]
    assert {h[4] for h in src_hits} >= {0, 1, 2, "center"}
    assert [h[4] for h in ui["azul_dst"]] == [0, 1, 2, 3, 4, -1]
    assert all(h[1] < h[3] for h in ui["azul_dst"])

    # 抓工厂盘 0 的红砖：墙 (0,0) 已占 + 第 2 行是蓝砖 → 只剩 2/3/4 行与地板可落。
    src = [h for h in src_hits if h[4] == 0 and h[5] == "r"][0]
    cu.handle_drag(cv, ui, (src[0] + src[2]) / 2, (src[1] + src[3]) / 2, "down")
    assert ui["_azul_drag"]["col"] == "r"
    assert ui["azul_ok"] == [2, 3, 4, -1]

    dst = [h for h in ui["azul_dst"] if h[4] == 3][0]
    x, y = (dst[0] + dst[2]) / 2, dst[1] + 1.0
    cu.handle_drag(cv, ui, x, y, "move")
    assert ui["_azul_drag"]["row"] == 3
    assert any(k.get("tags") == "azul_ghost"
               for n, _a, k in cv.calls if n == "create_oval")
    cu.handle_drag(cv, ui, x, y, "up")
    assert sent == [{"op": "take", "src": 0, "col": "r"},
                    {"op": "place", "row": 3}]


def test_painter_draws_no_ghost_without_an_active_drag(monkeypatch):
    _hide_banner_icon(monkeypatch)
    cv = Probe()
    st = _state()
    ui = _ui(st, [], cv)
    cu.render(cv, "azul", st, 7, _nick, lambda _m: None, ui["repaint"], ui, None,
              900, 640)
    assert ui.get("_azul_drag") is None
    assert not any(k.get("tags") == "azul_ghost"
                   for n, _a, k in cv.calls if n == "create_oval")


def test_painter_keeps_offering_tile_assets_for_every_visible_color(monkeypatch):
    """中央池归堆后仍逐色取材；>10 片也不再把某些色截断到看不见（不可拖）。"""
    from boardgames import shell as bshell

    asked = []

    def _rec_at(_cv, key, *_a, **_k):
        asked.append(key)
        return False

    monkeypatch.setattr(bshell, "_asset_at", _rec_at)
    monkeypatch.setattr(cu, "_asset_at", _rec_at)
    monkeypatch.setattr(cu, "_banner_icon", lambda *a, **k: None)
    st = _state(center=[{"c": c, "n": 6} for c in "rwbyk"])
    ui = _ui(st, [], None)
    cu.render(Probe(), "azul", st, 7, _nick, lambda _m: None, lambda: None, ui,
              None, 900, 640)
    for c in "rwbyk":
        assert f"azul_tile_{c}" in asked, c
