# -*- coding: utf-8 -*-
"""奥赛罗（黑白棋）：8x8，黑白各一轮落子，夹住对方子则翻转；无处可下则让，
双方均无子可下时按子数定胜负。"""
from games_pkg.base import BaseGame, GameRuleError

SIZE = 8
DIRS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
BLACK, WHITE = 1, 2


class OthelloGame(BaseGame):
    name = "othello"
    min_players = 2
    max_players = 2

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.board = [[0] * SIZE for _ in range(SIZE)]
        c = SIZE // 2 - 1
        self.board[c][c] = self.board[c + 1][c + 1] = BLACK
        self.board[c][c + 1] = self.board[c + 1][c] = WHITE
        self.turn = 0          # 黑先（players[0]）
        self.last_move = None
        self.winner_uid = None
        self.pass_next = False
        self.scores = None     # 结束后 {uid: n}

    def snapshot(self) -> dict:
        state = {
            "game": self.name, "status": "playing",
            "board": self.board, "size": SIZE,
            "turn_uid": None if self.winner_uid else self.players[self.turn],
            "players": list(self.players), "last_move": self.last_move,
            "winner_uid": self.winner_uid,
        }
        if self.pass_next and not self.winner_uid:
            state["passing"] = True
        if self.scores:
            state["scores"] = dict(self.scores)
        return state

    def act(self, uid: int, action: dict) -> list:
        if self.winner_uid is not None:
            raise GameRuleError("本局已结束，请开新局")
        if self.pass_next:
            raise GameRuleError("对方无处可下，对方已让过")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        try:
            x, y = int(action.get("x")), int(action.get("y"))
        except (TypeError, ValueError):
            raise GameRuleError("坐标必须为整数")
        if not (0 <= x < SIZE and 0 <= y < SIZE):
            raise GameRuleError("落子越界")
        self._place(x, y)
        return self._advance()

    def _advance(self) -> list:
        """落子后切换对手；对手无处可下则让过；双方皆无则结算"""
        nxt = 1 - self.turn
        if self._legal_for(nxt):
            self.turn = nxt
            self.pass_next = False
            return []
        if not self._legal_for(self.turn):
            # 双方都无处可下 → 结算
            self._finish()
            return ["棋局已满/双方皆无处可下，按子数结算"]
        # 对手被让过，由当前玩家继续
        self.pass_next = True
        return ["对手无处可下，自动让过，轮到你"]

    def _place(self, x: int, y: int) -> None:
        if self.board[y][x] != 0:
            raise GameRuleError("该位置已有棋子")
        stone = self.turn + 1
        opp = 3 - stone
        flips = []
        for dx, dy in DIRS:
            line = []
            nx, ny = x + dx, y + dy
            while 0 <= nx < SIZE and 0 <= ny < SIZE:
                if self.board[ny][nx] == opp:
                    line.append((nx, ny))
                elif self.board[ny][nx] == stone:
                    flips.extend(line)
                    break
                else:
                    break
                nx += dx
                ny += dy
        if not flips:
            raise GameRuleError("该落子无法夹住任何对手棋子")
        self.board[y][x] = stone
        for fx, fy in flips:
            self.board[fy][fx] = stone
        self.last_move = (x, y)

    def _legal_for(self, index: int) -> bool:
        stone = index + 1
        opp = 3 - stone
        for y in range(SIZE):
            for x in range(SIZE):
                if self.board[y][x] != 0:
                    continue
                if self._flip_count(x, y, stone, opp):
                    return True
        return False

    def _flip_count(self, x: int, y: int, stone: int, opp: int) -> int:
        total = 0
        for dx, dy in DIRS:
            cnt = 0
            nx, ny = x + dx, y + dy
            while 0 <= nx < SIZE and 0 <= ny < SIZE and self.board[ny][nx] == opp:
                cnt += 1
                nx += dx
                ny += dy
            if cnt and 0 <= nx < SIZE and 0 <= ny < SIZE and self.board[ny][nx] == stone:
                total += cnt
        return total

    def _finish(self) -> None:
        black = sum(row.count(BLACK) for row in self.board)
        white = sum(row.count(WHITE) for row in self.board)
        self.scores = {self.players[0]: black, self.players[1]: white}
        b_uid, w_uid = self.players[0], self.players[1]
        if black > white:
            self.winner_uid = b_uid
            self.turn = 0
        elif white > black:
            self.winner_uid = w_uid
            self.turn = 1
        else:
            self.winner_uid = None
            self.turn = 0

    def ended(self):
        if self.winner_uid is None and self.scores is None:
            return None
        a, b = self.scores[self.players[0]], self.scores[self.players[1]]
        if self.winner_uid is not None:
            return {"winner_uid": self.winner_uid,
                    "detail": f"{self._nick(self.winner_uid)} 以 {max(a, b)}:{min(a, b)} 获胜"}
        return {"winner_uid": None, "detail": f"平局 {a}:{b}"}

    def _nick(self, uid: int) -> str:
        return f"玩家{uid}"