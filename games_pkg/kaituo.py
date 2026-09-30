# -*- coding: utf-8 -*-
"""开拓（资源建设，致敬卡坦）：5x5 方格国土 + 定居点/城市/道路，掷骰采资源。

定居点落在方格点(角)上，邻接最多 4 块资源地；掷骰后所有邻接该数字资源地的
定居点获得资源，城市翻倍；可 4:1 换资源；先到 10 分者胜（村1 城2 最长路2）。
"""
from games_pkg.base import BaseGame, GameRuleError

SIZE = 5                     # 5x5 资源地
RES_COST = {"road": {"wood": 1, "brick": 1},
            "settle": {"wood": 1, "brick": 1, "lamb": 1, "wheat": 1},
            "city": {"wheat": 2, "ore": 3}}
RES_CN = {"wood": "木头", "brick": "砖", "lamb": "羊", "wheat": "麦", "ore": "矿"}
ROWS = ["wrblt", "obtwb", "tlrtd", "rwbwo", "bttrw"]
WIN_PTS = 10


class KaituoGame(BaseGame):
    name = "kaituo"
    min_players = 2
    max_players = 4

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.tiles = {}
        for r in range(SIZE):
            for c in range(SIZE):
                res = {"w": "wood", "r": "brick", "b": "lamb",
                   "l": "wheat", "t": "ore", "o": "ore", "d": "desert"}[ROWS[r][c]]
                self.tiles[(r, c)] = {"res": res,
                                      "num": self.rng.choice([x for x in range(2, 13) if x != 7])}
        self.res = {u: {"wood": 0, "brick": 0, "lamb": 0, "wheat": 0, "ore": 0}
                    for u in players}
        self.board = {}          # vertex -> {"owner","city"}
        self.roads = {}          # edge -> uid
        self.turn = 0
        self.phase = "setup"     # setup -> play -> done
        self.setup_count = 0     # 已布置村数
        self.last_roll = None
        self.winner = None
        self._ni = SIZE          # 顶点坐标上限 = SIZE

    # ---------- 几何 / 快照辅助 ----------
    def _atiles(self, v):
        i, j = v
        out = []
        for di, dj in ((0, 0), (0, -1), (-1, 0), (-1, -1)):
            ti, tj = i + di, j + dj
            if 0 <= ti < SIZE and 0 <= tj < SIZE:
                out.append((ti, tj))
        return out

    def _nb(self, v):
        i, j = v
        return [(i + di, j + dj) for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if 0 <= i + di <= self._ni and 0 <= j + dj <= self._ni]

    def _settle_free(self, v):
        return all(p not in self.board for p in self._nb(v))

    def _buildable(self, uid):
        ok = set()
        for v, x in self.board.items():
            if x["owner"] == uid:
                ok.add(v)
        for e, o in self.roads.items():
            if o == uid:
                ok.add(e[0]); ok.add(e[1])
        usable = set()
        for v in ok:
            for p in self._nb(v):
                if p not in self.board:
                    usable.add(p)
        return usable

    def _can_road(self, uid, e):
        a, b = e
        for v in (a, b):
            if v in self.board and self.board[v]["owner"] == uid:
                return True
        for os, o in self.roads.items():
            if o == uid and (a in os or b in os):
                return True
        return False

    # ---------- 动作 ----------
    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        if self.phase == "setup":
            return self._act_setup(uid, action)
        op = action.get("op")
        if op == "roll":
            return self._act_roll(uid)
        if op == "build":
            return self._act_build(uid, action)
        if op == "trade":
            return self._act_trade(uid, action)
        if op == "skip":
            self._advance(uid)
            return [f"⏭ {self._nick(uid)} 结束回合"]
        raise GameRuleError("未知动作")

    def _act_setup(self, uid, action):
        v = self._parse_v(action)
        if v in self.board:
            raise GameRuleError("该位置已有建筑")
        if not self._settle_free(v):
            raise GameRuleError("定居点不能相邻")
        e = self._parse_e(action)
        if e in self.roads:
            raise GameRuleError("该道路已被占用")
        if v not in e:
            raise GameRuleError("道路必须接新建村庄")
        self.board[v] = {"owner": uid, "city": False}
        self.roads[e] = uid
        n = len(self.players)
        self.setup_count += 1
        if self.setup_count < n:
            self.turn = (self.turn + 1) % n
        elif self.setup_count == n:
            self.turn = n - 1                # 逆向给房主第二个村
        elif self.setup_count < 2 * n:
            self.turn = (self.turn - 1) % n
        else:
            self.phase = "play"
            self.turn = 0
            return [f"🏠 {self._nick(uid)} 完成布置，进入主局"]
        return [f"🏠 {self._nick(uid)} 布置定居点 ({v[0]},{v[1]})"]

    def _act_roll(self, uid):
        d1, d2 = self.rng.randint(1, 6), self.rng.randint(1, 6)
        roll = d1 + d2
        self.last_roll = roll
        msgs = [f"🎲 {self._nick(uid)} 掷出 {roll}"]
        if roll == 7:
            self._advance(uid)
            return msgs + ["（7 点：此局不触发盗匪惩罚）"]
        for v, x in self.board.items():
            for tr in self._atiles(v):
                t = self.tiles[tr]
                if t["num"] == roll and t["res"] != "desert":
                    if t["res"] not in self.res[x["owner"]]:
                        continue
                    amt = 2 if x["city"] else 1
                    self.res[x["owner"]][t["res"]] += amt
                    msgs.append(f"⛰ {self._nick(x['owner'])} +{amt}{RES_CN[t['res']]}")
        self._advance(uid)
        return msgs

    def _act_build(self, uid, action):
        kind = action.get("kind")
        cost = RES_COST.get(kind)
        if not cost:
            raise GameRuleError("未知建筑类型")
        for r, n in cost.items():
            if self.res[uid][r] < n:
                raise GameRuleError(f"资源不足：缺 {RES_CN[r]}")
        if kind == "road":
            e = self._parse_e(action)
            if e in self.roads:
                raise GameRuleError("该道路已被占用")
            if not self._can_road(uid, e):
                raise GameRuleError("道路必须与你的村庄/道路相连")
            self._pay(uid, cost)
            self.roads[e] = uid
            self._advance(uid)
            return [f"🛣 {self._nick(uid)} 建造道路"]
        if kind in ("settle", "city"):
            v = self._parse_v(action)
            if kind == "settle":
                if v in self.board:
                    raise GameRuleError("该顶点已有建筑")
                if not self._settle_free(v):
                    raise GameRuleError("定居点不能相邻")
                if v not in self._buildable(uid):
                    raise GameRuleError("必须从你的道路/村庄延伸")
                self._pay(uid, cost)
                self.board[v] = {"owner": uid, "city": False}
            else:
                if v not in self.board or self.board[v]["owner"] != uid or self.board[v]["city"]:
                    raise GameRuleError("需选择你自己的定居点升级")
                self._pay(uid, cost)
                self.board[v]["city"] = True
            pts = self._score(uid)
            if pts >= WIN_PTS:
                self.winner = uid
                return [f"🏆 {self._nick(uid)} 建造，总分 {pts}，达成 {WIN_PTS} 分获胜！"]
            self._advance(uid)
            return [f"{self._nick(uid)} 建造{'城市' if kind=='city' else '定居点'}，总分 {pts}"]
        raise GameRuleError("未知建筑")

    def _act_trade(self, uid, action):
        give, want = action.get("give"), action.get("want")
        if give not in self.res[uid] or want not in self.res[uid] or give == want:
            raise GameRuleError("资源类型无效")
        amt = int(action.get("n") or 4)
        if amt < 4:
            raise GameRuleError("港口 4:1 最少换 4 个")
        if self.res[uid][give] < amt:
            raise GameRuleError(f"{RES_CN[give]} 不足")
        self.res[uid][give] -= amt
        self.res[uid][want] += 1
        self._advance(uid)
        return [f"🔄 {self._nick(uid)} {amt}{RES_CN[give]} → 1{RES_CN[want]}"]

    def _advance(self, uid):
        if self.winner:
            return
        self.turn = (self.turn + 1) % len(self.players)

    def _pay(self, uid, cost):
        for r, n in cost.items():
            self.res[uid][r] -= n

    def _score(self, uid):
        total = sum((2 if x["city"] else 1) for v, x in self.board.items()
                    if x["owner"] == uid)
        return total + self._longest_road(uid)

    def _longest_road(self, uid):
        mine = [e for e, o in self.roads.items() if o == uid]
        if not mine:
            return 0
        best = 0
        verts = set(x for e in mine for x in e)
        mem = {}

        def dfs(v, prev):
            key = (v, prev)
            if key in mem:
                return mem[key]
            m = 0
            for e in mine:
                if e[0] != v and e[1] != v:
                    continue
                nxt = e[1] if e[0] == v else e[0]
                if nxt == prev:
                    continue
                m = max(m, 1 + dfs(nxt, v))
            mem[key] = m
            return m

        for v in verts:
            best = max(best, dfs(v, None))
        return 2 if best >= 5 else 0

    def _parse_v(self, action):
        try:
            i, j = int(action.get("i")), int(action.get("j"))
        except (TypeError, ValueError):
            raise GameRuleError("顶点坐标无效")
        if not (0 <= i <= self._ni and 0 <= j <= self._ni):
            raise GameRuleError("顶点越界")
        return (i, j)

    def _parse_e(self, action):
        a = self._parse_v(action)
        b = self._parse_v({"i": action.get("b_i"), "j": action.get("b_j")})
        if a == b or abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
            raise GameRuleError("道路两端必须相邻")
        return tuple(sorted([a, b]))

    # ---------- 快照 ----------
    def snapshot(self):
        return {
            "game": self.name, "status": "playing", "size": SIZE,
            "phase": self.phase,
            "tiles": {f"{r},{c}": t for (r, c), t in self.tiles.items()},
            "board": {f"{i},{j}": x for (i, j), x in self.board.items()},
            "roads": {f"{a[0]},{a[1]}>{b[0]},{b[1]}": o
                      for e, o in self.roads.items()
                      for a, b in [e]},
            "res": {str(u): v for u, v in self.res.items()},
            "score": {str(u): self._score(u) for u in self.players},
            "turn_uid": None if self.winner else self.players[self.turn],
            "last_roll": self.last_roll,
            "players": list(self.players), "winner_uid": self.winner,
        }

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 率先达成 {WIN_PTS} 分"}
        return None

    def player_left(self, uid):
        return []

    def _nick(self, uid):
        return f"玩家{uid}"