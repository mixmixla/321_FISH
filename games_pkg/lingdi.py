# -*- coding: utf-8 -*-
"""领地（拼贴得分，致敬卡卡颂）：1x1 板块含四向地型(城/路/场)，相邻必须地型匹配，
可放米宝；当连通地型区四周被板块完全围住（无法再扩张）即关闭结算；终局清场结算。
"""
from games_pkg.base import BaseGame, GameRuleError

SIZE = 9                       # 9x9 开放网格
FEAT_CN = {"c": "城", "r": "路", "f": "场"}
DIRS = ["N", "E", "S", "W"]
OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}


class LingdiGame(BaseGame):
    name = "lingdi"
    min_players = 2
    max_players = 4

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        # 生成板块牌堆：每块 four edges 地型
        self.deck = [self._random_tile() for _ in range(4 * len(players) + 10)]
        self.rng.shuffle(self.deck)
        self.board = {}          # (r,c) -> {"edges": {d: kind}, "owner": uid|None}
        self.placed = 0
        self.turn = 0
        self.current = None      # 当前抽到的板块
        self.meeples = {u: 3 for u in players}   # 每个米宝数（简化 3 个）
        self.score = {u: 0 for u in players}
        self.closed_uid = None
        self.winner = None
        self._draw()

    def _random_tile(self):
        kinds = ["c", "r", "f"]
        edges = {d: self.rng.choice(kinds) for d in DIRS}
        return {"edges": edges}

    def _draw(self):
        self.current = self.deck.pop(0) if self.deck else None
        return not self.deck

    # ---------- 连通区 ----------
    def _region(self, r, c):
        """返回 (cells, closed)：从 (r,c) 出发，按主导地型相等相连的板块区；
        closed = 区中每格的 4 邻均已被板块占据（无法扩张）。"""
        root = self._main_feat(self.board[(r, c)]["edges"])
        stack = [(r, c)]
        seen = [(r, c)]
        while stack:
            cr, cc = stack.pop()
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = cr + dr, cc + dc
                if (nr, nc) in self.board and (nr, nc) not in seen \
                        and self._main_feat(self.board[(nr, nc)]["edges"]) == root:
                    seen.append((nr, nc))
                    stack.append((nr, nc))
        closed = all(all((nr + dr, nc + dc) in self.board
                         for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)))
                     for nr, nc in seen)
        return seen, closed

    def _main_feat(self, edges):
        # 取该块出现次数最多的地型
        cnt = {}
        for d in DIRS:
            cnt[edges[d]] = cnt.get(edges[d], 0) + 1
        return max(cnt, key=cnt.get)

    # ---------- 动作 ----------
    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if self.current is None:
            raise GameRuleError("牌堆已尽，对局结束")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        op = action.get("op")
        if op == "place":
            return self._act_place(uid, action)
        if op == "pass":
            return self._act_pass(uid)
        raise GameRuleError("未知动作")

    def _act_place(self, uid, action):
        try:
            r, c = int(action["r"]), int(action["c"])
        except (TypeError, ValueError):
            raise GameRuleError("坐标无效")
        if (r, c) in self.board:
            raise GameRuleError("该位置已有板块")
        if not (0 <= r < SIZE and 0 <= c < SIZE):
            raise GameRuleError("越界")
        # 必须与至少一块已放板块相邻，且共享边地型相等
        nbs = self._neighbors(r, c)
        if self.board and not nbs:
            raise GameRuleError("必须与已放板块相邻")
        for d, nb in nbs:
            br, bc = nb
            opp = OPP[d]
            if self.board[(br, bc)]["edges"][d] != self.current["edges"][opp]:
                raise GameRuleError("相邻地型不匹配")
        # 放置
        edges = dict(self.current["edges"])
        self.board[(r, c)] = {"edges": edges, "owner": None}
        self.placed += 1
        msgs = [f"🏗 {self._nick(uid)} 放置板块 ({r},{c}) {self._feat_short(edges)}"]
        # 放米宝
        pos = action.get("meeple")  # "r,c" 或 None
        if pos and self.meeples[uid] > 0:
            if pos == "self":
                pos = f"{r},{c}"
            mr, mc = pos.split(",")
            mr, mc = int(mr), int(mc)
            if (mr, mc) not in self.board:
                raise GameRuleError("米宝位置无板块")
            if self.board[(mr, mc)]["owner"] is not None:
                raise GameRuleError("该区已有米宝")
            reg, closed = self._region(mr, mc)
            if any(self.board[x]["owner"] not in (None, uid) for x in reg):
                raise GameRuleError("该连通区已有其他玩家米宝")
            self.board[(mr, mc)]["owner"] = uid
            self.meeples[uid] -= 1
            msgs.append(f"🧑‍🌾 {self._nick(uid)} 在 ({mr},{mc}) 放米宝")
            self._score_regions()
        self._next_turn()
        return msgs

    def _act_pass(self, uid):
        self._next_turn()
        return [f"⏭ {self._nick(uid)} 跳过"]

    def _next_turn(self):
        if self._draw():                 # 牌堆尽 → 结算存量
            self._final_scoring()
            return
        # 若手牌板块无处可放则自动跳过（简化：仍轮转）
        self.turn = (self.turn + 1) % len(self.players)

    def _neighbors(self, r, c):
        out = {}
        for d, (dr, dc) in [("N", (-1, 0)), ("S", (1, 0)), ("W", (0, -1)), ("E", (0, 1))]:
            nr, nc = r + dr, c + dc
            if (nr, nc) in self.board:
                out[d] = (nr, nc)
        return out

    def _score_regions(self):
        # 扫描所有带米宝的板块，若其连通区已关闭则结算
        seen_cells = set()
        for (r, c), cell in self.board.items():
            if cell["owner"] is None or (r, c) in seen_cells:
                continue
            reg, closed = self._region(r, c)
            for x in reg:
                seen_cells.add(x)
            owners = {self.board[x]["owner"] for x in reg} - {None}
            if closed and owners:
                gain = len(reg)
                for o in owners:
                    self.score[o] += gain
                    # 收回米宝
                    for x in reg:
                        if self.board[x]["owner"] == o:
                            self.board[x]["owner"] = None
                            self.meeples[o] = min(self.meeples[o] + 1, 3)
        self._check_end()

    def _final_scoring(self):
        seen = set()
        for (r, c), cell in self.board.items():
            if cell["owner"] is None or (r, c) in seen:
                continue
            reg, _ = self._region(r, c)
            for x in reg:
                seen.add(x)
            owners = {self.board[x]["owner"] for x in reg} - {None}
            if owners:
                gain = len(reg)
                for o in owners:
                    self.score[o] += gain
        self._check_end()

    def _check_end(self):
        self._maybe_winner()

    def _maybe_winner(self):
        if self.current is not None:
            return
        hi = max(self.score.values())
        leaders = [u for u in self.players if self.score[u] == hi]
        self.winner = leaders[self.rng.choice(range(len(leaders)))] if len(leaders) == 1 else leaders[0]

    def _feat_short(self, edges):
        return "/".join(FEAT_CN[edges[d]] for d in DIRS)

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "board": {f"{r},{c}": cell for (r, c), cell in self.board.items()},
            "current": self.current, "deck_left": len(self.deck),
            "meeples": {str(u): v for u, v in self.meeples.items()},
            "score": {str(u): v for u, v in self.score.items()},
            "turn_uid": None if self.winner else self.players[self.turn],
            "players": list(self.players), "winner_uid": self.winner,
            "size": SIZE,
        }

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 领地得分最高胜出"}
        return None

    def player_left(self, uid):
        self.turn = self.turn % len(self.players)
        return []

    def _nick(self, uid):
        return f"玩家{uid}"