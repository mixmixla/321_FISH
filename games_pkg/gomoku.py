# -*- coding: utf-8 -*-
"""五子棋：15x15，两人对战，多人观战。"""
from games_pkg.base import BaseGame, GameRuleError

SIZE = 15
DIRS = [(1, 0), (0, 1), (1, 1), (1, -1)]


class GomokuGame(BaseGame):
    name = "gomoku"
    min_players = 2
    max_players = 2          # 超过自动变观战

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.board = [[0] * SIZE for _ in range(SIZE)]
        self.turn = 0          # 指向 self.players 的下标
        self.last_move = None  # (x, y)
        self.winner_uid = None
        self.draw = False

    def snapshot(self) -> dict:
        return {
            "game": self.name, "status": "playing",
            "board": self.board, "size": SIZE,
            "turn_uid": None if self.winner_uid else self.players[self.turn],
            "players": list(self.players),
            "last_move": self.last_move, "winner_uid": self.winner_uid,
            "draw": self.draw,
        }

    def act(self, uid: int, action: dict) -> list:
        x, y = action.get("x"), action.get("y")
        try:
            x, y = int(x), int(y)
        except (TypeError, ValueError):
            raise GameRuleError("坐标必须为整数")
        if self.winner_uid is not None or self.draw:
            raise GameRuleError("本局已结束，请开新局")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        if not (0 <= x < SIZE and 0 <= y < SIZE):
            raise GameRuleError("落子越界")
        if self.board[y][x] != 0:
            raise GameRuleError("该位置已有棋子")
        stone = self.turn + 1
        self.board[y][x] = stone
        self.last_move = (x, y)
        if self._check_win(x, y, stone):
            self.winner_uid = uid
            return [f"🏆 {self._nick(uid)} 五连取胜！"]
        if all(all(cell for cell in row) for row in self.board):
            self.draw = True
            return ["平局：棋盘已满"]
        self.turn = 1 - self.turn
        return []

    def _check_win(self, x: int, y: int, stone: int) -> bool:
        for dx, dy in DIRS:
            cnt = 1
            for s in (1, -1):
                nx, ny = x + dx * s, y + dy * s
                while 0 <= nx < SIZE and 0 <= ny < SIZE and self.board[ny][nx] == stone:
                    cnt += 1
                    nx += dx * s
                    ny += dy * s
            if cnt >= 5:
                return True
        return False

    def ended(self):
        if self.winner_uid is not None:
            return {"winner_uid": self.winner_uid, "detail": f"{self._nick(self.winner_uid)} 五连取胜"}
        if self.draw:
            return {"winner_uid": None, "detail": "平局"}
        return None

    def _nick(self, uid: int) -> str:
        return f"玩家{uid}"
