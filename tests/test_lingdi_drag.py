# -*- coding: utf-8 -*-
"""领地（卡卡颂）拖拽投放 + 旋转：引擎旋转规则 / 桌面拖拽门禁 / 网页静态接线。

全 headless：画布桩无字符串 _gkey，素材入口一律短路；引擎与客户端镜像规则
逐例对拍，避免客户端误拒合法落点或放过非法旋转。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import client_gameui as cu  # noqa: E402
from games_pkg.base import GameRuleError  # noqa: E402
from games_pkg.lingdi import DIRS, LingdiGame, _rot_edges  # noqa: E402


def _edges(main="f", **over):
    e = {d: main for d in DIRS}
    e.update(over)
    return e


def _tile(main="f", **over):
    return {"edges": _edges(main, **over), "owner": None}


class Canvas:
    """记录绘制调用的画布桩；delete 单独记录以便断言幽灵清理。"""

    def __init__(self):
        self.calls = []
        self.deleted = []

    def delete(self, *tags):
        self.deleted.append(tags)

    def __getattr__(self, name):
        def _rec(*a, **k):
            self.calls.append((name, a, k))
            return len(self.calls)
        return _rec


# --------------------------------------------------------------- 引擎旋转
def test_rot_edges_clockwise_and_identity_after_four():
    e = {"N": "n", "E": "e", "S": "s", "W": "w"}
    assert _rot_edges(e, 0) == e
    assert _rot_edges(e, 1) == {"N": "w", "E": "n", "S": "e", "W": "s"}
    r = e
    for _ in range(4):
        r = _rot_edges(r, 1)
    assert r == e
    assert _rot_edges(e, 4) == e


def _rot_game():
    g = LingdiGame([1, 2], seed=1)
    g.board = {(4, 4): _tile("f", S="r")}
    g.current = {"edges": _edges("c", W="r")}      # rot=1 后 N=r
    g.turn = 0
    return g


def test_place_with_rot_stores_rotated_edges():
    g = _rot_game()
    g.act(1, {"op": "place", "r": 5, "c": 4, "rot": 1})
    assert g.board[(5, 4)]["edges"] == {"N": "r", "E": "c", "S": "c", "W": "c"}
    assert g.board[(4, 4)]["edges"]["S"] == "r"    # 邻块未被改写


def test_rot_matching_accepts_only_correct_orientation():
    g = _rot_game()
    with pytest.raises(GameRuleError):              # rot=0：N=c 与邻块 S=r 不符
        g.act(1, {"op": "place", "r": 5, "c": 4})
    assert (5, 4) not in g.board
    g.act(1, {"op": "place", "r": 5, "c": 4, "rot": 1})
    assert (5, 4) in g.board


def test_invalid_rot_rejected_without_touching_board():
    for bad in (4, -1, "x"):
        g = _rot_game()
        before = {k: dict(v) for k, v in g.board.items()}
        with pytest.raises(GameRuleError):
            g.act(1, {"op": "place", "r": 5, "c": 4, "rot": bad})
        assert g.board == before and (5, 4) not in g.board


def test_empty_board_any_cell_and_rotation_stored():
    g = LingdiGame([1, 2], seed=1)
    g.current = {"edges": _edges("c", E="r")}
    g.act(1, {"op": "place", "r": 0, "c": 8, "rot": 2})
    assert g.board[(0, 8)]["edges"] == {
        "N": "c", "E": "c", "S": "c", "W": "r"}


# ----------------------------------------------------- 客户端镜像规则
def test_client_rot_matches_engine_for_all_rots():
    e = {"N": "c", "E": "r", "S": "f", "W": "c"}
    for rot in range(4):
        assert cu._ld_rot_edges(e, rot) == _rot_edges(e, rot), rot


def _st(board=None, cur=None, size=9):
    return {"size": size,
            "board": board or {},
            "current": {"edges": cur or _edges("f")}}


def test_client_legal_empty_board_anywhere_but_in_bounds():
    st = _st()
    assert cu._ld_legal(st, 0, 0, 0)
    assert cu._ld_legal(st, 8, 8, 3)
    assert not cu._ld_legal(st, 9, 0, 0)
    assert not cu._ld_legal(st, 0, -1, 0)
    assert not cu._ld_legal(st, "x", 0, 0)


def test_client_legal_rejects_occupied_and_non_adjacent():
    st = _st({"4,4": _tile("f")})
    assert not cu._ld_legal(st, 4, 4, 0)            # 已占
    assert not cu._ld_legal(st, 0, 0, 0)            # 不相邻
    assert cu._ld_legal(st, 4, 5, 0)                # 相邻匹配


def test_client_legal_mismatch_and_rotated_match():
    st = _st({"4,4": _tile("f", S="r")}, cur=_edges("c", W="r"))
    assert not cu._ld_legal(st, 5, 4, 0)            # N=c 不匹配 S=r
    assert cu._ld_legal(st, 5, 4, 1)                # rot=1：N=旧W=r
    west = _st({"4,4": _tile("f", W="c")}, cur=_edges("f", E="c"))
    assert cu._ld_legal(west, 4, 3, 0)
    assert not cu._ld_legal(west, 4, 3, 2)


# --------------------------------------------------------- 桌面：重绘与拖拽
def _state():
    return {
        "game": "lingdi", "status": "playing", "size": 9, "turn_uid": 1,
        "players": [1, 2], "winner_uid": None, "deck_left": 5,
        "board": {"4,4": _tile("f")}, "current": {"edges": _edges("f")},
        "meeples": {"1": 3, "2": 3}, "score": {"1": 0, "2": 0},
    }


def _scene(w=900, h=640):
    st, sent, cv = _state(), [], Canvas()
    ui = {"game": "lingdi", "state": st, "room": {"status": "playing"},
          "me": 1, "submit": sent.append}

    def paint():
        cu._p_lingdi(cv, st, 1, lambda u: f"P{u}", sent.append, paint, ui,
                     None, w, h)

    ui["repaint"] = paint
    paint()
    return st, ui, sent, cv


def _center(rect):
    return ((rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0)


def _cell_center(ui, r, c):
    rect = next(x for x in ui["ld_cells"] if x[4] == r and x[5] == c)
    return _center(rect)


def test_painter_draws_fixed_nine_grid_and_preview_controls():
    _, ui, _, _ = _scene()
    assert len(ui["ld_cells"]) == 81
    assert ui["ld_src"] is not None
    assert ui["ld_rot_btn"] is not None and ui["ld_meeple_btn"] is not None
    assert ui["ld_rot"] == 0 and ui["ld_meeple"] is False
    assert ui["ld_ghost_cell"] is None
    # 空格也登记热区（空盘可见、可投放）
    assert _cell_center(ui, 0, 0) and _cell_center(ui, 8, 8)


def test_drag_from_preview_to_legal_cell_submits_place():
    _, ui, sent, cv = _scene()
    cu.handle_drag(cv, ui, *_center(ui["ld_src"]), "down")
    assert ui.get("ld_drag") is True
    cu.handle_drag(cv, ui, *_cell_center(ui, 4, 5), "move")
    assert ui["ld_ghost_cell"] == (4, 5)
    assert any(k.get("tags") == "ld_ghost"
               for n, _a, k in cv.calls if n == "create_rectangle")
    cu.handle_drag(cv, ui, *_cell_center(ui, 4, 5), "up")
    assert sent == [{"op": "place", "r": 4, "c": 5, "rot": 0}]
    assert ui["ld_rot"] == 0 and ui["ld_meeple"] is False
    assert ui["ld_ghost_cell"] is None


def test_drag_to_illegal_cell_never_submits():
    _, ui, sent, cv = _scene()
    down = _center(ui["ld_src"])
    cu.handle_drag(cv, ui, *down, "down")
    cu.handle_drag(cv, ui, *_cell_center(ui, 4, 4), "up")      # 已占
    assert sent == [] and ui.get("ld_drag") is False
    cu.handle_drag(cv, ui, *down, "down")
    cu.handle_drag(cv, ui, *_cell_center(ui, 0, 0), "up")      # 不相邻
    assert sent == [] and ui.get("ld_drag") is False


def test_drag_requires_own_turn_and_preview_hit():
    st, ui, sent, cv = _scene()
    ui["ld_drag"] = False
    cu.handle_drag(cv, ui, 880, 600, "down")                   # 空白处不起手
    assert not ui.get("ld_drag")
    st["turn_uid"] = 2
    cu.handle_drag(cv, ui, *_center(ui["ld_src"]), "down")
    assert not ui.get("ld_drag")


def test_rotation_and_meeple_toggle_affect_click_placement():
    st, ui, sent, _ = _scene()
    cu.handle_click(ui, *_center(ui["ld_rot_btn"]))
    assert ui["ld_rot"] == 1
    cu.handle_click(ui, *_center(ui["ld_meeple_btn"]))
    assert ui["ld_meeple"] is True
    cu.handle_click(ui, *_cell_center(ui, 4, 5))
    assert sent == [{"op": "place", "r": 4, "c": 5, "rot": 1,
                     "meeple": "self"}]
    assert ui["ld_rot"] == 0 and ui["ld_meeple"] is False


def test_click_illegal_or_off_turn_cell_does_nothing():
    st, ui, sent, _ = _scene()
    cu.handle_click(ui, *_cell_center(ui, 0, 0))               # 不相邻
    assert sent == []
    st["turn_uid"] = 2
    cu.handle_click(ui, *_cell_center(ui, 4, 5))               # 非本人回合
    assert sent == []


# ------------------------------------------------------------- 静态接线
def test_static_desktop_and_web_wiring():
    gui = (ROOT / "client_gameui.py").read_text(encoding="utf-8")
    assert "def _lingdi_drag(" in gui
    assert 'if game == "lingdi"' in gui
    assert "ld_cells" in gui and "ld_rot" in gui
    web_src = (ROOT / "web.py").read_text(encoding="utf-8")
    assert "data-ldr" in web_src
    assert "state.ldrot" in web_src
    assert '{op:"place"' in web_src
