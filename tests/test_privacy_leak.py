# -*- coding: utf-8 -*-
"""夜间/手牌信息隔离回归：公开快照不得再暴露四季手牌与狼人杀夜间行动者。"""
from pathlib import Path

from games_pkg.siji import SijiGame
from games_pkg.onewolf import (OneNightWolfGame, ROBBER as OW_ROBBER,
                               SEER as OW_SEER, VILLAGER as OW_VILLAGER)
from games_pkg.werewolf import (SEER, VILLAGER, WEREWOLF,
                                WerewolfGame)

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- 四季物语
def test_siji_snapshot_hides_hands_but_keeps_counts():
    """回归：此前 snapshot 广播所有人的手牌，等于把对手手牌公开。"""
    g = SijiGame([1, 2], seed=1)
    snap = g.snapshot()
    assert "hand" not in snap
    assert snap["hand_count"] == {"1": 6, "2": 6}
    mine = g.private(1)
    assert [c["id"] for c in mine["hand"]] == [c["id"] for c in g.hand[1]]
    other = g.private(2)
    assert [c["id"] for c in other["hand"]] == [c["id"] for c in g.hand[2]]


def test_siji_ui_reads_hand_from_private_channel():
    """两端必须从私密通道取手牌，不能再读公开快照的 hand。"""
    web = (ROOT / "web.py").read_text(encoding="utf-8")
    gui = (ROOT / "client_gameui.py").read_text(encoding="utf-8")
    assert "state.gpriv&&state.gpriv.hand" in web
    assert 'const hand=(s.hand[state.uid]' not in web
    assert '(priv or {}).get("hand")' in gui


# ---------------------------------------------------------------- 狼人杀
def test_werewolf_snapshot_no_longer_exposes_night_actors():
    """回归：此前 snapshot 带 need/acted，谁在夜里行动就等于公开了预言家/狼人/女巫。"""
    g = WerewolfGame(list(range(1, 7)), seed=1)
    snap = g.snapshot()
    assert "need" not in snap and "acted" not in snap
    assert snap["phase"] == "night_seer"

    seer = next(u for u in g.players if g.role[u] == SEER)
    wolf = next(u for u in g.players if g.role[u] == WEREWOLF)
    villager = next(u for u in g.players if g.role[u] == VILLAGER)

    assert g.private(seer)["can_act"] is True
    assert g.private(wolf)["can_act"] is False
    assert g.private(villager)["can_act"] is False

    target = next(u for u in g.alive if u != seer)
    g.act(seer, {"target": target})
    assert g.phase == "night_wolf"                 # _pump 自动推进
    assert g.snapshot().get("phase") == "night_wolf"
    # 进入下一阶段后 acted 重置，seer 不再可行动
    assert g.private(seer)["can_act"] is False
    assert g.private(wolf)["can_act"] is True
    assert g.private(villager)["can_act"] is False


def test_werewolf_ui_uses_private_can_act():
    """两端行动按钮必须依据私密 can_act，而不是公开的 need/acted。"""
    web = (ROOT / "web.py").read_text(encoding="utf-8")
    gui = (ROOT / "client_gameui.py").read_text(encoding="utf-8")
    assert "pv.can_act" in web
    assert 'priv and priv.get("can_act")' in gui


# ---------------------------------------------------------------- 一夜狼人
def test_onewolf_snapshot_no_longer_exposes_night_actors():
    """回归：此前 snapshot 带 need_act/acted，等于公开谁是预言家/强盗。"""
    g = OneNightWolfGame(list(range(1, 6)), seed=1)
    snap = g.snapshot()
    assert "need_act" not in snap and "acted" not in snap

    seer = next(u for u in g.players if g.original[u] == OW_SEER)
    robber = next(u for u in g.players if g.original[u] == OW_ROBBER)
    villager = next(u for u in g.players if g.original[u] == OW_VILLAGER)

    assert g.private(seer)["can_act"] is True
    assert g.private(robber)["can_act"] is False     # 强盗须等预言家先行动
    assert g.private(villager)["can_act"] is False

    target = next(u for u in g.players if u != seer)
    g.act(seer, {"look_one": target})
    assert g.phase == "night"
    assert g.private(seer)["can_act"] is False
    assert g.private(robber)["can_act"] is True
    assert g.private(villager)["can_act"] is False

    g.act(robber, {"rob": target})
    assert g.phase == "vote"
    assert g.private(robber)["can_act"] is False
    assert "need_act" not in g.snapshot() and "acted" not in g.snapshot()


def test_onewolf_ui_uses_private_can_act():
    """桌面与网页都不得再读公开的 need_act/acted。"""
    web = (ROOT / "web.py").read_text(encoding="utf-8")
    gui = (ROOT / "client_gameui.py").read_text(encoding="utf-8")
    cli = (ROOT / "client.py").read_text(encoding="utf-8")
    assert "s.acted" not in web.split("onewolf(box,s){", 1)[1].split("werewolf(box,s){", 1)[0]
    assert 'st.get("need_act")' not in cli
    assert 'priv.get("can_act")' in gui
