# -*- coding: utf-8 -*-
"""快艇骰子点击化：记分门禁纯函数与前后端接线静态断言。"""
import pathlib

import client_gameui as cu
from games_pkg.yahtzee import YahtzeeGame

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _rolled_state():
    g = YahtzeeGame([1, 2], seed=1)
    g.act(1, {"op": "roll"})
    return g.snapshot()


def test_can_score_false_before_roll():
    g = YahtzeeGame([1, 2], seed=1)
    assert cu._yz_can_score(g.snapshot(), "1", 1) is False


def test_can_score_true_after_roll():
    assert cu._yz_can_score(_rolled_state(), "1", 1) is True


def test_can_score_false_when_turn_already_scored():
    st = _rolled_state()
    st["category"] = True
    assert cu._yz_can_score(st, "1", 1) is False


def test_can_score_false_when_category_taken():
    st = _rolled_state()
    st["scores"]["1"]["1"] = 3
    assert cu._yz_can_score(st, "1", 1) is False
    assert cu._yz_can_score(st, "2", 1) is True


def test_can_score_false_when_not_my_turn():
    st = _rolled_state()
    st["turn_uid"] = 2
    assert cu._yz_can_score(st, "1", 1) is False


def test_engine_snapshot_exposes_rolled():
    assert "rolled" in YahtzeeGame([1, 2], seed=1).snapshot()
    src = (ROOT / "games_pkg" / "yahtzee.py").read_text(encoding="utf-8")
    assert '"rolled": self.rolled' in src


def test_desktop_click_hotzones_and_registration_are_wired():
    src = (ROOT / "client_gameui.py").read_text(encoding="utf-8")
    assert '_CLICKS["yahtzee"] = _click_yahtzee' in src
    assert "yz_dice" in src and "yz_cats" in src and "yz_keep" in src


def test_web_keep_state_and_reroll_are_wired():
    src = (ROOT / "web.py").read_text(encoding="utf-8")
    assert "state.yzkeep" in src
    assert 'op:"reroll"' in src
