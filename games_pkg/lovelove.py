# -*- coding: utf-8 -*-
"""情书（致敬 Love Letter）：牌值 1~8 各限张。每名玩家持 1 张暗记牌。回合内从牌堆摸 1 张，
再弃掉手里 2 张之一并触发其效果（侍女 4 本回合免疫、王子 5 令一人弃而重抽、国王 6 换手、
伯爵夫人 7 手有 7+8 必须弃、公主 8 出局、护卫 1 猜中即淘汰）。只剩 1 人胜；牌堆空则比手中牌大者胜。"""
from games_pkg.base import BaseGame, GameRuleError

VAL_LIMIT = {1: 5, 2: 2, 3: 2, 4: 2, 5: 2, 6: 1, 7: 1, 8: 1}
MISS = 4          # 侍女：本回合免疫
PRINCE = 5
KING = 6
COUNT = 7
PRINCE_SS = 8


def _names(v):
    return {1: "护卫", 2: "牧师", 3: "男爵", 4: "侍女", 5: "王子",
            6: "国王", 7: "伯爵夫人", 8: "公主"}[v]


class LoveLoveGame(BaseGame):
    name = "lovelove"
    min_players = 2
    max_players = 6

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.hand = {u: None for u in players}      # 只存一个盘内的“贴身牌”
        self.alive = list(players)
        self.miss = set()                            # 本回合受侍女保护的玩家
        self.turn_idx = 0
        self.discard = []
        self.dead = []
        self.winner = None
        self.game_over = False
        self._deal()

    def _build_deck(self):
        deck = []
        for v, n in VAL_LIMIT.items():
            deck += [v] * n
        self.rng.shuffle(deck)
        return deck

    def _deal(self):
        # 公子局：发 1 张，弃 1 张做牌堆顶暗牌
        deck = self._build_deck()
        if len(self.alive) > len(deck):
            self.alive = deck[:]
            deck = deck[len(self.alive):]
        n = len(self.alive)
        for i, u in enumerate(self.alive):
            self.hand[u] = deck.pop()
        # 模拟开局弃一张到牌堆底（保证可抽）
        self.deck = deck
        if not self.deck:
            self.deck = [x for x in range(1, 9) for _ in VAL_LIMIT[x]]
            self.rng.shuffle(self.deck)

    @property
    def cur(self):
        return self.alive[self.turn_idx % len(self.alive)]

    def act(self, uid, action):
        if self.winner or self.game_over:
            raise GameRuleError("本局已结束")
        if uid != self.cur:
            raise GameRuleError("还没轮到你")
        if uid not in self.alive:
            raise GameRuleError("你已出局")
        play = action.get("play")
        try:
            play = int(play)
        except (TypeError, ValueError):
            raise GameRuleError("出牌无效")
        hand = self.hand[uid]
        if play is None or play != hand:
            raise GameRuleError("你只能弃当前那张牌")
        return self._resolve(uid, play, action)

    def _resolve(self, uid, play, action):
        msgs = []
        # 强制：持 7+8 必须弃 7
        drawn = self.deck.pop() if self.deck else None
        if drawn is not None:
            self.hand[uid] = drawn
        else:
            self.hand[uid] = None
            self.game_over = True
            msgs.append("🏃 牌堆已空，按手中牌值比高低")
        # 弃掉 play
        self._table_card = play
        self.discard.append((uid, play))
        msgs.append(f"🂠 {self._nick(uid)} 弃掉 {_names(play)}（{play}）")
        # 若持双 蓝（7 & 8）则强制弃 7 已在选择处约束
        if play == PRINCE_SS:
            self._eliminate(uid, "贵女公主被丢弃，即刻出局")
            msgs.append("👑 公主离席，持王出局")
            self._after(uid, msgs, 0)
            return msgs
        # 触发效果
        msgs += self._effect(uid, play, action)
        self._after(uid, msgs, pulled=1)
        return msgs

    def _effect(self, uid, play, action):
        msgs = []
        if play == 1:                       # 护卫：猜一张牌值
            target = action.get("target")
            val = action.get("val")
            try:
                val = int(val)
            except (TypeError, ValueError):
                return msgs
            if target not in self.alive or target == uid:
                return msgs
            if target in self.miss:
                msgs.append(f"🛡️ {self._nick(target)} 有侍女护体，免疫本次猜牌")
                return msgs
            if self.hand[target] == val:
                self._eliminate(target, f"被护卫猜中牌面 {val}")
                msgs.append(f"🎯 {self._nick(uid)} 猜中！{self._nick(target)} 出局")
            else:
                msgs.append(f"🙈 {self._nick(uid)} 猜 {self._nick(target)}={val}，未中")
        elif play == 2:                     # 牧师：看牌
            target = action.get("target")
            if target in self.alive and target != uid:
                msgs.append(f"🔭 {self._nick(uid)} 偷看 {self._nick(target)}：{_names(self.hand[target])}" +
                            (f"（{self.hand[target]}）"))
        elif play == 3:                     # 男爵：比点
            target = action.get("target")
            if target in self.alive and target != uid:
                if self.hand[uid] > self.hand[target]:
                    self._eliminate(target, "男爵比点落败")
                    msgs.append(f"⚔️ {self._nick(uid)} 比 {self._nick(target)} 大，{self._nick(target)} 出局")
                elif self.hand[uid] < self.hand[target]:
                    self._eliminate(uid, "男爵比点落败")
                    msgs.append(f"⚔️ {self._nick(target)} 比 {self._nick(uid)} 大，{self._nick(uid)} 出局")
                else:
                    msgs.append(f"🤝 比点平手，无事发生")
        elif play == 5:                     # 王子：令一人弃而重抽
            target = action.get("target")
            if target in self.alive and target != uid:
                old = self.hand[target]
                if old == PRINCE_SS:
                    self._eliminate(target, "被王子强制丢弃了公主")
                    msgs.append(f"👑 {self._nick(target)} 王子令其弃公主，出局")
                else:
                    if self.deck:
                        self.hand[target] = self.deck.pop()
                    else:
                        self.hand[target] = None
                    msgs.append(f"🌪️ {self._nick(uid)} 令 {self._nick(target)} 弃 {_names(old)} 重抽")
        elif play == 6:                     # 国王：换手
            target = action.get("target")
            if target in self.alive and target != uid:
                self.hand[uid], self.hand[target] = self.hand[target], self.hand[uid]
                msgs.append(f"🤲 {self._nick(uid)} 与 {self._nick(target)} 交换手牌")
        elif play == 7:                     # 伯爵夫人（仅当拿+8强制弃）——本身无效果
            msgs.append(f"👵 伯爵夫人弃牌，无效果")
        return msgs

    def _eliminate(self, uid, why):
        if uid in self.alive:
            self.alive.remove(uid)
            self.dead.append(uid)

    def _after(self, uid, msgs, pulled):
        alive_now = [u for u in self.alive if self.hand[u] is not None or u == uid]
        if len(self.alive) == 1:
            self.winner = self.alive[0]
            self.game_over = True
            msgs.append(f"🏆 {self._nick(self.winner)} 成为最后的倾慕者！")
            return
        if self.game_over:
            # 牌堆空比手中牌高
            best = max((self.hand[u] or 0) for u in self.alive)
            leaders = [u for u in self.alive if (self.hand[u] or 0) == best]
            if len(leaders) == 1:
                self.winner = leaders[0]
                msgs.append(f"🏆 手中 {best} 点最大，{self._nick(leaders[0])} 胜！")
            else:
                self.game_over = True
                msgs.append("🏆 手牌同点，共同获胜")
            return
        # 前进到下一存活者（可能因出局跳过）
        k = 0
        while k < len(self.alive):
            self.turn_idx += 1
            if self.cur in self.alive:
                break
            k += 1
        self.miss = set()
        msgs.append(f"➡️ 轮到 {self._nick(self.cur)}")

    def snapshot(self):
        return {
            "game": self.name, "status": ("ended" if (self.winner or self.game_over) else "playing"),
            "cur": self.cur, "alive": self.alive, "dead": self.dead,
            "discard": self.discard, "deck_left": len(self.deck), "winner_uid": self.winner,
            "table": self._table_card if hasattr(self, "_table_card") else None,
        }

    def private(self, uid):
        if uid not in self.hand:
            return None
        return {"hand": self.hand[uid]}

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner, "detail": f"{self._nick(self.winner)} 情书胜者"}
        if self.game_over:
            return {"winner_uid": None, "detail": "牌堆空，手牌同点"}
        return None

    def player_left(self, uid):
        if uid in self.alive:
            self.alive.remove(uid)
        if uid == self.cur:
            self.turn_idx = max(0, self.turn_idx - 1)
        if len(self.alive) <= 1 and not self.winner:
            if self.alive:
                self.winner = self.alive[0]
            self.game_over = True
            return [f"💨 {self._nick(uid)} 离开，{self._nick(self.winner)} 胜"]
        return [f"💨 {self._nick(uid)} 离开了对局"]

    def _nick(self, uid):
        return f"玩家{uid}"