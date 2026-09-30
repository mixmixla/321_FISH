# -*- coding: utf-8 -*-
"""璀璨宝石（致敬 Splendor）：宝石金库分 5 色+万能金，市场摆 3 级发展卡。
回合＝取3颗异色/取2颗同色/保留卡(得金)/购买发展卡(扣款得永久折扣+分)。
手牌达贵宾需求即邀贵宾加分。先到 15 分(且当轮结束)者胜。"""
from games_pkg.base import BaseGame, GameRuleError

COLORS = ["o", "d", "r", "e", "s"]
COLOR_CN = {"o": "黑玛瑙", "d": "钻石", "r": "红宝石", "e": "祖母绿", "s": "蓝宝石"}
CN_TOK = {"o": "⬛", "d": "⬜", "r": "🔴", "e": "🟢", "s": "🔵", "g": "🟡"}
WIN_PTS = 15
NOBLES = [  # {cost: {color: n}, pts: 3}
    {"o": 4, "d": 4},
    {"r": 4, "e": 4},
    {"e": 4, "s": 4},
    {"o": 3, "s": 3, "d": 3},
    {"r": 3, "e": 3, "s": 3},
]
TIERS = 3
MARKET_PER_TIER = 4


class GemCityGame(BaseGame):
    name = "gemcity"
    min_players = 2
    max_players = 4

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        n = len(players)
        bank = {c: (4 if n == 2 else (5 if n == 3 else 7)) for c in COLORS}
        bank["g"] = 5
        self.bank = bank
        self.tokens = {u: {c: 0 for c in COLORS + ["g"]} for u in players}
        self.discount = {u: {c: 0 for c in COLORS} for u in players}   # 永久折扣
        self.cards = {u: [] for u in players}     # 买到的卡
        self.reserved = {u: [] for u in players}  # 保留卡
        self.score = {u: 0 for u in players}
        self.market = {t: [] for t in range(1, TIERS + 1)}
        self.deck = {t: [] for t in range(1, TIERS + 1)}
        for t in range(1, TIERS + 1):
            for _ in range(20):
                self.deck[t].append(self._make_card(t))
            self.rng.shuffle(self.deck[t])
            for _ in range(MARKET_PER_TIER):
                self.market[t].append(self.deck[t].pop())
        self.nobles_left = [dict(x) for x in NOBLES]
        self.nobles_cards = {u: [] for u in players}
        self.turn = 0
        self.trigger_uid = None
        self.extra = set()
        self.winner = None

    def _make_card(self, tier):
        disc = self.rng.choice(COLORS)
        cost = {c: 0 for c in COLORS}
        budget = tier + 1
        while budget > 0:
            c = self.rng.choice([x for x in COLORS if x != disc])
            if c in cost:
                cost[c] += 1
                budget -= 1
        return {"tier": tier, "disc": disc, "pts": tier, "cost": cost}

    # ---------- 动作 ----------
    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        op = action.get("op")
        if op == "take":
            return self._act_take(uid, action)
        if op == "take2":
            return self._act_take2(uid, action)
        if op == "reserve":
            return self._act_reserve(uid, action)
        if op == "buy":
            return self._act_buy(uid, action)
        if op == "buy_res":
            return self._act_buy_res(uid, action)
        raise GameRuleError("未知动作")

    def _act_take(self, uid, action):
        cs = action.get("colors")
        if not isinstance(cs, list) or len(set(cs)) != 3 or len(cs) != 3:
            raise GameRuleError("请选择 3 颗不同颜色的宝石")
        for c in cs:
            if c not in COLORS:
                raise GameRuleError("宝石颜色无效")
            if self.bank[c] < 1:
                raise GameRuleError(f"{COLOR_CN[c]} 不足")
        for c in cs:
            self.bank[c] -= 1
            self.tokens[uid][c] += 1
        self._advance()
        return [f"💎 {self._nick(uid)} 取 {'、'.join(COLOR_CN[c] for c in cs)}"]

    def _act_take2(self, uid, action):
        c = action.get("color")
        if c not in COLORS:
            raise GameRuleError("颜色无效")
        if self.bank[c] < 4:
            raise GameRuleError(f"{COLOR_CN[c]} 不足 4 颗")
        self.bank[c] -= 2
        self.tokens[uid][c] += 2
        self._advance()
        return [f"💎 {self._nick(uid)} 取 2 颗{COLOR_CN[c]}"]

    def _act_reserve(self, uid, action):
        try:
            t, i = int(action["tier"]), int(action["idx"])
        except (TypeError, ValueError):
            raise GameRuleError("参数无效")
        if len(self.reserved[uid]) >= 3:
            raise GameRuleError("最多保留 3 张卡")
        if t not in self.market or not (0 <= i < len(self.market[t])):
            raise GameRuleError("市场卡无效")
        card = self.market[t].pop(i)
        self.reserved[uid].append(card)
        if card["tier"] is None:
            pass
        if self.bank["g"] > 0:
            self.bank["g"] -= 1
            self.tokens[uid]["g"] += 1
        self._refill(t)
        self._advance()
        return [f"📥 {self._nick(uid)} 保留 1 张{t}级卡（+1 金)"]

    def _act_buy(self, uid, action):
        try:
            t, i = int(action["tier"]), int(action["idx"])
        except (TypeError, ValueError):
            raise GameRuleError("参数无效")
        if t not in self.market or not (0 <= i < len(self.market[t])):
            raise GameRuleError("市场卡无效")
        card = self.market[t][i]
        self._buy_card(uid, card)
        self.market[t].pop(i)
        self._refill(t)
        return self._after_buy(uid)

    def _act_buy_res(self, uid, action):
        try:
            i = int(action["idx"])
        except (TypeError, ValueError):
            raise GameRuleError("参数无效")
        if not (0 <= i < len(self.reserved[uid])):
            raise GameRuleError("保留卡无效")
        card = self.reserved[uid].pop(i)
        self._buy_card(uid, card)
        return self._after_buy(uid)

    def _buy_card(self, uid, card):
        need = {c: max(0, card["cost"][c] - self.discount[uid][c]) for c in COLORS}
        # 检查并支付：用 token + 金兜底
        for c in COLORS:
            have = self.tokens[uid][c] + self.tokens[uid]["g"]
            if have < need[c]:
                raise GameRuleError(f"{COLOR_CN[c]} 不足")
        # 支付（金优先用于最贵项，简单逐个扣）
        for c in COLORS:
            n = need[c]
            use_tok = min(n, self.tokens[uid][c])
            self.tokens[uid][c] -= use_tok
            n -= use_tok
            self.tokens[uid]["g"] -= n
            self.bank[c] += use_tok
            self.bank["g"] += n
        self.discount[uid][card["disc"]] += 1
        self.cards[uid].append(card)
        self.score[uid] += card["pts"]

    def _after_buy(self, uid):
        # 贵宾邀请
        nobles_msg = ""
        for nob in self.nobles_left:
            if all(self.discount[uid][c] >= v for c, v in nob.items()):
                self.nobles_left.remove(nob)
                self.nobles_cards[uid].append(3)
                self.score[uid] += 3
                nobles_msg = "；获贵宾 +3 分"
        self._check_win(uid)
        self._advance()
        return [f"🛒 {self._nick(uid)} 购得发展卡{nobles_msg}，总分 {self.score[uid]}"]

    def _check_win(self, uid):
        if self.score[uid] >= WIN_PTS and self.trigger_uid is None:
            self.trigger_uid = uid           # 达标：其余人各补一回合
            self.extra = set(self.players) - {uid}

    def _advance(self):
        n = len(self.players)
        if not self.trigger_uid:
            self.turn = (self.turn + 1) % n
            return
        # 触发终局：依次走完 extra 集合中的玩家
        for step in range(1, n + 1):
            nxt = self.players[(self.players.index(self.trigger_uid) + step) % n]
            if nxt in self.extra:
                self.turn = self.players.index(nxt)
                self.extra.discard(nxt)
                return
        self._finish()

    def _refill(self, tier):
        if self.deck[tier] and len(self.market[tier]) < MARKET_PER_TIER:
            self.market[tier].append(self.deck[tier].pop())

    def _finish(self):
        hi = max(self.score.values())
        leaders = [u for u in self.players if self.score[u] == hi]
        self.winner = leaders[0]

    # ---------- 快照 ----------
    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "bank": self.bank, "colors": COLOR_CN,
            "market": {str(t): self.market[t] for t in self.market},
            "tokens": {str(u): v for u, v in self.tokens.items()},
            "discount": {str(u): v for u, v in self.discount.items()},
            "score": {str(u): v for u, v in self.score.items()},
            "nobles": self.nobles_left,
            "turn_uid": None if self.winner else self.players[self.turn],
            "players": list(self.players), "winner_uid": self.winner,
            "trigger_uid": self.trigger_uid,
        }

    def private(self, uid):
        return {"cards": len(self.cards.get(uid, [])),
                "reserved": self.reserved.get(uid, []),
                "nobles": self.nobles_cards.get(uid, [])}

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 总分最高胜出"}
        return None

    def player_left(self, uid):
        return []

    def _nick(self, uid):
        return f"玩家{uid}"