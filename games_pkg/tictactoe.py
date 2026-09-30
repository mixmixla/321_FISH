# -*- coding: utf-8 -*-
"""井字棋（致敬 Tic-Tac-Toe）：3x3，两方轮流落子，横/竖/斜先连 3 者胜，棋盘满为平局。"""
from games_pkg.base import BaseGame, GameRuleError

SIZE = 3
DIRS = [(1, 0), (0, 1), (1, 1), (1, -1)]


class TicTacToeGame(BaseGame):
    name = "tictactoe"
    min_players = 2
    max_players = 2

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.board = [[0] * SIZE for _ in range(SIZE)]
        self.turn = 0
        self.last_move = None
        self.winner_uid = None
        self.draw = False

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "board": self.board, "size": SIZE,
            "turn_uid": None if self.winner_uid else self.players[self.turn],
            "players": list(self.players),
            "last_move": self.last_move, "winner_uid": self.winner_uid,
            "draw": self.draw,
        }

    def act(self, uid, action):
        x, y = action.get("x"), action.get("y")
        try:
            x, y = int(x), int(y)
        except (TypeError, ValueError):
            raise GameRuleError("坐标必须为整数")
        if self.winner_uid is not None or self.draw:
            raise GameRuleError("本局已结束")
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
            return [f"🏆 {self._nick(uid)} 三连取胜！"]
        if all(all(cell for cell in row) for row in self.board):
            self.draw = True
            return ["平局：棋盘已满"]
        self.turn = 1 - self.turn
        return [f"✅ {self._nick(uid)} 落子（{x},{y}）"]

    def _check_win(self, x, y, stone):
        for dx, dy in DIRS:
            cnt = 1
            for s in (1, -1):
                nx, ny = x + dx * s, y + dy * s
                while 0 <= nx < SIZE and 0 <= ny < SIZE and self.board[ny][nx] == stone:
                    cnt += 1
                    nx += dx * s
                    ny += dy * s
            if cnt >= 3:
                return True
        return False

    def ended(self):
        if self.winner_uid is not None:
            return {"winner_uid": self.winner_uid, "detail": f"{self._nick(self.winner_uid)} 三连取胜"}
        if self.draw:
            return {"winner_uid": None, "detail": "平局"}
        return None

    def _nick(self, uid):
        return f"玩家{uid}"