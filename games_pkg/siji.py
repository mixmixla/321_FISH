# -*- coding: utf-8 -*-
"""四季物语（致敬 Seasons，引擎构筑）：3 个「季」各为一轮，抓手牌。回合从手牌打一张
进自己的引擎，或启动引擎里某张卡生产资源，或用 3 金币换 1 胜利点。三季总分胜。"""
from games_pkg.base import BaseGame, GameRuleError

SEASONS = 3
TURNS_PER_SEASON = 3          # 每季每人行动数

CARD_DEFS = [
    (0, "晶田", "crystal", 0, 2),
    (1, "金窖", "apple", 1, 2),
    (2, "胜利碑", "vt", 3, 1),
    (3, "水晶温室", "crystal", 2, 3),
    (4, "金币矿井", "apple", 2, 3),
    (5, "王冠塔", "vt", 5, 2),
    (6, "小晶圃", "crystal", 0, 1),
    (7, "徽章坊", "apple", 1, 2),
    (8, "荣耀柱", "vt", 4, 1),
]
EFFECT_CN = {"crystal": "水晶", "apple": "金币", "vt": "胜利点"}
MAX_ENGINE = 6


class SijiGame(BaseGame):
    name = "siji"
    min_players = 2
    max_players = 4

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.season = 1
        self.turns_left = TURNS_PER_SEASON * len(players)
        self.hand = {u: self._draw_hand() for u in players}
        self.engine = {u: [] for u in players}     # {"def","kind","cost","out","played":bool}
        self.crystal = {u: 3 for u in players}
        self.gold = {u: 0 for u in players}
        self.vp = {u: 0 for u in players}
        self.turn = 0
        self.winner = None

    def _draw_hand(self):
        hand = []
        deck = list(CARD_DEFS)
        self.rng.shuffle(deck)
        for idx in range(6):
            cid, name, kind, cost, out = deck[idx]
            hand.append({"id": cid, "name": name, "kind": kind,
                         "cost": cost, "out": out})
        return hand

    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if self.turns_left <= 0:
            raise GameRuleError("本季结束，等待下一季")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        op = action.get("op")
        if op == "play":
            return self._act_play(uid, action)
        if op == "activate":
            return self._act_activate(uid, action)
        if op == "convert":
            return self._act_convert(uid)
        raise GameRuleError("未知动作")

    def _next(self):
        n = len(self.players)
        self.turn = (self.turn + 1) % n
        self.turns_left -= 1
        if self.turns_left > 0:
            return
        self._next_season()

    def _next_season(self):
        if self.season >= SEASONS:
            self._finish()
            return
        self.season += 1
        self.turns_left = TURNS_PER_SEASON * len(self.players)
        self.hand = {u: self._draw_hand() for u in self.players}
        self.turn = 0

    def _act_play(self, uid, action):
        try:
            idx = int(action["idx"])
        except (TypeError, ValueError):
            raise GameRuleError("数据无效")
        if not (0 <= idx < len(self.hand[uid])):
            raise GameRuleError("手牌无效")
        if len(self.engine[uid]) >= MAX_ENGINE:
            raise GameRuleError("引擎已满（最多 6 张）")
        card = self.hand[uid].pop(idx)
        if self.crystal[uid] < card["cost"]:
            raise GameRuleError(f"水晶不足，需 {card['cost']}")
        self.crystal[uid] -= card["cost"]
        self.engine[uid].append(dict(card, played=False))
        self._next()
        return [f"🎴 {self._nick(uid)} 打出「{card['name']}」加入引擎"]

    def _act_activate(self, uid, action):
        try:
            idx = int(action["idx"])
        except (TypeError, ValueError):
            raise GameRuleError("数据无效")
        if not (0 <= idx < len(self.engine[uid])):
            raise GameRuleError("选中无效")
        card = self.engine[uid][idx]
        if card["played"]:
            raise GameRuleError("该卡本季已激活")
        card["played"] = True
        k = card["kind"]
        if k == "crystal":
            self.crystal[uid] += card["out"]
        elif k == "apple":
            self.gold[uid] += card["out"]
        else:
            self.vp[uid] += card["out"]
        self._next()
        return [f"⚙️ {self._nick(uid)} 激活「{card['name']}」：+{card['out']}{EFFECT_CN[k]}"]

    def _act_convert(self, uid):
        if self.gold[uid] < 3:
            raise GameRuleError("金币不足 3")
        self.gold[uid] -= 3
        self.vp[uid] += 1
        self._next()
        return [f"👑 {self._nick(uid)} 用 3 金币换得 1 胜利点"]

    def _finish(self):
        # 每剩 2 水晶折 1 胜，金币按 3:1 折（取整）
        for u in self.players:
            self.vp[u] += self.crystal[u] // 2 + self.gold[u] // 3
        hi = max(self.vp.values())
        leaders = [u for u in self.players if self.vp[u] == hi]
        self.winner = leaders[0]

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "season": self.season, "seasons": SEASONS,
            "turns_left": self.turns_left,
            "hand": {str(u): v for u, v in self.hand.items()},
            "engine": {str(u): v for u, v in self.engine.items()},
            "crystal": {str(u): v for u, v in self.crystal.items()},
            "gold": {str(u): v for u, v in self.gold.items()},
            "vp": {str(u): v for u, v in self.vp.items()},
            "turn_uid": None if self.winner else self.players[self.turn],
            "players": list(self.players), "winner_uid": self.winner,
        }

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 三季总分最高胜出"}
        return None

    def player_left(self, uid):
        return []

    def _nick(self, uid):
        return f"玩家{uid}"