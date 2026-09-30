# -*- coding: utf-8 -*-
"""非洲播棋（致敬 Kalah/Mancala）：6 洞 ×2。每洞开局 4 子。轮到选自己 1~6 号洞，取走全部子，
逆时针逐洞各落 1 子（跳过对手库）。最后落在自己库可再走一次；最后落在自己空穴且对侧穴有子，
则连同对侧穴的子一起收入自己库。某玩家穴全空即终局，剩余子全入对方库，比库里子数，多者胜。"""
from games_pkg.base import BaseGame, GameRuleError

HOLES = 6
STORE0 = HOLES              # 玩家A库 index 6
STORE1 = HOLES + 1          # 玩家B库 index 7
START_B = HOLES + 2         # 玩家B洞穴起始 8


class KalahGame(BaseGame):
    name = "kalah"
    min_players = 2
    max_players = 2

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        a, b = players[0], players[1]
        self.p0, self.p1 = a, b
        self.cells = [4] * HOLES + [0, 0] + [4] * HOLES   # 0-5 A洞,6 A库,7 B库,8-13 B洞
        self.turn = a
        self.winner = None
        self.last_move = None
        self.finished = False

    # ---- 视角工具 ----
    def _is_store(self, idx):
        return idx in (STORE0, STORE1)

    def _opp_hole(self, i):
        """玩家A洞 i（0-5）对应的对手（B）洞 index"""
        return START_B + (HOLES - 1 - i)

    def _store_of(self, pid):
        return STORE0 if pid == self.p0 else STORE1

    def _holes_of(self, pid):
        if pid == self.p0:
            return list(range(0, HOLES))
        return list(range(START_B, START_B + HOLES))

    def act(self, uid, action):
        if self.finished or self.winner:
            raise GameRuleError("本局已结束")
        if uid != self.turn:
            raise GameRuleError("还没轮到你")
        hole = action.get("hole")
        try:
            hole = int(hole) - 1               # 前端用 1~6
        except (TypeError, ValueError):
            raise GameRuleError("洞号无效")
        holes = self._holes_of(uid)
        if hole not in holes:
            raise GameRuleError("只能选己方洞")
        if self.cells[hole] == 0:
            raise GameRuleError("该洞为空")
        return self._sow(uid, hole)

    def _sow(self, pid, hole):
        seeds = self.cells[hole]
        self.cells[hole] = 0
        idx = hole
        msgs = []
        go_again = False
        captured = 0
        while seeds > 0:
            idx = (idx + 1) % len(self.cells)
            if idx in (STORE0, STORE1) and idx != self._store_of(pid):
                continue                        # 跳过对方库
            self.cells[idx] += 1
            seeds -= 1
        last = idx
        # 若最后落在自己库 → 再走一次
        if last == self._store_of(pid):
            go_again = True
        # 收割：最后落在己方空穴且对侧有子
        own_holes = self._holes_of(pid)
        if last in own_holes and self.cells[last] == 1:
            opp = self._opp_hole(last) if pid == self.p0 else \
                (HOLES - 1 - (last - START_B))
            if 0 <= opp < len(self.cells) and not self._is_store(opp) and self.cells[opp] > 0:
                captured = self.cells[opp] + self.cells[last]
                self.cells[self._store_of(pid)] += captured
                self.cells[opp] = 0
                self.cells[last] = 0
        self.last_move = (pid, hole, last, go_again, captured)
        if go_again:
            msgs.append(f"🔁 {self._nick(pid)} 落在自己库，再走一次")
        elif captured:
            msgs.append(f"🐚 {self._nick(pid)} 收子 {captured} 入库")
        if not go_again:
            self._check_win()
            if self.winner:
                msgs.append(f"🏆 {self._nick(self.winner)} 库里子最多取胜！")
                return msgs
            self.turn = self.p1 if pid == self.p0 else self.p0
            msgs.insert(0, f"➡️ 轮到 {self._nick(self.turn)}")
        return msgs

    def _check_win(self):
        empty0 = all(self.cells[i] == 0 for i in range(0, HOLES))
        empty1 = all(self.cells[i] == 0 for i in range(START_B, START_B + HOLES))
        if not (empty0 or empty1):
            return
        # 收尾
        for i in range(0, HOLES):
            self.cells[STORE0] += self.cells[i]
            self.cells[i] = 0
        for i in range(START_B, START_B + HOLES):
            self.cells[STORE1] += self.cells[i]
            self.cells[i] = 0
        s0, s1 = self.cells[STORE0], self.cells[STORE1]
        if s0 > s1:
            self.winner = self.p0
        elif s1 > s0:
            self.winner = self.p1
        else:
            self.winner = None    # 平局
        self.finished = True

    def snapshot(self):
        return {
            "game": self.name, "status": "ended" if (self.winner or self.finished) else "playing",
            "turn": self.turn, "cells": self.cells,
            "p0": self.p0, "p1": self.p1, "winner_uid": self.winner,
            "stores": {str(self.p0): self.cells[STORE0], str(self.p1): self.cells[STORE1]},
            "last": self.last_move,
        }

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner,
                    "detail": f"{self._nick(self.winner)} 播棋库中 {self.cells[self._store_of(self.winner)]} 子"}
        if self.finished:
            return {"winner_uid": None, "detail": "库里子数平局"}
        return None

    def player_left(self, uid):
        other = self.p1 if uid == self.p0 else self.p0
        if self.winner is None and not self.finished:
            self.winner = other
            self.finished = True
        return [f"💨 {self._nick(uid)} 离开，{self._nick(other)} 获胜"]

    def _nick(self, uid):
        return f"玩家{uid}"