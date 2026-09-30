# -*- coding: utf-8 -*-
"""花砖物语·拼花（致敬 Azul）：5 色瓷砖。每回合若干工厂碗供选，玩家从一座碗（或中央）
拿取某色的全部瓷砖，填入自己的 5 排花纹行；排满一排即落一块上墙并计分，积压则掉地作负分。
终局：有玩家铺满整行(5格)或瓷砖袋耗尽即结束，按墙分-地板分定胜负（整行+2 / 整列+7 奖励）。"""
from games_pkg.base import BaseGame, GameRuleError

COLORS = ["r", "w", "b", "y", "k"]          # 红 白 蓝 黄 黑
COLOR_CN = {"r": "红", "w": "白", "b": "蓝", "y": "黄", "k": "黑"}
ROWS = 5                                     # 花纹行/墙共 5 行
ROW_PENALTY = [-1, -1, -2, -2, -2, -3, -3]   # 地板亏分（按超额度封顶 7）


def _wall_col(color_idx: int, row: int) -> int:
    """拉丁方：每行/每列恰各色一次。颜色 ci 在 row 行的落点列。"""
    return (color_idx + row) % ROWS


class AzulGame(BaseGame):
    name = "azul"
    min_players = 2
    max_players = 4

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.bag = self._seed_bag()
        self.offers = []          # 每座工厂碗（list of colors）
        self.center = []          # 中央待取区
        self.center_first_taken = False
        self.rows = {u: {i: [] for i in range(ROWS)} for u in players}   # 花纹行（未满）
        self.wall = {u: {(r, c): None for r in range(ROWS) for c in range(ROWS)}
                     for u in players}                                   # 墙
        self.floor = {u: 0 for u in players}
        self.pending = None       # 当前行动者刚取走的瓷砖
        self.turn = 0
        self.round = 1
        self.score = {u: 0 for u in players}
        self.winner = None
        self._replenish()

    # ---------- 组装 ----------
    def _seed_bag(self):
        bag = []
        for c in COLORS:
            bag += [c] * 20       # 每色 20 片，共 100
        self.rng.shuffle(bag)
        return bag

    def _replenish(self):
        if not any(x for x in self.offers) and not self.center:
            pass                  # 正常整轮刷新前先清场
        n = len(self.players)
        self.offers = []
        for _ in range(n):
            bowl = []
            for _ in range(4):
                if self.bag:
                    bowl.append(self.bag.pop())
            if bowl:
                self.offers.append(bowl)
        self.center = []
        self.center_first_taken = False

    def _cur(self):
        return self.players[self.turn]

    # ---------- 动作 ----------
    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if uid != self._cur():
            raise GameRuleError("还没轮到你")
        op = action.get("op")
        if op == "take":
            return self._take(uid, action)
        if op == "place":
            return self._place(uid, action)
        if op == "floor":
            return self._place(uid, {"row": -1})
        raise GameRuleError("未知动作")

    def _take(self, uid, action):
        src = action.get("src")
        col = action.get("col")
        if col not in COLORS:
            raise GameRuleError("颜色无效")
        source_list = self.center if src == "center" else None
        if src != "center":
            try:
                idx = int(src)
            except (TypeError, ValueError):
                raise GameRuleError("来源无效")
            if not (0 <= idx < len(self.offers)):
                raise GameRuleError("工厂碗不存在")
            if not self.offers[idx]:
                raise GameRuleError("该碗已空")
            source_list = self.offers[idx]
        if col not in source_list:
            raise GameRuleError("该处没有此色瓷砖")
        k = source_list.count(col)
        taken = [col] * k
        source_list[:] = [x for x in source_list if x != col]
        msgs = [f"🎨 {self._nick(uid)} 从{'中央' if src == 'center' else '碗' + str(src)} "
                f"取走 {COLOR_CN[col]}×{k}"]
        if src == "center":
            if not self.center_first_taken:
                self.floor[uid] += 1
                self.center_first_taken = True
                msgs.append("（首取中央：地板 -1）")
            self.center.extend(source_list)   # 已被取空
        else:
            self.center.extend(source_list)   # 留下的进中央
            source_list[:] = []
        self.pending = taken
        return msgs + [f"💬 请选择花纹行(0~4)落砖，或点 '溢出到地板'"]

    def _place(self, uid, action):
        if self.pending is None:
            raise GameRuleError("先取砖再落砖")
        taken = self.pending
        m = int(action.get("row", -1))
        if m == -1:
            floor_lost = min(len(taken), 2)
            self.floor[uid] += len(taken)
            self.pending = None
            self._advance(uid)
            return [f"🌀 {self._nick(uid)} 将 {len(taken)} 片全部溢出（地板 -{len(taken)}）"]
        if not (0 <= m < ROWS):
            raise GameRuleError("行号无效")
        col = taken[0]
        cell_col = _wall_col(COLORS.index(col), m)
        if self.wall[uid][(m, cell_col)] is not None:
            raise GameRuleError("此色在本行墙格已占用")
        row = self.rows[uid][m]
        cap = m + 1
        if row and row[0] != col:
            raise GameRuleError("此行只能放同一种颜色")
        fill = min(len(taken), cap - len(row))
        placed = taken[:fill]
        row.extend(placed)
        overflow = taken[fill:]
        self.floor[uid] += len(overflow) if len(overflow) <= 2 else 2
        msgs = [f"🧱 {self._nick(uid)} 落 {COLOR_CN[col]}×{fill} 于第 {m + 1} 行"]
        if overflow:
            msgs.append(f"（溢出 {len(overflow)} 片 → 地板）")
        if len(row) == cap:                     # 行满 → 上墙
            self.rows[uid][m] = []
            self.wall[uid][(m, cell_col)] = col
            pts = self._score_cell(uid, m, cell_col)
            self.score[uid] += pts
            msgs.append(f"✨ 第 {m + 1} 行铺满上墙，+{pts} 分")
        self.pending = None
        msgs += self._round_or_next(uid)
        return msgs

    def _score_cell(self, uid, r, c):
        """落瓦计分 = 1 + 同排连续 + 同列连续。"""
        w = self.wall[uid]
        pts = 1
        for dc in (-1, 1):                      # 横向
            cc = c + dc
            while 0 <= cc < ROWS and w[(r, cc)] is not None:
                pts += 1
                cc += dc
        for dr in (-1, 1):                      # 纵向
            rr = r + dr
            while 0 <= rr < ROWS and w[(rr, c)] is not None:
                pts += 1
                rr += dr
        return pts

    def _any_full_row(self):
        return any(all(self.wall[uid][(r, c)] is not None for c in range(ROWS))
                   for uid in self.players for r in range(ROWS))

    def _round_or_next(self, uid):
        msg = []
        if self._any_full_row():                # 有人拼满一行 → 结束
            self._finish()
            return ["🏁 有人拼满整行，对局结束"]
        if any(x for x in self.offers) or self.center:
            self.turn = (self.turn + 1) % len(self.players)
            self.pending = None
            return []
        # 整轮结束 → 补砖
        if not self.bag:
            self._finish()
            return [f"🏁 瓷砖袋耗尽，对局结束"]
        self.round += 1
        self._replenish()
        self.turn = (self.turn + 1) % len(self.players)
        return [f"—— 第 {self.round} 轮，重置瓷砖 ——"]

    def _advance(self, uid):
        self.turn = (self.turn + 1) % len(self.players)
        self.pending = None
        if not any(x for x in self.offers) and not self.center:
            if not self.bag:
                self._finish()
            else:
                self.round += 1
                self._replenish()

    def _finish(self):
        for u in self.players:
            w = self.wall[u]
            bonus = 0
            for r in range(ROWS):
                if all(w[(r, c)] is not None for c in range(ROWS)):
                    bonus += 2
            for c in range(ROWS):
                if all(w[(r, c)] is not None for r in range(ROWS)):
                    bonus += 7
            self.score[u] += bonus - min(self.floor[u], 7)
        hi = max(self.score.values())
        leaders = [u for u in self.players if self.score[u] == hi]
        self.winner = leaders[0]

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "round": self.round, "turn_uid": self._cur(),
            "colors": COLOR_CN,
            "offers": [[{"c": k, "n": 1} for k in x] for x in self.offers],
            "center": [{"c": k, "n": 1} for k in self.center],
            "rows": {str(u): {str(i): r for i, r in self.rows[u].items()}
                     for u in self.players},
            "wall": {str(u): {f"{r},{c}": self.wall[u][(r, c)] for (r, c) in self.wall[u]}
                     for u in self.players},
            "floor": {str(u): self.floor[u] for u in self.players},
            "score": {str(u): self.score[u] for u in self.players},
            "bag": len(self.bag), "players": list(self.players),
            "winner_uid": self.winner,
        }

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 墙分最高"}
        return None

    def player_left(self, uid):
        if uid in self.players and self.players[self.turn] == uid:
            self.turn = (self.turn + 1) % len(self.players)
        return []

    def _nick(self, uid):
        return f"玩家{uid}"