# -*- coding: utf-8 -*-
"""五子棋单人陪练：真人执黑，电脑执白。

这是 ``GomokuGame`` 的单人变体，不改变原双人棋的规则：棋盘仍为
15x15，只有**恰好**五子连线才算胜利，动作仍使用 ``x``/``y``。房间
里只登记真人一个 uid；电脑使用 ``AI_UID``，每次真人落子成功后在同一
次 ``act`` 调用内立即落子，服务器不会为它启动线程或定时搜索。

AI 的次序是有界且可重复的：先找自己的必胜点，再找真人的必杀点，最后
按中心距离、己方局部连子和对方潜在威胁做轻量启发式选点。这样陪练在
常见战术上不会漏掉一步胜负手，也不会引入机器学习或长耗时搜索。
"""

from games_pkg.base import GameRuleError
from games_pkg.gomoku import DIRS, SIZE, GomokuGame


AI_UID = -1


class GomokuSoloGame(GomokuGame):
    """单人五子棋：玩家执黑先行，电脑执白即时应手。"""

    name = "gomoku_solo"
    min_players = 1
    max_players = 1

    def __init__(self, players, seed=None):
        player_list = list(players or [])
        if len(player_list) != 1:
            raise GameRuleError("五子棋单人陪练只支持 1 名玩家")
        self.human = player_list[0]
        # Keep the parent game's two-seat representation for rule execution.
        # RoomManager owns the real room seats separately (and snapshot hides
        # the synthetic AI seat), so no per-move mutation of self.players is
        # needed.
        super().__init__([self.human, AI_UID], seed=seed)
        self.ai_uid = AI_UID
        self.last_move_uid = None

    # ---------- public state ----------
    def snapshot(self) -> dict:
        """公开快照只把真人放入 players，电脑以 ai_uid 标识。"""
        return {
            "game": self.name,
            "status": "playing",
            "board": self.board,
            "size": SIZE,
            "turn_uid": (None if self.winner_uid is not None or self.draw
                          else self.human),
            "players": [self.human],
            "ai_uid": AI_UID,
            "solo": True,
            "last_move": self.last_move,
            "last_move_uid": self.last_move_uid,
            "winner_uid": self.winner_uid,
            "draw": self.draw,
        }

    def act(self, uid: int, action: dict) -> list:
        """应用真人一手，并在未结算时立即应用电脑一手。"""
        if self.winner_uid is not None or self.draw:
            raise GameRuleError("本局已结束，请开新局")
        if uid != self.human:
            raise GameRuleError("单人练习只能由房主操作")

        # 父类已经持有 [human, AI] 两个内部座位；直接走同一套坐标、
        # 占位、恰好五连和满盘规则。
        messages = list(super().act(self.human, action))
        self.last_move_uid = self.human
        if self.winner_uid is not None or self.draw:
            return messages

        ai_action = self._ai_choose()
        x, y = int(ai_action["x"]), int(ai_action["y"])
        ai_messages = list(super().act(AI_UID, ai_action))
        self.last_move_uid = AI_UID
        # Parent returns the victory message on a winning move. Keep the
        # ordinary move visible too so the UI and room event log identify the
        # immediate computer response.
        return messages + [f"⚪ 电脑落子({x},{y})"] + ai_messages

    # ---------- bounded, deterministic AI ----------
    def _ordered_empty(self):
        """按中心距离稳定枚举空点，避免随机开局与不可复现回放。"""
        center = SIZE // 2
        points = [(x, y) for y in range(SIZE) for x in range(SIZE)
                  if self.board[y][x] == 0]
        points.sort(key=lambda p: (
            max(abs(p[0] - center), abs(p[1] - center)),
            abs(p[0] - center) + abs(p[1] - center),
            p[1], p[0]))
        return points

    def _would_win(self, x: int, y: int, stone: int) -> bool:
        """在当前盘面试下一子，沿用父类的恰好五连判断。"""
        if not (0 <= x < SIZE and 0 <= y < SIZE) or self.board[y][x] != 0:
            return False
        self.board[y][x] = stone
        try:
            return bool(self._check_win(x, y, stone))
        finally:
            self.board[y][x] = 0

    @staticmethod
    def _line_info(board, x: int, y: int, stone: int, dx: int, dy: int):
        """返回经过一点的连续长度和两端开放数。"""
        n = len(board)
        run = 1
        open_ends = 0
        for sign in (1, -1):
            nx, ny = x + dx * sign, y + dy * sign
            while 0 <= nx < n and 0 <= ny < n and board[ny][nx] == stone:
                run += 1
                nx += dx * sign
                ny += dy * sign
            if 0 <= nx < n and 0 <= ny < n and board[ny][nx] == 0:
                open_ends += 1
        return run, open_ends

    def _pattern_value(self, x: int, y: int, stone: int) -> int:
        """轻量局部形势分；不做递归搜索，单点评估有固定上界。"""
        self.board[y][x] = stone
        try:
            value = 0
            for dx, dy in DIRS:
                run, open_ends = self._line_info(
                    self.board, x, y, stone, dx, dy)
                if run > 5:                 # 长连按原规则不直接取胜
                    value -= 140
                elif run == 5:
                    value += 9000
                elif run == 4:
                    value += 1400 if open_ends == 2 else 420
                elif run == 3:
                    value += 260 if open_ends == 2 else 80
                elif run == 2:
                    value += 36 if open_ends == 2 else 12
                value += open_ends * 3
            return value
        finally:
            self.board[y][x] = 0

    def _ai_choose(self):
        """返回电脑应手 ``{"x": x, "y": y}``，无空位时返回 None。"""
        points = self._ordered_empty()
        if not points:
            return None

        # 1) 能赢先赢；2) 对手有一步杀先堵。两步均按中心优先稳定取点。
        for x, y in points:
            if self._would_win(x, y, 2):
                return {"x": x, "y": y}
        for x, y in points:
            if self._would_win(x, y, 1):
                return {"x": x, "y": y}

        # 空盘固定天元；随后只在已有棋子周围优先评估，保留全盘兜底。
        if len(points) == SIZE * SIZE:
            return {"x": SIZE // 2, "y": SIZE // 2}
        occupied = [(x, y) for y in range(SIZE) for x in range(SIZE)
                    if self.board[y][x]]
        local = [p for p in points
                 if any(max(abs(p[0] - q[0]), abs(p[1] - q[1])) <= 2
                        for q in occupied)]
        candidates = local or points
        center = SIZE // 2
        best = None
        best_score = None
        for x, y in candidates:
            own = self._pattern_value(x, y, 2)
            # 该点若不占，真人下一手可能获得的局部形势；占住它是
            # 轻量的防守加分，即使还没有形成必杀也会贴近对手棋形。
            opp = self._pattern_value(x, y, 1)
            adjacent_own = adjacent_any = 0
            for ox in range(max(0, x - 2), min(SIZE, x + 3)):
                for oy in range(max(0, y - 2), min(SIZE, y + 3)):
                    if ox == x and oy == y:
                        continue
                    value = self.board[oy][ox]
                    adjacent_any += bool(value)
                    adjacent_own += value == 2
            center_dist = abs(x - center) + abs(y - center)
            score = (own * 4 + opp * 2 + adjacent_own * 20
                     + adjacent_any * 3 - center_dist * 2)
            if best_score is None or score > best_score:
                best_score = score
                best = {"x": x, "y": y}
        return best or {"x": points[0][0], "y": points[0][1]}

    def _nick(self, uid: int) -> str:
        return "电脑" if uid == AI_UID else f"玩家{uid}"


__all__ = ["AI_UID", "GomokuSoloGame"]
