# -*- coding: utf-8 -*-
"""山屋惊魂（R29）纯逻辑测试：探索/预兆/惊魂检定/战斗/撤离/掉线善后"""
import json

from games_pkg import GAME_META, GAME_TYPES
from games_pkg.betrayal import BetrayalGame


class FakeRng:
    """确定性随机：randint 恒 1（惊魂检定必中 / 战斗最小点），choice 取首个"""

    def randint(self, a, b):
        return 1

    def choice(self, seq):
        return seq[0]

    def shuffle(self, x):
        pass

    def sample(self, seq, n):
        return list(seq)[:n]


def _bring_tile(g, kind):
    """把下一张要探索的房间牌换成指定类型（tiles 从末尾弹出）"""
    idx = next(i for i, (_, k) in enumerate(g.tiles) if k == kind)
    g.tiles.append(g.tiles.pop(idx))


def _reveal(g, kind, y=900):
    """白盒：把当前玩家挪到空旷处，向东走一步强制探索一张指定类型房间牌"""
    _bring_tile(g, kind)
    cur = g.players[g.turn_idx]
    g.pos[cur] = (900, y)
    return g.act(cur, {"move": "right"})


def test_registered_meta():
    assert "betrayal" in GAME_TYPES
    m = GAME_META["betrayal"]
    assert m["min"] == 3 and m["max"] == 6 and m["label"] == "山屋惊魂"


def test_snapshot_and_private_json_safe():
    g = BetrayalGame([1, 2, 3], seed=1)
    json.dumps(g.snapshot(), ensure_ascii=False)
    p = g.private(1)
    assert p and "stats" in p and p["side"] == "幸存者"
    assert g.private(99) is None


def test_explore_moves_and_reveals():
    g = BetrayalGame([1, 2, 3], seed=11)
    assert g.phase == "explore" and g.steps_left == 3
    msgs = _reveal(g, "item")
    assert any("发现" in m for m in msgs) and any("道具" in m for m in msgs)
    assert g.room_map[(901, 900)]
    assert g.steps_left == 2
    # 未轮到者不能动
    try:
        g.act(2, {"move": "up"})
        assert False, "应拒绝非当前玩家"
    except Exception:
        pass


def test_haunt_trigger_traitor_buff_and_exit():
    g = BetrayalGame([1, 2, 3], seed=5)
    g.rng = FakeRng()
    for i in range(8):
        msgs = _reveal(g, "omen", y=900 + i)
        if g.phase == "haunt":
            break
    assert g.phase == "haunt"
    t = g.haunt["traitor"]
    assert t in g.players
    assert g.stats[t]["might"] >= 5          # 3 + 2 附身加成
    ex = g.haunt["exit"]
    assert abs(ex[0]) + abs(ex[1]) >= 4 and ex not in g.room_map or \
        g.room_map.get(ex) == "出口之门"
    assert g.haunt["exit"] in g.room_map     # 出口之门已上地图
    st = json.loads(json.dumps(g.snapshot()))
    assert st["haunt"]["traitor"] == t and "exit" in st["haunt"]


def test_exploration_blocked_without_tiles():
    g = BetrayalGame([1, 2, 3], seed=2)
    g.tiles.clear()
    try:
        _reveal(g, "event")
        assert False, "房间牌用尽后应拒绝探索"
    except Exception:
        pass


def test_use_item_heal_and_passive():
    g = BetrayalGame([1, 2, 3], seed=3)
    g.items[1] = ["急救包", "消防斧", "圣水"]
    g.stats[1]["might"] = 1
    msgs = g.act(1, {"use": "急救包"})
    assert g.stats[1]["might"] == 3 and "急救包" not in g.items[1]
    msgs = g.act(1, {"use": "消防斧"})       # 被动武器不消耗
    assert "消防斧" in g.items[1]
    msgs = g.act(1, {"use": "圣水"})
    assert 1 in g.holy
    try:
        g.act(1, {"use": "不存在的道具"})
        assert False, "无主道具应被拒绝"
    except Exception:
        pass


def _force_haunt(g):
    g.rng = FakeRng()
    for i in range(8):
        _reveal(g, "omen", y=900 + i)
        if g.phase == "haunt":
            return
    assert False, "8 枚预兆必触发惊魂"


def test_combat_damage_and_survivors_win():
    g = BetrayalGame([1, 2, 3], seed=7)
    _force_haunt(g)
    t = g.haunt["traitor"]
    v = next(u for u in g.players if u != t)
    for other in g.players:                  # 白盒：其余幸存者先出局，只留 v 对决叛徒
        if other not in (t, v):
            g.dead.add(other)
    g.pos[t] = g.pos[v] = (0, 0)
    g.turn_idx = g.players.index(v)          # 幸存者 v 反击叛徒
    g.attack_used = False
    g.steps_left = 3
    g.stats[v]["might"] = 5
    g.stats[t]["might"] = 1
    g.act(v, {"attack": t})                  # 恒掷 1 → 差值 4，叛徒致命伤
    assert t in g.dead
    e = g.ended()
    assert e and e["winner_uid"] is None and "叛徒" in e["detail"]


def test_escape_win():
    g = BetrayalGame([1, 2, 3], seed=8)
    _force_haunt(g)
    t = g.haunt["traitor"]
    ex = g.haunt["exit"]
    sv = [u for u in g.players if u != t]
    g.turn_idx = g.players.index(sv[0])
    g.steps_left = 3
    # 未全员到齐应被拒绝
    g.pos[sv[0]] = ex
    try:
        g.act(sv[0], {"escape": True})
        assert False, "未全员到齐应拒绝撤离"
    except Exception:
        pass
    for u in sv:
        g.pos[u] = ex
    msgs = g.act(sv[0], {"escape": True})
    assert any("撤离" in m for m in msgs)
    e = g.ended()
    assert e and e["winner_uid"] is None and "幸存者" in e["detail"]


def test_traitor_left_survivors_win():
    g = BetrayalGame([1, 2, 3], seed=9)
    _force_haunt(g)
    t = g.haunt["traitor"]
    g.player_left(t)
    assert t in g.dead and t not in g.players
    e = g.ended()
    assert e and e["winner_uid"] is None


def test_all_dead_in_explore():
    g = BetrayalGame([1, 2, 3], seed=10)
    for u in g.players:
        g.stats[u] = {"might": 1, "speed": 1, "sanity": 0, "knowledge": 1}
    g.dead = set(g.players)
    e = g.ended()
    assert e and e["winner_uid"] is None and "山屋" in e["detail"]


def test_turn_rotation_skips_dead_and_steps_refresh():
    g = BetrayalGame([1, 2, 3], seed=12)
    g.dead.add(1)                            # 1 号死王，轮到 2 号
    g._end_turn([])
    assert g.players[g.turn_idx] == 2 and g.steps_left == 3
    assert g.attack_used is False
