# -*- coding: utf-8 -*-
"""璀璨宝石（致敬 Splendor）：宝石金库分 5 色+万能金，市场摆 3 级发展卡。
回合＝取 1~3 颗异色（超出 10 颗自动退回）/取2颗同色/保留卡(得金)/购买发展卡(扣款得永久折扣+分)。
手牌达贵宾需求即邀贵宾加分。先到 15 分(且当轮结束)者胜。"""
from games_pkg.base import BaseGame, GameRuleError

COLORS = ["o", "d", "r", "e", "s"]
COLOR_CN = {"o": "黑玛瑙", "d": "钻石", "r": "红宝石", "e": "祖母绿", "s": "蓝宝石"}
CN_TOK = {"o": "⬛", "d": "⬜", "r": "🔴", "e": "🟢", "s": "🔵", "g": "🟡"}
WIN_PTS = 15
MAX_GEMS = 10            # 持有宝石上限（金币不计入）
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
        self.extra = []          # 触发终局后仍需行动（按回合顺序）的玩家
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
        if self.winner is not None:
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
        if not isinstance(cs, list) or not (1 <= len(cs) <= 3):
            raise GameRuleError("请选择 1~3 颗不同颜色的宝石")
        cs = [str(c) for c in cs]
        if len(set(cs)) != len(cs):
            raise GameRuleError("颜色不能重复")
        for c in cs:
            if c not in COLORS:
                raise GameRuleError("宝石颜色无效")
        for c in cs:
            if self.bank[c] < 1:
                raise GameRuleError(f"{COLOR_CN[c]} 不足")
        for c in cs:
            self.bank[c] -= 1
            self.tokens[uid][c] += 1
        returned = self._trim_gems(uid, cs)
        self._advance()
        msg = f"💎 {self._nick(uid)} 取 {'、'.join(COLOR_CN[c] for c in cs)}"
        if returned:
            msg += f"（超过 {MAX_GEMS} 枚，退回 {'、'.join(COLOR_CN[c] for c in returned)}）"
        return [msg]

    def _act_take2(self, uid, action):
        c = action.get("color")
        if c not in COLORS:
            raise GameRuleError("颜色无效")
        if self.bank[c] < 4:
            raise GameRuleError(f"{COLOR_CN[c]} 不足 4 颗")
        self.bank[c] -= 2
        self.tokens[uid][c] += 2
        returned = self._trim_gems(uid, [c])
        self._advance()
        msg = f"💎 {self._nick(uid)} 取 2 颗{COLOR_CN[c]}"
        if returned:
            msg += f"（超过 {MAX_GEMS} 枚，退回 {'、'.join(COLOR_CN[c] for c in returned)}）"
        return [msg]

    def _trim_gems(self, uid, preferred):
        """宝石超过上限时按确定顺序退回金库（优先退回刚取的颜色）。"""
        returned = []
        order = list(reversed(preferred)) + [c for c in COLORS if c not in preferred]
        while self._gem_total(uid) > MAX_GEMS:
            for c in order:
                if self.tokens[uid][c] > 0:
                    self.tokens[uid][c] -= 1
                    self.bank[c] += 1
                    returned.append(c)
                    break
            else:                       # 理论上不可达：没有任何宝石可退
                break
        return returned

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
        card = self.reserved[uid][i]
        self._buy_card(uid, card)
        self.reserved[uid].pop(i)
        return self._after_buy(uid)

    def _buy_card(self, uid, card):
        need = {c: max(0, card["cost"][c] - self.discount[uid][c]) for c in COLORS}
        # 彩色宝石优先支付，金只能覆盖各色缺口的总和。
        # 整体校验通过前不改变资金或卡牌，拒绝动作保持状态不变。
        payment = {c: min(need[c], self.tokens[uid][c]) for c in COLORS}
        gold = sum(need[c] - payment[c] for c in COLORS)
        if gold > self.tokens[uid]["g"]:
            raise GameRuleError("宝石和金不足")
        for c in COLORS:
            self.tokens[uid][c] -= payment[c]
            self.bank[c] += payment[c]
        self.tokens[uid]["g"] -= gold
        self.bank["g"] += gold
        self.discount[uid][card["disc"]] += 1
        self.cards[uid].append(card)
        self.score[uid] += card["pts"]

    def _after_buy(self, uid):
        # 贵宾邀请（遍历副本：边遍历边删会漏掉后一张达标的贵宾）
        nobles_msg = ""
        for nob in list(self.nobles_left):
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
            self.trigger_uid = uid           # 达标：当轮结束（其后玩家各补一回合）
            idx = self.players.index(uid)
            n = len(self.players)
            self.extra = [self.players[(idx + k) % n] for k in range(1, n)]

    def _advance(self):
        n = len(self.players)
        if self.trigger_uid is None:
            self.turn = (self.turn + 1) % n
            return
        # 触发终局：按回合顺序走完 extra 中的玩家后结算
        if self.extra:
            self.turn = self.players.index(self.extra.pop(0))
            return
        self._finish()

    def _refill(self, tier):
        if self.deck[tier] and len(self.market[tier]) < MARKET_PER_TIER:
            self.market[tier].append(self.deck[tier].pop())

    def _finish(self):
        hi = max(self.score.values())
        leaders = [u for u in self.players if self.score[u] == hi]
        # 官方平分规则：同分时发展卡更少者胜；仍相同按座次先后
        self.winner = min(leaders, key=lambda u: (len(self.cards[u]),
                                                  self.players.index(u)))

    # ---------- 死锁兜底 ----------
    def _affordable(self, uid, card):
        """判断当前资产能否买下该卡（与 _buy_card 同一套抵扣规则）。"""
        need = {c: max(0, card["cost"][c] - self.discount[uid][c]) for c in COLORS}
        gold = sum(need[c] - min(need[c], self.tokens[uid][c]) for c in COLORS)
        return gold <= self.tokens[uid]["g"]

    def _can_act(self, uid):
        if any(self.bank[c] > 0 for c in COLORS):
            return True             # 至少可取 1 颗（超出上限会自动退回）
        if len(self.reserved[uid]) < 3 and any(self.market[t] for t in self.market):
            return True             # 保留卡不受宝石上限限制
        for t in self.market:
            for card in self.market[t]:
                if self._affordable(uid, card):
                    return True
        return any(self._affordable(uid, card) for card in self.reserved[uid])

    def tick(self, now):
        """当前玩家确实无任何合法动作时自动跳过，避免对局永久卡死。"""
        if self.winner is not None or not self.players:
            return []
        uid = self.players[self.turn]
        if self._can_act(uid):
            return []
        msg = f"⏭ {self._nick(uid)} 已无合法行动，自动跳过"
        self._advance()
        return [msg]

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
        if self.winner is not None:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 总分最高胜出"}
        return None

    def player_left(self, uid):
        """掉线善后：按座次清理离场者的宝石/折扣/卡与贵宾，并修正回合。

        宝石退回金库以保持供应守恒；终局补回合列表同步剔除离场者。
        """
        if uid not in self.players:
            return []
        msgs = [f"👋 {self._nick(uid)} 离开了对局"]
        idx = self.players.index(uid)
        was_turn = (self.winner is None and idx == self.turn)
        cur_uid = self.players[self.turn]
        for c in COLORS + ["g"]:
            self.bank[c] += self.tokens[uid][c]
        for book in (self.tokens, self.discount, self.cards,
                     self.reserved, self.score, self.nobles_cards):
            book.pop(uid, None)
        self.players.remove(uid)
        n = len(self.players)
        if n == 0:
            return msgs
        if n == 1:
            if self.winner is None:
                self.winner = self.players[0]
                self.turn = 0
                self.extra = []
                msgs.append(f"🏆 仅剩 {self._nick(self.winner)}，直接获胜")
            return msgs
        if self.winner is not None:
            self.turn %= n
            return msgs
        if self.trigger_uid is not None:
            # 终局补回合：保留尚未补过回合的玩家（当前行动者 + extra），每人一次
            pending = ([cur_uid] if cur_uid != uid else []) + \
                      [u for u in self.extra if u != uid]
            if not pending:
                self.extra = []
                self.turn = 0
                self._finish()
                return msgs
            self.extra = pending[1:]
            self.turn = self.players.index(pending[0])
            return msgs
        if was_turn or cur_uid == uid:
            self.turn = idx % n
        elif idx < self.turn:
            self.turn -= 1
        self.turn %= n
        return msgs

    def _gem_total(self, uid):
        return sum(self.tokens[uid][c] for c in COLORS)

    def _nick(self, uid):
        return f"玩家{uid}"
