"""开拓（卡坦）点击化：相邻判定、选点状态机与前后端接线静态断言。"""
import pathlib

import client_gameui as cu

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_kt_adjacent_accepts_orthogonal_neighbours():
    assert cu._kt_adjacent((2, 2), (2, 3))
    assert cu._kt_adjacent((2, 2), (3, 2))
    assert cu._kt_adjacent((0, 0), (0, 1))


def test_kt_adjacent_rejects_same_diagonal_and_far():
    assert not cu._kt_adjacent((2, 2), (2, 2))
    assert not cu._kt_adjacent((2, 2), (3, 3))
    assert not cu._kt_adjacent((0, 0), (0, 2))


def test_pick_setup_takes_two_clicks_then_emits_setup():
    sel, action = cu._kt_pick("setup", None, (1, 1), {})
    assert sel == (1, 1) and action is None
    sel, action = cu._kt_pick("setup", sel, (1, 2), {})
    assert sel is None
    assert action == {"op": "setup", "i": 1, "j": 1, "b_i": 1, "b_j": 2}


def test_pick_road_builds_between_orthogonal_vertices():
    sel, action = cu._kt_pick("road", (2, 3), (2, 4), {})
    assert sel is None
    assert action == {"op": "build", "kind": "road", "i": 2, "j": 3,
                      "b_i": 2, "b_j": 4}


def test_pick_settle_and_city_are_single_click():
    assert cu._kt_pick("settle", None, (0, 5), {}) == (
        None, {"op": "build", "kind": "settle", "i": 0, "j": 5})
    assert cu._kt_pick("city", (1, 1), (4, 0), {}) == (
        None, {"op": "build", "kind": "city", "i": 4, "j": 0})


def test_pick_same_vertex_cancels_selection():
    assert cu._kt_pick("road", (3, 3), (3, 3), {}) == (None, None)
    assert cu._kt_pick("setup", (0, 2), (0, 2), {}) == (None, None)


def test_pick_non_adjacent_keeps_selection_without_action():
    assert cu._kt_pick("road", (1, 1), (3, 4), {}) == ((1, 1), None)
    assert cu._kt_pick("setup", (1, 1), (2, 3), {}) == ((1, 1), None)


def test_desktop_hotzones_and_click_registration_are_wired():
    src = (ROOT / "client_gameui.py").read_text(encoding="utf-8")
    assert '_CLICKS["kaituo"] = _click_kaituo' in src
    assert "kt_vertices" in src and "kt_tiles" in src and "kt_modes" in src
    assert '"op": "setup"' in src
    assert '"op": "robber"' in src


def test_web_overlay_mode_state_and_robber_click_are_wired():
    src = (ROOT / "web.py").read_text(encoding="utf-8")
    assert "state.ktmode" in src
    assert 'op:"robber"' in src
    assert "position:relative" in src
    assert "state.ktsel" in src
