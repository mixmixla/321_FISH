# -*- coding: utf-8 -*-
"""铁路（连线得分，致敬车票之旅）：固定城市图，认领线路(两城, 付对应色车票卡)得长度分，
可摸 2 张车票卡或抽一张私人「票证」；终局按是否连通城市结算票证 +/- 分。"""
from games_pkg.base import BaseGame, GameRuleError

CITIES = [(0, "港口"), (1, "河城"), (2, "山城"), (3, "雪镇"),
          (4, "沙堡"), (5, "雾谷"), (6, "林郡"), (7, "金矿")]
CITY_CN = dict(CITIES)
COLORS = ["red", "yellow", "green", "blue", "purple"]
COLOR_CN = {"red": "红", "yellow": "黄", "green": "绿", "blue": "蓝", "purple": "紫"}
# (a, b, color, length)
ROUTES = [
    (0, 1, "red", 2), (1, 2, "green", 2), (2, 3, "blue", 3),
    (0, 4, "yellow", 3), (4, 5, "red", 2), (5, 6, "green", 2),
    (6, 7, "blue", 2), (3, 7, "yellow", 3), (0, 3, "purple", 4),
    (1, 4, "purple", 3), (2, 5, "yellow", 3), (3, 6, "red", 3),
    (0, 7, "green", 5), (1, 5, "blue", 3), (2, 6, "purple", 3),
]
TICKETS = [(0, 7, 3), (1, 6, 2), (2, 7, 2), (0, 4, 2), (1, 5, 2),
           (3, 6, 2), (0, 2, 2), (4, 7, 3), (2, 4, 2), (5, 7, 2)]
END_TARGET = 10          # 单人有此分即触发终局


class TieluGame(BaseGame):
    name = "tielu"
    min_players = 2
    max_players = 4

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.route_deck = [{"a": a, "b": b, "color": c, "length": l}
                       for a, b, c, l in ROUTES]
        self.rng.shuffle(self.route_deck)
        self.hand = {u: {c: 0 for c in COLORS} for u in players}
        for u in players:
            for _ in range(5):
                self.hand[u][self.rng.choice(COLORS)] += 1
        self.mine = {u: [] for u in players}      # 认领的线路 (a,b,len)
        self.tickets = {u: [] for u in players}   # 私有票证 (a,b,value)
        for u in players:
            for _ in range(2):
                t = self.rng.choice(TICKETS)
                self.tickets[u].append(list(t))
        self.routes_total = len(self.route_deck)
        self.turn = 0
        self.winner = None

    def _edges(self, uid):
        return [(a, b) for (a, b, _c, _l) in self.mine[uid]]

    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        op = action.get("op")
        if op == "draw":
            return self._act_draw(uid)
        if op == "claim":
            return self._act_claim(uid, action)
        if op == "ticket":
            return self._act_ticket(uid)
        if op == "skip":
            self.turn = (self.turn + 1) % len(self.players)
            return [f"⏭ {self._nick(uid)} 结束回合"]
        raise GameRuleError("未知动作")

    def _act_draw(self, uid):
        if not self.route_deck:
            raise GameRuleError("线路牌已空")
        got = []
        for _ in range(2):
            c = self.rng.choice(COLORS)
            self.hand[uid][c] += 1
            got.append(COLOR_CN[c])
        self.turn = (self.turn + 1) % len(self.players)
        return [f"🎫 {self._nick(uid)} 摸车票卡：{'、'.join(got)}"]

    def _act_claim(self, uid, action):
        try:
            a, b = int(action["a"]), int(action["b"])
        except (TypeError, ValueError):
            raise GameRuleError("城市无效")
        if a == b or a not in CITY_CN or b not in CITY_CN:
            raise GameRuleError("未知城市")
        route = None
        for r in self.route_deck:
            if set((r["a"], r["b"])) == {a, b}:
                route = r
                break
        if route is None:
            raise GameRuleError("该线路已被认领或不存在")
        color, length = route["color"], route["length"]
        if self.hand[uid][color] < length:
            raise GameRuleError(f"{COLOR_CN[color]}票卡不足 {length} 张")
        self.hand[uid][color] -= length
        self.route_deck.remove(route)
        self.mine[uid].append((a, b, length))
        score = self._score(uid)
        msgs = [f"🚂 {self._nick(uid)} 认领 {CITY_CN[a]}→{CITY_CN[b]}（{COLOR_CN[color]}×{length}），"
                f"长度分 {score}"]
        self.turn = (self.turn + 1) % len(self.players)
        return msgs

    def _act_ticket(self, uid):
        avail = [t for t in TICKETS if t not in self.tickets[uid]]
        if not avail:
            raise GameRuleError("无更多票证")
        t = list(self.rng.choice(avail))
        self.tickets[uid].append(t)
        self.turn = (self.turn + 1) % len(self.players)
        return [f"📜 {self._nick(uid)} 抽到票证：{CITY_CN[t[0]]}→{CITY_CN[t[1]]}（+{t[2]}）"]

    def _score(self, uid):
        return sum(l for (_a, _b, l) in self.mine[uid])

    def _connected(self, uid, a, b):
        g = {}
        for (x, y, _l) in self.mine[uid]:
            g.setdefault(x, []).append(y)
            g.setdefault(y, []).append(x)
        stack = [a]
        seen = {a}
        while stack:
            cur = stack.pop()
            if cur == b:
                return True
            for nxt in g.get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return False

    def _total(self, uid):
        s = self._score(uid)
        for (a, b, v) in self.tickets[uid]:
            s += v if self._connected(uid, a, b) else -v
        return s

    def _finalize(self):
        best = max(self._total(u) for u in self.players)
        leaders = [u for u in self.players if self._total(u) == best]
        self.winner = leaders[0]

    def ended(self):
        if not self.route_deck:
            if self.winner is None:
                self._finalize()
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 票证结算后总分最高"}
        return None

    def private(self, uid):
        return {"tickets": [{"a": a, "b": b, "v": v}
                            for (a, b, v) in self.tickets.get(uid, [])],
                "hand": self.hand.get(uid, {})}

    def snapshot(self):
        routes = [{"a": r["a"], "b": r["b"], "color": r["color"],
                   "length": r["length"], "claimed": False} for r in self.route_deck]
        for uid, mm in self.mine.items():
            for (a, b, l) in mm:
                routes.append({"a": a, "b": b, "color": None, "length": l,
                               "claimed": uid})
        return {
            "game": self.name, "status": "playing",
            "cities": CITY_CN, "colors": COLOR_CN,
            "route_left": len(self.route_deck), "routes": routes,
            "hand_count": {str(u): sum(self.hand[u].values()) for u in self.players},
            "score": {str(u): self._score(u) for u in self.players},
            "turn_uid": None if not self.route_deck else self.players[self.turn],
            "players": list(self.players), "winner_uid": self.winner,
        }

    def player_left(self, uid):
        return []

    def _nick(self, uid):
        return f"玩家{uid}"