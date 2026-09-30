# -*- coding: utf-8 -*-
"""波兰大选（区域控制/投票）：2–4 人在几块选区上轮流投放影响棋子。每投满一轮触发一次
选举结算——每选区子多者得该区票数(分)；多轮选举后总分最高者胜（并可弃一次性票翻倍某区）。"""
from games_pkg.base import BaseGame, GameRuleError

REGIONS = [(0, "北部"), (1, "东境"), (2, "首都"), (3, "西郡"), (4, "南野")]
REG_CN = dict(REGIONS)
N_REGIONS = 5
START_INFLUENCE = 8         # 每人影响棋子（分轮投放）
ELECTION_INTERVAL = 1       # 每轮（全体各投 1 枚）就结算一次选举，简化节奏


class BolanGame(BaseGame):
    name = "bolan"
    min_players = 2
    max_players = 4

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.influence = {u: START_INFLUENCE for u in players}
        self.board = {r: {u: 0 for u in players} for r in range(N_REGIONS)}
        self.used = {r: set() for r in range(N_REGIONS)}   # 本币/弃票状态（未用）
        self.score = {u: 0 for u in players}
        self.round_atl = 0            # 累计投放枚数（无槽位游戏）
        self.turn = 0
        self.election_round = 1
        self.phase = "place"
        self.winner = None

    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        if self.phase == "place":
            if action.get("op") == "place":
                return self._act_place(uid, action)
            if action.get("op") == "devote":
                return self._act_devote(uid, action)
            raise GameRuleError("未知动作")
        raise GameRuleError("当前不可操作")

    def _act_place(self, uid, action):
        try:
            r = int(action["r"])
        except (TypeError, ValueError):
            raise GameRuleError("选区无效")
        if not (0 <= r < N_REGIONS):
            raise GameRuleError("选区越界")
        if self.influence[uid] <= 0:
            raise GameRuleError("你的影响力已用完")
        self.influence[uid] -= 1
        self.board[r][uid] += 1
        msgs = [f"🗳 {self._nick(uid)} 在「{REG_CN[r]}」投 1 枚影响力棋子"]
        return self._advance(uid, msgs)

    def _act_devote(self, uid, action):
        # 弃子：以 2 枚翻倍指定选区本币影响力（加权）
        try:
            r = int(action["r"])
        except (TypeError, ValueError):
            raise GameRuleError("选区无效")
        if self.influence[uid] < 2:
            raise GameRuleError("弃子翻倍需 2 枚影响力")
        # 简化：弃 2 枚 → 该区视作 +1 加权分（以等效票体现）
        self.influence[uid] -= 2
        for _ in range(2):
            self.board[r][uid] += 1
        return [f"🔥 {self._nick(uid)} 在「{REG_CN[r]}」弃 2 枚翻倍影响力"]

    def _advance(self, uid, msgs):
        n = len(self.players)
        self.round_atl += 1
        self.turn = (self.turn + 1) % n
        # 全员各投完一轮（或用完）→ 选举
        if self.round_atl % n == 0:
            msgs += self._election()
        # 任一玩家用完全部影响力即终局
        if any(self.influence[u] <= 0 for u in self.players):
            self._finalize()
        return msgs

    def _election(self):
        msgs = []
        for r in range(N_REGIONS):
            counts = self.board[r]
            mx = max(counts.values())
            if mx == 0:
                continue
            winners = [u for u, v in counts.items() if v == mx]
            if len(winners) == 1:
                u = winners[0]
                self.score[u] += mx
                msgs.append(f"➖ 第 {self.election_round} 轮选举：「{REG_CN[r]}」由"
                            f"玩家{u} 领先，+{mx} 分")
        self.election_round += 1
        return msgs

    def _finalize(self):
        hi = max(self.score.values())
        leaders = [u for u in self.players if self.score[u] == hi]
        self.winner = leaders[0]

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "regions": REG_CN, "board": {str(r): self.board[r] for r in self.board},
            "influence": {str(u): v for u, v in self.influence.items()},
            "score": {str(u): v for u, v in self.score.items()},
            "election_round": self.election_round,
            "turn_uid": None if self.winner else self.players[self.turn],
            "players": list(self.players), "winner_uid": self.winner,
        }

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 选区票数最高获胜"}
        return None

    def player_left(self, uid):
        return []

    def _nick(self, uid):
        return f"玩家{uid}"