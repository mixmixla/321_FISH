# -*- coding: utf-8 -*-
"""牛头王（致敬 6 Nimmt）：104 张牌。4 列桌面递增排列。每轮所有人暗选一张，按牌面升序依次落列：
落到「比它小且最接近」的列尾；若比所有列头都小，则须吞一整列当负分并自起新列；
落列后该列超过 6 张，则列主吞其余 5 张。十轮后牛头最少者胜。"""
from games_pkg.base import BaseGame, GameRuleError

N_CARDS = 104
ROWS = 4
ROUNDS = 10


def heads(card):
    """卡的牛头数"""
    h = 1
    if card % 5 == 0:
        h = 2
    if card % 10 == 0:
        h = 3
    if card % 11 == 0:
        h = 5
    if card == 55:
        h = 7
    return h


class NimmtGame(BaseGame):
    name = "nimmt"
    min_players = 2
    max_players = 10

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        deck = list(range(1, N_CARDS + 1))
        self.rng.shuffle(deck)
        self.table = [[deck.pop()] for _ in range(ROWS)]
        hands = []
        for _ in players:
            hands.append([deck.pop() for _ in range(ROUNDS)])
        self.hands = {u: h for u, h in zip(players, hands)}
        self.choices = {}         # uid -> card
        self.bulls = {u: 0 for u in players}
        self.round = 1
        self.open_choices = None   # 本轮所有选择（揭晓后）
        self.phase = "choose"
        self.winner = None

    def _row_left_to_pick(self, card):
        """选择要吞的那列（比 card 小的列都可，简化：取最早可吞的列）"""
        cand = [i for i, r in enumerate(self.table) if r and r[-1] < card]
        return cand

    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if self.phase == "resolve":
            raise GameRuleError("本轮已在结算，等待下轮")
        if uid in self.choices:
            raise GameRuleError("本轮已出牌")
        card = action.get("card")
        try:
            card = int(card)
        except (TypeError, ValueError):
            raise GameRuleError("牌无效")
        if card not in self.hands[uid]:
            raise GameRuleError("你手牌里没有这张")
        self.hands[uid].remove(card)
        self.choices[uid] = card
        if len(self.choices) == len(self.players):
            msgs = self._resolve()
            return [f"⚔️ 全体出牌完毕，开始结算"] + msgs
        return [f"🙈 {self._nick(uid)} 暗选了一张牌"]

    def _resolve(self):
        order = sorted(self.choices.items(), key=lambda kv: kv[1])
        msgs = []
        for uid, card in order:
            best = None
            for i, r in enumerate(self.table):
                if r and r[-1] < card:
                    if best is None or r[-1] > self.table[best][-1]:
                        best = i
            if best is None:
                # 比所有列头小 → 吞一列
                ti = self._min_col()
                taken = self.table[ti]
                bh = sum(heads(x) for x in taken)
                self.bulls[uid] += bh
                self.table[ti] = [card]
                msgs.append(f"🔻 {self._nick(uid)} 出 {card}，吞下第 {ti + 1} 列（-{bh} 牛头）起新列")
            else:
                self.table[best].append(card)
                if len(self.table[best]) > 6:
                    # 超出 6 张 → 列主吞前面 5 张
                    taken = self.table[best][: -1]
                    bh = sum(heads(x) for x in taken)
                    self.bulls[uid] += bh
                    if len(taken) == 5:
                        last = self.table[best][-1]
                        self.table[best] = [last]
                    msgs.append(f"⚡ {self._nick(uid)} 出 {card} 拉爆第 {best + 1} 列（-{bh} 牛头）")
        self.choices = {}
        self.round += 1
        if self.round > ROUNDS:
            hi = max(self.bulls[u] for u in self.players)
            leaders = [u for u in self.players if self.bulls[u] == hi]
            # 牛头最少者胜 → 找最少
            lo = min(self.bulls[u] for u in self.players)
            leaders = [u for u in self.players if self.bulls[u] == lo]
            self.winner = leaders[0]
            msgs.append("🏁 十轮结束，结算牛头")
        return msgs

    def _min_col(self):
        """选吞哪列：取牛头最少的一列（简化规则）"""
        return min(range(ROWS), key=lambda i: sum(heads(x) for x in self.table[i]))

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "round": self.round, "table": self.table,
            "hands": {str(u): sorted(h) for u, h in self.hands.items()},
            "chosen": {str(u): 1 for u in self.choices},
            "bulls": {str(u): v for u, v in self.bulls.items()},
            "players": list(self.players), "winner_uid": self.winner,
            "phase": self.phase,
        }

    def private(self, uid):
        if uid not in self.hands:
            return None
        return {"hand": sorted(self.hands[uid])}

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 牛头最少"}
        return None

    def player_left(self, uid):
        if uid in self.choices:
            self.choices.pop(uid, None)
            if len(self.choices) == len([u for u in self.players if u in self.hands or u in self.choices]):
                msgs = self._resolve()
                return msgs
        return []

    def _nick(self, uid):
        return f"玩家{uid}"