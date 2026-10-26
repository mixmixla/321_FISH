"""铁路点击认领：线段命中几何、热区登记与前后端接线静态断言。"""
import math
import pathlib

import client_gameui as cu
from games_pkg.tielu import TieluGame

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_seg_dist_hits_endpoints():
    assert cu._tl_seg_dist(0, 0, 0, 0, 10, 0) == 0
    assert cu._tl_seg_dist(10, 0, 0, 0, 10, 0) == 0


def test_seg_dist_uses_projection_inside_segment():
    assert cu._tl_seg_dist(5, 3, 0, 0, 10, 0) == 3
    assert cu._tl_seg_dist(5, -4, 0, 0, 10, 0) == 4


def test_seg_dist_falls_back_to_nearest_endpoint_outside_segment():
    assert cu._tl_seg_dist(-5, 0, 0, 0, 10, 0) == 5
    assert cu._tl_seg_dist(15, 4, 0, 0, 10, 0) == math.hypot(5, 4)


def test_seg_dist_vertical_and_zero_length_segments():
    assert cu._tl_seg_dist(5, 5, 2, 2, 2, 8) == 3
    assert cu._tl_seg_dist(4, 5, 1, 1, 1, 1) == 5


class Canvas:
    def __init__(self):
        self.lines = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            if name == "create_line":
                self.lines.append(kwargs)
        return record


def tielu_scene(hand):
    game = TieluGame([1, 2], seed=1)
    st = game.snapshot()
    st["turn_uid"] = 1
    ui = {"game": "tielu", "state": st, "me": 1,
          "submit": lambda action: None, "repaint": lambda: None}
    cu._p_tielu(Canvas(), st, 1, lambda u: f"P{u}", ui["submit"],
                ui["repaint"], ui, {"hand": hand}, 920, 680)
    return st, ui


def test_painter_registers_affordable_unclaimed_routes():
    hand = {"red": 3, "yellow": 0, "green": 1, "blue": 0, "purple": 5}
    st, ui = tielu_scene(hand)
    assert len(ui["tl_routes"]) == len(st["routes"])
    for (x0, y0, x1, y1, a, b, color, length, affordable) in ui["tl_routes"]:
        assert a in st["cities"] and b in st["cities"]
        assert affordable == (hand.get(color, 0) >= length)


def test_click_claims_nearest_affordable_route_only():
    sent, painted = [], []
    ui = {"state": {"status": "playing", "players": [1, 2], "turn_uid": 1,
                    "winner_uid": None},
          "me": 1, "submit": sent.append, "repaint": lambda: painted.append(1),
          "tl_routes": [(0, 0, 100, 0, 0, 7, "green", 5, True),
                        (0, 60, 100, 60, 1, 2, "red", 2, True)]}
    cu._click_tielu(ui, 50, 3)
    assert sent == [{"op": "claim", "a": 0, "b": 7}]
    assert painted


def test_click_ignores_unaffordable_far_and_out_of_turn():
    base = {"status": "playing", "players": [1, 2], "turn_uid": 1,
            "winner_uid": None}
    sent = []
    ui = {"state": base, "me": 1, "submit": sent.append,
          "tl_routes": [(0, 0, 100, 0, 0, 7, "green", 5, False),
                        (0, 100, 100, 100, 1, 2, "red", 2, True)]}
    cu._click_tielu(ui, 50, 3)        # 买不起
    cu._click_tielu(ui, 50, 140)      # 太远
    assert sent == []
    ui["state"] = dict(base, turn_uid=2)
    cu._click_tielu(ui, 50, 103)
    assert sent == []
    ui["state"] = dict(base, winner_uid=2)
    cu._click_tielu(ui, 50, 103)
    assert sent == []


def test_desktop_click_registration_is_wired():
    src = (ROOT / "client_gameui.py").read_text(encoding="utf-8")
    assert '_CLICKS["tielu"] = _click_tielu' in src
    assert "tl_routes" in src
    assert "_tl_seg_dist" in src


def test_web_svg_map_and_claim_wiring():
    src = (ROOT / "web.py").read_text(encoding="utf-8")
    start = src.index("tielu(box,s){")
    section = src[start:src.index("gongfang(box,s){", start)]
    assert "stroke-width" in section
    assert 'op:"claim"' in section
    assert "opacity:.35" in section
    assert "<svg" in section and "viewBox='0 0 340 260'" in section
    assert "transparent" in section and "data-tla" in section
