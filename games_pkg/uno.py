# -*- coding: utf-8 -*-
"""UNO 简化版：108 张牌，同色/同数/万能可出；功能牌生效；出完者胜，按手牌计分。"""
import time

from games_pkg.base import BaseGame, GameRuleError
from config import UNO_ENFORCE_WILD4

COLORS = ["red", "yellow", "green", "blue"]
COLOR_CN = {"red": "红", "yellow": "黄", "green": "绿", "blue": "蓝"}
NUMBERS = list(range(10))               # 0 一张，1-9 两张
ACTIONS = ["skip", "reverse", "draw2"]  # 各色各两张
WILD = ["wild", "wild4"]                # 各 4 张


def _build_deck(rng) -> list:
    deck = []
    cid = 0
    for color in COLORS:
        for n in NUMBERS:
            deck.append({"id": cid, "color": color, "kind": "num", "value": n})
            cid += 1
            if n != 0:
                deck.append({"id": cid, "color": color, "kind": "num", "value": n})
                cid += 1
        for a in ACTIONS:
            for _ in range(2):
                deck.append({"id": cid, "color": color, "kind": "action", "value": a})
                cid += 1
    for _ in range(4):
        deck.append({"id": cid, "color": None, "kind": "wild", "value": "wild"})
        cid += 1
        deck.append({"id": cid, "color": None, "kind": "wild", "value": "wild4"})
        cid += 1
    rng.shuffle(deck)
    return deck


def _card_score(card) -> int:
    if card["kind"] == "num":
        return int(card["value"])
    if card["kind"] == "action":
        return 20
    return 50


def _card_str(card, color_override=None) -> str:
    color = color_override or card["color"]
    if card["kind"] == "num":
        return f"{COLOR_CN.get(color, '?')}{card['value']}"
    if card["kind"] == "action":
        names = {"skip": "跳过", "reverse": "反转", "draw2": "+2"}
        return f"{COLOR_CN.get(color, '?')}{names[card['value']]}"
    return "万能+4" if card["value"] == "wild4" else "万能"


class UnoGame(BaseGame):
    name = "uno"
    min_players = 2
    max_players = 10

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.scores = {u: 0 for u in players}
        self.round = 0
        self.phase = "round_end"         # playing | round_end
        self.hands = {}
        self.discard = []                # 弃牌堆（栈顶 = 当前牌）
        self.current_color = None
        self.direction = 1               # 1 正向 / -1 反向
        self.current_idx = 0
        self.winner_uid = None
        self.round_end_at = 0.0
        self.gap = 3.0
        self.match_winner = None
        self._start_round(announce=False)

    def snapshot(self) -> dict:
        top = self.discard[-1] if self.discard else None
        return {
            "game": self.name, "status": self.phase, "round": self.round,
            "players": list(self.players), "scores": dict(self.scores),
            "top": _card_str(top) if top else None,
            "top_color": self.current_color,
            "direction": "→" if self.direction == 1 else "←",
            "current_uid": None if self.phase != "playing" else self.players[self.current_idx],
            "hand_counts": {str(u): len(h) for u, h in self.hands.items()},
            "deck_remaining": len(self.discard),   # 弃牌堆剩余（示意）
            "winner_uid": self.winner_uid,
            "match_winner": self.match_winner,
        }

    def private(self, uid: int):
        if self.phase == "playing" and uid in self.hands:
            # R49：并行 hand_ids 供网页端点牌出牌（桌面端忽略未知键，兼容不变）
            return {"hand": [_card_str(c) for c in self.hands[uid]],
                    "hand_ids": [c["id"] for c in self.hands[uid]]}
        return None

    def act(self, uid: int, action: dict) -> list:
        if action.get("draw"):
            return self._draw(uid)
        if "card" in action:
            return self._play(uid, action["card"], action.get("color"))
        raise GameRuleError("未知动作")

    # ---- 开局 ----
    def _start_round(self, announce=True) -> list:
        self.round += 1
        self.discard = []
        deck = _build_deck(self.rng)
        self.hands = {u: [] for u in self.players}
        for u in self.players:
            for _ in range(7):
                self.hands[u].append(deck.pop())
        # 弃牌堆首张必须是数字牌
        while deck and deck[-1]["kind"] != "num":
            self.discard.append(deck.pop())
        first = deck.pop()
        self.discard.append(first)
        self.deck = deck
        self.current_color = first["color"]
        self.direction = 1
        self.current_idx = 0
        self.phase = "playing"
        self.winner_uid = None
        self._apply_first_card_effect()
        msgs = [f"第 {self.round} 轮开始，每人 7 张牌，先出完者胜"]
        msgs.append(f"首牌：{_card_str(first)}（当前颜色 {COLOR_CN.get(self.current_color, '任意')}）")
        return msgs

    def _apply_first_card_effect(self):
        """首牌若是功能牌也生效（简化：仅方向/跳过/抽牌）"""
        top = self.discard[-1]
        if top["kind"] == "action":
            if top["value"] == "reverse":
                self.direction = -1 if len(self.players) > 2 else self.direction
            elif top["value"] == "skip":
                self.current_idx = (self.current_idx + self.direction) % len(self.players)
            elif top["value"] == "draw2":
                nxt = (self.current_idx + self.direction) % len(self.players)
                self._give_cards(nxt, 2)
                self.current_idx = (self.current_idx + self.direction) % len(self.players)

    # ---- 出牌/摸牌 ----
    def _playable(self, card) -> bool:
        if card["kind"] == "wild":
            return True
        if card["kind"] == "action":
            return card["color"] == self.current_color or card["value"] == self.discard[-1].get("value")
        return card["color"] == self.current_color or card["value"] == self.discard[-1].get("value")

    def _play(self, uid: int, card_id, color) -> list:
        if self.phase != "playing" or uid != self.players[self.current_idx]:
            raise GameRuleError("还没轮到你")
        card = self._find_card(uid, card_id)
        if not self._playable(card):
            raise GameRuleError("这张牌不能出（需同色或同数字）")
        if card["kind"] == "wild":
            if card["value"] == "wild4" and UNO_ENFORCE_WILD4:
                has_current = any(
                    c["kind"] != "wild" and c["color"] == self.current_color
                    for c in self.hands[uid])
                if has_current:
                    raise GameRuleError("你还有当前颜色的牌，不能出万能+4")
            if color not in COLORS:
                raise GameRuleError("万能牌必须选颜色")
            card["color"] = color
        self.hands[uid].remove(card)
        self.discard.append(card)
        self.current_color = card["color"] if card["kind"] != "num" else card["color"]
        msgs = [f"{self._nick(uid)} 出了 {_card_str(card)}"]
        if not self.hands[uid]:
            self._finish_round(uid, msgs)
            return msgs
        if card["kind"] == "action" or (card["kind"] == "wild" and card["value"] == "wild4"):
            self._apply_action(card, msgs)          # wild4 也是动作：抽4+跳过
        elif card["kind"] == "wild":
            msgs.append(f"当前颜色变为 {COLOR_CN.get(self.current_color)}")
        self._advance_turn()
        return msgs

    def _apply_action(self, card, msgs: list):
        nxt = (self.current_idx + self.direction) % len(self.players)
        if card["value"] == "skip":
            self.current_idx = nxt
            msgs.append(f"跳过 {self._nick(self.players[nxt])}")
        elif card["value"] == "reverse":
            if len(self.players) == 2:
                self.current_idx = nxt
                msgs.append("2 人局反转视作跳过")
            else:
                self.direction *= -1
                msgs.append("方向反转")
        elif card["value"] == "draw2":
            self._give_cards(nxt, 2)
            msgs.append(f"{self._nick(self.players[nxt])} 抽 2 张并跳过")
            self.current_idx = (self.current_idx + self.direction) % len(self.players)
        if card["kind"] == "wild" and card["value"] == "wild4":
            self._give_cards(nxt, 4)
            msgs.append(f"{self._nick(self.players[nxt])} 抽 4 张并跳过")
            self.current_idx = (self.current_idx + self.direction) % len(self.players)

    def _draw(self, uid: int) -> list:
        if self.phase != "playing" or uid != self.players[self.current_idx]:
            raise GameRuleError("还没轮到你")
        if not self.deck:
            self._reshuffle()
        self._give_cards(uid, 1)
        drawn = self.hands[uid][-1]
        msgs = [f"{self._nick(uid)} 摸牌：{_card_str(drawn)}"]
        if self._playable(drawn) and drawn["kind"] != "wild":
            msgs.append(f"{self._nick(uid)} 摸到的牌可出，可再点「出牌」或「过」")
            return msgs
        msgs.append(f"{self._nick(uid)} 过")
        self._advance_turn()
        return msgs

    def _advance_turn(self):
        self.current_idx = (self.current_idx + self.direction) % len(self.players)

    def player_left(self, uid: int) -> list:
        """对局中掉线：剔除并调整轮次，避免永久卡住等待"""
        if uid not in self.players:
            return []
        idx = self.players.index(uid)
        was_current = (idx == self.current_idx)
        del self.players[idx]
        self.hands.pop(uid, None)
        self.scores.pop(uid, None)
        msgs = [f"{self._nick(uid)} 离开了游戏"]
        n = len(self.players)
        if n == 0:
            self.phase = "round_end"
            self.match_winner = None
            return msgs
        if was_current:
            # 当前行动者离开：交给下一位（按方向）
            if self.direction == -1:
                self.current_idx = (idx - 1) % n
        elif idx < self.current_idx:
            self.current_idx -= 1
        self.current_idx %= n
        if n < 2:
            self.phase = "round_end"
            self.match_winner = None
            msgs.append("剩余玩家不足 2 人，对局结束")
        return msgs

    # ---- 工具 ----
    def _find_card(self, uid: int, card_id):
        try:
            cid = int(card_id)
        except (TypeError, ValueError):
            raise GameRuleError("牌 id 非法")
        for c in self.hands.get(uid, []):
            if c["id"] == cid:
                return c
        raise GameRuleError("牌不在你手中")

    def _give_cards(self, uid: int, n: int):
        for _ in range(n):
            if not self.deck:
                self._reshuffle()
            if self.deck:
                self.hands[uid].append(self.deck.pop())

    def _reshuffle(self):
        if len(self.discard) > 1:
            top = self.discard.pop()
            self.deck = self.discard
            self.discard = [top]
            self.rng.shuffle(self.deck)

    def _finish_round(self, uid: int, msgs: list):
        self.winner_uid = uid
        self.phase = "round_end"
        self.round_end_at = time.time() + self.gap
        pts = sum(_card_score(c) for u, h in self.hands.items() for c in h if u != uid)
        self.scores[uid] += pts
        msgs.append(f"🏆 {self._nick(uid)} 出完手牌，本局获胜，得分 +{pts}！")
        if self.scores[uid] >= 100:
            self.match_winner = uid
            msgs.append(f"🎉 {self._nick(uid)} 先到 100 分，赢得整场比赛！")

    def tick(self, now: float) -> list:
        if self.phase == "round_end" and self.match_winner:
            return []                     # 比赛结束，等待离开
        if self.phase == "round_end" and now >= self.round_end_at:
            return self._start_round()
        return []

    def ended(self):
        if self.match_winner is not None:
            return {"winner_uid": self.match_winner, "detail": "先到 100 分"}
        return None

    def _nick(self, uid: int) -> str:
        return f"玩家{uid}"
