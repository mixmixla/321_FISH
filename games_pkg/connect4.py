# -*- coding: utf-8 -*-
"""四子棋 Connect4：7列x6行，双人轮流选列落子，棋子重力下落，先连四子胜。"""
from games_pkg.base import BaseGame, GameRuleError

COLS = 7
ROWS = 6
DIRS = [(0, 1), (1, 0), (1, 1), (1, -1)]


class Connect4Game(BaseGame):
    name = "connect4"
    min_players = 2
    max_players = 2

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        # board[y][x]，y=0 顶部，y=ROWS-1 底部；0 空
        self.board = [[0] * COLS for _ in range(ROWS)]
        self.turn = 0
        self.last_col = None
        self.last_move = None
        self.winner_uid = None
        self.draw = False

    def snapshot(self) -> dict:
        return {
            "game": self.name, "status": "playing",
            "board": self.board, "rows": ROWS, "cols": COLS,
            "turn_uid": None if self.winner_uid else self.players[self.turn],
            "players": list(self.players),
            "last_move": self.last_move, "winner_uid": self.winner_uid,
            "draw": self.draw,
        }

    def act(self, uid: int, action: dict) -> list:
        if self.winner_uid is not None or self.draw:
            raise GameRuleError("本局已结束，请开新局")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        try:
            col = int(action.get("col"))
        except (TypeError, ValueError):
            raise GameRuleError("请选择一列（0~6）")
        if not (0 <= col < COLS):
            raise GameRuleError("列越界（0~6）")
        row = self._drop_row(col)
        if row is None:
            raise GameRuleError("该列已满")
        stone = self.turn + 1
        self.board[row][col] = stone
        self.last_col = col
        self.last_move = (col, row)
        if self._check_win(col, row, stone):
            self.winner_uid = uid
            return [f"🏆 {self._nick(uid)} 四连取胜！"]
        if all(self.board[0][c] for c in range(COLS)):
            self.draw = True
            return ["平局：棋盘已满"]
        self.turn = 1 - self.turn
        return []

    def _drop_row(self, col: int) -> int | None:
        """重力下落：返回该列最底部空位的行号"""
        for row in range(ROWS - 1, -1, -1):
            if self.board[row][col] == 0:
                return row
        return None

    def _check_win(self, x: int, y: int, stone: int) -> bool:
        for dx, dy in DIRS:
            cnt = 1
            for s in (1, -1):
                nx, ny = x + dx * s, y + dy * s
                while 0 <= nx < COLS and 0 <= ny < ROWS and self.board[ny][nx] == stone:
                    cnt += 1
                    nx += dx * s
                    ny += dy * s
            if cnt >= 4:
                return True
        return False

    def ended(self):
        if self.winner_uid is not None:
            return {"winner_uid": self.winner_uid,
                    "detail": f"{self._nick(self.winner_uid)} 四连取胜"}
        if self.draw:
            return {"winner_uid": None, "detail": "平局"}
        return None

    def _nick(self, uid: int) -> str:
        return f"玩家{uid}"