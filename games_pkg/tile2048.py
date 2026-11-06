# -*- coding: utf-8 -*-
"""2048 单人规则。

规则对象只处理 4×4 棋盘和动作，不做任何 IO。房间层仍是唯一的状态广播者；
每个有效 ``move`` 会在合并完成后补一块新砖，非法的无效方向不会改变状态。
"""
from __future__ import annotations

from games_pkg.base import BaseGame, GameRuleError


class Tile2048Game(BaseGame):
    """标准 2048 单人局：玩家先得到两块砖，合并到 2048 即胜。"""

    name = "tile2048"
    min_players = 1
    max_players = 1
    SIZE = 4
    TARGET = 2048
    DIRECTIONS = ("left", "right", "up", "down")
    DIRECTION_LABELS = {"left": "左", "right": "右", "up": "上", "down": "下"}

    def __init__(self, players, seed=None):
        if len(players) != 1:
            raise GameRuleError("2048 仅支持一名玩家")
        super().__init__(players, seed)
        self.human = self.players[0]
        self.board = [[0] * self.SIZE for _ in range(self.SIZE)]
        self.score = 0
        self.status = "playing"       # playing | won | lost
        self.winner_uid = None
        self.over = False
        self._spawn_tile()
        self._spawn_tile()

    # ---------- public game contract ----------
    def snapshot(self) -> dict:
        """Return a detached, JSON-friendly public snapshot."""
        return {
            "game": self.name,
            "status": self.status,
            "board": [row[:] for row in self.board],
            "size": self.SIZE,
            "target": self.TARGET,
            "score": self.score,
            "players": list(self.players),
            "turn_uid": None if self.over else self.human,
            "winner_uid": self.winner_uid,
        }

    def legal_moves(self, uid: int) -> list:
        if uid != self.human or self.over:
            return []
        return [
            {"op": "move", "dir": direction}
            for direction in self.DIRECTIONS
            if self._move_board(self.board, direction)[1]
        ]

    def act(self, uid: int, action: dict) -> list:
        if uid != self.human:
            raise GameRuleError("单人 2048 只能由本局玩家操作")
        if self.over:
            raise GameRuleError("本局已结束")
        if not isinstance(action, dict) or action.get("op") != "move":
            raise GameRuleError("2048 动作必须是 move")
        direction = action.get("dir")
        if direction not in self.DIRECTIONS:
            raise GameRuleError("方向必须是 left/right/up/down")

        next_board, changed, gained = self._move_board(self.board, direction)
        if not changed:
            # 不生成砖，保证无效步对状态完全无副作用。
            raise GameRuleError("这个方向无法移动")

        self.board = next_board
        self.score += gained
        self._spawn_tile()

        if self._has_target():
            self.status = "won"
            self.over = True
            self.winner_uid = self.human
            return [f"🏆 {self._nick(self.human)} 达成 2048！得分 {self.score}"]
        if not self._has_moves():
            self.status = "lost"
            self.over = True
            self.winner_uid = None
            return [f"💥 {self._nick(self.human)} 无路可走，最终得分 {self.score}"]
        merged = f"，合并得分 +{gained}" if gained else ""
        return [f"{self._nick(self.human)} 向 {self.DIRECTION_LABELS[direction]} 移动{merged}"]

    def ended(self):
        if not self.over:
            return None
        if self.status == "won":
            return {
                "winner_uid": self.human,
                "detail": f"{self._nick(self.human)} 达成 2048，得分 {self.score}",
            }
        return {
            "winner_uid": None,
            "detail": f"{self._nick(self.human)} 无路可走，得分 {self.score}",
        }

    # ---------- rule helpers ----------
    def _spawn_tile(self):
        """在一个空格生成 2（90%）或 4（10%），返回公开位置或 None。"""
        empty = [
            (row, col)
            for row in range(self.SIZE)
            for col in range(self.SIZE)
            if self.board[row][col] == 0
        ]
        if not empty:
            return None
        row, col = self.rng.choice(empty)
        value = 4 if self.rng.random() < 0.10 else 2
        self.board[row][col] = value
        return {"row": row, "col": col, "value": value}

    @classmethod
    def _move_board(cls, board, direction):
        """Return ``(new_board, changed, gained)`` without mutating *board*."""
        if direction not in cls.DIRECTIONS:
            return [row[:] for row in board], False, 0
        out = [[0] * cls.SIZE for _ in range(cls.SIZE)]
        gained = 0
        for line_index in range(cls.SIZE):
            if direction in ("left", "right"):
                line = [board[line_index][col] for col in range(cls.SIZE)]
            else:
                line = [board[row][line_index] for row in range(cls.SIZE)]
            if direction in ("right", "down"):
                line.reverse()
            packed, points = cls._slide_line(line)
            if direction in ("right", "down"):
                packed.reverse()
            gained += points
            if direction in ("left", "right"):
                out[line_index] = packed
            else:
                for row, value in enumerate(packed):
                    out[row][line_index] = value
        return out, out != [row[:] for row in board], gained

    @staticmethod
    def _slide_line(line):
        """Compress and merge a line; each source tile participates once."""
        values = [value for value in line if value]
        merged = []
        points = 0
        index = 0
        while index < len(values):
            if index + 1 < len(values) and values[index] == values[index + 1]:
                value = values[index] * 2
                merged.append(value)
                points += value
                index += 2
            else:
                merged.append(values[index])
                index += 1
        return merged + [0] * (Tile2048Game.SIZE - len(merged)), points

    def _has_target(self):
        return any(value >= self.TARGET for row in self.board for value in row)

    def _has_moves(self):
        if any(value == 0 for row in self.board for value in row):
            return True
        for row in range(self.SIZE):
            for col in range(self.SIZE):
                value = self.board[row][col]
                if row + 1 < self.SIZE and self.board[row + 1][col] == value:
                    return True
                if col + 1 < self.SIZE and self.board[row][col + 1] == value:
                    return True
        return False

    @staticmethod
    def _nick(uid):
        return f"玩家{uid}"
