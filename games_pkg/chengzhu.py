# -*- coding: utf-8 -*-
"""我是城主·领地扩（致敬多米诺/Kingdomino）：每个玩家用 1x2 多米诺板块拼装自己的 5x5 领地，
板块两半各有地型与王冠。放置须与自家同地型相邻（首板任放）。终局按每片连通地块
「格数 × 王冠总数」计分。"""
from games_pkg.base import BaseGame, GameRuleError

SIZE = 5                 # 领地边长
DOM_PER_PLAYER = 12      # 每人可落板数（2 半 = 24 格，接近 25）
TERR_CN = {"fd": "田", "fo": "林", "mo": "山", "wa": "水", "gr": "牧"}
TERRS = list(TERR_CN)


class ChengZhuGame(BaseGame):
    name = "chengzhu"
    min_players = 2
    max_players = 4

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.grid = {u: {} for u in players}          # (r,c) -> {terr,crown}
        self.placed = {u: 0 for u in players}
        self.market = []                              # 本批待选板块
        self.pick_order = list(players)
        self.pick_idx = 0
        self.piles = self._make_dominos()
        self.score = {u: 0 for u in players}
        self.winner = None
        self._refill()

    def _make_dominos(self):
        piles = []
        for _ in range(100):
            t1 = self.rng.choice(TERRS)
            t2 = self.rng.choices([t1, self.rng.choice(TERRS)])[0]
            piles.append({"id": len(piles), "A": {"terr": t1,
                                                  "crown": self.rng.randint(0, 3)},
                          "B": {"terr": t2, "crown": self.rng.randint(0, 3)}})
        self.rng.shuffle(piles)
        return piles

    def _refill(self):
        n = len(self.players)
        self.market = [self.piles.pop() for _ in range(n)] if len(self.piles) >= n \
            else (self.piles if self.piles else [])
        self.pick_order = list(self.players)
        self.pick_idx = 0

    def _current_picker(self):
        if self.pick_idx < len(self.pick_order):
            return self.pick_order[self.pick_idx]
        return None

    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        uid_picker = self._current_picker()
        if uid_picker is None:
            raise GameRuleError("对局已结束")
        if uid != uid_picker:
            raise GameRuleError(f"轮不到你（当前是玩家{uid_picker}挑选）")

        if action.get("op") == "pass":
            self.pick_idx += 1
            self._round_check()
            return []

        dom = self._pick_dom(uid, action)      # 返回选择的板块
        placed = self._place(uid, dom, action)
        self.pick_idx += 1
        self._round_check()
        return [f"🏰 {self._nick(uid)} 拼装板块（{dom['A']['terr']}/{dom['B']['terr']}）"]

    def _pick_dom(self, uid, action):
        try:
            idx = int(action["dom"])
        except (TypeError, ValueError):
            raise GameRuleError("板块编号无效")
        if not (0 <= idx < len(self.market)):
            raise GameRuleError("板块不存在")
        return self.market.pop(idx)

    def _place(self, uid, dom, action):
        if self.placed[uid] >= DOM_PER_PLAYER:
            raise GameRuleError("你的领地已放满")
        try:
            x, y = int(action["x"]), int(action["y"])
            rot = int(action.get("rot", 0))
        except (TypeError, ValueError):
            raise GameRuleError("坐标无效")
        dr, dc = (0, 1) if rot == 0 else (1, 0)
        halves = [(x, y), (x + dr, y + dc)]
        if any(not (0 <= r < SIZE and 0 <= c < SIZE) for r, c in halves):
            raise GameRuleError("越界")
        if any((r, c) in self.grid[uid] for r, c in halves):
            raise GameRuleError("位置已被占用")
        if self.placed[uid] > 0:
            terrA, terrB = dom["A"]["terr"], dom["B"]["terr"]
            ok = False
            for (r, c), half in zip(halves, ["A", "B"]):
                terr = dom[half]["terr"]
                for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                    if (rr, cc) in self.grid[uid] and self.grid[uid][(rr, cc)]["terr"] == terr:
                        ok = True
            if not ok:
                raise GameRuleError("必须与同地型相邻")
        self.grid[uid][(x, y)] = dict(dom["A"])
        self.grid[uid][(x + dr, y + dc)] = dict(dom["B"])
        self.placed[uid] += 1

    def _round_check(self):
        n = len(self.players)
        if self.pick_idx >= n:
            if not self.market and not self.piles:
                self._finish()
                return
            self._refill()

    def _regions_score(self, uid):
        cells = self.grid[uid]
        seen = set()
        total = 0
        for start in list(cells):
            if start in seen:
                continue
            terr = cells[start]["terr"]
            stack = [start]
            region = []
            while stack:
                r, c = stack.pop()
                if (r, c) in seen:
                    continue
                seen.add((r, c))
                region.append((r, c))
                for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                    if (rr, cc) in cells and (rr, cc) not in seen \
                            and cells[(rr, cc)]["terr"] == terr:
                        stack.append((rr, cc))
            crowns = sum(cells[p]["crown"] for p in region)
            total += len(region) * crowns
        return total

    def _finish(self):
        for u in self.players:
            self.score[u] = self._regions_score(u)
        hi = max(self.score.values())
        leaders = [u for u in self.players if self.score[u] == hi]
        self.winner = leaders[0]

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "size": SIZE,
            "grid": {str(u): {f"{r},{c}": cell for (r, c), cell in g.items()}
                     for u, g in self.grid.items()},
            "placed": {str(u): v for u, v in self.placed.items()},
            "market": self.market, "piles": len(self.piles),
            "picker_uid": self._current_picker(),
            "score": {str(u): self.score[u] for u in self.players},
            "players": list(self.players), "winner_uid": self.winner,
        }

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 领地得分最高"}
        return None

    def player_left(self, uid):
        # 移出挑选顺序并重排（简化：保留原玩家仓位，跳过该 uid）
        self.pick_order = [p for p in self.pick_order if p != uid]
        return []

    def _nick(self, uid):
        return f"玩家{uid}"