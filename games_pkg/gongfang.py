# -*- coding: utf-8 -*-
"""工坊（工人放置，致敬工放）：每轮生成一排工位(含奖励分/独占位)，玩家轮流用有限工人
抢占空工位拿奖励，或过牌；全员结算后进入下一轮。3 轮结束总分胜。"""
from games_pkg.base import BaseGame, GameRuleError

WORKERS = 2          # 每人每轮工人数
ROUNDS = 3


class GongfangGame(BaseGame):
    name = "gongfang"
    min_players = 2
    max_players = 4

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.round_no = 1
        self.spots = []          # spot: {"id","pts","owner","take"：city}
        self.used = set()
        self.placed = {u: 0 for u in players}
        self.done = set()        # 本轮回合结束的玩家
        self.score = {u: 0 for u in players}
        self.turn = 0
        self.winner = None
        self.current = None      # 未用
        self._new_round()

    def _new_round(self):
        n = len(self.players)
        # 工位 = 3n 个，其中 n 个「独占先手」位（1 人拿）
        self.spots = []
        for i in range(3 * n):
            self.spots.append({"id": i, "pts": self.rng.randint(1, 4),
                               "exclusive": (i % 3 == 0), "owner": None})
        self.used = set()
        self.placed = {u: 0 for u in self.players}
        self.done = set()
        self.turn = 0
        self.current = None

    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        if uid in self.done:
            raise GameRuleError("你本轮回合已结束")
        op = action.get("op")
        if op == "work":
            return self._act_work(uid, action)
        if op == "pass":
            return self._act_pass(uid)
        raise GameRuleError("未知动作")

    def _open_spots(self):
        return [s for s in self.spots if s["owner"] is None]

    def _act_work(self, uid, action):
        if self.placed[uid] >= WORKERS:
            raise GameRuleError("工人已用完")
        try:
            sid = int(action.get("id"))
        except (TypeError, ValueError):
            raise GameRuleError("工位无效")
        spot = next((s for s in self.spots if s["id"] == sid), None)
        if spot is None:
            raise GameRuleError("工位不存在")
        if spot["owner"] is not None:
            raise GameRuleError("该工位已被占用")
        # 独占位只给先手
        if spot["exclusive"]:
            pass
        spot["owner"] = uid
        self.placed[uid] += 1
        self.score[uid] += spot["pts"]
        msgs = [f"👷 {self._nick(uid)} 在工位 {sid} 工作，+{spot['pts']} 分"]
        return self._advance(uid, msgs)

    def _act_pass(self, uid):
        self.done.add(uid)
        return self._advance(uid, [f"⏭ {self._nick(uid)} 本轮回合结束"])

    def _advance(self, uid, msgs):
        n = len(self.players)
        # 下一有效玩家：尚未 done 且（有工人可用 或 不强制）
        for step in range(1, n + 1):
            nxt = (self.turn + step) % n
            tx = self.players[nxt]
            if tx not in self.done:
                self.turn = nxt
                return msgs
        # 本轮结束
        fin = self.round_no
        msgs.append(f"＝ 第 {fin} 轮结束")
        self._end_round()
        return msgs

    def _end_round(self):
        scores = {u: self.score[u] for u in self.players}
        if self.round_no >= ROUNDS:
            hi = max(scores.values())
            leaders = [u for u in self.players if scores[u] == hi]
            self.winner = leaders[0]
            return
        self.round_no += 1
        self._new_round()

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "round": self.round_no, "rounds": ROUNDS,
            "spots": [s for s in self.spots],
            "used": list(self.used),
            "placed": {str(u): v for u, v in self.placed.items()},
            "done": list(self.done),
            "score": {str(u): v for u, v in self.score.items()},
            "turn_uid": None if self.winner else self.players[self.turn],
            "players": list(self.players), "winner_uid": self.winner,
            "workers": WORKERS,
        }

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 3轮工分最高"}
        return None

    def player_left(self, uid):
        return []

    def _nick(self, uid):
        return f"玩家{uid}"