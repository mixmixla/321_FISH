# -*- coding: utf-8 -*-
"""扑克配对接龙（王八/吱钓）：每人发牌先配对弃掉，一轮摸下一家一张牌再配对。
最终剩 1 张无法配对的牌，持牌者成为「王八」落败，其余人安全。纯运气欢乐向。"""
from collections import Counter
from uuid import uuid4

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
        self.round_key = uuid4().hex  # Distinguishes two deals without exposing the shuffle seed.
        self.seq = 0
        self.discarded_pairs = 0
        self.last_pair = None
        self.last_draw = None
        self._drawn_card = None
        self._deal()

    def _deal(self) -> None:
        deck = [(r, s) for r in range(1, 14) for s in SUITS]
        deck.remove((12, "♠"))      # 去掉黑桃Q，使场上 51 张（奇数）：最终必剩 1 张配不成对即王八
        self.rng.shuffle(deck)
        self.hands = {u: [] for u in self.players}
        for i, card in enumerate(deck):
            self.hands[self.players[i % len(self.players)]].append(card)
        for u in self.players:
            before = len(self.hands[u])
            self.hands[u] = _drop_pairs(self.hands[u])
            self.discarded_pairs += (before - len(self.hands[u])) // 2
            if not self.hands[u]:
                self.safe.add(u)
        self.turn = self._first_with_cards()
        loser = self._find_loser()
        if loser is not None:
            self._finish(loser)

    def snapshot(self) -> dict:
        current = self._current() if self.players and self.loser_uid is None else None
        return {
            "game": self.name, "status": "playing",
            "turn_uid": current,
            "draw_from_uid": self._next_with_cards() if current is not None else None,
            "players": list(self.players),
            "hand_size": {str(u): len(self.hands[u]) for u in self.players},
            "safe": sorted(self.safe), "loser_uid": self.loser_uid,
            "round_key": self.round_key, "seq": self.seq,
            "discarded_pairs": self.discarded_pairs,
            "last_pair": dict(self.last_pair) if self.last_pair else None,
            "last_draw": dict(self.last_draw) if self.last_draw else None,
        }

    def private(self, uid: int) -> dict:
        if uid in self.hands:
            result = {"hand": [_card_str(c) for c in self.hands[uid]],
                      "owner_uid": uid, "round_key": self.round_key, "seq": self.seq}
            if self._drawn_card is not None and self.last_draw["uid"] == uid:
                result["drawn_card"] = _card_str(self._drawn_card)
            return result
        return None

    def act(self, uid: int, action: dict) -> list:
        if self.loser_uid is not None:
            raise GameRuleError("本局已结束，请开新局")
        if not isinstance(action, dict):
            raise GameRuleError("动作数据无效")
        op = action.get("op")
        if op is None:
            if action.get("draw") is not True:
                raise GameRuleError("缺少摸牌参数")
        elif op == "draw":
            if "draw" in action and action.get("draw") is not True:
                raise GameRuleError("缺少摸牌参数")
        else:
            raise GameRuleError(f"未知动作: {op}")
        turn = self._turn_with_cards()
        if turn is None or uid != self.players[turn]:
            raise GameRuleError("还没轮到你")
        target = self._next_with_cards(turn)
        indexed = "index" in action
        if indexed and (action.get("round_key") != self.round_key
                        or type(action.get("seq")) is not int or action["seq"] != self.seq
                        or target is None or type(action.get("target")) is not int
                        or action["target"] != target
                        or type(action["index"]) is not int
                        or not 0 <= action["index"] < len(self.hands[target])):
            raise GameRuleError("牌面已变化，请重新选择")
        if target is None:
            self._finish(uid)
            return ["仅剩你可配对，其余玩家皆已安全"]
        wanted = action.get("target", action.get("from"))
        if wanted is not None:
            try:
                wanted = int(wanted)
            except (TypeError, ValueError):
                raise GameRuleError("目标不在对局")
            if wanted not in self.players or wanted == uid:
                raise GameRuleError("目标不在对局")
            if wanted != target:
                raise GameRuleError("只能摸下一家的牌")
        self.turn = turn
        index = action["index"] if indexed else self.rng.randrange(len(self.hands[target]))
        card = self.hands[target].pop(index)
        self.seq += 1
        if not self.hands[target]:
            self.safe.add(target)            # 被摸空手也是安全，快照/名册要一致
        self.hands[uid].append(card)
        peer = [c for c in self.hands[uid] if c[0] == card[0] and c != card]
        self.last_draw = {"uid": uid, "target": target, "index": index,
                          "paired": bool(peer), "seq": self.seq}
        self._drawn_card = None if peer else card
        if peer:
            self.hands[uid].remove(card)
            self.hands[uid].remove(peer[0])
            self.discarded_pairs += 1
            self.last_pair = {"uid": uid, "cards": (_card_str(card), _card_str(peer[0])),
                              "seq": self.seq}
        msgs = [f"{self._nick(uid)} 从 {self._nick(target)} 抽了 1 张牌"
                + (f"，凑对丢弃 {_card_str(card)}{_card_str(peer[0])}" if peer else "")]
        if not self.hands[uid]:
            self.safe.add(uid)
            msgs.append(f"{self._nick(uid)} 已配完，安全！")
        self._advance_turn()
        loser = self._find_loser()
        if loser is not None:
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

    def _skip_empty_turn(self) -> None:
        """当前座位已空手（安全）时向前跳过，避免空手玩家发动作或卡住轮次。"""
        turn = self._turn_with_cards()
        if turn is not None:
            self.turn = turn

    def _turn_with_cards(self) -> int | None:
        n = len(self.players)
        for step in range(n):
            turn = (self.turn + step) % n
            if self.hands[self.players[turn]]:
                return turn
        return None

    def _current(self) -> int:
        self._skip_empty_turn()
        return self.players[self.turn]

    def _next_with_cards(self, turn=None) -> int | None:
        n = len(self.players)
        turn = self.turn if turn is None else turn
        for step in range(1, n):
            u = self.players[(turn + step) % n]
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
        turn = self._turn_with_cards()
        current = self.players[turn] if turn is not None else None
        old_idx = self.players.index(uid)
        hand = self.hands[uid]
        self.players.remove(uid)
        self.hands.pop(uid, None)
        self.safe.discard(uid)
        self.seq += 1
        self.last_draw = self._drawn_card = None
        if not self.players:
            self.turn = 0
            return []
        if hand:
            target = self.players[old_idx] if old_idx < len(self.players) else self.players[-1]
            if target != uid:
                self.hands[target].extend(hand)
                before = len(self.hands[target])
                self.hands[target] = _drop_pairs(self.hands[target])
                self.discarded_pairs += (before - len(self.hands[target])) // 2
                if self.hands[target]:
                    self.safe.discard(target)
                else:
                    self.safe.add(target)
        # 重排轮次：当前玩家若已走/空手则落到下一个有牌者
        self.turn = self.players.index(current) if current in self.players else old_idx % len(self.players)
        self._skip_empty_turn()
        loser = self._find_loser()
        if loser is not None:
            self._finish(loser)
        return []

    def _nick(self, uid: int) -> str:
        return f"玩家{uid}"
