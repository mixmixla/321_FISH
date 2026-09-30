# -*- coding: utf-8 -*-
"""骗子酒馆（坦白·吹牛）。每人手牌为暗牌（0~9，可重复），轮流把一张牌扣到桌面中央并公开「报数」。
下一位可继续出牌（自设报数）或「挑战」上一位的报数；戳穿则报数者喝毒，猜错则挑战者喝毒。
每人累计 3 杯出局，最后留在桌上的玩家获胜。"""
from games_pkg.base import BaseGame, GameRuleError

VALUES = list(range(10))     # 0~9
MAX_DRINK = 3                # 喝满出局
HAND = 5                     # 起手牌


class LiarGame(BaseGame):
    name = "liar"
    min_players = 2
    max_players = 10

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.players = list(players)
        self._deal()
        self.phase = "play"        # play 阶段（持续出牌/挑战）
        self.turn_idx = 0          # 当前行动者 index
        self.pending = None        # 待挑战牌 {"uid", "claim", "val"}
        self.discard = []          # 已 出牌/被翻开 的弃牌
        self.drink = {u: 0 for u in players}   # 每人酒量（毒标）
        self.out = set()           # 被淘汰者
        self.winner = None
        self.detail = None
        self._skip_dead()

    def _deal(self):
        n = len(self.players)
        deck = list(VALUES) * ((n * HAND) // len(VALUES) + 1)
        self.rng.shuffle(deck)
        self.hand = {u: [] for u in self.players}
        for u in self.players:
            self.hand[u] = deck[:HAND]
            del deck[:HAND]
        self.deck_pool = deck        # 未发剩余（可再洗用）

    # ---- 快照/私密 ----
    def snapshot(self):
        alive = [u for u in self.players if u not in self.out]
        pending = None
        if self.pending:
            pending = {"uid": self.pending["uid"], "claim": self.pending["claim"]}
        return {
            "game": self.name, "phase": self.phase,
            "players": list(self.players),
            "alive": alive,
            "turn": self._turn_uid(),
            "pending": pending,
            "pending_count": len(self.pending["uid"]) if False else (0 if not self.pending else 1),
            "drink": {str(u): self.drink[u] for u in self.players},
            "hand_size": {str(u): len(self.hand[u]) for u in self.players},
            "winner": self.winner, "done": self.winner is not None,
        }

    def private(self, uid):
        if uid not in self.hand:
            return None
        return {"hand": sorted(self.hand[uid])}

    def act(self, uid, action):
        if self.winner is not None:
            raise GameRuleError("本局已结束")
        if uid != self._turn_uid():
            raise GameRuleError("还没轮到你")
        op = action.get("op")
        if op == "play":
            return self._play(uid, action)
        if op == "challenge":
            return self._challenge(uid)
        raise GameRuleError("未知操作")

    def _turn_uid(self):
        return self.players[self.turn_idx]

    def _skip_dead(self):
        """跳过已淘汰/空手且无牌可出的玩家；只剩一人时判胜"""
        alive = [p for p in self.players if p not in self.out]
        if len(alive) == 1 and self.winner is None:
            self.winner = alive[0]
            self.detail = "最后留在桌上的玩家获胜"
            return
        for _ in range(len(self.players)):
            u = self._turn_uid()
            if u not in self.out and self.hand[u]:
                return
            self.turn_idx = (self.turn_idx + 1) % len(self.players)

    def _play(self, uid, action):
        cards = self.hand[uid]
        val = action.get("card")
        if val not in VALUES or val not in cards:
            raise GameRuleError("你必须出一张自己手牌里有的牌值")
        claim = action.get("claim")
        if claim not in VALUES:
            raise GameRuleError("报数需在 0~9 之间")
        cards.remove(val)
        # 从手牌补一张（若池中有牌），保证手牌不空
        if len(cards) < HAND and self.deck_pool:
            cards.append(self.deck_pool.pop())
        self.pending = {"uid": uid, "claim": claim, "val": val}
        self.turn_idx = (self.turn_idx + 1) % len(self.players)
        self._skip_dead()
        return [f"🃏 {self._nick(uid)} 扣出一张牌，报数 {claim}（真值保密）"]

    def _challenge(self, uid):
        if not self.pending:
            raise GameRuleError("当前没有可挑战的牌")
        pend = self.pending
        liars = []
        if pend["val"] == pend["claim"]:
            drinker = uid           # 对方说真话，挑战者喝
            liars.append(f"✅ {self._nick(pend['uid'])} 说的 {pend['claim']} 是真牌，{self._nick(uid)} 猜错")
        else:
            drinker = pend["uid"]   # 吹牛被戳穿，报数者喝
            liars.append(f"💥 {self._nick(pend['uid'])} 报 {pend['claim']} 实为 {pend['val']}，说谎被戳穿")
        self.discard.append(pend["val"])
        self.pending = None
        self.drink[drinker] += 1
        msgs = liars + [f"🍺 {self._nick(drinker)} 喝一杯（{self.drink[drinker]}/{MAX_DRINK}）"]
        if self.drink[drinker] >= MAX_DRINK:
            self.out.add(drinker)
            msgs.append(f"🥃 {self._nick(drinker)} 喝醉出局！")
        self.turn_idx = (self.turn_idx + 1) % len(self.players)
        self._skip_dead()
        return msgs

    def ended(self):
        if self.winner is None:
            return None
        return {"winner_uid": self.winner, "detail": self.detail or f"{self._nick(self.winner)} 获胜"}

    def _nick(self, uid):
        return f"玩家{uid}"