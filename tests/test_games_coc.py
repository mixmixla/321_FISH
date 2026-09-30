# -*- coding: utf-8 -*-
"""COC 规则判定器单测：check_level 边界、选卡流程、begin 门槛、检定、掉线善后。"""
import pytest

from games_pkg.base import GameRuleError
from games_pkg.coc import CocGame, check_level, resolve_check, CHARS, _CHAR_BY_ID


def make(players, seed=0):
    return CocGame(list(players), seed=seed)


# ---- check_level 纯函数边界 ----
@pytest.mark.parametrize("roll,skill,expected", [
    (1, 50, "大成功"), (5, 50, "大成功"), (6, 50, "极难成功"),
    (20, 50, "极难成功"), (21, 50, "困难成功"), (50, 50, "困难成功"),
    (51, 60, "普通成功"), (60, 60, "普通成功"),
    (61, 60, "失败"), (95, 60, "失败"), (96, 60, "大失败"), (100, 60, "大失败"),
    (96, 96, "普通成功"),   # roll<=skill 优先于大失败
    (100, 100, "普通成功"),
])
def test_check_level(roll, skill, expected):
    assert check_level(roll, skill) == expected


@pytest.mark.parametrize("bad", [-1, 101])
def test_check_level_invalid(bad):
    with pytest.raises(ValueError):
        check_level(bad, 50)


def test_resolve_check_returns_valid():
    import random
    rng = random.Random(1)
    roll, level = resolve_check(70, rng)
    assert 1 <= roll <= 100
    assert level == check_level(roll, 70)


def test_chars_wellformed():
    assert len(CHARS) >= 6
    for c in CHARS:
        assert c["id"] in _CHAR_BY_ID
        assert {"STR", "DEX", "POW", "CON", "INT", "SIZ"} <= set(c["attrs"])
        assert c["sig"]


# ---- 实例化 / 基本快照 ----
def test_snapshot_setup():
    g = make([1, 2])
    s = g.snapshot()
    assert s["phase"] == "setup"
    assert s["kp_uid"] == 1
    assert s["picked"] == {}


def test_private_setup_deck():
    g = make([1, 2])
    p = g.private(1)
    assert "deck" in p
    assert len(p["deck"]) == len(CHARS)
    assert "attrs" not in p["deck"][0]   # 选卡阶段不泄露属性
    assert g.private(999) is None


# ---- 选卡流程 ----
def test_choose_card_then_begin():
    g = make([1, 2])
    first_id = g.chars[0]["id"]
    g.act(1, {"op": "choose_card", "card_id": first_id})
    assert g.assigned[1]["id"] == first_id
    # 同人重复选报错
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "choose_card", "card_id": first_id})
    # 选已被选走的卡报错
    with pytest.raises(GameRuleError):
        g.act(2, {"op": "choose_card", "card_id": first_id})
    # 未知卡 id
    with pytest.raises(GameRuleError):
        g.act(2, {"op": "choose_card", "card_id": "nope"})
    # 未完全员选卡，begin 门槛
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "begin"})
    # 玩家 2 选另一张
    g.act(2, {"op": "choose_card", "card_id": g.chars[1]["id"]})
    g.act(1, {"op": "begin"})
    assert g.phase == "play"


def test_begin_only_kp():
    g = make([1, 2, 3], seed=2)
    for u in (1, 2, 3):
        g.act(u, {"op": "choose_card", "card_id": g.chars[list(g.players).index(u)]["id"]})
    # 非 KP 不能 begin
    with pytest.raises(GameRuleError):
        g.act(2, {"op": "begin"})
    g.act(1, {"op": "begin"})
    assert g.phase == "play"


# ---- play 阶段：set_scene 权限 ----
def test_set_scene_only_kp():
    g = make([1, 2])
    for u, c in zip(g.players, g.chars):
        g.act(u, {"op": "choose_card", "card_id": c["id"]})
    g.act(1, {"op": "begin"})
    # 普通玩家不能设置场景
    with pytest.raises(GameRuleError):
        g.act(2, {"op": "set_scene", "scene": "hack"})
    g.act(1, {"op": "set_scene", "scene": "深宅大宅，烛影摇曳。"})
    assert g.scene == "深宅大宅，烛影摇曳。"
    assert "深宅大宅" in g.logs[-1]


# ---- play 阶段：检定 ----
def test_check_known_skill():
    g = make([1, 2])
    for u, c in zip(g.players, g.chars):
        g.act(u, {"op": "choose_card", "card_id": c["id"]})
    g.act(1, {"op": "begin"})
    skill = next(iter(g.assigned[1]["sig"]))
    g.act(1, {"op": "check", "skill": skill})
    assert any(skill in log for log in g.logs)


def test_check_unknown_skill_uses_base():
    g = make([1, 2])
    for u, c in zip(g.players, g.chars):
        g.act(u, {"op": "choose_card", "card_id": c["id"]})
    g.act(1, {"op": "begin"})
    g.act(1, {"op": "check", "skill": "铁匠"})   # 未知技能按 50
    assert any("铁匠" in log for log in g.logs)


def test_check_requires_card():
    g = make([1, 2])
    g.act(1, {"op": "choose_card", "card_id": g.chars[0]["id"]})
    g.act(2, {"op": "choose_card", "card_id": g.chars[1]["id"]})
    g.act(1, {"op": "begin"})
    # 强制剥离玩家 2 的卡后再检定应报错
    g.assigned.pop(2)
    with pytest.raises(GameRuleError):
        g.act(2, {"op": "check", "skill": "侦查"})


# ---- 私密信息（play 阶段展示 own card）----
def test_private_play_card():
    g = make([1, 2])
    for u, c in zip(g.players, g.chars):
        g.act(u, {"op": "choose_card", "card_id": c["id"]})
    g.act(1, {"op": "begin"})
    p = g.private(1)
    assert "card" in p
    assert "attrs" in p["card"] and "sig" in p["card"]


# ---- 掉线善后 ----
def test_player_left_releases_card_and_kp():
    g = make([1, 2, 3], seed=3)
    for u, c in zip(g.players, g.chars):
        g.act(u, {"op": "choose_card", "card_id": c["id"]})
    g.act(1, {"op": "begin"})
    g.player_left(1)   # KP 离开 → 移交 KP
    assert g.kp_uid == 2
    assert 1 not in g.players
    # 玩家离开后其卡释放为可再选（picked 清除）
    g.player_left(2)
    # 剩余 1 人 < min_players(2) → 结束
    assert g._ended


def test_player_left_setup_frees_card():
    g = make([1, 2])
    cid = g.chars[0]["id"]
    g.act(1, {"op": "choose_card", "card_id": cid})
    g.player_left(1)   # 选卡阶段离开，卡回牌堆
    assert cid not in g.picked


# ---- ended ----
def test_ended_kp_finish():
    g = make([1, 2])
    for u, c in zip(g.players, g.chars):
        g.act(u, {"op": "choose_card", "card_id": c["id"]})
    g.act(1, {"op": "begin"})
    assert g.ended() is None
    with pytest.raises(GameRuleError):
        g.act(2, {"op": "end"})   # 非 KP 不能结束
    g.act(1, {"op": "end"})
    assert g.ended() is not None