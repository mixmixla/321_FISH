# -*- coding: utf-8 -*-
"""快艇骰子（致敬 Yahtzee）：5 枚骰子，每回合最多掷 3 次，挑选一个分类记分；共 13 分类
全部填满后终局。上区合计≥63 加发 35。分类全原创中文皮。"""
from games_pkg.base import BaseGame, GameRuleError

CATS = ["1", "2", "3", "4", "5", "6", "three", "four", "house", "small", "large", "yahtzee", "chance"]
CAT_CN = {"1": "1点", "2": "2点", "3": "3点", "4": "4点", "5": "5点", "6": "6点",
          "three": "三条", "four": "四条", "house": "葫芦", "small": "小顺",
          "large": "大顺", "yahtzee": "快艇", "chance": "任意"}


def _counts(dice):
    c = {}
    for d in dice:
        c[d] = c.get(d, 0) + 1
    return c


def _cat_score(cat, dice):
    c = _counts(dice)
    if cat in "123456":
        f = int(cat)
        return f * c.get(f, 0)
    if cat == "three":
        return sum(dice) if max(c.values()) >= 3 else 0
    if cat == "four":
        return sum(dice) if max(c.values()) >= 4 else 0
    if cat == "house":
        v = sorted(c.values())
        return 25 if v == [2, 3] else 0
    uniq = sorted(c)
    if cat == "small":
        for base in range(1, 4):
            if all(x in uniq for x in (base, base + 1, base + 2, base + 3)):
                return 30
        return 0
    if cat == "large":
        return 40 if uniq == [1, 2, 3, 4, 5] or uniq == [2, 3, 4, 5, 6] else 0
    if cat == "yahtzee":
        return 50 if max(c.values()) == 5 else 0
    if cat == "chance":
        return sum(dice)
    return 0


class YahtzeeGame(BaseGame):
    name = "yahtzee"
    min_players = 2
    max_players = 8

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.turn = 0
        self.round = 1
        self.total_rounds = 13 * len(players)
        self.dice = [1, 1, 1, 1, 1]
        self.rolls_left = 0          # 当回合剩余可重掷次数
        self.category = None         # 本回合是否已记分
        self.scores = {u: {cat: None for cat in CATS} for u in players}
        self.totals = {u: 0 for u in players}
        self.done = None

    def _cur(self):
        return self.players[self.turn]

    def _turn_done(self, uid):
        return all(v is not None for v in self.scores[uid].values())

    def act(self, uid, action):
        if self.done:
            raise GameRuleError("本局已结束")
        if uid != self._cur():
            raise GameRuleError("还没轮到你")
        op = action.get("op")
        if op == "roll":
            return self._roll(uid)
        if op == "reroll":
            return self._reroll(uid, action)
        if op == "score":
            return self._score(uid, action)
        raise GameRuleError("未知动作")

    def _roll(self, uid):
        if self.scores[uid]["1"] is not None:
            # 玩家牌全部填过 → 直接下一家
            self._next()
            return [f"⏭ {self._nick(uid)} 已填满分类"]
        self.dice = [self.rng.randint(1, 6) for _ in range(5)]
        self.rolls_left = 2
        self.category = None
        return [f"🎲 {self._nick(uid)} 掷骰：" + " ".join(str(d) for d in self.dice)
                + "（可再重掷 2 次）"]

    def _reroll(self, uid, action):
        if self.category:
            raise GameRuleError("已记分")
        if self.rolls_left <= 0:
            raise GameRuleError("本回合重掷次数用完")
        raw = action.get("keep", [])
        try:
            keep = set(int(x) for x in raw)
        except (TypeError, ValueError):
            raise GameRuleError("保留位无效")
        for k in keep:
            if not (0 <= k < 5):
                raise GameRuleError("骰子位无效")
        self.dice = [self.dice[k] for k in keep] \
            + [self.rng.randint(1, 6) for _ in range(5 - len(keep))]
        self.rolls_left -= 1
        joined = " ".join(str(d) for d in self.dice)
        return [f"🔁 重掷：{joined}（剩 {self.rolls_left} 次）"]

    def _score(self, uid, action):
        if self.category:
            raise GameRuleError("本回合已记分")
        cat = action.get("cat")
        if cat not in CATS:
            raise GameRuleError("分类无效")
        if self.scores[uid][cat] is not None:
            raise GameRuleError("该分类已记分")
        pts = _cat_score(cat, self.dice)
        self.scores[uid][cat] = pts
        self.totals[uid] += pts
        self.category = True
        hi = [c for c in "123456" if self.scores[uid][c] is not None]
        bonus = 35 if len(hi) == 6 and sum(self.scores[uid][c] for c in hi) >= 63 else 0
        if bonus:
            self.totals[uid] += bonus
        msgs = [f"📝 {self._nick(uid)} 记 {CAT_CN[cat]} = {pts} 分"
                + (f"，上区≥63 奖励 +35" if bonus else "")]
        self._next()
        return msgs

    def _next(self):
        if self.done:
            return
        self.turn = (self.turn + 1) % len(self.players)
        self.round += 1
        self.rolls_left = 0
        self.category = None
        if self.round > self.total_rounds or all(self._turn_done(u) for u in self.players):
            hi = max(self.totals[u] for u in self.players)
            leaders = [u for u in self.players if self.totals[u] == hi]
            self.done = leaders[0]

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "turn_uid": self._cur(), "round": self.round,
            "dice": self.dice, "rolls_left": self.rolls_left,
            "category": self.category, "cats": CAT_CN,
            "scores": {str(u): {c: v for c, v in row.items()}
                       for u, row in self.scores.items()},
            "totals": {str(u): v for u, v in self.totals.items()},
            "players": list(self.players), "winner_uid": self.done,
        }

    def ended(self):
        if self.done:
            return {"winner_uid": self.done,
                    "detail": f"{self._nick(self.done)} 总分最高"}
        return None

    def player_left(self, uid):
        if uid in self.players and self.players[self.turn] == uid:
            self._next()
        return []

    def _nick(self, uid):
        return f"玩家{uid}"