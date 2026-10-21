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
        self.staged = {u: [] for u in players}   # 首任未达成时本回合暂存的牌组
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
            # 本回合没有任何牌真正上桌（未出牌 / 首任不足被回滚）时，按规则摸一张再结束
            had_play = self.initial_ok[uid] and self.placed_turn > 0
            tail = self._next()
            drawn = []
            if not had_play and self.bag:
                self.rack[uid].append(self.bag.pop())
                drawn = [f"🂠 {self._nick(uid)} 未出牌，摸一张后结束回合"]
            return [f"✅ {self._nick(uid)} 结束回合"] + drawn + tail
        if op == "draw":
            staged = bool(self.staged.get(uid))
            if self.placed_turn > 0 and not staged:
                raise GameRuleError("本回合已出牌，不能摸牌")
            # 首任未达成：摸牌结束回合前先把整回合暂存牌收回
            extra = self._rollback_staged(uid)
            if self.bag:
                self.rack[uid].append(self.bag.pop())
            self.drawn_turn = True
            tail = self._next()
            return [f"🂠 {self._nick(uid)} 摸牌后结束回合"] + extra + tail
        raise GameRuleError("未知动作")

    def _meld(self, uid, action):
        ids = self._parse_ids(action)
        if RummikubGame.classify(ids) is None:
            raise GameRuleError("不构成群或顺")
        # 先完整校验手牌再落子：校验失败时暂存/桌面/手牌都不变
        self._apply_rack(uid, ids)
        self.placed_turn += 1
        self.drawn_turn = False
        if self.initial_ok[uid]:
            self.table.append(ids)
            msg = f"{self._tile_str(ids)} 🎴 {self._nick(uid)} 组了一组牌"
        else:
            self.staged[uid].append(ids)
            pts = self._staged_pts(uid)
            if pts < INIT_SUM:
                msg = (f"{self._tile_str(ids)} 📥 {self._nick(uid)} 出牌暂存"
                       f"（首任累计 {pts}/{INIT_SUM}）")
            else:
                groups = self.staged[uid]
                self.staged[uid] = []
                self.table.extend(groups)
                self.initial_ok[uid] = True
                msg = (f"{self._tile_str(ids)} 🎴 {self._nick(uid)} 首任累计 {pts} 点达成，"
                       f"{len(groups)} 组牌一并上桌")
        # 只有首任已达成（牌真正上桌）时清空手牌才算胜利
        if self.initial_ok[uid] and not self.rack[uid]:
            self.winner = uid
        return [msg]

    def _staged_pts(self, uid):
        return sum(self._pts(g) for g in self.staged.get(uid, []))

    def _rollback_staged(self, uid):
        """回合结束时首任仍不足 30 点：把暂存的牌全部收回手牌"""
        groups = self.staged.get(uid) or []
        if not groups:
            return []
        for g in groups:
            self.rack[uid].extend(g)
        self.staged[uid] = []
        return [f"↩️ {self._nick(uid)} 首任累计不足 {INIT_SUM} 点，本回合出的牌已全部收回"]

    def _extend(self, uid, action):
        ids = self._parse_ids(action)
        try:
            row = int(action["row"])
        except (TypeError, ValueError):
            raise GameRuleError("行号无效")
        if not (0 <= row < len(self.table)):
            raise GameRuleError("行不存在")
        if not self.initial_ok[uid]:
            raise GameRuleError(f"首次上牌需先一次性出 ≥{INIT_SUM} 点")
        new = list(self.table[row]) + ids
        if RummikubGame.classify(new) is None:
            raise GameRuleError("接续后不构成群或顺")
        # 先校验手牌，再改桌面：失败时不留半状态
        self._apply_rack(uid, ids)
        self.table[row] = new
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
        # 回合结束：首任未达成的暂存牌组整回合回滚
        extra = self._rollback_staged(self._cur())
        self.turn = (self.turn + 1) % len(self.players)
        self.placed_turn = 0
        self.drawn_turn = False
        return extra

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
                          "n": num_of[i]} for i in self.rack[uid]],
                "staged": [[{"id": i, "c": COLOR_CN[COLORS[color_of[i]]],
                            "n": num_of[i]} for i in group]
                           for group in self.staged.get(uid, [])],
                "staged_pts": self._staged_pts(uid)}

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 率先清空手牌"}
        return None

    def player_left(self, uid):
        if uid not in self.players:
            return []
        idx = self.players.index(uid)
        # 手牌与暂存牌一起退回牌袋，避免留下无人可打却仍占座位的玩家
        self.bag.extend(self.rack.pop(uid, []))
        for g in self.staged.pop(uid, []):
            self.bag.extend(g)
        self.initial_ok.pop(uid, None)
        self.players.remove(uid)
        self.placed_turn = 0
        self.drawn_turn = False
        if not self.players:
            return [f"💨 {self._nick(uid)} 离开了对局"]
        if self.turn > idx:
            self.turn -= 1
        self.turn %= len(self.players)
        if len(self.players) < self.min_players and self.winner is None:
            self.winner = self.players[0]
            return [f"💨 {self._nick(uid)} 离开，{self._nick(self.winner)} 获胜"]
        return [f"💨 {self._nick(uid)} 离开了对局"]

    def _nick(self, uid):
        return f"玩家{uid}"