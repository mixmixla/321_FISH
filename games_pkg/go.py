# -*- coding: utf-8 -*-
"""围棋（9x9）：黑白交替落子，团团被吃(无气)即移除，禁自杀点并应用简单打劫同型禁着。
双方轮流「过」(pass)则终局，按「各色子 + 被其完全包围的空地」计分，目数多者胜。"""
from games_pkg.base import BaseGame, GameRuleError

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _grp(board, x, y, color):
    """返回 (团块格子集合, 气/贴邻空点集合)"""
    seen = {(x, y)}
    stack = [(x, y)]
    liberties = set()
    while stack:
        cx, cy = stack.pop()
        for dx, dy in DIRS:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < len(board) and 0 <= ny < len(board)):
                continue
            v = board[ny][nx]
            if v == 0:
                liberties.add((nx, ny))
            elif v == color and (nx, ny) not in seen:
                seen.add((nx, ny))
                stack.append((nx, ny))
    return seen, liberties


class GoGame(BaseGame):
    name = "go"
    min_players = 2
    max_players = 2

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.p0, self.p1 = players[0], players[1]
        self.size = 9
        self.board = [[0] * self.size for _ in range(self.size)]
        self.turn = 0
        self.passes = 0
        self.captured = [0, 0]          # 白方吃子(player1)列为0? 用[黑吞,白吞]
        self.history = []
        self.winner = None
        self.over = False
        self.scores = None
        self.last_opp = None
        self.last_move = None

    def _own_color(self):
        return 1 if self.turn == 0 else 2

    def _lawful(self, x, y, color):
        if not (0 <= x < self.size and 0 <= y < self.size):
            raise GameRuleError("越界")
        if self.board[y][x] != 0:
            raise GameRuleError("该位已有子")
        # 试下
        self.board[y][x] = color
        # 1) 吃对手
        opp = 1 if color == 2 else 2
        killed = 0
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < self.size and 0 <= ny < self.size):
                continue
            if self.board[ny][nx] == opp:
                grp, lib = _grp(self.board, nx, ny, opp)
                if not lib:
                    for gx, gy in grp:
                        self.board[gy][gx] = 0
                    killed += len(grp)
        # 2) 自杀检测
        grp, lib = _grp(self.board, x, y, color)
        if not lib:
            self.board[y][x] = 0
            raise GameRuleError("自杀点")
        self.board[y][x] = 0
        return True

    def act(self, uid, action):
        if self.over or self.winner:
            raise GameRuleError("本局已结束")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        if action.get("pass"):
            self.last_move = None
            self.passes += 1
            if self.passes >= 2:          # 连续两次过 → 终局
                self.over = True
                self._score()
                self.winner = self._decide_winner()
                msgs = [f"⏸ {self._nick(uid)} 过，双方停手下终局",
                        f"🏁 黑 {self.scores[1]} 目 / 白 {self.scores[2]} 目"]
                if self.winner:
                    msgs.append(f"🏆 {self._nick(self.winner)} 目数领先获胜")
                else:
                    msgs.append("🤝 和棋")
                return msgs
            self.turn = 1 - self.turn
            return [f"⏸ {self._nick(uid)} 过"]
        try:
            x = int(action.get("x")); y = int(action.get("y"))
        except (TypeError, ValueError):
            raise GameRuleError("坐标必须为整数")
        color = self._own_color()
        if not (0 <= x < self.size and 0 <= y < self.size):
            raise GameRuleError("越界")
        if self.board[y][x] != 0:
            raise GameRuleError("该位已有子")
        # 应用时校验自杀/吃
        self.board[y][x] = color
        opp = 1 if color == 2 else 2
        killed = 0
        caps = []
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < self.size and 0 <= ny < self.size):
                continue
            if self.board[ny][nx] == opp:
                grp, lib = _grp(self.board, nx, ny, opp)
                if not lib:
                    caps.extend(grp)
        if not caps:
            grp, lib = _grp(self.board, x, y, color)
            if not lib:
                self.board[y][x] = 0
                raise GameRuleError("自杀点")
        for gx, gy in caps:
            self.board[gy][gx] = 0
        self.captured[color - 1] += len(caps)
        # 简单同型禁止
        key = str(self.board)
        if key == self.last_opp:
            raise GameRuleError("同型反复禁止(打劫)")
        self.history.append(key)
        self.passes = 0
        self.last_opp = key
        self.last_move = (x, y)
        self.turn = 1 - self.turn
        return [f"⚫ {self._nick(uid)} 落子({x},{y})" + (f"，提 {len(caps)} 子" if caps else "")]

    def _score(self):
        """计分：各色子 + 完全被该色包围的空地"""
        size = self.size
        owned = {1: [0, 0], 2: [0, 0]}   # {颜色:[石头数, 空地数]}
        for y in range(size):
            for x in range(size):
                v = self.board[y][x]
                if v:
                    owned[v][0] += 1
        # 空地归属标记
        visited = set()
        for y in range(size):
            for x in range(size):
                if self.board[y][x] != 0 or (x, y) in visited:
                    continue
                region = {(x, y)}
                stack = [(x, y)]
                touches = set()
                while stack:
                    cx, cy = stack.pop()
                    for dx, dy in DIRS:
                        nx, ny = cx + dx, cy + dy
                        if not (0 <= nx < size and 0 <= ny < size):
                            continue
                        v = self.board[ny][nx]
                        if v == 0:
                            if (nx, ny) not in region:
                                region.add((nx, ny))
                                stack.append((nx, ny))
                        else:
                            touches.add(v)
                for rx, ry in region:
                    visited.add((rx, ry))
                if len(touches) == 1:
                    c = touches.pop()
                    owned[c][1] += len(region)
        self.scores = {1: owned[1][0] + owned[1][1], 2: owned[2][0] + owned[2][1]}

    def _decide_winner(self):
        b, w = self.scores[1], self.scores[2]
        if b > w:
            return self.p0
        if w > b:
            return self.p1
        return None

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "board": self.board, "size": self.size,
            "turn_uid": None if self.over else self.players[self.turn],
            "captured": self.captured, "players": list(self.players),
            "winner_uid": self.winner, "scores": self.scores, "over": self.over,
            "last_move": self.last_move,
            "legend": {"0": "空", "1": "⚫", "2": "⚪"},
        }

    def ended(self):
        if self.over:
            if self.winner:
                return {"winner_uid": self.winner,
                        "detail": f"黑 {self.scores[1]} 目 / 白 {self.scores[2]} 目，{self._nick(self.winner)} 胜"}
            return {"winner_uid": None, "detail": "和棋"}
        return None

    def _nick(self, uid):
        return f"玩家{uid}"