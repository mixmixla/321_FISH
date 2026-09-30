# -*- coding: utf-8 -*-
"""德国心脏病·慢棋改编（致敬 Halloween）：沿用原版“翻牌凑同类 5 张即抢铃”的核心，
但把“手速抢铃”改为回合制策略：每回合先必翻一张到桌，翻后你可选择“拍铃”。若桌上恰有某种水果
累计到 5 张 → 收走桌面全部牌计分且再走一次；若没到 5 却拍 → 计分扣 1 且回合结束。某玩家翻完牌即终局，
收牌得分最多者胜。"""
from games_pkg.base import BaseGame, GameRuleError

FRUITS = ["🍓", "🍋", "🍊", "🍌", "🍎"]
PER_OK = 8                    # 每水果张数
SLAP_N = 5                    # 触发张数


class HalloweenGame(BaseGame):
    name = "halloween"
    min_players = 2
    max_players = 6

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        deck = [i for i in range(len(FRUITS)) for _ in range(PER_OK)]
        self.rng.shuffle(deck)
        n = len(players)
        base = len(deck) // n
        piles = []
        for u in players:
            piles.append(deck[:base])
            deck = deck[base:]
        self.rng.shuffle(deck)
        for i, u in enumerate(players):
            piles[i] += deck[i::len(players)]
        self.stack = {u: list(p) for u, p in zip(players, piles)}
        self.counts = [0] * len(FRUITS)
        self.area = []                       # 公共已翻区
        self.score = {u: 0 for u in players}
        self.turn = players[0]
        self.have_flipped = False
        self.winner = None
        self.finished = False
        self.last = None

    def _is_slapable(self):
        return SLAP_N in self.counts

    def _check_end(self):
        for u in self.players:
            if self.turn == u and not self.stack[u]:
                self.finished = True
                hi = max(self.score[u] for u in self.players)
                leaders = [u for u in self.players if self.score[u] == hi]
                if len(leaders) == 1:
                    self.winner = leaders[0]
                return
        return

    def act(self, uid, action):
        if self.winner or self.finished:
            raise GameRuleError("本局已结束")
        if uid != self.turn:
            raise GameRuleError("还没轮到你")
        op = action.get("op")
        if op == "flip":
            return self._flip(uid)
        if op == "slap":
            return self._slap(uid)
        if op == "pass":
            if not self.have_flipped:
                raise GameRuleError("请先翻牌")
            return self._end_turn("不做声，默默等待")
        raise GameRuleError("未知操作")

    def _next_turn(self):
        self.have_flipped = False
        self.turn = self.players[(self.players.index(self.turn) + 1) % len(self.players)]
        # 若某人没牌只能被跳
        guard = 0
        while not self.stack[self.turn] and guard < len(self.players):
            self.turn = self.players[(self.players.index(self.turn) + 1) % len(self.players)]
            guard += 1
        if not self.stack[self.turn]:
            self.finished = True
            self._settle()

    def _flip(self, uid):
        if self.have_flipped:
            raise GameRuleError("本回合已翻过牌")
        if not self.stack[uid]:
            raise GameRuleError("你已经没有牌可翻，对局接近尾声")
        f = self.stack[uid].pop()
        self.counts[f] += 1
        self.area.append(f)
        self.have_flipped = True
        self.last = ("flip", uid, f)
        msgs = [f"🫲 {self._nick(uid)} 翻开 {FRUITS[f]}（桌上 {FRUITS[f]}×{self.counts[f]}）"]
        if self._is_slapable():
            msgs.append("🔔 桌上有凑齐 5 个的水果！可拍铃收牌！")
        return msgs

    def _slap(self, uid):
        if not self.have_flipped:
            raise GameRuleError("请先翻牌再拍铃")
        if self._is_slapable():
            got = len(self.area)
            self.score[uid] += got
            self.area = []
            self.counts = [0] * len(FRUITS)
            self.have_flipped = False          # 再走一次
            self.last = ("slap_ok", uid, got)
            msgs = [f"🔔 {self._nick(uid)} 拍铃抢到 {got} 张！再翻一次"]
            return msgs
        # 拍空
        self.score[uid] = max(0, self.score[uid] - 1)
        self._end_turn("拍空！被罚 1 分，回合结束")
        self.last = ("slap_bad", uid, None)
        return [f"🙅 {self._nick(uid)} 拍铃扑空（没有 5 张）！扣 1 分"] + [f"➡️ 轮到 {self._nick(self.turn)}"]

    def _end_turn(self, why):
        msgs = [f"⏭️ {self._nick(self.turn)} {why}"]
        self._next_turn()
        if self.winner:
            msgs.append(f"🏆 {self._nick(self.winner)} 收牌最多获胜！")
        elif self.finished:
            msgs.insert(0, "🏁 有人翻完手牌，按收牌数结算")
        else:
            msgs.append(f"➡️ 轮到 {self._nick(self.turn)}")
        return msgs

    def _settle(self):
        self.finished = True
        hi = max(self.score[u] for u in self.players)
        leaders = [u for u in self.players if self.score[u] == hi]
        if len(leaders) == 1:
            self.winner = leaders[0]

    def snapshot(self):
        return {
            "game": self.name, "status": ("ended" if (self.winner or self.finished) else "playing"),
            "turn": self.turn, "area": [FRUITS[i] for i in self.area],
            "counts": {FRUITS[i]: self.counts[i] for i in range(len(FRUITS))},
            "score": {str(u): v for u, v in self.score.items()},
            "left": {str(u): len(self.stack[u]) for u in self.players},
            "winner_uid": self.winner,
            "fruits": FRUITS, "can_slap": self._is_slapable(), "flipped": self.have_flipped,
        }

    def private(self, uid):
        return {"left": len(self.stack[uid])}

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 收牌 {self.score[self.winner]} 张"}
        if self.finished:
            return {"winner_uid": None, "detail": "手牌翻完，收牌数同分"}
        return None

    def player_left(self, uid):
        if uid == self.turn:
            self._next_turn()
        self.players = [u for u in self.players if u in self.stack]
        if len(self.players) <= 1 and not self.winner:
            if self.players:
                self.winner = self.players[0]
            self.finished = True
            return [f"💨 {self._nick(uid)} 离开，终局"]
        return [f"💨 {self._nick(uid)} 离开了对局"]

    def _nick(self, uid):
        return f"玩家{uid}"