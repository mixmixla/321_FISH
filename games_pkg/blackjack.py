# -*- coding: utf-8 -*-
"""21 点（Blackjack）：庄家为服务器自动代打，多人下注/要牌/停牌/比点。"""
from games_pkg.base import BaseGame, GameRuleError

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def _build_deck(rng) -> list:
    """6 副牌，返回 [(suit, rank), ...]"""
    cards = [(s, r) for _ in range(6) for s in SUITS for r in RANKS]
    rng.shuffle(cards)
    return cards


def _value(rank: str, hand_total: int) -> int:
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 1 if hand_total + 11 > 21 else 11
    return int(rank)


def _card_str(card) -> str:
    return f"{card[1]}{card[0]}"


class BlackjackGame(BaseGame):
    name = "blackjack"
    min_players = 2
    max_players = 8

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.scores = {u: 0 for u in players}
        self.round = 0
        self.phase = "betting"            # betting | playing | settling | round_end
        self.deck = _build_deck(self.rng)
        self.hands = {u: [] for u in players}
        self.dealer = []
        self.current_idx = 0
        self.stand = set()
        self.results = {}                 # uid -> win/lose/push/blackjack
        self.round_end_at = 0.0
        self.gap = 3.0

    def snapshot(self) -> dict:
        return {
            "game": self.name, "status": self.phase, "round": self.round,
            "players": list(self.players), "scores": dict(self.scores),
            "hands": {str(u): [_card_str(c) for c in h] for u, h in self.hands.items()},
            "hand_values": {str(u): self._hand_value(h) for u, h in self.hands.items()},
            "dealer": [_card_str(c) for c in self.dealer],
            "dealer_value": self._hand_value(self.dealer),
            "current_uid": self.players[self.current_idx] if self.phase == "playing" else None,
            "stand": sorted(self.stand),
            "results": {str(u): r for u, r in self.results.items()},
        }

    def act(self, uid: int, action: dict) -> list:
        if action.get("action") == "hit":
            return self._hit(uid)
        if action.get("action") == "stand":
            return self._stand(uid)
        raise GameRuleError("未知动作")

    def _hand_value(self, hand) -> int:
        total = 0
        for _, rank in hand:
            total += _value(rank, total)
        return total

    # ---- 开局 ----
    def _start_round(self) -> list:
        self.round += 1
        self.phase = "playing"
        self.deck = _build_deck(self.rng)
        self.hands = {u: [] for u in self.players}
        self.dealer = []
        self.stand = set()
        self.results = {}
        for u in self.players:
            self.hands[u].append(self.deck.pop())
        self.dealer.append(self.deck.pop())
        for u in self.players:
            self.hands[u].append(self.deck.pop())
        self.dealer.append(self.deck.pop())
        self.current_idx = 0
        # 庄家明牌 A 或 10 点时可提前检查 blackjack
        msgs = [f"第 {self.round} 局开始，每人 2 张牌（固定下注 1 分）"]
        if self._hand_value(self.dealer) == 21:
            self._settle(announce=True)
        return msgs

    def _next_player(self) -> int | None:
        while self.current_idx < len(self.players):
            u = self.players[self.current_idx]
            if u not in self.stand and self._hand_value(self.hands[u]) <= 21:
                return u
            self.current_idx += 1
        return None

    def _hit(self, uid: int) -> list:
        if self.phase != "playing" or uid != self.players[self.current_idx]:
            raise GameRuleError("还没轮到你")
        if uid in self.stand:
            raise GameRuleError("你已停牌")
        self.hands[uid].append(self.deck.pop())
        msgs = [f"{self._nick(uid)} 要牌：{_card_str(self.hands[uid][-1])}（合计 {self._hand_value(self.hands[uid])}）"]
        if self._hand_value(self.hands[uid]) > 21:
            self.stand.add(uid)
            msgs.append(f"{self._nick(uid)} 爆牌！")
            self._advance_or_settle(msgs)
        return msgs

    def _stand(self, uid: int) -> list:
        if self.phase != "playing" or uid != self.players[self.current_idx]:
            raise GameRuleError("还没轮到你")
        self.stand.add(uid)
        msgs = [f"{self._nick(uid)} 停牌（{self._hand_value(self.hands[uid])}）"]
        self._advance_or_settle(msgs)
        return msgs

    def _advance_or_settle(self, msgs: list):
        nxt = self._next_player()
        if nxt is None:
            self._settle(announce=True, msgs=msgs)
        else:
            self.current_idx = self.players.index(nxt)

    def _settle(self, announce=False, msgs=None) -> list:
        msgs = msgs if msgs is not None else []
        self.phase = "settling"
        while self._hand_value(self.dealer) < 17:
            self.dealer.append(self.deck.pop())
        dv = self._hand_value(self.dealer)
        msgs.append(f"庄家牌：{' '.join(_card_str(c) for c in self.dealer)}（{dv}）")
        self.results = {}
        for u in self.players:
            hv = self._hand_value(self.hands[u])
            if hv > 21:
                self.results[u] = "lose"
            elif dv > 21 or hv > dv:
                self.results[u] = "win"
                self.scores[u] += 1
            elif hv == dv:
                self.results[u] = "push"
            else:
                self.results[u] = "lose"
            msgs.append(f"{self._nick(u)}：{hv} → "
                        + {"win": "胜 +1", "lose": "负", "push": "平"}[self.results[u]])
        self.phase = "round_end"
        self.round_end_at = self._clock_now() + self.gap
        return msgs

    def tick(self, now: float) -> list:
        if self.phase == "round_end" and now >= self.round_end_at:
            return self._start_round()
        if self.phase == "betting":
            return self._start_round()
        return []

    def ended(self):
        return None

    def player_left(self, uid: int) -> list:
        """对局中掉线：剔除并推进轮次，避免 `_next_player` 空转卡死"""
        if uid not in self.players:
            return []
        idx = self.players.index(uid)
        del self.players[idx]
        self.hands.pop(uid, None)
        self.scores.pop(uid, None)
        self.stand.discard(uid)
        self.results.pop(uid, None)
        msgs = [f"{self._nick(uid)} 离开了游戏"]
        n = len(self.players)
        if n == 0:
            self.phase = "round_end"
            return msgs
        if idx < self.current_idx:
            self.current_idx -= 1
        if self.current_idx >= n:
            self.current_idx = 0
        if self.phase == "playing":
            if n < 2:
                self.phase = "round_end"
                self.results = {u: "lose" for u in self.players}
                self.round_end_at = self._clock_now() + self.gap
                msgs.append("剩余玩家不足 2 人，对局结束")
                return msgs
            nxt = self._next_player()
            if nxt is None:
                self._settle(announce=False, msgs=msgs)
            else:
                self.current_idx = self.players.index(nxt)
        return msgs

    def _clock_now(self) -> float:
        import time
        return time.time()

    def _nick(self, uid: int) -> str:
        return f"玩家{uid}"
