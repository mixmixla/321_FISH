# -*- coding: utf-8 -*-
"""石头剪刀布：多人同时提交，全部齐后随机配对揭晓；奇数轮空。"""
import time

from games_pkg.base import BaseGame, GameRuleError

CHOICES = ["✊", "✋", "✌️"]


def _rps_winner(a: int, b: int) -> int:
    """返回胜者下标（0=a胜, 1=b胜, -1=平）"""
    if a == b:
        return -1
    return 0 if (a - b) % 3 == 1 else 1


class RpsGame(BaseGame):
    name = "rps"
    min_players = 3
    max_players = None

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.scores = {u: 0 for u in players}
        self.phase = "collecting"       # collecting | revealed
        self.submitted = {}             # uid -> choice
        self.matches = []               # [{a,b,ca,cb,winner}]
        self.round = 0
        self.round_end_at = 0.0
        self.timeout = 15.0             # 秒（可注入）
        self.byes = []                  # 轮空者

    def snapshot(self) -> dict:
        return {
            "game": self.name, "status": self.phase, "round": self.round,
            "submitted": sorted(self.submitted.keys()),
            "players": list(self.players), "scores": dict(self.scores),
            # R49：始终携带最近一轮对战结果——_resolve 同步回到 collecting，
            # 旧写法只在 revealed 瞬间可见，客户端永远收不到结果
            "matches": self.matches, "byes": list(self.byes),
        }

    def act(self, uid: int, action: dict) -> list:
        if self.phase != "collecting":
            raise GameRuleError("本轮已揭晓，等待下一轮")
        if uid not in self.players:
            raise GameRuleError("你不在本局")
        if uid in self.submitted:
            raise GameRuleError("你已出拳")
        c = action.get("choice")
        if isinstance(c, str):                       # R49：兼容桌面端字符串出拳
            c = {"rock": 0, "paper": 1, "scissors": 2}.get(c.strip().lower())
        try:
            c = int(c)
        except (TypeError, ValueError):
            raise GameRuleError("出拳须为 0/1/2")
        if c not in (0, 1, 2):
            raise GameRuleError("出拳须为 0(✊)/1(✋)/2(✌️)")
        self.submitted[uid] = c
        if len(self.submitted) == len(self.players):
            self._resolve()
        return []

    def tick(self, now: float) -> list:
        if self.phase == "collecting" and self.submitted and now >= self.round_end_at:
            # 超时：未提交者判负（直接结揭晓）
            for u in self.players:
                if u not in self.submitted:
                    self.submitted[u] = -1
            return self._resolve(announce=True)
        return []

    def _resolve(self, announce: bool = False) -> list:
        self.phase = "revealed"
        self.round += 1
        msgs = []
        order = list(self.players)
        n = len(order)
        # 轮空者按轮次轮转（确定性且公平），配对顺序固定
        start = (self.round - 1) % n
        order = [order[(start + i) % n] for i in range(n)]
        self.matches, self.byes = [], []
        i = 0
        while i + 1 < len(order):
            a, b = order[i], order[i + 1]
            ca, cb = self.submitted.get(a, -1), self.submitted.get(b, -1)
            w = -1
            if ca != -1 and cb != -1:
                r = _rps_winner(ca, cb)
                w = a if r == 0 else (b if r == 1 else -1)
                if w != -1:
                    self.scores[w] += 1
            elif ca == -1 and cb != -1:
                w = b
                self.scores[b] += 1
            elif cb == -1 and ca != -1:
                w = a
                self.scores[a] += 1
            self.matches.append({"a": a, "b": b, "ca": ca, "cb": cb, "winner": w})
            if announce:
                ma = "未出拳" if ca == -1 else CHOICES[ca]
                mb = "未出拳" if cb == -1 else CHOICES[cb]
                msgs.append(f"{self._nick(a)} {ma} vs {self._nick(b)} {mb}"
                            + (f" → {self._nick(w)} 胜" if w != -1 else " → 平局"))
            i += 2
        if len(order) % 2:
            self.byes = [order[-1]]
            if announce:
                msgs.append(f"{self._nick(order[-1])} 轮空")
        self.submitted = {}
        self.phase = "collecting"
        self.round_end_at = time.time() + self.timeout
        return msgs

    def ended(self):
        return None

    def _nick(self, uid: int) -> str:
        return f"玩家{uid}"
