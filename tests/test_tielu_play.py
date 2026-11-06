"""铁路目标票隐私、连通与完整最后一轮（含上游四人守恒复现）。"""
import pytest

from games_pkg.base import GameRuleError
from games_pkg.tielu import COLORS, ROUTES, TICKETS, TieluGame


def test_private_goals_track_indirect_connections_and_draw_without_public_leak():
    g = TieluGame([1, 2], seed=1)
    g.tickets[1] = [[0, 2, 2]]
    assert g.private(1)["tickets"] == [{"a": 0, "b": 2, "v": 2, "connected": False}]
    for a, b, color in [(0, 1, "red"), (1, 2, "green")]:
        g.hand[1][color] = 2
        g.act(1, {"op": "claim", "a": a, "b": b})
        g.act(2, {"op": "skip"})
    assert g.private(1)["tickets"][0]["connected"] is True
    before = list(g.private(2)["tickets"])
    messages = g.act(1, {"op": "ticket"})
    assert messages == ["📜 玩家1 抽到 1 张私人目标票"]
    assert len(g.private(1)["tickets"]) == 2
    assert g.private(2)["tickets"] == before
    assert "tickets" not in g.snapshot() and g.snapshot()["final_scores"] == {}
    assert g.private(999)["tickets"] == []


def exhausted_routes_final_round():
    """复用 UPSTREAM-REVIEW-20261030 的发牌/摸牌计划和全部79个合法动作。

    初始手牌为合法合成夹具；每色手牌+牌库+已支付线路=12。无改分/跳 turn。
    """
    g = TieluGame([1, 2, 3, 4], seed=1)
    hands = [{"green": 1, "blue": 1, "purple": 2, "red": 1},
             {"yellow": 1, "green": 1, "blue": 1, "red": 2},
             {"yellow": 3, "purple": 2}, {"red": 1, "blue": 2, "purple": 2}]
    g.hand = {u: {c: hands[u - 1].get(c, 0) for c in COLORS} for u in g.players}
    draws = ["purple", "purple", "blue", "blue", "green", "green", "green", "green",
             "green", "green", "yellow", "yellow", "red", "red", "green", "blue",
             "yellow", "yellow", "yellow", "purple", "red", "red", "blue", "purple"]
    rest = [c for c in COLORS for _ in range(12 - sum(g.hand[u][c] for u in g.players) - draws.count(c))]
    g.ticket_deck = rest + list(reversed(draws))
    # 四人一行，c 后为两城市编号；其余 d=摸牌、s=跳过。
    script = """d s s s
    d s s s
    d s s s
    d s s s
    d d s s
    s d s s
    s d d s
    s s d d
    s s s d
    c03 s s s
    c23 s s s
    c12 c04 s s
    s c45 s s
    s c56 s s
    s c67 c37 s
    s s c14 s
    s s c25 c36
    s s s c15
    s s s c26
    c07 c01 s""".split()
    assert len(script) == 79
    for i, token in enumerate(script):
        uid = i % 4 + 1
        action = ({"op": "claim", "a": int(token[1]), "b": int(token[2])}
                  if token.startswith("c") else {"op": "draw" if token == "d" else "skip"})
        g.act(uid, action)
        assert g.ended() is None, (i, uid, action)
        for c in COLORS:
            paid = sum(r[3] for r in ROUTES
                       if r[2] == c and any({a, b} == {r[0], r[1]}
                                          for mm in g.mine.values() for a, b, _ in mm))
            assert sum(g.hand[u][c] for u in g.players) + g.ticket_deck.count(c) + paid == 12
        if i == 77:
            assert g.snapshot()["turn_uid"] == 3 and not g.route_deck
    assert g.snapshot()["turn_uid"] == 4 and g.extra == []
    assert g.snapshot()["final_round"] is True
    return g


@pytest.mark.parametrize("op", ["draw", "ticket", "skip"])
def test_four_player_last_supplementary_turn_is_actionable_without_routes(op):
    g = exhausted_routes_final_round()
    before_hand, before_goals = sum(g.hand[4].values()), len(g.tickets[4])
    g.act(4, {"op": op})
    assert g.ended() is not None
    assert sum(g.hand[4].values()) == before_hand + (2 if op == "draw" else 0)
    assert len(g.tickets[4]) == before_goals + (1 if op == "ticket" else 0)
    assert g.snapshot()["turn_uid"] is None
    assert g.snapshot()["final_round"] is False
    with pytest.raises(GameRuleError, match="本局已结束"):
        g.act(1, {"op": "skip"})


def test_final_breakdown_uses_ticket_additions_deductions_and_seat_order_tie():
    g = TieluGame([1, 2], seed=1)
    g.route_deck = []
    g.mine = {1: [(0, 1, 2), (1, 2, 2)], 2: [(0, 7, 5)]}
    g.tickets = {1: [[0, 2, 2], [0, 4, 2]], 2: [[0, 7, 3], [1, 6, 2]]}
    assert g.ended()["winner_uid"] == 2  # 线路4 vs5，最终4 vs6
    assert g.snapshot()["final_scores"] == {
        "1": {"route": 4, "ticket_bonus": 2, "ticket_penalty": 2, "total": 4},
        "2": {"route": 5, "ticket_bonus": 3, "ticket_penalty": 2, "total": 6}}
    tie = TieluGame([2, 1], seed=1)
    tie.route_deck = []
    tie.mine = {1: [], 2: []}
    tie.tickets = {u: [list(TICKETS[0])] for u in tie.players}
    assert tie.ended()["winner_uid"] == 2
