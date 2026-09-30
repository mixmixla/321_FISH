# -*- coding: utf-8 -*-
"""扑克配对接龙（王八/吱钓）：每人发牌先配对弃掉，一轮摸下一家一张牌再配对。
最终剩 1 张无法配对的牌，持牌者成为「王八」落败，其余人安全。纯运气欢乐向。"""
from collections import Counter

from games_pkg.base import BaseGame, GameRuleError

SUITS = "♠♥♦♣"
RANK_STR = {
    1: "A", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7",
    8: "8", 9: "9", 10: "10", 11: "J", 12: "Q", 13: "K",
}


def _card_str(card) -> str:
    return f"{RANK_STR[card[0]]}{card[1]}"


def _drop_pairs(hand: list) -> list:
    """每种牌面保留至多 1 张，成对即弃"""
    cnt = Counter(c[0] for c in hand)
    seen = set()
    out = []
    for card in hand:
        if cnt[card[0]] % 2 and card[0] not in seen:
            seen.add(card[0])
            out.append(card)
    return out


class MatchPairsGame(BaseGame):
    name = "matchpairs"
    min_players = 2
    max_players = 5

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.hands = {u: [] for u in players}
        self.turn = 0
        self.loser_uid = None
        self.safe = set()           # 空手安全的玩家
        self._deal()

    def _deal(self) -> None:
        deck = [(r, s) for r in range(1, 14) for s in SUITS]
        deck.remove((12, "♠"))      # 去掉黑桃Q，使场上 51 张（奇数）：最终必剩 1 张配不成对即王八
        self.rng.shuffle(deck)
        self.hands = {u: [] for u in self.players}
        for i, card in enumerate(deck):
            self.hands[self.players[i % len(self.players)]].append(card)
        for u in self.players:
            self.hands[u] = _drop_pairs(self.hands[u])
            if not self.hands[u]:
                self.safe.add(u)
        self.turn = self._first_with_cards()

    def snapshot(self) -> dict:
        return {
            "game": self.name, "status": "playing",
            "turn_uid": None if self.loser_uid else self._current(),
            "players": list(self.players),
            "hand_size": {str(u): len(self.hands[u]) for u in self.players},
            "safe": sorted(self.safe), "loser_uid": self.loser_uid,
        }

    def private(self, uid: int) -> dict:
        if uid in self.hands:
            return {"hand": [_card_str(c) for c in self.hands[uid]]}
        return None

    def act(self, uid: int, action: dict) -> list:
        if self.loser_uid is not None:
            raise GameRuleError("本局已结束，请开新局")
        if uid != self._current():
            raise GameRuleError("还没轮到你")
        target = self._next_with_cards()
        if target is None:
            self._finish(uid)
            return ["仅剩你可配对，其余玩家皆已安全"]
        card = self.rng.choice(self.hands[target])
        self.hands[target].remove(card)
        self.hands[uid].append(card)
        peer = [c for c in self.hands[uid] if c[0] == card[0] and c != card]
        if peer:
            self.hands[uid].remove(card)
            self.hands[uid].remove(peer[0])
        msgs = [f"{self._nick(uid)} 从 {self._nick(target)} 摸到 {_card_str(card)}"
                + (f"，凑对丢弃 {_card_str(card)}{_card_str(peer[0])}" if peer else "")]
        if not self.hands[uid]:
            self.safe.add(uid)
            msgs.append(f"{self._nick(uid)} 已配完，安全！")
        self._advance_turn()
        loser = self._find_loser()
        if loser:
            self._finish(loser)
            msgs.append(f"🐢 {self._nick(loser)} 只剩 1 张无法配对，成为王八！")
        return msgs

    def _first_with_cards(self) -> int:
        for i, u in enumerate(self.players):
            if self.hands[u]:
                return i
        return 0

    def _advance_turn(self) -> None:
        n = len(self.players)
        for _ in range(n):
            self.turn = (self.turn + 1) % n
            if self.hands[self.players[self.turn]]:
                return

    def _current(self) -> int:
        return self.players[self.turn]

    def _next_with_cards(self) -> int | None:
        n = len(self.players)
        for step in range(1, n):
            u = self.players[(self.turn + step) % n]
            if self.hands[u]:
                return u
        return None

    def _find_loser(self) -> int | None:
        with_cards = [u for u in self.players if self.hands[u]]
        if not with_cards:
            return None
        # 场上只剩最后 1 张（奇数）时，持单张者为王八
        total = sum(len(self.hands[u]) for u in with_cards)
        if total == 1:
            return next(u for u in with_cards if self.hands[u])
        return None

    def _finish(self, loser: int) -> None:
        self.loser_uid = loser
        self.turn = 0

    def ended(self):
        if self.loser_uid is not None:
            return {"winner_uid": None,
                    "detail": f"🐢 {self._nick(self.loser_uid)} 成为王八"}
        return None

    def player_left(self, uid: int) -> list:
        if uid not in self.hands:
            return []
        old_idx = self.players.index(uid)
        hand = self.hands[uid]
        self.players.remove(uid)
        self.hands.pop(uid, None)
        self.safe.discard(uid)
        if hand:
            target = self.players[old_idx] if old_idx < len(self.players) else self.players[-1]
            if target != uid:
                self.hands[target].extend(hand)
                self.hands[target] = _drop_pairs(self.hands[target])
                self.safe.discard(target)
        # 重排轮次：当前玩家若已走/空手则落到下一个有牌者
        if (self.turn >= len(self.players)
                or self.players[self.turn] not in self.hands
                or not self.hands[self.players[self.turn]]):
            self.turn = self._first_with_cards()
        loser = self._find_loser()
        if loser:
            self._finish(loser)
        return []

    def _nick(self, uid: int) -> str:
        return f"玩家{uid}"