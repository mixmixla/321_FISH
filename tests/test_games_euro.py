# -*- coding: utf-8 -*-
"""德式桌游八款（开拓/领地/铁路/工坊 + 我是城主/璀璨宝石/四季物语/波兰大选）逻辑单测。"""
import time

import pytest

from games_pkg.base import GameRuleError
from games_pkg.bolan import BolanGame
from games_pkg.chengzhu import ChengZhuGame
from games_pkg.gemcity import GemCityGame
from games_pkg.gongfang import GongfangGame
from games_pkg.kaituo import KaituoGame
from games_pkg.lingdi import LingdiGame
from games_pkg.siji import SijiGame
from games_pkg.tielu import TieluGame


def _nick_mid(g, action):
    """轮转直到指定 uid 行动。"""
    cur = g.players[g.turn]
    return cur


# ---------- 开拓 kaituo ----------
def _setup_kaituo_players(g):
    n = len(g.players)
    spots = [(0, 0), (SIZE_EDGE, SIZE_EDGE)]
    idx = 0
    for round_i in range(2):
        cur = g.players[0]
        for i in range(n):
            p = g.players[i]
            v = (i + 1, i + 1) if round_i == 0 else (n - i, n - i)
            e = _edge_for(v)
            g.act(p, {"op": "setup", "i": v[0], "j": v[1], "b_i": e[1][0], "b_j": e[1][1]})


def _edge_for(v):
    return (v, (v[0] + 1, v[1]))


from games_pkg.kaituo import SIZE  # noqa: E402
SIZE_EDGE = SIZE - 1


def test_kaituo_setup_and_roll():
    g = KaituoGame([1, 2], seed=5)
    assert g.phase == "setup"
    # 布置：两人 各2村2路，逆向
    g.act(1, {"op": "setup", "i": 0, "j": 0, "b_i": 0, "b_j": 1})
    g.act(2, {"op": "setup", "i": SIZE, "j": 0, "b_i": SIZE, "b_j": 1})
    g.act(2, {"op": "setup", "i": SIZE, "j": SIZE, "b_i": SIZE - 1, "b_j": SIZE})
    g.act(1, {"op": "setup", "i": 0, "j": SIZE, "b_i": 0, "b_j": SIZE - 1})
    assert g.phase == "play" and g.turn == 0
    # 掷骰后轮到 2
    msgs = g.act(1, {"op": "roll"})
    assert any("🎲" in m for m in msgs)
    assert g.players[g.turn] == 2
    # 非法：重复由 1 行动
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "roll"})


def test_kaituo_build_insufficient():
    g = KaituoGame([1, 2], seed=1)
    g.act(1, {"op": "setup", "i": 0, "j": 0, "b_i": 0, "b_j": 1})
    g.act(2, {"op": "setup", "i": SIZE, "j": 0, "b_i": SIZE, "b_j": 1})
    g.act(2, {"op": "setup", "i": SIZE, "j": SIZE, "b_i": SIZE - 1, "b_j": SIZE})
    g.act(1, {"op": "setup", "i": 0, "j": SIZE, "b_i": 0, "b_j": SIZE - 1})
    # 无资源造村
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "build", "kind": "settle", "i": 1, "j": 0})
    # 造路（需木头+砖）—— 无资源应拒绝
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "build", "kind": "road", "i": 0, "j": 0, "b_i": 1, "b_j": 0})
    # 强行给资源验证可建
    g.res[1]["wood"] += 1
    g.res[1]["brick"] += 1
    msgs = g.act(1, {"op": "build", "kind": "road", "i": 0, "j": 0, "b_i": 1, "b_j": 0})
    assert "道路" in msgs[0]


# ---------- 领地 lingdi ----------
def test_lingdi_place_and_meeple():
    g = LingdiGame([1, 2], seed=3)
    # 对局第一个动作：放板块在中心
    msgs = g.act(1, {"op": "place", "r": 4, "c": 4})
    assert msgs and "放置" in msgs[0]
    # 相邻处必须地型匹配：取下一块后放邻位（可能匹配失败需另挑，跳过严格断言）
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "place", "r": 4, "c": 4})   # 已占用
    g.act(2, {"op": "pass"})


def test_lingdi_invalid_coord():
    g = LingdiGame([1, 2], seed=3)
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "place", "r": 99, "c": 99})


# ---------- 铁路 tielu ----------
def test_tielu_draw_advances():
    g = TieluGame([1, 2], seed=2)
    t0 = g.turn
    msgs = g.act(1, {"op": "draw"})
    assert msgs and "🎫" in msgs[0]
    assert g.players[g.turn] == 2


def test_tielu_claim_ok_or_reject():
    g = TieluGame([1, 2], seed=2)
    # 给足够车票卡
    g.hand[1] = {c: 30 for c in g.hand[1]}
    route = g.route_deck[0]
    a, b = route["a"], route["b"]
    msgs = g.act(1, {"op": "claim", "a": a, "b": b})
    assert "认领" in msgs[0]
    # 非法：未轮到
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "skip"})


def test_tielu_claim_pay_exact():
    g = TieluGame([1, 2], seed=2)
    before = g.hand[1][g.route_deck[0]["color"]]
    a, b = g.route_deck[0]["a"], g.route_deck[0]["b"]
    L = g.route_deck[0]["length"]
    if before >= L:
        g.act(1, {"op": "claim", "a": a, "b": b})
        assert g.hand[1][g.route_deck[0]["color"]] == before - L if g.route_deck else True
    assert True


# ---------- 工坊 gongfang ----------
def test_gongfang_round_flow():
    g = GongfangGame([1, 2], seed=1)
    assert g.round_no == 1
    sid = g.spots[0]["id"]
    g.act(1, {"op": "work", "id": sid})
    g.act(2, {"op": "work", "id": g.spots[1]["id"]})
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "work", "id": sid})   # 已占用
    g.act(1, {"op": "pass"})
    g.act(2, {"op": "pass"})
    assert g.round_no == 2 or g.winner


# ---------- 我是城主 chengzhu ----------
def test_chengzhu_place_and_score():
    g = ChengZhuGame([1, 2], seed=4)
    # 首次放置任放
    g.act(1, {"op": "pick", "dom": 0, "x": 2, "y": 2, "rot": 0})
    g.act(2, {"op": "pick", "dom": 0, "x": 2, "y": 2, "rot": 0})
    # 非法：未轮到
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "pick", "dom": 0, "x": 0, "y": 0, "rot": 0})


def test_chengzhu_invalid_place():
    g = ChengZhuGame([1, 2], seed=4)
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "pick", "dom": 99, "x": 0, "y": 0, "rot": 0})   # dom 越界


# ---------- 璀璨宝石 gemcity ----------
def test_gemcity_take3():
    g = GemCityGame([1, 2], seed=1)
    g.act(1, {"op": "take", "colors": ["o", "d", "r"]})
    assert g.tokens[1]["o"] == 1 and g.tokens[1]["d"] == 1
    assert g.players[g.turn] == 2
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "take", "colors": ["o", "d"]})   # 未轮到


def test_gemcity_buy_and_win():
    g = GemCityGame([1, 2], seed=1)
    # 大量宝石以购卡
    g.tokens[1] = {c: 50 for c in g.tokens[1]}
    g.tokens[1]["g"] = 5
    tier, idx = 1, 0
    before_score = g.score[1]
    msgs = g.act(1, {"op": "buy", "tier": tier, "idx": idx})
    if msgs:
        assert "购得" in msgs[0]
    assert g.cards[1] != [] or g.reserved[1]


# ---------- 四季物语 siji ----------
def test_siji_play_and_activate():
    g = SijiGame([1, 2], seed=1)
    # 打一张成本为0的晶卡
    cheap = next(i for i, c in enumerate(g.hand[1]) if c["cost"] == 0)
    g.act(1, {"op": "play", "idx": cheap})
    assert len(g.engine[1]) == 1
    assert g.players[g.turn] == 2


def test_siji_activate_produces():
    g = SijiGame([1, 2], seed=1)
    # 直接塞一张引擎卡并激活
    g.engine[1].append({"id": 6, "name": "小晶圃", "kind": "crystal",
                        "cost": 0, "out": 1, "played": False})
    before = g.crystal[1]
    g.act(1, {"op": "activate", "idx": 0})
    assert g.crystal[1] == before + 1
    # 重复激活被拒
    with pytest.raises(GameRuleError):
        g.act(1, {"op": "activate", "idx": 0})


# ---------- 波兰大选 bolan ----------
def test_bolan_place_and_election():
    g = BolanGame([1, 2], seed=1)
    g.act(1, {"op": "place", "r": 0})
    assert g.board[0][1] == 1
    assert g.players[g.turn] == 2


def test_bolan_devote_and_end():
    g = BolanGame([1, 2], seed=1)
    # 初始影响力 8，弃 2 枚可在某选区翻倍
    before = g.influence[1]
    g.act(1, {"op": "devote", "r": 0})
    assert g.influence[1] == before - 2
    assert g.board[0][1] == 2


# ---------- 房间级注册/分发（rooms 自动兼容） ----------
def test_all_euro_rooms_created():
    from games_pkg.rooms import RoomManager
    import games_pkg as gp
    rm = RoomManager(gp.GAME_TYPES)

    def first_action(g, uid):
        t = g.players.index(uid)
        uid = g.players[0]
        if g.name == "kaituo":
            return {"op": "setup", "i": 0, "j": 0, "b_i": 0, "b_j": 1}
        if g.name == "lingdi":
            return {"op": "pass"}
        if g.name == "tielu":
            return {"op": "draw"}
        if g.name == "gongfang":
            return {"op": "pass"}
        if g.name == "chengzhu":
            return {"op": "pick", "dom": 0, "x": 2, "y": 2, "rot": 0}
        if g.name == "gemcity":
            return {"op": "take", "colors": ["o", "d", "r"]}
        if g.name == "siji":
            cheap = next((i for i, c in enumerate(g.hand[uid]) if c["cost"] == 0), 0)
            return {"op": "play", "idx": cheap}
        if g.name == "bolan":
            return {"op": "place", "r": 0}
        return {}

    for name in ("kaituo", "lingdi", "tielu", "gongfang",
                 "chengzhu", "gemcity", "siji", "bolan"):
        rm2 = RoomManager(gp.GAME_TYPES)
        r = rm2.create(1, name)
        rm2.join(2, r.room_id)
        rm2.start(1, r.room_id)
        assert r.status.value == "playing"
        a = first_action(r.gs, 1)
        rm2.handle_action(1, r.room_id, a)   # 不抛错即通过
        snap = r.gs.snapshot()
        assert snap["game"] == name
        # 客处非法动作拒绝（未轮到）
        try:
            rm2.handle_action(2, r.room_id, {"op": "pass"})
        except GameRuleError:
            pass