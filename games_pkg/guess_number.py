# -*- coding: utf-8 -*-
"""猜数字：出题者轮转，全体抢猜，区间收窄，先猜中 +1 分。"""
import time

from games_pkg.base import BaseGame, GameRuleError

SECRET_RANGE = (1, 100)


class GuessNumberGame(BaseGame):
    name = "guess_number"
    min_players = 2
    max_players = None

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.scores = {u: 0 for u in players}
        self.round_no = 1                 # 当前轮次（1 起）
        self.secret = None
        self.low, self.high = SECRET_RANGE
        self.owner_idx = 0
        self.status = "await_secret"      # await_secret | playing | round_end
        self.round_end_at = 0.0
        self.await_since = time.time()    # 等出题时间戳（超时自动代出题兜底）
        self.auto_secret_wait = 20.0      # 秒（可注入便于测试）
        self.last_guess = None            # {"uid","val","dir"}
        self.correct_uid = None
        self.gap = 3.0                    # 局间间隔（可注入便于测试）

    # ---- 状态 ----
    def snapshot(self) -> dict:
        return {
            "game": self.name, "status": self.status,
            "round": self.round_no,
            "owner_uid": self.players[self.owner_idx],
            "low": self.low, "high": self.high,
            "secret": None if self.status != "round_end" else self.secret,
            "last_guess": self.last_guess, "correct_uid": self.correct_uid,
            "scores": dict(self.scores),
        }

    # ---- 动作 ----
    def act(self, uid: int, action: dict) -> list:
        if "secret" in action:
            return self._set_secret(uid, action["secret"])
        if "guess" in action:
            return self._guess(uid, action["guess"])
        raise GameRuleError("未知动作")

    def _set_secret(self, uid: int, secret) -> list:
        if uid != self.players[self.owner_idx]:
            raise GameRuleError("只有本轮出题者能设数字")
        if self.status not in ("await_secret", "playing"):
            raise GameRuleError("本局已结束，等待下一轮")
        try:
            n = int(secret)
        except (TypeError, ValueError):
            raise GameRuleError("数字必须是整数")
        if not (SECRET_RANGE[0] <= n <= SECRET_RANGE[1]):
            raise GameRuleError(f"数字须在 {SECRET_RANGE[0]}~{SECRET_RANGE[1]}")
        self.secret = n
        self.low, self.high = SECRET_RANGE
        self.status = "playing"
        return [f"{self._nick(uid)} 出题完成，大家开始猜（1~100）"]

    def _guess(self, uid: int, val) -> list:
        if uid not in self.players:
            raise GameRuleError("你不在本局")
        if self.status != "playing" or self.secret is None:
            raise GameRuleError("对局未开始")
        try:
            n = int(val)
        except (TypeError, ValueError):
            raise GameRuleError("数字必须是整数")
        if not (self.low <= n <= self.high):
            raise GameRuleError(f"数字须在 {self.low}~{self.high}")
        if n == self.secret:
            self.scores[uid] += 1
            self.correct_uid = uid
            self.last_guess = {"uid": uid, "val": n, "dir": "hit"}
            self.status = "round_end"
            self.round_end_at = time.time() + self.gap
            self._advance_owner()
            return [f"🎉 {self._nick(uid)} 猜中了 {n}！+1 分，下一轮由 {self._nick(self.players[self.owner_idx])} 出题"]
        direction = "low" if n < self.secret else "high"
        if direction == "low":
            self.low = max(self.low, n + 1)
        else:
            self.high = min(self.high, n - 1)
        self.last_guess = {"uid": uid, "val": n, "dir": direction}
        return [f"{self._nick(uid)} 猜 {n}：{'低了' if direction == 'low' else '高了'}（区间 {self.low}~{self.high}）"]

    # ---- 定时推进 ----
    def tick(self, now: float) -> list:
        if self.status == "round_end" and now >= self.round_end_at:
            self.status = "await_secret"
            self.secret = None
            self.correct_uid = None
            self.last_guess = None
            self.await_since = now
            return [f"第 {self.round_no} 轮开始，由 {self._nick(self.players[self.owner_idx])} 出题"]
        if self.status == "await_secret" and now >= self.await_since + self.auto_secret_wait:
            # 出题者久未出题/掉线：服务器代出题兜底，避免卡局
            self.secret = self.rng.randint(*SECRET_RANGE)
            self.low, self.high = SECRET_RANGE
            self.status = "playing"
            return [f"出题者超时，由服务器代出数字（1~100）"]
        return []

    # ---- 结算 ----
    def ended(self):
        return None   # 连续多轮，无终局（玩家随时可离开）

    # ---- 内部 ----
    def _advance_owner(self):
        self.owner_idx = (self.owner_idx + 1) % len(self.players)
        self.round_no += 1

    def _nick(self, uid: int) -> str:
        return f"玩家{uid}"
