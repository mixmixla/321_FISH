# -*- coding: utf-8 -*-
"""军棋（休闲明棋版）：5x10 棋盘，上 5 行红方、下 5 行黑方，双方各 25 子布阵。
军衔：司令>军长>师长>旅长>团长>营长>连长>排长>工兵；炸弹可同归任何子；地雷不可动，
仅工兵能挖；军旗不可动，扛起对方军旗即获胜。非炸弹子撞地雷则自己被灭。"""
from games_pkg.base import BaseGame, GameRuleError

COLS, ROWS = 5, 10
EMPTY = 0
FLAG, MINE, BOMB = 0, 1, 2
ENGINEER = 3
# 编码：EMPTY=0；玩家0 子 = 10+rank (10..21)，玩家1 子 = 40+rank (40..51)
RANK_NAMES = {0: "军旗", 1: "地雷", 2: "炸弹", 3: "工兵", 4: "排长", 5: "连长",
              6: "营长", 7: "团长", 8: "旅长", 9: "师长", 10: "军长", 11: "司令"}
RANK_EMO = {0: "🚩", 1: "💣", 2: "💥", 3: "🔧", 4: "🪖", 5: "🪖", 6: "🪖",
            7: "🪖", 8: "🪖", 9: "🪖", 10: "🪖", 11: "👑"}
CN = {r: f"{RANK_EMO[r]} {RANK_NAMES[r]}" for r in RANK_NAMES}

# 每方 25 子
ARMY = [11, 10, 9, 9, 8, 8, 7, 7, 6, 6, 5, 5, 5, 4, 4, 4, 3, 3, 3, 2, 2, 1, 1, 1, 0]


def _side(code):
    return 1 if code >= 40 else 0


def _rank(code):
    return code - 40 if code >= 40 else code - 10


class JunqiGame(BaseGame):
    name = "junqi"
    min_players = 2
    max_players = 2

    def __init__(self, players, seed=None):
        super().__init__(players, seed)
        self.p0, self.p1 = players[0], players[1]
        self.board = [[EMPTY] * COLS for _ in range(ROWS)]
        # 布阵：玩家0(红) 上 5 行，玩家1(黑) 下 5 行
        r0 = ARMY[:]
        r1 = ARMY[:]
        self.rng.shuffle(r0)
        self.rng.shuffle(r1)
        for y in range(5):
            for x in range(COLS):
                self.board[y][x] = 10 + r0[y * COLS + x]           # 玩家0: code 10..21
        for y in range(5, ROWS):
            for x in range(COLS):
                self.board[y][x] = 40 + r1[(y - 5) * COLS + x]     # 玩家1: code 40..51
        self.turn = 0
        self.winner = None
        self.last_move = None

    # ---- 编码辅助 ----
    @staticmethod
    def _code(side, rank):
        return 10 + rank if side == 0 else 40 + rank

    def _nick(self, uid):
        return f"玩家{uid}"

    def _adj(self, x, y):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < COLS and 0 <= ny < ROWS:
                yield nx, ny

    def act(self, uid, action):
        if self.winner:
            raise GameRuleError("本局已结束")
        if uid != self.players[self.turn]:
            raise GameRuleError("还没轮到你")
        try:
            fx = int(action.get("fx")); fy = int(action.get("fy"))
            tx = int(action.get("tx")); ty = int(action.get("ty"))
        except (TypeError, ValueError):
            raise GameRuleError("坐标必须为整数")
        if not (0 <= fx < COLS and 0 <= fy < ROWS and 0 <= tx < COLS and 0 <= ty < ROWS):
            raise GameRuleError("越界")
        me = self._side_mask(self.board[fy][fx])
        if me != self.turn:
            raise GameRuleError("只能移动己方棋子")
        if (tx, ty) not in self._adj(fx, fy):
            raise GameRuleError("只能走相邻一格")
        code = self.board[fy][fx]
        rank = _rank(code)
        if rank in (FLAG, MINE):
            raise GameRuleError(f"{CN[rank]} 不能移动")
        target = self.board[ty][tx]
        if target and _side(target) == self.turn:
            raise GameRuleError("不能移动到己方棋子")
        return self._resolve(fx, fy, tx, ty, code, rank, target)

    def _side_mask(self, code):
        return 0 if code == EMPTY else _side(code)

    def _resolve(self, fx, fy, tx, ty, code, rank, target):
        msgs = [f"🐾 {self._nick_n(self.turn)} {CN[rank]} ({fx},{fy})→({tx},{ty})"]
        # 扛军旗 → 立即获胜
        if target and _side(target) != self.turn and _rank(target) == FLAG:
            self.board[fy][fx] = EMPTY
            self.board[ty][tx] = code
            self.winner = self.players[self.turn]
            return [f"🏆 {self._nick_n(self.turn)} 扛起对方军旗获胜！"]
        trank = _rank(target) if target else None
        tside = _side(target) if target else None
        # 有敌方子被吃判定
        if target and tside != self.turn:
            # 我方是炸弹 → 同归
            if rank == BOMB:
                self.board[fy][fx] = EMPTY
                self.board[ty][tx] = EMPTY
                self.turn = 1 - self.turn
                return msgs + [f"💥 炸弹与 {CN[trank]} 同归于尽"]
            # 敌方是炸弹 → 同归
            if trank == BOMB:
                self.board[fy][fx] = EMPTY
                self.board[ty][tx] = EMPTY
                self.turn = 1 - self.turn
                return msgs + [f"💥 撞上炸弹，同归于尽"]
            # 敌方是地雷 → 仅工兵可挖
            if trank == MINE:
                self.board[fy][fx] = EMPTY
                if rank == ENGINEER:
                    self.board[ty][tx] = code
                    self.turn = 1 - self.turn
                    return msgs + [f"🔧 工兵挖掉地雷"]
                else:
                    self.turn = 1 - self.turn
                    return msgs + [f"💣 {CN[rank]} 撞上地雷牺牲"]
            # 普通军衔比较
            if rank > trank:
                self.board[fy][fx] = EMPTY
                self.board[ty][tx] = code
                self.turn = 1 - self.turn
                return msgs + [f"⚔ 吃掉敌方 {CN[trank]}"]
            if rank == trank:
                self.board[fy][fx] = EMPTY
                self.board[ty][tx] = EMPTY
                self.turn = 1 - self.turn
                return msgs + [f"🤝 同级兑子"]
            # rank < trank → 被吃
            self.board[fy][fx] = EMPTY
            self.turn = 1 - self.turn
            return msgs + [f"💥 被敌方 {CN[trank]} 吃掉"]
        # 空位移动
        self.board[fy][fx] = EMPTY
        self.board[ty][tx] = code
        self.turn = 1 - self.turn
        return msgs

    def snapshot(self):
        return {
            "game": self.name, "status": "playing",
            "board": [[self.board[y][x] for x in range(COLS)] for y in range(ROWS)],
            "rows": ROWS, "cols": COLS,
            "turn_uid": None if self.winner else self.players[self.turn],
            "players": list(self.players), "winner_uid": self.winner,
            "legend": {str(r): CN[r] for r in RANK_NAMES},
        }

    def ended(self):
        if self.winner:
            return {"winner_uid": self.winner, "detail": f"{self._nick(self.winner)} 扛旗获胜"}
        return None

    def _nick_n(self, side):
        return self._nick(self.players[side])