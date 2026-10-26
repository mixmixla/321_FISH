# -*- coding: utf-8 -*-
"""四季物语 / 牛头王 点击化的桌面与网页接线静态断言（含假 ui 直调）。"""
import pathlib

import client_gameui as cu

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _sent(ui):
    box = []
    ui["submit"] = box.append
    return box


def _ui(state, **extra):
    ui = {"state": state, "room": {"status": "playing"}, "me": 1,
          "repaint": lambda: None}
    ui.update(extra)
    return ui


def test_desktop_source_registers_clicks_and_hotzones():
    src = (ROOT / "client_gameui.py").read_text(encoding="utf-8")
    assert '_CLICKS["siji"] = _click_siji' in src
    assert '_CLICKS["nimmt"] = _click_nimmt' in src
    for key in ("sj_hand", "sj_engine", "nm_hand"):
        assert f'ui["{key}"]' in src


def test_click_siji_engine_then_hand_and_gates():
    st = {"status": "playing", "players": [1, 2], "turn_uid": 1,
          "winner_uid": None}
    ui = _ui(st, sj_engine=[(10, 10, 50, 60, 0, False)],
             sj_hand=[(100, 10, 150, 60, 2)])
    box = _sent(ui)
    cu._click_siji(ui, 20, 20)
    assert box == [{"op": "activate", "idx": 0}]
    cu._click_siji(ui, 120, 20)
    assert box[-1] == {"op": "play", "idx": 2}
    # 已激活的引擎卡不发 activate
    ui["sj_engine"] = [(10, 10, 50, 60, 0, True)]
    n = len(box)
    cu._click_siji(ui, 20, 20)
    assert len(box) == n


def test_click_siji_rejects_when_not_my_turn_or_ended():
    st = {"status": "playing", "players": [1, 2], "turn_uid": 2,
          "winner_uid": None}
    ui = _ui(st, sj_hand=[(100, 10, 150, 60, 2)])
    box = _sent(ui)
    cu._click_siji(ui, 120, 20)
    assert box == []
    st["turn_uid"] = 1
    st["winner_uid"] = 1
    cu._click_siji(ui, 120, 20)
    assert box == []


def test_click_nimmt_choose_and_resolve_gate():
    st = {"status": "playing", "players": [1, 2], "winner_uid": None,
          "phase": "choose", "chosen": {}}
    ui = _ui(st, nm_hand=[(10, 10, 50, 68, 42)])
    box = _sent(ui)
    cu._click_nimmt(ui, 20, 20)
    assert box == [{"op": "choose", "card": 42}]
    # 本轮已暗选 / 结算中：不再提交
    st["chosen"] = {"1": 1}
    cu._click_nimmt(ui, 20, 20)
    assert len(box) == 1
    st["chosen"] = {}
    st["phase"] = "resolve"
    cu._click_nimmt(ui, 20, 20)
    assert len(box) == 1


def test_web_siji_has_clickable_hand_and_engine():
    src = (ROOT / "web.py").read_text(encoding="utf-8")
    seg = src.split("siji(box,s){", 1)[1].split("bolan(box,s){", 1)[0]
    assert 'op:"play",idx' in seg
    assert 'op:"activate",idx' in seg
    assert "data-sjhand" in seg and "data-sjeng" in seg
    assert "myTurn" in seg


def test_web_nimmt_guards_chosen():
    src = (ROOT / "web.py").read_text(encoding="utf-8")
    seg = src.split("nimmt(box,s){", 1)[1].split("davinci(box,s){", 1)[0]
    assert "s.chosen" in seg
    assert 'op:"choose",card' in seg
