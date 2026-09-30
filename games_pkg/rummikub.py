# -*- coding: utf-8 -*-
"""拉密·出牌（致敬 Rummikub）：1~13 四色两联牌。桌上按「群」(同数异色)或「顺」(同色连号)
排牌。回合里可用手牌组新组/接续桌上牌组；开局首上任要求一次性放 ≥30 点。谁先清空手牌谁胜。"""
from games_pkg.base import BaseGame, GameRuleError

COLORS = ["r", "y", "b", "k"]
COLOR_CN = {"r": "红", "y": "黄", "b": "蓝", "k": "黑"}
INIT_SUM = 30

# 牌：color_of / num_of 按 id 索引（每色每数两张）
color_of, num_of = [], []
for _c in range(4):
    for _n in range(1, 14):
        for _ in range(2):
            color_of.append(_c)
            num_of.append(_n)
N_TILE = len(color_of)


class RummikubGame(BaseGame):
    name = "rummikub"
    min_players = 2
    max_players = 8

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        n = len(players)
        self.rack_need = 14 if n <= 4 else max(6, (N_TILE - n) // n)
        ids = list(range(N_TILE))
        self.rng.shuffle(ids)
        self.bag = ids
        self.rack = {}
        for u in players:
            self.rack[u] = [self.bag.pop() for _ in range(self.rack_need)]
        self.table = []                 # list of rows; row = [tile_id,...]
        self.initial_ok = {u: False for u in players}
        self.turn = 0
        self.placed_turn = 0
        self.drawn_turn = False
        self.winner = None

    def _cur(self):
        return self.players[self.turn]

    # ---------- 判组 ----------
    @staticmethod
    def classify(ids):
        if len(ids) < 3:
            return None
        nums = [num_of[i] for i in ids]
        cols = [color_of[i] for i in ids]
        if len(set(nums)) == 1:
            if len(set(cols)) != len(cols) or len(cols) > 4:
                return None
            return ("group", nums[0])
        if len(set(cols)) == 1:
            n = sorted(nums)
            if n == list(range(n[0], n[0] + len(n))):
                return ("run", cols[0], n[0], len(n))
        return None

    def _pts(self, ids):
        return sum(num_of[i] for i in ids)

    def _apply_rack(self, uid, ids):
        """从手牌移出 ids 到指定集合（校验存在）"""
        r = self.rack[uid]
        from collections import Counter
        cnt = Counter(r)
        need = Counter(ids)
        if any(need[k] > cnt[k] for k in need):
            raise GameRuleError("没有这些牌")
        for k in need:
            for _ in range(need[k]):
                r.remove(k)
        return r

    # ---------- 动作 ----------
    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if uid != self._cur():
            raise GameRuleError("还没轮到你")
        op = action.get("op")
        if op == "meld":
            return self._meld(uid, action)
        if op == "extend":
            return self._extend(uid, action)
        if op == "done":
            self._next()
            return [f"✅ {self._nick(uid)} 结束回合"]
        if op == "draw":
            if self.placed_turn > 0:
                raise GameRuleError("本回合已出牌，不能摸牌")
            if self.bag:
                self.rack[uid].append(self.bag.pop())
            self.drawn_turn = True
            self._next()
            return [f"🂠 {self._nick(uid)} 摸牌后结束回合"]
        raise GameRuleError("未知动作")

    def _meld(self, uid, action):
        ids = self._parse_ids(action)
        if RummikubGame.classify(ids) is None:
            raise GameRuleError("不构成群或顺")
        if not self.initial_ok[uid] and self._pts(ids) < INIT_SUM:
            raise GameRuleError(f"首任需一次性 ≥{INIT_SUM} 点")
        self._apply_rack(uid, ids)
        self.table.append(ids)
        self.initial_ok[uid] = True
        self.placed_turn += 1
        self.drawn_turn = False
        if not self.rack[uid]:
            self.winner = uid
        return [f"{self._tile_str(ids)} 🎴 {self._nick(uid)} 组了一组牌"]

    def _extend(self, uid, action):
        ids = self._parse_ids(action)
        try:
            row = int(action["row"])
        except (TypeError, ValueError):
            raise GameRuleError("行号无效")
        if not (0 <= row < len(self.table)):
            raise GameRuleError("行不存在")
        new = list(self.table[row]) + ids
        if RummikubGame.classify(new) is None:
            raise GameRuleError("接续后不构成群或顺")
        self.table[row] = new
        self._apply_rack(uid, ids)
        self.placed_turn += 1
        self.drawn_turn = False
        if not self.rack[uid]:
            self.winner = uid
        return [f"{self._tile_str(ids)} 🔧 {self._nick(uid)} 接续入第 {row + 1} 组"]

    def _parse_ids(self, action):
        raw = action.get("tiles")
        try:
            ids = [int(x) for x in raw]
        except (TypeError, ValueError):
            raise GameRuleError("牌编号无效")
        if not ids:
            raise GameRuleError("至少要一张牌")
        for i in ids:
            if not (0 <= i < N_TILE):
                raise GameRuleError("牌不存在")
        return ids

    def _tile_str(self, ids):
        return "".join(COLOR_CN[COLORS[color_of[i]]][0] + str(num_of[i]) for i in ids)

    def _next(self):
        self.turn = (self.turn + 1) % len(self.players)
        self.placed_turn = 0
        self.drawn_turn = False
        if self.winner is None and all(not self.rack[u] for u in self.players):
            # 极端没人能继续，取手牌最少者为胜（不应发生：赢家已最先清空）
            pass

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "turn_uid": self._cur(),
            "rack_size": {str(u): len(r) for u, r in self.rack.items()},
            "initial_ok": {str(u): v for u, v in self.initial_ok.items()},
            "table": [[{"id": i, "c": COLOR_CN[COLORS[color_of[i]]],
                        "n": num_of[i]} for i in row] for row in self.table],
            "bag": len(self.bag), "players": list(self.players),
            "winner_uid": self.winner,
        }

    def private(self, uid):
        if uid not in self.rack:
            return None
        return {"hand": [{"id": i, "c": COLOR_CN[COLORS[color_of[i]]],
                          "n": num_of[i]} for i in self.rack[uid]]}

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 率先清空手牌"}
        return None

    def player_left(self, uid):
        if uid in self.players and self.players[self.turn] == uid:
            self.turn = (self.turn + 1) % len(self.players)
            self.placed_turn = 0
        # 简化：掉线手牌不并入，交给其他玩家均衡处理由房间层接管
        return []

    def _nick(self, uid):
        return f"玩家{uid}"