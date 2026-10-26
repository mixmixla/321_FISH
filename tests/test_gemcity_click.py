"""璀璨宝石点击化：买卡能力镜像、筹码选择纯函数与前后端接线静态断言。"""
import pathlib

import client_gameui as cu

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_afford_applies_discount_before_tokens():
    card = {"cost": {"o": 2, "d": 2, "r": 1}}
    assert cu._gc_afford({"o": 2, "d": 2, "r": 1}, {}, card) is True
    # 折扣先抵扣：只需补剩余缺口
    assert cu._gc_afford({"o": 1, "d": 1}, {"o": 1, "d": 1, "r": 1}, card) is True
    # 折扣足以全免
    assert cu._gc_afford({}, {"o": 2, "d": 2, "r": 1}, card) is True


def test_afford_uses_gold_for_every_gap():
    card = {"cost": {"o": 2, "d": 1}}
    assert cu._gc_afford({"o": 2, "d": 0, "g": 1}, {}, card) is True
    # 折扣先抵 d，只剩 o 缺 1：1 枚金够用
    assert cu._gc_afford({"o": 1, "g": 1}, {"d": 1}, card) is True
    # 各色缺口总和 3 > 1 枚金：买不起
    assert cu._gc_afford({"o": 0, "g": 1}, {}, card) is False


def test_afford_rejects_when_gems_and_gold_short():
    card = {"cost": {"o": 3}}
    assert cu._gc_afford({"o": 2}, {}, card) is False
    assert cu._gc_afford({"o": 2, "g": 0}, {}, card) is False


def test_pick_three_distinct_colors_takes_once_then_clears():
    bank = {"o": 4, "d": 4, "r": 4, "e": 4, "s": 4, "g": 5}
    sel, action = cu._gc_pick([], "o", bank)
    assert sel == ["o"] and action is None
    sel, action = cu._gc_pick(sel, "d", bank)
    assert sel == ["o", "d"] and action is None
    sel, action = cu._gc_pick(sel, "r", bank)
    assert sel == [] and action == {"op": "take", "colors": ["o", "d", "r"]}


def test_pick_same_color_takes_two_only_when_bank_has_four():
    sel, action = cu._gc_pick(["o"], "o", {"o": 4})
    assert sel == [] and action == {"op": "take2", "color": "o"}


def test_pick_same_color_cancels_when_bank_below_four():
    sel, action = cu._gc_pick(["o"], "o", {"o": 3})
    assert sel == [] and action is None


def test_pick_fourth_color_does_not_grow_selection():
    sel, action = cu._gc_pick(["o", "d", "r"], "e", {"e": 4})
    assert sel == ["o", "d", "r"] and action is None


def test_desktop_click_registration_and_bank_hotzones():
    src = (ROOT / "client_gameui.py").read_text(encoding="utf-8")
    assert '_CLICKS["gemcity"] = _click_gemcity' in src
    assert "gc_bank" in src and "gc_cards" in src
    assert "gc_reserve" in src and "gc_reserved" in src
    assert "gc_take" in src                     # 取 1~2 颗的确认按钮


def test_web_click_selection_and_reserved_purchase():
    src = (ROOT / "web.py").read_text(encoding="utf-8")
    assert "state.gcsel" in src
    assert 'op:"buy_res"' in src and 'op:"reserve"' in src
    assert 'op:"take",colors:cur' in src        # 网页端“取选中的 N 颗”
    assert "renderGamePanel()" in src
