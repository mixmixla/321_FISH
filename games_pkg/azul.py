# -*- coding: utf-8 -*-
"""花砖物语·拼花（致敬 Azul）：5 色瓷砖。

规则按官方/BGA 对齐：
- 工厂盘数量 = 2×人数+1（2/3/4 人 → 5/7/9），每盘发 4 片；袋空时用盒盖弃砖回填。
- 每人从一盘取走某色全部，余砖进中央；首取中央者拿起始玩家标记（占地板一格 -1），
  并成为下一轮先手。
- 花纹行从右往左填；行满只在**回合末 Wall-tiling 阶段**统一上墙计分，不立即上墙。
- 每轮末按地板格扣分并清空地板；终局额外分：整行 +2 / 整列 +7 / 某色集齐 5 片 +10。
- 有人在 Wall-tiling 后拼满整行 → 对局在该轮结束时结束（不在中途截断）。
"""
from games_pkg.base import BaseGame, GameRuleError

COLORS = ["r", "w", "b", "y", "k"]          # 红 白 蓝 黄 黑
COLOR_CN = {"r": "红", "w": "白", "b": "蓝", "y": "黄", "k": "黑"}
ROWS = 5                                     # 花纹行/墙共 5 行
ROW_PENALTY = [-1, -1, -2, -2, -2, -3, -3]   # 地板亏分（按超额度封顶 7）
MARKER = "*"                                 # 地板里的起始玩家标记占位


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
        self.lid = []            # 盒盖：本局弃砖；袋空时回填
        self.offers = []         # 每座工厂盘（list of colors）
        self.center = []         # 中央待取区
        self.center_first_taken = False
        self.rows = {u: {i: [] for i in range(ROWS)} for u in players}   # 花纹行（未满/已满）
        self.wall = {u: {(r, c): None for r in range(ROWS) for c in range(ROWS)}
                     for u in players}                                   # 墙
        self.floor = {u: [] for u in players}    # 地板砖色；MARKER 表示起始玩家标记
        self.pending = None      # 当前行动者刚取走的瓷砖
        self.turn = 0
        self.round = 1
        self.score = {u: 0 for u in players}
        self.start_uid = players[0] if players else None   # 本轮先手
        self.marker_uid = None   # 起始玩家标记持有者（None = 仍在中央）
        self.winner = None
        self.winners = []
        self._replenish()

    # ---------- 组装 ----------
    def _seed_bag(self):
        bag = []
        for c in COLORS:
            bag += [c] * 20       # 每色 20 片，共 100
        self.rng.shuffle(bag)
        return bag

    def _refill_bag(self):
        """袋空 → 用盒盖弃砖回填（官方 Preparing the next round）。"""
        if not self.bag and self.lid:
            self.bag = list(self.lid)
            self.lid = []
            self.rng.shuffle(self.bag)

    def _replenish(self):
        self._refill_bag()
        n_f = 2 * len(self.players) + 1
        self.offers = []
        for _ in range(n_f):
            bowl = []
            for _ in range(4):
                if self.bag:
                    bowl.append(self.bag.pop())
            self.offers.append(bowl)     # 砖不够时允许出现空盘
        self.center = []
        self.center_first_taken = False
        self.marker_uid = None           # 标记放回中央，等首取者拿

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
                self.center_first_taken = True
                self.marker_uid = uid
                self._to_floor(uid, [MARKER])
                msgs.append("（首取中央：拿起始玩家标记，地板 -1）")
            self.center.extend(source_list)   # 已被取空
        else:
            self.center.extend(source_list)   # 留下的进中央
            source_list[:] = []
        self.pending = taken
        return msgs + [f"💬 请选择花纹行(0~4)落砖，或点 '溢出到地板'"]

    def _to_floor(self, uid, tiles):
        """地板从左侧起填；满 7 格后多余砖回盒盖（官方 Floor line）。"""
        room = max(0, 7 - len(self.floor[uid]))
        tiles = list(tiles)
        self.floor[uid].extend(tiles[:room])
        self.lid.extend(x for x in tiles[room:] if x != MARKER)

    def _place(self, uid, action):
        if self.pending is None:
            raise GameRuleError("先取砖再落砖")
        taken = self.pending
        m = int(action.get("row", -1))
        if m == -1:
            self._to_floor(uid, taken)
            msgs = [f"🌀 {self._nick(uid)} 将 {len(taken)} 片全部溢出（地板）"]
            return msgs + self._after_place(uid)
        if not (0 <= m < ROWS):
            raise GameRuleError("行号无效")
        col = taken[0]
        cell_col = _wall_col(COLORS.index(col), m)
        if self.wall[uid][(m, cell_col)] is not None:
            raise GameRuleError("此色在本行墙格已占用")
        row = self.rows[uid][m]
        cap = m + 1
        if len(row) >= cap:
            raise GameRuleError("此行已满，等回合末上墙")
        if row and row[0] != col:
            raise GameRuleError("此行只能放同一种颜色")
        fill = min(len(taken), cap - len(row))
        row.extend(taken[:fill])
        overflow = taken[fill:]
        msgs = [f"🧱 {self._nick(uid)} 落 {COLOR_CN[col]}×{fill} 于第 {m + 1} 行"]
        if overflow:
            self._to_floor(uid, overflow)
            msgs.append(f"（溢出 {len(overflow)} 片 → 地板）")
        if len(row) == cap:
            msgs.append("（本行已满，回合末统一上墙）")
        return msgs + self._after_place(uid)

    def _after_place(self, uid):
        """一次落砖结束：移交回合；工厂与中央都空 → 进入回合末 Wall-tiling。"""
        self.pending = None
        self.turn = (self.turn + 1) % len(self.players)
        if not any(self.offers) and not self.center:
            return self._end_round()
        return []

    # ---------- 回合末 Wall-tiling ----------
    def _apply_floor(self, uid):
        """按地板格扣分并清空（0 分保底）；返回 (扣分, 扣前, 扣后)。"""
        cnt = min(len(self.floor[uid]), 7)
        loss = -sum(ROW_PENALTY[:cnt])
        before = self.score[uid]
        self.score[uid] = max(0, before - loss)
        self.lid.extend(x for x in self.floor[uid] if x != MARKER)
        self.floor[uid] = []
        return loss, before, self.score[uid]

    def _end_round(self):
        """Wall-tiling：满行统一上墙计分 → 地板结算 → 终局判定 / 下一轮。"""
        msgs = ["—— 回合结束，统一上墙 ——"]
        for u in self.players:
            for r in range(ROWS):
                row = self.rows[u][r]
                if len(row) < r + 1:            # 未满行保留到下一轮
                    continue
                col = row[0]
                c = _wall_col(COLORS.index(col), r)
                if self.wall[u][(r, c)] is None:
                    self.wall[u][(r, c)] = col
                    pts = self._score_cell(u, r, c)
                    self.score[u] += pts
                    msgs.append(f"✨ {self._nick(u)} 第 {r + 1} 行上墙，+{pts} 分")
                self.lid.extend(row[:-1])       # 其余同色砖进盒盖
                self.rows[u][r] = []
            loss, before, after = self._apply_floor(u)
            if loss:
                msgs.append(f"🧹 {self._nick(u)} 地板 -{loss} 分（{before}→{after}）")
        if self._any_full_row():
            self._finish()
            msgs.append("🏁 有人拼满整行，对局结束")
            return msgs
        if self.marker_uid is not None:
            self.start_uid = self.marker_uid     # 标记持有者先手下一轮
        self.round += 1
        self.turn = (self.players.index(self.start_uid)
                     if self.start_uid in self.players else 0)
        self._replenish()
        if not any(self.offers):                 # 袋与盒盖都空：无砖可发，直接终局
            self._finish()
            msgs.append("🏁 瓷砖耗尽，对局结束")
            return msgs
        msgs.append(f"—— 第 {self.round} 轮，重置瓷砖 ——")
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

    def _full_rows(self, uid):
        w = self.wall[uid]
        return sum(1 for r in range(ROWS)
                   if all(w[(r, c)] is not None for c in range(ROWS)))

    def _any_full_row(self):
        return any(self._full_rows(u) for u in self.players)

    def _finish(self):
        """终局加分（整行 +2 / 整列 +7 / 集齐一色 +10）并定胜负。"""
        for u in self.players:
            w = self.wall[u]
            rows_done = self._full_rows(u)
            cols_done = sum(1 for c in range(ROWS)
                            if all(w[(r, c)] is not None for r in range(ROWS)))
            colors_done = sum(1 for col in COLORS
                              if sum(1 for cell in w.values() if cell == col) == ROWS)
            self.score[u] += 2 * rows_done + 7 * cols_done + 10 * colors_done
        hi = max(self.score.values())
        leaders = [u for u in self.players if self.score[u] == hi]
        if len(leaders) > 1:                    # 平局先比完整行数
            best = max(self._full_rows(u) for u in leaders)
            leaders = [u for u in leaders if self._full_rows(u) == best]
        self.winners = leaders                  # 仍平 → 共享胜利
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
            "floor": {str(u): len(self.floor[u]) for u in self.players},
            "floor_tiles": {str(u): [x for x in self.floor[u] if x != MARKER]
                            for u in self.players},
            "score": {str(u): self.score[u] for u in self.players},
            "bag": len(self.bag), "players": list(self.players),
            "pending": list(self.pending) if self.pending else None,
            "start_uid": self.start_uid, "marker_uid": self.marker_uid,
            "winner_uid": self.winner, "winners": list(self.winners),
        }

    def ended(self):
        if self.winner:
            if len(self.winners) > 1:
                names = "、".join(self._nick(u) for u in self.winners)
                return {"winner_uid": self.winner,
                        "detail": f"平局：{names} 并列墙分最高"}
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 墙分最高"}
        return None

    def player_left(self, uid):
        if uid in self.players:
            if self.start_uid == uid:
                nxt = (self.players.index(uid) + 1) % len(self.players)
                self.start_uid = self.players[nxt]
            if self.marker_uid == uid:
                self.marker_uid = None
            if self.players[self.turn] == uid:
                self.turn = (self.turn + 1) % len(self.players)
            self.turn %= len(self.players)
        return []

    def _nick(self, uid):
        return f"玩家{uid}"
